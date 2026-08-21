from pathlib import Path
import argparse

from .canonical import CanonicalPanelSpec, run_canonical_checkpoint
from .canonical_experiment import (
    CanonicalPanelExperimentSpec,
    run_experiment_preflight,
    write_experiment_preflight_outputs,
)
from .lattice_diagnostics import (
    build_source_outside_lattice_diagnostics,
    write_source_outside_lattice_diagnostics,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resolve an FCV experiment over the canonical panel as an explicit "
            "measurement/eligibility preflight. This command never runs a regression."
        )
    )
    parser.add_argument("--canonical-manifest", required=True)
    parser.add_argument("--experiment-manifest", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    canonical_spec = CanonicalPanelSpec.from_json(args.canonical_manifest)
    experiment_spec = CanonicalPanelExperimentSpec.from_json(args.experiment_manifest)
    if experiment_spec.panel_id != canonical_spec.panel_id:
        raise ValueError(
            f"Experiment expects panel {experiment_spec.panel_id!r}, but canonical "
            f"manifest declares {canonical_spec.panel_id!r}."
        )

    checkpoint = run_canonical_checkpoint(canonical_spec, base_dir=args.base_dir)
    diagnostics = build_source_outside_lattice_diagnostics(
        canonical_spec, checkpoint["loaded"]
    )
    result = run_experiment_preflight(
        checkpoint["panel"],
        experiment_spec,
        source_only_keys=diagnostics["source_only_keys"],
    )

    out = write_experiment_preflight_outputs(result, experiment_spec, args.out_dir)
    write_source_outside_lattice_diagnostics(diagnostics, out)

    print(result["report"])
    print(f"\nExperiment preflight written to {Path(out).resolve()}")
    if result["estimation_permitted"]:
        print("Measurement policy is explicit. No estimator was run by this command.")
    else:
        print("ESTIMATION BLOCKED: outcome absent-record policy remains unresolved.")


if __name__ == "__main__":
    main()
