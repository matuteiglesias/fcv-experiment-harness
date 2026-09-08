from __future__ import annotations

import argparse
from pathlib import Path

from .current_e2_reference import (
    CurrentE2ArtifactPaths,
    CurrentE2ReferenceSpec,
    run_current_e2_reference,
)
from .current_e2_robustness import (
    CurrentE2RobustnessSuite,
    run_current_e2_robustness,
    write_current_e2_robustness_outputs,
)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Run the predeclared current GeoGCDF→ACLED E2 robustness suite on "
            "the exact governed artifacts used by the canonical reference."
        )
    )
    ap.add_argument("--config", required=True, help="Canonical current-E2 reference config.")
    ap.add_argument("--robustness-config", required=True)
    ap.add_argument("--geography-data", required=True)
    ap.add_argument("--geography-manifest", required=True)
    ap.add_argument("--geography-dataset-id", default="gadm_native_adm2")
    ap.add_argument("--treatment-data", required=True)
    ap.add_argument("--treatment-measurement-contract", required=True)
    ap.add_argument("--treatment-coverage-contract", required=True)
    ap.add_argument("--treatment-manifest", required=True)
    ap.add_argument(
        "--treatment-dataset-id",
        default="investments.aiddata_geogcdf.commitment_area_period",
    )
    ap.add_argument("--outcome-data", required=True)
    ap.add_argument("--outcome-measurement-contract", required=True)
    ap.add_argument("--outcome-coverage-contract", required=True)
    ap.add_argument("--outcome-manifest", required=True)
    ap.add_argument(
        "--outcome-dataset-id",
        default="violence.acled.area_period_native_event_certified",
    )
    ap.add_argument("--out", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    base_spec = CurrentE2ReferenceSpec.from_json(args.config)
    suite = CurrentE2RobustnessSuite.from_json(args.robustness_config)
    paths = CurrentE2ArtifactPaths(
        geography_data_path=Path(args.geography_data),
        geography_manifest_path=Path(args.geography_manifest),
        geography_dataset_id=args.geography_dataset_id,
        treatment_data_path=Path(args.treatment_data),
        treatment_measurement_contract_path=Path(args.treatment_measurement_contract),
        treatment_coverage_contract_path=Path(args.treatment_coverage_contract),
        treatment_manifest_path=Path(args.treatment_manifest),
        treatment_dataset_id=args.treatment_dataset_id,
        outcome_data_path=Path(args.outcome_data),
        outcome_measurement_contract_path=Path(args.outcome_measurement_contract),
        outcome_coverage_contract_path=Path(args.outcome_coverage_contract),
        outcome_manifest_path=Path(args.outcome_manifest),
        outcome_dataset_id=args.outcome_dataset_id,
    )
    canonical = run_current_e2_reference(base_spec, paths, run_observability=False)
    result = run_current_e2_robustness(canonical, suite)
    write_current_e2_robustness_outputs(result, args.out)
    print(
        f"suite_id={suite.suite_id} variants={len(suite.variants)} "
        f"out={Path(args.out).resolve()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
