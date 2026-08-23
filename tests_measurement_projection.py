from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
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
from fcv_harness.empirical_input import EmpiricalMeasurementBundle
from fcv_harness.measurement_projection import (
    MeasurementProjectionError,
    MeasurementProjectionSpec,
    project_empirical_measurement,
)


def _expect(error_type, fn, contains: str | None = None):
    try:
        fn()
    except error_type as error:
        if contains is not None:
            assert contains in str(error), str(error)
        return error
    raise AssertionError(f"expected {error_type.__name__}")


def _bundle(absent_semantics="unknown", *, temporal_start=None, temporal_end=None):
    geo = GeographySpec(
        provider="gadm",
        version="4.1",
        scheme="admin",
        level="2",
    )
    period = PeriodScheme(width_years=2, anchor_year=2001)
    source = DatasetRef(
        dataset_id="violence.events.silver",
        version="snapshot-1",
        schema_version="events-v1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=("event_row_id",)),
        content_sha256="1" * 64,
    )
    output_grain = GrainSpec(keys=("geo_uid", "period_id", "native_event_type"))
    dataset = DatasetRef(
        dataset_id="violence.area_period_native_event",
        version="gold-1",
        schema_version="native-event-v1",
        layer=DataLayer.GOLD,
        authority=AuthorityLevel.L3_REBUILT,
        grain=output_grain,
        geography=geo,
        period_scheme=period,
        content_sha256="2" * 64,
    )
    coverage = CoverageContract(
        geography_scope=geo.id,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
        observation_semantics="sparse observed native-event aggregates",
        absent_row_semantics=absent_semantics,
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic projection fixture",
    )
    measurement = MeasurementContract(
        measure_id="acled.native_event.area_period",
        description="normalized native event measurement",
        source_dataset=source,
        output_grain=output_grain,
        coverage=coverage,
        geography=geo,
        period_scheme=period,
    )
    manifest = RunManifest(
        run_id="projection-fixture",
        package="fcv-empirical-data",
        package_version="0.1.0",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        inputs=(source,),
        outputs=(dataset,),
    )
    table = pd.DataFrame(
        [
            {
                "geo_uid": "gadm:4.1:adm2:AGO.1.1_1",
                "period_id": "2001-2002",
                "native_event_type": "Violence against civilians",
                "fatalities": 0.0,
            },
            {
                "geo_uid": "gadm:4.1:adm2:AGO.1.1_1",
                "period_id": "2005-2006",
                "native_event_type": "Violence against civilians",
                "fatalities": 5.0,
            },
            {
                "geo_uid": "gadm:4.1:adm2:AGO.1.1_1",
                "period_id": "2005-2006",
                "native_event_type": "Battles",
                "fatalities": 99.0,
            },
        ]
    )
    return EmpiricalMeasurementBundle(
        dataset=dataset,
        measurement=measurement,
        coverage=coverage,
        run_manifest=manifest,
        data_path=Path("synthetic-not-read.parquet"),
        table=table,
    )


def _target():
    return pd.DataFrame(
        [
            {"GID": "AGO.1.1_1", "TimePeriod": "2003-2004"},
            {"GID": "KEN.1.1_1", "TimePeriod": "2003-2004"},
        ]
    )


def _linkage():
    return pd.DataFrame(
        [
            {"GID": "AGO.1.1_1", "geo_uid": "gadm:4.1:adm2:AGO.1.1_1"},
            {"GID": "KEN.1.1_1", "geo_uid": "gadm:4.1:adm2:KEN.1.1_1"},
        ]
    )


def _use(offset=0):
    return MeasurementProjectionSpec(
        measure_id="acled.native_event.area_period",
        selectors={"native_event_type": "Violence against civilians"},
        value_column="fatalities",
        role="outcome",
        timing_offset=offset,
        output_column="vac_fatalities",
    )


bundle = _bundle()
result = project_empirical_measurement(
    bundle,
    _target(),
    _use(offset=1),
    target_geography=bundle.dataset.geography,
    target_period_scheme=bundle.dataset.period_scheme,
    target_unit_col="GID",
    target_period_col="TimePeriod",
    geography_linkage=_linkage(),
)
ago = result.frame.loc[result.frame["GID"] == "AGO.1.1_1"].iloc[0]
ken = result.frame.loc[result.frame["GID"] == "KEN.1.1_1"].iloc[0]
assert ago["vac_fatalities"] == 5.0
assert ago["projection_status"] == "observed"
assert ago["measurement_period_id"] == "2005-2006"
assert pd.isna(ken["vac_fatalities"])
assert ken["projection_status"] == "unresolved"
assert ken["projection_detail"] == "absent_row_unknown"
assert result.report.input_row_count == 3
assert result.report.selected_row_count == 2
assert result.report.selector_row_counts["native_event_type=Violence against civilians"] == 2
assert result.report.output_row_count == 2
assert (
    result.report.observed_count
    + result.report.structural_zero_count
    + result.report.outside_coverage_count
    + result.report.unresolved_count
    == result.report.output_row_count
)

# Zero-fatality Gold rows are observations, not inferred absence.
pre = project_empirical_measurement(
    bundle,
    _target().iloc[[0]],
    _use(offset=-1),
    target_geography=bundle.dataset.geography,
    target_period_scheme=bundle.dataset.period_scheme,
    target_unit_col="GID",
    target_period_col="TimePeriod",
    geography_linkage=_linkage(),
)
row = pre.frame.iloc[0]
assert row["measurement_period_id"] == "2001-2002"
assert row["vac_fatalities"] == 0.0
assert row["projection_status"] == "observed"
assert row["measurement_record_present"]

# Sparse absence can become zero only when the upstream coverage contract licenses it.
licensed = _bundle(
    "zero_within_verified_coverage",
    temporal_start=date(2001, 1, 1),
    temporal_end=date(2008, 12, 31),
)
zeroed = project_empirical_measurement(
    licensed,
    _target().iloc[[1]],
    _use(offset=0),
    target_geography=licensed.dataset.geography,
    target_period_scheme=licensed.dataset.period_scheme,
    target_unit_col="GID",
    target_period_col="TimePeriod",
    geography_linkage=_linkage(),
)
row = zeroed.frame.iloc[0]
assert row["vac_fatalities"] == 0.0
assert row["projection_status"] == "structural_zero"
assert not row["measurement_record_present"]
assert zeroed.report.structural_zero_count == 1

# Outside temporal coverage remains unavailable even under a structural-zero license.
outside_target = pd.DataFrame([{"GID": "KEN.1.1_1", "TimePeriod": "2009-2010"}])
outside = project_empirical_measurement(
    licensed,
    outside_target,
    _use(offset=0),
    target_geography=licensed.dataset.geography,
    target_period_scheme=licensed.dataset.period_scheme,
    target_unit_col="GID",
    target_period_col="TimePeriod",
    geography_linkage=_linkage(),
)
row = outside.frame.iloc[0]
assert pd.isna(row["vac_fatalities"])
assert row["projection_status"] == "outside_coverage"
assert outside.report.outside_coverage_count == 1

wrong_geo = bundle.dataset.geography.model_copy(update={"version": "4.0"})
_expect(
    MeasurementProjectionError,
    lambda: project_empirical_measurement(
        bundle,
        _target(),
        _use(),
        target_geography=wrong_geo,
        target_period_scheme=bundle.dataset.period_scheme,
        target_unit_col="GID",
        target_period_col="TimePeriod",
        geography_linkage=_linkage(),
    ),
    "geography",
)
wrong_period = PeriodScheme(width_years=2, anchor_year=2000)
_expect(
    MeasurementProjectionError,
    lambda: project_empirical_measurement(
        bundle,
        _target(),
        _use(),
        target_geography=bundle.dataset.geography,
        target_period_scheme=wrong_period,
        target_unit_col="GID",
        target_period_col="TimePeriod",
        geography_linkage=_linkage(),
    ),
    "period",
)

# Timing is part of the downstream use, not the upstream measurement contract.
assert replace(_use(), timing_offset=1).timing_offset == 1
assert replace(_use(), timing_offset=-1).timing_offset == -1

# Active contracted projection code must not reconstruct raw ACLED ingestion semantics.
import fcv_harness.contracted_experiment as contracted_experiment
import fcv_harness.contracted_surface as contracted_surface
import fcv_harness.measurement_projection as measurement_projection

for module in (measurement_projection, contracted_surface, contracted_experiment):
    text = Path(module.__file__).read_text(encoding="utf-8")
    for raw_name in ("FATALITIES", "EVENT_TYPE", "GEO_PRECISION"):
        assert raw_name not in text, (module.__name__, raw_name)

print("CONTRACTED MEASUREMENT PROJECTION TEST PASSED")
