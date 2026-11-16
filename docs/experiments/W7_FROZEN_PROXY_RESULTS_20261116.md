# W7 — Frozen sector-proxy VAC experiment: first completed empirical read

**Date:** 2026-11-16. **Status:** DONE / qualified exploratory negative screen. **Primary result release:** `w7-frozen-proxy-experiments-20261116-r2` on the private Elements FCV empirical-data run root. A preceding first run (`w7-frozen-proxy-experiments-20261116`) had a reporting bug that overstated countries having both arms in the *same period*, even though its regression coefficients were identical to r2. The immutable first run is superseded, not silently overwritten. All eight coefficient contrasts and p-values match r2 to 1e-12.

## Question, design, and meaning

Eric's hypothesized pathway is local project implementation -> additional paid employment/wages -> income/security -> changes in later violence against civilians. **Neither wages nor worker counts are observed**. This is a reduced-form **sector-based candidate employment/productivity proxy** screen, not a measured employment-jobs treatment effect and not a causal effect. W7 also does not observe project delivery at the timing of its approval/commitment exposure.

Pre-outcome frozen JSON: `config/w7_exploratory_jobs_proxy_v0.json`. Broad candidate set: productive enterprise, physical infrastructure, skills/education; other-sector set: health/social, governance/finance, humanitarian/environment/other. Narrow candidate set: productive enterprise and physical infrastructure; all other categories are comparison. Multi-sector projects crossing sets are ambiguous. These are **other sectors, not confirmed non-jobs**.

Seven mutually exclusive donor/role arms (China candidate-only, China other-only, China mixed, WB candidate-only, WB other-only, WB mixed, both sources), omitting neither-source-recorded as the reference. Full 44,940 ADM2×biennium observations, 6,420 ADM2, 47 countries; ADM2 FE plus country×finance-period FE; country-clustered CR1, nominal t(46). Primary outcome: next-period any VAC; sensitivity: narrow definition; secondary: asinh(next VAC counts); negative-control selection diagnostic: any previous VAC. Only the predeclared within-donor candidate-minus-other contrasts are interpreted. No posthoc category search.

## Quality gate — outcome blind, bounded

Native-sector-to-channel parity mechanically checked in **all 2,535** projects. Independent sampling reviewer then inspected a **nested 10→20→50→100 project** stratified sample, with 100 TOTAL projects. Clear deterministic errors at cumulative stages: 0, 0, 0, 0. Semantic ambiguities: 1, 1, 2, 2, respectively (China 1791: vocational training center; WB P145585: skills for jobs). Sampled source IDs, checks and reviewer result are at `.../w7-blind-rule-audit-20261116/w7_blind_review_result.json`, plus `w7_blind_sample_100_audited.csv`. **PASS as a screening rule**, not verification of employment status; stratified selection cannot estimate the universe's error rate from 0/100. No further audit sampling is needed for v0.

## Exposure support and tallies

Source projects: China **1,948**, WB **587**. Broad **project-level** candidate/other/mixed: China **1,021 / 927 / 0**, WB **205 / 80 / 302**. Broad **donor-exclusive ADM2-period cells**: China **3,334 / 3,262 / 587**, WB **884 / 387 / 2,401**. Both sources **1,302** cells, neither recorded **32,783**. Native WB multi-hot records are never double-counted as separate projects.

Real within-country-period candidate/other co-support: broad China **41 countries / 133 country×periods**; broad WB **10 countries / 11 periods**. Narrow China **45 / 144**; narrow WB **15 / 20**. Pre-outcome reviewer advised a strong-interpretation gate of at least 12 same-period countries AND 20 country-period cells with both arms, plus ≥100 observations per compared arm. Broad WB **fails** that support gate. The narrow WB cut reaches this descriptive gate but remains observational and potentially dominated by influential countries. Model rank = 7 with 47 nominal country clusters for all fits.

## Prespecified estimates

Outcome is subsequent VAC event **incidence**; coefficient units are **percentage-point differences** in area-period probability (NOT percentage change in event counts, casualties, or individuals exposed).

| Experiment, contrast | Difference | 95% CI | Nominal p | Support |
| --- | ---: | --- | ---: | --- |
| **Broad, next any VAC — China candidate minus other** | **−0.025 pp** | [−2.913, +2.862] pp | **0.986** | 41 co-period countries / 133 country-periods |
| Broad, next any VAC — World Bank | −1.502 pp | [−6.551, +3.548] pp | 0.552 | **THIN: 10 / 11** |
| Narrow, next any VAC — China | −0.840 pp | [−3.440, +1.760] pp | 0.519 | 45 / 144 |
| Narrow, next any VAC — World Bank | −0.437 pp | [−4.374, +3.499] pp | 0.824 | 15 / 20 |
| Broad, previous any VAC — China (selection diagnostic) | −1.503 pp | [−3.664, +0.659] pp | 0.169 | Selection/pre-existing violence |
| Broad, previous any VAC — World Bank | −1.735 pp | [−6.545, +3.074] pp | 0.471 | Selection/pre-existing violence |

Secondary next VAC **asinh(count)**: China contrast **−0.02065** (95% CI [−0.06924, +0.02793]; p=0.397), WB **−0.00847** (95% CI [−0.09432, +0.07738]; p=0.843). The asinh unit is not percentage points.

## Interpretation / decision

**No statistically distinguishable sector-proxy contrast** for China or World Bank in the frozen models. This is not evidence that paid employment has no stabilizing effect: sector membership is a noisy proxy for additional local wages, broad WB has thin identifying support, project approval is not implementation, and 95% CIs include meaningful positive and negative differences. Prior VAC contrasts make residual project-selection and pre-existing security differences plausible; no mediator and no credible causal identification have been established. Do not selectively rerun new category cuts seeking a favorable beta.

**Scientific next action:** Only if the research program requires a true employment mechanism, obtain fuller project objectives/activities and create source-supported positive/negative/unknown classes through the canonical W7 ledger (not 120-as-universe), plus implementation intensity and population where possible. The current cheap deterministic screen is complete; do not expand it automatically.

## Provenance, maintenance, and permissions

Canonical source: `fcv_harness/w7_proxy_experiments.py`, `scripts/w7_proxy_experiments.py`, and `scripts/w7_blind_rule_audit.py`, frozen JSON policy and synthetic tests, all in the FCV Experiment Harness repo; CI exercises the tests. Private release receipt: `/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-frozen-proxy-experiments-20261116-r2/w7_proxy_receipt.json`; numeric outputs: adjacent `w7_proxy_results.json`. Frozen native-sector and project-sector ledger from canonical W7, W5 outcome frame unchanged; test result 9 targeted tests for new proxy/audit code, plus 26 W7/W6/VAC-related tests in initial host validation. No label promotion and no email to Eric authorized or sent.
