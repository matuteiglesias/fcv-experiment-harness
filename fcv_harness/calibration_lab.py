from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from empirical_contracts import DatasetRef

from .empirical_input import EmpiricalInputError, EmpiricalMeasurementBundle, load_empirical_measurement
from .measurement_projection import MeasurementProjectionSpec


class CalibrationBenchmarkKind(str, Enum):
    COMMISSIONING = "commissioning"
    POSITIVE_CONTROL = "positive_control"
    NEGATIVE_CONTROL = "negative_control"
    SYNTHETIC_INJECTION = "synthetic_injection"
    MEASUREMENT_AGREEMENT = "measurement_agreement"


class CalibrationStatus(str, Enum):
    PASS = "pass"
    YELLOW = "yellow"
    FAIL = "fail"
    NOT_RUN = "not_run"


class RecoveryLevel(str, Enum):
    PIPELINE = "level_1_pipeline"
    QUALITATIVE = "level_2_qualitative"
    QUANTITATIVE = "level_3_quantitative"


class RecoveryState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_REQUIRED = "not_required"
    NOT_RUN = "not_run"


_LEVELS = (
    RecoveryLevel.PIPELINE,
    RecoveryLevel.QUALITATIVE,
    RecoveryLevel.QUANTITATIVE,
)


@dataclass(frozen=True)
class RecoveryProfile:
    pipeline: RecoveryState
    qualitative: RecoveryState = RecoveryState.NOT_REQUIRED
    quantitative: RecoveryState = RecoveryState.NOT_REQUIRED

    def __post_init__(self) -> None:
        if self.pipeline != RecoveryState.PASS and self.qualitative == RecoveryState.PASS:
            raise ValueError("qualitative recovery requires pipeline recovery")
        if self.qualitative != RecoveryState.PASS and self.quantitative == RecoveryState.PASS:
            raise ValueError("quantitative recovery requires qualitative recovery")

    def state(self, level: RecoveryLevel) -> RecoveryState:
        return {
            RecoveryLevel.PIPELINE: self.pipeline,
            RecoveryLevel.QUALITATIVE: self.qualitative,
            RecoveryLevel.QUANTITATIVE: self.quantitative,
        }[level]

    @property
    def highest_recovered(self) -> RecoveryLevel | None:
        highest = None
        for level in _LEVELS:
            if self.state(level) != RecoveryState.PASS:
                break
            highest = level
        return highest

    def to_dict(self) -> dict[str, str]:
        return {level.value: self.state(level).value for level in _LEVELS}


@dataclass(frozen=True)
class CalibrationEmpiricalInputSpec:
    input_id: str
    data_path: str
    measurement_contract_path: str
    coverage_contract_path: str
    run_manifest_path: str
    dataset_id: str | None = None
    measurement_use: MeasurementProjectionSpec | None = None

    def __post_init__(self) -> None:
        values = (
            self.input_id,
            self.data_path,
            self.measurement_contract_path,
            self.coverage_contract_path,
            self.run_manifest_path,
        )
        if not all(values):
            raise ValueError("calibration empirical input identity and paths must be non-empty")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CalibrationEmpiricalInputSpec:
        raw_use = payload.get("measurement_use")
        return cls(
            input_id=str(payload["input_id"]),
            data_path=str(payload["data_path"]),
            measurement_contract_path=str(payload["measurement_contract_path"]),
            coverage_contract_path=str(payload["coverage_contract_path"]),
            run_manifest_path=str(payload["run_manifest_path"]),
            dataset_id=str(payload["dataset_id"]) if payload.get("dataset_id") else None,
            measurement_use=(
                MeasurementProjectionSpec.from_dict(dict(raw_use)) if raw_use else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "data_path": self.data_path,
            "measurement_contract_path": self.measurement_contract_path,
            "coverage_contract_path": self.coverage_contract_path,
            "run_manifest_path": self.run_manifest_path,
            "dataset_id": self.dataset_id,
            "measurement_use": self.measurement_use.to_dict() if self.measurement_use else None,
        }


@dataclass(frozen=True)
class CalibrationBenchmarkSpec:
    benchmark_id: str
    title: str
    kind: CalibrationBenchmarkKind
    description: str
    empirical_inputs: tuple[CalibrationEmpiricalInputSpec, ...]
    reference_behavior: dict[str, Any]
    acceptance_level: RecoveryLevel
    adapter_id: str
    purpose: str = "calibration"
    parameters: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.purpose != "calibration":
            raise ValueError("calibration benchmark purpose must be exactly 'calibration'")
        if not all((self.benchmark_id, self.title, self.description, self.adapter_id)):
            raise ValueError("calibration benchmark identity fields must be non-empty")
        input_ids = [item.input_id for item in self.empirical_inputs]
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("calibration empirical input IDs must be unique")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CalibrationBenchmarkSpec:
        return cls(
            benchmark_id=str(payload["benchmark_id"]),
            title=str(payload["title"]),
            purpose=str(payload.get("purpose", "calibration")),
            kind=CalibrationBenchmarkKind(str(payload["kind"])),
            description=str(payload["description"]),
            empirical_inputs=tuple(
                CalibrationEmpiricalInputSpec.from_dict(item)
                for item in payload.get("empirical_inputs", [])
            ),
            reference_behavior=dict(payload.get("reference_behavior", {})),
            acceptance_level=RecoveryLevel(str(payload["acceptance_level"])),
            adapter_id=str(payload["adapter_id"]),
            parameters=dict(payload.get("parameters", {})),
            notes=tuple(str(item) for item in payload.get("notes", [])),
            limitations=tuple(str(item) for item in payload.get("limitations", [])),
        )

    @classmethod
    def from_json(cls, path: str | Path) -> CalibrationBenchmarkSpec:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("calibration benchmark JSON must contain one object")
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "title": self.title,
            "purpose": self.purpose,
            "kind": self.kind.value,
            "description": self.description,
            "empirical_inputs": [item.to_dict() for item in self.empirical_inputs],
            "reference_behavior": self.reference_behavior,
            "acceptance_level": self.acceptance_level.value,
            "adapter_id": self.adapter_id,
            "parameters": self.parameters,
            "notes": list(self.notes),
            "limitations": list(self.limitations),
        }

    def identity_dict(self) -> dict[str, Any]:
        """Return scientific spec identity without machine-local input locators."""
        payload = self.to_dict()
        payload["empirical_inputs"] = [
            {
                "input_id": item.input_id,
                "dataset_id": item.dataset_id,
                "measurement_use": (
                    item.measurement_use.to_dict() if item.measurement_use else None
                ),
            }
            for item in self.empirical_inputs
        ]
        return payload

    @property
    def spec_sha256(self) -> str:
        return _sha256_json(self.identity_dict())


@dataclass(frozen=True)
class CalibrationObservation:
    recovery: RecoveryProfile
    diagnostics: dict[str, Any] = field(default_factory=dict)
    observed_behavior: dict[str, Any] = field(default_factory=dict)
    discrepancies: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    not_run_reason: str | None = None

    @classmethod
    def not_run(cls, reason: str) -> CalibrationObservation:
        return cls(
            recovery=RecoveryProfile(
                RecoveryState.NOT_RUN,
                RecoveryState.NOT_RUN,
                RecoveryState.NOT_RUN,
            ),
            not_run_reason=reason,
        )


@dataclass(frozen=True)
class CalibrationContext:
    spec: CalibrationBenchmarkSpec
    inputs: Mapping[str, EmpiricalMeasurementBundle]
    random_seed: int | None


CalibrationAdapter = Callable[[CalibrationContext], CalibrationObservation]


@dataclass(frozen=True)
class CalibrationResult:
    benchmark_id: str
    benchmark_kind: CalibrationBenchmarkKind
    status: CalibrationStatus
    recovery_level: RecoveryLevel | None
    recovery: RecoveryProfile
    empirical_datasets: tuple[DatasetRef, ...]
    key_diagnostics: dict[str, Any]
    expected_behavior: dict[str, Any]
    observed_behavior: dict[str, Any]
    discrepancies: tuple[str, ...]
    known_limitations: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    not_run_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_kind": self.benchmark_kind.value,
            "status": self.status.value,
            "recovery_level": self.recovery_level.value if self.recovery_level else None,
            "recovery": self.recovery.to_dict(),
            "empirical_datasets": [item.model_dump(mode="json") for item in self.empirical_datasets],
            "key_diagnostics": _sanitize(self.key_diagnostics),
            "expected_behavior": _sanitize(self.expected_behavior),
            "observed_behavior": _sanitize(self.observed_behavior),
            "discrepancies": list(self.discrepancies),
            "known_limitations": list(self.known_limitations),
            "warnings": list(self.warnings),
            "not_run_reason": self.not_run_reason,
        }


@dataclass(frozen=True)
class CalibrationRunManifest:
    benchmark_id: str
    benchmark_spec_sha256: str
    empirical_datasets: tuple[DatasetRef, ...]
    benchmark_parameters: dict[str, Any]
    harness_code_revision: str | None
    random_seed: int | None
    result_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "benchmark_spec_sha256": self.benchmark_spec_sha256,
            "empirical_datasets": [item.model_dump(mode="json") for item in self.empirical_datasets],
            "benchmark_parameters": _sanitize(self.benchmark_parameters),
            "harness_code_revision": self.harness_code_revision,
            "random_seed": self.random_seed,
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True)
class CalibrationRun:
    spec: CalibrationBenchmarkSpec
    result: CalibrationResult
    manifest: CalibrationRunManifest


@dataclass(frozen=True)
class CalibrationSuiteResult:
    runs: tuple[CalibrationRun, ...]

    @property
    def results(self) -> tuple[CalibrationResult, ...]:
        return tuple(run.result for run in self.runs)


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        raise ValueError("local filesystem paths are forbidden in calibration outputs")
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_sanitize(item) for item in value]
    if hasattr(value, "item"):
        return _sanitize(value.item())
    raise TypeError(f"unsupported calibration output value: {type(value).__name__}")


def _sha256_json(payload: Mapping[str, Any]) -> str:
    data = json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _resolve_path(path: str, data_root: str | Path | None) -> Path:
    declared = Path(path).expanduser()
    if declared.is_absolute():
        return declared.resolve()
    if data_root is None:
        raise ValueError("relative calibration input paths require data_root")
    root = Path(data_root).expanduser().resolve()
    resolved = (root / declared).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("calibration input path escapes data_root") from error
    return resolved


def _load_inputs(
    spec: CalibrationBenchmarkSpec, data_root: str | Path | None
) -> tuple[dict[str, EmpiricalMeasurementBundle], bool]:
    loaded: dict[str, EmpiricalMeasurementBundle] = {}
    for item in spec.empirical_inputs:
        paths = {
            "data_path": _resolve_path(item.data_path, data_root),
            "measurement_contract_path": _resolve_path(item.measurement_contract_path, data_root),
            "coverage_contract_path": _resolve_path(item.coverage_contract_path, data_root),
            "run_manifest_path": _resolve_path(item.run_manifest_path, data_root),
        }
        if not all(path.is_file() for path in paths.values()):
            return {}, False
        loaded[item.input_id] = load_empirical_measurement(**paths, dataset_id=item.dataset_id)
    return loaded, True


def _status(
    recovery: RecoveryProfile,
    required: RecoveryLevel,
    warnings: tuple[str, ...],
    not_run_reason: str | None,
) -> CalibrationStatus:
    if not_run_reason:
        return CalibrationStatus.NOT_RUN
    required_levels = _LEVELS[: _LEVELS.index(required) + 1]
    if any(recovery.state(level) == RecoveryState.FAIL for level in required_levels):
        return CalibrationStatus.FAIL
    if any(
        recovery.state(level) in {RecoveryState.NOT_REQUIRED, RecoveryState.NOT_RUN}
        for level in required_levels
    ):
        return CalibrationStatus.NOT_RUN
    optional_failure = any(
        recovery.state(level) == RecoveryState.FAIL
        for level in _LEVELS
        if level not in required_levels
    )
    return CalibrationStatus.YELLOW if warnings or optional_failure else CalibrationStatus.PASS


def _make_result(
    spec: CalibrationBenchmarkSpec,
    observation: CalibrationObservation,
    datasets: tuple[DatasetRef, ...],
) -> CalibrationResult:
    return CalibrationResult(
        benchmark_id=spec.benchmark_id,
        benchmark_kind=spec.kind,
        status=_status(
            observation.recovery,
            spec.acceptance_level,
            observation.warnings,
            observation.not_run_reason,
        ),
        recovery_level=observation.recovery.highest_recovered,
        recovery=observation.recovery,
        empirical_datasets=datasets,
        key_diagnostics=observation.diagnostics,
        expected_behavior=spec.reference_behavior,
        observed_behavior=observation.observed_behavior,
        discrepancies=observation.discrepancies,
        known_limitations=tuple(dict.fromkeys((*spec.limitations, *observation.limitations))),
        warnings=observation.warnings,
        not_run_reason=observation.not_run_reason,
    )


def run_calibration_benchmark(
    spec: CalibrationBenchmarkSpec,
    adapter: CalibrationAdapter,
    *,
    data_root: str | Path | None = None,
    random_seed: int | None = None,
    harness_code_revision: str | None = None,
) -> CalibrationRun:
    """Run one calibration benchmark without source-specific kernel semantics."""
    try:
        inputs, available = _load_inputs(spec, data_root)
    except EmpiricalInputError:
        inputs = {}
        observation = CalibrationObservation(
            RecoveryProfile(RecoveryState.FAIL),
            diagnostics={"input_contract_integrity": "failed"},
            discrepancies=("contract-backed empirical input failed validation",),
        )
    else:
        observation = (
            adapter(CalibrationContext(spec, inputs, random_seed))
            if available
            else CalibrationObservation.not_run(
                "declared empirical input files are unavailable in local mode"
            )
        )

    datasets = tuple(bundle.dataset for bundle in inputs.values())
    result = _make_result(spec, observation, datasets)
    manifest = CalibrationRunManifest(
        benchmark_id=spec.benchmark_id,
        benchmark_spec_sha256=spec.spec_sha256,
        empirical_datasets=datasets,
        benchmark_parameters=spec.parameters,
        harness_code_revision=harness_code_revision,
        random_seed=random_seed,
        result_sha256=_sha256_json(result.to_dict()),
    )
    return CalibrationRun(spec, result, manifest)


def run_calibration_suite(
    specs: tuple[CalibrationBenchmarkSpec, ...],
    registry: Mapping[str, CalibrationAdapter],
    *,
    data_root: str | Path | None = None,
    random_seed: int | None = None,
    harness_code_revision: str | None = None,
) -> CalibrationSuiteResult:
    ids = [spec.benchmark_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("calibration benchmark IDs must be unique")
    runs = []
    for index, spec in enumerate(specs):
        if spec.adapter_id not in registry:
            raise KeyError(f"no calibration adapter registered for {spec.adapter_id!r}")
        seed = None if random_seed is None else random_seed + index
        runs.append(
            run_calibration_benchmark(
                spec,
                registry[spec.adapter_id],
                data_root=data_root,
                random_seed=seed,
                harness_code_revision=harness_code_revision,
            )
        )
    return CalibrationSuiteResult(tuple(runs))


def render_instrument_health_report(suite: CalibrationSuiteResult) -> str:
    """Render multidimensional instrument health; deliberately no aggregate score."""
    results = suite.results
    pipeline_pass = sum(r.recovery.pipeline == RecoveryState.PASS for r in results)
    dataset_ids = {d.dataset_id for r in results for d in r.empirical_datasets}
    lines = [
        "# FCV Africa Observability Report",
        "",
        "Purpose: calibration",
        "",
        "## Source / contract integrity",
        f"- Pipeline recovery: {pipeline_pass} / {len(results)} benchmarks",
        f"- Contract-backed datasets observed: {len(dataset_ids)}",
        "",
    ]
    sections = (
        ("Commissioning", CalibrationBenchmarkKind.COMMISSIONING),
        ("Positive controls", CalibrationBenchmarkKind.POSITIVE_CONTROL),
        ("Negative controls", CalibrationBenchmarkKind.NEGATIVE_CONTROL),
        ("Synthetic detectability", CalibrationBenchmarkKind.SYNTHETIC_INJECTION),
        ("Measurement agreement", CalibrationBenchmarkKind.MEASUREMENT_AGREEMENT),
    )
    for title, kind in sections:
        selected = [result for result in results if result.benchmark_kind == kind]
        lines.append(f"## {title}")
        for result in selected:
            lines.append(
                f"- {result.benchmark_id}: {result.status.value.upper()} "
                f"(recovery={result.recovery_level.value if result.recovery_level else 'none'})"
            )
            if result.key_diagnostics:
                diagnostics = json.dumps(
                    _sanitize(result.key_diagnostics), sort_keys=True, separators=(",", ":")
                )
                lines.append(f"  - diagnostics: `{diagnostics}`")
            if result.discrepancies:
                lines.append(f"  - discrepancies: {'; '.join(result.discrepancies)}")
        if not selected:
            lines.append("- No benchmarks declared.")
        lines.append("")

    lines.append("## Known limitations")
    limitations = [
        f"{result.benchmark_id}: {item}"
        for result in results
        for item in result.known_limitations
    ]
    lines.extend(f"- {item}" for item in limitations) if limitations else lines.append(
        "- None declared in this suite."
    )
    lines.extend(
        [
            "",
            "This report characterizes observability and recovery behavior. It is not an FCV substantive result.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_sanitize(payload), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_calibration_suite_outputs(suite: CalibrationSuiteResult, out_dir: str | Path) -> Path:
    """Write only sanitized aggregate results/manifests, never local source tables or paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for run in suite.runs:
        run_dir = out / run.spec.benchmark_id
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "result.json", run.result.to_dict())
        _write_json(run_dir / "manifest.json", run.manifest.to_dict())
    (out / "instrument_health_report.md").write_text(
        render_instrument_health_report(suite), encoding="utf-8"
    )
    return out
