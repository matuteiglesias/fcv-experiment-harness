from __future__ import annotations

import hashlib
import json
import tempfile
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
from fcv_harness.analysis_surface import AnalysisUniverseSpec
from fcv_harness.calibration import (
    CalibrationCellSpec,
    CalibrationMatrixSpec,
    CalibrationThresholds,
)
from fcv_harness.canonical import CanonicalPanelSpec
from fcv_harness.canonical_experiment import EligibilitySpec, TreatmentMeasurementSpec
from fcv_harness.contracted_calibration import run_contracted_calibration_matrix
from fcv_harness.contracted_experiment import (
    ContractedPanelExperimentSpec,
    run_contracted_experiment_preflight,
)
from fcv_harness.contracted_surface import (
    ContractedAnalysisSurfaceSpec,
    run_contracted_analysis_surface_checkpoint,
)
from fcv_harness.empirical_input import load_empirical_measurement
from fcv_harness.measurement_projection import MeasurementProjectionSpec


def _write_model(path: Path, model) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    geography = GeographySpec(
        provider="gadm",
        version="4.1",
        scheme="admin",
        level="2",
    )
    period_scheme = PeriodScheme(width_years=2, anchor_year=2001)
    periods = ["2001-2002", "2003-2004", "2005-2006", "2007-2008"]

    linkage_rows = []
    lattice_rows = []
    wbad_rows = []
    gold_rows = []
    treated_units = set()

    for i in range(24):
        country = "AGO" if i < 12 else "KEN"
        gid = f"{country}.{i + 1}.1_1"
        geo_uid = f"gadm:4.1:adm2:{gid}"
        linkage_rows.append({"GID": gid, "geo_uid": geo_uid})
        if i % 12 < 6:
            treated_units.add(gid)

        for j, period in enumerate(periods):
            lattice_rows.append(
                {
                    "GID": gid,
                    "TimePeriod": period,
                    "rain": float((i + j) % 5),
                }
            )
            if gid in treated_units and period in {"2003-2004", "2005-2006"}:
                wbad_rows.append(
                    {
                        "GID": gid,
                        "TimePeriod": period,
                        "jobcat": 1,
                        "Amount_USD": float(10 + i),
                    }
                )

            # Omit a subset of rows. This synthetic coverage contract explicitly
            # licenses those sparse absences as structural zeros within 2001-2008.
            if (i + j) % 7 != 0:
                gold_rows.append(
                    {
                        "geo_uid": geo_uid,
                        "period_id": period,
                        "native_event_type": "Violence against civilians",
                        "fatalities": float((2 * i + j) % 6),
                    }
                )
            if i < 3 and period == "2005-2006":
                gold_rows.append(
                    {
                        "geo_uid": geo_uid,
                        "period_id": period,
                        "native_event_type": "Battles",
                        "fatalities": 100.0 + i,
                    }
                )

    linkage = pd.DataFrame(linkage_rows)
    loaded = {
        "lattice": pd.DataFrame(lattice_rows),
        "wbad": pd.DataFrame(wbad_rows),
    }

    canonical_payload = {
        "panel_id": "contracted-demo",
        "geography": {"scheme": "admin", "level": 2},
        "time": {"period_years": 2, "alignment_year": 2001},
        "annotation_version": "legacy_2023",
        "sources": {
            "lattice": {
                "path": "unused_lattice.csv",
                "kind": "lattice",
                "grain": ["GID", "TimePeriod"],
                "prefix": "dhsgc",
            },
            "wbad": {
                "path": "unused_wbad.csv",
                "kind": "project",
                "grain": ["GID", "TimePeriod", "jobcat"],
                "prefix": "wbad",
                "amount_col": "Amount_USD",
                "jobcat_col": "jobcat",
            },
        },
    }
    canonical_path = root / "canonical.json"
    canonical_path.write_text(json.dumps(canonical_payload), encoding="utf-8")
    canonical_spec = CanonicalPanelSpec.from_json(canonical_path)

    data_path = root / "contracted_gold.csv"
    pd.DataFrame(gold_rows).to_csv(data_path, index=False)
    source_dataset = DatasetRef(
        dataset_id="violence.acled.events",
        version="synthetic-snapshot",
        schema_version="acled-event-silver-v1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=("event_row_id",)),
        content_sha256="1" * 64,
    )
    gold_grain = GrainSpec(keys=("geo_uid", "period_id", "native_event_type"))
    gold_dataset = DatasetRef(
        dataset_id="violence.acled.area_period_native_event",
        version="synthetic-gold",
        schema_version="acled-native-event-gold-v1",
        layer=DataLayer.GOLD,
        authority=AuthorityLevel.L3_REBUILT,
        grain=gold_grain,
        geography=geography,
        period_scheme=period_scheme,
        content_sha256=_sha256(data_path),
    )
    coverage = CoverageContract(
        geography_scope=geography.id,
        temporal_start=date(2001, 1, 1),
        temporal_end=date(2008, 12, 31),
        observation_semantics="synthetic sparse observed native-event aggregates",
        absent_row_semantics="zero_within_verified_coverage",
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic fully verified projection support",
    )
    measurement = MeasurementContract(
        measure_id="acled.native_event.area_period",
        description="synthetic contracted native-event measurement",
        source_dataset=source_dataset,
        output_grain=gold_grain,
        coverage=coverage,
        geography=geography,
        period_scheme=period_scheme,
    )
    manifest = RunManifest(
        run_id="synthetic-measurement",
        package="fcv-empirical-data",
        package_version="0.1.0",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        inputs=(source_dataset,),
        outputs=(gold_dataset,),
    )
    measurement_path = root / "measurement_contract.json"
    coverage_path = root / "coverage.json"
    manifest_path = root / "run_manifest.json"
    _write_model(measurement_path, measurement)
    _write_model(coverage_path, coverage)
    _write_model(manifest_path, manifest)

    bundle = load_empirical_measurement(
        data_path=data_path,
        measurement_contract_path=measurement_path,
        coverage_contract_path=coverage_path,
        run_manifest_path=manifest_path,
    )

    vac_use = MeasurementProjectionSpec(
        measure_id="acled.native_event.area_period",
        selectors={"native_event_type": "Violence against civilians"},
        value_column="fatalities",
        role="analysis_surface",
        timing_offset=0,
        output_column="vac_fatalities",
    )
    surface_spec = ContractedAnalysisSurfaceSpec(
        surface_id="contracted-demo-surface",
        canonical_manifest="unused.json",
        universe=AnalysisUniverseSpec(
            mode="canonical_lattice",
            authority="synthetic_restricted_universe",
        ),
        geography=geography,
        period_scheme=period_scheme,
        measurement=vac_use,
    )
    surface = run_contracted_analysis_surface_checkpoint(
        surface_spec,
        canonical_spec,
        loaded,
        bundle=bundle,
        geography_linkage=linkage,
    )

    assert len(surface["panel"]) == 24 * 4
    assert "vac_fatalities" in surface["panel"].columns
    assert "acled_deaths_violence_against_civilians" not in surface["panel"].columns
    projection_report = surface["projection"].report
    assert projection_report.input_dataset == gold_dataset
    assert projection_report.measure_id == measurement.measure_id
    assert projection_report.structural_zero_count > 0
    assert projection_report.unresolved_count == 0
    assert projection_report.outside_coverage_count == 0
    assert projection_report.output_row_count == len(surface["panel"])

    experiment_spec = ContractedPanelExperimentSpec(
        experiment_id="contracted-demo-e1",
        panel_id=canonical_spec.panel_id,
        treatment=TreatmentMeasurementSpec(
            source="wbad",
            definition="record_present",
            annotation_version="legacy_2023",
        ),
        eligibility=EligibilitySpec(
            treatment_period_start="2003-2004",
            treatment_period_end="2005-2006",
        ),
        outcome=replace(
            vac_use,
            role="outcome",
            timing_offset=1,
            output_column="outcome_value",
        ),
    )
    preflight = run_contracted_experiment_preflight(
        surface["panel"],
        experiment_spec,
        bundle=bundle,
        target_geography=geography,
        target_period_scheme=period_scheme,
        geography_linkage=linkage,
        source_only_keys=surface["source_outside"]["source_only_keys"],
    )
    assert preflight["estimation_permitted"]
    assert preflight["projection"].report.timing_offset == 1
    assert preflight["frame"].loc[
        preflight["frame"]["eligible"], "outcome_value"
    ].notna().all()

    matrix = CalibrationMatrixSpec(
        matrix_id="contracted-demo-e2",
        surface_manifest="unused.json",
        treatment_period_start="2003-2004",
        treatment_period_end="2005-2006",
        annotation_version="legacy_2023",
        cells=[
            CalibrationCellSpec(
                cell_id="wbad_record_present",
                source="wbad",
                definition="record_present",
                role="PRIMARY",
            )
        ],
        thresholds=CalibrationThresholds(
            min_treated=5,
            min_control=5,
            min_mixed_periods=2,
            max_zero_share_green=0.99,
            max_zero_share_red=1.0,
            max_abs_pre_smd_green=0.25,
            max_abs_pre_smd_red=2.0,
            max_placebo_std_green=10.0,
            max_placebo_std_red=20.0,
            plausible_effect_sd=0.20,
            signal_draws=3,
            signal_target_green=0.0,
            signal_target_red=0.0,
            seed=20260823,
        ),
    )
    e2 = run_contracted_calibration_matrix(
        surface["panel"],
        matrix,
        surface_spec,
        surface["gates"],
        surface["source_outside"]["source_only_keys"],
        canonical_spec.panel_id,
        bundle=bundle,
        geography_linkage=linkage,
    )
    cell = e2["cells"]["wbad_record_present"]
    assert cell["post_projection"].report.timing_offset == 1
    assert cell["pre_projection"].report.timing_offset == -1
    assert cell["estimate"]["ok"], cell["estimate"]
    assert cell["signal_recovery"]["ok"], cell["signal_recovery"]
    assert cell["estimate"]["n"] > 0

print("CONTRACTED ACLED E1/E2 INTEGRATION TEST PASSED")
