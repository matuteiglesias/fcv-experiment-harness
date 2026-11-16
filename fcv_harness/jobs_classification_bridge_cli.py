"""Source-locked, derived-only W6 project label/ADM2 projection builder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .jobs_classification_bridge import (
    project_dimension, project_area_bridge, panel_proxy_bridge,
)
from .w5_china_wb_vac import sha256_file


def build(args: argparse.Namespace) -> dict:
    source_paths = {
        "w5_roster": Path(args.w5_roster),
        "w5_source_panel": Path(args.w5_panel),
        "china_project_silver": Path(args.china_projects),
        "wb_project_silver": Path(args.wb_projects),
        "sector_policy": Path(args.sector_policy),
    }
    for label, path in source_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label}: {path}")
    out = Path(args.out_dir).resolve()
    if any(out == p.resolve() or out in p.resolve().parents for p in source_paths.values()):
        raise ValueError("output location overlaps input")
    # Enforce immutable versioned inputs, no write to any Gold/Silver product.
    policy = json.loads(source_paths["sector_policy"].read_text(encoding="utf8"))
    roster = pd.read_parquet(source_paths["w5_roster"])
    panel = pd.read_parquet(source_paths["w5_source_panel"])
    cn = pd.read_parquet(source_paths["china_project_silver"])
    wb = pd.read_parquet(source_paths["wb_project_silver"])
    project_dim = project_dimension(
        roster,cn,wb,policy,
        source_paths["china_project_silver"].parent.name,
        source_paths["wb_project_silver"].parent.name
    )
    project_cell = project_area_bridge(roster,project_dim,panel)
    enriched_panel = panel_proxy_bridge(panel,roster,project_cell)
    if len(project_dim) != 2535 or len(project_cell) != 19588 or len(enriched_panel) != 44940:
        raise ValueError("expected locked W5 snapshot sizes have drifted")
    out.mkdir(parents=True,exist_ok=True)
    files = {
        "project_dim": out / "project_sector_proxy_dimension.parquet",
        "project_cell": out / "project_adm2_period_bridge.parquet",
        "panel": out / "adm2_period_sector_proxy_panel.parquet",
    }
    project_dim.to_parquet(files["project_dim"], index=False)
    project_cell.to_parquet(files["project_cell"], index=False)
    enriched_panel.to_parquet(files["panel"], index=False)
    # Output is sensitive source-derived data: never commit these parquet files.
    counts=project_dim.groupby(["source_family","sector_proxy"]).size()
    manifest = {
        "schema":"fcv.w6.sector_proxy_bridge_receipt.v0",
        "scientific_state":"SCHEMA_ONLY; sector proxy screening; editorial jobs annotation unavailable; no regressions",
        "source_files_sha256":{k:sha256_file(v) for k,v in source_paths.items()},
        "outputs_sha256":{k:sha256_file(v) for k,v in files.items()},
        "n_projects":len(project_dim),
        "n_project_area_periods":len(project_cell),
        "n_raw_project_location_rows":len(roster),
        "n_w5_area_periods":len(enriched_panel),
        "n_exposure_location_duplicates_removed":len(roster)-len(project_cell),
        "crossrecipient_project_area_periods": int((~project_cell.recipient_area_aligned).sum()),
        "crossrecipient_projects_by_source":{
            source:int(group.source_project_id.nunique())
            for source,group in project_cell.loc[~project_cell.recipient_area_aligned].groupby("source_family")
        },
        "project_proxy_counts":[
           {"source_family":str(a),"sector_proxy":str(b),"projects":int(count)}
           for (a,b),count in counts.items()
        ],
        "sector_group_area_period_counts":{
            donor:enriched_panel[f"{prefix}_sector_group"].value_counts().to_dict()
            for donor,prefix in [("china","cn"),("world_bank","wb")]
        },
        "zero_recorded_both_source_cells":int(
            enriched_panel.cn_project_count.eq(0).mul(enriched_panel.wb_project_count.eq(0)).sum()
        ),
        "note":"'None recorded' is absence in these two source families for this financing period, not a certified never-treated area.",
    }
    (out/"w6_bridge_receipt.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf8")
    return manifest


def main()->None:
    parser=argparse.ArgumentParser()
    for flag in ("w5-roster","w5-panel","china-projects","wb-projects","sector-policy","out-dir"):
        parser.add_argument("--"+flag,required=True)
    print(json.dumps(build(parser.parse_args()),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
