# W7 — Frozen deterministic exploratory jobs-potential proxy experiment (v0)

Date: 2026-11-16. This specification is frozen before NEW outcome fits. It uses W7 native-sector tags and the 44,940-row W5 ADM2-financing-biennium panel.

## Scientific scope
Eric's hypothesized mechanism is paid local employment and wages followed by changed social stability and subsequent violence against civilians. The current data do NOT measure actual workers, local wages, implementation-mediated employment or effects. This is a source-sector proxy screen, not a jobs or causal result.

## Deterministic rules (frozen, outcome-blind)
Primary BROAD: productive_enterprise, physical_infrastructure and skills_education count as candidate jobs-potential channels. Health/social, governance/finance and humanitarian/environmental/other are OTHER SECTORS, NOT confirmed non-jobs.
Secondary NARROW: productive_enterprise and physical_infrastructure are candidate channels; skills/education shifts to OTHER. This is an explicitly prespecified mechanism-width sensitivity.
Projects with multiple native channel tags: if all tags fall within candidate set assign candidate, if all within other set assign other-sector, otherwise MIXED/AMBIGUOUS. Retain all 2,535 project IDs.
Each ADM2-period donor-exclusive cell is positive_only if all of its projects are candidates; other_only if all are other-sector; mixed otherwise. Cells exposed to BOTH donors are a separate arm. Neither-source-recorded is reference, NOT never treated.

## Frozen estimation
Arms, in order: cn_positive_only, cn_other_only, cn_mixed_or_unknown, wb_positive_only, wb_other_only, wb_mixed_or_unknown, both_sources.
Primary response any_vac_next; secondary asinh(vac_events_next); prespecified negative control any_vac_prior from vac_events_prior>0. Prior VAC is a selection diagnostic, not strict pretrend test.
Outcome regressions use exact FWL demeaning ADM2 and country-by-biennium fixed effects; country-clustered CR1 SE with t(G-1), matching W5.
Predeclared within-donor contrasts China positive-only minus China other-only; and WB positive-only minus WB other-only. Report pp, 95% CI, p; all donor/source counts and country-period support; no significant-findings search. Rank <7 abort. <100 cells in any contrasted arm or <5 countries with both arm types => THIN SUPPORT (point estimate can be reported but no inferential claim).
Do not interpret as confirmed local employment or wages. The source timing is approval/commitment. Excluding problematic source geometry is separate future work, not a posthoc rerun for a favorable coefficient.

## Direct title signal
Fixed literal terms in JSON policy are only counts and illustrative review candidates (e.g. jobs, employment, vocational training). Ministry of Public Works is a known false-positive for naive keywords; title matches are unreviewed and never auto-verified.

## Reproducibility
Source-qualified input: W7_CLASSIFICATION_CONTROL Parquets and W5 outcome frame; source hash receipt. Code lives only in the canonical fcv-experiment-harness; output only in new immutable private run directory w7-frozen-proxy-experiments-20261116. Preserve old W7 sector screens as historical frozen artifacts. No ad-hoc scripts, no source file mutation.

Reviewers must read this policy BEFORE seeing regression results. If a correction is required it needs a distinctly versioned policy and explicitly separate result series.
