from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .canonical import CanonicalPanelSpec, _lattice_name


def derive_country_iso3(values: pd.Series) -> pd.Series:
    """Derive ISO3-like country code from recovered GADM-style GIDs.

    The legacy archive contains at least two GADM naming forms:

    - dotted country separator, e.g. ``AGO.1.1_1``;
    - GADM-v2-style direct level suffix, e.g. ``GHA1.1_2``.

    Only the leading three letters are accepted, and they must be followed by a
    dot, a digit (the first administrative level), or end-of-string. This avoids
    treating arbitrary longer alphabetic labels as country codes.
    """
    s = values.astype("string")
    out = s.str.extract(r"^([A-Za-z]{3})(?=\.|\d|$)", expand=False)
    return out.str.upper()


def attach_country_iso3(
    panel: pd.DataFrame,
    unit_col: str = "GID",
    country_col: str = "country_iso3",
) -> pd.DataFrame:
    if unit_col not in panel.columns:
        raise KeyError(f"Panel missing unit column: {unit_col}")
    out = panel.copy()
    derived = derive_country_iso3(out[unit_col])
    if country_col in out.columns:
        existing = out[country_col].astype("string")
        conflict = existing.notna() & derived.notna() & (existing.str.upper() != derived)
        if conflict.any():
            raise ValueError(
                f"Existing {country_col} conflicts with GID-derived country on "
                f"{int(conflict.sum())} rows."
            )
        out[country_col] = existing.fillna(derived).str.upper()
    else:
        out[country_col] = derived
    return out


def build_source_outside_lattice_diagnostics(
    spec: CanonicalPanelSpec,
    loaded: Dict[str, pd.DataFrame | None],
):
    """Report source GID×TimePeriod keys excluded by the canonical lattice.

    Project sources are first reduced to distinct GID×TimePeriod keys. Nothing is
    imputed or reclassified. The output is descriptive selection/provenance evidence.
    """
    lattice_name = _lattice_name(spec)
    lattice = loaded.get(lattice_name)
    if lattice is None:
        raise ValueError("Canonical lattice is not loaded.")

    key = [spec.unit_col, spec.period_col]
    lattice_keys = lattice[key].drop_duplicates().copy()

    rows = []
    for name, contract in spec.sources.items():
        if name == lattice_name:
            continue
        df = loaded.get(name)
        if df is None:
            continue
        missing = [c for c in key if c not in df.columns]
        if missing:
            raise KeyError(f"Source {name} missing lattice comparison keys: {missing}")

        source_keys = df[key].drop_duplicates().copy()
        compared = source_keys.merge(
            lattice_keys,
            on=key,
            how="left",
            indicator=True,
            validate="one_to_one",
        )
        outside = compared.loc[compared["_merge"] == "left_only", key].copy()
        if outside.empty:
            continue
        outside.insert(0, "source", name)
        outside.insert(1, "kind", contract.kind)
        outside["country_iso3"] = derive_country_iso3(outside[spec.unit_col])
        rows.append(outside)

    columns = ["source", "kind", spec.unit_col, spec.period_col, "country_iso3"]
    source_only = (
        pd.concat(rows, ignore_index=True)[columns]
        if rows
        else pd.DataFrame(columns=columns)
    )

    if source_only.empty:
        by_country = pd.DataFrame(
            columns=["source", "kind", "country_iso3", "outside_lattice_keys", "unique_gid"]
        )
        by_period = pd.DataFrame(
            columns=["source", "kind", spec.period_col, "outside_lattice_keys", "unique_gid"]
        )
    else:
        by_country = (
            source_only.groupby(["source", "kind", "country_iso3"], dropna=False)
            .agg(
                outside_lattice_keys=(spec.unit_col, "size"),
                unique_gid=(spec.unit_col, "nunique"),
            )
            .reset_index()
            .sort_values(["source", "outside_lattice_keys"], ascending=[True, False])
        )
        by_period = (
            source_only.groupby(["source", "kind", spec.period_col], dropna=False)
            .agg(
                outside_lattice_keys=(spec.unit_col, "size"),
                unique_gid=(spec.unit_col, "nunique"),
            )
            .reset_index()
            .sort_values(["source", spec.period_col])
        )

    return {
        "source_only_keys": source_only,
        "source_outside_lattice_by_country": by_country,
        "source_outside_lattice_by_period": by_period,
    }


def write_source_outside_lattice_diagnostics(diagnostics: dict, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, table in diagnostics.items():
        table.to_csv(out / f"{name}.csv", index=False)
    return out
