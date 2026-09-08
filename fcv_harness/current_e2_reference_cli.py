from __future__ import annotations

import argparse
from pathlib import Path

from .current_e2_reference import CurrentE2ArtifactPaths, CurrentE2ReferenceSpec
from .current_e2_scope import (
    run_scoped_current_e2_reference,
    write_scoped_current_e2_reference_outputs,
)
from .reference_identity import (
    CurrentE2ReferenceLock,
    build_current_e2_reference_identity,
)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Run the frozen current GeoGCDF→ACLED E2 reference from governed artifacts."
    )
    ap.add_argument("--config", required=True)
    ap.add_argument(
        "--reference-lock",
        help=(
            "Optional fail-closed lock for canonical config/upstream artifact hashes. "
            "Use config/current_e2_reference_lock.json for current_e2_reference_v1."
        ),
    )
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
    ap.add_argument(
        "--observability",
        action="store_true",
        help="Run the frozen observability grid only if the PRIMARY hard gates permit estimation.",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    spec = CurrentE2ReferenceSpec.from_json(args.config)
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
    result = run_scoped_current_e2_reference(
        spec,
        paths,
        run_observability=args.observability,
    )
    lock = CurrentE2ReferenceLock.from_json(args.reference_lock) if args.reference_lock else None
    result["reference_identity"] = build_current_e2_reference_identity(
        result,
        config_path=args.config,
        lock=lock,
    )
    write_scoped_current_e2_reference_outputs(result, args.out)
    primary = result["calibration"]["cells"][spec.primary_cell.cell_id]
    state = "PASS" if primary["estimation_permitted"] else "BLOCKED"
    scope = result["country_scope"]
    identity = result["reference_identity"]
    print(
        f"reference_id={spec.reference_id} primary_hard_gate_state={state} "
        f"analysis_countries={len(scope['analysis_country_iso3'])} "
        f"analysis_identity={identity['analysis_identity_sha256'][:12]} "
        f"execution_identity={identity['execution_identity_sha256'][:12]} "
        f"observability={result['observability_state']} out={Path(args.out).resolve()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
