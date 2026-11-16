#!/usr/bin/env python3
"""Freeze-and-run W8 J/O/N ADM2 common-support means. Source files are read only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from fcv_harness.w7_proxy_experiments import build_proxy_panel, sha256_file
from fcv_harness.w8_jon_common_support import (
    merge_exposure_outcome, construct_master, matched_standardization, W8DesignError
)


def main() -> None:
    ap = argparse.ArgumentParser()
    for label in ("w7-arm-panel", "w7-ledger", "w7-bridge", "w7-panel",
                  "w5-frame", "w7-policy", "scientific-design", "output-dir"):
        ap.add_argument("--" + label, type=Path, required=True)
    ap.add_argument("--bootstrap-reps", type=int, default=1999)
    args = ap.parse_args()
    if args.output_dir.exists():
        ap.error("output directory already exists; choose a new immutable run path")
    if args.bootstrap_reps < 0:
        ap.error("bootstrap reps must be nonnegative")
    inputs = {
        "w7_arm_panel": args.w7_arm_panel, "w7_ledger": args.w7_ledger,
        "w7_bridge": args.w7_bridge, "w7_panel": args.w7_panel,
        "w5_frame": args.w5_frame, "w7_policy": args.w7_policy,
        "scientific_design": args.scientific_design,
    }
    # Validate all source inputs and freeze their hashes before running.
    for k, p in inputs.items():
        if not p.is_file():
            ap.error(f"required source file absent: {k} {p}")
    sha = {k: sha256_file(p) for k, p in inputs.items()}
    broad = pd.read_parquet(args.w7_arm_panel)
    w5 = pd.read_parquet(args.w5_frame)
    ledger = pd.read_parquet(args.w7_ledger)
    bridge = pd.read_parquet(args.w7_bridge)
    source_panel = pd.read_parquet(args.w7_panel)
    # Reconstruct narrow *from frozen policy* — never reuse broad labels.
    _, narrow, diag = build_proxy_panel(
        ledger, bridge, source_panel, args.w7_policy, "narrow"
    )
    if len(broad) != len(narrow) or len(broad) != len(w5):
        raise W8DesignError("W5/W7 full panel size drift")
    results = {}
    matched_artifacts = {}
    for policy, arm_frame, rules in (
        ("broad", broad, ("not_yet_recorded", "period_only")),
        ("narrow", narrow, ("not_yet_recorded",)),
    ):
        data = merge_exposure_outcome(arm_frame, w5)
        for control_rule in rules:
            for donor in ("china", "world_bank"):
                master = construct_master(data, donor, control_rule, scenario=policy)
                result, matched = matched_standardization(
                    master, donor, policy, control_rule,
                    boot_reps=args.bootstrap_reps, seed=20261116
                )
                ident = f"{policy}__{control_rule}__{donor}"
                results[ident] = result
                if policy == "broad" and control_rule == "not_yet_recorded":
                    matched_artifacts[donor] = matched
                    assert matched.jon_group.value_counts().sum() == sum(
                        g["matched_group_cells"] for g in result["groups"].values()
                    )
                    # Outcome-blind exact cardinality acceptance for canonical v0 release.
                    expected = (128, 39, (1448, 2576, 13082)) if donor == "china" else (
                        11, 10, (86, 87, 484))
                    got = (result["matched_country_period_strata"], result["matched_countries"],
                           tuple(result["groups"][g]["matched_group_cells"] for g in ("J", "O", "N")))
                    if got != expected:
                        raise W8DesignError(f"canonical broad/clean-N cohort drift for {donor}: {got} vs {expected}")
    release = {
        "schema": "fcv.w8.jon_common_support_release.v0",
        "status": "COMPLETED_DESCRIPTIVE",
        "source_snapshot": "W5/W6/W7 2026-11-16",
        "policy": "frozen W7 broad primary, narrow sensitivity; exact country-finance-biennium common strata",
        "stratum_weights": "n_J_stratum / sum_retained_n_J across strata, shared for J/O/N",
        "causal": False,
        "measured_local_employment": False,
        "control_purity": "primary N zero CN & WB through t within observed seven biennia; other financiers and pre-2001 unseen",
        "bootstrapping": "country-level cluster nonparametric percentile CI; World Bank thin and CI unreliable",
        "narrow_source_diagnostics": diag,
        "results": results,
    }
    # Absolutely no original W5/W6/W7 overwrite. Every run gets its own output directory.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for donor, sub in matched_artifacts.items():
        cols = [
            "geo_uid", "period_id", "country_iso3", "jon_group",
            "had_source_before", "any_vac_next", "vac_events_prior",
            "stratum_nJ", "stratum_nOwn", "analysis_weight",
        ]
        sub[cols].to_parquet(args.output_dir / f"w8_{donor}_broad_cleanN_matched_adm2_private.parquet",
                             index=False)
    json_path = args.output_dir / "w8_jon_results.json"
    json_path.write_text(json.dumps(release, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema": "fcv.w8.jon_release_receipt.v0",
        "input_sha256": sha,
        "output_sha256": {p.name: sha256_file(p) for p in sorted(args.output_dir.iterdir())},
        "fit_counts": {k: {
            "countries": v["matched_countries"],
            "strata": v["matched_country_period_strata"],
            "J": v["groups"]["J"]["matched_group_cells"],
            "O": v["groups"]["O"]["matched_group_cells"],
            "N": v["groups"]["N"]["matched_group_cells"],
            "support_gate": v["support_gate"]
        } for k, v in results.items()},
        "immutable_output": True,
        "source_w5_w7_unchanged": True,
    }
    (args.output_dir / "w8_jon_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": release["status"], "models": list(results),
                      "output": str(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
