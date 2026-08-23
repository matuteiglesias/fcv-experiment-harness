from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
from empirical_contracts import GeographySpec, PeriodScheme

from .canonical import _period_start
from .canonical_experiment import (
    EligibilitySpec,
    TreatmentMeasurementSpec,
    resolve_treatment_measurement,
)
from .empirical_input import EmpiricalMeasurementBundle
from .lattice_diagnostics import attach_country_iso3
from .measurement_projection import (
    MeasurementProjectionSpec,
    ProjectionResult,
    project_empirical_measurement,
    write_projection_report,
)


@dataclass(frozen=True)
class ContractedPanelExperimentSpec:
    """Treatment design plus an explicit contract-backed outcome projection."""

    experiment_id: str
    panel_id: str
    treatment: TreatmentMeasurementSpec
    eligibility: EligibilitySpec
    outcome: MeasurementProjectionSpec
    covariates: tuple[str, ...] = ()
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path: str | Path) -> "ContractedPanelExperimentSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            experiment_id=str(raw["experiment_id"]),
            panel_id=str(raw["panel_id"]),
            treatment=TreatmentMeasurementSpec.from_dict(raw["treatment"]),
            eligibility=EligibilitySpec.from_dict(raw["eligibility"]),
            outcome=MeasurementProjectionSpec.from_dict(raw["outcome"]),
            covariates=tuple(raw.get("covariates", [])),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "panel_id": self.panel_id,
            "treatment": {
                "source": self.treatment.source,
                "definition": self.treatment.definition,
                "annotation_version": self.treatment.annotation_version,
            },
            "eligibility": {
                "treatment_period_start": self.eligibility.treatment_period_start,
                "treatment_period_end": self.eligibility.treatment_period_end,
            },
            "outcome": self.outcome.to_dict(),
            "covariates": list(self.covariates),
            "unit_col": self.unit_col,
            "period_col": self.period_col,
            "country_col": self.country_col,
        }


def _source_only_for_window(
    source_only_keys: Optional[pd.DataFrame],
    *,
    source: str,
    period_col: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    if source_only_keys is None or source_only_keys.empty:
        return pd.DataFrame()
    if "source" not in source_only_keys or period_col not in source_only_keys:
        return pd.DataFrame()
    lo = _period_start(start)
    hi = _period_start(end)
    years = source_only_keys[period_col].astype(str).map(_period_start)
    return source_only_keys.loc[
        source_only_keys["source"].eq(source)
        & years.between(lo, hi, inclusive="both")
    ].copy()


def prepare_contracted_experiment_frame(
    panel: pd.DataFrame,
    spec: ContractedPanelExperimentSpec,
    *,
    bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
) -> tuple[pd.DataFrame, ProjectionResult]:
    enriched = attach_country_iso3(
        panel,
        unit_col=spec.unit_col,
        country_col=spec.country_col,
    )
    treatment = resolve_treatment_measurement(enriched, spec)
    projection = project_empirical_measurement(
        bundle,
        enriched[[spec.unit_col, spec.period_col]],
        spec.outcome,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=geography_linkage,
    )

    out = enriched.copy()
    for column in [
        "treatment",
        "eligible",
        "treatment_source_record_present",
        "treatment_source_amount_positive",
        "treatment_measurement_status",
        "treatment_provenance",
    ]:
        out[column] = treatment[column].to_numpy()

    projected = projection.frame
    out["outcome_value"] = projected[spec.outcome.output_column].to_numpy()
    out["outcome_post_period"] = projected["measurement_period_id"].to_numpy()
    out["outcome_post_record_present"] = projected[
        "measurement_record_present"
    ].to_numpy()
    out["outcome_measurement_status"] = projected["projection_status"].to_numpy()
    out["outcome_projection_detail"] = projected["projection_detail"].to_numpy()
    out["outcome_eligible"] = out["outcome_value"].notna()
    out["outcome_provenance"] = (
        f"{spec.outcome.measure_id}:selectors={json.dumps(spec.outcome.selectors, sort_keys=True)}:"
        f"value={spec.outcome.value_column}:offset={spec.outcome.timing_offset}"
    )

    eligible = out["eligible"].astype(bool)
    permitted = bool(out.loc[eligible, "outcome_value"].notna().all())
    out["estimation_permitted"] = permitted
    return out, projection


def build_contracted_input_eligibility_report(
    frame: pd.DataFrame,
    spec: ContractedPanelExperimentSpec,
    *,
    bundle: EmpiricalMeasurementBundle,
    source_only_keys: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    eligible = frame.loc[frame["eligible"]].copy()
    outside_treatment = _source_only_for_window(
        source_only_keys,
        source=spec.treatment.source,
        period_col=spec.period_col,
        start=spec.eligibility.treatment_period_start,
        end=spec.eligibility.treatment_period_end,
    )
    treated = int(eligible["treatment"].eq(1).sum())
    control = int(eligible["treatment"].eq(0).sum())
    statuses = eligible["outcome_measurement_status"].astype(str)
    observed = int(statuses.eq("observed").sum())
    structural = int(statuses.eq("structural_zero").sum())
    outside = int(statuses.eq("outside_coverage").sum())
    unresolved = int(statuses.eq("unresolved").sum())
    permitted = bool(frame["estimation_permitted"].all())

    return pd.DataFrame(
        [
            {
                "gate": "E0_INPUT_ELIGIBILITY",
                "status": "OK" if permitted else "BLOCKED",
                "metric": "estimation permitted by projected outcome support",
                "value": permitted,
                "note": (
                    "All eligible projected outcomes are available."
                    if permitted
                    else "At least one eligible projected outcome is outside coverage or unresolved; estimator input remains blocked."
                ),
            },
            {
                "gate": "E0_INPUT_ELIGIBILITY",
                "status": "REVIEW" if len(outside_treatment) else "OK",
                "metric": "treatment source keys outside canonical lattice in treatment window",
                "value": int(len(outside_treatment)),
                "note": f"Treatment source: {spec.treatment.source}.",
            },
            {
                "gate": "E0_INPUT_ELIGIBILITY",
                "status": "OK" if treated and control else "BLOCKED",
                "metric": "eligible treated / control lattice rows",
                "value": f"{treated} / {control}",
                "note": "Treatment semantics are unchanged from the declared investment measurement definition.",
            },
            {
                "gate": "E0_INPUT_ELIGIBILITY",
                "status": "REVIEW" if outside or unresolved else "OK",
                "metric": "eligible outcome observed / structural-zero / outside / unresolved",
                "value": f"{observed} / {structural} / {outside} / {unresolved}",
                "note": (
                    "Sparse absence is interpreted only by the upstream CoverageContract; "
                    f"absent-row semantics={bundle.coverage.absent_row_semantics}."
                ),
            },
        ]
    )


def build_contracted_treatment_support_by_period(
    frame: pd.DataFrame,
    spec: ContractedPanelExperimentSpec,
) -> pd.DataFrame:
    eligible = frame.loc[frame["eligible"]].copy()
    rows = []
    for period, group in eligible.groupby(spec.period_col, dropna=False):
        status = group["outcome_measurement_status"].astype(str)
        rows.append(
            {
                spec.period_col: period,
                "eligible_rows": int(len(group)),
                "treated": int(group["treatment"].eq(1).sum()),
                "control": int(group["treatment"].eq(0).sum()),
                "treatment_record_present": int(
                    group["treatment_source_record_present"].sum()
                ),
                "treatment_amount_positive": int(
                    group["treatment_source_amount_positive"].sum()
                ),
                "outcome_observed": int(status.eq("observed").sum()),
                "outcome_structural_zero": int(status.eq("structural_zero").sum()),
                "outcome_outside_coverage": int(status.eq("outside_coverage").sum()),
                "outcome_unresolved": int(status.eq("unresolved").sum()),
                "outcome_values": int(group["outcome_value"].notna().sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(spec.period_col) if rows else pd.DataFrame()


def _render_table(frame: pd.DataFrame, *, empty: str) -> str:
    if frame.empty:
        return empty
    return "```text\n" + frame.to_string(index=False) + "\n```"


def render_contracted_experiment_preflight(
    spec: ContractedPanelExperimentSpec,
    input_eligibility: pd.DataFrame,
    support_by_period: pd.DataFrame,
    *,
    bundle: EmpiricalMeasurementBundle,
    permitted: bool,
) -> str:
    lines = [
        f"# Contracted Experiment Preflight — {spec.experiment_id}",
        "",
        "> This preflight resolves treatment eligibility and a contract-backed empirical outcome projection. It does **not** estimate a treatment effect.",
        "",
        "## Scientific declaration",
        "",
        f"- Treatment: `{spec.treatment.source}.{spec.treatment.definition}`",
        f"- Treatment periods: `{spec.eligibility.treatment_period_start}` through `{spec.eligibility.treatment_period_end}`",
        f"- Empirical measure: `{spec.outcome.measure_id}`",
        f"- Selectors: `{json.dumps(spec.outcome.selectors, sort_keys=True)}`",
        f"- Value: `{spec.outcome.value_column}`",
        f"- Timing offset: `{spec.outcome.timing_offset}` period(s)",
        f"- Coverage absent-row semantics: `{bundle.coverage.absent_row_semantics}`",
        f"- Estimation permitted by projected support: **{str(permitted).upper()}**",
        "",
        "## Input eligibility",
        "",
        _render_table(input_eligibility, empty="No input-eligibility rows."),
        "",
        "## Support by treatment period",
        "",
        _render_table(support_by_period, empty="No eligible rows."),
        "",
        "Unknown or outside-support empirical rows remain present with missing values and explicit statuses. They are never silently dropped or converted to zero.",
        "",
    ]
    return "\n".join(lines)


def run_contracted_experiment_preflight(
    panel: pd.DataFrame,
    spec: ContractedPanelExperimentSpec,
    *,
    bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
    source_only_keys: Optional[pd.DataFrame] = None,
) -> dict:
    frame, projection = prepare_contracted_experiment_frame(
        panel,
        spec,
        bundle=bundle,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        geography_linkage=geography_linkage,
    )
    input_eligibility = build_contracted_input_eligibility_report(
        frame,
        spec,
        bundle=bundle,
        source_only_keys=source_only_keys,
    )
    support = build_contracted_treatment_support_by_period(frame, spec)
    permitted = bool(frame["estimation_permitted"].all())
    report = render_contracted_experiment_preflight(
        spec,
        input_eligibility,
        support,
        bundle=bundle,
        permitted=permitted,
    )
    return {
        "frame": frame,
        "projection": projection,
        "input_eligibility": input_eligibility,
        "support_by_period": support,
        "report": report,
        "estimation_permitted": permitted,
    }


def write_contracted_experiment_preflight_outputs(
    result: dict,
    spec: ContractedPanelExperimentSpec,
    out_dir: str | Path,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["input_eligibility"].to_csv(out / "input_eligibility.csv", index=False)
    result["support_by_period"].to_csv(out / "treatment_support_by_period.csv", index=False)
    result["frame"].head(500).to_csv(out / "measurement_frame_sample.csv", index=False)
    write_projection_report(
        result["projection"].report,
        out / "outcome_projection_report.json",
    )
    (out / "experiment_preflight.md").write_text(result["report"], encoding="utf-8")
    payload = spec.to_dict()
    payload["estimation_permitted"] = bool(result["estimation_permitted"])
    (out / "experiment_contract.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
