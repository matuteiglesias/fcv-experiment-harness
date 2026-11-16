"""Project-identity → project×ADM2×biennium → source-exposure bridge (W6).

The sector proxy is a REVIEW/ABLATION DIMENSION, not an editorial jobs label.
There is no imputed jobs_direct, no jobs_indirect ground truth, no matching,
no causal identification, and no changed W5 coverage semantics.
"""
from __future__ import annotations


import numpy as np
import pandas as pd

PROJECT_KEY = ["source_family", "source_project_id"]
LOCATION_KEY = [*PROJECT_KEY, "source_location_id", "geo_uid", "period_id"]
PROJECT_CELL_KEY = [*PROJECT_KEY, "geo_uid", "period_id"]
PANEL_KEY = ["geo_uid", "period_id"]
LABELS = ("high", "low", "uncertain")
SOURCES = {"china": "cn", "world_bank": "wb"}

class BridgeError(ValueError):
    """Source/identity/schema drift; unsafe to construct new exposures."""


def _assert_unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise BridgeError(f"{label}: missing or duplicate key {keys}")


def _policy_lookup(policy: dict) -> dict:
    if policy.get("schema") != "fcv.w6.source_sector_proxy.v0":
        raise BridgeError("unexpected sector proxy policy")
    lookup = {}
    for donor in SOURCES:
        seen = {}
        for category, native in policy["sectors"][donor].items():
            if category not in LABELS:
                raise BridgeError(f"unexpected sector proxy label: {category}")
            for term in native:
                t = term.strip().casefold()
                if t in seen:
                    raise BridgeError(f"conflicting sector token for {donor}: {term}")
                seen[t] = category
        lookup[donor] = seen
    return lookup


def _sector_proxy(donor: str, raw: str, lookup: dict) -> tuple[str, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise BridgeError(f"missing native sector for {donor}")
    tokens = [v.strip().casefold() for v in raw.split("|")]
    if any(t not in lookup[donor] for t in tokens):
        bad = [t for t in tokens if t not in lookup[donor]]
        raise BridgeError(f"unmapped {donor} sector(s): {bad}")
    categories = {lookup[donor][t] for t in tokens}
    outcome = next(iter(categories)) if len(categories) == 1 else "uncertain"
    # A mixed project's semantic status is irreducibly uncertain.
    return outcome, ("mixed_sector_categories" if len(categories) > 1 else "native_sector_category")


def project_dimension(
    roster: pd.DataFrame,
    china_silver: pd.DataFrame,
    wb_silver: pd.DataFrame,
    policy: dict,
    china_release_id: str,
    wb_release_id: str,
) -> pd.DataFrame:
    """One source-versioned label per W5 project; no location-row annotation."""
    _assert_unique(roster, LOCATION_KEY, "W5 location roster")
    if set(roster.source_family) != set(SOURCES):
        raise BridgeError("unexpected donor source family")
    _assert_unique(china_silver, ["source_project_id"], "China Silver project")
    _assert_unique(wb_silver, ["project_id"], "World Bank Silver project")
    proj = roster[PROJECT_KEY].drop_duplicates()
    _assert_unique(proj, PROJECT_KEY, "W5 project identities")
    cn = china_silver.rename(columns={
        "title": "project_title", "native_sector": "native_sector_raw"
    })[["source_project_id", "project_title", "native_sector_raw"]].copy()
    cn["source_family"] = "china"
    cn["source_release_id"] = china_release_id
    wb = wb_silver.rename(columns={
        "project_id": "source_project_id", "ad_sector_names": "native_sector_raw",
    })[["source_project_id", "project_title", "native_sector_raw"]].copy()
    wb["source_family"] = "world_bank"
    wb["source_release_id"] = wb_release_id
    metadata = pd.concat([cn, wb], ignore_index=True)
    metadata["source_project_id"] = metadata.source_project_id.astype(str)
    _assert_unique(metadata, PROJECT_KEY, "source metadata")
    result = proj.merge(metadata, on=PROJECT_KEY, how="left", indicator=True, validate="one_to_one")
    if len(result) != len(proj) or not result._merge.eq("both").all():
        raise BridgeError("W5 project roster and source-native metadata do not align")
    result = result.drop(columns=["_merge"])
    if result[["project_title", "native_sector_raw", "source_release_id"]].isna().any().any():
        raise BridgeError("project-level native metadata incomplete")
    lk = _policy_lookup(policy)
    classes = [
        _sector_proxy(row.source_family, row.native_sector_raw, lk)
        for row in result.itertuples(index=False)
    ]
    result["sector_proxy"] = [c for c, _ in classes]
    result["sector_proxy_reason"] = [reason for _, reason in classes]
    result["label_origin"] = "native_sector_crosswalk"
    result["label_contract"] = policy["schema"]
    # A sector mapping does not say whether any particular project actually
    # states a jobs goal. Keep the scientific annotation missing, not 'No'.
    result["explicit_jobs_objective"] = "unannotated"
    result["jobs_channel_evidence"] = "unannotated"
    result["local_implementation_evidence"] = "unannotated"
    return result.sort_values(PROJECT_KEY, kind="stable").reset_index(drop=True)


def project_area_bridge(roster: pd.DataFrame, project_dim: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Source project→locations→area-period, deduplicating multiple WB sites."""
    _assert_unique(roster, LOCATION_KEY, "W5 location roster")
    _assert_unique(project_dim, PROJECT_KEY, "project classifications")
    _assert_unique(panel, PANEL_KEY, "W5 source area-period panel")
    if "country_iso3" not in panel:
        raise BridgeError("W5 source panel missing canonical area country")
    # Enforce one time, country and financing event per source project.
    for c in ["source_recipient_iso3", "period_id", "event_type"]:
        if roster.groupby(PROJECT_KEY, sort=False)[c].nunique().gt(1).any():
            raise BridgeError(f"source project has multiple {c}; investigate before projection")
    # Never count location duplicates twice, but keep row multiplicity as audit.
    location_multiplicity = (
        roster.groupby(PROJECT_CELL_KEY, sort=False)
        .agg(n_source_location_rows=("source_location_id", "size"),
             recipient_iso3=("source_recipient_iso3", "first"),
             event_type=("event_type", "first"),
             source_geo_confidence=("geographic_confidence", lambda v: "|".join(sorted(set(v.astype(str)))))
        ).reset_index()
    )
    base = location_multiplicity.merge(
        panel[PANEL_KEY+["country_iso3"]].rename(columns={"country_iso3":"area_country_iso3"}),
        on=PANEL_KEY, how="left", validate="many_to_one", indicator="area_join",
    )
    if len(base)!=len(location_multiplicity) or not base.area_join.eq("both").all():
        raise BridgeError("a mapped project area-period is absent from W5 source panel")
    base = base.drop(columns=["area_join"])
    base["recipient_area_aligned"] = base.recipient_iso3.eq(base.area_country_iso3)
    base = base.merge(
        project_dim[PROJECT_KEY+["source_release_id", "sector_proxy", "sector_proxy_reason", "label_contract"]],
        on=PROJECT_KEY, how="left", indicator=True, validate="many_to_one",
    )
    if not base._merge.eq("both").all() or len(base) != len(location_multiplicity):
        raise BridgeError("not all project-area cells received exactly one label")
    return base.drop(columns=["_merge"]).sort_values(PROJECT_CELL_KEY, kind="stable").reset_index(drop=True)


def panel_proxy_bridge(
    panel: pd.DataFrame, roster: pd.DataFrame, project_cells: pd.DataFrame,
) -> pd.DataFrame:
    """Versioned project labels on the original W5 panel with exact source parity."""
    _assert_unique(panel, PANEL_KEY, "W5 source panel")
    _assert_unique(project_cells, PROJECT_CELL_KEY, "deduplicated project-area-period")
    if not project_cells.sector_proxy.isin(LABELS).all():
        raise BridgeError("unknown project sector proxy")
    if not project_cells.source_family.isin(SOURCES).all():
        raise BridgeError("unknown project source family")
    if not project_cells.source_geo_confidence.notna().all():
        raise BridgeError("missing geographic provenance")
    if (project_cells.n_source_location_rows.lt(1)).any():
        raise BridgeError("non-positive source location count")
    # Exact preservation of coverage and source-native project counts.
    dedup = roster.drop_duplicates(PROJECT_CELL_KEY)
    if len(dedup) != len(project_cells):
        raise BridgeError("project-area-period bridge cardinality changed")
    if not dedup[PROJECT_CELL_KEY].sort_values(PROJECT_CELL_KEY).reset_index(drop=True).equals(
        project_cells[PROJECT_CELL_KEY].sort_values(PROJECT_CELL_KEY).reset_index(drop=True)):
        raise BridgeError("project-area-period membership changed")
    if "country_iso3" not in panel:
        raise BridgeError("W5 panel lacks country authority")
    check=project_cells[["geo_uid","period_id","area_country_iso3"]].merge(
        panel[["geo_uid","period_id","country_iso3"]],on=PANEL_KEY,
        how="left",validate="many_to_one"
    )
    if len(check)!=len(project_cells) or not check.area_country_iso3.eq(check.country_iso3).all():
        raise BridgeError("project area country disagrees with W5 canonical panel")
    if not project_cells.recipient_area_aligned.eq(
        project_cells.recipient_iso3.eq(project_cells.area_country_iso3)
    ).all():
        raise BridgeError("recipient/area alignment flag is inconsistent")
    counts = project_cells.groupby(["source_family", "sector_proxy", *PANEL_KEY], sort=False).source_project_id.nunique().sort_index()
    out = panel.copy()
    for source, prefix in SOURCES.items():
        for label in LABELS:
            col = f"{prefix}_sector_{label}_count"
            part = counts.loc[(source, label)] if (source, label) in counts.index.droplevel([2,3]).unique() else pd.Series(dtype=int)
            if part.empty:
                out[col] = 0
            else:
                part = part.rename(col).reset_index()
                out = out.merge(part, on=PANEL_KEY, how="left", validate="one_to_one")
                out[col] = out[col].fillna(0).astype("int64")
        cols = [f"{prefix}_sector_{label}_count" for label in LABELS]
        baseline = out[f"{prefix}_project_count"].astype("int64")
        if not (out[cols].sum(axis=1).eq(baseline)).all():
            mismatch = (~out[cols].sum(axis=1).eq(baseline)).sum()
            raise BridgeError(f"{source} project-count parity failed for {mismatch} area periods")
        # Flag inherited source-geometry extensions across recipient borders.
        # Baseline counts must still be reproduced exactly. Such rows are not
        # declared credible exposures for a downstream jobs-effect estimator.
        bad=project_cells.loc[
            project_cells.source_family.eq(source) & ~project_cells.recipient_area_aligned
        ].groupby(PANEL_KEY).source_project_id.nunique().rename(f"{prefix}_crossrecipient_project_count")
        out=out.merge(bad.reset_index(),on=PANEL_KEY,how="left",validate="one_to_one")
        out[f"{prefix}_crossrecipient_project_count"]=(
            out[f"{prefix}_crossrecipient_project_count"].fillna(0).astype("int64")
        )
        out[f"{prefix}_sector_group"] = np.select(
            [baseline.eq(0),out[cols[0]].eq(baseline),out[cols[1]].eq(baseline)],
            ["none_recorded","high_only","low_only"],
            default="mixed_or_uncertain",
        )
    if len(out) != len(panel) or not out[PANEL_KEY].equals(panel[PANEL_KEY]):
        raise BridgeError("W5 area-period panel shape/order drift")
    out["proxy_contract"] = "fcv.w6.source_sector_proxy.v0"
    return out
