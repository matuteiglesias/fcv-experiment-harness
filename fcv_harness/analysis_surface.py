from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import json

import numpy as np
import pandas as pd

from .canonical import (
    CanonicalPanelSpec,
    _lattice_name,
    _period_start,
    normalize_project_source,
    normalize_simple_source,
)
from .lattice_diagnostics import attach_country_iso3, build_source_outside_lattice_diagnostics


SUPPORTED_UNIVERSE_MODES = {"canonical_lattice", "external_gid_spine"}
SUPPORTED_OUTCOME_POLICIES = {
    "unresolved",
    "observed_records_only",
    "zero_within_verified_coverage",
}
SUPPORTED_GEOGRAPHY_SCOPES = {"analysis_universe"}


@dataclass(frozen=True)
class AnalysisUniverseSpec:
    mode: str
    authority: str
    external_spine_path: Optional[str] = None
    external_gid_col: str = "GID"
    external_period_col: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict) -> "AnalysisUniverseSpec":
        spec = cls(
            mode=str(payload["mode"]),
            authority=str(payload.get("authority", payload["mode"])),
            external_spine_path=payload.get("external_spine_path"),
            external_gid_col=str(payload.get("external_gid_col", "GID")),
            external_period_col=payload.get("external_period_col"),
        )
        if spec.mode not in SUPPORTED_UNIVERSE_MODES:
            raise ValueError(
                f"Unsupported analysis-universe mode {spec.mode!r}; "
                f"supported: {sorted(SUPPORTED_UNIVERSE_MODES)}"
            )
        if spec.mode == "external_gid_spine" and not spec.external_spine_path:
            raise ValueError("external_gid_spine requires external_spine_path")
        return spec


@dataclass(frozen=True)
class AreaPeriodOutcomeResolutionSpec:
    source: str
    column: str
    policy: str
    verified_period_start: Optional[str] = None
    verified_period_end: Optional[str] = None
    verified_geography_scope: Optional[str] = None
    coverage_basis: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict) -> "AreaPeriodOutcomeResolutionSpec":
        spec = cls(
            source=str(payload["source"]),
            column=str(payload["column"]),
            policy=str(payload["policy"]),
            verified_period_start=(
                str(payload["verified_period_start"])
                if payload.get("verified_period_start") is not None
                else None
            ),
            verified_period_end=(
                str(payload["verified_period_end"])
                if payload.get("verified_period_end") is not None
                else None
            ),
            verified_geography_scope=payload.get("verified_geography_scope"),
            coverage_basis=payload.get("coverage_basis"),
        )
        if spec.policy not in SUPPORTED_OUTCOME_POLICIES:
            raise ValueError(
                f"Unsupported outcome policy {spec.policy!r}; "
                f"supported: {sorted(SUPPORTED_OUTCOME_POLICIES)}"
            )
        if spec.policy == "zero_within_verified_coverage":
            missing = [
                name
                for name, value in [
                    ("verified_period_start", spec.verified_period_start),
                    ("verified_period_end", spec.verified_period_end),
                    ("verified_geography_scope", spec.verified_geography_scope),
                    ("coverage_basis", spec.coverage_basis),
                ]
                if not value
            ]
            if missing:
                raise ValueError(
                    "zero_within_verified_coverage requires explicit "
                    + ", ".join(missing)
                )
            if spec.verified_geography_scope not in SUPPORTED_GEOGRAPHY_SCOPES:
                raise ValueError(
                    "verified_geography_scope must be one of "
                    f"{sorted(SUPPORTED_GEOGRAPHY_SCOPES)}"
                )
        return spec


@dataclass(frozen=True)
class AnalysisSurfaceSpec:
    surface_id: str
    canonical_manifest: str
    universe: AnalysisUniverseSpec
    outcome: AreaPeriodOutcomeResolutionSpec
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path) -> "AnalysisSurfaceSpec":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            surface_id=str(raw["surface_id"]),
            canonical_manifest=str(raw["canonical_manifest"]),
            universe=AnalysisUniverseSpec.from_dict(raw["universe"]),
            outcome=AreaPeriodOutcomeResolutionSpec.from_dict(raw["outcome"]),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )


def _resolve_path(path: str, base_dir=".") -> Path:
    p = Path(path)
    return p if p.is_absolute() else Path(base_dir) / p


def _sorted_periods(values):
    vals = pd.Series(values).dropna().astype(str).unique().tolist()
    return sorted(vals, key=lambda x: (_period_start(x), x))


def _period_mask(values: pd.Series, start: str, end: str) -> pd.Series:
    lo = _period_start(start)
    hi = _period_start(end)
    years = values.astype(str).map(_period_start)
    return years.between(lo, hi, inclusive="both")


def _universe_keys_from_spec(
    canonical_spec: CanonicalPanelSpec,
    loaded: dict,
    universe_spec: AnalysisUniverseSpec,
    base_dir=".",
) -> pd.DataFrame:
    key = [canonical_spec.unit_col, canonical_spec.period_col]
    lattice_name = _lattice_name(canonical_spec)
    lattice = loaded[lattice_name]

    if universe_spec.mode == "canonical_lattice":
        return lattice[key].drop_duplicates().copy()

    spine_path = _resolve_path(universe_spec.external_spine_path, base_dir)
    spine = pd.read_csv(spine_path)
    if universe_spec.external_gid_col not in spine.columns:
        raise KeyError(
            f"External universe spine missing GID column "
            f"{universe_spec.external_gid_col!r}"
        )

    gid = spine[universe_spec.external_gid_col].rename(canonical_spec.unit_col)
    gids = pd.DataFrame({canonical_spec.unit_col: gid.dropna().astype(str).unique()})

    if (
        universe_spec.external_period_col
        and universe_spec.external_period_col in spine.columns
    ):
        keys = spine[
            [universe_spec.external_gid_col, universe_spec.external_period_col]
        ].rename(
            columns={
                universe_spec.external_gid_col: canonical_spec.unit_col,
                universe_spec.external_period_col: canonical_spec.period_col,
            }
        )
        keys = keys.dropna().drop_duplicates()
    else:
        periods = pd.DataFrame(
            {
                canonical_spec.period_col:
                    _sorted_periods(lattice[canonical_spec.period_col])
            }
        )
        gids["_join"] = 1
        periods["_join"] = 1
        keys = gids.merge(periods, on="_join").drop(columns="_join")

    if keys.duplicated(key).any():
        raise ValueError("Analysis universe spine is not unique at GID×TimePeriod")
    return keys


def build_analysis_universe(
    canonical_spec: CanonicalPanelSpec,
    loaded: dict,
    universe_spec: AnalysisUniverseSpec,
    base_dir=".",
) -> pd.DataFrame:
    """Build an explicit analysis-universe panel.

    The current production manifest uses the canonical DHSGC lattice and labels that
    restriction explicitly. An external GID spine can later replace it without
    changing project/outcome normalization semantics.
    """
    key = [canonical_spec.unit_col, canonical_spec.period_col]
    lattice_name = _lattice_name(canonical_spec)
    lattice = loaded[lattice_name].copy()

    universe = _universe_keys_from_spec(
        canonical_spec, loaded, universe_spec, base_dir=base_dir
    )
    universe = universe.merge(
        lattice,
        on=key,
        how="left",
        indicator="_dhsgc_merge",
        validate="one_to_one",
    )
    universe["dhsgc_available"] = universe["_dhsgc_merge"].eq("both")
    universe = universe.drop(columns="_dhsgc_merge")

    universe.insert(0, "panel_id", canonical_spec.panel_id)
    universe["geo_scheme"] = canonical_spec.geo_scheme
    universe["geo_level"] = canonical_spec.geo_level
    universe["period_years"] = canonical_spec.period_years
    universe["alignment_year"] = canonical_spec.alignment_year
    universe["annotation_version"] = canonical_spec.annotation_version
    universe["analysis_universe_mode"] = universe_spec.mode
    universe["analysis_universe_authority"] = universe_spec.authority

    for name, contract in canonical_spec.sources.items():
        if name == lattice_name:
            continue
        df = loaded.get(name)
        if df is None:
            continue
        if contract.kind == "project":
            normalized = normalize_project_source(df, contract, canonical_spec)
        else:
            normalized = normalize_simple_source(df, contract, canonical_spec)

        before = len(universe)
        universe = universe.merge(
            normalized, on=key, how="left", validate="one_to_one"
        )
        if len(universe) != before:
            raise AssertionError(
                f"Analysis universe changed row count while attaching {name}"
            )

        prefix = contract.prefix or name
        for col in [c for c in universe.columns if c.startswith(f"{prefix}_")]:
            if (
                col.endswith("_present")
                or col.endswith("_positive")
                or col.endswith("_observed")
                or col.endswith("_zero_only")
            ):
                universe[col] = (
                    universe[col].astype("boolean").fillna(False).astype(bool)
                )

    universe = attach_country_iso3(
        universe,
        unit_col=canonical_spec.unit_col,
        country_col="country_iso3",
    )
    if universe.duplicated(key).any():
        raise AssertionError("Analysis universe is not unique at GID×TimePeriod")
    return universe


def resolve_area_period_outcome(
    panel: pd.DataFrame,
    *,
    unit_col: str,
    period_col: str,
    source: str,
    value_col: str,
    policy: str,
    verified_period_start: Optional[str] = None,
    verified_period_end: Optional[str] = None,
    verified_geography_scope: Optional[str] = None,
    coverage_basis: Optional[str] = None,
) -> pd.DataFrame:
    """Resolve sparse area-period outcome semantics without losing raw provenance."""
    record_col = f"{source}_record_present"
    required = [unit_col, period_col, value_col, record_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise KeyError(f"Outcome resolution missing columns: {missing}")
    if policy not in SUPPORTED_OUTCOME_POLICIES:
        raise ValueError(f"Unsupported outcome policy: {policy}")

    if policy == "zero_within_verified_coverage":
        required_meta = {
            "verified_period_start": verified_period_start,
            "verified_period_end": verified_period_end,
            "verified_geography_scope": verified_geography_scope,
            "coverage_basis": coverage_basis,
        }
        missing_meta = [k for k, v in required_meta.items() if not v]
        if missing_meta:
            raise ValueError(
                "zero_within_verified_coverage requires explicit "
                + ", ".join(missing_meta)
            )
        if verified_geography_scope not in SUPPORTED_GEOGRAPHY_SCOPES:
            raise ValueError(
                f"Unsupported verified geography scope: {verified_geography_scope}"
            )

    out = panel[[unit_col, period_col]].copy()
    raw = pd.to_numeric(panel[value_col], errors="coerce")
    record = panel[record_col].astype("boolean").fillna(False).astype(bool)

    if verified_period_start and verified_period_end:
        coverage = _period_mask(
            panel[period_col], verified_period_start, verified_period_end
        )
    else:
        coverage = pd.Series(True, index=panel.index)

    resolved = raw.copy()
    status = pd.Series("absent_record_unresolved", index=panel.index, dtype="string")

    status.loc[coverage & record & raw.gt(0)] = "observed_record_positive"
    status.loc[coverage & record & raw.eq(0)] = "observed_record_zero"
    status.loc[coverage & record & raw.isna()] = "record_present_value_missing"
    status.loc[~coverage] = "outside_verified_coverage"

    if policy == "observed_records_only":
        status.loc[coverage & ~record] = "absent_record_excluded"
    elif policy == "zero_within_verified_coverage":
        fill = coverage & ~record & raw.isna()
        resolved.loc[fill] = 0.0
        status.loc[fill] = "structural_zero_from_absent_record"
    elif policy == "unresolved":
        status.loc[coverage & ~record] = "absent_record_unresolved"

    out["outcome_record_present"] = record
    out["outcome_value_raw"] = raw
    out["outcome_value_resolved"] = resolved
    out["outcome_coverage_eligible"] = coverage.astype(bool)
    out["outcome_resolution_status"] = status
    out["outcome_resolution_policy"] = policy
    out["outcome_coverage_basis"] = coverage_basis
    return out


def attach_resolved_outcome(
    panel: pd.DataFrame,
    spec: AnalysisSurfaceSpec,
) -> pd.DataFrame:
    resolved = resolve_area_period_outcome(
        panel,
        unit_col=spec.unit_col,
        period_col=spec.period_col,
        source=spec.outcome.source,
        value_col=spec.outcome.column,
        policy=spec.outcome.policy,
        verified_period_start=spec.outcome.verified_period_start,
        verified_period_end=spec.outcome.verified_period_end,
        verified_geography_scope=spec.outcome.verified_geography_scope,
        coverage_basis=spec.outcome.coverage_basis,
    )
    out = panel.copy()
    out["acled_value_raw"] = resolved["outcome_value_raw"].to_numpy()
    out["acled_value_resolved"] = resolved["outcome_value_resolved"].to_numpy()
    out["acled_record_present_resolved_view"] = (
        resolved["outcome_record_present"].to_numpy()
    )
    out["acled_coverage_eligible"] = (
        resolved["outcome_coverage_eligible"].to_numpy()
    )
    out["acled_resolution_status"] = (
        resolved["outcome_resolution_status"].to_numpy()
    )
    out["acled_resolution_policy"] = spec.outcome.policy
    out["acled_coverage_basis"] = spec.outcome.coverage_basis
    return out


def _audit_group(g: pd.DataFrame) -> dict:
    raw = pd.to_numeric(g["acled_value_raw"], errors="coerce")
    resolved = pd.to_numeric(g["acled_value_resolved"], errors="coerce")
    record = g["acled_record_present_resolved_view"].astype(bool)
    status = g["acled_resolution_status"].astype(str)
    return {
        "universe_rows": int(len(g)),
        "dhsgc_available_rows": int(g["dhsgc_available"].astype(bool).sum()),
        "observed_acled_records": int(record.sum()),
        "observed_positive_vac": int((record & raw.gt(0)).sum()),
        "observed_zero_vac": int((record & raw.eq(0)).sum()),
        "observed_missing_vac": int((record & raw.isna()).sum()),
        "structural_zeros_added": int(
            status.eq("structural_zero_from_absent_record").sum()
        ),
        "outside_coverage_rows": int(
            status.eq("outside_verified_coverage").sum()
        ),
        "resolved_nonmissing": int(resolved.notna().sum()),
        "resolved_zero": int(resolved.eq(0).sum()),
        "resolved_positive": int(resolved.gt(0).sum()),
    }


def build_acled_measurement_audit(
    resolved_panel: pd.DataFrame,
    country_col="country_iso3",
    period_col="TimePeriod",
):
    required = [
        country_col,
        period_col,
        "dhsgc_available",
        "acled_value_raw",
        "acled_value_resolved",
        "acled_record_present_resolved_view",
        "acled_resolution_status",
    ]
    missing = [c for c in required if c not in resolved_panel.columns]
    if missing:
        raise KeyError(f"Resolved analysis surface missing audit fields: {missing}")

    cp_rows = []
    for (country, period), g in resolved_panel.groupby(
        [country_col, period_col], dropna=False
    ):
        row = {country_col: country, period_col: period}
        row.update(_audit_group(g))
        cp_rows.append(row)
    by_country_period = pd.DataFrame(cp_rows)

    period_rows = []
    for period, g in resolved_panel.groupby(period_col, dropna=False):
        row = {period_col: period}
        row.update(_audit_group(g))
        period_rows.append(row)
    by_period = pd.DataFrame(period_rows)

    country_rows = []
    for country, g in resolved_panel.groupby(country_col, dropna=False):
        row = {country_col: country}
        row.update(_audit_group(g))
        country_rows.append(row)
    by_country = pd.DataFrame(country_rows)

    overall = pd.DataFrame([_audit_group(resolved_panel)])
    return {
        "acled_measurement_audit_by_country_period": by_country_period,
        "acled_measurement_audit_by_period": by_period,
        "acled_measurement_audit_by_country": by_country,
        "acled_measurement_audit_overall": overall,
    }


def build_universe_country_profile(
    panel: pd.DataFrame,
    unit_col="GID",
    country_col="country_iso3",
):
    rows = []
    for country, g in panel.groupby(country_col, dropna=False):
        rows.append(
            {
                country_col: country,
                "unique_gid": int(g[unit_col].nunique()),
                "universe_rows": int(len(g)),
                "dhsgc_available_rows": int(g["dhsgc_available"].astype(bool).sum()),
                "dhsgc_available_share": float(g["dhsgc_available"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(country_col)


def build_unparsed_country_gid_profile(
    panel: pd.DataFrame,
    unit_col="GID",
    country_col="country_iso3",
):
    missing = panel[country_col].isna()
    if not missing.any():
        return pd.DataFrame(
            columns=[unit_col, "rows", "periods", "first_period", "last_period"]
        )
    rows = []
    for gid, g in panel.loc[missing].groupby(unit_col, dropna=False):
        periods = _sorted_periods(g["TimePeriod"])
        rows.append(
            {
                unit_col: gid,
                "rows": int(len(g)),
                "periods": int(g["TimePeriod"].nunique()),
                "first_period": periods[0] if periods else None,
                "last_period": periods[-1] if periods else None,
            }
        )
    return pd.DataFrame(rows).sort_values(unit_col)


def run_analysis_surface_gates(
    surface_spec: AnalysisSurfaceSpec,
    panel: pd.DataFrame,
    source_outside: dict,
    acled_audit: dict,
    unparsed_country_gids: Optional[pd.DataFrame] = None,
):
    rows = []

    def add(gate, status, metric, value, note):
        rows.append(
            {
                "gate": gate,
                "status": status,
                "metric": metric,
                "value": value,
                "note": note,
            }
        )

    mode = surface_spec.universe.mode
    authority = surface_spec.universe.authority
    add(
        "U0_UNIVERSE_DECLARED",
        "GREEN",
        "analysis universe mode / authority",
        f"{mode} / {authority}",
        (
            "The current production universe is explicit. canonical_lattice means a DHSGC-restricted research universe, not all ADM2 Africa."
            if mode == "canonical_lattice"
            else "An external GID spine defines the research universe."
        ),
    )

    outside = source_outside["source_only_keys"]
    add(
        "U1_SOURCE_ATTRITION_QUANTIFIED",
        "YELLOW" if len(outside) else "GREEN",
        "substantive source GID-period keys outside declared universe",
        int(len(outside)),
        "These keys remain provenance/selection evidence and are not silently added as controls.",
    )

    unparsed_n = (
        int(len(unparsed_country_gids))
        if unparsed_country_gids is not None
        else int(panel["country_iso3"].isna().groupby(panel["GID"]).any().sum())
    )
    add(
        "U2_COUNTRY_IDENTITY",
        "GREEN" if unparsed_n == 0 else "RED",
        "GIDs without GID-derived country identity",
        unparsed_n,
        "Country identity must be resolved before country fixed effects or country-level coverage claims.",
    )

    unresolved = int(
        panel["acled_resolution_status"].isin(
            ["absent_record_unresolved", "record_present_value_missing"]
        ).sum()
    )
    add(
        "A0_ACLED_POLICY_EXPLICIT",
        "GREEN" if surface_spec.outcome.policy != "unresolved" else "RED",
        "ACLED absent-record policy",
        surface_spec.outcome.policy,
        f"Coverage basis: {surface_spec.outcome.coverage_basis}",
    )
    add(
        "A1_ACLED_RESOLUTION_COMPLETENESS",
        "GREEN" if unresolved == 0 else "RED",
        "unresolved rows in declared resolution surface",
        unresolved,
        "No record-present missing value or unresolved absent record should remain in the verified coverage window.",
    )

    overall = acled_audit["acled_measurement_audit_overall"].iloc[0]
    structural = int(overall["structural_zeros_added"])
    observed = int(overall["observed_acled_records"])
    add(
        "A2_ACLED_STRUCTURAL_ZERO_PROFILE",
        "YELLOW",
        "structural zeros added / observed ACLED records",
        f"{structural} / {observed}",
        "High zero shares are expected for sparse conflict outcomes but must remain visible in later model diagnostics.",
    )

    coverage_authority = (
        "YELLOW"
        if (surface_spec.outcome.coverage_basis or "").startswith("legacy_")
        else "GREEN"
    )
    add(
        "A3_ACLED_COVERAGE_PROVENANCE",
        coverage_authority,
        "coverage provenance",
        surface_spec.outcome.coverage_basis,
        "Legacy coverage semantics are explicit but have not yet been independently rebuilt from raw ACLED.",
    )
    return pd.DataFrame(rows)


def render_analysis_surface_card(
    surface_spec: AnalysisSurfaceSpec,
    canonical_spec: CanonicalPanelSpec,
    panel: pd.DataFrame,
    gates: pd.DataFrame,
    universe_profile: pd.DataFrame,
    acled_audit: dict,
    unparsed_country_gids: Optional[pd.DataFrame] = None,
):
    overall = acled_audit["acled_measurement_audit_overall"].iloc[0]
    periods = _sorted_periods(panel[surface_spec.period_col])
    lines = [
        f"# Analysis Surface Card — {surface_spec.surface_id}",
        "",
        "> This surface resolves the observation universe and ACLED measurement semantics. It does **not** estimate a treatment effect.",
        "",
        "## Analysis universe",
        "",
        f"- Canonical panel lineage: `{canonical_spec.panel_id}`",
        f"- Universe mode: `{surface_spec.universe.mode}`",
        f"- Universe authority: `{surface_spec.universe.authority}`",
        f"- Rows: `{len(panel):,}`",
        f"- GIDs: `{panel[surface_spec.unit_col].nunique():,}`",
        f"- Countries with resolved ISO3 identity: `{panel[surface_spec.country_col].nunique():,}`",
        f"- GIDs with unresolved country identity: `{0 if unparsed_country_gids is None else len(unparsed_country_gids):,}`",
        f"- Periods: `{len(periods)}` ({periods[0] if periods else '?'} to {periods[-1] if periods else '?'})",
        f"- DHSGC-available share: `{panel['dhsgc_available'].mean():.4f}`",
        "",
        "The current production manifest uses the recovered DHSGC lattice as an explicit **restricted analysis universe**. It is not asserted to be the full ADM2 geography of Africa. A future external GID spine can replace this universe without changing source normalization or experiment semantics.",
        "",
        "## ACLED resolution",
        "",
        f"- Raw field: `{surface_spec.outcome.column}`",
        f"- Policy: `{surface_spec.outcome.policy}`",
        f"- Verified period window: `{surface_spec.outcome.verified_period_start}` through `{surface_spec.outcome.verified_period_end}`",
        f"- Verified geography scope: `{surface_spec.outcome.verified_geography_scope}`",
        f"- Coverage basis: `{surface_spec.outcome.coverage_basis}`",
        f"- Observed ACLED records: `{int(overall['observed_acled_records']):,}`",
        f"- Observed positive VAC rows: `{int(overall['observed_positive_vac']):,}`",
        f"- Observed zero VAC rows: `{int(overall['observed_zero_vac']):,}`",
        f"- Structural zeros added: `{int(overall['structural_zeros_added']):,}`",
        f"- Outside verified coverage: `{int(overall['outside_coverage_rows']):,}`",
        "",
        "Resolved values retain the raw observation and a resolution status. An absent record becomes zero only inside the explicitly declared coverage window and geography scope; outside coverage it remains unavailable.",
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
            "## Scientific boundary",
            "",
            "- Legacy job annotations remain unchanged.",
            "- WBad/WBkg source reconciliation remains deferred.",
            "- DHSGC covariates are attached measurements, not an automatic control set.",
            "- The current universe restriction and ACLED coverage basis remain explicit inputs to later sensitivity work.",
            "- No coefficient, matching result, DiD estimate, or event-study estimate is produced here.",
            "",
            "## Next step",
            "",
            "Re-run E0 on the resolved surface. If the universe/measurement gates remain usable, the next PR may run the predeclared WB measurement calibration matrix under one common universe and one common ACLED resolution policy.",
            "",
        ]
    )
    return "\n".join(lines)


def run_analysis_surface_checkpoint(
    surface_spec: AnalysisSurfaceSpec,
    canonical_spec: CanonicalPanelSpec,
    loaded: dict,
    base_dir=".",
):
    panel = build_analysis_universe(
        canonical_spec,
        loaded,
        surface_spec.universe,
        base_dir=base_dir,
    )
    panel = attach_resolved_outcome(panel, surface_spec)
    source_outside = build_source_outside_lattice_diagnostics(
        canonical_spec, loaded
    )
    acled_audit = build_acled_measurement_audit(
        panel,
        country_col=surface_spec.country_col,
        period_col=surface_spec.period_col,
    )
    universe_profile = build_universe_country_profile(
        panel,
        unit_col=surface_spec.unit_col,
        country_col=surface_spec.country_col,
    )
    unparsed_country_gids = build_unparsed_country_gid_profile(
        panel,
        unit_col=surface_spec.unit_col,
        country_col=surface_spec.country_col,
    )
    gates = run_analysis_surface_gates(
        surface_spec,
        panel,
        source_outside,
        acled_audit,
        unparsed_country_gids=unparsed_country_gids,
    )
    card = render_analysis_surface_card(
        surface_spec,
        canonical_spec,
        panel,
        gates,
        universe_profile,
        acled_audit,
        unparsed_country_gids=unparsed_country_gids,
    )
    return {
        "panel": panel,
        "source_outside": source_outside,
        "acled_audit": acled_audit,
        "universe_country_profile": universe_profile,
        "unparsed_country_gids": unparsed_country_gids,
        "gates": gates,
        "card": card,
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    return value


def write_analysis_surface_outputs(
    result: dict,
    surface_spec: AnalysisSurfaceSpec,
    out_dir,
):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    result["panel"].to_csv(
        out / "resolved_analysis_panel.csv.gz",
        index=False,
        compression="gzip",
    )
    result["panel"].head(500).to_csv(
        out / "resolved_analysis_panel_sample.csv",
        index=False,
    )
    result["universe_country_profile"].to_csv(
        out / "analysis_universe_country_profile.csv", index=False
    )
    result["unparsed_country_gids"].to_csv(
        out / "unparsed_country_gids.csv", index=False
    )
    result["gates"].to_csv(out / "analysis_surface_gates.csv", index=False)
    for name, table in result["source_outside"].items():
        table.to_csv(out / f"{name}.csv", index=False)
    for name, table in result["acled_audit"].items():
        table.to_csv(out / f"{name}.csv", index=False)
    (out / "analysis_surface_card.md").write_text(
        result["card"], encoding="utf-8"
    )
    contract = asdict(surface_spec)
    (out / "analysis_surface_contract.json").write_text(
        json.dumps(_json_safe(contract), indent=2), encoding="utf-8"
    )
    return out
