from __future__ import annotations

import argparse
from pathlib import Path

from .current_e2_falsification import (
    CurrentE2FalsificationSpec,
    run_current_e2_falsification_battery,
    write_current_e2_falsification_outputs,
)
from .current_e2_inference import (
    CurrentE2InferenceSuiteSpec,
    run_current_e2_inference_suite,
    write_current_e2_inference_outputs,
)
from .current_e2_influence import (
    CurrentE2InfluenceSpec,
    run_current_e2_influence_stability,
    write_current_e2_influence_outputs,
)
from .current_e2_reference import CurrentE2ArtifactPaths, CurrentE2ReferenceSpec
from .current_e2_scope import (
    run_scoped_current_e2_reference,
    write_scoped_current_e2_reference_outputs,
)
from .current_e2_sparse_outcomes import (
    CurrentE2SparseOutcomeSpec,
    run_current_e2_sparse_outcomes,
    write_current_e2_sparse_outcome_outputs,
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
    ap.add_argument(
        "--inference-calibration",
        action="store_true",
        help=(
            "Run the frozen R2 inference-calibration suite on the already-prepared "
            "PRIMARY frame. Requires --reference-lock and a matching R0 identity."
        ),
    )
    ap.add_argument(
        "--inference-config",
        default="config/current_e2_inference_calibration.json",
        help="Frozen R2 inference suite declaration.",
    )
    ap.add_argument(
        "--influence-stability",
        action="store_true",
        help=(
            "Run the frozen R3 country/period omission and bounded ADM2 influence suite "
            "on the exact already-prepared PRIMARY frame. Requires --reference-lock."
        ),
    )
    ap.add_argument(
        "--influence-config",
        default="config/current_e2_influence_stability.json",
        help="Frozen R3 influence suite declaration.",
    )
    ap.add_argument(
        "--falsification-battery",
        action="store_true",
        help=(
            "Run the frozen R4 negative-control battery: existing t-1 placebo, deeper t-2 "
            "placebo, future-treatment placebo, and structured within-country treatment-history null."
        ),
    )
    ap.add_argument(
        "--falsification-config",
        default="config/current_e2_falsification_battery.json",
        help="Frozen R4 falsification suite declaration.",
    )
    ap.add_argument(
        "--sparse-outcome-family",
        action="store_true",
        help=(
            "Run the frozen R5 outcome-representation family: canonical OLS fatalities, "
            "OLS VAC event count, LPM any VAC, and PPML VAC event count. Requires --reference-lock."
        ),
    )
    ap.add_argument(
        "--sparse-outcome-config",
        default="config/current_e2_sparse_outcome_family.json",
        help="Frozen R5 sparse-outcome suite declaration.",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.inference_calibration and not args.reference_lock:
        raise ValueError("--inference-calibration requires --reference-lock")
    if args.influence_stability and not args.reference_lock:
        raise ValueError("--influence-stability requires --reference-lock")
    if args.falsification_battery and not args.reference_lock:
        raise ValueError("--falsification-battery requires --reference-lock")
    if args.sparse_outcome_family and not args.reference_lock:
        raise ValueError("--sparse-outcome-family requires --reference-lock")

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

    inference = None
    inference_state = "NOT_REQUESTED"
    if args.inference_calibration:
        suite = CurrentE2InferenceSuiteSpec.from_json(args.inference_config)
        inference = run_current_e2_inference_suite(result, suite)
        inference_state = "RUN"

    influence = None
    influence_state = "NOT_REQUESTED"
    if args.influence_stability:
        influence_spec = CurrentE2InfluenceSpec.from_json(args.influence_config)
        influence = run_current_e2_influence_stability(result, influence_spec)
        influence_state = "RUN"

    falsification = None
    falsification_state = "NOT_REQUESTED"
    if args.falsification_battery:
        falsification_spec = CurrentE2FalsificationSpec.from_json(args.falsification_config)
        falsification = run_current_e2_falsification_battery(result, falsification_spec)
        falsification_state = "RUN"

    sparse_outcomes = None
    sparse_outcome_state = "NOT_REQUESTED"
    if args.sparse_outcome_family:
        sparse_spec = CurrentE2SparseOutcomeSpec.from_json(args.sparse_outcome_config)
        sparse_outcomes = run_current_e2_sparse_outcomes(result, sparse_spec)
        sparse_outcome_state = "RUN"

    write_scoped_current_e2_reference_outputs(result, args.out)
    if inference is not None:
        write_current_e2_inference_outputs(inference, args.out)
    if influence is not None:
        write_current_e2_influence_outputs(influence, args.out)
    if falsification is not None:
        write_current_e2_falsification_outputs(falsification, args.out)
    if sparse_outcomes is not None:
        write_current_e2_sparse_outcome_outputs(sparse_outcomes, args.out)

    primary = result["calibration"]["cells"][spec.primary_cell.cell_id]
    state = "PASS" if primary["estimation_permitted"] else "BLOCKED"
    scope = result["country_scope"]
    identity = result["reference_identity"]
    print(
        f"reference_id={spec.reference_id} primary_hard_gate_state={state} "
        f"analysis_countries={len(scope['analysis_country_iso3'])} "
        f"analysis_identity={identity['analysis_identity_sha256'][:12]} "
        f"execution_identity={identity['execution_identity_sha256'][:12]} "
        f"observability={result['observability_state']} "
        f"inference_calibration={inference_state} "
        f"influence_stability={influence_state} "
        f"falsification_battery={falsification_state} "
        f"sparse_outcome_family={sparse_outcome_state} out={Path(args.out).resolve()}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
