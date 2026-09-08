from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm


REQUIRED_INPUT_COLUMNS = (
    "region_id",
    "country_id",
    "poorest_share",
    "richest_share",
    "total_project_count",
    "total_aid_value",
    "battle_count",
    "area",
    "capital",
)


@dataclass(frozen=True)
class BriggsLaneBSpec:
    reference_id: str
    expected_country_count: int
    expected_region_count: int
    log_aid_offset: float
    log_wealth_share_offset: float
    table3_oracle: dict[str, Any]


@dataclass(frozen=True)
class BriggsLaneBResult:
    prepared_frame: pd.DataFrame
    coefficients: pd.DataFrame
    model_summary: pd.DataFrame
    parity: pd.DataFrame
    diagnostics: dict[str, Any]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_briggs_lane_b_spec(path: str | Path) -> BriggsLaneBSpec:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("purpose") != "calibration":
        raise ValueError("Briggs Lane B config must declare purpose='calibration'")
    if payload.get("schema") != "briggs_lane_b_reference.v1":
        raise ValueError("unsupported Briggs Lane B config schema")
    universe = payload.get("analysis_universe") or {}
    transforms = payload.get("transformations") or {}
    return BriggsLaneBSpec(
        reference_id=str(payload["reference_id"]),
        expected_country_count=int(universe["expected_country_count"]),
        expected_region_count=int(universe["expected_region_count"]),
        log_aid_offset=float(transforms["log_aid_offset"]),
        log_wealth_share_offset=float(transforms["log_wealth_share_offset"]),
        table3_oracle=dict(payload["table3_oracle"]),
    )


def load_independent_region_frame(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(source)
    if suffix == ".csv":
        return pd.read_csv(source)
    raise ValueError("Briggs Lane B independent frame must be CSV or Parquet")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{column} contains missing/non-numeric values")
    return values.astype("float64")


def prepare_briggs_lane_b_frame(
    frame: pd.DataFrame,
    spec: BriggsLaneBSpec,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate an independently reconstructed regional frame and derive Briggs variables."""

    missing = sorted(set(REQUIRED_INPUT_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"independent Briggs frame is missing required columns: {missing}")
    if frame.empty:
        raise ValueError("independent Briggs frame must be non-empty")

    prepared = frame.copy()
    for column in ("region_id", "country_id"):
        prepared[column] = prepared[column].astype("string").str.strip()
        invalid = prepared[column].isna() | prepared[column].eq("")
        if invalid.any():
            raise ValueError(f"{column} contains missing/blank identities")
    if prepared["region_id"].duplicated().any():
        raise ValueError("region_id must be unique in the Briggs analysis frame")

    country_count = int(prepared["country_id"].nunique())
    region_count = int(len(prepared))
    if country_count != spec.expected_country_count:
        raise ValueError(
            f"Briggs Lane B requires exactly {spec.expected_country_count} countries; "
            f"found {country_count}"
        )
    if region_count != spec.expected_region_count:
        raise ValueError(
            f"Briggs Lane B requires exactly {spec.expected_region_count} regions; "
            f"found {region_count}"
        )

    for column in (
        "poorest_share",
        "richest_share",
        "total_project_count",
        "total_aid_value",
        "battle_count",
        "area",
        "capital",
    ):
        prepared[column] = _numeric(prepared, column)

    for column in ("poorest_share", "richest_share"):
        invalid = prepared[column].lt(0) | prepared[column].gt(1)
        if invalid.any():
            raise ValueError(f"{column} must lie in [0, 1]")
    for column in ("total_project_count", "total_aid_value", "battle_count"):
        if prepared[column].lt(0).any():
            raise ValueError(f"{column} must be non-negative")
    if prepared["area"].le(0).any():
        raise ValueError("area must be strictly positive")
    if not prepared["capital"].isin([0.0, 1.0]).all():
        raise ValueError("capital must be a 0/1 indicator")

    quintile_sums = prepared.groupby("country_id")[["poorest_share", "richest_share"]].sum()
    max_wealth_sum_error = float((quintile_sums - 1.0).abs().to_numpy().max())
    if max_wealth_sum_error > 1e-8:
        raise ValueError(
            "poorest/richest regional shares must each sum to one within country; "
            f"max error={max_wealth_sum_error}"
        )

    country_totals = prepared.groupby("country_id", sort=False).agg(
        country_project_count=("total_project_count", "sum"),
        country_aid_value=("total_aid_value", "sum"),
        country_battle_count=("battle_count", "sum"),
        country_area=("area", "sum"),
    )
    for column in ("country_project_count", "country_aid_value", "country_area"):
        if country_totals[column].le(0).any():
            bad = country_totals.index[country_totals[column].le(0)].tolist()
            raise ValueError(f"{column} must be positive for every country; invalid={bad}")

    prepared = prepared.merge(
        country_totals,
        left_on="country_id",
        right_index=True,
        how="left",
        validate="many_to_one",
    )
    prepared["prop_totalproj"] = (
        prepared["total_project_count"] / prepared["country_project_count"]
    )
    prepared["prop_totalcost"] = prepared["total_aid_value"] / prepared["country_aid_value"]
    prepared["prop_area"] = prepared["area"] / prepared["country_area"]
    prepared["prop_battles"] = np.where(
        prepared["country_battle_count"].gt(0),
        prepared["battle_count"] / prepared["country_battle_count"],
        0.0,
    )
    prepared["logCost"] = np.log(prepared["total_aid_value"] + spec.log_aid_offset)
    prepared["log_poorest"] = np.log(prepared["poorest_share"] + spec.log_wealth_share_offset)
    prepared["log_richest"] = np.log(prepared["richest_share"] + spec.log_wealth_share_offset)
    prepared["log_area"] = np.log(prepared["area"])

    diagnostics = {
        "reference_id": spec.reference_id,
        "purpose": "calibration",
        "analysis_frame_persisted": False,
        "country_count": country_count,
        "region_count": region_count,
        "regions_with_aid": int(prepared["total_project_count"].gt(0).sum()),
        "zero_aid_regions": int(prepared["total_project_count"].eq(0).sum()),
        "total_project_count": float(prepared["total_project_count"].sum()),
        "max_wealth_share_sum_error": max_wealth_sum_error,
        "zero_battle_countries": int(country_totals["country_battle_count"].eq(0).sum()),
        "transformations": {
            "logCost": f"ln(total_aid_value + {spec.log_aid_offset})",
            "log_poorest": f"ln(poorest_share + {spec.log_wealth_share_offset})",
            "log_richest": f"ln(richest_share + {spec.log_wealth_share_offset})",
            "country_shares": "region value / independently reconstructed country total",
        },
    }
    return prepared, diagnostics


def _within_cluster_fit(
    frame: pd.DataFrame,
    *,
    model_id: str,
    outcome: str,
    covariates: tuple[str, ...],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Replicate Stata xtreg, fe robust using within transformation + country clusters."""

    groups = frame["country_id"]
    y = frame[outcome].astype("float64")
    x = frame[list(covariates)].astype("float64")
    y_within = y - y.groupby(groups).transform("mean")
    x_within = x - x.groupby(groups).transform("mean")

    fit = sm.OLS(y_within, x_within).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups},
        use_t=True,
    )
    coefficient_rows = []
    for term in covariates:
        coefficient_rows.append(
            {
                "model_id": model_id,
                "outcome": outcome,
                "term": term,
                "coefficient": float(fit.params[term]),
                "se": float(fit.bse[term]),
                "t": float(fit.tvalues[term]),
                "p_value": float(fit.pvalues[term]),
                "ci95_low": float(fit.conf_int().loc[term, 0]),
                "ci95_high": float(fit.conf_int().loc[term, 1]),
            }
        )
    summary = {
        "model_id": model_id,
        "outcome": outcome,
        "n": int(fit.nobs),
        "countries": int(groups.nunique()),
        "within_r2": float(fit.rsquared),
        "covariance": "country-clustered robust after within-country transformation",
        "cluster_col": "country_id",
    }
    return pd.DataFrame(coefficient_rows), summary


def _oracle_parity(
    coefficients: pd.DataFrame,
    summaries: pd.DataFrame,
    spec: BriggsLaneBSpec,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model_id, oracle in spec.table3_oracle.items():
        model_coefficients = coefficients[coefficients["model_id"].eq(model_id)].set_index("term")
        for term, target in oracle.items():
            if term == "within_r2":
                actual = float(
                    summaries.loc[summaries["model_id"].eq(model_id), "within_r2"].iloc[0]
                )
                expected = float(target)
                rows.append(
                    {
                        "model_id": model_id,
                        "quantity": "within_r2",
                        "term": "",
                        "actual": actual,
                        "oracle": expected,
                        "difference": actual - expected,
                    }
                )
                continue
            if term not in model_coefficients.index:
                raise ValueError(f"oracle term {term!r} is absent from fitted {model_id}")
            for quantity in ("coefficient", "se"):
                actual = float(model_coefficients.loc[term, quantity])
                expected = float(target[quantity])
                rows.append(
                    {
                        "model_id": model_id,
                        "quantity": quantity,
                        "term": term,
                        "actual": actual,
                        "oracle": expected,
                        "difference": actual - expected,
                    }
                )
    return pd.DataFrame(rows)


def run_briggs_lane_b(
    frame: pd.DataFrame,
    spec: BriggsLaneBSpec,
) -> BriggsLaneBResult:
    prepared, diagnostics = prepare_briggs_lane_b_frame(frame, spec)
    model_specs = (
        (
            "model_1_share_value",
            "prop_totalcost",
            ("poorest_share", "richest_share", "capital", "prop_battles", "prop_area"),
        ),
        (
            "model_2_share_projects",
            "prop_totalproj",
            ("poorest_share", "richest_share", "capital", "prop_battles", "prop_area"),
        ),
        (
            "model_3_log_value",
            "logCost",
            ("log_poorest", "log_richest", "capital", "battle_count", "log_area"),
        ),
    )

    coefficient_frames = []
    model_rows = []
    for model_id, outcome, covariates in model_specs:
        fitted, summary = _within_cluster_fit(
            prepared, model_id=model_id, outcome=outcome, covariates=covariates
        )
        coefficient_frames.append(fitted)
        model_rows.append(summary)
    coefficients = pd.concat(coefficient_frames, ignore_index=True)
    model_summary = pd.DataFrame(model_rows)
    parity = _oracle_parity(coefficients, model_summary, spec)
    diagnostics["oracle_used_as_input"] = False
    diagnostics["oracle_reading_rule"] = (
        "Differences are diagnostics only; they cannot select source decoding, geography, weights, "
        "amount allocation, or estimator specification."
    )
    return BriggsLaneBResult(
        prepared_frame=prepared,
        coefficients=coefficients,
        model_summary=model_summary,
        parity=parity,
        diagnostics=diagnostics,
    )


def write_briggs_lane_b_run(
    result: BriggsLaneBResult,
    *,
    output_dir: str | Path,
    input_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result.coefficients.to_csv(output / "table3_coefficients.csv", index=False)
    result.model_summary.to_csv(output / "table3_model_summary.csv", index=False)
    result.parity.to_csv(output / "table3_oracle_parity.csv", index=False)

    identity = {
        "schema": "briggs_lane_b_run_identity.v1",
        "reference_id": result.diagnostics["reference_id"],
        "purpose": "calibration",
        "analysis_frame_persisted": False,
        "independent_input_sha256": sha256_file(input_path) if input_path is not None else None,
        "config_sha256": sha256_file(config_path) if config_path is not None else None,
        "oracle_used_as_input": False,
    }
    (output / "run_identity.json").write_text(_json_text(identity), encoding="utf-8")
    (output / "diagnostics.json").write_text(
        _json_text(result.diagnostics), encoding="utf-8"
    )
    return output
