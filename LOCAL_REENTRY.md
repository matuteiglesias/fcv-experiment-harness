# FCV local re-entry — canonical path first

> **Current guidance:** use [`CANONICAL_CHECKPOINT.md`](./CANONICAL_CHECKPOINT.md) before running a real area-period experiment.
>
> The earlier `panel_cli` route below is retained as a legacy compatibility path. New evidence from the surviving 2023 files showed that `*_DHSGC.csv` is best treated as the dense covariate lattice, while project exposures and outcomes survive as separate `agg_*` source surfaces.

## Recommended real-data entry

For the frozen ADM2 / T2 / y0=2001 checkpoint:

```bash
python -m fcv_harness.canonical_cli \
  --manifest config/canonical_a2_T2_y2001.json \
  --base-dir . \
  --out-dir out/canonical_a2_T2_y2001
```

Read in this order:

1. `canonical_panel_card.md`
2. `canonical_gates.csv`
3. `source_inventory.csv`
4. `key_integrity.csv`
5. `period_coverage.csv`
6. `project_exposure_profile.csv`
7. `wb_source_comparison.csv`
8. `merge_audit.json`
9. `covariate_profile.csv`
10. `canonical_panel_sample.csv`

This checkpoint deliberately stops before treatment selection, `t → t+1` outcome shifting, matching, or regression.

## Legacy panel experiment route

The previous reconstructed hello-world experiment expected a treatment/covariate panel plus a separate outcome table:

```bash
python -m fcv_harness.panel_cli \
  --panel "data/reg_data/africaa2T22001_DHSGC.csv" \
  --outcomes "data/reg_data/africaa2_T22001.csv" \
  --config "config/legacy_hello_world_acled_vac.json" \
  --out-dir "out/hello_world_adm2_T2_y2001"
```

That route remains useful for synthetic/compatibility tests, but should not be treated as the authoritative ingestion path for the newly inspected real files. The next experiment wave will adapt `PanelExperimentSpec` to consume treatment/outcome definitions from the canonical panel instead of assuming raw WB/CN amount columns already live in `_DHSGC.csv`.

## Interpretation policy

- A failed canonical-data gate is evidence about the inherited measurement substrate.
- Do not modify source semantics merely to obtain a better regression result.
- Legacy `jobcat` values remain unchanged at this checkpoint.
- Project-record presence and positive reported amount remain distinct facts.
- WBad and WBkg remain separate source implementations.
- Absent ACLED rows remain absent until zero-versus-missing semantics are explicitly resolved.
