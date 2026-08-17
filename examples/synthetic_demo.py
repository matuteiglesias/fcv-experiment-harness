from pathlib import Path
import sys
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from fcv_harness import ExperimentSpec, build_exposure_state, spatial_did, bandwidth_sweep, run_gates, render_gate_report

def make_demo(seed=20260817, n=1200):
    rng = np.random.default_rng(seed)
    obs = pd.DataFrame({
        "obs_id": np.arange(n),
        "cluster_id": rng.integers(0, 180, n),
        "obs_year": rng.choice([2006, 2008, 2010, 2012], n),
        "country": rng.choice(["A", "B", "C"], n),
        "round": rng.choice([3, 4, 5], n),
        "baseline_risk": rng.normal(0, 1, n),
        "population_z": rng.normal(0, 1, n),
    })
    obs["outcome_pre"] = (
        0.30 * obs["baseline_risk"]
        + 0.10 * obs["population_z"]
        + rng.normal(0, 1.0, n)
    )

    p = 150
    agr = rng.choice([2005, 2007, 2009, 2011, 2013], p)
    start = agr + rng.choice([1, 1, 2], p)
    end = start + rng.choice([1, 2, 3], p)
    projects = pd.DataFrame({
        "project_id": np.arange(p),
        "agreement_year": agr,
        "actual_start_year": start,
        "scheduled_start_year": start - 1,
        "actual_end_year": end,
        "scheduled_end_year": end - 1,
        "source_status": "completed",
        "geo_precision_km": rng.choice([1, 5, 20], p, p=[0.5, 0.3, 0.2]),
        "sector": rng.choice(["transport", "health", "education", "agriculture"], p),
    })

    rows = []
    for oid in obs.obs_id:
        for pid in rng.choice(projects.project_id, size=5, replace=False):
            rows.append((oid, int(pid), float(abs(rng.normal(32, 24)))))
    links = pd.DataFrame(rows, columns=["obs_id", "project_id", "distance_km"])

    spec = ExperimentSpec.from_json(ROOT / "config" / "example_experiment.json")

    df = build_exposure_state(obs, projects, links, spec.radius_km)
    signal = np.where(df.exposure_state.eq("completed"), -0.22, 0.0)

    obs["outcome_post"] = (
        0.55 * obs["outcome_pre"]
        + 0.15 * obs["baseline_risk"]
        + signal
        + rng.normal(0, 1.0, n)
    )
    return obs, projects, links, spec

if __name__ == "__main__":
    obs, projects, links, spec = make_demo()

    csv_dir = HERE / "demo_inputs"
    csv_dir.mkdir(exist_ok=True)
    obs.to_csv(csv_dir / "observations.csv", index=False)
    projects.to_csv(csv_dir / "projects.csv", index=False)
    links.to_csv(csv_dir / "exposure_links.csv", index=False)
    df = build_exposure_state(obs, projects, links, spec.radius_km)

    est = spatial_did(df, spec.outcome, spec.covariates, spec.fixed_effects)
    gates = run_gates(obs, projects, links, spec)
    report = render_gate_report(gates, title=f"Gate Report — {spec.experiment_id}")

    (HERE / "demo_gate_report.md").write_text(report, encoding="utf-8")
    bandwidth_sweep(obs, projects, links, spec).to_csv(HERE / "demo_bandwidth.csv", index=False)

    print("BASELINE ESTIMATE")
    print(est)
    print()
    print(report)
