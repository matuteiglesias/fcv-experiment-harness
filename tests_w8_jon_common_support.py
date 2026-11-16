"""Synthetic W8 J/O/N ADM2 matching, weighting and release invariants."""
import unittest

import numpy as np
import pandas as pd

from fcv_harness.w8_jon_common_support import (
    W8DesignError, merge_exposure_outcome, construct_master, matched_standardization
)
from scripts.w8_jon_prior_history_audit import summarize

PERIODS = [f"{t}-{t+1}" for t in range(2001, 2015, 2)]


def fixture():
    rows, results = [], []
    for country in ("AAA", "BBB"):
        for i, role in enumerate(("J", "O", "N", "PREV")):
            geo = f"{country}-{role}"
            for t, period in enumerate(PERIODS):
                if role == "J":
                    cn, wb, arm, y = 1, 0, "cn_positive_only", 1 if country == "AAA" else 0
                elif role == "O":
                    cn, wb, arm, y = 1, 0, "cn_other_only", 0 if country == "AAA" else 1
                elif role == "N":
                    cn, wb, arm, y = 0, 0, "neither_recorded", 0
                else:
                    cn, wb = (1, 0) if t == 0 else (0, 0)
                    arm = "cn_positive_only" if t == 0 else "neither_recorded"
                    y = 0
                rows.append(dict(geo_uid=geo, period_id=period, country_iso3=country,
                                 arm=arm, cn_project_count=cn, wb_project_count=wb))
                results.append(dict(geo_uid=geo, period_id=period, country_iso3=country,
                                    any_vac_next=y, vac_events_prior=int(t > 0)))
    return pd.DataFrame(rows), pd.DataFrame(results)


class TestW8CommonSupport(unittest.TestCase):
    def test_strict_history_for_N_and_conservation(self):
        exposure, outcomes = fixture()
        x = construct_master(merge_exposure_outcome(exposure, outcomes), "china")
        self.assertEqual(len(x), 56)
        prior = x[x.geo_uid.eq("AAA-PREV")].sort_values("period_id")
        self.assertEqual(prior.jon_group.tolist(), ["J"] + ["X"] * 6)
        self.assertTrue(prior.had_source_before.tolist()[1:][0])
        self.assertTrue(x.loc[x.jon_group.eq("N"), "cn_project_count"].eq(0).all())
        self.assertTrue(x.loc[x.jon_group.eq("N"), "wb_project_count"].eq(0).all())

    def test_shared_weights_identity_and_cluster_uncertainty(self):
        exposure, outcomes = fixture()
        master = construct_master(merge_exposure_outcome(exposure, outcomes), "china")
        summary, matched = matched_standardization(master, "china", "broad",
                                                    "not_yet_recorded", 199, 42)
        self.assertEqual(summary["matched_country_period_strata"], 14)
        self.assertEqual(summary["matched_countries"], 2)
        self.assertEqual(summary["groups"]["J"]["matched_group_cells"], 16)
        self.assertEqual(summary["groups"]["O"]["matched_group_cells"], 14)
        self.assertEqual(summary["groups"]["N"]["matched_group_cells"], 14)
        self.assertAlmostEqual(summary["identity_error_pp"], 0, places=12)
        self.assertAlmostEqual(
            summary["contrasts_pp"]["J_minus_O"],
            summary["contrasts_pp"]["J_minus_N"] - summary["contrasts_pp"]["O_minus_N"],
            places=12
        )
        for g, subset in matched.groupby("jon_group"):
            self.assertAlmostEqual(subset.analysis_weight.sum(), 1.0, places=12)
            self.assertGreater(summary["groups"][g]["weighted_effective_N"], 0)
        self.assertEqual(summary["support_gate"], "THIN_SUPPORT_DESCRIPTIVE_ONLY")
        self.assertEqual(summary["uncertainty"]["J_minus_O"]["cluster_bootstrap_percentile95_pp"].__len__(), 2)

    def test_period_only_N_is_weaker_than_not_yet_recorded(self):
        e, o = fixture()
        x = merge_exposure_outcome(e, o)
        a = construct_master(x, "china", "not_yet_recorded")
        b = construct_master(x, "china", "period_only")
        self.assertLess(int(a.jon_group.eq("N").sum()), int(b.jon_group.eq("N").sum()))
        self.assertEqual(int(a.loc[a.jon_group.eq("N"), "had_source_before"].sum()), 0)

    def test_bad_duplicate_country_and_binary_values_fail(self):
        e, o = fixture()
        with self.assertRaisesRegex(W8DesignError, "duplicate"):
            merge_exposure_outcome(pd.concat([e, e.iloc[[0]]]), o)
        o2 = o.copy()
        o2.loc[0, "country_iso3"] = "DIFF"
        with self.assertRaisesRegex(W8DesignError, "country mismatch"):
            merge_exposure_outcome(e, o2)
        o3 = o.copy()
        o3.loc[0, "any_vac_next"] = 2
        with self.assertRaisesRegex(W8DesignError, "binary"):
            merge_exposure_outcome(e, o3)

    def test_no_triple_strata_fails_closed(self):
        e, o = fixture()
        f = construct_master(merge_exposure_outcome(e, o), "china")
        f.loc[f.jon_group.eq("O"), "jon_group"] = "X"
        with self.assertRaisesRegex(W8DesignError, "no J/O/N"):
            matched_standardization(f, "china", "broad", "not_yet_recorded", boot_reps=0)

    def test_different_stratum_sizes_target_J_distribution(self):
        e, o = fixture()
        master = construct_master(merge_exposure_outcome(e, o), "china")
        summary, sample = matched_standardization(master, "china", "broad",
                                                  "not_yet_recorded", boot_reps=0)
        expected = sample.loc[sample.jon_group.eq("J"), "any_vac_next"].mean()
        self.assertAlmostEqual(summary["means_pct"]["J"] / 100, expected, places=12)
        self.assertAlmostEqual(summary["groups"]["J"]["weighted_effective_N"],
                               summary["groups"]["J"]["matched_group_cells"], places=12)
        self.assertAlmostEqual(summary["identity_error_pp"], 0, places=12)


    def test_prior_history_audit_reuses_same_weights(self):
        exposure, outcomes = fixture()
        master = construct_master(merge_exposure_outcome(exposure, outcomes), "china")
        result, matched = matched_standardization(master, "china", "broad",
                                                  "not_yet_recorded", boot_reps=0)
        audit = summarize(matched)
        for g in ("J", "O", "N"):
            self.assertAlmostEqual(audit["groups"][g]["next_vac_incidence_pct"],
                                   result["means_pct"][g], places=12)
        for key in ("J_minus_N", "O_minus_N", "J_minus_O"):
            self.assertAlmostEqual(audit["contrasts"][key]["next_gap_pp"],
                                   result["contrasts_pp"][key], places=12)
        diff = audit["contrasts"]
        self.assertAlmostEqual(diff["J_minus_O"]["change_in_gap_pp"],
                               diff["J_minus_N"]["change_in_gap_pp"] -
                               diff["O_minus_N"]["change_in_gap_pp"], places=12)
        broken = matched.copy()
        broken.loc[broken.jon_group.eq("O"), "analysis_weight"] *= 2
        with self.assertRaisesRegex(ValueError, "weights"):
            summarize(broken)

    def test_arm_project_count_consistency_and_scenario_guard(self):
        exposure, outcomes = fixture()
        frame = merge_exposure_outcome(exposure, outcomes)
        broken = frame.copy()
        broken.loc[broken.arm.eq("cn_positive_only").idxmax(), "wb_project_count"] = 1
        with self.assertRaisesRegex(W8DesignError, "disagree"):
            construct_master(broken, "china")
        master = construct_master(frame, "china", scenario="broad")
        with self.assertRaisesRegex(W8DesignError, "metadata mismatch"):
            matched_standardization(master, "world_bank", "broad", "not_yet_recorded", boot_reps=0)
        with self.assertRaisesRegex(W8DesignError, "metadata mismatch"):
            matched_standardization(master, "china", "narrow", "not_yet_recorded", boot_reps=0)
        with self.assertRaisesRegex(W8DesignError, "metadata mismatch"):
            matched_standardization(master, "china", "broad", "period_only", boot_reps=0)

if __name__ == "__main__":
    unittest.main()
