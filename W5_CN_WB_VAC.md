# W5: China/World Bank financing decisions and next-biennium civilian violence

**Status: E0 PASS; E1 exploratory fit reproduced independently. No causal effect identified.**
Scientific line: PL-015 / RP-008 (measurement) + RP-009 (inference).
Design owner: Matías; Eric Mvukiyehe is a prospective collaborator, not a confirmed coauthor.
Bounded research protocol: `~/.local/share/fcv-china-wb-comparison/W5_PAPER_ECONOMETRIC_PROTOCOL_2026-11-15.md`.
The primary result should not be included in a public manuscript or an external email without scientific review.

## What is new versus prior harness lanes?
This lane is **not** the 2023 DHSGC-restricted canonical panel, and not the
single-China-source E2 calibration. It joins two accepted **AidData source-specific
measurements** (WB geocoded approval v1.4.2, China GeoGCDF commitment v3.0.1)
and the separate provisionally certified ACLED VAC outcome. The four categories
(CN-only, WB-only, both, neither-recorded) refer to *financing decisions during a
two-year bin*, not actual project implementation, local spending, or permanent
treatment. The neither-recorded category is not verified never-treated.

Predeclared primary outcome: any ACLED violence-against-civilians event in the
**next** two-year bin. Secondary planned outcomes: number of VAC events,
fatality levels, and fatalities/event counts under FE PPML. Dynamic pre-trend
diagnostics, source precision, histories and country influence are not yet run.

## Input provenance / fail-closed contract
- `config/w5_china_wb_vac_v1.json` freezes the exact two input SHA-256 hashes,
  source IDs, ADM2 × T2_y2001 scope, primary model and E0 support minima.
- The CLI **requires** both L3 investment and L2 ACLED coverage-contract JSONs.
  ACLED zero coding is allowed only within operator-accepted, *provisionally
  certified* historical source coverage; it is **not** an independent fresh
  ACLED release audit. Missing outcomes, country/geography mismatch, duplicate
  keys and altered source bytes abort before fitting.
- Inputs are read-only. Analysis artifacts and receipts go to an explicit
  `--out-dir`, not into canonical Gold, source repos or the tracked code tree.

Example on Matías's local computer:

```bash
cd ~/repos/fcv-experiment-harness-w5
export PYTHONPATH=~/repos/spatial-data-foundation/src:${PYTHONPATH:-}
export D=/media/matias/Elements1/fcv-empirical-data

INV="$D/gold/investments/aiddata_china_wb_source_panel/aiddata-cn-wb-source-v1-558e6e093aca5e5c/source_area_period.parquet"
AC="$D/gold/violence/acled_area_period_certified/acled-local-africa-1997-2021-sep24-06d043a5f3d9--geo-70d8aab67f95--T2_y2001--cert-b7c87b27e221/certified_area_period.parquet"
IC="$D/runs/fcv-empirical-data/aiddata-china-wb-source-panel-20261109T200000Z/artifacts/contracts/coverage.json"
AC_C="$D/runs/fcv-empirical-data/acled-certified-africa-t2-20260908T170000Z/artifacts/contracts/coverage.json"
OUT="$D/runs/fcv-experiment-harness/w5-cn-wb-vac-20261115"

python3 tests_w5_china_wb_vac.py

python3 -m fcv_harness.w5_china_wb_vac_cli \
    --investment "$INV" --acled "$AC" \
    --investment-contract "$IC" --acled-contract "$AC_C" \
    --spec config/w5_china_wb_vac_v1.json \
    --phase e0 --out-dir "$OUT"

# E1 only after the E0 gate is PASS; reruns/freeze-checks E0 before estimating.
python3 -m fcv_harness.w5_china_wb_vac_cli \
    --investment "$INV" --acled "$AC" \
    --investment-contract "$IC" --acled-contract "$AC_C" \
    --spec config/w5_china_wb_vac_v1.json \
    --phase e1 --out-dir "$OUT"
```

## E0 acceptance, verified 2026-11-15
- 44,940 observations / 47 countries / 6,420 ADM2 / seven financing biennia;
  44,940 complete t−1 and t+1 certified VAC records.
- 7,183 China-only; 3,672 WB-only; 1,302 both; 32,783 neither-recorded.
- Both exclusive donor arms coexist within 164/329 country × financing-period
  cells, across 39 countries.
- Residualized design of the three arm indicators after area and country × time
  FE has full rank 3. This checks algebraic identification, NOT selection bias
  or sufficient effective cluster power.
- Primary sample VAC-event incidence 11.65%; fatality incidence 7.49%.

## E1 main fixed-effects association, exploratory
Define:
`1[any VAC event at (i,t+1)] = area_i FE + country_x_t FE + beta_C*C + beta_W*W + beta_B*B + error`.
Principal contrast `beta_C − beta_W`, direct covariance calculation.

Result: **+0.6562 percentage points**; country CR1 SE **1.1702 pp**;
95% CI **[-1.6993, +3.0117] pp**; two-sided **p = 0.5777**.
All 44,940 observations, 47 nominal country clusters, 46 cluster df.
No evidence of a precisely estimated difference; this does NOT establish
equivalence, lack of effect, or a causal source treatment contrast.

The FE estimator uses a balanced ADM2 lattice's exact FWL demeaning. A
separate sparse explicit-dummy OLS + independent country-cluster sandwich
recomputed all coefficients to ~2.2e−12 and the primary SE to ~6.5e−15.
The independent verification receipt is in the local E1 output directory.
Existing SciPy 1.8.0 on this laptop warns of an incompatibility with NumPy
1.26.4; tests and numeric cross-check passed, but the locked dependency
environment should be refreshed prior to external release.

## Artifact contracts
- `w5_analysis_frame.parquet` — private area-period analysis frame with
  pre/post VAC observations, source flags, statuses and exposure arm dummies.
- `e0_preflight.json` — gate, rank, country/period support, source/outcome counts.
- `e0_support_by_country*.csv` and `e0_support_by_period.csv` — source exposure.
- `e1_primary.json`, `e1_effects.csv`, `e1_report.md` — estimates with
  direct donor contrast, country-cluster CIs, no causal interpretation.
- `e1_independent_sparse_check.json` — alternative numerical estimator receipt.
- `run_receipt.json` — exact source/contract/config/frame hashes.

## Next gates
E2: fatalities FE OLS and event/fatality FE PPML with separation and sample
changes; no retroactive choice of the primary outcome. E3: pre-period
selection/first-recorded exposure diagnostics. E4: project-geography precision,
country concentration and exposure-history sensitivity. Scientific sign-off
and an explicit material-effect threshold are needed before statements of
causality or equivalence. No actor-specific VAC or employment-sector
classification in this lane until source prerequisites are met.
