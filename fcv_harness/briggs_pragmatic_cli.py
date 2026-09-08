from __future__ import annotations

import argparse
from pathlib import Path
import json

import pandas as pd

from .briggs_pragmatic import load_briggs_pragmatic_spec, run_briggs_pragmatic


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the explicitly approximate Briggs (2017) GADM/13-country analogue.")
    p.add_argument("--config", default="config/briggs_2017_pragmatic_analogue.json")
    p.add_argument("--analysis-frame", required=True, help="Local parquet or CSV with independently reconstructed regional quantities")
    p.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    spec = load_briggs_pragmatic_spec(args.config)
    path = Path(args.analysis_frame)
    frame = pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    result = run_briggs_pragmatic(frame, spec)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "briggs_pragmatic_result.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    comparison = result["comparison_to_briggs"]
    print(
        "BRIGGS_PRAGMATIC=RUN "
        f"rows={result['analysis_rows']} countries={result['analysis_countries']} "
        f"model={comparison['model_used']} "
        f"richest={comparison['log_richest']['estimate']:.6g} "
        f"published_richest={comparison['log_richest']['published']:.6g} "
        f"out={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
