# Mantle streaming — autogenesis consumer-side wiring patterns

Class-level patterns for wiring Mantle streaming through a downstream
consumer. Read this when you have a Bedrock + Mantle mix in production
and need to ensure streaming chunks reach the dispatcher uniformly, or
when investigating why a migrated agent runs to completion but emits
zero chunks.

**Verified**: 2026-07-30, Autogenesis streaming parity session —
consumer-side wiring for 30+ Mantle pipe instances across
writerAgent, worldupdates, geoPolitics, newcharacterscan,
nemesisCreation, hardenAgent, reverseAgent, passFailAgent,
ResponseRefinementAgent, playerAgent. Plan:
`.hermes/plans/2026-07-30_195300-mantle-streaming-parity-consumer-wiring.md`.

## The silent-drop factory pattern

The single biggest bug class for cross-provider streaming wiring is
the type-test early-return:

```kotlin
// WRONG — Mantle pipes silently dropped
private fun configureBedrockStreaming(connectionIds: Collection<String>, pipe: Pipe)
{
    if(pipe !is BedrockPipe)
    {
        return
    }
    val callback: (String) -> Unit = { chunk ->
        AgentWorkStreamDispatcher.appendChunkToMany(connectionIds, chunk)
    }
    pipe.enableStreaming()
        .streamingCallbacks {
            add(callback)
        }
}
```

This compiles cleanly. It runs cleanly. It silently does nothing for
every pipe that isn't a `BedrockPipe`. Production catch: 30+ Mantle
pipes wired but emitting zero chunks because this factory's return
path was the only Mantle codepath.

**Fix — explicit dispatch with `when`:**

```kotlin
private fun configureBedrockStreaming(connectionIds: Collection<String>, pipe: Pipe)
{
    if(pipe !is BedrockPipe) return
    val callback: (String) -> Unit = { chunk ->
        AgentWorkStreamDispatcher.appendChunkToMany(connectionIds, chunk)
    }
    pipe.enableStreaming().streamingCallbacks { add(callback) }
}

private fun configureGenericOpenAiStreaming(connectionIds: Collection<String>, pipe: Pipe)
{
    if(pipe !is GenericOpenAIPipe) return
    val callback: (String) -> Unit = { chunk ->
        AgentWorkStreamDispatcher.appendChunkToMany(connectionIds, chunk)
    }
    pipe.enableStreaming().streamingCallbacks { add(callback) }
}

// In the recursive walk:
configureBedrockStreaming(connectionIds, pipe)
configureGenericOpenAiStreaming(connectionIds, pipe)
configureStreamingForPipe(connectionIds, pipe.reasoningPipe, configured)
```

Both branches use the lifted `streamingCallbacks { add(cb) }` DSL — no
provider-specific streaming code in the factory, the branching is
purely on pipe type. Bedrock and Mantle share the same wiring code
shape; only the type guard differs.

**Test for both branches** — write a unit test that constructs a
`GenericOpenAIPipe` (no `init()`, no API credentials needed) and
asserts the manager has a callback registered after the factory runs:

```kotlin
@Test
fun configureStreamingWiresCallbackOnGenericOpenAIPipe()
{
    val pipe = GenericOpenAIPipe()
    val pipeline = Pipeline().apply { add(pipe) }
    streamPipelineOutputToAgentWorkBuffer(listOf("conn-1"), pipeline)
    val manager = pipe.obtainStreamingCallbackManager()
    assertTrue(manager.getCallbacks().isNotEmpty(),
        "Mantle pipe should have a streaming callback registered after factory wiring")
}
```

No live network needed — `obtainStreamingCallbackManager()` is a
public accessor that returns the (initially empty) callback list.
The factory writes to it; the test asserts the write happened. This
catches regression to "Mantle pipes silently dropped" in 0.3 seconds.

## `Pipeline.getPipes()` returns entry pipes only

`Pipeline` has ONE traversal API: `getPipes()`. There is no
`getAllChildPipes()` / `getAllPipes()` / `getChildren()` / `children`
property — verified by
`grep -nE 'fun getAll|fun getChildren|val children' TPipe/src/main/kotlin/Pipeline/Pipeline.kt`
returning zero matches.

This means: a consumer factory that walks
`pipeline.getPipes().forEach { registerCallback(it) }` only sees the
ENTRY pipes — not sibling pipes inside the same pipeline:

```kotlin
val pipeline = Pipeline()
pipeline.add(detectPipe)   // entry — visible to factory
pipeline.add(refinePipe)   // sibling — NOT visible to factory
```

For the Autogenesis `buildResponseRefinementAgent(...)` case, the
entry is `detectPipe`. The factory sees `detectPipe`, registers a
callback, and the streaming chunks flow. But `refinePipe` (the
sibling) has no callback registered through the factory path — its
chunks stream to nobody.

The SDK's `propagateStreamingCallback(callback)` walks a SINGLE pipe's
descendants (`reasoningPipe` / `transformationPipe` / `branchPipe` /
`validatorPipe`), not sibling pipes in the same `Pipeline`. So
registering on the entry covers that pipe's children but NOT its
siblings.

**Fix — self-register in the agent builder for multi-pipe pipelines:**

```kotlin
fun buildResponseRefinementAgent(connectionIds: Collection<String> = emptyList()): Pipeline {
    val detectPipe = GenericOpenAIPipe().apply {
        setBedrockMantle(...)
        ...
        if (connectionIds.isNotEmpty()) {
            val callback: (String) -> Unit = { chunk ->
                AgentWorkStreamDispatcher.appendChunkToMany(connectionIds.toList(), chunk)
            }
            streamingCallbacks { add(callback) }
        }
    }
    val refinePipe = GenericOpenAIPipe().apply {
        setBedrockMantle(...)
        ...
        if (connectionIds.isNotEmpty()) {
            val callback: (String) -> Unit = { chunk ->
                AgentWorkStreamDispatcher.appendChunkToMany(connectionIds.toList(), chunk)
            }
            streamingCallbacks { add(callback) }
        }
    }
    val pipeline = Pipeline()
    pipeline.add(detectPipe)
    pipeline.add(refinePipe)
    return pipeline
}
```

The orchestrator call site hoists `broadcastIds` above the agent
build call and passes them in:

```kotlin
val broadcastIds = getAllConnectedClientIds()
val refinementAgent = buildResponseRefinementAgent(broadcastIds).apply {
    init(true)
    streamPipelineOutputToAgentWorkBuffer(broadcastIds, this)
}
```

The factory's `getPipes()` walk still hits `detectPipe` (and registers
the same callback again — no double-fire because the manager dedupes
on identity for `streamingCallbacks`), and the self-registered
callback on `refinePipe` covers the sibling pipe. Both chunks flow.

`connectionIds = emptyList()` default keeps the existing call sites
backward-compatible — pre-connection-scope tests and build responses
that don't need streaming just skip the registration.

## `filterIsInstance<X>()` callsite relaxation

When a codebase has provider-specific guards scattered across
orchestrator files, fixing the central factory isn't enough — those
guards also need updating. A grep for `filterIsInstance<BedrockPipe>()`
in the autogenesis orchestrator files produced:

```
gameplayOrchestrator.kt:7 sites
npcOrchestrator.kt:1 site
```

The two-step fix depends on the callsite shape:

**Pattern A — `setStreamingCallback(callback)` on each pipe:**

```kotlin
// Before
getPipes().filterIsInstance<BedrockPipe>().forEach { pipe ->
    pipe.setStreamingCallback(callback)
}

// After
getPipes().forEach { pipe ->
    when (pipe) {
        is BedrockPipe -> pipe.setStreamingCallback(callback)
        is GenericOpenAIPipe -> pipe.streamingCallbacks { add(callback) }
    }
}
```

Bedrock codepath is byte-identical (single callback, same setter).
Mantle codepath is new. The `when` branch makes the guard explicit;
adding a third provider type later is one more branch, not a separate
filterIsInstance line.

**Pattern B — `enableBufferedNarrativeStreaming(throttler)` on each pipe:**

```kotlin
// Before
getPipes().filterIsInstance<BedrockPipe>().forEach { pipe ->
    pipe.enableBufferedNarrativeStreaming(reversalThrottler)
}

// After (add a parallel Mantle line)
getPipes().filterIsInstance<BedrockPipe>().forEach { pipe ->
    pipe.enableBufferedNarrativeStreaming(reversalThrottler)
}
getPipes().filterIsInstance<GenericOpenAIPipe>().forEach { pipe ->
    pipe.enableBufferedNarrativeStreaming(reversalThrottler)
}
```

This is a narrative-throttler setup, not a single-callback setup. The
Bedrock line is preserved unchanged for byte-identical Bedrock
behavior; the Mantle line is added as a parallel call (both lines
visit the same agent's pipes, calling the typed extension on whichever
pipe type matches). The extension function
`BedrockPipe.enableBufferedNarrativeStreaming(throttler)` is duplicated
on `GenericOpenAIPipe` — see "Orchestrator extension duplication"
below.

**Verify parity** — after the fix, grep must show the same count of
Bedrock and Mantle callsites in orchestrator files:

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
grep -rnE 'filterIsInstance<(BedrockPipe|GenericOpenAIPipe)>\(\)' \
    server/src/main/kotlin/agent/runners/*.kt | wc -l
```

Should report 5 Bedrock sites and 5 Mantle sites post-fix (the
3 `setStreamingCallback` sites converted to `when` dispatch drop the
Bedrock filterIsInstance count from 8 → 5; the Mantle count rises
from 0 → 5 via the parallel narrative-throttler lines).

## Orchestrator extension duplication

Before the unification, `gameplayOrchestrator.kt:315-320` and
`npcOrchestrator.kt:231-236` defined a private extension:

```kotlin
private fun BedrockPipe.enableBufferedNarrativeStreaming(throttler: NarrativeChunkThottler)
{
    enableStreaming()
    val callback: suspend (String) -> Unit = { chunk ->
        AgentCoroutineScope.scope.launch { throttler.append(chunk) }
    }
    setStreamingCallback(callback)
}
```

The receiver is `BedrockPipe` — Mantle pipes silently miss the
narrative chunking wiring. The fix duplicates the extension for
`GenericOpenAIPipe` with the same body, switching only the DSL call:

```kotlin
private fun GenericOpenAIPipe.enableBufferedNarrativeStreaming(throttler: NarrativeChunkThrottler)
{
    enableStreaming()
    val callback: suspend (String) -> Unit = { chunk ->
        AgentCoroutineScope.scope.launch { throttler.append(chunk) }
    }
    streamingCallbacks {
        add(callback)
    }
}
```

Same body, same callback, same throttler — only the DSL accessor
changes. The orchestrator's `filterIsInstance<...>().forEach` callsites
visit both extensions and wire both pipe types uniformly.

Import addition for both files:

```kotlin
import genericOpenAIPipe.GenericOpenAIPipe
```

## Mockk stub signature mismatch on signature change

When changing a production callsite signature (e.g.
`buildResponseRefinementAgent()` → `buildResponseRefinementAgent(connectionIds)`),
mockk stubs that matched the old zero-arg shape silently fall through
to the real function:

```kotlin
// mockk stub from prior session (5 sites in SummitOrchestratorTest,
                                  2 sites in GameplayMultiTargetTest)
every { buildResponseRefinementAgent() } returns mockPipeline

// Production callsite now reads:
val refinementAgent = buildResponseRefinementAgent(broadcastIds).apply { ... }

// mockk sees no matching stub, falls through to the REAL function
// which constructs a real GenericOpenAIPipe, calls init() without
// API credentials, and throws:
//
//   java.lang.IllegalStateException: GenericOpenAI API key is required.
//   at genericOpenAIPipe.GenericOpenAIPipe.init(GenericOpenAIPipe.kt:694)
```

The error message points to `GenericOpenAIPipe.init` — looks like a
provider wiring issue — but the actual cause is the mockk stub. The
fix:

```kotlin
every { buildResponseRefinementAgent(any()) } returns mockPipeline
```

Or match the exact new signature:

```kotlin
every { buildResponseRefinementAgent(ofType(Collection::class)) } returns mockPipeline
```

Re-run focused tests (`./gradlew :server:test --tests "<class>"`)
after any signature change to catch this regression class. The
diagnostic is unmistakable once you know the pattern: a real-function
fall-through during mocking always produces "init failed" or "API key
required" on the first invocation inside a previously-mocked path.

## `StreamingCallbackBuilder.add(lambda)` overload ambiguity

`StreamingCallbackBuilder.add` has TWO overloads (line 28, 41 of
`TPipe/src/main/kotlin/Pipe/StreamingCallbackBuilder.kt`):

```kotlin
fun add(callback: suspend (String) -> Unit): StreamingCallbackBuilder
fun add(callback: (String) -> Unit): StreamingCallbackBuilder
```

When you write:

```kotlin
streamingCallbacks {
    add { chunk -> AgentWorkStreamDispatcher.appendChunkToMany(ids, chunk) }
}
```

Kotlin's overload resolver sees two candidates with identical arity
and can't infer which matches a `Unit`-returning expression body. It
errors out with "Overload resolution ambiguity."

**Disambiguation** — use a typed local val for the callback:

```kotlin
val callback: (String) -> Unit = { chunk ->
    AgentWorkStreamDispatcher.appendChunkToMany(ids, chunk)
}
streamingCallbacks {
    add(callback)
}
```

The typed annotation forces the overload to resolve at the variable
declaration, not at the `add` call site. This matches the existing
pattern at
`server/src/main/kotlin/agent/builders/systemActions/answerAgent.kt:401-405`
and
`server/src/main/kotlin/agent/builders/systemActions/chatAgent.kt:176-185`
where Mantle wires callbacks via typed local vals.

If you need the `suspend` overload specifically, declare:

```kotlin
val callback: suspend (String) -> Unit = { chunk -> ... }
```

The autogenesis producer side generally wants the non-suspend
`(String) -> Unit` form because the callback body already wraps
suspending work in `AgentCoroutineScope.scope.launch { ... }` or is a
short synchronous `appendChunk` call.

## Verification recipe

The consumer-side fix is verified by a three-test hermetic gate (no
live network required):

```bash
# 1. Unit test on the consumer factory (catches the silent-drop bug)
./gradlew :server:test --tests "org.ttt.autogenesis.server.AgentWorkStreamStreamingTest"

# 2. Unit test on the agent builder with sibling-pipe fix
./gradlew :server:test --tests "agent.builders.writingAgent.BuildResponseRefinementAgentMantleTest"

# 3. Live integration test (gated on BEDROCK_MANTLE_LIVE_TEST=true)
#    - catches end-to-end chunk delivery
#    - gate skipped cleanly when env var absent
BEDROCK_MANTLE_LIVE_TEST=true \
BEDROCK_AWS_PROFILE=BedrockKey \
./gradlew :server:test --tests "org.ttt.autogenesis.server.MantleStreamingE2ELiveTest"
```

Capture JUnit XML — `tests="N" failures="0"` — to `/tmp/...` per the
ad-hoc verifier pattern (see SKILL.md "Verification" section).

For the `filterIsInstance` callsite parity check:

```bash
# Pre-fix baseline:
BEDROCK=$(grep -cE 'filterIsInstance<BedrockPipe>\(\)' \
    server/src/main/kotlin/agent/runners/*.kt | awk -F: '{s+=$2}END{print s}')
MANTLE=$(grep -cE 'filterIsInstance<GenericOpenAIPipe>\(\)' \
    server/src/main/kotlin/agent/runners/*.kt | awk -F: '{s+=$2}END{print s}')

# Post-fix expectation:
#   BEDROCK may drop (sites converted to `when` dispatch)
#   MANTLE rises to match via parallel narrative-throttler lines
#   BEDROCK == MANTLE is the steady-state invariant
```

If `BEDROCK != MANTLE` post-fix, you missed a callsite. The grep
result is the regression test.

## Pre-existing failure baselining on this kind of work

When the migration touches orchestrator tests, expect
pre-existing failures unrelated to your changes. The autogenesis
session surfaced 5 `SummitOrchestratorTest` failures (from missing
`GENERIC_OPENAI_API_KEY` env var in the test shell — same failure
mode as the mockk regression above) before any consumer-side change.

Baseline recipe (the one the `MantleStreamingE2ELiveTest` failure
post-mortem needs):

```bash
git stash --include-untracked
./gradlew :server:test --tests "<failing-class>"   # baseline on HEAD
git stash pop
```

If the failures reproduce bit-identically with the same exception
type and stack frame, they are pre-existing. Document them, attribute
to the prior baseline (the autogenesis handoff report from the
previous session listed 5× SummitOrchestratorTest as pre-existing),
and move on. Do NOT chase them as migration regressions.

## See Also

- `TPipe/src/main/kotlin/Pipe/StreamingCallbackBuilder.kt` — the
  lifted builder with both `add` overloads
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:438-535` —
  unified streaming setters
- `server/src/main/kotlin/org/ttt/autogenesis/server/AgentWorkStreamStreaming.kt` —
  the dispatch refactor in full
- `server/src/main/kotlin/agent/builders/writingAgent/ResponseRefinementAgent.kt` —
  multi-pipe Mantle agent with `connectionIds` self-registration
