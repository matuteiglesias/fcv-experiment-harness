"""No empirical source data required: small deliberately adversarial fixtures."""
import unittest

import pandas as pd

from fcv_harness.jobs_classification_bridge import (
    BridgeError, panel_proxy_bridge, project_area_bridge, project_dimension,
)

P = {
    "schema": "fcv.w6.source_sector_proxy.v0",
    "sectors": {
        "china":{"high":["Energy"],"low":["Health"],"uncertain":["Education"]},
        "world_bank":{"high":["Transport"],"low":["Health"],"uncertain":["Other"]},
    }
}

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.roster=pd.DataFrame([
            ["china","C1","L1","AGO","adm2:AGO.1_1","2001-2002","geometry","committed"],
            ["china","C1","L1","AGO","adm2:AGO.2_1","2001-2002","geometry","committed"],
            ["world_bank","P1","L1","AGO","adm2:AGO.1_1","2001-2002","named","approved"],
            ["world_bank","P1","L2","AGO","adm2:AGO.1_1","2001-2002","named","approved"],
            ["world_bank","P2","L3","AGO","adm2:AGO.2_1","2001-2002","named","approved"],
        ],columns=["source_family","source_project_id","source_location_id","source_recipient_iso3","geo_uid","period_id","geographic_confidence","event_type"])
        self.cn=pd.DataFrame({"source_project_id":["C1"],"title":["Power"],"native_sector":["Energy"]})
        self.wb=pd.DataFrame({"project_id":["P1","P2"],"project_title":["Road","Mixed"],"ad_sector_names":["Transport","Transport|Health"]})
        self.panel=pd.DataFrame({
            "geo_uid":["adm2:AGO.1_1","adm2:AGO.2_1"],"period_id":["2001-2002"]*2,
            "cn_project_count":[1,1],"wb_project_count":[1,1], "country_iso3":["AGO","AGO"]
        })

    def test_one_annotation_per_project_and_unknown_explicit(self):
        x=project_dimension(self.roster,self.cn,self.wb,P,"CN-v","WB-v")
        self.assertEqual(len(x),3)
        self.assertEqual(x.explicit_jobs_objective.unique().tolist(),["unannotated"])
        self.assertEqual(dict(zip(x.source_project_id,x.sector_proxy)),{"C1":"high","P1":"high","P2":"uncertain"})

    def test_deduplicate_location_not_project_or_area(self):
        x=project_dimension(self.roster,self.cn,self.wb,P,"CN-v","WB-v")
        a=project_area_bridge(self.roster,x,self.panel)
        self.assertEqual(len(a),4)  # WB P1 has two source locations in one area
        self.assertEqual(int(a.loc[a.source_project_id.eq("P1"),"n_source_location_rows"].iloc[0]),2)
        p=panel_proxy_bridge(self.panel,self.roster,a)
        self.assertEqual(len(p),2)
        self.assertEqual(p.cn_sector_high_count.tolist(),[1,1])
        self.assertEqual(p.wb_sector_high_count.tolist(),[1,0])
        self.assertEqual(p.wb_sector_uncertain_count.tolist(),[0,1])
        self.assertEqual(p.wb_sector_group.tolist(),["high_only","mixed_or_uncertain"])
        self.assertEqual(p.cn_crossrecipient_project_count.tolist(),[0,0])
        self.assertEqual(p.wb_crossrecipient_project_count.tolist(),[0,0])

    def test_cross_recipient_geometry_is_flagged_not_silently_dropped(self):
        roster=self.roster.copy()
        extra=roster.iloc[0].copy()
        extra["geo_uid"]="adm2:KEN.1_1"
        extra["source_location_id"]="L9"
        roster=pd.concat([roster,pd.DataFrame([extra])],ignore_index=True)
        panel=pd.concat([self.panel,pd.DataFrame([{
            "geo_uid":"adm2:KEN.1_1","period_id":"2001-2002",
            "cn_project_count":1,"wb_project_count":0,"country_iso3":"KEN"
        }])],ignore_index=True)
        x=project_dimension(roster,self.cn,self.wb,P,"CN-v","WB-v")
        a=project_area_bridge(roster,x,panel)
        y=panel_proxy_bridge(panel,roster,a)
        self.assertEqual(y.cn_crossrecipient_project_count.tolist(),[0,0,1])
        self.assertEqual(y.cn_sector_high_count.tolist(),[1,1,1])
        self.assertEqual(a.loc[a.geo_uid.eq("adm2:KEN.1_1"),"recipient_area_aligned"].tolist(),[False])

    def test_missing_label_fails_closed(self):
        x=project_dimension(self.roster,self.cn,self.wb,P,"CN-v","WB-v")
        x=x[x.source_project_id.ne("P1")]
        with self.assertRaises(BridgeError):
            project_area_bridge(self.roster,x,self.panel)

    def test_wrong_panel_count_fails_closed(self):
        x=project_dimension(self.roster,self.cn,self.wb,P,"CN-v","WB-v")
        a=project_area_bridge(self.roster,x,self.panel)
        panel=self.panel.copy()
        panel.loc[0,"wb_project_count"]=2
        with self.assertRaises(BridgeError):
            panel_proxy_bridge(panel,self.roster,a)

if __name__=="__main__":
    unittest.main()
