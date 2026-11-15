"""Predeclared W5 E2 severity/frequency and E3 pre-selection diagnostics.

Scientific claim boundaries: observational associations only; first-recorded
financing is not implementation or an irreversible treatment intervention.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .w5_china_wb_vac import (
    ARM_COLS, read_spec, residualize_balanced, sha256_file, shift_period,
)


def _country_cluster_contrasts(
    beta: np.ndarray, covariance: np.ndarray, G: int, label: str, units: str,
) -> list[dict[str, Any]]:
    contrasts = [
        ("china_only_vs_neither", [1, 0, 0]),
        ("wb_only_vs_neither", [0, 1, 0]),
        ("both_vs_neither", [0, 0, 1]),
        ("china_only_minus_wb_only", [1, -1, 0]),
    ]
    if beta.shape != (3,) or covariance.shape != (3, 3):
        raise ValueError("E2/E3 expects exactly three mutually exclusive exposure indicators")
    out = []
    cutoff = float(stats.t.ppf(0.975, df=G - 1))
    for name, vec in contrasts:
        v = np.array(vec, dtype=float)
        est = float(v @ beta)
        vv = float(v @ covariance @ v)
        if vv < 0 or not np.isfinite(vv):
            raise ValueError("invalid country covariance for direct contrast")
        se = np.sqrt(vv)
        p = float(2 * stats.t.sf(abs(est / se), df=G - 1)) if se else None
        out.append({
            "outcome": label, "contrast": name, "scale": units,
            "estimate": est, "se_country_cluster": float(se),
            "ci95_lower": est - cutoff * se, "ci95_upper": est + cutoff * se,
            "p_value_two_sided": p, "country_cluster_df": G - 1,
        })
    return out


def fit_balanced_fe_ols(
    frame: pd.DataFrame, outcome: str, label: str | None = None,
) -> dict[str, Any]:
    """Exact FWL OLS with same CR1 as the original E1, generalized outcome."""
    if outcome not in frame:
        raise ValueError(f"missing E2/E3 outcome {outcome}")
    work = residualize_balanced(frame, [*ARM_COLS, outcome])
    x, y = work[:, :3], work[:, -1]
    if not np.isfinite(y).all() or np.linalg.matrix_rank(x) != 3:
        raise ValueError("nonfinite outcome or nonidentified exposure design")
    b = np.linalg.solve(x.T @ x, x.T @ y)
    err = y - x @ b
    countries, codes = np.unique(frame.country_iso3.to_numpy(), return_inverse=True)
    G = len(countries)
    n = len(frame)
    nuisance = frame.geo_uid.nunique() + frame.country_period.nunique() - G
    df = n - nuisance - len(ARM_COLS)
    if G < 5 or df <= 0:
        raise ValueError("insufficient clusters or residual degrees")
    s = np.column_stack([
        np.bincount(codes, weights=x[:, j] * err, minlength=G)
        for j in range(3)
    ])
    bread = np.linalg.inv(x.T @ x)
    correction = G / (G - 1) * (n - 1) / df
    vc = correction * bread @ (s.T @ s) @ bread
    vc = (vc + vc.T) / 2
    return {
        "estimator": "OLS_FE_ADM2_country_period_CR1",
        "outcome": outcome, "nobs": n, "n_countries": G, "n_areas": frame.geo_uid.nunique(),
        "n_country_periods": frame.country_period.nunique(), "cr1_factor": correction,
        "coefficients": dict(zip(ARM_COLS, [float(v) for v in b])),
        "contrasts": _country_cluster_contrasts(b, vc, G, label or outcome, "outcome_level"),
        "interpretation": "conditional association, not causal; rare crises can dominate level outcomes",
    }


def load_accepted_frame(
    spec_path: Path, investment_path: Path, acled_path: Path, out_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fail closed if any accepted W5 input, source receipt or cached frame changed."""
    spec = read_spec(spec_path)
    report = json.loads((out_dir / "run_receipt.json").read_text(encoding="utf-8"))
    if report.get("e0", {}).get("e0_gate") != "PASS" or report.get("e1") is None:
        raise ValueError("E2/E3 requires accepted E0 and actual E1 completed")
    expected_input = {
        "investment": spec["investment_sha256"], "acled_certified": spec["acled_sha256"],
    }
    if (report.get("input_sha256") != expected_input or
        report.get("spec_sha256") != sha256_file(spec_path)):
        raise ValueError("W5 earlier provenance/spec differs from declared lock")
    if (sha256_file(investment_path) != expected_input["investment"] or
        sha256_file(acled_path) != expected_input["acled_certified"]):
        raise ValueError("W5 sources changed since E1")
    frame_path = out_dir / "w5_analysis_frame.parquet"
    if sha256_file(frame_path) != report["analysis_frame_sha256"]:
        raise ValueError("W5 E0/E1 frame hash drift")
    frame = pd.read_parquet(frame_path)
    if len(frame) != spec["expected_rows"]:
        raise ValueError("W5 frame row-count drift")
    ac = pd.read_parquet(acled_path)
    return spec, frame, ac, report


def write_phase_outputs(
    out_dir: Path, phase: str, result: dict[str, Any],
    effect_tables: dict[str, pd.DataFrame] | None = None,
) -> None:
    if phase not in ("e2", "e3"):
        raise ValueError("unsupported phase")
    for name, table in (effect_tables or {}).items():
        table.to_csv(out_dir / f"{phase}_{name}.csv", index=False)
    (out_dir / f"{phase}_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def attach_earlier_vac(
    frame: pd.DataFrame, ac: pd.DataFrame, native_event: str,
) -> pd.DataFrame:
    """Attach t-2 outcome by exact certified source keys, fail closed on holes."""
    ikey = ["geo_uid", "country_iso3", "period_id"]
    vac = ac.loc[ac.native_event_type.eq(native_event)].copy()
    if vac.duplicated(ikey).any():
        raise ValueError("duplicate VAC outcomes in certified source")
    if not vac.measurement_status.isin(["structural_zero", "aggregated_from_observed"]).all():
        raise ValueError("unacceptable certified measurement status")
    v = vac[ikey + ["event_count", "fatalities", "fatalities_missing_event_count"]].rename(
        columns={
            "period_id": "pre2_period", "event_count": "vac_events_pre2",
            "fatalities": "vac_fatalities_pre2",
        }
    )
    f = frame.copy()
    f["pre2_period"] = f.period_id.map(lambda x: shift_period(x, -2))
    f = f.merge(
        v, on=["geo_uid", "country_iso3", "pre2_period"],
        how="left", validate="one_to_one", indicator="pre2_match",
    )
    if (len(f) != len(frame) or not f.pre2_match.eq("both").all() or
        f[["vac_events_pre2", "vac_fatalities_pre2", "fatalities_missing_event_count"]].isna().any().any() or
        (f.fatalities_missing_event_count != 0).any()):
        raise ValueError("incomplete certified pre2 VAC lineage")
    f = f.drop(columns=["pre2_match", "fatalities_missing_event_count"])
    f["any_vac_pre2"] = (f.vac_events_pre2 > 0).astype(int)
    f["any_vac_prior"] = (f.vac_events_prior > 0).astype(int)
    f["pre_vac_incidence_change"] = f.any_vac_prior - f.any_vac_pre2
    f["post_vac_incidence_change"] = f.any_vac_next - f.any_vac_prior
    return f


def _fit_country_cohort_fe(
    sub: pd.DataFrame, target: str,
) -> dict[str, Any]:
    """Residualize country×cohort FE (not area FE) on matched first-record risk sets."""
    vars = [*ARM_COLS, target]
    v = sub[vars].to_numpy(dtype=float)
    means = sub.groupby("country_period", sort=False)[vars].transform("mean").to_numpy()
    v = v - means
    x, y = v[:, :3], v[:, 3]
    if np.linalg.matrix_rank(x) != 3:
        raise ValueError("rank-deficient matched first-record risk-set sample")
    b = np.linalg.solve(x.T @ x, x.T @ y)
    e = y - x @ b
    g, codes = np.unique(sub.country_iso3.to_numpy(), return_inverse=True)
    G = len(g)
    n = len(sub)
    dof = n - sub.country_period.nunique() - len(ARM_COLS)
    if dof <= 0 or G < 5:
        raise ValueError("risk-set country support/dof too small")
    sc = np.column_stack([
        np.bincount(codes, weights=x[:,j]*e, minlength=G) for j in range(3)
    ])
    bread = np.linalg.inv(x.T@x)
    mult = G/(G-1) * (n-1)/dof
    cov = mult * bread @ (sc.T@sc) @ bread
    cov = (cov + cov.T) / 2
    return {
        "model": "country_cohort_FE_first_recorded_riskset_LPM_change",
        "outcome": target, "nobs": n, "clusters": G,
        "cohort_cells": sub.country_period.nunique(),
        "coefficients": dict(zip(ARM_COLS, [float(q) for q in b])),
        "contrasts": _country_cluster_contrasts(b, cov, G, target, "incidence_change"),
        "not_an_ATT": True, "claim": "descriptive first-recorded timing diagnostic, not causal",
    }


def build_first_recorded_riskset(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """At each t include first-ever-recorded C/W/B or source-unexposed-as-of-t controls.

    Earliest source biennium 2001-02 is left-censored and its ever-exposed
    areas are excluded from subsequent risk sets. Source-unexposed as of
    t may receive projects later; never condition on future financing.
    """
    periods = sorted(frame.period_id.unique())
    index = {period: i for i, period in enumerate(periods)}
    g = frame[["geo_uid", "period_id", "china_only", "wb_only", "both"]].copy()
    g["time_index"] = g.period_id.map(index)
    g["any_finance"] = g[list(ARM_COLS)].sum(axis=1).gt(0)
    first = g.loc[g.any_finance].groupby("geo_uid").time_index.min()
    f = frame.copy()
    f["time_index"] = f.period_id.map(index)
    f["first_finance_index"] = f.geo_uid.map(first).fillna(len(periods)).astype(int)
    left = f.first_finance_index.eq(0)
    # A unit can contribute controls to multiple not-yet periods, one first-record exposure to exactly one.
    eligible = (~left) & f.time_index.gt(0) & f.time_index.le(f.first_finance_index)
    v = f.loc[eligible].copy()
    v["is_first_exposure"] = v.time_index.eq(v.first_finance_index)
    if ((v.loc[~v.is_first_exposure, list(ARM_COLS)].sum(axis=1) != 0).any() or
        (v.loc[v.is_first_exposure, list(ARM_COLS)].sum(axis=1) != 1).any()):
        raise ValueError("first-record risk-set treatment/control history incorrect")
    v["neither_recorded"] = (~v.is_first_exposure).astype(int)
    # This is a risk-set description: restrict to country-cohorts with BOTH
    # source-exclusive first-exposed arms and at least one contemporaneous control.
    cp = v.groupby(["country_iso3", "period_id"])[list(ARM_COLS) + ["neither_recorded"]].sum().reset_index()
    matched = cp.loc[
        (cp.china_only > 0) & (cp.wb_only > 0) & (cp.neither_recorded > 0),
        ["country_iso3", "period_id"],
    ]
    selected = v.merge(matched, on=["country_iso3", "period_id"], how="inner", validate="many_to_one")
    rows = {
        "scope": "first observed financing decision in 2003–2014 after source-empty observation from 2001–02 onward",
        "left_censor_excluded_2001_2002_areas": int(left.groupby(f.geo_uid).any().sum()),
        "source_never_recorded_areas": int((f.groupby("geo_uid").first_finance_index.min() == len(periods)).sum()),
        "eligible_riskset_rows_before_country_cohort_matching": len(v),
        "matched_country_cohort_cells": len(matched),
        "matched_countries": int(matched.country_iso3.nunique()),
        "matched_rows": len(selected),
        "matched_first_CN": int(selected.china_only.sum()),
        "matched_first_WB": int(selected.wb_only.sum()),
        "matched_first_both": int(selected.both.sum()),
        "matched_neither_at_t": int(selected.neither_recorded.sum()),
        "controls_repeated_across_future_cohorts": True,
        "future_financing_not_used_as_eligibility_condition": True,
        "interpretation": "not randomized, left-censored, and not an identified ATT",
    }
    return selected, rows


def run_e3(frame: pd.DataFrame, ac: pd.DataFrame, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    pre = attach_earlier_vac(frame, ac, spec["acled_event_type"])
    models = [
        fit_balanced_fe_ols(pre, "any_vac_pre2", label="VAC_incidence_t_minus_2"),
        fit_balanced_fe_ols(pre, "any_vac_prior", label="VAC_incidence_t_minus_1"),
        fit_balanced_fe_ols(pre, "pre_vac_incidence_change", label="pretrend_change_t_minus_1_minus_t_minus_2"),
    ]
    matched, risk_info = build_first_recorded_riskset(pre)
    risk_models = []
    risk_status = "HOLD_NO_COMMON_RISKSET_SUPPORT"
    if (
        risk_info["matched_country_cohort_cells"] >= 10
        and risk_info["matched_countries"] >= 8
        and min(risk_info["matched_first_CN"], risk_info["matched_first_WB"]) >= 20
    ):
        try:
            risk_models = [
                _fit_country_cohort_fe(matched, "pre_vac_incidence_change"),
                _fit_country_cohort_fe(matched, "post_vac_incidence_change"),
            ]
            risk_status = "RUN_DESCRIPTIVE_NOT_CAUSAL"
        except ValueError as err:
            risk_status = f"HOLD_RANK_OR_PRECISION:{err}"
    tables = {
        "preperiod_effects": pd.DataFrame([row for model in models for row in model["contrasts"]]),
        "riskset_support_by_country_cohort": (
            matched.groupby(["country_iso3", "period_id"])[
                list(ARM_COLS) + ["neither_recorded"]
            ].sum().reset_index()
        ),
    }
    if risk_models:
        tables["first_recorded_effects"] = pd.DataFrame(
            [row for model in risk_models for row in model["contrasts"]]
        )
    result = {
        "phase": "E3_SELECTION_TIMING",
        "status": "COMPLETED_DESCRIPTIVE_DIAGNOSTICS",
        "pre2_match_complete": True,
        "preperiod_lpm_models": models,
        "first_recorded_riskset": risk_info,
        "first_recorded_estimation_status": risk_status,
        "first_recorded_models": risk_models,
        "assumptions": [
            "2001-02 beginning source coverage implies left-censoring for some first-financed units",
            "recorded financing decisions are not irreversible treatment starts",
            "within-country-cohort association may reflect unobserved local selection",
            "preperiod lead outcomes diagnose differential prior dynamics, not sufficient tests of parallel trends",
            "reused not-yet-financed controls require country-level clustered uncertainty",
            "no future exposure conditioned away in risk-set eligibility",
        ],
    }
    return result, tables


def _weighted_group_residual(
    x: np.ndarray, w: np.ndarray, area: np.ndarray, ct: np.ndarray,
    narea: int, nct: int, *, tolerance: float = 2e-9, max_sweeps: int = 800,
) -> tuple[np.ndarray, int, float]:
    """Weighted alternating projection onto orthogonal complement of two FE."""
    out = np.array(x, dtype=float, copy=True)
    sums_area = np.bincount(area, weights=w, minlength=narea)
    sums_ct = np.bincount(ct, weights=w, minlength=nct)
    if np.any(sums_area <= 0) or np.any(sums_ct <= 0):
        raise ValueError("nonpositive weight within FE group")
    last = float("inf")
    for iteration in range(1, max_sweeps + 1):
        for g, denom, ng in [(area, sums_area, narea), (ct, sums_ct, nct)]:
            for j in range(out.shape[1]):
                mean = np.bincount(g, weights=w * out[:, j], minlength=ng) / denom
                out[:, j] -= mean[g]
        if iteration % 5 == 0 or iteration == 1:
            e_a = max(
                np.abs(np.bincount(area, weights=w*out[:,j], minlength=narea) / sums_area).max()
                for j in range(out.shape[1])
            )
            e_t = max(
                np.abs(np.bincount(ct, weights=w*out[:,j], minlength=nct) / sums_ct).max()
                for j in range(out.shape[1])
            )
            last = float(max(e_a, e_t))
            if last <= tolerance:
                return out, iteration, last
    raise ValueError(f"weighted two-FE absorption did not converge: {max_sweeps} sweeps, residual {last:.3g}")


def _separation_prune(
    frame: pd.DataFrame, outcome: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Iteratively remove all-zero-y ADM2 and country×period FE groups.

    Such groups have -infinite Poisson FE and cannot enter finite PPML
    inference. Retain a manifest of how much outcome support is excluded.
    """
    if outcome not in ("vac_events_next", "vac_fatalities_next"):
        raise ValueError("PPML only for frozen W5 E2 count/fatalities outcomes")
    if not (frame[outcome].notna().all() and np.isfinite(frame[outcome]).all()
            and (frame[outcome] >= 0).all()):
        raise ValueError("invalid nonnegative event counts for PPML")
    f = frame.copy()
    original = len(f)
    iterations = 0
    while True:
        iterations += 1
        area_sums = f.groupby("geo_uid")[outcome].transform("sum")
        ct_sums = f.groupby("country_period")[outcome].transform("sum")
        keep = area_sums.gt(0) & ct_sums.gt(0)
        if keep.all():
            break
        f = f.loc[keep].copy()
        if f.empty or iterations > 30:
            raise ValueError("PPML separation pruning did not stabilize")
    if f.groupby("geo_uid").country_iso3.nunique().max() != 1:
        raise ValueError("geography/country corruption after PPML separation prune")
    diagnostics = {
        "outcome": outcome, "original_nobs": original, "retained_nobs": len(f),
        "pruned_rows": original - len(f), "pruning_iterations": iterations,
        "original_areas": int(frame.geo_uid.nunique()), "retained_areas": int(f.geo_uid.nunique()),
        "original_country_periods": int(frame.country_period.nunique()),
        "retained_country_periods": int(f.country_period.nunique()),
        "retained_countries": int(f.country_iso3.nunique()),
        "retained_positive_outcome_rows": int(f[outcome].gt(0).sum()),
        "source_arm_counts_after_pruning": {
            name: int(f[name].sum()) for name in list(ARM_COLS)+["neither_recorded"]
        },
        "separation_policy": "iterative_drop_all_zero_outcome_ADM2_and_country_period_FE_groups",
        "scope_warning": "conditional-on-retained-outcome-support PPML sample differs from primary E1",
    }
    return f.reset_index(drop=True), diagnostics


def _fit_ppml_inner_fe(
    xbeta: np.ndarray, y: np.ndarray, a: np.ndarray, c: np.ndarray,
    na: int, nc: int, aa: np.ndarray, cc: np.ndarray,
    *, max_iter: int = 2000, tolerance: float = 1e-8,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Poisson FE IPF: match area and country-period sufficient statistics."""
    ya = np.bincount(a, weights=y, minlength=na)
    yc = np.bincount(c, weights=y, minlength=nc)
    if np.min(ya) <= 0 or np.min(yc) <= 0:
        raise ValueError("all-zero groups remain in PPML")
    for itr in range(1, max_iter+1):
        eta = xbeta + aa[a] + cc[c]
        if np.max(np.abs(eta)) > 300:
            raise ValueError("PPML numerical divergence before exponentiation")
        mu = np.exp(eta)
        amu = np.bincount(a, weights=mu, minlength=na)
        aa += np.log(ya / amu)
        eta = xbeta + aa[a] + cc[c]
        mu = np.exp(eta)
        cmu = np.bincount(c, weights=mu, minlength=nc)
        cc += np.log(yc / cmu)
        if itr % 10 == 0 or itr == 1:
            mu = np.exp(xbeta + aa[a] + cc[c])
            amu = np.bincount(a,weights=mu,minlength=na)
            cmu = np.bincount(c,weights=mu,minlength=nc)
            error = max(
                float((np.abs(amu-ya)/np.maximum(ya,1)).max()),
                float((np.abs(cmu-yc)/np.maximum(yc,1)).max()),
            )
            if error <= tolerance:
                return mu, aa, cc, {"fe_ipf_iterations":itr,"max_relative_FE_score":error}
    raise ValueError(f"PPML FE IPF did not converge in {max_iter} iterations (error={error:.3g})")


def fit_fe_ppml(
    frame: pd.DataFrame, outcome: str,
    *, max_outer: int = 35,
) -> dict[str, Any]:
    """IRLS/concentrated PPML, double-absorbed FE, country-robust covariance."""
    f, diag = _separation_prune(frame, outcome)
    cols = list(ARM_COLS)
    x = f[cols].to_numpy(dtype=float)
    y = f[outcome].to_numpy(dtype=float)
    au, ai = np.unique(f.geo_uid.to_numpy(), return_inverse=True)
    cu, ci = np.unique(f.country_period.to_numpy(), return_inverse=True)
    groups, country = np.unique(f.country_iso3.to_numpy(), return_inverse=True)
    na,nc,G = len(au),len(cu),len(groups)
    if G < 8:
        raise ValueError("too few independent country clusters after PPML pruning")
    b = np.zeros(3)
    aa = np.zeros(na)
    cc = np.zeros(nc)
    converged = False
    history = []
    for k in range(1,max_outer+1):
        mu,aa,cc,feinfo = _fit_ppml_inner_fe(x@b,y,ai,ci,na,nc,aa,cc)
        xt, sweeps, absorption = _weighted_group_residual(
            x,mu,ai,ci,na,nc,
        )
        info = xt.T@(mu[:,None]*xt)
        if np.linalg.matrix_rank(info) != 3:
            raise ValueError("PPML donor contrast not identified after weighted FE")
        score = xt.T@(y-mu)
        step = np.linalg.solve(info,score)
        max_step = float(np.abs(step).max())
        history.append({
            "outer": k, "maximum_beta_newton_step": max_step,
            "FE_ipf_iterations":feinfo["fe_ipf_iterations"],
            "weighted_absorption_sweeps":sweeps,
            "weighted_absorption_residual":absorption,
        })
        if max_step < 1e-7:
            converged = True
            break
        if max_step > 1.0:
            step *= 1.0/max_step
        b += step
        if np.max(np.abs(b)) > 15:
            raise ValueError("PPML donor coefficient divergence/perfect prediction")
    if not converged:
        raise ValueError(f"PPML did not converge within {max_outer} outer IRLS steps")
    # Scores use weighted-residualized X; IPF enforces nuisance scores ≈ 0.
    scores = np.column_stack([
        np.bincount(country,weights=xt[:,j]*(y-mu),minlength=G)
        for j in range(3)
    ])
    bread = np.linalg.inv(info)
    nuisance_rank = na+nc-G
    resid_df=len(f)-nuisance_rank-3
    if resid_df <= 0:
        raise ValueError("PPML covariance residual degrees of freedom not positive")
    correction = G/(G-1)*(len(f)-1)/resid_df
    covariance = correction*bread@(scores.T@scores)@bread
    covariance=(covariance+covariance.T)/2
    effects = _country_cluster_contrasts(
        b,covariance,G,outcome,"log_conditional_mean_ratio"
    )
    for row in effects:
        row["rate_ratio"] = float(np.exp(row["estimate"]))
        row["rate_ratio_ci95_lower"] = float(np.exp(row["ci95_lower"]))
        row["rate_ratio_ci95_upper"] = float(np.exp(row["ci95_upper"]))
    # Accuracy checks before writing an apparent result.
    area_score=np.bincount(ai,weights=y-mu,minlength=na)
    ct_score=np.bincount(ci,weights=y-mu,minlength=nc)
    if max(np.abs(area_score).max(),np.abs(ct_score).max()) > max(1e-6, y.sum()*2e-8):
        raise ValueError("PPML group score failed validation")
    return {
        "estimator":"PPML_FE_ADM2_country_period_country_CR1",
        "outcome":outcome, "status":"CONVERGED",
        "nobs":len(f), "n_countries":G,
        "n_areas":na,"n_country_periods":nc,
        "model_converged":converged,"outer_iterations":k,
        "unweighted_mean_y_original":float(frame[outcome].mean()),
        "mean_y_estimation_sample":float(y.mean()),
        "mean_fitted_mu_estimation_sample":float(mu.mean()),
        "fixed_effect_score_max_abs":float(max(np.abs(area_score).max(),np.abs(ct_score).max())),
        "cr1_factor":correction,
        "coefficients":dict(zip(ARM_COLS,[float(val) for val in b])),
        "contrasts":effects,"sample_separation":diag,
        "iterations":history,
        "interpretation":"conditional multiplicative mean association; not causal; estimation sample pruned for separation",
    }


def outcome_concentration_report(frame: pd.DataFrame) -> dict[str, Any]:
    """Independent descriptive outlier diagnostics, not model tuning."""
    deaths = frame.vac_fatalities_next.to_numpy(dtype=float)
    events = frame.vac_events_next.to_numpy(dtype=float)
    total_deaths = deaths.sum()
    by_country = frame.groupby("country_iso3").agg(
        fatalities=("vac_fatalities_next", "sum"),
        events=("vac_events_next", "sum"),
    ).sort_values("fatalities", ascending=False)
    if total_deaths <= 0 or not np.isfinite(total_deaths):
        raise ValueError("no valid fatalities for severity concentration")
    k = max(1, int(np.ceil(0.01 * len(deaths))))
    return {
        "total_recorded_vac_fatalities_next_period_across_area_period_cells": float(total_deaths),
        "total_vac_events_next_period": float(events.sum()),
        "positive_fatality_cells": int((deaths>0).sum()),
        "top_1pct_of_area_period_cells_fatality_share": float(np.sort(deaths)[-k:].sum()/total_deaths),
        "top_3_countries_fatality_share": float(by_country.fatalities.iloc[:3].sum()/total_deaths),
        "largest_cell_fatalities": float(np.max(deaths)),
        "top_5_fatality_countries": [
            {"country": str(country), "fatalities": float(row.fatalities),
             "share_of_total": float(row.fatalities/total_deaths)}
            for country,row in by_country.head(5).iterrows()
        ],
        "interpretation": "diagnostic for heavy tails; does not license excluding countries or choosing estimators post hoc",
    }


def run_e2(frame: pd.DataFrame) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    """Frozen E2: fatality levels plus VAC count/fatality PPML; record all outcomes."""
    fatality_ols=fit_balanced_fe_ols(frame,"vac_fatalities_next")
    models={"vac_fatalities_ols": fatality_ols}
    alerts=[]
    for outcome in ["vac_events_next","vac_fatalities_next"]:
        try:
            model=fit_fe_ppml(frame,outcome)
            models[f"{outcome}_ppml"]=model
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
            models[f"{outcome}_ppml"]={
                "status":"HOLD_CONVERGENCE_OR_SUPPORT","outcome":outcome,"reason":str(exc)
            }
            alerts.append(f"{outcome}: {exc}")
    effects=pd.DataFrame([
        {"model":name,**row} for name,model in models.items()
        for row in model.get("contrasts",[])
    ])
    result={
        "phase":"E2_SEVERITY_AND_FREQUENCY",
        "status":"COMPLETE" if not alerts else "PARTIAL_PPML_HOLD",
        "models":models,
        "outcome_concentration":outcome_concentration_report(frame),
        "alerts":alerts,
        "outcome_hierarchy":"secondary to E1 any VAC incidence; no retroactive primary switch",
        "limitations":[
            "fatalities are heavy-tailed; a few countries may dominate OLS",
            "PPML all-zero group separation can change estimand/sample",
            "country-cluster CR1 is not a substitute for causal identification",
            "count effects and linear-probability effects have different units",
        ],
    }
    return result,{"model_effects":effects}
