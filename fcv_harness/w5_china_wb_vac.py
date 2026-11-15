"""W5 source-comparable China/WB vs next-period VAC: governed E0 and E1.

This module never reuses the legacy-2023 ACLED-zero convention or calls
financing decisions randomized treatments. The source files are read-only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


ARM_COLS = ("china_only", "wb_only", "both")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema") != "fcv.w5.china_wb_vac.v1":
        raise ValueError("unsupported W5 schema")
    if spec["primary_outcome"] != "any_vac_next":
        raise ValueError("primary outcome is not the declared any_vac_next")
    if spec["main_fe"] != ["adm2", "country_x_financing_period"]:
        raise ValueError("unapproved main FE specification")
    if spec["inference"]["cluster"] != "country_iso3":
        raise ValueError("primary inference must cluster at country")
    return spec


def check_contracts(investment_contract: Path, acled_contract: Path) -> dict[str, Any]:
    inv = json.loads(investment_contract.read_text(encoding="utf-8"))
    ac = json.loads(acled_contract.read_text(encoding="utf-8"))
    if inv.get("authority") != "L3" or inv.get("absent_row_semantics") != "not_observed":
        raise ValueError("W4 investment source/absence contract mismatch")
    if ac.get("authority") != "L2" or ac.get("absent_row_semantics") != "zero_within_verified_coverage":
        raise ValueError("ACLED certified zero/coverage contract mismatch")
    if "ADM2" not in inv.get("observation_semantics", ""):
        # Source description need not be uppercase, but explicitly require scope.
        if "adm2" not in inv.get("geography_scope", ""):
            raise ValueError("source geography contract is not ADM2")
    if "provisional" not in ac.get("basis", "").lower():
        raise ValueError("ACLED coverage certification is not recognized")
    if ac.get("temporal_start", "") > "1999-01-01" or ac.get("temporal_end", "") < "2016-12-31":
        raise ValueError("ACLED coverage cannot contain all pre/post W5 periods")
    return {"investment": inv, "acled": ac}


def shift_period(s: str, increments: int) -> str:
    first, last = (int(v) for v in str(s).split("-"))
    if last != first + 1 or (first - 2001) % 2:
        raise ValueError(f"period misaligned with T2_y2001: {s}")
    return f"{first + increments * 2}-{last + increments * 2}"


def build_frame(investment: pd.DataFrame, acled: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Join native source observations without imputing project absences or ACLED outside scope."""
    ikey = ["geo_uid", "country_iso3", "period_id"]
    required_inv = ikey + [
        "cn_project_count", "wb_project_count", "cn_record_present", "wb_record_present",
        "cn_measurement_status", "wb_measurement_status",
    ]
    required_ac = ikey + [
        "native_event_type", "event_count", "fatalities", "record_present",
        "measurement_status", "fatalities_missing_event_count",
    ]
    for label, source, cols in [("investment", investment, required_inv), ("ACLED", acled, required_ac)]:
        missing = sorted(set(cols) - set(source))
        if missing:
            raise ValueError(f"{label} missing columns {missing}")
    if investment[ikey].isna().any().any() or investment.duplicated(ikey).any():
        raise ValueError("investment key missing or duplicated")
    if len(investment) != spec["expected_rows"]:
        raise ValueError(f"investment row count drift: {len(investment)}")
    if investment.geo_uid.nunique() != spec["expected_area_count"] or investment.country_iso3.nunique() != spec["expected_country_count"]:
        raise ValueError("investment geography/country count drift")
    periods = sorted(investment.period_id.unique().tolist())
    if len(periods) != spec["expected_period_count"] or periods[0] != spec["finance_period_start"] or periods[-1] != spec["finance_period_end"]:
        raise ValueError("investment period scope drift")
    if investment.groupby("geo_uid").period_id.nunique().ne(len(periods)).any():
        raise ValueError("balanced ADM2-period source lattice required by exact FE residualizer")
    if investment.groupby("geo_uid").country_iso3.nunique().gt(1).any():
        raise ValueError("ADM2 identifiers cross national boundaries")
    inv = investment[required_inv].copy()
    for prefix in ["cn", "wb"]:
        c = inv[f"{prefix}_project_count"]
        if c.isna().any() or not np.all(np.isfinite(c.to_numpy())) or (c < 0).any():
            raise ValueError(f"{prefix} project counts invalid")
        if not (c.gt(0) == inv[f"{prefix}_record_present"]).all():
            raise ValueError(f"{prefix} record_presence/count mismatch")
        if inv[f"{prefix}_measurement_status"].isna().any():
            raise ValueError(f"{prefix} measurement status missing")
    inv["china_only"] = (inv.cn_project_count.gt(0) & inv.wb_project_count.eq(0)).astype(int)
    inv["wb_only"] = (inv.wb_project_count.gt(0) & inv.cn_project_count.eq(0)).astype(int)
    inv["both"] = (inv.cn_project_count.gt(0) & inv.wb_project_count.gt(0)).astype(int)
    inv["neither_recorded"] = ((inv[list(ARM_COLS)].sum(axis=1)) == 0).astype(int)
    inv["next_period"] = inv.period_id.map(lambda p: shift_period(p, 1))
    inv["prior_period"] = inv.period_id.map(lambda p: shift_period(p, -1))

    vac = acled[acled.native_event_type.eq(spec["acled_event_type"])].copy()
    if vac.empty or vac.duplicated(ikey).any():
        raise ValueError("VAC outcome rows missing or duplicate")
    if vac[ikey].isna().any().any() or (vac[["event_count", "fatalities"]] < 0).any().any():
        raise ValueError("ACLED outcome key/count invalid")
    if vac[["event_count", "fatalities", "measurement_status"]].isna().any().any():
        raise ValueError("ACLED outcome unresolved: do not coerce missing to zero")
    if not vac.measurement_status.isin(["structural_zero", "aggregated_from_observed"]).all():
        raise ValueError("ACLED status is outside accepted certified semantics")
    if not (vac.record_present == vac.measurement_status.eq("aggregated_from_observed")).all():
        raise ValueError("ACLED observed/structural-zero status mismatch")
    if (vac.fatalities_missing_event_count != 0).any():
        raise ValueError("ACLED fatalities contain unknown values")

    n = inv.merge(
        vac[ikey + ["event_count", "fatalities", "measurement_status"]].rename(
            columns={"period_id": "next_period", "event_count": "vac_events_next",
                     "fatalities": "vac_fatalities_next", "measurement_status": "vac_status_next"}),
        on=["geo_uid", "country_iso3", "next_period"], how="left", validate="one_to_one", indicator="next_match",
    )
    n = n.merge(
        vac[ikey + ["event_count", "fatalities"]].rename(
            columns={"period_id": "prior_period", "event_count": "vac_events_prior", "fatalities": "vac_fatalities_prior"}),
        on=["geo_uid", "country_iso3", "prior_period"], how="left", validate="one_to_one", indicator="prior_match",
    )
    if len(n) != len(inv) or not n.next_match.eq("both").all() or not n.prior_match.eq("both").all():
        raise ValueError("incomplete certified ACLED pre/post join")
    n = n.drop(columns=["next_match", "prior_match"])
    if n[["vac_events_next", "vac_fatalities_next", "vac_events_prior", "vac_fatalities_prior"]].isna().any().any():
        raise ValueError("joined ACLED outcome includes missing values")
    n["any_vac_next"] = (n.vac_events_next > 0).astype(int)
    n["any_fatal_vac_next"] = (n.vac_fatalities_next > 0).astype(int)
    n["country_period"] = n.country_iso3.astype(str) + "|" + n.period_id.astype(str)
    return n.sort_values(ikey, kind="stable").reset_index(drop=True)


def residualize_balanced(frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Exact FWL: area FE and country-period FE for a balanced ADM2-country-period lattice."""
    if frame.groupby("geo_uid").period_id.nunique().nunique() != 1:
        raise ValueError("unbalanced geography/time would invalidate exact demeaning")
    v = frame[columns].astype(float)
    area = frame.groupby("geo_uid", sort=False)[columns].transform("mean")
    ct = frame.groupby("country_period", sort=False)[columns].transform("mean")
    country = frame.groupby("country_iso3", sort=False)[columns].transform("mean")
    out = (v - area - ct + country).to_numpy(dtype=float)
    if not np.all(np.isfinite(out)):
        raise ValueError("nonfinite residualized design/outcome")
    # Detect failure of exact nested/balanced construction rather than use approximate FE.
    for codes in [pd.factorize(frame.geo_uid)[0], pd.factorize(frame.country_period)[0]]:
        group_n = np.bincount(codes)
        max_mean = max((np.abs(np.bincount(codes, weights=out[:, j]) / group_n)).max()
                       for j in range(out.shape[1]))
        if max_mean > 1e-9:
            raise ValueError(f"FWL residuals are not orthogonal to FE (max={max_mean})")
    return out


def support_report(frame: pd.DataFrame, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    ct = frame.groupby(["country_iso3", "period_id"], observed=True)[list(ARM_COLS) + ["neither_recorded"]].sum().reset_index()
    c = frame.groupby("country_iso3", observed=True)[list(ARM_COLS) + ["neither_recorded"]].sum().reset_index()
    t = frame.groupby("period_id", observed=True)[list(ARM_COLS) + ["neither_recorded"]].sum().reset_index()
    both_available = (ct.china_only > 0) & (ct.wb_only > 0)
    countries_with = ct.loc[both_available, "country_iso3"].nunique()
    design = residualize_balanced(frame, list(ARM_COLS))
    norms = np.sqrt((design * design).sum(axis=0))
    svals = np.linalg.svd(design.T @ design, compute_uv=False)
    rank = int(np.linalg.matrix_rank(design.T @ design, tol=1e-7))
    summary = {
        "rows": int(len(frame)), "geographies": int(frame.geo_uid.nunique()),
        "countries": int(frame.country_iso3.nunique()), "periods": int(frame.period_id.nunique()),
        "source_arms": {key: int(frame[key].sum()) for key in [*ARM_COLS, "neither_recorded"]},
        "country_periods": int(len(ct)),
        "country_periods_both_exclusive_arms": int(both_available.sum()),
        "countries_with_contemporaneous_exclusive_comparison": int(countries_with),
        "residualized_arm_norms": {key: float(norms[j]) for j, key in enumerate(ARM_COLS)},
        "arm_design_rank": rank,
        "arm_normal_matrix_smallest_eigenvalue": float(svals.min()),
        "next_vac_incidence": float(frame.any_vac_next.mean()),
        "next_vac_fatality_incidence": float(frame.any_fatal_vac_next.mean()),
        "next_vac_mean_events": float(frame.vac_events_next.mean()),
        "next_vac_mean_fatalities": float(frame.vac_fatalities_next.mean()),
        "certified_structural_zero_rows": int(frame.vac_status_next.eq("structural_zero").sum()),
    }
    summary["e0_gate"] = (
        "PASS" if rank == 3 and countries_with >= spec["min_countries_with_same_period_both_exclusive_arms"]
        and int(both_available.sum()) >= spec["min_country_period_cells_with_both_exclusive_arms"]
        and min(norms) > 1e-8 else "HOLD"
    )
    return summary, {"country": c, "period": t, "country_period": ct}


def fit_primary_lpm(frame: pd.DataFrame) -> dict[str, Any]:
    """FWL linear probability model; CR1 country-cluster covariance, df=G-1."""
    transformed = residualize_balanced(frame, [*ARM_COLS, "any_vac_next"])
    x = transformed[:, :3]
    y = transformed[:, 3]
    rank = np.linalg.matrix_rank(x)
    if rank != 3:
        raise ValueError(f"nonidentified donor arm contrast after FE: rank={rank}")
    xtx = x.T @ x
    beta = np.linalg.solve(xtx, x.T @ y)
    error = y - x @ beta
    countries = frame.country_iso3.to_numpy()
    groups, codes = np.unique(countries, return_inverse=True)
    G = len(groups)
    n, k = x.shape
    narea = frame.geo_uid.nunique()
    n_ct = frame.country_period.nunique()
    ncountry = frame.country_iso3.nunique()
    nuisance_rank = narea + n_ct - ncountry  # nested ADM2 within country
    residual_df = n - nuisance_rank - k
    if G < 5 or residual_df <= 0:
        raise ValueError("too few country clusters or residual degrees of freedom")
    scores = np.zeros((G, k), dtype=float)
    for j in range(k):
        scores[:, j] = np.bincount(codes, weights=x[:, j] * error, minlength=G)
    bread = np.linalg.inv(xtx)
    correction = (G / (G - 1)) * ((n - 1) / residual_df)
    v = correction * bread @ (scores.T @ scores) @ bread
    v = (v + v.T) / 2
    if not np.all(np.isfinite(v)) or (np.diag(v) < 0).any():
        raise ValueError("nonfinite or negative cluster variance")

    def contrast(name: str, weights: list[float]) -> dict[str, Any]:
        z = np.asarray(weights, dtype=float)
        estimate = float(z @ beta)
        se = float(np.sqrt(z @ v @ z))
        stat = estimate / se if se > 0 else float("nan")
        p = float(2 * stats.t.sf(abs(stat), df=G - 1)) if np.isfinite(stat) else None
        critical = float(stats.t.ppf(0.975, df=G - 1))
        return {
            "contrast": name, "estimate_probability": estimate,
            "estimate_percentage_points": 100 * estimate, "se_probability": se,
            "ci95_probability_lower": estimate - critical * se,
            "ci95_probability_upper": estimate + critical * se,
            "ci95_percentage_points_lower": 100 * (estimate - critical * se),
            "ci95_percentage_points_upper": 100 * (estimate + critical * se),
            "t_stat": float(stat), "p_value_two_sided": p,
            "df_cluster": G - 1,
        }
    results = [
        contrast("china_only_vs_neither_recorded", [1, 0, 0]),
        contrast("wb_only_vs_neither_recorded", [0, 1, 0]),
        contrast("both_vs_neither_recorded", [0, 0, 1]),
        contrast("china_only_minus_wb_only_PRIMARY", [1, -1, 0]),
    ]
    return {
        "model": "balanced_nested_ADM2_FE_and_country_x_finance_period_FE_LPM",
        "role": "E1_PRIMARY_OBSERVATIONAL_ASSOCIATION",
        "outcome": "any_vac_next",
        "exposure_reference": "neither_source_recorded_this_period_not_never_treated",
        "country_cluster_CR1_multiplier": float(correction),
        "country_clusters": G, "nominal_cluster_df": G - 1,
        "nobs": n, "effective_parameters_within": k,
        "absorbed_nuisance_rank": int(nuisance_rank),
        "residual_df": int(residual_df),
        "betas": {name: float(val) for name, val in zip(ARM_COLS, beta)},
        "cluster_covariance": v.tolist(),
        "results": results,
        "claim": "adjusted observational donor-source contrast; no causal impact identified",
    }


def run_w5(
    spec_path: Path, investment_path: Path, acled_path: Path,
    investment_contract_path: Path, acled_contract_path: Path,
    out_dir: Path, phase: str = "e0",
) -> dict[str, Any]:
    if phase not in {"e0", "e1"}:
        raise ValueError("W5 phase only e0 or e1")
    spec = read_spec(spec_path)
    inhash = sha256_file(investment_path)
    achash = sha256_file(acled_path)
    if inhash != spec["investment_sha256"] or achash != spec["acled_sha256"]:
        raise ValueError(f"source hash lock mismatch; got investment={inhash} acled={achash}")
    contracts = check_contracts(investment_contract_path, acled_contract_path)
    inv = pd.read_parquet(investment_path)
    ac = pd.read_parquet(acled_path)
    frame = build_frame(inv, ac, spec)
    support, tables = support_report(frame, spec)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_path = out_dir / "w5_analysis_frame.parquet"
    frame.to_parquet(frame_path, index=False)
    with (out_dir / "e0_preflight.json").open("w", encoding="utf-8") as fh:
        json.dump(support, fh, indent=2, sort_keys=True)
        fh.write("\n")
    for name, table in tables.items():
        table.to_csv(out_dir / f"e0_support_by_{name}.csv", index=False)
    report = {
        "schema": spec["schema"], "phase": phase, "source_spec": str(spec_path),
        "purpose": spec["purpose"], "project_context": "PL-015 / RP-008 / RP-009",
        "source_identifiers": {"investment": spec["investment_dataset_id"], "acled": spec["acled_dataset_id"]},
        "input_sha256": {"investment": inhash, "acled_certified": achash},
        "contract_sha256": {
            "investment": sha256_file(investment_contract_path),
            "acled": sha256_file(acled_contract_path),
        },
        "contract_authorities": {
            "investment": contracts["investment"]["authority"],
            "acled": contracts["acled"]["authority"],
            "acled_source_certification": "operator_accepted_provisional_historical_completeness",
        },
        "spec_sha256": sha256_file(spec_path),
        "analysis_frame_sha256": sha256_file(frame_path),
        "e0": support,
        "e1": None,
        "excluded_outcome_missing": 0,
        "source_inputs_unchanged": True,
    }
    if phase == "e1":
        if support["e0_gate"] != "PASS":
            raise ValueError("E0 HOLD: primary E1 fitting not authorized")
        model = fit_primary_lpm(frame)
        report["e1"] = model
        pd.DataFrame(model["results"]).to_csv(out_dir / "e1_effects.csv", index=False)
        with (out_dir / "e1_primary.json").open("w", encoding="utf-8") as fh:
            json.dump(model, fh, indent=2, sort_keys=True)
            fh.write("\n")
        main = model["results"][-1]
        interpretation = "not identified as a causal donor effect"
        body = [
            "# W5 E1 primary: China-only minus WB-only next-period VAC",
            "",
            f"Status: exploratory, **observational**; {interpretation}.",
            f"Source observations: {model['nobs']:,}; ADM2: {support['geographies']:,}; country clusters: {model['country_clusters']}.",
            f"E0 gate: **{support['e0_gate']}**. Same-country same-period comparison cells: {support['country_periods_both_exclusive_arms']}.",
            "",
            "Model: LPM with ADM2 and country × financing-biennium fixed effects. Country-cluster CR1, t(G−1).",
            "",
            f"**CN-only − WB-only: {main['estimate_percentage_points']:+.3f} percentage points**",
            f"95% CI [{main['ci95_percentage_points_lower']:+.3f}, {main['ci95_percentage_points_upper']:+.3f}] pp; two-sided p={main['p_value_two_sided']:.4g}.",
            "",
            "Primary outcome: any ACLED VAC event during the following biennium; baseline observed incidence",
            f"{100 * support['next_vac_incidence']:.2f}% (unadjusted).",
            "",
            "Legacy 2023 China/WB and current China-only E2 coefficients use different panels/estimands and are not this result.",
            "This regression does not account for unobserved time-varying project targeting, anticipation, financial",
            "implementation clocks, spatial interference or pre-trend validity. E2–E4 remain unrun.",
            "Neither donor recorded is not a verified no-development-finance control group.",
        ]
        (out_dir / "e1_report.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    (out_dir / "run_receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
