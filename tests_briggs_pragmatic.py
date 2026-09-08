from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fcv_harness.briggs_pragmatic import (
    BriggsPragmaticError,
    load_briggs_pragmatic_spec,
    prepare_briggs_pragmatic_frame,
    run_briggs_pragmatic,
)


CONFIG = Path(__file__).resolve().parent / "config" / "briggs_2017_pragmatic_analogue.json"


def _fixture() -> pd.DataFrame:
    rows = []
    for country, shift in [("BEN", 0.0), ("GHA", 0.03), ("KEN", -0.02)]:
        for i in range(4):
            poorest = 0.05 + 0.04 * i + shift
            richest = 0.22 - 0.04 * i - shift
            rows.append(
                {
                    "country_iso3": country,
                    "region_id": f"{country}.{i+1}",
                    "poorest_share": max(poorest, 0.001),
                    "richest_share": max(richest, 0.001),
                    "aid_value": 10.0 + 20.0 * max(richest, 0.001) + i,
                    "aid_location_count": 1 + (i % 3),
                    "capital": 1 if i == 0 else 0,
                    "battles": i,
                    "area_km2": 1000 + 100 * i,
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
    frame.loc[0, "country_iso3"] = "TZA"
    with pytest.raises(BriggsPragmaticError, match="outside declared pragmatic scope"):
        prepare_briggs_pragmatic_frame(frame, spec)


def test_pragmatic_runner_reports_core_and_controlled_models():
    spec = load_briggs_pragmatic_spec(CONFIG)
    result = run_briggs_pragmatic(_fixture(), spec)
    assert result["oracle_data_used_as_input"] is False
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
