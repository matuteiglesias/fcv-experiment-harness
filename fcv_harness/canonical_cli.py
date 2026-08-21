from pathlib import Path
import argparse

from .canonical import (
    CanonicalPanelSpec,
    run_canonical_checkpoint,
    write_checkpoint_outputs,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build and characterize a canonical FCV GID×TimePeriod panel from "
            "inherited 2023 source surfaces. This command does not run a regression."
        )
    )
    parser.add_argument("--manifest", required=True, help="Canonical panel manifest JSON")
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Base directory used to resolve relative source paths (default: current directory)",
    )
    parser.add_argument("--out-dir", required=True, help="Directory for generated checkpoint artifacts")
    args = parser.parse_args()

    spec = CanonicalPanelSpec.from_json(args.manifest)
    result = run_canonical_checkpoint(spec, base_dir=args.base_dir)
    out = write_checkpoint_outputs(result, args.out_dir)

    print(result["card"])
    print(f"\nCanonical checkpoint written to {Path(out).resolve()}")
    print("No treatment effect or regression estimate was produced by this command.")


if __name__ == "__main__":
    main()
