from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional
import json

import numpy as np
import pandas as pd

from .canonical import _period_start
from .lattice_diagnostics import attach_country_iso3


SUPPORTED_PROJECT_SOURCES = {"wbad", "wbkg", "cn"}
SUPPORTED_TREATMENT_DEFINITIONS = {"record_present", "amount_positive"}
SUPPORTED_OUTCOME_TIMINGS = {"next_period"}
SUPPORTED_ABSENT_RECORD_POLICIES = {
    "unresolved",
    "observed_records_only",
    "zero_within_verified_coverage",
}


@dataclass(frozen=True)
class TreatmentMeasurementSpec:
    source: str
    definition: str
    annotation_version: str = "legacy_2023"

    @classmethod
    def from_dict(cls, payload: dict) -> "TreatmentMeasurementSpec":
        spec = cls(
            source=str(payload["source"]),
            definition=str(payload["definition"]),
            annotation_version=str(payload.get("annotation_version", "legacy_2023")),
        )
        if spec.source not in SUPPORTED_PROJECT_SOURCES:
            raise ValueError(
                f"Unsupported canonical project source {spec.source!r}; "
                f"supported: {sorted(SUPPORTED_PROJECT_SOURCES)}"
            )
        if spec.definition not in SUPPORTED_TREATMENT_DEFINITIONS:
            raise ValueError(
                f"Unsupported treatment definition {spec.definition!r}; "
                f"supported: {sorted(SUPPORTED_TREATMENT_DEFINITIONS)}"
            )
        return spec


@dataclass(frozen=True)
class EligibilitySpec:
    treatment_period_start: str
    treatment_period_end: str

    @classmethod
    def from_dict(cls, payload: dict) -> "EligibilitySpec":
        spec = cls(
            treatment_period_start=str(payload["treatment_period_start"]),
            treatment_period_end=str(payload["treatment_period_end"]),
        )
        if _period_start(spec.treatment_period_start) > _period_start(spec.treatment_period_end):
            raise ValueError("Treatment period start must not be after treatment period end.")
        return spec


@dataclass(frozen=True)
class OutcomeMeasurementSpec:
    source: str
    column: str
    timing: str = "next_period"
    absent_record_policy: str = "unresolved"
    verified_period_start: Optional[str] = None
    verified_period_end: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict) -> "OutcomeMeasurementSpec":
        spec = cls(
            source=str(payload["source"]),
            column=str(payload["column"]),
            timing=str(payload.get("timing", "next_period")),
            absent_record_policy=str(payload.get("absent_record_policy", "unresolved")),
            verified_period_start=(
                str(payload["verified_period_start"])
                if payload.get("verified_period_start") is not None else None
            ),
            verified_period_end=(
                str(payload["verified_period_end"])
                if payload.get("verified_period_end") is not None else None
            ),
        )
        if spec.timing not in SUPPORTED_OUTCOME_TIMINGS:
            raise ValueError(
                f"Unsupported outcome timing {spec.timing!r}; "
                f"supported: {sorted(SUPPORTED_OUTCOME_TIMINGS)}"
            )
        if spec.absent_record_policy not in SUPPORTED_ABSENT_RECORD_POLICIES:
            raise ValueError(
                f"Unsupported absent-record policy {spec.absent_record_policy!r}; "
                f"supported: {sorted(SUPPORTED_ABSENT_RECORD_POLICIES)}"
            )
        if spec.absent_record_policy == "zero_within_verified_coverage":
            if not spec.verified_period_start or not spec.verified_period_end:
                raise ValueError(
                    "zero_within_verified_coverage requires verified_period_start and "
                    "verified_period_end; coverage is never inferred silently."
                )
        return spec


@dataclass(frozen=True)
class CanonicalPanelExperimentSpec:
    experiment_id: str
    panel_id: str
    treatment: TreatmentMeasurementSpec
    eligibility: EligibilitySpec
    outcome: OutcomeMeasurementSpec
    covariates: List[str] = field(default_factory=list)
    unit_col: str = "GID"
    period_col: str = "TimePeriod"
    country_col: str = "country_iso3"

    @classmethod
    def from_json(cls, path) -> "CanonicalPanelExperimentSpec":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            experiment_id=str(raw["experiment_id"]),
            panel_id=str(raw["panel_id"]),
            treatment=TreatmentMeasurementSpec.from_dict(raw["treatment"]),
            eligibility=EligibilitySpec.from_dict(raw["eligibility"]),
            outcome=OutcomeMeasurementSpec.from_dict(raw["outcome"]),
            covariates=list(raw.get("covariates", [])),
            unit_col=str(raw.get("unit_col", "GID")),
            period_col=str(raw.get("period_col", "TimePeriod")),
            country_col=str(raw.get("country_col", "country_iso3")),
        )


def _period_window(values: pd.Series, start: str, end: str) -> pd.Series:
    start_year = _period_start(start)
    end_year = _period_start(end)
    starts = values.map(_period_start)
    return starts.between(start_year, end_year, inclusive="both")


def _validate_panel_identity(panel: pd.DataFrame, spec: CanonicalPanelExperimentSpec):
    required = {spec.unit_col, spec.period_col, "annotation_version"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise KeyError(f"Canonical panel missing experiment identity fields: {missing}")
    if "panel_id" in panel.columns:
        panel_ids = panel["panel_id"].dropna().astype(str).unique().tolist()
        if panel_ids and panel_ids != [spec.panel_id]:
            raise ValueError(
                f"Experiment expects panel_id={spec.panel_id!r}, found {panel_ids}."
            )


def resolve_treatment_measurement(
    panel: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
) -> pd.DataFrame:
    """Resolve treatment without hiding source/measurement semantics.

    Returned treatment is nullable and is only populated inside the declared
    eligibility window with the requested annotation version. Source record presence
    and amount positivity remain visible as separate facts.
    """
    _validate_panel_identity(panel, spec)
    source = spec.treatment.source
    record_col = f"{source}_record_present"
    positive_col = f"{source}_amount_positive"
    observed_col = f"{source}_amount_observed"
    zero_only_col = f"{source}_amount_zero_only"
    required = [record_col, positive_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise KeyError(
            f"Canonical panel cannot resolve {source}.{spec.treatment.definition}: "
            f"missing {missing}"
        )

    out = panel[[spec.unit_col, spec.period_col, "annotation_version"]].copy()
    record = panel[record_col].astype("boolean").fillna(False)
    positive = panel[positive_col].astype("boolean").fillna(False)
    observed = (
        panel[observed_col].astype("boolean").fillna(False)
        if observed_col in panel.columns else pd.Series(False, index=panel.index, dtype="boolean")
    )
    zero_only = (
        panel[zero_only_col].astype("boolean").fillna(False)
        if zero_only_col in panel.columns else pd.Series(False, index=panel.index, dtype="boolean")
    )

    period_ok = _period_window(
        panel[spec.period_col],
        spec.eligibility.treatment_period_start,
        spec.eligibility.treatment_period_end,
    )
    annotation_ok = (
        panel["annotation_version"].astype(str) == spec.treatment.annotation_version
    )
    eligible = period_ok & annotation_ok

    raw = record if spec.treatment.definition == "record_present" else positive
    treatment = pd.Series(pd.NA, index=panel.index, dtype="Int64")
    treatment.loc[eligible] = raw.loc[eligible].astype(int).to_numpy()

    status = pd.Series("outside_treatment_period", index=panel.index, dtype="string")
    status.loc[period_ok & ~annotation_ok] = "annotation_version_mismatch"
    inside = eligible
    status.loc[inside & ~record] = "no_project_record"
    status.loc[inside & record & positive] = "project_record_positive_amount"
    status.loc[inside & record & ~positive & zero_only] = "project_record_zero_only_amount"
    status.loc[inside & record & ~positive & ~zero_only & observed] = "project_record_nonpositive_amount"
    status.loc[inside & record & ~positive & ~observed] = "project_record_amount_unobserved"

    out["treatment"] = treatment
    out["eligible"] = eligible.astype(bool)
    out["treatment_source_record_present"] = record.astype(bool)
    out["treatment_source_amount_positive"] = positive.astype(bool)
    out["treatment_measurement_status"] = status
    out["treatment_provenance"] = (
        f"{spec.treatment.annotation_version}:"
        f"{spec.treatment.source}.{spec.treatment.definition}"
    )
    return out


def resolve_outcome_measurement(
    panel: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
) -> pd.DataFrame:
    """Resolve the declared outcome and its t+1 measurement policy.

    `unresolved` never fills absent records and explicitly blocks estimation. The
    zero-fill policy requires an externally declared verified source-coverage window.
    """
    source = spec.outcome.source
    value_col = spec.outcome.column
    record_col = f"{source}_record_present"
    required = [spec.unit_col, spec.period_col, value_col, record_col]
    missing = [c for c in required if c not in panel.columns]
    if missing:
        raise KeyError(f"Canonical outcome measurement missing columns: {missing}")

    x = panel[required].copy()
    x["_period_order"] = x[spec.period_col].map(_period_start)
    x = x.sort_values([spec.unit_col, "_period_order"]).reset_index()
    g = x.groupby(spec.unit_col, sort=False)

    x["outcome_post_raw"] = g[value_col].shift(-1)
    x["outcome_post_record_present"] = (
        g[record_col].shift(-1).astype("boolean").fillna(False).astype(bool)
    )
    x["outcome_post_period"] = g[spec.period_col].shift(-1)
    x["outcome_value"] = x["outcome_post_raw"]

    post_present = x["outcome_post_record_present"]
    post_value = x["outcome_post_raw"]
    status = pd.Series("absent_record_unresolved", index=x.index, dtype="string")
    status.loc[post_present & post_value.notna()] = "observed_record_value"
    status.loc[post_present & post_value.isna()] = "record_present_value_missing"
    status.loc[x["outcome_post_period"].isna()] = "no_next_period"

    policy = spec.outcome.absent_record_policy
    if policy == "observed_records_only":
        status.loc[~post_present & x["outcome_post_period"].notna()] = "absent_record_excluded"
    elif policy == "zero_within_verified_coverage":
        post_period = x["outcome_post_period"]
        verified = _period_window(
            post_period.fillna(""),
            spec.outcome.verified_period_start,
            spec.outcome.verified_period_end,
        )
        fill = verified & ~post_present & post_value.isna()
        x.loc[fill, "outcome_value"] = 0.0
        status.loc[fill] = "absent_record_zero_filled_verified_coverage"
        status.loc[
            ~verified & ~post_present & post_period.notna()
        ] = "outside_verified_outcome_coverage"

    x["outcome_measurement_status"] = status
    x["outcome_eligible"] = x["outcome_value"].notna()
    x["outcome_provenance"] = (
        f"{spec.outcome.source}:{spec.outcome.column}:"
        f"{spec.outcome.timing}:{policy}"
    )

    return x.set_index("index").sort_index()[
        [
            spec.unit_col,
            spec.period_col,
            "outcome_post_period",
            "outcome_post_raw",
            "outcome_value",
            "outcome_post_record_present",
            "outcome_eligible",
            "outcome_measurement_status",
            "outcome_provenance",
        ]
    ]


def prepare_experiment_measurement_frame(
    panel: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
) -> pd.DataFrame:
    _validate_panel_identity(panel, spec)
    enriched = attach_country_iso3(
        panel,
        unit_col=spec.unit_col,
        country_col=spec.country_col,
    )
    treatment = resolve_treatment_measurement(enriched, spec)
    outcome = resolve_outcome_measurement(enriched, spec)

    out = enriched.copy()
    for col in [
        "treatment",
        "eligible",
        "treatment_source_record_present",
        "treatment_source_amount_positive",
        "treatment_measurement_status",
        "treatment_provenance",
    ]:
        out[col] = treatment[col].to_numpy()
    for col in [
        "outcome_post_period",
        "outcome_post_raw",
        "outcome_value",
        "outcome_post_record_present",
        "outcome_eligible",
        "outcome_measurement_status",
        "outcome_provenance",
    ]:
        out[col] = outcome[col].to_numpy()

    out["estimation_permitted"] = (
        spec.outcome.absent_record_policy != "unresolved"
    )
    return out


def _source_only_for_periods(
    source_only_keys: pd.DataFrame,
    source: str,
    period_col: str,
    periods,
):
    if source_only_keys is None or source_only_keys.empty:
        return pd.DataFrame()
    if "source" not in source_only_keys or period_col not in source_only_keys:
        return pd.DataFrame()
    period_set = {str(x) for x in periods if pd.notna(x)}
    return source_only_keys.loc[
        (source_only_keys["source"] == source)
        & source_only_keys[period_col].astype(str).isin(period_set)
    ].copy()


def build_input_eligibility_report(
    panel: pd.DataFrame,
    frame: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
    source_only_keys: Optional[pd.DataFrame] = None,
):
    """Build E0 input-eligibility diagnostics before any estimator can run."""
    eligible = frame.loc[frame["eligible"]].copy()
    treatment_source = spec.treatment.source
    treatment_record_col = f"{treatment_source}_record_present"
    outcome_record_col = f"{spec.outcome.source}_record_present"

    treatment_periods = eligible[spec.period_col].dropna().astype(str).unique().tolist()
    post_periods = eligible["outcome_post_period"].dropna().astype(str).unique().tolist()

    treatment_inside = int(
        panel.loc[
            panel[spec.period_col].astype(str).isin(treatment_periods),
            treatment_record_col,
        ].astype("boolean").fillna(False).sum()
    )
    outcome_inside = int(
        panel.loc[
            panel[spec.period_col].astype(str).isin(post_periods),
            outcome_record_col,
        ].astype("boolean").fillna(False).sum()
    )

    t_out = _source_only_for_periods(
        source_only_keys, treatment_source, spec.period_col, treatment_periods
    )
    y_out = _source_only_for_periods(
        source_only_keys, spec.outcome.source, spec.period_col, post_periods
    )
    treatment_outside = int(len(t_out))
    outcome_outside = int(len(y_out))
    treatment_total = treatment_inside + treatment_outside
    outcome_total = outcome_inside + outcome_outside

    t_share = treatment_outside / treatment_total if treatment_total else np.nan
    y_share = outcome_outside / outcome_total if outcome_total else np.nan

    treated = int((eligible["treatment"] == 1).sum())
    control = int((eligible["treatment"] == 0).sum())
    post_record = int(eligible["outcome_post_record_present"].sum())
    post_value = int(eligible["outcome_value"].notna().sum())
    estimation_permitted = bool(frame["estimation_permitted"].all())

    summary_status = "BLOCKED" if not estimation_permitted else (
        "REVIEW" if (treatment_outside or outcome_outside) else "OK"
    )
    rows = [
        {
            "gate": "E0_INPUT_ELIGIBILITY",
            "status": summary_status,
            "metric": "estimation permitted by declared measurement policy",
            "value": estimation_permitted,
            "note": (
                "Outcome absent-record policy is unresolved; preflight may proceed but "
                "an estimator must not run."
                if not estimation_permitted else
                "Measurement policy is explicit; source/lattice attrition remains visible below."
            ),
        },
        {
            "gate": "E0_INPUT_ELIGIBILITY",
            "status": "REVIEW" if treatment_outside else "OK",
            "metric": "treatment source keys outside canonical lattice in treatment window",
            "value": treatment_outside,
            "share": t_share,
            "note": f"{treatment_source}: inside={treatment_inside}, outside={treatment_outside}.",
        },
        {
            "gate": "E0_INPUT_ELIGIBILITY",
            "status": "REVIEW" if outcome_outside else "OK",
            "metric": "outcome source keys outside canonical lattice in post window",
            "value": outcome_outside,
            "share": y_share,
            "note": f"{spec.outcome.source}: inside={outcome_inside}, outside={outcome_outside}.",
        },
        {
            "gate": "E0_INPUT_ELIGIBILITY",
            "status": "OK" if treated and control else "BLOCKED",
            "metric": "eligible treated / control lattice rows",
            "value": f"{treated} / {control}",
            "note": "Counts use the declared treatment semantics and period eligibility only.",
        },
        {
            "gate": "E0_INPUT_ELIGIBILITY",
            "status": "REVIEW",
            "metric": "eligible rows with next-period outcome record / value",
            "value": f"{post_record} / {post_value}",
            "note": "No absent outcome record is silently converted to zero under unresolved policy.",
        },
    ]
    return pd.DataFrame(rows)


def build_treatment_support_by_period(
    frame: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
):
    x = frame.loc[frame["eligible"]].copy()
    if x.empty:
        return pd.DataFrame(
            columns=[spec.period_col, "eligible_rows", "treated", "control", "outcome_post_records"]
        )
    grouped = x.groupby(spec.period_col, dropna=False)
    rows = []
    for period, g in grouped:
        treated = int((g["treatment"] == 1).sum())
        control = int((g["treatment"] == 0).sum())
        rows.append({
            spec.period_col: period,
            "eligible_rows": int(len(g)),
            "treated": treated,
            "control": control,
            "treatment_record_present": int(g["treatment_source_record_present"].sum()),
            "treatment_amount_positive": int(g["treatment_source_amount_positive"].sum()),
            "outcome_post_records": int(g["outcome_post_record_present"].sum()),
            "outcome_post_values": int(g["outcome_value"].notna().sum()),
        })
    return pd.DataFrame(rows).sort_values(spec.period_col)


def render_experiment_preflight(
    spec: CanonicalPanelExperimentSpec,
    input_eligibility: pd.DataFrame,
    support_by_period: pd.DataFrame,
):
    def table(df, cols):
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        rows = [header, sep]
        for _, row in df.iterrows():
            vals = []
            for c in cols:
                value = row.get(c, "")
                if pd.isna(value) if not isinstance(value, (list, dict)) else False:
                    value = ""
                vals.append(str(value).replace("|", "\\|"))
            rows.append("| " + " | ".join(vals) + " |")
        return "\n".join(rows)

    permitted = spec.outcome.absent_record_policy != "unresolved"
    lines = [
        f"# Experiment Measurement Preflight — {spec.experiment_id}",
        "",
        "> This is a measurement/eligibility preflight. It does **not** estimate a treatment effect.",
        "",
        "## Contract",
        "",
        f"- Canonical panel: `{spec.panel_id}`",
        f"- Treatment: `{spec.treatment.source}.{spec.treatment.definition}`",
        f"- Treatment annotation: `{spec.treatment.annotation_version}`",
        f"- Treatment periods: `{spec.eligibility.treatment_period_start}` through `{spec.eligibility.treatment_period_end}`",
        f"- Outcome: `{spec.outcome.column}` from `{spec.outcome.source}`",
        f"- Outcome timing: `{spec.outcome.timing}`",
        f"- Absent-record policy: `{spec.outcome.absent_record_policy}`",
        f"- Country FE field prepared as: `{spec.country_col}` derived transparently from GID",
        f"- Estimation permitted by measurement policy: **{str(permitted).upper()}**",
        "",
        "## E0 input eligibility",
        "",
        table(input_eligibility, ["gate", "status", "metric", "value", "share", "note"]),
        "",
        "## Treatment and next-period outcome support",
        "",
        table(
            support_by_period,
            [
                spec.period_col,
                "eligible_rows",
                "treated",
                "control",
                "treatment_record_present",
                "treatment_amount_positive",
                "outcome_post_records",
                "outcome_post_values",
            ],
        ),
        "",
        "## Stop rule",
        "",
    ]
    if permitted:
        lines.append(
            "The declared outcome measurement policy is resolved. A later estimation PR may proceed only after the remaining experiment gates are run."
        )
    else:
        lines.append(
            "**STOP before estimation.** The outcome absent-record policy is unresolved. Resolve ACLED zero-versus-absence semantics explicitly; do not make missing records disappear by complete-case regression."
        )
    lines.append("")
    return "\n".join(lines)


def run_experiment_preflight(
    panel: pd.DataFrame,
    spec: CanonicalPanelExperimentSpec,
    source_only_keys: Optional[pd.DataFrame] = None,
):
    frame = prepare_experiment_measurement_frame(panel, spec)
    input_eligibility = build_input_eligibility_report(
        panel, frame, spec, source_only_keys=source_only_keys
    )
    support = build_treatment_support_by_period(frame, spec)
    report = render_experiment_preflight(spec, input_eligibility, support)
    return {
        "frame": frame,
        "input_eligibility": input_eligibility,
        "support_by_period": support,
        "report": report,
        "estimation_permitted": spec.outcome.absent_record_policy != "unresolved",
    }


def write_experiment_preflight_outputs(result: dict, spec: CanonicalPanelExperimentSpec, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result["input_eligibility"].to_csv(out / "input_eligibility.csv", index=False)
    result["support_by_period"].to_csv(out / "treatment_support_by_period.csv", index=False)
    result["frame"].head(500).to_csv(out / "measurement_frame_sample.csv", index=False)
    (out / "experiment_preflight.md").write_text(result["report"], encoding="utf-8")
    contract = asdict(spec)
    contract["estimation_permitted"] = bool(result["estimation_permitted"])
    (out / "experiment_contract.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8"
    )
    return out
