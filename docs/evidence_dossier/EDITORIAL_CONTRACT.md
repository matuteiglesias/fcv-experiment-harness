# FCV empirical evidence dossier — editorial contract

## Purpose

This dossier is a data-first account of the frozen current FCV evidence.

It is not a repository tour, a pipeline report, or an argument engineered around a preferred treatment-effect result. Its job is to make the empirical pattern legible, including tension and negative evidence.

## Scientific story to preserve

The current evidence should be organized around five jointly visible facts:

1. the average fatality-severity signal is weak;
2. violence incidence/count outcomes show a clearer positive signal;
3. the severity result is strongly heterogeneous across time;
4. timing/placebo diagnostics are comparatively clean;
5. the observed severity estimate is not extreme under the structured permutation null.

These facts are not to be collapsed into a binary "effect / no effect" conclusion.

## Claim discipline

Every substantive claim must travel with the evidence that qualifies it.

- Positive-looking estimates travel with uncertainty, temporal sensitivity, falsification evidence, and the structured null where relevant.
- Weak or null-looking estimates travel with detectability/power evidence.
- Timing placebos are diagnostics against specific timing stories; they do not establish identification.
- Measurement validation establishes properties of the measurement system; it does not establish causal validity.
- Observability simulations characterize what the detector can recover under declared injections; they are not substantive FCV effects.
- A non-extreme permutation result is negative evidence about extremeness under that reassignment scheme, not proof of a zero effect.
- No result is upgraded or downgraded because it is statistically convenient.

## Main-text order

### 1. Empirical field
What units, periods, treatment support, and outcome distributions are actually present?

Required displays:
- analysis-unit / country / period counts;
- treated/control support by period;
- zero mass and upper-tail summaries for fatalities and event counts;
- a compact description of the treatment measurement.

### 2. Measurement reality
What exactly counts as an observed event, structural zero, treatment exposure, and eligible observation?

Keep only measurement facts necessary to interpret later figures. Detailed contracts and repository architecture belong outside the narrative.

### 3. Severity
Show the canonical fatality estimate in raw and standardized units with uncertainty.

Interpretation target: whether the frozen evidence supports a large, stable average change in fatality severity.

### 4. Incidence and counts
Place alternative outcome families beside severity:
- event count;
- any-event incidence;
- count-model result where available.

Interpretation target: determine whether the empirical pattern is more visible on the extensive/count margin than on fatality severity.

### 5. Temporal anatomy
Show period-specific or leave-period-out evidence before generic robustness tables.

The reader should be able to see whether the average estimate is stable or whether particular periods materially change it.

### 6. Timing falsification
Show pre-treatment/future-treatment/placebo timing results as a family, not selected examples.

State exactly what alternative explanation each diagnostic probes.

### 7. Structured null
Plot the complete permutation/null distribution and mark the observed statistic.

Report the reassignment scheme, number of draws, statistic, sidedness, and empirical p-value. The visual must make extremeness—or lack of it—immediately visible.

### 8. Observability
Show synthetic null behavior and the detection curve for declared effect sizes.

Connect the magnitude of the empirical severity estimate to the calibrated region of detectability without treating low power as evidence for an effect.

### 9. Integrated reading
End with a claim matrix, not a verdict:
- proposition;
- evidence;
- what the evidence supports;
- what remains unresolved.

## Figure contract

Main-text figures should be few and information-dense.

F1 — Empirical field and support.
F2 — Outcome distributions / sparsity.
F3 — Severity estimate with uncertainty and standardized magnitude.
F4 — Severity versus incidence/count outcome family.
F5 — Temporal heterogeneity / influence by period.
F6 — Timing placebo family.
F7 — Structured permutation null with observed statistic.
F8 — Observability / detection curve.

If a figure cannot be traced to frozen evidence, it is not silently approximated. It remains explicitly pending.

## Table contract

T1 — Analysis sample and support.
T2 — Main outcome-family estimates.
T3 — Temporal/influence diagnostics.
T4 — Falsification and structured-null diagnostics.
T5 — Measurement/observability qualification matrix.

Large estimator grids and repository-level diagnostics go to appendices.

## Language rules

Prefer:
- "the estimate is small relative to..."
- "the incidence/count signal is clearer than the fatality-severity signal"
- "the average masks substantial temporal heterogeneity"
- "the timing falsifications do not reproduce the main pattern"
- "the observed statistic is not extreme under this structured null"

Avoid:
- "no effect" from failure to reject;
- "causal" solely from placebo success;
- "robust" when a key period materially changes the estimate;
- "significant" as a synonym for scientifically important;
- architectural achievements as empirical evidence.

## Causal boundary

The dossier may document evidence consistent or inconsistent with particular identifying stories. It must not convert diagnostic success into proof of identification.

If treatment timing is staggered, dynamic/event-study displays require estimator-specific care because conventional TWFE leads/lags can mix heterogeneous cohort effects. The dossier should therefore describe the actual frozen estimator before applying event-study visual heuristics.

## Build rule

The dossier is downstream of frozen evidence.

No analysis choice may be changed in order to improve the narrative. If a missing display requires a new substantive estimate, mark it as a proposed extension rather than silently incorporating it into the frozen dossier.

## Definition of done for v1

A v1 dossier is complete when:

- every headline empirical statement has a frozen numeric/display backing;
- severity, incidence/counts, temporal heterogeneity, timing falsification, structured null, and observability are all visible in the main narrative;
- measurement and causal qualifications sit beside the claims they qualify;
- no main-text section is organized around repository architecture;
- negative and ambiguous evidence are as easy to see as positive evidence;
- the synthesis can be read without assigning a binary treatment-effect verdict.
