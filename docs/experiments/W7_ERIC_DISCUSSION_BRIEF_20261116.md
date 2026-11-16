# FCV / W7 — Scientific briefing for discussion with Eric
**16 November 2026 · Internal draft; NOT SENT**

## Question

Can development projects generating **additional locally paid employment and wage income** plausibly produce later improvements in civilian security in Africa? There are competing channels: local wages/income may stabilize households, while infrastructure, state access, displacement, resource rents and conflict targeting can move violence in either direction.

**Our present data do not observe additional jobs, locally paid wages, or the number of residents affected.** What we can estimate today is a deliberately coarser **project-sector composition** association with subsequent recorded ACLED violence against civilians (VAC).

## Study design

- **Observations:** 44,940 ADM2×financing-biennium cells (6,420 ADM2 units, 47 African countries, seven biennia from 2001–02 through 2013–14). Outcome: at least one **next-biennium** VAC event (2003–04 through 2015–16).
- **Source data:** 1,948 China and 587 World Bank source-qualified projects mapped through 19,588 deduplicated project–area–period exposures.
- **Proxy:** “candidate employment/productivity” sectors (enterprise, physical infrastructure, education/skills) versus other sectors (health/social, governance/finance, humanitarian/environmental/other). A narrower rule excludes skills from candidate. Multiple-channel WB projects and donor overlaps are retained as separate groups.
- **Regression:** district fixed effects + country×biennium fixed effects, 47-country-cluster CR1 standard errors. Main coefficient is **candidate-sector-only areas minus other-sector-only areas, within each donor**, NOT effect against no project, nor a causal jobs impact.
- **Reproducibility:** project-level crosswalk checked for all 2,535; a **single stratified nested 10→20→50→100 review** found **0 clear implementation errors** and **2 semantic ambiguities** (not a proven 0–2% population error bound).

## Main findings — probability of any VAC event in next biennium

| Predeclared comparison | Raw gap: candidate minus other | District/country-time adjusted gap | 95% CI | p |
|---|---:|---:|---:|---:|
| **China — broad (primary)** | +4.78 pp | **−0.03 pp** | [−2.91,+2.86] pp | .986 |
| World Bank — broad | +6.08 pp | **−1.50 pp** | [−6.55,+3.55] pp | .552 |
| China — narrow sensitivity | +2.47 pp | −0.84 pp | [−3.44,+1.76] pp | .519 |
| World Bank — narrow sensitivity | +6.48 pp | −0.44 pp | [−4.37,+3.50] pp | .824 |

**Scientific reading:** neither donor produces a statistically distinguishable sector-composition difference in subsequent VAC. The **raw gaps are positive** but adjusted coefficients are slightly negative and uncertain: composition and selection matter, not proof of stabilization. **World Bank broad overlap is thin**—only 10 countries and 11 country-periods have both compared arms in the same period. China broad has 41 countries and 133 country-periods.

Other checks are consistent with **no clear proxy signal**: China and WB broad event-count asinh contrasts −0.0207 (p=.397) and −0.0085 (p=.843). Prior-biennium VAC checks are also inconclusive and cannot establish exogeneity. The original W5 donor-only contrast, China minus World Bank, was +0.66 pp (CI [−1.70,+3.01], p=.578).

**Denominator and magnitude caution:** overall next-period VAC incidence is **11.65% of ADM2-biennia** (5,235/44,940), with 26,963 recorded VAC events. It is **not 11.65% of people**; one small ADM2 has the same statistical weight as a large one. Resident counts, population-normalized violence, additional worker-months and actual wage exposure are unavailable. A coefficient of −1 pp would concern probability of any event in an **area-biennium**, not a change in people killed or employed.

## Meaning of “employment/productivity has a negative impact minus other sectors”

The phrase should be **rejected as scientifically inaccurate**. The regression subtracts the adjusted VAC-incidence coefficient for *other-sector-only donor areas* from that for *candidate-sector-only donor areas*. A negative number means a **lower modeled area-period event probability relative to another heterogeneous sector bundle**—not a protective effect of new employment. Even the sector distinction is imperfect: hospitals and social programs employ people, while financing or infrastructure may not hire anyone locally.

## Decision and next experimental frontier

**Freeze this deterministic sector-screen as completed and inconclusive.** Do not search for additional favorable category cuts. To test Eric's employment hypothesis, retrieve evidence-bearing original project objectives and implementation narratives, classify **explicit jobs objectives**, **evidenced indirect locally paid work**, **verified other activities**, and **unclear cases**, then predeclare the geographic support/contrasts. To test *wages* as mediator, we additionally need actual local worker-months/wage bills and resident denominators, and must address project siting and exposure timing.

The existing 2,535-project ledger has **zero evidence-reviewed employment labels**, so the wage hypothesis itself remains open. No email to Eric has been sent.

**Technical backing:** [Detailed estimands, populations and interpretation](W7_ESTIMANDS_POPULATIONS_AND_NULLS_20261116.md) · [Original W7 result receipt memo](W7_FROZEN_PROXY_RESULTS_20261116.md) · [Machine-readable contrast table](../results/w7_frozen_proxy_contrasts_20261116.csv). All source and fit SHA-256 receipts remain in the immutable private run directory w7-frozen-proxy-experiments-20261116-r2.
