"""W5 E4 outcome-side ACLED geolocation precision sensitivity."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .w5_china_wb_vac import sha256_file
from .w5_e2_e3 import load_accepted_frame
from .w5_e4 import event_to_accepted_area_period, acled_outcome_precision_stress


def main():
    p=argparse.ArgumentParser()
    for name in ("investment","acled","event-silver","event-geo","event-period","out-dir"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--spec",type=Path,default=Path("config/w5_china_wb_vac_v1.json"))
    args=p.parse_args()
    spec,frame,_,base=load_accepted_frame(args.spec,args.investment,args.acled,args.out_dir)
    silver=pd.read_parquet(args.event_silver)
    geo=pd.read_parquet(args.event_geo)
    period=pd.read_parquet(args.event_period)
    eligible,parity=event_to_accepted_area_period(frame,silver,geo,period)
    effects,report=acled_outcome_precision_stress(frame,eligible)
    report["source_parity"]=parity
    report["provenance"]={
        "analysis_frame_sha256":base["analysis_frame_sha256"],
        "source_spec_sha256":base["spec_sha256"],
        "event_silver_sha256":sha256_file(args.event_silver),
        "event_geo_sha256":sha256_file(args.event_geo),
        "event_period_sha256":sha256_file(args.event_period),
    }
    (args.out_dir/"e4_acled_outcome_precision_results.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n")
    effects.to_csv(args.out_dir/"e4_acled_outcome_precision_effects.csv",index=False)
    print(json.dumps({"status":report["status"],"scenarios":report["scenarios"],
                      "effects":effects.to_dict("records")},indent=2))


if __name__=="__main__":
    main()
