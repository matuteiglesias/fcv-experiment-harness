from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from empirical_contracts import CoverageContract, DatasetRef, GeographySpec, PeriodScheme
from spatial_foundation import PeriodIndex

from .empirical_input import (
    EmpiricalCompatibilityError,
    EmpiricalMeasurementBundle,
    require_same_geography,
    require_same_period_scheme,
)


class MeasurementProjectionError(ValueError):
    """Raised when an empirical measurement cannot be projected as declared."""


@dataclass(frozen=True)
class MeasurementProjectionSpec:
    """Downstream scientific declaration of how an experiment uses a measurement."""

    measure_id: str
    selectors: dict[str, Any]
    value_column: str
    role: str
    timing_offset: int = 0
    output_column: str = "measurement_value"
    transform: str | None = None
    transformation_parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.measure_id:
            raise ValueError("measure_id must be non-empty")
        if not self.value_column:
            raise ValueError("value_column must be non-empty")
        if not self.role:
            raise ValueError("role must be non-empty")
        if not self.output_column:
            raise ValueError("output_column must be non-empty")
        if self.transform not in {None, "identity"}:
            raise ValueError(
                "only the identity transform is implemented; add new transforms explicitly"
            )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MeasurementProjectionSpec":
        return cls(
            measure_id=str(payload["measure_id"]),
            selectors=dict(payload.get("selectors", {})),
            value_column=str(payload["value_column"]),
            role=str(payload["role"]),
            timing_offset=int(payload.get("timing_offset", 0)),
            output_column=str(payload.get("output_column", "measurement_value")),
            transform=payload.get("transform"),
            transformation_parameters=dict(payload.get("transformation_parameters", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "measure_id": self.measure_id,
            "selectors": self.selectors,
            "value_column": self.value_column,
            "role": self.role,
            "timing_offset": self.timing_offset,
            "output_column": self.output_column,
            "transform": self.transform,
            "transformation_parameters": self.transformation_parameters,
        }


@dataclass(frozen=True)
class ExperimentProjectionReport:
    """Serializable audit trail from empirical measurement to experiment variable."""

    input_dataset: DatasetRef
    measure_id: str
    selectors: dict[str, Any]
    role: str
    geography: GeographySpec
    period_scheme: PeriodScheme
    input_row_count: int
    selector_row_counts: dict[str, int]
    selected_row_count: int
    coverage_semantics: dict[str, Any]
    observed_count: int
    structural_zero_count: int
    outside_coverage_count: int
    unresolved_count: int
    timing_offset: int
    transform: str | None
    transformation_parameters: dict[str, Any]
    output_row_count: int
    output_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_dataset": self.input_dataset.model_dump(mode="json"),
            "measure_id": self.measure_id,
            "selectors": self.selectors,
            "role": self.role,
            "geography": self.geography.model_dump(mode="json"),
            "period_scheme": self.period_scheme.model_dump(mode="json"),
            "input_row_count": self.input_row_count,
            "selector_row_counts": self.selector_row_counts,
            "selected_row_count": self.selected_row_count,
            "coverage_semantics": self.coverage_semantics,
            "observed_count": self.observed_count,
            "structural_zero_count": self.structural_zero_count,
            "outside_coverage_count": self.outside_coverage_count,
            "unresolved_count": self.unresolved_count,
            "timing_offset": self.timing_offset,
            "transform": self.transform,
            "transformation_parameters": self.transformation_parameters,
            "output_row_count": self.output_row_count,
            "output_sha256": self.output_sha256,
        }


@dataclass(frozen=True)
class ProjectionResult:
    frame: pd.DataFrame
    report: ExperimentProjectionReport


_PERIOD_ID = re.compile(r"^(\d{4})-(\d{4})$")


def _period_for_id(period_id: str, scheme: PeriodScheme):
    match = _PERIOD_ID.fullmatch(str(period_id))
    if not match:
        raise MeasurementProjectionError(
            f"period id {period_id!r} is not a shared PeriodIndex id"
        )
    start_year = int(match.group(1))
    period = PeriodIndex(scheme).period_for(start_year)
    if period.period_id != str(period_id):
        raise MeasurementProjectionError(
            f"period id {period_id!r} contradicts PeriodScheme {scheme.id}"
        )
    return period


def _shift_period_id(period_id: str, scheme: PeriodScheme, offset: int) -> str:
    period = _period_for_id(period_id, scheme)
    shifted_year = period.start_year + offset * scheme.width_years
    return PeriodIndex(scheme).period_for(shifted_year).period_id


def _coverage_state(period_id: str, coverage: CoverageContract, scheme: PeriodScheme) -> str:
    period = _period_for_id(period_id, scheme)
    if coverage.temporal_start is None or coverage.temporal_end is None:
        return "unknown"
    period_end = period.end_date_exclusive - timedelta(days=1)
    if period_end < coverage.temporal_start or period.start_date > coverage.temporal_end:
        return "outside"
    if period.start_date >= coverage.temporal_start and period_end <= coverage.temporal_end:
        return "inside"
    return "partial"


def _coverage_payload(coverage: CoverageContract) -> dict[str, Any]:
    return coverage.model_dump(mode="json")


def _frame_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _selector_label(column: str, value: Any) -> str:
    return f"{column}={value}"


def _prepare_selected_table(
    bundle: EmpiricalMeasurementBundle,
    spec: MeasurementProjectionSpec,
    *,
    measurement_geo_col: str,
    measurement_period_col: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if bundle.measurement.measure_id != spec.measure_id:
        raise MeasurementProjectionError(
            f"measurement use expects {spec.measure_id!r}, got {bundle.measurement.measure_id!r}"
        )
    if spec.value_column not in bundle.table.columns:
        raise MeasurementProjectionError(
            f"contracted measurement is missing requested value column {spec.value_column!r}"
        )

    selected = bundle.table.copy()
    selector_counts: dict[str, int] = {}
    for column, value in spec.selectors.items():
        if column not in selected.columns:
            raise MeasurementProjectionError(
                f"contracted measurement is missing selector column {column!r}"
            )
        selected = selected.loc[selected[column].eq(value)].copy()
        selector_counts[_selector_label(column, value)] = int(len(selected))

    residual_grain = [
        key for key in bundle.measurement.output_grain.keys if key not in spec.selectors
    ]
    required_keys = {measurement_geo_col, measurement_period_col}
    missing_required = sorted(required_keys - set(residual_grain))
    if missing_required:
        raise MeasurementProjectionError(
            "measurement projection does not retain required geography/period grain keys: "
            + ", ".join(missing_required)
        )
    extra_grain = sorted(set(residual_grain) - required_keys)
    if extra_grain:
        raise MeasurementProjectionError(
            "measurement remains multi-dimensional after selectors; declare additional "
            "selectors or an explicit transform for: "
            + ", ".join(extra_grain)
        )

    keep = [measurement_geo_col, measurement_period_col, spec.value_column]
    selected = selected[keep].copy()
    if selected.duplicated([measurement_geo_col, measurement_period_col]).any():
        raise MeasurementProjectionError(
            "selected measurement is not unique at geography × period; refusing implicit aggregation"
        )
    selected["_measurement_record_present"] = True
    return selected, selector_counts


def _attach_geography_linkage(
    target: pd.DataFrame,
    *,
    target_unit_col: str,
    measurement_geo_col: str,
    geography_linkage: pd.DataFrame | None,
    linkage_unit_col: str | None,
    linkage_geo_col: str,
) -> pd.DataFrame:
    out = target.copy()
    if geography_linkage is None:
        if target_unit_col != measurement_geo_col:
            raise MeasurementProjectionError(
                "target unit identity differs from measurement geography identity; "
                "an explicit geography linkage is required"
            )
        out["_measurement_geo_uid"] = out[target_unit_col]
        return out

    unit_col = linkage_unit_col or target_unit_col
    required = [unit_col, linkage_geo_col]
    missing = [column for column in required if column not in geography_linkage.columns]
    if missing:
        raise MeasurementProjectionError(
            f"geography linkage is missing required columns: {missing}"
        )
    linkage = geography_linkage[required].drop_duplicates().copy()
    if linkage[unit_col].duplicated().any():
        raise MeasurementProjectionError("geography linkage is not unique by analysis unit")
    if linkage[linkage_geo_col].duplicated().any():
        raise MeasurementProjectionError("geography linkage is not one-to-one by measurement unit")
    linkage = linkage.rename(
        columns={unit_col: target_unit_col, linkage_geo_col: "_measurement_geo_uid"}
    )
    return out.merge(linkage, on=target_unit_col, how="left", validate="many_to_one")


def project_empirical_measurement(
    bundle: EmpiricalMeasurementBundle,
    target: pd.DataFrame,
    spec: MeasurementProjectionSpec,
    *,
    target_geography: GeographySpec,
    target_period_scheme: PeriodScheme,
    target_unit_col: str,
    target_period_col: str,
    geography_linkage: pd.DataFrame | None = None,
    linkage_unit_col: str | None = None,
    linkage_geo_col: str = "geo_uid",
    measurement_geo_col: str = "geo_uid",
    measurement_period_col: str = "period_id",
) -> ProjectionResult:
    """Project a validated sparse measurement into an explicit experiment variable.

    Taxonomy selection, value choice, timing, and optional transform are downstream
    scientific choices. Sparse absence is resolved only from the upstream
    ``CoverageContract``; this function never assumes zero merely because a row is
    absent.
    """
    try:
        require_same_geography(bundle.dataset, target_geography)
        require_same_geography(bundle.measurement, target_geography)
    except EmpiricalCompatibilityError as error:
        raise MeasurementProjectionError(f"geography incompatibility: {error}") from error
    try:
        require_same_period_scheme(bundle.dataset, target_period_scheme)
        require_same_period_scheme(bundle.measurement, target_period_scheme)
    except EmpiricalCompatibilityError as error:
        raise MeasurementProjectionError(f"period incompatibility: {error}") from error

    required_target = [target_unit_col, target_period_col]
    missing_target = [column for column in required_target if column not in target.columns]
    if missing_target:
        raise MeasurementProjectionError(
            f"projection target is missing required keys: {missing_target}"
        )
    if target.duplicated(required_target).any():
        raise MeasurementProjectionError(
            "projection target is not unique at declared analysis unit × period"
        )

    selected, selector_counts = _prepare_selected_table(
        bundle,
        spec,
        measurement_geo_col=measurement_geo_col,
        measurement_period_col=measurement_period_col,
    )
    working = _attach_geography_linkage(
        target[required_target],
        target_unit_col=target_unit_col,
        measurement_geo_col=measurement_geo_col,
        geography_linkage=geography_linkage,
        linkage_unit_col=linkage_unit_col,
        linkage_geo_col=linkage_geo_col,
    )
    working["measurement_period_id"] = working[target_period_col].map(
        lambda period_id: _shift_period_id(
            str(period_id), target_period_scheme, spec.timing_offset
        )
    )

    selected = selected.rename(
        columns={
            measurement_geo_col: "_measurement_geo_uid",
            measurement_period_col: "measurement_period_id",
            spec.value_column: "_measurement_value",
        }
    )
    projected = working.merge(
        selected,
        on=["_measurement_geo_uid", "measurement_period_id"],
        how="left",
        validate="one_to_one",
    )
    record_present = projected["_measurement_record_present"].fillna(False).astype(bool)
    value = projected["_measurement_value"].copy()
    status = pd.Series("unresolved", index=projected.index, dtype="string")
    detail = pd.Series("absent_row_unknown", index=projected.index, dtype="string")

    missing_link = projected["_measurement_geo_uid"].isna()
    status.loc[missing_link] = "unresolved"
    detail.loc[missing_link] = "missing_geography_linkage"

    observed_value = record_present & value.notna()
    status.loc[observed_value] = "observed"
    detail.loc[observed_value] = "observed_empirical_row"
    observed_missing = record_present & value.isna()
    status.loc[observed_missing] = "unresolved"
    detail.loc[observed_missing] = "observed_row_value_missing"

    absent = ~record_present & ~missing_link
    for index in projected.index[absent]:
        coverage_state = _coverage_state(
            projected.at[index, "measurement_period_id"],
            bundle.coverage,
            target_period_scheme,
        )
        if coverage_state == "outside":
            status.at[index] = "outside_coverage"
            detail.at[index] = "outside_temporal_coverage"
            continue
        if coverage_state == "partial":
            status.at[index] = "unresolved"
            detail.at[index] = "partial_temporal_coverage"
            continue
        if coverage_state == "unknown":
            status.at[index] = "unresolved"
            detail.at[index] = "coverage_temporal_unknown"
            continue

        semantics = bundle.coverage.absent_row_semantics
        if semantics == "zero_within_verified_coverage":
            value.at[index] = 0.0
            status.at[index] = "structural_zero"
            detail.at[index] = "absent_row_zero_licensed_by_coverage"
        elif semantics == "unknown":
            status.at[index] = "unresolved"
            detail.at[index] = "absent_row_unknown"
        elif semantics == "not_observed":
            status.at[index] = "unresolved"
            detail.at[index] = "absent_row_not_observed"
        else:
            status.at[index] = "unresolved"
            detail.at[index] = "absent_row_not_applicable"

    if spec.transform in {None, "identity"}:
        transformed = value
    else:  # guarded by MeasurementProjectionSpec, retained as a fail-closed invariant
        raise MeasurementProjectionError(f"unsupported transform {spec.transform!r}")

    output = projected[required_target].copy()
    output["measurement_geo_uid"] = projected["_measurement_geo_uid"]
    output["measurement_period_id"] = projected["measurement_period_id"]
    output[spec.output_column] = transformed
    output["projection_status"] = status
    output["projection_detail"] = detail
    output["measurement_record_present"] = record_present

    observed_count = int(status.eq("observed").sum())
    structural_zero_count = int(status.eq("structural_zero").sum())
    outside_coverage_count = int(status.eq("outside_coverage").sum())
    unresolved_count = int(status.eq("unresolved").sum())
    output_count = int(len(output))
    if (
        observed_count
        + structural_zero_count
        + outside_coverage_count
        + unresolved_count
        != output_count
    ):
        raise AssertionError("projection status accounting does not reconcile")

    report = ExperimentProjectionReport(
        input_dataset=bundle.dataset,
        measure_id=bundle.measurement.measure_id,
        selectors=dict(spec.selectors),
        role=spec.role,
        geography=target_geography,
        period_scheme=target_period_scheme,
        input_row_count=int(len(bundle.table)),
        selector_row_counts=selector_counts,
        selected_row_count=int(len(selected)),
        coverage_semantics=_coverage_payload(bundle.coverage),
        observed_count=observed_count,
        structural_zero_count=structural_zero_count,
        outside_coverage_count=outside_coverage_count,
        unresolved_count=unresolved_count,
        timing_offset=spec.timing_offset,
        transform=spec.transform,
        transformation_parameters=dict(spec.transformation_parameters),
        output_row_count=output_count,
        output_sha256=_frame_sha256(output),
    )
    return ProjectionResult(frame=output, report=report)


def write_projection_report(report: ExperimentProjectionReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination
