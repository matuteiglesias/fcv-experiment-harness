from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
from empirical_contracts import GeographySpec, PeriodScheme
from spatial_foundation import PeriodIndex

from .empirical_input import EmpiricalMeasurementBundle
from .lattice_diagnostics import attach_country_iso3
from .measurement_projection import (
    MeasurementProjectionSpec,
    ProjectionResult,
    project_empirical_measurement,
    write_projection_report,
)

_PERIOD_ID = re.compile(r"^(\d{4})-(\d{4})$")


class FullyContractedExperimentError(ValueError):
    """Raised when contract-backed measurement uses cannot form the declared experiment."""


@dataclass(frozen=True)
class TreatmentDerivationSpec:
    """Downstream rule turning a projected empirical quantity into treatment state."""

    rule: str = "greater_than"
    threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.rule != "greater_than":
            raise ValueError("only explicit greater_than treatment derivation is implemented")

    @classmethod
    def from_dict(cls, payload: dict) -> TreatmentDerivationSpec:
        return cls(
            rule=str(payload.get("rule", "greater_than")),
            threshold=float(payload.get("threshold", 0.0)),
        )

    def to_dict(self) -> dict:
        return {"rule": self.rule, "threshold": self.threshold}


@dataclass(frozen=True)
class TreatmentEligibilitySpec:
    """Experiment-side period window; never an upstream source-coverage declaration."""

    period_start: str
    period_end: str

    @classmethod
    def from_dict(cls, payload: dict) -> TreatmentEligibilitySpec:
        return cls(
            period_start=str(payload["period_start"]),
            period_end=str(payload["period_end"]),
        )

    def to_dict(self) -> dict:
        return {"period_start": self.period_start, "period_end": self.period_end}


@dataclass(frozen=True)
class FullyContractedPanelExperimentSpec:
    """Scientific design whose treatment and outcome are both contracted measurements."""

    experiment_id: str
    treatment: MeasurementProjectionSpec
    treatment_derivation: TreatmentDerivationSpec
    eligibility: TreatmentEligibilitySpec
    outcome: MeasurementProjectionSpec
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    def __post_init__(self) -> None:
        if self.treatment.role not in {"treatment", "treatment_candidate"}:
            raise ValueError("treatment measurement projection must declare a treatment role")
        if self.outcome.role not in {"outcome", "post_outcome"}:
            raise ValueError("outcome measurement projection must declare an outcome role")

    @classmethod
    def from_json(cls, path: str | Path) -> FullyContractedPanelExperimentSpec:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            experiment_id=str(raw["experiment_id"]),
            treatment=MeasurementProjectionSpec.from_dict(raw["treatment"]),
            treatment_derivation=TreatmentDerivationSpec.from_dict(raw["treatment_derivation"]),
            eligibility=TreatmentEligibilitySpec.from_dict(raw["eligibility"]),
            outcome=MeasurementProjectionSpec.from_dict(raw["outcome"]),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "treatment": self.treatment.to_dict(),
            "treatment_derivation": self.treatment_derivation.to_dict(),
            "eligibility": self.eligibility.to_dict(),
            "outcome": self.outcome.to_dict(),
            "unit_col": self.unit_col,
            "period_col": self.period_col,
            "country_col": self.country_col,
        }


@dataclass(frozen=True)
class FullyContractedPreflightResult:
    frame: pd.DataFrame
    treatment_projection: ProjectionResult
    outcome_projection: ProjectionResult
    eligibility_report: pd.DataFrame
    support_by_period: pd.DataFrame
    estimation_permitted: bool


def _validated_period_start(period_id: str, scheme: PeriodScheme) -> int:
    match = _PERIOD_ID.fullmatch(str(period_id))
    if not match:
        raise FullyContractedExperimentError(
            f"period id {period_id!r} is not a shared PeriodIndex id"
        )
    start_year = int(match.group(1))
    period = PeriodIndex(scheme).period_for(start_year)
    if period.period_id != str(period_id):
        raise FullyContractedExperimentError(
            f"period id {period_id!r} contradicts PeriodScheme {scheme.id}"
        )
    return period.start_year


def _eligibility_mask(
    values: pd.Series,
    eligibility: TreatmentEligibilitySpec,
    scheme: PeriodScheme,
) -> pd.Series:
    start = _validated_period_start(eligibility.period_start, scheme)
    end = _validated_period_start(eligibility.period_end, scheme)
    if start > end:
        raise FullyContractedExperimentError("treatment eligibility start must not follow end")
    starts = values.astype(str).map(lambda value: _validated_period_start(value, scheme))
    return starts.between(start, end, inclusive="both")


def _projection_available(frame: pd.DataFrame) -> pd.Series:
    status = frame["projection_status"].astype("string")
    value = pd.to_numeric(frame["_value"], errors="coerce")
    return status.isin(["observed", "structural_zero"]) & value.notna()


def _derive_treatment(
    projection: ProjectionResult,
    spec: FullyContractedPanelExperimentSpec,
    *,
    target_periods: pd.Series,
    target_period_scheme: PeriodScheme,
) -> pd.DataFrame:
    frame = projection.frame.rename(columns={spec.treatment.output_column: "_value"}).copy()
    eligible = _eligibility_mask(target_periods, spec.eligibility, target_period_scheme)
    available = _projection_available(frame)
    numeric = pd.to_numeric(frame["_value"], errors="coerce")

    treatment = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    usable = eligible & available
    if spec.treatment_derivation.rule == "greater_than":
        treatment.loc[usable] = (
            numeric.loc[usable] > spec.treatment_derivation.threshold
        ).astype(int).to_numpy()
    else:  # guarded in TreatmentDerivationSpec
        raise FullyContractedExperimentError(
            f"unsupported treatment derivation {spec.treatment_derivation.rule!r}"
        )

    state = pd.Series("outside_treatment_period", index=frame.index, dtype="string")
    unavailable = eligible & ~available
    state.loc[unavailable] = "treatment_measurement_unavailable"
    state.loc[usable & treatment.eq(0).fillna(False)] = "control_by_declared_rule"
    state.loc[usable & treatment.eq(1).fillna(False)] = "treated_by_declared_rule"

    return pd.DataFrame(
        {
            "treatment_measurement_value": numeric,
            "treatment_measurement_status": frame["projection_status"].astype("string"),
            "treatment_projection_detail": frame["projection_detail"].astype("string"),
            "treatment_measurement_record_present": frame[
                "measurement_record_present"
            ].astype(bool),
            "treatment_measurement_geo_uid": frame["measurement_geo_uid"],
            "treatment_measurement_period_id": frame["measurement_period_id"],
            "treatment": treatment,
            "eligible": eligible.astype(bool),
            "treatment_derivation_status": state,
        }
    )


def prepare_fully_contracted_experiment_frame(
    panel: pd.DataFrame,
    spec: FullyContractedPanelExperimentSpec,
    *,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
) -> tuple[pd.DataFrame, ProjectionResult, ProjectionResult]:
    """Project two contracted measurements, then derive treatment downstream."""
    required = [spec.unit_col, spec.period_col]
    missing = [column for column in required if column not in panel.columns]
    if missing:
        raise FullyContractedExperimentError(f"analysis panel is missing keys: {missing}")
    if panel.duplicated(required).any():
        raise FullyContractedExperimentError(
            "analysis panel must be unique at declared analysis unit × period"
        )

    enriched = attach_country_iso3(
        panel,
        unit_col=spec.unit_col,
        country_col=spec.country_col,
    )
    target = enriched[[spec.unit_col, spec.period_col]]
    treatment_projection = project_empirical_measurement(
        treatment_bundle,
        target,
        spec.treatment,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=geography_linkage,
    )
    outcome_projection = project_empirical_measurement(
        outcome_bundle,
        target,
        spec.outcome,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=geography_linkage,
    )

    treatment = _derive_treatment(
        treatment_projection,
        spec,
        target_periods=enriched[spec.period_col],
        target_period_scheme=target_period_scheme,
    )
    outcome = outcome_projection.frame

    out = enriched.copy()
    for column in treatment.columns:
        out[column] = treatment[column].to_numpy()
    out["outcome_value"] = pd.to_numeric(
        outcome[spec.outcome.output_column], errors="coerce"
    ).to_numpy()
    out["outcome_measurement_status"] = outcome["projection_status"].astype("string").to_numpy()
    out["outcome_projection_detail"] = outcome["projection_detail"].astype("string").to_numpy()
    out["outcome_measurement_record_present"] = outcome[
        "measurement_record_present"
    ].astype(bool).to_numpy()
    out["outcome_measurement_geo_uid"] = outcome["measurement_geo_uid"].to_numpy()
    out["outcome_measurement_period_id"] = outcome["measurement_period_id"].to_numpy()

    eligible = out["eligible"].astype(bool)
    treatment_complete = bool(out.loc[eligible, "treatment"].notna().all())
    outcome_complete = bool(out.loc[eligible, "outcome_value"].notna().all())
    out["estimation_permitted"] = treatment_complete and outcome_complete
    return out, treatment_projection, outcome_projection


def build_fully_contracted_eligibility_report(
    frame: pd.DataFrame,
    spec: FullyContractedPanelExperimentSpec,
) -> pd.DataFrame:
    eligible = frame.loc[frame["eligible"]].copy()
    treatment_status = eligible["treatment_measurement_status"].astype(str)
    outcome_status = eligible["outcome_measurement_status"].astype(str)
    treated = int(eligible["treatment"].eq(1).sum())
    control = int(eligible["treatment"].eq(0).sum())
    treatment_missing = int(eligible["treatment"].isna().sum())
    outcome_missing = int(eligible["outcome_value"].isna().sum())
    permitted = bool(frame["estimation_permitted"].all())

    return pd.DataFrame(
        [
            {
                "gate": "E0_FULLY_CONTRACTED_INPUTS",
                "status": "OK" if permitted else "BLOCKED",
                "metric": "treatment / outcome unavailable in eligible window",
                "value": f"{treatment_missing} / {outcome_missing}",
                "note": (
                    "Both scientific variables come from explicit contract-backed projections; "
                    "unavailable treatment is never converted to control."
                ),
            },
            {
                "gate": "E0_FULLY_CONTRACTED_INPUTS",
                "status": "OK" if treated and control else "BLOCKED",
                "metric": "eligible treated / control rows",
                "value": f"{treated} / {control}",
                "note": (
                    f"Treatment rule is {spec.treatment_derivation.rule} "
                    f"{spec.treatment_derivation.threshold:g} applied downstream."
                ),
            },
            {
                "gate": "E0_FULLY_CONTRACTED_INPUTS",
                "status": "REVIEW"
                if treatment_status.isin(["outside_coverage", "unresolved"]).any()
                else "OK",
                "metric": "eligible treatment observed / structural-zero / outside / unresolved",
                "value": (
                    f"{int(treatment_status.eq('observed').sum())} / "
                    f"{int(treatment_status.eq('structural_zero').sum())} / "
                    f"{int(treatment_status.eq('outside_coverage').sum())} / "
                    f"{int(treatment_status.eq('unresolved').sum())}"
                ),
                "note": "Projection status comes from the generic empirical boundary.",
            },
            {
                "gate": "E0_FULLY_CONTRACTED_INPUTS",
                "status": "REVIEW"
                if outcome_status.isin(["outside_coverage", "unresolved"]).any()
                else "OK",
                "metric": "eligible outcome observed / structural-zero / outside / unresolved",
                "value": (
                    f"{int(outcome_status.eq('observed').sum())} / "
                    f"{int(outcome_status.eq('structural_zero').sum())} / "
                    f"{int(outcome_status.eq('outside_coverage').sum())} / "
                    f"{int(outcome_status.eq('unresolved').sum())}"
                ),
                "note": "Outcome support remains governed by its upstream CoverageContract.",
            },
        ]
    )


def build_fully_contracted_support_by_period(
    frame: pd.DataFrame,
    spec: FullyContractedPanelExperimentSpec,
) -> pd.DataFrame:
    rows = []
    for period, group in frame.loc[frame["eligible"]].groupby(spec.period_col, dropna=False):
        rows.append(
            {
                spec.period_col: period,
                "eligible_rows": int(len(group)),
                "treated": int(group["treatment"].eq(1).sum()),
                "control": int(group["treatment"].eq(0).sum()),
                "treatment_unavailable": int(group["treatment"].isna().sum()),
                "outcome_available": int(group["outcome_value"].notna().sum()),
                "outcome_unavailable": int(group["outcome_value"].isna().sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(spec.period_col) if rows else pd.DataFrame()


def run_fully_contracted_experiment_preflight(
    panel: pd.DataFrame,
    spec: FullyContractedPanelExperimentSpec,
    *,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
) -> FullyContractedPreflightResult:
    frame, treatment_projection, outcome_projection = prepare_fully_contracted_experiment_frame(
        panel,
        spec,
        treatment_bundle=treatment_bundle,
        outcome_bundle=outcome_bundle,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        geography_linkage=geography_linkage,
    )
    report = build_fully_contracted_eligibility_report(frame, spec)
    support = build_fully_contracted_support_by_period(frame, spec)
    return FullyContractedPreflightResult(
        frame=frame,
        treatment_projection=treatment_projection,
        outcome_projection=outcome_projection,
        eligibility_report=report,
        support_by_period=support,
        estimation_permitted=bool(frame["estimation_permitted"].all()),
    )


def write_fully_contracted_preflight_outputs(
    result: FullyContractedPreflightResult,
    spec: FullyContractedPanelExperimentSpec,
    out_dir: str | Path,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "experiment_spec.json").write_text(
        json.dumps(spec.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    result.eligibility_report.to_csv(out / "input_eligibility.csv", index=False)
    result.support_by_period.to_csv(out / "support_by_period.csv", index=False)
    write_projection_report(
        result.treatment_projection.report,
        out / "treatment_projection_report.json",
    )
    write_projection_report(
        result.outcome_projection.report,
        out / "outcome_projection_report.json",
    )
    result.frame.head(500).to_csv(out / "analysis_frame_sample.csv", index=False)
    return out


def pre_outcome_spec(spec: FullyContractedPanelExperimentSpec) -> MeasurementProjectionSpec:
    """Return the same contracted outcome measurement used one period before treatment."""
    return replace(
        spec.outcome,
        role="pre_outcome",
        timing_offset=-1,
        output_column="outcome_pre",
    )
