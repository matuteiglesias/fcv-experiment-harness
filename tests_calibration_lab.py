from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from empirical_contracts import (
    AuthorityLevel,
    CoverageContract,
    DataLayer,
    DatasetRef,
    GeographySpec,
    GrainSpec,
    MeasurementContract,
    PeriodScheme,
    RunManifest,
)
from fcv_harness.calibration_lab import (
    CalibrationBenchmarkKind,
    CalibrationBenchmarkSpec,
    CalibrationEmpiricalInputSpec,
    CalibrationObservation,
    CalibrationStatus,
    RecoveryLevel,
    RecoveryProfile,
    RecoveryState,
    render_instrument_health_report,
    run_calibration_benchmark,
    run_calibration_suite,
    write_calibration_suite_outputs,
)
from fcv_harness.measurement_projection import MeasurementProjectionSpec


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_model(path: Path, model) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _fixture(root: Path) -> CalibrationEmpiricalInputSpec:
    fixture = root / "fixture"
    fixture.mkdir()
    data_path = fixture / "measurement.csv"
    pd.DataFrame(
        [
            {"geo_uid": "A", "period_id": "2001-2002", "value": 1.0},
            {"geo_uid": "B", "period_id": "2001-2002", "value": 2.0},
        ]
    ).to_csv(data_path, index=False)

    geography = GeographySpec(
        provider="synthetic",
        version="1",
        scheme="admin",
        level="2",
    )
    period = PeriodScheme(width_years=2, anchor_year=2001)
    grain = GrainSpec(keys=("geo_uid", "period_id"))
    source = DatasetRef(
        dataset_id="synthetic.source.silver",
        version="fixture-1",
        schema_version="v1",
        layer=DataLayer.SILVER,
        authority=AuthorityLevel.L3_REBUILT,
        grain=GrainSpec(keys=("source_row_id",)),
        content_sha256="1" * 64,
    )
    dataset = DatasetRef(
        dataset_id="synthetic.measurement.gold",
        version="fixture-1",
        schema_version="v1",
        layer=DataLayer.GOLD,
        authority=AuthorityLevel.L3_REBUILT,
        grain=grain,
        geography=geography,
        period_scheme=period,
        content_sha256=_sha256(data_path),
    )
    coverage = CoverageContract(
        geography_scope="synthetic fixture",
        observation_semantics="two observed calibration rows",
        absent_row_semantics="unknown",
        authority=AuthorityLevel.L3_REBUILT,
        basis="synthetic calibration fixture",
    )
    measurement = MeasurementContract(
        measure_id="synthetic.measure",
        description="Synthetic measurement used only by calibration-kernel tests",
        source_dataset=source,
        output_grain=grain,
        coverage=coverage,
        geography=geography,
        period_scheme=period,
    )
    manifest = RunManifest(
        run_id="synthetic-calibration-input",
        package="fcv-empirical-data",
        package_version="0.1.0",
        code_commit="fixture",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        inputs=(source,),
        outputs=(dataset,),
    )

    _write_model(fixture / "measurement_contract.json", measurement)
    _write_model(fixture / "coverage_contract.json", coverage)
    _write_model(fixture / "run_manifest.json", manifest)
    return CalibrationEmpiricalInputSpec(
        input_id="measurement",
        data_path="fixture/measurement.csv",
        measurement_contract_path="fixture/measurement_contract.json",
        coverage_contract_path="fixture/coverage_contract.json",
        run_manifest_path="fixture/run_manifest.json",
        measurement_use=MeasurementProjectionSpec(
            measure_id="synthetic.measure",
            selectors={},
            value_column="value",
            role="calibration_observation",
        ),
    )


def _spec(
    input_spec: CalibrationEmpiricalInputSpec,
    benchmark_id: str,
    kind: CalibrationBenchmarkKind,
    adapter_id: str,
    acceptance_level: RecoveryLevel,
    *,
    limitations: tuple[str, ...] = (),
) -> CalibrationBenchmarkSpec:
    return CalibrationBenchmarkSpec(
        benchmark_id=benchmark_id,
        title=benchmark_id.replace("_", " ").title(),
        purpose="calibration",
        kind=kind,
        description="Synthetic observability characterization benchmark",
        empirical_inputs=(input_spec,),
        reference_behavior={"expected_pattern": "declared calibration behavior"},
        acceptance_level=acceptance_level,
        adapter_id=adapter_id,
        parameters={"fixture_parameter": 1},
        limitations=limitations,
    )


def _commissioning(context):
    bundle = context.inputs["measurement"]
    return CalibrationObservation(
        recovery=RecoveryProfile(RecoveryState.PASS),
        diagnostics={"rows_loaded": len(bundle.table), "contract_integrity": "pass"},
        observed_behavior={"pipeline": "recovered"},
    )


def _positive(context):
    values = pd.to_numeric(context.inputs["measurement"].table["value"])
    return CalibrationObservation(
        recovery=RecoveryProfile(
            RecoveryState.PASS,
            RecoveryState.PASS,
            RecoveryState.NOT_REQUIRED,
        ),
        diagnostics={"mean_value": float(values.mean()), "sign_recovered": True},
        observed_behavior={"pattern": "positive"},
    )


def _failed_expected_behavior(context):
    assert context.inputs["measurement"].dataset.dataset_id == "synthetic.measurement.gold"
    return CalibrationObservation(
        recovery=RecoveryProfile(
            RecoveryState.PASS,
            RecoveryState.FAIL,
            RecoveryState.NOT_REQUIRED,
        ),
        diagnostics={"null_rejection_rate": 0.4},
        observed_behavior={"pattern": "unexpected"},
        discrepancies=("expected null behavior was not recovered",),
    )


def _not_run(context):
    assert context.random_seed is not None
    return CalibrationObservation.not_run("benchmark deliberately unavailable in this fixture")


def _agreement(context):
    return CalibrationObservation(
        recovery=RecoveryProfile(
            RecoveryState.PASS,
            RecoveryState.PASS,
            RecoveryState.PASS,
        ),
        diagnostics={"agreement_correlation": 1.0},
        observed_behavior={"agreement": "exact in synthetic fixture"},
    )


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    input_spec = _fixture(root)

    # Calibration cannot silently masquerade as research.
    try:
        CalibrationBenchmarkSpec(
            benchmark_id="bad-purpose",
            title="Bad purpose",
            purpose="research",
            kind=CalibrationBenchmarkKind.COMMISSIONING,
            description="invalid",
            empirical_inputs=(input_spec,),
            reference_behavior={},
            acceptance_level=RecoveryLevel.PIPELINE,
            adapter_id="commissioning",
        )
    except ValueError as error:
        assert "purpose" in str(error)
    else:
        raise AssertionError("non-calibration benchmark purpose was accepted")

    specs = (
        _spec(
            input_spec,
            "commissioning_pass",
            CalibrationBenchmarkKind.COMMISSIONING,
            "commissioning",
            RecoveryLevel.PIPELINE,
        ),
        _spec(
            input_spec,
            "positive_qualitative",
            CalibrationBenchmarkKind.POSITIVE_CONTROL,
            "positive",
            RecoveryLevel.QUALITATIVE,
            limitations=("quantitative parity is not required for this benchmark",),
        ),
        _spec(
            input_spec,
            "negative_failure",
            CalibrationBenchmarkKind.NEGATIVE_CONTROL,
            "failed",
            RecoveryLevel.QUALITATIVE,
        ),
        _spec(
            input_spec,
            "synthetic_not_run",
            CalibrationBenchmarkKind.SYNTHETIC_INJECTION,
            "not-run",
            RecoveryLevel.QUALITATIVE,
        ),
        _spec(
            input_spec,
            "agreement_quantitative",
            CalibrationBenchmarkKind.MEASUREMENT_AGREEMENT,
            "agreement",
            RecoveryLevel.QUANTITATIVE,
        ),
    )
    suite = run_calibration_suite(
        specs,
        {
            "commissioning": _commissioning,
            "positive": _positive,
            "failed": _failed_expected_behavior,
            "not-run": _not_run,
            "agreement": _agreement,
        },
        data_root=root,
        random_seed=20260823,
        harness_code_revision="test-revision",
    )
    by_id = {run.spec.benchmark_id: run for run in suite.runs}

    # A. Commissioning can pass at pipeline recovery.
    assert by_id["commissioning_pass"].result.status == CalibrationStatus.PASS
    assert by_id["commissioning_pass"].result.recovery_level == RecoveryLevel.PIPELINE

    # B. Qualitative recovery can pass while quantitative recovery is explicitly not required.
    qualitative = by_id["positive_qualitative"].result
    assert qualitative.status == CalibrationStatus.PASS
    assert qualitative.recovery.qualitative == RecoveryState.PASS
    assert qualitative.recovery.quantitative == RecoveryState.NOT_REQUIRED
    assert qualitative.recovery_level == RecoveryLevel.QUALITATIVE

    # C. Failed expected behavior stays visibly failed with its discrepancy.
    failed = by_id["negative_failure"].result
    assert failed.status == CalibrationStatus.FAIL
    assert failed.recovery.qualitative == RecoveryState.FAIL
    assert "expected null behavior" in failed.discrepancies[0]

    # D. NOT RUN is preserved and not collapsed into pass/fail.
    not_run = by_id["synthetic_not_run"].result
    assert not_run.status == CalibrationStatus.NOT_RUN
    assert not_run.not_run_reason

    # E. Multiple benchmark kinds render together without a magic instrument score.
    report = render_instrument_health_report(suite)
    for heading in (
        "## Commissioning",
        "## Positive controls",
        "## Negative controls",
        "## Synthetic detectability",
        "## Measurement agreement",
    ):
        assert heading in report
    assert "null_rejection_rate" in report
    assert "Instrument score" not in report
    assert "not an FCV substantive result" in report

    out = write_calibration_suite_outputs(suite, root / "out")
    result_payload = json.loads(
        (out / "positive_qualitative" / "result.json").read_text(encoding="utf-8")
    )
    manifest_payload = json.loads(
        (out / "positive_qualitative" / "manifest.json").read_text(encoding="utf-8")
    )
    assert result_payload["empirical_datasets"][0]["dataset_id"] == "synthetic.measurement.gold"
    assert manifest_payload["benchmark_spec_sha256"] == specs[1].spec_sha256
    assert manifest_payload["harness_code_revision"] == "test-revision"
    assert manifest_payload["random_seed"] == 20260824
    assert len(manifest_payload["result_sha256"]) == 64

    # Local source paths and source tables must not leak into sanitized artifacts.
    artifacts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in out.rglob("*")
        if path.is_file()
    )
    assert str(root) not in artifacts
    assert "fixture/measurement.csv" not in artifacts

    # Missing local protected data produces a sanitized NOT RUN result, not an exception.
    missing = CalibrationEmpiricalInputSpec(
        input_id="measurement",
        data_path="protected/not-present.csv",
        measurement_contract_path="protected/measurement.json",
        coverage_contract_path="protected/coverage.json",
        run_manifest_path="protected/manifest.json",
    )
    missing_run = run_calibration_benchmark(
        _spec(
            missing,
            "local_missing",
            CalibrationBenchmarkKind.COMMISSIONING,
            "commissioning",
            RecoveryLevel.PIPELINE,
        ),
        _commissioning,
        data_root=root,
    )
    assert missing_run.result.status == CalibrationStatus.NOT_RUN
    assert missing_run.result.empirical_datasets == ()
    assert "protected/not-present.csv" not in json.dumps(missing_run.result.to_dict())

# The source-agnostic kernel itself must not grow source-family semantics.
kernel_text = Path("fcv_harness/calibration_lab.py").read_text(encoding="utf-8")
for source_specific_name in ("DHS", "ACLED", "GeoGCDF"):
    assert source_specific_name not in kernel_text
