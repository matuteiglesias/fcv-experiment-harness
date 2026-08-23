from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .canonical import CanonicalPanelSpec, load_sources
from .contracted_experiment import (
    ContractedPanelExperimentSpec,
    run_contracted_experiment_preflight,
    write_contracted_experiment_preflight_outputs,
)
from .contracted_surface import (
    ContractedAnalysisSurfaceSpec,
    run_contracted_analysis_surface_checkpoint,
    write_contracted_analysis_surface_outputs,
)
from .empirical_input import load_empirical_measurement


def _resolve(base_dir: str | Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else Path(base_dir) / value


def _load_linkage(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError("geography linkage must be CSV or Parquet")


def _assert_measurement_alignment(
    surface_spec: ContractedAnalysisSurfaceSpec,
    experiment_spec: ContractedPanelExperimentSpec,
) -> None:
    surface = surface_spec.measurement
    outcome = experiment_spec.outcome
    mismatches = {}
    for name in ("measure_id", "selectors", "value_column"):
        left = getattr(surface, name)
        right = getattr(outcome, name)
        if left != right:
            mismatches[name] = (left, right)
    if mismatches:
        raise ValueError(
            "experiment outcome does not project the same empirical measurement as E1: "
            f"{mismatches}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Project a validated contract-backed empirical measurement onto the E1 "
            "analysis universe and run the declared experiment preflight."
        )
    )
    parser.add_argument("--surface-manifest", required=True)
    parser.add_argument("--experiment-manifest", required=True)
    parser.add_argument("--empirical-data", required=True)
    parser.add_argument("--measurement-contract", required=True)
    parser.add_argument("--coverage-contract", required=True)
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--geography-linkage", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    surface_path = _resolve(args.base_dir, args.surface_manifest)
    surface_spec = ContractedAnalysisSurfaceSpec.from_json(surface_path)
    canonical_path = _resolve(args.base_dir, surface_spec.canonical_manifest)
    canonical_spec = CanonicalPanelSpec.from_json(canonical_path)
    loaded = load_sources(canonical_spec, base_dir=args.base_dir)

    experiment_path = _resolve(args.base_dir, args.experiment_manifest)
    experiment_spec = ContractedPanelExperimentSpec.from_json(experiment_path)
    _assert_measurement_alignment(surface_spec, experiment_spec)

    bundle = load_empirical_measurement(
        data_path=_resolve(args.base_dir, args.empirical_data),
        measurement_contract_path=_resolve(args.base_dir, args.measurement_contract),
        coverage_contract_path=_resolve(args.base_dir, args.coverage_contract),
        run_manifest_path=_resolve(args.base_dir, args.run_manifest),
    )
    linkage = _load_linkage(_resolve(args.base_dir, args.geography_linkage))

    result = run_contracted_analysis_surface_checkpoint(
        surface_spec,
        canonical_spec,
        loaded,
        bundle=bundle,
        geography_linkage=linkage,
        base_dir=args.base_dir,
    )
    out = write_contracted_analysis_surface_outputs(
        result,
        surface_spec,
        args.out_dir,
    )

    preflight = run_contracted_experiment_preflight(
        result["panel"],
        experiment_spec,
        bundle=bundle,
        target_geography=surface_spec.geography,
        target_period_scheme=surface_spec.period_scheme,
        geography_linkage=linkage,
        source_only_keys=result["source_outside"]["source_only_keys"],
    )
    write_contracted_experiment_preflight_outputs(
        preflight,
        experiment_spec,
        Path(out) / "resolved_preflight",
    )

    print(result["card"])
    print("\n--- CONTRACTED E0 PREFLIGHT ---\n")
    print(preflight["report"])
    print(f"\nE1 checkpoint written to {Path(out).resolve()}")
    print(
        "No treatment-effect estimator was executed. "
        f"Projected support permits later estimation: {preflight['estimation_permitted']}"
    )


if __name__ == "__main__":
    main()
