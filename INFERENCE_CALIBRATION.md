# FCV Inference Calibration

Purpose: **scientific-instrument calibration**, not specification search and not a new substantive estimator.

The current GeoGCDF → ACLED E2 reference has crossed the ordinary real-data gate sequence. The next question is whether uncertainty statements remain trustworthy at effect sizes much smaller than the original 0.20-SD positive control.

## R0 — exact reference identity

`config/current_e2_reference_lock.json` pins the current canonical upstream bytes and reference config:

- GADM geography artifact SHA-256;
- GeoGCDF commitment-area-period Gold SHA-256;
- coverage-certified ACLED Gold SHA-256;
- canonical E2 config SHA-256;
- PRIMARY cell identity;
- expected 47-country analysis scope size.

When `current_e2_reference_cli` is invoked with `--reference-lock`, it fails closed if those identities change.

Every successful current E2 run now also emits `reference_identity.json` containing two distinct identities:

1. **analysis identity** — config hash, upstream artifact hashes, exact analysis-country list and count, and PRIMARY prepared-frame SHA-256;
2. **execution identity** — the analysis identity plus harness git commit/dirty state and the numerical software environment.

The analysis frame itself is never persisted by this identity mechanism.

This lets later calibration packets state exactly:

> I tested this scientific frame, produced from these bytes, under this numerical implementation.

## R1 — paired inference calibration

The inference kernel compares uncertainty procedures while deliberately holding the estimand fixed:

```text
same OLS design
same point estimate
same known synthetic truth
same stochastic realization
        ↓
only inference method changes
```

The stochastic substrate is shared with the existing observability engine through `simulation_worlds.py`. A fixed repetition/root seed produces the same GID-level Rademacher residual-sign world for every declared effect size. Inference methods are then evaluated on exactly that world.

### First bounded method family

`default_e2_inference_methods(...)` declares:

- `ADM2_CLUSTER` — current canonical ADM2-clustered covariance with normal reference;
- `COUNTRY_CLUSTER_T` — country-clustered covariance with finite-cluster Student-t reference using `G-1` degrees of freedom;
- `WILD_COUNTRY_BOOTSTRAP` — Rademacher wild-country coefficient bootstrap with an unrestricted bootstrap interval and null-imposed zero-effect test.

Conley/spatial-HAC inference is intentionally **not** part of this first stage. It should enter only after governed coordinates and distance semantics exist for the exact analysis units.

### What is measured

For each method × effect size the kernel records internally:

- point estimate;
- standard error / bootstrap standard deviation;
- confidence interval;
- p-value / rejection;
- sign recovery;
- joint sign + rejection detection;
- CI coverage of known truth;
- sample and cluster context.

It asserts that inference methods do not change the OLS point estimate on the same synthetic world.

### Monte Carlo uncertainty

False-positive rates and interval-coverage rates are themselves estimated quantities. The kernel therefore reports Wilson binomial Monte Carlo intervals rather than assigning arbitrary GREEN/RED thresholds such as `false_positive_rate <= 0.06`.

The durable aggregate packet is:

```text
inference_calibration/
    method_summary.csv
    coverage_by_effect.csv
    null_size.csv
    power_by_effect.csv
    ci_width_by_effect.csv
    paired_method_differences.csv
    inference_spec.json
```

The repetition-level table remains available in memory to the caller but is not written by the standard aggregate writer. The empirical analysis frame is never written.

## Interpretation firewall

Do not choose the method with the smallest standard error.

Do not replace the canonical estimator because another inference procedure gives a preferred p-value.

The questions are instead:

- Is nominal 95% interval coverage approximately calibrated under known truth?
- Is the `delta = 0` false-positive rate compatible with the nominal test size once Monte Carlo uncertainty is acknowledged?
- How much precision and power are lost or gained under different defensible dependence assumptions?
- Are method disagreements concentrated at the very small effect sizes the FCV instrument aims to characterize?

A method can be wider and scientifically preferable if its uncertainty is better calibrated. A discrepancy is evidence to understand, not something to tune away.

## Current execution order

1. reproduce the current E2 reference in a supported clean numerical environment;
2. run the existing full observability grid on that exact PRIMARY frame;
3. bind this inference-calibration kernel to the same frozen frame in the current-E2 adapter stage;
4. only then add influence, deeper falsification, sparse-outcome robustness, or spatial-HAC inference.
