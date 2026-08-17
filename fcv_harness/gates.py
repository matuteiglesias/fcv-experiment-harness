from dataclasses import dataclass
import numpy as np
import pandas as pd
from .core import build_exposure_state, add_project_state
from .estimate import spatial_did, bandwidth_sweep

@dataclass
class GateResult:
    gate: str
    status: str
    metric: str
    value: object
    threshold: str
    note: str

def _status(green, yellow=True):
    if green:
        return "GREEN"
    return "YELLOW" if yellow else "RED"

def standardized_mean_difference(a, b):
    a = pd.Series(a).dropna()
    b = pd.Series(b).dropna()
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return 0.0 if pooled == 0 else float((a.mean() - b.mean()) / pooled)

def total_variation_from_counts(a, b):
    cats = sorted(set(a.index).union(set(b.index)))
    pa = a.reindex(cats, fill_value=0).astype(float)
    pb = b.reindex(cats, fill_value=0).astype(float)
    if pa.sum() == 0 or pb.sum() == 0:
        return np.nan
    pa, pb = pa / pa.sum(), pb / pb.sum()
    return float(0.5 * np.abs(pa - pb).sum())

def _cluster_bootstrap_power(df, spec):
    base = df[df.exposure_state.isin(["completed", "planned", "never"])].copy()
    if base.empty or base.exposure_state.nunique() < 3:
        return np.nan
    clusters = base["cluster_id"].dropna().unique()
    if len(clusters) < 10:
        return np.nan

    rng = np.random.default_rng(spec.seed)
    success, attempted = 0, 0
    for _ in range(spec.bootstrap_draws):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        parts = []
        for j, cid in enumerate(sampled):
            p = base.loc[base.cluster_id == cid].copy()
            p["cluster_id"] = f"boot_{j}"
            parts.append(p)
        boot = pd.concat(parts, ignore_index=True)
        boot["_synthetic_outcome"] = (
            boot[spec.outcome].astype(float)
            + np.where(boot.exposure_state.eq("completed"), spec.plausible_effect, 0.0)
        )
        est = spatial_did(boot, "_synthetic_outcome", spec.covariates, spec.fixed_effects)
        if not est.get("ok"):
            continue
        attempted += 1
        correct_sign = np.sign(est["effect_completed_minus_planned"]) == np.sign(spec.plausible_effect)
        detected = np.isfinite(est["z"]) and abs(est["z"]) >= 1.96
        success += int(correct_sign and detected)
    return success / attempted if attempted else np.nan

def run_gates(observations, projects, links, spec):
    results = []

    # G1: canonical integrity
    required_obs = {"obs_id", "cluster_id", "obs_year", spec.outcome}
    required_proj = {"project_id", "agreement_year"}
    required_links = {"obs_id", "project_id", "distance_km"}
    missing = (
        sorted(required_obs - set(observations.columns))
        + sorted(required_proj - set(projects.columns))
        + sorted(required_links - set(links.columns))
    )
    dup_obs = int(observations["obs_id"].duplicated().sum()) if "obs_id" in observations else -1
    good = (not missing) and dup_obs == 0
    results.append(GateResult(
        "G1_DATA_INTEGRITY", "GREEN" if good else "RED",
        "missing required / duplicate obs", f"{missing} / {dup_obs}", "none / 0",
        "Canonical objects must be structurally valid before experiment construction."
    ))
    if not good:
        return results

    linked = add_project_state(links, projects, observations)
    df = build_exposure_state(observations, projects, links, spec.radius_km)

    # G2: status timing resolvability
    exposed = df[df.n_near_projects > 0]
    ambig_share = float((exposed.exposure_state == "ambiguous").mean()) if len(exposed) else 1.0
    results.append(GateResult(
        "G2_TIMING_RESOLUTION",
        _status(ambig_share <= spec.max_ambiguous_share, ambig_share <= 2 * spec.max_ambiguous_share),
        "ambiguous exposed share", round(ambig_share, 4),
        f"green <= {spec.max_ambiguous_share:.2f}",
        "Agreement/start/end timing must resolve status at the observation date."
    ))

    # G2b: geocoding precision must be compatible with claimed radius
    if "geo_precision_km" in linked.columns:
        near = linked[linked.distance_km <= spec.radius_km].copy()
        bad = near["geo_precision_km"].astype(float) > float(spec.radius_km)
        bad_share = float(bad.mean()) if len(near) else 1.0
        results.append(GateResult(
            "G2B_SPATIAL_PRECISION",
            _status(bad_share <= 0.05, bad_share <= 0.20),
            "share near links coarser than radius", round(bad_share, 4),
            "green <= 0.05",
            "A computed short distance is not credible when the underlying location uncertainty exceeds the exposure radius."
        ))

    # G3: identifying support
    counts = df.exposure_state.value_counts().to_dict()
    nc, np_ = int(counts.get("completed", 0)), int(counts.get("planned", 0))
    green = nc >= spec.min_completed and np_ >= spec.min_planned
    yellow = nc >= max(10, spec.min_completed // 2) and np_ >= max(10, spec.min_planned // 2)
    results.append(GateResult(
        "G3_IDENTIFYING_SUPPORT", _status(green, yellow),
        "completed / planned", f"{nc} / {np_}",
        f"green >= {spec.min_completed} / {spec.min_planned}",
        "These groups carry the completed-vs-planned identifying contrast."
    ))

    # G3b: fixed-effect strata with actual identifying variation
    if spec.fixed_effects and all(c in df.columns for c in spec.fixed_effects):
        tab = (
            df[df.exposure_state.isin(["completed", "planned"])]
            .groupby(spec.fixed_effects)["exposure_state"]
            .nunique()
        )
        identifying = int((tab >= 2).sum())
        total = int(len(tab))
        share = identifying / total if total else 0.0
        results.append(GateResult(
            "G3B_WITHIN_STRATUM_SUPPORT",
            _status(share >= 0.50, share >= 0.25),
            "FE strata containing completed + planned", f"{identifying}/{total} ({share:.2f})",
            "green share >= 0.50",
            "Briggs shows that tighter FE can improve comparability while eliminating most identifying variation."
        ))

    # G3c: multiple/mixed exposure is visible
    mixed = (
        (df.n_completed_projects > 0).astype(int)
        + (df.n_planned_projects > 0).astype(int)
        + (df.n_active_projects > 0).astype(int)
    ) >= 2
    mixed_share = float(mixed.mean())
    results.append(GateResult(
        "G3C_EXPOSURE_COLLISIONS",
        _status(mixed_share <= 0.10, mixed_share <= 0.30),
        "share observations near multiple temporal states", round(mixed_share, 4),
        "green <= 0.10",
        "A priority rule is only a convenience. Mixed exposure should trigger explicit experiment decisions, not silent collapsing."
    ))

    # G4: planned vs never selection diagnostic
    smds = {}
    for c in [spec.pre_outcome] + list(spec.covariates):
        if c and c in df.columns:
            smds[c] = standardized_mean_difference(
                df.loc[df.exposure_state == "planned", c],
                df.loc[df.exposure_state == "never", c],
            )
    finite = [abs(v) for v in smds.values() if np.isfinite(v)]
    worst = max(finite) if finite else np.nan
    status = "YELLOW" if np.isnan(worst) else _status(worst <= spec.max_abs_pre_smd, worst <= 2 * spec.max_abs_pre_smd)
    results.append(GateResult(
        "G4_SELECTION_DIAGNOSTIC", status,
        "max |SMD| planned vs never", None if np.isnan(worst) else round(worst, 4),
        f"green <= {spec.max_abs_pre_smd:.2f}",
        f"Component SMDs: { {k: None if not np.isfinite(v) else round(v,3) for k,v in smds.items()} }"
    ))

    # G4b: planned/completed composition, Blair Appendix D analogue
    if "sector" in projects.columns:
        near = linked[linked.distance_km <= spec.radius_km]
        comp = near[near.project_state_at_obs == "completed"].drop_duplicates("project_id")["sector"].value_counts()
        plan = near[near.project_state_at_obs == "planned"].drop_duplicates("project_id")["sector"].value_counts()
        tv = total_variation_from_counts(comp, plan)
        tv_status = "YELLOW" if np.isnan(tv) else _status(tv <= 0.20, tv <= 0.35)
        results.append(GateResult(
            "G4B_PLANNED_COMPLETED_COMPOSITION",
            tv_status, "sector distribution total-variation distance",
            None if np.isnan(tv) else round(tv, 4),
            "green <= 0.20",
            "A direct analogue of Blair's planned-vs-completed sector-composition check."
        ))

    # G5: placebo on pre-treatment outcome
    if spec.pre_outcome and spec.pre_outcome in df.columns:
        placebo = spatial_did(df, spec.pre_outcome, spec.covariates, spec.fixed_effects)
        pe = abs(placebo.get("effect_completed_minus_planned", np.nan)) if placebo.get("ok") else np.nan
        pstatus = "YELLOW" if np.isnan(pe) else _status(pe <= spec.placebo_max_abs_effect, pe <= 2 * spec.placebo_max_abs_effect)
        results.append(GateResult(
            "G5_PRE_OUTCOME_PLACEBO", pstatus,
            "|completed-planned| on pre-outcome",
            None if np.isnan(pe) else round(pe, 4),
            f"green <= {spec.placebo_max_abs_effect:.2f}",
            "A large pre-treatment 'effect' warns about timing, selection, or model structure."
        ))

    # G6: bandwidth robustness
    bw = bandwidth_sweep(observations, projects, links, spec)
    usable = bw[bw["ok"] == True] if "ok" in bw.columns else pd.DataFrame()
    if len(usable) >= 3:
        effects = usable["effect_completed_minus_planned"].astype(float)
        same_sign = max((effects > 0).mean(), (effects < 0).mean())
        results.append(GateResult(
            "G6_BANDWIDTH_ROBUSTNESS",
            _status(same_sign >= 0.8, same_sign >= 0.6),
            "dominant-sign share across radii", round(float(same_sign), 3),
            "green >= 0.80",
            "Radius changes the identifying sample; interpret this as robustness, not automatic dose-response evidence."
        ))
    else:
        results.append(GateResult(
            "G6_BANDWIDTH_ROBUSTNESS", "RED", "usable bandwidths", len(usable), ">= 3",
            "Too little identifying variation survives across the radius grid."
        ))

    # G7: synthetic signal recovery / empirical sensitivity
    power = _cluster_bootstrap_power(df, spec)
    pstatus = "RED" if np.isnan(power) else _status(power >= spec.power_target, power >= 0.50)
    results.append(GateResult(
        "G7_SYNTHETIC_SIGNAL_RECOVERY", pstatus,
        "bootstrap detection probability",
        None if np.isnan(power) else round(float(power), 3),
        f"green >= {spec.power_target:.2f}",
        f"Injected effect = {spec.plausible_effect}. Calibration only; not substantive evidence."
    ))

    return results

def render_gate_report(results, title="FCV Experiment Gate Report"):
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
    lines = [f"# {title}", "", "| Gate | Status | Metric | Value | Threshold |", "|---|---:|---|---:|---|"]
    for r in results:
        lines.append(f"| `{r.gate}` | {icon.get(r.status,'')} {r.status} | {r.metric} | {r.value} | {r.threshold} |")
    lines += ["", "## Notes", ""]
    for r in results:
        lines += [f"### {icon.get(r.status,'')} {r.gate}", r.note, ""]
    return "\n".join(lines)
