from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pandas as pd

from fcv_harness.briggs_lane_b import (
    BriggsLaneBSpec,
    prepare_briggs_lane_b_frame,
    run_briggs_lane_b,
    write_briggs_lane_b_run,
)


def _spec() -> BriggsLaneBSpec:
    return BriggsLaneBSpec(
        reference_id="briggs-fixture",
        expected_country_count=3,
        expected_region_count=15,
        log_aid_offset=0.1,
        log_wealth_share_offset=0.001,
        table3_oracle={},
    )


def _frame() -> pd.DataFrame:
    poorest = [0.05, 0.10, 0.15, 0.25, 0.45]
    richest = [0.40, 0.25, 0.18, 0.12, 0.05]
    rows = []
    for country_index, country in enumerate(("AAA", "BBB", "CCC")):
        for region_index in range(5):
            rows.append(
                {
                    "region_id": f"{country}-{region_index + 1}",
                    "country_id": country,
                    "poorest_share": poorest[region_index],
                    "richest_share": richest[region_index],
                    "total_project_count": region_index + country_index,
                    "total_aid_value": float((region_index + 1) * (country_index + 2) * 10),
                    "battle_count": float((region_index + 2 * country_index) % 4),
                    "area": float(100 + 20 * region_index + 3 * country_index),
                    "capital": 1 if region_index == 0 else 0,
                }
            )
    return pd.DataFrame(rows)


def test_prepare_reconstructs_briggs_country_shares_and_log_offsets() -> None:
    prepared, diagnostics = prepare_briggs_lane_b_frame(_frame(), _spec())
    first = prepared.iloc[0]
    country = prepared[prepared["country_id"].eq(first["country_id"])]

    assert math.isclose(country["prop_totalproj"].sum(), 1.0)
    assert math.isclose(country["prop_totalcost"].sum(), 1.0)
    assert math.isclose(country["prop_area"].sum(), 1.0)
    assert math.isclose(first["logCost"], math.log(first["total_aid_value"] + 0.1))
    assert math.isclose(first["log_poorest"], math.log(first["poorest_share"] + 0.001))
    assert diagnostics["country_count"] == 3
    assert diagnostics["region_count"] == 15


def test_runner_uses_within_country_models_and_does_not_replace_input_with_oracle() -> None:
    result = run_briggs_lane_b(_frame(), _spec())

    assert set(result.model_summary["model_id"]) == {
        "model_1_share_value",
        "model_2_share_projects",
        "model_3_log_value",
    }
    assert set(result.coefficients["model_id"]) == set(result.model_summary["model_id"])
    assert result.diagnostics["oracle_used_as_input"] is False
    assert result.parity.empty


def test_writer_persists_results_but_not_analysis_frame() -> None:
    result = run_briggs_lane_b(_frame(), _spec())
    with tempfile.TemporaryDirectory() as tmp:
        output = write_briggs_lane_b_run(result, output_dir=tmp)
        assert (output / "table3_coefficients.csv").is_file()
        assert (output / "table3_model_summary.csv").is_file()
        assert (output / "table3_oracle_parity.csv").is_file()
        assert (output / "run_identity.json").is_file()
        assert not (output / "analysis_frame.parquet").exists()
        assert not (output / "analysis_frame.csv").exists()


def test_universe_mismatch_fails_before_estimation() -> None:
    frame = _frame().iloc[:-1].copy()
    try:
        prepare_briggs_lane_b_frame(frame, _spec())
    except ValueError as error:
        assert "requires exactly 15 regions" in str(error)
    else:
        raise AssertionError("expected universe mismatch to fail")


def test_wealth_share_denominator_mismatch_fails_closed() -> None:
    frame = _frame()
    frame.loc[0, "poorest_share"] += 0.1
    try:
        prepare_briggs_lane_b_frame(frame, _spec())
    except ValueError as error:
        assert "must each sum to one within country" in str(error)
    else:
        raise AssertionError("expected wealth-share mass mismatch to fail")


if __name__ == "__main__":
    test_prepare_reconstructs_briggs_country_shares_and_log_offsets()
    test_runner_uses_within_country_models_and_does_not_replace_input_with_oracle()
    test_writer_persists_results_but_not_analysis_frame()
    test_universe_mismatch_fails_before_estimation()
    test_wealth_share_denominator_mismatch_fails_closed()
    print("briggs lane B tests passed")
