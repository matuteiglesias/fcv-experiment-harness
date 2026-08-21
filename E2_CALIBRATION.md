# E2 — WB→ACLED measurement calibration matrix

E2 is the first checkpoint allowed to produce real treatment-effect calibration coefficients, but only after the declared hard gates pass.

It is **not** a model-selection exercise. The four cells are predeclared measurement variants of the same substantive WB→ACLED question.

## Frozen matrix

```text
                         record_present     amount_positive
WBad / AidData              PRIMARY             STRESS
WBkg / alternate            PRIMARY             STRESS
```

All four use the same:

```text
analysis surface     E1 DHSGC-restricted ADM2 universe
period length        T = 2 years
alignment            y0 = 2001
treatment window     2003-2004 through 2013-2014
outcome              ACLED deaths: violence against civilians at t+1
ACLED semantics      zero_within_verified_coverage
annotation           legacy_2023
extra covariates     none
```

The calibration regression is:

```text
VAC[g,t+1]
    ~ treatment[g,t]
    + VAC[g,t-1]
    + period FE
    + country FE
```

with standard errors clustered by `GID`.

No period is dropped because a measurement definition has poor support. In particular, the known WBad `amount_positive` collapse in `2013-2014` remains in the declared window and should appear explicitly in `support_by_period.csv`.

## Gates

Each cell runs:

```text
E0_INPUT_UNIVERSE
E1_TREATMENT_SUPPORT
E2_WITHIN_PERIOD_SUPPORT
E3_OUTCOME_SPARSITY
E4_PRE_OUTCOME_BALANCE
E5_PRE_OUTCOME_PLACEBO
E6_SYNTHETIC_SIGNAL_RECOVERY
```

Hard gates are E0, E1, E2, E3 and E6. A RED hard gate blocks the real calibration coefficient for that cell.

E4 and E5 are interpretation diagnostics. They may be RED without hiding the calibration coefficient: the point of this checkpoint is to expose whether measurement choices inherit obvious pre-treatment imbalance or placebo behavior, not to search for a better-looking specification.

### Correct placebo

The placebo is deliberately:

```text
VAC[g,t-1] ~ treatment[g,t] + period FE + country FE
```

It does **not** put the pre-outcome on both sides of the regression.

### Synthetic signal recovery

E6 first fits the nuisance structure without treatment, then performs GID-level wild residual sign flips, injects a known `0.20 SD` treatment signal, and asks whether the same calibration estimator recovers its sign with `|z| >= 1.96`.

This is calibration of detectability. It is not evidence that a real treatment effect exists.

### Detectability scale

For every estimated cell, `measurement_stability.csv` also reports:

```text
outcome_sd
effect_sd
95% coefficient interval
mde80_raw_approx
mde80_sd_approx
```

The approximate 80% minimum-detectable effect uses `2.80 × clustered SE` and is shown both in raw VAC deaths and outcome-SD units. It is a compact way to distinguish an unstable point estimate from an effect that is simply much smaller than the current design can resolve.

### WBad / WBkg treatment agreement

`wb_measurement_agreement.csv` compares the two WB source surfaces over the exact declared treatment window for both `record_present` and `amount_positive`.

For every period and overall it reports:

```text
both treated
WBad only
WBkg only
neither
treated union
Jaccard among treated cells
exact agreement share
```

This is a measurement diagnostic only. It does not reconcile the two sources or choose a preferred one.

## Run

```bash
python -m pip install -e .

python tests_smoke.py
python tests_canonical.py
python tests_experiment_semantics.py
python tests_analysis_surface.py
python tests_country_identity.py
python tests_calibration.py

python -m fcv_harness.calibration_cli \
  --matrix-manifest config/wb_acled_calibration_matrix.json \
  --base-dir . \
  --out-dir out/wb_acled_calibration
```

## Read in this order

1. `calibration_matrix_card.md`
2. `measurement_stability.csv`
3. `wb_measurement_agreement.csv`
4. `cell_gates.csv`
5. `cells/wbad_record_present/support_by_period.csv`
6. `cells/wbkg_record_present/support_by_period.csv`
7. `cells/wbad_amount_positive/support_by_period.csv`
8. `cells/wbkg_amount_positive/support_by_period.csv`
9. each cell's `placebo.csv` and `signal_recovery.csv`
10. only then each cell's `estimate.csv`

The intended primary table is `measurement_stability.csv`, not a ranking of p-values.

## Interpretation rule

The primary scientific question at this stage is:

> Does the empirical signal and the validity profile remain reasonably stable when the same WB exposure is measured through WBad versus WBkg?

Read the point estimates jointly with treatment agreement and the approximate detectable-effect scale. A sign difference between two imprecise estimates is not, by itself, evidence of contradictory causal effects; it may instead reflect source disagreement plus effects that are below the resolution of the current calibration design.

The `amount_positive` cells are stress tests of the inherited amount-based treatment proxy. They are not promoted over record presence because they happen to produce a more attractive coefficient.

After E2, the next decision should be based on the **joint pattern** of source stability, support, source agreement, placebo behavior and signal recovery. More sophisticated estimators should only be added after we know which empirical object is worth estimating.
