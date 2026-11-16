# FCV Experiment Harness v0

A deliberately small experimental measurement harness for the FCV spatial-data research project.

The project separates:

- **A — empirical infrastructure**: observations, projects, source surfaces, geography, timing and provenance;
- **B — experiment specification**: treatment, counterfactual, timing, outcome, geography, sample and estimator;
- **C — gates**: checks that say whether the measurement substrate or a candidate experiment is usable enough to proceed.

The governing rule is simple: weak or failed gates are information about the instrument/design, not an invitation to search the specification grid for a better coefficient.

## W5 — integrated China × World Bank VAC experiment (November 2026)

The harness includes the complete optional W5 E0–E4 workflow: source-locked
AidData donor comparison, ADM2×biennium VAC outcomes, fixed-effects inference,
selection diagnostics, country/event influence, and measurement sensitivities.
See [W5_CN_WB_VAC.md](W5_CN_WB_VAC.md) for inputs, runnable commands, exact
historical results, validation gates, and limitations. A compact, machine-readable
[2026-11-15 result index](docs/results/w5_china_wb_vac_20261115.json) is
versioned with the harness, including primary estimates, scientific caveats,
input and private-result SHA-256 references. Raw/source event-level data and
full empirical result files are intentionally **not** distributed in Git.

W5 operates on a **distinct, source-certified panel** from the legacy 2023
DHSGC canonical experiment and the China-only E2 calibration; this is a
dataset/estimand boundary, **not** a separate repository, isolated branch,
or competing experimental framework. Tests run in the normal harness CI.

## W6 — project identity and classification-propagation bridge (November 2026)

The [W6 bridge contract](docs/experiments/W6_JOBS_CLASSIFICATION_BRIDGE.md)
defines project-level labels, a separate project×ADM2×biennium bridge, location
deduplication and exact source-count conservation on the W5 panel. The
[native-sector proxy policy](config/w6_sector_proxy_v0.json) is a preliminary
**screening variable, not a validated direct/indirect jobs annotation**.
All editorial evidence remains explicitly unannotated; source-country
geographic mismatches are retained for W5 parity and separately flagged.
Five synthetic structural tests run in standard CI. Real project-level
derived data stay outside Git with source/output SHA-256 receipts.

## W7 — managed employment classifications and scientific gate (November 2026)

[W7 classification control](docs/experiments/W7_CLASSIFICATION_CONTROL.md)
provides one versioned project-level classification ledger over the full 2,535
China and World Bank projects and an exact project→ADM2×biennium exposure
propagation to the unchanged 44,940-cell W5 panel. Its [native-sector crosswalk](config/w7_native_sector_channels_v0.json)
is **candidate-mechanism metadata**, not observed employment or wages.
The first deterministic real-data release passes cardinality, donor-count
conservation and geographic consistency checks, but has **0 reviewed projects**
and explicitly **prohibits jobs-versus-other inference**. A reviewer must attach
source-qualified evidence and direct/indirect/local-implementation labels before
the scientific contrast can even be screened. W7 tests and the separate
VAC scale audit now run in harness CI; private row-level data remain off Git.

## W7 — frozen sector-proxy screen (November 2026)

The [outcome-blind frozen policy](config/w7_exploratory_jobs_proxy_v0.json),
[bounded 100-project nested quality audit](docs/experiments/W7_FROZEN_PROXY_EXPERIMENT_V0.md),
and [qualified empirical results](docs/experiments/W7_FROZEN_PROXY_RESULTS_20261116.md)
record a completed, deterministic broad/narrow sector-channel experiment.
For interpretation and population denominators see the [scientific synthesis](docs/experiments/W7_ESTIMANDS_POPULATIONS_AND_NULLS_20261116.md),
[discussion brief](docs/experiments/W7_ERIC_DISCUSSION_BRIEF_20261116.md),
and [eight-row coefficient export](docs/results/w7_frozen_proxy_contrasts_20261116.csv).
The native-sector mapping passed all 2,535 project identities; an independent
nested 10→20→50→100 sample found 0/100 definite mapping errors and 2 semantic
ambiguities. Full 44,940-cell W5 regressions were inconclusive. World Bank
broad proxy has thin same-period within-donor support (10 countries, 11 periods).
This is **not a measured employment effect**, and other sectors are not
verified non-jobs. Research-ready data outputs and receipts remain private
and source-hashed outside Git; synthetic tests run in the normal CI.

## W8 — ADM2 J/O/N common-support means (November 2026)

The [frozen scientific contract](docs/experiments/W8_ADM2_JON_SCIENTIFIC_DESIGN_V0.md),
[qualified empirical report](docs/experiments/W8_ADM2_JON_SCIENTIFIC_RESULTS_20261116.md),
and [18-contrast machine-readable index](docs/results/w8_jon_adm2_matched_contrasts_20261116.csv)
define the **J/O/N** three-group country×financing-period comparison:
J = sector-based candidate employment/productivity, O = other-sector,
N = no source-recorded China/WB investment through that period (within covered
2001–2014 history). **Shared J-target country-period weights** yield J−N,
O−N, and J−O = (J−N)−(O−N) on one common matched sample per donor.
China has 128 complete strata/39 countries; WB only 11 strata/10 countries.
The large negative China J−O post-period level difference is **already
present in previous-period VAC**, and is **not** an employment or causal effect.
The code and tests are canonical; private matched records and hashed release
receipts remain off Git.

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
explicit analysis universe + outcome measurement semantics
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

The initial outcome contract uses:

```text
absent_record_policy = unresolved
```

so its expected preflight state is **ESTIMATION BLOCKED**. This is deliberate: complete-case regression must not silently select on observed conflict records.

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

## E1 — analysis universe and ACLED measurement resolution

The real-data preflight showed that `_DHSGC` is a covariate lattice with meaningful source attrition, not automatically a complete ADM2-Africa universe. E1 therefore promotes the analysis universe to an explicit object.

The repository does not yet contain an independent full-ADM2 geography spine, so the production E1 manifest declares:

```text
mode       canonical_lattice
authority  dhsgc_restricted_legacy_2023
```

This means current experiments are explicitly **DHSGC-restricted**. The harness also supports an `external_gid_spine` mode for the later point when a trustworthy full ADM2 spine is recovered; in that mode DHSGC becomes an attached covariate surface with `dhsgc_available` rather than an eligibility requirement.

E1 also resolves the inherited sparse ACLED aggregate semantics explicitly:

```text
policy                    zero_within_verified_coverage
verified period window    1997-1998 through 2021-2022
verified geography scope  analysis_universe
coverage basis             legacy_2023_acled_africa_aggregate_zero_fill
```

An absent ACLED row is converted to zero only inside that declared coverage scope. Raw values, resolved values, record presence, coverage eligibility and resolution status remain separate fields.

Run:

```bash
python tests_analysis_surface.py

python -m fcv_harness.analysis_surface_cli \
  --surface-manifest config/analysis_surface_a2_T2_y2001.json \
  --experiment-manifest config/resolved_wbad_record_acled_vac.json \
  --base-dir . \
  --out-dir out/analysis_surface_a2_T2_y2001
```

The E1 checkpoint emits an `analysis_surface_card.md`, universe/country diagnostics, ACLED measurement audits by period and country, a resolved area-period panel, and a `resolved_preflight/` subdirectory that reruns E0 under the explicit zero-within-coverage policy. E1 still runs **no treatment-effect estimator**.

Its gates are:

```text
U0_UNIVERSE_DECLARED
U1_SOURCE_ATTRITION_QUANTIFIED
A0_ACLED_POLICY_EXPLICIT
A1_ACLED_RESOLUTION_COMPLETENESS
A2_ACLED_STRUCTURAL_ZERO_PROFILE
A3_ACLED_COVERAGE_PROVENANCE
```

`U1`, `A2`, and `A3` may remain YELLOW for scientifically meaningful reasons. `A1` is a hard stop if unresolved or record-present missing outcome values survive inside the declared coverage treatment.

Read `ANALYSIS_SURFACE.md` for the E1 human acceptance guide.

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

The recovered source evidence showed that `_DHSGC.csv` is more accurately treated as the dense covariate lattice, while project exposures and outcomes survive as separate `agg_*` surfaces. New real-data work should therefore pass through canonicalization, universe/outcome resolution, and canonical experiment preflight instead of using source-specific logic inside the legacy estimator adapter.

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
- recovering an independent full-ADM2 geography spine beyond the DHSGC-restricted universe;
- independently rebuilding/validating raw ACLED coverage instead of inheriting the legacy aggregate zero semantics;
- canonical period-varying population processing;
- modern staggered-adoption/event-study estimators;
- spatial-spillover estimators;
- final ACLED count/hurdle model;
- respondent-level Afrobarometer reconstruction.

These are scientific decisions, not cleanup tasks. They should be changed through explicit source/treatment versions so the same gates can be rerun after each improvement.
