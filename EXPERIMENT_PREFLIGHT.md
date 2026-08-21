# Canonical experiment measurement preflight

This layer sits between the canonical FCV panel and any estimator.

```text
legacy source surfaces
        ↓
canonical panel
        ↓
measurement semantics
        ↓
experiment eligibility / E0 preflight
        ↓
[STOP if unresolved]
        ↓
later experiment gates + estimator
```

It exists so treatment, outcome, eligibility, and missingness choices are explicit scientific inputs rather than hidden behavior in regression code.

## First preflight

The current manifest is deliberately conservative:

```text
panel               a2 / T=2 / y0=2001
treatment source    WBad (World Bank AidData surface)
treatment rule      record_present
annotation          legacy_2023
treatment window    2003-2004 through 2013-2014
outcome              ACLED deaths: violence against civilians
outcome timing       next period
absent ACLED policy  unresolved
covariates           none
```

Run:

```bash
python -m fcv_harness.experiment_preflight_cli \
  --canonical-manifest config/canonical_a2_T2_y2001.json \
  --experiment-manifest config/preflight_wbad_record_acled_vac.json \
  --base-dir . \
  --out-dir out/preflight_wbad_record_acled_vac
```

This command **never runs a regression**.

## Outputs

Read in this order:

1. `experiment_preflight.md`
2. `input_eligibility.csv`
3. `treatment_support_by_period.csv`
4. `source_outside_lattice_by_country.csv`
5. `source_outside_lattice_by_period.csv`
6. `source_only_keys.csv`
7. `measurement_frame_sample.csv`
8. `experiment_contract.json`

## Treatment contract

The first registry deliberately supports both inherited measurement interpretations for each project source:

```text
wbad.record_present
wbad.amount_positive

wbkg.record_present
wbkg.amount_positive

cn.record_present
cn.amount_positive
```

`record_present` and `amount_positive` are not aliases. The preflight preserves the distinction, including zero-only and unobserved-amount project records.

Treatment resolution returns explicit fields including:

```text
treatment
eligible
treatment_provenance
treatment_measurement_status
```

Rows outside the declared treatment-period window or annotation version are not silently coded as controls; `treatment` is nullable outside eligibility.

## Outcome contract

The outcome declaration includes an explicit `absent_record_policy`.

Supported policies are:

- `unresolved` — preserve absence as missing and block estimation;
- `observed_records_only` — use only rows with explicit source records; this is an explicit selection rule and is not the default scientific recommendation;
- `zero_within_verified_coverage` — zero-fill absent records only inside an externally declared verified coverage window. The manifest must provide the coverage bounds; the harness never infers them silently.

For the first ACLED preflight the policy is `unresolved`, so the expected state is:

```text
ESTIMATION BLOCKED
```

That is intentional. We first need to establish the meaning of absent ACLED area-period records.

## E0 input eligibility

Before any estimator, the preflight reports:

- treatment-source keys lost because they lie outside the canonical lattice;
- outcome-source keys lost because they lie outside the canonical lattice;
- eligible treated/control lattice rows;
- next-period outcome record/value availability;
- whether the declared measurement policy permits estimation.

The canonical checkpoint also now emits:

```text
source_only_keys.csv
source_outside_lattice_by_country.csv
source_outside_lattice_by_period.csv
```

These make the `_DHSGC`-lattice selection effect inspectable rather than treating it as invisible preprocessing.

## Country fixed-effect provenance

`country_iso3` is derived transparently from the first three letters of GADM-style `GID` values (for example `AGO.1.1_1 → AGO`). If an existing country field conflicts with the GID-derived value, the harness fails rather than silently overwriting it.

## What remains deliberately deferred

This layer does not:

- reinterpret legacy `jobcat` labels;
- decide that `record_present` is scientifically superior to `amount_positive`;
- reconcile WBad and WBkg;
- decide whether absent ACLED rows are structural zeroes;
- choose regression controls;
- run matching, OLS, DiD, event study, or any treatment-effect estimator.

The next analysis PR should resolve the ACLED absence policy and then run the predeclared WB measurement-calibration matrix through the experiment gates before interpreting coefficients.
