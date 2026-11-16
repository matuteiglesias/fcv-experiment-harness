# FCV Research Workgraph — Jobs-oriented investment and stability feasibility

**ID:** `FCV-RG-JOBS-STABILITY-20261116`  
**Created:** 2026-11-16 (Scientific Council)  
**State:** **QUEUED / NOT EXECUTING** · **Dispatch:** manual pull only  
**Lead:** Amara (Africa Observatory) · **Support:** Tomás (data engineering), Lucía (spatial measurement) · **Independent referee:** Ruth.

**Machine-readable plan:** [`workgraphs/jobs_stability_identification_feasibility_v0.json`](../../workgraphs/jobs_stability_identification_feasibility_v0.json). This is **planning metadata**, not an executable harness manifest or scheduled job. It must not be confused with W5–W8 run configurations or accepted empirical outputs.

## Why this workgraph exists

The existing W5–W8 tests created substantial reproducible descriptive evidence, but not a causal estimate of jobs creation. W8's China country-period standardized broad sector-proxy differences were **J−N +0.09 pp, O−N +9.64 pp, J−O −9.55 pp**. A comparable prior-VAC gap of **J−O −9.96 pp** indicates strong pre-existing group differences, though prior VAC is **not assured pre-first-exposure** for J/O. W7's China ADM2 fixed-effects J−O sector proxy was **−0.025 pp** [−2.913, +2.862]. These are **different populations and estimands**, not conflicting estimates of the same treatment effect.

Eric's target includes project types **explicitly claiming jobs**, **indirect jobs potential**, and their combination; genuine **J versus pure no-project N matched pairs** are primary, with **J/O/N matched trios** complementary. His desired ADM3 datasets/outcome alignments are not fulfilled by W8's ADM2 country-period standardization. Moreover `N` only means no *source-recorded China/WB investment* in observed coverage, not all absent financing.

**Question:** can we distinguish the opportunity-cost mechanism from nonrandom project placement and weak treatment/outcome measurement, using the existing FCV apparatus?

## DAG and specific work packets

```text
F00 Source lock + decision criteria
  ├── F01 Employment mechanism / project evidence (Amara + Tomás)
  ├── F02 Selection, first exposure, J−N counterfactual (Amara + Ruth)
  ├── F03 Geography, neighboring exposure, control contamination (Lucía + Tomás)
  └── F04 Outcomes, timeline, measurement and observability (Amara + Tomás)
            \ | | /
             F05 ≤2 defensible candidate designs (Amara)
                         ↓
             F06 Independent review + Director decision (Ruth)
```

Each task is **QUEUED**, including F00. No task was run when this graph was defined. Status of earlier W5–W8 runs is not inherited by future tasks.

| Packet | Main artifact | Acceptance boundary |
| --- | --- | --- |
| **F00** | W5–W8 provenance, protocol and explicit estimands | Pin original evidence and J/N/O definitions; distinguish causal estimands from descriptive levels. |
| **F01** | Small *outcome-blind* project coding audit | Evidence-backed direct/indirect/unknown categories; no broad sector turned into observed jobs; no full 2,535-project campaign. |
| **F02** | J−N support, placement and true pre-exposure feasibility | Separate never/first-observed/already-treated cohorts, pre-trend support and available pre-treatment covariates. No propensity score as automatic causal identification. |
| **F03** | Spatial-exposure measurement card | ADM2/ADM3 geocode accuracy, spillovers and N contamination; acknowledge that smaller geographies can amplify error. |
| **F04** | Outcome/observability matrix | Theory-relevant ACLED/UCDP and survey signals only if actual usable coverage and timing; predefine precision and detectability questions. |
| **F05** | At most two prespecified candidate designs or a justified dead end | Explicit treatment clock, group support, assumptions, power, falsification and mechanisms. |
| **F06** | Ruth's independent review and ≤3-page decision memo | Director chooses **PROCEED**, **MEASUREMENT FIRST**, or **DESCRIPTIVE ONLY / STOP**. |

## Scientific design restrictions

1. **Primary target J−N**, complementary O−N and J−O; descriptive W8 contrasts must not masquerade as ADM3 matched causal treatment effects.
2. **Placebo / pre-trends** require periods *before first relevant exposure*, not merely the previous finance period. If those data do not exist, record that identification is blocked; do not claim DiD by nomenclature.
3. **Selection** into jobs/other projects may reflect expected changes in conflict. Balance on measured baseline variables cannot remove unobserved targeting.
4. **Mediation** through realized jobs/wages cannot be claimed without measured employment and proper mediator identification; controlling for post-treatment jobs can introduce bias.
5. **Spatial interference** can make nominally unexposed districts inappropriate controls; the size and direction of bias are not known a priori.
6. **Observability** is distinct from effect truth: characterize meaningful effect magnitudes and precision on an actual governed frame; do not infer zero from an interval spanning zero.
7. **No p-value-driven specification expansion** or wholesale sector recoding; a credible null or a scientifically justified stop is an acceptable deliverable.
8. **Bounded execution**: pilot diagnostics and review first; new sample builds, estimators, geography changes, external communication and additional large-scale runs require explicit Director pull/authorization.

## Exit and handoff

One reviewed decision memo, pointers to source-backed diagnostics, and an updated graph state. After Ruth's review, Jeeves routes **only the Director's decision** into an authorized follow-up experiment; proposals and running work are kept separate. Do not dispatch anything merely because this graph exists.

### Source authority

- [W8 design](../experiments/W8_ADM2_JON_SCIENTIFIC_DESIGN_V0.md)
- [W8 results, uncertainty, and prior-history caveat](../experiments/W8_ADM2_JON_SCIENTIFIC_RESULTS_20261116.md)
- [W7 category evidence/annotation gate](../experiments/W7_CLASSIFICATION_CONTROL.md)

No new scientific results are claimed in this graph.
