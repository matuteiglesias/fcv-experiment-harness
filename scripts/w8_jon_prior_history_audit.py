#!/usr/bin/env python3
"""Outcome-history and weight-concentration audit for immutable W8 matched samples.

This reads *existing* W5 previous-biennium VAC; it does not shift exposure
timing, invent a new policy, or turn previous VAC into a true pre-treatment test.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fcv_harness.w7_proxy_experiments import sha256_file


def summarize(d: pd.DataFrame) -> dict:
    req = {"geo_uid", "period_id", "country_iso3", "jon_group",
           "any_vac_next", "vac_events_prior", "analysis_weight", "had_source_before"}
    if not req.issubset(d):
        raise ValueError(f"missing matched sample audit fields: {sorted(req - set(d))}")
    if d.duplicated(["geo_uid", "period_id"]).any():
        raise ValueError("duplicated matched geographic period")
    if set(d.jon_group) != {"J", "O", "N"}:
        raise ValueError("J/O/N must all be represented")
    z = {}
    for g in ("J", "O", "N"):
        x = d.loc[d.jon_group.eq(g)].copy()
        w = x.analysis_weight.to_numpy(dtype=float)
        if not np.all(np.isfinite(w)) or (w < 0).any() or not np.isclose(w.sum(), 1):
            raise ValueError("invalid shared within-group weights")
        prior = x.vac_events_prior.gt(0).astype(int).to_numpy()
        nxt = x.any_vac_next.to_numpy(dtype=int)
        z[g] = {
            "n_cells": int(len(x)),
            "effective_weighted_N": float(1 / (w @ w)),
            "previous_vac_incidence_pct": float(100 * np.dot(w, prior)),
            "next_vac_incidence_pct": float(100 * np.dot(w, nxt)),
            "change_in_measured_incidence_pp": float(100 * np.dot(w, nxt - prior)),
            "fraction_had_earlier_source_project": float(x.had_source_before.mean()),
            "largest_single_cell_weight_pct": float(100 * np.max(w)),
            "top_10_cell_weight_pct": float(100 * np.sort(w)[-10:].sum()),
            "top_100_cell_weight_pct": float(100 * np.sort(w)[-100:].sum()),
        }
    deltas = {}
    for tag, a, b in (("J_minus_N", "J", "N"), ("O_minus_N", "O", "N"), ("J_minus_O", "J", "O")):
        pp = z[a]["previous_vac_incidence_pct"] - z[b]["previous_vac_incidence_pct"]
        nx = z[a]["next_vac_incidence_pct"] - z[b]["next_vac_incidence_pct"]
        deltas[tag] = {"previous_gap_pp": pp, "next_gap_pp": nx,
                       "change_in_gap_pp": nx - pp}
    for fld in ("previous_gap_pp", "next_gap_pp", "change_in_gap_pp"):
        err = deltas["J_minus_O"][fld] - (deltas["J_minus_N"][fld] - deltas["O_minus_N"][fld])
        if abs(err) > 1e-10:
            raise ValueError("common-weight three-difference identity failure")
    return {
        "groups": z, "contrasts": deltas, "not_pre_treatment_for_all": True,
        "interpretation": "previous VAC may follow older projects in J/O; differences in outcomes are not causal effects",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--china-matched", type=Path, required=True)
    ap.add_argument("--world-bank-matched", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.output_dir.exists():
        ap.error("immutable output directory exists")
    inputs = {"china": args.china_matched, "world_bank": args.world_bank_matched}
    if any(not p.is_file() for p in inputs.values()):
        ap.error("matched source file missing")
    sources = {name: sha256_file(p) for name, p in inputs.items()}
    result = {"schema": "fcv.w8.jon_prior_history_audit.v0",
              "source_input_sha256": sources,
              "audit": {name: summarize(pd.read_parquet(p)) for name, p in inputs.items()}}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    path = args.output_dir / "w8_prior_history_diagnostics.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (args.output_dir / "w8_prior_audit_receipt.json").write_text(
        json.dumps({"input_sha256": sources, "output_sha256": sha256_file(path),
                    "immutable": True}, indent=2, sort_keys=True) + "\n"
    )
    print("AUDITED", str(path), "DONORS", list(result["audit"]))


if __name__ == "__main__":
    main()
