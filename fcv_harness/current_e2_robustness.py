from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .current_e2_reference import (
    CurrentE2ReferenceSpec,
    run_current_e2_from_bundles,
    write_current_e2_reference_outputs,
)
from .fully_contracted_calibration import FullyContractedTreatmentCellSpec


@dataclass(frozen=True)
class CurrentE2RobustnessVariant:
    """One predeclared one-dimension-at-a-time sensitivity variant."""

    variant_id: str
    dimension: str
    description: str
    treatment_value_column: str | None = None
    treatment_threshold: float | None = None
    treatment_period_start: str | None = None
    treatment_period_end: str | None = None
    outcome_value_column: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CurrentE2RobustnessVariant":
        return cls(
            variant_id=str(payload["variant_id"]),
            dimension=str(payload["dimension"]),
            description=str(payload["description"]),
            treatment_value_column=(
                str(payload["treatment_value_column"])
                if payload.get("treatment_value_column") is not None
                else None
            ),
            treatment_threshold=(
                float(payload["treatment_threshold"])
                if payload.get("treatment_threshold") is not None
                else None
            ),
            treatment_period_start=(
                str(payload["treatment_period_start"])
                if payload.get("treatment_period_start") is not None
                else None
            ),
            treatment_period_end=(
                str(payload["treatment_period_end"])
                if payload.get("treatment_period_end") is not None
                else None
            ),
            outcome_value_column=(
                str(payload["outcome_value_column"])
                if payload.get("outcome_value_column") is not None
                else None
            ),
        )

    def apply(self, base: CurrentE2ReferenceSpec) -> CurrentE2ReferenceSpec:
        """Return a reference-compatible spec changing only declared overrides."""
        primary = base.primary_cell
        cell = FullyContractedTreatmentCellSpec(
            cell_id=self.variant_id,
            role="PRIMARY",
            value_column=self.treatment_value_column or primary.value_column,
            threshold=(
                self.treatment_threshold
                if self.treatment_threshold is not None
                else primary.threshold
            ),
        )
        return replace(
            base,
            reference_id=f"{base.reference_id}__{self.variant_id}",
            treatment_period_start=self.treatment_period_start or base.treatment_period_start,
            treatment_period_end=self.treatment_period_end or base.treatment_period_end,
            outcome_value_column=self.outcome_value_column or base.outcome_value_column,
            cells=(cell,),
        )


@dataclass(frozen=True)
class CurrentE2RobustnessSuite:
    suite_id: str
    purpose: str
    base_config: str
    reading_rule: str
    variants: tuple[CurrentE2RobustnessVariant, ...]

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2RobustnessSuite":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        variants = tuple(CurrentE2RobustnessVariant.from_dict(x) for x in raw["variants"])
        ids = [variant.variant_id for variant in variants]
        if not variants or len(ids) != len(set(ids)):
            raise ValueError("robustness suite requires non-empty unique variant IDs")
        return cls(
            suite_id=str(raw["suite_id"]),
            purpose=str(raw.get("purpose", "calibration_sensitivity")),
            base_config=str(raw["base_config"]),
            reading_rule=str(raw["reading_rule"]),
            variants=variants,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "purpose": self.purpose,
            "base_config": self.base_config,
            "reading_rule": self.reading_rule,
            "variants": [asdict(variant) for variant in self.variants],
        }


def _geography_from_reference_result(result: dict[str, Any]) -> pd.DataFrame:
    spec: CurrentE2ReferenceSpec = result["spec"]
    units = result["panel"][[spec.unit_col, spec.country_col]].drop_duplicates().copy()
    linkage = result["geography_linkage"][[spec.unit_col, "geo_uid"]].drop_duplicates().copy()
    geography = units.merge(linkage, on=spec.unit_col, how="left", validate="one_to_one")
    if geography["geo_uid"].isna().any():
        raise ValueError("canonical reference result has incomplete geography linkage")
    return geography.rename(
        columns={
            spec.unit_col: spec.geography_source_unit_col,
            "geo_uid": spec.geography_measurement_unit_col,
            spec.country_col: spec.geography_country_col,
        }
    )[
        [
            spec.geography_source_unit_col,
            spec.geography_measurement_unit_col,
            spec.geography_country_col,
        ]
    ]


def _gate_value(cell_result: dict[str, Any], gate: str) -> Any:
    rows = cell_result["gates"].loc[cell_result["gates"]["gate"].eq(gate), "value"]
    return rows.iloc[0] if len(rows) == 1 else np.nan


def _summary_row(
    *,
    variant_id: str,
    dimension: str,
    description: str,
    spec: CurrentE2ReferenceSpec,
    cell: FullyContractedTreatmentCellSpec,
    cell_result: dict[str, Any],
) -> dict[str, Any]:
    estimate = cell_result["estimate"]
    support = cell_result["support_by_period"]
    mixed = (
        int(((support["treated"] > 0) & (support["control"] > 0)).sum())
        if len(support)
        else 0
    )
    red = cell_result["gates"].loc[
        cell_result["gates"]["status"].eq("RED"), "gate"
    ].tolist()
    yellow = cell_result["gates"].loc[
        cell_result["gates"]["status"].eq("YELLOW"), "gate"
    ].tolist()
    return {
        "variant_id": variant_id,
        "dimension": dimension,
        "description": description,
        "treatment_value_column": cell.value_column,
        "treatment_threshold": cell.threshold,
        "treatment_period_start": spec.treatment_period_start,
        "treatment_period_end": spec.treatment_period_end,
        "outcome_value_column": spec.outcome_value_column,
        "estimated": bool(estimate.get("ok")),
        "effect": estimate.get("effect", np.nan),
        "se": estimate.get("se", np.nan),
        "n": estimate.get("n", np.nan),
        "n_units": estimate.get("n_units", np.nan),
        "treated": estimate.get("n_treated", np.nan),
        "control": estimate.get("n_control", np.nan),
        "mixed_support_periods": f"{mixed}/{len(support)}",
        "outcome_zero_share": _gate_value(cell_result, "E3_OUTCOME_SPARSITY"),
        "pre_outcome_abs_smd": _gate_value(cell_result, "E4_PRE_OUTCOME_BALANCE"),
        "placebo_std_abs_effect": cell_result["placebo"].get("std_abs_effect", np.nan),
        "signal_recovery": cell_result["signal_recovery"].get("recovery_probability", np.nan),
        "hard_gate_state": "PASS" if cell_result["estimation_permitted"] else "BLOCKED",
        "red_gates": ";".join(red),
        "yellow_gates": ";".join(yellow),
        "estimate_reason": estimate.get("reason", ""),
    }


def run_current_e2_robustness(
    canonical_result: dict[str, Any],
    suite: CurrentE2RobustnessSuite,
) -> dict[str, Any]:
    """Run bounded sensitivities on the exact canonical governed input bundles.

    Variants never run observability and never select a preferred specification.
    The canonical run remains primary. Existing canonical STRESS treatment cells are
    retained in the summary as predeclared sensitivity evidence.
    """
    base: CurrentE2ReferenceSpec = canonical_result["spec"]
    geography = _geography_from_reference_result(canonical_result)
    rows: list[dict[str, Any]] = []

    for cell in base.cells:
        result = canonical_result["calibration"]["cells"][cell.cell_id]
        rows.append(
            _summary_row(
                variant_id=f"canonical_{cell.cell_id}",
                dimension=(
                    "canonical_reference"
                    if cell.role.upper() == "PRIMARY"
                    else "predeclared_treatment_measurement_stress"
                ),
                description=(
                    "Canonical reference treatment definition."
                    if cell.role.upper() == "PRIMARY"
                    else "Canonical predeclared treatment-measurement stress cell."
                ),
                spec=base,
                cell=cell,
                cell_result=result,
            )
        )

    variants: dict[str, dict[str, Any]] = {}
    for variant in suite.variants:
        spec = variant.apply(base)
        result = run_current_e2_from_bundles(
            geography,
            canonical_result["geography_dataset"],
            canonical_result["treatment_bundle"],
            canonical_result["outcome_bundle"],
            spec,
            run_observability=False,
        )
        variants[variant.variant_id] = result
        cell = spec.primary_cell
        rows.append(
            _summary_row(
                variant_id=variant.variant_id,
                dimension=variant.dimension,
                description=variant.description,
                spec=spec,
                cell=cell,
                cell_result=result["calibration"]["cells"][cell.cell_id],
            )
        )

    return {
        "suite": suite,
        "canonical": canonical_result,
        "variants": variants,
        "summary": pd.DataFrame(rows),
    }


def render_current_e2_robustness_card(result: dict[str, Any]) -> str:
    suite: CurrentE2RobustnessSuite = result["suite"]
    summary: pd.DataFrame = result["summary"]
    lines = [
        f"# Current GeoGCDF → ACLED E2 robustness — {suite.suite_id}",
        "",
        f"> {suite.reading_rule}",
        "",
        "| variant | dimension | treatment | threshold | window | outcome | effect | SE | N | treated/control | gates |",
        "|---|---|---|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for _, row in summary.iterrows():
        def fmt(value: Any) -> str:
            if pd.isna(value):
                return "—"
            if isinstance(value, float):
                return f"{value:.4g}"
            return str(value)

        treated_control = (
            "—"
            if pd.isna(row["treated"])
            else f"{int(row['treated'])}/{int(row['control'])}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["variant_id"]),
                    str(row["dimension"]),
                    str(row["treatment_value_column"]),
                    fmt(row["treatment_threshold"]),
                    f"{row['treatment_period_start']}…{row['treatment_period_end']}",
                    str(row["outcome_value_column"]),
                    fmt(row["effect"]),
                    fmt(row["se"]),
                    "—" if pd.isna(row["n"]) else str(int(row["n"])),
                    treated_control,
                    str(row["hard_gate_state"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "The table is a stability/influence diagnostic. A robustness variant does not replace the canonical estimate, and significance is never a selection criterion.",
        "",
    ]
    return "\n".join(lines)


def write_current_e2_robustness_outputs(result: dict[str, Any], out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_current_e2_reference_outputs(result["canonical"], out / "canonical")
    for variant_id, variant_result in result["variants"].items():
        write_current_e2_reference_outputs(variant_result, out / "variants" / variant_id)
    result["summary"].to_csv(out / "robustness_summary.csv", index=False)
    (out / "robustness_card.md").write_text(
        render_current_e2_robustness_card(result), encoding="utf-8"
    )
    suite: CurrentE2RobustnessSuite = result["suite"]
    payload = {
        "suite": suite.to_dict(),
        "canonical_reference_id": result["canonical"]["spec"].reference_id,
        "variant_reference_ids": {
            variant_id: variant_result["spec"].reference_id
            for variant_id, variant_result in result["variants"].items()
        },
        "analysis_frame_persisted": False,
        "variant_selection_by_result": False,
    }
    (out / "robustness_run.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


__all__ = [
    "CurrentE2RobustnessSuite",
    "CurrentE2RobustnessVariant",
    "render_current_e2_robustness_card",
    "run_current_e2_robustness",
    "write_current_e2_robustness_outputs",
]
