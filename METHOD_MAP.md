# Method map: what the retrieval changes for FCV

This file records methodological implications, not a broad literature review.

## Ancestor design family

### Isaksson & Kotsadam
Core idea: use locations selected for future projects as a counterfactual for locations with implemented projects, rather than treating never-aid locations as automatically comparable.

FCV implication:
- represent project state at observation time explicitly;
- treat `future/planned` as a selection diagnostic as well as a possible counterfactual;
- do not collapse all locations to a timeless `treated` boolean.

### Kotsadam et al.
Core idea: exploit stronger within-unit timing when the outcome data permit it.

FCV implication:
- ACLED/UCDP area×time data may support a genuine longitudinal design that is stronger than a repeated-cross-section spatial DiD;
- future-project comparisons can remain a complementary identification/selection check.

### Briggs
Implementation lessons:
- `present`, `future`, and `neither` are exclusive empirical groups;
- stronger geographic fixed effects improve comparability but can destroy identifying support;
- a wide radius can contaminate exposure; a narrow radius can destroy power;
- changing radius changes the identifying sample;
- coarse geocoding can manufacture artificial proximity;
- incomplete aid data make "never treated" uncertain.

FCV gates added:
- effective support inside fixed-effect strata;
- spatial-precision compatibility;
- bandwidth robustness without interpreting it automatically as dose-response;
- explicit multiple-project exposure counts.

## Blair implementation details that become infrastructure requirements

From the supplement:

1. **Status at observation time**
   - planned if surveyed before agreement year;
   - completed if surveyed during/after end year;
   - actual start/end preferred;
   - scheduled dates used with a +1 year correction when actual dates are unavailable;
   - unresolved timing is dropped rather than guessed.

2. **Geocoding**
   - only projects with precise geographic information are used;
   - baseline exposure is 30 km;
   - narrower bandwidths can exceed the precision of the source geocode.

3. **Counterfactual validity**
   - planned vs completed project composition is compared by sector;
   - a stricter robustness check keeps only planned projects known eventually to complete.

4. **Robustness**
   - alternate status cutoffs;
   - earlier survey round avoiding inferred project status;
   - ADM1 fixed effects;
   - bandwidth sweep;
   - additional controls with explicit post-treatment-bias warning;
   - spatial-dependence check;
   - sector heterogeneity.

FCV implication:
these are not appendix chores. They define reusable C-layer diagnostics.

## Post-Blair / modern-method boundary

### Bai, Li & Wang (2022)
Use a DDD-type design plus IV for Chinese aid and local political attitudes.

Use for FCV:
- evidence that later work is not treating the Blair estimator as the only possible design;
- reminds us to keep B as an estimator family, not one sacred regression.

### Adera (2023/2024)
Continues to use ongoing vs planned Chinese projects with geocoded Afrobarometer exposure.

Use for FCV:
- the planned/ongoing logic remains operational in later aid-attitude work;
- but its credibility still depends on timing and counterfactual construction.

### Butts — geocoded microdata / spatial spillovers
Spatial treatment effects can spill into nominal controls, and ring/radius definitions can bias estimates.

Use for FCV:
- future C-layer extension: explicit spillover/ring diagnostics;
- do not assume nearby untreated administrative areas are uncontaminated controls.

### Callaway–Sant'Anna; Sun–Abraham
With staggered treatment timing and heterogeneous effects, naïve TWFE/event-study coefficients can be contaminated.

Use for FCV:
- if the ACLED lane becomes a true area×time staggered-adoption design, use a modern staggered-DiD/event-study estimator rather than default TWFE leads/lags.

## v0 estimator policy

The harness contains one deliberately simple baseline:

`completed - planned`

conditional on optional covariates/fixed effects.

It is a calibration/reference estimator, not the final FCV causal estimator.

A mature experiment should be allowed to choose among:
- matched comparison;
- completed-vs-planned spatial comparison;
- modern staggered DiD / event study;
- spatial-ring/spillover-aware design;
- outcome-appropriate count models.

The gates are intended to survive estimator changes.
