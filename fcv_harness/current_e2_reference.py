from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from empirical_contracts import DatasetRef, GeographySpec, PeriodScheme, RunManifest
from spatial_foundation import PeriodIndex

from .calibration import CalibrationThresholds
from .empirical_input import (
    EmpiricalMeasurementBundle,
    load_empirical_measurement,
    require_same_geography,
    require_same_period_scheme,
)
from .fully_contracted_calibration import (
    FullyContractedCalibrationSpec,
    FullyContractedTreatmentCellSpec,
    run_fully_contracted_calibration_matrix,
    write_fully_contracted_calibration_outputs,
)
from .fully_contracted_experiment import (
    FullyContractedPanelExperimentSpec,
    TreatmentDerivationSpec,
    TreatmentEligibilitySpec,
)
from .lattice_diagnostics import derive_country_iso3
from .measurement_projection import MeasurementProjectionSpec
from .observability import run_e2_observability, write_observability_outputs


@dataclass(frozen=True)
class CurrentE2ObservabilitySpec:
    effect_sizes_sd: tuple[float, ...]
    repetitions: int
    root_seed: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CurrentE2ObservabilitySpec":
        effects = tuple(float(value) for value in payload["effect_sizes_sd"])
        if not effects or len(effects) != len(set(effects)):
            raise ValueError("observability effect_sizes_sd must be non-empty and unique")
        repetitions = int(payload["repetitions"])
        root_seed = int(payload["root_seed"])
        if repetitions <= 0 or root_seed < 0:
            raise ValueError("observability repetitions must be positive and root_seed non-negative")
        return cls(effects, repetitions, root_seed)


@dataclass(frozen=True)
class CurrentE2ReferenceSpec:
    reference_id: str
    purpose: str
    geography: GeographySpec
    period_scheme: PeriodScheme
    treatment_measure_id: str
    outcome_measure_id: str
    outcome_native_event_type: str
    outcome_value_column: str
    treatment_period_start: str
    treatment_period_end: str
    cells: tuple[FullyContractedTreatmentCellSpec, ...]
    thresholds: CalibrationThresholds
    observability: CurrentE2ObservabilitySpec
    geography_source_unit_col: str = "source_geo_id"
    geography_measurement_unit_col: str = "geo_uid"
    geography_country_col: str = "country_iso3"
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2ReferenceSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        cells = tuple(
            FullyContractedTreatmentCellSpec(
                cell_id=str(cell["cell_id"]),
                role=str(cell["role"]),
                value_column=str(cell["value_column"]),
                threshold=float(cell.get("threshold", 0.0)),
            )
            for cell in raw["cells"]
        )
        if len([cell for cell in cells if cell.role.upper() == "PRIMARY"]) != 1:
            raise ValueError("current E2 reference requires exactly one PRIMARY treatment cell")
        return cls(
            reference_id=str(raw["reference_id"]),
            purpose=str(raw.get("purpose", "calibration")),
            geography=GeographySpec.model_validate(raw["geography"]),
            period_scheme=PeriodScheme.model_validate(raw["period_scheme"]),
            treatment_measure_id=str(raw["treatment_measure_id"]),
            outcome_measure_id=str(raw["outcome_measure_id"]),
            outcome_native_event_type=str(raw["outcome_native_event_type"]),
            outcome_value_column=str(raw.get("outcome_value_column", "fatalities")),
            treatment_period_start=str(raw["treatment_period_start"]),
            treatment_period_end=str(raw["treatment_period_end"]),
            cells=cells,
            thresholds=CalibrationThresholds.from_dict(raw.get("thresholds")),
            observability=CurrentE2ObservabilitySpec.from_dict(raw["observability"]),
            geography_source_unit_col=str(
                raw.get("geography_source_unit_col", "source_geo_id")
            ),
            geography_measurement_unit_col=str(
                raw.get("geography_measurement_unit_col", "geo_uid")
            ),
            geography_country_col=str(raw.get("geography_country_col", "country_iso3")),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )

    @property
    def primary_cell(self) -> FullyContractedTreatmentCellSpec:
        return next(cell for cell in self.cells if cell.role.upper() == "PRIMARY")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "purpose": self.purpose,
            "geography": self.geography.model_dump(mode="json"),
            "period_scheme": self.period_scheme.model_dump(mode="json"),
            "treatment_measure_id": self.treatment_measure_id,
            "outcome_measure_id": self.outcome_measure_id,
            "outcome_native_event_type": self.outcome_native_event_type,
            "outcome_value_column": self.outcome_value_column,
            "treatment_period_start": self.treatment_period_start,
            "treatment_period_end": self.treatment_period_end,
            "cells": [asdict(cell) for cell in self.cells],
            "thresholds": asdict(self.thresholds),
            "observability": asdict(self.observability),
            "geography_source_unit_col": self.geography_source_unit_col,
            "geography_measurement_unit_col": self.geography_measurement_unit_col,
            "geography_country_col": self.geography_country_col,
            "unit_col": self.unit_col,
            "period_col": self.period_col,
            "country_col": self.country_col,
        }


@dataclass(frozen=True)
class CurrentE2ArtifactPaths:
    geography_data_path: Path
    geography_manifest_path: Path
    geography_dataset_id: str
    treatment_data_path: Path
    treatment_measurement_contract_path: Path
    treatment_coverage_contract_path: Path
    treatment_manifest_path: Path
    treatment_dataset_id: str
    outcome_data_path: Path
    outcome_measurement_contract_path: Path
    outcome_coverage_contract_path: Path
    outcome_manifest_path: Path
    outcome_dataset_id: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_dataset(path: Path, data_path: Path, dataset_id: str) -> DatasetRef:
    manifest = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    digest = _sha256_file(data_path)
    matches = [
        output
        for output in manifest.outputs
        if output.dataset_id == dataset_id and output.content_sha256 == digest
    ]
    if len(matches) != 1:
        raise ValueError(
            f"manifest does not bind exactly one {dataset_id!r} output to SHA-256 {digest}"
        )
    return matches[0]


def load_current_geography(
    spec: CurrentE2ReferenceSpec,
    *,
    data_path: str | Path,
    manifest_path: str | Path,
    dataset_id: str,
) -> tuple[DatasetRef, pd.DataFrame]:
    data = Path(data_path).expanduser().resolve()
    manifest = Path(manifest_path).expanduser().resolve()
    if not data.is_file() or not manifest.is_file():
        raise FileNotFoundError("current E2 geography data or manifest does not exist")
    dataset = _manifest_dataset(manifest, data, dataset_id)
    require_same_geography(dataset, spec.geography)
    table = pd.read_parquet(data)
    required = {
        spec.geography_source_unit_col,
        spec.geography_measurement_unit_col,
        spec.geography_country_col,
    }
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("governed geography is missing reference columns: " + ", ".join(missing))
    spine = table[list(required)].copy()
    for column in required:
        if spine[column].isna().any():
            raise ValueError(f"governed geography contains missing {column}")
    if spine[spec.geography_source_unit_col].duplicated().any():
        raise ValueError("analysis-unit source IDs must be unique")
    if spine[spec.geography_measurement_unit_col].duplicated().any():
        raise ValueError("measurement geography IDs must be unique")
    return dataset, spine


def _declared_period_ids(spec: CurrentE2ReferenceSpec) -> tuple[str, ...]:
    def start_year(period_id: str) -> int:
        return int(str(period_id).split("-", 1)[0])

    start = start_year(spec.treatment_period_start)
    end = start_year(spec.treatment_period_end)
    if start > end:
        raise ValueError("treatment period start follows treatment period end")
    index = PeriodIndex(spec.period_scheme)
    periods = tuple(index.period_for(year).period_id for year in range(start, end + 1, spec.period_scheme.width_years))
    if not periods or periods[0] != spec.treatment_period_start or periods[-1] != spec.treatment_period_end:
        raise ValueError("treatment window does not align exactly to the declared PeriodScheme")
    return periods


def build_current_reference_panel(
    geography: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = [
        spec.geography_source_unit_col,
        spec.geography_measurement_unit_col,
        spec.geography_country_col,
    ]
    missing = [column for column in required if column not in geography.columns]
    if missing:
        raise ValueError(f"geography spine is missing required columns: {missing}")
    units = geography[required].drop_duplicates().copy()
    if units[spec.geography_source_unit_col].duplicated().any():
        raise ValueError("reference geography is not unique by source analysis unit")
    if units[spec.geography_measurement_unit_col].duplicated().any():
        raise ValueError("reference geography linkage is not one-to-one")

    units = units.rename(columns={spec.geography_source_unit_col: spec.unit_col})
    derived = derive_country_iso3(units[spec.unit_col])
    source_country = units[spec.geography_country_col].astype("string").str.upper()
    conflict = derived.notna() & source_country.notna() & derived.ne(source_country)
    if conflict.any():
        raise ValueError(
            f"governed geography country identity conflicts with source GID on {int(conflict.sum())} units"
        )
    units[spec.country_col] = source_country.fillna(derived)
    if units[spec.country_col].isna().any():
        raise ValueError("reference geography has unresolved country identity")

    linkage = units[[spec.unit_col, spec.geography_measurement_unit_col]].rename(
        columns={spec.geography_measurement_unit_col: "geo_uid"}
    )
    period_ids = _declared_period_ids(spec)
    panel = (
        units[[spec.unit_col, spec.country_col]]
        .assign(_key=1)
        .merge(pd.DataFrame({spec.period_col: period_ids, "_key": 1}), on="_key")
        .drop(columns="_key")
        .sort_values([spec.unit_col, spec.period_col])
        .reset_index(drop=True)
    )
    if panel.duplicated([spec.unit_col, spec.period_col]).any():
        raise AssertionError("reference panel is not unique at unit × period")
    return panel, linkage


def _load_bundle(
    *,
    data_path: Path,
    measurement_contract_path: Path,
    coverage_contract_path: Path,
    manifest_path: Path,
    dataset_id: str,
    expected_measure_id: str,
    spec: CurrentE2ReferenceSpec,
) -> EmpiricalMeasurementBundle:
    bundle = load_empirical_measurement(
        data_path=data_path,
        measurement_contract_path=measurement_contract_path,
        coverage_contract_path=coverage_contract_path,
        run_manifest_path=manifest_path,
        dataset_id=dataset_id,
    )
    if bundle.measurement.measure_id != expected_measure_id:
        raise ValueError(
            f"expected measure_id {expected_measure_id!r}, got {bundle.measurement.measure_id!r}"
        )
    require_same_geography(bundle.dataset, spec.geography)
    require_same_period_scheme(bundle.dataset, spec.period_scheme)
    return bundle


def _experiment_spec(spec: CurrentE2ReferenceSpec) -> FullyContractedPanelExperimentSpec:
    return FullyContractedPanelExperimentSpec(
        experiment_id=spec.reference_id,
        treatment=MeasurementProjectionSpec(
            measure_id=spec.treatment_measure_id,
            selectors={},
            value_column=spec.primary_cell.value_column,
            role="treatment_candidate",
            output_column="investment_value",
        ),
        treatment_derivation=TreatmentDerivationSpec(
            rule="greater_than",
            threshold=spec.primary_cell.threshold,
        ),
        eligibility=TreatmentEligibilitySpec(
            period_start=spec.treatment_period_start,
            period_end=spec.treatment_period_end,
        ),
        outcome=MeasurementProjectionSpec(
            measure_id=spec.outcome_measure_id,
            selectors={"native_event_type": spec.outcome_native_event_type},
            value_column=spec.outcome_value_column,
            role="outcome",
            timing_offset=1,
            output_column="outcome_value",
        ),
        unit_col=spec.unit_col,
        period_col=spec.period_col,
        country_col=spec.country_col,
    )


def _calibration_spec(spec: CurrentE2ReferenceSpec) -> FullyContractedCalibrationSpec:
    return FullyContractedCalibrationSpec(
        calibration_id=spec.reference_id,
        thresholds=spec.thresholds,
        unit_col=spec.unit_col,
        period_col=spec.period_col,
        country_col=spec.country_col,
    )


def run_current_e2_from_bundles(
    geography: pd.DataFrame,
    geography_dataset: DatasetRef,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    spec: CurrentE2ReferenceSpec,
    *,
    run_observability: bool = False,
) -> dict[str, Any]:
    require_same_geography(geography_dataset, spec.geography)
    require_same_geography(treatment_bundle.dataset, spec.geography)
    require_same_geography(outcome_bundle.dataset, spec.geography)
    require_same_period_scheme(treatment_bundle.dataset, spec.period_scheme)
    require_same_period_scheme(outcome_bundle.dataset, spec.period_scheme)
    if treatment_bundle.measurement.measure_id != spec.treatment_measure_id:
        raise ValueError("treatment bundle does not match reference treatment measure")
    if outcome_bundle.measurement.measure_id != spec.outcome_measure_id:
        raise ValueError("outcome bundle does not match reference outcome measure")

    panel, linkage = build_current_reference_panel(geography, spec)
    calibration_spec = _calibration_spec(spec)
    calibration = run_fully_contracted_calibration_matrix(
        panel,
        _experiment_spec(spec),
        calibration_spec,
        spec.cells,
        treatment_bundle=treatment_bundle,
        outcome_bundle=outcome_bundle,
        target_geography=spec.geography,
        target_period_scheme=spec.period_scheme,
        geography_linkage=linkage,
    )
    observability: dict[str, pd.DataFrame] | None = None
    observability_state = "NOT_REQUESTED"
    if run_observability:
        primary = calibration["cells"][spec.primary_cell.cell_id]
        if primary["estimation_permitted"]:
            observability = run_e2_observability(
                primary["frame"],
                calibration_spec,
                effect_sizes_sd=spec.observability.effect_sizes_sd,
                repetitions=spec.observability.repetitions,
                root_seed=spec.observability.root_seed,
            )
            observability_state = "RUN"
        else:
            observability_state = "BLOCKED_BY_HARD_GATES"

    return {
        "spec": spec,
        "geography_dataset": geography_dataset,
        "panel": panel,
        "geography_linkage": linkage,
        "treatment_bundle": treatment_bundle,
        "outcome_bundle": outcome_bundle,
        "calibration_spec": calibration_spec,
        "calibration": calibration,
        "observability": observability,
        "observability_state": observability_state,
    }


def run_current_e2_reference(
    spec: CurrentE2ReferenceSpec,
    paths: CurrentE2ArtifactPaths,
    *,
    run_observability: bool = False,
) -> dict[str, Any]:
    geography_dataset, geography = load_current_geography(
        spec,
        data_path=paths.geography_data_path,
        manifest_path=paths.geography_manifest_path,
        dataset_id=paths.geography_dataset_id,
    )
    treatment = _load_bundle(
        data_path=paths.treatment_data_path,
        measurement_contract_path=paths.treatment_measurement_contract_path,
        coverage_contract_path=paths.treatment_coverage_contract_path,
        manifest_path=paths.treatment_manifest_path,
        dataset_id=paths.treatment_dataset_id,
        expected_measure_id=spec.treatment_measure_id,
        spec=spec,
    )
    outcome = _load_bundle(
        data_path=paths.outcome_data_path,
        measurement_contract_path=paths.outcome_measurement_contract_path,
        coverage_contract_path=paths.outcome_coverage_contract_path,
        manifest_path=paths.outcome_manifest_path,
        dataset_id=paths.outcome_dataset_id,
        expected_measure_id=spec.outcome_measure_id,
        spec=spec,
    )
    return run_current_e2_from_bundles(
        geography,
        geography_dataset,
        treatment,
        outcome,
        spec,
        run_observability=run_observability,
    )


def _frame_sha256(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> str:
    ordered = frame.sort_values([spec.unit_col, spec.period_col]).reset_index(drop=True)
    return hashlib.sha256(
        ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()


def write_current_e2_reference_outputs(result: dict[str, Any], out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spec: CurrentE2ReferenceSpec = result["spec"]
    calibration = result["calibration"]
    write_fully_contracted_calibration_outputs(calibration, out / "calibration")

    frame_hashes: dict[str, str] = {}
    for cell_id, cell_result in calibration["cells"].items():
        cell_dir = out / "calibration" / "cells" / cell_id
        pd.DataFrame([cell_result["placebo"]]).to_csv(cell_dir / "placebo.csv", index=False)
        frame_hashes[cell_id] = _frame_sha256(cell_result["frame"], spec)

    observability = result.get("observability")
    if observability is not None:
        write_observability_outputs(observability, out / "observability")

    geography_dataset: DatasetRef = result["geography_dataset"]
    treatment: EmpiricalMeasurementBundle = result["treatment_bundle"]
    outcome: EmpiricalMeasurementBundle = result["outcome_bundle"]
    payload = {
        "reference_spec": spec.to_dict(),
        "analysis_panel": {
            "rows": int(len(result["panel"])),
            "units": int(result["panel"][spec.unit_col].nunique()),
            "periods": int(result["panel"][spec.period_col].nunique()),
            "frame_sha256_by_cell": frame_hashes,
            "analysis_frame_persisted": False,
        },
        "inputs": {
            "geography_dataset": geography_dataset.model_dump(mode="json"),
            "treatment_dataset": treatment.dataset.model_dump(mode="json"),
            "treatment_measurement": treatment.measurement.model_dump(mode="json"),
            "treatment_run_id": treatment.run_manifest.run_id,
            "outcome_dataset": outcome.dataset.model_dump(mode="json"),
            "outcome_measurement": outcome.measurement.model_dump(mode="json"),
            "outcome_run_id": outcome.run_manifest.run_id,
        },
        "observability_state": result["observability_state"],
    }
    (out / "reference_run.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


__all__ = [
    "CurrentE2ArtifactPaths",
    "CurrentE2ObservabilitySpec",
    "CurrentE2ReferenceSpec",
    "build_current_reference_panel",
    "load_current_geography",
    "run_current_e2_from_bundles",
    "run_current_e2_reference",
    "write_current_e2_reference_outputs",
]
