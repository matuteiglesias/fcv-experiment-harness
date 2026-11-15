"""Command line interface for the W5 China/WB source-specific VAC paper experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .w5_china_wb_vac import run_w5


def main() -> None:
    parser = argparse.ArgumentParser(description="W5 China/WB E0 or E1 (source-locked)")
    parser.add_argument("--spec", type=Path, default=Path("config/w5_china_wb_vac_v1.json"))
    parser.add_argument("--investment", type=Path, required=True)
    parser.add_argument("--acled", type=Path, required=True)
    parser.add_argument("--investment-contract", type=Path, required=True)
    parser.add_argument("--acled-contract", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=["e0", "e1"], default="e0")
    args = parser.parse_args()
    result = run_w5(
        args.spec, args.investment, args.acled,
        args.investment_contract, args.acled_contract, args.out_dir, args.phase,
    )
    summary = {
        "status": "E1_DONE" if args.phase == "e1" else "E0_DONE",
        "gate": result["e0"]["e0_gate"],
        "rows": result["e0"]["rows"],
        "countries": result["e0"]["countries"],
        "same_country_period_both_exclusive_arms": result["e0"]["country_periods_both_exclusive_arms"],
        "out_dir": str(args.out_dir),
        "primary": result["e1"]["results"][-1] if result["e1"] else None,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
