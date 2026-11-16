import hashlib
import json
import unittest

import pandas as pd

from fcv_harness.w7_employment_classification import (
    W7ClassificationError, apply_editorial_annotations, build_project_ledger,
    derive_exposure_panel,
)


POLICY = json.load(open("config/w7_native_sector_channels_v0.json"))


class W7Tests(unittest.TestCase):
    def setUp(self):
        self.dim = pd.DataFrame([
            ["china", "r1", "C1", "Road", "TRANSPORT AND STORAGE"],
            ["world_bank", "r2", "P1", "Mixed", "Agriculture|Health"],
            ["world_bank", "r2", "P2", "Unknown review", "General environmental protection"],
        ], columns=["source_family", "source_release_id", "source_project_id", "project_title", "native_sector_raw"])
        self.bridge = pd.DataFrame([
            ["china", "r1", "C1", "g1", "p1", "AGO", "AGO", True],
            ["world_bank", "r2", "P1", "g1", "p1", "AGO", "AGO", True],
            ["world_bank", "r2", "P2", "g2", "p1", "KEN", "KEN", True],
        ], columns=["source_family", "source_release_id", "source_project_id", "geo_uid", "period_id", "area_country_iso3", "recipient_iso3", "recipient_area_aligned"])
        self.bridge["n_source_location_rows"] = 1
        self.panel = pd.DataFrame({"geo_uid": ["g1", "g2"], "period_id": ["p1", "p1"], "country_iso3": ["AGO", "KEN"], "cn_project_count": [1, 0], "wb_project_count": [1, 1], "untouched": ["a", "b"]})

    def annotation(self, **overrides):
        base = {"source_family": "china", "source_release_id": "r1", "source_project_id": "C1", "annotation_version": "v1", "editorial_status": "reviewed", "class": "reviewed_jobs", "direct": "yes", "indirect": "no", "local_implementation": "yes", "confidence": "high", "evidence_source": "reviewed://source", "evidence_content_hash": hashlib.sha256(b"evidence").hexdigest(), "evidence_reference": "page:1", "reviewer": "reviewer-1"}
        base.update(overrides)
        return pd.DataFrame([base])

    def test_ledger_is_unique_unresolved_and_does_not_auto_confirm_jobs(self):
        x = build_project_ledger(self.dim, POLICY)
        self.assertEqual(len(x), 3)
        self.assertFalse((x["class"] == "reviewed_jobs").any())
        self.assertEqual(x.loc[x.source_project_id.eq("P1"), "candidate_sector_channel"].item(), "productive_enterprise|health_social")
        self.assertEqual(x["class"].tolist(), ["unresolved"] * 3)

    def test_missing_or_orphan_or_duplicate_annotations_fail(self):
        x = build_project_ledger(self.dim, POLICY)
        bad = self.annotation(source_project_id="NOPE")
        with self.assertRaises(W7ClassificationError): apply_editorial_annotations(x, bad)
        dup = pd.concat([self.annotation(), self.annotation()], ignore_index=True)
        with self.assertRaises(W7ClassificationError): apply_editorial_annotations(x, dup)
        with self.assertRaises(W7ClassificationError): apply_editorial_annotations(x, self.annotation(evidence_content_hash="bad"))

    def test_reviewed_jobs_requires_explicit_evidenced_logic(self):
        x = build_project_ledger(self.dim, POLICY)
        y = apply_editorial_annotations(x, self.annotation())
        self.assertEqual(y.loc[y.source_project_id.eq("C1"), "class"].item(), "reviewed_jobs")
        with self.assertRaises(W7ClassificationError): apply_editorial_annotations(x, self.annotation(direct="no", indirect="no"))
        with self.assertRaises(W7ClassificationError): apply_editorial_annotations(x, self.annotation(evidence_source=""))

    def test_partition_parity_and_geo_receptor_preservation(self):
        x = build_project_ledger(self.dim, POLICY)
        exposure, out = derive_exposure_panel(x, self.bridge, self.panel)
        self.assertEqual(len(exposure), 3)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["country_iso3"].tolist(), ["AGO", "KEN"])
        self.assertEqual(out["wb_unresolved_project_count"].tolist(), [1, 1])
        self.assertEqual(out["cn_unresolved_project_count"].tolist(), [1, 0])
        self.assertEqual(out[["wb_reviewed_jobs_project_count", "wb_reviewed_nonjobs_project_count", "wb_unresolved_project_count"]].sum(axis=1).tolist(), [1, 1])

    def test_duplicate_project_key_fails(self):
        with self.assertRaises(W7ClassificationError): build_project_ledger(pd.concat([self.dim, self.dim.iloc[[0]]]), POLICY)


    def test_reviewed_nonjobs_can_be_locally_implemented_but_both_channels_must_be_no(self):
        ledger = build_project_ledger(self.dim, POLICY)
        negative = self.annotation(source_project_id="C1", **{"class": "reviewed_nonjobs",
            "direct": "no", "indirect": "no", "local_implementation": "yes"})
        classified = apply_editorial_annotations(ledger, negative)
        self.assertEqual(classified.loc[classified.source_project_id.eq("C1"), "class"].item(),
                         "reviewed_nonjobs")
        _, projected = derive_exposure_panel(classified, self.bridge, self.panel)
        self.assertEqual(projected.cn_reviewed_nonjobs_project_count.tolist(), [1, 0])
        with self.assertRaisesRegex(W7ClassificationError, "BOTH"):
            apply_editorial_annotations(ledger, negative.assign(indirect=pd.NA))

    def test_positive_and_negative_require_local_evidence(self):
        ledger = build_project_ledger(self.dim, POLICY)
        for label in ("reviewed_jobs", "reviewed_nonjobs"):
            a = self.annotation(**{"class": label,
                "direct": "yes" if label == "reviewed_jobs" else "no",
                "indirect": "no"})
            for locality in ("no", pd.NA):
                with self.subTest(label=label, locality=str(locality)):
                    with self.assertRaisesRegex(W7ClassificationError, "local implementation"):
                        apply_editorial_annotations(ledger, a.assign(local_implementation=locality))

    def test_geography_flags_cannot_disagree_with_canonical_area(self):
        ledger = build_project_ledger(self.dim, POLICY)
        altered = self.bridge.copy()
        altered.loc[0, "area_country_iso3"] = "ZWE"
        with self.assertRaisesRegex(W7ClassificationError, "geography"):
            derive_exposure_panel(ledger, altered, self.panel)
        altered = self.bridge.copy()
        altered.loc[0, "recipient_area_aligned"] = False
        with self.assertRaisesRegex(W7ClassificationError, "geography"):
            derive_exposure_panel(ledger, altered, self.panel)

    def test_unreviewed_forged_label_and_broken_project_membership_fail(self):
        ledger = build_project_ledger(self.dim, POLICY)
        forged = ledger.copy()
        forged.loc[0, "class"] = "reviewed_jobs"
        with self.assertRaisesRegex(W7ClassificationError, "unreviewed"):
            derive_exposure_panel(forged, self.bridge, self.panel)
        extra = ledger.copy()
        extra.loc[len(extra)] = extra.iloc[0]
        extra.loc[len(extra)-1,"source_project_id"] = "UNMAPPED"
        with self.assertRaisesRegex(W7ClassificationError, "project identities"):
            derive_exposure_panel(extra, self.bridge, self.panel)

    def test_review_evidence_has_nonempty_reviewer_confidence_and_version(self):
        ledger = build_project_ledger(self.dim, POLICY)
        for kw in ({"reviewer": ""}, {"confidence": "not_assessed"},
                   {"annotation_version": ""}, {"evidence_reference": ""}):
            with self.subTest(kw=kw):
                with self.assertRaises(W7ClassificationError):
                    apply_editorial_annotations(ledger, self.annotation(**kw))


if __name__ == "__main__":
    unittest.main()
