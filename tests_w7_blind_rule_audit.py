"""Synthetic invariants for bounded outcome-blind W7 rule QA."""
import json
import unittest
import pandas as pd
from scripts.w7_blind_rule_audit import audit_sample, STAGES

NATIVE = json.load(open("config/w7_native_sector_channels_v0.json"))
PROXY = json.load(open("config/w7_exploratory_jobs_proxy_v0.json"))

def fixture():
    rows = []
    for donor, release, sector, channel in [
        ("china", "c-r", "EDUCATION", "skills_education"),
        ("china", "c-r", "ENERGY", "physical_infrastructure"),
        ("world_bank", "w-r", "Health", "health_social"),
        ("world_bank", "w-r", "Post-secondary education|Mineral resources and mining", "productive_enterprise|skills_education")
    ]:
        for i in range(36):
            rows.append(dict(source_family=donor, source_release_id=release,
                source_project_id=f"{sector[:3]}-{i:03d}", project_title=f"Example project {sector} {i}",
                native_sector_raw=sector, candidate_sector_channel=channel,
                editorial_status="unreviewed"))
    return pd.DataFrame(rows)

class W7NestedAuditTests(unittest.TestCase):
    def test_nested_stages_parity_and_stability(self):
        data = fixture()
        original = data.copy(deep=True)
        x, meta = audit_sample(data, PROXY, NATIVE)
        self.assertEqual(len(x), 100)
        self.assertEqual(tuple(meta["stages"]), STAGES)
        self.assertEqual(x.audit_sequence.tolist(), list(range(1,101)))
        self.assertTrue(x.editorial_status.eq("unreviewed").all())
        self.assertFalse(x.anomaly.any())
        self.assertEqual(tuple(x.head(10).source_project_id),
                         tuple(audit_sample(data, PROXY, NATIVE)[0].head(10).source_project_id))
        pd.testing.assert_frame_equal(data, original)
        for n in STAGES:
            self.assertEqual(len(x.head(n)), n)

    def test_strict_full_universe_crosswalk_drift_fails(self):
        data = fixture()
        data.loc[0, "candidate_sector_channel"] = "governance_finance"
        with self.assertRaisesRegex(ValueError, "mapping parity"):
            audit_sample(data, PROXY, NATIVE)

    def test_duplicate_or_reviewed_source_fails(self):
        data = fixture()
        with self.assertRaisesRegex(ValueError, "unique"):
            audit_sample(pd.concat([data, data.iloc[[0]]]), PROXY, NATIVE)
        data.loc[0,"editorial_status"] = "reviewed"
        with self.assertRaisesRegex(ValueError, "review state"):
            audit_sample(data, PROXY, NATIVE)

    def test_stages_do_not_require_extra_projects(self):
        x,_ = audit_sample(fixture(), PROXY, NATIVE)
        self.assertEqual(int((x.audit_sequence > 100).sum()), 0)
        self.assertEqual(x.stratum.nunique(), 4)

if __name__ == "__main__":
    unittest.main()
