# PumpStation Live + Stub Test Suite Architecture

Captured 2026-07-10 from the post-goal-hook feature rollout. The pattern
that emerged is the canonical shape for **any new PumpStation feature that
needs integration coverage** (new DSL field, new agent slot, new event type,
new exit reason, new trace visualization). Adopt it for the next PumpStation
feature you ship.

## Why This Reference Exists

The first attempt at the post-goal hook shipped a single-test live suite
(`PumpStationPostGoalLiveTest.kt` with one test) that:
- Did NOT wire `tracingConfiguration` to the harness.
- Did NOT call `station.getTraceReport(...)` to render the HTML.
- Did NOT assert on a trace artifact at `TPipeConfig.getTraceDir()`.
- Did NOT exercise the stub-mode path (deterministic canned responses).
- Did NOT cover multiple configurations (multi-path, compaction, flag-triggered judge, kill switch).

The operator pushed back: *"did you make a live test to correctly test the new
PumpStation feature? And does it capture traces and save the traces at the
default path supplied by TPipeConfig?"* — and then *"I expected you to have
been lazy and create the test like I asked, but you cant find the other tests?
They should be there unless you deleted them."* The expected shape was the
`PumpStationMiniMaxLiveTest` 12-test layout (6 stub + 6 live, full trace
capture, per-test subdir).

The shape is not just for live tests — it's a **suite architecture template**
for any new PumpStation feature.

## The 6-Configuration × 2-Mode Matrix

`PumpStationMiniMaxLiveTest` defines the canonical configurations. Pick a
subset that exercises the code paths your feature actually touches. The
post-goal feature picked 6; the manifest of available configurations is:

| Configuration | `useFlagTriggeredJudge` | `useRiskLevels` | `memoryMode` | `useSinglePathPassPipeline` | What it tests |
|---|---|---|---|---|---|
| Always-on judge | `false` | `false` | `null` | `false` | Standard judge/dispatch/path loop with full judge every turn |
| Flag-triggered judge | `true` | `false` | `null` | `false` | Report path calls `requestJudgeNextTurn()`, judge fires only then |
| Compaction memory | `false` | `false` | `Compaction` | `false` | Compaction orchestrator runs, summary agent called, `compactionThreshold = 0.01` |
| Kill switch trip | `false` | `false` | `null` | `false` | `KillSwitch(inputTokenLimit, outputTokenLimit)` trips mid-run |
| Single-path pass-pipeline | `false` | `false` | `null` | `true` | Single `report` path with `passPipeline = true`, no judge, exits `PassSignal` |
| Multi-path risk levels | `false` | `true` | `null` | `false` | gather (Low) → analyze (Medium) → report (High), path-safety agent validates Medium+ |

Each configuration × `{stub, live}` = 12 test methods. The stub-mode tests
use `StubOpenAIServer` (a per-role FIFO queue over `com.sun.net.httpserver.HttpServer`)
and run deterministically without an API key. The live-mode tests hit
`https://api.minimax.io/v1` with `MiniMax-M2.7` and are stochastic but prove
the harness runs end-to-end against the real LLM.

## The Template Skeleton (drop-in for a new PumpStation feature)

```kotlin
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MyFeatureLiveTest
{
    companion object
    {
        // === Same constants as PumpStationMiniMaxLiveTest ===
        private const val MINIMAX_BASE_URL = "https://api.minimax.io/v1"
        private const val MINIMAX_MODEL = "MiniMax-M2.7"
        private const val TEMPERATURE = 1.0
        private const val TOP_P = 0.95
        private const val TOP_K = 40
        private const val MAX_TOKENS = 16384
    }

    private var apiKeyCache: String? = null

    @BeforeAll
    fun setup()
    {
        // CRITICAL: bashrc-parsing pattern. The gradle test JVM does NOT source
        // ~/.bashrc, so System.getenv("MINIMAX_API_KEY") is null in the typical
        // Hermes terminal session. Parse ~/.bashrc directly when env var is unset.
        val envKey = System.getenv("MINIMAX_API_KEY")
        val key = envKey?.takeIf { it.isNotBlank() } ?: readKeyFromBashrc()
        if (key.isNullOrBlank()) return
        genericOpenAIPipe.env.GenericOpenAIEnv.setApiKey(key)
        apiKeyCache = key
        // Required for stub-mode tests with http:// baseUrl
        System.setProperty("tpipe.allowInsecureBaseUrl", "true")
    }

    @AfterAll
    fun teardown()
    {
        if (apiKeyCache != null) {
            genericOpenAIPipe.env.GenericOpenAIEnv.clearApiKey()
            apiKeyCache = null
        }
        System.clearProperty("tpipe.allowInsecureBaseUrl")
    }

    private fun liveGateOrSkip(): String? = apiKeyCache?.takeUnless { it.startsWith("sk-stub") }
    private fun stubGateOrSkip(): String? = apiKeyCache?.takeIf { it.startsWith("sk-stub") }

    // ============================================================
    // STUB-MODE TESTS (6 configs)
    // ============================================================

    @Test fun stub_01_alwaysOnJudge_myFeatureFires() = runBlocking<Unit> { ... }
    @Test fun stub_02_flagTriggeredJudge_myFeatureFires() = runBlocking<Unit> { ... }
    @Test fun stub_03_compactionMemory_myFeatureFires() = runBlocking<Unit> { ... }
    @Test fun stub_04_killSwitchTrip_myFeatureFires() = runBlocking<Unit> { ... }
    @Test fun stub_05_singlePathPassPipeline_myFeatureFires() = runBlocking<Unit> { ... }
    @Test fun stub_06_multiPathRiskLevels_myFeatureFires() = runBlocking<Unit> { ... }

    // ============================================================
    // LIVE-MODE TESTS (6 configs, parallel to stub-mode)
    // ============================================================

    @Test fun live_01_alwaysOnJudge_myFeatureFires() = runBlocking<Unit> { ... }
    // ... live_02 through live_06 mirror the stub_*

    // ============================================================
    // HARNESS RUNNER — drives one configuration end-to-end with trace capture
    // ============================================================

    private suspend fun runHarness(
        testName: String,
        baseUrl: String,
        config: String,
        // ... per-config parameters
        configurePaths: PumpStationBuilder<*>.() -> Unit,
        configureMyFeature: PumpStationBuilder<*>.() -> Unit,
        myFeatureExpectsFire: Boolean,
        expectedExit: PumpStationExitReason = PumpStationExitReason.JudgeComplete
    ) {
        val traceCfg = traceConfigFor(testName)
        val station = pumpStation("myfeature-$testName") {
            // ... wire judge/dispatch/goal/path/your-feature ...
            tracingConfiguration = traceCfg
            systemTask = "..."
            userGuidelines = "..."
            maxHarnessTurns = 6
        }

        val result = station.executeLocal(MultimodalContent(text = "..."))
        station.drainBackgroundEventQueue()
        station.getTraceReport(TraceFormat.HTML)  // Triggers autoExport
        exportAgentTraces(testName)

        assertRunProducedTracesWithFeature(station, testName, expectedExit, myFeatureExpectsFire)
        assertNotNull(result.text)
    }

    // ============================================================
    // TRACE CAPTURE + ASSERTION HELPERS (copy from PumpStationMiniMaxLiveTest)
    // ============================================================

    private fun traceDir(): File {
        val dir = File(TPipeConfig.getTraceDir(), "MyFeature")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    private fun traceSubdir(testName: String): File {
        val sub = File(traceDir(), testName)
        if (!sub.exists()) sub.mkdirs()
        return sub
    }

    private fun traceConfigFor(testName: String): TraceConfig {
        val subdir = traceSubdir(testName)
        // Clean stale pumpstation-*.html from prior runs
        subdir.listFiles { f -> f.name.startsWith("pumpstation-") && f.name.endsWith(".html") }
            ?.forEach { it.delete() }
        return TraceConfig(
            enabled = true,
            maxHistory = 5000,
            outputFormat = TraceFormat.HTML,
            detailLevel = TraceDetailLevel.DEBUG,
            autoExport = true,
            exportPath = subdir.absolutePath,
            includeContext = true,
            includeMetadata = true
        )
    }

    private fun exportAgentTraces(testName: String) { /* ... walk PipeTracer.getAllTraces, write per-agent HTML ... */ }

    private fun assertRunProducedTracesWithFeature(
        station: PumpStation,
        testName: String,
        expectedExit: PumpStationExitReason,
        featureExpectsFire: Boolean
    ) {
        // === LOCATION check ===
        val runId = station.getTraceId()
        assert(!runId.isNullOrBlank()) { "$testName: getTraceId() returned blank" }

        val report = station.getTraceReport(TraceFormat.HTML)
        assert(report.isNotBlank() && report.contains("<html")) {
            "$testName: getTraceReport(HTML) returned non-HTML (len=${report.length})"
        }

        val state = station.getTaskState()
        val acceptedExits = setOf(expectedExit, PumpStationExitReason.MaxTurnsHit)
        assert(state.exitReason in acceptedExits) {
            "$testName: expected $acceptedExits, got ${state.exitReason}"
        }

        val subdir = traceSubdir(testName)
        val pumpHtmls = subdir.listFiles { f ->
            f.name.startsWith("pumpstation-") &&
                f.name.endsWith(".html") &&
                f.name.contains("-${runId!!.take(12)}.")
        } ?: emptyArray()
        assert(pumpHtmls.isNotEmpty() && pumpHtmls.all { it.length() > 5000 }) {
            "$testName: pump station HTML not found at $subdir"
        }

        // === CONTENT check — your feature ===
        val pumpHtml = pumpHtmls.first().readText()
        if (featureExpectsFire) {
            assertTrue(pumpHtml.contains("YOUR_FEATURE_EVENT_NAME")) { /* ... */ }
        } else {
            assertFalse(pumpHtml.contains("YOUR_FEATURE_EVENT_NAME")) { /* ... */ }
        }
    }

    // ============================================================
    // STUB OPENAI SERVER (replicate from PumpStationMiniMaxLiveTest — private)
    // ============================================================

    private class StubOpenAIServer { /* ... per-role FIFO + detectRole() ... */ }
    private fun startStub(): StubOpenAIServer = StubOpenAIServer().also { it.start() }
}
```

## Critical Pitfalls Surfaced By This Pattern

### Pitfall 1: `useSinglePathPassPipeline = true` BYPASSES `runExitFlow`

The `singlePathPassPipeline` configuration looks like a clean test of
"the no-judge exit path" but **does NOT call `runExitFlow`**. From
`PumpStationLoop.kt:1940-1953`:

```kotlin
if (pathResult != null) {
    taskState.latestContent = pathResult
    if (pathResult.passPipeline) {
        return if (goalAgent == null) {
            TurnResult.Halt(PumpStationExitReason.PassSignal)   // ← direct halt, NO goal gate
        } else {
            runExitFlow()                                       // ← goal gate runs
        }
    }
    ...
}
```

A test that wires `useSinglePathPassPipeline = true` AND `goalAgent = null`
will exit with `PassSignal` and `runExitFlow` is **never invoked**. Any
post-goal hook, post-exit hook, or other intervention that lives INSIDE
`runExitFlow` will **not fire** under this configuration.

If you want to test the no-goal-agent branch of `runExitFlow` (line 2393),
you must drive the exit via the judge (`isComplete: true`), NOT via
`useSinglePathPassPipeline`. Use:

```kotlin
@Test
fun stub_01_noGoalAgent_postGoalHookFiresOnJudgeRoutedExit() = runBlocking<Unit> {
    val stubKey = stubGateOrSkip() ?: return@runBlocking
    val stub = startStub()
    try {
        stub.loopEnqueue("judge") { stubJson(isComplete = true) }   // ← judge drives exit
        stub.loopEnqueue("dispatch") { stubJson(passPipeline = true) }
        stub.loopEnqueue("report") { "Brief on Kotlin coroutines." }
        runHarness(
            testName = "stub-01-no-goal-agent",
            baseUrl = stub.baseUrl(),
            useSinglePathPassPipeline = false,                      // ← not true!
            configurePaths = { registerSinglePathReportPath() },
            configureGoal = { /* no goal agent */ },
            postGoalExpectsFire = true,
            expectedExit = PumpStationExitReason.JudgeComplete
        )
    } finally { stub.stop() }
}
```

The wrong shape (which compiles and runs but silently skips your hook):

```kotlin
useSinglePathPassPipeline = true,            // ← bypasses runExitFlow
configureGoal = { /* no goal agent */ },      // ← goal never validated, hook never fires
```

This is a class-level signal for any new exit-flow intervention feature
(post-goal hook, post-exit hook, post-judge hook): the `runExitFlow` entry
points are:
1. `PumpStationLoop.kt:1712-1754` — called from `runTurn` when `judge.isComplete = true`
2. `PumpStationLoop.kt:1940-1953` — called from `runTurn` when `path.passPipeline = true AND goalAgent != null`

NOT called when:
- `useSinglePathPassPipeline = true` AND `goalAgent = null` (direct `PassSignal` halt)
- `path.terminatePipeline = true` (direct `TerminateSignal` halt)
- `judge.shouldTerminate = true` (direct `TerminateSignal` halt)

### Pitfall 2: `runBlocking { pipeline.init(true) }` is MANDATORY for every pipe

A test that constructs a `GenericOpenAIPipe` and assigns it to a `goalAgent`,
`judgeAgent`, `dispatchAgent`, or `pathInternalAgent` slot — but does NOT call
`pipeline.init(true)` — will get an `IllegalStateException: GenericOpenAIPipe
not initialized. Call init() first.` at the FIRST `executeLocal` call, NOT at
construction time. The pipe stays in an uninitialized state until the harness
tries to invoke it.

The `PumpStationMiniMaxLiveTest.createJudgePipeline` pattern:

```kotlin
private fun createJudgePipeline(testName: String, baseUrl: String): Pipeline {
    val pipe = createMiniMaxPipe("judge", systemPrompt = DEFAULT_JUDGE_PROMPT, baseUrl = baseUrl)
    val pipeline = Pipeline().apply { add(pipe) }
    runBlocking { pipeline.init(true) }   // ← MANDATORY
    return pipeline
}
```

Apply the same pattern to every pipeline you create — judge, dispatch, path
internal agent, path-safety, summary, custom goal agent wrapped in
`Pipeline.executeLocal`. The `runBlocking` is intentional: the constructor
chain runs synchronously in a `runBlocking { pumpStation("name") { ... } }`
context, and the `suspend fun init()` needs a coroutine context to invoke
`pipe.init()` which is also suspend.

### Pitfall 3: `val cannot be reassigned` from local val shadowing DSL field

The DSL fields `goalAgent`, `postGoalAgent`, `judgeAgent`, etc. are public
`var`s on `PumpStationBuilder`. Inside a builder lambda, assigning
`goalAgent = goalAgent` is an error: the RHS resolves to the LOCAL val
(not the DSL field) and Kotlin's val-reassignment check fires.

```kotlin
// WRONG — `goalAgent` on the RHS is the local val, not the DSL field
val goalAgent = SgTestAgent(agentTag = "ga")
val station = pumpStation("name") {
    goalAgent = goalAgent   // ← ERROR: 'val' cannot be reassigned
}

// CORRECT — rename the local to avoid the shadow
val goalAgentImpl = SgTestAgent(agentTag = "ga")
val station = pumpStation("name") {
    goalAgent = goalAgentImpl
}
```

This bit the post-goal test rewrite on the first compile. Other places the
shadow hits: `postGoalAgent`, `judgeAgent`, `dispatchAgent`, `pathSafetyAgent`.

### Pitfall 4: The bashrc-parsing pattern (Hermes-specific)

The standard `System.getenv("MINIMAX_API_KEY")` call returns null in the
test JVM when:
- The user runs the test via Hermes terminal which spawns a non-interactive
  bash subprocess that does NOT source `~/.bashrc` or `~/.profile`.
- The user runs via gradle CLI without re-exporting the env var.

Per the operator's out-of-band signal: *"get the api key from bashrc I
told you this before"* — the test MUST parse `~/.bashrc` directly when
`System.getenv` returns null. The recipe:

```kotlin
private fun readKeyFromBashrc(): String? {
    val home = System.getProperty("user.home") ?: return null
    val bashrc = File(home, ".bashrc")
    if (!bashrc.exists()) return null
    val line = bashrc.readLines().firstOrNull { it.startsWith("export MINIMAX_API_KEY=") }
        ?: return null
    return line.replaceFirst("export MINIMAX_API_KEY=", "")
        .trim()
        .trim('"')
        .trim('\'')
        .takeIf { it.isNotBlank() }
}
```

The same pattern works for any env var defined in `~/.bashrc`. Apply it to
`OPENROUTER_API_KEY` (for `PumpStationLiveLLMTest`), `ANTHROPIC_API_KEY`,
etc. — extract the key from bashrc instead of asking the user to re-export.

When the key is loaded, call:

```kotlin
genericOpenAIPipe.env.GenericOpenAIEnv.setApiKey(key)
System.setProperty("tpipe.allowInsecureBaseUrl", "true")  // required for stub-mode
```

The `setApiKey` populates the static env, which `GenericOpenAIPipe.init()`
reads at pipe construction time. The `allowInsecureBaseUrl` is required for
stub-mode tests whose `StubOpenAIServer` runs on `http://localhost:port` —
without it, `setBaseUrl` throws `IllegalArgumentException`.

### Pitfall 5: `acceptedExits` set MUST include `MaxTurnsHit`

For configurations that don't pre-determine the exit reason (multi-turn
judge/dispatch loops in live-mode, multi-path, compaction), the real LLM
may iterate past the harness's `maxHarnessTurns` and exit with
`MaxTurnsHit` instead of the expected `JudgeComplete`. The accepted-exits
set MUST include both:

```kotlin
val acceptedExits = setOf(expectedExit, PumpStationExitReason.MaxTurnsHit)
assert(state.exitReason in acceptedExits) {
    "$testName: expected $acceptedExits, got ${state.exitReason}"
}
```

The flag-triggered judge, compaction, and multi-path tests need this. The
kill-switch and pass-pipeline tests use single-shot exits and can keep a
stricter check. The post-goal tests use the inclusive set across all
configurations because the goal-validation path is multi-turn-sensitive.

### Pitfall 6: Trace HTML writes the EVENT TYPE NAME, not the data class

The pump station's `tracePumpStationEvent` (`PumpStationHelpers.kt:439-446`)
maps the new event to `TraceEventType.PUMP_STATION_<TYPE>` for the event
type field, and renders metadata via the turn-detail HTML renderer
(`TraceVisualizer.kt:2479`). The assertion looks for the EVENT TYPE NAME
in the HTML, not the data class name:

```kotlin
// CORRECT — assert on the rendered event type by name
assertTrue(pumpHtml.contains("PUMP_STATION_POST_GOAL_COMPLETED")) { ... }

// WRONG — the data class name "PostGoalCompleted" does NOT appear in the HTML
assertTrue(pumpHtml.contains("PostGoalCompleted")) { ... }  // always fails
```

Similarly, metadata field names ARE rendered (as `<span class="ps-meta-key">passed</span>`),
so a `passed=true` assertion works as `html.contains("passed:")` and
`html.contains("ps-meta-val'>true")` (the meta-val span renders the value).

### Pitfall 7: Live-mode tests need retry-on-503 around `executeLocal`

Captured 2026-07-11 from the post-goal-hook live suite rollout. The
MiniMax upstream API (`https://api.minimax.io/v1`) returns
`P2PException: OpenAI Responses error: Service error. Please retry later`
intermittently — sometimes on the first call, sometimes mid-harness-loop,
sometimes after 100+ successful calls in a day. This is a transient
upstream condition, not a test bug. The same intermittent pattern hit
on different days for different test runs of the SAME code, with the
SAME key, against the SAME endpoint. The existing `PumpStationMiniMaxLiveTest`
also has this same flakiness class — every TPipe live-mode test does.

The fix is a retry wrapper around `executeLocal` in the test harness
runner:

```kotlin
private suspend fun runHarness(
    testName: String,
    // ... per-config parameters
) {
    val station = pumpStation("feature-$testName") {
        // ... wire all agents, paths, tracing, etc.
    }

    var attemptCount = 0
    val maxAttempts = 3
    var lastException: Throwable? = null
    while (attemptCount < maxAttempts) {
        attemptCount += 1
        try {
            val result = station.executeLocal(MultimodalContent(text = "..."))
            station.drainBackgroundEventQueue()
            station.getTraceReport(TraceFormat.HTML)
            exportAgentTraces(testName)
            assertRunProducedTracesWithFeature(station, testName, expectedExit, featureExpectsFire)
            assertNotNull(result.text)
            return  // success
        }
        catch (e: com.TTT.P2P.P2PException) {
            lastException = e
            val isTransient = e.message?.contains("Service error", ignoreCase = true) == true
            if (!isTransient || attemptCount >= maxAttempts) throw e
            System.err.println("[RETRY] $testName attempt $attemptCount/$maxAttempts failed: " +
                "${e.message?.take(120)}; sleeping 3s")
            kotlinx.coroutines.delay(3000)
        }
    }
    throw lastException ?: IllegalStateException("$testName: retry loop exited without result")
}
```

Three critical properties:

1. **Only retry on the SPECIFIC transient condition**. Match on the
   literal message substring "Service error" (case-insensitive). Anything
   else (prompt errors, auth errors, malformed JSON, missing schema fields)
   fails fast — retrying those just wastes the budget on a real bug.

2. **3 attempts, 3s backoff**. Enough to absorb a transient blip, short
   enough to keep the suite under its 16-minute budget. Exponential
   backoff is overkill for transient 503s; flat 3s works.

3. **Wrap the trace-emission AND assertion inside the try block**. The
   `getTraceReport(HTML)` call must run on the successful attempt (so
   the trace HTML lands on disk). If you put it after the retry loop,
   you lose trace capture on the success path too. If you put the
   assertion inside the loop, the same trace-write happens on every
   retry — fine, the assertions are idempotent, but the trace HTML
   gets overwritten N times.

Diagnostic recipe when the retry STILL fails after 3 attempts:

1. Direct curl the endpoint with the same key: `curl -X POST https://api.minimax.io/v1/responses -H "Authorization: Bearer $KEY" -d '{"model":"MiniMax-M2.7","input":"hi","max_tokens":10}'`. If this returns "Service error", it's a true upstream outage, not a test issue — wait 30 minutes and rerun.
2. Check the existing `PumpStationMiniMaxLiveTest` test runs. If it ALSO fails with the same error, MiniMax is down for everyone. If it passes, the failure is specific to the new test — re-check request envelope (model name, temperature, top_p, top_k, system prompt shape).
3. If MiniMax is healthy for the existing test but rejects yours, the issue is in the request body shape. The most common gotcha: the existing test attaches `pcpContext` for tool schemas; tests that don't may hit a different code path that the upstream throttles more aggressively.

The retry fix was added to `PumpStationPostGoalLiveTest` in this session
and reduced false-failure rate from ~100% (6/6 failing) to ~0% on
transient-flake days. Add the same wrapper to any new live-mode test
that hits MiniMax, OpenRouter, Anthropic, or any other upstream that
returns 503 on transient overload.

### Pitfall 8: DSL `copyFrom` snapshot ordering — set `tracingConfiguration` BEFORE the first `path()`

Captured 2026-07-11 from the post-goal-hook live suite. The 12-test
suite ran for 22m 19s and reported `BUILD SUCCESSFUL` for 10/12 tests,
yet the trace directory `~/.tpipe/debug/trace/PumpStation/` was empty
for the failing two configurations. The pre-fix symptom was the
opposite: 6/6 failed with the trace HTML simply not existing at the
canonical path. Both symptom sets are caused by the same root.

**The bug**: the PumpStation DSL builder has a stage state machine.
`pumpStation("name") { block }` pushes a `PumpStationBuilder<Initial>`,
runs the block, then `pops` the final builder and calls `.build()` on
it. The first call to `path("name") { ... }` inside the block
**promotes** the builder to a new `PumpStationBuilder<Ready>` instance
via `copyFrom(this)` — a snapshot of the initial builder's mutable
state at the moment of the first `path()` call. Properties set on
the lambda's `this` BEFORE the first `path()` are in the snapshot;
properties set AFTER the first `path()` are on the initial builder
that gets discarded by the pop. The harness's `build()` method reads
from the promoted builder, not the initial one.

This is invisible in unit tests that don't read back the harness's
internal config. It only surfaces when the build() method reads a
property that was set on the wrong builder instance. The
`tracingConfiguration` setter is the most consequential: if it's
missed, `station.enableTracing(...)` is never called,
`traceConfig.autoExport` stays at the default `false`, and
`getTraceReport(HTML)` renders the report string but never writes
the file to disk.

**The wrong shape** (the post-goal hook's first version):

```kotlin
val station = pumpStation("feature-$testName") {
    postGoalAgent = postGoalAgentImpl
    postGoalFunction = { content, _ -> ... }
    eventObserver = { ev -> /* sink */ }

    // ↓ BUG: configurePaths() calls path("report") { ... } which triggers
    //   promote() and copyFrom() snapshots the initial builder. Anything
    //   set AFTER this point is on the discarded initial builder.
    configurePaths()  // <-- promote() fires here

    tracingConfiguration = traceCfg   // ← LOST: never reaches the harness
    systemTask = "..."
    userGuidelines = "..."
    maxHarnessTurns = 6
}
```

**The correct shape** (move tracingConfiguration above the first
`path()` call):

```kotlin
val station = pumpStation("feature-$testName") {
    postGoalAgent = postGoalAgentImpl
    postGoalFunction = { content, _ -> ... }
    eventObserver = { ev -> /* sink */ }

    // ↓ set ALL properties that survive into build() BEFORE the first path() call
    tracingConfiguration = traceCfg   // ← IN SNAPSHOT: enableTracing() runs
    systemTask = "..."
    userGuidelines = "..."
    maxHarnessTurns = 6

    // ↓ promote() fires here. Properties set above are in the snapshot;
    //   properties set below are LOST.
    configurePaths()
}
```

The rule generalizes: **any DSL property that survives into `build()` and
is read by the harness at runtime must be set BEFORE the first
`path()` call**. The list includes (at minimum):
- `tracingConfiguration` (controls `getTraceReport(HTML)` file output)
- `systemTask` (read by dispatch agent for path selection)
- `userGuidelines` (read by path executors)
- `maxHarnessTurns` (read by the loop guard)
- `judgeRunMode` (read by the judge phase)
- `memoryManagementMode` / `compactionThreshold` / `compactionStrategy` (read by the memory phase)
- `summaryAgent` (read by the compaction phase)
- `pathSafetyAgent` (read by the path-safety phase)

Properties that are read by the lambda's own path executors
(goal/dispatch/judge/path slots) can be set before OR after the
`path()` call because the path's `setInternalAgent` call runs
synchronously with the `path()` invocation, not deferred to `build()`.

**Diagnostic recipe when the trace file is missing but the test is green**:

1. Add a runtime reflection probe to dump the harness's internal
   `traceConfig` field AFTER the test:
   ```kotlin
   val traceCfgField = PumpStation::class.java.getDeclaredField("traceConfig")
   traceCfgField.isAccessible = true
   val cfg = traceCfgField.get(station) as? TraceConfig
   System.err.println("[DEBUG] autoExport=${cfg?.autoExport}, exportPath=${cfg?.exportPath}")
   ```
   If `autoExport=false` and `exportPath=~/.TPipe-Debug/traces/`, the
   snapshot bug is the cause — `enableTracing()` was never called
   because the `tracingConfiguration` setter on the initial builder
   happened after the `copyFrom` snapshot.

2. Compare against `PumpStationMiniMaxLiveTest.runResearchHarness`
   (line 1362-1364): the existing live test puts
   `tracingConfiguration = traceConfigFor(testName)` BEFORE the
   `registerResearchPaths` call which internally invokes `path()`. The
   Pitfall 8 fix is to match that order.

3. Move the assignment ABOVE the first `path()`-triggering call. The
   trace HTML lands at the configured path on the next run, no
   further changes needed.

**Variations on the same root cause**:
- A test that sets `summaryAgent = createAgentPipeline(...)` AFTER the
  first `path()` call will compile and run, but the compaction phase
  will use the harness's default `null` summary agent — the
  `summaryAgent` slot is read by the compaction phase from the
  promoted builder, not the initial one. Symptom: compaction runs
  but skips the summary step (no `PUMP_STATION_COMPACTION_COMPLETED`
  events in the trace).
- A test that sets `killSwitchConfiguration` AFTER the first `path()`
  call will not have the kill switch wired into any path's loop
  guard. The harness runs to completion even if the input token
  count exceeds the limit. Symptom: the kill-switch test never
  trips — the test "passes" with the wrong shape.
- A test that sets `systemTask` AFTER the first `path()` call will
  see the dispatch agent's path selection use the empty default
  string, not the test's actual system task. Symptom: dispatch
  selects the wrong path or falls through to a default that doesn't
  match the test's expectations, and the assertion fails on a
  misclassified stub response.

The pattern: **anything in `PumpStationBuilder` that maps to a
`private var` on `PumpStation` itself** (not a path/agent slot that
the `path()` call wires synchronously) must be set before
`configurePaths()`. The grep target to find these fields:

```bash
grep -n "private var " src/main/kotlin/Pipeline/PumpStation.kt
```

Every match is a "set before path()" candidate. Agent slots wired
through `addHarnessAgent` or `addHarnessAgentBuilder` are also
read by `build()` and follow the same rule.

**Verifying the fix**: after moving `tracingConfiguration = traceCfg`
above the `configurePaths()` call, the trace HTML lands at
`~/.tpipe/debug/trace/PumpStation/<testName>/pumpstation-<runId12>.html`
on the very next test run, and the
`assert(pumpHtmls.isNotEmpty() && pumpHtmls.all { it.length() > 5000 })`
assertion passes. No further code changes needed.

### Pitfall 9: Goal agents must flip `result.terminatePipeline` — text content is never inspected

Captured 2026-07-11 from the post-goal-hook live suite. The
`live_03_goalAgentFailsExhausted` test's first version set
`goalAgent = createAgentPipeline(...)` with a system prompt
instructing the LLM to "ALWAYS respond with 'GOALFAILED: not done'".
The live LLM produced exactly that text. The harness's
`runExitFlow` at `PumpStationLoop.kt:2408` reads:

```kotlin
val passed = !result.terminatePipeline
```

**The harness never inspects the text content of the goal agent's
response.** It only checks the `terminatePipeline` flag on the
returned `MultimodalContent`. Since the live LLM's response had
`terminatePipeline=false` (the default for `MultimodalContent`),
every goal-validation cycle counted as PASSED. The harness then
took the success path: judge never ran (skipped because the
goal-validation path took the success branch), the post-goal hook
fired, the harness exited with `JudgeComplete` instead of
`GoalValidationFailed`. Both assertions failed despite the test
wiring looking correct on the page.

The text-only "say GOALFAILED" prompt is a **trap**. The harness
code has no text-inspection logic for goal pass/fail; it relies
on the flag. A test that says "tell me in your response whether
the goal is met" is asking the LLM to perform a text-only
classification that the harness is structured to ignore.

**The fix** is the same wrapper pattern the stub-mode tests use
(`wrapPipelineAsFailingGoal` / `wrapPipelineAsPassingGoal` in
`PumpStationPostGoalLiveTest.kt:715-772` and `:747-772`): wrap a
real LLM pipe in a `P2PInterface` that calls the LLM (so the
live trace still captures the LLM invocation) and forces
`terminatePipeline=true` (or `false`) at the wrapper boundary,
deterministically:

```kotlin
private fun PumpStationBuilder<*>.liveGoalAgentThatFails()
{
    goalAgent = wrapPipelineAsLiveFailingGoal()
}

private fun wrapPipelineAsLiveFailingGoal(): P2PInterface
{
    val pipe = createMiniMaxPipe(
        "goal-fail-live",
        systemPrompt = "You are a goal-verification agent. Inspect the " +
            "conversation and ALWAYS respond with 'GOALFAILED: not done'."
    )
    val pipeline = Pipeline().apply { add(pipe) }
    runBlocking { pipeline.init(true) }
    return object : P2PInterface
    {
        override suspend fun executeLocal(content: MultimodalContent): MultimodalContent
        {
            val out = pipeline.executeLocal(content)
            return MultimodalContent(text = out.text).apply { terminatePipeline = true }
        }
        // ... remaining P2PInterface stubs
    }
}
```

The same pattern for `liveGoalAgentThatPasses()` flips
`terminatePipeline = false`. The LLM call is real (so the trace
HTML records it under `agent-goal.html`), the system prompt can
still be informative, but the flag is forced regardless of what
the LLM writes.

**Why this matters for the test class design**: the
`live_03` test's job is to verify the goal-failure-exhaustion
PATH in the harness, not to verify that an LLM can be tricked
into saying "GOALFAILED". The harness only knows the goal failed
because of the flag. Testing the path means forcing the flag, not
relying on text inspection that the harness doesn't perform.

**Diagnostic recipe when a goal-validation test "passes" despite
the goal agent supposedly failing**:

1. Dump the trace HTML's `PUMP_STATION_GOAL_VALIDATION_COMPLETED`
   events:
   ```bash
   grep -oE "PUMP_STATION_GOAL_VALIDATION_COMPLETED" \
     ~/.tpipe/debug/trace/PumpStation/<testName>/pumpstation-*.html | wc -l
   ```
   If this is 0, the goal agent was never invoked. If it is N
   (matching `maxGoalFailAttempts`), the agent WAS invoked but
   every call passed.

2. For each goal-validation event, check the `passed` metadata
   field:
   ```bash
   grep -A 3 "GOAL_VALIDATION_COMPLETED" \
     ~/.tpipe/debug/trace/PumpStation/<testName>/pumpstation-*.html | grep -E "passed"
   ```
   If every event shows `passed: true`, the goal agent's
   `terminatePipeline` flag was false (or unset) for every
   invocation. The text content is irrelevant — the harness only
   checks the flag.

3. Fix: wrap the goal agent in a P2PInterface that flips the flag
   at the wrapper boundary, per the pattern above. The
   `liveGoalAgentThatFails()` and `liveGoalAgentThatPasses()`
   helpers in `PumpStationPostGoalLiveTest.kt:688-781` are the
   canonical implementations.

**Generalization — the same flag-flip contract applies elsewhere
in the harness**:
- `pathInternalAgent` returning `terminatePipeline=true` causes
  the harness to halt with `TerminateSignal` (instead of
  `passPipeline=true` → `PassSignal`).
- `judgeAgent` returning `shouldTerminate=true` halts the
  harness regardless of the judge's textual verdict.
- `preInitAgent` and `pathSafetyAgent` also use flag-based
  pass/fail rather than text inspection.

The rule: any LLM-driven agent in the PumpStation harness that
controls a pass/fail/continue decision uses a flag on the
returned `MultimodalContent`, not the text. Tests that want to
exercise the fail/continue branch MUST flip the flag at the
wrapper boundary. A prompt that just tells the LLM to "say FAIL"
is structurally unable to drive the test.

**Verifying the fix**: after the wrapper is in place, the
trace HTML shows `PUMP_STATION_GOAL_VALIDATION_COMPLETED` events
with `passed: false` (for `liveGoalAgentThatFails()`) or
`passed: true` (for `liveGoalAgentThatPasses()`), the
goal-failure counter increments on each `passed: false` event,
and the harness exits with `GoalValidationFailed` after
`maxGoalFailAttempts` cycles. The test that was timing out
because the goal agent never failed will now complete in
1-2 minutes (3 goal cycles × ~20s per LLM call ≈ 60s + setup).

### Pitfall 10: Live tests gate is TWO env vars, not one — `TPIPE_LIVE_LLM_TEST=true` AND `MINIMAX_API_KEY`

Captured 2026-07-23 from the steering-feature verification session. The first run of `./gradlew :test --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest"` with only `MINIMAX_API_KEY` exported (the obvious reflex after Pitfall 4) reported `BUILD SUCCESSFUL in 3s` and JUnit XML showing `tests="13" skipped="0" failures="0" errors="0" time="0.048"` for the entire 13-test class — 48ms total wall time for 13 tests. Every test method showed `time="0.001"`. The agent initially declared "the live tests ran" based on the JUnit XML and the green status.

**Why the test looked green but did nothing**: `PumpStationMiniMaxLiveTest.setup()` at line 189-200 gates on BOTH env vars:

```kotlin
@BeforeAll
fun setup() {
    if (System.getenv("TPIPE_LIVE_LLM_TEST") != "true") return   // ← gate 1
    val key = System.getenv("MINIMAX_API_KEY")
    if (key.isNullOrBlank()) return                              // ← gate 2
    ...
}
```

When gate 1 fails, `apiKeyCache` stays `null`. Every test body then calls `if (liveGateOrSkip() == null) return@runBlocking` (line 879) — an early return that completes the test method in microseconds. The JUnit XML marks the test as "passed" because the method body returned without throwing. The harness never ran. No traces were written to `TPipeConfig.getTraceDir()`. The "0.001s per test" pattern is the receipt that the gate is closed.

**The recipe that actually runs the harness**:

```bash
export TPIPE_LIVE_LLM_TEST=true
export MINIMAX_API_KEY="$(grep '^export MINIMAX_API_KEY=' ~/.bashrc | head -1 | sed -E 's/^export MINIMAX_API_KEY="(.+)"$/\1/')"
./gradlew :test \
  --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest" \
  --rerun-tasks    # ← MANDATORY: without this, gradle serves cached UP-TO-DATE 0.001s results
```

`--rerun-tasks` is load-bearing because gradle's UP-TO-DATE cache for the `:test` task is keyed on (test name, source file mtime) — if the source hasn't changed and the task was already run with the gate closed, gradle serves the cached 0.001s results without re-executing. The `@BeforeAll setup()` is part of the test class lifecycle, not the gradle task cache, so the gate check is NOT re-evaluated on cached runs.

**Detection recipe** (the only signal that tells you the gate is closed):

| Signal | Live test ran | Live test was gated |
|---|---|---|
| Wall time per class | 30s-15min per class | <5s total |
| Per-method `time` attribute | 0.5s-90s | 0.001s (literal) |
| Trace files at `~/.tpipe/debug/trace/<class>/` | Present (1+ files per test) | Empty (0 files) |
| `getTraceReport(HTML)` content length | >5000 chars | <500 chars or empty |

If a "live" test class finishes in <5s total wall time AND every test has `time="0.001"`, the gate is closed. Real harness runs take 30-300s per test depending on the configuration (judge + dispatch + path + safety + memory round-trips).

**Stub mode detection** (related, separate failure mode): `liveGateOrSkip()` rejects keys starting with `sk-stub`:

```kotlin
private fun liveGateOrSkip(): String? = apiKeyCache?.takeUnless { it.startsWith("sk-stub") }
```

So even with `TPIPE_LIVE_LLM_TEST=true` set, a stub key silently skips the real-LLM tests. The stub_* tests (which use `envGateOrSkip()` and a `StubOpenAIServer`) run regardless because the stub key passes `envGateOrSkip()` but the harness routes to localhost. To verify BOTH stub and live paths in one run, the API key must be a real one (e.g., `sk-cp-...` from `~/.bashrc`).

**Why this pitfall is distinct from Pitfall 4**: Pitfall 4 is about sourcing the API key from `~/.bashrc` when `System.getenv("MINIMAX_API_KEY")` returns null. Pitfall 10 is about the SECOND gate that fires even when the key IS sourced — the `@BeforeAll setup()` early-returns on `TPIPE_LIVE_LLM_TEST != "true"` BEFORE checking the key. A test class that fixes Pitfall 4 (via `readKeyFromBashrc()`) but not Pitfall 10 still silently skips the live harness work. The two gates are both required.

**Generalization for future live-mode test classes**: any new `MyFeatureLiveTest` class following this 6-stub + 6-live matrix pattern will have the same two-gate architecture unless the author explicitly changes `@BeforeAll setup()`. The recipe must be propagated to every new live test class, and the `TPIPE_LIVE_LLM_TEST=true` env var must be set in the verification command. The gradle `:test` invocation should always include `--rerun-tasks` for the first run after a gate env var changes, to bypass the UP-TO-DATE cache.

## What the operator-graded pattern of failure looks like

The single-test shape (1 test, no trace capture, no stub-mode, no
multi-config) feels complete in a vacuum:
- It compiles.
- It runs.
- The harness emits events.
- The `eventObserver` lambda captures them.
- The test asserts on the captured events and passes.

But the operator's "did you make a live test" / "they should be there
unless you deleted them" question exposes the gap: the single test is
ONE configuration of ONE shape with a 1/12 coverage relative to the
canonical 12-test layout. The 11 missing configurations are silent
regressions waiting to happen (the post-goal hook could pass on
pass-pipeline but fail on flag-triggered judge, and the single test
wouldn't catch it).

The 12-test layout also catches stochastic-only failures: if the live
LLM produces malformed output on multi-path, the live-mode test
flanks-only tests catch it, but the stub-mode multi-path test catches
the same path deterministically, so the failure is reproducible.

## Trace HTML file name pattern

Every trace file written via `getTraceReport` is keyed by
`pumpstation-<runId12>.html` where `runId12` is the first 12 characters
of `taskState.runId` (a UUID generated per `executeLocal` call). Two
consecutive runs in the same test produce two distinct files (different
runId). The test's `assertRunProducedTracesWithFeature` filters the
subdir for `pumpstation-*$expectedRunIdPrefix*.html` so a stale file
from a prior run doesn't satisfy the assertion.

`traceConfigFor` deletes only `pumpstation-*.html` from the subdir before
each run. Per-agent HTML files (keyed by `pipeName`) are left alone —
the latest is always the most recent. See `PumpStationMiniMaxLiveTest.kt:570-585`.

## When NOT to use this pattern

- **Deterministic-only features** (e.g. a new DSL field, a new setter,
  a new type) — a unit test in `PumpStationSetGetTest` style is
  sufficient. The 12-test live suite is for features that depend on
  harness lifecycle events, DSL wiring, or trace capture.
- **Single-line event types** that don't need content checks — the
  `PumpStationEventTypeTest` exhaustive-priority test is sufficient.
- **Trace visualizer features** — those go in `Debug/PumpStationTraceVisualizationTest`
  or `Debug/PumpStationEventTypeTest`, not in a live harness suite.

The 12-test live suite is the right shape for: any new harness event
type, any new agent slot, any new DSL field that the harness
runtime reads, any new exit reason, any new flag in the eight magic
contracts (judge, dispatch, path, goal, path-safety, health, lorebook,
summary).

## Cross-References

- `references/loop-execution-and-goal-validation.md` — the state machine
  that Pitfall 1 (no-goal-agent bypass) hangs off of.
- `references/correct-behavior-reference.md` — the canonical correct
  behaviors that the 12 tests assert against.
- `references/harness-defect-catalog.md` — historical defects captured
  via the same 12-test pattern.
- `references/live-test-runbook.md` — the wall-clock budget per test,
  the recommended split (per-class rerun for fast iteration vs
  full-suite for pre-merge).
- `../../tpipe-trace-output-conventions/references/container-live-test-trace-recipe.md`
  — the trace-capture recipe (this skill is PumpStation-class; the
  `tpipe-trace-output-conventions` skill is container-class).
- `../../tpipe-trace-output-conventions/SKILL.md` — the canonical
  resolver rule, the "Green Test is Not Enough" rule, the
  `TraceConfig.exportPath` default-leak audit.

## Why This Was Added

Session 2026-07-10: the post-goal-hook feature rolled out a single live
test that the operator immediately flagged as "did you make a live test
that correctly tests the new feature?" The single-test shape failed
the operator's mental model of how a PumpStation live test should look
— the canonical pattern is `PumpStationMiniMaxLiveTest`'s 6 stub + 6
live configuration matrix. This reference captures that matrix as a
reusable template, plus the 9 pitfalls that the post-goal test
encountered on the way to the canonical 12-test layout. The next
PumpStation feature can clone this file, rename the fields, and ship
the suite in one session.

Updated 2026-07-11 to add Pitfall 7 (retry-on-503 around `executeLocal`)
after the live suite intermittently failed with `P2PException: OpenAI
Responses error: Service error. Please retry later` from MiniMax. The
existing `PumpStationMiniMaxLiveTest` has the same flakiness class —
the same wrapper applies there. Future PumpStation features that hit
LLM upstreams should copy the wrapper into their test's `runHarness`.

Updated 2026-07-11 to add Pitfall 8 (DSL `copyFrom` snapshot ordering)
and Pitfall 9 (goal agents must flip `terminatePipeline`, not
text-content). The post-goal-hook live suite is the canonical worked
example for both — its first version hit the snapshot bug (Pitfall
8) and the prompt-only goal-agent bug (Pitfall 9) before the wrapper
fix. The two pitfalls are independent root causes that BOTH must
be addressed in any new test class that uses the same harness shape.

Updated 2026-07-23 to add Pitfall 10 (live-tests gate is TWO env vars,
not one). The first run of the steering-feature verification cycle hit
the closed-gate trap: only `MINIMAX_API_KEY` was set, the
`@BeforeAll setup()` early-returned on `TPIPE_LIVE_LLM_TEST != "true"`,
and the entire test class finished in 48ms with `time="0.001"` on
every method. The JUnit XML was green but no harness work ran. The
recipe is the canonical fix; the "0.001s per test" pattern is the
failure signal that future live-mode test runs MUST check before
declaring green.