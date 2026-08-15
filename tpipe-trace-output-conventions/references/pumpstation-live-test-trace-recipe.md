# TPipe PumpStation Live Test Trace Capture Recipe

The canonical recipe for capturing PumpStation traces in an env-gated live test
(`TPIPE_LIVE_LLM_TEST=true` + `MINIMAX_API_KEY`/`OPENROUTER_API_KEY`). Compiled from the
2026-07-11 `PumpStationMultiPathLiveTest` session.

## The Three Signals (all required, not two-of-three)

1. **`tracingConfiguration = traceConfig`** inside the `pumpStation { ... }` DSL block — wires
   the harness's own `enableTracing` against the canonical `TraceConfig`. Without this,
   the `pumpstation-<traceId12>.html` file is never written (the harness has its own
   `getTraceReport` override at `PumpStation.kt:2518-2542` that uses `taskState.runId`
   for the filename; that path only fires when `tracingConfiguration` is set on the
   builder).

2. **`pipeline.enableTracing(traceConfig)` on every agent pipeline** (judge, dispatch,
   any path) BEFORE `runBlocking { pipeline.init(true) }`. This writes the per-pipe
   HTML (`agent-<pipeName>.html`) at the same `exportPath` root. The PumpStation HTML
   and the per-pipe HTMLs both land at the same `<testName>/` subdir.

3. **Explicit `station.getTraceReport(TraceFormat.HTML)` call AFTER
   `runBlocking { executeLocal(...) }`**. This triggers `TraceConfig.autoExport` on
   the harness side — without it, the `pumpstation-<traceId12>.html` does not land
   on disk even though signals (1) and (2) are in place.

## Canonical path resolution

`TraceConfig.exportPath` MUST come from `TPipeConfig.getTraceDir()` (canonical TPipe trace
root). NEVER hard-code `~/.TPipe-Debug/...`.

```kotlin
val traceDir = File(TPipeConfig.getTraceDir(), "PumpStation/$testName")
traceDir.mkdirs()

val traceConfig = TraceConfig(
    enabled = true,
    maxHistory = 5000,
    outputFormat = TraceFormat.HTML,
    detailLevel = TraceDetailLevel.DEBUG,
    autoExport = true,
    exportPath = traceDir.absolutePath,
    includeContext = true,
    includeMetadata = true
)
```

## The full shape

```kotlin
@Test
fun multiPathDispatchProducesValidBatch()
{
    if (System.getenv("TPIPE_LIVE_LLM_TEST") != "true") return
    val apiKey = System.getenv("MINIMAX_API_KEY")
        ?: error("MINIMAX_API_KEY must be set when TPIPE_LIVE_LLM_TEST=true")

    // Per-test cleanup of stale pumpstation-*.html from prior runs.
    val testName = "multiPathDispatchProducesValidBatch"
    val traceDir = File(TPipeConfig.getTraceDir(), "PumpStation/$testName")
    traceDir.mkdirs()
    traceDir.listFiles { f -> f.name.startsWith("pumpstation-") && f.name.endsWith(".html") }
        ?.forEach { it.delete() }

    val traceConfig = TraceConfig(/* as above, exportPath = traceDir.absolutePath */)

    val station = pumpStation("multi-live") {
        judgeAgent = miniMaxPipeline("judge", apiKey, traceConfig)
        dispatchAgent = miniMaxPipeline("dispatch", apiKey, traceConfig)
        tracingConfiguration = traceConfig                // signal 1
        // ... paths, killSwitch, eventObserver ...
    }

    runBlocking {
        station.executeLocal(/* input */)
        station.getTraceReport(TraceFormat.HTML)          // signal 3
    }
}

private fun miniMaxPipeline(name: String, apiKey: String, traceConfig: TraceConfig): Pipeline
{
    val pipe = GenericOpenAIPipe().setApiKey(apiKey)...
    val pipeline = Pipeline().apply { add(pipe) }
    pipeline.enableTracing(traceConfig)                    // signal 2
    runBlocking { pipeline.init(true) }
    return pipeline
}
```

## GenericOpenAIPipe wiring for MiniMax

```kotlin
val pipe = GenericOpenAIPipe()
    .setApiKey(apiKey)
    .setApiMode(ApiMode.OpenAIResponses)
    .setBaseUrl("https://api.minimax.io/v1")   // NOT .chat
    .also { p ->
        p.setPipeName(name)
        p.setModel("MiniMax-M2.7")
        p.setMaxTokens(2000)
        p.setTemperature(0.0)
    }
// Required for non-api.openai.com base URLs:
System.setProperty("tpipe.allowInsecureBaseUrl", "true")
```

Without the `tpipe.allowInsecureBaseUrl=true` system property, the pipe rejects
non-openai.com base URLs at runtime. Set it before `pipeline.init(true)`, clear it
in a `finally` block.

## Mistake: signal (3) without signal (1) or signal (2)

The Harness override at `PumpStation.kt:2518` reads `traceConfig.autoExport` from the
HARNESS'S OWN traceConfig (not the pipeline traceConfigs). Setting `tracingConfiguration
= traceConfig` IS what wires that. Without signal (1), `getTraceReport` at signal (3)
returns the HTML string but the try-catch swallows the export error. Symptom: green
test, zero files in the subdir.

## Mistake: asserting file existence immediately after `getTraceReport`

`getTraceReport` is synchronous and writes via `writeStringToFile`; the file is on
disk before the call returns. BUT, on Gradle test classpath-load races, the file may
not be visible to subsequent `File.listFiles()` calls in the same JVM run — race
condition between `writeStringToFile` returning and the parent's directory entry cache.
If your assertion runs in a tight loop and the file shows up on the next loop
iteration, add a 100-200ms `Thread.sleep` between the call and the assertion. (Rare;
observed once on the 2026-07-11 MultiPath session.)

## Reference implementations

- `src/test/kotlin/Pipeline/PumpStationMultiPathLiveTest.kt` (commit `cdcd9eff`) — MultiPath
  with `pathExecutionShape = PathExecutionShape.MultiPath` and event-observer batch
  capture. The recommended starting template for any new PumpStation live test.
- `src/test/kotlin/Pipeline/PumpStationMiniMaxLiveTest.kt` — earlier reference pattern;
  predates the `tracingConfiguration` fix (its `enableTracing` is wired via agent
  pipelines only, no harness-level `pumpstation-*.html` file).
