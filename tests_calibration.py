import numpy as np
import pandas as pd

from fcv_harness.analysis_surface import (
    AnalysisSurfaceSpec,
    AnalysisUniverseSpec,
    AreaPeriodOutcomeResolutionSpec,
)
from fcv_harness.calibration import (
    CalibrationCellSpec,
    CalibrationMatrixSpec,
    CalibrationThresholds,
    run_calibration_cell,
)


periods = [
    "2001-2002", "2003-2004", "2005-2006", "2007-2008",
    "2009-2010", "2011-2012", "2013-2014", "2015-2016",
]
rows = []
rng = np.random.default_rng(7)
for i in range(40):
    country = "KEN" if i < 20 else "UGA"
    gid = f"{country}.1.{i + 1}_1"
    treated_unit = i % 2 == 0
    y_prev = float(rng.poisson(1.0))
    for period in periods:
        in_window = period in periods[1:7]
        record = bool(treated_unit and in_window)
        amount_positive = bool(record and period != "2013-2014")
        # Sparse but non-degenerate resolved outcome with a known synthetic-looking relation.
        y = float(rng.poisson(0.5 + 0.35 * treated_unit + 0.15 * y_prev))
        rows.append({
            "panel_id": "demo",
            "GID": gid,
            "TimePeriod": period,
            "country_iso3": country,
            "annotation_version": "legacy_2023",
            "wbad_record_present": record,
            "wbad_amount_observed": record,
            "wbad_amount_positive": amount_positive,
            "wbad_amount_zero_only": bool(record and not amount_positive),
            "wbkg_record_present": record,
            "wbkg_amount_observed": record,
            "wbkg_amount_positive": amount_positive,
            "wbkg_amount_zero_only": bool(record and not amount_positive),
            "cn_record_present": False,
            "cn_amount_observed": False,
            "cn_amount_positive": False,
            "cn_amount_zero_only": False,
            "acled_record_present": True,
            "acled_deaths_violence_against_civilians": y,
            "acled_value_resolved": y,
        })
        y_prev = y
panel = pd.DataFrame(rows)

surface_spec = AnalysisSurfaceSpec(
    surface_id="demo_surface",
    canonical_manifest="unused.json",
    universe=AnalysisUniverseSpec(mode="canonical_lattice", authority="test"),
    outcome=AreaPeriodOutcomeResolutionSpec(
        source="acled",
        column="acled_deaths_violence_against_civilians",
        policy="zero_within_verified_coverage",
        verified_period_start="2001-2002",
        verified_period_end="2015-2016",
        verified_geography_scope="analysis_universe",
        coverage_basis="test",
    ),
)

thresholds = CalibrationThresholds(
    min_treated=10,
    min_control=10,
    min_mixed_periods=2,
    plausible_effect_sd=1.0,
    signal_draws=4,
    signal_target_green=0.50,
    signal_target_red=0.0,
    seed=11,
)
matrix_spec = CalibrationMatrixSpec(
    matrix_id="demo_matrix",
    surface_manifest="unused.json",
    treatment_period_start="2003-2004",
    treatment_period_end="2013-2014",
    annotation_version="legacy_2023",
    cells=[],
    thresholds=thresholds,
)
surface_gates = pd.DataFrame([
    {"gate": "U0_UNIVERSE_DECLARED", "status": "GREEN"},
    {"gate": "U2_COUNTRY_IDENTITY", "status": "GREEN"},
    {"gate": "A0_ACLED_POLICY_EXPLICIT", "status": "GREEN"},
    {"gate": "A1_ACLED_RESOLUTION_COMPLETENESS", "status": "GREEN"},
])
source_only = pd.DataFrame(columns=["source", "GID", "TimePeriod"])

record = run_calibration_cell(
    panel,
    matrix_spec,
    surface_spec,
    surface_gates,
    source_only,
    "demo",
    CalibrationCellSpec("wbad_record", "wbad", "record_present", "PRIMARY"),
)
assert record["estimate"]["ok"]
assert record["support_by_period"].shape[0] == 6
assert record["gates"].set_index("gate").loc["E2_WITHIN_PERIOD_SUPPORT", "status"] == "GREEN"
assert "outcome_pre ~ treatment" in record["placebo"]["formula"]
assert "outcome_pre +" not in record["placebo"]["formula"]

stress = run_calibration_cell(
    panel,
    matrix_spec,
    surface_spec,
    surface_gates,
    source_only,
    "demo",
    CalibrationCellSpec("wbad_amount", "wbad", "amount_positive", "STRESS"),
    seed_offset=100,
)
# The declared last period remains in the design with zero treated units; it is not dropped.
last = stress["support_by_period"].loc[
    stress["support_by_period"]["TimePeriod"] == "2013-2014"
].iloc[0]
assert last["treated"] == 0
assert stress["support_by_period"].shape[0] == 6
assert stress["gates"].set_index("gate").loc["E2_WITHIN_PERIOD_SUPPORT", "status"] == "YELLOW"
assert stress["estimate"]["ok"]

# A genuinely unsupported treatment is blocked before a real coefficient.
blocked_panel = panel.copy()
blocked_panel["cn_record_present"] = False
blocked = run_calibration_cell(
    blocked_panel,
    matrix_spec,
    surface_spec,
    surface_gates,
    source_only,
    "demo",
    CalibrationCellSpec("cn_none", "cn", "record_present", "STRESS"),
    seed_offset=200,
)
assert not blocked["estimate"]["ok"]
assert "E1_TREATMENT_SUPPORT" in blocked["hard_red_gates"]

print("WB ACLED CALIBRATION TEST PASSED")
