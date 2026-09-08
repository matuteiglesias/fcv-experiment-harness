from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .current_e2_reference import CurrentE2ReferenceSpec
from .measurement_projection import project_empirical_measurement, write_projection_report
from .reference_identity import stable_frame_sha256


FALSIFICATION_SUITE_SCHEMA = "current_e2_falsification_battery.v1"


class CurrentE2FalsificationError(ValueError):
    """Raised when R4 is not bound to the frozen current-E2 reference."""


@dataclass(frozen=True)
class CurrentE2FalsificationSpec:
    suite_id: str
    purpose: str
    reference_id: str
    primary_cell_id: str
    required_analysis_identity_sha256: str
    required_primary_frame_sha256: str
    deep_pre_timing_offset: int
    future_treatment_timing_offset: int
    current_outcome_timing_offset: int
    permutation_policy: str
    permutation_repetitions: int
    permutation_root_seed: int

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2FalsificationSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != FALSIFICATION_SUITE_SCHEMA:
            raise CurrentE2FalsificationError("unsupported current E2 falsification suite schema")
        policy = str(raw.get("permutation_policy", ""))
        if policy != "within_country_complete_treatment_history":
            raise CurrentE2FalsificationError("unsupported current E2 permutation policy")
        deep = int(raw.get("deep_pre_timing_offset", -2))
        future = int(raw.get("future_treatment_timing_offset", 1))
        current = int(raw.get("current_outcome_timing_offset", 0))
        if deep >= -1:
            raise CurrentE2FalsificationError("deep pre placebo must precede the existing t-1 placebo")
        if future <= 0 or current != 0:
            raise CurrentE2FalsificationError("future-treatment placebo requires future treatment and t outcome")
        reps = int(raw.get("permutation_repetitions", 1000))
        seed = int(raw.get("permutation_root_seed", 20260908))
        if reps < 99 or seed < 0:
            raise CurrentE2FalsificationError("invalid permutation repetitions/root seed")
        return cls(
            suite_id=str(raw["suite_id"]),
            purpose=str(raw.get("purpose", "calibration")),
            reference_id=str(raw["reference_id"]),
            primary_cell_id=str(raw["primary_cell_id"]),
            required_analysis_identity_sha256=str(raw["required_analysis_identity_sha256"]),
            required_primary_frame_sha256=str(raw["required_primary_frame_sha256"]),
            deep_pre_timing_offset=deep,
            future_treatment_timing_offset=future,
            current_outcome_timing_offset=current,
            permutation_policy=policy,
            permutation_repetitions=reps,
            permutation_root_seed=seed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FALSIFICATION_SUITE_SCHEMA,
            "suite_id": self.suite_id,
            "purpose": self.purpose,
            "reference_id": self.reference_id,
            "primary_cell_id": self.primary_cell_id,
            "required_analysis_identity_sha256": self.required_analysis_identity_sha256,
            "required_primary_frame_sha256": self.required_primary_frame_sha256,
            "deep_pre_timing_offset": self.deep_pre_timing_offset,
            "future_treatment_timing_offset": self.future_treatment_timing_offset,
            "current_outcome_timing_offset": self.current_outcome_timing_offset,
            "permutation_policy": self.permutation_policy,
            "permutation_repetitions": self.permutation_repetitions,
            "permutation_root_seed": self.permutation_root_seed,
        }


def _require_binding(
    result: Mapping[str, Any],
    suite: CurrentE2FalsificationSpec,
) -> tuple[CurrentE2ReferenceSpec, Mapping[str, Any], Mapping[str, Any], pd.DataFrame, str]:
    spec = result.get("spec")
    if not isinstance(spec, CurrentE2ReferenceSpec):
        raise CurrentE2FalsificationError("R4 requires a CurrentE2ReferenceSpec")
    if suite.purpose != "calibration" or spec.purpose != "calibration":
        raise CurrentE2FalsificationError("R4 must remain calibration-only")
    if suite.reference_id != spec.reference_id or suite.primary_cell_id != spec.primary_cell.cell_id:
        raise CurrentE2FalsificationError("R4 reference/PRIMARY identity mismatch")

    identity = result.get("reference_identity")
    if not isinstance(identity, Mapping):
        raise CurrentE2FalsificationError("R4 requires reference_identity")
    lock = identity.get("lock")
    if not isinstance(lock, Mapping) or lock.get("verified") is not True:
        raise CurrentE2FalsificationError("R4 requires a verified reference lock")
    if identity.get("analysis_identity_sha256") != suite.required_analysis_identity_sha256:
        raise CurrentE2FalsificationError("R4 analysis identity mismatch")

    calibration = result.get("calibration")
    if not isinstance(calibration, Mapping):
        raise CurrentE2FalsificationError("R4 requires calibration results")
    cells = calibration.get("cells")
    if not isinstance(cells, Mapping) or suite.primary_cell_id not in cells:
        raise CurrentE2FalsificationError("R4 PRIMARY cell result missing")
    primary = cells[suite.primary_cell_id]
    if not isinstance(primary, Mapping) or primary.get("estimation_permitted") is not True:
        raise CurrentE2FalsificationError("R4 blocked because PRIMARY hard gates do not pass")
    frame = primary.get("frame")
    if not isinstance(frame, pd.DataFrame):
        raise CurrentE2FalsificationError("R4 requires in-memory PRIMARY frame")
    frame_sha = stable_frame_sha256(frame, unit_col=spec.unit_col, period_col=spec.period_col)
    if frame_sha != suite.required_primary_frame_sha256:
        raise CurrentE2FalsificationError("R4 PRIMARY frame fingerprint drift")
    if identity.get("primary_frame_sha256") != frame_sha:
        raise CurrentE2FalsificationError("R4 reference identity frame fingerprint mismatch")
    return spec, identity, primary, frame, frame_sha


def _placebo_fit(
    frame: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    *,
    outcome_col: str,
    treatment_col: str = "treatment",
) -> dict[str, Any]:
    needed = [outcome_col, treatment_col, spec.unit_col, spec.period_col, spec.country_col]
    sample = frame.loc[frame["eligible"]].dropna(subset=needed).copy()
    if sample.empty or sample[treatment_col].nunique() < 2:
        return {"ok": False, "reason": "placebo sample has no treatment variation"}
    formula = f"{outcome_col} ~ {treatment_col} + C({spec.period_col}) + C({spec.country_col})"
    fit = smf.ols(formula, data=sample).fit(
        cov_type="cluster",
        cov_kwds={"groups": sample[spec.unit_col].to_numpy()},
    )
    effect = float(fit.params[treatment_col])
    se = float(fit.bse[treatment_col])
    sd = float(pd.to_numeric(sample[outcome_col], errors="coerce").std(ddof=1))
    return {
        "ok": True,
        "effect": effect,
        "se": se,
        "z": effect / se if se > 0 else np.nan,
        "std_abs_effect": abs(effect) / sd if sd > 0 else np.nan,
        "effect_sd": effect / sd if sd > 0 else np.nan,
        "outcome_sd": sd,
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "treated": int((sample[treatment_col] == 1).sum()),
        "control": int((sample[treatment_col] == 0).sum()),
        "formula": formula,
    }


def _projection_frame(
    result: Mapping[str, Any],
    spec: CurrentE2ReferenceSpec,
    primary: Mapping[str, Any],
    suite: CurrentE2FalsificationSpec,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel = result.get("panel")
    linkage = result.get("geography_linkage")
    treatment_bundle = result.get("treatment_bundle")
    outcome_bundle = result.get("outcome_bundle")
    if not isinstance(panel, pd.DataFrame) or not isinstance(linkage, pd.DataFrame):
        raise CurrentE2FalsificationError("R4 requires in-memory panel and geography linkage")
    if treatment_bundle is None or outcome_bundle is None:
        raise CurrentE2FalsificationError("R4 requires already-loaded governed measurement bundles")
    experiment = primary.get("experiment_spec")
    if experiment is None:
        raise CurrentE2FalsificationError("R4 requires PRIMARY experiment spec")

    target = panel[[spec.unit_col, spec.period_col]]
    deep_use = replace(
        experiment.outcome,
        role="deep_pre_outcome_placebo",
        timing_offset=suite.deep_pre_timing_offset,
        output_column="outcome_deep_pre",
    )
    current_outcome_use = replace(
        experiment.outcome,
        role="current_outcome_future_treatment_placebo",
        timing_offset=suite.current_outcome_timing_offset,
        output_column="outcome_current",
    )
    future_treatment_use = replace(
        experiment.treatment,
        role="future_treatment_placebo",
        timing_offset=suite.future_treatment_timing_offset,
        output_column="future_treatment_value",
    )
    deep = project_empirical_measurement(
        outcome_bundle,
        target,
        deep_use,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=linkage,
    )
    current = project_empirical_measurement(
        outcome_bundle,
        target,
        current_outcome_use,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=linkage,
    )
    future = project_empirical_measurement(
        treatment_bundle,
        target,
        future_treatment_use,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=linkage,
    )

    base = primary["frame"].copy()
    for projection, value_col, prefix in (
        (deep, "outcome_deep_pre", "deep_pre"),
        (current, "outcome_current", "current_outcome"),
        (future, "future_treatment_value", "future_treatment"),
    ):
        attach = projection.frame[
            [
                spec.unit_col,
                spec.period_col,
                value_col,
                "measurement_period_id",
                "projection_status",
                "projection_detail",
            ]
        ].rename(
            columns={
                "measurement_period_id": f"{prefix}_measurement_period_id",
                "projection_status": f"{prefix}_projection_status",
                "projection_detail": f"{prefix}_projection_detail",
            }
        )
        base = base.merge(
            attach,
            on=[spec.unit_col, spec.period_col],
            how="left",
            validate="one_to_one",
        )

    threshold = float(spec.primary_cell.threshold)
    resolved_future = base["future_treatment_projection_status"].isin(["observed", "structural_zero"])
    base["future_treatment"] = np.where(
        resolved_future,
        pd.to_numeric(base["future_treatment_value"], errors="coerce") > threshold,
        np.nan,
    )
    reports = {
        "deep_pre": deep.report,
        "current_outcome": current.report,
        "future_treatment": future.report,
    }
    return base, reports


def _permutation_null(
    frame: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    *,
    observed_effect: float,
    repetitions: int,
    root_seed: int,
) -> dict[str, Any]:
    needed = [
        "outcome_value",
        "outcome_pre",
        "treatment",
        spec.unit_col,
        spec.period_col,
        spec.country_col,
    ]
    sample = frame.loc[frame["eligible"]].dropna(subset=needed).copy()
    sample = sample.sort_values([spec.country_col, spec.unit_col, spec.period_col]).reset_index(drop=True)
    counts = sample.groupby(spec.unit_col, sort=False)[spec.period_col].nunique()
    if counts.nunique() != 1:
        raise CurrentE2FalsificationError("permutation null requires a balanced complete treatment history")
    period_count = int(counts.iloc[0])

    nuisance_formula = f"outcome_value ~ outcome_pre + C({spec.period_col}) + C({spec.country_col})"
    nuisance_model = smf.ols(nuisance_formula, data=sample)
    z = np.asarray(nuisance_model.exog, dtype=float)
    pinv_z = np.linalg.pinv(z)
    y = pd.to_numeric(sample["outcome_value"], errors="coerce").to_numpy(dtype=float)
    y_resid = y - z @ (pinv_z @ y)

    unit_rows: dict[str, np.ndarray] = {
        str(unit): np.asarray(index, dtype=int)
        for unit, index in sample.groupby(spec.unit_col, sort=False).groups.items()
    }
    unit_country = (
        sample[[spec.unit_col, spec.country_col]]
        .drop_duplicates()
        .assign(**{spec.unit_col: lambda x: x[spec.unit_col].astype(str)})
    )
    country_units = {
        str(country): group[spec.unit_col].astype(str).tolist()
        for country, group in unit_country.groupby(spec.country_col, sort=True)
    }
    treatment = pd.to_numeric(sample["treatment"], errors="coerce").to_numpy(dtype=float)
    histories = {unit: treatment[rows].copy() for unit, rows in unit_rows.items()}
    if any(len(values) != period_count for values in histories.values()):
        raise CurrentE2FalsificationError("permutation history length mismatch")

    rng = np.random.default_rng(int(root_seed))
    effects = np.empty(int(repetitions), dtype=float)
    for rep in range(int(repetitions)):
        permuted = np.empty_like(treatment)
        for units in country_units.values():
            donor = list(units)
            rng.shuffle(donor)
            for target_unit, donor_unit in zip(units, donor):
                permuted[unit_rows[target_unit]] = histories[donor_unit]
        t_resid = permuted - z @ (pinv_z @ permuted)
        denominator = float(t_resid @ t_resid)
        effects[rep] = float((t_resid @ y_resid) / denominator) if denominator > 0 else np.nan

    finite = effects[np.isfinite(effects)]
    if len(finite) != int(repetitions):
        raise CurrentE2FalsificationError("permutation null produced non-finite coefficient")
    p_value = float((1 + np.count_nonzero(np.abs(finite) >= abs(observed_effect))) / (len(finite) + 1))
    quantiles = np.quantile(finite, [0.01, 0.025, 0.05, 0.5, 0.95, 0.975, 0.99])
    return {
        "ok": True,
        "policy": "within_country_complete_treatment_history",
        "repetitions": int(repetitions),
        "root_seed": int(root_seed),
        "observed_canonical_effect": float(observed_effect),
        "two_sided_empirical_p_value": p_value,
        "null_mean": float(np.mean(finite)),
        "null_median": float(np.median(finite)),
        "null_std": float(np.std(finite, ddof=1)),
        "null_q01": float(quantiles[0]),
        "null_q025": float(quantiles[1]),
        "null_q05": float(quantiles[2]),
        "null_q50": float(quantiles[3]),
        "null_q95": float(quantiles[4]),
        "null_q975": float(quantiles[5]),
        "null_q99": float(quantiles[6]),
        "countries": int(len(country_units)),
        "units": int(len(unit_rows)),
        "periods_per_unit": period_count,
        "preserved_structure": [
            "country membership",
            "complete within-unit treatment histories as indivisible vectors",
            "country-period treatment prevalence",
            "distribution of serial treatment patterns within country",
        ],
        "interpretation": (
            "Structured calibration null only. The empirical p-value is not a causal randomization "
            "test unless the required exchangeability assumptions are separately justified."
        ),
    }


def run_current_e2_falsification_battery(
    result: Mapping[str, Any],
    suite: CurrentE2FalsificationSpec,
) -> dict[str, Any]:
    spec, identity, primary, frame, frame_sha = _require_binding(result, suite)
    existing_tminus1 = primary.get("placebo")
    if not isinstance(existing_tminus1, Mapping):
        raise CurrentE2FalsificationError("R4 requires the existing t-1 placebo result")
    projected, reports = _projection_frame(result, spec, primary, suite)

    deep_pre = _placebo_fit(projected, spec, outcome_col="outcome_deep_pre")
    future = _placebo_fit(
        projected,
        spec,
        outcome_col="outcome_current",
        treatment_col="future_treatment",
    )
    baseline = primary.get("estimate")
    if not isinstance(baseline, Mapping) or not baseline.get("ok"):
        raise CurrentE2FalsificationError("R4 requires successful canonical estimate")
    permutation = _permutation_null(
        frame,
        spec,
        observed_effect=float(baseline["effect"]),
        repetitions=suite.permutation_repetitions,
        root_seed=suite.permutation_root_seed,
    )

    binding = {
        "schema": "current_e2_falsification_binding.v1",
        "suite_id": suite.suite_id,
        "purpose": "calibration",
        "reference_id": spec.reference_id,
        "primary_cell_id": suite.primary_cell_id,
        "analysis_identity_sha256": identity["analysis_identity_sha256"],
        "execution_identity_sha256": identity["execution_identity_sha256"],
        "primary_frame_sha256": frame_sha,
        "reference_lock_id": identity["lock"].get("lock_id"),
        "primary_hard_gate_state": "PASS",
        "analysis_frame_persisted": False,
        "reingestion_performed": False,
        "canonical_frame_mutated": False,
        "additional_falsification_projections_performed": True,
        "canonical_result_replaced": False,
    }
    summary = {
        "schema": "current_e2_falsification_summary.v1",
        "purpose": "calibration",
        "canonical_effect": float(baseline["effect"]),
        "existing_tminus1_placebo_std_abs_effect": existing_tminus1.get("std_abs_effect"),
        "deep_tminus2_placebo_std_abs_effect": deep_pre.get("std_abs_effect"),
        "future_treatment_placebo_std_abs_effect": future.get("std_abs_effect"),
        "structured_permutation_two_sided_p_value": permutation.get("two_sided_empirical_p_value"),
        "interpretation": (
            "Negative-control characterization only. Results constrain interpretation but cannot "
            "select a preferred specification or replace the canonical estimate."
        ),
    }
    return {
        "suite_spec": suite.to_dict(),
        "reference_binding": binding,
        "summary": summary,
        "existing_tminus1_placebo": dict(existing_tminus1),
        "deep_tminus2_placebo": deep_pre,
        "future_treatment_placebo": future,
        "permutation_null": permutation,
        "projection_reports": reports,
    }


def write_current_e2_falsification_outputs(
    result: Mapping[str, Any],
    out_dir: str | Path,
) -> Path:
    root = Path(out_dir)
    target = root / "falsification_battery"
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "falsification_spec.json": result.get("suite_spec"),
        "reference_binding.json": result.get("reference_binding"),
        "falsification_summary.json": result.get("summary"),
        "placebo_tminus1.json": result.get("existing_tminus1_placebo"),
        "placebo_tminus2.json": result.get("deep_tminus2_placebo"),
        "future_treatment_placebo.json": result.get("future_treatment_placebo"),
        "permutation_null_summary.json": result.get("permutation_null"),
    }
    for filename, payload in payloads.items():
        if not isinstance(payload, Mapping):
            raise CurrentE2FalsificationError(f"R4 output {filename!r} must be a mapping")
        (target / filename).write_text(
            json.dumps(dict(payload), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    reports = result.get("projection_reports")
    if not isinstance(reports, Mapping):
        raise CurrentE2FalsificationError("R4 projection reports missing")
    write_projection_report(reports["deep_pre"], target / "deep_pre_projection_report.json")
    write_projection_report(reports["current_outcome"], target / "current_outcome_projection_report.json")
    write_projection_report(reports["future_treatment"], target / "future_treatment_projection_report.json")

    run_path = root / "reference_run.json"
    if run_path.is_file():
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload["falsification_battery"] = {
            "state": "RUN",
            "path": "falsification_battery",
            "suite_id": result["suite_spec"]["suite_id"],
            "analysis_identity_sha256": result["reference_binding"]["analysis_identity_sha256"],
            "primary_frame_sha256": result["reference_binding"]["primary_frame_sha256"],
            "analysis_frame_persisted": False,
        }
        run_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return target


__all__ = [
    "CurrentE2FalsificationError",
    "CurrentE2FalsificationSpec",
    "run_current_e2_falsification_battery",
    "write_current_e2_falsification_outputs",
]
