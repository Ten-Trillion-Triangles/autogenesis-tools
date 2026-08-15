# PumpStation Gap-Coverage Test Recipe

Captured from the 2026-07-10 `PumpStationGapCoverageLiveTest` session. The user explicitly asked: *"Did you make sure every test you wrote is capturing traces, and saving those traces to the default trace dir defined exactly by TPipeConfig?"* — every future PumpStation test that asserts on trace artifacts must follow the recipe below.

## The Recipe (5 mandatory steps)

```kotlin
private fun traceConfigFor(testName: String): TraceConfig
{
    val perTestDir = File(TPipeConfig.getTraceDir(), testName)
    perTestDir.deleteRecursively()   // wipe stale traces from prior runs
    perTestDir.mkdirs()
    return TraceConfig(
        enabled = true,
        maxHistory = 5000,
        outputFormat = TraceFormat.HTML,
        detailLevel = traceDetail,
        autoExport = true,
        exportPath = perTestDir.absolutePath   // path is exactly $TPIPE_TRACE_DIR/<testName>
    )
}
```

Then in every test:
1. `val traceCfg = traceConfigFor("<test-name>")`
2. `val pumpStationHtmlDir = File(TPipeConfig.getTraceDir(), "<test-name>")` ← same path as step 1
3. `pumpStation(...) { tracingConfiguration = traceCfg; ... }`
4. `station.executeLocal(...)` (drives the harness)
5. `station.getTraceReport(TraceFormat.HTML)` (triggers autoExport)
6. Walk `pumpStationHtmlDir.walkTopDown().filter { it.extension == "html" }` to assert

Both the trace WRITE (step 3 wiring) and trace READ (step 6 assertion) MUST use the same `File(TPipeConfig.getTraceDir(), testName)` path. If they diverge, the test passes against the wrong artifact root — the worst false-positive class (see "Canonical vs Legacy Trace Diff" in SKILL.md).

## Why TPipeConfig.getTraceDir() specifically

`src/main/kotlin/Config/TPipeConfig.kt:52` returns `"${getDebugDir()}/trace"` = `~/.tpipe/debug/trace`. There is also a LEGACY root at `~/.TPipe-Debug/traces/PumpStation/` hardcoded at `PumpStationMiniMaxLiveTest.kt:140`. Always wire to the canonical root — production code uses TPipeConfig, tests should too.

## Verification pattern

After the test passes, the trace dir MUST contain at least one `pumpstation-ps-NNN.html` file. If `pumpStationHtmlDir.walkTopDown()` returns empty after `getTraceReport(TraceFormat.HTML)`, the harness did NOT write a trace — usually because `tracingConfiguration` was set on the wrong DSL variable or `autoExport=false` blocked the write.

## Companion: stub-vs-live symmetry

When writing a gap test, prefer BOTH a stub variant and a live variant (per the apex-coder persona's preference and the user's "using generic open ai and minimax" instruction):

- Stub variant: queue per-role canned responses on a `com.sun.net.httpserver.HttpServer`, deterministic, no API key required (any non-blank key + `tpipe.allowInsecureBaseUrl=true`).
- Live variant: gate on `liveGateOrSkip()` (rejects stub keys starting with `sk-stub`), hits real MiniMax endpoint.

Per-role detection in the stub: the OpenAI Responses API hoists the system prompt into the top-level `instructions` field. Substring-match `lower.contains("the dispatcher in an agentic harness")` etc. against the body — same heuristic as the production `StubOpenAIServer` in `PumpStationMiniMaxLiveTest.kt:1591`.

## Anti-pattern: writing trace to a literal path

```kotlin
// BAD: hardcoded literal — diverges from TPipeConfig.getTraceDir()
val traceDir = "/tmp/pumpstation-test-traces"
```

```kotlin
// GOOD: canonical path
val traceDir = File(TPipeConfig.getTraceDir(), "my-test")
```

## Companion: per-test trace dir cleanup

The `deleteRecursively()` at the start of `traceConfigFor` ensures each run starts with an empty trace dir. Without it, `walkTopDown()` walks into stale traces from prior runs that may share the same harness configuration — false positive risk.

## Existing gap-coverage test as reference implementation

`src/test/kotlin/Pipeline/PumpStationGapCoverageLiveTest.kt` (Cycle 112, 2026-07-10) is the canonical implementation. 4 test methods, all use `traceConfigFor()` + `pumpStationHtmlDir` from the same `File(TPipeConfig.getTraceDir(), testName)` path. Bug 14 source fix shipped as paired additive change in the same patch.