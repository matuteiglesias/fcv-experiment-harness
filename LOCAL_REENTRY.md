# FCV local re-entry: first real-data run

The recovered 2023 architecture has two separate GID×TimePeriod surfaces:

1. treatment/covariates, e.g. `africaa2T22001_DHSGC.csv`;
2. outcomes, e.g. `africaa2_T22001.csv`.

The old regression prototype explicitly used:

```text
acled_deaths_violence_against_civilians
```

as a violence outcome. Treat it as a **legacy hello-world outcome**, not yet the final canonical FCV outcome.

## 1. Scan empirical support before selecting a lane

From the empirical-study directory:

```bash
python -m fcv_harness.grid_scan \
  --glob "data/reg_data/*_DHSGC.csv" \
  --out "out/fcv_grid_viability.csv" \
  --treatment-type cnwb_pooled
```

This answers a cheap question first: where do treated/control support and usable time periods actually exist?

## 2. First lane to inspect

Default only until the data gates say otherwise:

```text
geography: ADM2
T: 2 years
y0: 2001
treatment: cnwb_pooled
outcome: acled_deaths_violence_against_civilians
covariate: popsum
```

This is not a final scientific specification. It is the shortest route to an end-to-end real-data calibration run.

## 3. Run the real hello-world experiment

```bash
python -m fcv_harness.panel_cli \
  --panel "data/reg_data/africaa2T22001_DHSGC.csv" \
  --outcomes "data/reg_data/africaa2_T22001.csv" \
  --config "config/legacy_hello_world_acled_vac.json" \
  --out-dir "out/hello_world_adm2_T2_y2001"
```

Read in this order:

1. `outcome_merge_audit.json`
2. `gate_report.md`
3. `support_by_period.csv`
4. `analysis_frame.csv`
5. **only then** `baseline_estimate.csv`

## 4. Interpretation policy

- RED merge/data/support gate → repair data or choose another experiment.
- RED placebo/signal-recovery gate → do not interpret the baseline coefficient as evidence.
- GREEN gates → permission to investigate, not proof of causality.
- Baseline OLS is calibration only.
- Do not add the full historical covariate set until each variable is audited for meaning and treatment timing.
