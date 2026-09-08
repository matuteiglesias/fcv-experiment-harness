from __future__ import annotations

import argparse

from .briggs_lane_b import (
    load_briggs_lane_b_spec,
    load_independent_region_frame,
    run_briggs_lane_b,
    write_briggs_lane_b_run,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the Briggs (2016) Lane B external calibration on an independent region frame."
    )
    p.add_argument("--input", required=True, help="Independent reconstructed CSV or Parquet frame")
    p.add_argument(
        "--config", default="config/briggs_2016_lane_b.json", help="Frozen Briggs Lane B config"
    )
    p.add_argument("--out", required=True, help="Output directory")
    return p


def main() -> int:
    args = parser().parse_args()
    spec = load_briggs_lane_b_spec(args.config)
    frame = load_independent_region_frame(args.input)
    result = run_briggs_lane_b(frame, spec)
    output = write_briggs_lane_b_run(
        result,
        output_dir=args.out,
        input_path=args.input,
        config_path=args.config,
    )
    rich = result.coefficients[
        result.coefficients["model_id"].eq("model_3_log_value")
        & result.coefficients["term"].eq("log_richest")
    ].iloc[0]
    print(
        f"reference_id={spec.reference_id} countries={result.diagnostics['country_count']} "
        f"regions={result.diagnostics['region_count']} "
        f"model3_log_richest={rich['coefficient']:.6g} se={rich['se']:.6g} out={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
