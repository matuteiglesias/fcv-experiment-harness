"""Synthetic and falsification tests for W5 source/lag/FE contracts; no real data."""
import unittest
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from fcv_harness.w5_china_wb_vac import (
    build_frame, fit_primary_lpm, residualize_balanced, support_report, shift_period, run_w5,
)


def _fixture():
    inv = []
    ac = []
    periods = ["2001-2002", "2003-2004", "2005-2006", "2007-2008"]
    countries = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    for ci, country in enumerate(countries):
        for area in range(4):
            uid = f"gadm:4.1-africa-adm2:adm2:{country}.{area}"
            for ti, period in enumerate(periods):
                cat = (area + ti + ci) % 4
                cn = 1 if cat in (1, 3) else 0
                wb = 1 if cat in (2, 3) else 0
                inv.append({
                    "geo_uid": uid, "country_iso3": country, "period_id": period,
                    "cn_project_count": cn, "wb_project_count": wb,
                    "cn_record_present": bool(cn), "wb_record_present": bool(wb),
                    "cn_measurement_status": "observed" if cn else "structural_zero",
                    "wb_measurement_status": "observed" if wb else "zero_among_resolved_eligible_source_geocodes",
                })
            outcome_periods = ["1999-2000", *periods, "2009-2010"]
            for ti, period in enumerate(outcome_periods):
                events = int((area + ci + ti * 2) % 5 < 2)
                ac.append({
                    "geo_uid": uid, "country_iso3": country, "period_id": period,
                    "native_event_type": "Violence against civilians",
                    "event_count": events, "fatalities": float(2 * events),
                    "record_present": bool(events),
                    "measurement_status": "aggregated_from_observed" if events else "structural_zero",
                    "fatalities_missing_event_count": 0,
                })
    spec = {
        "expected_rows": len(inv), "expected_area_count": 20,
        "expected_country_count": 5, "expected_period_count": 4,
        "finance_period_start": periods[0], "finance_period_end": periods[-1],
        "acled_event_type": "Violence against civilians",
        "min_countries_with_same_period_both_exclusive_arms": 3,
        "min_country_period_cells_with_both_exclusive_arms": 10,
    }
    return pd.DataFrame(inv), pd.DataFrame(ac), spec


class W5Tests(unittest.TestCase):
    def test_period_shift_and_reject_alignment_error(self):
        self.assertEqual(shift_period("2001-2002", 1), "2003-2004")
        self.assertEqual(shift_period("2001-2002", -1), "1999-2000")
        with self.assertRaises(ValueError):
            shift_period("2002-2003", 1)

    def test_frozen_four_arm_join_and_outcome_clocks(self):
        inv, ac, spec = _fixture()
        frame = build_frame(inv, ac, spec)
        self.assertEqual(len(frame), len(inv))
        self.assertTrue((frame[["china_only", "wb_only", "both", "neither_recorded"]].sum(axis=1) == 1).all())
        self.assertFalse(frame[["vac_events_next", "vac_events_prior"]].isna().any().any())
        self.assertEqual(frame.geo_uid.nunique(), 20)
        self.assertEqual(frame.period_id.nunique(), 4)
        report, _ = support_report(frame, spec)
        self.assertEqual(report["e0_gate"], "PASS")
        self.assertEqual(report["arm_design_rank"], 3)

    def test_fails_closed_on_missing_acled_outcome(self):
        inv, ac, spec = _fixture()
        ac = ac.drop(ac.index[0])  # missing one prior period
        with self.assertRaisesRegex(ValueError, "incomplete certified ACLED"):
            build_frame(inv, ac, spec)

    def test_fails_closed_on_inconsistent_project_flags(self):
        inv, ac, spec = _fixture()
        inv.loc[0, "cn_record_present"] = not bool(inv.loc[0, "cn_record_present"])
        with self.assertRaisesRegex(ValueError, "record_presence/count mismatch"):
            build_frame(inv, ac, spec)

    def test_source_sha_lock_rejects_changed_inputs_before_outputs(self):
        inv, ac, spec = _fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inv_path = root / "investment.parquet"
            ac_path = root / "acled.parquet"
            config = root / "config.json"
            inv.to_parquet(inv_path, index=False)
            ac.to_parquet(ac_path, index=False)
            config.write_text(json.dumps({
                "schema": "fcv.w5.china_wb_vac.v1",
                "primary_outcome": "any_vac_next",
                "main_fe": ["adm2", "country_x_financing_period"],
                "inference": {"cluster": "country_iso3"},
                "investment_sha256": "0" * 64, "acled_sha256": "a" * 64,
            }))
            with self.assertRaisesRegex(ValueError, "source hash lock mismatch"):
                run_w5(config, inv_path, ac_path, root / "missing_ic.json",
                       root / "missing_ac.json", root / "not_created", phase="e1")
            self.assertFalse((root / "not_created").exists())

    def test_exact_fwl_equals_full_dummy_ols(self):
        inv, ac, spec = _fixture()
        frame = build_frame(inv, ac, spec)
        m = smf.ols("any_vac_next ~ china_only + wb_only + both + C(geo_uid) + C(country_period)", data=frame).fit()
        w = residualize_balanced(frame, ["china_only", "wb_only", "both", "any_vac_next"])
        beta = np.linalg.lstsq(w[:, :3], w[:, -1], rcond=None)[0]
        np.testing.assert_allclose(beta, m.params[list(("china_only", "wb_only", "both"))], atol=1e-10, rtol=0)
        ours = fit_primary_lpm(frame)
        np.testing.assert_allclose(list(ours["betas"].values()), beta, atol=1e-10, rtol=0)
        self.assertEqual(ours["country_clusters"], 5)
        self.assertEqual(ours["results"][-1]["contrast"], "china_only_minus_wb_only_PRIMARY")


if __name__ == "__main__":
    unittest.main()
