from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from fcv_harness.calibration import calibration_estimate
from fcv_harness.current_e2_influence import (
    CurrentE2InfluenceError,
    CurrentE2InfluenceSpec,
    run_current_e2_influence_stability,
)
from fcv_harness.current_e2_reference import CurrentE2ReferenceSpec
from fcv_harness.reference_identity import stable_frame_sha256


def _spec() -> CurrentE2ReferenceSpec:
    return CurrentE2ReferenceSpec.from_json("config/current_geogcdf_acled_e2.json")


def _frame(spec: CurrentE2ReferenceSpec) -> pd.DataFrame:
    rows = []
    periods = ["2003-2004", "2005-2006", "2007-2008"]
    countries = ["AAA", "BBB", "CCC"]
    rng = np.random.default_rng(123)
    for ci, country in enumerate(countries):
        for ui in range(5):
            gid = f"{country}.{ui+1}"
            pre = float(ci + ui / 5.0)
            for pi, period in enumerate(periods):
                treatment = int((ui + pi + ci) % 3 == 0)
                noise = float(rng.normal(scale=0.15))
                outcome = 0.4 * pre + 0.8 * treatment + 0.1 * pi + noise
                rows.append(
                    {
                        spec.unit_col: gid,
                        spec.period_col: period,
                        spec.country_col: country,
                        "eligible": True,
                        "treatment": treatment,
                        "outcome_pre": pre + 0.05 * pi,
                        "outcome_value": outcome,
                    }
                )
    return pd.DataFrame(rows)


def _result():
    spec = _spec()
    frame = _frame(spec)
    calibration_spec = SimpleNamespace(
        unit_col=spec.unit_col,
        period_col=spec.period_col,
        country_col=spec.country_col,
    )
    estimate = calibration_estimate(frame, calibration_spec)
    assert estimate["ok"]
    frame_sha = stable_frame_sha256(frame, unit_col=spec.unit_col, period_col=spec.period_col)
    identity = {
        "analysis_identity_sha256": "a" * 64,
        "execution_identity_sha256": "b" * 64,
        "primary_frame_sha256": frame_sha,
        "lock": {"verified": True, "lock_id": "test-lock"},
    }
    result = {
        "spec": spec,
        "reference_identity": identity,
        "calibration_spec": calibration_spec,
        "calibration": {
            "cells": {
                spec.primary_cell.cell_id: {
                    "estimation_permitted": True,
                    "frame": frame,
                    "estimate": estimate,
                }
            }
        },
    }
    suite = CurrentE2InfluenceSpec(
        suite_id="test-influence",
        purpose="calibration",
        reference_id=spec.reference_id,
        primary_cell_id=spec.primary_cell.cell_id,
        required_analysis_identity_sha256="a" * 64,
        required_primary_frame_sha256=frame_sha,
        country_leave_one_out=True,
        period_leave_one_out=True,
        adm2_screening_method="cluster_score_linearization",
        top_adm2_exact_refits=3,
    )
    return result, suite


def test_influence_reuses_exact_frame_and_is_bounded() -> None:
    result, suite = _result()
    before = result["calibration"]["cells"][suite.primary_cell_id]["frame"].copy(deep=True)
    output = run_current_e2_influence_stability(result, suite)
    pd.testing.assert_frame_equal(
        before,
        result["calibration"]["cells"][suite.primary_cell_id]["frame"],
    )
    assert len(output["country_leave_one_out"]) == 3
    assert len(output["period_leave_one_out"]) == 3
    assert len(output["adm2_influence_screen"]) == 15
    assert len(output["top_adm2_exact_refits"]) == 3
    assert output["reference_binding"]["reprojection_performed"] is False
    assert output["reference_binding"]["reingestion_performed"] is False
    assert output["reference_binding"]["canonical_result_replaced"] is False
    assert "fragility_score" not in output["summary"]


def test_influence_fails_closed_on_frame_drift() -> None:
    result, suite = _result()
    frame = result["calibration"]["cells"][suite.primary_cell_id]["frame"]
    frame.loc[frame.index[0], "outcome_value"] += 1.0
    try:
        run_current_e2_influence_stability(result, suite)
    except CurrentE2InfluenceError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("R3 must fail closed on PRIMARY frame drift")


def test_production_suite_is_frozen_to_real_r0() -> None:
    suite = CurrentE2InfluenceSpec.from_json("config/current_e2_influence_stability.json")
    assert suite.required_analysis_identity_sha256 == (
        "8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a"
    )
    assert suite.required_primary_frame_sha256 == (
        "e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f"
    )
    assert suite.top_adm2_exact_refits == 20


if __name__ == "__main__":
    test_influence_reuses_exact_frame_and_is_bounded()
    test_influence_fails_closed_on_frame_drift()
    test_production_suite_is_frozen_to_real_r0()
    print("current E2 influence acceptance: PASS")
