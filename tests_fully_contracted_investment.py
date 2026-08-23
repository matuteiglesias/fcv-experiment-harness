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
from fcv_harness.fully_contracted_experiment import (
    FullyContractedPanelExperimentSpec,
    TreatmentDerivationSpec,
    TreatmentEligibilitySpec,
    run_fully_contracted_experiment_preflight,
)
from fcv_harness.measurement_projection import MeasurementProjectionSpec

GEO = GeographySpec(provider="gadm", version="4.1", scheme="native", level="adm2")
PERIOD = PeriodScheme(width_years=2, anchor_year=2001)


def _bundle(
    table: pd.DataFrame,
    *,
    dataset_id: str,
    measure_id: str,
    grain: tuple[str, ...],
    absent_row_semantics: str = "not_observed",
) -> EmpiricalMeasurementBundle:
    source = DatasetRef(
        dataset_id=f"{dataset_id}.source",
        version="source-v1",
        schema_version="v1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=("source_row_id",)),
    )
    coverage = CoverageContract(
        geography_scope=GEO.id,
        temporal_start=date(2001, 1, 1),
        temporal_end=date(2008, 12, 31),
        observation_semantics="synthetic contracted measurement",
        absent_row_semantics=absent_row_semantics,
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic unit-test coverage",
    )
    dataset = DatasetRef(
        dataset_id=dataset_id,
        version="v1",
        schema_version="v1",
        layer=DataLayer.GOLD,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=grain),
        geography=GEO,
        period_scheme=PERIOD,
        content_sha256="a" * 64,
    )
    measurement = MeasurementContract(
        measure_id=measure_id,
        description="synthetic",
        source_dataset=source,
        output_grain=GrainSpec(keys=grain),
        coverage=coverage,
        geography=GEO,
        period_scheme=PERIOD,
    )
    manifest = RunManifest(
        run_id=f"{dataset_id}-run",
        package="fcv-empirical-data",
        package_version="0.1.0",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        inputs=(source,),
        outputs=(dataset,),
    )
    return EmpiricalMeasurementBundle(
        dataset=dataset,
        measurement=measurement,
        coverage=coverage,
        run_manifest=manifest,
        data_path=Path("/synthetic/not-read.parquet"),
        table=table,
    )


def _treatment_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "geo_uid": ["geo-a", "geo-b", "geo-a", "geo-b"],
            "period_id": ["2003-2004", "2003-2004", "2005-2006", "2005-2006"],
            "project_count": [1, 0, 0, 2],
            "positive_reported_amount_project_count": [1, 0, 0, 1],
        }
    )


def _outcome_table() -> pd.DataFrame:
    rows = []
    for geo_uid, base in (("geo-a", 1.0), ("geo-b", 2.0)):
        for index, period_id in enumerate(
            ["2001-2002", "2003-2004", "2005-2006", "2007-2008"]
        ):
            rows.append(
                {
                    "geo_uid": geo_uid,
                    "period_id": period_id,
                    "native_event_type": "Violence against civilians",
                    "fatalities": base + index,
                }
            )
    return pd.DataFrame(rows)


def _spec(*, treatment_value: str = "project_count") -> FullyContractedPanelExperimentSpec:
    return FullyContractedPanelExperimentSpec(
        experiment_id="china-acled-contract-test",
        treatment=MeasurementProjectionSpec(
            measure_id="aiddata.geogcdf.commitment_exposure.area_period",
            selectors={},
            value_column=treatment_value,
            role="treatment_candidate",
            timing_offset=0,
            output_column="investment_value",
        ),
        treatment_derivation=TreatmentDerivationSpec(rule="greater_than", threshold=0),
        eligibility=TreatmentEligibilitySpec(
            period_start="2003-2004",
            period_end="2005-2006",
        ),
        outcome=MeasurementProjectionSpec(
            measure_id="acled.native_event.area_period",
            selectors={"native_event_type": "Violence against civilians"},
            value_column="fatalities",
            role="outcome",
            timing_offset=1,
            output_column="vac_post",
        ),
    )


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GID": ["EXA.1_1", "EXA.2_1", "EXA.1_1", "EXA.2_1"],
            "TimePeriod": ["2003-2004", "2003-2004", "2005-2006", "2005-2006"],
        }
    )


def _linkage() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "GID": ["EXA.1_1", "EXA.2_1"],
            "geo_uid": ["geo-a", "geo-b"],
        }
    )


def _run(spec: FullyContractedPanelExperimentSpec, treatment_table=None):
    treatment = _bundle(
        _treatment_table() if treatment_table is None else treatment_table,
        dataset_id="investments.aiddata_geogcdf.commitment_area_period",
        measure_id="aiddata.geogcdf.commitment_exposure.area_period",
        grain=("geo_uid", "period_id"),
    )
    outcome = _bundle(
        _outcome_table(),
        dataset_id="violence.acled.area_period_native_event",
        measure_id="acled.native_event.area_period",
        grain=("geo_uid", "period_id", "native_event_type"),
        absent_row_semantics="unknown",
    )
    return run_fully_contracted_experiment_preflight(
        _panel(),
        spec,
        treatment_bundle=treatment,
        outcome_bundle=outcome,
        target_geography=GEO,
        target_period_scheme=PERIOD,
        geography_linkage=_linkage(),
    )


def test_project_count_is_projected_then_derived_into_treatment_downstream():
    result = _run(_spec())

    assert result.estimation_permitted
    assert result.frame["treatment"].tolist() == [1, 0, 0, 1]
    assert result.frame["treatment_measurement_value"].tolist() == [1, 0, 0, 2]
    assert result.frame["treatment_derivation_status"].tolist() == [
        "treated_by_declared_rule",
        "control_by_declared_rule",
        "control_by_declared_rule",
        "treated_by_declared_rule",
    ]
    assert result.treatment_projection.report.measure_id.startswith("aiddata.geogcdf")
    assert result.outcome_projection.report.measure_id.startswith("acled")


def test_positive_reported_amount_project_count_is_predeclared_stress_treatment():
    result = _run(_spec(treatment_value="positive_reported_amount_project_count"))

    assert result.estimation_permitted
    assert result.frame["treatment"].tolist() == [1, 0, 0, 1]
    assert result.frame["treatment_measurement_value"].tolist() == [1, 0, 0, 1]


def test_missing_contracted_investment_row_does_not_become_control():
    treatment = _treatment_table().loc[
        ~(
            _treatment_table()["geo_uid"].eq("geo-b")
            & _treatment_table()["period_id"].eq("2005-2006")
        )
    ].copy()
    result = _run(_spec(), treatment_table=treatment)

    row = result.frame[
        result.frame["GID"].eq("EXA.2_1")
        & result.frame["TimePeriod"].eq("2005-2006")
    ].iloc[0]
    assert pd.isna(row["treatment"])
    assert row["treatment_measurement_status"] == "unresolved"
    assert row["treatment_derivation_status"] == "treatment_measurement_unavailable"
    assert not result.estimation_permitted


def test_fully_contracted_path_has_no_jobcat_or_legacy_source_columns():
    result = _run(_spec())

    forbidden = {
        "jobcat",
        "cn_record_present",
        "cn_amount_positive",
        "wbad_record_present",
        "wbkg_record_present",
        "annotation_version",
    }
    assert forbidden.isdisjoint(result.frame.columns)


def test_post_outcome_timing_remains_an_explicit_downstream_choice():
    result = _run(_spec())

    assert result.frame["outcome_measurement_period_id"].tolist() == [
        "2005-2006",
        "2005-2006",
        "2007-2008",
        "2007-2008",
    ]
    assert result.frame["outcome_value"].tolist() == [3.0, 4.0, 4.0, 5.0]
    assert result.outcome_projection.report.timing_offset == 1
