# FCV Africa Observability Lab — calibration kernel

This module makes empirical instrument-characterization runs first-class without turning the harness into a second experiment framework.

A calibration benchmark asks:

> Given this empirical measurement system and scientific design, what kind of signal should we be able to observe?

It does **not** assert an FCV substantive result. Every benchmark spec must declare `purpose = "calibration"`.

## Boundary

Upstream empirical products continue to own source identity, natural grain, geography, time, coverage, and measurement semantics. The calibration layer only declares how those measurements are used for a known-behavior check and records the resulting recovery diagnostics.

The kernel is deliberately source-agnostic. Source-family logic belongs either in upstream contracts or in an explicit benchmark adapter, never in `fcv_harness.calibration_lab`.

This layer is also distinct from the existing E2 estimator-calibration modules. Those modules characterize a particular estimator/gate path; the observability lab coordinates heterogeneous commissioning, control, injection, and agreement benchmarks over the shared contract-backed input seam.

## Benchmark specification

`CalibrationBenchmarkSpec` carries a small declarative surface:

- benchmark identity, title, description, and kind;
- `purpose = "calibration"`;
- contract-backed empirical input declarations;
- optional `MeasurementProjectionSpec` declarations describing measurement use;
- expected/reference behavior;
- the recovery level required for acceptance;
- an explicit adapter ID plus benchmark parameters, notes, and limitations.

Supported benchmark kinds are:

- `commissioning`
- `positive_control`
- `negative_control`
- `synthetic_injection`
- `measurement_agreement`

Adapters are supplied through a plain mapping from `adapter_id` to callable. There is no dynamic plugin system or workflow engine.

## Recovery levels

Recovery is represented independently at three levels:

1. `level_1_pipeline` — the declared inputs and benchmark pipeline execute coherently.
2. `level_2_qualitative` — the expected sign, pattern, ordering, or null behavior is recovered.
3. `level_3_quantitative` — a declared numeric target or tolerance is recovered.

Each level has an explicit state: `pass`, `fail`, `not_required`, or `not_run`.

A benchmark may therefore pass at Level 2 while declaring Level 3 `not_required`. This is the intended representation when, for example, a published qualitative pattern should recover but exact coefficient parity is not scientifically justified because source releases or measurement construction differ.

Benchmark status is `pass`, `yellow`, `fail`, or `not_run`. A failed required recovery level stays a visible failure. Optional higher-level failures or warnings can produce `yellow`; they are never silently promoted to success.

## Local empirical mode

Real protected data remains outside Git. `CalibrationEmpiricalInputSpec` declares paths to the same durable data artifact, `MeasurementContract`, `CoverageContract`, and upstream `RunManifest` consumed by the existing empirical-input seam.

Relative paths resolve only beneath an explicit `data_root`:

```python
suite = run_calibration_suite(
    specs,
    registry,
    data_root="/data/fcv-empirical-artifacts",
    random_seed=20260823,
    harness_code_revision="<git-sha>",
)
```

Absolute paths are also accepted when explicitly supplied. A missing local empirical artifact yields a sanitized `NOT_RUN` benchmark rather than copying data into the repository. Contract or hash validation failure yields pipeline failure.

Calibration outputs contain DatasetRef identities and aggregate diagnostics only. The writer does not persist input tables or local filesystem paths, and path-like objects are rejected from result diagnostics.

A generic CLI is intentionally deferred. The repository currently uses small `argparse` entry points, but a useful calibration CLI would require adapter discovery/registration policy. The library entry point keeps local execution possible without introducing a plugin architecture just for this PR.

## Minimal calibration manifest

Every benchmark run records:

- benchmark spec SHA-256 over scientific declarations (excluding machine-local path locators);
- empirical `DatasetRef` identities;
- benchmark parameters;
- optional harness code revision;
- random seed when supplied;
- a SHA-256 of the canonical sanitized result envelope.

This is intentionally calibration-specific. It is not a general experiment provenance platform.

## Instrument health report

`render_instrument_health_report` summarizes a suite across separate dimensions:

- source / contract integrity;
- commissioning;
- positive controls;
- negative controls;
- synthetic detectability;
- measurement agreement;
- known limitations.

Each benchmark remains visible with its status, highest recovered level, selected aggregate diagnostics, and discrepancies. There is deliberately no single instrument score.

## CI policy

CI uses only tiny synthetic contract-backed fixtures. Real DHS, ACLED, GeoGCDF, or other protected/source artifacts are neither required nor permitted as test fixtures for this kernel.
