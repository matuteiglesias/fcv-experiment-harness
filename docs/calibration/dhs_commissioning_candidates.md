# DHS commissioning benchmarks

Status: research design for the FCV Africa Observability Lab. These are **instrument commissioning** checks, not new FCV substantive results.

Every benchmark below has:

```text
purpose = calibration
kind = commissioning
```

The commissioning question is: given a specific DHS release, the rebuilt HR measurement system, and an externally published DHS statistic, does the rebuilt instrument recover the published measurement under the same denominator, weighting, category, and missing-value conventions?

## Scope and current upstream capability

The current `fcv-empirical-data` DHS substrate keeps HR, GE/GPS, and GC as separate natural-grain empirical products linked by explicit `SurveyCatalogEntry` identity. The integration report is QA evidence; it is not a joined analysis table. GPS coordinates remain displaced reported-coordinate measurements, and GC temporal semantics are registry/documentation driven. None of those spatial products is required for the commissioning statistics proposed here.

The first DHS semantic registry is deliberately small and DHS-VII/HR-specific. It currently supports exactly:

| Source variable | Registered measurement | Current semantic boundary |
| --- | --- | --- |
| `HV206` | `dhs.household.electricity_access` | Standard binary measurement; `9` is a source missing code, not zero. |
| `HV270` | `dhs.household.wealth_quintile` | Ordered source quintile; explicitly survey-relative. |
| `HV201` | `dhs.household.drinking_water_source_code` | Source category code only; no inferred improved/unimproved or safe/unsafe harmonization. |

HR Silver also preserves every source-native field and the source household weight unchanged. Its standard column map identifies `HV005` as the household weight. The semantic measurement view does not make a weighting or denominator choice, so a commissioning calculation must explicitly relate measurement rows back to the corresponding HR `source_row_id` to obtain `HV005` and, where a published denominator requires them, source-native auxiliary fields such as `HV012` or `HV025`.

This is intentional: weighting and denominator selection belong to the benchmark design, not to the upstream variable registry.

## Authoritative methodological references

Primary methodological references used here:

- The DHS Program, **DHS-VII Standard Recode Manual**, August 29, 2018: <https://www.dhsprogram.com/pubs/pdf/DHSG4/Recode7_DHS_10Sep2018_DHSG4.pdf>
- The DHS Program, **DHS-VII Standard Recode Map**, August 31, 2018: <https://www.dhsprogram.com/pubs/pdf/DHSG4/Recode7_Map_31Aug2018_DHSG4.pdf>
- The DHS Program, **Guide to DHS Statistics, DHS-7**, household characteristics and drinking-water sections: <https://www.dhsprogram.com/pubs/pdf/DHSG1/Guide_to_DHS_Statistics_DHS-7_v2.pdf>
- The DHS Program, **Guide to DHS Statistics**, Wealth Quintiles: <https://dhsprogram.com/Data/Guide-to-DHS-Statistics/Wealth_Quintiles.htm>

The DHS-7 guide defines household electricity tabulation from the HR file using `HV206`, with household sample weight `HV005`. For de jure population tabulations from HR it uses `HV005 * HV012`. It also states that households/population with missing information are included as separate categories in percent distributions. Dividing every `HV005` by 1,000,000 changes the scale of weighted counts but not percentages.

For wealth quintiles, DHS defines the published distribution over the **de jure population**, not over households: `HV270` supplies the quintile, `HV012` the number of de jure members, and `HV005` the household sample weight. National quintiles are constructed to contain approximately one fifth of the de jure population, making the national 20/20/20/20/20 pattern a weak quantitative commissioning target by itself.

For `HV201`, the DHS recode documentation explicitly warns that individual drinking-water source codes can be country-specific even where major categories are standardized. Therefore this design does **not** infer an improved/unimproved mapping from the generic registry.

## Candidate set and ranking

### C1 — Nigeria 2018: national household electricity access — HIGH

- **Survey:** Nigeria DHS 2018, DHS survey identifier `NG2018DHS`, DHS-VII.
- **Official report:** *Nigeria Demographic and Health Survey 2018*, Final Report `FR359`, <https://www.dhsprogram.com/pubs/pdf/FR359/FR359.pdf>.
- **Reference:** Table 2.4, “Household characteristics”, p. 26.
- **Published statistic:** households with electricity, Total = **59.4%**; No = **40.6%**.
- **Numerator:** weighted HR households with `HV206 = 1`.
- **Denominator:** all HR households in the table population, including any `HV206` missing category rather than silently dropping it.
- **Source variables:** registered `HV206` measurement plus `HV005` from the matching HR Silver row.
- **Weight:** `HV005`; `/ 1_000_000` normalization is scale-equivalent for the percentage.
- **Domain restriction:** national households; no residence filter.
- **Missing treatment:** preserve/report source missing separately and keep it in the percent-distribution denominator, per the DHS guide.
- **Likely discrepancy sources:** wrong survey/release, filtering missing values out of the denominator, unweighted mean, using a person rather than household denominator, or mixing report/recode versions.
- **Expected recovery:** **Level 3 quantitative recovery should be near-exact**. The recomputed percentage should round to 59.4 at one decimal place.

This is the strongest first benchmark because it directly exercises one registered semantic measurement, survey identity, `HV005`, and denominator semantics without a country-specific category map.

### C2 — Uganda 2016: national household electricity access — HIGH

- **Survey:** Uganda DHS 2016, DHS survey identifier `UG2016DHS`, DHS-VII.
- **Official report:** *Uganda Demographic and Health Survey 2016*, Final Report `FR333`, <https://www.dhsprogram.com/Pubs/Pdf/Fr333/Fr333.Pdf>.
- **Reference:** Table 2.4, “Household characteristics”, p. 23.
- **Published statistic:** households with electricity, Total = **28.6%**; No = **71.4%**.
- **Numerator / denominator / source variables / weight:** same DHS household-electricity definition as C1 (`HV206`, `HV005`).
- **Domain restriction:** national households.
- **Missing treatment:** same explicit missing-category policy as C1.
- **Likely discrepancy sources:** same as C1, plus wrong cross-survey identity or release binding.
- **Expected recovery:** **Level 3 near-exact** after release-specific recode validation.

Calibration value is high, but this is primarily a **cross-survey replication** of C1. It is an excellent second-survey acceptance target, not the best use of the first local commissioning run if only one authorized HR release is already available.

### C3 — Zambia 2018: national household electricity access — HIGH

- **Survey:** Zambia DHS 2018, DHS survey identifier `ZM2018DHS`, DHS-VII.
- **Official report:** *Zambia Demographic and Health Survey 2018*, Final Report `FR361`, <https://www.dhsprogram.com/pubs/pdf/FR361/FR361.pdf>.
- **Reference:** Table 2.4, “Household characteristics”, p. 22.
- **Published statistic:** households with electricity, Total = **34.2%**; No = **65.8%**.
- **Numerator / denominator / source variables / weight:** same DHS household-electricity definition as C1 (`HV206`, `HV005`).
- **Domain restriction:** national households.
- **Missing treatment:** same explicit missing-category policy as C1.
- **Likely discrepancy sources:** same as C1, plus wrong cross-survey identity or release binding.
- **Expected recovery:** **Level 3 near-exact** after release-specific recode validation.

Like C2, this is valuable as a later cross-survey commissioning replication rather than as a distinct first-test mechanism.

### C4 — Nigeria 2018: national household drinking-water source distribution — MEDIUM

- **Survey:** Nigeria DHS 2018 (`NG2018DHS`).
- **Official report:** `FR359`, Table 2.1.1, “Household drinking water”, p. 21.
- **Published detailed household-source pattern, Total column:**
  - piped into dwelling/yard/plot 3.0%
  - piped to neighbour 0.7%
  - public tap/standpipe 7.5%
  - tube well or borehole 37.2%
  - protected dug well 11.4%
  - protected spring 0.5%
  - rainwater 2.0%
  - tanker truck/cart with small tank 2.6%
  - bottled water 0.7%
  - unprotected dug well 13.5%
  - unprotected spring 1.6%
  - surface water 9.4%
  - sachet water 9.8%
  - other 0.1%
- **Numerator:** weighted HR households in each verified Nigeria-release `HV201` source category.
- **Denominator:** all HR households in the table population, with missing information retained as a separate category if present.
- **Source variables:** registered `HV201` source-code measurement plus `HV005`.
- **Weight:** `HV005`.
- **Domain restriction:** national households.
- **Missing treatment:** do not convert missing code `99` into another water category or silently remove its weight from the denominator.
- **Critical release requirement:** the local operator must verify the Nigeria 2018 release-specific mapping from raw `HV201` codes to the report’s detailed source labels. The benchmark must compare only categories whose mapping is explicit.
- **Not an acceptance target:** the report’s **65.7% improved** / **34.2% unimproved** aggregate. The current registry deliberately does not encode that country-/period-sensitive classification, and this commissioning work must not smuggle it in.
- **Likely discrepancy sources:** country-specific code-label mapping, report-era water classification, missing convention, wrong denominator, and independent one-decimal rounding of category cells.
- **Expected recovery:** **Level 3 is meaningful only after release-local code-label validation**; until then the benchmark can reach Level 2 semantic readiness but not claim quantitative category recovery.

### C5 — Nigeria 2018: national de jure population electricity access — MEDIUM

- **Survey/report/reference:** Nigeria DHS 2018, `FR359`, Table 2.4, p. 26.
- **Published statistic:** de jure population living in households with electricity, Total = **56.5%**; No = **43.5%**.
- **Numerator:** `sum(HV005 * HV012)` among HR households with `HV206 = 1`.
- **Denominator:** `sum(HV005 * HV012)` over all HR households contributing de jure members to the table, with missing electricity information kept as a separate category.
- **Source variables:** registered `HV206`; source-native `HV012`; `HV005`.
- **Domain restriction:** national de jure population represented through HR household member counts.
- **Likely discrepancy sources:** accidentally using one row = one household denominator, forgetting `HV012`, using de facto rather than de jure members, or excluding missing electricity from the denominator.
- **Expected recovery:** **Level 3 near-exact** if the benchmark kernel can explicitly declare the auxiliary population-count field.

This is a good denominator-stress test, but it reuses the same substantive source variable as C1 and therefore is not the preferred second benchmark.

### C6 — Nigeria 2018: urban de jure wealth-quintile distribution — MEDIUM

- **Survey:** Nigeria DHS 2018 (`NG2018DHS`).
- **Official report:** `FR359`, Table 2.6, “Wealth quintiles”, p. 28.
- **Published statistic, Urban row:** **[4.2, 8.0, 18.9, 30.6, 38.4]%** for Lowest through Highest.
- **Numerator for quintile q:** `sum(HV005 * HV012)` for urban HR households with `HV270 = q`.
- **Denominator:** `sum(HV005 * HV012)` for urban HR households.
- **Source variables:** registered `HV270`; source-native `HV012`; source-native `HV025` for residence; `HV005`.
- **Domain restriction:** urban (`HV025 = 1` in the DHS-VII standard recode; verify the distributed Nigeria release before execution).
- **Missing treatment:** `HV270` should contain the source-defined quintile; any unexpected missing/unmapped value is a discrepancy to explain, not a case to silently drop.
- **Likely discrepancy sources:** treating quintiles as household shares, omitting `HV012`, wrong urban/rural domain, misbinding `HV270` to a different survey, or applying an experiment-level weight.
- **Expected recovery:** **Level 3 is quantitatively meaningful**, but this candidate depends on auxiliary source-native denominator/domain fields that are not themselves members of the first semantic registry.

This stresses a genuinely different mechanism from electricity: ordinal source semantics plus a population-weighted denominator and a simple domain restriction.

### C7 — Nigeria 2018: national de jure wealth-quintile distribution — LOW

- **Survey/report/reference:** Nigeria DHS 2018, `FR359`, Table 2.6, p. 28.
- **Published pattern:** **20.0% in each quintile** nationally.
- **Source variables / weighting:** `HV270`, `HV012`, `HV005`.
- **Why LOW:** DHS constructs national wealth quintiles by ranking the de jure population and dividing it into five approximately equal groups. Recovering 20/20/20/20/20 is therefore partly a construction identity and is much less diagnostic than the urban distribution in C6.
- **Useful role:** denominator sanity check after a more informative wealth benchmark, not a first commissioning target.

## Recommended first commissioning sequence

### 1. Nigeria 2018 national household electricity — start here

Use C1 as the first real-data benchmark. It is a direct match to the current registry and should support genuine Level 3 quantitative recovery without a country-specific category map.

### 2. Nigeria 2018 detailed drinking-water source distribution — conditional second

Use C4 next **only after** the local Nigeria 2018 `HV201` value-label mapping has been verified against the distributed release metadata/codebook. This tests categorical passthrough and missing/category handling without inventing improved-water semantics.

If that release-local mapping is not available, do not block commissioning by guessing it. Move C4 back to Level 2 readiness and proceed to C6.

### 3. Nigeria 2018 urban de jure wealth-quintile distribution — denominator/domain stress

Use C6 as the third benchmark once the Calibration Lab can declaratively request source-native auxiliary fields `HV012` and `HV025` alongside the registered `HV270` measurement. Do not add fake semantic registry entries merely to make the benchmark convenient.

Keeping the first three on one Nigeria 2018 HR release minimizes local protected-data handling while exercising three different failure modes: binary semantics + household weights; country-specific categorical semantics; and de jure population weighting + domain restriction.

C2 and C3 are then strong cross-survey replications when authorized Uganda/Zambia HR releases are locally available.

## Draft benchmark specs

At the time of this research pass, the emerging Calibration Lab commissioning-spec API is not present on `main` and no stable calibration-kernel branch/PR is available to consume. The drafts below are therefore **declarative handoff sketches**, not a competing executable schema. Field names should be mapped onto the kernel once its API lands.

The recovery-level descriptions below are intentionally minimal:

- **L1 — identity/reference:** exact external reference and survey/release identity resolved.
- **L2 — semantic readiness:** required measurement, weight, denominator/domain, and missing policy are explicit and available.
- **L3 — quantitative recovery:** the independently computed statistic satisfies the published-value discrepancy policy.

### Draft A — household electricity

```yaml
benchmark_id: dhs.ng2018.household_electricity.national
purpose: calibration
kind: commissioning
reference:
  authority: The DHS Program
  publication: Nigeria Demographic and Health Survey 2018
  publication_id: FR359
  url: https://www.dhsprogram.com/pubs/pdf/FR359/FR359.pdf
  table: "2.4 Household characteristics"
  page: 26
  cell: "Electricity / Yes / Households / Total"
required_survey:
  dhs_survey_id: NG2018DHS
  phase: DHS-VII
  recode_family: HR
  release_policy: bind to the exact locally registered HR release and SourceSnapshotRef; never infer release identity from filename
required_empirical_measurement: dhs.household.electricity_access
source_variable: HV206
weight:
  source_variable: HV005
  scale: arbitrary_common_scalar
  note: HV005 and HV005/1000000 yield the same percentage
population:
  unit: household
  domain: national
  denominator: all HR households in the published table population
missing_policy: retain source missing as a separate denominator category; never coerce missing to no and never drop it silently
expected:
  percent_yes: 59.4
  percent_no: 40.6
discrepancy_policy:
  primary: recomputed percentages must round to the published one-decimal cells
  diagnostic_abs_tolerance_percentage_points: 0.05
  investigate_before_code_change: true
recovery_levels:
  L1: reference and NG2018DHS release identity resolved
  L2: HV206 semantics, HV005 weight, household denominator, and missing policy verified
  L3: weighted national percentages recover 59.4/40.6 under report rounding
```

### Draft B — drinking-water source distribution

```yaml
benchmark_id: dhs.ng2018.drinking_water_source_distribution.national
purpose: calibration
kind: commissioning
reference:
  authority: The DHS Program
  publication: Nigeria Demographic and Health Survey 2018
  publication_id: FR359
  url: https://www.dhsprogram.com/pubs/pdf/FR359/FR359.pdf
  table: "2.1.1 Household drinking water"
  page: 21
required_survey:
  dhs_survey_id: NG2018DHS
  phase: DHS-VII
  recode_family: HR
required_empirical_measurement: dhs.household.drinking_water_source_code
source_variable: HV201
weight:
  source_variable: HV005
population:
  unit: household
  domain: national
  denominator: all HR households in the published table population
category_policy:
  require_release_local_code_to_report_label_mapping: true
  prohibit_inferred_improved_unimproved_mapping: true
missing_policy: preserve code 99/source missing as its own status/category and do not silently shrink the denominator
expected_pattern_percent:
  piped_into_dwelling_yard_plot: 3.0
  piped_to_neighbour: 0.7
  public_tap_standpipe: 7.5
  tube_well_or_borehole: 37.2
  protected_dug_well: 11.4
  protected_spring: 0.5
  rainwater: 2.0
  tanker_truck_or_cart_small_tank: 2.6
  bottled_water: 0.7
  unprotected_dug_well: 13.5
  unprotected_spring: 1.6
  surface_water: 9.4
  sachet_water: 9.8
  other: 0.1
discrepancy_policy:
  primary: each verified detailed category must round to its published one-decimal cell
  do_not_require_rounded_subcells_to_equal_published_group_heading: true
  investigate_before_code_change: true
recovery_levels:
  L1: reference and NG2018DHS release identity resolved
  L2: HV201 plus release-local code-label mapping, HV005, denominator, and missing policy verified
  L3: all verified detailed source-category cells recover under report rounding
```

### Draft C — urban wealth-quintile distribution

```yaml
benchmark_id: dhs.ng2018.wealth_quintile.urban_dejure_population
purpose: calibration
kind: commissioning
reference:
  authority: The DHS Program
  publication: Nigeria Demographic and Health Survey 2018
  publication_id: FR359
  url: https://www.dhsprogram.com/pubs/pdf/FR359/FR359.pdf
  table: "2.6 Wealth quintiles"
  page: 28
  row: Urban
required_survey:
  dhs_survey_id: NG2018DHS
  phase: DHS-VII
  recode_family: HR
required_empirical_measurement: dhs.household.wealth_quintile
source_variable: HV270
required_source_native_auxiliary_fields:
  de_jure_members: HV012
  residence: HV025
  household_weight: HV005
population:
  unit: de_jure_person_represented_via_household_count
  domain: "HV025 = 1 (urban), after release-specific validation"
  denominator: sum(HV005 * HV012) in the urban domain
expected_pattern_percent:
  lowest: 4.2
  second: 8.0
  middle: 18.9
  fourth: 30.6
  highest: 38.4
discrepancy_policy:
  primary: each quintile percentage must round to the published one-decimal cell
  investigate_before_code_change: true
recovery_levels:
  L1: reference and NG2018DHS release identity resolved
  L2: HV270 semantics and HV012/HV025/HV005 denominator/domain facts verified
  L3: urban de jure population distribution recovers the five published cells
```

## Discrepancy policy

A commissioning miss is evidence to investigate, not a target for code tuning.

For every run record both the unrounded estimate and the rendered comparison value, then classify discrepancies before changing any implementation:

1. **Reference/release mismatch.** Confirm the final report, survey identifier, survey phase, HR release, snapshot hash, and registry/codebook provenance refer to the same survey product.
2. **Denominator mismatch.** Distinguish households from de jure population. Population tabulations from HR require `HV012`; household tabulations do not. Never let a convenient non-null subset become the denominator implicitly.
3. **Missing-value mismatch.** DHS percent distributions can include missing information as a separate category. The current semantic registry deliberately distinguishes source missing from observed zero/false. Do not drop missing rows merely because the normalized numeric value is null.
4. **Weight mismatch.** `HV005` is the household sample weight. Raw `HV005` versus `HV005 / 1,000,000` is a common scalar and therefore should not alter percentages. A difference caused only by this normalization is not a scientific discrepancy; a different or absent weight is.
5. **Published rounding.** These report cells are displayed to one decimal. Primary acceptance should be that the independently computed estimate renders to the same one-decimal value. An absolute 0.05 percentage-point diagnostic bound may be used around the displayed value, with a tiny numerical epsilon; do not demand equality of unrounded values that the report does not publish.
6. **Country-specific category mapping.** Especially for `HV201`, verify release-local raw-code labels before comparing named report categories. Do not reverse-engineer a mapping from the desired percentages.
7. **Survey subpopulation/domain.** Verify national versus urban/rural and household versus de jure population domains. For C6, validate `HV025` against the distributed Nigeria release before applying the standard DHS-VII `1 = Urban` code.
8. **Rounded subtotal behavior.** Independently rounded detailed category cells need not sum exactly to independently computed/published group headings. Do not “fix” individual category estimates to force a displayed subtotal.

The rule is: **explain differences; never tune code until a report number matches.**

## Local-data handoff

No protected DHS microdata should be uploaded to GitHub, a PR, chat, CI, or a fixture. Real HR files remain external and are bound through `SourceSnapshotRef` plus SHA-256.

### To run Draft A / C1

The local operator needs:

- authorized **Nigeria DHS 2018 HR** data corresponding to DHS survey `NG2018DHS`;
- verified `DhsHrMetadata` / `SurveyCatalogEntry` for that exact local release, with `survey_phase = DHS-VII`;
- a registered immutable HR `SourceSnapshotRef` and resulting content-hashed HR Silver `DatasetRef`;
- the current DHS-VII registry entry for `HV206` and its materialized `dhs.household.electricity_access` rows;
- `HV005` preserved on the matching HR Silver rows;
- official final report `FR359`, Table 2.4, p. 26.

Before execution, confirm the local release-specific recode documentation agrees with the standard `HV206` definition/codes. The repository should retain only aggregate benchmark output, QA, hashes, and provenance—not microdata.

### To run Draft B / C4

In addition to the Nigeria 2018 components above, the operator needs:

- the registry/materialization for `HV201` (`dhs.household.drinking_water_source_code`);
- the **release-local Nigeria 2018 raw-code to water-source label mapping** from authoritative distributed metadata/codebook material;
- official final report `FR359`, Table 2.1.1, p. 21.

If the release-local mapping is not explicit, stop at semantic readiness. Do not infer the mapping from report percentages and do not introduce an “improved water” semantic measurement as part of this commissioning task.

### To run Draft C / C6

The operator needs:

- the same authorized Nigeria 2018 HR release and survey identity;
- the registry/materialization for `HV270` (`dhs.household.wealth_quintile`);
- source-native `HV012`, `HV025`, and `HV005` retained in HR Silver;
- release-specific validation that the residence code used for the urban domain matches the DHS-VII standard meaning;
- official final report `FR359`, Table 2.6, p. 28.

No new upstream measurement should be fabricated just to satisfy this benchmark. If the Calibration Lab cannot yet request auxiliary source-native denominator/domain fields declaratively, this benchmark should remain queued rather than weakening the empirical boundary.

## Commissioning order after the first survey

Once Nigeria C1/C4/C6 have characterized the different mechanisms, repeat the electricity benchmark against Uganda 2016 (C2) and Zambia 2018 (C3) when those authorized HR releases are available locally. The cross-survey repetitions are valuable because a benchmark that works only for one survey can still hide survey-identity, release-binding, or source-code assumptions.

The national wealth 20/20/20/20/20 check (C7) is best retained as a cheap diagnostic, not promoted to a headline commissioning success.
