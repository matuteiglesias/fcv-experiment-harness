# W5: China/World Bank financing decisions and next-biennium civilian violence

**Status: E0–E4 completed 2026-11-15; 16 targeted W5 synthetic tests pass. Observational and noncausal; primary findings require scientific review.**
Scientific line: PL-015 / RP-008 (measurement) + RP-009 (inference).
Design owner: Matías; Eric Mvukiyehe is a prospective collaborator, not a confirmed coauthor.
Versioned source and estimator contracts: `config/w5_china_wb_vac_v1.json` and `config/w5_e4_influence_v1.json`. Original detailed protocol archived locally as `~/.local/share/fcv-china-wb-comparison/W5_PAPER_ECONOMETRIC_PROTOCOL_2026-11-15.md` (not needed to execute the documented commands).
The primary result was communicated to Eric with caveats on 2026-11-15; public/causal manuscript claims and any new identification strategy still require scientific review.

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
fatality levels, and fatalities/event counts under FE PPML. Pre-period selection diagnostics and source-first cohort comparisons have now run
in E3. Country influence, original ACLED event-level tests, and geographic precision sensitivities were executed in E4.

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
cd ~/repos/fcv-experiment-harness
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

## E2 — severity and frequency (completed 2026-11-15)
Run `python3 -m fcv_harness.w5_e2_e3_cli --phase e2` with the same
`--spec --investment --acled --out-dir` arguments as E1 above. E2 requires
the verified E0/E1 frame receipt and exact source hashes before estimating.
- Next VAC fatalities, FE OLS: CN-only − WB-only **+0.55065 fatalities**,
  country-clustered SE 0.63428, CI95 [−0.72608, +1.82738], p=.3898
  (full 44,940 rows).
- VAC events, FE Poisson pseudolikelihood: **ratio 1.1336**,
  CI95 [0.8250, 1.5577], p=.4309; **15,309** retained observations,
  **46** country clusters.
- VAC fatalities, FE Poisson pseudolikelihood: **ratio 1.4682**,
  CI95 [0.8330, 2.5876], p=.1791; **11,121** observations,
  **46** country clusters.
- PPML iterative removal of all-zero dependent-variable ADM2 and
  country-period FE groups is *explicit*: 29,631 event-count rows and
  33,819 fatality-count rows dropped. PPML therefore describes a different
  finite-FE/outcome-support sample and is not full-sample E1 replication.
- Recorded fatalities are concentrated: top 1% of area-period cells
  account for **80.2%** of fatalities; top three countries (NGA/SSD/SDN)
  **57.7%**. E4 influence checks remain necessary.

The PPML code uses concentrated FE iterated proportional fitting and
weighted FWL/Newton scoring, country-cluster sandwich uncertainty and
convergence diagnostics, not an unexamined dense dummy fit. Synthetic
W5 acceptance tests independently confirm its coefficients match a
**full-rank** dummy-variable Poisson GLM on a separate test dataset.

## E3 — timing and source-placement diagnostics (completed 2026-11-15)
Run `python3 -m fcv_harness.w5_e2_e3_cli --phase e3` with the same
four required input/output arguments. E3 reads the accepted W5 frame
and exact certified ACLED data for outcome (t−2) and confirms full
coverage. Full-sample CN−WB prior-incidence contrasts (country-cluster):
- (t−2): +1.145 pp (p=.224);
- (t−1): +0.090 pp (p=.899);
- prior difference (t−1 - t−2): −1.055 pp (p=.323).

Source-first risk set: exclude **1,247 areas** already source-financed in
the first observed 2001–02 period, acknowledging left censoring. Of
the remaining eligible rows, 61 country-financing-period cohorts in 27
countries have CN-first, WB-first and as-of-t no-source comparisons:
6,550 area-cohort rows (1,127 CN-first; 605 WB-first; 117 both-first;
4,701 as-of-t source-unexposed, possibly reused at later cohorts).
- pre-change (A_{t-1}-A_{t-2}): CN-first−WB-first −1.118 pp,
  CI95 [−5.863, +3.627], p=.632.
- post-change (A_{t+1}-A_{t-1}): +0.376 pp,
  CI95 [−3.669, +4.421], p=.850.

The risk-set compares observed source decisions, *not randomized or
irreversible implementations*. Country-cohort FE and country clustering
do not eliminate unobserved local targeting. No future financing is
used to eliminate eligible contemporaneous controls; repeated controls
can finance later. Pretrend nonrejection does not establish balance
or a causal ATT.

An independent real-data check re-fits the 6,550-row matched first-recorded
risk set using statsmodels country×cohort explicit-dummy OLS and the
country-cluster sandwich. Both pre- and post-change coefficients/SE
reproduce to better than 1e−15. Receipt:
`e3_independent_matched_check.json`. This is numerical validation,
**not** a causal assignment or pre-trend validation.

Run outputs are `e2_results.json`, `e2_model_effects.csv`,
`e3_results.json`, `e3_preperiod_effects.csv`,
`e3_first_recorded_effects.csv`, and the cohort support CSV.
Provenance and model limit documentation is in both phase JSON receipts.

## E4 — influence, event-level source parity, geographic precision (completed 2026-11-15)

**Purpose:** Test *all* planned exclusions and transparently report sign and
confidence-interval changes, rather than choose exclusions to improve p-values.
All 47 leave-one-country-out fits, four cumulative high-fatality-country
deletions (top 1/2/3/5), four *individual-event* deletions, three
asymmetric financing-location precision definitions, observed source-history
controls, and two common outcome-source ACLED geo-precision filters are run.
Nothing is deleted or changed in certified Gold/Silver or input sources.

### Country influence: same FE model and country-cluster CR1
Original CN-only − WB-only: +0.6562 **pp** any VAC incidence (p=.578);
+0.55065 **fatalities/ADM2×biennium** (p=.390).
Across **all 47 single-country omissions**:
- incidence difference remains positive in **[+0.132, +1.395] pp**;
  no single omission crosses p=.05 or reverses sign;
- fatality coefficient remains positive in **[+0.321, +0.918] fatalities**;
  no single omission crosses p=.05 or reverses sign.
Largest perturbation to incidence is from Uganda (leave out UGA:
+1.395 pp, p=.143), not Nigeria.

By cumulative exclusion of countries with the most recorded VAC fatalities:
| Source countries omitted | VAC incidence difference (pp) | Fatality difference (level) |
|---|---:|---:|
| Nigeria | +0.847 | +0.321 |
| Nigeria + South Sudan | +0.869 | +0.120 |
| Nigeria + South Sudan + Sudan | +0.687 | **+0.057** |
| The above + DR Congo + CAR | +0.559 | +0.161 |

No selected country deletion establishes a statistically discernible donor
difference. However, **severity magnitude changes substantially**: the
three-country removal cuts the unadjusted-to-crisis-influence fatality
coefficient by ~90%. Source-country deletion is a robustness stress, not an
inference that conflict in those countries was recorded incorrectly.

### Actual source-event influence, certified ACLED parity before deletion
ACLED Silver events + `event_geography` matched_unique assignments +
`event_period` assigned periods reconstructed EXACTLY **26,963 VAC events
and 91,396 reported VAC fatalities** in the full W5 t+1 outcome periods,
including zero-positive cells. Exact event-count and fatality parity across
all 44,940 ADM2×financing-period rows passed. Eligible source events have
immutable event_row_id, date, source event ID, reported fatalities and
precision; no aggregation method was redefined post hoc.

**Individual event deletion** affects only the specific areas/biennia, not
countries. Events ranked by **reported fatalities descending**, tied by
event-row ID, independently of the donor coefficient. Separate copies:
| Deleted source event rows | Share of fatalities dropped | Incidence contrast (pp) | Fatality contrast (level) |
|---|---:|---:|---:|
| largest one (1,000 reported fatalities, Nigeria) | 1.1% | +0.654 | +0.526 |
| top 5 | 4.0% | +0.654 | +0.693 |
| top 10 | 7.2% | +0.654 | +0.829 |
| top 1% of positive-fatality event rows (132 events) | 31.2% | +0.672 | **−0.045** |

All remain statistically inconclusive. The fatality coefficient can reverse
*sign* under deletion of ~31% of recorded fatality mass, despite no single
extreme event changing its interpretation. **This is a sensitivity, not a
justification to censor valid extreme events.** `e4_top_source_events.csv`
and the JSON experiment manifest document the original top event IDs.
ACLED's reporting/precision is not independently audited beyond source parity.

### Geographic uncertainty: two different domains, do not conflate
**Outcome-side ACLED geo precision**, applied uniformly to Chinese, WB,
joint and neither source categories:
- only ACLED geo_precision 1 or 2: n=25,727 VAC events, incidence +0.649 pp
  (p=.579), fatalities +0.534 (p=.332);
- only ACLED geo_precision 1: n=19,294 events, incidence **+0.384 pp**
  (p=.705), fatalities **+0.419** (p=.377), 66.1% fatality mass retained.
The full 44,940-row lattice and original financing categories are retained
in both cases. Missing events are *structural zeros only for these deliberately
restricted outcome definitions*, with original certified event parity checked.

**Financing-side source-location confidence** is asymmetrically measured:
WB `exact_named_place|verified_adm2` versus China geometry `matched_single`
(or broad source geometry, often matched_multiple due polygon coverage).
Restricting WB to high-confidence location source records leaves broad China:
incidence contrast **+1.499 pp**, p=.135. Restricting China to single-ADM2
geometry and leaving broad WB: incidence **−3.820 pp**, p=.130. Both strict:
**−3.139 pp**, p=.201. These filters cause strong changes in exposure
support (CN-only falls from 7,183 to ~427/451 in China-strict scenarios);
CN matched_multiple is not necessarily *lower spatial precision* than
matched_single, so **this is NOT a symmetric precision comparison and does
not prove the primary inference robust to equivalent geocoding quality**.
The source roster reconstructs BOTH Gold project counts with zero mismatches.

### Financing history within the observed period
Adding separate prior-recorded CN/WB source indicators to the main
area + country-period FE regression (without future-financing selection):
- Incidence contrast **+0.780 pp**, p=.497.
- Fatality-level contrast **+1.123**, p=.222.
The histories are necessarily left-censored before the 2001–02 panel start.

### Acceptance criteria and scientific status
This E4 is **COMPLETED WITH EXPLICIT FRAGILITY**, not “fully robust”.
The incidence result resists each country deletion, individual event stress
and common ACLED precision definition. The severity coefficient is fragile
in magnitude and its sign reverses under extreme-tail trimming; the financing
location-restricted estimates differ sharply under asymmetric source rules.
None establishes equivalence, causal effects, or a robust difference.
Do not pick the model with the smallest p-value. Never present these
deletions as removal of bad/confounded data. E4 is a descriptive study of
estimator sensitivity, not an identification strategy.

Re-run E4 using the source-locked accepted frame with:
`python -m fcv_harness.w5_e4_cli --spec config/w5_china_wb_vac_v1.json
--e4-spec config/w5_e4_influence_v1.json --investment "$INV" --acled "$AC"
--roster "$D/gold/investments/aiddata_china_wb_source_panel/aiddata-cn-wb-source-v1-558e6e093aca5e5c/source_project_roster.parquet"
--event-silver <ACLED_SILVER_EVENTS> --event-geo <ACLED_EVENT_GEOGRAPHY>
--event-period <ACLED_EVENT_PERIOD> --out-dir "$OUT"`.
The independent outcome-side ACLED precision CLI uses the same source
`--spec --investment --acled --event-silver --event-geo --event-period --out-dir`.
The exact paths/hashes of all extra sources are recorded in result receipts.

Outputs: `e4_results.json`,
`e4_country_leaveout_effects.csv`, `e4_event_influence_effects.csv`,
`e4_top_source_events.csv`, `e4_country_fatality_ranking.csv`,
`e4_source_precision_effects.csv`, `e4_history_adjusted_effects.csv`,
`e4_acled_outcome_precision_effects.csv`,
`e4_acled_outcome_precision_results.json`.
Source Gold remains unchanged. Reruns must preserve all declared
exclusions and include every p-value and confidence interval.

## Scientific gate
E0–E4 are executed, committed and merged into the canonical harness via
[PR #29](https://github.com/matuteiglesias/fcv-experiment-harness/pull/29).
The November 15 E0/E1 replay from canonical `main` reproduced the exact original
E1 coefficient vector, covariance, p-values, confidence intervals, source
hashes and analysis-frame hash. Publication-level claims remain **DIRECTOR REVIEW**,
not “all robustness passed.” Prior literature, causal targeting, time
misalignment between approvals and commitments, eventual implementation,
and joint location exposure must be interpreted by Eric and Matías before
deciding the manuscript's contribution. No author/venue/outreach agreement
has been made. The original local Python 3.10 environment retains a SciPy/NumPy warning;
**the full GitHub repository CI passed on Python 3.12 for merged PR #29**.
For byte-identical future reruns, preserve the accepted source/version locks,
check output hashes, and maintain a compatible/pinned environment.

## Integrated reproducibility and archived result index
The canonical harness's W5 modules and synthetic tests are maintained alongside other
experiments; they are not a throwaway worktree. The checked-in aggregate
[2026-11-15 result index](docs/results/w5_china_wb_vac_20261115.json)
records the historic effect sizes, uncertainty, 47-country influence summary,
source-precision/terminal-tail warnings, validated event-to-Gold parity, exact
source SHA-256 locks, and hashes of the richer private result files. This index
contains **no raw ACLED event records**, geographic assignments, identifiable
row-level data, or source extracts. It is evidence of a particular run, not a
CI synthetic fixture or a newly identified causal treatment effect.

To recreate the same figures, obtain **exactly the recorded source versions**,
run E0 then E1 (then E2/E3 and the independent E4 commands) with the documented
inputs and coverage contracts, and compare `run_receipt.json` and the E0–E4
output SHA-256 digests to the archived index. Reruns with updated software or
sources may change numerical bytes; don't silently replace this historic index.
If private data are unavailable, execute all W5 synthetic tests and inspect
the published index, but do **not** claim that synthetic tests reproduce the
empirical coefficients. The complete event-level and project roster inputs must
be provisioned locally and remain outside Git. The exact output receipts live in
`/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w5-cn-wb-vac-20261115/`
on the original authorized machine.
