import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fcv_harness.current_e2_reference import run_current_e2_from_bundles
from fcv_harness.current_e2_robustness import (
    CurrentE2RobustnessSuite,
    CurrentE2RobustnessVariant,
    run_current_e2_robustness,
    write_current_e2_robustness_outputs,
)
from tests_current_e2_reference import CurrentE2ReferenceTests


class CurrentE2RobustnessTests(unittest.TestCase):
    @staticmethod
    def suite() -> CurrentE2RobustnessSuite:
        return CurrentE2RobustnessSuite(
            suite_id="synthetic-robustness",
            purpose="calibration_sensitivity",
            base_config="synthetic",
            reading_rule="Do not select variants by result.",
            variants=(
                CurrentE2RobustnessVariant(
                    variant_id="project_count_gt1",
                    dimension="treatment_intensity",
                    description="Synthetic stricter treatment threshold.",
                    treatment_value_column="project_count",
                    treatment_threshold=1.0,
                ),
                CurrentE2RobustnessVariant(
                    variant_id="core_window",
                    dimension="time_window",
                    description="Synthetic core-window trim.",
                    treatment_period_start="2005-2006",
                    treatment_period_end="2007-2008",
                ),
                CurrentE2RobustnessVariant(
                    variant_id="event_count",
                    dimension="outcome_metric",
                    description="Synthetic alternate native outcome metric.",
                    outcome_value_column="event_count",
                ),
            ),
        )

    @staticmethod
    def canonical_result():
        geography, geography_dataset, treatment, outcome = CurrentE2ReferenceTests.synthetic_inputs()
        outcome_table = outcome.table.copy()
        outcome_table["event_count"] = (outcome_table["fatalities"] * 2.0 + 1.0).round()
        outcome = replace(outcome, table=outcome_table)
        return run_current_e2_from_bundles(
            geography,
            geography_dataset,
            treatment,
            outcome,
            CurrentE2ReferenceTests.spec(),
            run_observability=False,
        )

    def test_repo_suite_is_small_predeclared_and_one_dimension_at_a_time(self):
        suite = CurrentE2RobustnessSuite.from_json(
            "config/current_geogcdf_acled_e2_robustness.json"
        )
        self.assertEqual(suite.purpose, "calibration_sensitivity")
        self.assertEqual(
            [variant.variant_id for variant in suite.variants],
            ["project_count_gt1", "core_window_2005_2012", "vac_event_count"],
        )
        for variant in suite.variants:
            overrides = [
                variant.treatment_value_column is not None
                or variant.treatment_threshold is not None,
                variant.treatment_period_start is not None
                or variant.treatment_period_end is not None,
                variant.outcome_value_column is not None,
            ]
            self.assertEqual(sum(bool(value) for value in overrides), 1)

    def test_suite_keeps_canonical_and_exposes_failed_stress_instead_of_selecting_around_it(self):
        result = run_current_e2_robustness(self.canonical_result(), self.suite())
        summary = result["summary"].set_index("variant_id")
        self.assertEqual(len(summary), 5)  # canonical PRIMARY + STRESS + three variants
        self.assertIn("canonical_record_present", summary.index)
        self.assertIn("canonical_positive_reported_amount", summary.index)
        self.assertEqual(summary.loc["project_count_gt1", "hard_gate_state"], "BLOCKED")
        self.assertFalse(bool(summary.loc["project_count_gt1", "estimated"]))
        self.assertEqual(
            result["variants"]["core_window"]["spec"].treatment_period_start,
            "2005-2006",
        )
        self.assertEqual(
            result["variants"]["event_count"]["spec"].outcome_value_column,
            "event_count",
        )
        self.assertTrue(
            bool(summary.loc["event_count", "estimated"]),
            "alternate native outcome metric should use the unchanged estimator when gates permit",
        )

    def test_writer_emits_comparison_evidence_without_analysis_frames(self):
        result = run_current_e2_robustness(self.canonical_result(), self.suite())
        with tempfile.TemporaryDirectory() as tmp:
            out = write_current_e2_robustness_outputs(result, tmp)
            files = {
                path.relative_to(out).as_posix()
                for path in Path(out).rglob("*")
                if path.is_file()
            }
            payload = json.loads((Path(out) / "robustness_run.json").read_text())

        self.assertIn("robustness_summary.csv", files)
        self.assertIn("robustness_card.md", files)
        self.assertIn("canonical/reference_run.json", files)
        self.assertIn("variants/event_count/reference_run.json", files)
        self.assertFalse(any("analysis_frame" in name for name in files))
        self.assertFalse(payload["analysis_frame_persisted"])
        self.assertFalse(payload["variant_selection_by_result"])


if __name__ == "__main__":
    unittest.main()
