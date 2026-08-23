from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from empirical_contracts import (
    AuthorityLevel,
    CoverageContract,
    DataLayer,
    DatasetRef,
    GeographySpec,
    GrainSpec,
    MeasurementContract,
    PeriodScheme,
    RunManifest,
)
from fcv_harness.empirical_input import (
    EmpiricalCompatibilityError,
    EmpiricalInputError,
    load_empirical_measurement,
    require_same_geography,
    require_same_period_scheme,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, model) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _expect(error_type, fn, contains: str | None = None):
    try:
        fn()
    except error_type as error:
        if contains is not None:
            assert contains in str(error), str(error)
        return error
    raise AssertionError(f"expected {error_type.__name__}")


def _fixture(
    root: Path,
    *,
    rows: list[dict] | None = None,
    dataset_geo: GeographySpec | None = None,
    measurement_geo: GeographySpec | None = None,
    dataset_period: PeriodScheme | None = None,
    measurement_period: PeriodScheme | None = None,
    measurement_source: DatasetRef | None = None,
    manifest_inputs: tuple[DatasetRef, ...] | None = None,
    manifest_outputs: tuple[DatasetRef, ...] | None = None,
    coverage_payload: dict | None = None,
):
    rows = rows or [
        {"geo_uid": "A", "period_id": "2001-2002", "value": 3.0},
        {"geo_uid": "C", "period_id": "2001-2002", "value": None},
    ]
    data_path = root / "measurement.csv"
    pd.DataFrame(rows).to_csv(data_path, index=False)

    geo = dataset_geo or GeographySpec(
        provider="gadm",
        version="4.1",
        scheme="admin",
        level="2",
        scheme_version="2026-08",
    )
    measure_geo = measurement_geo or geo
    period = dataset_period or PeriodScheme(width_years=2, anchor_year=2001)
    measure_period = measurement_period or period
    grain = GrainSpec(keys=("geo_uid", "period_id"))
    source = measurement_source or DatasetRef(
        dataset_id="synthetic.events.silver",
        version="snapshot-1",
        schema_version="synthetic-silver-v1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=("event_row_id",)),
        content_sha256="1" * 64,
    )
    dataset = DatasetRef(
        dataset_id="synthetic.area_period.measurement",
        version="fixture-1",
        schema_version="synthetic-gold-v1",
        layer=DataLayer.GOLD,
        authority=AuthorityLevel.L3_REBUILT,
        grain=grain,
        geography=geo,
        period_scheme=period,
        content_sha256=_sha256(data_path),
    )
    coverage = CoverageContract(
        geography_scope="synthetic declared support",
        observation_semantics="sparse observed rows only",
        absent_row_semantics="unknown",
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic fixture",
    )
    measurement = MeasurementContract(
        measure_id="synthetic.area_period",
        description="synthetic sparse measurement",
        source_dataset=source,
        output_grain=grain,
        coverage=coverage,
        geography=measure_geo,
        period_scheme=measure_period,
    )
    manifest = RunManifest(
        run_id="synthetic-measurement-run",
        package="fcv-empirical-data",
        package_version="0.1.0",
        code_commit="abc123",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        inputs=manifest_inputs if manifest_inputs is not None else (source,),
        outputs=manifest_outputs if manifest_outputs is not None else (dataset,),
    )

    measurement_path = root / "measurement_contract.json"
    coverage_path = root / "coverage.json"
    manifest_path = root / "run_manifest.json"
    _write_json(measurement_path, measurement)
    if coverage_payload is None:
        _write_json(coverage_path, coverage)
    else:
        coverage_path.write_text(json.dumps(coverage_payload), encoding="utf-8")
    _write_json(manifest_path, manifest)
    return {
        "data": data_path,
        "measurement": measurement_path,
        "coverage": coverage_path,
        "manifest": manifest_path,
        "dataset": dataset,
        "source": source,
        "geo": geo,
        "period": period,
    }


def _load(paths):
    return load_empirical_measurement(
        data_path=paths["data"],
        measurement_contract_path=paths["measurement"],
        coverage_contract_path=paths["coverage"],
        run_manifest_path=paths["manifest"],
    )


with tempfile.TemporaryDirectory() as td:
    paths = _fixture(Path(td))
    bundle = _load(paths)
    assert bundle.dataset == paths["dataset"]
    assert bundle.measurement.source_dataset == paths["source"]
    assert bundle.coverage.absent_row_semantics == "unknown"
    assert bundle.authority == AuthorityLevel.L3_REBUILT
    assert bundle.coverage.authority == AuthorityLevel.L3_REBUILT
    assert len(bundle.table) == 2
    assert set(bundle.table["geo_uid"]) == {"A", "C"}
    assert "B" not in set(bundle.table["geo_uid"])
    assert pd.isna(bundle.table.loc[bundle.table["geo_uid"] == "C", "value"]).all()
    assert not any(column.startswith("filled_") for column in bundle.table.columns)

with tempfile.TemporaryDirectory() as td:
    paths = _fixture(Path(td))
    paths["data"].write_text(
        paths["data"].read_text() + "B,2001-2002,0\n", encoding="utf-8"
    )
    _expect(
        EmpiricalInputError,
        lambda: _load(paths),
        "does not identify the loaded artifact",
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    paths = _fixture(root)
    foreign_source = paths["source"].model_copy(update={"dataset_id": "foreign.silver"})
    paths = _fixture(
        root,
        measurement_source=foreign_source,
        manifest_inputs=(paths["source"],),
    )
    _expect(EmpiricalInputError, lambda: _load(paths), "source_dataset")

with tempfile.TemporaryDirectory() as td:
    paths = _fixture(
        Path(td),
        rows=[{"geo_uid": "A", "value": 1.0}],
    )
    _expect(EmpiricalInputError, lambda: _load(paths), "missing declared grain keys")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    dataset_geo = GeographySpec(
        provider="gadm",
        version="4.1",
        scheme="admin",
        level="2",
        scheme_version="2026-08",
    )
    measurement_geo = dataset_geo.model_copy(update={"version": "4.0"})
    paths = _fixture(root, dataset_geo=dataset_geo, measurement_geo=measurement_geo)
    _expect(
        EmpiricalCompatibilityError,
        lambda: _load(paths),
        "geography contract mismatch",
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    dataset_period = PeriodScheme(width_years=2, anchor_year=2001)
    measurement_period = PeriodScheme(width_years=2, anchor_year=2000)
    paths = _fixture(
        root,
        dataset_period=dataset_period,
        measurement_period=measurement_period,
    )
    _expect(
        EmpiricalCompatibilityError,
        lambda: _load(paths),
        "period scheme contract mismatch",
    )

with tempfile.TemporaryDirectory() as td:
    paths = _fixture(
        Path(td),
        coverage_payload={
            "geography_scope": "broken",
            "observation_semantics": "missing required authority and basis",
            "absent_row_semantics": "unknown",
        },
    )
    _expect(EmpiricalInputError, lambda: _load(paths), "invalid CoverageContract")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    paths = _fixture(root)
    other_output = paths["dataset"].model_copy(
        update={"dataset_id": "other.output", "content_sha256": "2" * 64}
    )
    paths = _fixture(root, manifest_outputs=(other_output,))
    _expect(
        EmpiricalInputError,
        lambda: _load(paths),
        "does not identify the loaded artifact",
    )

# Compatibility is based on full declared contract identity, not convenient labels.
geo = GeographySpec(provider="gadm", version="4.1", scheme="admin", level="2")
assert require_same_geography(geo, geo.model_copy()) == geo
_expect(
    EmpiricalCompatibilityError,
    lambda: require_same_geography(geo, geo.model_copy(update={"version": "4.0"})),
)
period = PeriodScheme(width_years=2, anchor_year=2001)
assert require_same_period_scheme(period, period.model_copy()) == period
_expect(
    EmpiricalCompatibilityError,
    lambda: require_same_period_scheme(
        period, period.model_copy(update={"anchor_year": 2000})
    ),
)

print("CONTRACTED EMPIRICAL INPUT TEST PASSED")
