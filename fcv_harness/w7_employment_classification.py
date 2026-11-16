"""Bounded W7 classification and propagation contract.

Native sectors are candidate channels only.  This module never turns a title,
sector, or absence of text into an employment label.
"""
from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_KEY = ["source_family", "source_release_id", "source_project_id"]
CELL_KEY = ["source_family", "source_release_id", "source_project_id", "geo_uid", "period_id"]
PANEL_KEY = ["geo_uid", "period_id"]
CATEGORIES = [
    "productive_enterprise", "physical_infrastructure", "skills_education",
    "health_social", "governance_finance", "humanitarian_environment_other",
]
STATUSES = {"unreviewed", "unclear", "reviewed"}
CLASSES = {"reviewed_jobs", "reviewed_nonjobs", "unresolved"}
ANNOTATION_COLUMNS = [
    *PROJECT_KEY, "annotation_version", "editorial_status", "class", "direct",
    "indirect", "local_implementation", "confidence", "evidence_source",
    "evidence_content_hash", "evidence_reference", "reviewer",
]


class W7ClassificationError(ValueError):
    """Fail-closed schema, provenance, identity, or conservation error."""


def _unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = [k for k in keys if k not in frame]
    if missing or frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise W7ClassificationError(f"{label}: missing or duplicate key {keys}")


def load_policy(policy: dict | str | Path) -> dict:
    if not isinstance(policy, dict):
        policy = json.loads(Path(policy).read_text())
    if policy.get("schema") != "fcv.w7.native_sector_channels.v0":
        raise W7ClassificationError("unexpected W7 channel policy")
    if policy.get("categories") != CATEGORIES:
        raise W7ClassificationError("W7 category order drift")
    donors = policy.get("donors", {})
    if set(donors) != {"china", "world_bank"} or len(donors["china"]) != 19 or len(donors["world_bank"]) != 20:
        raise W7ClassificationError("W7 donor token inventory drift")
    if any(v not in CATEGORIES for d in donors.values() for v in d.values()):
        raise W7ClassificationError("unknown W7 channel category")
    return policy


def _channels(donor: str, raw: Any, lookup: dict[str, dict[str, str]]) -> list[str]:
    if donor not in lookup:
        raise W7ClassificationError(f"unrecognized donor {donor}")
    if not isinstance(raw, str) or not raw.strip():
        raise W7ClassificationError(f"missing native sector for {donor}")
    tokens = [t.strip() for t in raw.split("|") if t.strip()]
    missing = [t for t in tokens if t not in lookup[donor]]
    if missing:
        raise W7ClassificationError(f"unmapped {donor} sector token(s): {missing}")
    return sorted({lookup[donor][t] for t in tokens}, key=CATEGORIES.index)


def build_project_ledger(dimension: pd.DataFrame, policy: dict | str | Path) -> pd.DataFrame:
    """Create one exact source-qualified row per project, initially unresolved."""
    policy = load_policy(policy)
    _unique(dimension, PROJECT_KEY, "W6 project dimension")
    required = {"project_title", "native_sector_raw"}
    if not required.issubset(dimension.columns):
        raise W7ClassificationError(f"dimension missing {sorted(required - set(dimension))}")
    out = dimension.copy()
    lookup = policy["donors"]
    tags = [_channels(r.source_family, r.native_sector_raw, lookup) for r in out.itertuples()]
    out["candidate_sector_channel"] = ["|".join(x) for x in tags]
    out["candidate_sector_channel_count"] = [len(x) for x in tags]
    out["editorial_status"] = "unreviewed"
    out["annotation_version"] = "w7.inventory.v0"
    out["class"] = "unresolved"
    out["full_text_status"] = "not_supplied"
    out["direct"] = pd.NA
    out["indirect"] = pd.NA
    out["local_implementation"] = pd.NA
    out["confidence"] = pd.NA
    for col in ["evidence_source", "evidence_content_hash", "evidence_reference", "reviewer"]:
        out[col] = pd.NA
    return out.sort_values(PROJECT_KEY, kind="stable").reset_index(drop=True)


def _bool_or_na(value: Any, field: str) -> bool | None:
    if pd.isna(value) or value in ("", None):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.casefold() in {"yes", "true", "1"}:
        return True
    if isinstance(value, str) and value.casefold() in {"no", "false", "0"}:
        return False
    raise W7ClassificationError(f"invalid {field}; use yes/no")


def validate_editorial_state(ledger: pd.DataFrame) -> None:
    """Fail closed even when a caller bypasses apply_editorial_annotations."""
    _unique(ledger, PROJECT_KEY, "W7 reviewed ledger")
    required = set(ANNOTATION_COLUMNS)
    missing = sorted(required - set(ledger))
    if missing:
        raise W7ClassificationError(f"W7 ledger missing editorial fields: {missing}")
    if not ledger.editorial_status.isin(STATUSES).all() or not ledger["class"].isin(CLASSES).all():
        raise W7ClassificationError("invalid W7 editorial status or class")
    if ledger.annotation_version.isna().any() or ledger.annotation_version.astype(str).str.strip().eq("").any():
        raise W7ClassificationError("empty annotation_version")
    for _, row in ledger.iterrows():
        direct, indirect = _bool_or_na(row["direct"], "direct"), _bool_or_na(row["indirect"], "indirect")
        local = _bool_or_na(row["local_implementation"], "local_implementation")
        cls, status = row["class"], row["editorial_status"]
        if status != "reviewed":
            if cls != "unresolved":
                raise W7ClassificationError("unreviewed/unclear projects cannot receive confirmed classes")
            if status == "unreviewed" and any(v is not None for v in (direct, indirect, local)):
                raise W7ClassificationError("unreviewed projects cannot contain definitive mechanism labels")
            continue
        if cls == "unresolved":
            raise W7ClassificationError("reviewed annotation cannot be unresolved")
        if local is not True:
            raise W7ClassificationError("confirmed jobs/other requires documented local implementation")
        if cls == "reviewed_jobs" and not (direct is True or indirect is True):
            raise W7ClassificationError("reviewed_jobs requires direct or indirect yes")
        if cls == "reviewed_nonjobs" and not (direct is False and indirect is False):
            raise W7ClassificationError("reviewed_nonjobs requires BOTH direct and indirect no")
        if row["confidence"] not in ("high", "medium", "low"):
            raise W7ClassificationError("reviewed annotation needs confidence high/medium/low")
        for name in ("evidence_source", "evidence_reference", "reviewer"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise W7ClassificationError(f"reviewed annotation missing {name}")
        digest = row["evidence_content_hash"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in string.hexdigits for c in digest):
            raise W7ClassificationError("reviewed annotation requires evidence SHA256")


def apply_editorial_annotations(ledger: pd.DataFrame, annotations: pd.DataFrame) -> pd.DataFrame:
    """Apply a complete, separately versioned annotation table with provenance."""
    _unique(ledger, PROJECT_KEY, "W7 ledger")
    missing = [c for c in ANNOTATION_COLUMNS if c not in annotations]
    if missing:
        raise W7ClassificationError(f"annotation columns missing: {missing}")
    if annotations.empty:
        return ledger.copy()
    _unique(annotations, [*PROJECT_KEY, "annotation_version"], "W7 annotations")
    if not annotations[PROJECT_KEY].merge(ledger[PROJECT_KEY], on=PROJECT_KEY, how="left", indicator=True)["_merge"].eq("both").all():
        raise W7ClassificationError("orphan W7 annotation")
    if annotations[PROJECT_KEY].drop_duplicates().shape[0] != len(annotations):
        raise W7ClassificationError("multiple annotation versions for one project")
    if annotations.annotation_version.astype(str).str.strip().eq("").any():
        raise W7ClassificationError("annotation_version must not be empty")
    out = ledger.merge(annotations, on=PROJECT_KEY, how="left", suffixes=("", "_annotation"), indicator=True, validate="one_to_one")
    for col in ANNOTATION_COLUMNS:
        if col in PROJECT_KEY:
            continue
        out[col] = out[f"{col}_annotation"].where(out["_merge"].eq("both"), out[col]) if f"{col}_annotation" in out else out[col]
        if f"{col}_annotation" in out:
            out = out.drop(columns=f"{col}_annotation")
    out = out.drop(columns="_merge").sort_values(PROJECT_KEY, kind="stable").reset_index(drop=True)
    validate_editorial_state(out)
    return out


def derive_exposure_panel(ledger: pd.DataFrame, bridge: pd.DataFrame, panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Propagate project classes to cells while preserving all source geometry."""
    validate_editorial_state(ledger)
    _unique(bridge, CELL_KEY, "W6 project-area bridge")
    _unique(panel, PANEL_KEY, "W6 panel")
    if not bridge[PROJECT_KEY].drop_duplicates().sort_values(PROJECT_KEY).reset_index(drop=True).equals(
        ledger[PROJECT_KEY].sort_values(PROJECT_KEY).reset_index(drop=True)
    ):
        raise W7ClassificationError("ledger and project-area bridge project identities disagree")
    for c in ["geo_uid", "period_id", "area_country_iso3", "recipient_iso3", "recipient_area_aligned"]:
        if c not in bridge:
            raise W7ClassificationError(f"bridge missing {c}")
    join = bridge.merge(ledger[PROJECT_KEY + ["candidate_sector_channel", "class", "editorial_status"]], on=PROJECT_KEY, how="left", validate="many_to_one", indicator=True)
    if len(join) != len(bridge) or not join["_merge"].eq("both").all():
        raise W7ClassificationError("project bridge membership is not covered by ledger")
    join = join.drop(columns="_merge")
    # W6 geometry is inherited and must remain coherent with W5 canonical country.
    authority = join[PANEL_KEY + ["area_country_iso3", "recipient_iso3", "recipient_area_aligned"]].merge(
        panel[PANEL_KEY + ["country_iso3"]], on=PANEL_KEY, how="left", validate="many_to_one",
        indicator=True,
    )
    if (not authority["_merge"].eq("both").all() or
            not authority.area_country_iso3.eq(authority.country_iso3).all() or
            not authority.recipient_area_aligned.eq(
                authority.recipient_iso3.eq(authority.area_country_iso3)
            ).all()):
        raise W7ClassificationError("W6 project geography/recipient flag violates canonical panel")
    join["_candidate_channels"] = join.candidate_sector_channel.str.split("|")
    rows = []
    for _, r in join.iterrows():
        for channel in r["_candidate_channels"]:
            rows.append({"geo_uid": r.geo_uid, "period_id": r.period_id, "source_family": r.source_family, "channel": channel, "class": r["class"]})
    counts = pd.DataFrame(rows)
    out = panel.copy()
    def add_counts(frame: pd.DataFrame, grouped: pd.Series, name: str) -> pd.DataFrame:
        if grouped.empty:
            q = pd.DataFrame(columns=PANEL_KEY + [name])
        else:
            q = grouped.rename(name).reset_index()
        result = frame.merge(q, on=PANEL_KEY, how="left", validate="one_to_one")
        result[name] = result[name].astype("Int64").fillna(0).astype("int64")
        return result

    for donor, prefix in [("china", "cn"), ("world_bank", "wb")]:
        for category in CATEGORIES:
            for cls, suffix in [("reviewed_jobs", "reviewed_jobs"), ("reviewed_nonjobs", "reviewed_nonjobs"), ("unresolved", "unresolved")]:
                name = f"{prefix}_{suffix}_{category}_count"
                if counts.empty:
                    out[name] = 0
                else:
                    q = counts[(counts.source_family == donor) & (counts.channel == category) & (counts["class"] == cls)].groupby(PANEL_KEY).size().rename(name)
                    out = add_counts(out, q, name)
        category_cols = [f"{prefix}_{s}_{c}_count" for s in ["reviewed_jobs", "reviewed_nonjobs", "unresolved"] for c in CATEGORIES]
        # Multi-sector rows are counted in multiple candidate channels; parity is
        # therefore checked against project counts using the unresolved/class bins.
        # A project class partition, independent of candidate multi-hot channels.
        part = join[join.source_family == donor].groupby(PANEL_KEY + ["class"]).source_project_id.nunique().unstack(fill_value=0)
        for cls, suffix in [("reviewed_jobs", "reviewed_jobs"), ("reviewed_nonjobs", "reviewed_nonjobs"), ("unresolved", "unresolved")]:
            q = part[cls] if cls in part else pd.Series(dtype="int64")
            out = add_counts(out, q, f"{prefix}_{suffix}_project_count")
        baseline = out[f"{prefix}_project_count"].astype("int64")
        if not (out[[f"{prefix}_{s}_project_count" for s in ["reviewed_jobs", "reviewed_nonjobs", "unresolved"]]].sum(axis=1).eq(baseline)).all():
            raise W7ClassificationError(f"{donor} class partition parity failed")
    if len(out) != len(panel) or not out[PANEL_KEY].equals(panel[PANEL_KEY]):
        raise W7ClassificationError("W7 panel shape/order drift")
    return join, out
