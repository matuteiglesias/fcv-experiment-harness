from pathlib import Path
import json
import tempfile

import pandas as pd

from fcv_harness.canonical import (
    CanonicalPanelSpec,
    normalize_project_source,
    run_canonical_checkpoint,
    write_checkpoint_outputs,
)


def _write_fixture(root: Path):
    periods = ["2001-2002", "2003-2004", "2005-2006"]
    lattice = pd.DataFrame(
        [
            {
                "GID": gid,
                "TimePeriod": period,
                "Rainfall": 100 + i,
                "Slope": 1.0,
            }
            for gid in ["AAA.1", "BBB.1"]
            for i, period in enumerate(periods)
        ]
    )
    acled = pd.DataFrame(
        [
            {"GID": "AAA.1", "TimePeriod": "2001-2002", "deaths_Violence against civilians": 0},
            {"GID": "AAA.1", "TimePeriod": "2003-2004", "deaths_Violence against civilians": 2},
            {"GID": "BBB.1", "TimePeriod": "2003-2004", "deaths_Violence against civilians": 0},
        ]
    )
    afb = pd.DataFrame(
        [
            {"GID": "AAA.1", "TimePeriod": "2003-2004", "round": 4.0, "trust_police": 2.5}
        ]
    )
    wbad = pd.DataFrame(
        [
            {"GID": "AAA.1", "TimePeriod": "2001-2002", "jobcat": 0, "Amount_USD": 0},
            {"GID": "AAA.1", "TimePeriod": "2001-2002", "jobcat": 1, "Amount_USD": 100},
            {"GID": "BBB.1", "TimePeriod": "2003-2004", "jobcat": 3, "Amount_USD": 0},
        ]
    )
    wbkg = pd.DataFrame(
        [
            {"GID": "AAA.1", "TimePeriod": "2001-2002", "jobcat": 1, "Amount_USD": 80},
            {"GID": "BBB.1", "TimePeriod": "2005-2006", "jobcat": 2, "Amount_USD": 50},
        ]
    )
    cn = pd.DataFrame(
        [
            {"GID": "BBB.1", "TimePeriod": "2003-2004", "jobcat": 0, "Amount_USD": 0}
        ]
    )

    for name, df in {
        "lattice": lattice,
        "acled": acled,
        "afb": afb,
        "wbad": wbad,
        "wbkg": wbkg,
        "cn": cn,
    }.items():
        df.to_csv(root / f"{name}.csv", index=False)

    manifest = {
        "panel_id": "synthetic_a2_T2_y2001",
        "geography": {"scheme": "admin", "level": 2},
        "time": {"period_years": 2, "alignment_year": 2001},
        "annotation_version": "legacy_2023",
        "sources": {
            "lattice": {"path": "lattice.csv", "kind": "lattice", "grain": ["GID", "TimePeriod"], "prefix": "dhsgc"},
            "acled": {"path": "acled.csv", "kind": "outcome", "grain": ["GID", "TimePeriod"], "prefix": "acled"},
            "afb": {"path": "afb.csv", "kind": "survey", "grain": ["GID", "TimePeriod"], "prefix": "afb"},
            "wbad": {"path": "wbad.csv", "kind": "project", "grain": ["GID", "TimePeriod", "jobcat"], "prefix": "wbad", "amount_col": "Amount_USD", "jobcat_col": "jobcat"},
            "wbkg": {"path": "wbkg.csv", "kind": "project", "grain": ["GID", "TimePeriod", "jobcat"], "prefix": "wbkg", "amount_col": "Amount_USD", "jobcat_col": "jobcat"},
            "cn": {"path": "cn.csv", "kind": "project", "grain": ["GID", "TimePeriod", "jobcat"], "prefix": "cn", "amount_col": "Amount_USD", "jobcat_col": "jobcat"}
        }
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return wbad


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    wbad_fixture = _write_fixture(root)
    spec = CanonicalPanelSpec.from_json(root / "manifest.json")
    result = run_canonical_checkpoint(spec, base_dir=root)
    panel = result["panel"]

    assert len(panel) == 6
    assert not panel.duplicated(["GID", "TimePeriod"]).any()

    a = panel.loc[
        (panel.GID == "AAA.1") & (panel.TimePeriod == "2001-2002")
    ].iloc[0]
    assert bool(a["wbad_record_present"])
    assert bool(a["wbad_amount_positive"])
    assert a["wbad_amount_usd"] == 100
    assert bool(a["wbad_jobcat_0_present"])
    assert bool(a["wbad_jobcat_1_present"])

    b = panel.loc[
        (panel.GID == "BBB.1") & (panel.TimePeriod == "2003-2004")
    ].iloc[0]
    assert bool(b["wbad_record_present"])
    assert not bool(b["wbad_amount_positive"])
    assert bool(b["wbad_amount_zero_only"])

    missing_acled = panel.loc[
        (panel.GID == "BBB.1") & (panel.TimePeriod == "2005-2006")
    ].iloc[0]
    assert not bool(missing_acled["acled_record_present"])
    assert pd.isna(missing_acled["acled_deaths_violence_against_civilians"])

    expected_gates = {
        "C0_LATTICE_INTEGRITY",
        "C1_SOURCE_KEY_INTEGRITY",
        "C2_SOURCE_COVERAGE_REPORTED",
        "C3_LEGACY_EXPOSURE_STRUCTURE",
        "C4_ACLED_MEASUREMENT_SEMANTICS",
        "C5_WB_SOURCE_COMPARISON",
        "C6_COVARIATE_PROFILE",
    }
    assert set(result["gates"].gate) == expected_gates

    out = write_checkpoint_outputs(result, root / "out")
    assert (out / "canonical_panel_card.md").exists()
    assert (out / "canonical_panel.csv.gz").exists()
    assert (out / "source_inventory.csv").exists()

    duplicate = pd.concat([wbad_fixture, wbad_fixture.iloc[[0]]], ignore_index=True)
    try:
        normalize_project_source(duplicate, spec.sources["wbad"], spec)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate project grain should fail loudly")

print("CANONICAL CHECKPOINT TEST PASSED")
