# TPipe Live Integration Test Patterns

A live integration test in TPipe is a `@Test`-annotated method that wires real pipes (Bedrock, OpenRouter, GenericOpenAI) into a real container (Pipeline, Manifold, Junction, PumpStation, DistributionGrid) and exercises it end-to-end against a real LLM endpoint. This reference captures the conventions and pitfalls surfaced by the existing test suite, so future containers (Junction? Splitter? MultiConnector?) and providers can ship a live test the same way.

## Two Variants of the Live-Test Pattern

The TPipe repo currently ships live tests in two distinct shapes. Pick the one that matches the cost-of-failure contract for your test.

### Variant A: Env-gate silent-skip (the right pattern for "happy path" tests)

Gated on a pair of env vars — `TPIPE_LIVE_LLM_TEST=true` AND a provider-specific key. If either is absent, every test method short-circuits at the gate and the test is reported as PASS. Developers without credentials never get a red bar.

**Canonical examples** (use as templates):

- `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/MiniMaxLiveTest.kt` (54 LOC, 1 test) — the simplest possible version.
- `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/ManifoldMiniMaxLiveTest.kt` (570 LOC, 4 tests) — the canonical "container × provider" live test.
- `src/test/kotlin/Pipeline/PumpStationMiniMaxLiveTest.kt` (1917 LOC, 6 real + 7 stub) — the heaviest version, with a `StubOpenAIServer` for offline runs.

**Pattern:**

```kotlin
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class <Container><Provider>LiveTest
{
    companion object
    {
        // Provider constants (base URL, model name, sampling)
        private const val <PROVIDER>_BASE_URL = "https://api.provider/v1"
        private const val <PROVIDER>_MODEL = "model-id"
    }

    /** API key cached after the env-gate. Null means "tests should silently skip". */
    private var apiKeyCache: String? = null

    @BeforeAll
    fun setup()
    {
        if (System.getenv("TPIPE_LIVE_LLM_TEST") != "true") return
        val key = System.getenv("<PROVIDER>_API_KEY")
        if (key.isNullOrBlank()) return
        GenericOpenAIEnv.setApiKey(key)
        apiKeyCache = key
    }

    @AfterAll
    fun teardown()
    {
        if (apiKeyCache != null) { GenericOpenAIEnv.clearApiKey(); apiKeyCache = null }
    }

    /** Silent-skip gate. Null = test no-ops (no failure). */
    private fun envGateOrSkip(): String? = apiKeyCache

    @Test
    fun <testName>() = runBlocking<Unit>
    {
        val key = envGateOrSkip() ?: return@runBlocking
        assert(key.isNotBlank()) { "<PROVIDER>_API_KEY must be set when TPIPE_LIVE_LLM_TEST=true" }
        // ... build the container, execute, assert
    }
}
```

Key points:

- `envGateOrSkip() ?: return@runBlocking` at the top of every test — the silent-skip mechanism.
- `runBlocking<Unit>` (with explicit `Unit` type parameter) — required when the last expression in the block is `Unit`-returning. Without it, the Kotlin parser fails to recognize the function expression. See the syntax gotcha below.
- `@TestInstance(Lifecycle.PER_CLASS)` so `@BeforeAll`/`@AfterAll` are non-static.
- Provider key in env + `GenericOpenAIEnv.setApiKey()` so child pipes can resolve via the env resolver.

### Variant B: Hard-assert (the legacy pattern, do NOT use for new tests)

`assertTrue(apiKey.isNotBlank(), "<PROVIDER>_API_KEY env var must be set")` at the top of the test. If the env var is absent, the test FAILS. This breaks the build for developers without credentials.

**One example still uses this pattern:** `MiniMaxLiveTest.kt:32`. It is a pre-existing condition; the fix is to convert it to Variant A. **Do not write new live tests in this shape.**

The discovery that surfaced this: a gradle run with both `MiniMaxLiveTest` and `ManifoldMiniMaxLiveTest` flagged one failure (`testMiniMaxLiveNonStreaming`) but not the other. The new test (Variant A) silently skipped; the legacy test (Variant B) hard-failed. If the new test had been Variant B too, the operator would have seen a red bar every time they ran the live test suite without a key.

## The Helper-Factory Pattern

When a test needs multiple pipe instances (e.g., a manager + a worker), use a private `create<Provider>Pipe` helper to avoid copy-paste boilerplate. The factory takes a `pipeName` and a system prompt, applies the provider's recommended sampling defaults, and returns a configured but not-yet-`init()`'d pipe:

```kotlin
private fun create<Provider>Pipe(
    pipeName: String,
    systemPrompt: String = "",
    baseUrl: String = <PROVIDER>_BASE_URL
): <Provider>Pipe
{
    val key = apiKeyCache ?: throw IllegalStateException("API key not loaded")
    return <Provider>Pipe()
        .setApiKey(key)
        .setApiMode(ApiMode.OpenAIResponses)  // or .OpenAI / .Anthropic
        .setBaseUrl(baseUrl)
        .also { p ->
            p.setPipeName(pipeName)
            p.setModel(<PROVIDER>_MODEL)
            if (systemPrompt.isNotEmpty()) p.setSystemPrompt(systemPrompt)
            p.setMaxTokens(MAX_TOKENS)
            p.setTemperature(TEMPERATURE)
            p.setTopP(TOP_P)
            p.setTopK(TOP_K)
        }
}
```

For pipes that need `.apply { ... }` configuration (JSON output, auto-truncate, dispatch-pipe naming), do the configuration at the call site, not in the factory. The factory returns a minimally-configured pipe; the caller adds the test-specific bits.

For MiniMax specifically, the recommended sampling is `temperature=1.0, top_p=0.95, top_k=40, max_output=128k` per the model card. For Manifold's binary dispatch decision (manager emits `AgentRequest` or `TaskProgress`), drop temperature to `0.1` so the manager doesn't waste tokens on creative dispatch prose — the decision is binary.

## The 4-Test Container Harness

Any TPipe container (Manifold, Junction, PumpStation, DistributionGrid) can be exercised by the same 4-test pattern. The pattern tests the container's primary safety systems plus a structural smoke test:

| # | Test | What it proves |
|---|------|----------------|
| 1 | **Happy path** (e.g. `manifoldsWithSingleWorkerExecutesTask`) | The container runs end-to-end with a real worker producing real output. Validates the dispatch protocol, the LLM-bound prompt, and the termination signal. |
| 2 | **Secondary safety: loop limit** (e.g. `manifoldsLoopLimitExceededAtMaxIterations`) | The secondary safety system trips at the configured iteration count. Catches regressions in `loopLimitCount`, `loopGuardTripped` plumbing, or the exit-reason funnel. |
| 3 | **Primary safety: kill switch** (e.g. `manifoldsKillSwitchTripsOnTokenLimit`) | The primary safety system trips on accumulated input/output tokens. Catches regressions in `killSwitchInputAccumulator`, `killSwitch.checkKillSwitch`, or the `KillSwitchException` re-throw invariant. |
| 4 | **HTML trace export** (e.g. `manifoldsWithSingleWorkerProducesHtmlTrace`) | The container's HTML trace export produces a non-empty file with the expected event anchors. Catches regressions in `getTraceReport`, the trace funnel, and the `TraceConfig.autoExport` path. |

Test 1's prompt should include a clear, low-ambiguity termination signal — e.g. "set `passPipeline` via the worker's response" — so the loop closes on the first iteration in most cases. Tests 2 and 3 need a forced no-progress loop ("never mark the task complete, always dispatch to the same worker"). Test 4 is the structural smoke and is the cheapest of the four.

## 5th Test: Remote-Worker Dispatch (when the container supports it)

When the container under test advertises workers via `P2PRegistry.listLocalAgents` (Manifold is the canonical example; Junction and DistributionGrid have the same pattern), add a 5th test that exercises the remote-dispatch path. The point: prove that a Manifold with an empty `workerPipelines` list can still complete a task by dispatching to a worker registered only in `P2PRegistry` with `allowExternalConnections = true`.

**Setup recipe:**

```kotlin
val remoteWorkerPipeline = createMiniMaxPipe(
    pipeName = "remote-echo-worker",
    systemPrompt = "You are remote-echo-worker. ...",
    baseUrl = MINIMAX_BASE_URL,
    pcpContext = null
)
val remoteWorkerTransport = P2PTransport().apply {
    transportMethod = Transport.Tpipe
    transportAddress = "remote-echo-worker@external"
}
val remoteWorkerDescriptor = P2PDescriptor().apply {
    agentName = "remote-echo-worker"
    description = "External worker reachable via P2PRegistry only"
}
val remoteWorkerRequirements = P2PRequirements().apply {
    allowExternalConnections = true
}
try {
    P2PRegistry.register(remoteWorkerPipeline, remoteWorkerTransport,
        remoteWorkerDescriptor, remoteWorkerRequirements)
    val manifold = manifold {
        // ... manager only, no worker { } block ...
    }
    manifold.init()
    manifold.execute(MultimodalContent(text = "echo: remote worker is live"))
    // ... assert trace HTML present, > 0 bytes ...
} finally {
    P2PRegistry.remove(remoteWorkerPipeline)
}
```

Three things this catches:

1. **The listing site is widened correctly.** The manager LLM must see `remote-echo-worker` in its prompt. If the container only feeds `listLocalAgents(this)`, the test fails because the manager picks a non-existent agent.
2. **The dispatch routes through `P2PRegistry.sendP2pRequest` correctly.** The local-by-name `Transport.Tpipe` lookup at `P2PRegistry.kt:1037-1058` must match the remote worker's transport.
3. **The validator / failure functions still fire** (or are intentionally skipped) for remote workers. If the container's `if(workerPipeline != null && ...)` guard short-circuits and the test had a validator bound, the test catches that pattern.

**P2PRegistry is a global singleton.** Always wrap `P2PRegistry.register` in `try { ... } finally { P2PRegistry.remove(pipeline) }` so a failing test doesn't leak the registration into sibling tests in the same JVM. Use a transport address with an `@external` suffix so collisions with anything else in the registry are unlikely.

**The 5th test is opt-in.** Don't add it to a container that doesn't advertise workers via P2PRegistry (Pipeline, Connector, Splitter). It's specifically for `P2PInterface` containers that build agent lists for a manager/moderator pipe.

## Trace Output Convention

Per `tpipe-trace-output-conventions`, the trace directory MUST resolve via `TPipeConfig.getTraceDir()`, never a hard-coded `~/.TPipe-Debug/...` literal. The live test's per-test convention:

```kotlin
val traceBaseDir = File("${TPipeConfig.getTraceDir()}/Library/<container>-<provider>-live/<test>")
traceBaseDir.mkdirs()
// ... build container with trace { config(traceConfig()) }
// ... after execute:
val htmlTrace = container.getTraceReport(TraceFormat.HTML)
val htmlTracePath = File(traceBaseDir, "<test>.html")
htmlTracePath.writeText(htmlTrace)
assert(htmlTracePath.exists()) { "HTML trace file should exist at ${htmlTracePath.absolutePath}" }
assert(htmlTracePath.length() > 0) { "HTML trace file should not be empty" }
```

The per-test subfolder (`<test>`) keeps multiple test runs from clobbering each other. `getTraceReport(TraceFormat.HTML)` returns the rendered string; `getTraceReport(TraceFormat.MARKDOWN)` is also available.

## Hermes Verification Evidence Workflow

The system applies a "verification status" gate to code-change turns. To get fresh passing evidence, write a focused temporary verification script under `/tmp/hermes-verify-<name>.sh` (OS-safe `tempfile` path with the `hermes-verify-` prefix), run it, and summarize it as AD-HOC verification, not suite green.

**What the script should check, in priority order:**

1. **File presence** — `[[ -f $REPO/$TEST ]]`
2. **Compile** — `./gradlew :<module>:compileTestKotlin -q` (no `--rerun-tasks`; let gradle cache)
3. **`@Test` method count** — `grep -cE '^\s*@Test\s*$' $TEST`
4. **Required symbol presence** — `grep -q "$sym" $TEST` for each DSL/API symbol the test must use
5. **Env-gate wiring** — every test has `envGateOrSkip() ?: return@runBlocking`; `BeforeAll` reads `TPIPE_LIVE_LLM_TEST` and the provider key
6. **Style check** — no `snake_case` identifiers (Apex convention; see AGENTS.md "No snake_case")
7. **Compiled class artifacts** — `find $CLASS_DIR -name "<TestClass>\$*.class" | wc -l` should be ≥ the number of `@Test` methods
8. **JUnit XML** — `<module>/build/test-results/test/TEST-<class>.xml` shows `tests=N, failures=0, errors=0`

**Gotcha: gradle daemon contention.** When a parallel `gradle test` invocation is running (a sibling agent or process), your gradle invocation will block behind it and the 300s terminal timeout will fire on the verification script. The fallback: drop step 2 from the script and rely on the existing `.class` artifacts in `build/classes/kotlin/test/` plus the JUnit XML from the previous run. The XML gets wiped by `--rerun-tasks`, so if the parallel run wiped it, the verification can only confirm (1)(3)(4)(5)(6)(7) — explicitly say so in the summary, do not claim suite green.

**Pattern: gradle-free verification when the daemon is busy.**

```bash
[[ -f $REPO/$CLASS_DIR/<TestClass>.class ]] && report PASS "class file present" || report FAIL
inner_count=$(find $REPO/$CLASS_DIR -name "<TestClass>\$*.class" 2>/dev/null | wc -l)
[[ "$inner_count" -ge $expected_tests ]] && report PASS "compiled inner classes" || report FAIL
```

## Syntax Gotcha: `fun foo() = runBlocking<Unit> { ... }`

When a test method's last expression is a `Unit`-returning `try/finally` or statement block (not a returnable value), the Kotlin parser requires `runBlocking<Unit>` with the explicit type parameter. Without it, the parser fails to recognize the function expression and emits a cascade of `Cannot infer type for type parameter 'T'` errors.

```kotlin
// WRONG — Cannot infer type for type parameter 'T'
@Test
fun myTest() = runBlocking
{
    val key = envGateOrSkip() ?: return@runBlocking
    // ...
}

// RIGHT — explicit Unit
@Test
fun myTest() = runBlocking<Unit>
{
    val key = envGateOrSkip() ?: return@runBlocking
    // ...
}
```

This is hit only when the function body ends with a `Unit`-returning call (like `try { ... } catch { ... }` or `println(...)` followed by other calls). When in doubt, use `runBlocking<Unit>` — it always compiles.

## JUnit XML as the Verdict of Record

**The JUnit XML is the authoritative verdict.** File: `<module>/build/test-results/test/TEST-<fully-qualified-class>.xml`. Each `<testcase>` element carries `name=...` and either an empty body (PASS) or a `<failure>` block (FAIL). The agent can read this directly:

```bash
report_xml="$REPO/<module>/build/test-results/test/TEST-<class>.xml"
tests=$(grep -oE 'tests="[0-9]+"' "$report_xml" | head -1 | grep -oE '[0-9]+')
failures=$(grep -cE '<failure' "$report_xml")
errors=$(grep -cE '<error' "$report_xml")
[[ "$tests" -eq 4 && "$failures" -eq 0 && "$errors" -eq 0 ]] && report PASS "all tests passed (silent-skip honored)"
```

Gradle's `FAILED` summary in console output is a subset of JUnit's coverage and can be confusing if stderr leaks — defer to the XML.

**The XML schema for a passing silent-skip test** is empty inside the `<testcase>` element with `time=N` populated, but the wall time is sub-second (the test returned at `envGateOrSkip() ?: return@runBlocking` without doing any LLM work). Stub tests are also sub-second. Live tests are 60-300s.

## Cleanup: Trace Directories Are NOT Cleaned

The container's trace export writes a fresh subfolder per test run but does NOT clean prior folders. Old trace directories from prior sessions accumulate in `${TPipeConfig.getTraceDir()}/Library/<container>-<provider>-live/`. Wipe the per-test subfolder before a clean run, or accept that the runId-prefix check may match a prior run.

## Anti-Pattern: `MiniMaxLiveTest`'s `assertTrue(apiKey.isNotBlank())`

`MiniMaxLiveTest.kt:32` still has the hard-assert pattern. It's a pre-existing condition from before the env-gate convention landed. When writing a new live test, use Variant A. If you need to run `MiniMaxLiveTest` in a CI environment without `MINIMAX_API_KEY`, convert it to Variant A first or scope the gradle run to skip it (`--tests "genericOpenAIPipe.MiniMaxLiveTest" --exclude-task` or use `-Dtest.exclude`).

## Cross-Reference: `tpipe-generic-openai/references/live-test-verification.md`

That reference (in the `tpipe-generic-openai` skill) covers the **other half** of the live-test problem: how to *verify* a live test is real, not canned. Symptoms: empty `outputTokens`, missing `responseId`, no TCP capture. Use that reference when a user asks "is this test actually calling the API or is it returning canned data?" — it's the verification-of-the-verification, not how to author a new live test.
