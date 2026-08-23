from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from empirical_contracts import GeographySpec, PeriodScheme

from .calibration import (
    CalibrationThresholds,
    calibration_estimate,
    run_calibration_gates,
)
from .empirical_input import EmpiricalMeasurementBundle
from .fully_contracted_experiment import (
    FullyContractedPanelExperimentSpec,
    run_fully_contracted_experiment_preflight,
)
from .measurement_projection import (
    MeasurementProjectionSpec,
    project_empirical_measurement,
    write_projection_report,
)


@dataclass(frozen=True)
class FullyContractedCalibrationSpec:
    """Estimator/gate settings after both scientific inputs have been contracted."""

    calibration_id: str
    thresholds: CalibrationThresholds = CalibrationThresholds()
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"


@dataclass(frozen=True)
class FullyContractedTreatmentCellSpec:
    """Predeclared alternative use of the same upstream investment measurement."""

    cell_id: str
    role: str
    value_column: str
    threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.role.upper() not in {"PRIMARY", "STRESS"}:
            raise ValueError("fully contracted cell role must be PRIMARY or STRESS")
        if not self.value_column:
            raise ValueError("fully contracted treatment value_column must be non-empty")


def experiment_for_treatment_cell(
    base: FullyContractedPanelExperimentSpec,
    cell: FullyContractedTreatmentCellSpec,
) -> FullyContractedPanelExperimentSpec:
    treatment = replace(base.treatment, value_column=cell.value_column)
    derivation = replace(base.treatment_derivation, threshold=cell.threshold)
    return replace(
        base,
        experiment_id=f"{base.experiment_id}__{cell.cell_id}",
        treatment=treatment,
        treatment_derivation=derivation,
    )


def _pre_outcome_projection(
    panel: pd.DataFrame,
    experiment: FullyContractedPanelExperimentSpec,
    *,
    outcome_bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
):
    pre_use = replace(
        experiment.outcome,
        role="pre_outcome",
        timing_offset=-1,
        output_column="outcome_pre",
    )
    return project_empirical_measurement(
        outcome_bundle,
        panel[[experiment.unit_col, experiment.period_col]],
        pre_use,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        target_unit_col=experiment.unit_col,
        target_period_col=experiment.period_col,
        geography_linkage=geography_linkage,
    )


def run_fully_contracted_calibration_cell(
    panel: pd.DataFrame,
    experiment: FullyContractedPanelExperimentSpec,
    calibration: FullyContractedCalibrationSpec,
    *,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
    surface_gates: pd.DataFrame | None = None,
    seed_offset: int = 0,
) -> dict:
    """Run the existing calibration estimator after two contract-backed projections."""
    if (
        calibration.unit_col != experiment.unit_col
        or calibration.period_col != experiment.period_col
        or calibration.country_col != experiment.country_col
    ):
        raise ValueError("calibration identity columns must match fully contracted experiment")

    preflight = run_fully_contracted_experiment_preflight(
        panel,
        experiment,
        treatment_bundle=treatment_bundle,
        outcome_bundle=outcome_bundle,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        geography_linkage=geography_linkage,
    )
    pre_projection = _pre_outcome_projection(
        panel,
        experiment,
        outcome_bundle=outcome_bundle,
        target_geography=target_geography,
        target_period_scheme=target_period_scheme,
        geography_linkage=geography_linkage,
    )
    frame = preflight.frame.copy()
    frame["outcome_pre"] = pd.to_numeric(
        pre_projection.frame["outcome_pre"], errors="coerce"
    ).to_numpy()
    frame["outcome_pre_period"] = pre_projection.frame["measurement_period_id"].to_numpy()
    frame["outcome_pre_status"] = pre_projection.frame["projection_status"].to_numpy()
    frame["outcome_pre_detail"] = pre_projection.frame["projection_detail"].to_numpy()

    gate_surface = (
        surface_gates
        if surface_gates is not None
        else pd.DataFrame(columns=["gate", "status", "metric", "value", "note"])
    )
    gate_result = run_calibration_gates(
        frame,
        {"estimation_permitted": preflight.estimation_permitted},
        calibration,
        gate_surface,
        seed_offset=seed_offset,
    )
    estimate = (
        calibration_estimate(frame, calibration)
        if gate_result["estimation_permitted"]
        else {
            "ok": False,
            "reason": "Hard calibration gate RED: "
            + ", ".join(gate_result["hard_red_gates"]),
        }
    )
    return {
        "experiment_spec": experiment,
        "calibration_spec": calibration,
        "preflight": preflight,
        "frame": frame,
        "treatment_projection": preflight.treatment_projection,
        "outcome_post_projection": preflight.outcome_projection,
        "outcome_pre_projection": pre_projection,
        **gate_result,
        "estimate": estimate,
    }


def _matrix_row(cell: FullyContractedTreatmentCellSpec, result: dict) -> dict:
    estimate = result["estimate"]
    support = result["support_by_period"]
    mixed = (
        int(((support["treated"] > 0) & (support["control"] > 0)).sum())
        if len(support)
        else 0
    )
    red = result["gates"].loc[result["gates"]["status"].eq("RED"), "gate"].tolist()
    yellow = result["gates"].loc[
        result["gates"]["status"].eq("YELLOW"), "gate"
    ].tolist()
    return {
        "cell_id": cell.cell_id,
        "role": cell.role.upper(),
        "treatment_value_column": cell.value_column,
        "threshold": cell.threshold,
        "estimated": bool(estimate.get("ok")),
        "effect": estimate.get("effect", np.nan),
        "se": estimate.get("se", np.nan),
        "n": estimate.get("n", np.nan),
        "n_units": estimate.get("n_units", np.nan),
        "treated": estimate.get("n_treated", np.nan),
        "control": estimate.get("n_control", np.nan),
        "mixed_support_periods": f"{mixed}/{len(support)}",
        "signal_recovery": result["signal_recovery"].get("recovery_probability", np.nan),
        "hard_gate_state": "PASS" if result["estimation_permitted"] else "BLOCKED",
        "red_gates": ";".join(red),
        "yellow_gates": ";".join(yellow),
        "estimate_reason": estimate.get("reason", ""),
    }


def run_fully_contracted_calibration_matrix(
    panel: pd.DataFrame,
    base_experiment: FullyContractedPanelExperimentSpec,
    calibration: FullyContractedCalibrationSpec,
    cells: tuple[FullyContractedTreatmentCellSpec, ...],
    *,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    geography_linkage: pd.DataFrame,
    surface_gates: pd.DataFrame | None = None,
) -> dict:
    if not cells:
        raise ValueError("fully contracted calibration matrix requires at least one cell")
    ids = [cell.cell_id for cell in cells]
    if len(ids) != len(set(ids)):
        raise ValueError("fully contracted treatment cell IDs must be unique")

    results = {}
    for index, cell in enumerate(cells):
        experiment = experiment_for_treatment_cell(base_experiment, cell)
        results[cell.cell_id] = run_fully_contracted_calibration_cell(
            panel,
            experiment,
            calibration,
            treatment_bundle=treatment_bundle,
            outcome_bundle=outcome_bundle,
            target_geography=target_geography,
            target_period_scheme=target_period_scheme,
            geography_linkage=geography_linkage,
            surface_gates=surface_gates,
            seed_offset=1000 * index,
        )
    stability = pd.DataFrame([_matrix_row(cell, results[cell.cell_id]) for cell in cells])
    return {"cells": results, "stability": stability}


def write_fully_contracted_calibration_outputs(result: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["stability"].to_csv(out / "measurement_stability.csv", index=False)
    gate_rows = []
    for cell_id, cell_result in result["cells"].items():
        cell_dir = out / "cells" / cell_id
        cell_dir.mkdir(parents=True, exist_ok=True)
        gates = cell_result["gates"].copy()
        gates.insert(0, "cell_id", cell_id)
        gate_rows.append(gates)
        gates.to_csv(cell_dir / "gates.csv", index=False)
        cell_result["support_by_period"].to_csv(cell_dir / "support_by_period.csv", index=False)
        pd.DataFrame([cell_result["estimate"]]).to_csv(cell_dir / "estimate.csv", index=False)
        pd.DataFrame([cell_result["signal_recovery"]]).to_csv(
            cell_dir / "signal_recovery.csv", index=False
        )
        write_projection_report(
            cell_result["treatment_projection"].report,
            cell_dir / "treatment_projection_report.json",
        )
        write_projection_report(
            cell_result["outcome_post_projection"].report,
            cell_dir / "outcome_post_projection_report.json",
        )
        write_projection_report(
            cell_result["outcome_pre_projection"].report,
            cell_dir / "outcome_pre_projection_report.json",
        )
    if gate_rows:
        pd.concat(gate_rows, ignore_index=True).to_csv(out / "cell_gates.csv", index=False)
    return out
