from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from empirical_contracts import GeographySpec, PeriodScheme

from .analysis_surface import (
    AnalysisUniverseSpec,
    build_analysis_universe,
    build_universe_country_profile,
    build_unparsed_country_gid_profile,
)
from .canonical import CanonicalPanelSpec
from .empirical_input import EmpiricalMeasurementBundle
from .lattice_diagnostics import build_source_outside_lattice_diagnostics
from .measurement_projection import (
    MeasurementProjectionSpec,
    ProjectionResult,
    project_empirical_measurement,
    write_projection_report,
)


@dataclass(frozen=True)
class ContractedAnalysisSurfaceSpec:
    """E1 analysis surface driven by a validated empirical measurement bundle."""

    surface_id: str
    canonical_manifest: str
    universe: AnalysisUniverseSpec
    geography: GeographySpec
    period_scheme: PeriodScheme
    measurement: MeasurementProjectionSpec
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path: str | Path) -> "ContractedAnalysisSurfaceSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            surface_id=str(raw["surface_id"]),
            canonical_manifest=str(raw["canonical_manifest"]),
            universe=AnalysisUniverseSpec.from_dict(raw["universe"]),
            geography=GeographySpec.model_validate(raw["geography"]),
            period_scheme=PeriodScheme.model_validate(raw["period_scheme"]),
            measurement=MeasurementProjectionSpec.from_dict(raw["measurement"]),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )

    def to_dict(self) -> dict:
        return {
            "surface_id": self.surface_id,
            "canonical_manifest": self.canonical_manifest,
            "universe": {
                "mode": self.universe.mode,
                "authority": self.universe.authority,
                "external_spine_path": self.universe.external_spine_path,
                "external_gid_col": self.universe.external_gid_col,
                "external_period_col": self.universe.external_period_col,
            },
            "geography": self.geography.model_dump(mode="json"),
            "period_scheme": self.period_scheme.model_dump(mode="json"),
            "measurement": self.measurement.to_dict(),
            "unit_col": self.unit_col,
            "period_col": self.period_col,
            "country_col": self.country_col,
        }


def _projection_columns(spec: ContractedAnalysisSurfaceSpec) -> dict[str, str]:
    prefix = spec.measurement.output_column
    return {
        "status": f"{prefix}_projection_status",
        "detail": f"{prefix}_projection_detail",
        "record": f"{prefix}_record_present",
        "measurement_period": f"{prefix}_measurement_period_id",
        "measurement_geo": f"{prefix}_measurement_geo_uid",
    }


def attach_contracted_measurement(
    panel: pd.DataFrame,
    spec: ContractedAnalysisSurfaceSpec,
    *,
    bundle: EmpiricalMeasurementBundle,
    geography_linkage: pd.DataFrame,
) -> tuple[pd.DataFrame, ProjectionResult]:
    projection = project_empirical_measurement(
        bundle,
        panel[[spec.unit_col, spec.period_col]],
        spec.measurement,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        target_unit_col=spec.unit_col,
        target_period_col=spec.period_col,
        geography_linkage=geography_linkage,
    )
    cols = _projection_columns(spec)
    projected = projection.frame.rename(
        columns={
            "projection_status": cols["status"],
            "projection_detail": cols["detail"],
            "measurement_record_present": cols["record"],
            "measurement_period_id": cols["measurement_period"],
            "measurement_geo_uid": cols["measurement_geo"],
        }
    )
    out = panel.merge(
        projected,
        on=[spec.unit_col, spec.period_col],
        how="left",
        validate="one_to_one",
    )
    if len(out) != len(panel):
        raise AssertionError("contracted measurement projection changed analysis-universe row count")
    return out, projection


def _audit_group(group: pd.DataFrame, spec: ContractedAnalysisSurfaceSpec) -> dict:
    cols = _projection_columns(spec)
    status = group[cols["status"]].astype(str)
    value = pd.to_numeric(group[spec.measurement.output_column], errors="coerce")
    return {
        "universe_rows": int(len(group)),
        "dhsgc_available_rows": int(group["dhsgc_available"].astype(bool).sum()),
        "observed_rows": int(status.eq("observed").sum()),
        "structural_zero_rows": int(status.eq("structural_zero").sum()),
        "outside_coverage_rows": int(status.eq("outside_coverage").sum()),
        "unresolved_rows": int(status.eq("unresolved").sum()),
        "nonmissing_values": int(value.notna().sum()),
        "zero_values": int(value.eq(0).sum()),
        "positive_values": int(value.gt(0).sum()),
    }


def build_projection_audit(
    panel: pd.DataFrame,
    spec: ContractedAnalysisSurfaceSpec,
) -> dict[str, pd.DataFrame]:
    by_period = []
    for period, group in panel.groupby(spec.period_col, dropna=False):
        row = {spec.period_col: period}
        row.update(_audit_group(group, spec))
        by_period.append(row)

    by_country = []
    for country, group in panel.groupby(spec.country_col, dropna=False):
        row = {spec.country_col: country}
        row.update(_audit_group(group, spec))
        by_country.append(row)

    by_country_period = []
    for (country, period), group in panel.groupby(
        [spec.country_col, spec.period_col], dropna=False
    ):
        row = {spec.country_col: country, spec.period_col: period}
        row.update(_audit_group(group, spec))
        by_country_period.append(row)

    return {
        "measurement_projection_audit_overall": pd.DataFrame([_audit_group(panel, spec)]),
        "measurement_projection_audit_by_period": pd.DataFrame(by_period),
        "measurement_projection_audit_by_country": pd.DataFrame(by_country),
        "measurement_projection_audit_by_country_period": pd.DataFrame(by_country_period),
    }


def run_contracted_surface_gates(
    spec: ContractedAnalysisSurfaceSpec,
    panel: pd.DataFrame,
    source_outside: dict[str, pd.DataFrame],
    projection: ProjectionResult,
    unparsed_country_gids: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []

    def add(gate: str, status: str, metric: str, value, note: str) -> None:
        rows.append(
            {
                "gate": gate,
                "status": status,
                "metric": metric,
                "value": value,
                "note": note,
            }
        )

    add(
        "U0_UNIVERSE_DECLARED",
        "GREEN",
        "analysis universe mode / authority",
        f"{spec.universe.mode} / {spec.universe.authority}",
        "The analysis universe is declared independently of empirical row presence.",
    )
    outside = source_outside["source_only_keys"]
    add(
        "U1_SOURCE_ATTRITION_QUANTIFIED",
        "YELLOW" if len(outside) else "GREEN",
        "canonical-source keys outside declared universe",
        int(len(outside)),
        "Source-only keys remain diagnostics and are not converted into controls.",
    )
    add(
        "U2_COUNTRY_IDENTITY",
        "GREEN" if len(unparsed_country_gids) == 0 else "RED",
        "GIDs without country identity",
        int(len(unparsed_country_gids)),
        "Country identity must be resolved before country fixed effects.",
    )

    report = projection.report
    add(
        "M0_CONTRACTED_MEASUREMENT_IDENTITY",
        "GREEN",
        "dataset / measure / geography / period",
        (
            f"{report.input_dataset.dataset_id} / {report.measure_id} / "
            f"{report.geography.id} / {report.period_scheme.id}"
        ),
        "The empirical input boundary and projection both validated exact shared contracts.",
    )
    reconciled = (
        report.observed_count
        + report.structural_zero_count
        + report.outside_coverage_count
        + report.unresolved_count
        == report.output_row_count
        == len(panel)
    )
    add(
        "M1_PROJECTION_ACCOUNTING",
        "GREEN" if reconciled else "RED",
        "projection status rows / output rows",
        (
            f"{report.observed_count + report.structural_zero_count + report.outside_coverage_count + report.unresolved_count} "
            f"/ {report.output_row_count}"
        ),
        "Every analysis row must have an auditable projection status; no row may disappear.",
    )
    unresolved = report.unresolved_count
    outside_n = report.outside_coverage_count
    add(
        "M2_MEASUREMENT_SUPPORT_PROFILE",
        "YELLOW" if unresolved or outside_n else "GREEN",
        "unresolved / outside coverage",
        f"{unresolved} / {outside_n}",
        "Unresolved and outside-support rows remain unavailable; E2 checks them again inside its eligibility window.",
    )
    return pd.DataFrame(rows)


def render_contracted_surface_card(
    spec: ContractedAnalysisSurfaceSpec,
    canonical_spec: CanonicalPanelSpec,
    panel: pd.DataFrame,
    projection: ProjectionResult,
    gates: pd.DataFrame,
) -> str:
    report = projection.report
    coverage = report.coverage_semantics
    lines = [
        f"# Contracted Analysis Surface — {spec.surface_id}",
        "",
        "> This E1 surface projects a validated empirical measurement into an experimental variable. It does **not** estimate a treatment effect.",
        "",
        "## Empirical input",
        "",
        f"- Dataset: `{report.input_dataset.dataset_id}` version `{report.input_dataset.version}`",
        f"- Dataset authority: `{report.input_dataset.authority.value}`",
        f"- Measurement: `{report.measure_id}`",
        f"- Geography: `{report.geography.id}`",
        f"- Period scheme: `{report.period_scheme.id}`",
        f"- Upstream absent-row semantics: `{coverage['absent_row_semantics']}`",
        f"- Upstream coverage basis: `{coverage['basis']}`",
        "",
        "## Experiment measurement choice",
        "",
        f"- Role: `{spec.measurement.role}`",
        f"- Selectors: `{json.dumps(spec.measurement.selectors, sort_keys=True)}`",
        f"- Value column: `{spec.measurement.value_column}`",
        f"- Timing offset: `{spec.measurement.timing_offset}` period(s)",
        f"- Transform: `{spec.measurement.transform or 'identity'}`",
        "",
        "The selectors, value choice, and timing are experiment semantics. They do not alter the upstream measurement contract.",
        "",
        "## Projection accounting",
        "",
        f"- Input rows: `{report.input_row_count:,}`",
        f"- Selected rows: `{report.selected_row_count:,}`",
        f"- Analysis rows: `{report.output_row_count:,}`",
        f"- Observed: `{report.observed_count:,}`",
        f"- Structural zero: `{report.structural_zero_count:,}`",
        f"- Outside coverage: `{report.outside_coverage_count:,}`",
        f"- Unresolved: `{report.unresolved_count:,}`",
        f"- Output SHA-256: `{report.output_sha256}`",
        "",
        "A structural zero can appear only when the upstream CoverageContract explicitly licenses zero within verified coverage. Unknown sparse absence remains unresolved.",
        "",
        "## Analysis universe",
        "",
        f"- Canonical lineage: `{canonical_spec.panel_id}`",
        f"- Rows: `{len(panel):,}`",
        f"- Units: `{panel[spec.unit_col].nunique():,}`",
        f"- Universe authority: `{spec.universe.authority}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Metric | Value |",
        "|---|---|---|---|",
    ]
    for _, row in gates.iterrows():
        lines.append(
            f"| {row['gate']} | {row['status']} | {row['metric']} | {row['value']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Source ingestion and source-file semantics stop upstream. This surface consumes only validated shared contracts, normalized measurement grain, an explicit geography linkage, and downstream scientific choices.",
            "",
        ]
    )
    return "\n".join(lines)


def run_contracted_analysis_surface_checkpoint(
    spec: ContractedAnalysisSurfaceSpec,
    canonical_spec: CanonicalPanelSpec,
    loaded: dict,
    *,
    bundle: EmpiricalMeasurementBundle,
    geography_linkage: pd.DataFrame,
    base_dir: str | Path = ".",
) -> dict:
    panel = build_analysis_universe(
        canonical_spec,
        loaded,
        spec.universe,
        base_dir=base_dir,
    )
    panel, projection = attach_contracted_measurement(
        panel,
        spec,
        bundle=bundle,
        geography_linkage=geography_linkage,
    )
    source_outside = build_source_outside_lattice_diagnostics(canonical_spec, loaded)
    audit = build_projection_audit(panel, spec)
    universe_profile = build_universe_country_profile(
        panel,
        unit_col=spec.unit_col,
        country_col=spec.country_col,
    )
    unparsed = build_unparsed_country_gid_profile(
        panel,
        unit_col=spec.unit_col,
        country_col=spec.country_col,
    )
    gates = run_contracted_surface_gates(
        spec,
        panel,
        source_outside,
        projection,
        unparsed,
    )
    card = render_contracted_surface_card(
        spec,
        canonical_spec,
        panel,
        projection,
        gates,
    )
    return {
        "panel": panel,
        "projection": projection,
        "source_outside": source_outside,
        "projection_audit": audit,
        "universe_country_profile": universe_profile,
        "unparsed_country_gids": unparsed,
        "gates": gates,
        "card": card,
    }


def write_contracted_analysis_surface_outputs(
    result: dict,
    spec: ContractedAnalysisSurfaceSpec,
    out_dir: str | Path,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["panel"].to_csv(
        out / "resolved_analysis_panel.csv.gz",
        index=False,
        compression="gzip",
    )
    result["panel"].head(500).to_csv(
        out / "resolved_analysis_panel_sample.csv", index=False
    )
    result["universe_country_profile"].to_csv(
        out / "analysis_universe_country_profile.csv", index=False
    )
    result["unparsed_country_gids"].to_csv(out / "unparsed_country_gids.csv", index=False)
    result["gates"].to_csv(out / "analysis_surface_gates.csv", index=False)
    for name, table in result["source_outside"].items():
        table.to_csv(out / f"{name}.csv", index=False)
    for name, table in result["projection_audit"].items():
        table.to_csv(out / f"{name}.csv", index=False)
    write_projection_report(
        result["projection"].report,
        out / "experiment_projection_report.json",
    )
    (out / "analysis_surface_card.md").write_text(result["card"], encoding="utf-8")
    (out / "analysis_surface_contract.json").write_text(
        json.dumps(spec.to_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return out
