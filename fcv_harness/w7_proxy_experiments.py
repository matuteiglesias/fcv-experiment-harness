"""Frozen, outcome-blind W7 native-sector proxy experiment.

The proxy is deliberately independent of W7 editorial classes: native channel
tags define candidate/other/ambiguous, and titles are diagnostic only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .w5_china_wb_vac import residualize_balanced

PROJECT_KEY = ["source_family", "source_release_id", "source_project_id"]
CELL_KEY = [*PROJECT_KEY, "geo_uid", "period_id"]
PANEL_KEY = ["geo_uid", "period_id"]
DONORS = {"china": "cn", "world_bank": "wb"}
CATEGORIES = [
    "productive_enterprise", "physical_infrastructure", "skills_education",
    "health_social", "governance_finance", "humanitarian_environment_other",
]
ARMS = [
    "cn_positive_only", "cn_other_only", "cn_mixed_or_unknown",
    "wb_positive_only", "wb_other_only", "wb_mixed_or_unknown", "both_sources",
]
TITLE_TERMS = [
    "employment", "job creation", "jobs", "unemployed", "cash-for-work",
    "cash for work", "wage subsidy", "labor market", "labour market",
    "vocational training", "skills training", "income generation", "livelihoods",
]


class W7ProxyError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    if any(k not in df for k in keys) or df[keys].isna().any().any() or df.duplicated(keys).any():
        raise W7ProxyError(f"{label}: missing, null, or duplicate key {keys}")


def load_policy(policy: dict | str | Path) -> dict[str, Any]:
    if not isinstance(policy, dict):
        policy = json.loads(Path(policy).read_text(encoding="utf-8"))
    if policy.get("schema") != "fcv.w7.exploratory_jobs_proxy_v0":
        raise W7ProxyError("unexpected W7 proxy policy schema")
    for name in ("broad", "narrow"):
        p = policy.get("policies", {}).get(name, {})
        if set(p.get("positive", [])) | set(p.get("other", [])) != set(CATEGORIES):
            raise W7ProxyError(f"{name} policy does not partition frozen categories")
        if set(p["positive"]) & set(p["other"]):
            raise W7ProxyError(f"{name} policy overlaps positive and other")
    if policy["regression"]["arms"] != ARMS:
        raise W7ProxyError("arm order drift")
    if policy.get("title_signal", {}).get("terms") != TITLE_TERMS:
        raise W7ProxyError("title diagnostic term list drift")
    return policy


def _tags(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise W7ProxyError("missing candidate channel tags")
    tags = list(dict.fromkeys(x.strip() for x in value.split("|") if x.strip()))
    if not tags or any(x not in CATEGORIES for x in tags):
        raise W7ProxyError("unknown candidate channel tag")
    return tags


def classify_projects(ledger: pd.DataFrame, policy: dict | str | Path, width: str = "broad") -> pd.DataFrame:
    """Return one role per source-qualified project; never promote reviewed classes."""
    policy = load_policy(policy)
    _unique(ledger, PROJECT_KEY, "ledger")
    required = set(PROJECT_KEY) | {"candidate_sector_channel", "project_title"}
    if not required.issubset(ledger.columns):
        raise W7ProxyError(f"ledger missing {sorted(required - set(ledger))}")
    rows = ledger.copy()
    roles = []
    title_hits = []
    if width not in ("broad", "narrow"):
        raise W7ProxyError("unknown frozen policy width")
    broad = policy["policies"][width]
    for row in rows.itertuples(index=False):
        tags = _tags(row.candidate_sector_channel)
        if set(tags) <= set(broad["positive"]):
            role = "candidate"
        elif set(tags) <= set(broad["other"]):
            role = "other"
        else:
            role = "ambiguous"
        roles.append(role)
        title = str(row.project_title).casefold()
        title_hits.append(any(term in title for term in policy["title_signal"]["terms"]))
    rows["proxy_project_role"] = roles
    rows["title_keyword_diagnostic"] = title_hits
    rows["title_keyword_diagnostic_count"] = int(sum(title_hits))
    # The editorial fields remain in the receipt/data, but are not inputs to role.
    return rows.sort_values(PROJECT_KEY, kind="stable").reset_index(drop=True)


def _check_release_parity(ledger: pd.DataFrame, bridge: pd.DataFrame) -> None:
    _unique(ledger, PROJECT_KEY, "ledger")
    _unique(bridge, CELL_KEY, "bridge")
    lk = ledger[PROJECT_KEY].sort_values(PROJECT_KEY).reset_index(drop=True)
    bk = bridge[PROJECT_KEY].drop_duplicates().sort_values(PROJECT_KEY).reset_index(drop=True)
    if not lk.equals(bk):
        raise W7ProxyError("ledger and bridge source-qualified project identities disagree")
    releases = ledger.groupby("source_family").source_release_id.nunique()
    if set(releases.index) != set(DONORS) or (releases != 1).any():
        raise W7ProxyError("ledger must have exactly one release per donor")
    for donor in DONORS:
        a = set(ledger.loc[ledger.source_family.eq(donor), "source_release_id"])
        b = set(bridge.loc[bridge.source_family.eq(donor), "source_release_id"])
        if a != b:
            raise W7ProxyError(f"{donor} bridge release parity failure")


def _cell_status(roles: pd.Series) -> str:
    vals = set(roles)
    if vals == {"candidate"}:
        return "positive_only"
    if vals == {"other"}:
        return "other_only"
    return "mixed_or_unknown"


def build_proxy_panel(ledger: pd.DataFrame, bridge: pd.DataFrame, panel: pd.DataFrame,
                      policy: dict | str | Path, width: str = "broad") -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    classified = classify_projects(ledger, policy, width)
    _check_release_parity(classified, bridge)
    _unique(panel, PANEL_KEY, "W7 panel")
    needed_bridge = set(CELL_KEY) | {"area_country_iso3", "recipient_iso3", "recipient_area_aligned"}
    if not needed_bridge.issubset(bridge.columns):
        raise W7ProxyError(f"bridge missing {sorted(needed_bridge - set(bridge))}")
    if "country_iso3" not in panel:
        raise W7ProxyError("panel missing country_iso3")
    b = bridge.merge(classified[PROJECT_KEY + ["proxy_project_role"]], on=PROJECT_KEY,
                     how="left", validate="many_to_one", indicator=True)
    if not b._merge.eq("both").all():
        raise W7ProxyError("bridge project is absent from ledger")
    b = b.drop(columns="_merge")
    geo = b[PANEL_KEY + ["area_country_iso3", "recipient_iso3", "recipient_area_aligned"]].merge(
        panel[PANEL_KEY + ["country_iso3"]], on=PANEL_KEY, how="left", validate="many_to_one", indicator=True)
    if (not geo._merge.eq("both").all() or not geo.area_country_iso3.eq(geo.country_iso3).all()
            or not geo.recipient_area_aligned.eq(geo.recipient_iso3.eq(geo.area_country_iso3)).all()):
        raise W7ProxyError("bridge geometry disagrees with canonical panel")

    counts = b.groupby(["source_family", *PANEL_KEY, "proxy_project_role"], observed=True).source_project_id.nunique()
    out = panel.copy()
    source_counts: dict[str, dict[str, int]] = {}
    for donor, prefix in DONORS.items():
        for role in ("candidate", "other", "ambiguous"):
            q = counts.loc[donor, :, :, role] if (donor, role) in counts.index.droplevel([1, 2]).unique() else pd.Series(dtype=int)
            col = f"{prefix}_{role}_project_count"
            q = q.rename(col).reset_index() if not q.empty else pd.DataFrame(columns=PANEL_KEY + [col])
            out = out.merge(q, on=PANEL_KEY, how="left", validate="one_to_one")
            out[col] = out[col].fillna(0).astype(int)
        donor_total = f"{prefix}_project_count"
        if donor_total not in out:
            raise W7ProxyError(f"panel missing {donor_total}")
        cols = [f"{prefix}_{r}_project_count" for r in ("candidate", "other", "ambiguous")]
        if not out[cols].sum(axis=1).eq(out[donor_total]).all():
            raise W7ProxyError(f"{donor} project-to-cell status count parity failed")
        source_counts[donor] = {r: int(out[f"{prefix}_{r}_project_count"].sum()) for r in ("candidate", "other", "ambiguous")}

    # Donor-exclusive statuses are computed from all projects in that donor/cell.
    cell_roles = b.groupby(["geo_uid", "period_id", "source_family"], observed=True).proxy_project_role.agg(_cell_status)
    for donor, prefix in DONORS.items():
        other_prefix = "wb" if prefix == "cn" else "cn"
        exclusive = out[f"{prefix}_project_count"].gt(0) & out[f"{other_prefix}_project_count"].eq(0)
        statuses = out[PANEL_KEY].apply(lambda r: cell_roles.get((r.geo_uid, r.period_id, donor), "mixed_or_unknown"), axis=1)
        out[f"{prefix}_exclusive_status"] = statuses.where(exclusive, "not_exclusive")
        for status, suffix in [("positive_only", "positive_only"), ("other_only", "other_only"), ("mixed_or_unknown", "mixed_or_unknown")]:
            out[f"{prefix}_{suffix}"] = (exclusive & statuses.eq(status)).astype(int)
    out["both_sources"] = (out.cn_project_count.gt(0) & out.wb_project_count.gt(0)).astype(int)
    out["neither_source_recorded"] = (out.cn_project_count.eq(0) & out.wb_project_count.eq(0)).astype(int)
    arm_cols = [f"cn_{x}" for x in ("positive_only", "other_only", "mixed_or_unknown")] + [f"wb_{x}" for x in ("positive_only", "other_only", "mixed_or_unknown")] + ["both_sources", "neither_source_recorded"]
    if not out[arm_cols].sum(axis=1).eq(1).all():
        raise W7ProxyError("arms do not partition panel")
    out["arm"] = out[arm_cols].idxmax(axis=1).replace({"cn_mixed_or_unknown": "cn_mixed_or_unknown", "wb_mixed_or_unknown": "wb_mixed_or_unknown"})
    out.loc[out.arm.eq("neither_source_recorded"), "arm"] = "neither_recorded"
    # idxmax already leaves the declared arm names intact; both is unchanged.
    out["crossrecipient_cn_project_count"] = b.loc[b.source_family.eq("china") & ~b.recipient_area_aligned].groupby(PANEL_KEY).source_project_id.nunique().reindex(pd.MultiIndex.from_frame(out[PANEL_KEY]), fill_value=0).to_numpy()
    out["crossrecipient_wb_project_count"] = b.loc[b.source_family.eq("world_bank") & ~b.recipient_area_aligned].groupby(PANEL_KEY).source_project_id.nunique().reindex(pd.MultiIndex.from_frame(out[PANEL_KEY]), fill_value=0).to_numpy()
    diagnostics = {
        "project_counts": {role: int(classified.proxy_project_role.eq(role).sum()) for role in ("candidate", "other", "ambiguous")},
        "donor_project_counts": {d: int(classified.source_family.eq(d).sum()) for d in DONORS},
        "donor_status_project_counts": source_counts,
        "cell_arm_counts": {arm: int((out.arm == arm).sum()) for arm in [*ARMS, "neither_recorded"]},
        "distinct_areas": int(out.geo_uid.nunique()), "distinct_countries": int(out.country_iso3.nunique()),
        "missing_geometry_crossrecipient_cells": {p: int(out[f"crossrecipient_{p}_project_count"].gt(0).sum()) for p in ("cn", "wb")},
        "title_keyword_diagnostic_count": int(classified.title_keyword_diagnostic.sum()),
    }
    return b, out, diagnostics


def _prepare_outcomes(proxy: pd.DataFrame, w5: pd.DataFrame) -> pd.DataFrame:
    _unique(w5, PANEL_KEY, "W5 frame")
    if not proxy[PANEL_KEY].equals(w5[PANEL_KEY]):
        if not proxy[PANEL_KEY].sort_values(PANEL_KEY).reset_index(drop=True).equals(w5[PANEL_KEY].sort_values(PANEL_KEY).reset_index(drop=True)):
            raise W7ProxyError("W7 panel and W5 frame key parity failure")
        w5 = w5.set_index(PANEL_KEY).loc[pd.MultiIndex.from_frame(proxy[PANEL_KEY])].reset_index()
    f = proxy.merge(w5, on=PANEL_KEY, how="left", suffixes=("", "_w5"), validate="one_to_one")
    if "country_iso3_w5" in f:
        if not f.country_iso3.eq(f.country_iso3_w5).all():
            raise W7ProxyError("country parity failure")
        f = f.drop(columns="country_iso3_w5")
    if "any_vac_next" not in f and "vac_events_next" in f: f["any_vac_next"] = (f.vac_events_next > 0).astype(int)
    if "any_vac_prior" not in f and "vac_events_prior" in f: f["any_vac_prior"] = (f.vac_events_prior > 0).astype(int)
    if "vac_events_next" not in f or "vac_events_prior" not in f:
        raise W7ProxyError("W5 frame missing declared outcome columns")
    f["asinh_vac_events_next"] = np.arcsinh(f.vac_events_next.astype(float))
    f["country_period"] = f.country_iso3.astype(str) + "|" + f.period_id.astype(str)
    if f.groupby("geo_uid").period_id.nunique().nunique() != 1:
        raise W7ProxyError("balanced ADM2-by-period panel required")
    return f


def _fit(frame: pd.DataFrame, outcome: str) -> dict[str, Any]:
    dummies = [f"arm_{i}" for i in range(7)]
    xraw = pd.DataFrame({c: frame.arm.eq(arm).astype(int) for c, arm in zip(dummies, ARMS)})
    work = frame.copy()
    for c in dummies: work[c] = xraw[c]
    transformed = residualize_balanced(work, [*dummies, outcome])
    x, y = transformed[:, :7], transformed[:, 7]
    rank = int(np.linalg.matrix_rank(x))
    if rank != 7: raise W7ProxyError(f"seven-arm design rank failure: {rank}")
    xtx = x.T @ x
    beta = np.linalg.solve(xtx, x.T @ y)
    error = y - x @ beta
    groups, codes = np.unique(frame.country_iso3.to_numpy(), return_inverse=True)
    G, n, k = len(groups), len(frame), 7
    nuisance = frame.geo_uid.nunique() + frame.country_period.nunique() - frame.country_iso3.nunique()
    residual_df = n - nuisance - k
    if G < 2 or residual_df <= 0: raise W7ProxyError("insufficient clustered degrees of freedom")
    scores = np.zeros((G, k))
    for j in range(k): scores[:, j] = np.bincount(codes, weights=x[:, j] * error, minlength=G)
    bread = np.linalg.inv(xtx)
    correction = (G / (G - 1)) * ((n - 1) / residual_df)
    cov = correction * bread @ (scores.T @ scores) @ bread
    cov = (cov + cov.T) / 2
    if not np.all(np.isfinite(cov)) or (np.diag(cov) < -1e-12).any(): raise W7ProxyError("invalid clustered covariance")
    result = []
    for donor, pos, other in (("cn", 0, 1), ("wb", 3, 4)):
        z = np.zeros(7); z[pos], z[other] = 1, -1
        est = float(z @ beta); se = float(np.sqrt(max(0, z @ cov @ z))); df = G - 1
        crit = float(stats.t.ppf(.975, df)); t = est / se if se else np.nan
        result.append({"contrast": f"{donor}_positive_only_minus_{donor}_other_only", "estimate": est, "se": se, "ci95_lower": est-crit*se, "ci95_upper": est+crit*se, "p_value": float(2*stats.t.sf(abs(t), df)) if np.isfinite(t) else None, "df_cluster": df})
    binary = outcome in {"any_vac_next", "any_vac_prior"}
    for row in result:
        row["estimate_unit"] = "percentage_points" if binary else "asinh_events"
        if binary:
            row["estimate_percentage_points"] = 100 * row.pop("estimate")
            row["se_percentage_points"] = 100 * row.pop("se")
            row["ci95_percentage_points_lower"] = 100 * row.pop("ci95_lower")
            row["ci95_percentage_points_upper"] = 100 * row.pop("ci95_upper")
        else:
            row["estimate_asinh_events"] = row["estimate"]
    return {"outcome": outcome, "rank": rank, "nobs": n, "country_clusters": G, "nuisance_rank": int(nuisance), "residual_df": int(residual_df), "betas": dict(zip(ARMS, map(float, beta))), "cluster_covariance": cov.tolist(), "contrasts": result}


def run_experiment(ledger: pd.DataFrame, bridge: pd.DataFrame, panel: pd.DataFrame, w5_frame: pd.DataFrame, policy: dict | str | Path) -> dict[str, Any]:
    bridge_out, proxy, diagnostics = build_proxy_panel(ledger, bridge, panel, policy, "broad")
    _, narrow_proxy, _ = build_proxy_panel(ledger, bridge, panel, policy, "narrow")
    frame = _prepare_outcomes(proxy, w5_frame)
    narrow_frame = _prepare_outcomes(narrow_proxy, w5_frame)
    support = {}
    for width, support_frame in (("broad", frame), ("narrow", narrow_frame)):
      support[width] = {}
      for donor, prefix, pos, other in (("china", "cn", "cn_positive_only", "cn_other_only"), ("world_bank", "wb", "wb_positive_only", "wb_other_only")):
        cp = support_frame.groupby(["country_iso3", "period_id"], observed=True).arm.agg(lambda x: {pos, other} <= set(x))
        cp_support = int(cp.sum())
        same_period_countries = int(cp[cp].index.get_level_values("country_iso3").nunique())
        countries_across_periods = support_frame.loc[support_frame.arm.isin([pos, other])].groupby("country_iso3").arm.nunique()
        strong_support = bool((support_frame.arm == pos).sum() >= 100 and (support_frame.arm == other).sum() >= 100 and cp_support >= 20 and same_period_countries >= 12)
        support[width][donor] = {"positive_cells": int((support_frame.arm == pos).sum()), "other_cells": int((support_frame.arm == other).sum()), "country_periods_both": cp_support, "countries_both_same_period": same_period_countries, "countries_both_across_any_period": int(countries_across_periods.ge(2).sum()), "support_gate": "PASS_DESCRIPTIVE_COSUPPORT" if strong_support else "THIN_SUPPORT_NO_STRONG_INFERENCE", "thin_support": not strong_support}
    models = {"broad_any_vac_next": _fit(frame, "any_vac_next"), "narrow_any_vac_next": _fit(narrow_frame, "any_vac_next"), "broad_asinh_vac_events_next": _fit(frame, "asinh_vac_events_next"), "broad_any_vac_prior_negative_control": _fit(frame, "any_vac_prior")}
    return {"schema": "fcv.w7.exploratory_jobs_proxy_results.v0", "diagnostics": diagnostics, "support": support, "models": models, "arm_order": ARMS, "estimand": "observational sector proxy contrast; never actual jobs/wage effect", "bridge_rows": int(len(bridge_out))}
