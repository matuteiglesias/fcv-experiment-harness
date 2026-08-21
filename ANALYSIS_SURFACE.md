# Analysis universe and ACLED resolution — E1 checkpoint

This checkpoint answers two questions before the first treatment-effect calibration:

1. **Which area-periods are observations in the current experiment universe?**
2. **What does an absent ACLED aggregate row mean inside verified legacy coverage?**

It deliberately does not run a coefficient.

## Current production decision

The repository does not yet contain an independent full-ADM2 GADM/population spine. Therefore E1 does **not** manufacture one from the union of treatment and outcome sources, because doing so would omit pure controls that have neither investment nor violence.

The current analysis universe is declared as:

```text
mode       canonical_lattice
authority  dhsgc_restricted_legacy_2023
```

This means the recovered `_DHSGC` lattice is used as a **restricted research universe**, not asserted to be all ADM2 Africa. Every output carries this authority explicitly and source keys outside it remain visible in the attrition diagnostics.

The implementation also supports `external_gid_spine`: once a trustworthy ADM2 GID spine is recovered, it can define the universe while DHSGC becomes an attached covariate surface with `dhsgc_available` rather than an eligibility requirement.

## ACLED measurement decision

The recovered 2023 processing treated sparse aggregated violence as zero in downstream construction. E1 makes that inherited rule explicit instead of using a generic `fillna(0)`:

```text
policy                    zero_within_verified_coverage
verified period start     1997-1998
verified period end       2021-2022
verified geography scope  analysis_universe
coverage basis             legacy_2023_acled_africa_aggregate_zero_fill
```

For every area-period the resolved surface retains:

```text
acled_record_present
acled_value_raw
acled_value_resolved
acled_coverage_eligible
acled_resolution_status
acled_resolution_policy
acled_coverage_basis
```

The statuses distinguish:

```text
observed_record_positive
observed_record_zero
record_present_value_missing
structural_zero_from_absent_record
outside_verified_coverage
```

An absent record becomes zero **only** inside the declared coverage window and current analysis universe. Outside coverage it remains unavailable.

The coverage basis remains legacy-inherited rather than independently rebuilt from raw ACLED, so the checkpoint intentionally keeps a provenance YELLOW even after the semantics are explicit.

## Run

From the repository root after installing the package:

```bash
python tests_smoke.py
python tests_canonical.py
python tests_experiment_semantics.py
python tests_analysis_surface.py

python -m fcv_harness.analysis_surface_cli \
  --surface-manifest config/analysis_surface_a2_T2_y2001.json \
  --experiment-manifest config/resolved_wbad_record_acled_vac.json \
  --base-dir . \
  --out-dir out/analysis_surface_a2_T2_y2001
```

## Outputs

The E1 directory contains:

```text
analysis_surface_card.md
analysis_surface_contract.json
analysis_surface_gates.csv
analysis_universe_country_profile.csv

acled_measurement_audit_overall.csv
acled_measurement_audit_by_period.csv
acled_measurement_audit_by_country.csv
acled_measurement_audit_by_country_period.csv

source_only_keys.csv
source_outside_lattice_by_country.csv
source_outside_lattice_by_period.csv

resolved_analysis_panel.csv.gz
resolved_analysis_panel_sample.csv

resolved_preflight/
  experiment_preflight.md
  input_eligibility.csv
  treatment_support_by_period.csv
  measurement_frame_sample.csv
  experiment_contract.json
```

## Reading order

1. `analysis_surface_card.md`
2. `analysis_surface_gates.csv`
3. `acled_measurement_audit_overall.csv`
4. `acled_measurement_audit_by_period.csv`
5. `analysis_universe_country_profile.csv`
6. `source_outside_lattice_by_country.csv`
7. `resolved_preflight/experiment_preflight.md`
8. `resolved_preflight/treatment_support_by_period.csv`

Do not begin by inspecting the full resolved panel.

## E1 gates

```text
U0_UNIVERSE_DECLARED
U1_SOURCE_ATTRITION_QUANTIFIED
A0_ACLED_POLICY_EXPLICIT
A1_ACLED_RESOLUTION_COMPLETENESS
A2_ACLED_STRUCTURAL_ZERO_PROFILE
A3_ACLED_COVERAGE_PROVENANCE
```

Interpretation:

- **U0 GREEN** means the observation universe is explicitly named, not that it is the final ideal geography.
- **U1 YELLOW** is expected while substantive source keys remain outside the DHSGC-restricted universe.
- **A0 GREEN** means zero-versus-absence semantics are explicit.
- **A1 RED** is a hard stop: a record-present missing value or unresolved absent record survived inside the declared coverage treatment.
- **A2 YELLOW** is descriptive: sparse conflict data will generate many structural zeroes and later models must respect that distribution.
- **A3 YELLOW** is expected while ACLED coverage provenance is inherited from the recovered 2023 pipeline rather than independently rebuilt.

## Resolved E0

E1 reruns the WBad-record-presence preflight under the resolved ACLED policy:

```text
WBad record presence
2003-2004 through 2013-2014
→ ACLED violence-against-civilians deaths at t+1
```

The resolved preflight may report that measurement policy now permits a later estimator. That is **not** permission to skip the remaining experiment gates, and E1 itself still produces no treatment-effect estimate.

## Stop rules

Stop before E2 if:

- the universe is not unique at `GID × TimePeriod`;
- an ACLED record inside verified coverage has a missing outcome value;
- unresolved ACLED absence remains inside the verified coverage window;
- the resolved E0 loses treated/control support;
- source attrition reveals an unrecognized universe-construction error rather than a documented DHSGC restriction.

Otherwise E2 may construct the predeclared common-window WB measurement matrix under this one universe and one ACLED resolution policy.
