import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fcv_harness.reference_identity import (
    CurrentE2ReferenceLock,
    REFERENCE_IDENTITY_SCHEMA,
    collect_runtime_environment,
    sha256_file,
    stable_frame_sha256,
    verify_current_e2_reference_lock,
    write_reference_identity,
)


class ReferenceIdentityTests(unittest.TestCase):
    def test_repo_lock_pins_current_inputs_and_config(self):
        lock = CurrentE2ReferenceLock.from_json("config/current_e2_reference_lock.json")
        self.assertEqual(lock.lock_id, "current_e2_reference_v1")
        self.assertEqual(lock.reference_id, "current_geogcdf_acled_e2_v1")
        self.assertEqual(lock.expected_analysis_country_count, 47)
        self.assertEqual(
            lock.config_sha256,
            sha256_file("config/current_geogcdf_acled_e2.json"),
        )
        self.assertEqual(
            lock.geography_sha256,
            "f136bb8c4294090abc7b03ff8a28e7b7717cc0a972e79ac761e38bc42f874663",
        )
        self.assertEqual(
            lock.treatment_sha256,
            "b6c2afcb3f37f2f52989fa946fb408788aaabc5bd864bf3ddd59fc46fdfb3394",
        )
        self.assertEqual(
            lock.outcome_sha256,
            "bffb63a924253255574aa3d84c090a1c7246cfad527f91fecfbed3b5f2d445f8",
        )

    def test_frame_hash_is_order_invariant_after_key_sort(self):
        frame = pd.DataFrame(
            {
                "GID": ["AAA1.2_1", "AAA1.1_1"],
                "TimePeriod": ["2005-2006", "2003-2004"],
                "value": [2.0, 1.0],
            }
        )
        shuffled = frame.iloc[::-1].reset_index(drop=True)
        first = stable_frame_sha256(frame, unit_col="GID", period_col="TimePeriod")
        second = stable_frame_sha256(shuffled, unit_col="GID", period_col="TimePeriod")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_lock_fails_closed_on_changed_input(self):
        lock = CurrentE2ReferenceLock.from_json("config/current_e2_reference_lock.json")
        identity = {
            "reference_id": lock.reference_id,
            "config_sha256": lock.config_sha256,
            "primary_cell_id": lock.primary_cell_id,
            "analysis_country_count": 47,
            "inputs": {
                "geography_sha256": lock.geography_sha256,
                "treatment_sha256": "0" * 64,
                "outcome_sha256": lock.outcome_sha256,
            },
        }
        with self.assertRaisesRegex(ValueError, "treatment_sha256"):
            verify_current_e2_reference_lock(identity, lock)

    def test_runtime_environment_records_numerical_packages(self):
        environment = collect_runtime_environment()
        self.assertIn("python_version", environment)
        self.assertIn("packages", environment)
        for package in ("numpy", "pandas", "scipy", "statsmodels"):
            self.assertIn(package, environment["packages"])

    def test_identity_writer_is_json_and_never_requires_a_frame_file(self):
        identity = {
            "schema": REFERENCE_IDENTITY_SCHEMA,
            "reference_id": "synthetic",
            "analysis_frame_persisted": False,
            "analysis_identity_sha256": "a" * 64,
            "execution_identity_sha256": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = write_reference_identity(identity, Path(tmp) / "reference_identity.json")
            payload = json.loads(path.read_text())
            files = {p.name for p in Path(tmp).iterdir()}
        self.assertEqual(files, {"reference_identity.json"})
        self.assertFalse(payload["analysis_frame_persisted"])


if __name__ == "__main__":
    unittest.main()
