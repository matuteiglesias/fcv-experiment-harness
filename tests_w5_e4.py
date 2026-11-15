"""E4 synthetic acceptance: exact event parity, real event removals, history/precision."""
import unittest
import numpy as np
import pandas as pd
from tests_w5_china_wb_vac import _fixture
from tests_w5_e2_e3 import _poisson_fixture
from fcv_harness.w5_china_wb_vac import build_frame
from fcv_harness.w5_e4 import (
    event_to_accepted_area_period, event_removal_scenarios, run_country_influence,
    source_precision_stresses, fit_history_adjusted, acled_outcome_precision_stress,
)


def _event_fixture():
    inv,ac,spec=_fixture()
    frame=build_frame(inv,ac,spec)
    all_events=[];geo=[];period=[]
    for _,row in frame.iterrows():
        for k in range(int(row.vac_events_next)):
            eid=f"event:{len(all_events)}"
            all_events.append({
                "event_row_id":eid,"source_event_id":eid,
                "native_event_type":"Violence against civilians",
                "fatalities":row.vac_fatalities_next/row.vac_events_next,
                "geo_precision":1,"event_date":pd.Timestamp(row.next_period[:4]+"-01-01"),
            })
            geo.append({"event_row_id":eid,"geo_uid":row.geo_uid,"assignment_status":"matched_unique"})
            period.append({"event_row_id":eid,"period_id":row.next_period,
                           "period_assignment_status":"assigned"})
    return frame,pd.DataFrame(all_events),pd.DataFrame(geo),pd.DataFrame(period)


class E4Tests(unittest.TestCase):
    def test_event_parity_and_event_removal_not_cell_removal(self):
        frame,silver,geo,period=_event_fixture()
        eligible,report=event_to_accepted_area_period(frame,silver,geo,period)
        self.assertEqual(report["status"],"PASS_EVENT_TO_CERTIFIED_GOLD_EXACT_CELL_PARITY")
        self.assertEqual(len(eligible),int(frame.vac_events_next.sum()))
        changed,top,rec=event_removal_scenarios(frame,eligible)
        self.assertEqual(set(changed.scenario),set(rec["experiment_rows"]))
        self.assertEqual(rec["experiment_rows"]["drop_largest_1_event"]["removed_event_count"],1)
        self.assertEqual(len(top),min(25,len(eligible)))

    def test_common_acled_outcome_precision_is_distinct_from_event_deletion(self):
        frame,silver,geo,period=_event_fixture()
        # A subset is coarser than 1; exact reconstruction should retain
        # all rows but reduce outcomes under strict precision.
        silver.loc[silver.index[:4],"geo_precision"]=2
        eligible,parity=event_to_accepted_area_period(frame,silver,geo,period)
        result,report=acled_outcome_precision_stress(frame,eligible)
        strict=result.loc[result.scenario.eq("ACLED_vac_geo_precision_le_1_ONLY")]
        self.assertEqual(len(strict),2)
        self.assertEqual(report["scenarios"]["ACLED_vac_geo_precision_le_1_ONLY"]["excluded_ACLED_events"],4)
        self.assertTrue(strict.nobs.eq(len(frame)).all())

    def test_event_parity_holds_on_changed_source_event(self):
        frame,silver,geo,period=_event_fixture()
        silver.loc[0,"fatalities"]=1000.
        with self.assertRaisesRegex(ValueError,"fatality parity FAIL"):
            event_to_accepted_area_period(frame,silver,geo,period)

    def test_all_country_leave_one_out_influence(self):
        frame=_poisson_fixture()
        # At least ten clusters must remain after the synthetic top-five
        # deletion; the production experiment retains more than forty.
        clones=[]
        for j in range(3):
            clone=frame.loc[frame.country_iso3.eq(f"C{j}")].copy()
            clone["country_iso3"]=f"Z{j}"
            clone["geo_uid"]=clone.geo_uid.str.replace(f"C{j}.",f"Z{j}.",regex=False)
            clone["country_period"]=clone.country_period.str.replace(f"C{j}|",f"Z{j}|",regex=False)
            clones.append(clone)
        frame=pd.concat([frame,*clones],ignore_index=True)
        frame["vac_fatalities_next"]=frame.vac_events_next*2
        top=frame.groupby("country_iso3").vac_fatalities_next.sum().nlargest(5).index.tolist()
        data,info=run_country_influence(frame,top)
        self.assertEqual(info["one_by_one_count"],12)
        self.assertEqual(info["scheduled_scenarios"],17)
        self.assertTrue(data.countries.ge(7).all())
        self.assertEqual(data.groupby("outcome").size().tolist(),[17,17])

    def test_history_requires_prior_flags_exclusive_of_current(self):
        frame,silver,geo,period=_event_fixture()
        model=fit_history_adjusted(frame,"any_vac_next")
        self.assertEqual(model["nobs"],len(frame))
        self.assertIn("prior_cn",model["coefficients"])

    def test_strict_geography_reconstructs_count_parity(self):
        frame,silver,geo,period=_event_fixture()
        roster=[]
        for _,row in frame.iterrows():
            for source,col in (("china","cn_project_count"),("world_bank","wb_project_count")):
                for k in range(int(row[col])):
                    roster.append({
                        "source_family":source,"source_project_id":f"{source}:{row.geo_uid}:{row.period_id}:{k}",
                        "source_location_id":f"{source}:{row.geo_uid}:{row.period_id}:{k}",
                        "geo_uid":row.geo_uid,"period_id":row.period_id,
                        "geography_relation_status":"matched_single" if source=="china" else "exact_named_place_point",
                        "geographic_confidence":"source_geometry_original" if source=="china" else "exact_named_place",
                    })
        frame["wb_high_confidence_project_count"]=frame.wb_project_count
        out,qa=source_precision_stresses(frame,pd.DataFrame(roster))
        self.assertEqual(qa["roster_parity"],"PASS")
        self.assertEqual(len(out),6)
        self.assertTrue(all(x["status"]=="RUN_DESCRIPTIVE" for x in qa["scenarios"].values()))


if __name__=="__main__":
    unittest.main()
