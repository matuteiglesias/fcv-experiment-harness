from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


LEGACY_TREATMENTS = ("cnwb_pooled", "wb_only", "cn_only")


@dataclass
class PanelExperimentSpec:
    experiment_id: str
    outcome: str
    treatment_type: str = "cnwb_pooled"
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    period_order_col: Optional[str] = "Period"
    country_col: Optional[str] = "ISO"
    wb_amount_col: str = "wbad_amount_usd"
    cn_amount_col: str = "cn_amount_usd"
    covariates: List[str] = field(default_factory=list)
    include_pre_outcome: bool = True
    require_declared_covariates: bool = True

    min_treated: int = 30
    min_control: int = 30
    max_outcome_missing_share: float = 0.10
    max_zero_share: float = 0.95
    max_abs_pre_smd: float = 0.25

    plausible_effect_sd: float = 0.20
    power_target: float = 0.80
    bootstrap_draws: int = 200
    seed: int = 20260817

    @classmethod
    def from_json(cls, path):
        import json
        with open(path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))



def merge_panel_outcomes(
    panel: pd.DataFrame,
    outcomes: pd.DataFrame,
    outcome_col: str,
    unit_col: str = "GID",
    period_col: str = "TimePeriod",
):
    """
    Strictly attach an outcome table to the treatment/covariate panel.

    This mirrors the recovered 2023 architecture, where `_DHSGC.csv` treatment/covariate
    panels and `{region}{level}_T{T}{y0}.csv` outcome files were read separately and aligned
    on GID × TimePeriod.

    Returns (merged, audit).
    """
    key = [unit_col, period_col]

    missing_panel = [c for c in key if c not in panel.columns]
    missing_out = [c for c in key + [outcome_col] if c not in outcomes.columns]
    if missing_panel:
        raise KeyError(f"Panel missing merge keys: {missing_panel}")
    if missing_out:
        raise KeyError(f"Outcome table missing fields: {missing_out}")

    pdup = int(panel.duplicated(key).sum())
    odup = int(outcomes.duplicated(key).sum())
    if pdup:
        raise ValueError(f"Panel has {pdup} duplicate GID×TimePeriod rows.")
    if odup:
        raise ValueError(f"Outcome table has {odup} duplicate GID×TimePeriod rows.")

    o = outcomes[key + [outcome_col]].copy()
    o["_outcome_row_present"] = True

    merged = panel.merge(
        o,
        on=key,
        how="left",
        validate="one_to_one",
        indicator="_outcome_merge",
    )

    audit = {
        "panel_rows": int(len(panel)),
        "outcome_rows": int(len(outcomes)),
        "matched_rows": int((merged["_outcome_merge"] == "both").sum()),
        "panel_rows_without_outcome_record": int((merged["_outcome_merge"] == "left_only").sum()),
        "matched_share": float((merged["_outcome_merge"] == "both").mean()) if len(merged) else 0.0,
        "outcome_value_missing_share_on_matched": float(
            merged.loc[merged["_outcome_merge"] == "both", outcome_col].isna().mean()
        ) if (merged["_outcome_merge"] == "both").any() else 1.0,
    }

    merged = merged.drop(columns=["_outcome_row_present"])
    return merged, audit

def derive_legacy_treatment(
    df: pd.DataFrame,
    treatment_type: str,
    wb_amount_col: str = "wbad_amount_usd",
    cn_amount_col: str = "cn_amount_usd",
) -> pd.Series:
    """
    Reconstructs the source-family treatment logic visible in the recovered 2023 matching code.
    Missing investment amounts are treated as zero only after the input columns exist.
    """
    if treatment_type not in LEGACY_TREATMENTS:
        raise ValueError(f"Unsupported legacy treatment: {treatment_type}")

    missing = [c for c in (wb_amount_col, cn_amount_col) if c not in df.columns]
    if missing:
        raise KeyError(f"Missing treatment source columns: {missing}")

    wb = pd.to_numeric(df[wb_amount_col], errors="coerce").fillna(0.0)
    cn = pd.to_numeric(df[cn_amount_col], errors="coerce").fillna(0.0)

    if treatment_type == "cnwb_pooled":
        return ((wb + cn) > 0).astype(int)
    if treatment_type == "wb_only":
        return ((wb > 0) & (cn <= 0)).astype(int)
    return ((cn > 0) & (wb <= 0)).astype(int)


def _period_sort_values(df: pd.DataFrame, spec: PanelExperimentSpec):
    if spec.period_order_col and spec.period_order_col in df.columns:
        return pd.to_numeric(df[spec.period_order_col], errors="coerce")

    # Fall back to the first four-digit year in TimePeriod-like labels.
    s = df[spec.period_col].astype(str)
    extracted = pd.to_numeric(s.str.extract(r"(\d{4})", expand=False), errors="coerce")
    if extracted.notna().any():
        return extracted

    # Last-resort stable category order.
    cats = {v: i for i, v in enumerate(pd.unique(s))}
    return s.map(cats).astype(float)


def build_panel_analysis_frame(df: pd.DataFrame, spec: PanelExperimentSpec) -> pd.DataFrame:
    required = {spec.unit_col, spec.period_col, spec.outcome, spec.wb_amount_col, spec.cn_amount_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise KeyError(f"Missing required panel columns: {missing}")

    missing_covariates = [c for c in spec.covariates if c not in df.columns]
    if spec.require_declared_covariates and missing_covariates:
        raise KeyError(f"Declared covariates missing from panel: {missing_covariates}")

    out = df.copy()
    out["_period_order"] = _period_sort_values(out, spec)
    out = out.sort_values([spec.unit_col, "_period_order"]).reset_index(drop=True)

    out["treatment"] = derive_legacy_treatment(
        out, spec.treatment_type, spec.wb_amount_col, spec.cn_amount_col
    )

    # Treatment is defined in t. Outcome is explicitly moved to t+1.
    g = out.groupby(spec.unit_col, sort=False)
    out["outcome_post"] = g[spec.outcome].shift(-1)
    out["outcome_pre"] = g[spec.outcome].shift(1)

    # Keep timing provenance explicit.
    out["outcome_post_period"] = g[spec.period_col].shift(-1)
    out["outcome_pre_period"] = g[spec.period_col].shift(1)

    return out


def standardized_mean_difference(a, b):
    a = pd.Series(a).dropna().astype(float)
    b = pd.Series(b).dropna().astype(float)
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def panel_baseline_estimate(frame: pd.DataFrame, spec: PanelExperimentSpec, outcome_col="outcome_post"):
    """
    Deliberately simple calibration estimator.

    Y_{g,t+1} ~ treatment_{g,t} + pre-outcome + declared covariates + period FE + country FE
    with SE clustered at GID.

    This is NOT the final staggered-adoption estimator.
    """
    sample = frame.dropna(subset=[outcome_col, "treatment"]).copy()

    rhs = ["treatment"]
    model_cols = [outcome_col, "treatment", spec.unit_col, spec.period_col]

    if spec.include_pre_outcome and "outcome_pre" in sample.columns:
        rhs.append("outcome_pre")
        model_cols.append("outcome_pre")

    covars = [c for c in spec.covariates if c in sample.columns]
    rhs.extend(covars)
    model_cols.extend(covars)

    rhs.append(f"C({spec.period_col})")
    if spec.country_col and spec.country_col in sample.columns:
        rhs.append(f"C({spec.country_col})")
        model_cols.append(spec.country_col)

    # Patsy/statsmodels silently drops NA rows from the design matrix.
    # Drop them ourselves so clustered groups stay exactly aligned with model rows.
    sample = sample.dropna(subset=list(dict.fromkeys(model_cols))).copy()

    if sample["treatment"].nunique() < 2:
        return {"ok": False, "reason": "Treatment has no variation after model-complete-case filtering."}

    formula = f"{outcome_col} ~ " + " + ".join(rhs)
    fit = smf.ols(formula, data=sample).fit(
        cov_type="cluster",
        cov_kwds={"groups": sample[spec.unit_col].to_numpy()},
    )

    return {
        "ok": True,
        "effect": float(fit.params["treatment"]),
        "se": float(fit.bse["treatment"]),
        "z": float(fit.params["treatment"] / fit.bse["treatment"]),
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "n_treated": int(sample["treatment"].sum()),
        "n_control": int((1 - sample["treatment"]).sum()),
        "formula": formula,
    }


def profile_panel(df: pd.DataFrame, spec: PanelExperimentSpec) -> pd.DataFrame:
    """
    Compact data dictionary/profile so an old reg_data CSV can be inspected before choosing
    outcomes/covariates. No silent semantic classification.
    """
    rows = []
    for c in df.columns:
        s = df[c]
        numeric = pd.api.types.is_numeric_dtype(s)
        rows.append({
            "column": c,
            "dtype": str(s.dtype),
            "n": int(len(s)),
            "n_nonmissing": int(s.notna().sum()),
            "missing_share": float(s.isna().mean()),
            "n_unique": int(s.nunique(dropna=True)),
            "numeric": bool(numeric),
            "mean": float(pd.to_numeric(s, errors="coerce").mean()) if numeric else np.nan,
            "zero_share": float((pd.to_numeric(s, errors="coerce") == 0).mean()) if numeric else np.nan,
        })
    return pd.DataFrame(rows)


def _bootstrap_signal_recovery(frame: pd.DataFrame, spec: PanelExperimentSpec):
    base = frame.dropna(subset=["outcome_post"]).copy()
    units = base[spec.unit_col].dropna().unique()
    if len(units) < 20 or base["treatment"].nunique() < 2:
        return np.nan

    sd = float(base["outcome_post"].std(ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return np.nan
    injected = spec.plausible_effect_sd * sd

    rng = np.random.default_rng(spec.seed)
    successes = 0
    attempted = 0

    for _ in range(spec.bootstrap_draws):
        sampled = rng.choice(units, size=len(units), replace=True)
        pieces = []
        for j, uid in enumerate(sampled):
            p = base.loc[base[spec.unit_col] == uid].copy()
            # Bootstrap-cluster relabel, preserving original covariates.
            p[spec.unit_col] = f"boot_{j}"
            pieces.append(p)
        boot = pd.concat(pieces, ignore_index=True)

        boot["_synthetic_post"] = (
            boot["outcome_post"].astype(float)
            + injected * boot["treatment"].astype(float)
        )
        est = panel_baseline_estimate(boot, spec, outcome_col="_synthetic_post")
        if not est.get("ok"):
            continue
        attempted += 1
        sign_ok = np.sign(est["effect"]) == np.sign(injected)
        detected = np.isfinite(est["z"]) and abs(est["z"]) >= 1.96
        successes += int(sign_ok and detected)

    return successes / attempted if attempted else np.nan


def run_panel_gates(df: pd.DataFrame, spec: PanelExperimentSpec):
    """
    Traffic-light gates for the recovered FCV GID × TimePeriod lane.
    """
    results = []

    def add(gate, status, metric, value, threshold, note):
        results.append({
            "gate": gate, "status": status, "metric": metric,
            "value": value, "threshold": threshold, "note": note
        })

    required = {
        spec.unit_col, spec.period_col, spec.outcome,
        spec.wb_amount_col, spec.cn_amount_col
    }
    if spec.require_declared_covariates:
        required.update(spec.covariates)
    missing = sorted(required - set(df.columns))
    dup = (
        int(df.duplicated([spec.unit_col, spec.period_col]).sum())
        if not missing else -1
    )
    g1 = (not missing) and dup == 0
    add("P1_PANEL_INTEGRITY", "GREEN" if g1 else "RED",
        "missing required / duplicate unit-period", f"{missing} / {dup}", "none / 0",
        "The area-period panel must be unique before any treatment/outcome shifting.")
    if not g1:
        return pd.DataFrame(results), None

    frame = build_panel_analysis_frame(df, spec)

    # Post-outcome coverage after the explicit t -> t+1 shift.
    miss = float(frame["outcome_post"].isna().mean())
    add("P2_POST_OUTCOME_COVERAGE",
        "GREEN" if miss <= spec.max_outcome_missing_share else ("YELLOW" if miss <= 0.30 else "RED"),
        "missing share outcome(t+1)", round(miss, 4),
        f"green <= {spec.max_outcome_missing_share:.2f}",
        "Edge periods necessarily disappear; additional missingness is measurement loss.")

    valid = frame.dropna(subset=["outcome_post"]).copy()
    nt = int(valid["treatment"].sum())
    nc = int((1 - valid["treatment"]).sum())
    add("P3_TREATMENT_SUPPORT",
        "GREEN" if nt >= spec.min_treated and nc >= spec.min_control else
        ("YELLOW" if nt >= 10 and nc >= 10 else "RED"),
        "treated / control rows", f"{nt} / {nc}",
        f"green >= {spec.min_treated} / {spec.min_control}",
        "This is the usable t -> t+1 sample, not the raw panel row count.")

    # Treatment support by period; catches designs carried by a single time slice.
    byp = valid.groupby(spec.period_col)["treatment"].agg(["sum", "count"])
    byp["control"] = byp["count"] - byp["sum"]
    usable_periods = int(((byp["sum"] > 0) & (byp["control"] > 0)).sum())
    total_periods = int(len(byp))
    add("P3B_WITHIN_PERIOD_SUPPORT",
        "GREEN" if usable_periods >= max(2, total_periods - 1) else
        ("YELLOW" if usable_periods >= 2 else "RED"),
        "periods with treated + control", f"{usable_periods}/{total_periods}",
        "green: >=2 and nearly all periods",
        "The old matching design operates within time periods; pooled N can hide absent overlap.")

    # Sparsity/noise floor of the outcome.
    y = pd.to_numeric(valid["outcome_post"], errors="coerce")
    zero_share = float((y == 0).mean())
    add("P4_OUTCOME_SPARSITY",
        "GREEN" if zero_share <= spec.max_zero_share else
        ("YELLOW" if zero_share <= 0.99 else "RED"),
        "zero share outcome(t+1)", round(zero_share, 4),
        f"green <= {spec.max_zero_share:.2f}",
        "A highly sparse conflict outcome may require a binary/count/hurdle definition rather than OLS.")

    # Pre-treatment balance: outcome(t-1) + declared covariates.
    smds = {}
    for c in ["outcome_pre"] + [x for x in spec.covariates if x in valid.columns]:
        smds[c] = standardized_mean_difference(
            valid.loc[valid.treatment == 1, c],
            valid.loc[valid.treatment == 0, c],
        )
    finite = [abs(v) for v in smds.values() if np.isfinite(v)]
    worst = max(finite) if finite else np.nan
    status = (
        "YELLOW" if np.isnan(worst) else
        ("GREEN" if worst <= spec.max_abs_pre_smd else
         ("YELLOW" if worst <= 2 * spec.max_abs_pre_smd else "RED"))
    )
    add("P5_PRETREATMENT_BALANCE", status,
        "max |SMD| treated vs control", None if np.isnan(worst) else round(worst, 4),
        f"green <= {spec.max_abs_pre_smd:.2f}",
        f"Components: { {k: None if not np.isfinite(v) else round(v,3) for k,v in smds.items()} }")

    # Placebo: treatment(t) should not "explain" outcome(t-1) after basic adjustment.
    placebo = valid.dropna(subset=["outcome_pre"]).copy()
    if len(placebo) and placebo["treatment"].nunique() == 2:
        pl = panel_baseline_estimate(placebo, spec, outcome_col="outcome_pre")
        pe = abs(pl.get("effect", np.nan)) if pl.get("ok") else np.nan
        ysd = float(placebo["outcome_pre"].std(ddof=1))
        std_pe = pe / ysd if np.isfinite(pe) and ysd > 0 else np.nan
        add("P6_PRE_OUTCOME_PLACEBO",
            "YELLOW" if np.isnan(std_pe) else
            ("GREEN" if std_pe <= 0.10 else ("YELLOW" if std_pe <= 0.25 else "RED")),
            "|placebo effect| / SD(pre-outcome)",
            None if np.isnan(std_pe) else round(std_pe, 4),
            "green <= 0.10",
            "A strong treatment association with the previous-period outcome flags selection/pre-trends.")
    else:
        add("P6_PRE_OUTCOME_PLACEBO", "RED", "usable placebo sample", len(placebo),
            "two treatment groups",
            "The design cannot run a basic pre-outcome falsification.")

    power = _bootstrap_signal_recovery(frame, spec)
    add("P7_SYNTHETIC_SIGNAL_RECOVERY",
        "RED" if np.isnan(power) else
        ("GREEN" if power >= spec.power_target else ("YELLOW" if power >= 0.50 else "RED")),
        "cluster-bootstrap detection probability",
        None if np.isnan(power) else round(float(power), 3),
        f"green >= {spec.power_target:.2f}",
        f"Injects {spec.plausible_effect_sd:.2f} SD into treated post outcomes. Calibration, not evidence.")

    return pd.DataFrame(results), frame


def render_panel_report(gates: pd.DataFrame, spec: PanelExperimentSpec):
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
    lines = [
        f"# Panel Gate Report — {spec.experiment_id}",
        "",
        f"Treatment: `{spec.treatment_type}`  ",
        f"Outcome source column: `{spec.outcome}`  ",
        f"Temporal estimand in this v0: treatment at **t** → outcome at **t+1**.",
        "",
        "| Gate | Status | Metric | Value | Threshold |",
        "|---|---:|---|---:|---|",
    ]
    for _, r in gates.iterrows():
        lines.append(
            f"| `{r.gate}` | {icon.get(r.status,'')} {r.status} | {r.metric} | {r.value} | {r.threshold} |"
        )
    lines += ["", "## Notes", ""]
    for _, r in gates.iterrows():
        lines += [f"### {icon.get(r.status,'')} {r.gate}", str(r.note), ""]
    return "\n".join(lines)
