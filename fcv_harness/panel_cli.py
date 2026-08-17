from pathlib import Path
import argparse
import json
import pandas as pd

from .panel import (
    PanelExperimentSpec,
    build_panel_analysis_frame,
    panel_baseline_estimate,
    profile_panel,
    run_panel_gates,
    render_panel_report,
    merge_panel_outcomes,
)

def main():
    ap = argparse.ArgumentParser(
        description="Run the FCV recovered GID×TimePeriod experiment lane."
    )
    ap.add_argument("--panel", required=True, help="Treatment/covariate panel CSV, e.g. *_DHSGC.csv")
    ap.add_argument(
        "--outcomes",
        default=None,
        help="Optional separate GID×TimePeriod outcome CSV, matching the recovered 2023 architecture.",
    )
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    panel = pd.read_csv(args.panel)
    spec = PanelExperimentSpec.from_json(args.config)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Profile the raw treatment/covariate panel before any merge.
    profile_panel(panel, spec).to_csv(out / "panel_column_profile.csv", index=False)

    merge_audit = None
    df = panel

    if args.outcomes:
        outcomes = pd.read_csv(args.outcomes)
        # Generic profile for the raw outcome file.
        rows = []
        for c in outcomes.columns:
            s = outcomes[c]
            rows.append({
                "column": c,
                "dtype": str(s.dtype),
                "n": len(s),
                "n_nonmissing": int(s.notna().sum()),
                "missing_share": float(s.isna().mean()),
                "n_unique": int(s.nunique(dropna=True)),
            })
        pd.DataFrame(rows).to_csv(out / "outcome_column_profile.csv", index=False)

        df, merge_audit = merge_panel_outcomes(
            panel,
            outcomes,
            outcome_col=spec.outcome,
            unit_col=spec.unit_col,
            period_col=spec.period_col,
        )
        (out / "outcome_merge_audit.json").write_text(
            json.dumps(merge_audit, indent=2),
            encoding="utf-8",
        )

    # Profile the experiment-ready merged table.
    profile_panel(df, spec).to_csv(out / "merged_column_profile.csv", index=False)

    gates, frame = run_panel_gates(df, spec)

    # Prepend explicit outcome-merge gate when using a separate outcome file.
    if merge_audit is not None:
        share = merge_audit["matched_share"]
        if share >= 0.98:
            status = "GREEN"
        elif share >= 0.90:
            status = "YELLOW"
        else:
            status = "RED"

        merge_gate = pd.DataFrame([{
            "gate": "P0_OUTCOME_MERGE_COVERAGE",
            "status": status,
            "metric": "panel rows with matching outcome record",
            "value": round(share, 4),
            "threshold": "green >= 0.98",
            "note": (
                f"Matched {merge_audit['matched_rows']} of {merge_audit['panel_rows']} panel rows. "
                "This gate distinguishes absent outcome records from outcome values that are present but missing."
            ),
        }])
        gates = pd.concat([merge_gate, gates], ignore_index=True)

    gates.to_csv(out / "gates.csv", index=False)
    report = render_panel_report(gates, spec)
    (out / "gate_report.md").write_text(report, encoding="utf-8")

    if frame is not None:
        frame.to_csv(out / "analysis_frame.csv", index=False)
        est = panel_baseline_estimate(frame, spec)
        pd.DataFrame([est]).to_csv(out / "baseline_estimate.csv", index=False)

        by_period = (
            frame.dropna(subset=["outcome_post"])
                 .groupby(spec.period_col)
                 .agg(
                     n=(spec.unit_col, "size"),
                     n_units=(spec.unit_col, "nunique"),
                     treated=("treatment", "sum"),
                     outcome_mean=("outcome_post", "mean"),
                     outcome_sd=("outcome_post", "std"),
                 )
                 .reset_index()
        )
        by_period["control"] = by_period["n"] - by_period["treated"]
        by_period.to_csv(out / "support_by_period.csv", index=False)

    print(report)
    print(f"\\nOutputs written to {out}")

if __name__ == "__main__":
    main()
