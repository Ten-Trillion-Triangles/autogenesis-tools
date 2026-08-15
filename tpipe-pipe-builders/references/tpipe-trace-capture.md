# TPipe pipeline trace capture pattern (HTML + JSON to TPipeConfig.getTraceDir())

Use when the task is "enable tracing, capture it, and save as html and json as per standards to the default dir supplied by TPipeConfig.getTraceDir()" — the canonical Autogenesis pattern for instrumenting a TPipe `Pipeline` so its trace is persisted to disk for post-mortem inspection.

## The 30-second mental model

`TPipeConfig.getTraceDir()` is the project-wide trace root (default `~/.tpipe/trace/`). The trace subsystem writes per-pipeline traces when `enableTracing(...)` is set, and `getTraceReport(TraceFormat)` extracts the trace as a String. To save the trace to disk in the canonical way, the project combines three pieces:

1. `pipeline.enableTracing(TraceConfig(enabled = true, detailLevel = TraceDetailLevel.DEBUG))` before `execute(...)`.
2. `pipeline.getTraceReport(TraceFormat.JSON)` and `pipeline.getTraceReport(TraceFormat.HTML)` for capture.
3. `com.TTT.Util.writeStringToFile(path, content)` for write.

The trace subsystem lives in `TPipe/src/main/kotlin/Debug/` (`PipeTracer.kt`, `TraceFormat.kt`, `TraceConfig.kt`, `TraceDetailLevel.kt`).

## The canonical `saveSystemTrace` shape

The reference implementation is `server/src/main/kotlin/agent/runners/traceCleanup.kt::saveSystemTrace`. Two overloads — one for `Pipeline`, one for `Splitter` — share the same skeleton:

```kotlin
fun saveSystemTrace(subFolder: String, pipeline: Pipeline, fileName: String = "trace")
{
    val dir = File(File(TPipeConfig.getTraceDir()), subFolder)
    if (!dir.exists()) dir.mkdirs()

    val jsonContent = pipeline.getTraceReport(TraceFormat.JSON)
    val htmlContent = pipeline.getTraceReport(TraceFormat.HTML)

    writeStringToFile("${dir.absolutePath}/$fileName.json", jsonContent)
    writeStringToFile("${dir.absolutePath}/$fileName.html", htmlContent)

    Logger.debug(LogCategory.SYSTEM, "Saved system traces (JSON/HTML) to ${dir.absolutePath}/$fileName.*")
}
```

`subFolder` is the per-feature name (e.g. `"MapUploadGate"`, `"Judge"`, `"ReversalAgent"`). The `fileName` default is `"trace"`. The output layout is `${TPipeConfig.getTraceDir()}/${subFolder}/${fileName}.{json,html}`. The `getTurnTraceDir()` helper at `traceCleanup.kt:27-39` wraps the same shape with an optional turn-folder prefix when `setCurrentTurnFolderName(name)` has been called — for one-shot invocations like the map-upload gate, the simpler `subFolder` form is the right shape.

## Wiring into a `@RpcMethod`-orchestrated function (real case: `MapUploadGate`)

The 2026-08-10 `MapUploadGate.uploadMapGate` instrumentation is the working example. The pattern lives in three places:

### 1. Imports in the orchestrator file

```kotlin
import com.TTT.Config.TPipeConfig
import com.TTT.Debug.TraceConfig
import com.TTT.Debug.TraceDetailLevel
import com.TTT.Debug.TraceFormat
import com.TTT.Pipeline.Pipeline
import com.TTT.Util.writeStringToFile
import java.io.File
```

### 2. The production branch — `enableTracing` + capture call site

```kotlin
// Inside the else-branch of the `if (runner != null)` test seam:
val pipeline = buildMapSafetyAgent(playerId, payload)
pipeline.enableTracing(TraceConfig(enabled = true, detailLevel = TraceDetailLevel.DEBUG))

val multimodal = MultimodalContent(text = "Map upload safety check")
multimodal.addBinary(payload.imageBytes, mimeType = "image/png", filename = "map.png")
val pipelineResult = pipeline.execute(multimodal)

captureAndSaveTrace(pipeline, playerId)   // <-- the new helper call
pipelineResult
```

Three details worth pinning:
- The `enableTracing` call MUST happen before `execute(...)` — the trace subsystem attaches lifecycle listeners during this call, and `execute` is the moment they fire.
- The capture happens for both pass and fail paths (capture before the `!result.shouldTerminate()` check). Failures are usually MORE valuable to trace than passes, so capturing the trace even when the pipeline reports a safety rejection is intentional.
- Test-seam-driven paths (the `if (runner != null)` branch in `MapUploadGate`) bypass the real pipeline entirely and never call `enableTracing` — the test seam returns a synthetic `MultimodalContent` without going through the pipeline. The trace helper is wired into the production branch only, so the existing fake-seam unit tests still pass without exercising the trace path.

### 3. The private `captureAndSaveTrace` helper

```kotlin
private fun captureAndSaveTrace(pipeline: Pipeline, playerId: String)
{
    try
    {
        val subFolder = "MapUploadGate"
        val dir = File(File(TPipeConfig.getTraceDir()), subFolder)
        if (!dir.exists()) dir.mkdirs()

        val jsonContent = pipeline.getTraceReport(TraceFormat.JSON)
        val htmlContent = pipeline.getTraceReport(TraceFormat.HTML)

        writeStringToFile("${dir.absolutePath}/trace.json", jsonContent)
        writeStringToFile("${dir.absolutePath}/trace.html", htmlContent)

        Logger.debug(LogCategory.SYSTEM, "MapUploadGate: saved trace (JSON/HTML) to ${dir.absolutePath}/trace.* for playerId=$playerId")
    }
    catch (e: Exception)
    {
        Logger.error(LogCategory.SYSTEM, "MapUploadGate: trace capture failed for playerId=$playerId: ${e.message}")
    }
}
```

The helper is `internal` (not `private`) when the test class needs to invoke it directly. The try/catch around the entire body is the load-bearing piece — any I/O failure (disk full, permissions flipped, the trace dir accidentally replaced by a file) logs at ERROR but does NOT propagate, so the orchestrator's HTTP response / RPC return value is never blocked by a trace-write problem.

## Test seam — `captureAndSaveTrace` is `internal` for the test, not `private`

`MapUploadGate.captureAndSaveTrace` is declared `internal fun` (not `private fun`) so the unit test class in the same module can invoke it directly. The test shape:

```kotlin
@Test
fun `captureAndSaveTrace writes trace json and trace html under TPipeConfig getTraceDir MapUploadGate`() = runBlocking {
    val pipeline = Pipeline()
    pipeline.enableTracing()

    // Sanity: confirm the file does not exist before the call.
    val traceDir = File(File(TPipeConfig.getTraceDir()), "MapUploadGate")
    val jsonFile = File(traceDir.absolutePath, "trace.json")
    val htmlFile = File(traceDir.absolutePath, "trace.html")
    if (jsonFile.exists()) jsonFile.delete()
    if (htmlFile.exists()) htmlFile.delete()

    MapUploadGate.captureAndSaveTrace(pipeline, playerId = "player-trace-test")

    assertTrue(traceDir.exists(), "MapUploadGate trace dir must exist")
    assertTrue(jsonFile.exists(), "trace.json must exist")
    assertTrue(htmlFile.exists(), "trace.html must exist")
    assertTrue(jsonFile.readText().isNotEmpty(), "trace.json must be non-empty")
    assertTrue(htmlFile.readText().isNotEmpty(), "trace.html must be non-empty")
}

@After
fun resetAfter() {
    val dir = File(File(TPipeConfig.getTraceDir()), "MapUploadGate")
    if (dir.exists()) dir.deleteRecursively()  // hermetic
}
```

The test is hermetic: the `@After` cleans the subfolder so subsequent runs (and other test classes) don't accumulate traces from the test.

## Failure-path test — point the config dir at a path that cannot be created

```kotlin
@Test
fun `captureAndSaveTrace swallows IO failures and does not propagate`() = runBlocking {
    val pipeline = Pipeline()
    pipeline.enableTracing()

    val originalConfigDir = TPipeConfig.configDir
    try
    {
        // Block the trace dir with a non-directory file so mkdirs() fails.
        val blocker = File("/tmp/hermes-trace-blocker-${System.nanoTime()}")
        blocker.createNewFile()
        TPipeConfig.configDir = blocker.absolutePath
        try
        {
            // The helper's catch block swallows the IO failure.
            // If the call threw, this line would be unreachable and the test fails.
            MapUploadGate.captureAndSaveTrace(pipeline, playerId = "player-fail-test")
        }
        finally
        {
            TPipeConfig.configDir = originalConfigDir
            blocker.delete()
        }
    }
    catch (e: Exception)
    {
        TPipeConfig.configDir = originalConfigDir
        throw AssertionError("captureAndSaveTrace must not propagate IO failures; got: ${e.message}", e)
    }
}
```

This test pins the contract that the trace helper does NOT become a load-bearing piece of the orchestrator's response path.

## Honest limitations of the unit test

The trace content is empty for an empty `Pipeline` — no pipes were executed. The test pins the file-write contract, NOT the trace payload shape. The trace payload format is verified by the upstream TPipe test suite (`TPipe/src/test/kotlin/Debug/PipeTracerTest.kt`, `TraceVerbosityTest.kt`, etc.) — those are the canonical tests for the trace content, not the orchestrator.

A test that exercised the full `MapUploadGate.uploadMapGate` path end-to-end would require a live Bedrock pipeline (or a heavy mock layer), which is the same kind of "live API test" the rest of the orchestrator suite already punts to manual smoke tests. The two-case unit test in `MapUploadGateTraceTest` is the right level for this class of helper.

## Why this is not just `pipeline.exportTrace(pipelineId, TraceFormat.HTML)`

`PipeTracer.exportTrace(pipelineId, TraceFormat.HTML)` is a lower-level API at `TPipe/src/main/kotlin/Debug/PipeTracer.kt:137` that takes a pipelineId string and exports via the trace subsystem. The orchestrator should use `pipeline.getTraceReport(TraceFormat.X)` instead because:

1. The `getTraceReport` form is what every other Autogenesis trace-writer uses (`traceCleanup.kt::saveSystemTrace`, `npcOrchestrator.kt:411/452`). Consistency with the project's existing trace-writer pattern is more important than reaching for the lower-level API.
2. `getTraceReport` returns a `String`, which `writeStringToFile` accepts directly. `exportTrace` returns a `String` too but couples the call site to the `PipeTracer` global instead of the local `pipeline` instance.
3. `getTraceReport` defaults to `traceConfig.outputFormat` (set during `enableTracing(...)`), so the call site picks the format explicitly — the captured string is unambiguous.

## Trade-offs and known debt

- **Tracing cost.** `TraceDetailLevel.DEBUG` produces large traces for every safety pass. For a high-volume upload scenario this would be expensive. The 2026-08-10 implementation matches the canonical `traceCleanup.kt` pattern (always-on DEBUG) on the rationale that the gate is a low-frequency path (one per upload per player). If upload volume ever justifies it, gate the `enableTracing` call on a `TPipeConfig`-driven feature flag.
- **Trace dir cleanup.** `TPipeConfig.getTraceDir()` is shared across the whole process. The `MapUploadGate/` subfolder accumulates traces indefinitely. Long-running server-extend processes will accumulate traces until manual cleanup. Defer to a separate cleanup ticket — the existing `traceCleanup.kt::clearTraceDirectory()` helper at `traceCleanup.kt:82-142` is the right shape for the cleanup, gated on whether a feature has finished.
- **Concurrency.** Two simultaneous uploads from the same player race on `trace.json` / `trace.html` writes. The `writeStringToFile` helper is the same one used elsewhere — verified atomicity behavior is the existing project's responsibility.
- **`Pipeline` is `final`; cannot subclass for a test stub.** `class Pipeline : P2PInterface` at `TPipe/src/main/kotlin/Pipeline/Pipeline.kt:45` is plain `class`, not `open class`, AND `getTraceReport` is non-`open`. The unit test that exercises the helper directly cannot subclass the pipeline; it must use `Pipeline()` directly with an empty pipe list. The trace content for an empty pipeline is empty, but the file-write contract is what the test pins. If a future test needs a richer trace, the answer is a heavier integration test (live Bedrock) — not a subclass.

## Related references

- `references/stall-detection-recursive-config.md` — the recursive `StreamingStallConfig` helper, which is the OTHER `enable<Tracing-lifecycle>` setter on a Pipeline (runtime stall detection vs. persisted trace). Companion concept; same Pipeline target, different instrumentation.
- `tpipe-pipe-builders/SKILL.md` — the parent umbrella. The Mantle / Bedrock / TPipe-Tuner / streaming / reasoning-metadata / parent-child-alignment references are all related but orthogonal to the trace capture pattern.
