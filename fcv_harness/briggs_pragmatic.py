from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


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
    raw: dict

    @property
    def benchmark_id(self) -> str:
        return str(self.raw["benchmark_id"])

    @property
    def analysis_countries(self) -> tuple[str, ...]:
        return tuple(self.raw["analysis_countries"])

    @property
    def oracle(self) -> dict:
        return dict(self.raw["oracle"])


def load_briggs_pragmatic_spec(path: str | Path) -> BriggsPragmaticSpec:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != "briggs_2017_pragmatic_analogue.v1":
        raise BriggsPragmaticError("unexpected pragmatic Briggs schema")
    if raw.get("purpose") != "calibration_analogue":
        raise BriggsPragmaticError("pragmatic Briggs lane must declare calibration_analogue")
    if raw.get("geography", {}).get("provider") != "GADM":
        raise BriggsPragmaticError("pragmatic lane is explicitly bound to GADM")
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

    out = frame.copy()
    if out[["country_iso3", "region_id"]].duplicated().any():
        raise BriggsPragmaticError("analysis frame must be one row per country-region")

    allowed = set(spec.analysis_countries)
    unexpected = set(out["country_iso3"].dropna().astype(str)) - allowed
    if unexpected:
        raise BriggsPragmaticError(f"frame contains countries outside declared pragmatic scope: {sorted(unexpected)}")

    numeric = ["poorest_share", "richest_share", "aid_value", "aid_location_count"]
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out[numeric].isna().any().any():
        raise BriggsPragmaticError("base analytical quantities must be numeric and nonmissing")
    if (out[["poorest_share", "richest_share", "aid_value", "aid_location_count"]] < 0).any().any():
        raise BriggsPragmaticError("base analytical quantities must be nonnegative")

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
        out["prop_battles"] = out["battles"] / out.groupby("country_iso3")["battles"].transform("sum").replace(0, np.nan)
        out["prop_battles"] = out["prop_battles"].fillna(0.0)
        out["prop_area"] = out["area_km2"] / out.groupby("country_iso3")["area_km2"].transform("sum")
        out["log_area"] = np.log(out["area_km2"])
    return out


def _fit(formula: str, frame: pd.DataFrame) -> dict:
    model = smf.ols(formula, data=frame).fit(
        cov_type="cluster",
        cov_kwds={"groups": frame["country_iso3"], "use_correction": True},
    )
    payload = {
        "formula": formula,
        "n": int(model.nobs),
        "countries": int(frame["country_iso3"].nunique()),
        "r2": float(model.rsquared),
        "coefficients": {},
    }
    for term in ["poorest_share", "richest_share", "log_poorest", "log_richest"]:
        if term in model.params.index:
            payload["coefficients"][term] = {
                "estimate": float(model.params[term]),
                "se": float(model.bse[term]),
                "t_or_z": float(model.tvalues[term]),
                "pvalue": float(model.pvalues[term]),
            }
    return payload


def run_briggs_pragmatic(frame: pd.DataFrame, spec: BriggsPragmaticSpec) -> dict:
    prepared = prepare_briggs_pragmatic_frame(frame, spec)
    results = {
        "schema": "briggs_2017_pragmatic_result.v1",
        "benchmark_id": spec.benchmark_id,
        "purpose": "calibration_analogue",
        "analysis_rows": int(len(prepared)),
        "analysis_countries": int(prepared["country_iso3"].nunique()),
        "oracle_data_used_as_input": False,
        "known_divergences": {
            "excluded_published_countries": spec.raw["excluded_published_countries"],
            "geography": spec.raw["geography"]["known_divergence"],
            "aid_identity": spec.raw["aid"]["known_divergence"],
            "acled": spec.raw["conflict_control"]["known_divergence"],
            "inference": "statsmodels country-cluster covariance is an analogue of the published Stata xtreg robust implementation, not claimed byte-identical",
        },
        "models": {},
    }

    core_formula = "logCost ~ log_poorest + log_richest + C(country_iso3)"
    results["models"]["core"] = _fit(core_formula, prepared)

    if REQUIRED_CONTROL_COLUMNS <= set(prepared.columns):
        results["models"]["share_value"] = _fit(
            "prop_totalcost ~ poorest_share + richest_share + capital + prop_battles + prop_area + C(country_iso3)",
            prepared,
        )
        results["models"]["share_locations"] = _fit(
            "prop_totalproj ~ poorest_share + richest_share + capital + prop_battles + prop_area + C(country_iso3)",
            prepared,
        )
        results["models"]["preferred_analogue"] = _fit(
            "logCost ~ log_poorest + log_richest + capital + battles + log_area + C(country_iso3)",
            prepared,
        )

    target_model = results["models"].get("preferred_analogue", results["models"]["core"])
    richest = target_model["coefficients"]["log_richest"]
    poorest = target_model["coefficients"]["log_poorest"]
    oracle = spec.oracle
    results["comparison_to_briggs"] = {
        "model_used": "preferred_analogue" if "preferred_analogue" in results["models"] else "core",
        "log_richest": {
            "estimate": richest["estimate"],
            "published": oracle["published_log_richest"],
            "drift": richest["estimate"] - oracle["published_log_richest"],
            "same_sign": bool(np.sign(richest["estimate"]) == np.sign(oracle["published_log_richest"])),
        },
        "log_poorest": {
            "estimate": poorest["estimate"],
            "published": oracle["published_log_poorest"],
            "drift": poorest["estimate"] - oracle["published_log_poorest"],
            "same_sign": bool(np.sign(poorest["estimate"]) == np.sign(oracle["published_log_poorest"])),
        },
    }
    return results
