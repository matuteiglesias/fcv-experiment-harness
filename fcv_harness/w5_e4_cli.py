"""Reproducible E4 influence CLI; all inputs source hashed, outputs private."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .w5_china_wb_vac import sha256_file
from .w5_e2_e3 import load_accepted_frame
from .w5_e4 import run_e4


def main():
    p=argparse.ArgumentParser(description="W5 E4 source-locked country/event influence")
    for name in ("investment","acled","roster","event-silver","event-geo","event-period","out-dir"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--spec",type=Path,default=Path("config/w5_china_wb_vac_v1.json"))
    p.add_argument("--e4-spec",type=Path,default=Path("config/w5_e4_influence_v1.json"))
    args=p.parse_args()
    spec,frame,ac,base=load_accepted_frame(args.spec,args.investment,args.acled,args.out_dir)
    e4=json.loads(args.e4_spec.read_text())
    if e4.get("source_spec") != str(args.spec):
        raise ValueError("E4 source specification path does not match E1")
    roster=pd.read_parquet(args.roster)
    investment=pd.read_parquet(args.investment)
    silver=pd.read_parquet(args.event_silver)
    geography=pd.read_parquet(args.event_geo)
    period=pd.read_parquet(args.event_period)
    result,tables=run_e4(frame,investment,roster,silver,geography,period,spec,e4)
    result["provenance"]={
        "source_spec_sha256":sha256_file(args.spec),
        "e4_spec_sha256":sha256_file(args.e4_spec),
        "E1_analysis_frame_sha256":base["analysis_frame_sha256"],
        "input_sha256":base["input_sha256"],
        "extra_inputs_sha256":{
            "source_project_roster":sha256_file(args.roster),
            "silver_events":sha256_file(args.event_silver),
            "silver_geography":sha256_file(args.event_geo),
            "silver_period":sha256_file(args.event_period),
        },
        "no_gold_modification":True,
    }
    for name,table in tables.items():
        table.to_csv(args.out_dir/f"e4_{name}.csv",index=False)
    (args.out_dir/"e4_results.json").write_text(
        json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n",
        encoding="utf-8",
    )
    bycountry=result["country"]["outcome_diagnostics"]
    print(json.dumps({
        "status":result["status"],
        "source_event_parity":result["event_level_parity"]["status"],
        "country_top5":result["country"]["top_five_countries"],
        "country_primary":bycountry["any_vac_next"],
        "country_severity":bycountry["vac_fatalities_next"],
        "event_summary":{k:{
            "removed_event_count":v["removed_event_count"],
            "share_of_all_W5_fatalities_removed":v["share_of_all_W5_fatalities_removed"],
        } for k,v in result["event_removal"]["experiment_rows"].items()},
        "source_precision":{k:v["status"] for k,v in result["precision"]["scenarios"].items()},
        "out_dir":str(args.out_dir),
    },indent=2,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
