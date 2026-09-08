from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .calibration import calibration_estimate
from .current_e2_reference import CurrentE2ReferenceSpec
from .reference_identity import stable_frame_sha256


INFLUENCE_SUITE_SCHEMA = "current_e2_influence_stability.v1"


class CurrentE2InfluenceError(ValueError):
    """Raised when R3 is not bound to the frozen current-E2 reference."""


@dataclass(frozen=True)
class CurrentE2InfluenceSpec:
    suite_id: str
    purpose: str
    reference_id: str
    primary_cell_id: str
    required_analysis_identity_sha256: str
    required_primary_frame_sha256: str
    country_leave_one_out: bool
    period_leave_one_out: bool
    adm2_screening_method: str
    top_adm2_exact_refits: int

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2InfluenceSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != INFLUENCE_SUITE_SCHEMA:
            raise CurrentE2InfluenceError("unsupported current E2 influence suite schema")
        method = str(raw.get("adm2_screening_method", "cluster_score_linearization"))
        if method != "cluster_score_linearization":
            raise CurrentE2InfluenceError("unsupported ADM2 influence screening method")
        top = int(raw.get("top_adm2_exact_refits", 20))
        if top <= 0:
            raise CurrentE2InfluenceError("top_adm2_exact_refits must be positive")
        return cls(
            suite_id=str(raw["suite_id"]),
            purpose=str(raw.get("purpose", "calibration")),
            reference_id=str(raw["reference_id"]),
            primary_cell_id=str(raw["primary_cell_id"]),
            required_analysis_identity_sha256=str(raw["required_analysis_identity_sha256"]),
            required_primary_frame_sha256=str(raw["required_primary_frame_sha256"]),
            country_leave_one_out=bool(raw.get("country_leave_one_out", True)),
            period_leave_one_out=bool(raw.get("period_leave_one_out", True)),
            adm2_screening_method=method,
            top_adm2_exact_refits=top,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INFLUENCE_SUITE_SCHEMA,
            "suite_id": self.suite_id,
            "purpose": self.purpose,
            "reference_id": self.reference_id,
            "primary_cell_id": self.primary_cell_id,
            "required_analysis_identity_sha256": self.required_analysis_identity_sha256,
            "required_primary_frame_sha256": self.required_primary_frame_sha256,
            "country_leave_one_out": self.country_leave_one_out,
            "period_leave_one_out": self.period_leave_one_out,
            "adm2_screening_method": self.adm2_screening_method,
            "top_adm2_exact_refits": self.top_adm2_exact_refits,
        }


def _require_binding(
    result: Mapping[str, Any],
    suite: CurrentE2InfluenceSpec,
) -> tuple[CurrentE2ReferenceSpec, Mapping[str, Any], Mapping[str, Any], pd.DataFrame, str]:
    spec = result.get("spec")
    if not isinstance(spec, CurrentE2ReferenceSpec):
        raise CurrentE2InfluenceError("R3 requires a CurrentE2ReferenceSpec")
    if suite.purpose != "calibration" or spec.purpose != "calibration":
        raise CurrentE2InfluenceError("R3 must remain calibration-only")
    if suite.reference_id != spec.reference_id:
        raise CurrentE2InfluenceError("R3 reference_id mismatch")
    if suite.primary_cell_id != spec.primary_cell.cell_id:
        raise CurrentE2InfluenceError("R3 PRIMARY cell mismatch")

    identity = result.get("reference_identity")
    if not isinstance(identity, Mapping):
        raise CurrentE2InfluenceError("R3 requires reference_identity")
    lock = identity.get("lock")
    if not isinstance(lock, Mapping) or lock.get("verified") is not True:
        raise CurrentE2InfluenceError("R3 requires a verified reference lock")
    if identity.get("analysis_identity_sha256") != suite.required_analysis_identity_sha256:
        raise CurrentE2InfluenceError("R3 analysis identity mismatch")

    calibration = result.get("calibration")
    if not isinstance(calibration, Mapping):
        raise CurrentE2InfluenceError("R3 requires calibration results")
    cells = calibration.get("cells")
    if not isinstance(cells, Mapping) or suite.primary_cell_id not in cells:
        raise CurrentE2InfluenceError("R3 PRIMARY cell result missing")
    primary = cells[suite.primary_cell_id]
    if not isinstance(primary, Mapping) or primary.get("estimation_permitted") is not True:
        raise CurrentE2InfluenceError("R3 blocked because PRIMARY hard gates do not pass")
    frame = primary.get("frame")
    if not isinstance(frame, pd.DataFrame):
        raise CurrentE2InfluenceError("R3 requires in-memory PRIMARY frame")
    frame_sha = stable_frame_sha256(frame, unit_col=spec.unit_col, period_col=spec.period_col)
    if frame_sha != suite.required_primary_frame_sha256:
        raise CurrentE2InfluenceError("R3 PRIMARY frame fingerprint drift")
    if identity.get("primary_frame_sha256") != frame_sha:
        raise CurrentE2InfluenceError("R3 reference identity frame fingerprint mismatch")
    return spec, identity, primary, frame, frame_sha


def _complete_sample(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> pd.DataFrame:
    needed = [
        "outcome_value",
        "outcome_pre",
        "treatment",
        spec.unit_col,
        spec.period_col,
        spec.country_col,
    ]
    return frame.loc[frame["eligible"]].dropna(subset=needed).copy()


def _support_summary(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> tuple[int, int, int, int]:
    sample = _complete_sample(frame, spec)
    treated = int((sample["treatment"] == 1).sum())
    control = int((sample["treatment"] == 0).sum())
    support = sample.groupby(spec.period_col, sort=True)["treatment"].agg(
        treated=lambda x: int((x == 1).sum()),
        control=lambda x: int((x == 0).sum()),
    )
    mixed = int(((support["treated"] > 0) & (support["control"] > 0)).sum()) if len(support) else 0
    return int(len(sample)), treated, control, mixed


def _diagnostic_row(
    *,
    omission_type: str,
    omitted_value: str,
    subset: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    calibration_spec: Any,
    baseline_effect: float,
    baseline_se: float,
    outcome_sd: float,
) -> dict[str, Any]:
    estimate = calibration_estimate(subset, calibration_spec)
    n, treated, control, mixed = _support_summary(subset, spec)
    if not estimate.get("ok"):
        return {
            "omission_type": omission_type,
            "omitted_value": omitted_value,
            "ok": False,
            "reason": estimate.get("reason", "estimation failed"),
            "n": n,
            "treated": treated,
            "control": control,
            "mixed_support_periods": mixed,
        }
    effect = float(estimate["effect"])
    delta = effect - baseline_effect
    return {
        "omission_type": omission_type,
        "omitted_value": omitted_value,
        "ok": True,
        "effect": effect,
        "se": float(estimate["se"]),
        "effect_sd": effect / outcome_sd if outcome_sd > 0 else np.nan,
        "delta_effect": delta,
        "delta_effect_sd": delta / outcome_sd if outcome_sd > 0 else np.nan,
        "delta_effect_in_canonical_se": delta / baseline_se if baseline_se > 0 else np.nan,
        "sign_same_as_canonical": bool(np.sign(effect) == np.sign(baseline_effect)),
        "n": n,
        "n_units": int(estimate.get("n_units", 0)),
        "treated": treated,
        "control": control,
        "mixed_support_periods": mixed,
        "reason": "",
    }


def _country_loo(
    frame: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    calibration_spec: Any,
    *,
    baseline_effect: float,
    baseline_se: float,
    outcome_sd: float,
) -> pd.DataFrame:
    rows = []
    countries = sorted(frame[spec.country_col].dropna().astype(str).unique().tolist())
    for country in countries:
        subset = frame.loc[frame[spec.country_col].astype(str).ne(country)].copy()
        rows.append(
            _diagnostic_row(
                omission_type="country",
                omitted_value=country,
                subset=subset,
                spec=spec,
                calibration_spec=calibration_spec,
                baseline_effect=baseline_effect,
                baseline_se=baseline_se,
                outcome_sd=outcome_sd,
            )
        )
    table = pd.DataFrame(rows)
    if len(table):
        table["abs_delta_effect"] = pd.to_numeric(table["delta_effect"], errors="coerce").abs()
        table = table.sort_values(["abs_delta_effect", "omitted_value"], ascending=[False, True]).reset_index(drop=True)
    return table


def _period_loo(
    frame: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    calibration_spec: Any,
    *,
    baseline_effect: float,
    baseline_se: float,
    outcome_sd: float,
) -> pd.DataFrame:
    rows = []
    periods = sorted(frame[spec.period_col].dropna().astype(str).unique().tolist())
    for period in periods:
        subset = frame.loc[frame[spec.period_col].astype(str).ne(period)].copy()
        rows.append(
            _diagnostic_row(
                omission_type="period",
                omitted_value=period,
                subset=subset,
                spec=spec,
                calibration_spec=calibration_spec,
                baseline_effect=baseline_effect,
                baseline_se=baseline_se,
                outcome_sd=outcome_sd,
            )
        )
    table = pd.DataFrame(rows)
    if len(table):
        table["abs_delta_effect"] = pd.to_numeric(table["delta_effect"], errors="coerce").abs()
        table = table.sort_values(["abs_delta_effect", "omitted_value"], ascending=[False, True]).reset_index(drop=True)
    return table


def _adm2_screen(frame: pd.DataFrame, spec: CurrentE2ReferenceSpec) -> pd.DataFrame:
    sample = _complete_sample(frame, spec)
    formula = (
        f"outcome_value ~ treatment + outcome_pre + "
        f"C({spec.period_col}) + C({spec.country_col})"
    )
    fit = smf.ols(formula, data=sample).fit()
    names = list(fit.model.exog_names)
    if "treatment" not in names:
        raise CurrentE2InfluenceError("R3 influence screen cannot locate treatment coefficient")
    treatment_index = names.index("treatment")
    exog = np.asarray(fit.model.exog, dtype=float)
    residual = np.asarray(fit.resid, dtype=float)
    xtx_inv = np.linalg.pinv(exog.T @ exog)
    beta_weight = exog @ xtx_inv[:, treatment_index]
    one_step_contribution = beta_weight * residual

    work = sample[[spec.unit_col, spec.country_col, "treatment"]].copy()
    work["one_step_treatment_beta_contribution"] = one_step_contribution
    grouped = work.groupby(spec.unit_col, sort=True).agg(
        country_iso3=(spec.country_col, "first"),
        rows=(spec.unit_col, "size"),
        treated_rows=("treatment", lambda x: int((x == 1).sum())),
        one_step_treatment_beta_contribution=("one_step_treatment_beta_contribution", "sum"),
    ).reset_index()
    grouped["abs_one_step_contribution"] = grouped["one_step_treatment_beta_contribution"].abs()
    grouped = grouped.sort_values(
        ["abs_one_step_contribution", spec.unit_col], ascending=[False, True]
    ).reset_index(drop=True)
    grouped.insert(0, "screen_rank", np.arange(1, len(grouped) + 1))
    grouped["screening_method"] = "cluster_score_linearization"
    return grouped


def _exact_adm2_refits(
    frame: pd.DataFrame,
    screen: pd.DataFrame,
    spec: CurrentE2ReferenceSpec,
    calibration_spec: Any,
    *,
    top_n: int,
    baseline_effect: float,
    baseline_se: float,
    outcome_sd: float,
) -> pd.DataFrame:
    rows = []
    for _, candidate in screen.head(int(top_n)).iterrows():
        gid = str(candidate[spec.unit_col])
        subset = frame.loc[frame[spec.unit_col].astype(str).ne(gid)].copy()
        row = _diagnostic_row(
            omission_type="adm2",
            omitted_value=gid,
            subset=subset,
            spec=spec,
            calibration_spec=calibration_spec,
            baseline_effect=baseline_effect,
            baseline_se=baseline_se,
            outcome_sd=outcome_sd,
        )
        row["screen_rank"] = int(candidate["screen_rank"])
        row["screen_abs_one_step_contribution"] = float(candidate["abs_one_step_contribution"])
        row["country_iso3"] = str(candidate["country_iso3"])
        rows.append(row)
    table = pd.DataFrame(rows)
    if len(table):
        table["abs_delta_effect"] = pd.to_numeric(table["delta_effect"], errors="coerce").abs()
        table = table.sort_values(["abs_delta_effect", "screen_rank"], ascending=[False, True]).reset_index(drop=True)
    return table


def _max_abs_row(table: pd.DataFrame) -> dict[str, Any] | None:
    if table.empty or "delta_effect" not in table:
        return None
    values = pd.to_numeric(table["delta_effect"], errors="coerce").abs()
    if not values.notna().any():
        return None
    idx = values.idxmax()
    row = table.loc[idx]
    return {
        "omitted_value": str(row["omitted_value"]),
        "delta_effect": float(row["delta_effect"]),
        "delta_effect_sd": float(row.get("delta_effect_sd", np.nan)),
        "delta_effect_in_canonical_se": float(row.get("delta_effect_in_canonical_se", np.nan)),
    }


def run_current_e2_influence_stability(
    result: Mapping[str, Any],
    suite: CurrentE2InfluenceSpec,
) -> dict[str, Any]:
    """Characterize concentration of the unchanged canonical point estimate.

    Omission results are diagnostics only. They never replace the canonical result and
    are not converted into an aggregate pass/fail score.
    """
    spec, identity, primary, frame, frame_sha = _require_binding(result, suite)
    calibration_spec = result.get("calibration_spec")
    if calibration_spec is None:
        raise CurrentE2InfluenceError("R3 requires calibration_spec")
    baseline = primary.get("estimate")
    if not isinstance(baseline, Mapping) or not baseline.get("ok"):
        raise CurrentE2InfluenceError("R3 requires successful canonical estimate")
    baseline_effect = float(baseline["effect"])
    baseline_se = float(baseline["se"])
    sample = _complete_sample(frame, spec)
    outcome_sd = float(pd.to_numeric(sample["outcome_value"], errors="coerce").std(ddof=1))
    if not np.isfinite(outcome_sd) or outcome_sd <= 0:
        raise CurrentE2InfluenceError("R3 requires finite positive outcome SD")

    country = (
        _country_loo(
            frame,
            spec,
            calibration_spec,
            baseline_effect=baseline_effect,
            baseline_se=baseline_se,
            outcome_sd=outcome_sd,
        )
        if suite.country_leave_one_out
        else pd.DataFrame()
    )
    period = (
        _period_loo(
            frame,
            spec,
            calibration_spec,
            baseline_effect=baseline_effect,
            baseline_se=baseline_se,
            outcome_sd=outcome_sd,
        )
        if suite.period_leave_one_out
        else pd.DataFrame()
    )
    screen = _adm2_screen(frame, spec)
    exact = _exact_adm2_refits(
        frame,
        screen,
        spec,
        calibration_spec,
        top_n=suite.top_adm2_exact_refits,
        baseline_effect=baseline_effect,
        baseline_se=baseline_se,
        outcome_sd=outcome_sd,
    )

    binding = {
        "schema": "current_e2_influence_binding.v1",
        "suite_id": suite.suite_id,
        "purpose": "calibration",
        "reference_id": spec.reference_id,
        "primary_cell_id": suite.primary_cell_id,
        "analysis_identity_sha256": identity["analysis_identity_sha256"],
        "execution_identity_sha256": identity["execution_identity_sha256"],
        "primary_frame_sha256": frame_sha,
        "reference_lock_id": identity["lock"].get("lock_id"),
        "primary_hard_gate_state": "PASS",
        "analysis_frame_persisted": False,
        "reprojection_performed": False,
        "reingestion_performed": False,
        "canonical_result_replaced": False,
    }
    summary = {
        "schema": "current_e2_influence_summary.v1",
        "purpose": "calibration",
        "canonical_effect": baseline_effect,
        "canonical_se": baseline_se,
        "canonical_effect_sd": baseline_effect / outcome_sd,
        "outcome_sd": outcome_sd,
        "country_loo_count": int(len(country)),
        "period_loo_count": int(len(period)),
        "adm2_screen_count": int(len(screen)),
        "adm2_exact_refit_count": int(len(exact)),
        "largest_country_movement": _max_abs_row(country),
        "largest_period_movement": _max_abs_row(period),
        "largest_screened_adm2_exact_movement": _max_abs_row(exact),
        "interpretation": (
            "Influence/concentration evidence only. No omission is a preferred specification, "
            "and no aggregate fragility score is used to replace the canonical estimate."
        ),
    }
    return {
        "suite_spec": suite.to_dict(),
        "reference_binding": binding,
        "summary": summary,
        "country_leave_one_out": country,
        "period_leave_one_out": period,
        "adm2_influence_screen": screen,
        "top_adm2_exact_refits": exact,
    }


def write_current_e2_influence_outputs(
    result: Mapping[str, Any],
    out_dir: str | Path,
) -> Path:
    root = Path(out_dir)
    target = root / "influence_stability"
    target.mkdir(parents=True, exist_ok=True)
    tables = {
        "country_leave_one_out": "country_leave_one_out.csv",
        "period_leave_one_out": "period_leave_one_out.csv",
        "adm2_influence_screen": "adm2_influence_screen.csv",
        "top_adm2_exact_refits": "top_adm2_exact_refits.csv",
    }
    for key, filename in tables.items():
        table = result.get(key)
        if not isinstance(table, pd.DataFrame):
            raise CurrentE2InfluenceError(f"R3 result {key!r} must be a DataFrame")
        table.to_csv(target / filename, index=False)
    for key, filename in (
        ("suite_spec", "influence_spec.json"),
        ("reference_binding", "reference_binding.json"),
        ("summary", "influence_summary.json"),
    ):
        payload = result.get(key)
        if not isinstance(payload, Mapping):
            raise CurrentE2InfluenceError(f"R3 result {key!r} must be a mapping")
        (target / filename).write_text(
            json.dumps(dict(payload), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    run_path = root / "reference_run.json"
    if run_path.is_file():
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload["influence_stability"] = {
            "state": "RUN",
            "path": "influence_stability",
            "suite_id": result["suite_spec"]["suite_id"],
            "analysis_identity_sha256": result["reference_binding"]["analysis_identity_sha256"],
            "primary_frame_sha256": result["reference_binding"]["primary_frame_sha256"],
            "analysis_frame_persisted": False,
        }
        run_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return target


__all__ = [
    "CurrentE2InfluenceError",
    "CurrentE2InfluenceSpec",
    "run_current_e2_influence_stability",
    "write_current_e2_influence_outputs",
]
