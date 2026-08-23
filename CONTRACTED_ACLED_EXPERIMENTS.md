# Contracted ACLED experiment integration

This wave makes the normalized ACLED measurement the first empirical product to cross the upstream/downstream boundary into active FCV experiment code.

```text
fcv-empirical-data
  ACLED Gold: geo_uid × period_id × native_event_type
        |
        | DatasetRef + MeasurementContract + CoverageContract + RunManifest
        v
fcv_harness.empirical_input
  validated EmpiricalMeasurementBundle
        |
        v
fcv_harness.measurement_projection
  explicit experiment MeasurementProjectionSpec
        |
        | selector: native_event_type = Violence against civilians
        | value: fatalities
        | timing: 0 / +1 / -1 shared periods
        | coverage resolution: observed / structural-zero / outside / unresolved
        v
contracted E1 analysis surface
        |
        v
contracted E2 calibration machinery
```

## Scientific boundary

The upstream fact is the contracted measurement itself: a sparse measurement by declared geography, shared period scheme, and native event taxonomy. The harness does not reconstruct source ingestion semantics.

The experiment makes separate, explicit choices about:

- which native taxonomy member to select;
- which normalized measurement column to use;
- the role of that value in the design;
- the timing offset relative to the treatment period;
- optional downstream transformations.

Those choices are serialized in `MeasurementProjectionSpec` and retained in an `ExperimentProjectionReport`. They intentionally do not belong in `empirical-data-contracts` because they are scientific-use semantics rather than statements about what the upstream system measured.

## Coverage firewall

Projection produces one of four statuses for every requested analysis row:

- `observed`: a contracted empirical row exists with a usable value;
- `structural_zero`: a sparse row is absent, the requested period is fully inside declared coverage, and `CoverageContract.absent_row_semantics` explicitly licenses `zero_within_verified_coverage`;
- `outside_coverage`: the requested period is outside declared temporal support;
- `unresolved`: coverage or value semantics do not license a value.

Unknown sparse absence never becomes zero. Unresolved and outside-support rows remain in the projection frame with missing values and explanatory detail; downstream preflight blocks estimation when such rows occur in the eligible experiment sample.

## Geography and time

The contracted geography identity is checked exactly against the experiment surface. Current legacy lattice GID labels are connected to contracted `geo_uid` values through an explicit one-to-one linkage artifact; the harness does not derive or guess that mapping.

Timing offsets use `spatial-data-foundation.PeriodIndex` with the contracted `PeriodScheme`. A `+1` outcome and `-1` pre-outcome therefore mean one declared period, not a string or year heuristic.

## Active E1/E2 path

The active E1 and E2 CLIs require explicit paths for:

- the contracted empirical table;
- `measurement_contract.json`;
- `coverage.json`;
- the upstream `run_manifest.json`;
- the analysis-unit to `geo_uid` linkage.

There is no legacy/contracted runtime switch. The active canonical experiment manifest no longer contains an ACLED aggregate source, the active experiment manifest no longer embeds historical ACLED coverage facts, and CI no longer runs the legacy ACLED aggregate path.

The existing investment treatment definitions remain unchanged in this PR. WBad/WBkg `record_present` and `amount_positive` semantics continue to use the current canonical investment surface; migrating those inputs is a separate boundary task and is not faked here.

## Projection audit

Each empirical-to-experiment projection reports at least:

- input `DatasetRef` and authority;
- measurement identity;
- selectors and role;
- geography and period scheme;
- input and selected row counts;
- upstream coverage semantics;
- observed, structural-zero, outside-coverage, and unresolved counts;
- timing offset and transform parameters;
- output row count and deterministic output SHA-256.

E1 writes a surface projection report. E2 writes separate `+1` outcome and `-1` pre-outcome projection reports for every calibration cell. Estimator results are deliberately separate from these reports.

## Real-data acceptance status

**REAL RUN NOT EXECUTED in this agent environment.**

The repository and linked GitHub sources expose the contracted ACLED implementation but do not contain a real materialized Gold table, its persisted contract sidecars, and the required current-lattice `GID -> geo_uid` linkage as runnable artifacts. No real-data counts, coefficient, gate result, or calibration result is claimed here.

Synthetic end-to-end acceptance exercises the same validated bundle -> projection -> E1 -> E2 interfaces, including the existing estimator and signal-recovery implementation. A real run should be executed by supplying the actual durable artifacts to the active CLIs; its acceptance criterion is coherent execution under the declared contracts, not reproduction of a historical coefficient.

## Human review answers

1. **Does active E1/E2 depend on a raw ACLED field?** No. Active projection consumes normalized contracted columns only; a static test rejects known raw ingestion names.
2. **Can unknown absence turn into zero?** No. Structural zero requires an explicit upstream `zero_within_verified_coverage` license and in-support period.
3. **Is every taxonomy selection visibly an experiment choice?** Yes. Selectors are part of `MeasurementProjectionSpec` and the projection report.
4. **Is timing visibly an experiment choice?** Yes. Timing offsets are serialized downstream and resolved with shared period semantics.
5. **Are geography/period incompatibilities blocked?** Yes. Exact shared contract identities are required before projection.
6. **Can we explain how many observations were lost or created?** Yes. Every requested row is retained under one of four statuses and report counts must reconcile to output rows.
7. **Did estimator semantics change?** No. Contracted E2 reuses the existing calibration estimator, gates, placebo, and synthetic signal-recovery functions.
8. **Is there an active legacy ACLED runtime path?** No. The active CLIs have no legacy flag or adapter, active configs do not reference the legacy aggregate, and active CI exercises the contracted path only.
