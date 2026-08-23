from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
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

from fcv_harness.calibration import CalibrationThresholds, calibration_estimate
from fcv_harness.empirical_input import EmpiricalMeasurementBundle
from fcv_harness.fully_contracted_calibration import (
    FullyContractedCalibrationSpec,
    FullyContractedTreatmentCellSpec,
    run_fully_contracted_calibration_matrix,
)
from fcv_harness.fully_contracted_experiment import (
    FullyContractedPanelExperimentSpec,
    TreatmentDerivationSpec,
    TreatmentEligibilitySpec,
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
        temporal_end=date(2010, 12, 31),
        observation_semantics="synthetic fully contracted calibration fixture",
        absent_row_semantics="not_observed",
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic fixture",
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
        content_sha256="b" * 64,
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


def _fixture():
    units = [f"AAA1.{index}_1" for index in range(1, 41)]
    geo_uids = [f"geo-{index}" for index in range(1, 41)]
    treatment_periods = ["2003-2004", "2005-2006", "2007-2008"]
    outcome_periods = ["2001-2002", *treatment_periods, "2009-2010"]

    panel_rows = []
    investment_rows = []
    outcome_rows = []
    linkage_rows = []
    for unit_index, (unit, geo_uid) in enumerate(zip(units, geo_uids, strict=True)):
        linkage_rows.append({"GID": unit, "geo_uid": geo_uid})
        for period_index, period_id in enumerate(treatment_periods):
            treated = int((unit_index + period_index) % 2 == 0)
            panel_rows.append({"GID": unit, "TimePeriod": period_id})
            investment_rows.append(
                {
                    "geo_uid": geo_uid,
                    "period_id": period_id,
                    "project_count": treated,
                    "positive_reported_amount_project_count": treated,
                }
            )
        for period_index, period_id in enumerate(outcome_periods):
            # Deliberately nonzero and heterogeneous so the unchanged calibration
            # estimator has finite variance and clustered support.
            fatalities = (
                2.0
                + 0.15 * unit_index
                + 0.4 * period_index
                + 0.25 * np.sin(unit_index + period_index)
            )
            outcome_rows.append(
                {
                    "geo_uid": geo_uid,
                    "period_id": period_id,
                    "native_event_type": "Violence against civilians",
                    "fatalities": fatalities,
                }
            )

    treatment = _bundle(
        pd.DataFrame(investment_rows),
        dataset_id="investments.aiddata_geogcdf.commitment_area_period",
        measure_id="aiddata.geogcdf.commitment_exposure.area_period",
        grain=("geo_uid", "period_id"),
    )
    outcome = _bundle(
        pd.DataFrame(outcome_rows),
        dataset_id="violence.acled.area_period_native_event",
        measure_id="acled.native_event.area_period",
        grain=("geo_uid", "period_id", "native_event_type"),
    )
    return pd.DataFrame(panel_rows), pd.DataFrame(linkage_rows), treatment, outcome


def _experiment() -> FullyContractedPanelExperimentSpec:
    return FullyContractedPanelExperimentSpec(
        experiment_id="geogcdf-acled-e2",
        treatment=MeasurementProjectionSpec(
            measure_id="aiddata.geogcdf.commitment_exposure.area_period",
            selectors={},
            value_column="project_count",
            role="treatment_candidate",
            output_column="investment_value",
        ),
        treatment_derivation=TreatmentDerivationSpec(rule="greater_than", threshold=0.0),
        eligibility=TreatmentEligibilitySpec(
            period_start="2003-2004",
            period_end="2007-2008",
        ),
        outcome=MeasurementProjectionSpec(
            measure_id="acled.native_event.area_period",
            selectors={"native_event_type": "Violence against civilians"},
            value_column="fatalities",
            role="outcome",
            timing_offset=1,
            output_column="outcome_value",
        ),
    )


def test_existing_e2_estimator_accepts_fully_contracted_investment_and_acled_inputs():
    panel, linkage, treatment, outcome = _fixture()
    calibration = FullyContractedCalibrationSpec(
        calibration_id="geogcdf-acled-e2",
        thresholds=CalibrationThresholds(
            min_treated=10,
            min_control=10,
            min_mixed_periods=2,
            signal_draws=4,
        ),
    )
    cells = (
        FullyContractedTreatmentCellSpec(
            cell_id="record_present",
            role="PRIMARY",
            value_column="project_count",
        ),
        FullyContractedTreatmentCellSpec(
            cell_id="positive_reported_amount",
            role="STRESS",
            value_column="positive_reported_amount_project_count",
        ),
    )

    result = run_fully_contracted_calibration_matrix(
        panel,
        _experiment(),
        calibration,
        cells,
        treatment_bundle=treatment,
        outcome_bundle=outcome,
        target_geography=GEO,
        target_period_scheme=PERIOD,
        geography_linkage=linkage,
    )

    assert list(result["stability"]["cell_id"]) == [
        "record_present",
        "positive_reported_amount",
    ]
    primary = result["cells"]["record_present"]
    assert primary["preflight"].estimation_permitted
    assert primary["treatment_projection"].report.measure_id.startswith("aiddata.geogcdf")
    assert primary["outcome_post_projection"].report.measure_id.startswith("acled")
    assert primary["outcome_pre_projection"].report.timing_offset == -1

    # This directly invokes the pre-existing estimator on the fully contracted frame.
    estimate = calibration_estimate(primary["frame"], calibration)
    assert estimate["ok"]
    assert estimate["n"] == 120
    assert estimate["n_units"] == 40
    assert estimate["n_treated"] == 60
    assert estimate["n_control"] == 60


def test_fully_contracted_calibration_matrix_never_needs_legacy_cn_or_jobcat_fields():
    panel, linkage, treatment, outcome = _fixture()
    calibration = FullyContractedCalibrationSpec(
        calibration_id="no-legacy-cn",
        thresholds=CalibrationThresholds(signal_draws=2),
    )
    result = run_fully_contracted_calibration_matrix(
        panel,
        _experiment(),
        calibration,
        (
            FullyContractedTreatmentCellSpec(
                cell_id="primary",
                role="PRIMARY",
                value_column="project_count",
            ),
        ),
        treatment_bundle=treatment,
        outcome_bundle=outcome,
        target_geography=GEO,
        target_period_scheme=PERIOD,
        geography_linkage=linkage,
    )

    frame = result["cells"]["primary"]["frame"]
    forbidden = {
        "jobcat",
        "cn_record_present",
        "cn_amount_positive",
        "annotation_version",
    }
    assert forbidden.isdisjoint(frame.columns)
