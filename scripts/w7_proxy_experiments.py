"""CLI for the frozen W7 proxy experiment; never overwrites a run directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from fcv_harness.w7_proxy_experiments import load_policy, run_experiment, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("ledger", "bridge", "panel", "w5-frame", "policy", "output-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")
    policy = load_policy(args.policy)
    ledger = pd.read_parquet(args.ledger)
    bridge = pd.read_parquet(args.bridge)
    panel = pd.read_parquet(args.panel)
    w5 = pd.read_parquet(args.w5_frame)
    results = run_experiment(ledger, bridge, panel, w5, policy)
    args.output_dir.mkdir(parents=True)
    classified = ledger.copy()
    # Keep the candidate-ledger artifact private to this immutable run.
    from fcv_harness.w7_proxy_experiments import classify_projects, build_proxy_panel
    classified = classify_projects(classified, policy, "broad")
    _, arm_panel, _ = build_proxy_panel(ledger, bridge, panel, policy, "broad")
    classified.to_parquet(args.output_dir / "w7_candidate_ledger_private.parquet", index=False)
    arm_panel.to_parquet(args.output_dir / "w7_arm_panel_private.parquet", index=False)
    receipt = {
        "schema": "fcv.w7.exploratory_jobs_proxy_receipt.v0",
        "inputs_sha256": {name: sha256_file(path) for name, path in {
            "ledger": args.ledger, "bridge": args.bridge, "panel": args.panel,
            "w5_frame": args.w5_frame, "policy": args.policy}.items()},
        "outputs_sha256": {}, "source_inputs_unchanged": True,
        "frozen_policy": True, "results": results,
    }
    for path in args.output_dir.iterdir():
        receipt["outputs_sha256"][path.name] = sha256_file(path)
    (args.output_dir / "w7_proxy_results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["outputs_sha256"]["w7_proxy_results.json"] = sha256_file(args.output_dir / "w7_proxy_results.json")
    (args.output_dir / "w7_proxy_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "output_dir": str(args.output_dir), "models": list(results["models"])}, indent=2))


if __name__ == "__main__":
    main()
