# FCV / W7 — Scientific synthesis: equations, populations, estimates, interpretation

**Date:** 16 November 2026. **Status:** Internal technical note, not approved for external publication. W5 donor baseline complete; W7 frozen deterministic sector-proxy experiment complete; actual local jobs and wages unmeasured.

> **Finding:** In 44,940 area–biennium observations across 47 African countries, the broad sector-employment-potential contrast in next-period violence against civilians (VAC) is essentially zero for China (−0.025 percentage points, 95% CI [−2.913,+2.862], p=.986). For World Bank it is −1.502 pp (CI [−6.551,+3.548], p=.552), but same-period support is thin. These are observational **sector composition** comparisons, not jobs, wage, or causal estimates.

## 1. Eric's question: mechanism versus current measured variables

The hypothesized process is:

**financed project → local implementation → additional paid local workers / wage income → households, opportunity costs, social stability → later VAC.**

Competing pathways can run in either direction: roads may improve markets or armed-group mobility; contractors may hire nonlocal workers; extraction can generate rents/conflict; employment can displace existing jobs; education and health programs also employ people. A negative adjusted sector coefficient does not isolate the wage channel or prove spillovers.

| Concept | What would be observed | W5/W7 status |
|---|---|---|
| Source-recorded investment | Donor, project, mapped area, financing biennium | **Yes** (source record, not verified labor implementation) |
| Sector composition | Native China/WB sectors and harmonized six-family crosswalk | **Yes** (deterministic; no jobs adjudication) |
| Explicit jobs objective | Evidence from project objectives / source text | **No:** currently zero evidence-reviewed project labels |
| Indirect paid-employment channel | Plausible activity **with source evidence** of locally relevant implementation | **No validated labels** |
| Realized jobs and wages | Local incremental paid worker-months, wage bill | **No** |
| Resident population / working-age adults | Population in each ADM2 in the appropriate year | **Not matched; cannot construct rates** |
| Civilian-targeting outcomes | ACLED next-biennium any VAC, event counts, reported fatalities | **Yes**, within frozen certified coverage |

The World Bank public metadata probe of eight title-selected cases returned keyed records but no full objective text in the inspected fields. For the true employment hypothesis, project objectives / appraisal and completion documents are necessary. This does **not** justify calling a missing-description project a non-jobs project.

## 2. Units, geographical population, time window

**Unit of analysis:** geographic ADM2 area i × financing biennium t. There are **6,420** unique ADM2 units in **47** countries, repeated in **seven** financing biennia from **2001–02 through 2013–14**, giving **44,940** equally weighted area-period rows. The ACLED dependent variable is measured in the **following two-year period** (2003–04 through 2015–16). Prior VAC covers the preceding period (1999–2000 through 2011–12).

We do not know the number of **human residents** represented in each ADM2, and one large city and one small rural ADM2 receive the same observation weight. Thus 44,940 is **not** a population of people. The currently known 2010 GHSL population-raster archive has **not** been linked and checked against all source ADM2 boundaries or the seven years, so no per-capita violence, new jobs per resident, or wage exposure is reported.

**ACLED outcome:** Y(i,t+1) equals 1 if at least one violence-against-civilians event is recorded in ADM2 i in the next biennium; otherwise 0 within certified source coverage. Overall **5,235 / 44,940 = 11.65%** of cells are positive; summed outcome records are **26,963** VAC events and **91,396** reported fatalities. Those numbers are **not** unique people victimized. The top **1%** of area-period cells account for **55.23%** of VAC event-count mass; Somalia, Sudan, DR Congo, Nigeria and Zimbabwe together account for **57.76%** of recorded events. The geographic distribution and unequal human populations matter enormously for interpretation.

## 3. The actual empirical equations

Let a(i) denote ADM2, c(i) its country, and t the financing biennium. Let alpha_i be an ADM2 fixed effect and lambda_(c,t) a country-by-financing-period fixed effect. The common dependent variable is the binary next-period VAC event-incidence indicator.

### W5: donor-only baseline

\[
Y_{i,t+1}=\alpha_i+\lambda_{c(i),t}+\gamma_C\,C^{\mathrm{only}}_{it}+\gamma_W\,W^{\mathrm{only}}_{it}+\gamma_B\,B_{it}+\varepsilon_{it},
\qquad \Delta_{\mathrm{W5}}=\gamma_C-\gamma_W.
\]

Omitted category: **neither China nor World Bank source-recorded in that financing period**, which is not necessarily a never-treated area.

The W5 estimand is gamma_C minus gamma_W, the **adjusted donor-only comparison**, not the effect of either donor versus no investment. W5 estimated **+0.656 pp** (95% CI [−1.699,+3.012], p=.578): no statistically clear donor difference.

### W7: sector-based candidate employment / productivity channel

Every project first receives a source-qualified native-sector → shared-sector mapping. The six families are productive enterprise, physical infrastructure, skills/education, health/social, governance/finance, and humanitarian/environmental/other.

- **Broad candidate set:** enterprise, infrastructure, skills/education. **Broad other-sector set:** health/social, governance/finance, humanitarian/environmental/other.
- **Narrow candidate set:** enterprise, infrastructure. **Narrow other-sector set:** includes education/skills.
- A project whose tags cross both sets is **mixed**. An ADM2-period with one donor is **candidate-only** only when every linked donor project is candidate, **other-only** only when every linked donor project is other-sector; otherwise it is mixed. All cells exposed to both donors are their own arm. This rule never creates evidence-reviewed jobs labels.

Seven-arm fixed-effects linear-probability regression:

\[
\begin{aligned}
Y_{i,t+1}={}&\alpha_i+\lambda_{c(i),t}
+\beta_{C,P}C^P_{it}+\beta_{C,O}C^O_{it}+\beta_{C,M}C^M_{it}\\
&+\beta_{W,P}W^P_{it}+\beta_{W,O}W^O_{it}+\beta_{W,M}W^M_{it}
+\beta_B B_{it}+\varepsilon_{it}.
\end{aligned}
\]

The main **within-donor contrasts** are:

\[
\boxed{\Delta_C=\beta_{C,P}-\beta_{C,O},\qquad
\Delta_{WB}=\beta_{W,P}-\beta_{W,O}.}
\]

Estimation uses ADM2 and country×financing-biennium fixed effects, exact FWL/within-OLS, **CR1 standard errors clustered at country** (47 nominal clusters; reference t-distribution with 46 df). Each binary-coefficient difference is reported in **percentage points**, not percent changes. The design has residualized rank seven.

**What a negative Delta means, exactly:** *conditional on those fixed effects and the other six group indicators*, candidate-sector-only area-periods exhibit a **lower fitted chance of at least one next-biennium VAC event** than other-sector-only area-periods for the same donor. It does NOT say the project prevented violence relative to no project, created local paid employment, reduced the number of affected people, or operated through wages. Nor is this an identified spatial spillover estimate. The comparison is observational and subject to project placement and measurement bias.

For intuition, 1 pp in this model is one VAC-positive **area-biennium** per 100 otherwise comparable area-biennia, not one civilian in 100. The China broad point estimate −0.025 pp corresponds to a near-zero difference in that area-period scale; its interval still allows substantively meaningful positive or negative differences.

### What a genuine wage mediation test would require

The *unobserved* mechanism-level variables would include:

\[
L_{it}=\frac{\sum_{p\in\mathcal P(i,t)}\mathrm{incremental\ locally\ paid\ worker\!-\!months}_{pit}}
{\mathrm{resident\ population}_{it}},\qquad
W_{it}=\frac{\sum_{p\in\mathcal P(i,t)}\mathrm{real\ local\ wages\ paid}_{pit}}
{\mathrm{resident\ population}_{it}}.
\]

A source-grounded intermediate study could compare **explicit employment objectives**, **documented indirect local paid-work channels**, **verified locally implemented other projects**, and **unknowns** without claiming it measures L or W. For any source-supported future design, a new preregistered arm partition, sufficient country-period co-support and implementation timing must be specified. Current sample has **0/2,535** source-evidence-reviewed positive/negative labels; this is a deliberately separate scientific gate, not an unfinished W7 crosswalk.

## 4. Who is represented in the regressions?

**Projects:** 2,535 source-qualified project IDs: **1,948 China**, **587 World Bank**. They expand into **19,588 deduplicated project–area–period links**, not distinct workers or individual implementation sites. Under broad-sector rules the project-level partition is China **1,021 candidate / 927 other / 0 mixed**, World Bank **205 candidate / 80 other / 302 mixed**. World Bank also has 353 projects with multiple native sector channel families; those multi-hot sector memberships must never be counted as separate projects.

### Broad scenario: area-period arms and their raw outcome rates

| Recorded exposure in financing biennium | Area-periods | Distinct ADM2 in arm | Cells with next VAC | Unadjusted next VAC incidence |
|---|---:|---:|---:|---:|
| China candidate-only | 3,334 | 2,364 | 414 | 12.42% |
| China other-sector-only | 3,262 | 1,168 | 249 | 7.63% |
| China mixed | 587 | 399 | 92 | 15.67% |
| WB candidate-only | 884 | 737 | 152 | 17.19% |
| WB other-sector-only | 387 | 369 | 43 | 11.11% |
| WB mixed | 2,401 | 1,683 | 352 | 14.66% |
| Both donors | 1,302 | 813 | 293 | 22.50% |
| Neither donor recorded in period | 32,783 | 6,302 | 3,640 | 11.10% |
| **Total** | **44,940** | **6,420** | **5,235** | **11.65%** |

An ADM2 may appear in different arms in different periods, so **distinct ADM2 counts are not additive**. The 32,783 reference observations could have had exposure outside the source, earlier periods or other donors. Sector assignment is by source and project-count presence, **not** by the amount disbursed, jobs created, or workers hired.

**Geographic caveat:** 814 area-periods contain a China source-mapped project with a recipient-country mismatch. They remain flagged for parity but their local implementation should not be presumed.

## 5. Raw differences are not the regression coefficients

| Contrast | Candidate raw % | Other raw % | **Raw gap** | **Adjusted sector-proxy Delta** | 95% CI | Nominal p |
|---|---:|---:|---:|---:|---|---:|
| **China BROAD: primary** | 12.42 | 7.63 | **+4.78 pp** | **−0.025 pp** | [−2.913,+2.862] | .986 |
| World Bank BROAD | 17.19 | 11.11 | **+6.08 pp** | **−1.502 pp** | [−6.551,+3.548] | .552 |
| China NARROW | 11.85 | 9.38 | **+2.47 pp** | **−0.840 pp** | [−3.440,+1.760] | .519 |
| World Bank NARROW | 17.40 | 10.91 | **+6.48 pp** | **−0.437 pp** | [−4.374,+3.499] | .824 |

The **raw candidate-only cells are more likely to have subsequent recorded VAC** in both donors and both policies. The differences shrink and change sign once persistent geography and country-period composition are absorbed. This is a direct caution against reading *negative adjusted Delta* as a “somewhat negative impact” or wage-mediated stability. It might reflect local targeting, differences in geography, country×time distribution and exposure characteristics. FE reduce some compositional variation but do not identify a counterfactual.

None of these four confidence intervals excludes zero; they also do **not** establish an equivalence-to-zero conclusion. The China broad CI is about ±3 pp around zero relative to the unconditional 11.65% incidence, and the WB broad interval is still wider.

## 6. Robustness and diagnostics: what was actually run

| Check | China | World Bank | Meaning |
|---|---|---|---|
| W5 source donor-only baseline | China minus WB +0.656 pp, p=.578 | same comparison | Neither donor source dominates in the adjusted donor-only baseline |
| W7 broad next-any-VAC, primary | −0.025 pp, p=.986 | −1.502 pp, p=.552 | No clear sector-proxy difference; WB broad support thin |
| W7 narrow next-any-VAC | −0.840 pp, p=.519 | −0.437 pp, p=.824 | No clear sensitivity signal when skills/education changes group |
| W7 broad next-event **asinh(count)** | −0.02065, CI [−0.06924,+0.02793], p=.397 | −0.00847, CI [−0.09432,+0.07738], p=.843 | No clear event-intensity pattern; **not pp** |
| W7 broad **prior** any-VAC | −1.503 pp, CI [−3.664,+0.659], p=.169 | −1.735 pp, CI [−6.545,+3.074], p=.471 | Selection diagnostic, **not** a clean placebo/pretrend test |

**Primary family:** China broad binary next VAC. WB broad is a predeclared companion donor; narrow and alternative outcome are sensitivity, previous VAC is a diagnostic. Do not select a result after looking at its sign or nominal p-value; don't treat eight tests as independent discoveries.

### Geographic overlap / effective empirical population

| Donor and scenario | Candidate-only cells | Other-only cells | Countries with both arms **during at least one same period** | Country×periods supporting both | Support |
|---|---:|---:|---:|---:|---|
| China broad | 3,334 | 3,262 | **41** | **133** | Substantial descriptive co-support |
| WB broad | 884 | 387 | **10** | **11** | **THIN** |
| China narrow | 2,759 | 3,699 | **45** | **144** | Substantial descriptive co-support |
| WB narrow | 776 | 623 | **15** | **20** | Reaches descriptive support threshold |

The outcome-blind methods reviewer specified ≥12 same-period countries and ≥20 country-periods with both arms, plus ≥100 cells per compared arm. The **WB broad comparison fails** despite the full 47 nominal clusters, so its wide coefficient should not carry strong inference. The WB narrow cut reaches that descriptive threshold but remains sensitive to country leverage and unobserved selection.

**Validation completed:** native-sector crosswalk parity for all 2,535 projects; full treatment-count conservation; immutable source/derived SHA-256 receipts; full-rank regression; country-clustered CR1; independent outcome-blind methods and measurement reviews; one **stratified nested 10→20→50→100 audit of 100 total projects**, with **0 clear deterministic errors / 2 substantive title ambiguities**. A stratified 100-project screen does **not** bound the population misclassification probability at 2%.

**Not yet done for this specific frozen W7 contrast:** leave-one-country-out / country influence, source-location restriction, cross-recipient-map sensitivity, causal matching, dynamic event-study pretrends, area-population denominators, explicit local-job creation or wages. Earlier W5 and 14-sector W7 influence checks pertain to **different** estimands and cannot be silently called robustness for this result.

## 7. Scientific interpretation, including what the null means

1. **What we can say:** under these two frozen, transparent sector rules, there is **no statistically distinguishable adjusted difference** in VAC event incidence for either donor. The event-intensity and prior-event checks do not overturn that assessment. China has appreciably better co-support than WB.
2. **What we cannot say:** that actual paid employment has no pacifying effect; that employment causally reduced VAC; that a one-point change means one percent of residents; that other sectors contain no jobs; or that spatial spillovers into neighboring districts have been measured.
3. **Why a signal could be attenuated even if a wage mechanism exists:** the proxies combine very different project activities; projects often do not produce local hires in the finance period; imported workers, implementation delays, mixed projects and weak labor demand dilute treatment; equal ADM2 weighting ignores population; outcome and source geocoding can misalign.
4. **Why a negative sign might occur for reasons unrelated to wages:** targeting, donor-country/country-period composition, infrastructure access, rent and state-presence channels, displacement, pre-existing instability, policy timing. “Minus other sectors” is a **difference between two heterogeneous bundles**, not a negative response of violence to one unit of employment.
5. **Scientific discipline:** do not run new category cuts to hunt a protective beta. If the causal pathway remains important, pivot to defensible source-text employment objectives, realized implementation and population denominator information, with a new preregistered design and explicit identifying assumptions.

### Illustrative wording for Eric (internal; not sent)

> We built a reproducible 47-country ADM2×biennium China/World Bank exposure–VAC panel, harmonized projects into six sector families, and screened a frozen proxy for potential productive/employment channels, with an independent outcome-blind sample audit. In a district and country-period fixed-effects design, the China-only candidate-sector versus other-sector contrast in subsequent civilian-targeting incidence is −0.03 percentage points (95% CI −2.91 to +2.86; p=.99); the narrow cut and event-count checks are also inconclusive. The World Bank comparison is inconclusive and has thin same-period support under the broad definition. Crucially, raw candidate-sector cells have higher violence incidence than the other-sector cells, and these are sector proxies rather than observed locally paid employment. The next scientific decision is whether to obtain project objectives and implementation evidence to distinguish direct jobs, credible indirect local paid work, and verified other activities before testing the employment mechanism.

## 8. Provenance and closure

**Versioned canonical code:** FCV Experiment Harness PR #32, main merge **dd86889**; frozen policy config/w7_exploratory_jobs_proxy_v0.json; existing result memo docs/experiments/W7_FROZEN_PROXY_RESULTS_20261116.md. **Authoritative private W7 result directory:** /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-frozen-proxy-experiments-20261116-r2/ (numeric JSON and SHA receipts). **New companion descriptive-only source:** /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-scientific-synthesis-20261116/w7_descriptive_arm_profiles.json. **W5 reference:** docs/results/w5_china_wb_vac_20261115.json.

There are **no active W7 background experiment processes** at this checkpoint; all planned sector fits finished. **Decision: W7 fixed proxy screen DONE / scientifically inconclusive; keep this null as a stable reference and open a different evidence/denominator task only if necessary.** No email to Eric has been sent.
