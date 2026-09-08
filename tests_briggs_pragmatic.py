from __future__ import annotations

from pathlib import Path

import pandas as pd

from fcv_harness.briggs_pragmatic import (
    BriggsPragmaticError,
    load_briggs_pragmatic_spec,
    prepare_briggs_pragmatic_frame,
    run_briggs_pragmatic,
)


CONFIG = Path(__file__).resolve().parent / "config" / "briggs_2017_pragmatic_analogue.json"


def _fixture() -> pd.DataFrame:
    countries = ["BEN", "GHA", "KEN", "NGA"]
    poorest_base = [1, 2, 3, 4, 5]
    richest_base = [5, 1, 4, 2, 3]
    rows = []
    for cidx, country in enumerate(countries):
        poorest = poorest_base[cidx:] + poorest_base[:cidx]
        richest = richest_base[-cidx:] + richest_base[:-cidx] if cidx else richest_base
        for i in range(5):
            p = poorest[i] / 15.0
            r = richest[i] / 15.0
            rows.append(
                {
                    "country_iso3": country,
                    "region_id": f"{country}.{i+1}",
                    "poorest_share": p,
                    "richest_share": r,
                    "aid_value": 5.0 + 50.0 * r + 2.0 * i + cidx,
                    "aid_location_count": 1 + ((i + cidx) % 4),
                    "capital": 1 if i == cidx % 5 else 0,
                    "battles": (2 * i + cidx) % 5,
                    "area_km2": 1000 + 137 * i + 31 * cidx,
                }
            )
    return pd.DataFrame(rows)


def test_pragmatic_spec_preserves_explicit_divergences():
    spec = load_briggs_pragmatic_spec(CONFIG)
    assert len(spec.analysis_countries) == 13
    assert set(spec.raw["excluded_published_countries"]) == {"GIN", "NAM", "MWI", "TZA"}
    assert spec.raw["geography"]["provider"] == "GADM"
    assert spec.raw["geography"]["historical_entity_parity_required"] is False


def test_prepare_rejects_country_scope_drift():
    spec = load_briggs_pragmatic_spec(CONFIG)
    frame = _fixture()
    frame.loc[frame["country_iso3"].eq("BEN"), "country_iso3"] = "TZA"
    try:
        prepare_briggs_pragmatic_frame(frame, spec)
    except BriggsPragmaticError as exc:
        assert "outside declared pragmatic scope" in str(exc)
    else:
        raise AssertionError("expected country-scope failure")


def test_pragmatic_runner_reports_core_and_controlled_models():
    spec = load_briggs_pragmatic_spec(CONFIG)
    result = run_briggs_pragmatic(_fixture(), spec)
    assert result["oracle_data_used_as_input"] is False
    assert result["max_wealth_share_sum_error"] < 1e-12
    assert "core" in result["models"]
    assert "preferred_analogue" in result["models"]
    assert result["comparison_to_briggs"]["model_used"] == "preferred_analogue"
    assert "geography" in result["known_divergences"]


def test_core_model_can_run_before_controls_are_ready():
    spec = load_briggs_pragmatic_spec(CONFIG)
    frame = _fixture().drop(columns=["capital", "battles", "area_km2"])
    result = run_briggs_pragmatic(frame, spec)
    assert set(result["models"]) == {"core"}
    assert result["comparison_to_briggs"]["model_used"] == "core"
