from __future__ import annotations

from pathlib import Path
import argparse
import re
import numpy as np
import pandas as pd

from .panel import derive_legacy_treatment


FILE_RE = re.compile(
    r"africa(?P<level>[al]\d)T(?P<T>\d)(?P<y0>\d{4})_DHSGC\.csv$",
    re.IGNORECASE,
)


def parse_legacy_filename(path: str | Path):
    name = Path(path).name
    m = FILE_RE.search(name)
    if not m:
        return {"level": None, "T": None, "y0": None}
    d = m.groupdict()
    return {"level": d["level"].lower(), "T": int(d["T"]), "y0": int(d["y0"])}


def _period_support(df, treatment, period_col):
    tmp = pd.DataFrame({"period": df[period_col], "treatment": treatment})
    t = tmp.groupby("period")["treatment"].agg(["sum", "count"])
    t["control"] = t["count"] - t["sum"]
    usable = (t["sum"] > 0) & (t["control"] > 0)
    return {
        "n_periods": int(len(t)),
        "n_usable_periods": int(usable.sum()),
        "min_treated_in_usable_period": int(t.loc[usable, "sum"].min()) if usable.any() else 0,
        "min_control_in_usable_period": int(t.loc[usable, "control"].min()) if usable.any() else 0,
    }


def scan_file(path, outcome=None, unit_col="GID", period_col="TimePeriod",
              wb_col="wbad_amount_usd", cn_col="cn_amount_usd"):
    p = Path(path)
    meta = parse_legacy_filename(p)
    row = {
        "file": str(p),
        "filename": p.name,
        **meta,
        "read_ok": False,
    }

    try:
        df = pd.read_csv(p)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
        return row

    row["read_ok"] = True
    row["n_rows"] = int(len(df))
    row["n_columns"] = int(df.shape[1])
    row["has_unit"] = unit_col in df.columns
    row["has_period"] = period_col in df.columns
    row["has_wb_amount"] = wb_col in df.columns
    row["has_cn_amount"] = cn_col in df.columns

    if unit_col in df.columns:
        row["n_units"] = int(df[unit_col].nunique())
    if period_col in df.columns:
        row["n_periods_raw"] = int(df[period_col].nunique())

    if unit_col in df.columns and period_col in df.columns:
        row["duplicate_unit_period"] = int(df.duplicated([unit_col, period_col]).sum())

    if wb_col in df.columns and cn_col in df.columns:
        for tt in ("cnwb_pooled", "wb_only", "cn_only"):
            tr = derive_legacy_treatment(df, tt, wb_col, cn_col)
            row[f"{tt}_treated"] = int(tr.sum())
            row[f"{tt}_control"] = int((1 - tr).sum())
            row[f"{tt}_treated_share"] = float(tr.mean())
            if period_col in df.columns:
                ps = _period_support(df, tr, period_col)
                for k, v in ps.items():
                    row[f"{tt}_{k}"] = v

    # Outcome is explicit if supplied. We do not silently promote a numeric column to outcome.
    if outcome:
        row["outcome"] = outcome
        row["has_outcome"] = outcome in df.columns
        if outcome in df.columns:
            y = pd.to_numeric(df[outcome], errors="coerce")
            row["outcome_missing_share"] = float(y.isna().mean())
            row["outcome_zero_share"] = float((y == 0).mean())
            row["outcome_mean"] = float(y.mean())
            row["outcome_sd"] = float(y.std(ddof=1))

    # Still surface plausible columns for human inspection.
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    excluded = {wb_col, cn_col}
    patterns = ("viol", "fatal", "death", "event", "conflict", "battle", "riot", "protest", "civilian")
    candidate = [
        c for c in numeric
        if c not in excluded and any(pat in c.lower() for pat in patterns)
    ]
    row["candidate_outcome_columns"] = "|".join(candidate[:30])
    return row


def scan_grid(pattern, outcome=None, **kwargs):
    files = sorted(Path().glob(pattern)) if not Path(pattern).is_absolute() else sorted(Path(pattern).parent.glob(Path(pattern).name))
    return pd.DataFrame([scan_file(p, outcome=outcome, **kwargs) for p in files])


def viability_score(row, treatment_type):
    """
    A ranking convenience, not a scientific gate.
    Rewards usable period support and treated/control material.
    """
    if not row.get("read_ok", False):
        return -1.0
    if row.get("duplicate_unit_period", 1) != 0:
        return -1.0

    nt = float(row.get(f"{treatment_type}_treated", 0) or 0)
    nc = float(row.get(f"{treatment_type}_control", 0) or 0)
    periods = float(row.get(f"{treatment_type}_n_usable_periods", 0) or 0)
    if nt <= 0 or nc <= 0:
        return 0.0
    harmonic = 2 * nt * nc / (nt + nc)
    return float(np.log1p(harmonic) * np.sqrt(max(periods, 0)))


def main():
    ap = argparse.ArgumentParser(description="Scan the recovered FCV reg_data grid for empirical support.")
    ap.add_argument("--glob", required=True, help="e.g. data/reg_data/*_DHSGC.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--outcome", default=None, help="Optional explicit outcome column")
    ap.add_argument("--treatment-type", default="cnwb_pooled",
                    choices=["cnwb_pooled", "wb_only", "cn_only"])
    args = ap.parse_args()

    df = scan_grid(args.glob, outcome=args.outcome)
    if len(df):
        df["viability_score"] = df.apply(
            lambda r: viability_score(r.to_dict(), args.treatment_type), axis=1
        )
        df = df.sort_values("viability_score", ascending=False)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    cols = [c for c in [
        "filename", "level", "T", "y0", "n_rows", "n_units",
        f"{args.treatment_type}_treated",
        f"{args.treatment_type}_control",
        f"{args.treatment_type}_n_usable_periods",
        f"{args.treatment_type}_min_treated_in_usable_period",
        "outcome_missing_share", "outcome_zero_share",
        "candidate_outcome_columns", "viability_score",
    ] if c in df.columns]

    print(df[cols].head(20).to_string(index=False) if len(df) else "No files matched.")
    print(f"\\nWrote {out}")

if __name__ == "__main__":
    main()
