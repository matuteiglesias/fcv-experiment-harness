from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm, t as student_t

from .simulation_worlds import (
    ObservabilityDesign,
    generate_observability_world,
    prepare_observability_design,
)


_ALLOWED_KINDS = {
    "cluster_normal",
    "cluster_t",
    "wild_cluster_bootstrap",
}


@dataclass(frozen=True)
class InferenceMethodSpec:
    """One predeclared uncertainty procedure over an unchanged OLS estimand."""

    method_id: str
    kind: str
    cluster_col: str
    bootstrap_repetitions: int = 0
    bootstrap_root_seed: int = 0

    def __post_init__(self) -> None:
        if not self.method_id:
            raise ValueError("inference method_id must be non-empty")
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported inference kind: {self.kind!r}")
        if not self.cluster_col:
            raise ValueError("inference cluster_col must be non-empty")
        if self.kind == "wild_cluster_bootstrap":
            if self.bootstrap_repetitions < 19:
                raise ValueError("wild cluster bootstrap requires at least 19 repetitions")
            if self.bootstrap_root_seed < 0:
                raise ValueError("bootstrap_root_seed must be non-negative")
        elif self.bootstrap_repetitions != 0:
            raise ValueError("bootstrap_repetitions is only valid for wild cluster bootstrap")


@dataclass(frozen=True)
class PreparedInferenceDesign:
    """Fixed OLS design matrix reused across paired synthetic worlds."""

    sample: pd.DataFrame
    exog: np.ndarray
    exog_names: tuple[str, ...]
    pinv_exog: np.ndarray
    xtx_inv: np.ndarray
    treatment_index: int
    restricted_exog: np.ndarray
    restricted_pinv: np.ndarray
    unit_col: str
    period_col: str
    country_col: str
    treatment_col: str
    pre_outcome_col: str

    @property
    def n(self) -> int:
        return int(self.exog.shape[0])

    @property
    def k(self) -> int:
        return int(self.exog.shape[1])


def default_e2_inference_methods(
    *,
    unit_col: str,
    country_col: str,
    wild_bootstrap_repetitions: int = 399,
    wild_bootstrap_root_seed: int = 20260908,
) -> tuple[InferenceMethodSpec, ...]:
    """Return the first bounded FCV uncertainty family; Conley is intentionally deferred."""
    return (
        InferenceMethodSpec(
            method_id="ADM2_CLUSTER",
            kind="cluster_normal",
            cluster_col=unit_col,
        ),
        InferenceMethodSpec(
            method_id="COUNTRY_CLUSTER_T",
            kind="cluster_t",
            cluster_col=country_col,
        ),
        InferenceMethodSpec(
            method_id="WILD_COUNTRY_BOOTSTRAP",
            kind="wild_cluster_bootstrap",
            cluster_col=country_col,
            bootstrap_repetitions=int(wild_bootstrap_repetitions),
            bootstrap_root_seed=int(wild_bootstrap_root_seed),
        ),
    )


def prepare_inference_design(
    design: ObservabilityDesign,
) -> PreparedInferenceDesign:
    """Freeze the OLS design matrix shared by every method and synthetic world."""
    formula = (
        f"{design.outcome_col} ~ {design.treatment_col} + {design.pre_outcome_col} + "
        f"C({design.period_col}) + C({design.country_col})"
    )
    model = smf.ols(formula, data=design.sample)
    exog = np.asarray(model.exog, dtype=float)
    names = tuple(str(name) for name in model.exog_names)
    if design.treatment_col not in names:
        raise ValueError("treatment coefficient is absent from the inference design")
    treatment_index = names.index(design.treatment_col)
    pinv = np.linalg.pinv(exog)
    xtx_inv = pinv @ pinv.T
    restricted_exog = np.delete(exog, treatment_index, axis=1)
    restricted_pinv = np.linalg.pinv(restricted_exog)
    return PreparedInferenceDesign(
        sample=design.sample.copy(),
        exog=exog,
        exog_names=names,
        pinv_exog=pinv,
        xtx_inv=xtx_inv,
        treatment_index=treatment_index,
        restricted_exog=restricted_exog,
        restricted_pinv=restricted_pinv,
        unit_col=design.unit_col,
        period_col=design.period_col,
        country_col=design.country_col,
        treatment_col=design.treatment_col,
        pre_outcome_col=design.pre_outcome_col,
    )


def _group_codes(sample: pd.DataFrame, column: str) -> tuple[np.ndarray, tuple[str, ...]]:
    if column not in sample.columns:
        raise KeyError(f"inference cluster column is absent: {column!r}")
    values = sample[column].astype(str)
    labels = tuple(sorted(values.unique().tolist()))
    if len(labels) < 2:
        raise ValueError(f"inference requires at least two clusters in {column!r}")
    mapping = {label: index for index, label in enumerate(labels)}
    codes = values.map(mapping).to_numpy(dtype=int)
    return codes, labels


def _ols_components(
    prepared: PreparedInferenceDesign,
    outcome: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(outcome, dtype=float)
    if y.shape != (prepared.n,):
        raise ValueError("synthetic outcome length does not match fixed inference design")
    beta = prepared.pinv_exog @ y
    residual = y - prepared.exog @ beta
    return beta, residual


def _cluster_standard_error(
    prepared: PreparedInferenceDesign,
    residual: np.ndarray,
    cluster_col: str,
) -> tuple[float, int]:
    codes, labels = _group_codes(prepared.sample, cluster_col)
    groups = len(labels)
    scores = np.zeros((groups, prepared.k), dtype=float)
    np.add.at(scores, codes, prepared.exog * residual[:, None])
    meat = scores.T @ scores
    covariance = prepared.xtx_inv @ meat @ prepared.xtx_inv
    if groups > 1 and prepared.n > prepared.k:
        correction = (groups / (groups - 1.0)) * (
            (prepared.n - 1.0) / (prepared.n - prepared.k)
        )
        covariance *= correction
    variance = float(covariance[prepared.treatment_index, prepared.treatment_index])
    se = float(np.sqrt(max(variance, 0.0)))
    return se, groups


def _stable_method_seed(root_seed: int, repetition_id: int, method_id: str) -> int:
    method_digest = hashlib.sha256(method_id.encode("utf-8")).digest()
    method_key = int.from_bytes(method_digest[:8], "big", signed=False)
    state = np.random.SeedSequence(
        [int(root_seed), int(repetition_id), method_key]
    ).generate_state(1, dtype=np.uint64)
    return int(state[0])


def _cluster_inference(
    prepared: PreparedInferenceDesign,
    beta: np.ndarray,
    residual: np.ndarray,
    method: InferenceMethodSpec,
    *,
    alpha: float,
) -> dict[str, Any]:
    effect = float(beta[prepared.treatment_index])
    se, clusters = _cluster_standard_error(prepared, residual, method.cluster_col)
    statistic = effect / se if se > 0 else np.nan
    if method.kind == "cluster_normal":
        critical = float(norm.ppf(1.0 - alpha / 2.0))
        p_value = float(2.0 * norm.sf(abs(statistic))) if np.isfinite(statistic) else np.nan
        reference_df = np.nan
        reference_distribution = "normal"
    else:
        reference_df = float(clusters - 1)
        critical = float(student_t.ppf(1.0 - alpha / 2.0, reference_df))
        p_value = (
            float(2.0 * student_t.sf(abs(statistic), reference_df))
            if np.isfinite(statistic)
            else np.nan
        )
        reference_distribution = "student_t_cluster_df"
    return {
        "ok": bool(np.isfinite(effect) and np.isfinite(se) and se >= 0),
        "effect": effect,
        "se": se,
        "statistic": statistic,
        "p_value": p_value,
        "ci_low": effect - critical * se,
        "ci_high": effect + critical * se,
        "critical_value": critical,
        "reference_df": reference_df,
        "reference_distribution": reference_distribution,
        "n_clusters": clusters,
    }


def _wild_cluster_bootstrap_inference(
    prepared: PreparedInferenceDesign,
    outcome: np.ndarray,
    beta: np.ndarray,
    residual: np.ndarray,
    method: InferenceMethodSpec,
    *,
    alpha: float,
    repetition_id: int,
) -> dict[str, Any]:
    """Rademacher wild-country coefficient bootstrap with a null-imposed p-value.

    The point estimate remains the exact same OLS coefficient used by every method.
    An unrestricted wild bootstrap supplies the bootstrap standard deviation and
    basic confidence interval. A restricted model without treatment supplies the
    null-imposed coefficient distribution used for the two-sided zero-effect test.
    This deliberately calibrates uncertainty; it never changes the estimand.
    """
    codes, labels = _group_codes(prepared.sample, method.cluster_col)
    groups = len(labels)
    effect = float(beta[prepared.treatment_index])
    coefficient_map = prepared.pinv_exog[prepared.treatment_index, :]

    restricted_beta = prepared.restricted_pinv @ outcome
    restricted_fitted = prepared.restricted_exog @ restricted_beta
    restricted_residual = outcome - restricted_fitted
    restricted_center = float(coefficient_map @ restricted_fitted)

    unrestricted_contrib = np.bincount(
        codes,
        weights=coefficient_map * residual,
        minlength=groups,
    )
    null_contrib = np.bincount(
        codes,
        weights=coefficient_map * restricted_residual,
        minlength=groups,
    )

    derived_seed = _stable_method_seed(
        method.bootstrap_root_seed,
        repetition_id,
        method.method_id,
    )
    rng = np.random.default_rng(derived_seed)
    signs = rng.choice(
        np.array([-1.0, 1.0]),
        size=(int(method.bootstrap_repetitions), groups),
    )
    unrestricted_delta = signs @ unrestricted_contrib
    bootstrap_effect = effect + unrestricted_delta
    null_effect = restricted_center + signs @ null_contrib

    se = float(np.std(bootstrap_effect, ddof=1))
    q_low, q_high = np.quantile(
        unrestricted_delta,
        [alpha / 2.0, 1.0 - alpha / 2.0],
    )
    ci_low = float(effect - q_high)
    ci_high = float(effect - q_low)
    p_value = float(
        (1 + np.count_nonzero(np.abs(null_effect) >= abs(effect)))
        / (int(method.bootstrap_repetitions) + 1)
    )
    statistic = effect / se if se > 0 else np.nan
    return {
        "ok": bool(np.isfinite(effect) and np.isfinite(se) and se >= 0),
        "effect": effect,
        "se": se,
        "statistic": statistic,
        "p_value": p_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "critical_value": np.nan,
        "reference_df": np.nan,
        "reference_distribution": "wild_cluster_rademacher_coefficient_bootstrap",
        "n_clusters": groups,
        "bootstrap_repetitions": int(method.bootstrap_repetitions),
        "bootstrap_derived_seed": derived_seed,
    }


def estimate_with_inference_method(
    prepared: PreparedInferenceDesign,
    outcome: np.ndarray,
    method: InferenceMethodSpec,
    *,
    alpha: float,
    repetition_id: int,
) -> dict[str, Any]:
    beta, residual = _ols_components(prepared, outcome)
    if method.kind in {"cluster_normal", "cluster_t"}:
        result = _cluster_inference(
            prepared,
            beta,
            residual,
            method,
            alpha=alpha,
        )
    elif method.kind == "wild_cluster_bootstrap":
        result = _wild_cluster_bootstrap_inference(
            prepared,
            np.asarray(outcome, dtype=float),
            beta,
            residual,
            method,
            alpha=alpha,
            repetition_id=repetition_id,
        )
    else:  # pragma: no cover - dataclass validation prevents this
        raise AssertionError(method.kind)
    result.update(
        {
            "method_id": method.method_id,
            "method_kind": method.kind,
            "cluster_col": method.cluster_col,
            "n": prepared.n,
            "k": prepared.k,
        }
    )
    return result


def wilson_interval(
    successes: int,
    trials: int,
    *,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Wilson binomial interval for Monte Carlo proportions."""
    n = int(trials)
    x = int(successes)
    if n <= 0 or x < 0 or x > n:
        return np.nan, np.nan
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be between zero and one")
    z = float(norm.ppf(0.5 + confidence / 2.0))
    p = x / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return float(max(0.0, center - half)), float(min(1.0, center + half))


def _rate_row(
    group: pd.DataFrame,
    column: str,
    *,
    confidence: float,
) -> tuple[int, int, float, float, float]:
    values = group[column].dropna().astype(bool)
    trials = int(len(values))
    successes = int(values.sum())
    rate = successes / trials if trials else np.nan
    low, high = wilson_interval(successes, trials, confidence=confidence)
    return successes, trials, float(rate), low, high


def summarize_inference_calibration(
    repetitions: pd.DataFrame,
    *,
    alpha: float,
    monte_carlo_confidence: float,
) -> dict[str, pd.DataFrame]:
    if repetitions.empty:
        raise ValueError("inference calibration repetition table must not be empty")

    coverage_rows: list[dict[str, Any]] = []
    width_rows: list[dict[str, Any]] = []
    power_rows: list[dict[str, Any]] = []
    null_rows: list[dict[str, Any]] = []
    for (method_id, effect_size), group in repetitions.groupby(
        ["method_id", "effect_size_sd"], sort=True, dropna=False
    ):
        estimated = group.loc[group["estimation_ok"].astype(bool)].copy()
        covered, trials, coverage, cov_low, cov_high = _rate_row(
            estimated,
            "ci_covers_truth",
            confidence=monte_carlo_confidence,
        )
        coverage_rows.append(
            {
                "method_id": method_id,
                "effect_size_sd": float(effect_size),
                "estimated_repetitions": trials,
                "covered_repetitions": covered,
                "ci_coverage_rate": coverage,
                "coverage_mc_low": cov_low,
                "coverage_mc_high": cov_high,
                "nominal_coverage": 1.0 - alpha,
                "nominal_inside_mc_interval": bool(
                    np.isfinite(cov_low)
                    and cov_low <= 1.0 - alpha <= cov_high
                ),
            }
        )
        width_rows.append(
            {
                "method_id": method_id,
                "effect_size_sd": float(effect_size),
                "estimated_repetitions": int(len(estimated)),
                "median_ci_width": float(estimated["ci_width"].median()) if len(estimated) else np.nan,
                "mean_ci_width": float(estimated["ci_width"].mean()) if len(estimated) else np.nan,
                "median_standard_error": float(estimated["standard_error"].median()) if len(estimated) else np.nan,
            }
        )
        rejected, r_trials, rejection_rate, rej_low, rej_high = _rate_row(
            estimated,
            "rejected",
            confidence=monte_carlo_confidence,
        )
        if float(effect_size) == 0.0:
            null_rows.append(
                {
                    "method_id": method_id,
                    "repetitions": r_trials,
                    "rejections": rejected,
                    "false_positive_rate": rejection_rate,
                    "false_positive_mc_low": rej_low,
                    "false_positive_mc_high": rej_high,
                    "nominal_alpha": alpha,
                    "alpha_inside_mc_interval": bool(
                        np.isfinite(rej_low) and rej_low <= alpha <= rej_high
                    ),
                    "ci_coverage_zero": coverage,
                    "coverage_mc_low": cov_low,
                    "coverage_mc_high": cov_high,
                    "coefficient_mean": float(estimated["estimated_effect"].mean()) if len(estimated) else np.nan,
                    "coefficient_median": float(estimated["estimated_effect"].median()) if len(estimated) else np.nan,
                }
            )
        else:
            detected, d_trials, detection_rate, det_low, det_high = _rate_row(
                estimated,
                "joint_detection",
                confidence=monte_carlo_confidence,
            )
            power_rows.append(
                {
                    "method_id": method_id,
                    "effect_size_sd": float(effect_size),
                    "repetitions": r_trials,
                    "rejections": rejected,
                    "rejection_rate": rejection_rate,
                    "rejection_mc_low": rej_low,
                    "rejection_mc_high": rej_high,
                    "joint_detections": detected,
                    "joint_detection_rate": detection_rate,
                    "joint_detection_mc_low": det_low,
                    "joint_detection_mc_high": det_high,
                }
            )

    coverage = pd.DataFrame(coverage_rows).sort_values(["method_id", "effect_size_sd"])
    widths = pd.DataFrame(width_rows).sort_values(["method_id", "effect_size_sd"])
    power = pd.DataFrame(power_rows).sort_values(["method_id", "effect_size_sd"])
    null = pd.DataFrame(null_rows).sort_values("method_id")

    pair_rows: list[dict[str, Any]] = []
    methods = sorted(repetitions["method_id"].unique().tolist())
    for effect_size in sorted(repetitions["effect_size_sd"].unique().tolist()):
        effect_group = repetitions.loc[repetitions["effect_size_sd"].eq(effect_size)]
        for method_a, method_b in itertools.combinations(methods, 2):
            left = effect_group.loc[effect_group["method_id"].eq(method_a)].set_index("repetition_id")
            right = effect_group.loc[effect_group["method_id"].eq(method_b)].set_index("repetition_id")
            paired = left.join(right, lsuffix="_a", rsuffix="_b", how="inner")
            if paired.empty:
                continue
            effect_diff = paired["estimated_effect_b"] - paired["estimated_effect_a"]
            pair_rows.append(
                {
                    "effect_size_sd": float(effect_size),
                    "method_a": method_a,
                    "method_b": method_b,
                    "paired_repetitions": int(len(paired)),
                    "max_abs_point_estimate_difference": float(effect_diff.abs().max()),
                    "median_standard_error_difference_b_minus_a": float(
                        (paired["standard_error_b"] - paired["standard_error_a"]).median()
                    ),
                    "median_ci_width_difference_b_minus_a": float(
                        (paired["ci_width_b"] - paired["ci_width_a"]).median()
                    ),
                    "rejection_disagreement_rate": float(
                        paired["rejected_a"].ne(paired["rejected_b"]).mean()
                    ),
                    "coverage_disagreement_rate": float(
                        paired["ci_covers_truth_a"].ne(paired["ci_covers_truth_b"]).mean()
                    ),
                }
            )
    paired = pd.DataFrame(pair_rows)

    summary_rows: list[dict[str, Any]] = []
    positive_effects = sorted(
        effect for effect in repetitions["effect_size_sd"].unique().tolist() if float(effect) > 0
    )
    smallest_positive = float(positive_effects[0]) if positive_effects else np.nan
    for method_id in methods:
        nrow = null.loc[null["method_id"].eq(method_id)]
        prow = power.loc[
            power["method_id"].eq(method_id)
            & power["effect_size_sd"].eq(smallest_positive)
        ]
        wrow = widths.loc[
            widths["method_id"].eq(method_id)
            & widths["effect_size_sd"].eq(smallest_positive)
        ]
        method_rows = repetitions.loc[repetitions["method_id"].eq(method_id)]
        summary_rows.append(
            {
                "method_id": method_id,
                "method_kind": str(method_rows["method_kind"].iloc[0]),
                "cluster_col": str(method_rows["cluster_col"].iloc[0]),
                "null_false_positive_rate": float(nrow["false_positive_rate"].iloc[0]) if len(nrow) else np.nan,
                "null_false_positive_mc_low": float(nrow["false_positive_mc_low"].iloc[0]) if len(nrow) else np.nan,
                "null_false_positive_mc_high": float(nrow["false_positive_mc_high"].iloc[0]) if len(nrow) else np.nan,
                "null_ci_coverage": float(nrow["ci_coverage_zero"].iloc[0]) if len(nrow) else np.nan,
                "smallest_positive_effect_sd": smallest_positive,
                "power_at_smallest_effect": float(prow["rejection_rate"].iloc[0]) if len(prow) else np.nan,
                "joint_detection_at_smallest_effect": float(prow["joint_detection_rate"].iloc[0]) if len(prow) else np.nan,
                "median_ci_width_at_smallest_effect": float(wrow["median_ci_width"].iloc[0]) if len(wrow) else np.nan,
                "median_se_at_smallest_effect": float(wrow["median_standard_error"].iloc[0]) if len(wrow) else np.nan,
            }
        )
    method_summary = pd.DataFrame(summary_rows).sort_values("method_id")

    return {
        "method_summary": method_summary,
        "coverage_by_effect": coverage,
        "null_size": null,
        "power_by_effect": power,
        "ci_width_by_effect": widths,
        "paired_method_differences": paired,
    }


def run_inference_calibration(
    frame: pd.DataFrame,
    calibration_spec: Any,
    *,
    effect_sizes_sd: Sequence[float],
    repetitions: int,
    root_seed: int,
    methods: Sequence[InferenceMethodSpec] | None = None,
    alpha: float = 0.05,
    monte_carlo_confidence: float = 0.95,
) -> dict[str, Any]:
    """Compare uncertainty procedures on identical real-frame synthetic worlds.

    Every method sees the same OLS design, coefficient, synthetic truth and
    stochastic realization. Only the uncertainty procedure changes. The result
    is calibration evidence, never an automatic method-selection score.
    """
    effects = tuple(float(value) for value in effect_sizes_sd)
    if not effects or len(effects) != len(set(effects)):
        raise ValueError("effect_sizes_sd must be non-empty and unique")
    if int(repetitions) <= 0:
        raise ValueError("repetitions must be positive")
    if int(root_seed) < 0:
        raise ValueError("root_seed must be non-negative")
    if not (0.0 < float(alpha) < 1.0):
        raise ValueError("alpha must be between zero and one")

    selected = tuple(methods) if methods is not None else default_e2_inference_methods(
        unit_col=calibration_spec.unit_col,
        country_col=calibration_spec.country_col,
    )
    if not selected:
        raise ValueError("at least one inference method is required")
    ids = [method.method_id for method in selected]
    if len(ids) != len(set(ids)):
        raise ValueError("inference method IDs must be unique")

    design = prepare_observability_design(
        frame,
        unit_col=calibration_spec.unit_col,
        period_col=calibration_spec.period_col,
        country_col=calibration_spec.country_col,
    )
    prepared = prepare_inference_design(design)

    rows: list[dict[str, Any]] = []
    for repetition_id in range(int(repetitions)):
        for delta_sd in effects:
            world = generate_observability_world(
                design,
                repetition_id=repetition_id,
                root_seed=int(root_seed),
                delta_sd=delta_sd,
                synthetic_outcome_col="_inference_calibration_outcome",
            )
            outcome = pd.to_numeric(
                world.frame[world.stochastic_outcome_col], errors="coerce"
            ).to_numpy(dtype=float)
            world_effects: list[float] = []
            for method in selected:
                estimate = estimate_with_inference_method(
                    prepared,
                    outcome,
                    method,
                    alpha=float(alpha),
                    repetition_id=repetition_id,
                )
                ok = bool(estimate["ok"])
                effect = float(estimate["effect"]) if ok else np.nan
                ci_low = float(estimate["ci_low"]) if ok else np.nan
                ci_high = float(estimate["ci_high"]) if ok else np.nan
                p_value = float(estimate["p_value"]) if ok else np.nan
                rejected = bool(ok and np.isfinite(p_value) and p_value < alpha)
                covers = bool(ok and ci_low <= world.truth_effect <= ci_high)
                sign_recovery = (
                    bool(np.sign(effect) == np.sign(world.truth_effect))
                    if ok and world.truth_effect != 0.0 and np.isfinite(effect)
                    else np.nan
                )
                joint_detection = (
                    bool(sign_recovery and rejected)
                    if world.truth_effect != 0.0
                    and isinstance(sign_recovery, (bool, np.bool_))
                    else np.nan
                )
                world_effects.append(effect)
                rows.append(
                    {
                        "world_id": world.world_id,
                        "repetition_id": repetition_id,
                        "world_derived_seed": world.derived_seed,
                        "effect_size_sd": float(delta_sd),
                        "truth_effect": world.truth_effect,
                        "outcome_sd": design.outcome_sd,
                        "method_id": method.method_id,
                        "method_kind": method.kind,
                        "cluster_col": method.cluster_col,
                        "estimation_ok": ok,
                        "estimated_effect": effect,
                        "estimated_effect_sd": effect / design.outcome_sd if ok else np.nan,
                        "standard_error": float(estimate["se"]) if ok else np.nan,
                        "statistic": float(estimate["statistic"]) if ok else np.nan,
                        "p_value": p_value,
                        "rejected": rejected,
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                        "ci_width": ci_high - ci_low if ok else np.nan,
                        "ci_covers_truth": covers,
                        "sign_recovery": sign_recovery,
                        "joint_detection": joint_detection,
                        "reference_distribution": estimate.get("reference_distribution", ""),
                        "reference_df": estimate.get("reference_df", np.nan),
                        "n_clusters": estimate.get("n_clusters", np.nan),
                        "n": prepared.n,
                        "treated": design.treated,
                        "control": design.control,
                    }
                )
            finite_effects = [value for value in world_effects if np.isfinite(value)]
            if finite_effects and max(finite_effects) - min(finite_effects) > 1e-10:
                raise AssertionError(
                    "inference methods changed the OLS point estimate on the same synthetic world"
                )

    repetition_table = pd.DataFrame(rows)
    summaries = summarize_inference_calibration(
        repetition_table,
        alpha=float(alpha),
        monte_carlo_confidence=float(monte_carlo_confidence),
    )
    spec_payload = {
        "purpose": "calibration",
        "estimand_policy": "same_ols_point_estimate_only_uncertainty_changes",
        "world_generator": "paired_gid_wild_residual_sign_flip",
        "effect_sizes_sd": list(effects),
        "repetitions": int(repetitions),
        "root_seed": int(root_seed),
        "alpha": float(alpha),
        "monte_carlo_confidence": float(monte_carlo_confidence),
        "methods": [asdict(method) for method in selected],
        "conley_status": "DEFERRED_UNTIL_GOVERNED_COORDINATES_AND_DISTANCE_SEMANTICS",
    }
    return {
        "repetition_results": repetition_table,
        "inference_spec": spec_payload,
        **summaries,
    }


def write_inference_calibration_outputs(
    result: Mapping[str, Any],
    out_dir: str | Path,
) -> Path:
    """Write aggregate inference-characterization evidence; never write the frame."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "method_summary": "method_summary.csv",
        "coverage_by_effect": "coverage_by_effect.csv",
        "null_size": "null_size.csv",
        "power_by_effect": "power_by_effect.csv",
        "ci_width_by_effect": "ci_width_by_effect.csv",
        "paired_method_differences": "paired_method_differences.csv",
    }
    for key, filename in tables.items():
        table = result.get(key)
        if not isinstance(table, pd.DataFrame):
            raise TypeError(f"inference calibration result {key!r} must be a DataFrame")
        table.to_csv(out / filename, index=False)
    spec = result.get("inference_spec")
    if not isinstance(spec, Mapping):
        raise TypeError("inference calibration inference_spec must be a mapping")
    (out / "inference_spec.json").write_text(
        json.dumps(dict(spec), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


__all__ = [
    "InferenceMethodSpec",
    "PreparedInferenceDesign",
    "default_e2_inference_methods",
    "prepare_inference_design",
    "estimate_with_inference_method",
    "wilson_interval",
    "summarize_inference_calibration",
    "run_inference_calibration",
    "write_inference_calibration_outputs",
]
