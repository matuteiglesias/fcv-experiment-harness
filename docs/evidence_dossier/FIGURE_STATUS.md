# Figure build status

This inventory separates what is frozen in repository declarations from what exists only in ignored real-run outputs.

| Figure | Scientific family | Frozen declaration found in Git | Numerical real-run family available in Git | Build state |
|---|---|---:|---:|---|
| F1 | empirical field/support | partial | no | WAITING_FOR_FROZEN_OUTPUT |
| F2 | outcome distribution/sparsity | partial | no | WAITING_FOR_FROZEN_OUTPUT |
| F3 | canonical fatality severity | yes, reference identity | no | WAITING_FOR_FROZEN_OUTPUT |
| F4 | sparse outcome family | yes | no | WAITING_FOR_FROZEN_OUTPUT |
| F5 | country/period/ADM2 influence | yes | no | WAITING_FOR_FROZEN_OUTPUT |
| F6 | t-1/t-2/future timing falsification | yes | no | WAITING_FOR_FROZEN_OUTPUT |
| F7 | within-country complete-history permutation null | yes: 1,000 draws, seed 20260908 | no draws | WAITING_FOR_FROZEN_OUTPUT |
| F8 | paired inference calibration | yes: 0/.02/.05/.10/.20 SD, 200 reps, three methods | no summaries | WAITING_FOR_FROZEN_OUTPUT |

## Frozen declarations recovered

Reference:
- reference ID: `current_geogcdf_acled_e2_v1`
- primary cell: `record_present`
- expected analysis countries: 47
- analysis identity: `8d30161872363d6e43af6334d258b351acf68cadab38d73923a0781eb42f513a`
- primary frame: `e82f273a61a91d5dbc772b775d1b0b2107b0b5c9e3c637f8b9cfadd8078b737f`

F5 influence:
- country leave-one-out: enabled
- period leave-one-out: enabled
- ADM2 screening: cluster-score linearization
- exact ADM2 refits: top 20

F6/F7 falsification:
- deep pre timing offset: -2
- future treatment offset: +1
- current outcome offset: 0
- permutation policy: `within_country_complete_treatment_history`
- repetitions: 1,000
- root seed: 20260908

F4 sparse outcomes:
- canonical fatalities OLS remains primary
- OLS VAC event count
- LPM any VAC
- PPML VAC event count
- natural-scale metrics must remain distinct

F8 inference calibration:
- effect sizes: 0, .02, .05, .10, .20 SD
- repetitions: 200
- alpha: .05
- ADM2 cluster-normal
- country-cluster t
- wild-country bootstrap (399 bootstrap repetitions)

## Current blocking seam

The numerical real-run products are under the repository's ignored `out/` surface and therefore are not retrievable from GitHub. The dossier branch must not reconstruct them from raw data because that would violate the frozen-evidence constraint.

The correct next operation is to place/copy the existing aggregate frozen outputs at the local renderer input seam described in `FROZEN_INPUT_CONTRACT.md`. No substantive model rerun is required.
