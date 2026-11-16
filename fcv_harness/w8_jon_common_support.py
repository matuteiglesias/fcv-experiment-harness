"""W8 ADM2 country-period exact-strata J/O/N standardization.

J is a W7 sector-**candidate** proxy, not verified local paid employment.
All groups are source-defined and W7/W5 outcomes are read-only.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

ARM_BY_DONOR = {
    "china": ("cn_positive_only", "cn_other_only"),
    "world_bank": ("wb_positive_only", "wb_other_only"),
}
KEY = ["geo_uid", "period_id"]
STRATUM = ["country_iso3", "period_id"]
GROUPS = ("J", "O", "N")
CONTRASTS = (("J_minus_N", "J", "N"), ("O_minus_N", "O", "N"), ("J_minus_O", "J", "O"))


class W8DesignError(ValueError):
    pass


def _check_keys(df: pd.DataFrame, name: str) -> None:
    if (not set(KEY).issubset(df.columns) or df[KEY].isna().any().any()
            or df.duplicated(KEY).any()):
        raise W8DesignError(f"{name}: null, missing or duplicate ADM2-period keys")


def merge_exposure_outcome(proxy: pd.DataFrame, w5: pd.DataFrame) -> pd.DataFrame:
    """Join only the immutable outcome columns; no outcome used for group assignment."""
    _check_keys(proxy, "W7 proxy")
    _check_keys(w5, "W5 outcome")
    required = {"arm", "country_iso3", "cn_project_count", "wb_project_count"}
    if not required.issubset(proxy):
        raise W8DesignError(f"W7 proxy missing {sorted(required - set(proxy))}")
    if not {"any_vac_next", "vac_events_prior", "country_iso3"}.issubset(w5):
        raise W8DesignError("W5 missing required outcome/country fields")
    if len(proxy) != len(w5) or (set(map(tuple, proxy[KEY].to_numpy())) !=
                              set(map(tuple, w5[KEY].to_numpy()))):
        raise W8DesignError("W5/W7 panel key parity violation")
    columns = KEY + ["country_iso3", "any_vac_next", "vac_events_prior"]
    if w5[columns].isna().any().any():
        raise W8DesignError("W5 null core fields")
    out = proxy.merge(w5[columns], on=KEY, how="left", validate="one_to_one",
                      suffixes=("", "_w5"))
    if not out.country_iso3.eq(out.country_iso3_w5).all():
        raise W8DesignError("country mismatch W5/W7")
    out = out.drop(columns="country_iso3_w5")
    if not out.any_vac_next.isin([0, 1, False, True]).all():
        raise W8DesignError("next VAC incidence must be binary")
    if (out.vac_events_prior < 0).any():
        raise W8DesignError("prior VAC event count must be nonnegative")
    for c in ("cn_project_count", "wb_project_count"):
        if out[c].isna().any() or (out[c] < 0).any():
            raise W8DesignError(f"invalid source project count {c}")
    return out


def construct_master(frame: pd.DataFrame, donor: str, control_rule: str = "not_yet_recorded",
                     scenario: str = "broad") -> pd.DataFrame:
    """Assign J, O, N or X after full-panel prior-exposure history audit."""
    if donor not in ARM_BY_DONOR or control_rule not in {"not_yet_recorded", "period_only"} or scenario not in {"broad", "narrow"}:
        raise W8DesignError("invalid donor, scenario or control rule")
    _check_keys(frame, "W8 input")
    needed = set(KEY + ["arm", "country_iso3", "cn_project_count", "wb_project_count", "any_vac_next", "vac_events_prior"])
    if not needed.issubset(frame):
        raise W8DesignError("W8 missing required fields")
    x = frame.sort_values(["geo_uid", "period_id"]).copy()
    # Balanced source panel: all seven bins for every unique ADM2, same canonical ordering.
    periods = sorted(x.period_id.unique().tolist())
    if len(periods) != 7 or len(x) != 7 * x.geo_uid.nunique():
        raise W8DesignError("W8 requires full frozen seven-period ADM2 panel")
    if not x.groupby("geo_uid").period_id.nunique().eq(7).all():
        raise W8DesignError("incomplete geographic period coverage")
    if x.groupby("geo_uid").country_iso3.nunique().max() != 1:
        raise W8DesignError("ADM2 country not invariant")
    cn = x.cn_project_count.gt(0)
    wb = x.wb_project_count.gt(0)
    legal_arm = (
        (x.arm.isin(("cn_positive_only", "cn_other_only", "cn_mixed_or_unknown")) & cn & ~wb) |
        (x.arm.isin(("wb_positive_only", "wb_other_only", "wb_mixed_or_unknown")) & wb & ~cn) |
        (x.arm.eq("both_sources") & cn & wb) |
        (x.arm.eq("neither_recorded") & ~cn & ~wb)
    )
    if not legal_arm.all():
        raise W8DesignError("source project counts disagree with declared donor-exclusive arm")
    x["w8_donor"] = donor
    x["w8_scenario"] = scenario
    x["w8_control_rule"] = control_rule
    x["any_source_now"] = cn | wb
    x["had_source_before"] = x.groupby("geo_uid", sort=False).any_source_now.transform(
        lambda v: v.cummax().shift(fill_value=False)
    ).astype(bool)
    positive, other = ARM_BY_DONOR[donor]
    x["jon_group"] = "X"
    x.loc[x.arm.eq(positive), "jon_group"] = "J"
    x.loc[x.arm.eq(other), "jon_group"] = "O"
    n_condition = ~x.any_source_now
    if control_rule == "not_yet_recorded":
        n_condition = n_condition & ~x.had_source_before
    x.loc[n_condition, "jon_group"] = "N"
    n = x[x.jon_group.eq("N")]
    if n.any_source_now.any() or (control_rule == "not_yet_recorded" and n.had_source_before.any()):
        raise W8DesignError("control exposure purity violated")
    excluded = x.jon_group.eq("X")
    if len(x) != len(frame) or x.loc[~excluded, "jon_group"].isin(GROUPS).sum() + excluded.sum() != len(x):
        raise W8DesignError("W8 groups fail full population conservation")
    return x.sort_values(KEY).reset_index(drop=True)


def matched_standardization(master: pd.DataFrame, donor: str, scenario: str,
                            control_rule: str, boot_reps: int = 1999,
                            seed: int = 20261116) -> tuple[dict[str, Any], pd.DataFrame]:
    """Exactly coarsened matched country-period J/O/N means with J-target weights.

    Bootstrap resamples whole countries, preserving all strata and the three groups.
    """
    if boot_reps < 0:
        raise W8DesignError("negative bootstrap count")
    if donor not in ARM_BY_DONOR or scenario not in {"broad", "narrow"} or control_rule not in {"not_yet_recorded", "period_only"}:
        raise W8DesignError("invalid W8 donor, scenario or control metadata")
    for column, expected in (("w8_donor", donor), ("w8_scenario", scenario), ("w8_control_rule", control_rule)):
        if column not in master or not master[column].eq(expected).all():
            raise W8DesignError(f"W8 estimator metadata mismatch: {column}")
    cols = STRATUM + ["jon_group", "any_vac_next", "geo_uid", "had_source_before"]
    if not set(cols).issubset(master):
        raise W8DesignError("master missing support fields")
    valid = master.loc[master.jon_group.isin(GROUPS)].copy()
    size = valid.groupby(STRATUM + ["jon_group"], observed=True).size().unstack(fill_value=0)
    for g in GROUPS:
        if g not in size:
            size[g] = 0
    full = size.loc[size[list(GROUPS)].gt(0).all(axis=1)].copy()
    if full.empty:
        raise W8DesignError(f"{donor}/{scenario}: no J/O/N common strata")
    indices = pd.MultiIndex.from_frame(valid[STRATUM])
    chosen = indices.isin(full.index)
    matched = valid.loc[chosen].copy()
    if not all(g in set(matched.jon_group) for g in GROUPS):
        raise W8DesignError("incomplete matched group")
    matched["stratum_nJ"] = pd.MultiIndex.from_frame(matched[STRATUM]).map(full["J"]).astype(int)
    matched["stratum_nOwn"] = matched.groupby(STRATUM + ["jon_group"])["geo_uid"].transform("size").astype(int)
    nJ = int(full["J"].sum())
    matched["analysis_weight"] = matched.stratum_nJ / nJ / matched.stratum_nOwn
    check_weight = matched.groupby("jon_group").analysis_weight.sum()
    if not np.allclose(check_weight.loc[list(GROUPS)].to_numpy(), 1.0, atol=1e-12):
        raise W8DesignError("group standardized weights do not sum to one")
    means = matched.groupby("jon_group", sort=True).apply(
        lambda z: float(np.dot(z.analysis_weight, z.any_vac_next)), include_groups=False
    ).to_dict()
    # Aggregate by common strata, then by COUNTRY for cluster resampling.
    grouped = matched.groupby(STRATUM + ["jon_group"], observed=True).any_vac_next.agg(["mean", "size"]).reset_index()
    pivot_mean = grouped.pivot(index=STRATUM, columns="jon_group", values="mean").loc[full.index, list(GROUPS)]
    if pivot_mean.isna().any().any():
        raise W8DesignError("missing a grouped mean in common support")
    jn = full["J"].astype(float)
    m_country = pivot_mean.mul(jn.to_numpy(), axis=0)
    m_country["stratum_J"] = jn.to_numpy()
    cluster = m_country.groupby(level="country_iso3", sort=True).sum()
    nums = cluster[list(GROUPS)].to_numpy(dtype=float)
    den = cluster.stratum_J.to_numpy(dtype=float)
    if not np.allclose(nums.sum(axis=0) / den.sum(), [means[g] for g in GROUPS], atol=1e-12):
        raise W8DesignError("country-cluster aggregation mean mismatch")
    delta = {name: float(means[a] - means[b]) for name, a, b in CONTRASTS}
    if abs(delta["J_minus_O"] - (delta["J_minus_N"] - delta["O_minus_N"])) > 1e-12:
        raise W8DesignError("three contrasts violate exact identity")
    clusters = int(len(cluster))
    weights_by_country = den / den.sum()
    eff_countries = float(1.0 / np.sum(weights_by_country**2))
    intervals: dict[str, dict[str, Any]] = {}
    if boot_reps:
        rng = np.random.default_rng(seed)
        multiplier = rng.multinomial(clusters, [1 / clusters] * clusters, size=boot_reps)
        boot_means = (multiplier @ nums) / (multiplier @ den)[:, None]
        for name, a, b in CONTRASTS:
            k, j = GROUPS.index(a), GROUPS.index(b)
            dist = 100 * (boot_means[:, k] - boot_means[:, j])
            intervals[name] = {
                "cluster_bootstrap_percentile95_pp": [float(v) for v in np.quantile(dist, [.025, .975])],
                "cluster_bootstrap_se_pp": float(np.std(dist, ddof=1))
            }
    total_num = nums.sum(axis=0)
    total_denom = den.sum()
    for name, a, b in CONTRASTS:
        ai, bi = GROUPS.index(a), GROUPS.index(b)
        looc = (total_num[None, :] - nums) / (total_denom - den)[:, None]
        contrast = 100 * (looc[:, ai] - looc[:, bi])
        intervals.setdefault(name, {}).update({
            "leave_one_country_out_range_pp": [float(np.min(contrast)), float(np.max(contrast))]
        })
    orig_counts = master.jon_group.value_counts()
    matched_counts = matched.jon_group.value_counts()
    group_profile = {}
    for g in GROUPS:
        weight = matched.loc[matched.jon_group.eq(g), "analysis_weight"].to_numpy(dtype=float)
        group_profile[g] = {
            "full_panel_group_cells": int(orig_counts.get(g, 0)),
            "matched_group_cells": int(matched_counts.get(g, 0)),
            "retained_fraction": float(matched_counts.get(g, 0) / orig_counts[g]) if orig_counts.get(g, 0) else None,
            "distinct_matched_adm2": int(matched.loc[matched.jon_group.eq(g), "geo_uid"].nunique()),
            "weighted_effective_N": float(1 / np.sum(weight**2)),
            "fraction_with_previous_source_record": float(matched.loc[matched.jon_group.eq(g), "had_source_before"].mean()),
            "standardized_vac_incidence_pct": 100 * float(means[g]),
            "unweighted_vac_incidence_pct_in_matched_cells": 100 * float(matched.loc[matched.jon_group.eq(g), "any_vac_next"].mean()),
        }
    output = {
        "schema": "fcv.w8.jon_matched_standardization_v0",
        "donor": donor, "scenario": scenario, "control_rule": control_rule,
        "reference_population": "matched J candidate-sector ADM2-finance-biennium cells",
        "matched_country_period_strata": int(len(full)),
        "matched_countries": clusters,
        "effective_weighted_countries": eff_countries,
        "stratum_weights_sum": 1.0,
        "groups": group_profile,
        "means_pct": {g: 100 * float(means[g]) for g in GROUPS},
        "contrasts_pp": {k: 100 * v for k, v in delta.items()},
        "identity_error_pp": 100 * float(delta["J_minus_O"] - delta["J_minus_N"] + delta["O_minus_N"]),
        "uncertainty": intervals,
        "bootstrap_replications": boot_reps,
        "bootstrap_seed": seed,
        "support_gate": "PASS_DESCRIPTIVE_COSUPPORT" if clusters >= 12 and len(full) >= 20 else "THIN_SUPPORT_DESCRIPTIVE_ONLY",
        "not_causal": True,
        "not_measured_employment": True,
    }
    return output, matched
