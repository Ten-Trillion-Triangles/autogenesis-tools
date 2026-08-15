# Thread-safe autoExport closure — 2026-08-08 worked reference

The 2026-08-08 session closed the cross-container parity gap for `TraceConfig.autoExport` + `exportPath`. The fix introduced a concurrency surface (writing to disk from a synchronous `getTraceReport()` that multiple containers can call), so it required the thread-safe `TraceAutoExporter` design and the test-seam taxonomy that the closure surfaced.

## Scope-narrowing workflow rule

The session's progression — captured here because every future audit session will hit the same shape:

1. **Broad ask** (initial): "Identify dead vars and params in TPipe" — would cover all `private var` declarations across `src/main/kotlin`.
2. **First narrowing** (operator mid-session): "Not dead code in TPipe just unused vars and params in the tracing system itself ones that when set do not do anything" — focused on the trace system only.
3. **Second narrowing** (operator): "Let's update max history to support other types beyond pipeline. Apply tdd patterns test and verify correct." — specific fix with TDD discipline.
4. **Third narrowing** (operator): "Now let's address auto export in the same way. Of note we need to handle thread safety with it being able to do this and do so without deadlocking." — specific fix with concurrency constraint.

The rule: **each narrowing produces a fresh scope with fresh audit + fresh fix.** The previous report becomes a precursor, not a deliverable. Drop findings from earlier scopes that don't intersect the narrowed surface. The "Closing a cross-container parity gap with TDD" section in SKILL.md handles the generic close-out; this reference handles the concurrency-specific extension.

## Thread-safe `TraceAutoExporter` design

Production code in `src/main/kotlin/Debug/TraceAutoExporter.kt`:

```kotlin
class TraceAutoExporter private constructor(
    private val pathLocks: ConcurrentHashMap<String, ReentrantLock> = ConcurrentHashMap()
) {
    fun export(targetPath: String, report: String, writeAction: () -> Unit) {
        val lock = pathLocks.computeIfAbsent(targetPath) { ReentrantLock() }
        lock.withLock { writeAction() }
    }

    fun export(targetPath: String, report: String) {
        export(targetPath, report) { writeStringToFile(targetPath, report) }
    }

    internal fun getPathLocksForTest(): Map<String, ReentrantLock> = pathLocks.toMap()
    internal fun flushForTest() { /* no-op for sync impl; forward-compat for async */ }

    companion object {
        val default: TraceAutoExporter = TraceAutoExporter()
        fun create(): TraceAutoExporter = TraceAutoExporter()
    }
}
```

Hard-deadlock-free by construction:

1. **Per-path granularity** — concurrent writes to the same path serialize; concurrent writes to different paths run in parallel. A global lock would serialize everything.
2. **`computeIfAbsent` is atomic** — exactly-one lock creation per path. Two threads racing to insert the same lock cannot deadlock.
3. **No nested locks** — the exporter does not acquire any other lock while holding the per-path lock. The user's write closure does not call back into the exporter.
4. **Lock held only for the write closure** — the report-building (inside `getTraceReport()` BEFORE the call to `export(...)`) is outside the lock. Only the actual file I/O is serialized.

## Test-seam taxonomy (3 flavors)

Three flavors of test seam emerged from the 2026-08-08 closures. Each fits a different "what is the test asserting?" question:

| Seam flavor | Production signature | Test asserts | Example |
|---|---|---|---|
| **Reader seam** | `internal fun getXxxForTest(): T` next to the existing setter, with KDoc explaining production code does not consume it and `internal` visibility keeps it out of the public API surface | "Field X was set" — e.g. `assertEquals(N, PipeTracer.getMaxHistoryForTest())` | `PipeTracer.getMaxHistoryForTest()` |
| **ID seam** | `internal fun setRunIdForTest(id: String)` on the container that owns a `private val id` field — the seam REPLACES the auto-generated id with a deterministic one | "Container used the right id" — tests pre-populate `PipeTracer.startTrace(id)` and then call the container's method to confirm the lookup keyed on that id | `PumpStation.setRunIdForTest("unit-test-run")` |
| **Producer seam** | Add the missing public method (e.g. `getTraceReport()`, `getTraceId()`) that the container should have had all along — the seam IS the production API | "Container produced an output" — tests assert the output (e.g. file written, trace event emitted) without reconstructing internal state | `DistributionGrid.getTraceReport()`, `MultiConnector.getTraceReport()`, `Connector.getTraceReport()` |

## The 4 thread-safety tests (canonical pin set)

All 4 in `src/test/kotlin/Debug/TraceAutoExporterTest.kt`:

```kotlin
@Test fun concurrentWritesToSamePathExecuteSerially() {
    // 8 threads, all targeting the same path, each holds the lock for 50ms
    // Assertion: max concurrent observers == 1 (lock serializes same-path writes)
}

@Test fun concurrentWritesToDifferentPathsDoNotBlockEachOther() {
    // 4 threads, each targeting a distinct path, each holds the lock for 100ms
    // Assertion: max concurrent observers >= 2 (different paths run in parallel)
}

@Test fun writesDoNotCorruptFileUnderContention() {
    // 10 threads × 100 iterations on the same path, each writes a self-delimited record
    // Assertion: all 1000 records present, no interleaved bytes
}

@Test fun exportReturnsResultWithoutBlockingIndefinitely() {
    // Single small write
    // Assertion: returns in under 1 second
}
```

Each test targets a specific invariant. Test #3 is the load-bearing one: any concurrency design that fails to serialize will fail this test with interleaved bytes visible in the file.

## The 8 container-propagation tests

One per container, asserting `enableTracing(TraceConfig(autoExport = true))` produces a file. The pre-fix state: only Pipeline + PumpStation pass. Post-fix: all 8 pass.

```kotlin
@Test fun pipeline_getTraceReportWithAutoExport_writesFile()           // pre-fix pass
@Test fun pumpStation_getTraceReportWithAutoExport_writesFile()       // pre-fix pass
@Test fun manifold_getTraceReportWithAutoExport_writesFile()           // pre-fix fail
@Test fun splitter_getTraceReportWithAutoExport_writesFile()          // pre-fix fail
@Test fun junction_getTraceReportWithAutoExport_writesFile()          // pre-fix fail
@Test fun distributionGrid_getTraceReportWithAutoExport_writesFile()   // pre-fix fail
@Test fun connector_getTraceReportWithAutoExport_writesFile()         // pre-fix fail (missing getTraceReport)
@Test fun multiConnector_getTraceReportWithAutoExport_writesFile()     // pre-fix fail (missing both)
```

## The malformed-filename regression test

The pre-fix `Pipeline.kt:873` had `"trace-${pipelineId.take(8)}-$extension.${extension}"` — literal `$extension` in the middle of the name. The regression test pins the canonical shape:

```kotlin
@Test fun autoExportFilenameDoesNotContainLiteralExtensionToken() {
    // ... call pipeline.getTraceReport(TraceFormat.HTML) ...
    val malformed = files.filter { f ->
        val name = f.name
        name.count { it == '.' } >= 2 && name.substringBeforeLast('.').contains('.')
    }
    assertEquals(emptyList<Any>(), malformed,
        "Filename must be 'trace-<id>.<ext>' (one dot), not 'trace-<id>-<ext>.<ext>'")
}
```

Apply this fix to every container's autoExport block. The fix is the same shape — drop the literal `$extension` token from the middle of the filename template:

```kotlin
// Before
val filename = "trace-${id.take(8)}-$extension.${extension}"
// After
val filename = "trace-${id.take(8)}.$extension"
```

## The 6 surgical wire patches

Each missing container got a one-line addition to its `enableTracing(...)` plus a one-line addition to its `getTraceReport(...)`. The patches were identical in shape with container-specific id-taker length and filename prefix. Per-container diff:

```kotlin
// In enableTracing(...) — Pipeline.kt:851 already had it; the 6 missing containers needed:
fun enableTracing(config: TraceConfig = TraceConfig(enabled = true)): XxxContainer
{
    this.tracingEnabled = true
    this.traceConfig = config
    PipeTracer.enable()
    PipeTracer.setMaxHistory(config.maxHistory)  // ADD for maxHistory
    return this
}

// In getTraceReport(...) — Pipeline + PumpStation already had autoExport; the 6 missing containers needed:
fun getTraceReport(format: TraceFormat = traceConfig.outputFormat): String
{
    val report = PipeTracer.exportTrace(id, format)

    if(traceConfig.autoExport)
    {
        val extension = when(format) {
            TraceFormat.HTML -> "html"
            TraceFormat.JSON -> "json"
            TraceFormat.MARKDOWN -> "md"
            TraceFormat.CONSOLE -> "txt"
        }
        val filename = "trace-${id.take(8)}.$extension"
        val exportPath = traceConfig.exportPath.trimEnd('/') + "/" + filename
        TraceAutoExporter.default.export(exportPath, report) {
            com.TTT.Util.writeStringToFile(exportPath, report)
        }
    }

    return report
}
```

## Doc-claim contradiction pattern

The pre-fix `docs/core-concepts/tracing-and-debugging.md:90` literally stated:

> "The `enabled`, `maxHistory`, `autoExport`, and `exportPath` properties exist in TraceConfig but are not used by the actual tracing system."

This is the canonical example of a **doc claim that contradicts the implementation surface**. The doc was written when the cross-container parity gap was already known (a workaround-during-implementation note). After the autoExport closure, the doc had to be patched to:

> "`enabled`, `detailLevel`, `includeContext`, `includeMetadata`, and `maxHistory` are honored when their owning container's `enableTracing(config)` is called: ... `autoExport` and `exportPath` are honored by every container — Pipeline, PumpStation, Manifold, Splitter, Junction, DistributionGrid, Connector, and MultiConnector — and routed through the thread-safe `TraceAutoExporter` so concurrent writes to the same path serialize without corrupting the file."

The pattern: **a doc that contradicts working code is a bug class of its own**. It belongs in the parity audit's reach surface, not just the implementation surface. The verification recipe (find every "not used / silently dropped / dead" doc claim and patch it) is in the SKILL.md pitfalls section.

## Verification matrix

13 tests total: 4 thread-safety + 8 container-propagation + 1 filename-shape regression. All 13 pass after the GREEN phase. JUnit XML is the authoritative signal:

```
TraceAutoExporterTest: tests=13 failures=0 errors=0
ContainerMaxHistoryPropagationTest: tests=9 failures=0 errors=0
```

The full repo test suite stayed green: 134 tests across the Debug/* tree, 0 failures, 0 errors. Targeted Pipeline/* trace tests (PumpStationTraceVisualizationTest, PumpStationTPipeConfigTraceLiveTest, EventObserverTest, PumpStationSetGetTest, PumpStationDefaultsTest, PumpStationDispatchDefaultsTest, PumpStationMiniMaxLiveTest, PumpStationTurnSummaryDemarcationTest, PumpStationPathCaseInsensitiveTest, PumpStationEventMetadataTest, PumpStationEventTypeTest, PumpStationSnapshotTest, PumpStationWarningTest, PumpStationFlagTriggeredVisualizationTest, PumpStationPauseResumeTest, PumpStationDslParityTest) all passed.

## Lessons for future sessions

1. **The narrow-after-broad pattern is normal.** Don't try to deliver the broad audit when the operator narrows — re-scope and deliver the narrowed ask.
2. **Concurrency surfaces need their own TDD pattern.** A RED-GREEN cycle for "container N wrote a file" is straightforward; for "container N wrote a file under thread contention without corruption" requires 4 separate invariant tests.
3. **Test seams are not free.** Each flavor (reader / ID / producer) implies a different relationship between the test and the production code. Pick the wrong one and the test passes while the bug stays live.
4. **Docs that contradict the implementation are part of the fix.** A successful RED-GREEN that leaves the docs stale will not be visible to operators reading them — they'll skip the feature they think is broken.
