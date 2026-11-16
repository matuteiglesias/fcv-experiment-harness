#!/usr/bin/env python3
"""Read-only, aggregate-only W7 audit of W5 VAC scale and rarity."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED = {
    "geo_uid", "country_iso3", "period_id", "cn_project_count", "wb_project_count",
    "any_vac_next", "vac_events_next", "vac_fatalities_next", "vac_events_prior",
}
COUNT_COLUMNS = [
    "cn_project_count", "wb_project_count", "vac_events_next",
    "vac_fatalities_next", "vac_events_prior",
]
PERIODS_EXPECTED = 7
LIMITS = (
    "Unit is an ADM2 geographic unit x financing biennium; outcomes are next-biennium VAC.",
    "Counts are recorded events/fatalities and project counts, NOT per capita, NOT a jobs treatment, "
    "and cannot claim population affected. Low-count cells remain informative.",
    "Finance approval/commitment is not realized expenditure, implementation, local employment, or wages; "
    "this is a descriptive scale diagnostic with no p-values and no causal claim.",
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _validate(frame: pd.DataFrame) -> None:
    missing = sorted(REQUIRED - set(frame.columns))
    if missing:
        _fail("missing required columns: " + ", ".join(missing))
    if frame.empty:
        _fail("input has no rows")
    for column in ["geo_uid", "country_iso3", "period_id"]:
        if frame[column].isna().any() or (frame[column].astype(str).str.strip() == "").any():
            _fail(f"missing or blank values in {column}")
    if not frame["country_iso3"].astype(str).str.fullmatch(r"[A-Z]{3}").all():
        _fail("invalid country_iso3 values; expected uppercase ISO3 strings")
    if frame.duplicated(["geo_uid", "period_id", "country_iso3"]).any():
        _fail("duplicate geo_uid+period_id+country_iso3 cells")
    for column in COUNT_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or (~values.map(math.isfinite)).any():
            _fail(f"missing or non-finite values in {column}")
        if (values < 0).any() or (values != values.round()).any():
            _fail(f"negative or non-integer count in {column}")
    any_values = pd.to_numeric(frame["any_vac_next"], errors="coerce")
    if any_values.isna().any() or (~any_values.map(math.isfinite)).any() or not any_values.isin([0, 1]).all():
        _fail("any_vac_next must contain only 0/1 or boolean values")
    if frame["period_id"].nunique() != PERIODS_EXPECTED:
        _fail(f"expected {PERIODS_EXPECTED} financing periods")
    expected_any = pd.to_numeric(frame["vac_events_next"]) > 0
    if not (any_values.astype(bool) == expected_any).all():
        _fail("inconsistent any_vac_next=(vac_events_next>0)")


def _quantiles(values: pd.Series) -> dict[str, float]:
    return {key: float(values.quantile(q, interpolation="linear")) for key, q in
            (("p50", .50), ("p90", .90), ("p99", .99), ("max", 1.0))}


def _arm_report(frame: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    sub = frame.loc[mask]
    events = sub["vac_events_next"].sum()
    return {
        "cells": int(len(sub)),
        "any_vac_cells": int(sub["any_vac_next"].sum()),
        "any_vac_fraction": float(sub["any_vac_next"].mean()) if len(sub) else None,
        "event_count_sum": int(events),
        "fatality_sum": int(sub["vac_fatalities_next"].sum()),
    }


def audit_frame(frame: pd.DataFrame, input_sha256: str) -> dict[str, Any]:
    _validate(frame)
    frame = frame.copy()
    for column in COUNT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column]).astype("int64")
    frame["any_vac_next"] = pd.to_numeric(frame["any_vac_next"]).astype("int64")
    cn = frame["cn_project_count"] > 0
    wb = frame["wb_project_count"] > 0
    arms = {"cn_exclusive": cn & ~wb, "wb_exclusive": wb & ~cn, "both": cn & wb, "neither": ~cn & ~wb}
    events = frame.loc[frame["vac_events_next"] > 0, "vac_events_next"]
    total_events = int(frame["vac_events_next"].sum())
    top_n = max(1, math.ceil(len(frame) * .01)) if total_events else 0
    top_sum = int(events.nlargest(top_n).sum()) if top_n else 0
    period_summary = {}
    for period, sub in frame.groupby("period_id", sort=True):
        period_summary[str(period)] = {
            "cells": int(len(sub)),
            "geographic_units": int(sub["geo_uid"].nunique()),
            "any_vac_cells": int(sub["any_vac_next"].sum()),
            "any_vac_fraction": float(sub["any_vac_next"].mean()),
            "event_count_sum": int(sub["vac_events_next"].sum()),
            "fatality_sum": int(sub["vac_fatalities_next"].sum()),
        }
    result = {
        "schema": "w7_vac_scale_audit.v1",
        "status": "PASS",
        "input": {"sha256": input_sha256},
        "measurement_limits": list(LIMITS),
        "scale": {
            "cells": int(len(frame)), "distinct_geographic_units": int(frame.geo_uid.nunique()),
            "countries": int(frame.country_iso3.nunique()), "periods": int(frame.period_id.nunique()),
            "period_cell_counts": {str(k): int(v) for k, v in frame.groupby("period_id", sort=True).size().items()},
        },
        "donor_cells_unadjusted": {name: _arm_report(frame, mask) for name, mask in arms.items()},
        "overall_vac": {
            "cells": int(len(frame)), "any_vac_cells": int(frame.any_vac_next.sum()),
            "any_vac_fraction": float(frame.any_vac_next.mean()),
            "event_count_sum": total_events, "fatality_sum": int(frame.vac_fatalities_next.sum()),
            "prior_event_count_sum": int(frame.vac_events_prior.sum()),
        },
        "positive_event_cells": {"cells": int(len(events)), "event_count_quantiles": _quantiles(events) if len(events) else {},
                                  "top_1_percent_cell_count": top_n,
                                  "top_1_percent_event_count_fraction": float(top_sum / total_events) if total_events else 0.0},
        "periodwise_outcomes": period_summary,
    }
    return result


def audit(input_path: Path) -> dict[str, Any]:
    raw = input_path.read_bytes()
    result = audit_frame(pd.read_parquet(input_path), hashlib.sha256(raw).hexdigest())
    result["input"]["path"] = str(input_path)
    return result


def encode_result(result: dict[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate-only W7 VAC scale/rarity audit")
    parser.add_argument("--input-parquet", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()
    if args.input_parquet is None:
        parser.error("--input-parquet is required")
    result = audit(args.input_parquet)
    encoded = encode_result(result)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
