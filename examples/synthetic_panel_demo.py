from pathlib import Path
import sys
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from fcv_harness.panel import (
    PanelExperimentSpec, run_panel_gates, render_panel_report,
    panel_baseline_estimate, build_panel_analysis_frame
)

def make_panel(seed=20260817, n_units=320, n_periods=7):
    rng = np.random.default_rng(seed)
    units = [f"G{i:04d}" for i in range(n_units)]
    periods = list(range(n_periods))
    rows = []

    unit_risk = dict(zip(units, rng.normal(0, 1, n_units)))
    country = dict(zip(units, rng.choice(["AA", "BB", "CC", "DD"], n_units)))

    # A staggered-ish but noisy project process. Deliberately some selection on baseline risk.
    first_treat = {}
    for u in units:
        prob = 1 / (1 + np.exp(-(-1.0 + 0.35 * unit_risk[u])))
        if rng.random() < prob:
            first_treat[u] = int(rng.integers(1, n_periods - 1))
        else:
            first_treat[u] = None

    y_prev = {u: max(0.0, rng.poisson(np.exp(-0.3 + 0.25 * unit_risk[u]))) for u in units}
    for p in periods:
        for u in units:
            active = first_treat[u] is not None and p == first_treat[u]
            wb = float(active and rng.random() < 0.75) * float(rng.uniform(1e5, 3e6))
            cn = float(active and wb == 0) * float(rng.uniform(1e5, 3e6))

            # Weak post-treatment reduction shows up in the following period through y_prev state.
            lam = np.exp(-0.25 + 0.28 * unit_risk[u] + 0.12 * y_prev[u])
            if first_treat[u] is not None and p == first_treat[u] + 1:
                lam *= np.exp(-0.18)
            y = float(rng.poisson(lam))

            rows.append({
                "GID": u,
                "Period": p,
                "TimePeriod": f"{2001 + 2*p:04d}-{2002 + 2*p:04d}",
                "ISO": country[u],
                "wbad_amount_usd": wb,
                "cn_amount_usd": cn,
                "violence_events": y,
                "baseline_risk": unit_risk[u],
                "popsum": float(rng.integers(1000, 250000)),
            })
            y_prev[u] = y

    return pd.DataFrame(rows)

if __name__ == "__main__":
    df = make_panel()
    spec = PanelExperimentSpec(
        experiment_id="synthetic_legacy_panel",
        outcome="violence_events",
        treatment_type="cnwb_pooled",
        covariates=["baseline_risk"],
        max_outcome_missing_share=0.20,
        plausible_effect_sd=-0.20,
        bootstrap_draws=100,
    )

    gates, frame = run_panel_gates(df, spec)
    report = render_panel_report(gates, spec)
    print(report)
    print("\\nBASELINE:", panel_baseline_estimate(frame, spec))

    out = HERE / "panel_demo"
    out.mkdir(exist_ok=True)
    panel_cols = [c for c in df.columns if c != "violence_events"]
    df[panel_cols].to_csv(out / "legacy_panel_DHSGC.csv", index=False)
    df[["GID", "TimePeriod", "violence_events"]].to_csv(out / "legacy_outcomes.csv", index=False)
    df.to_csv(out / "legacy_merged.csv", index=False)
    gates.to_csv(out / "gates.csv", index=False)
    frame.to_csv(out / "analysis_frame.csv", index=False)
    (out / "gate_report.md").write_text(report, encoding="utf-8")
