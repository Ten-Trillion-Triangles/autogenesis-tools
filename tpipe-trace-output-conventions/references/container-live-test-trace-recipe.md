# Container Live Test Trace Recipe — Manifold, Junction, DistributionGrid

Operator-mandated standard (2026-07-09, captured during the
`ManifoldMiniMaxLiveTest` rollout): every new live integration test that drives a
TPipe container (Manifold, Junction, DistributionGrid, Splitter) MUST capture
its HTML trace into the default trace dir resolved via
`TPipeConfig.getTraceDir()`. This is the container-class equivalent of the
PumpStation recipe in `references/test-trace-capture-recipe.md`, but the
plumbing is different enough to need its own document.

The earlier `SKILL.md` rule ("use `TPipeConfig.getTraceDir()`, not a
hard-coded literal") and the "Green Test is Not Enough" rule apply here
verbatim. The point of this recipe is to make the container-class pattern
concrete.

## Why Containers Need a Different Recipe

PumpStation uses `enableTracing(TracingConfig(...))` + autoExport. Containers
(Manifold, Junction, DistributionGrid) do **not** auto-export — they expose
`getTraceReport(format: TraceFormat): String` which returns the rendered report
as a Kotlin string. The test has to:

1. Resolve the canonical trace dir via `TPipeConfig.getTraceDir()`.
2. Build the subdir `<component>/<test>/` (the `Library/<feature>/<scenario>/`
   convention used across the live-test suite).
3. `mkdirs()` it.
4. Run the container with `tracing { config(traceConfig) }` enabled.
5. Call `container.getTraceReport(TraceFormat.HTML)` to obtain the HTML string.
6. Write the string to a `.html` file inside the subdir via
   `writeStringToFile`.
7. Assert: file exists, file size > some minimum, file contains expected
   anchors (`MANIFOLD`, `KILLSWITCH_TRIPPED`, etc. — event-type-specific).

Without step 6 the rendered HTML only lives in the heap and is GC'd at test
end. Without step 7 the test is a false positive — same failure mode the
`SKILL.md` "Green Test is Not Enough" section warns about.

## The Recipe (7 Steps)

### Step 1 — Resolve the trace dir at test setup

```kotlin
val traceBaseDir = File(
    "${TPipeConfig.getTraceDir()}/$TRACE_SUBDIRECTORY/$TEST_SUBDIRECTORY"
)
traceBaseDir.mkdirs()
```

`TRACE_SUBDIRECTORY` is the test class's subdir (e.g.
`"Library/manifold-minimax-live"`) and `$TEST_SUBDIRECTORY` is the per-test
subdir (e.g. `"single-worker"`, `"kill-switch"`). The `Library/<feature>/`
prefix matches every existing container live test in the suite
(`JunctionLiveBedrockIntegrationTest.kt:723`,
`DistributionGridLiveBedrockIntegrationTest.kt:937`,
`ManifoldLoopLimitLiveBedrockIntegrationTest.kt:72`).

### Step 2 — Build a `TraceConfig` with explicit `outputFormat = TraceFormat.HTML`

```kotlin
val traceConfig = TraceConfig(
    enabled = true,
    outputFormat = TraceFormat.HTML,
    detailLevel = TraceDetailLevel.DEBUG,
    includeContext = true,
    includeMetadata = true,
)
```

`TraceConfig.exportPath` is OPTIONAL here — the container's `getTraceReport`
doesn't honor it (it returns a string, not a write). The test writes the
rendered HTML manually in step 6.

### Step 3 — Wire the trace config into the container via DSL `tracing { }` block

```kotlin
val manifold = manifold {
    tracing { config(traceConfig) }
    maxIterations(5)
    killSwitch(inputTokenLimit = 2_000, outputTokenLimit = 2_000)
    history { autoTruncate() }
    manager {
        pipeline { /* GenericOpenAIPipe with MiniMax / Bedrock config */ }
        agentDispatchPipe("manager-dispatch")
    }
    worker("echo-worker") { /* worker pipe config */ }
}
```

The `tracing { config(...) }` block calls `Manifold.enableTracing(config)`
internally (`Manifold.kt:1012-1093`) which propagates the trace config to
manager and worker sub-pipelines, AND initializes
`PipeTracer.startTrace(manifoldId)` for the container-level event stream.

### Step 4 — Run the container

```kotlin
runBlocking<Unit> { manifold.execute(userPrompt) }
```

The container emits events to `PipeTracer` keyed by `manifoldId`. Multiple
containers in the same JVM isolate their event streams by ID (UUID generated
at construction).

### Step 5 — Render the HTML trace report to a string

```kotlin
val traceHtml: String = manifold.getTraceReport(TraceFormat.HTML)
```

`getTraceReport` at `Manifold.kt:2220` is a thin wrapper around
`PipeTracer.exportTrace(manifoldId, format)`. Same shape exists on Junction
(`Junction.kt:1520`), DistributionGrid (`DistributionGrid.kt:1156`), and
Splitter (`Splitter.kt:541`).

### Step 6 — Write the HTML to the resolved dir

```kotlin
val tracePath = File(traceBaseDir, "$TEST_SUBDIRECTORY.html")
writeStringToFile(tracePath.absolutePath, traceHtml)
```

`writeStringToFile` is the same helper used in the Bedrock container live
tests. It writes UTF-8 and creates parent dirs as needed (defensive, but
step 1's `mkdirs()` is the canonical path-creation step).

### Step 7 — Assert on file existence, size, and content anchors

```kotlin
assert(tracePath.exists()) { "trace file not written: $tracePath" }
val bytes = tracePath.length()
assert(bytes > 10_000) { "trace suspiciously small: $bytes bytes at $tracePath" }
val content = tracePath.readText()
assert(content.contains("MANIFOLD") || content.contains("kill-switch")) {
    "trace missing expected event anchors"
}
```

The 10 KB minimum is empirical — a container that ran even one LLM call
emits enough Mermaid + summary + event cards to clear 10 KB. A 0-byte or
<1 KB file means `getTraceReport` returned empty (typically because
`tracing { }` was never wired, or the container was never executed).

## Canonical Worked Example

The full pattern lives in
`TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/ManifoldMiniMaxLiveTest.kt`
(shipped 2026-07-09). The 4 tests use this recipe with three variations:

| Test | `TEST_SUBDIRECTORY` | Special assertion |
|------|---------------------|-------------------|
| `manifoldsWithSingleWorkerExecutesTask` | `single-worker` | Final content length > 1000 + agent dispatch trace events present |
| `manifoldsLoopLimitExceededAtMaxIterations` | `loop-limit` | `ManifoldLoopLimitExceededException` thrown within 3 iterations |
| `manifoldsKillSwitchTripsOnTokenLimit` | `kill-switch` | Kill switch trips at inputTokens > 2000 BEFORE loop limit (15 events captured, 8.4s wall clock) |
| `manifoldsWithSingleWorkerProducesHtmlTrace` | `html-trace` | File size > 50 KB, file contains Mermaid node tags + 15+ event cards |

Each test runs the same 7-step recipe, just with different per-test
subdirectory and assertion.

## Failure Modes the Recipe Catches

| Failure | Symptom | What the recipe catches |
|---------|---------|-------------------------|
| `getTraceReport` not called | HTML only lives in heap, GC'd at test end | Step 7 file-exists assertion |
| Hard-coded `~/.tpipe/...` literal | Artifact lands outside `TPipeConfig.getTraceDir()` — survives CI override breakage | Step 1 + Step 6 path assertion |
| Forgot `tracing { config(...) }` | Container emits no events, `getTraceReport` returns empty string | Step 7 size + content assertion |
| Wrong `outputFormat` (e.g. `JSON`) | File is JSON, not HTML — user can't open it in a browser | Step 7 content anchor assertion (HTML-specific) |
| `mkdirs()` not called | `writeStringToFile` may silently create parents, but the canonical location is unclear | Step 1 explicit mkdirs + Step 6 path check |
| Test class lives in the wrong module | E.g. writing live tests under `src/test/` instead of `<module>/src/test/` | Module-level convention (see existing live tests for placement) |

## Anti-Pattern: Asserting Only the Return Value

A container test that asserts
`assertTrue(manifold.getTraceReport(TraceFormat.HTML).isNotBlank())` passes
when the trace string is non-empty in memory. But that string evaporates the
moment the test method returns. The user can't open it, the postmortem can't
read it, and the CI artifact collection step has nothing to upload.

Always write to disk. Always assert on the FILE, not the in-memory string.

## Companion Pitfall: `PumpStationLiveLLMTest` is the PumpStation Equivalent

The PumpStation live test in `TPipe-Bedrock/src/test/kotlin/bedrockPipe/`
uses the PumpStation recipe (autoExport + `taskState.runId` stamp). The
container recipe above is for Manifold/Junction/DistributionGrid/Splitter,
where autoExport doesn't exist and the test must call `getTraceReport` +
`writeStringToFile` manually. Don't mix the two patterns.

## Why This Is a Recipe, Not a New Rule

`SKILL.md` already establishes (a) the resolver rule
(`TPipeConfig.getTraceDir()`), (b) the "Library/<feature>/<scenario>/"
subdir naming convention, (c) the per-test isolation rule (try/finally
around `configDir` mutations), and (d) the "Green Test is Not Enough" rule
(assert on location, not just existence). The recipe adds the container-
class specifics: the `tracing { config(...) }` DSL block, the
`getTraceReport` → string → `writeStringToFile` chain, and the per-test
subdirectory pattern. These specifics are class-level recipe detail, not a
new rule — they live under the existing rule umbrella.
