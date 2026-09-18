# Frozen evidence input contract for dossier figures

The dossier renderer consumes **already-generated aggregate evidence**. It must not ingest raw empirical data, rebuild projections, refit substantive models, change eligibility, or search specifications.

## Why this exists

The repository intentionally ignores `out/`, so the real frozen result tables are not available from GitHub. This contract defines the narrow seam between those frozen outputs and publication figures.

## Required source families

Copy/export the frozen aggregate result files into a local directory (for example `dossier_inputs/`). The renderer accepts CSV/JSON inputs and maps them into the following canonical tables.

### F1 — empirical field/support

Required columns:

```
period_id
n_obs
n_treated
n_control
n_units
n_countries
```

### F2 — outcome distribution

One row per outcome representation:

```
outcome_id
label
n
zero_share
mean
sd
p50
p90
p95
p99
max
```

Unknown quantiles may be left blank; they are not imputed.

### F3/F4 — estimate family

```
estimate_id
outcome_id
label
estimator
estimate
std_error
ci_low
ci_high
natural_unit
standardized_effect
```

Raw coefficients with incompatible units must not be plotted on one numerical axis. F4 therefore uses standardized effects only when a legitimate frozen standardized quantity exists; otherwise it renders a table/card comparison.

### F5 — period influence

```
omitted_period
estimate
std_error
ci_low
ci_high
n_obs
```

All frozen period omissions are required. A partial family is rejected.

### F6 — timing falsification

```
diagnostic_id
label
timing_offset
estimate
std_error
ci_low
ci_high
n_obs
```

Expected governed diagnostics include t-1, t-2, and future-treatment timing. Missing governed members are rejected rather than silently omitted.

### F7 — structured null

Summary:

```
observed_statistic
empirical_p_value
sidedness
policy
repetitions
root_seed
```

Draws:

```
repetition
statistic
```

The current frozen policy is `within_country_complete_treatment_history`, with 1,000 repetitions and root seed 20260908. The renderer verifies those declarations but does not regenerate draws.

### F8 — inference/observability calibration

```
method_id
effect_size_sd
repetitions
detection_rate
detection_ci_low
detection_ci_high
sign_recovery_rate
coverage_rate
median_estimate_sd
```

The frozen declared effect-size grid is 0, 0.02, 0.05, 0.10, 0.20 SD with 200 repetitions. Unknown optional diagnostics remain blank rather than being synthesized.

## Fail-closed rules

The renderer refuses to produce a figure when:

- a required family is incomplete;
- values are non-finite where required;
- confidence bounds do not contain the reported estimate;
- treated + control does not reconcile to observations;
- a governed placebo member is missing;
- the structured-null policy/repetition count differs from the frozen declaration;
- the observability effect-size grid differs from the frozen declaration;
- incompatible natural units would be placed on one axis.

This is deliberately stricter than a generic plotting script: missing evidence produces a visible missing figure, never an inferred number.
