from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .simulation_worlds import (
    derive_repetition_seed,
    generate_observability_world,
    inject_known_effect,
    prepare_observability_design,
    wild_cluster_signs,
)


NORMAL_95_CRITICAL_VALUE = 1.959963984540054


def _validate_effect_grid(effect_sizes_sd: Sequence[float]) -> tuple[float, ...]:
    effects = tuple(float(value) for value in effect_sizes_sd)
    if not effects:
        raise ValueError("effect_sizes_sd must contain at least one declared effect size")
    if any(not np.isfinite(value) for value in effects):
        raise ValueError("effect_sizes_sd values must be finite")
    if len(effects) != len(set(effects)):
        raise ValueError("effect_sizes_sd values must be unique")
    return effects


def _condition_label(delta_sd: float) -> str:
    if delta_sd == 0.0:
        return "null"
    return "positive_injection" if delta_sd > 0 else "negative_injection"


def _safe_mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else np.nan


def _safe_median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if len(values) else np.nan


def summarize_observability(repetitions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Aggregate repetition-level detector behavior without hiding interval quality."""
    if repetitions.empty:
        raise ValueError("repetition results must not be empty")

    summary_rows: list[dict[str, Any]] = []
    for effect_size, group in repetitions.groupby("effect_size_sd", sort=True, dropna=False):
        estimated = group.loc[group["estimation_ok"].astype(bool)]
        nonnull = float(effect_size) != 0.0
        summary_rows.append(
            {
                "effect_size_sd": float(effect_size),
                "condition": _condition_label(float(effect_size)),
                "repetitions": int(len(group)),
                "estimated_repetitions": int(len(estimated)),
                "recovery_probability": (
                    _safe_mean(estimated["joint_detection"])
                    if nonnull
                    else np.nan
                ),
                "sign_recovery_rate": (
                    _safe_mean(estimated["sign_recovery"])
                    if nonnull
                    else np.nan
                ),
                "rejection_rate": _safe_mean(estimated["rejected"]),
                "ci_coverage_rate": _safe_mean(estimated["ci_covers_truth"]),
                "median_estimated_effect": _safe_median(estimated["estimated_effect"]),
                "median_estimated_effect_sd": _safe_median(
                    estimated["estimated_effect_sd"]
                ),
                "median_abs_recovery_error": _safe_median(
                    estimated["absolute_recovery_error"]
                ),
                "median_relative_recovery_error": _safe_median(
                    estimated["relative_recovery_error"]
                ),
                "median_ci_width": _safe_median(estimated["ci_width"]),
                "sample_size": int(group["sample_size"].iloc[0]),
                "outcome_sd": float(group["outcome_sd"].iloc[0]),
                "treated": int(group["treated"].iloc[0]),
                "control": int(group["control"].iloc[0]),
                "treatment_share": float(group["treatment_share"].iloc[0]),
            }
        )

    effect_summary = pd.DataFrame(summary_rows).sort_values("effect_size_sd").reset_index(drop=True)
    detection_curve = effect_summary[
        [
            "effect_size_sd",
            "condition",
            "repetitions",
            "recovery_probability",
            "sign_recovery_rate",
            "rejection_rate",
            "ci_coverage_rate",
            "median_estimated_effect",
            "median_estimated_effect_sd",
            "median_ci_width",
        ]
    ].copy()

    null = repetitions.loc[
        repetitions["effect_size_sd"].eq(0.0) & repetitions["estimation_ok"].astype(bool)
    ].copy()
    if null.empty:
        null_summary = pd.DataFrame(
            columns=[
                "condition",
                "repetitions",
                "rejection_rate",
                "coefficient_mean",
                "coefficient_median",
                "coefficient_std",
                "positive_sign_share",
                "negative_sign_share",
                "zero_sign_share",
                "sign_balance",
                "ci_coverage_zero",
            ]
        )
    else:
        coefficient = pd.to_numeric(null["estimated_effect"], errors="coerce").dropna()
        positive = float((coefficient > 0).mean()) if len(coefficient) else np.nan
        negative = float((coefficient < 0).mean()) if len(coefficient) else np.nan
        zero = float((coefficient == 0).mean()) if len(coefficient) else np.nan
        null_summary = pd.DataFrame(
            [
                {
                    "condition": "null",
                    "repetitions": int(len(null)),
                    "rejection_rate": _safe_mean(null["rejected"]),
                    "coefficient_mean": float(coefficient.mean()) if len(coefficient) else np.nan,
                    "coefficient_median": float(coefficient.median()) if len(coefficient) else np.nan,
                    "coefficient_std": (
                        float(coefficient.std(ddof=1)) if len(coefficient) > 1 else 0.0
                    ),
                    "positive_sign_share": positive,
                    "negative_sign_share": negative,
                    "zero_sign_share": zero,
                    "sign_balance": positive - negative if np.isfinite(positive + negative) else np.nan,
                    "ci_coverage_zero": _safe_mean(null["ci_covers_truth"]),
                }
            ]
        )

    return {
        "effect_size_summary": effect_summary,
        "detection_curve": detection_curve,
        "null_calibration_summary": null_summary,
    }


def run_observability_grid(
    frame: pd.DataFrame,
    *,
    effect_sizes_sd: Sequence[float],
    repetitions: int,
    root_seed: int,
    estimator: Callable[[pd.DataFrame, str], Mapping[str, Any]],
    unit_col: str,
    period_col: str,
    country_col: str,
    outcome_col: str = "outcome_value",
    pre_outcome_col: str = "outcome_pre",
    treatment_col: str = "treatment",
    eligible_col: str = "eligible",
    nuisance_formula: str | None = None,
    synthetic_outcome_col: str = "_observability_outcome",
    critical_value: float = NORMAL_95_CRITICAL_VALUE,
) -> dict[str, pd.DataFrame]:
    """Characterize recovery over a declared effect grid on an empirical E2 frame.

    The stochastic component is generated by the shared paired-world engine.
    A fixed repetition/root seed produces the same GID-level residual sign
    realization for every declared effect size; only the injected truth changes.
    """
    effects = _validate_effect_grid(effect_sizes_sd)
    draws = int(repetitions)
    if draws <= 0:
        raise ValueError("repetitions must be positive")
    root = int(root_seed)
    if root < 0:
        raise ValueError("root_seed must be non-negative")
    cv = float(critical_value)
    if not np.isfinite(cv) or cv <= 0:
        raise ValueError("critical_value must be finite and positive")

    design = prepare_observability_design(
        frame,
        unit_col=unit_col,
        period_col=period_col,
        country_col=country_col,
        outcome_col=outcome_col,
        pre_outcome_col=pre_outcome_col,
        treatment_col=treatment_col,
        eligible_col=eligible_col,
        nuisance_formula=nuisance_formula,
    )

    rows: list[dict[str, Any]] = []
    for repetition_id in range(draws):
        for delta_sd in effects:
            world = generate_observability_world(
                design,
                repetition_id=repetition_id,
                root_seed=root,
                delta_sd=delta_sd,
                synthetic_outcome_col=synthetic_outcome_col,
            )
            estimate = dict(estimator(world.frame, synthetic_outcome_col))
            ok = bool(estimate.get("ok", False))
            effect = float(estimate.get("effect", np.nan)) if ok else np.nan
            se = float(estimate.get("se", np.nan)) if ok else np.nan
            finite_interval = ok and np.isfinite(effect) and np.isfinite(se) and se >= 0
            ci_low = effect - cv * se if finite_interval else np.nan
            ci_high = effect + cv * se if finite_interval else np.nan
            z = effect / se if finite_interval and se > 0 else np.nan
            rejected = bool(np.isfinite(z) and abs(z) >= cv) if ok else False
            ci_covers = (
                bool(ci_low <= world.truth_effect <= ci_high) if finite_interval else False
            )
            sign_recovery = (
                bool(np.sign(effect) == np.sign(world.truth_effect))
                if ok and world.truth_effect != 0.0 and np.isfinite(effect)
                else np.nan
            )
            joint_detection = (
                bool(sign_recovery and rejected)
                if world.truth_effect != 0.0
                and ok
                and isinstance(sign_recovery, (bool, np.bool_))
                else np.nan
            )
            abs_error = (
                abs(effect - world.truth_effect) if ok and np.isfinite(effect) else np.nan
            )
            rel_error = (
                abs_error / abs(world.truth_effect)
                if world.truth_effect != 0.0 and np.isfinite(abs_error)
                else np.nan
            )

            rows.append(
                {
                    "condition": _condition_label(delta_sd),
                    "effect_size_sd": float(delta_sd),
                    "truth_effect": world.truth_effect,
                    "root_seed": root,
                    "repetition_id": repetition_id,
                    "derived_seed": world.derived_seed,
                    "world_id": world.world_id,
                    "estimation_ok": ok,
                    "estimate_reason": str(estimate.get("reason", "")),
                    "estimated_effect": effect,
                    "estimated_effect_sd": (
                        effect / design.outcome_sd if ok and np.isfinite(effect) else np.nan
                    ),
                    "standard_error": se,
                    "z": z,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "ci_width": ci_high - ci_low if finite_interval else np.nan,
                    "sign_recovery": sign_recovery,
                    "rejected": rejected,
                    "joint_detection": joint_detection,
                    "ci_covers_truth": ci_covers,
                    "absolute_recovery_error": abs_error,
                    "relative_recovery_error": rel_error,
                    "sample_size": (
                        int(estimate.get("n", len(design.sample)))
                        if ok
                        else int(len(design.sample))
                    ),
                    "n_units": (
                        int(estimate.get("n_units", design.sample[unit_col].nunique()))
                        if ok
                        else int(design.sample[unit_col].nunique())
                    ),
                    "treated": int(estimate.get("n_treated", design.treated)) if ok else design.treated,
                    "control": int(estimate.get("n_control", design.control)) if ok else design.control,
                    "treatment_share": float(design.treatment_share),
                    "outcome_sd": design.outcome_sd,
                }
            )

    repetitions_table = pd.DataFrame(rows)
    summaries = summarize_observability(repetitions_table)
    return {
        "repetition_results": repetitions_table,
        **summaries,
    }


def run_e2_observability(
    frame: pd.DataFrame,
    calibration_spec: Any,
    *,
    effect_sizes_sd: Sequence[float],
    repetitions: int,
    root_seed: int,
) -> dict[str, pd.DataFrame]:
    """Reference adapter for the existing FCV E2 estimator/design."""
    from .calibration import calibration_estimate

    def estimator(sim: pd.DataFrame, outcome_name: str) -> Mapping[str, Any]:
        return calibration_estimate(sim, calibration_spec, outcome_col=outcome_name)

    return run_observability_grid(
        frame,
        effect_sizes_sd=effect_sizes_sd,
        repetitions=repetitions,
        root_seed=root_seed,
        estimator=estimator,
        unit_col=calibration_spec.unit_col,
        period_col=calibration_spec.period_col,
        country_col=calibration_spec.country_col,
    )


def write_observability_outputs(result: Mapping[str, pd.DataFrame], out_dir: str | Path) -> Path:
    """Write sanitized detector summaries; never write the empirical frame."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs = {
        "repetition_results": "repetition_results.csv",
        "effect_size_summary": "effect_size_summary.csv",
        "detection_curve": "detection_curve.csv",
        "null_calibration_summary": "null_calibration_summary.csv",
    }
    for key, filename in outputs.items():
        table = result.get(key)
        if not isinstance(table, pd.DataFrame):
            raise TypeError(f"observability result {key!r} must be a pandas DataFrame")
        table.to_csv(out / filename, index=False)
    return out


__all__ = [
    "NORMAL_95_CRITICAL_VALUE",
    "derive_repetition_seed",
    "wild_cluster_signs",
    "inject_known_effect",
    "prepare_observability_design",
    "generate_observability_world",
    "summarize_observability",
    "run_observability_grid",
    "run_e2_observability",
    "write_observability_outputs",
]
