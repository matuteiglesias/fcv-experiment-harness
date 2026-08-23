# DHS commissioning — Calibration Lab integration handoff

Status: consumer-driven integration audit for the first DHS commissioning benchmarks. This document follows the candidate research in `dhs_commissioning_candidates.md` and the public API introduced by Calibration Lab PR #13 (`feat/calibration-lab-kernel`).

This is not a substantive FCV result and does not contain DHS microdata.

## What became available

PR #13 exposes the intended source-agnostic kernel surface:

- `CalibrationBenchmarkSpec`
- `CalibrationEmpiricalInputSpec`
- `CalibrationBenchmarkKind.COMMISSIONING`
- `RecoveryLevel.QUANTITATIVE`
- explicit adapter IDs and adapter callables
- contract-backed loading through `EmpiricalMeasurementBundle`
- sanitized `PASS` / `YELLOW` / `FAIL` / `NOT_RUN` outputs

This is the correct abstraction to target. No competing benchmark/spec model is needed.

## First consumer finding: the benchmark needs two different upstream facts

Nigeria 2018 national household electricity is intentionally simple scientifically:

```text
registered semantic fact: HV206 -> dhs.household.electricity_access
survey-design fact:       HV005 -> source household sample weight
join identity:            source_row_id
published target:         59.4% yes, FR359 Table 2.4 p.26
```

The current DHS empirical boundary correctly keeps those facts separate:

- the semantic household measurement table contains `source_row_id`, `survey_id`, `measurement_id`, source/normalized values, status, and codebook provenance;
- HR Silver retains `source_household_weight` and every source-native field;
- `iter_dhs_hr_design_records` exposes the source weight as `SurveyDesignRecord` without choosing an estimator design;
- the semantic registry deliberately does not assign a scientific role to `HV005`.

The commissioning adapter therefore must consume both the semantic measurement and the source-native design fact. It must not solve the problem by adding a fake `dhs.household.weight` semantic measurement merely for convenience.

## Current kernel seam that blocks a real run

`CalibrationEmpiricalInputSpec` currently resolves every declared input through `load_empirical_measurement(...)`. That loader requires:

1. a data artifact;
2. one persisted `MeasurementContract` JSON object;
3. one persisted `CoverageContract` JSON object;
4. one upstream `RunManifest`.

The rebuilt DHS artifacts do not currently line up with that shape in two important ways.

### A. DHS semantic materialization persists a contract collection

`materialize_dhs_household_measurements(...)` emits one table containing all selected registry measurements and persists:

```text
contracts/dhs_household_measurements.json
```

as a JSON **array** of `MeasurementContract` objects — one contract for each registered measurement. `load_empirical_measurement(...)` validates its path directly as one `MeasurementContract` object.

The table itself is perfectly selectable by `measurement_id`; the persistence shape, not the science, is the mismatch.

### B. HR Silver/design facts are not a MeasurementContract-backed measurement

HR Silver is a source-native `DatasetRef` + `RunManifest` product. It preserves:

```text
source_row_id
survey_id
source_weight_variable
source_household_weight
HV012
HV025
...
```

and exposes survey design records, but it is intentionally **not** a semantic measurement product. Therefore the current `CalibrationEmpiricalInputSpec` cannot declare it as a second calibration input without manufacturing a downstream `MeasurementContract` that upstream never asserted.

That would weaken the empirical boundary and should not be the integration strategy.

## Minimal capability the consumer needs

The kernel should remain source-agnostic. The DHS benchmark only needs a generic way to declare an auxiliary contract-backed empirical dataset in addition to measurement inputs.

Conceptually one of these equivalent shapes is sufficient:

```text
CalibrationMeasurementInputSpec
    -> current EmpiricalMeasurementBundle validation

CalibrationDatasetInputSpec
    -> data artifact + DatasetRef resolved from RunManifest
    -> no MeasurementContract required
```

or a single input spec with an explicit generic input kind / loader policy.

The important invariants are:

- the loaded data artifact must still match a hashed `DatasetRef` in the upstream `RunManifest`;
- declared dataset identity/grain must still be checked;
- source paths and protected rows must remain absent from persisted calibration outputs;
- the calibration kernel must not learn DHS-specific variable names;
- the adapter, not the kernel, owns the `source_row_id` join and the statement that `source_household_weight` is required for this benchmark.

A second small compatibility improvement would allow a caller to select one `MeasurementContract` from an upstream persisted contract collection by `measure_id`, or otherwise consume the canonical per-measurement contract representation once one exists. This should be solved generically; no DHS special case is needed.

## Native `CalibrationBenchmarkSpec` mapping once that seam exists

The first benchmark maps cleanly onto PR #13's API. The following is illustrative of the **actual kernel fields**; the auxiliary dataset input is the one currently unrepresentable part.

```json
{
  "benchmark_id": "dhs.ng2018.household_electricity.national",
  "title": "Nigeria 2018 national household electricity",
  "purpose": "calibration",
  "kind": "commissioning",
  "description": "Recover the published weighted national share of DHS households with electricity from the rebuilt DHS household measurement system.",
  "empirical_inputs": [
    {
      "input_id": "electricity_measurement",
      "data_path": "<local materialized DHS household-measurement artifact>",
      "measurement_contract_path": "<selected HV206 MeasurementContract>",
      "coverage_contract_path": "<matching HV206 CoverageContract>",
      "run_manifest_path": "<semantic-measurement RunManifest>",
      "dataset_id": "surveys.dhs.hr_household_measurements",
      "measurement_use": {
        "measure_id": "dhs.household.electricity_access",
        "selectors": {
          "measurement_id": "dhs.household.electricity_access"
        },
        "value_column": "normalized_numeric_value",
        "role": "calibration_observation"
      }
    },
    {
      "input_id": "hr_design",
      "INPUT_KIND_NEEDED": "contract-backed dataset without fabricated MeasurementContract",
      "dataset_id": "surveys.dhs.hr_households"
    }
  ],
  "reference_behavior": {
    "authority": "The DHS Program",
    "publication_id": "FR359",
    "table": "2.4 Household characteristics",
    "page": 26,
    "cell": "Electricity / Yes / Households / Total",
    "expected_percent_yes": 59.4,
    "expected_percent_no": 40.6
  },
  "acceptance_level": "level_3_quantitative",
  "adapter_id": "dhs_weighted_household_share",
  "parameters": {
    "survey_id": "dhs-NG2018DHS",
    "join_key": "source_row_id",
    "weight_column": "source_household_weight",
    "expected_source_weight_variable": "hv005",
    "missing_policy": "exclude missing from numerator; retain its weight in denominator",
    "render_decimals": 1
  },
  "notes": [
    "Raw HV005 and HV005 divided by 1,000,000 differ by a common scalar and therefore give identical percentages.",
    "Never tune implementation to force the published cell; explain discrepancies first."
  ],
  "limitations": [
    "Execution requires an authorized local Nigeria 2018 HR release and release-specific validation of HV206 semantics."
  ]
}
```

The placeholder `INPUT_KIND_NEEDED` is deliberately not committed as an executable spec. It marks the single kernel seam that must exist before this becomes a valid native spec.

## Adapter behavior for the first benchmark

Once both inputs are available through the kernel, `dhs_weighted_household_share` should remain small and deterministic:

1. require one explicit survey identity in both inputs and require the configured survey ID;
2. select exactly the declared semantic `measurement_id`;
3. require one semantic row per selected `source_row_id` and one matching HR row;
4. verify the HR design envelope reports `HV005` as the source household weight variable for the release-specific mapping;
5. parse weights numerically and fail/diagnose missing, invalid, or non-positive weights rather than silently repairing them;
6. classify observed yes/no/missing from the semantic measurement status/value, never from historical notebooks;
7. compute
   `100 * sum(weight for yes) / sum(weight for all table-population households)`;
8. retain source-missing household weight in the denominator and outside the yes/no numerators;
9. report the unrounded estimate, one-decimal rendered estimate, denominator weight, missing-weight share, row counts, and discrepancy from the published cell;
10. pass Level 3 when the independently computed estimate rounds to the published one-decimal cell, subject to a tiny numerical epsilon.

This adapter should not know how to find DHS files, register snapshots, construct HR Silver, or infer survey identity from filenames. Those remain upstream responsibilities.

## Why not solve this upstream immediately

This research branch treats `fcv-empirical-data` as read-only scientific context. More importantly, the observed need is generic: calibration sometimes requires a semantic measurement plus auxiliary source/design facts. Pushing `HV005`, `HV012`, or `HV025` into the semantic registry solely because the current harness loader accepts only measurements would turn a consumer limitation into upstream semantic pollution.

The first move should therefore be to make the Calibration Lab empirical-input seam capable of consuming an already contract-backed auxiliary dataset without pretending it is a measurement.

## Next executable milestone

After the generic auxiliary-dataset seam is available:

1. add the native Nigeria 2018 electricity JSON spec;
2. add the small `dhs_weighted_household_share` adapter;
3. test it with synthetic household rows only;
4. verify missing-value denominator behavior adversarially;
5. verify common-scalar weight normalization invariance;
6. run locally against the authorized Nigeria 2018 HR release;
7. persist only aggregate diagnostics, contract identities, hashes, and recovery status.

Water-source and wealth benchmarks should wait behind this first executable commissioning path. Electricity exercises the most important shared boundary with the fewest moving parts.