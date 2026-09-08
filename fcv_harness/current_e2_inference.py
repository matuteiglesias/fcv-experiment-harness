from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .current_e2_reference import CurrentE2ReferenceSpec
from .inference_calibration import (
    InferenceMethodSpec,
    run_inference_calibration,
    write_inference_calibration_outputs,
)
from .reference_identity import stable_frame_sha256


INFERENCE_SUITE_SCHEMA = "current_e2_inference_calibration.v1"


class CurrentE2InferenceError(ValueError):
    """Raised when the current-E2 inference suite is not bound to the frozen reference."""


@dataclass(frozen=True)
class CurrentE2InferenceSuiteSpec:
    suite_id: str
    purpose: str
    reference_id: str
    primary_cell_id: str
    required_analysis_identity_sha256: str
    required_primary_frame_sha256: str
    effect_sizes_sd: tuple[float, ...]
    repetitions: int
    root_seed: int
    alpha: float
    monte_carlo_confidence: float
    methods: tuple[InferenceMethodSpec, ...]

    @classmethod
    def from_json(cls, path: str | Path) -> "CurrentE2InferenceSuiteSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != INFERENCE_SUITE_SCHEMA:
            raise CurrentE2InferenceError("unsupported current E2 inference suite schema")
        methods = tuple(
            InferenceMethodSpec(
                method_id=str(item["method_id"]),
                kind=str(item["kind"]),
                cluster_col=str(item["cluster_col"]),
                bootstrap_repetitions=int(item.get("bootstrap_repetitions", 0)),
                bootstrap_root_seed=int(item.get("bootstrap_root_seed", 0)),
            )
            for item in raw["methods"]
        )
        effects = tuple(float(value) for value in raw["effect_sizes_sd"])
        if not methods:
            raise CurrentE2InferenceError("current E2 inference suite requires methods")
        if len({method.method_id for method in methods}) != len(methods):
            raise CurrentE2InferenceError("current E2 inference method IDs must be unique")
        if not effects or len(set(effects)) != len(effects):
            raise CurrentE2InferenceError("current E2 inference effect sizes must be unique")
        repetitions = int(raw["repetitions"])
        root_seed = int(raw["root_seed"])
        alpha = float(raw.get("alpha", 0.05))
        mc_confidence = float(raw.get("monte_carlo_confidence", 0.95))
        if repetitions <= 0 or root_seed < 0:
            raise CurrentE2InferenceError("invalid current E2 inference repetitions/root seed")
        if not 0.0 < alpha < 1.0 or not 0.0 < mc_confidence < 1.0:
            raise CurrentE2InferenceError("invalid current E2 inference probability parameter")
        return cls(
            suite_id=str(raw["suite_id"]),
            purpose=str(raw.get("purpose", "calibration")),
            reference_id=str(raw["reference_id"]),
            primary_cell_id=str(raw["primary_cell_id"]),
            required_analysis_identity_sha256=str(raw["required_analysis_identity_sha256"]),
            required_primary_frame_sha256=str(raw["required_primary_frame_sha256"]),
            effect_sizes_sd=effects,
            repetitions=repetitions,
            root_seed=root_seed,
            alpha=alpha,
            monte_carlo_confidence=mc_confidence,
            methods=methods,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INFERENCE_SUITE_SCHEMA,
            "suite_id": self.suite_id,
            "purpose": self.purpose,
            "reference_id": self.reference_id,
            "primary_cell_id": self.primary_cell_id,
            "required_analysis_identity_sha256": self.required_analysis_identity_sha256,
            "required_primary_frame_sha256": self.required_primary_frame_sha256,
            "effect_sizes_sd": list(self.effect_sizes_sd),
            "repetitions": self.repetitions,
            "root_seed": self.root_seed,
            "alpha": self.alpha,
            "monte_carlo_confidence": self.monte_carlo_confidence,
            "methods": [
                {
                    "method_id": method.method_id,
                    "kind": method.kind,
                    "cluster_col": method.cluster_col,
                    "bootstrap_repetitions": method.bootstrap_repetitions,
                    "bootstrap_root_seed": method.bootstrap_root_seed,
                }
                for method in self.methods
            ],
        }


def _dataset_sha(dataset: Any, label: str) -> str:
    value = getattr(dataset, "content_sha256", None)
    if not value:
        raise CurrentE2InferenceError(f"{label} DatasetRef lacks content_sha256")
    return str(value)


def _require_reference_binding(
    result: Mapping[str, Any],
    suite: CurrentE2InferenceSuiteSpec,
) -> tuple[CurrentE2ReferenceSpec, Mapping[str, Any], Mapping[str, Any], str]:
    spec = result.get("spec")
    if not isinstance(spec, CurrentE2ReferenceSpec):
        raise CurrentE2InferenceError("current E2 inference requires a CurrentE2ReferenceSpec")
    if suite.purpose != "calibration" or spec.purpose != "calibration":
        raise CurrentE2InferenceError("current E2 inference suite must remain calibration-only")
    if suite.reference_id != spec.reference_id:
        raise CurrentE2InferenceError("inference suite reference_id does not match current E2 reference")
    if suite.primary_cell_id != spec.primary_cell.cell_id:
        raise CurrentE2InferenceError("inference suite PRIMARY cell does not match current E2 reference")

    identity = result.get("reference_identity")
    if not isinstance(identity, Mapping):
        raise CurrentE2InferenceError("current E2 inference requires reference_identity")
    lock = identity.get("lock")
    if not isinstance(lock, Mapping) or lock.get("verified") is not True:
        raise CurrentE2InferenceError("current E2 inference requires a verified reference lock")
    if identity.get("reference_id") != spec.reference_id:
        raise CurrentE2InferenceError("reference identity does not match current E2 reference")
    if identity.get("analysis_identity_sha256") != suite.required_analysis_identity_sha256:
        raise CurrentE2InferenceError("analysis identity does not match frozen inference suite")
    if identity.get("primary_cell_id") != suite.primary_cell_id:
        raise CurrentE2InferenceError("reference identity PRIMARY cell mismatch")

    calibration = result.get("calibration")
    if not isinstance(calibration, Mapping):
        raise CurrentE2InferenceError("current E2 inference requires calibration results")
    cells = calibration.get("cells")
    if not isinstance(cells, Mapping) or suite.primary_cell_id not in cells:
        raise CurrentE2InferenceError("current E2 inference PRIMARY cell result is absent")
    primary = cells[suite.primary_cell_id]
    if not isinstance(primary, Mapping) or primary.get("estimation_permitted") is not True:
        raise CurrentE2InferenceError("current E2 inference is blocked by PRIMARY hard gates")
    frame = primary.get("frame")
    if frame is None:
        raise CurrentE2InferenceError("current E2 inference requires the in-memory PRIMARY frame")
    frame_sha = stable_frame_sha256(frame, unit_col=spec.unit_col, period_col=spec.period_col)
    if frame_sha != suite.required_primary_frame_sha256:
        raise CurrentE2InferenceError("PRIMARY frame fingerprint does not match frozen inference suite")
    if identity.get("primary_frame_sha256") != frame_sha:
        raise CurrentE2InferenceError("reference identity PRIMARY frame fingerprint mismatch")

    if tuple(spec.observability.effect_sizes_sd) != tuple(suite.effect_sizes_sd):
        raise CurrentE2InferenceError("inference effect grid must match frozen observability grid")
    if int(spec.observability.repetitions) != int(suite.repetitions):
        raise CurrentE2InferenceError("inference repetitions must match frozen observability repetitions")
    if int(spec.observability.root_seed) != int(suite.root_seed):
        raise CurrentE2InferenceError("inference root seed must match frozen observability root seed")

    treatment = result.get("treatment_bundle")
    outcome = result.get("outcome_bundle")
    geography = result.get("geography_dataset")
    if treatment is None or outcome is None or geography is None:
        raise CurrentE2InferenceError("current E2 inference requires governed input bundles")
    if treatment.measurement.measure_id != spec.treatment_measure_id:
        raise CurrentE2InferenceError("treatment measurement identity changed before inference")
    if outcome.measurement.measure_id != spec.outcome_measure_id:
        raise CurrentE2InferenceError("outcome measurement identity changed before inference")

    inputs = identity.get("inputs")
    if not isinstance(inputs, Mapping):
        raise CurrentE2InferenceError("reference identity is missing upstream content hashes")
    expected_hashes = {
        "geography_sha256": _dataset_sha(geography, "geography"),
        "treatment_sha256": _dataset_sha(treatment.dataset, "treatment"),
        "outcome_sha256": _dataset_sha(outcome.dataset, "outcome"),
    }
    for key, expected in expected_hashes.items():
        if inputs.get(key) != expected:
            raise CurrentE2InferenceError(f"reference identity upstream hash mismatch: {key}")

    return spec, identity, primary, frame_sha


def run_current_e2_inference_suite(
    result: Mapping[str, Any],
    suite: CurrentE2InferenceSuiteSpec,
) -> dict[str, Any]:
    """Run R1 inference calibration on the exact already-prepared current-E2 PRIMARY frame.

    The adapter never reloads empirical data, creates another projection, changes
    treatment semantics, or persists the row-level frame. It refuses to run unless
    hard gates pass and the verified R0 analysis/frame identities match the frozen
    R2 suite declaration.
    """
    spec, identity, primary, frame_sha = _require_reference_binding(result, suite)
    calibration_spec = result.get("calibration_spec")
    if calibration_spec is None:
        raise CurrentE2InferenceError("current E2 inference requires calibration_spec")

    inference = run_inference_calibration(
        primary["frame"],
        calibration_spec,
        effect_sizes_sd=suite.effect_sizes_sd,
        repetitions=suite.repetitions,
        root_seed=suite.root_seed,
        methods=suite.methods,
        alpha=suite.alpha,
        monte_carlo_confidence=suite.monte_carlo_confidence,
    )
    binding = {
        "schema": "current_e2_inference_binding.v1",
        "suite_id": suite.suite_id,
        "purpose": "calibration",
        "adapter_policy": "reuse_existing_in_memory_primary_frame_no_reprojection",
        "reference_id": spec.reference_id,
        "primary_cell_id": suite.primary_cell_id,
        "primary_hard_gate_state": "PASS",
        "analysis_identity_sha256": identity["analysis_identity_sha256"],
        "execution_identity_sha256": identity["execution_identity_sha256"],
        "primary_frame_sha256": frame_sha,
        "reference_lock_id": identity["lock"].get("lock_id"),
        "treatment_measure_id": spec.treatment_measure_id,
        "outcome_measure_id": spec.outcome_measure_id,
        "geography_sha256": identity["inputs"]["geography_sha256"],
        "treatment_sha256": identity["inputs"]["treatment_sha256"],
        "outcome_sha256": identity["inputs"]["outcome_sha256"],
        "analysis_frame_persisted": False,
        "reprojection_performed": False,
        "reingestion_performed": False,
    }
    inference["reference_binding"] = binding
    inference["inference_spec"] = {
        **dict(inference["inference_spec"]),
        "current_e2_suite": suite.to_dict(),
        "reference_binding": binding,
    }
    return inference


def write_current_e2_inference_outputs(
    inference: Mapping[str, Any],
    out_dir: str | Path,
) -> Path:
    """Write aggregate R2 evidence and bind it into an existing reference packet."""
    root = Path(out_dir)
    target = write_inference_calibration_outputs(inference, root / "inference_calibration")
    binding = inference.get("reference_binding")
    if not isinstance(binding, Mapping):
        raise CurrentE2InferenceError("R2 inference result lacks reference_binding")
    (target / "reference_binding.json").write_text(
        json.dumps(dict(binding), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    run_path = root / "reference_run.json"
    if not run_path.is_file():
        raise CurrentE2InferenceError("reference_run.json must exist before writing R2 outputs")
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["inference_calibration"] = {
        "state": "RUN",
        "path": "inference_calibration",
        "suite_id": binding["suite_id"],
        "analysis_identity_sha256": binding["analysis_identity_sha256"],
        "primary_frame_sha256": binding["primary_frame_sha256"],
        "analysis_frame_persisted": False,
        "reprojection_performed": False,
        "reingestion_performed": False,
    }
    run_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "INFERENCE_SUITE_SCHEMA",
    "CurrentE2InferenceError",
    "CurrentE2InferenceSuiteSpec",
    "run_current_e2_inference_suite",
    "write_current_e2_inference_outputs",
]
