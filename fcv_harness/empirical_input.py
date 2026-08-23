from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from empirical_contracts import (
    AuthorityLevel,
    CoverageContract,
    DatasetRef,
    GeographySpec,
    MeasurementContract,
    PeriodScheme,
    RunManifest,
)


class EmpiricalInputError(ValueError):
    """Raised when persisted empirical inputs contradict their contracts."""


class EmpiricalCompatibilityError(EmpiricalInputError):
    """Raised when declared geography or period identities are incompatible."""


@dataclass(frozen=True)
class EmpiricalMeasurementBundle:
    """A validated upstream measurement plus its untouched sparse data table."""

    dataset: DatasetRef
    measurement: MeasurementContract
    coverage: CoverageContract
    run_manifest: RunManifest
    data_path: Path
    table: pd.DataFrame

    @property
    def authority(self) -> AuthorityLevel:
        """Return upstream dataset authority without promotion or reinterpretation."""
        return self.dataset.authority


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise EmpiricalInputError(f"{label} does not exist as a file: {resolved}")
    return resolved


def _load_contract(path: Path, model: type[Any], label: str) -> Any:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EmpiricalInputError(f"invalid {label}: {path}: {error}") from error


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    raise EmpiricalInputError(
        f"unsupported empirical table format {suffix!r}; use CSV, Parquet, or JSON Lines"
    )


def _geography_of(
    value: DatasetRef | MeasurementContract | GeographySpec | None,
) -> GeographySpec | None:
    if isinstance(value, GeographySpec) or value is None:
        return value
    return value.geography


def _period_scheme_of(
    value: DatasetRef | MeasurementContract | PeriodScheme | None,
) -> PeriodScheme | None:
    if isinstance(value, PeriodScheme) or value is None:
        return value
    return value.period_scheme


def require_same_geography(
    left: DatasetRef | MeasurementContract | GeographySpec | None,
    right: DatasetRef | MeasurementContract | GeographySpec | None,
) -> GeographySpec | None:
    """Require exact declared geography identity, not a convenient string label."""
    left_geo = _geography_of(left)
    right_geo = _geography_of(right)
    if left_geo != right_geo:
        raise EmpiricalCompatibilityError(
            f"geography contract mismatch: {left_geo!r} != {right_geo!r}"
        )
    return left_geo


def require_same_period_scheme(
    left: DatasetRef | MeasurementContract | PeriodScheme | None,
    right: DatasetRef | MeasurementContract | PeriodScheme | None,
) -> PeriodScheme | None:
    """Require exact declared period identity without resampling or coercion."""
    left_period = _period_scheme_of(left)
    right_period = _period_scheme_of(right)
    if left_period != right_period:
        raise EmpiricalCompatibilityError(
            f"period scheme contract mismatch: {left_period!r} != {right_period!r}"
        )
    return left_period


def _resolve_manifest_output(
    manifest: RunManifest,
    *,
    content_sha256: str,
    dataset_id: str | None,
) -> DatasetRef:
    matches = [
        output
        for output in manifest.outputs
        if output.content_sha256 == content_sha256
        and (dataset_id is None or output.dataset_id == dataset_id)
    ]
    if not matches:
        qualifier = f" for dataset_id={dataset_id!r}" if dataset_id else ""
        raise EmpiricalInputError(
            "upstream RunManifest does not identify the loaded artifact as an output"
            f"{qualifier} with SHA-256 {content_sha256}"
        )
    if len(matches) > 1:
        raise EmpiricalInputError(
            "loaded artifact matches multiple RunManifest outputs; provide dataset_id explicitly"
        )
    return matches[0]


def _require_measurement_lineage(
    measurement: MeasurementContract,
    manifest: RunManifest,
) -> None:
    dataset_inputs = tuple(value for value in manifest.inputs if isinstance(value, DatasetRef))
    if measurement.source_dataset not in dataset_inputs:
        raise EmpiricalInputError(
            "MeasurementContract.source_dataset is not represented among upstream "
            "RunManifest DatasetRef inputs"
        )


def load_empirical_measurement(
    *,
    data_path: str | Path,
    measurement_contract_path: str | Path,
    coverage_contract_path: str | Path,
    run_manifest_path: str | Path,
    dataset_id: str | None = None,
) -> EmpiricalMeasurementBundle:
    """Load one sparse empirical measurement without assigning meaning to absent rows.

    The durable table is bound to the hashed DatasetRef emitted in ``RunManifest.outputs``.
    ``MeasurementContract.source_dataset`` retains its upstream meaning as the provenance
    input from which the measurement was constructed and must appear in manifest inputs.
    No rows are reindexed, filled, or projected into experiment semantics here.
    """
    data_file = _require_file(data_path, "empirical data artifact")
    measurement_file = _require_file(measurement_contract_path, "MeasurementContract")
    coverage_file = _require_file(coverage_contract_path, "CoverageContract")
    manifest_file = _require_file(run_manifest_path, "RunManifest")

    measurement = _load_contract(
        measurement_file,
        MeasurementContract,
        "MeasurementContract",
    )
    coverage = _load_contract(coverage_file, CoverageContract, "CoverageContract")
    manifest = _load_contract(manifest_file, RunManifest, "RunManifest")

    artifact_sha256 = _sha256_file(data_file)
    dataset = _resolve_manifest_output(
        manifest,
        content_sha256=artifact_sha256,
        dataset_id=dataset_id,
    )
    if dataset.content_sha256 is None or dataset.content_sha256 != artifact_sha256:
        raise EmpiricalInputError("DatasetRef content SHA-256 does not match loaded artifact")

    _require_measurement_lineage(measurement, manifest)
    if dataset.grain != measurement.output_grain:
        raise EmpiricalInputError(
            "DatasetRef grain does not match MeasurementContract.output_grain"
        )
    require_same_geography(dataset, measurement)
    require_same_period_scheme(dataset, measurement)
    if measurement.coverage != coverage:
        raise EmpiricalInputError(
            "persisted CoverageContract does not match MeasurementContract.coverage"
        )

    table = _read_table(data_file)
    missing_grain = [key for key in dataset.grain.keys if key not in table.columns]
    if missing_grain:
        raise EmpiricalInputError(
            f"empirical table is missing declared grain keys: {', '.join(missing_grain)}"
        )

    return EmpiricalMeasurementBundle(
        dataset=dataset,
        measurement=measurement,
        coverage=coverage,
        run_manifest=manifest,
        data_path=data_file,
        table=table,
    )
