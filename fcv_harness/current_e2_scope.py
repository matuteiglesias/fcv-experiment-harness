from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .current_e2_reference import (
    CurrentE2ArtifactPaths,
    CurrentE2ReferenceSpec,
    load_current_geography,
    run_current_e2_from_bundles,
    write_current_e2_reference_outputs,
)
from .empirical_input import (
    EmpiricalMeasurementBundle,
    load_empirical_measurement,
    require_same_geography,
    require_same_period_scheme,
)


def _declared_country_scope(
    bundle: EmpiricalMeasurementBundle,
    *,
    parameter: str,
    label: str,
) -> tuple[str, ...]:
    raw = bundle.measurement.parameters.get(parameter)
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(
            f"{label} measurement must declare non-empty {parameter!r} for current E2 scope"
        )
    countries = tuple(sorted({str(value).strip().upper() for value in raw if str(value).strip()}))
    if not countries:
        raise ValueError(f"{label} measurement declares an empty country scope")
    return countries


def scope_current_geography(
    geography: pd.DataFrame,
    treatment_bundle: EmpiricalMeasurementBundle,
    outcome_bundle: EmpiricalMeasurementBundle,
    spec: CurrentE2ReferenceSpec,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Restrict the current reference lattice to contract-declared common country support.

    GeoGCDF structural zeros are licensed only for ``covered_country_iso3`` in the
    treatment MeasurementContract. The reference panel must therefore not extend the
    dense treatment surface to additional GADM countries merely because those units are
    present in the governed geography. The certified ACLED outcome must cover every
    treatment country as an independent fail-closed compatibility check.
    """
    if spec.geography_country_col not in geography.columns:
        raise ValueError(
            f"governed geography is missing country column {spec.geography_country_col!r}"
        )

    treatment_countries = _declared_country_scope(
        treatment_bundle,
        parameter="covered_country_iso3",
        label="treatment",
    )
    outcome_countries = _declared_country_scope(
        outcome_bundle,
        parameter="certified_country_iso3",
        label="outcome",
    )

    geo_country = geography[spec.geography_country_col].astype("string").str.upper()
    governed_countries = tuple(sorted(geo_country.dropna().astype(str).unique().tolist()))

    missing_geography = sorted(set(treatment_countries) - set(governed_countries))
    if missing_geography:
        raise ValueError(
            "treatment country coverage contains countries absent from governed geography: "
            + ", ".join(missing_geography)
        )

    missing_outcome = sorted(set(treatment_countries) - set(outcome_countries))
    if missing_outcome:
        raise ValueError(
            "certified outcome does not cover all treatment countries: "
            + ", ".join(missing_outcome)
        )

    scoped = geography.loc[geo_country.isin(treatment_countries)].copy()
    if scoped.empty:
        raise ValueError("current E2 has no governed geographies inside treatment coverage")

    scoped_country = scoped[spec.geography_country_col].astype("string").str.upper()
    analysis_countries = tuple(sorted(scoped_country.dropna().astype(str).unique().tolist()))
    if analysis_countries != treatment_countries:
        raise ValueError("scoped geography does not exactly reproduce treatment country coverage")

    excluded_countries = tuple(sorted(set(governed_countries) - set(analysis_countries)))
    scope = {
        "scope_policy": "treatment_measurement_covered_country_iso3",
        "treatment_covered_country_iso3": list(treatment_countries),
        "outcome_certified_country_iso3": list(outcome_countries),
        "governed_geography_country_iso3": list(governed_countries),
        "analysis_country_iso3": list(analysis_countries),
        "excluded_governed_country_iso3": list(excluded_countries),
        "governed_geography_rows": int(len(geography)),
        "analysis_geography_rows": int(len(scoped)),
    }
    return scoped, scope


def _load_bundle(
    *,
    data_path: Path,
    measurement_contract_path: Path,
    coverage_contract_path: Path,
    manifest_path: Path,
    dataset_id: str,
    expected_measure_id: str,
    spec: CurrentE2ReferenceSpec,
) -> EmpiricalMeasurementBundle:
    bundle = load_empirical_measurement(
        data_path=data_path,
        measurement_contract_path=measurement_contract_path,
        coverage_contract_path=coverage_contract_path,
        run_manifest_path=manifest_path,
        dataset_id=dataset_id,
    )
    if bundle.measurement.measure_id != expected_measure_id:
        raise ValueError(
            f"expected measure_id {expected_measure_id!r}, got {bundle.measurement.measure_id!r}"
        )
    require_same_geography(bundle.dataset, spec.geography)
    require_same_period_scheme(bundle.dataset, spec.period_scheme)
    return bundle


def run_scoped_current_e2_reference(
    spec: CurrentE2ReferenceSpec,
    paths: CurrentE2ArtifactPaths,
    *,
    run_observability: bool = False,
) -> dict[str, Any]:
    geography_dataset, geography = load_current_geography(
        spec,
        data_path=paths.geography_data_path,
        manifest_path=paths.geography_manifest_path,
        dataset_id=paths.geography_dataset_id,
    )
    treatment = _load_bundle(
        data_path=paths.treatment_data_path,
        measurement_contract_path=paths.treatment_measurement_contract_path,
        coverage_contract_path=paths.treatment_coverage_contract_path,
        manifest_path=paths.treatment_manifest_path,
        dataset_id=paths.treatment_dataset_id,
        expected_measure_id=spec.treatment_measure_id,
        spec=spec,
    )
    outcome = _load_bundle(
        data_path=paths.outcome_data_path,
        measurement_contract_path=paths.outcome_measurement_contract_path,
        coverage_contract_path=paths.outcome_coverage_contract_path,
        manifest_path=paths.outcome_manifest_path,
        dataset_id=paths.outcome_dataset_id,
        expected_measure_id=spec.outcome_measure_id,
        spec=spec,
    )
    scoped_geography, country_scope = scope_current_geography(
        geography,
        treatment,
        outcome,
        spec,
    )
    result = run_current_e2_from_bundles(
        scoped_geography,
        geography_dataset,
        treatment,
        outcome,
        spec,
        run_observability=run_observability,
    )
    result["country_scope"] = country_scope
    return result


def write_scoped_current_e2_reference_outputs(
    result: dict[str, Any],
    out_dir: str | Path,
) -> Path:
    out = write_current_e2_reference_outputs(result, out_dir)
    run_path = out / "reference_run.json"
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["country_scope"] = result["country_scope"]
    run_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


__all__ = [
    "run_scoped_current_e2_reference",
    "scope_current_geography",
    "write_scoped_current_e2_reference_outputs",
]
