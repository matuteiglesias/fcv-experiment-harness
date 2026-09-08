from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd

from fcv_harness.current_e2_falsification import (
    CurrentE2FalsificationError,
    CurrentE2FalsificationSpec,
    run_current_e2_falsification_battery,
)
from fcv_harness.current_e2_reference import run_current_e2_from_bundles
from fcv_harness.reference_identity import stable_frame_sha256
from tests_current_e2_reference import CurrentE2ReferenceTests


def _extended_result():
    spec = CurrentE2ReferenceTests.spec()
    geography, geography_dataset, treatment, outcome = CurrentE2ReferenceTests.synthetic_inputs()

    geo_uids = sorted(treatment.table["geo_uid"].unique().tolist())
    future_rows = []
    for index, geo_uid in enumerate(geo_uids):
        treated = int(index % 2 == 0)
        future_rows.append(
            {
                "geo_uid": geo_uid,
                "period_id": "2009-2010",
                "project_count": treated,
                "positive_reported_amount_project_count": treated,
            }
        )
    treatment = replace(
        treatment,
        table=pd.concat([treatment.table, pd.DataFrame(future_rows)], ignore_index=True),
    )

    deep_rows = []
    for index, geo_uid in enumerate(geo_uids):
        deep_rows.append(
            {
                "geo_uid": geo_uid,
                "period_id": "1999-2000",
                "native_event_type": "Violence against civilians",
                "fatalities": 1.0 + 0.1 * index,
            }
        )
    outcome_coverage = outcome.coverage.model_copy(update={"temporal_start": date(1999, 1, 1)})
    outcome_measurement = outcome.measurement.model_copy(update={"coverage": outcome_coverage})
    outcome = replace(
        outcome,
        table=pd.concat([outcome.table, pd.DataFrame(deep_rows)], ignore_index=True),
        coverage=outcome_coverage,
        measurement=outcome_measurement,
    )

    result = run_current_e2_from_bundles(
        geography,
        geography_dataset,
        treatment,
        outcome,
        spec,
        run_observability=False,
    )
    primary = result["calibration"]["cells"][spec.primary_cell.cell_id]
    assert primary["estimation_permitted"]
    frame_sha = stable_frame_sha256(primary["frame"], unit_col=spec.unit_col, period_col=spec.period_col)
    result["reference_identity"] = {
        "analysis_identity_sha256": "c" * 64,
        "execution_identity_sha256": "d" * 64,
        "primary_frame_sha256": frame_sha,
        "lock": {"verified": True, "lock_id": "test-lock"},
    }
    suite = CurrentE2FalsificationSpec(
        suite_id="test-falsification",
        purpose="calibration",
        reference_id=spec.reference_id,
        primary_cell_id=spec.primary_cell.cell_id,
        required_analysis_identity_sha256="c" * 64,
        required_primary_frame_sha256=frame_sha,
        deep_pre_timing_offset=-2,
        future_treatment_timing_offset=1,
        current_outcome_timing_offset=0,
        permutation_policy="within_country_complete_treatment_history",
        permutation_repetitions=99,
        permutation_root_seed=12345,
    )
    return result, suite


def test_falsification_uses_governed_timing_and_structured_null() -> None:
    result, suite = _extended_result()
    primary = result["calibration"]["cells"][suite.primary_cell_id]
    before = primary["frame"].copy(deep=True)
    output = run_current_e2_falsification_battery(result, suite)
    pd.testing.assert_frame_equal(before, primary["frame"])
    assert output["existing_tminus1_placebo"]["ok"]
    assert output["deep_tminus2_placebo"]["ok"]
    assert output["future_treatment_placebo"]["ok"]
    assert output["permutation_null"]["ok"]
    assert output["permutation_null"]["repetitions"] == 99
    assert output["projection_reports"]["deep_pre"].timing_offset == -2
    assert output["projection_reports"]["current_outcome"].timing_offset == 0
    assert output["projection_reports"]["future_treatment"].timing_offset == 1
    assert output["reference_binding"]["reingestion_performed"] is False
    assert output["reference_binding"]["canonical_frame_mutated"] is False
    assert output["reference_binding"]["canonical_result_replaced"] is False


def test_falsification_fails_closed_on_frame_drift() -> None:
    result, suite = _extended_result()
    frame = result["calibration"]["cells"][suite.primary_cell_id]["frame"]
    frame.loc[frame.index[0], "outcome_value"] += 1.0
    try:
        run_current_e2_falsification_battery(result, suite)
    except CurrentE2FalsificationError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("R4 must fail closed on PRIMARY frame drift")


def test_production_falsification_suite_is_frozen_to_real_r0() -> None:
    suite = CurrentE2FalsificationSpec.from_json("config/current_e2_falsification_battery.json")
    assert suite.required_analysis_identity_sha256 == (
        "8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a"
    )
    assert suite.required_primary_frame_sha256 == (
        "e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f"
    )
    assert suite.deep_pre_timing_offset == -2
    assert suite.future_treatment_timing_offset == 1
    assert suite.permutation_repetitions == 1000


if __name__ == "__main__":
    test_falsification_uses_governed_timing_and_structured_null()
    test_falsification_fails_closed_on_frame_drift()
    test_production_falsification_suite_is_frozen_to_real_r0()
    print("current E2 falsification acceptance: PASS")
