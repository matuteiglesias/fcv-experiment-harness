import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from fcv_harness.fully_contracted_calibration import FullyContractedCalibrationSpec
from fcv_harness.observability import (
    derive_repetition_seed,
    inject_known_effect,
    run_e2_observability,
    wild_cluster_signs,
    write_observability_outputs,
)


class ObservabilityTests(unittest.TestCase):
    @staticmethod
    def frame() -> pd.DataFrame:
        rows = []
        periods = ["2003-2004", "2005-2006", "2007-2008"]
        for unit_index in range(40):
            unit = f"AAA1.{unit_index + 1}_1"
            for period_index, period in enumerate(periods):
                treatment = int((unit_index + period_index) % 2 == 0)
                pre = 1.0 + 0.08 * unit_index + 0.3 * period_index
                outcome = (
                    2.0
                    + 0.12 * unit_index
                    + 0.4 * period_index
                    + 0.2 * np.sin(unit_index + period_index)
                )
                rows.append(
                    {
                        "GID": unit,
                        "TimePeriod": period,
                        "country_iso3": "AAA",
                        "eligible": True,
                        "treatment": treatment,
                        "outcome_pre": pre,
                        "outcome_value": outcome,
                    }
                )
        return pd.DataFrame(rows)

    def test_delta_zero_has_no_deterministic_shift(self):
        y = np.array([1.0, 2.0, 3.0])
        treatment = np.array([0.0, 1.0, 1.0])
        shifted = inject_known_effect(y, treatment, delta_sd=0.0, outcome_sd=2.0)
        np.testing.assert_array_equal(shifted, y)

    def test_known_positive_delta_is_added_in_sd_units(self):
        y = np.array([1.0, 2.0, 3.0])
        treatment = np.array([0.0, 1.0, 1.0])
        shifted = inject_known_effect(y, treatment, delta_sd=0.5, outcome_sd=2.0)
        np.testing.assert_allclose(shifted, np.array([1.0, 3.0, 4.0]))

    def test_large_delta_cannot_reduce_deterministic_injected_truth(self):
        y = np.zeros(4)
        treatment = np.array([0.0, 1.0, 1.0, 0.0])
        small = inject_known_effect(y, treatment, delta_sd=2.0, outcome_sd=3.0)
        large = inject_known_effect(y, treatment, delta_sd=20.0, outcome_sd=3.0)
        self.assertGreaterEqual(float(large.sum()), float(small.sum()))
        self.assertTrue(np.all(large[treatment == 1] >= small[treatment == 1]))

    def test_seed_semantics_are_reproducible_and_change_the_draw(self):
        units = pd.Series([f"u{i // 2}" for i in range(40)])
        seed_a = derive_repetition_seed(1234, 7)
        seed_b = derive_repetition_seed(1234, 7)
        seed_c = derive_repetition_seed(4321, 7)
        self.assertEqual(seed_a, seed_b)
        self.assertNotEqual(seed_a, seed_c)
        np.testing.assert_array_equal(
            wild_cluster_signs(units, seed_a),
            wild_cluster_signs(units, seed_b),
        )
        self.assertFalse(
            np.array_equal(
                wild_cluster_signs(units, seed_a),
                wild_cluster_signs(units, seed_c),
            )
        )

    def test_same_seed_reproduces_full_observability_outputs(self):
        frame = self.frame()
        spec = FullyContractedCalibrationSpec(calibration_id="e2-observability-test")
        kwargs = {
            "effect_sizes_sd": [0.0, 0.05, 0.20],
            "repetitions": 4,
            "root_seed": 20260823,
        }
        first = run_e2_observability(frame, spec, **kwargs)
        second = run_e2_observability(frame, spec, **kwargs)
        for key in first:
            assert_frame_equal(first[key], second[key], check_exact=True)

    def test_aggregation_counts_every_repetition_and_separates_null(self):
        frame = self.frame()
        spec = FullyContractedCalibrationSpec(calibration_id="e2-count-test")
        result = run_e2_observability(
            frame,
            spec,
            effect_sizes_sd=[0.0, 0.10],
            repetitions=5,
            root_seed=11,
        )
        repetitions = result["repetition_results"]
        self.assertEqual(len(repetitions), 10)
        self.assertEqual(set(repetitions["condition"]), {"null", "positive_injection"})
        self.assertEqual(
            result["effect_size_summary"].set_index("effect_size_sd")["repetitions"].to_dict(),
            {0.0: 5, 0.1: 5},
        )
        self.assertEqual(int(result["null_calibration_summary"].iloc[0]["repetitions"]), 5)
        self.assertTrue(
            repetitions.loc[repetitions["condition"].eq("null"), "relative_recovery_error"].isna().all()
        )
        self.assertTrue(
            repetitions.loc[
                repetitions["condition"].eq("positive_injection"), "truth_effect"
            ].gt(0).all()
        )

    def test_observability_does_not_mutate_projected_treatment_or_outcome_semantics(self):
        frame = self.frame()
        before = frame.copy(deep=True)
        spec = FullyContractedCalibrationSpec(calibration_id="e2-semantics-test")
        run_e2_observability(
            frame,
            spec,
            effect_sizes_sd=[0.0, 0.20],
            repetitions=2,
            root_seed=9,
        )
        assert_frame_equal(frame, before, check_exact=True)

    def test_output_writer_emits_only_durable_summary_tables(self):
        frame = self.frame()
        spec = FullyContractedCalibrationSpec(calibration_id="e2-output-test")
        result = run_e2_observability(
            frame,
            spec,
            effect_sizes_sd=[0.0, 0.20],
            repetitions=2,
            root_seed=19,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = write_observability_outputs(result, tmp)
            names = {path.name for path in Path(out).iterdir()}
        self.assertEqual(
            names,
            {
                "repetition_results.csv",
                "effect_size_summary.csv",
                "detection_curve.csv",
                "null_calibration_summary.csv",
            },
        )


if __name__ == "__main__":
    unittest.main()
