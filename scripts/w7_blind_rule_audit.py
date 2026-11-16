#!/usr/bin/env python3
"""Outcome-blind deterministic nested audit: project and crosswalk QA, not jobs labels."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

KEY = ["source_family", "source_release_id", "source_project_id"]
STAGES = (10, 20, 50, 100)

def audit_sample(ledger, proxy_policy, native_policy, seed=20261116):
    if len(ledger) < 100 or ledger.duplicated(KEY).any():
        raise ValueError("Expected >=100 unique source qualified projects")
    cols = KEY + ["project_title", "native_sector_raw", "candidate_sector_channel", "editorial_status"]
    df = ledger[cols].copy().sort_values(KEY).reset_index(drop=True)
    if set(df.source_family) != {"china", "world_bank"}:
        raise ValueError("Missing donors")
    def original_channels(row):
        dictionary = native_policy["donors"][row.source_family]
        sectors = [t.strip() for t in row.native_sector_raw.split("|")]
        if not sectors or any(t not in dictionary for t in sectors):
            raise ValueError("Unmapped source sector")
        tags = {dictionary[t] for t in sectors}
        return "|".join(sorted(tags, key=native_policy["categories"].index))
    expected = df.apply(original_channels, axis=1)
    if not expected.equals(df.candidate_sector_channel):
        raise ValueError("Native sector mapping parity fails")
    if not df.editorial_status.eq("unreviewed").all():
        raise ValueError("Unexpected editorial review state")
    for label in ["broad", "narrow"]:
        positive = set(proxy_policy["policies"][label]["positive"])
        other = set(proxy_policy["policies"][label]["other"])
        def decide(channels):
            tags = set(channels.split("|"))
            if tags <= positive:
                return "candidate"
            if tags <= other:
                return "other_sector"
            if tags <= (positive | other):
                return "mixed"
            raise ValueError("Unknown harmonized channel")
        df[label + "_role"] = df.candidate_sector_channel.map(decide)
    df["stratum"] = df.source_family + "/" + df.broad_role + "/" + df.narrow_role
    df["selection_hash"] = df[KEY].apply(
        lambda r: hashlib.sha256((str(seed) + "|" + "|".join(map(str, r))).encode()).hexdigest(), axis=1)
    pools = {k: g.sort_values("selection_hash").to_dict("records")
             for k, g in df.groupby("stratum", sort=True)}
    ordered = []
    while len(ordered) < max(STAGES):
        prior = len(ordered)
        for k in sorted(pools):
            if pools[k]:
                ordered.append(pools[k].pop(0))
                if len(ordered) == max(STAGES):
                    break
        if len(ordered) == prior:
            raise ValueError("Sample pool exhausted")
    sample = pd.DataFrame(ordered)
    sample.insert(0, "audit_sequence", range(1, 101))
    sample["review_status"] = "NOT_REVIEWED"
    sample["anomaly"] = False
    sample["anomaly_explanation"] = ""
    sample["proposed_correction"] = ""
    report = {
        "schema": "fcv.w7.nested_rule_audit.v0",
        "n_universe": len(df),
        "donor_universe": df.source_family.value_counts().to_dict(),
        "full_universe_mapping_parity": True,
        "stages": list(STAGES),
        "max_rows_for_semantic_review": 100,
        "selection_seed": seed,
        "sample_strata_counts": sample.stratum.value_counts().to_dict(),
        "acceptance": "max 2 material anomalies per 100 inspected; does not certify population error rate",
    }
    return sample, report

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--ledger", required=True, type=Path)
    a.add_argument("--proxy-policy", required=True, type=Path)
    a.add_argument("--native-policy", required=True, type=Path)
    a.add_argument("--output-dir", required=True, type=Path)
    args = a.parse_args()
    if args.output_dir.exists():
        a.error("Output exists: immutable release")
    sample, report = audit_sample(pd.read_parquet(args.ledger),
        json.loads(args.proxy_policy.read_text()), json.loads(args.native_policy.read_text()))
    args.output_dir.mkdir(parents=True)
    for n in STAGES:
        sample.head(n).to_csv(args.output_dir / f"w7_blind_sample_{n}.csv", index=False)
    report["input_sha256"] = {str(f): hashlib.sha256(f.read_bytes()).hexdigest()
                              for f in (args.ledger, args.proxy_policy, args.native_policy)}
    report["sample_100_sha256"] = hashlib.sha256(
        (args.output_dir / "w7_blind_sample_100.csv").read_bytes()).hexdigest()
    (args.output_dir / "w7_blind_audit_receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PARITY PASS", report["n_universe"], "SAMPLE", str(args.output_dir))

if __name__ == "__main__":
    main()
