# FCV empirical evidence dossier

> Working draft. This document reports the frozen current evidence as evidence, not as a software-system narrative.

## Executive empirical reading

The current FCV evidence does not reduce cleanly to a single positive or null treatment-effect statement.

The most defensible reading is a contrast across margins and time. The average fatality-severity estimate is weak and small in standardized terms. Violence incidence and event-count outcomes show a clearer positive signal. The severity result is not temporally stable: period-level influence is materially more important than geographic leave-outs in the current diagnostics. At the same time, timing falsifications are comparatively clean. Finally, the observed severity statistic is not extreme under the current structured permutation null.

Taken together, those facts motivate a narrower interpretation than either "investment causes violence" or "there is no relationship." The frozen evidence is more consistent with a detectable change in the occurrence/frequency margin than with a large stable average increase in fatality severity, while leaving important causal and temporal questions unresolved.

## 1. What is in the empirical field?

The first task is descriptive: establish the actual analysis field before showing a coefficient.

**Frozen headline quantities currently recorded for the dossier**

| Quantity | Current frozen value |
|---|---:|
| ADM2-period observations | 38,520 |
| ADM2 units | 6,420 |
| Countries | 47 |
| Periods | 6 |
| Treated observations | 7,667 |
| Control observations | 30,853 |
| Fatality zero share | 92.22% |

These numbers should ultimately be accompanied by treatment support by period and the full outcome distribution. The zero mass matters directly for interpretation: fatalities are an unusually sparse severity measure, so a comparison with event incidence and counts is substantively informative rather than merely a model-choice exercise.

**Figure F1 — empirical field and support:** pending frozen display extraction.

**Figure F2 — outcome distributions and sparsity:** pending frozen display extraction.

### Measurement qualification

An absent sparse ACLED row is not generically treated as zero. The active measurement boundary distinguishes observed values, structural zeros licensed inside declared coverage, observations outside coverage, and unresolved cases. This distinction is important for the high zero mass above: the dossier should not describe all zeros as directly observed zero-event records.

## 2. Fatality severity: weak average signal

The current canonical fatality result is approximately:

| Metric | Frozen value |
|---|---:|
| Estimated effect | +0.550 fatalities |
| Standard error | 0.458 |
| z-statistic | ~1.20 |
| Standardized effect | +0.0176 SD |

The main empirical fact is magnitude plus uncertainty, not a significance label. In standardized terms the point estimate is small. The observability work also places an effect of roughly this size in a region where the current detector has limited power, so the result is more informative against a moderate or large stable average severity effect than against effects close to 0.02 SD.

This does **not** turn low power into evidence that a small positive effect exists. It means that "weak evidence of a large average severity increase" and "precise evidence of zero severity effect" are different claims, and only the former is supported by the current evidence.

**Figure F3 — fatality severity estimate, uncertainty, and standardized scale:** pending frozen display extraction.

## 3. Incidence and event counts: a clearer signal

The alternative violence outcomes are more visibly positive than the fatality-severity outcome.

| Outcome / estimator | Frozen result | Scale |
|---|---:|---|
| VAC event count, OLS | +0.270 | +0.0549 SD |
| Any VAC, LPM | +2.04 pp | incidence margin |
| VAC event count, PPML | IRR ~1.348 | ~+0.203 events |
| VAC fatalities, canonical | +0.550 | +0.0176 SD |

The important comparison is across outcome families, not across p-values. The frozen evidence suggests that treatment exposure is more clearly associated with whether/how often violence occurs than with the number of fatalities generated.

That pattern admits several possible substantive mechanisms and measurement explanations. The dossier should not choose among them without additional evidence. It should make the margin contrast explicit.

**Figure F4 — outcome-family comparison:** build from frozen estimate table, preserving incomparable units rather than forcing all estimators onto one artificial scale.

## 4. The average hides strong temporal structure

The severity estimate is sensitive to the temporal composition of the sample. In the current leave-period-out diagnostics, removing 2011–12 changes the canonical fatality estimate to approximately **−0.138**.

That movement is scientifically more important than a generic statement that many robustness checks were run. It says that the positive average severity coefficient is not a stable summary across periods.

By contrast, the current country/ADM2 influence diagnostics do not indicate the same degree of single-geography dependence. The appropriate conclusion is therefore not that the result is "robust"; it is that the principal instability detected so far is temporal rather than attributable to one obvious geographic unit.

**Figure F5 — leave-period-out estimates:** must show every frozen period omission with intervals, not only 2011–12.

## 5. Timing falsifications

The frozen timing placebos/future-treatment checks are comparatively clean: the main pattern is not reproduced when treatment is assigned to periods where it should not operate.

These checks weaken simple stories in which the result is generated mechanically by pre-existing timing differences or by assigning future treatment backward. They do not prove the identifying assumptions. Pre-treatment diagnostics can themselves have low power, and their interpretation depends on the estimator and treatment-timing structure.

**Figure F6 — timing falsification family:** show all frozen placebo/future-treatment estimates on one common scale.

## 6. The observed severity statistic is not extreme under the structured null

The current structured-null exercise uses approximately **1,000 within-country complete-history permutations**. The frozen empirical p-value is approximately **0.176**.

This is important negative evidence. Under this reassignment scheme, the observed severity statistic lies inside the range generated reasonably often by the null procedure rather than in an extreme tail.

The inference is deliberately narrow: the observed statistic is **not extreme under this structured null**. The permutation design does not prove a zero treatment effect, and its interpretation is conditional on the exchangeability/reassignment structure encoded by the procedure.

**Figure F7 — permutation distribution:** histogram/density of all frozen draws with the observed statistic marked and the exact empirical p-value/sidedness stated.

## 7. What could the instrument have seen?

The synthetic observability exercise injects known treatment effects while preserving the declared empirical design. The current calibration indicates approximately:

| Injected effect | Detection/power |
|---|---:|
| ~0.02 SD | ~25% |
| ~0.05 SD | ~96% |

The empirical severity estimate, about +0.0176 SD, therefore sits close to the low-detectability region of the current calibration. A 0.05 SD effect is a qualitatively different proposition: the current detector should usually recover a signal of that size.

The useful conclusion is asymmetric. The evidence weighs against a stable severity effect around 0.05 SD much more strongly than it weighs against one around 0.02 SD.

**Figure F8 — full detection curve:** use all frozen injected-effect cells, including the synthetic null, sign recovery, rejection/detection rate, and interval coverage as appropriate.

## 8. Integrated reading

| Proposition | What the frozen evidence says | Qualification |
|---|---|---|
| There is a large stable average increase in fatality severity | Little support | Small effects are poorly resolved |
| Violence incidence/counts increase | Clearer positive empirical signal | Outcome/estimator dependent; causal interpretation remains bounded |
| The severity result is stable through time | No | Period composition materially changes the estimate |
| One obvious geography drives the result | Not indicated by current influence checks | Does not eliminate broader spatial dependence or composition concerns |
| Fake/future timing reproduces the main pattern | Not in current diagnostics | Successful placebos do not establish identification |
| The severity statistic is extreme under the structured null | No; empirical p ~0.176 | Conditional on the permutation scheme |
| A ~0.05 SD severity effect would usually be visible | Yes in current synthetic calibration | Simulation characterizes the detector, not the substantive truth |
| A ~0.02 SD severity effect would usually be visible | No; detection is limited | Failure to detect is correspondingly weak evidence against this magnitude |

## 9. Causal boundary

The dossier should distinguish three layers.

**Observed:** distributions, treatment support, coefficients, temporal influence, placebo estimates, permutation location, and synthetic detector behavior.

**Supported interpretation:** the incidence/count margin is clearer than the fatality-severity margin; the average severity result is temporally heterogeneous; simple timing falsifications do not reproduce the result; and the severity statistic is non-extreme under the declared structured null.

**Not established:** a unique causal mechanism, a stable homogeneous treatment effect, absence of all residual confounding, or a precise zero effect on fatalities.

If the frozen treatment design uses staggered adoption, dynamic/event-study interpretation must respect the actual estimator. Conventional TWFE lead/lag coefficients can be contaminated when treatment effects vary across cohorts or time, so no event-study heuristic should be imported without checking the frozen specification.

## Next build pass

The next pass is mechanical rather than exploratory:

1. extract the complete frozen estimate families behind F1–F8;
2. generate the eight displays without rerunning or tuning substantive models;
3. replace approximate headline values with exact frozen values and intervals;
4. attach figure-level notes describing measurement, inference, and causal scope;
5. move architecture/provenance detail that does not qualify a claim to a technical appendix.
