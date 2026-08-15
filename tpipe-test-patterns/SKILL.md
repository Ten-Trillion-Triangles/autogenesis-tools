---
name: tpipe-test-patterns
description: "TPipe-specific TDD patterns: P2PInterface test doubles, suspend-call-chain threading, runBlocking anti-pattern, container harness test construction, per-class test sweep runner with HTTP env gate, and live-test rerun recipe. Load when writing tests for Junction, Manifold, DistributionGrid, Pipeline, or any TPipe container that calls executeLocal on a P2PInterface agent."
version: 1.5.0
author: Hermes Agent
license: MIT
created: 2026-07-14
version: 1.6.0
changelog: >
  1.7.0 (2026-07-30): Added Section 5.4.1 "Live-Test Wall-Time Fingerprint — `time` Attribute is the Bug-Class Diagnostic" — the JUnit XML `time` attribute is the precise signal for "did the test run the real wire?" Captured from a 3-test streaming-callback live sequence where two failures looked identical but were two different bugs: real-wire-but-wrong-parser (`time=0.4+`) vs dispatcher-short-circuit (`time=0.004`). The wall-time matrix (0.001 / 0.004–0.020 / 0.1–2 / 2–200) is the diagnostic that disambiguates. Includes the AWS Legacy-model swap procedure (catalog probe via `aws bedrock list-foundation-models` → swap to `amazon.nova-lite-v1:0`) and the production-debug print pattern using `/tmp/*-debug-${System.currentTimeMillis()}.log` files when gradle's stdout is truncated for background invocations.
  1.6.0 (2026-07-30): Added Sections 5.4–5.8 covering four new streaming-callback test patterns: (5.4) Bedrock Legacy model deprecation blocking live test assertions — Haiku must be replaced with a current model; (5.5) `setStreamingCallback` overload ambiguity when bare lambda returns `Boolean` — explicit type annotation required; (5.6) JUnit 5 `@BeforeTest` does not exist — correct is `@BeforeAll`/`@BeforeEach`, wrong annotation blocks all module test compilation; (5.7) `GenericOpenAIPipe` now exposes `streamingCallbacks { add }` DSL and `enableStreaming(callback)` — both register via `obtainStreamingCallbackManager().addCallback` + `propagateStreamingCallback`; (5.8) `testStreamingCallbacksConcurrentModeFansOutInParallel` deadlocks with `CompletableDeferred` gate — `emitToAll` in concurrent mode runs callbacks sequentially from a single coroutine, so `gate.await()` blocks forever; use `CountDownLatch` instead.
  1.5.0 (2026-07-27): Added Section 8 "The 3-Run Empirical Triage Pattern for Flaky Tests"
  — the canonical recipe for distinguishing TIMEOUT+deterministic-failure from
  pre-existing-on-every-version when source-read cannot pin the cause. Adds the
  per-class debug writeText to /tmp/<class>-debug-${System.currentTimeMillis()}.log
  pattern for identifying which assertion fails when the message is generic
  ("Expected value to be true."). Captures three TPipe-specific root-cause patterns
  discovered during the 2.3.21 C-bucket fix pass: (a) setSkipJudgeOnFirstTurn(false)
  is required before runJudgePhase() is called directly because the default skips on
  turn 0; (b) shapeOutboundEnvelopeForPeer replaces envelope.content.context with a
  fresh contextWindow from text only, dropping any pre-populated contextElements;
  (c) getDeclaredField does not walk inheritance — the declaring class is the parent.
  Adds an updated reference recipe with 3-run + debug capture. Also captures the
  user's persistent correction "Investigate why each test fails, do not skip
  pre-existing flakes because TIMEOUT sometimes hides them — when not timing out,
  the same test fails deterministically and that failure is the real signal."
  1.4.0 (2026-07-27): Added Section 6 "Per-Class Test Sweep Runner" — the canonical
  shell harness for running every TPipe test class individually, capturing per-class
  pass/fail, and triaging Kotlin upgrade regressions. Adds the
  TPIPE_ALLOW_INSECURE_BASEURL=true env gate (Section 4 cross-ref) that local-HTTP
  tests require. Confirms the Section 2.5 suspend-reflection prediction hit
  DistributionGridHardeningTest.remoteHandoffBuildsOutboundMemoryEnvelope in the
  live 2.3.21 sweep.
  1.3.0 (2026-07-23): Added Section 4 "TPipe Container Live Tests — MiniMax Rerun +
  Trace Parsing Pattern" — the canonical recipe for running *LiveTest.kt classes
  with the TPIPE_LIVE_LLM_TEST=true gate + MINIMAX_API_KEY from ~/.bashrc, per-class
  rerun for stochastic LLM noise (5-10x speedup over full-suite reruns), trace
  parsing via parse_pumpstation_html.py --input <path>, and failure-class
  disambiguation (upstream noise vs MaxTurnsExceeded test budget vs gate-closed
  early-skip). Captured from the steering-feature session's 6-test live sequence
  (5 pass, 1 MaxTurnsExceeded).
  1.2.0 (2026-07-23): Added Section 3.5 "PumpStation Minimal Construction Pattern for
  Feature Tests" — the canonical harness shape (dispatchAgent = Pipeline() +
  path("noop") { setExecutionFunction { ... } }) for testing new PumpStation DSL
  blocks + runtime APIs without spinning up an LLM. Captured from the
  steering-feature session's 18-test harness reuse.
  1.1.2 (2026-07-19): Skill hygiene pass — converted LLM-ism drift (Convert 'The fix
  was' to **Fix:**) to instruction-form. The YAML changelog block remains the single
  source of truth for version history.
  1.1.1 (2026-07-19): Skill hygiene pass — removed 1 drift markers (inline dates,
  past-tense narrative, verbatim user prompts). The YAML changelog block remains
  the single source of truth for version history.
  1.1.0 (2026-07-14): distributiongrid confirmation + containerObject-tracking
  requirement on test doubles; suspend-reflection pitfall with internal fix;
  DistributionGrid DSL ordering constraint (summaryAgent must apply AFTER
  setMemoryPolicy)
  1.0.0 (2026-07-14): initial — P2PInterface test doubles, suspend threading,
  runBlocking anti-pattern
---
# TPipe Test Patterns

TDD patterns specific to TPipe containers and the Kotlin coroutine execution model. For general TDD discipline, use `test-driven-development`. This skill covers TPipe-specific traps.

## 1. P2PInterface Test Doubles — Complete Interface Wiring

When testing TPipe containers (Junction, Manifold, DistributionGrid, Pipeline) that call `executeLocal` on a `P2PInterface` agent, a test double must implement the full interface. Incomplete stubs silently accept the call but return wrong types, causing hard-to-debug downstream failures.

### The complete test double

```kotlin
private class RecordingAgent(var outputText: String = "agent output") : P2PInterface {
    var invokeCount = 0
        private set
    var lastLocalInput: MultimodalContent? = null
        private set

    private var descriptor: P2PDescriptor? = null
    private var requirements: P2PRequirements? = null
    private var transport: P2PTransport? = null
    private var containerObject: Any? = null   // MUST track — see "containerObject trap" below
    override var killSwitch: KillSwitch? = null

    // === P2PInterface contract ===
    override fun setP2pDescription(description: P2PDescriptor) { descriptor = description }
    override fun getP2pDescription(): P2PDescriptor? = descriptor
    override fun setP2pTransport(transport: P2PTransport) { this.transport = transport }
    override fun getP2pTransport(): P2PTransport? = transport
    override fun setP2pRequirements(requirements: P2PRequirements) { this.requirements = requirements }
    override fun getP2pRequirements(): P2PRequirements? = requirements
    override fun getContainerObject(): Any? = containerObject
    override fun setContainerObject(container: Any) { containerObject = container }
    override fun setParentInterface(parent: P2PInterface) {}
    override fun getParentP2PInterface(): P2PInterface? = null
    override fun getPipelinesFromInterface(): List<Pipeline> = listOf()
    override fun getPaths(): String = ""
    override fun setTokenBudgetRecursive(budget: TokenBudgetSettings) {}
    override fun getTokenBudgetSettings(): TokenBudgetSettings? = null
    override fun setPipeSettingsRecursively(settings: PipeSettings) {}
    override suspend fun P2PInit() {}

    override suspend fun executeLocal(content: MultimodalContent): MultimodalContent {
        invokeCount++
        lastLocalInput = content
        return MultimodalContent(text = outputText)
    }

    override suspend fun executeP2PRequest(request: P2PRequest): P2PResponse? {
        invokeCount++
        lastLocalInput = request.prompt
        return P2PResponse(output = MultimodalContent(text = outputText))
    }

    init {
        descriptor = P2PDescriptor(
            agentName = "RecordingAgent",
            agentDescription = "Test double that records invocations",
            transport = P2PTransport(
                transportMethod = Transport.Tpipe,
                transportAddress = "test-recording-agent"
            ),
            requiresAuth = false,
            usesConverse = true,
            allowsAgentDuplication = false,
            allowsCustomContext = false,
            allowsCustomAgentJson = false,
            recordsInteractionContext = false,
            recordsPromptContent = false,
            allowsExternalContext = false,
            contextProtocol = com.TTT.P2P.ContextProtocol.none
        )
        requirements = P2PRequirements(
            allowExternalConnections = true,
            allowAgentDuplication = false,
            allowCustomContext = false,
            allowCustomJson = false
        )
    }
}
```

### Four errors that break test doubles

1. **Forgetting `P2PRequirements`** — TPipe's `addParticipant` / `setSummaryAgent` calls `setP2pRequirements` on the passed agent; a stub that doesn't store it causes NPE at the call site.

2. **Forgetting `allowsCustomContext` / `allowsCustomAgentJson` / `recordsInteractionContext` / `recordsPromptContent` / `allowsExternalContext` / `contextProtocol`** — `P2PDescriptor` has no defaults; all fields are required positional args at construction time.

3. **Missing `override` on `killSwitch`** — `killSwitch` on `P2PInterface` is `abstract var` (not `var` with default), so omitting `override` silently creates a separate property that P2PInterface methods never read.

4. **`containerObject` no-op stub** — see "containerObject trap" below.

### containerObject trap: must track, not default to `{}`

`P2PInterface.getContainerObject()` defaults to `null` and `setContainerObject` defaults to `{}`. A naive test double that doesn't override them (or overrides them as no-ops) breaks silently when the production container's `init()` walks the binding chain and calls `validateLocalOwnership(...)`.

**DistributionGrid's `init()`** at `DistributionGrid.kt:1715-1724`:

```kotlin
private fun validateLocalOwnership(label: String, binding: DistributionGridBinding) {
    val owner = binding.component.getContainerObject()
    require(owner === this) {
        "DistributionGrid requires $label to remain bound to this grid before init(). " +
            "Current owner: ${describeContainer(owner)}"
    }
}
```

If the stub doesn't track the container reference, `getContainerObject()` returns `null`, and `init()` throws `IllegalArgumentException: DistributionGrid requires router to remain bound to this grid before init(). Current owner: null`. The DSL test path (which calls `init()` after `buildInternal()`) is the one that surfaces this — direct manual `setRouter(stub)` tests don't trigger `init()`, so they pass even with the bug.

**Fix:** in the test double, store the container in a field and override both getters/setters to track it:

```kotlin
private var containerObject: Any? = null
override fun getContainerObject(): Any? = containerObject
override fun setContainerObject(container: Any) { containerObject = container }
```

This isn't optional when a test instantiates the container via its DSL (`distributionGrid { router(stub) }`) and then calls `init()` or any operation that walks the binding chain.

### `runBlocking` vs `suspend` in test doubles

When production code calls `executeLocal` directly (not via `runBlocking`), the test double's `executeLocal` must be `suspend`. If it's a non-suspend `fun`, the call from a `suspend` production site compiles but may call the wrong overload or throw at runtime. Always match the interface: `override suspend fun executeLocal`.

## 2. Suspend Threading — Never Bridge with `runBlocking`

When adding an agent-calling path to any TPipe container (e.g. `summaryAgent`, `lorebookAgent`), trace the full call chain from `execute` to `executeLocal`. All intermediate functions must be `suspend`. If any is `private fun`, change it to `private suspend fun`.

**The rule:** thread `suspend` through the full call chain rather than bridging with `runBlocking`.

### Junction example — the full chain for `buildSummaryText`

```
execute(content: MultimodalContent)          — suspend fun
  → executeWorkflow(content)                 — private suspend fun
    → runParticipantRound(...)              — private suspend fun
      → dispatchParticipant(...)            — private suspend fun
        → buildParticipantRequest(...)      — private fun → change to private suspend fun
          → buildParticipantMemoryEnvelope(…) — private fun → change to private suspend fun
            → budgetEnvelope(...)           — private fun → change to private suspend fun
              → buildSummaryText(...)      — private fun → change to private suspend fun
                → executeLocal(agentInput)  — direct suspend call (no runBlocking)
```

**Why `runBlocking` is always wrong here:** `runParticipantRound` uses `async { dispatchParticipant(...) }` inside `coroutineScope`. The threads are coroutine dispatchers. `runBlocking` blocks the dispatcher thread until `executeLocal` completes, preventing it from handling other coroutines concurrently — negating the entire fan-out benefit of the `async { }` calls.

**Reference case:** `Junction.kt buildSummaryText` (2026-07-14) — originally used `runBlocking { executeLocal(...) }` inside a non-suspend function called from `async { }`. Fixed by threading `suspend` through all 7 intermediate functions (7× `private fun` → `private suspend fun`).

## 2.5 Suspend Reflection Pitfall — Use `internal`, not `private`

This is the trap that bites whenever you add `suspend` to a previously non-suspend `private fun`. The Kotlin compiler emits a JVM signature that **appends a `Continuation` parameter** to the function. Any existing test that calls the function via Java reflection (`Method.invoke(...)` with the old argument list) breaks with `NoSuchMethodException` against the JVM signature, even though the source-level function declaration looks reasonable.

Verify with `javap`:

```bash
$ javap -p build/classes/kotlin/main/com/TTT/Pipeline/<Class>.class | grep <methodName>
private final java.lang.Object <methodName>(
    <String>, int, com.TTT.Pipe.TruncationSettings,
    java.lang.String, java.lang.String, java.lang.String,
    kotlin.coroutines.Continuation<? super java.lang.String>   # <-- appended by suspend
);
```

### Why this matters when refactoring `private` → `suspend`

When you thread `suspend` through a call chain (Section 2), any pre-existing test that uses `Method.invoke(...)` against a now-`suspend` function will fail at runtime. The error message is `NoSuchMethodException: com.TTT.Pipeline.<Class>.<methodName>(<old args>)` — not a code-level compile error — so it slips past grep-based regression scans.

Reference case: when `DistributionGrid.buildSummaryText` was promoted from `private fun buildSummaryText(summarySeed: String, summaryBudget: Int, settings: TruncationSettings): String` to `private suspend fun buildSummaryText(summarySeed: String, summaryBudget: Int, settings: TruncationSettings, taskId: String, currentNodeId: String, targetNodeId: String): String`, the existing `DistributionGridHardeningTest.remoteHandoffBuildsOutboundMemoryEnvelope()` test — which called `buildOutboundMemoryEnvelope(...)` via `Method.invoke(...)` with the old 2-argument signature — started throwing `NoSuchMethodException: ... DistributionGrid.buildOutboundMemoryEnvelope(DistributionGridEnvelope, P2PDescriptor)`.

### Two fixes — pick the right one per context

**Fix A (preferred when the test is in the same module):** mark the function `internal suspend` instead of `private suspend`. Same-module tests in the same package can then call the function directly from Kotlin with `runBlocking { container.methodName(...) }` — no reflection, no JVM signature traps.

```kotlin
// Before (breaks reflection):
private suspend fun buildOutboundMemoryEnvelope(envelope: DistributionGridEnvelope, descriptor: P2PDescriptor): DistributionGridMemoryEnvelope

// After (callable directly from tests):
internal suspend fun buildOutboundMemoryEnvelope(envelope: DistributionGridEnvelope, descriptor: P2PDescriptor): DistributionGridMemoryEnvelope
```

```kotlin
// Test side:
val result = kotlinx.coroutines.runBlocking {
    senderGrid.buildOutboundMemoryEnvelope(testEnvelope, testDescriptor)
}
```

**Fix B (only when external/test cannot share package):** keep `private` and add the `Continuation` param to the reflection lookup. Brittle — the reflection helper must know about the synthetic Continuation, and any `IntrinsicsKt.getCOROUTINE_SUSPENDED()` machinery is fragile under test-classpath changes. Avoid if you can use Fix A.

For the canonical Container test path (`XxxHardeningTest.kt` style, same package), **always use Fix A**.

## 3. TDD for Container Memory Policy DSL — Targeted Mutation Pattern

When adding a `P2PInterface` agent slot to a container's memory policy, the DSL method must not call `memoryPolicy { this.newField = x }` — that creates a fresh policy object and replaces whatever the user configured earlier in the same builder block.

The rule applies to **every** TPipe container with a memory policy: `Junction`, `DistributionGrid`, and any future container that follows the same shape. Both Junction and DistributionGrid got bitten by this in the same session (2026-07-14).

### Wrong pattern (silently destroys existing policy state)

```kotlin
fun summaryAgent(agent: P2PInterface): JunctionBuilder<S> {
    junction.memoryPolicy {
        this.summaryAgent = agent  // creates NEW JunctionMemoryPolicy(), overwrites existing
    }
    return this
}
```

### Correct pattern (targeted mutation)

```kotlin
// Junction exposes:
fun setSummaryAgent(agent: P2PInterface?): Junction {
    junctionMemoryPolicy.summaryAgent = agent  // mutates in place
    return this
}

// DSL method:
fun summaryAgent(agent: P2PInterface): JunctionBuilder<S> {
    junction.setSummaryAgent(agent)  // preserves existing memoryPolicy fields
    return this
}
```

### Why the bug is silent

`JunctionMemoryPolicy` (and `DistributionGridMemoryPolicy`) is a data class with all-default fields. `memoryPolicy { }` creates a new instance with defaults (including `enableSummarization = false`). When `summaryAgent(agent)` was called after `memoryPolicy { enableSummarization = true }`, the new policy reset `enableSummarization` to `false`. The test failed with `invokeCount == 0` — never invoked because summarization was silently disabled.

### Reference case (Junction)

`JunctionSummaryAgentTest.kt` (2026-07-14) — `summaryAgent(agent)` was calling `memoryPolicy { this.summaryAgent = agent }`. Fixed by adding `Junction.setSummaryAgent(P2PInterface?)` and calling that instead.

### Reference case (DistributionGrid) — additional DSL ordering constraint

`DistributionGridSummaryAgentTest.kt` (2026-07-14) — same fix. But `DistributionGrid`'s DSL has a stricter ordering requirement than Junction because its `configureGridInternal()` ALREADY calls `setMemoryPolicy(policy.copy())` to apply the user's `memory { ... }` block during `build()`. If the top-level `summaryAgent(agent)` DSL method just stored a setter invocation into the same builder, the order would be:

1. (during build) `setMemoryPolicy(policyWithSummaryAgent = null)` — full replacement
2. (during build) `setSummaryAgent(myAgent)` — mutates current policy, but step 1 already wiped earlier fields

Two issues would result: (a) the `summaryAgent(agent)` field would be set on a brand-new policy with defaults other than `summaryAgent`, silently losing any earlier `enableSummarization = true` setting; (b) `setMemoryPolicy` followed by `setSummaryAgent` is the wrong order for a targeted mutation.

**DistributionGrid's fix (in `DistributionGridBuilder.configureGridInternal()`):**

```kotlin
// Apply the user's memory block first (this remains the existing pattern)
memoryConfiguration?.let { grid.setMemoryPolicy(it.copy()) }
// THEN apply the summary agent via the targeted mutator, AFTER the policy replacement.
// This route preserves all memory block fields — including enableSummarization, summaryBudget, etc.
summaryAgentConfiguration?.let { grid.setSummaryAgent(it) }
```

The `DistributionGridBuilder` carries a separate `summaryAgentConfiguration: P2PInterface?` field (parallel to `memoryConfiguration: DistributionGridMemoryPolicy?`). The DSL method `summaryAgent(agent)` writes to this field, not to the memory policy directly. At `build()` time, the two configuration paths are applied in the order above. The user-visible behavior — `memory { enableSummarization(true) }` followed by `summaryAgent(myAgent)` preserves both — is preserved across both containers via the same targeted-mutation discipline.

## 3.5 PumpStation Minimal Construction Pattern for Feature Tests (added 2026-07-23)

When testing a NEW PumpStation feature end-to-end without spinning up a real LLM, the test harness needs a `pumpStation { }` block that:

1. Satisfies `build()`'s `require(dispatchAgent != null) { "dispatchAgent is required" }` and `require(dispatchAgent is Pipeline) { "dispatchAgent must be a Pipeline" }` (validated at `PumpStationDsl.kt:1095-1096`)
2. Has at least one `path { }` so `require(pathObjects.isNotEmpty()) { "At least one path is required" }` passes
3. Sets the `setExecutionFunction` on the path to a no-op that returns the content unchanged
4. Calls the feature's DSL block under test

### The minimal harness

```kotlin
private fun buildMinimalStation(featureBlock: PumpStationBuilder<*>.() -> Unit = {}): PumpStation {
    return pumpStation("test-station-${System.nanoTime()}") {
        dispatchAgent = Pipeline()                                          // satisfies build()'s dispatchAgent requirement
        path("noop") {                                                     // satisfies build()'s pathObjects.isNotEmpty()
            setExecutionFunction { content, _, _, _ -> content }             // no-op path that returns content unchanged
        }
        featureBlock()                                                     // the feature under test
    }
}
```

Then each test follows the shape:

```kotlin
@Test
fun `feature X works`() = runTest {
    val station = buildMinimalStation {
        steeringPolicy {                                                   // the new DSL block being tested
            persistentOverlay(PumpStationPausePhase.BeforeJudge, "msg")
        }
    }
    // assert against station.steeringService.drainForPhase(...)
}
```

### Three failure modes to recognize

**(a) `dispatchAgent` not set → `IllegalArgumentException: dispatchAgent is required` at `PumpStationDsl.kt:1095`.** The fix is the line `dispatchAgent = Pipeline()` at the top of the lambda. A bare `Pipeline()` works because Pipeline is a class with no required constructor args (`src/main/kotlin/Pipeline/Pipeline.kt:43`).

**(b) `path { }` missing → `IllegalArgumentException: At least one path is required` at `PumpStationDsl.kt:1097`.** The fix is the `path("noop") { setExecutionFunction { content, _, _, _ -> content } }` block. The `setExecutionFunction` is on `PathBlock`, not on `PumpStationBuilder` — search `path { }` definitions for the right overload (it's at `PumpStationDsl.kt:1587`).

**(c) `setExecutionFunction` lambda parameter count wrong → `Type mismatch`.** The signature is `(content: MultimodalContent, stationRef: PumpStation, turnHistory: ConverseHistory?, turnSummary: String) -> MultimodalContent`. The no-op shorthand `{ content, _, _, _ -> content }` discards the three trailing params. If a future iteration of the path DSL changes the signature, update the lambda to match — the existing 4-arg pattern is verified in `PumpStationSteeringRuntimeTest.kt`.

### Why this pattern is reusable

The shape generalizes to ANY PumpStation feature that exposes a DSL block + runtime API + drain helper. The same minimal harness applies whether the feature is `steeringPolicy { }` (today), `retryPolicy { }` (future), `personalityOverride { }` (future), or `phaseOverlay { }` (future). The feature-block parameter is the only variation.

**Reference case:** `src/test/kotlin/Pipeline/PumpStationSteeringRuntimeTest.kt` (2026-07-23) — 12 tests, all green, all using this exact harness shape. Same pattern is in `PumpStationSteeringDslTest.kt` (6 tests) — 18 tests total use this harness across the two files.

### When this pattern is NOT sufficient

- Tests that exercise the FULL harness loop (judge agent, dispatch agent, path execution chain) need `PumpStationMiniMaxLiveTest`-style architecture with real agents. See `pump-station/SKILL.md` "Live + stub test suite architecture" for the 6 stub + 6 live matrix.
- Tests that exercise the harness loop WITHOUT a real LLM but WITH `runHarnessLoop` need a fake `judgeAgent` that returns `terminatePipeline=true` (the harness only checks the flag, never the text — `pump-station/SKILL.md` Pitfall 9).
- Tests that exercise the persistence/durability stack need `PipeTracer.exportTrace` setup. See `pump-station/SKILL.md` TraceServer dispatch section.

For the 90% case of "I just added a new DSL block + runtime method + drain helper to PumpStation, I want regression tests that exercise the surface without LLMs," this minimal pattern is the right tool.

## 4. TPipe Container Live Tests — MiniMax Rerun + Trace Parsing Pattern

TPipe container live tests (`*LiveTest.kt` classes like `PumpStationMiniMaxLiveTest`, `PumpStationSafePruneLiveTest`, `PumpStationTPipeConfigTraceLiveTest`) require a real LLM endpoint to exercise the full harness loop. They are gated by environment variables and produce `pumpstation-*.html` trace artifacts under `TPipeConfig.getTraceDir()`. This section captures the canonical recipe for running them, recovering from stochastic LLM noise, and parsing the traces.

### Why live tests need a different workflow than unit/in-process tests

Live tests hit a real LLM (default: MiniMax via `GenericOpenAIEnv`). Each test takes 1–10 minutes. The LLM response is stochastic — the same prompt may produce a different verdict on different runs. A test that "failed because the judge LLM returned a malformed JSON" on one run may pass cleanly on the next run with no code changes. The user-visible signal is P2PException wrapping an OpenAI service error (e.g. `OpenAI Responses error: Service error. Please retry later`) or a test assertion that fires because the LLM produced a valid-but-different verdict.

**The rule:** do not treat a single live-test failure as a code regression. Per-class reruns are the proven recovery pattern. Full-suite reruns are wasteful — one failure per class is the typical mode, and rerunning only the failing class is 5–10× cheaper.

### The recipe (8 numbered steps)

1. **Extract the API key from `~/.bashrc`** — the canonical line is:
   ```bash
   KEY=$(grep "MINIMAX_API_KEY" ~/.bashrc | head -1 | sed -E 's/^export MINIMAX_API_KEY="(.+)"$/\1/')
   ```
   Verify with `${#KEY}` — should be ~125 chars. The `source ~/.bashrc` approach does NOT work in a subshell; the sed extraction is the reliable path.

2. **Set BOTH env vars** before invoking gradle:
   ```bash
   export MINIMAX_API_KEY="$KEY"
   export TPIPE_LIVE_LLM_TEST="true"
   ```
   Without `TPIPE_LIVE_LLM_TEST=true`, the `@BeforeAll setup()` at `PumpStationMiniMaxLiveTest.kt:189-200` returns early and `apiKeyCache` stays null. The test body's `liveGateOrSkip() == null` early-return then triggers, and every test reports `0.001s` wall time (the early-return path). This is the most common mistake: "the test passed in 0.001s, did it actually run?" — answer: no, it skipped because the gate was closed.

3. **Run one test class at a time, in sequence.** Per-class reruns are 5–10 min each; a full live-test suite is 40+ min and risks hitting the foreground timeout cap (600s). Use `terminal(background=true, notify_on_complete=true)` for any run over 2 min.

4. **Use `--rerun-tasks`** to force re-execution when the previous run hit the early-skip path or produced cached results.

5. **The two gate functions in the test class:**
   - `envGateOrSkip(): String?` — returns the API key if `TPIPE_LIVE_LLM_TEST=true` AND `MINIMAX_API_KEY` is set. Used by `stub_*` tests (which use `StubOpenAIServer`, a local mock).
   - `liveGateOrSkip(): String?` — stricter; returns null when the key starts with `"sk-stub"` so the live tests skip in stub mode (they would otherwise hit the real MiniMax endpoint with the stub key and fail with `1004 login fail` P2PException).
   - If you see `time="0.001s"` on a `*_researchSucceeds` test, the gate was closed. Fix env vars, not code.

6. **Trace artifacts land under `TPipeConfig.getTraceDir()`** which resolves to `~/.tpipe/debug/trace/` by default. The harness writes a per-test subdirectory: `~/.tpipe/debug/trace/PumpStation/<testName>/pumpstation-ps-<id>.html` for MiniMax tests, or `~/.tpipe/debug/trace/<testName>/pumpstation-ps-<id>.html` for TPipeConfigTrace tests.

7. **Parse each trace with `parse_pumpstation_html.py`:**
   ```bash
   python3 ~/.hermes/skills/software-development/tpipe-trace-parser/scripts/parse_pumpstation_html.py \
     --input ~/.tpipe/debug/trace/PumpStation/01-always-on-judge/pumpstation-ps-178483687.html \
     --quiet
   ```
   The script takes `--input <path>`, NOT a positional arg. Returns JSON with `path`, `run_status`, `run_id`, `events`, `event_count`. The `events` list is the canonical source of truth for what the harness actually did — not the JUnit XML.

8. **Interpret the trace against the user's criteria:**
   - **Event chain integrity**: every `_STARTED` event should have a matching `_COMPLETED` / `_FAILED` / `_SKIPPED`. If you see `PUMP_STATION_STARTED` followed by `PUMP_STATION_JUDGE_STARTED` followed by `PUMP_STATION_DISPATCH_STARTED` followed by ... `PUMP_STATION_COMPLETED`, the loop is healthy.
   - **Token usage**: events with `meta.inputTokens` / `meta.outputTokens` / `meta.totalTokens` confirm the LLM calls actually executed (not stubbed).
   - **Exit reason**: `meta.exitReason` on `PUMP_STATION_COMPLETED` tells you why the harness ended. `JudgeComplete` = judge LLM said done. `PassSignal` = `passPipeline=true` flag. `MaxTurnsHit` = the harness safety net tripped because the LLM needed more turns than the test budget allowed (NOT a code defect).
   - **Steering/memory events**: `PUMP_STATION_SAFE_PRUNE_APPLIED`, `PUMP_STATION_COMPACTION_STARTED` / `_COMPLETED` confirm memory machinery fired. Check `meta.originalCount` / `meta.finalCount` / `meta.tokensRemoved` on safe-prune events to verify the compression was real.
   - **Steering chokepoints** do NOT emit their own event type — they only append to `turnHistory`. Verify steering at the `turnHistory` level, not the trace level. The 27 dedicated regression tests in `PumpStationSteering*Test.kt` cover this.

### Failure-class disambiguation

| Symptom | Class | Action |
|---------|-------|--------|
| `FileNotFoundException: .../remote/grid.html` on stdio DistributionGrid tests | Test reads wrong trace subdirectory | Stdio transport saves traces under `sender/` subdirectory, not `remote/`. Fix: change `remote` to `sender` in the test's `File(TPipeConfig.getTraceDir(), ".../$scenarioName/remote/grid.html")` read. The remote peer's trace also lives under `sender/` (as `sender/worker-pipeline.html`), not under a distinct `remote/` folder. Reference: `DistributionGridTransportLiveBedrockIntegrationTest.kt:994,1049`. |
| `P2PException: OpenAI Responses error: Service error. Please retry later` | Upstream LLM noise | Per-class rerun. The trace may show partial progress (e.g. `run_status: running` with only `STARTED` + `JUDGE_SKIPPED` + `DISPATCH_STARTED`) — the harness exited cleanly on the error path. |
| `MaxTurnsExceeded` in `meta.error` of `PUMP_STATION_FAILED` | Test budget, not code defect | The harness safety net tripped. The full event chain ran correctly up to the turn limit. Check the per-turn event sequence — if every turn has JUDGE+DISPATCH+PATH+MEMORY_UPDATE, the loop is healthy. |
| `invokeCount == 0` on a stub `RecordingAgent` | Stub skipped because test path didn't reach it | Check whether the test is exercising the right code path. For `Junction` summary tests, see Section 3 (DSL ordering constraint). |
| `time="0.001s"` on a `*_researchSucceeds` test | Gate was closed | Set `TPIPE_LIVE_LLM_TEST=true` and `MINIMAX_API_KEY`. Re-run. |
| Test class skipped entirely (no XML in `build/test-results/test/`) | `liveGateOrSkip()` returned null AND no stub tests fired | Same fix: env vars. |
| Non-live test fails with `IllegalArgumentException: baseUrl must use HTTPS for security (got: http://127.0.0.1:<port>/v1)` | Local-HTTP-server test blocked by the production HTTPS-required check | Set `TPIPE_ALLOW_INSECURE_BASEURL=true` (or `-Dtpipe.allowInsecureBaseUrl=true`) and rerun. NOT a regression. Affects `PumpStationF1PathInjectionTest`, `RunJudgePhaseTest`, and any test that boots a local HTTP server. See Section 6 for the full env-gate matrix. |

### Cost estimate

Per-class reruns (6 tests in 3 classes):
- `PumpStationSafePruneLiveTest` (1 test): 1–2 min
- `PumpStationTPipeConfigTraceLiveTest` (2 tests): 2–3 min each
- `PumpStationMiniMaxLiveTest` (13 tests, 7 live + 6 stub): 1–3 min per live test, ~15 min total

A full live-test rerun is 40–60 min. If one or two tests fail, run only the failing class — that's the 5–10× speedup the memory preserves.

### Reference case

2026-07-23 steering-feature session: 6 of 6 live tests ran in sequence (per-class, one at a time). 5 passed on first attempt; 1 (`multiPathRiskLevels_researchSucceeds`) failed with `MaxTurnsExceeded` (test budget). 1 test (`compactionMemory_researchSucceeds`) was restarted per user directive after a `--rerun-tasks` rerun attempt; passed on restart. The trace parser confirmed: full event chain fired correctly on all 5 passing tests, harness lifecycle was healthy, no broken loop, no corrupted prompts, no missing context. The steering feature's 11 chokepoints are additive and do not emit their own event types — verified at the `turnHistory` level by the 27 dedicated regression tests.

## 5. When Tests Fail — Trace the DSL Wiring Before Assuming the Implementation Is Wrong

When a TDD test for a new feature fails, the bug might be in the DSL wiring (how configuration flows into the container) rather than in the implementation. Always verify the DSL wiring before patching the test or the implementation.

**Diagnostic checklist for DSL wiring failures:**
1. Read the DSL method body — does it mutate the right object in place?
2. Does the builder block (`memoryPolicy { }`) replace the entire policy?
3. Is the targeted setter (`setSummaryAgent`) actually mutating the container's live policy reference?
4. Is `junctionMemoryPolicy` accessible from the DSL scope, or does it need a dedicated setter?

**The Junction failure mode:** `summaryAgentIsCalledDuringDiscussion` failed with `invokeCount == 0`. The implementation (`buildSummaryText`) was correct. The DSL wiring (`memoryPolicy { this.summaryAgent = agent }`) was replacing the entire policy and resetting `enableSummarization` to `false`. **Fix:** a 3-line change in the DSL method, not in `buildSummaryText`.

## 5.1 propagateStreamingCallback Double-Fire — Never Add to suspend setStreamingCallback

When wiring `propagateStreamingCallback(callback)` into BedrockPipe's `setStreamingCallback(suspend (String) -> Unit)` overload, the callback fires TWICE:

1. `emitStreamingChunk(chunk)` → fires `streamingCallback` (legacy field) → first fire
2. `emitStreamingChunk(chunk)` → fires `streamingCallbackManager?.emitToAll(chunk)` → but `propagateStreamingCallback` ALSO added the callback to the manager → second fire

The root cause: `propagateStreamingCallback` calls `obtainStreamingCallbackManager().addCallback(callback)` which registers the callback in the manager. When `emitStreamingChunk` fires, it calls BOTH the legacy field (line 5244-5257) AND the manager (line 5259-5260). Adding `propagateStreamingCallback` to the suspend overload means the callback is registered both as the legacy field AND in the manager.

**Fix:** The `suspend` overload of `setStreamingCallback` must NOT call `propagateStreamingCallback`. Only the `non-suspend` (String)→Unit overload should, because it wraps the callback in a fresh lambda before assigning to `streamingCallback` — the wrapped lambda is a distinct reference, so the manager's dedup-by-reference check (`callbacks.contains(callback)`) prevents double registration.

```kotlin
// CORRECT — suspend overload: legacy field only, no propagation
fun setStreamingCallback(callback: suspend (String) -> Unit): BedrockPipe {
    this.streamingCallback = callback
    this.streamingEnabled = true
    return this  // NO propagateStreamingCallback
}

// CORRECT — non-suspend overload: wrap then propagate (fresh reference → dedup-safe)
fun setStreamingCallback(callback: (String) -> Unit): BedrockPipe {
    val wrapped: suspend (String) -> Unit = { chunk -> callback(chunk) }
    this.streamingCallback = wrapped
    this.streamingEnabled = true
    propagateStreamingCallback(wrapped)  // safe: wrapped is a new object
    return this
}
```

**Why this matters for tests:** `testBackwardCompatibilityLegacyCallback` uses the `suspend` overload and expects exactly 1 fire. Adding `propagateStreamingCallback` to that overload breaks this existing test. The propagation for descendant pipes when using the `suspend` overload must come from a DIFFERENT entry point (`enableStreaming(callback)` → calls `propagateStreamingCallback` directly for ALL callback types).

**Reference case:** StreamingCallbackTest.kt `testBackwardCompatibilityLegacyCallback` — expected 1, got 2 when `propagateStreamingCallback` was added to the suspend overload. Confirmed by stashing all changes and verifying the test passes at HEAD.

## 5.2 Lambda Type Disambiguation in streamingCallbacks DSL

When `StreamingCallbackBuilder.add()` is overloaded as both `add(suspend (String) -> Unit)` and `add((String) -> Unit)`, a bare lambda `{ chunk -> ... }` fails overload resolution:

```
Overload resolution ambiguity between candidates:
  fun add(callback: suspend (String) -> Unit): StreamingCallbackBuilder
  fun add(callback: (String) -> Unit): StreamingCallbackBuilder
```

**Fix:** Use the `suspend` keyword in the lambda literal to disambiguate:

```kotlin
// WRONG — ambiguous lambda type
streamingCallbacks { add { chunk -> received.add(chunk) } }

// CORRECT — suspend keyword disambiguates to the suspend overload
streamingCallbacks { add(suspend { chunk: String -> received.add(chunk) }) }

// ALSO CORRECT — explicit type on the lambda parameter
streamingCallbacks { add { chunk: String -> received.add(chunk) } }
```

The `suspend { ... }` form is required when the callback reference is passed directly (not stored in a val). When the callback is stored in a `val` with explicit type, the type annotation on the `val` or the parameter is sufficient.

## 5.3 BedrockPipeStreamingCallbacksLiveTest.kt Blocks ALL Test Compilation

A pre-existing untracked test file `BedrockPipeStreamingCallbacksLiveTest.kt` in the TPipe-Bedrock test directory uses JUnit 5 annotations (`@org.junit.jupiter.api.BeforeTest`) imported from `org.junit.jupiter.api` while the test class is annotated with `@kotlin.test.Test` (kotlin.test). This causes a compilation failure that BLOCKS ALL TEST CLASSES in the module from compiling, not just the failing file.

The error:
```
Unresolved reference 'BeforeTest'
Overload resolution ambiguity: setStreamingCallback(callback: suspend (String) -> Unit) vs (String) -> Unit
```

**Recovery pattern:** When the Gradle build fails with compilation errors in an unrelated test file and you need to run a specific test class:

1. `ls src/test/kotlin/.../ | grep -i live` to find untracked / unusual test files
2. `git status --short` to confirm untracked files
3. `mv BadFile.kt BadFile.kt.bak` to temporarily remove it
4. Run the target test class
5. Restore: `mv BadFile.kt.bak BadFile.kt`

The file is NOT part of the repo (untracked) — it was created in a prior session. The compilation errors are pre-existing and not related to the current changes.

**Reference case:** `BedrockPipeStreamingCallbacksLiveTest.kt` (6KB, untracked) — blocked `StreamingCallbackTest` compilation. Moved aside to verify 13/0/0 on `StreamingCallbackTest`. The file has JUnit 5 annotation imports with kotlin.test.Test class annotation — mixed test framework usage that fails compilation.

## 5. Streaming Callback Propagation — RecordingPipe vs DummyPipe

When testing streaming recursive setters (`setStreamingCallbackRecursive`, `enableStreamingOnInterface`, etc.), the choice of test-pipe base class matters:

### `RecordingPipe : BedrockPipe()` — works everywhere except Manifold

`BedrockPipe` is a concrete class with no abstract members. It can be instantiated directly and `emitStreamingChunk` is accessible within the same package (it's `protected open` in `com.TTT.Pipe`, and `BedrockPipe` is in `bedrockPipe` — different package, so `protected` is NOT accessible from the test file). Actually `emitStreamingChunk` is `protected`, so it's only accessible from within `com.TTT.Pipe` or a subclass in the same package. `BedrockPipe` is in `bedrockPipe` — not the same package.

**For Pipeline, Connector, Splitter, Junction, MultiConnector, and PumpStation tests**, use a local `RecordingPipe : BedrockPipe()` that exposes `emitStreamingChunk` via a public `suspend fun emit(chunk: String)` wrapper:

```kotlin
private class RecordingPipe : BedrockPipe() {
    val recordedChunks = mutableListOf<String>()
    suspend fun emit(chunk: String) {
        emitStreamingChunk(chunk)
    }
}
```

`BedrockPipe` doesn't require live agent infrastructure — it just needs the generic provider to be configured, which is not needed for emit-only tests.

### `DummyPipe : Pipe()` — for Manifold

`Manifold.setManagerPipeline` validates that at least one pipe in the manager pipeline has `jsonOutput == examplePromptFor(AgentRequest::class)` (checked at `Manifold.kt:892`). `BedrockPipe` doesn't satisfy this automatically — use a `DummyPipe : Pipe()` instead:

```kotlin
private class DummyPipe : Pipe() {
    init {
        @Suppress("UNCHECKED_CAST")
        setJsonOutput(AgentRequest())  // satisfies Manifold's agent-call validation
    }
    override fun truncateModuleContext(): Pipe = this
    override suspend fun generateText(promptInjector: String): String = promptInjector
    // Not abstract: generateContent is NOT abstract in Pipe (only truncateModuleContext + generateText are)
}
```

`DummyPipe` is for Manifold-only tests. For all other containers, `RecordingPipe : BedrockPipe()` is simpler since it avoids the validation check.

### Testing idempotency (dedup by reference)

`StreamingCallbackManager` dedups callbacks by reference equality (`callbacks.contains(callback)`). To verify no double-fire:

```kotlin
val chunks = mutableListOf<String>()
val callback: suspend (String) -> Unit = { chunks.add(it) }

// Register same callback twice on same pipeline
pipeline.setStreamingCallbackRecursive(callback)
pipeline.setStreamingCallbackRecursive(callback)

pipe.emit("once")
assertEquals(listOf("once"), chunks)  // not ["once", "once"]
```

## 7. Manifold setManagerPipeline Validation — What Makes a Manager Pipe Pass

`Manifold.setManagerPipeline` (at `Manifold.kt:886-899`) throws `Exception("No pipe in the manager pipeline can make agent calls.")` if no pipe in the manager pipeline has `jsonOutput == examplePromptFor(AgentRequest::class)`.

This is NOT a compile-time constraint — it's a runtime check inside `setManagerPipeline`. The validator walks `managerPipeline.getPipes()` and checks `pipe.jsonOutput == expectedSchema`.

**What to set** (from `AgentRequest` schema):
```kotlin
setJsonOutput(AgentRequest())
```

**What NOT to use:** A plain `BedrockPipe` or a `RecordingPipe` that doesn't call `setJsonOutput(AgentRequest())` will fail this validation.

**The existing test double in `P2PConcurrencyModeTest`** (`DummyPipe`, package `com.TTT.P2P`) already does this correctly — it inherits from `Pipe()` without setting `jsonOutput`, which means it CANNOT be used as a manager pipe in Manifold tests without the same fix.

## 5.4 Bedrock Live Tests — Model Deprecation Blocks All Assertions

When a `BedrockPipeStreamingCallbacksLiveTest` runs against a model that AWS has marked as **Legacy** in the account, every assertion in the class fails with `ResourceNotFoundException: Access denied. This Model is marked by provider as Legacy` — even though the test code is correct.

**Current known-deprecated model:**
- `anthropic.claude-3-haiku-20240307-v1:0` — deprecated 2025. Use `us-west-2` region + a current model (`anthropic.claude-sonnet-4-20250514`, `amazon.nova-pro-v1:0`, or `us-east-1` + `anthropic.claude-3-5-sonnet-20241022`).

**Verified ACTIVE replacements in this account (2026-07-30):** `amazon.nova-lite-v1:0` (cheapest, Amazon's own model — won't Legacy-mark), `amazon.nova-micro-v1:0`, `amazon.nova-pro-v1:0`, `anthropic.claude-haiku-4-5-20251001-v1:0`, `anthropic.claude-sonnet-4-5-20250929-v1:0`, `deepseek.v3-v1:0`, `meta.llama3-1-8b-instruct-v1:0`. Probe before commit on any new model via `aws bedrock list-foundation-models --region us-west-2 --query "modelSummaries[?modelLifecycle.status=='ACTIVE']"`.

**Recovery:** Switch to a non-legacy model and re-run. The test file is correct — the API key, credentials, and streaming callback wiring all work; only the model ARN is stale.

### LiveTest stream-routing — `execute(MultimodalContent)` may not fire `emitStreamingChunk`

After the model swap, the test runs without the `ResourceNotFoundException` and the model responds successfully, BUT `assertTrue(received.isNotEmpty())` still fails with `Expected streaming chunks; got none`. The model returned content; the callback was never invoked.

**Root cause:** `BedrockPipe.execute(MultimodalContent(text="..."))` is the unified entry point and may route to a non-streaming `executeConverse` (or the equivalent non-streaming path) instead of `executeConverseStream`. When the unified path doesn't stream, `emitStreamingChunk` is never called and the registered `streamingCallback`/`streamingCallbackManager` listeners fire nothing.

**Detection:** the JUnit XML shows `time="0.4+"` (the test ran for real, model responded), but the failure message is `Expected streaming chunks; got none` / `Callback A received no chunks` — i.e. the assertion fires on chunk-list size, not on a wire error.

**Recovery:** invoke the test through the explicit streaming entry point (e.g. `executeStreaming(MultimodalContent(...))` or whichever streaming-specific method the pipe exposes) so the streaming wire is forced. Verify the streaming entry point exists in the pipe class before writing the test — `BedrockPipe` may expose only `execute()` in some builds and require a streaming-specific call path in others. The pre-existing `StreamingCallbackTest` passes because it uses `TestBedrockPipe.testEmit(chunk)` which calls `emitStreamingChunk(chunk)` directly, bypassing the dispatch entirely — LiveTests that go through `execute()` don't get that bypass.

**Symptom summary table:**

| Symptom | Cause | Fix |
|---|---|---|
| `ResourceNotFoundException: marked by provider as Legacy` | AWS Legacy model marker | Swap to non-Legacy model (verified-ACTIVE: `amazon.nova-lite-v1:0`) |
| `time="0.001s"` and all assertions pass | Test gate closed (env vars missing) | Set `AllowTest=true` + AWS creds in `~/.aws/credentials` |
| `time="0.4+"`, `Expected streaming chunks; got none` | `execute(MultimodalContent)` not routing to streaming wire | Use the streaming-specific entry point (`executeStreaming` or equivalent) — verify the path exists before writing the test |
| `time="0.4+"`, `P2PException: OpenAI Responses error: Service error. Please retry later` | Upstream LLM noise | Per-class rerun (Section 4) |

## 5.4.1 Live-Test Wall-Time Fingerprint — `time` Attribute is the Bug-Class Diagnostic (NEW 2026-07-30)

When a LiveTest reports `tests=N failures=0 errors=0` with **zero wall-time** per test, the test class is NOT actually green — the gate was closed and zero assertions exercised the wire. The `time` attribute on each `<testcase>` in the JUnit XML is the precise diagnostic for "did the test run the real wire?" — without it, the agent treats gate-closed and dispatcher-short-circuit as identical failures (both show "no chunks fired") and applies the wrong fix.

### Wall-time signature matrix

| `time` value | What happened | Action |
|---|---|---|
| `0.001s` | `assumeTrue`/`liveGateOrSkip` early-return. Gate didn't open. | Set env vars. Not a code bug. |
| `0.004s` – `0.020s` | Dispatcher short-circuit. Either swallowed exception in SDK call or early-return in `executeMultimodal`. | Find the short-circuit. Add print at entry of the LLM-touching function; if it doesn't fire, the dispatcher is the bug. |
| `0.100s` – `2.000s` | Real round-trip but small model + short prompt. Working. | None — the test ran. |
| `2.0s+` – `200.0s+` | Real round-trip on larger prompt or reasoning-capable model. Working but slow. | None — the test ran. |

### The `time` failure-cluster pattern (real case from this session)

`TPipe-Bedrock/src/test/kotlin/bedrockPipe/BedrockPipeStreamingCallbacksLiveTest.kt` had three tests after the model swap from `anthropic.claude-3-haiku-20240307-v1:0` (Legacy) to `amazon.nova-lite-v1:0`:

- `testSetStreamingCallbackPropagatesToValidatorOnLiveCall` → `time=0.432` (real AWS round-trip; recursion assertion PASSED; live-wire chunks assertion FAILED)
- `testStreamingCallbacksMultipleListenersBothReceiveOnLiveCall` → `time=0.004` (4ms — too short for any wire; dispatcher short-circuit path)
- `testDisableStreamingClearsDescendantsOnLiveCall` → `time=0.003` (4ms — assertion trivially passes because post-disable expects zero chunks)

Two failures look identical in the JUnit XML (`failure message: Callback A received no chunks`) but are TWO different bugs: test 1 hit a real wire but the streaming parser didn't extract chunks (Nova `contentBlockDelta` envelope missing from the parser); test 2 short-circuited at the dispatcher before reaching the wire at all. Without the wall-time signature, both failures look identical and the wrong fix (parse Nova envelope) would have been applied to a test that was never running the wire.

### Recipe for the production-debug print when gradle's stdout doesn't reach the agent

When gradle is invoked via background `terminal` and stdout is buffered/truncated, `println` inside production code does NOT appear in agent-visible stdout. Use a file write instead:

```kotlin
// In production code, at the point where state is built:
val html = generateDistributionGridHtmlReport(trace)
java.io.File("/tmp/c8-debug-${System.currentTimeMillis()}.log").writeText(
    "html.length=${html.length}\n" +
    "html.contains('TPipe DistributionGrid Execution Analysis')=${html.contains("TPipe DistributionGrid Execution Analysis")}\n" +
    "html.contains('Routing, Handoff, and Decision Timeline')=${html.contains("Routing, Handoff, and Decision Timeline")}\n"
)
```

```kotlin
// In production Bedrock streaming code, at the start of executeInvokeStream:
java.io.File("/tmp/streaming-dbg-${System.currentTimeMillis()}.log").writeText(
    "executeInvokeStream entry: model=$modelId streamingEnabled=$streamingEnabled\n"
)
```

```bash
# Recover the file contents:
ls -t /tmp/*-debug-*.log | head
cat $(ls -t /tmp/*-debug-*.log | head -1)
```

### The AWS Legacy-model swap procedure

When the AWS account marks a Bedrock model as Legacy, ALL LiveTests that target that model fail with `ResourceNotFoundException` regardless of test code correctness. The verification + swap procedure:

```bash
# 1. Confirm what models are ACTIVE in this account + region:
aws bedrock list-foundation-models --region us-west-2 \
    --query "modelSummaries[?modelLifecycle.status=='ACTIVE']" \
    --output json | jq -r '.[].modelId' | sort

# 2. Pick a cheap ACTIVE Amazon model (won't Legacy-mark):
#    amazon.nova-lite-v1:0  (cheapest, fastest)
#    amazon.nova-micro-v1:0 (smaller, faster)
#    amazon.nova-pro-v1:0   (slightly larger, still cheap)
# Avoid claude-haiku-3-... — marked Legacy in this account 2026-07-30.

# 3. Verify the model stream-wires correctly with a direct SDK probe:
/usr/bin/python3 - <<'PY'
import boto3
client = boto3.client("bedrock-runtime", region_name="us-west-2")
stream = client.invoke_model_with_response_stream(
    modelId="amazon.nova-lite-v1:0",
    body=json.dumps({"inferenceConfig":{"max_new_tokens":80},
                     "messages":[{"role":"user","content":[{"text":"Reply with one short sentence."}]}]}).encode(),
    contentType="application/json",
)
for ev in stream["body"]:
    print(ev["chunk"]["bytes"].decode())
PY
# Expected: multiple small JSON envelopes (messageStart, contentBlockDelta, contentBlockStop, messageStop).

# 4. Swap the model in the LiveTest file (sed/replace pattern), recompile, re-run.
```

### Pitfall — Wall-time 4ms is NOT a fast green

The default grading instinct on `time=0.004s + failures=0` is "fast green — the test ran successfully." This is wrong when the gate was closed (no real wire call) or when the dispatcher short-circuited (no real wire call for a different reason). The test class appears as "passed" in JUnit XML either way, but the user-visible behavior in production is "the streaming feature doesn't actually work" — and the agent doesn't know.

The right default: when a LiveTest reports `time < 0.1s`, treat it as `time=NOT_RUN` until proven otherwise. Re-run with env vars confirmed, look at stderr/stdout, or instrument production code with a file-write debug statement to confirm whether `executeInvokeStream` or equivalent was reached.

**Reference case (this session):** the Bedrock LiveTests went through three model states — (1) `anthropic.claude-3-haiku-20240307-v1:0` Legacy 404 across all 3 tests; (2) `amazon.nova-lite-v1:0` swap removed Legacy 404 but 2 of 3 tests still failed at the wire; (3) `addCallbackToDescendants` helper extracted `propagateStreamingCallback` recursion-from-self, fixing the regression test that surfaced once the Legacy blocker was removed. Each fix was gated on the previous fix's wall-time signature change.

### Companion pitfall — gradle stdout is truncated for background invocations

When `terminal(background=True)` runs a long gradle test JVM, stdout is buffered and `output_preview` is throttled to a stale snapshot. **The test JVM's stdout is NOT a real-time source of truth** for what's happening inside production code. The right diagnostic for "did my fix work" is the JUnit XML on disk (`build/test-results/test/TEST-<fqcn>.xml`) + the production-code file-write debug pattern above. Don't rely on stdout to detect production-code prints — use files.

## 5.5 `setStreamingCallback` Overload Ambiguity — Explicit Type Required

`BedrockPipe.setStreamingCallback` has two overloads:
```kotlin
fun setStreamingCallback(callback: suspend (String) -> Unit): BedrockPipe
fun setStreamingCallback(callback: (String) -> Unit): BedrockPipe
```

When a bare lambda `{ chunk -> list.add(chunk) }` is passed, Kotlin infers the return type as `Boolean` (from `MutableList.add`), creating an overload resolution ambiguity:
```
Overload resolution ambiguity between candidates:
  fun setStreamingCallback(callback: suspend (String) -> Unit)
  fun setStreamingCallback(callback: (String) -> Unit)
```

**Fix — use explicit type annotation on the callback parameter:**
```kotlin
// WRONG — bare lambda: return type of add() is Boolean, creates ambiguity
pipe.setStreamingCallback { chunk -> chunks.add(chunk) }

// CORRECT — explicit type on val forces (String) -> Boolean to match (String) -> Unit
val cb: (String) -> Unit = { chunk -> chunks.add(chunk) }
pipe.setStreamingCallback(cb)

// ALSO CORRECT — explicit type on the lambda parameter
val cb = { chunk: String -> chunks.add(chunk) }
pipe.setStreamingCallback(cb)
```

When using `streamingCallbacks { add { ... } }` DSL, the same ambiguity applies to `StreamingCallbackBuilder.add()`. Use explicit parameter type:
```kotlin
// WRONG
streamingCallbacks { add { chunk -> chunksA.add(chunk) } }

// CORRECT
val captureA: (String) -> Unit = { chunk -> chunksA.add(chunk) }
streamingCallbacks { add(captureA) }
```

## 5.6 JUnit 5 Annotation Correctness — `@BeforeTest` Does Not Exist

`org.junit.jupiter.api.BeforeTest` does not exist in JUnit 5 (Jupiter). The correct annotations are:
- `@BeforeAll` — runs once before all tests; use with `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`
- `@BeforeEach` — runs before each individual test

The incorrect `@BeforeTest` annotation produces `Unresolved reference 'BeforeTest'` at compile time and blocks **all test classes in the module** from compiling, not just the file with the error.

**Pattern for TPipe live tests with PER_CLASS lifecycle:**
```kotlin
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MyLiveTest {
    @BeforeAll
    fun setup() {
        gateLiveTest()
        // credential installation, env setup
    }
}
```

This error blocked all TPipe-Bedrock tests from compiling when `BedrockPipeStreamingCallbacksLiveTest.kt` used `@BeforeTest`. The error was caught by running `./gradlew :TPipe-Bedrock:compileTestKotlin`.

## 5.7 GenericOpenAIPipe Now Has Both `streamingCallbacks { add }` DSL and `enableStreaming(callback)`

Both `BedrockPipe` and `GenericOpenAIPipe` now expose the same streaming callback surfaces:

- `streamingCallbacks { add(cb); add(cb2); concurrent() }` — multi-listener builder DSL
- `enableStreaming(callback: suspend (String) -> Unit)` — single-callback with propagation
- `enableStreaming()` — no-arg flag flip (equivalent to `setStreamingEnabled(true)`)

Both implementations follow the same pattern:
1. Register each callback via `obtainStreamingCallbackManager().addCallback(callback)`
2. Propagate to descendants via `propagateStreamingCallback(callback)`
3. Set `streamingEnabled = true`

The `@JvmOverloads` annotation on `enableStreaming(callback?)` generates both the 0-arg and 1-arg Java overloads.

For Mantle live tests:
```kotlin
val chunks = mutableListOf<String>()
val pipe = GenericOpenAIPipe()
pipe.streamingCallbacks { add(suspend { chunk: String -> chunks.add(chunk) }) }
// OR
pipe.enableStreaming { chunk -> chunks.add(chunk) }
```

## 5.8 Concurrent-Mode Test Deadlock — `CompletableDeferred` vs `CountDownLatch`

When testing `streamingCallbacks { concurrent() }` mode, a `CompletableDeferred` gate used to synchronize parallel callback execution deadlocks:

```kotlin
// DEADLOCK — gate.await() blocks the single coroutine running emitToAll
val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
val cb1: suspend (String) -> Unit = { chunk ->
    seen.add(1 to chunk)
    gate.await()   // blocks the emitToAll coroutine — cb2 never runs
}
val cb2: suspend (String) -> Unit = { chunk -> seen.add(2 to chunk) }
pipe.streamingCallbacks { add(cb1); add(cb2); concurrent() }

runBlocking {
    manager.emitToAll("payload")
    gate.complete(Unit)  // never reached — emitToAll is stuck waiting for cb1
}
```

Root cause: `emitToAll` in concurrent mode calls each callback sequentially from the SAME coroutine (it uses `async` for fan-out but awaits all of them before returning). When `cb1` calls `gate.await()`, it suspends the `emitToAll` coroutine — `cb2` never gets to run, so `gate.complete()` is never called, so `gate.await()` waits forever.

**Fix:** use `java.util.concurrent.CountDownLatch` — it's a blocking call that works from any thread including the test's main thread:

```kotlin
// CORRECT — CountDownLatch blocks without suspending the coroutine
val latch = java.util.concurrent.CountDownLatch(2)
val cb1: suspend (String) -> Unit = { chunk ->
    seen.add(1 to chunk)
    latch.countDown()
}
val cb2: suspend (String) -> Unit = { chunk ->
    seen.add(2 to chunk)
    latch.countDown()
}
pipe.streamingCallbacks { add(cb1); add(cb2); concurrent() }

runBlocking {
    manager.emitToAll("payload")
    latch.await()  // blocks the runBlocking thread, not a suspend function
}

assertEquals(2, manager.callbackCount())
assertTrue(seen.any { it.first == 1 && it.second == "payload" })
assertTrue(seen.any { it.first == 2 && it.second == "payload" })
```

The latch starts at 2. Each callback decrements it. When it hits 0, `await()` unblocks and the assertion runs.

## 6. Per-Class Test Sweep Runner — Upgrade Triage Harness (added 2026-07-27)

When triaging a Kotlin/JDK/Gradle upgrade (or any cross-cutting regression hunt), the fastest signal is **running every test class individually** and capturing pass/fail per class in a single log file. A single `:test` invocation loses the per-class attribution when something breaks mid-suite — you only see the first failure or the cumulative XML. The per-class sweep captures every class's outcome in one place and lets you triage by surface.

### The env-gate matrix (set ALL of these before sweeping)

| Env var | Purpose | Default behavior if unset |
|---|---|---|
| `MINIMAX_API_KEY=sk-stub` | Force live tests to skip (liveGateOrSkip returns null when key starts with `sk-stub`) | Live tests would hit the real MiniMax endpoint and fail with `1004 login fail` |
| `TPIPE_LIVE_LLM_TEST=false` | Closes the live-test gate explicitly | Same — live tests would try to run |
| `AllowTest=true` | Enables TPipe-Bedrock's `*LiveTest.kt` classes (gated on AWS creds in `TestCredentialUtils.requireAwsCredentials`) | All Bedrock live tests skip with "AllowTest flag not enabled" — silent skip, zero XML |
| `TPIPE_ALLOW_INSECURE_BASEURL=true` | Allows non-live tests that spin up local HTTP servers on `127.0.0.1:<port>` to bypass the HTTPS-required check | **Tests fail** with `IllegalArgumentException: baseUrl must use HTTPS for security`. Affects `PumpStationF1PathInjectionTest`, `RunJudgePhaseTest`, any test that boots a local HTTP listener. NOT a regression — test-infra gap. Set it from the start. |

### The runner script — two scripts + one list

`scripts/per-class-sweep/run-class.sh` — runs one class, parses the JUnit XML, writes one line to the log:
```bash
#!/usr/bin/env bash
# Args: <module> <fqcn>  e.g. :test com.TTT.Pipeline.JunctionTest
MODULE="$1"; FQCN="$2"
LOG=".hermes/test-results/<session-id>/per-class.log"
GRADLE_LOG=".hermes/test-results/<session-id>/gradle-raw.log"
case "$MODULE" in
  ":test") XML="build/test-results/test/TEST-${FQCN}.xml" ;;
  *)      MOD_DIR="${MODULE#:}"; MOD_DIR="${MOD_DIR%:test}"
         XML="${MOD_DIR}/build/test-results/test/TEST-${FQCN}.xml" ;;
esac
./gradlew "${MODULE}" --tests "${FQCN}" --no-daemon --console=plain > "${GRADLE_LOG}" 2>&1
EXIT=$?
if [ ! -f "$XML" ]; then
  echo "${FQCN} | module=${MODULE} | NO_XML | exit=${EXIT}" >> "${LOG}"
  tail -10 "${GRADLE_LOG}" >> "${LOG}" 2>/dev/null
  exit 0
fi
SUMMARY=$(head -2 "$XML" | grep -oE 'tests="[0-9]+" skipped="[0-9]+" failures="[0-9]+" errors="[0-9]+"' | head -1)
echo "${FQCN} | module=${MODULE} | ${SUMMARY} | exit=${EXIT}" >> "${LOG}"
if echo "$SUMMARY" | grep -qE 'failures="[1-9]|errors="[1-9]'; then
  echo "  --- failure detail ---" >> "${LOG}"
  grep -E '(<testcase|<failure|<error)' "$XML" | head -60 >> "${LOG}"
fi
```

`scripts/per-class-sweep/run-list.sh` — drives a TSV of `(module<TAB>fqcn)` rows:
```bash
LIST="$1"; LABEL="$2"; LOG=".hermes/test-results/<session-id>/per-class.log"
TOTAL=$(wc -l < "$LIST"); IDX=0
while IFS=$'\t' read -r MOD FQCN; do
  [ -z "$MOD" ] || [ -z "$FQCN" ] && continue
  IDX=$((IDX + 1))
  echo "--- $IDX/$TOTAL : $FQCN ($MOD) ---" >> "$LOG"
  .hermes/test-results/<session-id>/run-class.sh "$MOD" "$FQCN"
done < "$LIST"
```

The TSV is built by parsing each module's `src/test/kotlin` tree for `package` lines + `@Test`/`@kotlin.test.Test` markers, then dropping files named `*LiveTest.kt` (live tests need a different gate). Top-level `TPipe-Bedrock/src/test/kotlin/*.kt` files have no `package` line (default package); Gradle's `--tests` filter for them is just the class name, not `bedrockPipe.X`. The TSV rows must reflect that.

### The PIPESTATUS gotcha — capture the right exit code

`./gradlew ... 2>&1 | tail -6` sets `$?` to `tail`'s exit code (always 0 if `tail` succeeded), NOT `gradle`'s. The fix:

```bash
GRADLE_OUT=$(./gradlew "${MODULE}" --tests "${FQCN}" --no-daemon --console=plain 2>&1)
EXIT=$?    # this IS gradle's exit code, because there's no pipe
```

If you must pipe (e.g., through `tee` to capture full output while still printing to stderr), use `${PIPESTATUS[0]}`. Anything else will silently report exit=0 for failing classes and you'll miss the NO_XML vs BUILD FAILED distinction.

### Reading progress while the loop runs

`process(action='poll')` and `process(action='wait')` clamp `timeout` to 60s regardless of the value passed, and the `output_preview.uptime_seconds` field is throttled to a stale snapshot. The polling preview lies about wall clock. **Source of truth is the per-class log file on disk.** Tail it directly to know what the loop is actually doing:

```bash
grep -c '^com\.' .hermes/test-results/<session-id>/per-class.log
grep '^com\.' .hermes/test-results/<session-id>/per-class.log | tail -3
grep -E 'failures="[1-9]|errors="[1-9]' .hermes/test-results/<session-id>/per-class.log | head
```

### Triage buckets

After the sweep finishes, every failure falls into one of three buckets:

1. **Test-infrastructure (env gate missing or quarantine)** — set the env var from the matrix above, re-run, expect green. `CoercionTest.kt` and `Util/JsonRepairTest.kt` are quarantined at `build.gradle.kts:200-202` because the 2.2.20 serialization compiler plugin can't read the kotlinx-serialization-core version from the classpath — they will silently emit `NO_XML` (gradle exits 0, no `<testsuite>` produced). That's the expected quarantine shape, not a bug. See `jvm-build-toolchain-migration` Section on the 2.2 → 2.3 serialization compiler plugin transition.
2. **Kotlin upgrade regression candidate** — investigate live source. The 2026-07-27 Kotlin 2.3.21 sweep confirmed `DistributionGridHardeningTest.remoteHandoffBuildsOutboundMemoryEnvelope` failed exactly the way Section 2.5 predicted (`Method.invoke` against a suspend function with synthetic `Continuation` parameter). Fix: change `private suspend fun buildOutboundMemoryEnvelope(...)` to `internal suspend fun` so the same-module test can call it via `runBlocking { container.methodName(...) }` without reflection.
3. **Pre-existing flake vs. genuine behavioral change** — re-run with `--rerun-tasks` and compare to a 2.2.20 baseline. Anything in the `Iterable<T>.intersect` / `.subtract` semantics surface (KTLC-268) needs a baseline run because the change is silent at compile time.

### Reference case — 2026-07-27 Kotlin 2.3.21 sweep

237/293 root classes run before user stopped the sweep. 9 classes had at least one failure (14 individual test methods). Bucket breakdown:
- Test-infra: `PumpStationF1PathInjectionTest` (1), `RunJudgePhaseTest` (2) — both HTTPS env gate, not regressions.
- Kotlin regression candidates: `NestedTracingTest` (2 — `setReasoningPipe` tracing), `DistributionGridHardeningTest.remoteHandoffBuildsOutboundMemoryEnvelope` (1 — Section 2.5 hit), `MagicContractOptOutTest` (2), `PumpStationWarningTest.noJudge_maxTurns10_firesAdvisory` (1), `PumpStationPathSchemaValidationTest.buildPathInput_filters_non_json_dispatch_schema_and_falls_back` (1 — Harness Notice content mismatch), `Util.SemanticCompressionTest` (2), `Debug.DistributionGridTraceVisualizationTest` (2).
- Tier-0 readiness (12 classes / 122 cases): all GREEN — the 2.3.21 readiness plan was validated by this run.

### Reference case — 2026-07-27 C-bucket fix pass (Kotlin 2.3.21)

After the initial sweep, the 22 failing classes were triaged into 4 buckets (A: live-LLM, B: env-gate, C: pre-existing test bug, D: K2.3.21 regression) and 9 of the 10 C/D classes were patched. Source-read-only triage without a 2.2.20 baseline run was sufficient because 5 of 9 classes had obvious pre-existing test bugs (Bucket C: `DeepSeekV31Test` use of `getDeclaredField` not walking inheritance; `PumpStationWarningTest` fixture setting `executionFunction` blocking the warning condition; `PumpStationPathSchemaValidationTest` role-filter using `user` instead of `harness`; `SemanticCompressionTest` using common-English words like "Alpha Beta Gamma" that fail `phraseHasNonComplexEnglishToken`; `DistributionGridTraceVisualizationTest` HTML headers with `&&` typo and 2 bogus assertions for `Router` + `tracePolicyAllowTracePersistence`). The 4 genuine K2.3.21 regressions fixed were: `ApiMode.DEFAULT` returning null (companion-object init-order regression — fix with `by lazy`); `NestedTracingTest` (early-return guard in `propagateTracingRecursively` — fix with `tracingEnabled = true` at top); `SemanticCompressionTest`'s `Alpha Beta Gamma` (legitimate K2.3.21 regex behavior change, but the test fix happens to be the right fix for both); and the redaction typo in `TraceVisualizer.kt`. The remaining 5 (C1, C2, C4, C5, C10) were left as pre-existing flakes per the rule that source-side fixes are required when root cause is unknown.

#### TPipe-specific test patterns from the 2.3.21 triage

Three test patterns emerged that are specific to TPipe and worth capturing as direct knowledge-bank additions:

**Test 1: `phraseHasNonCommonEnglishToken` requires uncommon tokens, not just proper nouns.** Production (src/main/kotlin/Util/SemanticCompression.kt:1035) requires at least one token NOT in `COMMON_ENGLISH_WORDS`. Test inputs using common English words like "Alpha Beta Gamma" or "Alice Johnson" FAIL this filter because all three tokens are in `Dictionary.words`. Test inputs need at least one uncommon token (e.g. "Xyzqwert Betaz Gammaz") to pass. Diagnostic: write a debug file from inside `compressParagraph` to dump `phraseToCode`, `legendMap`, `legendText` — if all are empty, the filter rejected the candidate before the legend could be built.

**Test 2: `getDeclaredField` does NOT walk inheritance — must use the declaring class.** Production `protected var contextWindowSize` is declared on `Pipe`, not `BedrockPipe`. `BedrockPipe::class.java.getDeclaredField("contextWindowSize")` throws `NoSuchFieldException` regardless of Kotlin version. Use `Pipe::class.java.getDeclaredField("contextWindowSize")` (the declaring class) for reflection. This was always wrong Java reflection semantics, not a Kotlin regression.

**Test 3: HTML assertion substring matching needs the production wording, not the spec wording.** `TraceVisualizer.kt:985` had `Handoff, && Decision Timeline` (production) vs test asserting `Handoff, and Decision Timeline`. The test was correct (production had `&&` typo); fix was a 1-character change in production. For visualizer tests, always grep the production HTML before asserting substrings.

Full per-class log: `.hermes/test-results/2026-07-27-kotlin-231/per-class.log`. Per-failure detail: `.hermes/test-results/2026-07-27-kotlin-231/failures.log`.

## 8. The 3-Run Empirical Triage Pattern for Flaky Tests (added 2026-07-27)

When a single test class is failing intermittently — sometimes TIMEOUT, sometimes fast with deterministic failures — the default instinct is to label it "flaky, leave alone." That instinct is wrong for TPipe regression triage. **The TIMEOUT is hiding deterministic failures.** When the test doesn't time out, the SAME test produces a deterministic 2-test-method failure pattern that you CAN fix.

### Why "flaky" is the wrong conclusion

The pattern across 4 distinct TPipe classes (C2 DistributionGridHardeningTest, C4 MagicContractOptOutTest, C7 SemanticCompressionTest, C8 DistributionGridTraceVisualizationTest) in the 2026-07-27 sweep: TIMEOUT sometimes, then 6/0/2/0 in 9s, then 6/0/2/0 in 9s, then 6/0/2/0 in 9s. The TIMEOUT is a stochastic infrastructure failure (gradle daemon startup race, JVM GC pause, sandbox cgroup reaper) that masks the same deterministic failure that fires reliably otherwise. The user verbatim: "if they always fail when they timeout we have no choice but to investigate why like prior, and fix any regressions or bugs in TPipe, or in the test if the test ist he problem."

### The 3-run recipe

1. **Run the class 3 times** with `run-class.sh :module TestClass` (Section 6 runner) and a 90s timeout each. Capture every run's per-class.log line and the per-test-method failure detail.

2. **Classify the run pattern into one of three buckets:**
   - **3x TIMEOUT** — likely a real environmental block (memory, infinite loop, JDK pinning). Look at gradle-raw.log for stack traces and increase the timeout to 180s to rule out slow CI.
   - **TIMEOUT + 6/0/N/0** (mixed) — the test is flaky at the infrastructure layer but has a deterministic failure mode in the non-timeout runs. THIS IS THE C-BUCKET. Do not skip — the deterministic failures ARE the fixable signal.
   - **3x 6/0/N/0 deterministic** — stable reproducible failure. Standard TDD flow. Read source, identify root cause, propose fix, apply, re-run.

3. **For the C-BUCKET pattern, extract the per-test-method failure detail** from the non-timeout run. JUnit XML has `<failure message="...">` blocks per failing test method. Grep `per-class.log` for `--- failure detail ---` and read the next 30 lines — this is the source of truth, NOT the assertion in the test source.

4. **Do NOT add debug printlns to test files directly until you know the assertion that fails.** Test code compile errors break the whole class. If you need to instrument production, do that — production code can have `writeText` to `/tmp/c-<class>-debug-${System.currentTimeMillis()}.log` and the test JVM has full write access to `/tmp/`.

5. **Investigate root cause per failing method, not per class.** Each method's failure has a different root cause:
   - C4 `judgeFlagsDriveVerdictWhenContractDisabled` (default mode, contract on): `setSkipJudgeOnFirstTurn(false)` needed because the default skips on turn 0
   - C4 `judgeJsonParserRunsByDefault` (default mode, contract on): same — judge phase is skipped before the parser can run
   - C7 `semanticCompressionLegendCodesStartAtAaAndAdvanceDeterministically` (input at sentence start): `seenNotAtSentenceStart` filter rejects sentence-start proper nouns, prepend `"and "` to put the test in the middle of a sentence
   - C7 `semanticCompressionUsesResearchNoteLegendThresholds` (3/4/6-token cases): `phraseHasNonCommonEnglishToken` returns false when ALL tokens are in `COMMON_ENGLISH_WORDS`; use made-up tokens like `Xyzqwert Betaz Gammaz`
   - C2 `remoteHandoffBuildsOutboundMemoryEnvelope`: `shapeOutboundEnvelopeForPeer` replaces `envelope.content.context` with a freshly-built `contextWindow` from text only, dropping any pre-populated `contextElements`; drop the assertion
   - C8 `generateDistributionGridHtmlTraceShowsGridSpecificSections`: `&&` typo in production HTML at line 985/990; fix production to `and`; then drop 2 bogus assertions for `Router` (only emitted by ROUTER_DECISION event) and `tracePolicyAllowTracePersistence` (never emitted by production)

### The debug-writeText pattern

When the failure message is generic ("Expected value to be true." or "NoSuchFieldException: ..." with no test-method context), instrument the production code or test to dump the actual state:

```kotlin
// In a test method, BEFORE the failing assertion:
val capturedEnvelope = remotePeer.lastTaskEnvelope
java.io.File("/tmp/c2-debug-${System.currentTimeMillis()}.log").writeText(
    "result.passPipeline=${result.passPipeline}\n" +
    "capturedEnvelope.content.text=${capturedEnvelope.content.text}\n" +
    "capturedEnvelope.content.context.contextElements.isNotEmpty()=${capturedEnvelope.content.context.contextElements.isNotEmpty()}\n"
)
assertTrue(result.passPipeline)
```

```kotlin
// In production code, at the point where state is built:
val html = generateDistributionGridHtmlReport(trace)
java.io.File("/tmp/c8-debug-${System.currentTimeMillis()}.log").writeText(
    "html.length=${html.length}\n" +
    "html.contains('TPipe DistributionGrid Execution Analysis')=${html.contains("TPipe DistributionGrid Execution Analysis")}\n" +
    "html.contains('Routing, Handoff, and Decision Timeline')=${html.contains("Routing, Handoff, and Decision Timeline")}\n"
)
```

```kotlin
// When investigating a parse or build path:
val phraseToCode = ...
java.io.File("/tmp/c7-debug-${System.currentTimeMillis()}.log").writeText(
    "phraseToCode=$phraseToCode\n" +
    "legendMap=$legendMap\n" +
    "legendText=$legendText\n"
)
```

The file goes to `/tmp/c<short>-debug-<timestamp>.log` and the test JVM's stderr doesn't capture it. Use `ls -t /tmp/c-*-debug-*.log | head` to find the most recent.

### Three TPipe-specific root-cause patterns discovered

**Pattern A: `setSkipJudgeOnFirstTurn(false)` is required before `runJudgePhase()` is called directly.** Default value of `skipJudgeOnFirstTurnInternal = true` (PumpStation.kt:1313). When the judge run mode is `Always` (default), the first `runJudgePhase()` call on turn 0 returns `JudgeVerdict.empty()` (PumpStationLoop.kt:382-399) and emits a `JudgeSkipped` event. Tests that call `runJudgePhase()` directly from a test method need to call `station.setSkipJudgeOnFirstTurn(false)` first, or they'll get the empty verdict regardless of what the judge agent returns. The 3rd judge test in `MagicContractOptOutTest` (`judgeJsonParserSkippedWhenContractDisabled`) passes by accident — it asserts `verdict.isComplete == false` which is what `JudgeVerdict.empty()` returns.

**Pattern B: `shapeOutboundEnvelopeForPeer` rebuilds `envelope.content.context` from text only.** At DistributionGrid.kt:5595-5597:
```kotlin
content = content.deepCopy().apply {
    context = memoryEnvelope.contextWindow.deepCopy()  // REPLACES any pre-existing context.contextElements
    miniBankContext = memoryEnvelope.miniBank.deepCopy()
    ...
}
```
`buildOutboundMemoryEnvelope` returns a fresh `contextWindow` built from the envelope's text via `buildContextWindowForPrompt`, NOT from any pre-populated `contextElements` on the input. So tests that pre-populate `MultimodalContent.context.contextElements` before routing and expect them to survive find an empty list post-shape. The pre-populate approach is a no-op; the correct test fix is to drop the assertion. (Production rebuild-from-text is the correct behavior; the test was written assuming the old "preserve" path.)

**Pattern C: HTML `&&` typo vs `and` substring assertion.** `TraceVisualizer.kt:985`:
```kotlin
<h2>🎯 Routing, Handoff, && Decision Timeline</h2>  // PRODUCED
```
vs the test asserting:
```kotlin
assertTrue(htmlReport.contains("Routing, Handoff, and Decision Timeline"))  // EXPECTED
```
The production had a 1-character typo (`&&` vs `and`). Both are valid English separators, but the test was written assuming the cleaner `and`. The fix is production-side: change `&&` to `and`. For all visualizer tests, always grep the production HTML for the expected substrings before assuming the test is correct — production had a real bug here, the test was right.

### The "do not skip pre-existing flakes" rule

The user has repeatedly corrected the "skip pre-existing flakes" instinct across sessions. The 2026-07-27 C-bucket fix pass produced 5 such "flaky" classes that were all eventually fixed:

- **C1 NestedTracingTest** — pre-existing test bug (the cycle detection test expects `CycleChild` in the trace, but the production cycle check prevents it from executing). NOT a Kotlin regression.
- **C2 DistributionGridHardeningTest** — Pattern B above. Production rebuilds context from text. Test fix: drop the bogus assertion.
- **C4 MagicContractOptOutTest** — Pattern A above. Test fix: `setSkipJudgeOnFirstTurn(false)`.
- **C5 PumpStationWarningTest** — pre-existing test bug. The test's `testPath()` fixture calls `setExecutionFunction` which makes the path have an execution mechanism, so `hasPathExitSignal=true` and the warning condition `!hasPathExitSignal` is false, so the warning never fires. Test fix: use a path WITHOUT execution function (the test wants to verify the warning condition fires, not that the path executes).
- **C10 McpBridgeHttpHostTest** — pre-existing Ktor DSL issue. The `authenticate("mcp-auth") { ... }` block doesn't capture Bearer tokens correctly under certain Ktor 3.3.3 path configurations. NOT a K2.3.21 regression.

The rule: **for each "flaky" class, run 3x to determine if the failure is stochastic-only (no signal, can be left) or stochastic-masking-deterministic (real signal, fix it).** The deterministic signal is the same test failing the same way in 2+ runs. Apply the fix per the rules in Section 8 above.

## See Also

- `tpipe-pipeline-patterns` — TPipe container DSL patterns (Junction state machine, Manifold scope, container embedding shims)
- `test-driven-development` — general TDD discipline (Red-Green-Refactor, test double patterns, race condition testing)
- `systematic-debugging` — 4-phase root cause debugging when tests pass but the feature doesn't work end-to-end
- `jvm-build-toolchain-migration` — Kotlin/JDK/Gradle upgrade recipe; Section 2.5 of THIS skill is cross-referenced from there for the suspend-reflection pitfall
- `references/streaming-sweep-shell-pattern.md` — shell scaffolding + env-gate matrix for streaming-callback live test sweeps (2026-07-30 session)
