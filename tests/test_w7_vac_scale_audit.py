import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.w7_vac_scale_audit import audit_frame, encode_result


PERIODS = [f"{2001 + 2 * i}-{2002 + 2 * i}" for i in range(7)]


def fixture() -> pd.DataFrame:
    rows = []
    for period_i, period in enumerate(PERIODS):
        for geo_i, country in enumerate(("AAA", "BBB")):
            cn = int((geo_i + period_i) % 3 == 0)
            wb = int((geo_i + period_i) % 3 == 1)
            events = int((geo_i + period_i) % 4)
            rows.append({"geo_uid": f"g{geo_i}", "country_iso3": country, "period_id": period,
                         "cn_project_count": cn, "wb_project_count": wb,
                         "any_vac_next": int(events > 0), "vac_events_next": events,
                         "vac_fatalities_next": events * 2, "vac_events_prior": geo_i})
    return pd.DataFrame(rows)


def test_partition_zeros_and_metrics_are_aggregate_only(tmp_path):
    result = audit_frame(fixture(), "a" * 64)
    arms = result["donor_cells_unadjusted"]
    assert sum(item["cells"] for item in arms.values()) == 14
    assert {k: v["cells"] for k, v in arms.items()} == {"cn_exclusive": 5, "wb_exclusive": 5, "both": 0, "neither": 4}
    assert result["scale"]["periods"] == 7
    assert result["overall_vac"]["event_count_sum"] == 21
    assert "NOT per capita" in " ".join(result["measurement_limits"])


@pytest.mark.parametrize("column,value,message", [
    ("cn_project_count", -1, "negative"),
    ("vac_events_next", 1, "inconsistent"),
    ("country_iso3", "bad", "invalid"),
])
def test_invalid_inputs_fail_closed(tmp_path, column, value, message):
    frame = fixture()
    if column == "vac_events_next":
        frame.loc[0, "vac_events_next"] = value
    else:
        frame.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        audit_frame(frame, "b" * 64)


def test_deterministic_cli_json(tmp_path):
    result = audit_frame(fixture(), "c" * 64)
    first = encode_result(result)
    second = encode_result(result)
    assert first == second
    assert json.loads(first)["status"] == "PASS"
