from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .analysis_surface import AnalysisSurfaceSpec
from .canonical import _period_start
from .canonical_experiment import (
    CanonicalPanelExperimentSpec,
    EligibilitySpec,
    OutcomeMeasurementSpec,
    TreatmentMeasurementSpec,
    run_experiment_preflight,
)


HARD_GATES = {
    "E0_INPUT_UNIVERSE",
    "E1_TREATMENT_SUPPORT",
    "E2_WITHIN_PERIOD_SUPPORT",
    "E3_OUTCOME_SPARSITY",
    "E6_SYNTHETIC_SIGNAL_RECOVERY",
}


@dataclass(frozen=True)
class CalibrationCellSpec:
    cell_id: str
    source: str
    definition: str
    role: str

    @classmethod
    def from_dict(cls, payload: dict) -> "CalibrationCellSpec":
        role = str(payload.get("role", "PRIMARY")).upper()
        if role not in {"PRIMARY", "STRESS"}:
            raise ValueError("Calibration cell role must be PRIMARY or STRESS")
        return cls(
            cell_id=str(payload["cell_id"]),
            source=str(payload["source"]),
            definition=str(payload["definition"]),
            role=role,
        )


@dataclass(frozen=True)
class CalibrationThresholds:
    min_treated: int = 30
    min_control: int = 30
    min_mixed_periods: int = 2
    max_zero_share_green: float = 0.95
    max_zero_share_red: float = 0.99
    max_abs_pre_smd_green: float = 0.25
    max_abs_pre_smd_red: float = 0.50
    max_placebo_std_green: float = 0.10
    max_placebo_std_red: float = 0.25
    plausible_effect_sd: float = 0.20
    signal_draws: int = 30
    signal_target_green: float = 0.80
    signal_target_red: float = 0.50
    seed: int = 20260821

    @classmethod
    def from_dict(cls, payload: Optional[dict]) -> "CalibrationThresholds":
        return cls(**(payload or {}))


@dataclass(frozen=True)
class CalibrationMatrixSpec:
    matrix_id: str
    surface_manifest: str
    treatment_period_start: str
    treatment_period_end: str
    annotation_version: str
    cells: List[CalibrationCellSpec]
    thresholds: CalibrationThresholds = field(default_factory=CalibrationThresholds)
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path) -> "CalibrationMatrixSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        spec = cls(
            matrix_id=str(raw["matrix_id"]),
            surface_manifest=str(raw["surface_manifest"]),
            treatment_period_start=str(raw["treatment_period_start"]),
            treatment_period_end=str(raw["treatment_period_end"]),
            annotation_version=str(raw.get("annotation_version", "legacy_2023")),
            cells=[CalibrationCellSpec.from_dict(x) for x in raw["cells"]],
            thresholds=CalibrationThresholds.from_dict(raw.get("thresholds")),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )
        if _period_start(spec.treatment_period_start) > _period_start(spec.treatment_period_end):
            raise ValueError("Calibration treatment period start must not follow end")
        ids = [x.cell_id for x in spec.cells]
        if len(ids) != len(set(ids)):
            raise ValueError("Calibration cell_id values must be unique")
        return spec


def _surface_outcome_contract(surface_spec: AnalysisSurfaceSpec) -> OutcomeMeasurementSpec:
    return OutcomeMeasurementSpec(
        source=surface_spec.outcome.source,
        column=surface_spec.outcome.column,
        timing="next_period",
        absent_record_policy=surface_spec.outcome.policy,
        verified_period_start=surface_spec.outcome.verified_period_start,
        verified_period_end=surface_spec.outcome.verified_period_end,
    )


def build_cell_experiment_spec(
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: AnalysisSurfaceSpec,
    panel_id: str,
    cell: CalibrationCellSpec,
) -> CanonicalPanelExperimentSpec:
    return CanonicalPanelExperimentSpec(
        experiment_id=f"{matrix_spec.matrix_id}__{cell.cell_id}",
        panel_id=panel_id,
        treatment=TreatmentMeasurementSpec(
            source=cell.source,
            definition=cell.definition,
            annotation_version=matrix_spec.annotation_version,
        ),
        eligibility=EligibilitySpec(
            treatment_period_start=matrix_spec.treatment_period_start,
            treatment_period_end=matrix_spec.treatment_period_end,
        ),
        outcome=_surface_outcome_contract(surface_spec),
        covariates=[],
        unit_col=matrix_spec.unit_col,
        period_col=matrix_spec.period_col,
        country_col=matrix_spec.country_col,
    )


def _period_order(series: pd.Series) -> pd.Series:
    return series.astype(str).map(_period_start)


def attach_pre_outcome(
    measurement_frame: pd.DataFrame,
    resolved_panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
) -> pd.DataFrame:
    required = {
        matrix_spec.unit_col,
        matrix_spec.period_col,
        "acled_value_resolved",
    }
    missing = sorted(required - set(resolved_panel.columns))
    if missing:
        raise KeyError(f"Resolved E1 panel missing pre-outcome inputs: {missing}")

    panel = resolved_panel[
        [matrix_spec.unit_col, matrix_spec.period_col, "acled_value_resolved"]
    ].copy()
    panel["_period_order"] = _period_order(panel[matrix_spec.period_col])
    panel = panel.sort_values([matrix_spec.unit_col, "_period_order"])
    g = panel.groupby(matrix_spec.unit_col, sort=False)
    panel["outcome_pre"] = g["acled_value_resolved"].shift(1)
    panel["outcome_pre_period"] = g[matrix_spec.period_col].shift(1)

    pre = panel[
        [matrix_spec.unit_col, matrix_spec.period_col, "outcome_pre", "outcome_pre_period"]
    ]
    out = measurement_frame.merge(
        pre,
        on=[matrix_spec.unit_col, matrix_spec.period_col],
        how="left",
        validate="one_to_one",
    )
    return out


def standardized_mean_difference(a, b) -> float:
    a = pd.to_numeric(pd.Series(a), errors="coerce").dropna()
    b = pd.to_numeric(pd.Series(b), errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if not np.isfinite(pooled) or pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def _model_sample(frame: pd.DataFrame, spec: CalibrationMatrixSpec) -> pd.DataFrame:
    sample = frame.loc[frame["eligible"]].copy()
    needed = [
        "outcome_value",
        "outcome_pre",
        "treatment",
        spec.unit_col,
        spec.period_col,
        spec.country_col,
    ]
    return sample.dropna(subset=needed).copy()


def calibration_estimate(
    frame: pd.DataFrame,
    spec: CalibrationMatrixSpec,
    outcome_col: str = "outcome_value",
) -> dict:
    sample = _model_sample(frame, spec)
    if outcome_col != "outcome_value":
        sample = frame.loc[frame["eligible"]].dropna(
            subset=[outcome_col, "outcome_pre", "treatment", spec.unit_col, spec.period_col, spec.country_col]
        ).copy()
    if sample["treatment"].nunique() < 2:
        return {"ok": False, "reason": "Treatment has no variation in model-complete sample."}

    formula = (
        f"{outcome_col} ~ treatment + outcome_pre + "
        f"C({spec.period_col}) + C({spec.country_col})"
    )
    fit = smf.ols(formula, data=sample).fit(
        cov_type="cluster",
        cov_kwds={"groups": sample[spec.unit_col].to_numpy()},
    )
    se = float(fit.bse["treatment"])
    effect = float(fit.params["treatment"])
    return {
        "ok": True,
        "effect": effect,
        "se": se,
        "z": effect / se if se > 0 else np.nan,
        "n": int(len(sample)),
        "n_units": int(sample[spec.unit_col].nunique()),
        "n_treated": int((sample["treatment"] == 1).sum()),
        "n_control": int((sample["treatment"] == 0).sum()),
        "formula": formula,
    }


def placebo_estimate(frame: pd.DataFrame, spec: CalibrationMatrixSpec) -> dict:
    """Correct placebo: pre-outcome is the dependent variable, never its own control."""
    sample = frame.loc[frame["eligible"]].dropna(
        subset=["outcome_pre", "treatment", spec.unit_col, spec.period_col, spec.country_col]
    ).copy()
    if sample["treatment"].nunique() < 2:
        return {"ok": False, "reason": "Treatment has no variation in placebo sample."}
    formula = (
        f"outcome_pre ~ treatment + C({spec.period_col}) + C({spec.country_col})"
    )
    fit = smf.ols(formula, data=sample).fit(
        cov_type="cluster",
        cov_kwds={"groups": sample[spec.unit_col].to_numpy()},
    )
    effect = float(fit.params["treatment"])
    se = float(fit.bse["treatment"])
    sd = float(pd.to_numeric(sample["outcome_pre"], errors="coerce").std(ddof=1))
    return {
        "ok": True,
        "effect": effect,
        "se": se,
        "z": effect / se if se > 0 else np.nan,
        "std_abs_effect": abs(effect) / sd if sd > 0 else np.nan,
        "n": int(len(sample)),
        "formula": formula,
    }


def synthetic_signal_recovery(
    frame: pd.DataFrame,
    spec: CalibrationMatrixSpec,
    thresholds: CalibrationThresholds,
    seed_offset: int = 0,
) -> dict:
    """Wild-cluster residual simulation for a declared incremental treatment signal.

    A nuisance model without treatment preserves period/country/pre-outcome structure.
    Residuals are sign-flipped at GID level, a known treatment signal is injected,
    and the calibration estimator must recover its sign with |z| >= 1.96.
    """
    sample = _model_sample(frame, spec)
    if sample["treatment"].nunique() < 2 or sample[spec.unit_col].nunique() < 20:
        return {"ok": False, "reason": "Insufficient treatment/unit support for signal recovery."}

    nuisance_formula = (
        f"outcome_value ~ outcome_pre + C({spec.period_col}) + C({spec.country_col})"
    )
    nuisance = smf.ols(nuisance_formula, data=sample).fit()
    fitted = np.asarray(nuisance.fittedvalues, dtype=float)
    resid = np.asarray(nuisance.resid, dtype=float)
    ysd = float(pd.to_numeric(sample["outcome_value"], errors="coerce").std(ddof=1))
    if not np.isfinite(ysd) or ysd <= 0:
        return {"ok": False, "reason": "Outcome has no finite variance for signal injection."}
    injected = float(thresholds.plausible_effect_sd * ysd)

    rng = np.random.default_rng(thresholds.seed + seed_offset)
    unit_values = sample[spec.unit_col].astype(str)
    units = unit_values.unique()
    successes = 0
    attempts = 0
    z_values = []
    effects = []

    for _ in range(int(thresholds.signal_draws)):
        signs = pd.Series(rng.choice([-1.0, 1.0], size=len(units)), index=units)
        wild = unit_values.map(signs).to_numpy(dtype=float)
        synthetic = fitted + resid * wild + injected * sample["treatment"].to_numpy(dtype=float)
        sim = sample.copy()
        sim["_synthetic_outcome"] = synthetic
        est = calibration_estimate(sim, spec, outcome_col="_synthetic_outcome")
        if not est.get("ok"):
            continue
        attempts += 1
        effects.append(est["effect"])
        z_values.append(est["z"])
        sign_ok = np.sign(est["effect"]) == np.sign(injected)
        detected = np.isfinite(est["z"]) and abs(est["z"]) >= 1.96
        successes += int(sign_ok and detected)

    return {
        "ok": attempts > 0,
        "attempts": attempts,
        "successes": successes,
        "recovery_probability": successes / attempts if attempts else np.nan,
        "injected_effect": injected,
        "injected_effect_sd": thresholds.plausible_effect_sd,
        "median_estimated_effect": float(np.median(effects)) if effects else np.nan,
        "median_abs_z": float(np.median(np.abs(z_values))) if z_values else np.nan,
        "method": "GID-level wild sign-flip residual simulation",
    }


def _gate_row(gate, status, metric, value, threshold, note, hard):
    return {
        "gate": gate,
        "status": status,
        "hard": bool(hard),
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "note": note,
    }


def run_calibration_gates(
    frame: pd.DataFrame,
    preflight: dict,
    matrix_spec: CalibrationMatrixSpec,
    surface_gates: pd.DataFrame,
    seed_offset: int = 0,
):
    t = matrix_spec.thresholds
    rows = []
    eligible = frame.loc[frame["eligible"]].copy()

    surface_hard_names = {"U0_UNIVERSE_DECLARED", "U2_COUNTRY_IDENTITY", "A0_ACLED_POLICY_EXPLICIT", "A1_ACLED_RESOLUTION_COMPLETENESS"}
    surface_bad = surface_gates.loc[
        surface_gates["gate"].isin(surface_hard_names) & surface_gates["status"].eq("RED")
    ]
    model = _model_sample(frame, matrix_spec)
    pre_missing = int(eligible["outcome_pre"].isna().sum())
    post_missing = int(eligible["outcome_value"].isna().sum())
    e0_ok = bool(preflight["estimation_permitted"]) and surface_bad.empty and pre_missing == 0 and post_missing == 0
    rows.append(_gate_row(
        "E0_INPUT_UNIVERSE",
        "GREEN" if e0_ok else "RED",
        "resolved measurement + universe + pre/post outcome completeness",
        f"policy={preflight['estimation_permitted']}; pre_missing={pre_missing}; post_missing={post_missing}; surface_red={len(surface_bad)}",
        "resolved policy; 0 pre/post missing; no hard E1 surface RED",
        "The E1 analysis surface and timing inputs must be complete before calibration.",
        True,
    ))

    nt = int((model["treatment"] == 1).sum())
    nc = int((model["treatment"] == 0).sum())
    if nt >= t.min_treated and nc >= t.min_control:
        s = "GREEN"
    elif nt >= 10 and nc >= 10:
        s = "YELLOW"
    else:
        s = "RED"
    rows.append(_gate_row(
        "E1_TREATMENT_SUPPORT", s, "treated / control model rows", f"{nt} / {nc}",
        f"green >= {t.min_treated} / {t.min_control}",
        "Pooled support is necessary but cannot substitute for within-period support.", True,
    ))

    byp = eligible.groupby(matrix_spec.period_col)["treatment"].agg(["sum", "count"])
    byp["control"] = byp["count"] - byp["sum"]
    mixed = int(((byp["sum"] > 0) & (byp["control"] > 0)).sum())
    total = int(len(byp))
    if mixed == total and total > 0:
        s = "GREEN"
    elif mixed >= t.min_mixed_periods:
        s = "YELLOW"
    else:
        s = "RED"
    rows.append(_gate_row(
        "E2_WITHIN_PERIOD_SUPPORT", s, "periods with treated + control", f"{mixed}/{total}",
        f"hard minimum >= {t.min_mixed_periods}; green = all declared periods",
        "A stress definition may remain estimable with a YELLOW period, but the missing support stays visible; periods are never dropped to improve the result.", True,
    ))

    y = pd.to_numeric(model["outcome_value"], errors="coerce")
    zero_share = float((y == 0).mean()) if len(y) else np.nan
    if np.isnan(zero_share) or zero_share > t.max_zero_share_red:
        s = "RED"
    elif zero_share > t.max_zero_share_green:
        s = "YELLOW"
    else:
        s = "GREEN"
    rows.append(_gate_row(
        "E3_OUTCOME_SPARSITY", s, "zero share resolved VAC(t+1)", None if np.isnan(zero_share) else round(zero_share, 4),
        f"green <= {t.max_zero_share_green:.2f}; red > {t.max_zero_share_red:.2f}",
        "The first OLS is calibration only; high zero mass is a reason to later test count/binary/hurdle outcomes, not to search coefficients now.", True,
    ))

    smd = standardized_mean_difference(
        model.loc[model["treatment"] == 1, "outcome_pre"],
        model.loc[model["treatment"] == 0, "outcome_pre"],
    )
    if np.isnan(smd):
        s = "YELLOW"
    elif abs(smd) <= t.max_abs_pre_smd_green:
        s = "GREEN"
    elif abs(smd) <= t.max_abs_pre_smd_red:
        s = "YELLOW"
    else:
        s = "RED"
    rows.append(_gate_row(
        "E4_PRE_OUTCOME_BALANCE", s, "|SMD| pre-outcome", None if np.isnan(smd) else round(abs(smd), 4),
        f"green <= {t.max_abs_pre_smd_green:.2f}; red > {t.max_abs_pre_smd_red:.2f}",
        "Diagnostic rather than a coefficient-selection rule. Strong imbalance constrains causal interpretation.", False,
    ))

    placebo = placebo_estimate(frame, matrix_spec)
    pstd = placebo.get("std_abs_effect", np.nan) if placebo.get("ok") else np.nan
    if np.isnan(pstd):
        s = "RED"
    elif pstd <= t.max_placebo_std_green:
        s = "GREEN"
    elif pstd <= t.max_placebo_std_red:
        s = "YELLOW"
    else:
        s = "RED"
    rows.append(_gate_row(
        "E5_PRE_OUTCOME_PLACEBO", s, "|placebo treatment effect| / SD(pre-outcome)", None if np.isnan(pstd) else round(float(pstd), 4),
        f"green <= {t.max_placebo_std_green:.2f}; red > {t.max_placebo_std_red:.2f}",
        "Correct placebo regression excludes outcome_pre from its own RHS. RED constrains interpretation but does not hide the calibration coefficient.", False,
    ))

    recovery = synthetic_signal_recovery(frame, matrix_spec, t, seed_offset=seed_offset)
    power = recovery.get("recovery_probability", np.nan) if recovery.get("ok") else np.nan
    if np.isnan(power) or power < t.signal_target_red:
        s = "RED"
    elif power < t.signal_target_green:
        s = "YELLOW"
    else:
        s = "GREEN"
    rows.append(_gate_row(
        "E6_SYNTHETIC_SIGNAL_RECOVERY", s, "known-signal recovery probability", None if np.isnan(power) else round(float(power), 3),
        f"green >= {t.signal_target_green:.2f}; hard red < {t.signal_target_red:.2f}",
        f"Injects {t.plausible_effect_sd:.2f} outcome SD using GID-level wild residual sign flips. Calibration, never evidence for a real effect.", True,
    ))

    gates = pd.DataFrame(rows)
    hard_red = gates.loc[gates["hard"] & gates["status"].eq("RED")]
    estimation_permitted = hard_red.empty
    support = byp.reset_index().rename(columns={"sum": "treated", "count": "eligible_rows"})
    return {
        "gates": gates,
        "support_by_period": support,
        "placebo": placebo,
        "signal_recovery": recovery,
        "estimation_permitted": bool(estimation_permitted),
        "hard_red_gates": hard_red["gate"].tolist(),
    }


def run_calibration_cell(
    resolved_panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: AnalysisSurfaceSpec,
    surface_gates: pd.DataFrame,
    source_only_keys: pd.DataFrame,
    panel_id: str,
    cell: CalibrationCellSpec,
    seed_offset: int = 0,
):
    exp = build_cell_experiment_spec(matrix_spec, surface_spec, panel_id, cell)
    preflight = run_experiment_preflight(
        resolved_panel,
        exp,
        source_only_keys=source_only_keys,
    )
    frame = attach_pre_outcome(preflight["frame"], resolved_panel, matrix_spec)
    gate_result = run_calibration_gates(
        frame, preflight, matrix_spec, surface_gates, seed_offset=seed_offset
    )
    estimate = (
        calibration_estimate(frame, matrix_spec)
        if gate_result["estimation_permitted"]
        else {"ok": False, "reason": "Hard calibration gate RED: " + ", ".join(gate_result["hard_red_gates"])}
    )
    return {
        "cell": cell,
        "experiment_spec": exp,
        "preflight": preflight,
        "frame": frame,
        **gate_result,
        "estimate": estimate,
    }


def _stability_row(result: dict) -> dict:
    cell = result["cell"]
    est = result["estimate"]
    placebo = result["placebo"]
    recovery = result["signal_recovery"]
    support = result["support_by_period"]
    mixed = int(((support["treated"] > 0) & (support["control"] > 0)).sum()) if len(support) else 0
    red = result["gates"].loc[result["gates"]["status"].eq("RED"), "gate"].tolist()
    yellow = result["gates"].loc[result["gates"]["status"].eq("YELLOW"), "gate"].tolist()
    return {
        "cell_id": cell.cell_id,
        "role": cell.role,
        "source": cell.source,
        "treatment_definition": cell.definition,
        "estimated": bool(est.get("ok")),
        "effect": est.get("effect", np.nan),
        "se": est.get("se", np.nan),
        "n": est.get("n", np.nan),
        "n_units": est.get("n_units", np.nan),
        "treated": est.get("n_treated", np.nan),
        "control": est.get("n_control", np.nan),
        "mixed_support_periods": f"{mixed}/{len(support)}",
        "placebo_std_abs_effect": placebo.get("std_abs_effect", np.nan),
        "signal_recovery": recovery.get("recovery_probability", np.nan),
        "hard_gate_state": "PASS" if result["estimation_permitted"] else "BLOCKED",
        "red_gates": ";".join(red),
        "yellow_gates": ";".join(yellow),
        "estimate_reason": est.get("reason", ""),
    }


def render_calibration_card(matrix_spec: CalibrationMatrixSpec, stability: pd.DataFrame) -> str:
    def fmt(x):
        if pd.isna(x):
            return "—"
        if isinstance(x, float):
            return f"{x:.4g}"
        return str(x)

    lines = [
        f"# WB→ACLED Measurement Calibration — {matrix_spec.matrix_id}",
        "",
        "> This is a measurement calibration matrix, not a model-selection tournament. No cell is selected because of coefficient sign or significance.",
        "",
        "## Frozen design",
        "",
        f"- Treatment window: `{matrix_spec.treatment_period_start}` through `{matrix_spec.treatment_period_end}`",
        "- Geography/time: inherited E1 ADM2 / T=2 / y0=2001 surface",
        "- Outcome: resolved ACLED deaths from violence against civilians at t+1",
        "- Regression: `VAC(t+1) ~ treatment(t) + VAC(t-1) + period FE + country FE`, SE clustered by GID",
        "- Additional DHSGC covariates: none",
        "",
        "## Measurement stability table",
        "",
        "| cell | role | effect | SE | N | treated/control | support | placebo/SD | signal recovery | hard gates |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, r in stability.iterrows():
        tc = "—" if pd.isna(r["treated"]) else f"{int(r['treated'])}/{int(r['control'])}"
        lines.append(
            "| " + " | ".join([
                str(r["cell_id"]), str(r["role"]), fmt(r["effect"]), fmt(r["se"]),
                "—" if pd.isna(r["n"]) else str(int(r["n"])), tc,
                str(r["mixed_support_periods"]), fmt(r["placebo_std_abs_effect"]),
                fmt(r["signal_recovery"]), str(r["hard_gate_state"]),
            ]) + " |"
        )
    lines += [
        "",
        "## Reading rule",
        "",
        "Primary comparison is `record_present` across WBad and WBkg. `amount_positive` is retained as a predeclared stress definition even when a period loses treated support; the period is never dropped to make the stress specification look better.",
        "",
        "RED soft diagnostics (pre-outcome balance/placebo) restrict causal interpretation but do not erase a calibration estimate. A RED hard gate blocks the real coefficient entirely. Synthetic recovery is a hard gate because a measurement/estimation system that cannot recover a known injected signal has not earned interpretation of the observed coefficient.",
        "",
    ]
    return "\n".join(lines)


def run_calibration_matrix(
    resolved_panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: AnalysisSurfaceSpec,
    surface_gates: pd.DataFrame,
    source_only_keys: pd.DataFrame,
    panel_id: str,
):
    results = {}
    for i, cell in enumerate(matrix_spec.cells):
        results[cell.cell_id] = run_calibration_cell(
            resolved_panel,
            matrix_spec,
            surface_spec,
            surface_gates,
            source_only_keys,
            panel_id,
            cell,
            seed_offset=1000 * i,
        )
    stability = pd.DataFrame([_stability_row(results[c.cell_id]) for c in matrix_spec.cells])
    card = render_calibration_card(matrix_spec, stability)
    return {"cells": results, "stability": stability, "card": card}


def write_calibration_outputs(result: dict, matrix_spec: CalibrationMatrixSpec, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["stability"].to_csv(out / "measurement_stability.csv", index=False)
    (out / "calibration_matrix_card.md").write_text(result["card"], encoding="utf-8")
    contract = asdict(matrix_spec)
    (out / "calibration_matrix_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")

    gate_rows = []
    for cell_id, cell_result in result["cells"].items():
        cell_dir = out / "cells" / cell_id
        cell_dir.mkdir(parents=True, exist_ok=True)
        gates = cell_result["gates"].copy()
        gates.insert(0, "cell_id", cell_id)
        gate_rows.append(gates)
        gates.to_csv(cell_dir / "gates.csv", index=False)
        cell_result["support_by_period"].to_csv(cell_dir / "support_by_period.csv", index=False)
        pd.DataFrame([cell_result["placebo"]]).to_csv(cell_dir / "placebo.csv", index=False)
        pd.DataFrame([cell_result["signal_recovery"]]).to_csv(cell_dir / "signal_recovery.csv", index=False)
        pd.DataFrame([cell_result["estimate"]]).to_csv(cell_dir / "estimate.csv", index=False)
        cell_result["frame"].head(500).to_csv(cell_dir / "analysis_frame_sample.csv", index=False)
        (cell_dir / "experiment_contract.json").write_text(
            json.dumps(asdict(cell_result["experiment_spec"]), indent=2), encoding="utf-8"
        )
    pd.concat(gate_rows, ignore_index=True).to_csv(out / "cell_gates.csv", index=False)
    return out
