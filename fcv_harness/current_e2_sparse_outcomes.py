from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from .current_e2_reference import CurrentE2ReferenceSpec
from .measurement_projection import MeasurementProjectionSpec, project_empirical_measurement, write_projection_report
from .reference_identity import stable_frame_sha256


SPARSE_OUTCOME_SCHEMA = "current_e2_sparse_outcome_family.v1"


class CurrentE2SparseOutcomeError(ValueError):
    """Raised when R5 is not bound to the frozen current-E2 reference."""


@dataclass(frozen=True)
class SparseOutcomeModelSpec:
    model_id: str
    outcome_representation: str
    estimator: str
    natural_primary_metric: str
    natural_primary_unit: str
    natural_secondary_metric: str
    natural_secondary_unit: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SparseOutcomeModelSpec":
        return cls(
            model_id=str(payload["model_id"]),
            outcome_representation=str(payload["outcome_representation"]),
            estimator=str(payload["estimator"]),
            natural_primary_metric=str(payload["natural_primary_metric"]),
            natural_primary_unit=str(payload["natural_primary_unit"]),
            natural_secondary_metric=str(payload["natural_secondary_metric"]),
            natural_secondary_unit=str(payload["natural_secondary_unit"]),
        )


@dataclass(frozen=True)
class CurrentE2SparseOutcomeSpec:
    suite_id: str
    purpose: str
    reference_id: str
    primary_cell_id: str
    required_analysis_identity_sha256: str
    required_primary_frame_sha256: str
    source_event_count_column: str
    binary_derivation: str
    models: tuple[SparseOutcomeModelSpec, ...]
    reading_rule: str

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2SparseOutcomeSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != SPARSE_OUTCOME_SCHEMA:
            raise CurrentE2SparseOutcomeError("unsupported current E2 sparse-outcome schema")
        models = tuple(SparseOutcomeModelSpec.from_dict(item) for item in raw["models"])
        ids = [item.model_id for item in models]
        expected = {"ols_event_count", "lpm_any_vac", "ppml_event_count"}
        if set(ids) != expected or len(ids) != len(expected):
            raise CurrentE2SparseOutcomeError(
                "R5 model family must contain exactly OLS event count, LPM any VAC, and PPML event count"
            )
        if str(raw.get("binary_derivation")) != "event_count_gt_zero":
            raise CurrentE2SparseOutcomeError("R5 binary outcome must be derived as event_count > 0")
        if not str(raw.get("source_event_count_column", "")):
            raise CurrentE2SparseOutcomeError("R5 requires an explicit source event-count column")
        return cls(
            suite_id=str(raw["suite_id"]),
            purpose=str(raw.get("purpose", "calibration_sensitivity")),
            reference_id=str(raw["reference_id"]),
            primary_cell_id=str(raw["primary_cell_id"]),
            required_analysis_identity_sha256=str(raw["required_analysis_identity_sha256"]),
            required_primary_frame_sha256=str(raw["required_primary_frame_sha256"]),
            source_event_count_column=str(raw["source_event_count_column"]),
            binary_derivation=str(raw["binary_derivation"]),
            models=models,
            reading_rule=str(raw["reading_rule"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SPARSE_OUTCOME_SCHEMA,
            "suite_id": self.suite_id,
            "purpose": self.purpose,
            "reference_id": self.reference_id,
            "primary_cell_id": self.primary_cell_id,
            "required_analysis_identity_sha256": self.required_analysis_identity_sha256,
            "required_primary_frame_sha256": self.required_primary_frame_sha256,
            "source_event_count_column": self.source_event_count_column,
            "binary_derivation": self.binary_derivation,
            "models": [item.__dict__ for item in self.models],
            "reading_rule": self.reading_rule,
        }


def _require_binding(
    result: Mapping[str, Any],
    suite: CurrentE2SparseOutcomeSpec,
) -> tuple[CurrentE2ReferenceSpec, Mapping[str, Any], Mapping[str, Any], pd.DataFrame, str]:
    spec = result.get("spec")
    if not isinstance(spec, CurrentE2ReferenceSpec):
        raise CurrentE2SparseOutcomeError("R5 requires a CurrentE2ReferenceSpec")
    if spec.purpose != "calibration" or suite.purpose != "calibration_sensitivity":
        raise CurrentE2SparseOutcomeError("R5 must remain calibration sensitivity only")
    if suite.reference_id != spec.reference_id or suite.primary_cell_id != spec.primary_cell.cell_id:
        raise CurrentE2SparseOutcomeError("R5 reference/PRIMARY identity mismatch")
    if spec.outcome_value_column != "fatalities":
        raise CurrentE2SparseOutcomeError("R5 requires the unchanged canonical fatalities reference")

    identity = result.get("reference_identity")
    if not isinstance(identity, Mapping):
        raise CurrentE2SparseOutcomeError("R5 requires reference_identity")
    lock = identity.get("lock")
    if not isinstance(lock, Mapping) or lock.get("verified") is not True:
        raise CurrentE2SparseOutcomeError("R5 requires a verified reference lock")
    if identity.get("analysis_identity_sha256") != suite.required_analysis_identity_sha256:
        raise CurrentE2SparseOutcomeError("R5 analysis identity mismatch")

    calibration = result.get("calibration")
    if not isinstance(calibration, Mapping):
        raise CurrentE2SparseOutcomeError("R5 requires calibration results")
    cells = calibration.get("cells")
    if not isinstance(cells, Mapping) or suite.primary_cell_id not in cells:
        raise CurrentE2SparseOutcomeError("R5 PRIMARY cell result missing")
    primary = cells[suite.primary_cell_id]
    if not isinstance(primary, Mapping) or primary.get("estimation_permitted") is not True:
        raise CurrentE2SparseOutcomeError("R5 blocked because PRIMARY hard gates do not pass")
    frame = primary.get("frame")
    if not isinstance(frame, pd.DataFrame):
        raise CurrentE2SparseOutcomeError("R5 requires the in-memory canonical PRIMARY frame")
    frame_sha = stable_frame_sha256(frame, unit_col=spec.unit_col, period_col=spec.period_col)
    if frame_sha != suite.required_primary_frame_sha256:
        raise CurrentE2SparseOutcomeError("R5 PRIMARY frame fingerprint drift")
    if identity.get("primary_frame_sha256") != frame_sha:
        raise CurrentE2SparseOutcomeError("R5 reference identity frame fingerprint mismatch")
    return spec, identity, primary, frame, frame_sha


def _project_event_counts(
    result: Mapping[str, Any],
    spec: CurrentE2ReferenceSpec,
    suite: CurrentE2SparseOutcomeSpec,
) -> tuple[pd.DataFrame, Any, Any]:
    panel = result.get("panel")
    linkage = result.get("geography_linkage")
    outcome_bundle = result.get("outcome_bundle")
    if not isinstance(panel, pd.DataFrame) or not isinstance(linkage, pd.DataFrame):
        raise CurrentE2SparseOutcomeError("R5 requires in-memory panel and geography linkage")
    if outcome_bundle is None:
        raise CurrentE2SparseOutcomeError("R5 requires the already-loaded governed outcome bundle")

    common = dict(
        measure_id=spec.outcome_measure_id,
        selectors={"native_event_type": spec.outcome_native_event_type},
        value_column=suite.source_event_count_column,
        transform=None,
    )
    post_spec = MeasurementProjectionSpec(
        **common,
        role="sparse_outcome_event_count",
        timing_offset=1,
        output_column="event_count",
    )
    pre_spec = MeasurementProjectionSpec(
        **common,
        role="sparse_pre_outcome_event_count",
        timing_offset=-1,
        output_column="event_count_pre",
    )
    target = panel[[spec.unit_col, spec.period_col]].copy()
    post = project_empirical_measurement(
        outcome_bundle,
        target,
        post_spec,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=linkage,
    )
    pre = project_empirical_measurement(
        outcome_bundle,
        target,
        pre_spec,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=linkage,
    )
    keys = [spec.unit_col, spec.period_col]
    post_frame = post.frame[keys + ["event_count", "projection_status"]].rename(
        columns={"projection_status": "event_count_status"}
    )
    pre_frame = pre.frame[keys + ["event_count_pre", "projection_status"]].rename(
        columns={"projection_status": "event_count_pre_status"}
    )
    projected = post_frame.merge(pre_frame, on=keys, how="inner", validate="one_to_one")
    allowed = {"observed", "structural_zero"}
    if not set(projected["event_count_status"].dropna().unique()).issubset(allowed):
        raise CurrentE2SparseOutcomeError("R5 post event-count projection is not fully resolved")
    if not set(projected["event_count_pre_status"].dropna().unique()).issubset(allowed):
        raise CurrentE2SparseOutcomeError("R5 pre event-count projection is not fully resolved")
    if projected[["event_count", "event_count_pre"]].isna().any().any():
        raise CurrentE2SparseOutcomeError("R5 event-count projections contain missing values")
    if (projected[["event_count", "event_count_pre"]] < 0).any().any():
        raise CurrentE2SparseOutcomeError("R5 event-count projections contain negative counts")
    return projected, post.report, pre.report


def _analysis_frame(
    canonical_frame: pd.DataFrame,
    projected: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
) -> pd.DataFrame:
    keys = [spec.unit_col, spec.period_col]
    keep = keys + [spec.country_col, "eligible", "treatment", "outcome_value", "outcome_pre"]
    missing = sorted(set(keep) - set(canonical_frame.columns))
    if missing:
        raise CurrentE2SparseOutcomeError("canonical PRIMARY frame is missing R5 design columns: " + ", ".join(missing))
    base = canonical_frame[keep].copy()
    out = base.merge(projected, on=keys, how="left", validate="one_to_one")
    if len(out) != len(base) or out[["event_count", "event_count_pre"]].isna().any().any():
        raise CurrentE2SparseOutcomeError("R5 alternative outcome frame does not preserve the canonical panel")
    out["any_vac"] = (pd.to_numeric(out["event_count"], errors="raise") > 0).astype(float)
    out["any_vac_pre"] = (pd.to_numeric(out["event_count_pre"], errors="raise") > 0).astype(float)
    return out


def _sample(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec, outcome: str, pre: str) -> pd.DataFrame:
    needed = [outcome, pre, "treatment", spec.unit_col, spec.period_col, spec.country_col]
    sample = frame.loc[frame["eligible"]].dropna(subset=needed).copy()
    if sample.empty or sample["treatment"].nunique() < 2:
        raise CurrentE2SparseOutcomeError("R5 model-complete sample lacks treatment support")
    return sample


def _ols_fit(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec, *, outcome: str, pre: str) -> dict[str, Any]:
    sample = _sample(frame, spec, outcome, pre)
    formula = f"{outcome} ~ treatment + {pre} + C({spec.period_col}) + C({spec.country_col})"
    fit = smf.ols(formula, data=sample).fit(
        cov_type="cluster", cov_kwds={"groups": sample[spec.unit_col].to_numpy()}
    )
    effect = float(fit.params["treatment"])
    se = float(fit.bse["treatment"])
    sd = float(pd.to_numeric(sample[outcome], errors="coerce").std(ddof=1))
    return {
        "ok": True,
        "coefficient": effect,
        "se": se,
        "z": effect / se if se > 0 else np.nan,
        "absolute_difference": effect,
        "standardized_difference": effect / sd if sd > 0 else np.nan,
        "outcome_sd": sd,
        "zero_share": float(pd.to_numeric(sample[outcome], errors="coerce").eq(0).mean()),
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "treated": int((sample["treatment"] == 1).sum()),
        "control": int((sample["treatment"] == 0).sum()),
        "formula": formula,
    }


def _lpm_fit(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> dict[str, Any]:
    result = _ols_fit(frame, spec, outcome="any_vac", pre="any_vac_pre")
    effect = float(result["coefficient"])
    result.update(
        {
            "probability_difference": effect,
            "percentage_point_difference": 100.0 * effect,
            "incidence_rate": float(
                frame.loc[frame["eligible"], "any_vac"].mean()
            ),
        }
    )
    return result


def _ppml_fit(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> dict[str, Any]:
    sample = _sample(frame, spec, "event_count", "event_count_pre")
    formula = (
        f"event_count ~ treatment + event_count_pre + "
        f"C({spec.period_col}) + C({spec.country_col})"
    )
    fit = smf.glm(formula, data=sample, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": sample[spec.unit_col].to_numpy()}
    )
    coefficient = float(fit.params["treatment"])
    se = float(fit.bse["treatment"])
    irr = float(np.exp(coefficient))
    irr_low = float(np.exp(coefficient - 1.96 * se))
    irr_high = float(np.exp(coefficient + 1.96 * se))
    treated_world = sample.copy()
    control_world = sample.copy()
    treated_world["treatment"] = 1.0
    control_world["treatment"] = 0.0
    mu1 = np.asarray(fit.predict(treated_world), dtype=float)
    mu0 = np.asarray(fit.predict(control_world), dtype=float)
    ame = float(np.mean(mu1 - mu0))
    return {
        "ok": True,
        "coefficient_log_irr": coefficient,
        "se_log_irr": se,
        "z": coefficient / se if se > 0 else np.nan,
        "incidence_rate_ratio": irr,
        "irr_ci95_low": irr_low,
        "irr_ci95_high": irr_high,
        "average_marginal_event_count_difference": ame,
        "mean_predicted_events_treated": float(np.mean(mu1)),
        "mean_predicted_events_control": float(np.mean(mu0)),
        "zero_share": float(pd.to_numeric(sample["event_count"], errors="coerce").eq(0).mean()),
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "treated": int((sample["treatment"] == 1).sum()),
        "control": int((sample["treatment"] == 0).sum()),
        "formula": formula,
        "family": "Poisson log-link pseudo-maximum likelihood",
    }


def _canonical_fatalities(primary: Mapping[str, Any], frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> dict[str, Any]:
    estimate = primary.get("estimate")
    if not isinstance(estimate, Mapping) or not estimate.get("ok"):
        raise CurrentE2SparseOutcomeError("R5 requires a successful canonical fatalities estimate")
    sample = _sample(frame, spec, "outcome_value", "outcome_pre")
    effect = float(estimate["effect"])
    sd = float(pd.to_numeric(sample["outcome_value"], errors="coerce").std(ddof=1))
    return {
        "ok": True,
        "absolute_difference": effect,
        "standardized_difference": effect / sd if sd > 0 else np.nan,
        "se": float(estimate["se"]),
        "outcome_sd": sd,
        "zero_share": float(pd.to_numeric(sample["outcome_value"], errors="coerce").eq(0).mean()),
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "treated": int((sample["treatment"] == 1).sum()),
        "control": int((sample["treatment"] == 0).sum()),
        "formula": estimate.get("formula"),
    }


def _summary_rows(
    suite: CurrentE2SparseOutcomeSpec,
    canonical: Mapping[str, Any],
    event_ols: Mapping[str, Any],
    lpm: Mapping[str, Any],
    ppml: Mapping[str, Any],
) -> pd.DataFrame:
    by_id = {item.model_id: item for item in suite.models}
    rows = [
        {
            "model_id": "canonical_ols_fatalities",
            "role": "CANONICAL",
            "outcome_representation": "VAC fatalities",
            "estimator": "OLS",
            "n": canonical["n"],
            "treated": canonical["treated"],
            "control": canonical["control"],
            "zero_share": canonical["zero_share"],
            "natural_primary_metric": "absolute_difference",
            "natural_primary_value": canonical["absolute_difference"],
            "natural_primary_unit": "fatalities",
            "natural_secondary_metric": "standardized_difference",
            "natural_secondary_value": canonical["standardized_difference"],
            "natural_secondary_unit": "outcome_sd",
            "canonical_result_replaced": False,
        }
    ]
    payloads = {
        "ols_event_count": (
            event_ols,
            event_ols["absolute_difference"],
            event_ols["standardized_difference"],
        ),
        "lpm_any_vac": (
            lpm,
            lpm["probability_difference"],
            lpm["percentage_point_difference"],
        ),
        "ppml_event_count": (
            ppml,
            ppml["incidence_rate_ratio"],
            ppml["average_marginal_event_count_difference"],
        ),
    }
    for model_id in ("ols_event_count", "lpm_any_vac", "ppml_event_count"):
        result, primary_value, secondary_value = payloads[model_id]
        model = by_id[model_id]
        rows.append(
            {
                "model_id": model_id,
                "role": "ROBUSTNESS",
                "outcome_representation": model.outcome_representation,
                "estimator": model.estimator,
                "n": result["n"],
                "treated": result["treated"],
                "control": result["control"],
                "zero_share": result["zero_share"],
                "natural_primary_metric": model.natural_primary_metric,
                "natural_primary_value": primary_value,
                "natural_primary_unit": model.natural_primary_unit,
                "natural_secondary_metric": model.natural_secondary_metric,
                "natural_secondary_value": secondary_value,
                "natural_secondary_unit": model.natural_secondary_unit,
                "canonical_result_replaced": False,
            }
        )
    return pd.DataFrame(rows)


def run_current_e2_sparse_outcomes(
    result: Mapping[str, Any],
    suite: CurrentE2SparseOutcomeSpec,
) -> dict[str, Any]:
    """Characterize severity, incidence, and count intensity without specification search.

    R5 binds to the frozen canonical PRIMARY frame and reuses its treatment/eligibility
    design unchanged. Only the governed ACLED value representation is projected anew.
    The canonical fatalities OLS remains primary and is never replaced by an alternative
    model on the basis of sign, magnitude, precision, or fit.
    """
    spec, identity, primary, canonical_frame, frame_sha = _require_binding(result, suite)
    before = canonical_frame.copy(deep=True)
    projected, post_report, pre_report = _project_event_counts(result, spec, suite)
    frame = _analysis_frame(canonical_frame, projected, spec)

    canonical = _canonical_fatalities(primary, canonical_frame, spec)
    event_ols = _ols_fit(frame, spec, outcome="event_count", pre="event_count_pre")
    lpm = _lpm_fit(frame, spec)
    ppml = _ppml_fit(frame, spec)

    pd.testing.assert_frame_equal(before, canonical_frame)
    summary = _summary_rows(suite, canonical, event_ols, lpm, ppml)
    binding = {
        "schema": "current_e2_sparse_outcome_binding.v1",
        "suite_id": suite.suite_id,
        "purpose": suite.purpose,
        "reference_id": spec.reference_id,
        "primary_cell_id": suite.primary_cell_id,
        "primary_hard_gate_state": "PASS",
        "analysis_identity_sha256": identity["analysis_identity_sha256"],
        "execution_identity_sha256": identity["execution_identity_sha256"],
        "primary_frame_sha256": frame_sha,
        "reference_lock_id": identity["lock"].get("lock_id"),
        "treatment_measure_id": spec.treatment_measure_id,
        "outcome_measure_id": spec.outcome_measure_id,
        "canonical_outcome_value_column": spec.outcome_value_column,
        "alternative_source_value_column": suite.source_event_count_column,
        "analysis_frame_persisted": False,
        "reingestion_performed": False,
        "canonical_treatment_reprojection_performed": False,
        "alternative_outcome_projection_performed": True,
        "canonical_result_replaced": False,
        "specification_selected_by_result": False,
        "hurdle_model_included": False,
    }
    return {
        "suite": suite,
        "summary": summary,
        "canonical_fatalities_ols": canonical,
        "ols_event_count": event_ols,
        "lpm_any_vac": lpm,
        "ppml_event_count": ppml,
        "event_count_post_projection_report": post_report,
        "event_count_pre_projection_report": pre_report,
        "reference_binding": binding,
    }


def write_current_e2_sparse_outcome_outputs(
    result: Mapping[str, Any],
    out_dir: str | Path,
) -> Path:
    root = Path(out_dir) / "sparse_outcome_family"
    root.mkdir(parents=True, exist_ok=True)
    result["summary"].to_csv(root / "model_summary.csv", index=False)
    for key in (
        "canonical_fatalities_ols",
        "ols_event_count",
        "lpm_any_vac",
        "ppml_event_count",
        "reference_binding",
    ):
        (root / f"{key}.json").write_text(
            json.dumps(result[key], sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    write_projection_report(
        result["event_count_post_projection_report"], root / "event_count_post_projection_report.json"
    )
    write_projection_report(
        result["event_count_pre_projection_report"], root / "event_count_pre_projection_report.json"
    )
    suite: CurrentE2SparseOutcomeSpec = result["suite"]
    (root / "sparse_outcome_spec.json").write_text(
        json.dumps(suite.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    family = {
        "schema": "current_e2_sparse_outcome_summary.v1",
        "suite_id": suite.suite_id,
        "purpose": suite.purpose,
        "representations": ["severity", "incidence", "count_intensity"],
        "canonical_model": "OLS fatalities",
        "robustness_models": ["OLS event_count", "LPM any_VAC", "PPML event_count"],
        "raw_coefficients_cross_model_comparable": False,
        "canonical_result_replaced": False,
        "hurdle_model_included": False,
        "reading_rule": suite.reading_rule,
    }
    (root / "family_summary.json").write_text(
        json.dumps(family, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return root


__all__ = [
    "CurrentE2SparseOutcomeError",
    "CurrentE2SparseOutcomeSpec",
    "run_current_e2_sparse_outcomes",
    "write_current_e2_sparse_outcome_outputs",
]
