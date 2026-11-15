"""E2/E3 bounded post-E1 experiments; original W5 source locks required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .w5_e2_e3 import load_accepted_frame, run_e2, run_e3, write_phase_outputs


def main() -> None:
    p = argparse.ArgumentParser(description="W5 E2/E3 source-locked empirical experiments")
    p.add_argument("--spec",type=Path,default=Path("config/w5_china_wb_vac_v1.json"))
    p.add_argument("--investment",type=Path,required=True)
    p.add_argument("--acled",type=Path,required=True)
    p.add_argument("--out-dir",type=Path,required=True)
    p.add_argument("--phase",choices=["e2","e3"],required=True)
    args=p.parse_args()
    spec,frame,ac,receipt=load_accepted_frame(args.spec,args.investment,args.acled,args.out_dir)
    if args.phase=="e2":
        result,tables=run_e2(frame)
    else:
        result,tables=run_e3(frame,ac,spec)
    result["provenance"]={
        "W5_E1_frame_sha256":receipt["analysis_frame_sha256"],
        "input_sha256":receipt["input_sha256"],
        "source_spec_sha256":receipt["spec_sha256"],
        "country_cluster":spec["inference"]["cluster"],
        "phase":args.phase,
    }
    write_phase_outputs(args.out_dir,args.phase,result,tables)
    summary={"phase":args.phase,"status":result["status"],"output_directory":str(args.out_dir)}
    if args.phase=="e2":
        summary["models"]={
            key:{
                "status":value.get("status","COMPLETE"),
                "nobs":value.get("nobs"),
                "main_contrast":value.get("contrasts",[None])[-1],
            } for key,value in result["models"].items()
        }
    else:
        summary["preperiod"]= [
            {"outcome":m["outcome"],"main_contrast":m["contrasts"][-1]}
            for m in result["preperiod_lpm_models"]
        ]
        summary["risk_set"]=result["first_recorded_riskset"]
        summary["risk_models"]=[
            {"outcome":m["outcome"],"main_contrast":m["contrasts"][-1]}
            for m in result["first_recorded_models"]
        ]
    print(json.dumps(summary,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
