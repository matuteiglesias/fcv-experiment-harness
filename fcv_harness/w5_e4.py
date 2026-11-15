"""W5 E4 predeclared observational influence / source precision audit.

Never delete a source event or a country from canonical datasets. Create
counterfactual sensitivity frames only, and report every scheduled contrast.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from scipy import stats

from .w5_china_wb_vac import ARM_COLS, residualize_balanced, sha256_file
from .w5_e2_e3 import fit_balanced_fe_ols, load_accepted_frame


def _contrast(model: dict) -> dict:
    return model["contrasts"][-1]


def _row(label: str, outcome: str, model: dict, dropped: int, **extra) -> dict[str, Any]:
    q = _contrast(model)
    return {
        "scenario": label, "outcome": outcome,
        "nobs": int(model["nobs"]), "countries": int(model["n_countries"]),
        "removed_rows": int(dropped),
        "estimate": float(q["estimate"]),
        "se_country_cluster": float(q["se_country_cluster"]),
        "ci95_lower": float(q["ci95_lower"]), "ci95_upper": float(q["ci95_upper"]),
        "p_value_two_sided": float(q["p_value_two_sided"]),
        **extra,
    }


def _fit_two_outcomes(frame: pd.DataFrame, label: str, removed: int = 0, **extra) -> list[dict]:
    if len(frame) == 0 or frame.groupby("geo_uid").period_id.nunique().nunique() != 1:
        raise ValueError("country-out scenario is not an exact balanced subpanel")
    return [
        _row(label, col, fit_balanced_fe_ols(frame, col), removed, **extra)
        for col in ("any_vac_next", "vac_fatalities_next")
    ]


def run_country_influence(frame: pd.DataFrame, top_countries: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if len(top_countries) != 5 or len(set(top_countries)) != 5:
        raise ValueError("E4 expects five descending-fatality selected countries")
    baseline = _fit_two_outcomes(frame, "all_countries")
    rows = list(baseline)
    countries = sorted(frame.country_iso3.unique())
    for country in countries:
        sub = frame.loc[frame.country_iso3.ne(country)].copy()
        rows.extend(_fit_two_outcomes(sub, f"leave_out_{country}", len(frame)-len(sub),
                                     removed_countries=country))
    for n in (1,2,3,5):
        removed = top_countries[:n]
        sub = frame.loc[~frame.country_iso3.isin(removed)].copy()
        rows.extend(_fit_two_outcomes(sub, f"cumulative_top_{n}", len(frame)-len(sub),
                                     removed_countries=",".join(removed)))
    result = pd.DataFrame(rows)
    diagnostics = {}
    for outcome in ("any_vac_next", "vac_fatalities_next"):
        base = result.loc[(result.scenario == "all_countries") & (result.outcome == outcome)].iloc[0]
        sub = result.loc[(result.scenario != "all_countries") & (result.outcome == outcome)]
        ones = sub[sub.scenario.str.startswith("leave_out_")]
        crossing = ones.loc[(ones.p_value_two_sided < 0.05) != (base.p_value_two_sided < 0.05)]
        signflip = ones.loc[np.sign(ones.estimate) != np.sign(base.estimate)]
        diagnostics[outcome] = {
            "baseline_estimate": float(base.estimate), "baseline_p": float(base.p_value_two_sided),
            "leave_one_country_min_estimate": float(ones.estimate.min()),
            "leave_one_country_max_estimate": float(ones.estimate.max()),
            "leave_one_country_sign_flip": signflip.scenario.to_list(),
            "leave_one_country_p_0p05_status_change": crossing.scenario.to_list(),
            "max_abs_coefficient_change_country": str(
                ones.iloc[np.argmax(np.abs(ones.estimate.to_numpy()-base.estimate))].scenario),
            "cumulative_top3": sub.loc[sub.scenario.eq("cumulative_top_3")].to_dict("records")[0],
        }
    return result, {
        "ranking_by": "realized VAC fatalities (not significance, prespecified E2 tail)",
        "top_five_countries": top_countries,
        "one_by_one_count": len(countries),
        "scheduled_scenarios": result.scenario.nunique(),
        "outcome_diagnostics": diagnostics,
        "meaning": "country deletion is influence stress, not a correction or causal identification",
    }


def _nonchanging_source_status(frame: pd.DataFrame) -> None:
    if frame.empty or not frame[["cn_project_count","wb_project_count"]].notna().all().all():
        raise ValueError("unexpected accepted W5 source panel")


def source_precision_stresses(frame: pd.DataFrame, roster: pd.DataFrame,
                              strict_cn_relation: str = "matched_single") -> tuple[pd.DataFrame, dict[str, Any]]:
    _nonchanging_source_status(frame)
    req = {"source_family","source_project_id","geo_uid","period_id",
           "geography_relation_status","geographic_confidence"}
    if req - set(roster):
        raise ValueError(f"source roster columns missing {req-set(roster)}")
    if roster.duplicated(["source_family","source_project_id","geo_uid","period_id","source_location_id"]).any():
        raise ValueError("duplicate source project/location roster")
    key=["geo_uid","period_id"]
    base=frame[key+["cn_project_count","wb_project_count"]].copy()
    for source, col in (("china","cn_project_count"),("world_bank","wb_project_count")):
        unique=roster.loc[roster.source_family.eq(source)].groupby(key).source_project_id.nunique()
        reconstructed=frame.set_index(key).index.map(unique).fillna(0).to_numpy(dtype=int)
        if not np.array_equal(reconstructed,base[col].to_numpy()):
            raise ValueError(f"source roster fails parity against Gold source project counts: {source}")
    wb_strict=roster.loc[
        roster.source_family.eq("world_bank") &
        roster.geographic_confidence.isin(["exact_named_place","verified_adm2"])
    ].groupby(key).source_project_id.nunique()
    cn_strict=roster.loc[
        roster.source_family.eq("china") &
        roster.geography_relation_status.eq(strict_cn_relation)
    ].groupby(key).source_project_id.nunique()
    idx=frame.set_index(key).index
    wb_s=idx.map(wb_strict).fillna(0).to_numpy(dtype=int)
    cn_s=idx.map(cn_strict).fillna(0).to_numpy(dtype=int)
    # Gold high confidence is exact named place + verified ADM2 by policy.
    # Any discrepancy is a HOLD, not a change to a strict donor definition.
    gold=base.copy()
    if "wb_high_confidence_project_count" not in frame:
        raise ValueError("W5 frame lacks source Gold high-confidence count; use verified roster only")
    if not np.array_equal(wb_s,frame.wb_high_confidence_project_count.to_numpy()):
        raise ValueError("WB high-confidence roster and source Gold disagree")
    if np.any(cn_s > frame.cn_project_count.to_numpy()):
        raise ValueError("CN restricted source count exceeds Gold")
    scenarios={
        "wb_high_confidence_only_china_broad": (frame.cn_project_count.to_numpy(),wb_s),
        "china_single_ADM2_assignment_only_wb_broad": (cn_s,frame.wb_project_count.to_numpy()),
        "wb_high_confidence_and_china_single_assignment": (cn_s,wb_s),
    }
    rows=[]
    states={}
    for name,(cn,wb) in scenarios.items():
        x=frame.copy()
        x["china_only"]=((cn>0)&(wb==0)).astype(int)
        x["wb_only"]=((wb>0)&(cn==0)).astype(int)
        x["both"]=((cn>0)&(wb>0)).astype(int)
        x["neither_recorded"]=((cn==0)&(wb==0)).astype(int)
        if (x[list(ARM_COLS)+["neither_recorded"]].sum(axis=1)!=1).any():
            raise ValueError("invalid strict exposure partition")
        try:
            out=_fit_two_outcomes(x,name,0,stress="asymmetric_source_definition")
            rows.extend(out)
            states[name]={"status":"RUN_DESCRIPTIVE",
                         "source_arms":{t:int(x[t].sum()) for t in [*ARM_COLS,"neither_recorded"]},
                         "description":"source count confidence filters are not comparable across donors"}
        except (ValueError,np.linalg.LinAlgError) as exc:
            states[name]={"status":"HOLD_FE_SUPPORT", "reason":str(exc)}
    return pd.DataFrame(rows),{
        "roster_parity":"PASS","roster_rows":len(roster),
        "wb_high_confidence_project_definition":"exact_named_place_or_verified_adm2",
        "china_single_definition":"matched_single_ADM2_source_geometry_relation",
        "warning":"CN source_geometry_original geometries may span multiple ADM2: matched_multiple is not necessarily low coordinate precision. Strict filters asymmetric and change interpretation.",
        "scenarios":states,
    }


def fit_history_adjusted(frame: pd.DataFrame, outcome: str) -> dict[str, Any]:
    """ADM2 and country-period FE with source-history flags as extra controls."""
    if outcome not in ("any_vac_next","vac_fatalities_next"):
        raise ValueError("not a frozen history sensitivity outcome")
    x=frame.sort_values(["geo_uid","period_id"]).copy()
    for prefix in ("cn","wb"):
        x[f"prior_{prefix}"] = x.groupby("geo_uid")[f"{prefix}_project_count"].transform(
            lambda s: s.gt(0).astype(int).cumsum().shift(fill_value=0).gt(0).astype(int)
        )
    cols=[*ARM_COLS,"prior_cn","prior_wb"]
    v=residualize_balanced(x,[*cols,outcome])
    Z,y=v[:,:5],v[:,5]
    if np.linalg.matrix_rank(Z)!=5:
        raise ValueError("additional source-history covariates not identified")
    b=np.linalg.solve(Z.T@Z,Z.T@y)
    err=y-Z@b
    groups,codes=np.unique(x.country_iso3.to_numpy(),return_inverse=True)
    G=len(groups);N=len(x);K=Z.shape[1]
    nuisance=x.geo_uid.nunique()+x.country_period.nunique()-G
    df=N-nuisance-K
    scores=np.column_stack([np.bincount(codes,weights=Z[:,j]*err,minlength=G) for j in range(K)])
    inv=np.linalg.inv(Z.T@Z)
    V=G/(G-1)*(N-1)/df*inv@(scores.T@scores)@inv
    z=np.array([1.,-1.,0.,0.,0.])
    effect=float(z@b);se=float(np.sqrt(z@V@z))
    cutoff=float(stats.t.ppf(.975,G-1))
    return {
        "outcome":outcome,"scenario":"prior_CN_WB_recorded_source_history_controls",
        "nobs":N,"countries":G,"estimator":"area_and_countryperiod_FE_five_covariates_country_CR1",
        "estimate":effect,"se_country_cluster":se,
        "ci95_lower":effect-cutoff*se,"ci95_upper":effect+cutoff*se,
        "p_value_two_sided":float(2*stats.t.sf(abs(effect/se),G-1)),
        "prior_cn_rows":int(x.prior_cn.sum()),"prior_wb_rows":int(x.prior_wb.sum()),
        "coefficients":dict(zip(cols,[float(k) for k in b])),
        "meaning":"all recorded earlier source periods within panel; left-censored before first observed biennium",
    }


def event_to_accepted_area_period(
    frame: pd.DataFrame, event_silver: pd.DataFrame,
    event_geo: pd.DataFrame, event_period: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Exact event-level ACLED lineage; zero missing only after certified parity.

    A source event is eligible if exactly one ADM2 and a 2-year period
    assignment are established. Compare all original cell counts AND totals
    against accepted Gold BEFORE any event scenario is allowed.
    """
    required={
        "silver":(event_silver,{"event_row_id","source_event_id","native_event_type","fatalities","geo_precision","event_date"}),
        "geography":(event_geo,{"event_row_id","geo_uid","assignment_status"}),
        "period":(event_period,{"event_row_id","period_id","period_assignment_status"}),
    }
    for name,(f,cols) in required.items():
        if cols-set(f):
            raise ValueError(f"event {name} missing {cols-set(f)}")
    for name,f in (("silver",event_silver),("period",event_period)):
        if f.event_row_id.duplicated().any():
            raise ValueError(f"duplicate event row ID in {name}")
    accepted=event_silver.loc[
        event_silver.native_event_type.eq("Violence against civilians"),
        ["event_row_id","source_event_id","native_event_type","fatalities","geo_precision","event_date"],
    ].copy()
    if accepted.event_row_id.duplicated().any():
        raise ValueError("duplicate eligible event IDs")
    accepted=accepted.merge(
        event_geo.loc[
            event_geo.assignment_status.eq("matched_unique"),
            ["event_row_id","geo_uid"],
        ],
        on="event_row_id",validate="one_to_one",how="inner",
    ).merge(
        event_period.loc[
            event_period.period_assignment_status.eq("assigned"),
            ["event_row_id","period_id"],
        ],
        on="event_row_id",validate="one_to_one",how="inner",
    )
    if accepted[["event_row_id","geo_uid","period_id","fatalities"]].isna().any().any():
        raise ValueError("eligible event id/geography/period/fatalities absent")
    if not np.isfinite(accepted.fatalities.to_numpy()).all() or accepted.fatalities.lt(0).any():
        raise ValueError("invalid event fatalities for parity")
    # W5 outcome is the *next period*, not investment period.
    key=["geo_uid","period_id"]
    lookup=frame[["geo_uid","next_period","country_iso3","vac_events_next","vac_fatalities_next"]].rename(
        columns={"next_period":"period_id"}
    )
    if lookup.duplicated(key).any():
        raise ValueError("W5 outcome target keys duplicated")
    eligible=accepted.merge(
        lookup[key+["country_iso3"]],on=key,how="inner",validate="many_to_one"
    )
    reconstructed=eligible.groupby(key).agg(
        events=("event_row_id","count"),fatalities=("fatalities","sum")
    )
    parity=lookup.set_index(key).join(reconstructed,how="left").fillna(
        {"events":0,"fatalities":0}
    )
    if not np.array_equal(parity.events.to_numpy(),parity.vac_events_next.to_numpy()):
        delta=np.abs(parity.events-parity.vac_events_next).sum()
        raise ValueError(f"ACLED event-level count parity FAIL, total absolute discrepancy {delta}")
    if not np.allclose(parity.fatalities,parity.vac_fatalities_next,atol=1e-8,rtol=0):
        delta=np.abs(parity.fatalities-parity.vac_fatalities_next).sum()
        raise ValueError(f"ACLED event-level fatality parity FAIL, absolute discrepancy {delta}")
    if eligible.event_row_id.duplicated().any():
        raise ValueError("one source event assigned twice to W5 outcome")
    info={
        "status":"PASS_EVENT_TO_CERTIFIED_GOLD_EXACT_CELL_PARITY",
        "vac_source_silver_rows":len(accepted),"eligible_matched_W5_outcome_rows":len(eligible),
        "event_count_gold":int(parity.vac_events_next.sum()),
        "event_count_rebuilt":int(parity.events.sum()),
        "fatalities_gold":float(parity.vac_fatalities_next.sum()),
        "fatalities_rebuilt":float(parity.fatalities.sum()),
        "n_positive_outcome_cells":int((parity.events>0).sum()),
        "event_geo_precision_counts":{
            str(k):int(v) for k,v in eligible.geo_precision.astype(str).value_counts().items()
        },
        "lineage_note":"unique ADM2 event and assigned biennium from original certified Gold precursor; no raw source mutated",
    }
    return eligible,info


def event_removal_scenarios(
    frame: pd.DataFrame, eligible_events: pd.DataFrame
) -> tuple[pd.DataFrame,pd.DataFrame,dict[str,Any]]:
    """Delete actual mapped event rows in counterfactual copies, not whole areas.

    Source event ranking uses fatalities only, NOT treatment nor fitted residuals;
    predeclared 1,5,10 and top 1% *positive-fatality* event rows.
    """
    ranked=eligible_events.loc[eligible_events.fatalities.gt(0)].sort_values(
        ["fatalities","event_row_id"], ascending=[False,True],kind="stable"
    )
    if len(ranked) < 10:
        raise ValueError("too few fatal events for event-influence stress")
    top_pct=max(1,int(np.ceil(.01*len(ranked))))
    counts={"drop_largest_1_event":1,"drop_largest_5_events":5,
            "drop_largest_10_events":10,
            "drop_top_1pct_positive_fatality_events":top_pct}
    rows=[]
    info={"ranked_fatal_events":len(ranked),"eligible_total_events":len(eligible_events),
          "experiment_rows":{},"selection_rule":"reported event fatalities desc, event_row_id asc; independent of donor and model",
          "counterfactual_outcome_perturbation":True}
    # For each scenario, subtract only removed events from the original certified
    # cell values. An event with 0 deaths cannot be in the fatality-ranked list.
    for label,k in counts.items():
        cut=ranked.head(k)
        reduced=cut.groupby(["geo_uid","period_id"]).agg(
            removed_events=("event_row_id","size"),
            removed_fatalities=("fatalities","sum")
        ).reset_index().rename(columns={"period_id":"next_period"})
        perturb=frame.merge(reduced,on=["geo_uid","next_period"],validate="one_to_one",how="left")
        re=perturb.removed_events.fillna(0).to_numpy(dtype=int)
        rf=perturb.removed_fatalities.fillna(0).to_numpy(dtype=float)
        perturb["vac_events_next"]=perturb.vac_events_next.to_numpy()-re
        perturb["vac_fatalities_next"]=perturb.vac_fatalities_next.to_numpy()-rf
        if (perturb.vac_events_next.lt(0) | perturb.vac_fatalities_next.lt(-1e-7)).any():
            raise ValueError("event deletions produce negative certified aggregate")
        perturb["any_vac_next"]=perturb.vac_events_next.gt(0).astype(int)
        out=_fit_two_outcomes(perturb,label,0,
                              removed_events=k,removed_fatalities=float(cut.fatalities.sum()),
                              changed_cells=int((re>0).sum()))
        rows.extend(out)
        info["experiment_rows"][label]={
            "removed_event_count":k,"sum_reported_fatalities_removed":float(cut.fatalities.sum()),
            "share_of_all_W5_fatalities_removed":float(cut.fatalities.sum()/frame.vac_fatalities_next.sum()),
            "cells_changed":int((re>0).sum()),"countries_affected":sorted(cut.country_iso3.unique().tolist()),
            "source_event_row_ids":cut.event_row_id.astype(str).tolist(),
        }
    top=ranked.head(25)[
        ["event_row_id","source_event_id","event_date","geo_uid","period_id",
         "country_iso3","fatalities","geo_precision"]
    ].copy()
    return pd.DataFrame(rows),top,info


def run_e4(
    frame: pd.DataFrame, investment: pd.DataFrame, roster: pd.DataFrame,
    event_silver: pd.DataFrame, event_geo: pd.DataFrame, event_period: pd.DataFrame,
    spec: dict[str,Any], e4_spec: dict[str,Any],
) -> tuple[dict[str,Any],dict[str,pd.DataFrame]]:
    if e4_spec.get("schema") != "fcv.w5.e4.influence.v1":
        raise ValueError("wrong E4 manifest")
    if e4_spec.get("country_deletions") != "leave_each_of_47_countries_out_and_top_fatality_cumulative":
        raise ValueError("E4 country influence manifest changed")
    if e4_spec.get("event_deletions") != [
        "top_1","top_5","top_10","top_1pct_positive_fatality_events",
    ]:
        raise ValueError("E4 event deletion settings changed")
    country_rank=frame.groupby("country_iso3").vac_fatalities_next.sum().sort_values(
        ascending=False,kind="stable"
    )
    top_five=list(country_rank.head(5).index)
    country_rows,country_info=run_country_influence(frame,top_five)
    events,event_info=event_to_accepted_area_period(
        frame,event_silver,event_geo,event_period
    )
    event_rows,top_events,event_effect_info=event_removal_scenarios(frame,events)
    strict=investment[["geo_uid","period_id","wb_high_confidence_project_count"]]
    frame_precision=frame.merge(strict,on=["geo_uid","period_id"],
                                validate="one_to_one",how="left")
    if frame_precision.wb_high_confidence_project_count.isna().any():
        raise ValueError("missing WB strict source data in accepted investment panel")
    precision_rows,precision_info=source_precision_stresses(frame_precision,roster)
    history_models=[
        fit_history_adjusted(frame,"any_vac_next"),
        fit_history_adjusted(frame,"vac_fatalities_next"),
    ]
    tables={
        "country_leaveout_effects":country_rows,
        "top_source_events":top_events,
        "event_influence_effects":event_rows,
        "source_precision_effects":precision_rows,
        "history_adjusted_effects":pd.DataFrame(history_models),
        "country_fatality_ranking":country_rank.rename("vac_fatalities").reset_index(),
    }
    result={
        "phase":"E4_COUNTRY_EVENT_PRECISION_HISTORY",
        "status":"COMPLETED_DESCRIPTIVE_INFLUENCE_WITH_SOURCE_LIMITS",
        "country":country_info,
        "event_level_parity":event_info,
        "event_removal":event_effect_info,
        "precision":precision_info,
        "history":history_models,
        "not_causal":True,
        "not_data_corrections":True,
        "limits":[
            "dropping correctly recorded events or countries changes the question and is only a sensitivity test",
            "p-value crossings are diagnostics of specification influence, not multiple-testing adjusted confirmatory evidence",
            "China/WB geography restrictions are asymmetric and cannot establish a common precision threshold",
            "historical ACLED completeness rests on original provisional operator acceptance",
            "all source deletions and original Gold untouched",
        ],
    }
    return result,tables


def acled_outcome_precision_stress(
    frame: pd.DataFrame, eligible_events: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reconstruct VAC outcomes using observed source geo_precision <= 1 and <= 2.

    This restricts *outcome source events*, not donor source records.
    It applies the same ACLED quality definition on China and WB areas.
    Certified original outcome parity must have been checked upstream.
    """
    p = pd.to_numeric(eligible_events.geo_precision, errors="coerce")
    if p.isna().any() or (~p.isin([1,2,3])).any():
        raise ValueError("ACLED geo_precision values outside documented 1/2/3; HOLD")
    original=len(eligible_events)
    rows=[]
    diag={}
    for threshold in (2,1):
        sub=eligible_events.loc[p.le(threshold)].copy()
        key=["geo_uid","period_id"]
        meas=sub.groupby(key).agg(
            observed_events=("event_row_id","size"),
            observed_fatalities=("fatalities","sum"),
        ).reset_index().rename(columns={"period_id":"next_period"})
        f=frame.merge(meas,on=["geo_uid","next_period"],how="left",validate="one_to_one")
        f["vac_events_next"]=f.observed_events.fillna(0).astype(int)
        f["vac_fatalities_next"]=f.observed_fatalities.fillna(0.0)
        f["any_vac_next"]=f.vac_events_next.gt(0).astype(int)
        if f.vac_events_next.gt(frame.vac_events_next).any() or f.vac_fatalities_next.gt(frame.vac_fatalities_next).any():
            raise ValueError("geo-precision restricted ACLED events exceed accepted Gold")
        label=f"ACLED_vac_geo_precision_le_{threshold}_ONLY"
        rows.extend(_fit_two_outcomes(f,label,0,
                                      kept_events=len(sub),
                                      excluded_events=original-len(sub),
                                      fatality_share_retained=float(sub.fatalities.sum()/frame.vac_fatalities_next.sum())))
        diag[label]={
            "kept_ACLED_events":len(sub),"excluded_ACLED_events":original-len(sub),
            "kept_ACLED_reported_fatalities":float(sub.fatalities.sum()),
            "excluded_ACLED_reported_fatalities":float(frame.vac_fatalities_next.sum()-sub.fatalities.sum()),
            "kept_positive_ADM2_periods":int(f.any_vac_next.sum()),
            "meaning":"ACLED event precision, common outcome definition, not investment-location precision",
        }
    return pd.DataFrame(rows), {
        "status":"RUN_OUTCOME_SOURCE_PRECISION_STRESS",
        "cutoffs":"ACLED reported geo_precision <= 2 and <= 1 on originally parity-checked event rows",
        "scenarios":diag,
    }
