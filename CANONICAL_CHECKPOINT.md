# Canonical FCV panel checkpoint — human run guide

This guide is the first real-data checkpoint after reconstructing the 2023 FCV empirical surfaces.

The goal is **not** to obtain a regression coefficient. The goal is to build and inspect one provenance-rich canonical `GID × TimePeriod` panel before defining a substantive experiment.

## Frozen calibration lane

For this checkpoint:

```text
geography        GADM ADM2 (`a2`)
period length    2 years
alignment        y0 = 2001
annotation       legacy_2023 (jobcat preserved unchanged)
```

Inherited source surfaces:

```text
lattice          data/reg_data/africaa2T22001_DHSGC.csv
ACLED            data/reg_data/agg_acled_africa_a2_2y_2001
Afrobarometer    data/reg_data/agg_afb_places_GID_africa_a2_2y_2001
WB AidData       data/reg_data/agg_WBad_africa_a2_2y_2001
WB alternate     data/reg_data/agg_WBkg_africa_a2_2y_2001
China            data/reg_data/agg_CN_africa_a2_2y_2001
```

The data directory is intentionally ignored by Git. The files may be local copies or reached through a symlink.

## 1. Get the branch and verify the environment

From the repository root:

```bash
git fetch
git checkout feat/canonical-panel-v1
python -m pip install -e .
```

Run both synthetic checks:

```bash
python tests_smoke.py
python tests_canonical.py
```

Expected final line from the new test:

```text
CANONICAL CHECKPOINT TEST PASSED
```

If either synthetic test fails, stop before touching the real-data output.

## 2. Verify the real source files exist

```bash
ls -lh \
  data/reg_data/africaa2T22001_DHSGC.csv \
  data/reg_data/agg_acled_africa_a2_2y_2001 \
  data/reg_data/agg_afb_places_GID_africa_a2_2y_2001 \
  data/reg_data/agg_WBad_africa_a2_2y_2001 \
  data/reg_data/agg_WBkg_africa_a2_2y_2001 \
  data/reg_data/agg_CN_africa_a2_2y_2001
```

The manifest does not infer filenames. These exact paths are declared in `config/canonical_a2_T2_y2001.json`.

## 3. Build the checkpoint

```bash
rm -rf out/canonical_a2_T2_y2001

python -m fcv_harness.canonical_cli \
  --manifest config/canonical_a2_T2_y2001.json \
  --base-dir . \
  --out-dir out/canonical_a2_T2_y2001
```

This command should **not** print or write a treatment-effect estimate.

## 4. Inspect outputs in this order

Do not begin with the canonical data file. Read the human/audit surfaces first:

```text
1. canonical_panel_card.md
2. canonical_gates.csv
3. source_inventory.csv
4. key_integrity.csv
5. period_coverage.csv
6. project_exposure_profile.csv
7. wb_source_comparison.csv
8. merge_audit.json
9. covariate_profile.csv
10. canonical_panel_sample.csv
11. canonical_panel.csv.gz
```

Quick terminal view:

```bash
cat out/canonical_a2_T2_y2001/canonical_panel_card.md
column -s, -t < out/canonical_a2_T2_y2001/canonical_gates.csv | less -S
column -s, -t < out/canonical_a2_T2_y2001/source_inventory.csv | less -S
```

## 5. Approximate source counts already observed

These are **sanity checks, not hard-coded requirements**. They come from the surviving files inspected during reconstruction and should help catch path/version mistakes.

```text
DHSGC lattice
  data rows       78,698
  GIDs             4,142
  periods              19

ACLED
  rows             10,965
  GIDs              3,354
  periods              13

Afrobarometer
  rows              6,734
  GIDs              3,171
  periods               6

WB AidData (WBad)
  rows             11,714
  GIDs              2,983
  GID-periods       8,641
  periods              10
  zero-only GID-periods 2,497

WB alternate (WBkg)
  rows             13,088
  GIDs              3,287
  GID-periods       9,554
  periods              11
  zero-only GID-periods 1,167

China
  rows              1,645
  GIDs                645
  GID-periods       1,283
  periods              12
  zero-only GID-periods   330
```

Small differences are a reason to inspect source/version provenance, not automatically a failure.

## 6. What the canonicalizer is allowed to do

It may:

- use `_DHSGC` as the dense `GID × TimePeriod` lattice;
- validate each source at its declared grain;
- collapse project records from `GID × TimePeriod × jobcat` to `GID × TimePeriod`;
- preserve separate `jobcat_*_present` and `jobcat_*_amount_usd` fields;
- add source-record-presence and amount-positive indicators;
- prefix/normalize attached ACLED and Afrobarometer column names;
- attach sources by left join;
- report source-only keys and coverage differences.

It may **not**:

- relabel the 2023 job categories;
- infer that `Amount_USD == 0` means no project;
- fill absent ACLED rows with zero;
- merge WBad and WBkg into a single World Bank treatment;
- choose treatment/control groups;
- shift outcomes to `t+1`;
- match units;
- run a regression.

## 7. Expected interpretation of the C-gates

The initial gates are about the measurement substrate:

```text
C0  lattice integrity
C1  source-key integrity
C2  source coverage reported
C3  legacy exposure structure
C4  ACLED zero-vs-absence measurement semantics
C5  WBad/WBkg source comparison
C6  inherited covariate profile
```

Some YELLOW gates are expected and scientifically useful.

In particular:

- `C3` will likely be YELLOW because project records with zero reported amount survive in all three project sources. This checkpoint preserves the ambiguity.
- `C4` will likely be YELLOW because ACLED is sparse relative to the full lattice and we have not yet declared absent rows to be structural zeroes.
- `C5` will likely be YELLOW because WBad and WBkg are materially different source implementations. They remain separate.

A YELLOW gate is not an invitation to modify the source until it turns green. It marks a question that the next scientific/design step must handle explicitly.

## 8. Human acceptance checklist

Before merging this checkpoint into the next experiment wave, answer:

- Does the panel have exactly one row per `GID × TimePeriod`?
- Does the source inventory match the files we think we loaded?
- Are project sources unique at `GID × TimePeriod × jobcat`?
- Are legacy `jobcat` values still exactly the inherited values?
- Do record-presence and amount-positive flags remain distinct?
- Are WBad and WBkg visibly separate?
- Are absent ACLED values still missing rather than silently zero-filled?
- Do any source-only GIDs/periods reveal a geography-version mismatch?
- Do the covariate missingness/within-GID variation profiles look plausible?
- Does the card make all deferred scientific decisions visible?

If the answer is yes, the next wave can adapt `PanelExperimentSpec` to consume canonical treatment definitions and run the first WB→ACLED calibration experiments.

## Stop rule

Do not tune the canonicalizer based on whether a future regression coefficient becomes larger, smaller, or more significant.

The checkpoint is successful when the empirical substrate is transparent enough that later experiment choices can be changed and rerun without silently changing the underlying data interpretation.
