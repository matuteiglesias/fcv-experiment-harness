import copy
import json
import tempfile
import unittest
from pathlib import Path

from pandas.testing import assert_frame_equal

from fcv_harness.current_e2_inference import (
    CurrentE2InferenceError,
    CurrentE2InferenceSuiteSpec,
    run_current_e2_inference_suite,
    write_current_e2_inference_outputs,
)
from fcv_harness.current_e2_reference import (
    run_current_e2_from_bundles,
    write_current_e2_reference_outputs,
)
from fcv_harness.inference_calibration import InferenceMethodSpec
from fcv_harness.reference_identity import stable_frame_sha256
from tests_current_e2_reference import CurrentE2ReferenceTests


class CurrentE2InferenceSuiteTests(unittest.TestCase):
    @staticmethod
    def synthetic_result():
        spec = CurrentE2ReferenceTests.spec()
        geography, geography_dataset, treatment, outcome = CurrentE2ReferenceTests.synthetic_inputs()
        result = run_current_e2_from_bundles(
            geography,
            geography_dataset,
            treatment,
            outcome,
            spec,
            run_observability=False,
        )
        result["country_scope"] = {
            "analysis_country_iso3": ["AAA"],
            "scope_policy": "synthetic_test",
        }
        primary = result["calibration"]["cells"][spec.primary_cell.cell_id]
        frame_sha = stable_frame_sha256(
            primary["frame"], unit_col=spec.unit_col, period_col=spec.period_col
        )
        result["reference_identity"] = {
            "reference_id": spec.reference_id,
            "analysis_identity_sha256": "a" * 64,
            "execution_identity_sha256": "b" * 64,
            "primary_cell_id": spec.primary_cell.cell_id,
            "primary_frame_sha256": frame_sha,
            "analysis_country_count": 1,
            "analysis_frame_persisted": False,
            "inputs": {
                "geography_sha256": geography_dataset.content_sha256,
                "treatment_sha256": treatment.dataset.content_sha256,
                "outcome_sha256": outcome.dataset.content_sha256,
            },
            "lock": {"lock_id": "synthetic-current-e2-lock", "verified": True},
        }
        return result

    @staticmethod
    def suite_for(result):
        spec = result["spec"]
        identity = result["reference_identity"]
        return CurrentE2InferenceSuiteSpec(
            suite_id="synthetic-current-e2-inference",
            purpose="calibration",
            reference_id=spec.reference_id,
            primary_cell_id=spec.primary_cell.cell_id,
            required_analysis_identity_sha256=identity["analysis_identity_sha256"],
            required_primary_frame_sha256=identity["primary_frame_sha256"],
            effect_sizes_sd=spec.observability.effect_sizes_sd,
            repetitions=spec.observability.repetitions,
            root_seed=spec.observability.root_seed,
            alpha=0.05,
            monte_carlo_confidence=0.95,
            methods=(
                InferenceMethodSpec(
                    method_id="ADM2_CLUSTER",
                    kind="cluster_normal",
                    cluster_col=spec.unit_col,
                ),
            ),
        )

    def test_repo_inference_config_is_bound_to_real_r0_identity(self):
        suite = CurrentE2InferenceSuiteSpec.from_json(
            "config/current_e2_inference_calibration.json"
        )
        self.assertEqual(suite.purpose, "calibration")
        self.assertEqual(suite.reference_id, "current_geogcdf_acled_e2_v1")
        self.assertEqual(suite.primary_cell_id, "record_present")
        self.assertEqual(
            suite.required_analysis_identity_sha256,
            "8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a",
        )
        self.assertEqual(
            suite.required_primary_frame_sha256,
            "e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f",
        )
        self.assertEqual(suite.effect_sizes_sd, (0.0, 0.02, 0.05, 0.10, 0.20))
        self.assertEqual(suite.repetitions, 200)
        self.assertEqual(suite.root_seed, 20260908)
        self.assertEqual(
            [method.method_id for method in suite.methods],
            ["ADM2_CLUSTER", "COUNTRY_CLUSTER_T", "WILD_COUNTRY_BOOTSTRAP"],
        )
        self.assertEqual(suite.methods[-1].bootstrap_repetitions, 399)

    def test_adapter_runs_on_existing_primary_frame_without_mutation(self):
        result = self.synthetic_result()
        suite = self.suite_for(result)
        primary = result["calibration"]["cells"][suite.primary_cell_id]
        before = primary["frame"].copy(deep=True)

        inference = run_current_e2_inference_suite(result, suite)

        assert_frame_equal(primary["frame"], before, check_exact=True)
        binding = inference["reference_binding"]
        self.assertEqual(binding["adapter_policy"], "reuse_existing_in_memory_primary_frame_no_reprojection")
        self.assertFalse(binding["reprojection_performed"])
        self.assertFalse(binding["reingestion_performed"])
        self.assertFalse(binding["analysis_frame_persisted"])
        self.assertEqual(binding["primary_frame_sha256"], suite.required_primary_frame_sha256)
        self.assertEqual(binding["analysis_identity_sha256"], suite.required_analysis_identity_sha256)
        self.assertEqual(set(inference["method_summary"]["method_id"]), {"ADM2_CLUSTER"})

    def test_adapter_refuses_unverified_reference_lock(self):
        result = self.synthetic_result()
        suite = self.suite_for(result)
        result["reference_identity"]["lock"]["verified"] = False
        with self.assertRaisesRegex(CurrentE2InferenceError, "verified reference lock"):
            run_current_e2_inference_suite(result, suite)

    def test_adapter_refuses_frame_fingerprint_drift(self):
        result = self.synthetic_result()
        suite = self.suite_for(result)
        drifted = CurrentE2InferenceSuiteSpec(
            **{
                **suite.__dict__,
                "required_primary_frame_sha256": "f" * 64,
            }
        )
        with self.assertRaisesRegex(CurrentE2InferenceError, "PRIMARY frame fingerprint"):
            run_current_e2_inference_suite(result, drifted)

    def test_adapter_refuses_when_primary_hard_gates_block(self):
        result = self.synthetic_result()
        suite = self.suite_for(result)
        blocked = copy.deepcopy(result)
        blocked["calibration"]["cells"][suite.primary_cell_id]["estimation_permitted"] = False
        with self.assertRaisesRegex(CurrentE2InferenceError, "blocked by PRIMARY hard gates"):
            run_current_e2_inference_suite(blocked, suite)

    def test_writer_emits_aggregate_r2_packet_and_updates_reference_run(self):
        result = self.synthetic_result()
        suite = self.suite_for(result)
        inference = run_current_e2_inference_suite(result, suite)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_current_e2_reference_outputs(result, root)
            target = write_current_e2_inference_outputs(inference, root)
            files = {
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            }
            run_payload = json.loads((root / "reference_run.json").read_text())

        self.assertEqual(target.name, "inference_calibration")
        self.assertIn("inference_calibration/method_summary.csv", files)
        self.assertIn("inference_calibration/coverage_by_effect.csv", files)
        self.assertIn("inference_calibration/null_size.csv", files)
        self.assertIn("inference_calibration/power_by_effect.csv", files)
        self.assertIn("inference_calibration/ci_width_by_effect.csv", files)
        self.assertIn("inference_calibration/paired_method_differences.csv", files)
        self.assertIn("inference_calibration/inference_spec.json", files)
        self.assertIn("inference_calibration/reference_binding.json", files)
        self.assertNotIn("inference_calibration/repetition_results.csv", files)
        self.assertFalse(any("analysis_frame" in name for name in files))
        self.assertEqual(run_payload["inference_calibration"]["state"], "RUN")
        self.assertFalse(run_payload["inference_calibration"]["reprojection_performed"])
        self.assertFalse(run_payload["inference_calibration"]["reingestion_performed"])


if __name__ == "__main__":
    unittest.main()
