from pathlib import Path
import json
import tempfile

import pandas as pd

from fcv_harness.analysis_surface import (
    AnalysisSurfaceSpec,
    AnalysisUniverseSpec,
    AreaPeriodOutcomeResolutionSpec,
    attach_resolved_outcome,
    build_acled_measurement_audit,
    build_analysis_universe,
    run_analysis_surface_checkpoint,
)
from fcv_harness.canonical import CanonicalPanelSpec
from fcv_harness.canonical_experiment import (
    CanonicalPanelExperimentSpec,
    run_experiment_preflight,
)


canonical_payload = {
    "panel_id": "demo",
    "geography": {"scheme": "admin", "level": 2},
    "time": {"period_years": 2, "alignment_year": 2001},
    "annotation_version": "legacy_2023",
    "sources": {
        "lattice": {
            "path": "unused_lattice.csv",
            "kind": "lattice",
            "grain": ["GID", "TimePeriod"],
            "prefix": "dhsgc",
        },
        "acled": {
            "path": "unused_acled.csv",
            "kind": "outcome",
            "grain": ["GID", "TimePeriod"],
            "prefix": "acled",
        },
        "wbad": {
            "path": "unused_wbad.csv",
            "kind": "project",
            "grain": ["GID", "TimePeriod", "jobcat"],
            "prefix": "wbad",
            "amount_col": "Amount_USD",
            "jobcat_col": "jobcat",
        },
    },
}

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "canonical.json"
    path.write_text(json.dumps(canonical_payload), encoding="utf-8")
    canonical_spec = CanonicalPanelSpec.from_json(path)

periods = ["2001-2002", "2003-2004", "2005-2006", "2007-2008"]
lattice_rows = []
for gid in ["AGO.1.1_1", "KEN.1.1_1"]:
    for i, period in enumerate(periods):
        lattice_rows.append(
            {
                "GID": gid,
                "TimePeriod": period,
                "rain": float(i + 1),
            }
        )

loaded = {
    "lattice": pd.DataFrame(lattice_rows),
    "acled": pd.DataFrame(
        [
            {
                "GID": "AGO.1.1_1",
                "TimePeriod": "2005-2006",
                "deaths_Violence against civilians": 2.0,
            },
            {
                "GID": "AGO.1.1_1",
                "TimePeriod": "2007-2008",
                "deaths_Violence against civilians": 0.0,
            },
            {
                "GID": "UGA.1.1_1",
                "TimePeriod": "2005-2006",
                "deaths_Violence against civilians": 4.0,
            },
        ]
    ),
    "wbad": pd.DataFrame(
        [
            {
                "GID": "AGO.1.1_1",
                "TimePeriod": "2003-2004",
                "jobcat": 1,
                "Amount_USD": 10.0,
            },
            {
                "GID": "UGA.1.1_1",
                "TimePeriod": "2003-2004",
                "jobcat": 1,
                "Amount_USD": 20.0,
            },
        ]
    ),
}

universe_spec = AnalysisUniverseSpec(
    mode="canonical_lattice",
    authority="dhsgc_restricted_test",
)
panel = build_analysis_universe(
    canonical_spec,
    loaded,
    universe_spec,
)
assert len(panel) == 8
assert panel["dhsgc_available"].all()
assert set(panel["country_iso3"]) == {"AGO", "KEN"}
assert "UGA.1.1_1" not in set(panel["GID"])
assert panel.duplicated(["GID", "TimePeriod"]).sum() == 0

outcome_spec = AreaPeriodOutcomeResolutionSpec(
    source="acled",
    column="acled_deaths_violence_against_civilians",
    policy="zero_within_verified_coverage",
    verified_period_start="2003-2004",
    verified_period_end="2007-2008",
    verified_geography_scope="analysis_universe",
    coverage_basis="legacy_test_zero_fill",
)
surface_spec = AnalysisSurfaceSpec(
    surface_id="demo_surface",
    canonical_manifest="unused.json",
    universe=universe_spec,
    outcome=outcome_spec,
)

resolved = attach_resolved_outcome(panel, surface_spec)
ago_positive = resolved.loc[
    (resolved.GID == "AGO.1.1_1")
    & (resolved.TimePeriod == "2005-2006")
].iloc[0]
assert ago_positive["acled_value_raw"] == 2.0
assert ago_positive["acled_value_resolved"] == 2.0
assert ago_positive["acled_resolution_status"] == "observed_record_positive"

ago_zero = resolved.loc[
    (resolved.GID == "AGO.1.1_1")
    & (resolved.TimePeriod == "2007-2008")
].iloc[0]
assert ago_zero["acled_value_raw"] == 0.0
assert ago_zero["acled_resolution_status"] == "observed_record_zero"

ken_structural = resolved.loc[
    (resolved.GID == "KEN.1.1_1")
    & (resolved.TimePeriod == "2005-2006")
].iloc[0]
assert pd.isna(ken_structural["acled_value_raw"])
assert ken_structural["acled_value_resolved"] == 0.0
assert (
    ken_structural["acled_resolution_status"]
    == "structural_zero_from_absent_record"
)

outside = resolved.loc[
    (resolved.GID == "KEN.1.1_1")
    & (resolved.TimePeriod == "2001-2002")
].iloc[0]
assert pd.isna(outside["acled_value_resolved"])
assert outside["acled_resolution_status"] == "outside_verified_coverage"

audit = build_acled_measurement_audit(resolved)
overall = audit["acled_measurement_audit_overall"].iloc[0]
assert overall["observed_acled_records"] == 2
assert overall["observed_positive_vac"] == 1
assert overall["observed_zero_vac"] == 1
assert overall["structural_zeros_added"] == 4
assert overall["outside_coverage_rows"] == 2

# The full E1 checkpoint keeps source-only UGA evidence visible rather than
# redefining the production universe as a union of observed sources.
checkpoint = run_analysis_surface_checkpoint(
    surface_spec,
    canonical_spec,
    loaded,
)
source_only = checkpoint["source_outside"]["source_only_keys"]
assert set(source_only["GID"]) == {"UGA.1.1_1"}
assert checkpoint["gates"].set_index("gate").loc[
    "U1_SOURCE_ATTRITION_QUANTIFIED", "status"
] == "YELLOW"
assert checkpoint["gates"].set_index("gate").loc[
    "A0_ACLED_POLICY_EXPLICIT", "status"
] == "GREEN"

# External-spine mode is supported for the later point at which a full ADM2
# geography spine is recovered. It expands the universe without requiring
# DHSGC covariates to exist for every GID.
with tempfile.TemporaryDirectory() as td:
    spine = Path(td) / "spine.csv"
    pd.DataFrame({"GID": ["AGO.1.1_1", "KEN.1.1_1", "UGA.1.1_1"]}).to_csv(
        spine, index=False
    )
    external = AnalysisUniverseSpec(
        mode="external_gid_spine",
        authority="synthetic_full_spine",
        external_spine_path=str(spine),
    )
    expanded = build_analysis_universe(
        canonical_spec,
        loaded,
        external,
    )

assert len(expanded) == 12
uga = expanded.loc[expanded.GID == "UGA.1.1_1"]
assert not uga["dhsgc_available"].any()
assert uga["acled_record_present"].sum() == 1
assert uga["wbad_record_present"].sum() == 1

# Resolved E0 is permitted, but still remains a preflight rather than an estimate.
experiment_payload = {
    "experiment_id": "resolved_demo",
    "panel_id": "demo",
    "treatment": {
        "source": "wbad",
        "definition": "record_present",
        "annotation_version": "legacy_2023",
    },
    "eligibility": {
        "treatment_period_start": "2003-2004",
        "treatment_period_end": "2005-2006",
    },
    "outcome": {
        "source": "acled",
        "column": "acled_deaths_violence_against_civilians",
        "timing": "next_period",
        "absent_record_policy": "zero_within_verified_coverage",
        "verified_period_start": "2003-2004",
        "verified_period_end": "2007-2008",
    },
}
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "experiment.json"
    path.write_text(json.dumps(experiment_payload), encoding="utf-8")
    experiment_spec = CanonicalPanelExperimentSpec.from_json(path)

preflight = run_experiment_preflight(
    panel,
    experiment_spec,
    source_only_keys=checkpoint["source_outside"]["source_only_keys"],
)
assert preflight["estimation_permitted"]
assert preflight["input_eligibility"].iloc[0]["status"] != "BLOCKED"

print("ANALYSIS UNIVERSE / ACLED RESOLUTION TEST PASSED")
