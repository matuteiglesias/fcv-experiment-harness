from pathlib import Path
import json
import tempfile

import pandas as pd

from fcv_harness.canonical_experiment import (
    CanonicalPanelExperimentSpec,
    prepare_experiment_measurement_frame,
    run_experiment_preflight,
)
from fcv_harness.lattice_diagnostics import (
    attach_country_iso3,
    build_source_outside_lattice_diagnostics,
)
from fcv_harness.canonical import CanonicalPanelSpec


def make_panel():
    periods = ["2001-2002", "2003-2004", "2005-2006", "2007-2008"]
    rows = []
    for gid in ["AGO.1.1_1", "KEN.1.1_1"]:
        for i, period in enumerate(periods):
            rows.append({
                "panel_id": "demo",
                "GID": gid,
                "TimePeriod": period,
                "annotation_version": "legacy_2023",
                "wbad_record_present": gid.startswith("AGO") and period in {"2003-2004", "2005-2006"},
                "wbad_amount_observed": gid.startswith("AGO") and period in {"2003-2004", "2005-2006"},
                "wbad_amount_positive": gid.startswith("AGO") and period == "2005-2006",
                "wbad_amount_zero_only": gid.startswith("AGO") and period == "2003-2004",
                "wbkg_record_present": False,
                "wbkg_amount_observed": False,
                "wbkg_amount_positive": False,
                "wbkg_amount_zero_only": False,
                "cn_record_present": False,
                "cn_amount_observed": False,
                "cn_amount_positive": False,
                "cn_amount_zero_only": False,
                "acled_record_present": (gid.startswith("AGO") and period == "2005-2006"),
                "acled_deaths_violence_against_civilians": (
                    2.0 if gid.startswith("AGO") and period == "2005-2006" else None
                ),
            })
    return pd.DataFrame(rows)


def make_spec(definition="record_present", policy="unresolved"):
    payload = {
        "experiment_id": f"demo_{definition}_{policy}",
        "panel_id": "demo",
        "treatment": {
            "source": "wbad",
            "definition": definition,
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
            "absent_record_policy": policy,
        },
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "spec.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return CanonicalPanelExperimentSpec.from_json(path)


panel = make_panel()

# Country FE source is transparent and deterministic from GID.
enriched = attach_country_iso3(panel)
assert set(enriched["country_iso3"].dropna()) == {"AGO", "KEN"}

# Record presence and amount positivity are distinct treatment definitions.
record_spec = make_spec("record_present", "unresolved")
record_frame = prepare_experiment_measurement_frame(panel, record_spec)
ago_2003 = record_frame.loc[
    (record_frame.GID == "AGO.1.1_1") & (record_frame.TimePeriod == "2003-2004")
].iloc[0]
assert ago_2003["eligible"]
assert ago_2003["treatment"] == 1
assert ago_2003["treatment_measurement_status"] == "project_record_zero_only_amount"
assert ago_2003["treatment_provenance"] == "legacy_2023:wbad.record_present"

amount_spec = make_spec("amount_positive", "unresolved")
amount_frame = prepare_experiment_measurement_frame(panel, amount_spec)
ago_2003_amount = amount_frame.loc[
    (amount_frame.GID == "AGO.1.1_1") & (amount_frame.TimePeriod == "2003-2004")
].iloc[0]
assert ago_2003_amount["treatment"] == 0
assert ago_2003_amount["treatment_source_record_present"]

# Unresolved ACLED absence policy is fail-closed: descriptive preflight is allowed,
# but estimation permission is false and absent records stay missing.
preflight = run_experiment_preflight(panel, record_spec)
assert not preflight["estimation_permitted"]
assert preflight["input_eligibility"].iloc[0]["status"] == "BLOCKED"
ken_2003 = preflight["frame"].loc[
    (preflight["frame"].GID == "KEN.1.1_1")
    & (preflight["frame"].TimePeriod == "2003-2004")
].iloc[0]
assert pd.isna(ken_2003["outcome_value"])
assert ken_2003["outcome_measurement_status"] == "absent_record_unresolved"

# Explicit observed-records-only policy changes permission but still does not zero-fill.
observed_spec = make_spec("record_present", "observed_records_only")
observed = run_experiment_preflight(panel, observed_spec)
assert observed["estimation_permitted"]
ken_obs = observed["frame"].loc[
    (observed["frame"].GID == "KEN.1.1_1")
    & (observed["frame"].TimePeriod == "2003-2004")
].iloc[0]
assert pd.isna(ken_obs["outcome_value"])
assert ken_obs["outcome_measurement_status"] == "absent_record_excluded"

# Lattice selection diagnostics preserve source keys that do not enter the panel.
canonical_payload = {
    "panel_id": "demo",
    "geography": {"scheme": "admin", "level": 2},
    "time": {"period_years": 2, "alignment_year": 2001},
    "sources": {
        "lattice": {
            "path": "unused.csv",
            "kind": "lattice",
            "grain": ["GID", "TimePeriod"],
        },
        "acled": {
            "path": "unused_acled.csv",
            "kind": "outcome",
            "grain": ["GID", "TimePeriod"],
        },
        "wbad": {
            "path": "unused_wbad.csv",
            "kind": "project",
            "grain": ["GID", "TimePeriod", "jobcat"],
            "amount_col": "Amount_USD",
            "jobcat_col": "jobcat",
        },
    },
}
with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "canonical.json"
    path.write_text(json.dumps(canonical_payload), encoding="utf-8")
    canonical_spec = CanonicalPanelSpec.from_json(path)

loaded = {
    "lattice": pd.DataFrame({
        "GID": ["AGO.1_1", "KEN.1_1"],
        "TimePeriod": ["2003-2004", "2003-2004"],
    }),
    "acled": pd.DataFrame({
        "GID": ["AGO.1_1", "UGA.1_1"],
        "TimePeriod": ["2003-2004", "2003-2004"],
        "deaths": [1, 2],
    }),
    "wbad": pd.DataFrame({
        "GID": ["AGO.1_1", "TZA.1_1"],
        "TimePeriod": ["2003-2004", "2003-2004"],
        "jobcat": [1, 1],
        "Amount_USD": [10.0, 20.0],
    }),
}
diag = build_source_outside_lattice_diagnostics(canonical_spec, loaded)
assert set(diag["source_only_keys"]["GID"]) == {"UGA.1_1", "TZA.1_1"}
assert set(diag["source_only_keys"]["country_iso3"]) == {"UGA", "TZA"}

print("CANONICAL EXPERIMENT SEMANTICS TEST PASSED")
