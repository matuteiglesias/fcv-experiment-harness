# E2 observability instrument

This module turns the existing E2 synthetic-signal check into a reusable detector-characterization run. Its purpose is calibration: given the empirical measurement system and the already-declared E2 design, what injected signal can the instrument recover?

It is not a new substantive estimator and it does not define a new treatment, outcome, geography, or period scheme.

## Reference configuration

The first reference configuration is the fully contracted investment + ACLED E2 design already present in the harness:

- treatment comes from the existing contracted investment measurement projection and downstream treatment derivation;
- outcome is the existing ACLED Violence against civilians fatalities projection at `t+1`;
- the pre-outcome is the existing `t-1` ACLED projection;
- the estimator remains `outcome ~ treatment + pre-outcome + period FE + country FE` with standard errors clustered by the declared analysis unit.

Run the normal fully contracted calibration cell first so all projection and eligibility semantics remain unchanged. Then pass its prepared analysis frame to `run_e2_observability`:

```python
from fcv_harness import run_e2_observability, write_observability_outputs

observability = run_e2_observability(
    calibration_cell["frame"],
    calibration_cell["calibration_spec"],
    effect_sizes_sd=[0.0, 0.02, 0.05, 0.10, 0.20],
    repetitions=200,
    root_seed=20260823,
)

write_observability_outputs(observability, "out/e2_observability")
```

The effect-size grid is supplied by the caller. The example above is illustrative, not a hard-coded grid.

## Monte Carlo semantics

For each repetition the instrument fits the same nuisance structure used by the former one-off E6 check, applies one cluster-level wild residual sign-flip draw, and reuses that draw across every declared effect size. The deterministic injection is

```text
Y* = Y_simulated + delta_sd * SD(Y_observed) * T
```

Pairing the stochastic draw across effect sizes makes adjacent cells differ only by the known injected truth within a repetition.

Every repetition-level row records:

- root seed;
- repetition ID;
- deterministic derived seed;
- injected truth in outcome-SD and raw outcome units;
- estimated effect and standard error;
- 95% interval;
- sign recovery;
- rejection at the existing normal 95% threshold;
- joint sign + rejection recovery;
- CI coverage of the injected truth;
- absolute and relative recovery error;
- sample size, cluster count, outcome SD, and treatment support.

Identical inputs and seed configuration reproduce identical outputs.

## Null calibration

`delta_sd = 0` is a first-class synthetic null. It asks how the detector behaves when the injected treatment truth is exactly zero; it does not rely on claiming that a real social relationship should be null.

The null summary reports rejection rate, the coefficient distribution, positive/negative/zero sign shares, sign balance, and CI coverage around zero.

## Durable outputs

`write_observability_outputs` writes only sanitized result tables:

```text
repetition_results.csv
effect_size_summary.csv
detection_curve.csv
null_calibration_summary.csv
```

The empirical analysis frame is intentionally not written by this function.

The detection curve exposes several dimensions of observability simultaneously: sign recovery, rejection rate, joint detection, interval coverage, median estimate, and interval width. It should not be read as a p-value ranking.

## Extension seam

`run_observability_grid` accepts the estimator as a callback and receives the unit, period, country, outcome, pre-outcome, treatment, and eligibility columns explicitly. This is the intended narrow extension seam for later characterization under another geography scheme, period width, outcome family, or treatment measurement.

No sensitivity grid is implemented here. When the calibration-lab kernel lands, this ordinary input/output module can be adapted to its benchmark runner without introducing a competing benchmark/result abstraction.
