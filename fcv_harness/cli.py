from pathlib import Path
import argparse
import pandas as pd

from .core import ExperimentSpec, build_exposure_state
from .estimate import spatial_did, bandwidth_sweep
from .gates import run_gates, render_gate_report

def main():
    ap = argparse.ArgumentParser(description="Run an FCV experiment gate pass on canonical CSV inputs.")
    ap.add_argument("--observations", required=True)
    ap.add_argument("--projects", required=True)
    ap.add_argument("--links", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    obs = pd.read_csv(args.observations)
    projects = pd.read_csv(args.projects)
    links = pd.read_csv(args.links)
    spec = ExperimentSpec.from_json(args.config)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sample = build_exposure_state(obs, projects, links, spec.radius_km)
    sample.to_csv(out / "analysis_sample.csv", index=False)

    est = spatial_did(sample, spec.outcome, spec.covariates, spec.fixed_effects)
    pd.DataFrame([est]).to_csv(out / "baseline_estimate.csv", index=False)

    bw = bandwidth_sweep(obs, projects, links, spec)
    bw.to_csv(out / "bandwidth_sweep.csv", index=False)

    gates = run_gates(obs, projects, links, spec)
    report = render_gate_report(gates, title=f"Gate Report — {spec.experiment_id}")
    (out / "gate_report.md").write_text(report, encoding="utf-8")

    print(report)
    print(f"\nOutputs written to: {out}")

if __name__ == "__main__":
    main()
