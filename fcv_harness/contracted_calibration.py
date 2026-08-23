from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .calibration import (
    CalibrationCellSpec,
    CalibrationMatrixSpec,
    calibration_estimate,
    placebo_estimate,
    render_calibration_card,
    run_calibration_gates,
    synthetic_signal_recovery,
)
from .canonical_experiment import EligibilitySpec, TreatmentMeasurementSpec
from .contracted_experiment import (
    ContractedPanelExperimentSpec,
    run_contracted_experiment_preflight,
)
from .contracted_surface import ContractedAnalysisSurfaceSpec
from .empirical_input import EmpiricalMeasurementBundle
from .measurement_projection import project_empirical_measurement, write_projection_report


def build_contracted_cell_experiment_spec(
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: ContractedAnalysisSurfaceSpec,
    panel_id: str,
    cell: CalibrationCellSpec,
) -> ContractedPanelExperimentSpec:
    outcome = replace(
        surface_spec.measurement,
        role="outcome",
        timing_offset=1,
        output_column="outcome_value",
    )
    return ContractedPanelExperimentSpec(
        experiment_id=f"{matrix_spec.matrix_id}__{cell.cell_id}",
        panel_id=panel_id,
        treatment=TreatmentMeasurementSpec(
            source=cell.source,
            definition=cell.definition,
            annotation_version=matrix_spec.annotation_version,
        ),
        eligibility=EligibilitySpec(
            treatment_period_start=matrix_spec.treatment_period_start,
            treatment_period_end=matrix_spec.treatment_period_end,
        ),
        outcome=outcome,
        covariates=(),
        unit_col=matrix_spec.unit_col,
        period_col=matrix_spec.period_col,
        country_col=matrix_spec.country_col,
    )


def run_contracted_calibration_cell(
    resolved_panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: ContractedAnalysisSurfaceSpec,
    surface_gates: pd.DataFrame,
    source_only_keys: pd.DataFrame,
    panel_id: str,
    cell: CalibrationCellSpec,
    *,
    bundle: EmpiricalMeasurementBundle,
    geography_linkage: pd.DataFrame,
    seed_offset: int = 0,
) -> dict:
    experiment = build_contracted_cell_experiment_spec(
        matrix_spec,
        surface_spec,
        panel_id,
        cell,
    )
    preflight = run_contracted_experiment_preflight(
        resolved_panel,
        experiment,
        bundle=bundle,
        target_geography=surface_spec.geography,
        target_period_scheme=surface_spec.period_scheme,
        geography_linkage=geography_linkage,
        source_only_keys=source_only_keys,
    )
    frame = preflight["frame"].copy()

    pre_use = replace(
        experiment.outcome,
        role="pre_outcome",
        timing_offset=-1,
        output_column="outcome_pre",
    )
    pre_projection = project_empirical_measurement(
        bundle,
        resolved_panel[[matrix_spec.unit_col, matrix_spec.period_col]],
        pre_use,
        target_geography=surface_spec.geography,
        target_period_scheme=surface_spec.period_scheme,
        target_unit_col=matrix_spec.unit_col,
        target_period_col=matrix_spec.period_col,
        geography_linkage=geography_linkage,
    )
    frame["outcome_pre"] = pre_projection.frame["outcome_pre"].to_numpy()
    frame["outcome_pre_period"] = pre_projection.frame["measurement_period_id"].to_numpy()
    frame["outcome_pre_status"] = pre_projection.frame["projection_status"].to_numpy()
    frame["outcome_pre_detail"] = pre_projection.frame["projection_detail"].to_numpy()

    gate_result = run_calibration_gates(
        frame,
        preflight,
        matrix_spec,
        surface_gates,
        seed_offset=seed_offset,
    )
    estimate = (
        calibration_estimate(frame, matrix_spec)
        if gate_result["estimation_permitted"]
        else {
            "ok": False,
            "reason": "Hard calibration gate RED: "
            + ", ".join(gate_result["hard_red_gates"]),
        }
    )
    return {
        "cell": cell,
        "experiment_spec": experiment,
        "preflight": preflight,
        "frame": frame,
        "post_projection": preflight["projection"],
        "pre_projection": pre_projection,
        **gate_result,
        "estimate": estimate,
    }


def _stability_row(result: dict) -> dict:
    cell = result["cell"]
    estimate = result["estimate"]
    placebo = result["placebo"]
    recovery = result["signal_recovery"]
    support = result["support_by_period"]
    mixed = (
        int(((support["treated"] > 0) & (support["control"] > 0)).sum())
        if len(support)
        else 0
    )
    red = result["gates"].loc[
        result["gates"]["status"].eq("RED"), "gate"
    ].tolist()
    yellow = result["gates"].loc[
        result["gates"]["status"].eq("YELLOW"), "gate"
    ].tolist()
    return {
        "cell_id": cell.cell_id,
        "role": cell.role,
        "source": cell.source,
        "treatment_definition": cell.definition,
        "estimated": bool(estimate.get("ok")),
        "effect": estimate.get("effect", np.nan),
        "se": estimate.get("se", np.nan),
        "n": estimate.get("n", np.nan),
        "n_units": estimate.get("n_units", np.nan),
        "treated": estimate.get("n_treated", np.nan),
        "control": estimate.get("n_control", np.nan),
        "mixed_support_periods": f"{mixed}/{len(support)}",
        "placebo_std_abs_effect": placebo.get("std_abs_effect", np.nan),
        "signal_recovery": recovery.get("recovery_probability", np.nan),
        "hard_gate_state": "PASS" if result["estimation_permitted"] else "BLOCKED",
        "red_gates": ";".join(red),
        "yellow_gates": ";".join(yellow),
        "estimate_reason": estimate.get("reason", ""),
    }


def run_contracted_calibration_matrix(
    resolved_panel: pd.DataFrame,
    matrix_spec: CalibrationMatrixSpec,
    surface_spec: ContractedAnalysisSurfaceSpec,
    surface_gates: pd.DataFrame,
    source_only_keys: pd.DataFrame,
    panel_id: str,
    *,
    bundle: EmpiricalMeasurementBundle,
    geography_linkage: pd.DataFrame,
) -> dict:
    results = {}
    for index, cell in enumerate(matrix_spec.cells):
        results[cell.cell_id] = run_contracted_calibration_cell(
            resolved_panel,
            matrix_spec,
            surface_spec,
            surface_gates,
            source_only_keys,
            panel_id,
            cell,
            bundle=bundle,
            geography_linkage=geography_linkage,
            seed_offset=1000 * index,
        )
    stability = pd.DataFrame(
        [_stability_row(results[cell.cell_id]) for cell in matrix_spec.cells]
    )
    card = render_calibration_card(matrix_spec, stability)
    return {"cells": results, "stability": stability, "card": card}


def write_contracted_calibration_outputs(
    result: dict,
    matrix_spec: CalibrationMatrixSpec,
    out_dir: str | Path,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["stability"].to_csv(out / "measurement_stability.csv", index=False)
    (out / "calibration_matrix_card.md").write_text(result["card"], encoding="utf-8")

    gate_rows = []
    for cell_id, cell_result in result["cells"].items():
        cell_dir = out / "cells" / cell_id
        cell_dir.mkdir(parents=True, exist_ok=True)
        gates = cell_result["gates"].copy()
        gates.insert(0, "cell_id", cell_id)
        gate_rows.append(gates)
        gates.to_csv(cell_dir / "gates.csv", index=False)
        cell_result["support_by_period"].to_csv(
            cell_dir / "support_by_period.csv", index=False
        )
        pd.DataFrame([cell_result["placebo"]]).to_csv(
            cell_dir / "placebo.csv", index=False
        )
        pd.DataFrame([cell_result["signal_recovery"]]).to_csv(
            cell_dir / "signal_recovery.csv", index=False
        )
        pd.DataFrame([cell_result["estimate"]]).to_csv(
            cell_dir / "estimate.csv", index=False
        )
        cell_result["frame"].head(500).to_csv(
            cell_dir / "analysis_frame_sample.csv", index=False
        )
        (cell_dir / "experiment_contract.json").write_text(
            json.dumps(cell_result["experiment_spec"].to_dict(), sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        write_projection_report(
            cell_result["post_projection"].report,
            cell_dir / "outcome_post_projection_report.json",
        )
        write_projection_report(
            cell_result["pre_projection"].report,
            cell_dir / "outcome_pre_projection_report.json",
        )

    if gate_rows:
        pd.concat(gate_rows, ignore_index=True).to_csv(
            out / "cell_gates.csv", index=False
        )
    return out


__all__ = [
    "build_contracted_cell_experiment_spec",
    "run_contracted_calibration_cell",
    "run_contracted_calibration_matrix",
    "write_contracted_calibration_outputs",
    "calibration_estimate",
    "placebo_estimate",
    "synthetic_signal_recovery",
]
