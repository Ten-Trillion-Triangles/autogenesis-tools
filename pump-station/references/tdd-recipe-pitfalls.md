# TDD Recipe Pitfalls — Worked Examples for Pitfalls #N+2 and #N+3

Companion to `references/tdd-recipe-pitfalls.md` in the pump-station skill. Captures the two pitfalls a future agent will hit on the FIRST harness test they write, with the exact code patterns that work and the exact code patterns that fail silently.

Source session: 2026-07-08 third-pass bug-fix session on branch `pumpstation-bugfixes-2026-07-08` (worktree `/home/cage/Desktop/Workspaces/pumpstation-bugfixes`). 5 new RED→GREEN tests committed: `PumpStationCompletedMetaTest` (B1), `PumpStationLoopGuardResetTest` (B2), `PumpStationRationaleNudgeDedupTest` (B3), `PumpStationPathTimeoutTest` (B4), `PumpStationTokenMetaTest` (B7).

---

## Pitfall #N+2 — Observer-fires-twice dedup

### Symptom

A test that asserts on event counts via `setEventObserver` reports 2× the actual count. The B2 test (loop-guard counter) hit this: first RED run reported `[3, 3, 3, 3, 3, 3, 3, 3]` (8 trips) instead of `[3, 3, 3, 3]` (4 trips). A `println(turnIndex, detail)` debug dump showed each `LoopGuardTripped` event firing twice with identical `(turnIndex, timestamp)` — once at `emitEvent` time, once at `runFinalizationPhase` drain.

### Why

`emitEventInternal` delivers to `eventObserver` synchronously at emit. `runFinalizationPhase` re-delivers from the background event queue at the end. Documented as oracle pitfall #1 in `/home/cage/.hermes/plans/pumpstation-correct-behavior.md:728`: "every `PumpStationEvent` is delivered to the synchronous observer once at `emitEvent` and once at the finalization drain. Tests must dedupe by `(turnIndex, timestamp)`."

### Right pattern

```kotlin
val trips = mutableListOf<Pair<Int, Int>>()  // (turnIndex, consecutive)
val seen = mutableSetOf<Pair<Int, Long>>()
val station = buildTestStation(maxHarnessTurns = 6)
station.setMaxConsecutiveSamePath(3)
// ... wire judge, dispatch, path ...
station.setEventObserver { event ->
    if (event is LoopGuardTripped && event.guard == "maxConsecutiveSamePath") {
        val consecutiveStr = event.detail.substringAfter("consecutive=")
            .substringBefore(",")
        val key = event.turnIndex to event.timestamp
        if (seen.add(key)) {
            trips.add(event.turnIndex to consecutiveStr.toInt())
        }
    }
}
runBlocking { station.executeLocal(MultimodalContent(text = "...")) }
```

### Why `(turnIndex, timestamp)` not just `turnIndex`

Multiple events can fire at the same `turnIndex` in the same millisecond (especially in fast loop runs where the harness emits Dispatch → Path → Judge in tight succession). `timestamp` disambiguates within a turn. `seen.add(key)` returns `false` on duplicate (same pair), so the captured list ends up with exactly one entry per actual event.

### Companion rule for `PipeTracer.getTrace(...)`

The funnel (`PumpStationHelpers::tracePumpStationEvent`) also flows through `emitEventInternal`, so the events captured by `PipeTracer.getTrace(station.getTraceId())` are ALSO duplicated if your test queries the trace funnel twice (once at emit, once at drain). The dedup pattern is the same — `seen.add(turnIndex to timestamp)` over the `TraceEvent.eventType` + metadata.

---

## Pitfall #N+3 — Pre-set `taskState.runId` does not survive `P2PInit`

### Symptom

The first RED run of B1 reported "no events captured" — the test set `taskState.runId = runId` before `executeLocal`, then called `PipeTracer.getTrace(runId)` after, and got back an empty list. The harness had emitted `PUMP_STATION_COMPLETED` but used a DIFFERENT runId.

### Why

`executeLocal` calls `P2PInit` first (PumpStation.kt:2068: `if (!harnessIsReady) P2PInit()`). `P2PInit` delegates to `P2PInitInternal` at line 1792, which calls `generateRunId()` at line 1959 (`"ps-${System.currentTimeMillis()}-${(0..9999).random()}"`) and OVERWRITES `taskState.runId` at line 1798. Any pre-set runId is silently lost. `PipeTracer.addEvent(traceId, event)` keys traces by the final `traceId`, so a pre-set lookup misses.

### Wrong (looks plausible, silently fails)

```kotlin
val station = buildTestStation(maxHarnessTurns = 1)
// ... wire judge, dispatch, path ...
station.taskState.runId = "test-B1-red"
station.enableTracing(TraceConfig(enabled = true, ...))
station.executeLocal(MultimodalContent(text = "..."))
val events = PipeTracer.getTrace("test-B1-red")  // ← EMPTY: harness overwrote runId
```

### Right

```kotlin
val station = buildTestStation(maxHarnessTurns = 1)
// ... wire judge, dispatch, path ...
station.enableTracing(TraceConfig(enabled = true, ...))
station.executeLocal(MultimodalContent(text = "..."))
val traceId = station.getTraceId() ?: error("station has no traceId after executeLocal")
val events = PipeTracer.getTrace(traceId)
```

### When you DO need a specific runId

For tests that need a deterministic runId (e.g. integration with an external trace server or a regression-pinning test), there is no public API to override `P2PInit`. Either:

1. Use `station.getTraceId()` and treat the auto-generated runId as the source of truth.
2. Construct a `PumpStation` with `harnessIsReady = true` BEFORE calling `executeLocal`. This is not currently exposed via a public setter — `harnessIsReady` is `private var` at PumpStation.kt:1790. A test-side workaround would need a `forceP2PInit(runId)` hook, which doesn't exist. Filed for future work.

For the 2026-07-08 fix session, option (1) was sufficient — every assertion read `station.getTraceId()` post-execute.

---

## Full worked example: B1 test pattern

`src/test/kotlin/Pipeline/PumpStationCompletedMetaTest.kt:51-83` — the canonical harness-funnel-assertion test:

```kotlin
@Test
fun harnessCompletedCarriesExitReasonAndFinalOutput()
{
    val station = buildTestStation(maxHarnessTurns = 5)
    val judgePipe = ScriptedTestPipe(
        name = "judge",
        response = """{"isComplete": true, "shouldTerminate": false, "reason": "task done"}"""
    )
    val judge = Pipeline().apply { add(judgePipe) }
    val dispatchPipe = ScriptedTestPipe(
        name = "dispatch",
        response = """{"pathName": "p1", "pathSchema": "{}"}"""
    )
    val dispatch = Pipeline().apply { add(dispatchPipe) }
    station.setJudgeAgent(judge)
    station.setDispatchAgent(dispatch)
    station.addPath(testPath("p1", returnText = "the final brief"))

    station.enableTracing(
        TraceConfig(
            enabled = true,
            autoExport = false,
            exportPath = "",
            outputFormat = TraceFormat.HTML,
            detailLevel = TraceDetailLevel.DEBUG
        )
    )

    runBlocking {
        station.executeLocal(MultimodalContent(text = "do the thing"))
    }

    val traceId = station.getTraceId()
        ?: error("B1 RED: station has no traceId after executeLocal")
    val events = PipeTracer.getTrace(traceId)
    val completed = events.firstOrNull {
        it.eventType == TraceEventType.PUMP_STATION_COMPLETED
    }
    assertNotNull(completed, "B1 RED: harness never emitted PUMP_STATION_COMPLETED")
    assertNotNull(
        completed.metadata["exitReason"],
        "B1 RED: PUMP_STATION_COMPLETED metadata missing 'exitReason'. " +
            "Actual meta keys: ${completed.metadata.keys}"
    )
    assertNotNull(
        completed.metadata["finalOutput"],
        "B1 RED: PUMP_STATION_COMPLETED metadata missing 'finalOutput'. " +
            "Actual meta keys: ${completed.metadata.keys}"
    )
}
```

The 3-step rhythm is: enableTracing → executeLocal → getTraceId/getTrace. Every harness-funnel-assertion test should follow this shape. Pre-set runId is a trap.

---

## Why these pitfalls aren't documented anywhere else

- **#N+2** (observer-fires-twice) IS documented in the oracle (pumpstation-correct-behavior.md:728) as a one-liner. It is NOT documented as a test fixture pattern — that's the gap. The 2026-07-08 session codified the dedup pattern with `(turnIndex, timestamp)`.
- **#N+3** (runId clobber) is NOT documented anywhere. The `P2PInit → generateRunId → overwrite taskState.runId` chain is at PumpStation.kt:1797-1798 and the docs in the data class fields don't call it out. Future harness tests that try to pre-set runId for deterministic regression pinners will hit this trap without warning.

Both pitfalls are unique to harness-level TDD — `PumpStationTestFixtures.kt` provides the standard recipes for buildTestStation/ScriptedTestPipe/testPath but doesn't document the observer and trace-funnel pitfalls. This reference is the missing piece.

---

## Pitfall #N+7 — Defects inside `invokePath` / `runPathFlow` / `invokeAgent` need `*Internal` direct-drive, not `executeLocal`

**Symptom:** A future defect lives inside `PumpStation.kt::invokePath` (or any equivalent `runX` helper used by `runPathFlow`). The standard recipe says "drive `executeLocal` end-to-end and assert on event streams," but every `@Test` blows up under direct kotlinc with `kotlinx.serialization.SerializationException: Serializer for class 'PathRequest' is not found` from `Pipe.applySystemPrompt` (Pitfall #N+6).

**Why the N+6 pivot doesn't help here:** `executeLocal` triggers `refreshPipelinesPrompts` → `Pipe.applySystemPrompt` → `examplePromptFor(PathRequest::class)` regardless of what you assert on. The wall is in the harness init chain, not in the patched helper. Pitfall #N+6's pivot (drive the helper directly) works ONLY when the helper is callable as a public/internal function (e.g. `buildPathInput` in Defect 10).

**Right pattern (Defect 11, 2026-07-10):** `invokePath` has an `internal suspend fun invokePathInternal(path, input): MultimodalContent` at `PumpStation.kt:2413` precisely because the runPathFlow extension in `PumpStationLoop.kt` calls it. Drive `invokePathInternal` directly. The test compiles with `-Xfriend-paths=build/classes/kotlin/main` and asserts on:
- The event stream via `setEventObserver` (dedup by `(turnIndex, timestamp)` per Pitfall #N+2).
- The `*Internal` accessors for any private state: `consecutivePathCountInternal`, `lastSelectedPathNameInternal`, `pathCallCounts` (all `internal`-getter at `PumpStation.kt:2310-2312, 1632`). Don't try to access `consecutivePathCount` directly (it's `private`).
- Side effects on `turnHistory` (via `ConverseData` additions).

```kotlin
@Test
fun safetyRejectedPathNeverTripsLoopGuard() = runBlocking {
    val station = buildTestStation(maxHarnessTurns = 6)
        .setMaxConsecutiveSamePath(2)
        .setPathSafetyFunction { _, _, _ -> false }   // canonical reject gate
    val path = PathObject().apply {
        pathName = "p1"; riskLevel = PathRiskLevel.Medium
        setExecutionFunction { content, _, _, _ ->
            MultimodalContent(text = "ok", context = content.context)
        }
    }
    station.addPath(path)

    val loopGuardTripped = mutableListOf<LoopGuardTripped>()
    val seen = mutableSetOf<Pair<String, Int>>()
    station.setEventObserver { event ->
        if (event is LoopGuardTripped) {
            val key = "guard" to event.timestamp.toInt()
            if (seen.add(key)) loopGuardTripped.add(event)
        }
    }

    val beforeConsecutive = station.consecutivePathCountInternal
    val beforeCallCounts = station.pathCallCounts.toMap()
    repeat(3) { station.invokePathInternal(path, MultimodalContent(text = "call #$it")) }

    assertTrue(loopGuardTripped.isEmpty(), "loop-guard must not trip on rejected paths")
    assertTrue(station.consecutivePathCountInternal == beforeConsecutive,
        "consecutivePathCount must not grow when safety always rejects")
    assertTrue(station.pathCallCounts.getOrDefault("p1", 0) == beforeCallCounts.getOrDefault("p1", 0),
        "pathCallCounts[p1] must not grow when safety always rejects")
}
```

**The general rule for future defects inside the harness's internal flow helpers:** always check whether the helper exposes an `internal` entry point (`invokePathInternal` / `runPathFlow` / `invokeAgent` / `applyXxxFunction` / etc.) before falling back to `executeLocal`. If yes, direct-drive with `invokeXxxInternal` and assert on the public observer stream + `*Internal` accessors. If no, the helper's patch must also expose one as part of the fix (mirrors the `buildPathInput` precedent in Defect 10).

**Why this is preferred over relying on `consecutivePathCount` reflection:** reflection on Kotlin `private` fields works but is fragile (name-mangled properties, breaks under `kotlinc` optimization), and the `*Internal` getter is a documented public API for tests. Future maintainers know to keep the contract; reflection traps disappear when fields are renamed.

Full Defect 11 worked example: `src/test/kotlin/Pipeline/PumpStationLoopGuardSafetyOrderingTest.kt`.