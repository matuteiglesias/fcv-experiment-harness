from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm


class BriggsPragmaticError(ValueError):
    pass


REQUIRED_BASE_COLUMNS = {
    "country_iso3",
    "region_id",
    "poorest_share",
    "richest_share",
    "aid_value",
    "aid_location_count",
}
REQUIRED_CONTROL_COLUMNS = {"capital", "battles", "area_km2"}


@dataclass(frozen=True)
class BriggsPragmaticSpec:
    raw: dict[str, Any]

    @property
    def benchmark_id(self) -> str:
        return str(self.raw["benchmark_id"])

    @property
    def analysis_countries(self) -> tuple[str, ...]:
        return tuple(self.raw["analysis_countries"])

    @property
    def oracle(self) -> dict[str, Any]:
        return dict(self.raw["oracle"])


def load_briggs_pragmatic_spec(path: str | Path) -> BriggsPragmaticSpec:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != "briggs_2017_pragmatic_analogue.v1":
        raise BriggsPragmaticError("unexpected pragmatic Briggs schema")
    if raw.get("purpose") != "calibration_analogue":
        raise BriggsPragmaticError("pragmatic Briggs lane must declare purpose=calibration_analogue")
    if raw.get("geography", {}).get("provider") != "GADM":
        raise BriggsPragmaticError("pragmatic lane is explicitly bound to a GADM-derived geography")
    if raw.get("geography", {}).get("historical_entity_parity_required") is not False:
        raise BriggsPragmaticError("pragmatic lane must disclose that historical entity parity is not required")
    countries = raw.get("analysis_countries", [])
    if len(countries) != 13 or len(set(countries)) != 13:
        raise BriggsPragmaticError("current pragmatic lane must keep the declared 13-country subset")
    if raw.get("oracle", {}).get("published_log_richest") != 0.72034:
        raise BriggsPragmaticError("published oracle must remain evaluation-only and unchanged")
    return BriggsPragmaticSpec(raw=raw)


def prepare_briggs_pragmatic_frame(frame: pd.DataFrame, spec: BriggsPragmaticSpec) -> pd.DataFrame:
    missing = REQUIRED_BASE_COLUMNS - set(frame.columns)
    if missing:
        raise BriggsPragmaticError(f"missing required columns: {sorted(missing)}")
    if frame.empty:
        raise BriggsPragmaticError("pragmatic Briggs frame must be non-empty")

    out = frame.copy()
    out["country_iso3"] = out["country_iso3"].astype("string").str.strip()
    out["region_id"] = out["region_id"].astype("string").str.strip()
    if out[["country_iso3", "region_id"]].isna().any().any():
        raise BriggsPragmaticError("country and region identities must be nonmissing")
    if out["region_id"].duplicated().any():
        raise BriggsPragmaticError("region_id must be globally unique")

    allowed = set(spec.analysis_countries)
    unexpected = set(out["country_iso3"].dropna().astype(str)) - allowed
    if unexpected:
        raise BriggsPragmaticError(f"frame contains countries outside declared pragmatic scope: {sorted(unexpected)}")

    numeric = ["poorest_share", "richest_share", "aid_value", "aid_location_count"]
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out[numeric].isna().any().any():
        raise BriggsPragmaticError("base analytical quantities must be numeric and nonmissing")
    if (out[numeric] < 0).any().any():
        raise BriggsPragmaticError("base analytical quantities must be nonnegative")
    if (out[["poorest_share", "richest_share"]] > 1).any().any():
        raise BriggsPragmaticError("wealth shares must lie in [0, 1]")

    share_sums = out.groupby("country_iso3")[["poorest_share", "richest_share"]].sum()
    max_share_error = float((share_sums - 1.0).abs().to_numpy().max())
    if max_share_error > 1e-6:
        raise BriggsPragmaticError(
            "poorest and richest regional shares must each sum to one within retained country; "
            f"max error={max_share_error}"
        )

    country_aid = out.groupby("country_iso3")["aid_value"].transform("sum")
    country_locations = out.groupby("country_iso3")["aid_location_count"].transform("sum")
    if (country_aid <= 0).any() or (country_locations <= 0).any():
        raise BriggsPragmaticError("each retained country must have positive aid value and location support")

    out["prop_totalcost"] = out["aid_value"] / country_aid
    out["prop_totalproj"] = out["aid_location_count"] / country_locations
    out["logCost"] = np.log(out["aid_value"] + 0.1)
    out["log_poorest"] = np.log(out["poorest_share"] + 0.001)
    out["log_richest"] = np.log(out["richest_share"] + 0.001)

    if REQUIRED_CONTROL_COLUMNS <= set(out.columns):
        for col in REQUIRED_CONTROL_COLUMNS:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[list(REQUIRED_CONTROL_COLUMNS)].isna().any().any():
            raise BriggsPragmaticError("declared controls must be numeric and nonmissing when supplied")
        if (out["area_km2"] <= 0).any() or (out["battles"] < 0).any():
            raise BriggsPragmaticError("area must be positive and battles nonnegative")
        if not out["capital"].isin([0, 1]).all():
            raise BriggsPragmaticError("capital must be a 0/1 indicator")
        country_battles = out.groupby("country_iso3")["battles"].transform("sum")
        out["prop_battles"] = np.where(country_battles > 0, out["battles"] / country_battles, 0.0)
        out["prop_area"] = out["area_km2"] / out.groupby("country_iso3")["area_km2"].transform("sum")
        out["log_area"] = np.log(out["area_km2"])

    out.attrs["max_wealth_share_sum_error"] = max_share_error
    return out


def _within_cluster_fit(
    frame: pd.DataFrame,
    *,
    model_id: str,
    outcome: str,
    covariates: tuple[str, ...],
) -> dict[str, Any]:
    """Use the same within-country + country-cluster estimator family as exact Lane B."""
    groups = frame["country_iso3"]
    y = frame[outcome].astype("float64")
    x = frame[list(covariates)].astype("float64")
    y_within = y - y.groupby(groups).transform("mean")
    x_within = x - x.groupby(groups).transform("mean")
    fit = sm.OLS(y_within, x_within).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups},
        use_t=True,
    )
    coefficients: dict[str, Any] = {}
    for term in covariates:
        coefficients[term] = {
            "estimate": float(fit.params[term]),
            "se": float(fit.bse[term]),
            "t": float(fit.tvalues[term]),
            "pvalue": float(fit.pvalues[term]),
        }
    return {
        "model_id": model_id,
        "outcome": outcome,
        "n": int(fit.nobs),
        "countries": int(groups.nunique()),
        "within_r2": float(fit.rsquared),
        "covariance": "country-clustered robust after within-country transformation",
        "coefficients": coefficients,
    }


def run_briggs_pragmatic(frame: pd.DataFrame, spec: BriggsPragmaticSpec) -> dict[str, Any]:
    prepared = prepare_briggs_pragmatic_frame(frame, spec)
    results: dict[str, Any] = {
        "schema": "briggs_2017_pragmatic_result.v1",
        "benchmark_id": spec.benchmark_id,
        "purpose": "calibration_analogue",
        "analysis_rows": int(len(prepared)),
        "analysis_countries": int(prepared["country_iso3"].nunique()),
        "analysis_country_iso3": sorted(prepared["country_iso3"].unique().tolist()),
        "oracle_data_used_as_input": False,
        "max_wealth_share_sum_error": prepared.attrs["max_wealth_share_sum_error"],
        "known_divergences": {
            "excluded_published_countries": spec.raw["excluded_published_countries"],
            "geography": spec.raw["geography"]["known_divergence"],
            "aid_identity": spec.raw["aid"]["known_divergence"],
            "acled": spec.raw["conflict_control"]["known_divergence"],
            "inference": "same within-country/country-cluster estimator family as the exact harness Lane B runner; numerical software is not claimed byte-identical to Briggs Stata",
        },
        "models": {},
    }

    results["models"]["core"] = _within_cluster_fit(
        prepared,
        model_id="core",
        outcome="logCost",
        covariates=("log_poorest", "log_richest"),
    )

    if REQUIRED_CONTROL_COLUMNS <= set(prepared.columns):
        results["models"]["share_value"] = _within_cluster_fit(
            prepared,
            model_id="share_value",
            outcome="prop_totalcost",
            covariates=("poorest_share", "richest_share", "capital", "prop_battles", "prop_area"),
        )
        results["models"]["share_locations"] = _within_cluster_fit(
            prepared,
            model_id="share_locations",
            outcome="prop_totalproj",
            covariates=("poorest_share", "richest_share", "capital", "prop_battles", "prop_area"),
        )
        results["models"]["preferred_analogue"] = _within_cluster_fit(
            prepared,
            model_id="preferred_analogue",
            outcome="logCost",
            covariates=("log_poorest", "log_richest", "capital", "battles", "log_area"),
        )

    target_name = "preferred_analogue" if "preferred_analogue" in results["models"] else "core"
    target = results["models"][target_name]
    richest = target["coefficients"]["log_richest"]
    poorest = target["coefficients"]["log_poorest"]
    oracle = spec.oracle
    results["comparison_to_briggs"] = {
        "model_used": target_name,
        "reading_rule": "Drift is descriptive calibration evidence only and must not select or tune upstream source mappings.",
        "log_richest": {
            "estimate": richest["estimate"],
            "se": richest["se"],
            "published": oracle["published_log_richest"],
            "published_se": oracle["published_log_richest_se"],
            "drift": richest["estimate"] - oracle["published_log_richest"],
            "same_sign": bool(np.sign(richest["estimate"]) == np.sign(oracle["published_log_richest"])),
        },
        "log_poorest": {
            "estimate": poorest["estimate"],
            "se": poorest["se"],
            "published": oracle["published_log_poorest"],
            "published_se": oracle["published_log_poorest_se"],
            "drift": poorest["estimate"] - oracle["published_log_poorest"],
            "same_sign": bool(np.sign(poorest["estimate"]) == np.sign(oracle["published_log_poorest"])),
        },
        "within_r2": {
            "actual": target["within_r2"],
            "published": oracle["published_within_r2"],
            "drift": target["within_r2"] - oracle["published_within_r2"],
        },
    }
    return results
