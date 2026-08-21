from __future__ import annotations

from pathlib import Path
import argparse

from .analysis_surface import AnalysisSurfaceSpec, run_analysis_surface_checkpoint
from .calibration import CalibrationMatrixSpec, run_calibration_matrix, write_calibration_outputs
from .canonical import CanonicalPanelSpec, load_sources


def _resolve(base_dir, path):
    p = Path(path)
    return p if p.is_absolute() else Path(base_dir) / p


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run the predeclared WB→ACLED measurement calibration matrix on the "
            "resolved E1 analysis surface. Gates run before each real coefficient."
        )
    )
    parser.add_argument("--matrix-manifest", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    matrix_path = _resolve(args.base_dir, args.matrix_manifest)
    matrix_spec = CalibrationMatrixSpec.from_json(matrix_path)

    surface_path = _resolve(args.base_dir, matrix_spec.surface_manifest)
    surface_spec = AnalysisSurfaceSpec.from_json(surface_path)
    canonical_path = _resolve(args.base_dir, surface_spec.canonical_manifest)
    canonical_spec = CanonicalPanelSpec.from_json(canonical_path)
    loaded = load_sources(canonical_spec, base_dir=args.base_dir)

    surface = run_analysis_surface_checkpoint(
        surface_spec,
        canonical_spec,
        loaded,
        base_dir=args.base_dir,
    )
    hard_surface_red = surface["gates"].loc[
        surface["gates"]["gate"].isin(
            [
                "U0_UNIVERSE_DECLARED",
                "U2_COUNTRY_IDENTITY",
                "A0_ACLED_POLICY_EXPLICIT",
                "A1_ACLED_RESOLUTION_COMPLETENESS",
            ]
        )
        & surface["gates"]["status"].eq("RED")
    ]
    if len(hard_surface_red):
        raise RuntimeError(
            "E2 blocked by hard E1 surface gate(s): "
            + ", ".join(hard_surface_red["gate"].tolist())
        )

    result = run_calibration_matrix(
        surface["panel"],
        matrix_spec,
        surface_spec,
        surface["gates"],
        surface["source_outside"]["source_only_keys"],
        canonical_spec.panel_id,
    )
    out = write_calibration_outputs(result, matrix_spec, args.out_dir)

    print(result["card"])
    print(f"\nE2 calibration checkpoint written to {Path(out).resolve()}")
    estimated = int(result["stability"]["estimated"].sum())
    print(
        f"Real calibration coefficients produced for {estimated}/{len(result['stability'])} "
        "predeclared cells. Any blocked cell remains visible in measurement_stability.csv."
    )


if __name__ == "__main__":
    main()
