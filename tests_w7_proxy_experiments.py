"""Synthetic-only tests for the frozen W7 proxy; no locked data is read."""
import json
import unittest

import numpy as np
import pandas as pd

from fcv_harness.w7_proxy_experiments import (
    ARMS, W7ProxyError, build_proxy_panel, classify_projects, run_experiment,
)


POLICY = json.load(open("config/w7_exploratory_jobs_proxy_v0.json"))


def _small_ledger():
    cats = ["productive_enterprise", "physical_infrastructure", "skills_education",
            "health_social", "governance_finance", "humanitarian_environment_other"]
    return pd.DataFrame([{
        "source_family": "china" if i < 3 else "world_bank", "source_release_id": "cn-r" if i < 3 else "wb-r",
        "source_project_id": f"p{i}", "project_title": "jobs project" if i == 0 else "ordinary",
        "candidate_sector_channel": c,
    } for i, c in enumerate(cats)])


def _fixture():
    ledger_rows, bridge_rows, panel_rows, outcomes = [], [], [], []
    cn_tags = ["productive_enterprise", "health_social", "productive_enterprise|health_social"]
    wb_tags = ["physical_infrastructure", "governance_finance", "physical_infrastructure|governance_finance"]
    for ci, country in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"]):
        for ai in range(2):
            geo = f"{country}-{ai}"
            for ti in range(8):
                period = f"{2001 + 2 * ti}-{2002 + 2 * ti}"
                arm_index = ((ti + ci) % 8) if ai == 0 else ((3 * ti + 2 * ci + 1) % 8)
                cn_n = int(arm_index in (1, 2, 3, 7))
                wb_n = int(arm_index in (4, 5, 6, 7))
                panel_rows.append({"geo_uid": geo, "period_id": period, "country_iso3": country,
                                   "cn_project_count": cn_n, "wb_project_count": wb_n})
                for donor, present, tags, rel, prefix in [
                    ("china", cn_n, cn_tags, "cn-r", "c"), ("world_bank", wb_n, wb_tags, "wb-r", "w")]:
                    if not present:
                        continue
                    role_i = {1: 0, 2: 1, 3: 2, 7: 0, 4: 0, 5: 1, 6: 2}.get(arm_index, 0)
                    project_id = f"{prefix}{ci}{ai}{ti}"
                    ledger_rows.append({"source_family": donor, "source_release_id": rel,
                                        "source_project_id": project_id, "project_title": "ordinary",
                                        "candidate_sector_channel": tags[role_i]})
                    bridge_rows.append({"source_family": donor, "source_release_id": rel,
                                        "source_project_id": project_id, "geo_uid": geo, "period_id": period,
                                        "area_country_iso3": country, "recipient_iso3": country,
                                        "recipient_area_aligned": True})
                outcomes.append({"geo_uid": geo, "period_id": period,
                                 "vac_events_next": (ci + ai + ti) % 3,
                                 "vac_events_prior": (ci + ti) % 2})
    return (pd.DataFrame(ledger_rows), pd.DataFrame(bridge_rows), pd.DataFrame(panel_rows), pd.DataFrame(outcomes))


class W7ProxyTests(unittest.TestCase):
    def test_six_categories_multi_tag_title_and_no_review_promotion(self):
        x = classify_projects(_small_ledger(), POLICY)
        self.assertEqual(set(x.proxy_project_role), {"candidate", "other"})
        self.assertEqual(int(x.title_keyword_diagnostic.sum()), 1)
        self.assertNotIn("reviewed_jobs", set(x.proxy_project_role))
        mixed = pd.DataFrame([{**_small_ledger().iloc[0].to_dict(), "source_project_id": "m",
                               "candidate_sector_channel": "productive_enterprise|health_social"}])
        self.assertEqual(classify_projects(mixed, POLICY).proxy_project_role.item(), "ambiguous")

    def test_two_donor_status_counts_arms_partition_and_geometry_diagnostic(self):
        ledger, bridge, panel, _ = _fixture()
        bridge.loc[bridge.source_project_id.eq("c001"), "recipient_area_aligned"] = False
        bridge.loc[bridge.source_project_id.eq("c001"), "recipient_iso3"] = "BBB"
        _, out, diag = build_proxy_panel(ledger, bridge, panel, POLICY)
        self.assertEqual(len(out), 80)
        self.assertTrue((out[["cn_project_count", "wb_project_count"]].sum(axis=1) >= 0).all())
        self.assertEqual(sum(diag["cell_arm_counts"].values()), 80)
        self.assertGreater(diag["missing_geometry_crossrecipient_cells"]["cn"], 0)
        self.assertEqual(diag["project_counts"]["ambiguous"], 20)
        self.assertTrue((out[["cn_candidate_project_count", "cn_other_project_count", "cn_ambiguous_project_count"]].sum(axis=1) == out.cn_project_count).all())
        self.assertTrue((out[["wb_candidate_project_count", "wb_other_project_count", "wb_ambiguous_project_count"]].sum(axis=1) == out.wb_project_count).all())
        self.assertTrue(out["arm"].isin([*ARMS, "neither_recorded"]).all())

    def test_parity_and_source_release_fail_closed(self):
        ledger, bridge, panel, _ = _fixture()
        bad = bridge.copy(); bad.loc[0, "source_release_id"] = "wrong"
        with self.assertRaises(W7ProxyError): build_proxy_panel(ledger, bad, panel, POLICY)
        bad_panel = panel.iloc[:-1].copy()
        with self.assertRaises(W7ProxyError): build_proxy_panel(ledger, bridge, bad_panel, POLICY)

    def test_balanced_seven_arm_clustered_models_and_units(self):
        ledger, bridge, panel, outcomes = _fixture()
        result = run_experiment(ledger, bridge, panel, outcomes, POLICY)
        self.assertEqual(set(result["models"]), {"broad_any_vac_next", "narrow_any_vac_next",
                                                   "broad_asinh_vac_events_next", "broad_any_vac_prior_negative_control"})
        self.assertTrue(all(m["rank"] == 7 for m in result["models"].values()))
        self.assertEqual(result["models"]["broad_any_vac_next"]["contrasts"][0]["estimate_unit"], "percentage_points")
        self.assertEqual(result["models"]["broad_asinh_vac_events_next"]["contrasts"][0]["estimate_unit"], "asinh_events")
        self.assertEqual(result["models"]["broad_any_vac_next"]["country_clusters"], 5)
        for width in ("broad", "narrow"):
            for donor in ("china", "world_bank"):
                q = result["support"][width][donor]
                self.assertLessEqual(q["countries_both_same_period"], q["countries_both_across_any_period"])
                self.assertEqual(q["support_gate"], "THIN_SUPPORT_NO_STRONG_INFERENCE")
                self.assertTrue(q["thin_support"])

    def test_panel_key_parity_is_strict(self):
        ledger, bridge, panel, outcomes = _fixture()
        outcomes.loc[0, "geo_uid"] = "missing"
        with self.assertRaises(W7ProxyError): run_experiment(ledger, bridge, panel, outcomes, POLICY)


if __name__ == "__main__":
    unittest.main()
