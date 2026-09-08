import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd
from empirical_contracts import AuthorityLevel, DataLayer, DatasetRef, GrainSpec

from fcv_harness.calibration import CalibrationThresholds
from fcv_harness.current_e2_reference import (
    CurrentE2ObservabilitySpec,
    CurrentE2ReferenceSpec,
    build_current_reference_panel,
    run_current_e2_from_bundles,
    write_current_e2_reference_outputs,
)
from fcv_harness.empirical_input import EmpiricalMeasurementBundle
from fcv_harness.fully_contracted_calibration import FullyContractedTreatmentCellSpec
from tests_fully_contracted_calibration import GEO, PERIOD, _fixture


class CurrentE2ReferenceTests(unittest.TestCase):
    @staticmethod
    def spec() -> CurrentE2ReferenceSpec:
        return CurrentE2ReferenceSpec(
            reference_id="synthetic-current-e2",
            purpose="calibration",
            geography=GEO,
            period_scheme=PERIOD,
            treatment_measure_id="aiddata.geogcdf.commitment_exposure.area_period",
            outcome_measure_id="acled.native_event.area_period.coverage_certified",
            outcome_native_event_type="Violence against civilians",
            outcome_value_column="fatalities",
            treatment_period_start="2003-2004",
            treatment_period_end="2007-2008",
            cells=(
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
            ),
            thresholds=CalibrationThresholds(
                min_treated=10,
                min_control=10,
                min_mixed_periods=2,
                signal_draws=2,
                signal_target_green=0.0,
                signal_target_red=0.0,
            ),
            observability=CurrentE2ObservabilitySpec(
                effect_sizes_sd=(0.0, 0.20),
                repetitions=2,
                root_seed=20260908,
            ),
        )

    @staticmethod
    def synthetic_inputs():
        panel, linkage, treatment, outcome = _fixture()
        units = panel[["GID"]].drop_duplicates().merge(linkage, on="GID", validate="one_to_one")
        units["source_geo_id"] = units["GID"]
        units["country_iso3"] = "AAA"
        geography = units[["source_geo_id", "geo_uid", "country_iso3"]].copy()
        geography_dataset = DatasetRef(
            dataset_id="gadm_native_adm2",
            version="fixture",
            schema_version="gadm-v1",
            layer=DataLayer.SILVER,
            authority=AuthorityLevel.L3_REBUILT,
            grain=GrainSpec(keys=("source_geo_id",)),
            geography=GEO,
            content_sha256="a" * 64,
        )
        certified_measurement = outcome.measurement.model_copy(
            update={"measure_id": "acled.native_event.area_period.coverage_certified"}
        )
        outcome = replace(outcome, measurement=certified_measurement)
        return geography, geography_dataset, treatment, outcome

    def test_repo_reference_config_is_frozen_as_declared(self):
        spec = CurrentE2ReferenceSpec.from_json("config/current_geogcdf_acled_e2.json")
        self.assertEqual(spec.purpose, "calibration")
        self.assertEqual(spec.geography.id, "gadm:4.1-africa-adm2:native:adm2")
        self.assertEqual(spec.period_scheme.width_years, 2)
        self.assertEqual(spec.period_scheme.anchor_year, 2001)
        self.assertEqual(spec.treatment_period_start, "2003-2004")
        self.assertEqual(spec.treatment_period_end, "2013-2014")
        self.assertEqual(spec.primary_cell.value_column, "project_count")
        self.assertEqual(
            spec.outcome_measure_id,
            "acled.native_event.area_period.coverage_certified",
        )
        self.assertEqual(spec.observability.effect_sizes_sd, (0.0, 0.02, 0.05, 0.10, 0.20))
        self.assertEqual(spec.observability.repetitions, 200)

    def test_reference_panel_comes_from_governed_geography_not_legacy_dhsgc(self):
        geography, _, _, _ = self.synthetic_inputs()
        panel, linkage = build_current_reference_panel(geography, self.spec())
        self.assertEqual(len(panel), 120)
        self.assertEqual(panel["GID"].nunique(), 40)
        self.assertEqual(panel["TimePeriod"].nunique(), 3)
        self.assertEqual(set(panel["country_iso3"]), {"AAA"})
        self.assertEqual(len(linkage), 40)
        self.assertTrue(linkage["GID"].is_unique)
        self.assertTrue(linkage["geo_uid"].is_unique)
        self.assertNotIn("dhsgc_available", panel.columns)

    def test_current_reference_reuses_fully_contracted_gates_and_observability(self):
        geography, geography_dataset, treatment, outcome = self.synthetic_inputs()
        result = run_current_e2_from_bundles(
            geography,
            geography_dataset,
            treatment,
            outcome,
            self.spec(),
            run_observability=True,
        )
        primary = result["calibration"]["cells"]["record_present"]
        self.assertTrue(primary["preflight"].estimation_permitted)
        self.assertTrue(primary["estimate"]["ok"])
        self.assertEqual(primary["estimate"]["n"], 120)
        self.assertTrue(
            primary["treatment_projection"].report.measure_id.startswith("aiddata.geogcdf")
        )
        self.assertEqual(
            primary["outcome_post_projection"].report.measure_id,
            "acled.native_event.area_period.coverage_certified",
        )
        self.assertEqual(primary["outcome_pre_projection"].report.timing_offset, -1)
        self.assertEqual(result["observability_state"], "RUN")
        self.assertEqual(len(result["observability"]["repetition_results"]), 4)

    def test_writer_persists_evidence_but_never_the_analysis_frame(self):
        geography, geography_dataset, treatment, outcome = self.synthetic_inputs()
        result = run_current_e2_from_bundles(
            geography,
            geography_dataset,
            treatment,
            outcome,
            self.spec(),
            run_observability=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = write_current_e2_reference_outputs(result, tmp)
            files = {path.relative_to(out).as_posix() for path in Path(out).rglob("*") if path.is_file()}
            payload = json.loads((Path(out) / "reference_run.json").read_text())

        self.assertIn("reference_run.json", files)
        self.assertIn("calibration/measurement_stability.csv", files)
        self.assertIn("calibration/cell_gates.csv", files)
        self.assertIn("calibration/cells/record_present/placebo.csv", files)
        self.assertIn("observability/effect_size_summary.csv", files)
        self.assertIn("observability/null_calibration_summary.csv", files)
        self.assertFalse(any("analysis_frame" in name for name in files))
        self.assertFalse(payload["analysis_panel"]["analysis_frame_persisted"])
        self.assertEqual(len(payload["analysis_panel"]["frame_sha256_by_cell"]["record_present"]), 64)
        self.assertEqual(
            payload["inputs"]["outcome_measurement"]["measure_id"],
            "acled.native_event.area_period.coverage_certified",
        )


if __name__ == "__main__":
    unittest.main()
