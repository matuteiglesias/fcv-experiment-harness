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

The first locked real current-E2 run established:

- analysis identity `8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a`;
- PRIMARY frame SHA-256 `e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f`;
- 47-country treatment-authorized scope;
- PRIMARY hard-gate state `PASS`.

This lets later calibration packets state exactly:

> I tested this scientific frame, produced from these bytes, under this numerical implementation.

The locked run that established those analysis identities used a system SciPy/NumPy combination that emitted a compatibility warning. That does not alter the analysis identity, but its execution identity is not treated as the final clean numerical checkpoint. A supported-environment reproduction should therefore remain part of acceptance.

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

## R2 — bind R1 to the exact current-E2 PRIMARY frame

`config/current_e2_inference_calibration.json` freezes the current real R2 suite against the R0 analysis identity and PRIMARY frame fingerprint above.

`run_current_e2_inference_suite(...)` is intentionally a thin adapter. It accepts an already-executed current-E2 reference result and refuses to run unless all of the following are true:

- the reference lock is verified;
- `reference_id` and PRIMARY cell match;
- PRIMARY hard gates permit estimation;
- the current in-memory PRIMARY frame SHA-256 exactly matches the frozen R0 fingerprint;
- the R0 analysis identity exactly matches the frozen R2 declaration;
- treatment and outcome MeasurementContract identities are unchanged;
- upstream geography/treatment/outcome hashes match the reference identity;
- effect-size grid, repetitions and root seed match the frozen observability declaration.

The adapter then calls the generic R1 kernel **on `primary["frame"]` itself**. It does not reload empirical files, rebuild a panel, create another projection, redefine treatment, or persist row-level analysis data.

The frozen first R2 suite uses the same `[0, .02, .05, .10, .20]` SD grid, 200 outer repetitions and root seed `20260908`. The wild-country bootstrap uses 399 inner Rademacher repetitions.

In addition to the R1 aggregate packet, R2 writes:

```text
inference_calibration/reference_binding.json
```

which records the analysis/execution identities, frame fingerprint, input hashes, measurement IDs, hard-gate state and explicit `reprojection_performed=false` / `reingestion_performed=false` assertions. `reference_run.json` is amended with the same aggregate R2 binding metadata.

The reference CLI exposes this stage through:

```text
--inference-calibration
--inference-config config/current_e2_inference_calibration.json
```

and requires `--reference-lock` when R2 is requested.

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

1. reproduce the locked current E2 reference in a supported clean numerical environment;
2. run the full observability grid on that exact PRIMARY frame;
3. run R2 inference calibration on that same in-memory PRIMARY frame;
4. compare detector power, null size and interval coverage across the declared uncertainty family;
5. only then add influence, deeper falsification, sparse-outcome robustness, or spatial-HAC inference.
