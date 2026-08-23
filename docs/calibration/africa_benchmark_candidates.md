# Africa observability benchmark candidates

**Status:** research memo / commissioning design, 2026-08-23  
**Purpose:** `calibration`  
**Destination:** FCV Africa Observability Lab / `fcv-experiment-harness`  
**Scope:** published external results that can test the FCV scientific instrument. This memo does **not** implement, re-estimate, extend, or reinterpret any paper as a new FCV substantive result.

## Executive decision

Recommend two first published-study calibration benchmarks:

1. **Briggs (2017), _Does Foreign Aid Target the Poorest?_** — a deliberately simple regional result that directly stresses DHS household identity, `HV270` semantics, survey/sample weights, denominator construction, survey-region geography, and geocoded aid aggregation.
2. **Breckner & Sunde (2019), _Temperature extremes, global warming, and armed conflict: new insights from high resolution data_** — an Africa-wide monthly ACLED × weather result with a versioned Harvard Dataverse replication package that stresses event ingestion, temporal aggregation, spatial binning, structural zeros/coverage, external exposure construction, and fixed-effects estimation.

These two are complementary. Briggs is primarily a **survey/weighting/denominator/geography** benchmark. Breckner–Sunde is primarily an **event/time/geography/external-shock** benchmark.

Do **not** make exact coefficient equality the universal pass condition. For both benchmarks, pipeline reconstruction and qualitative recovery are first-class acceptance levels. Quantitative compatibility is conditional on recovering the same historical source releases and transformations.

No draft `BenchmarkSpec` files are added here. As of the branch point from current `main`, no merged/stable `BenchmarkSpec` / `CalibrationResult` public API was found; inventing one in this research branch would create avoidable integration work with the calibration-kernel branch.

---

## 1. What makes a useful calibration benchmark?

A benchmark is useful when failure has diagnostic meaning. The desired question is not “is this an interesting result?” but:

> If our rebuilt empirical instrument is correct, should it reproduce an externally documented measurement or relationship?

The best benchmarks therefore have:

- identifiable source releases and legal local acquisition paths;
- transparent natural grain and geography;
- a simple enough transformation chain that disagreement can be localized;
- a strong/stable enough signal to avoid treating sampling noise as an engineering failure;
- replication code/data or unusually explicit construction documentation;
- overlap with current FCV components rather than requiring an unrelated one-off data platform;
- complementary stress relative to other benchmarks.

### Candidate categories

The search used five categories as a **coverage guide**, not a quota:

- **A — DHS household + survey weights:** tests survey identity, source-variable semantics, missingness, weights, denominator/sample definition, and regional aggregation.
- **B — DHS cluster geography + external spatial variable:** tests displaced DHS coordinates, radius/spatial membership, temporal alignment, and an externally located exposure.
- **C — geocoded development/investment + survey outcome:** tests project identity/location/timing, survey geography, status-at-observation, and respondent/cluster exposure.
- **D — area-period conflict + external exposure/shock:** tests event semantics, structural zeros/coverage, point-to-area assignment, periodization, external covariate alignment, and panel design.
- **E — cross-source / convergent-validity measurement:** tests whether distinct source families yield documented directional agreement/disagreement without requiring them to be ontologically identical.

Not every category should be commissioned immediately. In particular, current FCV capability makes respondent-level Afrobarometer and DHS birth-history studies substantially more expensive than HR-level DHS or ACLED-event benchmarks.

---

## 2. Current FCV capability relevant to benchmark choice

This memo evaluated candidates against the current repositories rather than against an imagined future system.

### DHS

`fcv-empirical-data` currently keeps DHS products at their natural grains:

- HR household Silver;
- GE/GPS cluster Silver with explicitly displaced/reported coordinates;
- GC cluster measurements with explicit temporal semantics;
- cross-product survey/cluster QA;
- a deliberately small codebook-backed household registry.

The current household semantic registry supports only:

- `HV206` → `dhs.household.electricity_access`;
- `HV270` → `dhs.household.wealth_quintile`;
- `HV201` → `dhs.household.drinking_water_source_code`.

This strongly favors a first DHS benchmark centered on `HV270` over one requiring birth histories, anthropometrics, fertility, or respondent-attitude recodes.

### ACLED

The rebuilt ACLED vertical already provides source-native event Silver, auditable point geography membership, period assignment, and sparse area-period-native-event Gold. It preserves event rows and source semantics, does not silently turn absent aggregate rows into zero, and treats coverage policy separately from measurement.

This makes an external ACLED benchmark attractive, provided the external shock construction is bounded and historically traceable.

### Investments

World Bank and AidData investment verticals currently rebuild source records and provenance but intentionally do **not** yet own project locations, exposure, or treatment. Published aid-location studies therefore remain useful calibration candidates but require a bounded upstream location/exposure capability before they can be executed from rebuilt sources.

### Spatial foundation

`spatial-data-foundation` already owns immutable source registration, GADM materialization, period indexing, and auditable point-to-polygon membership. Its concrete geography provider is currently GADM. A regular latitude/longitude grid is therefore a bounded capability gap, not an existing first-class geography product.

---

## 3. Candidate set

Eleven studies survived the initial screen. The order below is organizational, not a ranking.

### Candidate 1 — Briggs (2017), _Does Foreign Aid Target the Poorest?_

**Category:** A + C  
**Citation:** Ryan C. Briggs (2017), _International Organization_ 71(1): 187–206. DOI: `10.1017/S0020818316000345`.

**Research question.** Within African recipient countries, do World Bank and African Development Bank projects disproportionately reach regions containing poorer or richer people?

**Countries / period.** 17 countries and 195 regions. DHS surveys: Benin 2006; DRC 2007; Ethiopia 2005; Ghana 2008; Guinea 2005; Kenya 2003; Lesotho 2004; Malawi 2004; Mali 2006; Mozambique 2003; Namibia 2006; Niger 2006; Nigeria 2008; Rwanda 2007–08; Sierra Leone 2008; Tanzania 2004–05; Zambia 2007. Aid outcome uses new WB/AfDB commitments in 2009–2010.

**Source datasets.** DHS household recodes and wealth quintile; geocoded World Bank and African Development Bank project/subproject data; regional area/capital geography; ACLED battles as a control in the published model.

**Natural grain.** Household observations are transformed into **survey region × wealth quintile population shares**; estimation grain is **region** (195 rows across 17 countries).

**Geography.** DHS country-specific survey regions / first-order regional units, not a timeless universal modern ADM1 assumption. Aid locations are aggregated to those regions.

**Estimator/design.** OLS with country fixed effects. Main outcomes include regional share of aid value, regional share of project count, and log total aid value. The paper is explicitly model-based/descriptive rather than a causal identification claim.

**Weights / clustering.** This is the unusually valuable part for commissioning. The published construction weights household observations by the sampling weight and de jure household membership: the working-paper appendix states that the “household membership weight” is typically `HV005 × HV012`. Regression standard errors are robust and clustered by country.

**Key benchmark relationship.** Regions containing a larger share of the **richest** national DHS wealth quintile receive substantially more aid; the poorest-quintile share does not show the corresponding pro-poor relationship.

**Expected sign / magnitude.** Main Table 3 reports coefficients for the richest share of approximately **+0.61** on regional aid-value share and **+0.66** on project share; the logged specification reports about **+0.72** for log richest share. The paper reports that the richest-quintile effect is significant at p<0.05 in **92 of 93** main/robustness tests, versus 3 of 93 for the poorest quintile. This stability is unusually useful for a positive calibration control.

**Replication materials.** Cambridge hosts an 8.4 MB supplementary package alongside the article. The AidData working-paper version contains unusually explicit survey-year and weighting documentation.

**Source-version recoverability.** **High for DHS survey identity; medium-high overall.** The exact 17 DHS surveys are listed and the core DHS variables/weight construction are explicit. The exact historical WB/AfDB geocoded aid releases and regional boundary files should be pinned from the supplement before Level 3; do not substitute a later project database silently.

**Implementation difficulty.** **Medium.** The household calculation is simple and `HV270` is already in the FCV registry. Required additions are `HV005`/`HV012` semantics, survey-region aggregation/crosswalk, AfDB/project-location inputs, and the paper’s historical aid snapshot.

**Calibration value.** **Very high.** It jointly tests survey identity, `HV270`, missingness, weighting, denominators, region membership, aid aggregation, and a simple estimator. A wrong denominator or ignored household size can alter the benchmark before any regression is run.

**Risks / caveats.** DHS microdata are controlled-access and must remain external. Survey regions must be treated as survey-era source geography rather than assumed equal to current GADM polygons. The substantive result is correlational; the calibration goal is reproduction, not endorsement of a causal interpretation.

**Suitability:**
- Source accessibility — **HIGH:** DHS is lawfully obtainable under DHS authorization; publication supplement is public; donor data are historically public, though exact archived releases need pinning.
- Source-version traceability — **HIGH/MEDIUM:** survey identity and construction are excellent; historical WB/AfDB release identity still needs supplement audit.
- Design transparency — **HIGH:** simple region-level transformations and OLS FE.
- Signal strength/stability — **HIGH:** very stable richest-quintile relationship.
- Current FCV overlap — **HIGH:** `HV270`, HR Silver, provenance, GADM machinery, and investment source families already exist.
- Implementation cost — **MEDIUM** (HIGH cost is worse in this scorecard): a few targeted upstream capabilities are missing, not an entirely new vertical.
- Scientific complementarity — **HIGH:** covers the survey/weight/denominator side that ACLED benchmarks do not.

### Candidate 2 — Kotsadam et al. (2018), _Development aid and infant mortality. Micro-level evidence from Nigeria_

**Category:** B + C  
**Citation:** Andreas Kotsadam, Gudrun Østby, Siri Aas Rustad, Andreas Forø Tollefsen & Henrik Urdal (2018), _World Development_ 105: 59–69. DOI: `10.1016/j.worlddev.2017.12.022`.

**Research question.** Does proximity to active development-aid projects reduce infant mortality in Nigeria?

**Countries / period.** Nigeria; DHS rounds 1990, 2003, 2008, 2010, 2013. Retrospective birth histories span 1953–2013. AidData Nigeria release is explicitly identified as **Release Level 1 v1.0, August 2015**.

**Source datasets.** Five Nigerian DHS surveys; AidData Nigeria geocoded aid (621 projects, 1,843 locations in the cited release).

**Natural grain.** Live birth / child, nested in mother and DHS cluster; 294,835 reported live births in the source description.

**Geography.** DHS cluster points matched to aid project locations with 25 km and 50 km buffers.

**Estimator/design.** Difference-in-differences-style active/inactive exposure and a preferred mother-fixed-effects model exploiting siblings born before/after nearby aid activation.

**Weights / clustering.** Survey weights are not the central identifying device in the reported preferred model. Robust standard errors are clustered at the DHS cluster level; models include birth-order FE, multiple-birth control, and birth-year trend.

**Key benchmark relationship.** Proximity to active aid reduces infant mortality, including within-mother comparisons.

**Expected sign / magnitude.** Preferred mother-FE estimate is about **−0.01 probability**, interpreted by the authors as roughly **10 fewer infant deaths per 1,000 live births**. The paper reports a sample infant mortality rate around 92/1,000.

**Replication materials.** Article is open access and the data construction is unusually explicit; supplemental material exists. A clean journal-hosted full reconstruction package was not as easily identifiable as for Blair/Breckner–Sunde.

**Source-version recoverability.** **High** for AidData Nigeria and DHS survey identity.

**Implementation difficulty.** **High now.** Current FCV DHS is HR-household based; this benchmark needs birth-history/BR or IR/Women recodes, mother/child identity, mortality timing, and life-history semantics.

**Calibration value.** **High eventually**, especially for displaced-cluster geography plus time-varying project exposure. It is not the cheapest first DHS commissioning standard.

**Risks / caveats.** Implementing it first would conflate calibration with building a new DHS observation vertical. DHS coordinate displacement interacts directly with 25/50 km buffers and must be treated as measurement uncertainty, not exact location.

**Suitability:** accessibility **HIGH/MEDIUM**; traceability **HIGH**; transparency **HIGH**; signal **HIGH**; current overlap **MEDIUM/LOW**; implementation cost **HIGH**; complementarity **HIGH**.

### Candidate 3 — Blair, Marty & Roessler (2022), _Foreign Aid and Soft Power_

**Category:** C  
**Citation:** Robert A. Blair, Robert Marty & Philip Roessler (2022), _British Journal of Political Science_ 52(3): 1355–1376. DOI: `10.1017/S0007123421000193`.

**Research question.** Do Chinese and US aid generate donor affinity and political-value changes among nearby African survey respondents?

**Countries / period.** 38 African countries; Afrobarometer survey waves matched to temporally classified aid projects.

**Source datasets.** Afrobarometer; AidData Chinese projects; country Aid Information Management Systems for US/other aid; supporting conflict/protest information in robustness checks.

**Natural grain.** Afrobarometer respondent / survey community with project-exposure links.

**Geography.** Baseline 30 km exposure. Chinese project geocodes are restricted to relatively precise locations; project state is defined relative to survey timing.

**Estimator/design.** Spatial difference-in-differences contrasting respondents near completed/ongoing projects with respondents near planned/future project sites, with covariates and fixed effects.

**Weights / clustering.** Published/working-paper tables use OLS and community-clustered standard errors. Exact survey-weight policy should be read from the deposited replication code rather than inferred.

**Key benchmark relationship.** Chinese aid does not improve and may reduce support for China; US aid increases support for the US and strengthens some liberal-democratic attitudes.

**Expected sign / magnitude.** The most useful calibration target is not one universal coefficient but the documented **completed-versus-planned contrast** at the 30 km baseline and its donor-direction pattern. The working paper reports several effects in roughly tenths of outcome scale units depending on outcome.

**Replication materials.** **Excellent:** Harvard Dataverse V1, DOI `10.7910/DVN/HEZ7ZV`, explicitly linked by Cambridge.

**Source-version recoverability.** **High** at the replication-package level.

**Implementation difficulty.** **High in current FCV.** The harness already encodes many Blair timing/buffer concepts, but current upstream repos do not rebuild respondent-level Afrobarometer or project-location exposure.

**Calibration value.** **High**, especially as an eventual end-to-end experiment-state benchmark. Not selected first because too many currently absent empirical components would fail simultaneously.

**Risks / caveats.** A replication-package run can succeed without validating FCV’s own source rebuild; these must be separate stages. Avoid treating planned projects as generic untreated observations outside the exact paper logic.

**Suitability:** accessibility **HIGH**; traceability **HIGH**; transparency **HIGH**; signal **MEDIUM/HIGH**; current overlap **MEDIUM**; implementation cost **HIGH**; complementarity **HIGH**.

### Candidate 4 — Isaksson & Kotsadam (2018), _Chinese aid and local corruption_

**Category:** C  
**Citation:** Ann-Sofie Isaksson & Andreas Kotsadam (2018), _Journal of Public Economics_ 159: 146–159. DOI: `10.1016/j.jpubeco.2018.01.002`.

**Research question.** Does living near an active Chinese aid project increase experienced local corruption relative to living near a not-yet-active project location?

**Countries / period.** 29 African countries; Afrobarometer 2002–2013; Chinese projects 2000–2012.

**Source datasets.** Afrobarometer plus geocoded Chinese Official Finance to Africa (AidData vintage around v1.1/v1.1.1).

**Natural grain.** Respondent / Afrobarometer survey cluster.

**Geography.** Distance to Chinese project sites, with baseline 50 km active/inactive exposure.

**Estimator/design.** Difference-in-differences-type active-versus-inactive project-site comparison with 352 subnational-region FE, year FE, and individual controls.

**Weights / clustering.** Baseline robust SE are clustered at geographical survey clusters; robustness includes region, country, and multi-way clustering. Survey weighting is not the defining ingredient of the result.

**Key benchmark relationship.** Bribe experience is higher near active Chinese sites than near inactive/future sites.

**Expected sign / magnitude.** Baseline active-minus-inactive differences are positive; for police bribes the working/public versions report differences around **+0.06 probability** in key specifications.

**Replication materials.** Working-paper PDF and detailed appendix are public; no journal-linked versioned replication deposit surfaced as cleanly as Blair’s.

**Source-version recoverability.** **Medium-high.** AidData version family and Afrobarometer waves are identifiable, but the exact computational package is less clean.

**Implementation difficulty.** **High** given absent respondent-Afrobarometer rebuild and project-location exposure.

**Calibration value.** **High but dominated by Blair for first commissioning** because Blair offers a cleaner versioned replication anchor while stressing nearly the same project-state/spatial machinery.

**Risks / caveats.** Historical geocoding/version changes; respondent-source reconstruction; exact active/inactive timing semantics.

**Suitability:** accessibility **HIGH/MEDIUM**; traceability **MEDIUM/HIGH**; transparency **HIGH**; signal **HIGH**; current overlap **MEDIUM**; implementation cost **HIGH**; complementarity **MEDIUM**.

### Candidate 5 — Knutsen et al. (2017), _Mining and Local Corruption in Africa_

**Category:** B / external point exposure + survey  
**Citation:** Carl Henrik Knutsen, Andreas Kotsadam, Eivind Hammersmark Olsen & Tore Wig (2017), _American Journal of Political Science_ 61(2): 320–334. DOI: `10.1111/ajps.12268`.

**Research question.** Does opening an industrial mine increase local corruption?

**Countries / period.** 33-country baseline sample; Afrobarometer rounds 2–5 plus South Africa round 2.5; 92,762 respondents and 496 industrial mines.

**Source datasets.** Afrobarometer; industrial-mine location/opening data assembled by the authors; supplementary geocoding sources.

**Natural grain.** Respondent / enumeration area or town, linked to mine state.

**Geography.** Baseline 50 km active/inactive mine exposure; 25 km robustness.

**Estimator/design.** Difference-in-differences active-versus-inactive mine comparison, country and year FE, respondent controls.

**Weights / clustering.** No survey-weight-driven benchmark. Baseline robust SE clustered at EA/town; appendix also clusters at closest mine.

**Key benchmark relationship.** Mine opening raises bribe payment, particularly police bribes.

**Expected sign / magnitude.** Baseline police-bribe active-minus-inactive contrast is about **+0.074** in the 33-country sample.

**Replication materials.** Author page exposes replication files and an online appendix; Wiley hosts supplementary material.

**Source-version recoverability.** **Medium/low.** Mine-location/opening source construction is less standardized and less obviously source-release recoverable than AidData/ACLED.

**Implementation difficulty.** **High.** Requires a new mine-source vertical plus respondent Afrobarometer.

**Calibration value.** **Medium.** Strong pattern but would commission two currently absent source systems, reducing diagnostic specificity.

**Risks / caveats.** Historical geocoding and mine-state provenance; custom source assembly.

**Suitability:** accessibility **MEDIUM**; traceability **LOW/MEDIUM**; transparency **HIGH**; signal **HIGH**; current overlap **LOW**; implementation cost **HIGH**; complementarity **MEDIUM**.

### Candidate 6 — Breckner & Sunde (2019), _Temperature extremes, global warming, and armed conflict_

**Category:** D  
**Citation:** Miriam Breckner & Uwe Sunde (2019), _World Development_ 123: 104624. DOI: `10.1016/j.worlddev.2019.104624`.

**Research question.** Do cell-specific extreme-temperature events increase the monthly incidence of armed conflict across Africa?

**Countries / period.** Entire African continent; monthly 1997–2015.

**Source datasets.** ACLED geocoded events; ECMWF **ERA-Interim** monthly temperature/precipitation; later heterogeneity analyses add gridded population, agricultural productivity, and land degradation. Those mechanism datasets are not required for the minimal calibration benchmark.

**Natural grain.** **0.75° × 0.75° grid cell × month**; 4,826 cells.

**Geography.** Regular lat/lon grid, approximately 83 km side length at the equator.

**Estimator/design.** Linear conflict-incidence model using within-cell/month variation in an extreme-temperature indicator plus weather controls and a rich fixed-effect structure. A longer-run generalized difference-in-differences exercise is secondary and should not be the first calibration target.

**Weights / clustering.** No survey weights. For Level 3, the exact covariance/SE and fixed-effect implementation must be taken verbatim from the deposited code; this memo deliberately does not reverse-engineer an inference policy from prose.

**Key benchmark relationship.** Temperature extremes increase conflict incidence. Effects are stronger when extremes persist for two months than when they last one month.

**Expected sign / magnitude.** **Positive.** The paper emphasizes a robust positive incidence effect and a larger effect for longer-duration extremes. Rather than hard-code a rounded coefficient from secondary text, the calibration target should pin one baseline table/column directly from the Dataverse package during implementation.

**Replication materials.** **Excellent:** Harvard Dataverse DOI `10.7910/DVN/XFTRMY`, explicitly linked by the journal as the paper’s replication code/data.

**Source-version recoverability.** **Medium-high overall.** ERA-Interim, resolution, sample dates, and extreme definition are explicit. The historical ACLED snapshot/release identifier is less explicit than the replication deposit itself. Therefore the deposited constructed data are the authority for Level 3 unless the exact historical ACLED bytes can be recovered.

**Implementation difficulty.** **Medium-high.** FCV already has ACLED events, provenance, point assignment, and period machinery, but needs a first-class regular-grid geography and monthly period use plus ERA-Interim exposure construction.

**Calibration value.** **Very high.** The result simultaneously tests ACLED event semantics, location, month assignment, zero/coverage policy, regular-grid membership, external weather alignment, and a simple panel regression.

**Risks / caveats.** ACLED is a living dataset; a current export is not equivalent to the authors’ historical snapshot. ERA5 must not be substituted for ERA-Interim for Level 3. The first benchmark should exclude mechanism heterogeneity to keep the transformation chain diagnostic.

**Suitability:**
- Source accessibility — **HIGH:** versioned replication deposit; identifiable climate source; ACLED is obtainable under its access terms.
- Source-version traceability — **MEDIUM/HIGH:** excellent replication reference, weaker exact historical ACLED snapshot identity.
- Design transparency — **HIGH:** simple monthly grid-cell outcome/exposure before optional mechanisms.
- Signal strength/stability — **HIGH:** positive effect plus duration ordering.
- Current FCV overlap — **MEDIUM/HIGH:** ACLED vertical is directly relevant; grid/month capability is the main gap.
- Implementation cost — **MEDIUM/HIGH:** bounded but real new grid/climate work.
- Scientific complementarity — **HIGH:** stresses entirely different failure modes from Briggs.

### Candidate 7 — Harari & La Ferrara (2018), _Conflict, Climate, and Cells: A Disaggregated Analysis_

**Category:** D  
**Citation:** Mariaflavia Harari & Eliana La Ferrara (2018), _Review of Economics and Statistics_ 100(4): 594–608. DOI: `10.1162/rest_a_00730`.

**Research question.** Do adverse weather shocks during the local growing season increase subsequent local conflict?

**Countries / period.** 46 African countries; approximately 2,700 1° × 1° cells; 1997–2011.

**Source datasets.** ACLED (**Fall 2012** vintage documented in the paper); UCDP GED v2.0 robustness; M3-Crops; MIRCA/SAGE crop calendars; ECMWF ERA-Interim/SPEI construction; terrain, ethnicity and other controls.

**Natural grain.** Grid cell × year, with monthly climate/crop information collapsed into growing-season shocks.

**Geography.** 1° regular grid, crop-season-specific exposure.

**Estimator/design.** Cell FE, country×year controls/fixed effects and spatial-dynamic specifications; the design explicitly distinguishes growing-season from non-growing-season weather.

**Weights / clustering.** No survey weights; inference addresses spatial dependence as part of the model. Exact implementation should be taken from the original code if a replication package is recovered.

**Key benchmark relationship.** Adverse growing-season climate shocks increase conflict; analogous shocks outside the growing season are close to zero.

**Expected sign / magnitude.** The published discussion gives an effect around **+1.3 percentage points** in conflict probability for a one-SD adverse growing-season shock (roughly 8% of the unconditional mean in the cited specification), plus positive temporal/spatial conflict persistence.

**Replication materials.** Article and appendices are well documented, but a clean public versioned replication package did not surface in this scout.

**Source-version recoverability.** **Medium.** The ACLED vintage and many external sources are unusually explicit, but historical ACLED Fall 2012 and the complete transformation stack may be difficult to reconstruct byte-for-byte today.

**Implementation difficulty.** **High.** Crop maps, calendars, SPEI, grid geography, and spatial dynamics create many simultaneous failure points.

**Calibration value.** **High scientifically, lower for first commissioning.** It is a good later stress test after a simpler ACLED×weather benchmark passes.

**Risks / caveats.** High transformation complexity makes discrepancy diagnosis expensive; historical source availability.

**Suitability:** accessibility **MEDIUM/HIGH**; traceability **MEDIUM**; transparency **HIGH**; signal **HIGH**; current overlap **MEDIUM**; implementation cost **HIGH**; complementarity **HIGH**.

### Candidate 8 — Berman et al. (2017), _This Mine Is Mine! How Minerals Fuel Conflicts in Africa_

**Category:** D  
**Citation:** Nicolas Berman, Mathieu Couttenier, Dominic Rohner & Mathias Thoenig (2017), _American Economic Review_ 107(6): 1564–1610. DOI: `10.1257/aer.20150774`.

**Research question.** Does mining activity, interacted with exogenous world mineral-price changes, increase local conflict?

**Countries / period.** All Africa; 1997–2010.

**Source datasets.** Georeferenced mine extraction for 14 minerals; ACLED conflict events; world mineral prices; supporting actor/rebel data.

**Natural grain.** 0.5° × 0.5° grid cell × year.

**Geography.** Regular grid.

**Estimator/design.** Panel models exploiting mine presence/extraction × global mineral-price variation; multiple conflict outcomes and escalation analyses.

**Weights / clustering.** No survey weights. Exact FE/inference are fully recoverable from deposited do-files and should be treated as code-defined for any Level 3 attempt.

**Key benchmark relationship.** Mining × mineral-price increases local conflict probability/intensity.

**Expected sign / magnitude.** Positive. Authors estimate that the historical commodity super-cycle may explain up to roughly **one quarter** of average violence over the sample.

**Replication materials.** **Excellent:** AEA-linked openICPSR V1, DOI `10.3886/E113068V1`, with data, construction do-files, table do-files, and result logs.

**Source-version recoverability.** **Mixed.** Replication inputs are very well packaged, but the underlying mine source includes Raw Materials Data / IntierraRMG-era commercial information. That weakens independent source reconstruction.

**Implementation difficulty.** **High** for an FCV-source rebuild; lower if merely replaying deposited constructed data.

**Calibration value.** **Medium-high**, but not selected because an opaque/proprietary upstream source makes a failed independent reconstruction difficult to interpret and conflicts with the preference for lawfully recoverable source releases.

**Risks / caveats.** Replicating the package is not the same as validating a source rebuild. Do not make proprietary mine data a foundational FCV dependency merely to obtain a famous coefficient.

**Suitability:** accessibility **MEDIUM**; traceability **HIGH for deposit / LOW-MEDIUM for raw mine source**; transparency **HIGH**; signal **HIGH**; current overlap **MEDIUM**; implementation cost **HIGH**; complementarity **MEDIUM**.

### Candidate 9 — von Uexkull et al. (2016), _Civil conflict sensitivity to growing-season drought_

**Category:** D + E  
**Citation:** Nina von Uexkull, Mihai Croicu, Hanne Fjelde & Halvard Buhaug (2016), _PNAS_ 113(44): 12391–12396. DOI: `10.1073/pnas.1607542113`.

**Research question.** Does growing-season drought increase civil-conflict risk for politically relevant ethnic groups, especially under agricultural dependence and political exclusion?

**Countries / period.** 316 politically relevant ethnic groups in 63 countries across Africa and Asia (excluding the Middle East), 1989–2014; Africa can be isolated for FCV.

**Source datasets.** UCDP GED v4.0; ACD2EPR; GeoEPR-ETH v2.0; PRIO-GRID 0.5°; SPAM 2005; MIRCA/SAGE crop calendars; SPEI; WDI controls.

**Natural grain.** Ethnic group × year, constructed from 0.5° cells and monthly climate.

**Geography.** Ethnic settlement polygons over PRIO-GRID.

**Estimator/design.** Multilevel models for conflict onset/incidence with lagged drought, group trends and vulnerability interactions.

**Weights / clustering.** No survey weights; hierarchical/group structure is intrinsic to the model.

**Key benchmark relationship.** Average drought-conflict effects are conditional rather than universally large; drought raises sustained violence especially for agriculturally dependent or politically excluded groups in very poor settings.

**Expected sign / magnitude.** Positive in the vulnerable-group interactions; weaker/limited unconditional effect.

**Replication materials.** **Excellent:** replication data are explicitly hosted by Uppsala/PRIO.

**Source-version recoverability.** **High.** Major source versions are named.

**Implementation difficulty.** **High.** FCV currently lacks UCDP/EPR ethnic-group geography and crop-calendar products.

**Calibration value.** **Medium for first wave, high later.** Excellent reproducibility, but would commission too many new source families before testing existing ACLED capability.

**Risks / caveats.** Conditional signal is less convenient as a simple positive control; one-off ethnic-group geography could distract from FCV’s present bottleneck.

**Suitability:** accessibility **HIGH**; traceability **HIGH**; transparency **HIGH**; signal **MEDIUM**; current overlap **LOW**; implementation cost **HIGH**; complementarity **MEDIUM/HIGH**.

### Candidate 10 — Gehring, Kaplan & Wong (2022), _China and the World Bank—How contrasting development approaches affect the stability of African states_

**Category:** C + D + E  
**Citation:** Kai Gehring, Lennart Kaplan & Melvin H. L. Wong (2022), _Journal of Development Economics_ 158: 102902. DOI: `10.1016/j.jdeveco.2022.102902`.

**Research question.** Do georeferenced Chinese and World Bank aid projects have different associations with local conflict, unrest, repression, and political attitudes?

**Countries / period.** African first-order subnational regions; WB sample roughly 1995–2012 aid / subsequent conflict, China roughly 2000–2012 aid / subsequent conflict.

**Source datasets.** Georeferenced World Bank and Chinese aid; conflict and social-unrest sources; Afrobarometer for attitudes; auxiliary geographic/economic controls.

**Natural grain.** Main conflict lane: ADM1-like region × year; attitude lane: survey respondent.

**Geography.** First-order subnational regions plus geocoded project assignment.

**Estimator/design.** Region FE, country-year FE variants, regional/country time trends, lagged aid; IV strategies as additional identification.

**Weights / clustering.** Main conflict specifications use two-way clustering at region and country-year; appendix demonstrates robustness to region, country-year, or country clustering.

**Key benchmark relationship.** Neither donor increases local conflict on average; World Bank aid has a stable negative association after region FE, while Chinese aid is mostly negative/insignificant. Attitude results differ by donor regime.

**Expected sign / magnitude.** For WB, a one-SD increase in logged aid is associated with roughly **1.5–2.0 percentage points lower** conflict likelihood in the reported preferred regional specifications; Chinese coefficients are smaller and statistically weak.

**Replication materials.** Detailed appendix is public. A clean versioned replication repository did not surface in this scout.

**Source-version recoverability.** **Medium.** Source families are identifiable, but the full multi-source release stack is substantial.

**Implementation difficulty.** **High.** Requires project-location exposure and at least one non-ACLED conflict source plus optionally Afrobarometer.

**Calibration value.** **High later for convergent validity**, especially as a test that donor-source differences survive consistent geography. Not a good first commissioning target because a null/negative pattern is less diagnostic than a strong positive control.

**Risks / caveats.** Multi-outcome scope can become an accidental research program; use one narrow table if commissioned.

**Suitability:** accessibility **MEDIUM/HIGH**; traceability **MEDIUM**; transparency **HIGH**; signal **MEDIUM**; current overlap **MEDIUM**; implementation cost **HIGH**; complementarity **HIGH**.

### Candidate 11 — Briggs (2018), _Poor targeting: A gridded spatial analysis of the degree to which aid reaches the poor in Africa_

**Category:** C + E  
**Citation:** Ryan C. Briggs (2018), _World Development_ 103: 133–148. DOI: `10.1016/j.worlddev.2017.10.020`.

**Research question.** At fine spatial scale, do World Bank and African Development Bank projects target poorer places within African countries?

**Countries / period.** Africa-wide donor sample, roughly 10,500 cells.

**Source datasets.** Geotagged WB/AfDB aid; gridded poverty/development measures including nighttime-light-type proxies and population.

**Natural grain.** Approximately 50 km × 50 km grid cell.

**Geography.** Regular Africa-wide grid.

**Estimator/design.** Within-country/country-FE spatial regressions of aid presence/count/value on poverty measures conditional on population.

**Weights / clustering.** No survey weights. Exact spatial-inference specification should be pinned from the paper/code before commissioning; no versioned replication package was identified in this scout.

**Key benchmark relationship.** Aid tends to flow to relatively richer rather than poorer cells within countries.

**Expected sign / magnitude.** Directionally robust rich-place targeting; the paper reports the conclusion across binary aid presence, project count, and aid value.

**Replication materials.** Article and author materials; no clean journal-linked versioned replication deposit surfaced.

**Source-version recoverability.** **Medium.** Donor sources are identifiable; precise gridded transformations/releases need further archaeology.

**Implementation difficulty.** **Medium-high.** Requires project-location ingestion and regular grid, but not protected microdata.

**Calibration value.** **Medium-high.** Useful later as a cross-check on Briggs (2017): two different poverty/geography measurement systems should point in the same broad direction. It is less diagnostic as the first benchmark because the exact replication surface is weaker.

**Risks / caveats.** Grid-definition and historical remote-sensing version drift; could duplicate rather than complement Briggs (2017) if run too early.

**Suitability:** accessibility **HIGH/MEDIUM**; traceability **MEDIUM**; transparency **HIGH**; signal **HIGH**; current overlap **MEDIUM**; implementation cost **MEDIUM/HIGH**; complementarity **MEDIUM**.

---

## 4. Comparative scorecard

`HIGH` implementation cost means **more expensive / worse**; for all other columns `HIGH` is favorable.

| Candidate | Accessibility | Version traceability | Design transparency | Signal / stability | Current FCV overlap | Implementation cost | Complementarity |
|---|---|---|---|---|---|---|---|
| Briggs 2017 | HIGH | HIGH/MEDIUM | HIGH | HIGH | HIGH | MEDIUM | HIGH |
| Kotsadam et al. 2018 | HIGH/MEDIUM | HIGH | HIGH | HIGH | MEDIUM/LOW | HIGH | HIGH |
| Blair et al. 2022 | HIGH | HIGH | HIGH | MEDIUM/HIGH | MEDIUM | HIGH | HIGH |
| Isaksson & Kotsadam 2018 | HIGH/MEDIUM | MEDIUM/HIGH | HIGH | HIGH | MEDIUM | HIGH | MEDIUM |
| Knutsen et al. 2017 | MEDIUM | LOW/MEDIUM | HIGH | HIGH | LOW | HIGH | MEDIUM |
| Breckner & Sunde 2019 | HIGH | MEDIUM/HIGH | HIGH | HIGH | MEDIUM/HIGH | MEDIUM/HIGH | HIGH |
| Harari & La Ferrara 2018 | MEDIUM/HIGH | MEDIUM | HIGH | HIGH | MEDIUM | HIGH | HIGH |
| Berman et al. 2017 | MEDIUM | MIXED | HIGH | HIGH | MEDIUM | HIGH | MEDIUM |
| von Uexkull et al. 2016 | HIGH | HIGH | HIGH | MEDIUM | LOW | HIGH | MEDIUM/HIGH |
| Gehring et al. 2022 | MEDIUM/HIGH | MEDIUM | HIGH | MEDIUM | MEDIUM | HIGH | HIGH |
| Briggs 2018 | HIGH/MEDIUM | MEDIUM | HIGH | HIGH | MEDIUM | MEDIUM/HIGH | MEDIUM |

### What the scorecard rules out

- **Berman et al.** is not selected despite excellent replication because the commercial mine source weakens independent raw-source commissioning.
- **Harari–La Ferrara** is not selected first because the crop-calendar/SPEI/spatial-dynamic stack introduces too many simultaneous transformations.
- **von Uexkull et al.** has excellent source traceability but would require UCDP + EPR + crop geography, mostly outside current FCV capability.
- **Blair et al.** maps beautifully to the harness’s project-state concepts and should remain a high-priority later benchmark, but respondent-level Afrobarometer and project-location exposure are not yet rebuilt upstream.
- **Kotsadam et al.** is probably the strongest later DHS geography benchmark, but implementing a birth-history DHS vertical merely to commission the current HR instrument would be backwards sequencing.

---

## 5. Recommended benchmark 1: Briggs (2017)

### Calibration statement

```text
purpose = calibration
```

Reproducing Briggs (2017) is evidence that FCV can reconstruct a documented survey-weighted regional wealth distribution and relate it correctly to historical geocoded aid. It is **not** a new FCV estimate of whether aid targets the rich, and it must not be reported as substantive confirmation or extension of the paper.

### Minimal benchmark target

Do not start by reproducing every robustness table. Target the smallest externally anchored chain:

1. reconstruct the five regional wealth-quintile shares for each of the 195 region observations;
2. reproduce the article’s country/region sample and denominator identities;
3. reconstruct one baseline regional aid outcome from the historical WB/AfDB data;
4. reproduce one Table 3 richest/poorest specification with country FE and country-clustered SE;
5. only then add the two alternative aid outcomes as robustness/calibration extensions.

The **richest-quintile relationship** is the positive control. The non-result for the poorest quintile is useful as a secondary specificity check, not as the only pass condition.

### Recovery expectation

**Level 1 — pipeline/data/design reconstruction: EXPECTED.**  
Required evidence:

- exact 17-survey identity;
- household row counts and cluster/region support;
- correct `HV270` category semantics;
- explicit source missingness;
- exact `HV005 × HV012` household-membership weighting rule;
- five wealth-quintile regional shares summing/normalizing as documented;
- 195-region analysis universe or documented reason for any discrepancy;
- historical donor records assigned to the same regional geography;
- design matrix and clustered-SE configuration matching the paper.

**Level 2 — qualitative pattern/sign recovery: EXPECTED.**  
The richest regional population share should have a clearly positive relationship with aid; the poorest share should not exhibit a similarly stable positive relationship. Failure here after Level 1 is a substantive calibration alarm, not an invitation to tune region definitions or outcomes.

**Level 3 — quantitative estimate compatibility: CONDITIONALLY EXPECTED.**  
If the exact DHS survey releases, historical WB/AfDB geocoded aid inputs, survey-region boundaries/crosswalks, exclusions, and transformations from the supplement are recovered, the Table 3 coefficients should be quantitatively compatible with the published values (e.g. richest-share coefficients around +0.61 / +0.66 in the two share outcomes). Exact floating-point equality is unnecessary; confidence intervals, sample identity, and transformation equivalence matter more.

If later donor releases or modern region geometries are substituted, **do not demand Level 3**. That becomes a source-version sensitivity run, where Level 2 is the relevant expectation.

### Exact local-data checklist

#### DHS controlled-access inputs

For each of the following surveys, retain the authorized local HR source file(s), official survey/recode documentation, source filename/release identity, and SHA-256 in the external snapshot system:

- Benin 2006;
- DRC 2007;
- Ethiopia 2005;
- Ghana 2008;
- Guinea 2005;
- Kenya 2003;
- Lesotho 2004;
- Malawi 2004;
- Mali 2006;
- Mozambique 2003;
- Namibia 2006;
- Niger 2006;
- Nigeria 2008;
- Rwanda 2007–08;
- Sierra Leone 2008;
- Tanzania 2004–05;
- Zambia 2007.

Minimum household fields needed for the published construction, subject to each survey’s official HR dictionary:

- household/sample identity and cluster identity needed for QA;
- survey region variable and region labels/codes;
- `HV270` wealth quintile;
- `HV005` household sample weight;
- `HV012` de jure household-member count / household-size field used by the paper;
- source missing-value metadata for all of the above.

Do **not** upload or commit DHS microdata. Use local external snapshots and persist only non-sensitive QA/provenance artifacts.

#### Aid inputs

- Cambridge supplementary package for DOI `10.1017/S0020818316000345` (8.4 MB at time of scout); retain archive hash and extracted README/code hashes.
- Exact historical geocoded **World Bank** project/subproject file used for 2009–2010 new commitments.
- Exact historical geocoded **African Development Bank** project/subproject file used for 2009–2010 new commitments.
- Source codebooks for geocoding precision, project/subproject identity, commitment value, and date fields.
- Any paper-supplied exclusions/country eligibility rules.

The supplement should be treated as the authority for the exact donor-release filenames. Do not infer a historical release from the current FCV AidData/World Bank tables.

#### Geography / controls

- survey-era region polygons or exact paper crosswalks matching each DHS regional sampling domain;
- capital-region indicator/source used by the paper;
- regional area calculation basis;
- exact conflict/battles control source/version and temporal window from the supplement before Level 3.

#### Documentation

- published article;
- Cambridge supplementary package;
- AidData working-paper appendix, especially DHS Table 5 and the weighting construction;
- relevant DHS recode manuals and each survey’s final report / region definitions;
- donor geocoding codebooks.

### Items not represented in current repository capability and therefore likely missing locally unless held outside Git

- the 17 authorized real DHS HR snapshots as registered FCV source inputs;
- registry/semantic definitions for `HV005` and `HV012`;
- historical survey-region boundary/crosswalk assets;
- African Development Bank source vertical / the exact historical geocoded AfDB file;
- project-location membership/exposure materialization for donor projects;
- the Cambridge supplementary archive and exact historical donor snapshots.

These are acquisition/materialization requirements, not a request to upload protected data.

---

## 6. Recommended benchmark 2: Breckner & Sunde (2019)

### Calibration statement

```text
purpose = calibration
```

Reproducing Breckner–Sunde is evidence that FCV can align an external monthly weather shock to a correctly geocoded/periodized ACLED conflict measurement. It does **not** create a new FCV claim that heat causes conflict, and FCV should not tune conflict definitions, grid origin, or weather thresholds to improve the coefficient.

### Minimal benchmark target

Restrict the first run to the baseline short-run result:

1. materialize the exact 0.75° Africa grid / land-cell universe used in the replication package (4,826 cells);
2. map ACLED events to cell × month and construct the paper’s binary conflict-incidence outcome;
3. materialize ERA-Interim monthly temperature/precipitation;
4. reproduce the cell/calendar-month-specific temperature-extreme indicator using the paper’s **1979–1997** reference period and 95th-percentile rule;
5. execute one deposited baseline table/column with the exact fixed effects and covariance estimator from the Dataverse code;
6. separately verify the qualitative duration ordering (two-month extremes > one-month extremes) if it is inexpensive.

Do **not** begin with population-change, agricultural-productivity, land-degradation, or conflict-type heterogeneity. Those are scientifically interesting but reduce commissioning diagnosis.

### Recovery expectation

**Level 1 — pipeline/data/design reconstruction: EXPECTED.**  
Required evidence:

- 4,826-cell universe and exact grid origin/mask from replication materials;
- monthly 1997–2015 analysis index;
- ACLED event-to-cell membership accounting;
- explicit treatment of months with no events, tied to verified historical coverage rather than generic zero filling;
- ERA-Interim 0.75° climate alignment;
- 1979–1997 cell × calendar-month climate reference distribution;
- extreme indicator parity on deposited constructed data;
- exact baseline design matrix / FE / covariance configuration.

**Level 2 — qualitative pattern/sign recovery: EXPECTED.**  
Temperature extremes should have a positive association with monthly conflict incidence, and longer-duration extremes should not reverse the core pattern. A sign failure after Level 1 is a strong alarm about event coverage, grid alignment, month assignment, or climate construction.

**Level 3 — quantitative estimate compatibility: TWO TRACKS.**

- **Replication-package track: EXPECTED.** Running the deposited constructed data with the deposited code should reproduce the selected baseline coefficient/table within software/numerical tolerance. This validates our calibration runner and design transcription.
- **Independent FCV raw-source track: NOT automatically expected.** A modern ACLED export can differ from the authors’ historical event snapshot through backfills, corrections, taxonomy changes, and revised locations. Unless the exact historical ACLED source bytes can be recovered, require Level 1 + Level 2 and report coefficient drift rather than calling it a pipeline failure.

If the exact historical ACLED snapshot is recovered and ERA-Interim/grid transformations match the deposit, Level 3 becomes a reasonable expectation for the independent track.

### Exact local-data checklist

#### Replication reference

- Harvard Dataverse package DOI `10.7910/DVN/XFTRMY`;
- all deposited analysis data, code, README/metadata, and any grid/crosswalk files;
- hashes for each retained file and Dataverse version/UNF if exposed.

This package is the authority for the baseline table/column and grid construction.

#### ACLED

- historical Africa ACLED events covering **1997–2015** with the event taxonomy used by the paper;
- exact historical snapshot/release if recoverable from the replication package, authors, or archived acquisition metadata;
- ACLED codebook corresponding to that vintage;
- event ID, date, coordinates, event type and any fields used to define the binary conflict outcome.

For a current FCV export, register it as a **different source snapshot** and never label it the paper’s source release.

#### Climate

- ECMWF **ERA-Interim** temperature and precipitation at **0.75°** resolution;
- historical reference interval needed for the extreme definition: **1979–1997**;
- analysis-period climate through the paper’s 1997–2015 window (the thesis/source table describes ERA-Interim 1979–2014 while the paper sample extends through 2015; resolve this endpoint from the Dataverse code/data before implementation rather than guessing);
- variable/units documentation and any land/sea mask used by the authors.

Do not substitute ERA5 for ERA-Interim in the Level-3 reference run.

#### Geography / time

- exact 0.75° cell definitions, origin, cell IDs, Africa/land mask and 4,826-cell analysis universe from replication material;
- monthly period scheme 1997-01 through 2015-12;
- explicit point-on-boundary membership policy matching the paper/deposit;
- diagnostics for unmatched/ambiguous event points.

#### Documentation

- World Development article and online appendix;
- Harvard Dataverse README/code;
- ECMWF ERA-Interim documentation / Dee et al. (2011);
- ACLED codebook matching the historical release if recoverable.

### Items not represented in current repository capability and therefore likely missing locally unless held outside Git

- Harvard Dataverse replication snapshot;
- first-class regular 0.75° grid geography materialization;
- monthly period configuration exercised as a production calibration substrate;
- ERA-Interim registered source/materialization and temperature-extreme measurement;
- exact historical 1997–2015 ACLED snapshot used by the authors;
- legacy event-type mapping if the historical taxonomy differs from current ACLED.

The current ACLED event vertical is nevertheless a substantial head start: this benchmark should extend the geography/time/external-covariate seam rather than create a second conflict ingestion system.

---

## 7. Commissioning sequence

The recommended sequence minimizes ambiguous failures.

### Phase 0 — replay reference packages

Before comparing rebuilt FCV sources to a published number:

- execute the selected published code/data in an isolated reproducibility environment where legally possible;
- identify the exact benchmark table/column and analysis sample;
- record software/runtime differences and reference outputs;
- hash all reference inputs.

A failure here is a replication-environment problem, not an FCV empirical-data failure.

### Phase 1 — measurement parity before regression

For Briggs:

- survey/sample identities;
- regional quintile shares;
- weight totals / denominators;
- 195-region universe;
- donor project counts/value by region.

For Breckner–Sunde:

- grid universe;
- event counts/incidence by month/cell;
- weather summaries;
- extreme-indicator prevalence;
- analysis row count and missingness.

Do not run the regression until these objects have explicit parity diagnostics.

### Phase 2 — Level 2 positive-control recovery

Run the minimal estimator with the published design frozen. Evaluate sign/pattern and support. Do not search radii, filters, taxonomies, climate thresholds, or FE variants to obtain the expected direction.

### Phase 3 — conditional quantitative compatibility

Only declare a Level-3 target after source-version equivalence is demonstrated. Otherwise characterize quantitative drift explicitly as a version sensitivity.

---

## 8. Calibration versus substantive FCV inference

Every benchmark run must carry:

```text
purpose = calibration
external_reference = <paper / table / column / replication version>
```

and an explicit statement equivalent to:

> This run characterizes the FCV empirical instrument against a previously published external result. It is not a new FCV substantive hypothesis test, estimate, or replication claim beyond the declared calibration target.

Guardrails:

- do not select among specifications based on which best reproduces the published sign;
- do not reinterpret discrepancies as novel research findings during commissioning;
- do not publish a later-source estimate as “replication” when historical source identity differs;
- do not silently harmonize source taxonomies or geographies to improve agreement;
- preserve failed Level-1/Level-2 diagnostics as instrument evidence;
- treat the paper’s design as externally frozen for the calibration run, even when FCV would choose a different substantive estimator today.

---

## 9. Sources consulted / recovery anchors

Primary or replication sources were preferred over secondary summaries.

### Briggs 2017

- Cambridge article and supplementary material: https://doi.org/10.1017/S0020818316000345
- AidData working paper page: https://www.aiddata.org/publications/does-foreign-aid-target-the-poorest
- Working-paper PDF with survey-year/weight appendix: https://docs.aiddata.org/ad4/files/wps13_does_aid_target_the_poorest.pdf

### Kotsadam et al. 2018

- Open-access article: https://doi.org/10.1016/j.worlddev.2017.12.022
- AidData publication record: https://www.aiddata.org/publications/development-aid-and-infant-mortality-micro-level-evidence-from-nigeria

### Blair, Marty & Roessler 2022

- Cambridge article: https://doi.org/10.1017/S0007123421000193
- Harvard Dataverse V1: https://doi.org/10.7910/DVN/HEZ7ZV
- AidData publication record: https://www.aiddata.org/publications/foreign-aid-and-soft-power-great-power-competition-in-africa-in-the-early-twenty-first-century-journal

### Isaksson & Kotsadam 2018

- Journal DOI: https://doi.org/10.1016/j.jpubeco.2018.01.002
- AidData working paper: https://docs.aiddata.org/ad4/files/wps33_chinese_aid_and_local_corruption.pdf

### Knutsen et al. 2017

- Wiley article: https://doi.org/10.1111/ajps.12268
- PRIO publication record: https://www.prio.org/publications/10930
- Author replication index: https://eivindhammers.github.io/

### Breckner & Sunde 2019

- World Development article: https://doi.org/10.1016/j.worlddev.2019.104624
- Harvard Dataverse replication: https://doi.org/10.7910/DVN/XFTRMY
- Miriam Breckner dissertation appendix with source-construction table: https://edoc.ub.uni-muenchen.de/23734/1/Breckner_Miriam.pdf

### Harari & La Ferrara 2018

- MIT / Review of Economics and Statistics article: https://doi.org/10.1162/rest_a_00730

### Berman et al. 2017

- AER article: https://doi.org/10.1257/aer.20150774
- openICPSR replication V1: https://doi.org/10.3886/E113068V1

### von Uexkull et al. 2016

- PNAS article: https://doi.org/10.1073/pnas.1607542113
- Uppsala replication-data index: https://www.uu.se/en/department/peace-and-conflict-research/research/research-data/replication-data

### Gehring, Kaplan & Wong 2022

- Journal of Development Economics article: https://doi.org/10.1016/j.jdeveco.2022.102902

### Briggs 2018

- World Development article: https://doi.org/10.1016/j.worlddev.2017.10.020

---

## 10. Decision record

**Selected now:** Briggs (2017); Breckner & Sunde (2019).  
**Keep warm for later:** Blair et al. (2022); Kotsadam et al. (2018); Harari & La Ferrara (2018); von Uexkull et al. (2016).  
**Do not prioritize as first commissioning standards:** Berman et al. (raw mine-source accessibility), Knutsen et al. (custom mine source + Afrobarometer), Gehring et al. (multi-source complexity / weaker positive-control character), Briggs (2018) (useful convergent check but weaker exact replication anchor).

The two selected benchmarks are deliberately not the two most elaborate or famous studies. They were chosen because disagreement should be cheap to localize: one stresses **DHS semantics/weights/denominators**, the other **ACLED event/time/geography/external exposure**. That is the relevant criterion for a calibration lab.
