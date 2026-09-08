from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from fcv_harness.current_e2_reference import run_current_e2_from_bundles
from fcv_harness.current_e2_sparse_outcomes import (
    CurrentE2SparseOutcomeError,
    CurrentE2SparseOutcomeSpec,
    SparseOutcomeModelSpec,
    run_current_e2_sparse_outcomes,
)
from fcv_harness.reference_identity import stable_frame_sha256
from tests_current_e2_reference import CurrentE2ReferenceTests


def _suite(frame_sha: str) -> CurrentE2SparseOutcomeSpec:
    return CurrentE2SparseOutcomeSpec(
        suite_id="synthetic-r5",
        purpose="calibration_sensitivity",
        reference_id="synthetic-current-e2",
        primary_cell_id="record_present",
        required_analysis_identity_sha256="a" * 64,
        required_primary_frame_sha256=frame_sha,
        source_event_count_column="event_count",
        binary_derivation="event_count_gt_zero",
        models=(
            SparseOutcomeModelSpec(
                "ols_event_count", "VAC event count", "OLS",
                "absolute_difference", "events", "standardized_difference", "outcome_sd",
            ),
            SparseOutcomeModelSpec(
                "lpm_any_vac", "any VAC event", "LPM",
                "probability_difference", "probability", "percentage_point_difference", "percentage_points",
            ),
            SparseOutcomeModelSpec(
                "ppml_event_count", "VAC event count", "PPML",
                "incidence_rate_ratio", "ratio", "average_marginal_event_count_difference", "events",
            ),
        ),
        reading_rule="synthetic sparse-outcome acceptance",
    )


def _result_and_suite():
    spec = CurrentE2ReferenceTests.spec()
    geography, geography_dataset, treatment, outcome = CurrentE2ReferenceTests.synthetic_inputs()
    table = outcome.table.copy()
    idx = np.arange(len(table))
    baseline = np.maximum(1.0, np.floor(pd.to_numeric(table["fatalities"], errors="raise")))
    table["event_count"] = np.where(idx % 4 == 0, 0.0, baseline)
    outcome = replace(outcome, table=table)
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
        "analysis_identity_sha256": "a" * 64,
        "execution_identity_sha256": "b" * 64,
        "primary_frame_sha256": frame_sha,
        "lock": {"verified": True, "lock_id": "synthetic-lock"},
    }
    return result, _suite(frame_sha)


def test_sparse_outcomes_preserve_design_and_natural_scales() -> None:
    result, suite = _result_and_suite()
    primary = result["calibration"]["cells"][suite.primary_cell_id]
    before = primary["frame"].copy(deep=True)
    output = run_current_e2_sparse_outcomes(result, suite)
    pd.testing.assert_frame_equal(before, primary["frame"])

    summary = output["summary"]
    assert list(summary["model_id"]) == [
        "canonical_ols_fatalities",
        "ols_event_count",
        "lpm_any_vac",
        "ppml_event_count",
    ]
    assert summary["n"].nunique() == 1
    assert summary["treated"].nunique() == 1
    assert summary["control"].nunique() == 1
    assert "effect" not in summary.columns
    assert "coefficient" not in summary.columns

    lpm = output["lpm_any_vac"]
    assert np.isfinite(lpm["probability_difference"])
    assert np.isclose(lpm["percentage_point_difference"], 100 * lpm["probability_difference"])
    ppml = output["ppml_event_count"]
    assert ppml["incidence_rate_ratio"] > 0
    assert np.isfinite(ppml["average_marginal_event_count_difference"])

    binding = output["reference_binding"]
    assert binding["reingestion_performed"] is False
    assert binding["canonical_treatment_reprojection_performed"] is False
    assert binding["alternative_outcome_projection_performed"] is True
    assert binding["canonical_result_replaced"] is False
    assert binding["specification_selected_by_result"] is False
    assert binding["hurdle_model_included"] is False


def test_sparse_outcomes_fail_closed_on_canonical_frame_drift() -> None:
    result, suite = _result_and_suite()
    frame = result["calibration"]["cells"][suite.primary_cell_id]["frame"]
    frame.loc[frame.index[0], "outcome_value"] += 2.0
    try:
        run_current_e2_sparse_outcomes(result, suite)
    except CurrentE2SparseOutcomeError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("R5 must fail closed on canonical PRIMARY frame drift")


def test_production_sparse_outcome_suite_is_frozen() -> None:
    suite = CurrentE2SparseOutcomeSpec.from_json("config/current_e2_sparse_outcome_family.json")
    assert suite.required_analysis_identity_sha256 == (
        "8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a"
    )
    assert suite.required_primary_frame_sha256 == (
        "e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f"
    )
    assert suite.source_event_count_column == "event_count"
    assert suite.binary_derivation == "event_count_gt_zero"
    assert {model.model_id for model in suite.models} == {
        "ols_event_count", "lpm_any_vac", "ppml_event_count"
    }


if __name__ == "__main__":
    test_sparse_outcomes_preserve_design_and_natural_scales()
    test_sparse_outcomes_fail_closed_on_canonical_frame_drift()
    test_production_sparse_outcome_suite_is_frozen()
    print("current E2 sparse-outcome acceptance: PASS")
