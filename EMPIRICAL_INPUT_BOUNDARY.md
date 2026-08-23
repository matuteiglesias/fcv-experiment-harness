# Contract-backed empirical input boundary

This boundary separates empirical measurement production from scientific use inside the experiment harness.

```text
fcv-empirical-data
      ↓
empirical-data-contracts
      ↓
harness empirical input boundary
      ↓
experiment projection / MeasurementUse
      ↓
design, gates, estimator
```

Source-specific ingestion semantics stop above this boundary. The harness input loader does not need to know ACLED columns, AidData workbook sheets, World Bank response shapes, source download logic, or source-specific precision fields.

## What crosses the boundary

A validated `EmpiricalMeasurementBundle` exposes:

- the durable measurement table and its explicit path;
- the hashed output `DatasetRef` that identifies those exact bytes;
- the upstream `MeasurementContract` describing what was measured;
- the persisted `CoverageContract` describing observed support and row-absence semantics;
- the upstream `RunManifest` recording lineage and materialization authority.

The bundle is a harness-side view over shared contracts, not a new data contract. No upstream Pydantic model is copied or redefined.

## Validation semantics

The loader computes the artifact SHA-256 and resolves exactly one matching `DatasetRef` from `RunManifest.outputs`. It then requires:

- the loaded bytes to match the output hash;
- `MeasurementContract.source_dataset` to appear among the manifest's `DatasetRef` inputs;
- the output `DatasetRef.grain` to equal `MeasurementContract.output_grain`;
- exact `GeographySpec` agreement between output dataset and measurement;
- exact `PeriodScheme` agreement between output dataset and measurement;
- the persisted coverage sidecar to equal `MeasurementContract.coverage`;
- every declared output-grain key to exist in the actual table.

The distinction between the durable output `DatasetRef` and `MeasurementContract.source_dataset` is intentional. In the current shared contract and merged empirical verticals, `source_dataset` identifies the upstream dataset from which the measurement was constructed, while the measurement artifact itself is an output of the run. The harness preserves that lineage rather than inventing another shared model.

## Absence firewall

Loading is not experiment projection. The generic loader never reindexes the measurement lattice, fills missing rows, calls `fillna(0)`, or infers untreated/no-event/no-project states. Sparse rows remain sparse and missing values remain missing.

`CoverageContract.absent_row_semantics` remains visible to later experiment code. Any decision to interpret absence, create structural zeros, select a treatment role, aggregate categories, align timing, or link grains belongs to an explicit experiment projection layer.

## Geography, periods, and grain

`require_same_geography` and `require_same_period_scheme` compare the complete declared shared contracts, not labels that merely look alike. They do not transform geography or resample time.

Different natural grains are not rejected globally. Each bundle must be internally consistent with its own declared output grain, but a future experiment may explicitly link an area-period treatment measurement to respondent- or household-level outcomes. Such linkage must be declared in experiment use; it is not inferred by the loader.

## Scope

This boundary is intentionally small: explicit artifact paths in, validated bundles out. It is not a registry, catalog service, orchestration daemon, legacy compatibility switch, or second empirical-data platform. Existing E1/E2 projections and estimators are unchanged by this seam.
