# Published-study calibration implementation handoff

**Status:** implementation-readiness handoff, 2026-08-23  
**Purpose:** `calibration`  
**Scope:** convert the two published-study recommendations in `africa_benchmark_candidates.md` into executable work without creating parallel infrastructure or bypassing current source contracts.

## Decision

Do **not** implement Briggs (2017) or Breckner & Sunde (2019) immediately from this branch.

The correct near-term sequence is:

1. close the generic calibration auxiliary-input gap tracked in harness issue #16;
2. execute the cheaper official-DHS-report commissioning benchmark already designed in PR #12;
3. use that same validated survey-input seam for Briggs (2017), the first **published-study** DHS benchmark;
4. defer Breckner & Sunde until regular-grid geography and subannual time are explicit shared capabilities rather than one-off adapter inventions.

This sequence reduces diagnostic ambiguity. If the official DHS electricity statistic cannot be reproduced, a Briggs failure would be uninterpretable. If the survey measurement system first reproduces an authoritative DHS table, Briggs then becomes a meaningful cross-source positive control rather than a combined ingestion/debugging exercise.

## Coordination with the merged Calibration Lab kernel

Calibration Lab PR #13 is merged on the `main` commit from which this research branch was created. Its native public model is `CalibrationBenchmarkSpec`, with explicit `purpose = "calibration"`, adapter IDs, and independent Level 1/2/3 recovery states.

The scout memo originally said no stable merged spec API was visible. That observation is superseded by the merged kernel and this handoff.

No JSON benchmark specs are committed here yet because the remaining blocker is **not** spec syntax. The current input seam can validate semantic `EmpiricalMeasurementBundle`s but cannot yet represent provenance-validated source-native auxiliary datasets such as HR Silver without fabricating a `MeasurementContract`. PR #12 independently found the same consumer gap. Harness issue #16 is therefore the shared prerequisite.

## Shared prerequisite — issue #16

The desired capability is source-agnostic:

- keep normal semantic measurement inputs unchanged;
- allow an auxiliary empirical dataset validated by content hash plus `DatasetRef` resolved from its upstream `RunManifest`;
- do not require auxiliary source-native facts to masquerade as semantic measurements;
- allow explicit selection of one measurement contract from a persisted contract collection;
- keep source-specific joins, weights, denominators, and transformations inside adapters.

The first consumer is Nigeria DHS 2018 household electricity from PR #12 (`HV206` measurement + HR Silver `HV005`, joined on `source_row_id`). Briggs later uses the same seam.

---

## Benchmark 1 handoff — Briggs (2017)

### Intended role

`purpose = calibration`

Published-study positive control for:

- survey identity;
- `HV270` wealth-quintile semantics;
- source-native household weights and de jure membership;
- denominator construction;
- survey-region identity/geography;
- historical geocoded donor-project aggregation;
- country fixed-effects estimation and clustered uncertainty.

This does **not** create a new FCV claim about aid targeting.

### Why it comes after PR #12

The official DHS commissioning benchmark isolates the survey side of the machine with a near-exact published table cell. Briggs combines that survey machinery with donor-project geography and a regression. Running Briggs first would make a disagreement expensive to localize.

### Required empirical inputs

The final adapter should consume explicit, provenance-backed inputs rather than a prejoined replication table:

1. **DHS wealth measurement**
   - semantic measure: `dhs.household.wealth_quintile`;
   - source variable: `HV270`;
   - exact survey identities listed in the paper/supplement;
   - join identity back to source household row retained.

2. **DHS HR auxiliary facts**
   - `HV005` household sample weight;
   - `HV012` de jure household-member count;
   - release-verified survey-region field used by each survey;
   - stable `source_row_id` / survey identity;
   - any region labels/codes required to reproduce the paper's 195-region universe.

3. **Historical project-location inputs**
   - exact World Bank and African Development Bank geocoded release(s) used by Briggs;
   - project/subproject IDs, commitment values, dates, coordinates, source release identity;
   - no substitution of current APIs/releases without an explicit source-equivalence decision.

4. **Region geography / mapping evidence**
   - exact survey-region boundaries or an auditable mapping to the paper's regional units;
   - mapping provenance for project locations to survey regions;
   - explicit treatment of projects/locations that cannot be mapped uniquely.

5. **Published replication package**
   - original scripts/data where legally redistributable;
   - reference outputs for the selected baseline table/specification;
   - pinned checksum/version in local commissioning metadata.

### Adapter boundary

Provisional adapter identity once issue #16 is closed:

`briggs_2017_aid_targeting`

The adapter should own only downstream calibration choices:

1. validate that all DHS inputs resolve to the declared surveys;
2. join semantic wealth rows to source-native design facts by stable household identity;
3. construct weighted de jure population mass as `HV005 * HV012`;
4. aggregate population mass by survey region × wealth quintile;
5. derive each region's national-quintile population shares;
6. aggregate the historical donor-project release to the same region definition under an explicit spatial-membership policy;
7. reconstruct the declared baseline regression;
8. return aggregate diagnostics, observed coefficients/signs, and discrepancies only.

The adapter must **not** alter upstream DHS meanings, silently harmonize region identifiers, or infer a later donor release as equivalent.

### Recovery expectation

**Level 1 — required.**

Pipeline/data/design reconstruction succeeds with the intended survey universe, region count, weighted population totals, project support, and regression sample.

Important diagnostics should include at least:

- surveys expected / loaded;
- households and weighted de jure population by survey;
- regions expected / reconstructed;
- unmapped or ambiguous region/project rows;
- project counts/value before and after regional mapping;
- final regression `N` and country count.

**Level 2 — required first acceptance level.**

Recover the published qualitative pattern:

- richest-quintile regional population share has a positive aid relationship;
- poorest-quintile share does not show the corresponding stable pro-poor result;
- the result is not driven by an obvious survey/region construction failure.

**Level 3 — conditional, not universal.**

Quantitative coefficient compatibility is appropriate only after the exact historical DHS surveys, project releases, region construction, and baseline specification are pinned. Exact floating-point equality is not required; a tolerance must be justified from the replication environment and transformation parity.

### Earliest implementation gate

Do not open the Briggs adapter implementation until:

- issue #16 is resolved;
- at least one official DHS report commissioning benchmark from PR #12 passes Level 3 on real local data;
- exact Briggs replication/project-release assets have been recovered locally and checksummed;
- survey-region geography is no longer an implicit notebook artifact.

---

## Benchmark 2 handoff — Breckner & Sunde (2019)

### Intended role

`purpose = calibration`

Published-study positive control for:

- ACLED event identity and retention;
- conflict-incidence construction;
- verified structural-zero / coverage treatment;
- spatial binning of geocoded events;
- external weather exposure alignment;
- monthly panel construction;
- fixed-effects estimation.

This does **not** create a new FCV climate-conflict result.

### Current capability mismatch

This benchmark should not be forced into the present abstractions.

Two shared contracts are currently too narrow for the paper's native design:

1. **Time.** `empirical-data-contracts.PeriodScheme` is explicitly year-based (`width_years`, `anchor_year`, Gregorian year calendar). The paper's natural grain is monthly. Encoding months as fake annual periods would destroy temporal semantics.
2. **Geography.** `spatial-data-foundation` currently provides concrete GADM materialization and auditable point-to-polygon membership. The paper uses a regular 0.75-degree latitude/longitude grid. Encoding cells as fake GADM units would destroy geography authority.

These are generic capability questions, but they should be solved only when this benchmark is actually next in the pull queue. Do not create one-off Breckner-specific grid/time types inside the calibration adapter.

### Required empirical inputs

1. **Historical ACLED snapshot**
   - exact or demonstrably equivalent event release covering the paper's 1997–2015 window;
   - source IDs, dates, coordinates, event semantics, and coverage evidence;
   - explicit decision on whether a modern ACLED export is equivalent enough for Level 2 only or for Level 3.

2. **Weather source**
   - ERA-Interim fields/release used by the paper;
   - exact variable definitions, temporal aggregation, units, and extreme-temperature construction;
   - source snapshot checksums and documentation.

3. **Regular grid**
   - authoritative construction of the 0.75-degree African analysis cells;
   - stable cell IDs and geometry;
   - point-to-cell membership policy;
   - land/sample mask matching the paper.

4. **Monthly period semantics**
   - a shared contract capable of representing calendar months exactly;
   - no reinterpretation through the existing year-width `PeriodScheme`.

5. **Replication package**
   - Harvard Dataverse package and reference outputs;
   - pinned version/checksum;
   - baseline sample and coefficient diagnostics.

### Adapter boundary

Provisional future adapter identity:

`breckner_sunde_2019_temperature_conflict`

Once shared grid/month support exists, the adapter should:

1. resolve ACLED events to the declared historical snapshot;
2. assign events to regular-grid cells with auditable membership;
3. construct monthly conflict incidence under explicit coverage/zero semantics;
4. align weather measurements to cell-month;
5. recreate the declared extreme-temperature indicator and baseline sample;
6. run the published baseline fixed-effects design;
7. emit aggregate diagnostics and recovery states.

### Recovery expectation

**Level 1 — required.**

Recover the paper's cell universe, monthly window, event support, weather support, and estimation sample within documented tolerances.

**Level 2 — required first acceptance level.**

Recover the positive relationship between temperature extremes and conflict incidence, including the documented stronger pattern for longer-duration extremes where the selected reference specification supports that comparison.

**Level 3 — conditional.**

Expect quantitative compatibility against the pinned replication package. Do **not** demand the same coefficient from a later ACLED release unless source-equivalence analysis justifies it.

### Earliest implementation gate

Do not implement this adapter until:

- the Briggs/DHS lane is no longer blocked on the generic auxiliary-input seam;
- a decision is made on shared monthly-period semantics;
- a decision is made on reusable regular-grid geography authority;
- exact replication and weather assets are recovered locally.

This prevents a single benchmark from pulling generic time/geography design into the harness prematurely.

---

## Pull order

The recommended near-term queue is therefore deliberately short:

```text
issue #16: generic calibration auxiliary dataset input
        ↓
PR #12: official DHS report commissioning
        ↓
Briggs 2017: first published-study survey/cross-source benchmark
        ↓
reassess bottleneck
        ↓
Breckner–Sunde only if grid/monthly support is now justified
```

The important distinction is that **PR #12 commissions the survey instrument**, while **Briggs tests whether that commissioned instrument participates correctly in a published cross-source empirical design**.

## Definition of ready for a published-study implementation PR

A benchmark is ready to leave research/design status only when:

- [ ] its required source releases are identified and locally obtainable;
- [ ] every input can be represented truthfully through existing empirical contracts;
- [ ] protected/restricted data remains external to Git;
- [ ] the adapter boundary is source-specific but the calibration kernel remains source-agnostic;
- [ ] Level 1 diagnostics can localize a failure before any coefficient is interpreted;
- [ ] Level 2 expected behavior is explicit;
- [ ] Level 3 is either justified with a pinned reference/tolerance or explicitly not required;
- [ ] the run is labeled `purpose = calibration` and cannot be presented as new FCV substantive inference.
