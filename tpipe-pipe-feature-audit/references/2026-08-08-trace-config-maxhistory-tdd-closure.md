# Closing the TraceConfig.maxHistory cross-container parity gap with TDD (2026-08-08)

## What this captures

The companion session-applied reference to the cross-container parity audit at `references/2026-08-08-trace-config-cross-container-parity.md`. That file captures the AUDIT findings — the 2-of-6 scorecard for `TraceConfig.maxHistory`, the 2-of-6 scorecard for `TraceConfig.autoExport` / `exportPath`, and the surrounding dead-code kill list. This reference captures the FIX-SIDE recipe: how the `maxHistory` gap was closed end-to-end with TDD discipline, surgical 15-line diff, JUnit XML verification, and a docs patch to remove the now-incorrect "not used" claim.

The general recipe lives in `tpipe-pipe-feature-audit` § "Closing a cross-container parity gap with TDD" — this file is the canonical worked example for that recipe.

## The audit surface that this fix addresses

From the 2026-08-08 audit, `TraceConfig.maxHistory` (`Debug/TraceConfig.kt:16`) was:
- Honored by 2 of 8 containers that have an `enableTracing(TraceConfig)` overload: `Pipeline.kt:851` and `PumpStation.kt:2802`.
- Silently dropped by 6: `Manifold`, `Splitter`, `Junction`, `DistributionGrid`, `Connector`, `MultiConnector`.

User wiring `manifold { tracing { maxHistory(5000) } }` got nothing — the value lived in the DSL builder, was passed into `traceConfig`, but no container read it. The TrimBehavior was silently the global default (1000) on those 6 containers.

The operator also called out the docs at `docs/core-concepts/tracing-and-debugging.md:90` (the old "Note: The `enabled`, `maxHistory`, `autoExport`, and `exportPath` properties exist in TraceConfig but are **not used** by the actual tracing system.") — which confirmed the gap was a known limitation, not a hidden defect. The fix surface for any parity gap closure always includes the docs that documented the gap.

## The TDD closure (six steps, fully traced)

### Step 1 — Write the failing test for every container

Test file: `src/test/kotlin/Debug/ContainerMaxHistoryPropagationTest.kt` (9 tests).

```kotlin
@Test fun pipeline_enableTracing_propagatesMaxHistory() {
    val p = Pipeline().enableTracing(TraceConfig(maxHistory = 42))
    assertEquals(42, PipeTracer.getMaxHistoryForTest())
}
@Test fun pumpStation_enableTracing_propagatesMaxHistory() {
    val ps = PumpStation().enableTracing(TraceConfig(maxHistory = 17))
    assertEquals(17, PipeTracer.getMaxHistoryForTest())
}
@Test fun manifold_enableTracing_propagatesMaxHistory() {
    val m = Manifold().enableTracing(TraceConfig(maxHistory = 23))
    assertEquals(23, PipeTracer.getMaxHistoryForTest())
}
// ... 5 more container tests + 1 behavioral trim test ...
```

Pattern: one test per container, asserting the propagation landed in `PipeTracer.maxTraceHistory`. Plus one behavioral trim test that adds N+5 events and asserts the oldest are dropped — pins the user-visible contract, not just the field-read.

### Step 2 — Test seam on the production class

`PipeTracer.maxTraceHistory` is `private`. Add an `internal` accessor next to the existing setter:

```kotlin
/**
 * Test seam: returns the current max history limit. Production code does not consume
 * this — it lets tests assert that [TraceConfig.maxHistory] propagated from a container's
 * enableTracing call into PipeTracer.setMaxHistory. Same-module visibility keeps the
 * seam out of the public API surface while still being reachable from src/test/kotlin.
 */
internal fun getMaxHistoryForTest(): Int = maxTraceHistory
```

The `internal` visibility is the right choice: same-module reachability for tests, no public API surface, no risk of consumers depending on it. Already-documented precedent: `BedrockMultimodalPipe.bedrockClient` was made `internal` (not `protected`) for the same reason on a Task 7 wire.

### Step 3 — Confirm RED

Initial test run (after Step 2 only):

```
> Task :test

ContainerMaxHistoryPropagationTest > splitter_enableTracing_propagatesMaxHistory() FAILED
ContainerMaxHistoryPropagationTest > distributionGrid_enableTracing_propagatesMaxHistory() FAILED
ContainerMaxHistoryPropagationTest > manifold_enableTracing_propagatesMaxHistory() FAILED
ContainerMaxHistoryPropagationTest > multiConnector_enableTracing_propagatesMaxHistory() FAILED
ContainerMaxHistoryPropagationTest > connector_enableTracing_propagatesMaxHistory() FAILED
ContainerMaxHistoryPropagationTest > junction_enableTracing_propagatesMaxHistory() FAILED

9 tests completed, 6 failed
```

The 6 failures match the audit's 2-of-6 scorecard exactly. Pipeline + PumpStation + the trim test passed (they were already wired, and the trim test verifies a behavior the global default value already happens to satisfy at the 1000-event size we tested).

This is the textbook RED state: failures match the bug class exactly. If 5 tests failed and 4 passed, the test is wrong — the failure pattern is the diagnostic signal.

### Step 4 — Wire each missing container

Six surgical patches, one per container, each adding `PipeTracer.setMaxHistory(config.maxHistory)` to the `enableTracing(TraceConfig)` body. Patches were done individually with surrounding context (`markShellDirty()` for DistributionGrid, `startTrace(pipelineId)` for Connector, `startTrace(multiConnectorId)` for MultiConnector, plain `PipeTracer.enable()` for Manifold/Splitter/Junction) — NO `replace_all=true` because the surrounding code differs at each site.

Diff stat:

```
docs/core-concepts/tracing-and-debugging.md  | 2 +-
src/main/kotlin/Debug/PipeTracer.kt          | 8 ++++++++
src/main/kotlin/Pipeline/Connector.kt        | 1 +
src/main/kotlin/Pipeline/DistributionGrid.kt | 1 +
src/main/kotlin/Pipeline/Junction.kt         | 1 +
src/main/kotlin/Pipeline/Manifold.kt         | 1 +
src/main/kotlin/Pipeline/MultiConnector.kt   | 1 +
src/main/kotlin/Pipeline/Splitter.kt         | 1 +
8 files changed, 15 insertions(+), 1 deletion(-)
```

15 lines added, 1 removed — the absolute minimum to close a 6-container gap.

### Step 5 — Confirm GREEN with JUnit XML verification

Re-run the test:

```
BUILD SUCCESSFUL in 21s
```

Then verify with the authoritative JUnit XML (the `build/test-results/test/*.xml` files are the source of truth; gradle stdout can drop `PASSED` markers under heavy stdout):

```
testsuite name="com.TTT.Debug.ContainerMaxHistoryPropagationTest"
  tests="9" skipped="0" failures="0" errors="0"
  testcase name="splitter_enableTracing_propagatesMaxHistory()" ...
  testcase name="distributionGrid_enableTracing_propagatesMaxHistory()" ...
  testcase name="pipeline_enableTracing_propagatesMaxHistory()" ...
  testcase name="traceEventsBeyondMaxHistoryAreTruncated()" ...
  testcase name="manifold_enableTracing_propagatesMaxHistory()" ...
  testcase name="pumpStation_enableTracing_propagatesMaxHistory()" ...
  testcase name="multiConnector_enableTracing_propagatesMaxHistory()" ...
  testcase name="connector_enableTracing_propagatesMaxHistory()" ...
  testcase name="junction_enableTracing_propagatesMaxHistory()" ...
```

9 tests, 0 failures, 0 errors. GREEN.

### Step 6 — Regression check on the broader suite

Ran `com.TTT.Debug.*` (the package containing the test seam) — 121 tests, 0 failures, 0 errors across 29 reports. Ran targeted subsets of `com.TTT.Pipeline.*` that exercise the 6 modified containers (`PumpStationTraceVisualizationTest`, `PumpStationSetGetTest`, `EventObserverTest`, etc.) — all green.

Killed the full `com.TTT.Pipeline.*` run after ~10 minutes because the suite is too heavy for the "verify GREEN" loop. JUnit XML is the authoritative signal; tail stdout is decoration. Pattern: focused subsets for verification, full suite for pre-commit gating (operator's call when).

## The docs patch

`docs/core-concepts/tracing-and-debugging.md:90` originally said:

> **Note**: The `enabled`, `maxHistory`, `autoExport`, and `exportPath` properties exist in TraceConfig but are **not used** by the actual tracing system.

After the fix, that line was wrong on 3 of the 4 named fields (only `autoExport` and `exportPath` remain partially dead — honored by 2 of 6 containers, not 0). Replaced with:

> **Note**: `enabled`, `detailLevel`, `includeContext`, `includeMetadata`, and `maxHistory` are honored when their owning container's `enableTracing(config)` is called: `enabled` flips the global tracer, `maxHistory` propagates to `PipeTracer.setMaxHistory`, `detailLevel` filters via `EventPriorityMapper.shouldTrace`, and `includeContext`/`includeMetadata` gate the per-event payload. `autoExport` and `exportPath` are honored by Pipeline and PumpStation only — Manifold, Splitter, Junction, DistributionGrid, Connector, and MultiConnector ignore them.

The replacement lists the actual contract: which fields are honored, by which containers, where the remaining gap is. A future auditor reading the docs can verify the doc matches the implementation.

## What this session did NOT close

`autoExport` and `exportPath` parity (2 of 6 containers honored) is the SAME class of bug as `maxHistory` was. The same TDD recipe would close it: write 4 failing tests for Manifold/Splitter/Junction/DistributionGrid that assert `getTraceReport()` writes a file when `autoExport=true`, add a `internal fun getTraceExportPathForTest(): String?` seam if needed, wire the same `if(traceConfig.autoExport) { writeStringToFile(...) }` block across the 4 missing containers. The fix lives in this skill's recipe; it was deferred because the operator asked for the `maxHistory` close-out specifically.

If a future session tackles `autoExport`, this recipe is the pattern. The autoExport filename bug at `Pipeline.kt:873` (`"trace-${pipelineId.take(8)}-$extension.${extension}"` produces names with the literal extension token embedded) should also be fixed at the same time.

## Cross-references

- `tpipe-pipe-feature-audit` § "Closing a cross-container parity gap with TDD (the FIX-side recipe)" — the general pattern this reference worked.
- `tpipe-pipe-feature-audit` § "Cross-container feature parity audit (the SECOND COMPARE side)" — the audit-side framework.
- `references/2026-08-08-trace-config-cross-container-parity.md` — the audit findings that this fix addresses (maxHistory 2-of-6 scorecard + the kill list).
- `references/2026-08-02-provider-feature-parity-breakdown.md` — the provider-modules equivalent (the parallel fix-side recipe lives in the JUnit-XML verification recipe at the bottom of that reference).
- `test-driven-development` skill — the general RED-GREEN-REFACTOR discipline this closure follows.
- `test-driven-development` § "TDD Against Process-Singleton State" — relevant for the `PipeTracer` test-seam pattern (process-singleton state, accessor with domain predicate).
