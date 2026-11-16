# W6 — project classification and W5 panel propagation contract

Status: structural bridge complete and real-data parity-checked; no job-effect regression, no full editorial annotation, and no matched design yet.

## 1. Scientific labels

Eric's jobs classification contains (1) explicit jobs objectives, (2) plausible indirect jobs potential, and (3) their union. Our 2026 protocol also separates locally delivered activity, financial-only transactions, donor-country activity, and channels of employment relevance. These must remain independent versioned editorial labels.

The first 20-row annotation sample is a coding-calibration resource spanning several geographies, not a joinable source of ground-truth labels. At least two samples assert jobs_any=Yes while jobs_channel=none; some nonmacro donations/finance/training were assigned macro-policy status. Preserve original model judgments and adjudicate these cases before treating the sample as validated.

W6 currently provides only a sector-based proxy in config/w6_sector_proxy_v0.json:
- high = productive sectors such as transport, energy, agriculture, industry, communications;
- low = less immediate productive sectors such as health and governance;
- uncertain = heterogeneous sectors and mixed sector labels, especially prevalent in World Bank projects.

High does not demonstrate jobs; low does not prove absence of a jobs mechanism. Editorial jobs fields explicitly remain unannotated. The proxy is a structural/feasibility screen, not a substitute for Eric's three labels.

## 2. Data objects, keys and cardinalities

| Object | Unique key | W5 snapshot size |
| --- | --- | ---: |
| Project dimension | source_family + source_project_id (source release/version also preserved) | 2,535 |
| Input source-location bridge | donor + project ID + source_location_id + geo_uid + period_id | 21,440 |
| Deduplicated project-area-period bridge | donor + project ID + geo_uid + period_id | 19,588 |
| Enriched source panel | geo_uid + period_id | 44,940 |

The project label belongs to a project identity, not to its locations. Join the project dimension many-to-one to source locations; deduplicate multiple physical source locations in the same area-period before aggregating. A project may legitimately map to many ADM2 areas.

The canonical area country must come from the existing W5 source panel, while recipient country remains an independent attribute. In the locked sample, 1,022 China project-area-period mappings involving 174 projects cross recipient borders. They are retained for exact baseline parity and flagged; they must be assessed separately before interpreting geographic exposure as implementation.

Project metadata source versions and sha256 checksums distinguish revisions. For future editorial annotation, use a unique versioned key (source_family, source_release_id, source_project_id, annotation_version), then review disagreements explicitly. Do not overwrite native Silver or Gold.

## 3. Invariants and columns

The project dimension carries source_family, source_project_id, source_release_id, title, native_sector_raw, sector_proxy, sector_proxy_reason, label_contract and three unannotated editorial fields.

The project-area-period bridge retains canonical area country, source recipient country, recipient_area_aligned, location multiplicity, source geographic confidence and label provenance.

The area-period panel preserves all original W5 fields and adds donor-specific high/low/uncertain project counts, mixed/none support group and cross-recipient project counts.

Conservation gates:
1. Every W5 project has one metadata identity.
2. All 21,440 source-location rows remain immutable; 1,852 duplicate area contributions are removed.
3. Every project carries the same label to all mapped geographies.
4. In every area-period cell, high + low + uncertain equals original source project count for each donor.
5. Exactly 44,940 area-period observations remain in original order.
6. Cross-recipient-country areas remain flagged, not silently deleted.
7. Unknown native sectors, missing joins, duplicate identities and count mismatches fail closed.

The no-recorded-project classification refers only to the two sources in that financing period, not to a certified never-treated counterfactual.

## 4. Reproduction and current outputs

Source locks: GeoGCDF v3.0.1 China, AidData World Bank Geocoded v1.4.2, and the W5 source-project roster.

Recreate the output from the canonical FCV Experiment Harness by running its jobs_classification_bridge_cli with the W5 source roster, W5 area-period panel, both native Silver project tables, and config/w6_sector_proxy_v0.json. The CLI records exact input and output SHA-256 values.

Private output directory:
/media/matias/Elements1/fcv-empirical-data/runs/fcv-experiment-harness/w6-jobs-sector-proxy-20261115/

Files: project_sector_proxy_dimension.parquet, project_adm2_period_bridge.parquet, adm2_period_sector_proxy_panel.parquet, w6_bridge_receipt.json.

The source-derived Parquet products must remain out of Git. Executable code, small JSON sector policy, synthetic tests and this contract belong in the harness.

## 5. Next gates, before regressions

Reconcile the 20 calibration labels with the current coding manual; introduce a versioned editorial jobs annotation surface and structured uncertainty. Quantify cross-donor support under mixed sectors and cross-recipient geography. Test whether plausible alternative assignments could materially change treatment support before committing to expensive bulk annotation. Pre-specify the observational jobs/non-jobs VAC comparison only after those checks. Matched pairs/trios, survey outcomes and causal claims remain separate later decisions.
