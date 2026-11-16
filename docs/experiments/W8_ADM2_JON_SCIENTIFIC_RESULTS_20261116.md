# W8 — ADM2 common-support J/O/N comparisons: empirical results and limits
**16 November 2026 · Scientific lead checkpoint · Internal, not sent to Eric**

**Status:** deterministic three-group standardization **DONE**; primary China feasible and descriptively identified, World Bank **THIN**; jobs/wages effect **NOT IDENTIFIED**. W8 fits are a **different target population and estimator** from the existing W7 district-FE sector-proxy benchmark.

## 1. Scientific question and frozen estimand

Within the **same country and financing biennium**, compare ADM2 area-periods with **J** (only China or WB candidate employment/productivity *sector* projects), **O** (only other *sector* projects from that donor), and **N** (no China or World Bank source project recorded **at or before** the financing period within the 2001–2014 panel). Treat donors separately. J/O require the *other* donor absent in that period; both-donor, mixed, unknown and historical-exposure control violations are excluded from the clean matched contrast but retained in the source master. Other financiers and pre-2001 project histories are not observed. A financing period is not implementation start. **J is not a human-reviewed jobs label and O is not verified to create zero jobs.**

Unit: ADM2 × financing biennium, **not person**. Outcome: binary indicator of at least one **subsequent biennium** ACLED violence-against-civilians event. No year-shift sensitivity, ADM3 inference or employment/wage mediator test was performed.

**Exact stratification:** stratum s=(country, financing period). Retain s only if J/O/N all observed. Within eligible s, let n_{g,s} be its ADM2-period group count. We standardize to the eligible **J area-period composition**:

\[
w_s=\frac{n_{J,s}}{\sum_{r\in S}n_{J,r}},\quad
\widehat\mu_g=\sum_{s\in S}w_s\bar Y_{g,s},\quad g\in\{J,O,N\}.
\]

The SAME w_s applies to all three group means. The J mean is the retained-J average; O and N are reweighted to J's country-period distribution. Individual matched cells in group g in stratum s have weight w_s/n_{g,s}.

**Two independent comparisons, three reported differences:**

\[
\widehat\beta_J=\widehat\mu_J-\widehat\mu_N,\qquad
\widehat\beta_O=\widehat\mu_O-\widehat\mu_N,
\]
\[
\boxed{\widehat\Delta_{JO}=\widehat\mu_J-\widehat\mu_O
       =\widehat\beta_J-\widehat\beta_O.}
\]

Algebraic identity holds to machine precision in ALL six completed scenarios. These are standardized descriptive mean differences; they are **not** ordinary W7 fixed-effect regression coefficients or causal ATT estimates, despite the J-target group-composition weighting. Retain prior/source history as a diagnostic.

## 2. Effective samples — *matched*, not full W5 44,940 observations

| Primary scenario | Complete country×period strata | Countries | J ADM2-periods | O ADM2-periods | N ADM2-periods | J-target effective countries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **China** broad, clean N | **128** | **39** | **1,448** | **2,576** | **13,082** | **16.84** |
| **World Bank** broad, clean N | **11** | **10** | **86** | **87** | **484** | **5.26** |

Sample counts are numbers of **area-period cells**, not distinct people, project IDs, or independent treatment assignments. Each country appears in several periods and an ADM2 may change exposure status. WB's sample is a severely selected sliver of 884 candidate-only and 387 other-only WB cells available before triple-overlap matching.

**Effective area-period N after shared weighting** (Kish ESS): China J 1,448; O **83.05**; N 368.82. WB J 86; O **34.37**; N 238.59. **China's top 100 O cells receive 74.59% of all O target-standardized weight; the top ten alone receive 26.55%.** Source record of earlier projects is present for **55.9% of retained China J**, **69.1% China O**, versus **0% clean N**. Thus these observations are not first-time intervention cohorts and lagged VAC may be after past investment. WB earlier-source proportions are 79.1% J and 71.3% O, also far from clean N.

Country × period alone does not match districts on prior violence risk, population, market size, political importance, geography, accessibility, or investment selection; these are major limitations.

## 3. Primary next-biennium VAC outcomes

| Donor | Standardized J mean | O mean | N mean | **J − N** | **O − N** | **J − O** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **China** | **13.54%** | **23.08%** | **13.45%** | **+0.09 pp** | **+9.64 pp** | **−9.55 pp** |
| **World Bank** | **19.77%** | **23.75%** | **13.75%** | **+6.02 pp** | **+10.00 pp** | **−3.98 pp** |

**Uncertainty (exploratory)**: 1,999 country-block resamples, seed 20261116, 2.5/97.5 percentiles; not reliable frequentist coverage for thin WB. Leave-one-country-out (LOCO) ranges also calculated without retuning treatment definitions.

| Contrast | China cluster-bootstrap 95% | China LOCO range | WB cluster-bootstrap 95% | WB LOCO range |
| --- | --- | --- | --- | --- |
| J−N | [−5.32, +4.64] pp | [−0.83, +2.62] | [−4.26, +13.44] | [+3.97, +8.11] |
| O−N | [+2.15, +17.30] pp | [+7.33, +12.47] | [+0.21, +24.46] | [+6.65, +15.83] |
| J−O | [−14.06, −4.87] pp | [−10.52, −8.13] | [−24.15, +6.82] | [−11.02, +1.46] |

A bootstrap interval excluding zero for China J−O is **NOT evidence that J reduces violence**: country-period stratification leaves substantial ADM2 selection/history differences and the following section reveals the differential already existed in the previous outcome.

## 4. Strong scientific falsification of a naive protective interpretation

Use the **same rows and same stratum weights**, but read the pre-existing W5 previous-biennium VAC indicator. This **does not shift the declared future outcome window**. Some areas had past project exposures, so the previous period is not guaranteed true pre-treatment.

| China broad clean-N | Previous-biennium VAC | Subsequent-biennium VAC |
| --- | ---: | ---: |
| J | **10.84%** | **13.54%** |
| O | **20.80%** | **23.08%** |
| N | **11.91%** | **13.45%** |
| J−O | **−9.96 pp** | **−9.55 pp** |
| **Change in J−O gap** | | **+0.41 pp** |

**Interpretation:** the apparently large J–O negative *level* gap almost entirely predates the measured next outcome. It is not a newly created treatment contrast. The matched stratum weights changed neither. This baseline imbalance makes the −9.55 pp number unsuitable as an employment-stabilization effect, regardless of its descriptive uncertainty interval.

For WB, the prior J−O gap was **+13.29 pp** and next J−O is **−3.98 pp**, a large change of **−17.27 pp**; however WB has only **11 complete strata / 10 nominal countries / 5.26 effective weighted countries**, 87 O observations (ESS 34.37), and very high historical exposure. Do **not** interpret its change as a causal or robust mechanism signal.

## 5. Frozen prespecified sensitivity experiments (no new sector cuts)

| Rule / donor | J−N (pp) | O−N (pp) | J−O (pp) | Matched strata, countries | Status |
| --- | ---: | ---: | ---: | --- | --- |
| **Broad + clean N / China** | +0.09 | +9.64 | −9.55 | 128 / 39 | Descriptive; substantial pre-existing gap |
| Broad + period-only N / China | −0.43 | +8.19 | −8.63 | 133 / 41 | N has 29.1% earlier source-project history |
| Narrow + clean N / China | −1.03 | +10.07 | −11.10 | 135 / 41 | Same sector proxy caveat |
| **Broad + clean N / WB** | +6.02 | +10.00 | −3.98 | 11 / 10 | **THIN** |
| Broad + period-only N / WB | +7.10 | +11.08 | −3.98 | 11 / 10 | **THIN**; N has 48.4% earlier donor history |
| Narrow + clean N / WB | +10.82 | +9.17 | +1.64 | 19 / 14 | **THIN** under 20-stratum gate; different treatment composition |

The WB J−O direction is **not even stable across the frozen broad/narrow rules**. China J−N stays near zero across scenarios, but precise equivalence to zero is not demonstrated.

**Alternative strict first-ever-recorded J/O onset design was screened outcome-blind but NOT FIT:** it would retain only 354 Chinese J and 14 WB J cells in complete strata. A causal project-start analysis is a different and severely under-supported estimator for WB; we did not surreptitiously use it.

## 6. Relating W8 to W7 and Eric's proposed matches

| Model | China candidate vs other | What comparison means |
| --- | ---: | --- |
| **W7 broad ADM2/country×period FE (44,940 rows)** | **−0.025 pp** (95% CI [−2.913,+2.862]; p=.986) | Residualized ADM2 within-area & country-specific-time sector comparison; includes mixed/both/zero groups in common panel |
| **W8 broad common-stratum standardized J−O** | **−9.55 pp** (exploratory country-block interval [−14.06,−4.87]) | ADM2 area-period J-target matched **level** means within country×period; only clean triple-support strata, no ADM2 FE |
| **W8 same sample J−O in previous-biennium VAC** | **−9.96 pp** | Pre-existing area-risk difference, timing not necessarily before earlier investments |

W7 and W8 use **different populations, weights, and identifying comparisons**. Their coefficients should not be numerically equal. The divergence warns that simply controlling for country×period or reweighting on J composition is insufficient to eliminate area-level differences in baseline risk. This is why a large negative W8 level difference does not overturn the near-zero W7 FE screen.

Eric's request is a three-group matched **jobs/other/no-investment** program with outcome-aligned samples and direct-vs-indirect labels. W8 is a clean algebraic **ADM2 prototype** with one common support population and auditable source-based N. It **does not yet implement genuine employment labels or a causal matched design**.

## 7. Design decision and stop condition

**Verdict:** W8 common-support algebra, control rules, tests and reproducible descriptive estimation PASS. **Scientific causal/job-impact claim FAIL.** The large J−O level gap is already present in previous VAC; do not report it as an employment effect. Report W8 next to W7 with explicit population and baseline-risk differences. Refrain from adding more heuristic sector variations or moving the outcome window. The next substantive hypothesis test, if commissioned, needs source-grounded employment and implementation evidence and/or a separately preregistered within-area temporal comparison with credible pre-exposure history and better matched baseline covariates. WB should not be promoted to strong inference until support improves.

No email to Eric sent.

## 8. Stable source and receipts

- Frozen scientific protocol: `docs/experiments/W8_ADM2_JON_SCIENTIFIC_DESIGN_V0.md`.
- Canonical code: `fcv_harness/w8_jon_common_support.py`, `scripts/w8_jon_adm2_release.py`, and `scripts/w8_jon_prior_history_audit.py`. Synthetic tests: `tests_w8_jon_common_support.py`, integrated into existing CI.
- Private main immutable release: `/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w8-adm2-jon-20261116-v1/` with input SHA256, aggregated results and two first-scenario matched panels.
- Private outcome-history audit: `.../w8-adm2-jon-prior-history-audit-20261116-v1/` with input SHA256 and aggregate prior/next means. Neither private row-level panels nor sensitive outcome rows are committed to Git.

### Final independent-review gate and release supersession

An independent read-only methods review confirmed the J-target weighting and country-level resampling algebra, but identified two missing fail-closed guards: donor-specific arms were not revalidated against both donor project counts at the W8 boundary, and donor/scenario/control-rule identifiers could be mislabeled by a caller. Both guards and adversarial tests were added to the canonical module. **The reviewer did not diagnose a numerical estimator defect.** The exact six frozen scenario estimates were rerun with both guards active in immutable `w8-adm2-jon-20261116-v1`: every reported contrast matches v0 to better than 1e-12 pp. v0 and its prior-history audit are retained as superseded receipts, not silently overwritten. The `v1` associated prior-history diagnostic reproduces the v0 weighted gaps and changes. The reviewer also requested that the standardization be described as **J-target descriptive**, not a causal ATT.
