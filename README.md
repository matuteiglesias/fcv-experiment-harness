# FCV Experiment Harness v0

A deliberately small experimental harness for the FCV spatial-data research project.

The purpose is not to encode the final scientific design. It separates:

- **A — empirical infrastructure**: observations, projects, exposure links, timing/provenance;
- **B — experiment specification**: radius, treatment state, outcome, covariates, fixed effects;
- **C — gates**: checks that say whether a candidate experiment is measurable and interpretable enough to proceed.

This v0 is informed by the methodological implementation in Blair, Marty & Roessler and Briggs:

- project status is evaluated at the observation date;
- `planned`, `active`, `completed`, and `ambiguous` are preserved explicitly;
- the main baseline contrast is `completed - planned`;
- exposure radius is an experiment parameter, not a hard-coded fact;
- project geolocation precision is preserved;
- effective identifying support is reported, not just raw row count;
- selection diagnostics, placebo behavior, and synthetic signal recovery are first-class outputs.

## Data contract

### observations
Required: `obs_id`, `cluster_id`, `obs_year`, selected outcome.
Optional: pre-treatment outcome, covariates, fixed-effect columns.

### projects
Required: `project_id`, `agreement_year`.
Recommended: actual/scheduled start/end year, source status, geolocation precision.

### exposure_links
Required: `obs_id`, `project_id`, `distance_km`.

## Quick start

```bash
python examples/synthetic_demo.py
```

Produces:
- `examples/demo_gate_report.md`
- `examples/demo_bandwidth.csv`

## Intentionally deferred
- final jobs/non-jobs annotation;
- canonical WB/China ingestion;
- project amount allocation over multiple locations;
- modern staggered-adoption/event-study estimators;
- spatial-spillover estimators;
- final ACLED count model.


## Run on canonical CSVs

```bash
python -m fcv_harness.cli \
  --observations path/to/observations.csv \
  --projects path/to/projects.csv \
  --links path/to/exposure_links.csv \
  --config config/example_experiment.json \
  --out-dir run_output
```

The run emits:

- `analysis_sample.csv`
- `baseline_estimate.csv`
- `bandwidth_sweep.csv`
- `gate_report.md`

This is the intended interface for connecting the recovered FCV data without moving production logic back into notebooks.


## Recovered FCV area-period panel lane

The 2023 FCV preprocessing pipeline already created `GID × TimePeriod` CSVs for
`T = 2, 3, 4` and `y0 = 2000, 2001`. The panel lane deliberately consumes those outputs
instead of rebuilding the historical notebooks first.

Treatment definitions reconstructed from the old matching code:

- `cnwb_pooled`: `wbad_amount_usd + cn_amount_usd > 0`
- `wb_only`: World Bank amount > 0 and China amount == 0
- `cn_only`: China amount > 0 and World Bank amount == 0

The v0 temporal contract is explicit:

```text
treatment in period t
        ↓
outcome in period t+1
```

with `outcome(t-1)` retained for balance/placebo checks.

Run:

```bash
python -m fcv_harness.panel_cli \
  --panel "data/reg_data/africaa2T22001_DHSGC.csv" \
  --config config/legacy_panel_example.json \
  --out-dir out/legacy_adm2_T2_y2001
```

Before running a real outcome, replace `REPLACE_WITH_VIOLENCE_OUTCOME_COLUMN` in the config
after inspecting `column_profile.csv` or the source schema. The harness intentionally refuses
to guess which historical violence column is the scientific outcome.

Panel outputs:

- `column_profile.csv`
- `analysis_frame.csv`
- `support_by_period.csv`
- `gates.csv`
- `gate_report.md`
- `baseline_estimate.csv`

Panel gates:

- panel uniqueness/integrity;
- post-outcome coverage after t→t+1 shift;
- treated/control support;
- within-period support;
- outcome sparsity;
- pre-treatment balance;
- prior-outcome placebo;
- synthetic signal recovery.

The baseline panel OLS is a calibration estimator only. A mature staggered-adoption/event-study
lane should use an estimator designed for heterogeneous treatment timing rather than naïve TWFE.


## Scan the whole legacy experiment grid first

Before selecting an ADM/T/y0 specification, scan the recovered CSV grid:

```bash
python -m fcv_harness.grid_scan \
  --glob "data/reg_data/*_DHSGC.csv" \
  --out out/grid_viability.csv \
  --treatment-type cnwb_pooled
```

If the violence outcome column is already known:

```bash
python -m fcv_harness.grid_scan \
  --glob "data/reg_data/*_DHSGC.csv" \
  --out out/grid_viability.csv \
  --treatment-type cnwb_pooled \
  --outcome YOUR_OUTCOME_COLUMN
```

The scanner reports, per file:

- admin level, T, y0 parsed from filename;
- rows, units, periods and duplicate unit-periods;
- treated/control counts for pooled/WB-only/CN-only;
- periods with genuine treated/control overlap;
- minimum treated/control support inside usable periods;
- explicit outcome missingness/sparsity when supplied;
- candidate violence-like numeric columns for inspection;
- a rough viability score used only for ranking where to look first.

The ranking score is not a statistical result. It is a cheap way to avoid spending research time
on configurations that have no empirical support.


## Legacy outcomes are a separate table

The recovered regression prototype did **not** assume that `*_DHSGC.csv` already contained the outcome.
Use `--outcomes` to attach the corresponding outcome surface by strict `GID × TimePeriod` keys.

The first grounded legacy calibration config is:

```text
config/legacy_hello_world_acled_vac.json
```

with:

- outcome: `acled_deaths_violence_against_civilians`
- treatment: `cnwb_pooled`
- first explicit covariate: `popsum`

This recovers the old project's empirical vocabulary without treating it as the final scientific design.
The CLI writes `outcome_merge_audit.json` and adds `P0_OUTCOME_MERGE_COVERAGE` before the other panel gates.
