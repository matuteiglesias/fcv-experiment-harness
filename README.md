# FCV Experiment Harness v0

A deliberately small experimental measurement harness for the FCV spatial-data research project.

The project separates:

- **A — empirical infrastructure**: observations, projects, source surfaces, geography, timing and provenance;
- **B — experiment specification**: treatment, counterfactual, timing, outcome, geography, sample and estimator;
- **C — gates**: checks that say whether the measurement substrate or a candidate experiment is usable enough to proceed.

The governing rule is simple: weak or failed gates are information about the instrument/design, not an invitation to search the specification grid for a better coefficient.

## Current real-data architecture

The recovered 2023 work contains multiple empirical surfaces that share a `GID × TimePeriod` system. The harness now treats them explicitly as separate inherited objects:

```text
legacy 2023 processing
        ↓
source-specific surfaces
        ↓
HARNESS CANONICALIZATION
        ↓
canonical GID × TimePeriod panel + panel card
        ↓
measurement semantics + E0 eligibility preflight
        ↓
experiment specification
        ↓
experiment gates
        ↓
estimator / falsification / sensitivity
```

The first canonical calibration lane is frozen at:

```text
geography        GADM ADM2 (`a2`)
period length    2 years
alignment        y0 = 2001
annotations      legacy_2023 jobcat values, unchanged
```

The source manifest is:

```text
config/canonical_a2_T2_y2001.json
```

and expects local/linked files under `data/reg_data/`.

## Canonical panel checkpoint

This is the recommended entry point for real FCV data.

```bash
python -m pip install -e .
python tests_smoke.py
python tests_canonical.py

python -m fcv_harness.canonical_cli \
  --manifest config/canonical_a2_T2_y2001.json \
  --base-dir . \
  --out-dir out/canonical_a2_T2_y2001
```

The canonicalizer:

- uses `africaa2T22001_DHSGC.csv` as the dense covariate lattice;
- validates source grains before any collapse;
- keeps ACLED and Afrobarometer as separate sparse outcome/survey surfaces;
- keeps WBad, WBkg and China as separate project-source implementations;
- preserves legacy `jobcat` values exactly as inherited;
- records project-record presence separately from positive `Amount_USD`;
- does **not** fill absent ACLED records with zero;
- does **not** choose treatment/control groups or run a regression.

Generated outputs include:

```text
canonical_panel_card.md
canonical_gates.csv
source_inventory.csv
key_integrity.csv
period_coverage.csv
gid_coverage.csv
column_inventory.csv
project_exposure_profile.csv
wb_source_comparison.csv
covariate_profile.csv
merge_audit.json
source_only_keys.csv
source_outside_lattice_by_country.csv
source_outside_lattice_by_period.csv
canonical_panel_sample.csv
canonical_panel.csv.gz
```

Read `CANONICAL_CHECKPOINT.md` for the human inspection guide and expected real-data sanity counts.

## Canonical-data gates

The checkpoint currently reports:

- `C0_LATTICE_INTEGRITY`
- `C1_SOURCE_KEY_INTEGRITY`
- `C2_SOURCE_COVERAGE_REPORTED`
- `C3_LEGACY_EXPOSURE_STRUCTURE`
- `C4_ACLED_MEASUREMENT_SEMANTICS`
- `C5_WB_SOURCE_COMPARISON`
- `C6_COVARIATE_PROFILE`

Some YELLOW gates are expected. In particular, zero-amount project records, sparse ACLED row presence, differences between the two World Bank source implementations, and source keys excluded by the `_DHSGC` lattice are deliberately exposed rather than silently repaired.

> **Canonicalized does not mean causally validated.** The canonical panel is a measurement substrate from which experiments can be defined and rerun.

## Canonical experiment measurement preflight

Before an estimator sees the panel, treatment and outcome semantics are resolved through an explicit experiment manifest.

The first preflight is:

```text
config/preflight_wbad_record_acled_vac.json
```

Run:

```bash
python tests_experiment_semantics.py

python -m fcv_harness.experiment_preflight_cli \
  --canonical-manifest config/canonical_a2_T2_y2001.json \
  --experiment-manifest config/preflight_wbad_record_acled_vac.json \
  --base-dir . \
  --out-dir out/preflight_wbad_record_acled_vac
```

The current treatment registry intentionally distinguishes:

```text
wbad.record_present       wbad.amount_positive
wbkg.record_present       wbkg.amount_positive
cn.record_present         cn.amount_positive
```

Treatment resolution produces an explicit nullable `treatment`, `eligible`, `treatment_provenance`, and `treatment_measurement_status`. Rows outside the declared experiment window are not silently recoded as controls.

The outcome contract also requires an explicit absent-record policy. The first ACLED manifest uses:

```text
absent_record_policy = unresolved
```

so the expected preflight state is **ESTIMATION BLOCKED**. This is deliberate: ACLED zero-versus-absence semantics must be resolved before complete-case regression can accidentally select on observed conflict records.

The preflight emits:

```text
experiment_preflight.md
input_eligibility.csv
treatment_support_by_period.csv
source_only_keys.csv
source_outside_lattice_by_country.csv
source_outside_lattice_by_period.csv
measurement_frame_sample.csv
experiment_contract.json
```

`E0_INPUT_ELIGIBILITY` reports source/lattice attrition, treated/control support, next-period outcome record/value coverage, and whether the declared measurement policy permits estimation. No coefficient is produced.

Read `EXPERIMENT_PREFLIGHT.md` for the semantic contract and stop rules.

## Authority boundary

For the current wave, the harness primarily **inherits and characterizes** the 2023 processing rather than rebuilding it.

Authority may move upstream later when evidence justifies replacing a legacy step. A future source family can therefore evolve from:

```text
L0  legacy inherited
L1  harness normalized
L2  harness derived
L3  harness rebuilt from upstream/raw data
L4  research-validated processing choice
```

The canonical contracts are designed so a better upstream source can eventually replace a legacy surface without rewriting downstream experiments.

## Spatial project-state experiment lane

The original harness lane remains available for project-location designs inspired by Blair, Marty & Roessler and Briggs.

Its data contract is:

### observations
Required: `obs_id`, `cluster_id`, `obs_year`, selected outcome.
Optional: pre-treatment outcome, covariates, fixed-effect columns.

### projects
Required: `project_id`, `agreement_year`.
Recommended: actual/scheduled start/end year, source status, geolocation precision.

### exposure_links
Required: `obs_id`, `project_id`, `distance_km`.

Run the synthetic demonstration with:

```bash
python examples/synthetic_demo.py
```

or the CSV CLI with:

```bash
python -m fcv_harness.cli \
  --observations path/to/observations.csv \
  --projects path/to/projects.csv \
  --links path/to/exposure_links.csv \
  --config config/example_experiment.json \
  --out-dir run_output
```

The main project-state concepts remain `planned`, `active`, `completed`, `ambiguous`, and `never`; radius, geolocation precision, effective identifying support, selection diagnostics, placebo behavior and synthetic signal recovery are first-class experiment properties.

## Legacy area-period experiment adapter

`fcv_harness.panel_cli` is retained as a compatibility/archaeological adapter. It reflects the earlier reconstruction in which treatment amount columns were expected to be present in the panel and then shifted directly into a calibration regression.

The recovered source evidence showed that `_DHSGC.csv` is more accurately treated as the dense covariate lattice, while project exposures and outcomes survive as separate `agg_*` surfaces. New real-data work should therefore pass through the canonical checkpoint and canonical experiment preflight instead of using source-specific logic inside the legacy estimator adapter.

The existing panel gates and baseline estimator remain useful downstream:

- post-outcome coverage after a declared `t → t+1` shift;
- treated/control support;
- within-period support;
- outcome sparsity;
- pre-treatment balance;
- prior-outcome placebo;
- synthetic signal recovery.

The baseline OLS is calibration only, not the final staggered-treatment estimator.

## Intentionally deferred

- revising the legacy 2023 jobs/non-jobs annotation;
- deciding whether project-record presence or positive amount is the preferred exposure definition;
- reconciling WBad versus WBkg into a preferred World Bank source;
- declaring absent ACLED rows to be structural zeroes;
- canonical period-varying population processing;
- modern staggered-adoption/event-study estimators;
- spatial-spillover estimators;
- final ACLED count/hurdle model;
- respondent-level Afrobarometer reconstruction.

These are scientific decisions, not cleanup tasks. They should be changed through explicit source/treatment versions so the same gates can be rerun after each improvement.
