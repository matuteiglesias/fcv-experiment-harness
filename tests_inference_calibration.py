import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from fcv_harness.fully_contracted_calibration import FullyContractedCalibrationSpec
from fcv_harness.inference_calibration import (
    default_e2_inference_methods,
    run_inference_calibration,
    wilson_interval,
    write_inference_calibration_outputs,
)
from fcv_harness.simulation_worlds import (
    generate_observability_world,
    prepare_observability_design,
)


class InferenceCalibrationTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        rows = []
        periods = ["2003-2004", "2005-2006", "2007-2008"]
        countries = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        for unit_index in range(60):
            country = countries[unit_index // 10]
            unit = f"{country}1.{unit_index % 10 + 1}_1"
            for period_index, period in enumerate(periods):
                treatment = int((unit_index + period_index) % 3 == 0)
                pre = 1.0 + 0.04 * unit_index + 0.25 * period_index
                country_shift = 0.3 * countries.index(country)
                outcome = (
                    2.0
                    + 0.08 * unit_index
                    + 0.35 * period_index
                    + country_shift
                    + 0.3 * np.sin(unit_index + 2 * period_index)
                )
                rows.append(
                    {
                        "GID": unit,
                        "TimePeriod": period,
                        "country_iso3": country,
                        "eligible": True,
                        "treatment": treatment,
                        "outcome_pre": pre,
                        "outcome_value": outcome,
                    }
                )
        return pd.DataFrame(rows)

    def methods(self):
        return default_e2_inference_methods(
            unit_col="GID",
            country_col="country_iso3",
            wild_bootstrap_repetitions=39,
            wild_bootstrap_root_seed=20260908,
        )

    def test_shared_world_generator_changes_only_injected_truth_across_effects(self):
        design = prepare_observability_design(
            self.frame(),
            unit_col="GID",
            period_col="TimePeriod",
            country_col="country_iso3",
        )
        null = generate_observability_world(
            design,
            repetition_id=7,
            root_seed=1234,
            delta_sd=0.0,
            synthetic_outcome_col="y_star",
        )
        positive = generate_observability_world(
            design,
            repetition_id=7,
            root_seed=1234,
            delta_sd=0.20,
            synthetic_outcome_col="y_star",
        )
        self.assertEqual(null.derived_seed, positive.derived_seed)
        expected_shift = 0.20 * design.outcome_sd * design.treatment
        np.testing.assert_allclose(
            positive.frame["y_star"].to_numpy() - null.frame["y_star"].to_numpy(),
            expected_shift,
        )

    def test_methods_share_exact_point_estimate_on_each_world(self):
        spec = FullyContractedCalibrationSpec(calibration_id="inference-test")
        result = run_inference_calibration(
            self.frame(),
            spec,
            effect_sizes_sd=[0.0, 0.20],
            repetitions=3,
            root_seed=20260908,
            methods=self.methods(),
        )
        repetitions = result["repetition_results"]
        self.assertEqual(len(repetitions), 18)
        spread = repetitions.groupby(["repetition_id", "effect_size_sd"])[
            "estimated_effect"
        ].agg(lambda values: float(values.max() - values.min()))
        self.assertLessEqual(float(spread.max()), 1e-12)
        self.assertEqual(
            set(repetitions["method_id"]),
            {"ADM2_CLUSTER", "COUNTRY_CLUSTER_T", "WILD_COUNTRY_BOOTSTRAP"},
        )

    def test_country_t_uses_cluster_count_minus_one_reference_df(self):
        spec = FullyContractedCalibrationSpec(calibration_id="country-t-test")
        result = run_inference_calibration(
            self.frame(),
            spec,
            effect_sizes_sd=[0.0],
            repetitions=1,
            root_seed=1,
            methods=self.methods(),
        )
        row = result["repetition_results"].loc[
            result["repetition_results"]["method_id"].eq("COUNTRY_CLUSTER_T")
        ].iloc[0]
        self.assertEqual(int(row["n_clusters"]), 6)
        self.assertEqual(float(row["reference_df"]), 5.0)
        self.assertEqual(row["reference_distribution"], "student_t_cluster_df")

    def test_same_seeds_reproduce_all_aggregate_outputs(self):
        spec = FullyContractedCalibrationSpec(calibration_id="determinism-test")
        kwargs = dict(
            effect_sizes_sd=[0.0, 0.05],
            repetitions=2,
            root_seed=41,
            methods=self.methods(),
        )
        first = run_inference_calibration(self.frame(), spec, **kwargs)
        second = run_inference_calibration(self.frame(), spec, **kwargs)
        for key in (
            "repetition_results",
            "method_summary",
            "coverage_by_effect",
            "null_size",
            "power_by_effect",
            "ci_width_by_effect",
            "paired_method_differences",
        ):
            assert_frame_equal(first[key], second[key], check_exact=True)
        self.assertEqual(first["inference_spec"], second["inference_spec"])

    def test_monte_carlo_rates_have_wilson_intervals_not_hard_pass_thresholds(self):
        low, high = wilson_interval(10, 20, confidence=0.95)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)
        spec = FullyContractedCalibrationSpec(calibration_id="mc-interval-test")
        result = run_inference_calibration(
            self.frame(),
            spec,
            effect_sizes_sd=[0.0, 0.20],
            repetitions=3,
            root_seed=2,
            methods=self.methods(),
        )
        null = result["null_size"]
        self.assertIn("false_positive_mc_low", null.columns)
        self.assertIn("false_positive_mc_high", null.columns)
        self.assertIn("alpha_inside_mc_interval", null.columns)
        self.assertNotIn("status", null.columns)

    def test_writer_emits_only_declared_aggregate_evidence(self):
        spec = FullyContractedCalibrationSpec(calibration_id="writer-test")
        result = run_inference_calibration(
            self.frame(),
            spec,
            effect_sizes_sd=[0.0, 0.20],
            repetitions=2,
            root_seed=7,
            methods=self.methods(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = write_inference_calibration_outputs(result, tmp)
            names = {path.name for path in Path(out).iterdir()}
        self.assertEqual(
            names,
            {
                "method_summary.csv",
                "coverage_by_effect.csv",
                "null_size.csv",
                "power_by_effect.csv",
                "ci_width_by_effect.csv",
                "paired_method_differences.csv",
                "inference_spec.json",
            },
        )
        self.assertFalse(any("frame" in name for name in names))
        self.assertFalse(any("repetition_results" in name for name in names))


if __name__ == "__main__":
    unittest.main()
