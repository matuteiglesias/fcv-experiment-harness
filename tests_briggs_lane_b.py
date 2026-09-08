from __future__ import annotations

import json
from pathlib import Path

import pytest

from fcv_harness.briggs_lane_b import (
    BriggsLaneBSpecError,
    build_lane_b_readiness,
    load_briggs_lane_b_spec,
)


CONFIG = Path(__file__).resolve().parent / "config" / "briggs_2017_lane_b.json"


def test_lane_b_config_is_frozen_calibration_contract():
    spec = load_briggs_lane_b_spec(CONFIG)
    assert spec.benchmark_id == "briggs_2017_regional_aid_lane_b_v1"
    assert spec.oracle_targets["total_regions"] == 195
    assert spec.oracle_targets["total_included_aid_locations_or_subprojects"] == 1351


def test_readiness_never_claims_estimation_ready_from_archive_preflight_alone():
    spec = load_briggs_lane_b_spec(CONFIG)
    report = build_lane_b_readiness(
        spec,
        {
            "world_bank": {"sha256": "a" * 64},
            "afdb": {"sha256": "b" * 64},
        },
    )
    assert report["ready_for_source_semantic_mapping"] is True
    assert report["ready_for_estimation"] is False
    assert report["oracle_data_used_as_input"] is False


def test_rejects_modern_gadm_as_implicit_replacement(tmp_path):
    payload = json.loads(CONFIG.read_text())
    payload["geography"]["modern_gadm_as_is_allowed"] = True
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(payload))
    with pytest.raises(BriggsLaneBSpecError, match="modern GADM"):
        load_briggs_lane_b_spec(p)
