from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .calibration import CalibrationMatrixSpec
from .canonical import CanonicalPanelSpec, _period_start, load_sources
from .contracted_calibration import (
    run_contracted_calibration_matrix,
    write_contracted_calibration_outputs,
)
from .contracted_surface import (
    ContractedAnalysisSurfaceSpec,
    run_contracted_analysis_surface_checkpoint,
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


def _augment_stability(result: dict) -> dict:
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
    stability["mde80_sd_approx"] = (
        stability["mde80_raw_approx"] / stability["outcome_sd"]
    )
    result["stability"] = stability
    return result


def _agreement_row(df: pd.DataFrame, definition: str, period_label: str) -> dict:
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


def _build_wb_measurement_agreement(
    panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
) -> pd.DataFrame:
    years = panel[matrix_spec.period_col].astype(str).map(_period_start)
    mask = years.between(
        _period_start(matrix_spec.treatment_period_start),
        _period_start(matrix_spec.treatment_period_end),
        inclusive="both",
    )
    subset = panel.loc[mask].copy()
    rows = []
    for definition in ["record_present", "amount_positive"]:
        rows.append(_agreement_row(subset, definition, "OVERALL"))
        for period, group in subset.groupby(matrix_spec.period_col, sort=False):
            rows.append(_agreement_row(group, definition, str(period)))
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the predeclared WB calibration matrix using a contract-backed "
            "empirical outcome projection. Existing estimator and calibration "
            "semantics are unchanged."
        )
    )
    parser.add_argument("--matrix-manifest", required=True)
    parser.add_argument("--empirical-data", required=True)
    parser.add_argument("--measurement-contract", required=True)
    parser.add_argument("--coverage-contract", required=True)
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--geography-linkage", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    matrix_path = _resolve(args.base_dir, args.matrix_manifest)
    matrix_spec = CalibrationMatrixSpec.from_json(matrix_path)
    surface_path = _resolve(args.base_dir, matrix_spec.surface_manifest)
    surface_spec = ContractedAnalysisSurfaceSpec.from_json(surface_path)
    canonical_path = _resolve(args.base_dir, surface_spec.canonical_manifest)
    canonical_spec = CanonicalPanelSpec.from_json(canonical_path)
    loaded = load_sources(canonical_spec, base_dir=args.base_dir)

    bundle = load_empirical_measurement(
        data_path=_resolve(args.base_dir, args.empirical_data),
        measurement_contract_path=_resolve(args.base_dir, args.measurement_contract),
        coverage_contract_path=_resolve(args.base_dir, args.coverage_contract),
        run_manifest_path=_resolve(args.base_dir, args.run_manifest),
    )
    linkage = _load_linkage(_resolve(args.base_dir, args.geography_linkage))

    surface = run_contracted_analysis_surface_checkpoint(
        surface_spec,
        canonical_spec,
        loaded,
        bundle=bundle,
        geography_linkage=linkage,
        base_dir=args.base_dir,
    )
    hard_surface_red = surface["gates"].loc[
        surface["gates"]["gate"].isin(
            [
                "U0_UNIVERSE_DECLARED",
                "U2_COUNTRY_IDENTITY",
                "M0_CONTRACTED_MEASUREMENT_IDENTITY",
                "M1_PROJECTION_ACCOUNTING",
            ]
        )
        & surface["gates"]["status"].eq("RED")
    ]
    if len(hard_surface_red):
        raise RuntimeError(
            "E2 blocked by hard contracted E1 surface gate(s): "
            + ", ".join(hard_surface_red["gate"].tolist())
        )

    result = run_contracted_calibration_matrix(
        surface["panel"],
        matrix_spec,
        surface_spec,
        surface["gates"],
        surface["source_outside"]["source_only_keys"],
        canonical_spec.panel_id,
        bundle=bundle,
        geography_linkage=linkage,
    )
    result = _augment_stability(result)
    agreement = _build_wb_measurement_agreement(surface["panel"], matrix_spec)
    out = write_contracted_calibration_outputs(result, matrix_spec, args.out_dir)
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
