from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import json
import re

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SourceContract:
    name: str
    path: str
    kind: str
    grain: List[str]
    prefix: Optional[str] = None
    amount_col: Optional[str] = None
    jobcat_col: Optional[str] = None
    optional: bool = False

    @classmethod
    def from_dict(cls, name: str, payload: dict) -> "SourceContract":
        return cls(
            name=name,
            path=payload["path"],
            kind=payload["kind"],
            grain=list(payload["grain"]),
            prefix=payload.get("prefix", name),
            amount_col=payload.get("amount_col"),
            jobcat_col=payload.get("jobcat_col"),
            optional=bool(payload.get("optional", False)),
        )


@dataclass
class CanonicalPanelSpec:
    panel_id: str
    geo_scheme: str
    geo_level: int
    period_years: int
    alignment_year: int
    sources: Dict[str, SourceContract]
    annotation_version: str = "legacy_2023"
    unit_col: str = "GID"
    period_col: str = "TimePeriod"

    @classmethod
    def from_json(cls, path) -> "CanonicalPanelSpec":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        geo = raw["geography"]
        time = raw["time"]
        return cls(
            panel_id=raw["panel_id"],
            geo_scheme=geo["scheme"],
            geo_level=int(geo["level"]),
            period_years=int(time["period_years"]),
            alignment_year=int(time["alignment_year"]),
            annotation_version=raw.get("annotation_version", "legacy_2023"),
            unit_col=raw.get("unit_col", "GID"),
            period_col=raw.get("period_col", "TimePeriod"),
            sources={
                name: SourceContract.from_dict(name, payload)
                for name, payload in raw["sources"].items()
            },
        )


def _period_start(value) -> float:
    match = re.search(r"(\d{4})", str(value))
    return float(match.group(1)) if match else np.nan


def _sorted_periods(values) -> List[str]:
    vals = pd.Series(values).dropna().astype(str).unique().tolist()
    return sorted(vals, key=lambda v: (_period_start(v), v))


def _snake(value: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _cat_token(value) -> str:
    try:
        x = float(value)
        if x.is_integer():
            return str(int(x))
    except (TypeError, ValueError):
        pass
    return _snake(str(value))


def _resolve_path(contract: SourceContract, base_dir: Path) -> Path:
    p = Path(contract.path)
    return p if p.is_absolute() else base_dir / p


def load_sources(spec: CanonicalPanelSpec, base_dir="."):
    base = Path(base_dir)
    loaded = {}
    missing = []
    for name, contract in spec.sources.items():
        path = _resolve_path(contract, base)
        if not path.exists():
            if contract.optional:
                loaded[name] = None
                continue
            missing.append(f"{name}: {path}")
            continue
        loaded[name] = pd.read_csv(path)
    if missing:
        raise FileNotFoundError(
            "Required canonical sources not found:\n" + "\n".join(missing)
        )
    return loaded


def _source_metrics(df: pd.DataFrame, contract: SourceContract, spec: CanonicalPanelSpec):
    missing_grain = [c for c in contract.grain if c not in df.columns]
    duplicate_grain_rows = -1 if missing_grain else int(df.duplicated(contract.grain).sum())
    key_missing_rows = (
        -1 if missing_grain
        else int(df[contract.grain].isna().any(axis=1).sum())
    )

    inventory = {
        "source": contract.name,
        "path": contract.path,
        "kind": contract.kind,
        "grain": " × ".join(contract.grain),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "unique_gid": int(df[spec.unit_col].nunique(dropna=True)) if spec.unit_col in df else np.nan,
        "unique_period": int(df[spec.period_col].nunique(dropna=True)) if spec.period_col in df else np.nan,
        "first_period": None,
        "last_period": None,
        "duplicate_grain_rows": duplicate_grain_rows,
        "key_missing_rows": key_missing_rows,
    }

    if spec.period_col in df.columns and len(df):
        periods = _sorted_periods(df[spec.period_col])
        inventory["first_period"] = periods[0] if periods else None
        inventory["last_period"] = periods[-1] if periods else None

    key_status = "GREEN"
    if missing_grain or duplicate_grain_rows != 0 or key_missing_rows != 0:
        key_status = "RED"

    key_row = {
        "source": contract.name,
        "expected_grain": " × ".join(contract.grain),
        "missing_grain_fields": ",".join(missing_grain),
        "duplicate_grain_rows": duplicate_grain_rows,
        "key_missing_rows": key_missing_rows,
        "status": key_status,
    }

    period_rows = []
    if spec.period_col in df.columns:
        for period, g in df.groupby(spec.period_col, dropna=False):
            row = {
                "source": contract.name,
                "TimePeriod": period,
                "rows": int(len(g)),
                "unique_gid": int(g[spec.unit_col].nunique(dropna=True)) if spec.unit_col in g else np.nan,
            }
            if spec.unit_col in g:
                row["unique_gid_period"] = int(
                    g[[spec.unit_col, spec.period_col]].drop_duplicates().shape[0]
                )
            period_rows.append(row)

    column_rows = []
    for col in df.columns:
        s = df[col]
        column_rows.append({
            "source": contract.name,
            "column": col,
            "dtype": str(s.dtype),
            "rows": int(len(s)),
            "nonmissing": int(s.notna().sum()),
            "missing_share": float(s.isna().mean()) if len(s) else np.nan,
            "unique": int(s.nunique(dropna=True)),
        })

    project_row = None
    if contract.kind == "project" and not missing_grain:
        gp = df.groupby([spec.unit_col, spec.period_col], dropna=False)
        amount = (
            pd.to_numeric(df[contract.amount_col], errors="coerce")
            if contract.amount_col and contract.amount_col in df.columns
            else pd.Series(np.nan, index=df.index)
        )
        jobcats = (
            sorted(df[contract.jobcat_col].dropna().unique().tolist())
            if contract.jobcat_col and contract.jobcat_col in df.columns
            else []
        )
        zero_only = np.nan
        if contract.amount_col and contract.amount_col in df.columns:
            tmp = df[[spec.unit_col, spec.period_col]].copy()
            tmp["_amount"] = amount
            zero_only = int(
                tmp.groupby([spec.unit_col, spec.period_col])["_amount"]
                   .max()
                   .eq(0)
                   .sum()
            )
        project_row = {
            "source": contract.name,
            "rows": int(len(df)),
            "unique_gid_period": int(gp.ngroups),
            "multi_jobcat_gid_periods": int((gp.size() > 1).sum()),
            "jobcat_values": ",".join(_cat_token(x) for x in jobcats),
            "amount_missing_rows": int(amount.isna().sum()),
            "zero_amount_rows": int((amount == 0).sum()),
            "positive_amount_rows": int((amount > 0).sum()),
            "zero_only_gid_periods": zero_only,
        }

    return inventory, key_row, period_rows, column_rows, project_row


def _lattice_name(spec: CanonicalPanelSpec) -> str:
    names = [name for name, c in spec.sources.items() if c.kind == "lattice"]
    if len(names) != 1:
        raise ValueError(f"Expected exactly one lattice source; found {names}")
    return names[0]


def audit_sources(spec: CanonicalPanelSpec, loaded: dict):
    inventories, keys, periods, columns, projects = [], [], [], [], []
    lattice_name = _lattice_name(spec)
    lattice = loaded.get(lattice_name)
    lattice_gids = (
        set(lattice[spec.unit_col].dropna().astype(str))
        if lattice is not None else set()
    )

    gid_rows = []
    for name, contract in spec.sources.items():
        df = loaded.get(name)
        if df is None:
            inventories.append({
                "source": name,
                "path": contract.path,
                "kind": contract.kind,
                "grain": " × ".join(contract.grain),
                "rows": 0,
                "columns": 0,
                "unique_gid": 0,
                "unique_period": 0,
                "first_period": None,
                "last_period": None,
                "duplicate_grain_rows": np.nan,
                "key_missing_rows": np.nan,
            })
            keys.append({
                "source": name,
                "expected_grain": " × ".join(contract.grain),
                "missing_grain_fields": "source_missing",
                "duplicate_grain_rows": np.nan,
                "key_missing_rows": np.nan,
                "status": "YELLOW" if contract.optional else "RED",
            })
            continue

        inv, key, period_rows, column_rows, project_row = _source_metrics(df, contract, spec)
        inventories.append(inv)
        keys.append(key)
        periods.extend(period_rows)
        columns.extend(column_rows)
        if project_row:
            projects.append(project_row)

        gids = set(df[spec.unit_col].dropna().astype(str)) if spec.unit_col in df else set()
        gid_rows.append({
            "source": name,
            "unique_gid": len(gids),
            "gids_in_lattice": len(gids & lattice_gids) if lattice_gids else np.nan,
            "gids_outside_lattice": len(gids - lattice_gids) if lattice_gids else np.nan,
            "share_of_lattice_gids": (
                len(gids & lattice_gids) / len(lattice_gids)
                if lattice_gids else np.nan
            ),
        })

    return {
        "source_inventory": pd.DataFrame(inventories),
        "key_integrity": pd.DataFrame(keys),
        "period_coverage": pd.DataFrame(periods),
        "gid_coverage": pd.DataFrame(gid_rows),
        "column_inventory": pd.DataFrame(columns),
        "project_exposure_profile": pd.DataFrame(projects),
    }


def _assert_buildable(df: pd.DataFrame, contract: SourceContract):
    missing = [c for c in contract.grain if c not in df.columns]
    if missing:
        raise KeyError(f"{contract.name} missing grain columns: {missing}")
    dup = int(df.duplicated(contract.grain).sum())
    if dup:
        raise ValueError(
            f"{contract.name} has {dup} duplicate rows at declared grain "
            f"{contract.grain}; canonicalization refuses to guess how to collapse them."
        )
    key_missing = int(df[contract.grain].isna().any(axis=1).sum())
    if key_missing:
        raise ValueError(
            f"{contract.name} has {key_missing} rows with missing grain keys."
        )


def normalize_project_source(
    df: pd.DataFrame,
    contract: SourceContract,
    spec: CanonicalPanelSpec,
) -> pd.DataFrame:
    _assert_buildable(df, contract)
    if not contract.amount_col or contract.amount_col not in df.columns:
        raise KeyError(f"{contract.name} requires amount_col={contract.amount_col!r}")
    if not contract.jobcat_col or contract.jobcat_col not in df.columns:
        raise KeyError(f"{contract.name} requires jobcat_col={contract.jobcat_col!r}")

    prefix = contract.prefix or contract.name
    key = [spec.unit_col, spec.period_col]
    x = df.copy()
    x["_amount"] = pd.to_numeric(x[contract.amount_col], errors="coerce")

    grouped = x.groupby(key, dropna=False)
    base = grouped["_amount"].agg(
        **{
            f"{prefix}_amount_usd": lambda s: s.sum(min_count=1),
            f"{prefix}_amount_max": "max",
        }
    ).reset_index()
    base[f"{prefix}_record_present"] = True

    observed = grouped["_amount"].apply(
        lambda s: bool(s.notna().any())
    ).rename(f"{prefix}_amount_observed")
    positive = grouped["_amount"].apply(
        lambda s: bool((s > 0).any())
    ).rename(f"{prefix}_amount_positive")
    base = base.merge(observed.reset_index(), on=key, validate="one_to_one")
    base = base.merge(positive.reset_index(), on=key, validate="one_to_one")
    base[f"{prefix}_amount_zero_only"] = (
        base[f"{prefix}_amount_observed"]
        & ~base[f"{prefix}_amount_positive"]
        & base[f"{prefix}_amount_max"].eq(0)
    )
    base = base.drop(columns=[f"{prefix}_amount_max"])

    categories = sorted(x[contract.jobcat_col].dropna().unique().tolist())
    for category in categories:
        token = _cat_token(category)
        sub = x.loc[
            x[contract.jobcat_col] == category,
            key + ["_amount"],
        ].copy()
        if sub.duplicated(key).any():
            raise ValueError(
                f"{contract.name} has multiple rows for jobcat={category!r} "
                "at GID×TimePeriod."
            )
        sub[f"{prefix}_jobcat_{token}_present"] = True
        sub = sub.rename(
            columns={"_amount": f"{prefix}_jobcat_{token}_amount_usd"}
        )
        base = base.merge(sub, on=key, how="left", validate="one_to_one")

    return base


def normalize_simple_source(
    df: pd.DataFrame,
    contract: SourceContract,
    spec: CanonicalPanelSpec,
) -> pd.DataFrame:
    _assert_buildable(df, contract)
    key = [spec.unit_col, spec.period_col]
    if contract.grain != key:
        raise ValueError(
            f"Simple source {contract.name} must declare GID×TimePeriod grain; "
            f"got {contract.grain}"
        )
    prefix = contract.prefix or contract.name
    rename = {
        c: f"{prefix}_{_snake(c)}"
        for c in df.columns
        if c not in key
    }
    out = df.rename(columns=rename).copy()
    out[f"{prefix}_record_present"] = True
    return out


def build_canonical_panel(spec: CanonicalPanelSpec, loaded: dict):
    lattice_name = _lattice_name(spec)
    lattice_contract = spec.sources[lattice_name]
    lattice = loaded[lattice_name].copy()
    _assert_buildable(lattice, lattice_contract)

    key = [spec.unit_col, spec.period_col]
    panel = lattice.copy()
    panel.insert(0, "panel_id", spec.panel_id)
    panel["geo_scheme"] = spec.geo_scheme
    panel["geo_level"] = spec.geo_level
    panel["period_years"] = spec.period_years
    panel["alignment_year"] = spec.alignment_year
    panel["annotation_version"] = spec.annotation_version

    lattice_keys = panel[key].drop_duplicates()
    audits = {}

    for name, contract in spec.sources.items():
        if name == lattice_name:
            continue
        df = loaded.get(name)
        if df is None:
            continue

        if contract.kind == "project":
            normalized = normalize_project_source(df, contract, spec)
        else:
            normalized = normalize_simple_source(df, contract, spec)

        source_keys = normalized[key].drop_duplicates()
        source_vs_lattice = source_keys.merge(
            lattice_keys, on=key, how="left", indicator=True
        )
        source_only = int((source_vs_lattice["_merge"] == "left_only").sum())

        before = len(panel)
        panel = panel.merge(normalized, on=key, how="left", validate="one_to_one")
        if len(panel) != before:
            raise AssertionError(
                f"Canonical lattice changed row count after merging {name}."
            )

        present_col = f"{contract.prefix or name}_record_present"
        matched = (
            int(panel[present_col].astype("boolean").fillna(False).sum())
            if present_col in panel else 0
        )
        audits[name] = {
            "source_rows": int(len(df)),
            "normalized_rows": int(len(normalized)),
            "matched_lattice_rows": matched,
            "source_only_keys": source_only,
            "lattice_rows": int(len(panel)),
            "matched_share_of_lattice": matched / len(panel) if len(panel) else 0.0,
        }

        bool_prefix = f"{contract.prefix or name}_"
        for col in [c for c in panel.columns if c.startswith(bool_prefix)]:
            if (
                col.endswith("_present")
                or col.endswith("_positive")
                or col.endswith("_observed")
                or col.endswith("_zero_only")
            ):
                panel[col] = (
                    panel[col].astype("boolean").fillna(False).astype(bool)
                )

    if panel.duplicated(key).any():
        raise AssertionError(
            "Canonical panel is not unique at GID×TimePeriod after merges."
        )

    return panel, audits


def build_wb_source_comparison(
    panel: pd.DataFrame,
    spec: CanonicalPanelSpec,
    left_source="wbad",
    right_source="wbkg",
):
    left = spec.sources.get(left_source)
    right = spec.sources.get(right_source)
    if not left or not right:
        return pd.DataFrame()
    lcol = f"{left.prefix or left_source}_record_present"
    rcol = f"{right.prefix or right_source}_record_present"
    if lcol not in panel or rcol not in panel:
        return pd.DataFrame()

    rows = []
    grouped = [("__ALL__", panel)] + list(panel.groupby(spec.period_col))
    for label, g in grouped:
        left_present = g[lcol].astype(bool)
        right_present = g[rcol].astype(bool)
        both = int((left_present & right_present).sum())
        left_only = int((left_present & ~right_present).sum())
        right_only = int((~left_present & right_present).sum())
        union = both + left_only + right_only
        rows.append({
            "TimePeriod": label,
            "wbad_only": left_only,
            "wbkg_only": right_only,
            "both": both,
            "neither": int((~left_present & ~right_present).sum()),
            "union": union,
            "jaccard": both / union if union else np.nan,
        })
    return pd.DataFrame(rows)


def build_lattice_covariate_profile(
    lattice: pd.DataFrame,
    spec: CanonicalPanelSpec,
):
    rows = []
    for col in lattice.columns:
        if col in (spec.unit_col, spec.period_col):
            continue
        s = lattice[col]
        if not pd.api.types.is_numeric_dtype(s):
            continue
        within_vary = (
            lattice[[spec.unit_col, col]]
            .groupby(spec.unit_col)[col]
            .nunique(dropna=True)
            .gt(1)
            .mean()
        )
        numeric = pd.to_numeric(s, errors="coerce")
        rows.append({
            "column": col,
            "missing_share": float(s.isna().mean()),
            "n_unique": int(s.nunique(dropna=True)),
            "mean": float(numeric.mean()),
            "zero_share": float((numeric == 0).mean()),
            "share_gids_with_within_variation": float(within_vary),
        })
    return pd.DataFrame(rows)


def run_canonical_gates(
    spec: CanonicalPanelSpec,
    loaded: dict,
    panel: pd.DataFrame,
    covariate_profile: pd.DataFrame,
    wb_comparison: pd.DataFrame,
):
    results = []

    def add(gate, status, metric, value, threshold, note):
        results.append({
            "gate": gate,
            "status": status,
            "metric": metric,
            "value": value,
            "threshold": threshold,
            "note": note,
        })

    lattice_name = _lattice_name(spec)
    lattice = loaded[lattice_name]
    key = [spec.unit_col, spec.period_col]
    n_gid = int(lattice[spec.unit_col].nunique())
    n_period = int(lattice[spec.period_col].nunique())
    expected = n_gid * n_period
    dup = int(lattice.duplicated(key).sum())
    key_missing = int(lattice[key].isna().any(axis=1).sum())
    dense = len(lattice) == expected
    add(
        "C0_LATTICE_INTEGRITY",
        "GREEN" if dup == 0 and key_missing == 0 and dense else "RED",
        "rows / expected dense rows",
        f"{len(lattice)} / {expected}",
        "unique keys and rows = GIDs × periods",
        f"{n_gid} GIDs × {n_period} periods; duplicate rows={dup}; "
        f"key-missing rows={key_missing}.",
    )

    bad = []
    for name, contract in spec.sources.items():
        df = loaded.get(name)
        if df is None:
            if not contract.optional:
                bad.append(f"{name}:missing")
            continue
        missing = [c for c in contract.grain if c not in df.columns]
        dup_n = -1 if missing else int(df.duplicated(contract.grain).sum())
        miss_n = (
            -1 if missing else int(df[contract.grain].isna().any(axis=1).sum())
        )
        if missing or dup_n or miss_n:
            bad.append(
                f"{name}:missing={missing},dup={dup_n},keyna={miss_n}"
            )
    add(
        "C1_SOURCE_KEY_INTEGRITY",
        "GREEN" if not bad else "RED",
        "sources violating declared grain",
        len(bad),
        "0",
        "No source may be silently collapsed at an undeclared grain. "
        + ("; ".join(bad) if bad else "All source grains are structurally valid."),
    )

    nonempty = [
        name for name, contract in spec.sources.items()
        if loaded.get(name) is not None and len(loaded[name]) > 0
    ]
    required = [name for name, c in spec.sources.items() if not c.optional]
    missing_required = sorted(set(required) - set(nonempty))
    add(
        "C2_SOURCE_COVERAGE_REPORTED",
        "GREEN" if not missing_required else "RED",
        "nonempty required sources",
        f"{len(nonempty)} / {len(required)}",
        "all required sources available",
        "Coverage windows are descriptive, not assumed to span the full lattice. "
        + (
            f"Missing/empty: {missing_required}"
            if missing_required else "All required source surfaces loaded."
        ),
    )

    project_contracts = [
        c for c in spec.sources.values() if c.kind == "project"
    ]
    zero_only_total = 0
    for contract in project_contracts:
        df = loaded.get(contract.name)
        if df is None or not contract.amount_col:
            continue
        tmp = df[[spec.unit_col, spec.period_col, contract.amount_col]].copy()
        tmp["_amount"] = pd.to_numeric(
            tmp[contract.amount_col], errors="coerce"
        )
        zero_only_total += int(
            tmp.groupby([spec.unit_col, spec.period_col])["_amount"]
               .max()
               .eq(0)
               .sum()
        )
    add(
        "C3_LEGACY_EXPOSURE_STRUCTURE",
        "YELLOW" if zero_only_total else "GREEN",
        "project GID-periods with records but zero-only amount",
        zero_only_total,
        "diagnostic; zero amount semantics intentionally unresolved",
        "Legacy jobcat values are preserved unchanged. Record presence and "
        "positive amount are stored separately; this wave does not repair amount semantics.",
    )

    acled = spec.sources.get("acled")
    acled_status, acled_value = "RED", None
    acled_note = "ACLED source not configured."
    if acled and loaded.get("acled") is not None:
        acol = f"{acled.prefix or 'acled'}_record_present"
        adf = loaded["acled"]
        periods = _sorted_periods(adf[spec.period_col])
        if periods:
            lo, hi = _period_start(periods[0]), _period_start(periods[-1])
            pstart = panel[spec.period_col].map(_period_start)
            in_window = panel[pstart.between(lo, hi, inclusive="both")]
            matched = int(in_window[acol].sum()) if acol in in_window else 0
            share = matched / len(in_window) if len(in_window) else np.nan
            acled_value = None if np.isnan(share) else round(share, 4)
            acled_status = "GREEN" if share >= 0.98 else "YELLOW"
            acled_note = (
                f"ACLED records cover {matched}/{len(in_window)} lattice rows inside "
                f"the observed {periods[0]}–{periods[-1]} window. Absent rows remain "
                "absent; this checkpoint does not assert that they are structural zeroes."
            )
    add(
        "C4_ACLED_MEASUREMENT_SEMANTICS",
        acled_status,
        "record-present share within ACLED observed window",
        acled_value,
        "green >= 0.98; otherwise inspect zero-vs-absence semantics",
        acled_note,
    )

    if wb_comparison.empty:
        add(
            "C5_WB_SOURCE_COMPARISON",
            "RED",
            "WBad/WBkg overlap",
            None,
            "both source implementations available",
            "Cannot compare the two inherited World Bank source implementations.",
        )
    else:
        overall = wb_comparison.loc[
            wb_comparison["TimePeriod"] == "__ALL__"
        ].iloc[0]
        jaccard = (
            float(overall["jaccard"])
            if pd.notna(overall["jaccard"]) else np.nan
        )
        status = (
            "RED" if np.isnan(jaccard) or overall["union"] == 0
            else ("GREEN" if jaccard >= 0.90 else "YELLOW")
        )
        add(
            "C5_WB_SOURCE_COMPARISON",
            status,
            "GID-period exposure-record Jaccard",
            None if np.isnan(jaccard) else round(jaccard, 4),
            "green >= 0.90 for near-equivalence; lower values require source choice/reconciliation",
            f"both={int(overall['both'])}, WBad-only={int(overall['wbad_only'])}, "
            f"WBkg-only={int(overall['wbkg_only'])}. The two sources remain separate; "
            "they are not summed.",
        )

    max_missing = (
        float(covariate_profile["missing_share"].max())
        if len(covariate_profile) else np.nan
    )
    cov_status = (
        "RED" if np.isnan(max_missing)
        else (
            "GREEN" if max_missing <= 0.10
            else ("YELLOW" if max_missing <= 0.30 else "RED")
        )
    )
    add(
        "C6_COVARIATE_PROFILE",
        cov_status,
        "maximum inherited lattice-covariate missing share",
        None if np.isnan(max_missing) else round(max_missing, 4),
        "green <= 0.10; yellow <= 0.30",
        "This checks availability only. Static-looking or weakly varying covariates "
        "are reported separately and are not automatically approved as regression controls.",
    )

    return pd.DataFrame(results)


def _markdown_table(headers, rows):
    def fmt(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""
        return str(value).replace("|", "\\|")

    output = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        output.append(
            "| " + " | ".join(fmt(row.get(h)) for h in headers) + " |"
        )
    return "\n".join(output)


def render_panel_card(
    spec: CanonicalPanelSpec,
    loaded: dict,
    audit_tables: dict,
    merge_audit: dict,
    gates: pd.DataFrame,
    wb_comparison: pd.DataFrame,
):
    lattice_name = _lattice_name(spec)
    lattice = loaded[lattice_name]
    periods = _sorted_periods(lattice[spec.period_col])
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}

    source_rows = []
    for _, row in audit_tables["source_inventory"].iterrows():
        source_rows.append({
            "Source": row["source"],
            "Role": row["kind"],
            "Rows": row["rows"],
            "GIDs": row["unique_gid"],
            "Periods": row["unique_period"],
            "First": row["first_period"],
            "Last": row["last_period"],
            "Authority": "legacy inherited",
        })

    gate_rows = []
    for _, row in gates.iterrows():
        gate_rows.append({
            "Gate": row["gate"],
            "Status": f"{icon.get(row['status'], '')} {row['status']}",
            "Metric": row["metric"],
            "Value": row["value"],
        })

    merge_rows = []
    for source, row in merge_audit.items():
        merge_rows.append({
            "Source": source,
            "Normalized rows": row["normalized_rows"],
            "Matched lattice rows": row["matched_lattice_rows"],
            "Source-only keys": row["source_only_keys"],
            "Lattice match share": round(row["matched_share_of_lattice"], 4),
        })

    lines = [
        f"# Canonical Panel Card — {spec.panel_id}",
        "",
        "> **Canonicalized does not mean causally validated.** This card characterizes the empirical substrate available to candidate experiments.",
        "",
        "## Identity",
        "",
        f"- Geography: `{spec.geo_scheme}` level `{spec.geo_level}`",
        f"- Temporal window: `{spec.period_years}` years",
        f"- Alignment year: `{spec.alignment_year}`",
        f"- Canonical grain: `{spec.unit_col} × {spec.period_col}`",
        f"- Lattice rows: `{len(lattice):,}`",
        f"- Geographic units: `{lattice[spec.unit_col].nunique():,}`",
        f"- Periods: `{lattice[spec.period_col].nunique():,}` "
        f"({periods[0] if periods else '?'} to {periods[-1] if periods else '?'})",
        f"- Annotation version: `{spec.annotation_version}`",
        "",
        "## Authority boundary",
        "",
        "This checkpoint **inherits and characterizes** the 2023 processed source surfaces. "
        "It does not rebuild raw-source geocoding, time aggregation, project allocation, or job annotations.",
        "",
        "- Legacy `jobcat` values are preserved unchanged.",
        "- Project-record presence and positive reported amount are separate derived facts.",
        "- Zero-amount project records are documented but not repaired.",
        "- WBad and WBkg remain separate World Bank source implementations.",
        "- ACLED absent rows are not automatically converted to zero.",
        "- No treatment, sample, t→t+1 outcome shift, matching, or regression is selected here.",
        "",
        "## Source surfaces",
        "",
        _markdown_table(
            ["Source", "Role", "Rows", "GIDs", "Periods", "First", "Last", "Authority"],
            source_rows,
        ),
        "",
        "## Attachment audit",
        "",
        _markdown_table(
            ["Source", "Normalized rows", "Matched lattice rows", "Source-only keys", "Lattice match share"],
            merge_rows,
        ),
        "",
        "## Canonicalization operations",
        "",
        f"1. Use `{lattice_name}` as the authoritative dense area-period lattice.",
        "2. Validate every source at its declared grain before any collapse.",
        "3. Collapse project sources only from `GID × TimePeriod × jobcat` to `GID × TimePeriod`, preserving jobcat-specific presence and amount columns.",
        "4. Left-join outcome/survey surfaces without filling absent values.",
        "5. Add explicit source-record-presence indicators and design provenance.",
        "",
        "## Measurement / canonical-data gates",
        "",
        _markdown_table(["Gate", "Status", "Metric", "Value"], gate_rows),
        "",
        "## Known deferred decisions",
        "",
        "- Whether project-record presence or positive `Amount_USD` is the preferred exposure definition.",
        "- Whether and how the legacy 2023 job labels should be revised.",
        "- Which World Bank source implementation should be preferred or reconciled.",
        "- Whether absent ACLED area-period records inside source coverage are structural zeroes.",
        "- Which inherited covariates are scientifically appropriate pre-treatment controls.",
        "- Whether aggregated Afrobarometer surfaces are sufficient or respondent-level reconstruction is required.",
        "",
        "## Next scientific step",
        "",
        "After human inspection of this card and its audit tables, define experiments **from this canonical object**. "
        "The first calibration experiment should not modify the source data merely to improve a coefficient.",
        "",
    ]
    return "\n".join(lines)


def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


def run_canonical_checkpoint(spec: CanonicalPanelSpec, base_dir="."):
    loaded = load_sources(spec, base_dir=base_dir)
    audits = audit_sources(spec, loaded)
    panel, merge_audit = build_canonical_panel(spec, loaded)
    wb_comparison = build_wb_source_comparison(panel, spec)
    lattice = loaded[_lattice_name(spec)]
    covariate_profile = build_lattice_covariate_profile(lattice, spec)
    gates = run_canonical_gates(
        spec, loaded, panel, covariate_profile, wb_comparison
    )
    card = render_panel_card(
        spec, loaded, audits, merge_audit, gates, wb_comparison
    )
    return {
        "loaded": loaded,
        "audits": audits,
        "panel": panel,
        "merge_audit": merge_audit,
        "wb_comparison": wb_comparison,
        "covariate_profile": covariate_profile,
        "gates": gates,
        "card": card,
    }


def write_checkpoint_outputs(result: dict, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name, table in result["audits"].items():
        table.to_csv(out / f"{name}.csv", index=False)

    result["wb_comparison"].to_csv(
        out / "wb_source_comparison.csv", index=False
    )
    result["covariate_profile"].to_csv(
        out / "covariate_profile.csv", index=False
    )
    result["gates"].to_csv(out / "canonical_gates.csv", index=False)

    panel = result["panel"]
    panel.to_csv(
        out / "canonical_panel.csv.gz", index=False, compression="gzip"
    )
    panel.head(250).to_csv(out / "canonical_panel_sample.csv", index=False)

    (out / "merge_audit.json").write_text(
        json.dumps(_json_safe(result["merge_audit"]), indent=2),
        encoding="utf-8",
    )
    source_summary = {
        "source_inventory": result["audits"]["source_inventory"].to_dict("records"),
        "key_integrity": result["audits"]["key_integrity"].to_dict("records"),
    }
    (out / "source_audit.json").write_text(
        json.dumps(_json_safe(source_summary), indent=2),
        encoding="utf-8",
    )
    (out / "canonical_panel_card.md").write_text(
        result["card"], encoding="utf-8"
    )
    return out
