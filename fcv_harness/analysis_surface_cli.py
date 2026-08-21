from pathlib import Path
import argparse
import json

from .analysis_surface import (
    AnalysisSurfaceSpec,
    run_analysis_surface_checkpoint,
    write_analysis_surface_outputs,
)
from .canonical import CanonicalPanelSpec, load_sources
from .canonical_experiment import (
    CanonicalPanelExperimentSpec,
    render_experiment_preflight,
    run_experiment_preflight,
    write_experiment_preflight_outputs,
)


def _resolve(base_dir, path):
    p = Path(path)
    return p if p.is_absolute() else Path(base_dir) / p


def _assert_contract_alignment(surface_spec, experiment_path):
    raw = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    outcome = raw["outcome"]
    expected = {
        "source": surface_spec.outcome.source,
        "column": surface_spec.outcome.column,
        "absent_record_policy": surface_spec.outcome.policy,
        "verified_period_start": surface_spec.outcome.verified_period_start,
        "verified_period_end": surface_spec.outcome.verified_period_end,
    }
    mismatches = {
        key: (expected_value, outcome.get(key))
        for key, expected_value in expected.items()
        if outcome.get(key) != expected_value
    }
    if mismatches:
        raise ValueError(
            "Resolved experiment outcome contract does not match the E1 analysis "
            f"surface: {mismatches}"
        )

    # These E1-only fields are intentionally stronger than the generic D contract.
    if outcome.get("verified_geography_scope") != surface_spec.outcome.verified_geography_scope:
        raise ValueError("Resolved experiment verified_geography_scope differs from E1 surface")
    if outcome.get("coverage_basis") != surface_spec.outcome.coverage_basis:
        raise ValueError("Resolved experiment coverage_basis differs from E1 surface")


def _align_resolved_preflight_reporting(preflight, experiment_spec):
    """Keep E0 explanatory text aligned with the explicit outcome policy.

    The generic D-stage E0 table predates E1's resolved ACLED policy and its final
    outcome-coverage row used unresolved-policy wording. E1 corrects the human-facing
    note without changing any counts, eligibility, or treatment semantics.
    """
    table = preflight["input_eligibility"].copy()
    metric = "eligible rows with next-period outcome record / value"
    mask = table["metric"].eq(metric)

    policy = experiment_spec.outcome.absent_record_policy
    if policy == "zero_within_verified_coverage":
        note = (
            "Observed-record count and resolved-value count are reported separately. "
            "Absent records inside the declared verified coverage window are explicitly "
            "resolved to zero; rows outside verified coverage remain unavailable."
        )
    elif policy == "observed_records_only":
        note = (
            "Absent outcome records are explicitly excluded under the "
            "observed-records-only policy; they are not zero-filled."
        )
    else:
        note = (
            "Absent outcome records remain unresolved and are not silently converted "
            "to zero."
        )

    table.loc[mask, "note"] = note
    preflight["input_eligibility"] = table
    preflight["report"] = render_experiment_preflight(
        experiment_spec,
        table,
        preflight["support_by_period"],
    )
    return preflight


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the FCV analysis universe and ACLED area-period measurement "
            "semantics, then rerun E0 under that resolved contract. No treatment "
            "effect estimator is executed."
        )
    )
    parser.add_argument("--surface-manifest", required=True)
    parser.add_argument("--experiment-manifest", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    surface_path = _resolve(args.base_dir, args.surface_manifest)
    surface_spec = AnalysisSurfaceSpec.from_json(surface_path)
    canonical_path = _resolve(args.base_dir, surface_spec.canonical_manifest)
    canonical_spec = CanonicalPanelSpec.from_json(canonical_path)
    loaded = load_sources(canonical_spec, base_dir=args.base_dir)

    experiment_path = _resolve(args.base_dir, args.experiment_manifest)
    _assert_contract_alignment(surface_spec, experiment_path)
    experiment_spec = CanonicalPanelExperimentSpec.from_json(experiment_path)

    result = run_analysis_surface_checkpoint(
        surface_spec,
        canonical_spec,
        loaded,
        base_dir=args.base_dir,
    )
    out = write_analysis_surface_outputs(result, surface_spec, args.out_dir)

    preflight = run_experiment_preflight(
        result["panel"],
        experiment_spec,
        source_only_keys=result["source_outside"]["source_only_keys"],
    )
    preflight = _align_resolved_preflight_reporting(preflight, experiment_spec)
    preflight_dir = Path(out) / "resolved_preflight"
    write_experiment_preflight_outputs(
        preflight,
        experiment_spec,
        preflight_dir,
    )

    print(result["card"])
    print("\n--- RESOLVED E0 PREFLIGHT ---\n")
    print(preflight["report"])
    print(f"\nE1 checkpoint written to {Path(out).resolve()}")
    print(
        "No treatment-effect estimator was executed. "
        f"E0 measurement policy permits later estimation: {preflight['estimation_permitted']}"
    )


if __name__ == "__main__":
    main()
