from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


class BriggsLaneBSpecError(ValueError):
    pass


EXPECTED_COUNTRIES = {
    "BEN", "COD", "ETH", "GHA", "GIN", "KEN", "LSO", "MWI", "MLI",
    "MOZ", "NAM", "NER", "NGA", "RWA", "SLE", "TZA", "ZMB",
}
EXPECTED_ARCHIVES = {
    "AllWorldBank_IBRDIDA.csv.zip",
    "AfDB_2009_2010_AllApprovedProjects.xlsx.zip",
}


@dataclass(frozen=True)
class BriggsLaneBSpec:
    raw: dict

    @property
    def benchmark_id(self) -> str:
        return str(self.raw["benchmark_id"])

    @property
    def oracle_targets(self) -> dict:
        return dict(self.raw["oracle_targets"])


def load_briggs_lane_b_spec(path: str | Path) -> BriggsLaneBSpec:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != "briggs_2017_lane_b.v1":
        raise BriggsLaneBSpecError("unexpected Briggs Lane B schema")
    if raw.get("purpose") != "calibration":
        raise BriggsLaneBSpecError("Briggs Lane B must declare purpose=calibration")
    if raw.get("external_result", {}).get("replication_files_role") != "evaluation_oracle_only":
        raise BriggsLaneBSpecError("Briggs replication files must remain evaluation-oracle-only")

    countries = {row.get("country_iso3") for row in raw.get("country_surveys", [])}
    if countries != EXPECTED_COUNTRIES:
        raise BriggsLaneBSpecError(
            f"Briggs country roster changed: expected {sorted(EXPECTED_COUNTRIES)}, got {sorted(countries)}"
        )

    aid = raw.get("aid", {})
    if aid.get("approval_years") != [2009, 2010]:
        raise BriggsLaneBSpecError("Briggs aid approval years must remain 2009 and 2010")
    if aid.get("analysis_precision_rule") != "precision < 5":
        raise BriggsLaneBSpecError("Briggs analytical geocoding rule must remain precision < 5")
    if set(aid.get("historical_source_archives", [])) != EXPECTED_ARCHIVES:
        raise BriggsLaneBSpecError("Briggs historical donor archives changed")

    geography = raw.get("geography", {})
    if geography.get("modern_gadm_as_is_allowed") is not False:
        raise BriggsLaneBSpecError("raw modern GADM ADM1 must not be silently accepted")

    targets = raw.get("oracle_targets", {})
    if targets.get("total_regions") != 195 or targets.get("published_country_count", 17) != 17:
        # published_country_count is optional here because it lives in external_result in v1.
        pass
    if targets.get("total_included_aid_locations_or_subprojects") != 1351:
        raise BriggsLaneBSpecError("Briggs aid-location oracle count changed")
    if targets.get("world_bank_included_locations_or_subprojects") != 856:
        raise BriggsLaneBSpecError("Briggs World Bank oracle count changed")
    if targets.get("afdb_included_locations_or_subprojects") != 495:
        raise BriggsLaneBSpecError("Briggs AfDB oracle count changed")

    return BriggsLaneBSpec(raw=raw)


def build_lane_b_readiness(spec: BriggsLaneBSpec, source_preflight: dict | None = None) -> dict:
    source_preflight = source_preflight or {}
    wb = source_preflight.get("world_bank") or {}
    afdb = source_preflight.get("afdb") or {}

    checks = [
        {
            "check": "historical_world_bank_archive_fingerprinted",
            "state": "READY" if wb.get("sha256") else "BLOCKED",
        },
        {
            "check": "historical_afdb_archive_fingerprinted",
            "state": "READY" if afdb.get("sha256") else "BLOCKED",
        },
        {
            "check": "historical_region_identity_crosswalk",
            "state": "PENDING_LOCAL_SOURCE_DISCOVERY",
        },
        {
            "check": "seventeen_authoritative_dhs_hr_releases",
            "state": "PENDING_LOCAL_SOURCE_DISCOVERY",
        },
        {
            "check": "acled_2007_2008_battles_historical_region_projection",
            "state": "PENDING_IMPLEMENTATION",
        },
    ]
    return {
        "schema": "briggs_2017_lane_b_readiness.v1",
        "benchmark_id": spec.benchmark_id,
        "purpose": "calibration",
        "oracle_data_used_as_input": False,
        "checks": checks,
        "ready_for_source_semantic_mapping": all(
            c["state"] == "READY" for c in checks[:2]
        ),
        "ready_for_estimation": False,
    }
