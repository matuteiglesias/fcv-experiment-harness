# W7 classification control — bounded canonical code station

Status: structural coverage release only. The initial 2,535-row release is a valid structural pass and a scientific label-gate fail: every project is `unreviewed`/`unresolved`, so no employment regression or jobs claim is permitted.

## Contract

`config/w7_native_sector_channels_v0.json` maps all 19 China and 20 World Bank native tokens to six candidate channel categories. A project may have multiple `candidate_sector_channel` values. These are sector-based candidate channels, not jobs labels; title, sector, or missing full text never confirms jobs or other.

The ledger key is exactly `source_family + source_release_id + source_project_id`. Its separate fields are `editorial_status` (`unreviewed`, `unclear`, `reviewed`), `class` (`reviewed_jobs`, `reviewed_nonjobs`, `unresolved`), `direct`, `indirect`, `local_implementation`, `confidence`, and evidence/reference fields. A reviewed jobs/nonjobs row requires explicit direct/indirect logic and an evidence source, SHA-256 content hash, and reference. Invalid, orphaned, duplicate, incomplete, or discordant annotations fail closed.

The exposure panel retains every W6 `geo_uid`, `period_id`, `country_iso3`, donor count, recipient/cross-recipient information, and panel row. Multi-sector candidate counts are intentionally multi-hot; donor project class counts are the exact parity partition against original donor project counts. Unknown and mixed World Bank projects remain present.

## Locked inputs and run

Inputs are the W6 files in `/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w6-jobs-sector-proxy-20261115/`:

```bash
python3 scripts/w7_employment_classification_release.py \
  --dimension /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w6-jobs-sector-proxy-20261115/project_sector_proxy_dimension.parquet \
  --bridge /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w6-jobs-sector-proxy-20261115/project_adm2_period_bridge.parquet \
  --panel /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w6-jobs-sector-proxy-20261115/adm2_period_sector_proxy_panel.parquet \
  --policy config/w7_native_sector_channels_v0.json \
  --output-dir /media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-classification-control-20261116
```

Outputs are newly named and private: `w7_project_classification_ledger_v0.parquet`, `w7_project_area_classification_bridge_v0.parquet`, `w7_classification_exposure_panel_v0.parquet`, and `w7_classification_control_receipt.json`. The receipt records SHA-256 locks, counts, class/status counts, gate state, and the no-regression prohibition. W5/W6 inputs and outputs are never overwritten.

## Editorial annotation submission

Submit a separate versioned CSV, Parquet, or JSON table with these columns:

`source_family, source_release_id, source_project_id, annotation_version, editorial_status, class, direct, indirect, local_implementation, confidence, evidence_source, evidence_content_hash, evidence_reference, reviewer`.

Use `yes`/`no` for explicit booleans. A confirmed positive requires (direct=yes OR indirect=yes) AND source-supported local implementation; a confirmed negative requires direct=no AND indirect=no AND source-supported local implementation. A locally implemented project may be non-jobs. Nonlocal and finance-only projects stay excluded/unresolved, not silently confirmed as negative. `unreviewed` and `unclear` must remain `unresolved`. The content hash must be the SHA-256 of the supplied evidence content, not a fabricated placeholder. The annotation file is a coding artifact and is not source text or a bulk LLM label file.

Run with `--annotation-file PATH` only after independent review. The scientific gate remains a review decision even when reviewed rows exist.

## QA and limits

Run `python3 -m unittest tests_w7_employment_classification.py`. Tests cover uniqueness, no automatic jobs, mixed/multi-sector retention, evidence validation, annotation joins, exact donor partition parity, receptor/geo-country preservation, and fail-closed drift. The complete real-input run is allowed when the private output directory is writable; otherwise the CLI remains runnable by the host with the exact command above.

This station does not infer employment, wages, causality, true jobs absence, or counterfactual treatment. A 120-row review sample is optional: it can support calibration and adjudication, but it cannot substitute for a pre-specified complete annotation policy or silently become ground truth. No W5/W6 source code or data is modified.

## Full-universe checkpoint: verified host release

The initial W7 release has **2,535 source-qualified projects**: 1,948 China
and 587 World Bank; **19,588** project-area-period links; and **44,940**
W5-compatible area-period cells. Every donor project count is conserved
per cell. **2,535 remain unreviewed/unresolved**; the structural gate passes
and the scientific jobs-regression gate fails, correctly.

Exclusive **candidate sector** project counts (NOT measured employment):

| Candidate family | China | World Bank |
| --- | ---: | ---: |
| Productive enterprise | 195 | 28 |
| Physical infrastructure | 513 | 135 |
| Skills/education | 313 | 14 |
| Health/social | 628 | 24 |
| Governance/finance | 229 | 32 |
| Humanitarian/environment/other | 70 | 1 |
| Multiple channel families | 0 | 353 |

World Bank multi-hot channel-membership totals overlap; they cannot be
added as if they were independent projects.

Private authoritative source/output hashes and donor support:
`/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-classification-control-20261116/w7_classification_control_receipt.json`.
Host W7/W6/VAC targeted tests: 20 passed, with 8 subtests.

## Frozen exploratory runners: historical rather than maintained code

Seven earlier ad-hoc W7 scripts were preserved in a SHA256-verified
archive alongside their original exploratory receipts:
`/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w7-jobs-first-support-20261116/w7_exploratory_runners_20261116.tar.gz`
(SHA256 `4455a670944c68789f0a391980f5c49e1065ad334d3041460dced15ab3e8b9b8`).
The adjacent `w7_exploratory_runner_archive_manifest.json` lists the exact
source-file hashes. Those old sector-proxy scripts are not the maintained
scientific classification product; local copies may be retired only after
the archive and canonical release are verified.

## Next scientific gate

Add outcome-blind, versioned source-grounded reviewed labels with local
implementation, direct/indirect mechanisms, reviewer identity and source hash.
Measure how much independent area-period support definite jobs and nonjobs
labels achieve, rather than relying on an arbitrary 120-project sample.
Only a separate prespecified support/FE check can authorize jobs-vs-other
VAC estimation.
