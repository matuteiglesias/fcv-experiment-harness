from __future__ import annotations

from pathlib import Path
import argparse
import numpy as np
import pandas as pd

from .analysis_surface import AnalysisSurfaceSpec, run_analysis_surface_checkpoint
from .calibration import CalibrationMatrixSpec, run_calibration_matrix, write_calibration_outputs
from .canonical import CanonicalPanelSpec, load_sources, _period_start


def _resolve(base_dir, path):
    p = Path(path)
    return p if p.is_absolute() else Path(base_dir) / p


def _augment_stability(result):
    stability = result["stability"].copy()
    outcome_sd = {}
    for cell_id, cell_result in result["cells"].items():
        frame = cell_result["frame"]
        eligible = frame.loc[frame["eligible"]].dropna(
            subset=["outcome_value", "outcome_pre", "treatment"]
        )
        outcome_sd[cell_id] = float(
            pd.to_numeric(eligible["outcome_value"], errors="coerce").std(ddof=1)
        )

    stability["outcome_sd"] = stability["cell_id"].map(outcome_sd)
    stability["effect_sd"] = stability["effect"] / stability["outcome_sd"]
    stability["ci95_low"] = stability["effect"] - 1.96 * stability["se"]
    stability["ci95_high"] = stability["effect"] + 1.96 * stability["se"]
    stability["mde80_raw_approx"] = 2.80 * stability["se"]
    stability["mde80_sd_approx"] = stability["mde80_raw_approx"] / stability["outcome_sd"]
    result["stability"] = stability
    return result


def _agreement_row(df, definition, period_label):
    a = df[f"wbad_{definition}"].astype("boolean").fillna(False).astype(bool)
    b = df[f"wbkg_{definition}"].astype("boolean").fillna(False).astype(bool)
    both = int((a & b).sum())
    a_only = int((a & ~b).sum())
    b_only = int((~a & b).sum())
    neither = int((~a & ~b).sum())
    union = both + a_only + b_only
    return {
        "definition": definition,
        "TimePeriod": period_label,
        "rows": int(len(df)),
        "both_treated": both,
        "wbad_only": a_only,
        "wbkg_only": b_only,
        "neither": neither,
        "treated_union": union,
        "jaccard_treated": both / union if union else np.nan,
        "exact_agreement_share": (both + neither) / len(df) if len(df) else np.nan,
    }


def _build_wb_measurement_agreement(panel, matrix_spec):
    years = panel[matrix_spec.period_col].astype(str).map(_period_start)
    mask = years.between(
        _period_start(matrix_spec.treatment_period_start),
        _period_start(matrix_spec.treatment_period_end),
        inclusive="both",
    )
    p = panel.loc[mask].copy()
    rows = []
    for definition in ["record_present", "amount_positive"]:
        rows.append(_agreement_row(p, definition, "OVERALL"))
        for period, g in p.groupby(matrix_spec.period_col, sort=False):
            rows.append(_agreement_row(g, definition, str(period)))
    return pd.DataFrame(rows)


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
    result = _augment_stability(result)
    agreement = _build_wb_measurement_agreement(surface["panel"], matrix_spec)
    out = write_calibration_outputs(result, matrix_spec, args.out_dir)
    agreement.to_csv(Path(out) / "wb_measurement_agreement.csv", index=False)

    print(result["card"])
    print("\n--- WB MEASUREMENT AGREEMENT ---\n")
    print(agreement.loc[agreement["TimePeriod"] == "OVERALL"].to_string(index=False))
    print(f"\nE2 calibration checkpoint written to {Path(out).resolve()}")
    estimated = int(result["stability"]["estimated"].sum())
    print(
        f"Real calibration coefficients produced for {estimated}/{len(result['stability'])} "
        "predeclared cells. Any blocked cell remains visible in measurement_stability.csv."
    )


if __name__ == "__main__":
    main()
