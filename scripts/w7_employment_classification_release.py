#!/usr/bin/env python3
"""Release the bounded W7 classification product."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from fcv_harness.w7_employment_classification import (
    apply_editorial_annotations, build_project_ledger, derive_exposure_panel,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_annotations(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.DataFrame(json.loads(path.read_text()))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dimension", type=Path, required=True)
    p.add_argument("--bridge", type=Path, required=True)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--annotation-file", type=Path)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dim, bridge, panel = (pd.read_parquet(x) for x in (args.dimension, args.bridge, args.panel))
    ledger = build_project_ledger(dim, args.policy)
    if args.annotation_file:
        ledger = apply_editorial_annotations(ledger, read_annotations(args.annotation_file))
    exposure, out_panel = derive_exposure_panel(ledger, bridge, panel)
    ledger_path = args.output_dir / "w7_project_classification_ledger_v0.parquet"
    exposure_path = args.output_dir / "w7_project_area_classification_bridge_v0.parquet"
    panel_path = args.output_dir / "w7_classification_exposure_panel_v0.parquet"
    ledger.to_parquet(ledger_path, index=False)
    exposure.to_parquet(exposure_path, index=False)
    out_panel.to_parquet(panel_path, index=False)
    donor_support = {}
    for donor, sub in ledger.groupby("source_family", sort=True):
        tags = sub.candidate_sector_channel.str.split("|")
        multi = sub.candidate_sector_channel_count.gt(1)
        donor_support[str(donor)] = {
            "projects": int(len(sub)),
            "unreviewed": int(sub.editorial_status.eq("unreviewed").sum()),
            "reviewed_jobs": int(sub["class"].eq("reviewed_jobs").sum()),
            "reviewed_nonjobs": int(sub["class"].eq("reviewed_nonjobs").sum()),
            "mixed_candidate_channel_projects": int(multi.sum()),
            "exclusive_candidate_channel_project_counts": {
                str(c): int((sub.candidate_sector_channel.eq(c)).sum())
                for c in sorted(set("|".join(sub.candidate_sector_channel).split("|")))
            },
            "multihot_candidate_channel_membership_counts": {
                str(c): int(tags.map(lambda t: c in t).sum())
                for c in sorted(set("|".join(sub.candidate_sector_channel).split("|")))
            },
        }
    receipt = {
        "schema": "fcv.w7.employment_classification.v0",
        "status": "VALID_STRUCTURAL_PASS_SCIENTIFIC_LABEL_GATE_FAIL",
        "jobs_regression_prohibited": True,
        "annotation_file": str(args.annotation_file) if args.annotation_file else None,
        "counts": {"projects": len(ledger), "project_area_period_links": len(exposure), "panel_cells": len(out_panel)},
        "class_counts": {str(k): int(v) for k, v in ledger["class"].value_counts(dropna=False).items()},
        "status_counts": {str(k): int(v) for k, v in ledger.editorial_status.value_counts(dropna=False).items()},
        "donor_support": donor_support,
        "inputs_sha256": {str(x): sha256(x) for x in (args.dimension, args.bridge, args.panel, args.policy)},
        "outputs_sha256": {str(x): sha256(x) for x in (ledger_path, exposure_path, panel_path)},
        "source_qualified_key": ["source_family", "source_release_id", "source_project_id"],
        "candidate_channel_is_multihot": True,
        "scientific_gate": "FAIL: no reviewed employment labels supplied" if not args.annotation_file else "REQUIRES_REVIEW_OF_REVIEWED_LABELS",
    }
    receipt_path = args.output_dir / "w7_classification_control_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("OUTPUT", ledger_path, exposure_path, panel_path, receipt_path, sep="\n")


if __name__ == "__main__":
    main()
