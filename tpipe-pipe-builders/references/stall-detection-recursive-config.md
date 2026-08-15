# Recursive TPipe stall-detection configuration

## Why pipeline-level propagation is not enough

`Pipeline.enableStallDetector(config, callback)` at `TPipe/src/main/kotlin/Pipeline/Pipeline.kt:724-733`
only flips the flag on every pipe in `pipeline.getPipes()`. The
in-tree comment at `Pipeline.kt:1217-1226` is explicit:

> Apply pipeline-level stall detection settings if enabled.
> Note: stall detection does NOT recursively cascade by default —
> each pipe owns its own `StreamingStallDetector` since per-pipe
> stats need per-pipe state. The config and callback are simply
> propagated to every child.

The "every child" wording is misleading: the propagation walks the
same entry list the timeout propagation walks — meaning reasoning,
validator, branch, and transformation pipes installed via
`setReasoningPipe` / `setValidatorPipe` / `setTransformationPipe` /
`setBranchPipe` (`Pipe.kt:1683-1711`) are NOT reached.

Verified on the 2026-08-02 autogenesis rollout: relying on
`Pipeline.enableStallDetector` left these pipes unprotected:

- `reversal-pipe`'s `mantle structured cot (gemma4ModelId)` reasoning child
- `defensive legality checker pipe`'s `qwen validator pipe (flex host, standard reasoning)` validation chain
- `mantle npc karma pipe (g31b)`'s `Refusal Detection Karma (mantle g31b fallback)` branch child

Each is a known stall-prone site from the live trace audit
(see `~/.tpipe/debug/trace/Round_*_Turn_*/NPC_Judge/trace.json` — see
`PIPE_FAILURE` events trace-event-4340, trace-event-4347, trace-event-4348).
A pipeline-level call would have looked correct at compile time and
in the JUnit suite, but the reasoning/branch children would have kept
silently dying without a retry.

## Fix shape

Add a global helper on the consumer's config singleton (e.g.
`BedrockConfig` in autogenesis) that walks the public child graph with
cycle protection and calls `enableStallDetector` on every node:

```kotlin
import com.TTT.Pipe.StreamingStallConfig
import com.TTT.Pipe.StallCallback
import com.TTT.Pipeline.Pipeline
import java.util.IdentityHashMap

val gameplayStallDetectorConfig = StreamingStallConfig(
    windowSize = 50,
    stddevMultiplier = 3.0,
    stallMinSilenceMs = 10_000L,
    maxStallRetries = 3,
    warmupTokenCount = 20,
)

fun configureGameplayStallDetection(
    pipeline: Pipeline,
    callback: StallCallback? = null,
): Pipeline {
    val visited = IdentityHashMap<Pipe, Boolean>()
    pipeline.getPipes().forEach { pipe ->
        walkAndConfigure(pipe, callback, visited)
    }
    return pipeline
}

private fun walkAndConfigure(
    pipe: Pipe,
    callback: StallCallback?,
    visited: IdentityHashMap<Pipe, Boolean>,
) {
    if (visited.put(pipe, true) != null) return
    pipe.enableStallDetector(gameplayStallDetectorConfig, callback)
    listOfNotNull(
        pipe.validatorPipe,
        pipe.transformationPipe,
        pipe.branchPipe,
        pipe.reasoningPipe,
    ).forEach { child ->
        walkAndConfigure(child, callback, visited)
    }
}
```

Key constraints to preserve:

1. **`IdentityHashMap<Pipe, Boolean>` for cycle protection.** `Pipe.pipeId`
   is declared `protected var` on `Pipe`, so consumers cannot reach it
   from outside the package. Using `IdentityHashMap` keeps the cycle
   check on object identity, which is what TPipe itself uses elsewhere
   (e.g. `StreamingCallbackManager` dedup at
   `TPipe/src/main/kotlin/Pipe/StreamingCallbackManager.kt:40-50`).
2. **Apply the helper before `init(true)`.** TPipe's streaming stall
   detector is installed lazily in `execute(...)` via
   `Pipe.kt:6189-6211`, but the children get visited during `init(...)`
   when `validatorPipe` etc. are walked by framework callbacks. Calling
   the helper inside the same `.apply { ... }` block as `enablePipeTimeout`
   guarantees the policy lands on every node before the first
   `execute()` call.
3. **Stay generic.** Both `BedrockMultimodalPipe` (Bedrock) and
   `GenericOpenAIPipe` (Mantle) extend `com.TTT.Pipe.Pipe`, so the same
   recursion covers both providers. No `when (pipe) { is BedrockPipe -> ...; is GenericOpenAIPipe -> ... }`
   dispatch is needed — that would re-introduce the silent-drop bug
   that previously hid Mantle pipes from Bedrock-only helpers.

## TDD recipe — `DummyPipe`-based recursive-coverage test

The companion test that pins the helper against a deliberately shared
child to detect the no-rewrite regression. Lives at
`server/src/test/kotlin/globals/BedrockConfigStallDetectionTest.kt`:

```kotlin
class BedrockConfigStallDetectionTest {

    @Test
    fun `configures every reachable child pipe once and preserves runtime settings`() {
        val root = DummyPipe().apply {
            setPipeName("root")
            enablePipeTimeout(duration = 1234L, autoRetry = true, retryLimit = 7)
        }
        val validator = DummyPipe().apply { setPipeName("validator") }
        val transformation = DummyPipe().apply { setPipeName("transformation") }
        val branch = DummyPipe().apply { setPipeName("branch") }
        val reasoning = DummyPipe().apply { setPipeName("reasoning") }
        val nested = DummyPipe().apply { setPipeName("nested") }
        val shared = DummyPipe().apply { setPipeName("shared") }

        root.validatorPipe = validator
        root.transformationPipe = transformation
        root.branchPipe = branch
        root.reasoningPipe = reasoning
        validator.reasoningPipe = nested
        transformation.branchPipe = shared
        branch.validatorPipe = shared
        reasoning.transformationPipe = nested
        nested.branchPipe = root

        val pipeline = Pipeline().add(root)
        val callback: suspend (com.TTT.Pipe.StallEvent) -> Unit = { }

        assertSame(pipeline, BedrockConfig.configureGameplayStallDetection(pipeline, callback))

        val expected = BedrockConfig.gameplayStallDetectorConfig
        listOf(root, validator, transformation, branch, reasoning, nested, shared).forEach { pipe ->
            assertTrue(pipe.enableStallDetector, pipe.pipeName)
            assertEquals(expected, pipe.stallDetectorConfig, pipe.pipeName)
            assertNotNull(pipe.stallCallback, pipe.pipeName)
            assertFalse(pipe.streamingEnabled, pipe.pipeName)
        }
        assertEquals(1234L, root.pipeTimeout)
        assertEquals(7, root.maxRetryAttempts)
    }
}
```

Why each assertion matters:

- `assertTrue(pipe.enableStallDetector)` — pins that the flag actually
  flipped on each reachable node. Without `IdentityHashMap` dedup this
  would still pass on a single-traversal helper; with a non-idempotent
  re-traversal helper it would also pass. The next assertion (a real
  `callback` setter) proves the dedup is real.
- `assertEquals(expected, pipe.stallDetectorConfig)` — pins the
  *value*, not just the flag. A helper that flips `enableStallDetector`
  with `StreamingStallConfig()` defaults would pass the first
  assertion and silently miss the operator-chosen thresholds.
- `assertNotNull(pipe.stallCallback)` — pins that the same callback
  instance reached every node, which proves the helper recursed
  rather than re-applying. A helper that took a fresh callback per
  node would pass the first three assertions and fail this one.
- `assertFalse(pipe.streamingEnabled)` — pins that the helper does
  not change transport behavior. A naïve "also enable streaming while
  we're here" shortcut would silently expand the rollout surface.
- `assertEquals(1234L, root.pipeTimeout)` and
  `assertEquals(7, root.maxRetryAttempts)` — pin that the helper
  preserves the existing timeout configuration. A helper that
  re-applies `enablePipeTimeout` with defaults would silently change
  orchestrator timeout semantics.

The graph deliberately shares `shared` and `nested` between siblings,
and `nested.branchPipe = root` creates a cycle through the entry pipe.
If the `IdentityHashMap.put` cycle guard regresses, `shared` is
configured twice and the callback assertion fails — exactly the
silent-double-configure regression a real production helper would
suffer.

## Orchestrator wiring rule

Apply the helper inside every `.apply { ... }` block that ends in
`init(true)` for an LLM-driven pipeline. The 2026-08-02 autogenesis
audit covered:

- `gameplayOrchestrator.kt` — 24 of 24 `init(true)` sites
- `npcOrchestrator.kt` — 10 of 10 `init(true)` sites

Coverage verification recipe (paste into a Python script run from the
repo root):

```python
from pathlib import Path
out = {}
for name in ("gameplayOrchestrator.kt", "npcOrchestrator.kt"):
    lines = (Path("server/src/main/kotlin/agent/runners") / name).read_text().splitlines()
    misses = []
    for i, line in enumerate(lines):
        if "init(true)" in line:
            window = "\n".join(lines[max(0, i - 28): i + 1])
            if "configureGameplayStallDetection" not in window:
                misses.append(i + 1)
    out[name] = {
        "init_true_count": sum("init(true)" in l for l in lines),
        "helper_count": sum("configureGameplayStallDetection" in l for l in lines),
        "uncovered_init_lines": misses,
    }
print(out)
```

Expected output (after the helper is wired everywhere):

```python
{
  "gameplayOrchestrator.kt": {"init_true_count": 24, "helper_count": 24, "uncovered_init_lines": []},
  "npcOrchestrator.kt":      {"init_true_count": 10, "helper_count": 10, "uncovered_init_lines": []},
}
```

Any non-empty `uncovered_init_lines` means a builder was missed —
most likely an `init(true)` followed immediately by a streaming
callback or a result sink where `BedrockConfig.configureGameplayStallDetection(this)`
slipped out of the patch.

## Why this is not a "behavior change"

The helper is an additive policy application. It does not:

- enable streaming (`streamingEnabled` stays at its caller-set value)
- change timeout values, retry limits, or `pipeRetryFunction`
- change `setStreamingCallback` registration
- inject new content or system prompt text

The only observable new behavior is that a stall — defined per
`StreamingStallDetector.kt:88-99` as a silence exceeding
`max(mean + stddevMultiplier × stddev, stallMinSilenceMs)` — will
trigger `PipeTimeoutManager.handleStallSignal(pipe, content, stallEvent)`
followed by `abort()` on the in-flight stream. The retry path is
identical to the existing timeout retry: snapshot restore, set
`repeatPipe=true`, re-execute. Operators who want fewer stall retries
can override `stallDetectorConfig` at the call site after the helper
runs, or pass a different `StreamingStallConfig` into a
builder-specific wrapper.

## When the helper does NOT cover something

The helper covers TPipe pipe-to-pipe recursion. It does NOT cover:

- Manifold/Junction/DistributionGrid container entries — those go
  through their own worker registration and have separate streaming
  setup. For container-level stall detection, register a
  `StreamingCallback` whose `onTokenReceived` callback walks the
  worker pipe graph the same way this helper does.
- Pipes that aren't `Pipe` instances — `P2PInterface` references
  inside Manifold worker slots register through
  `P2PRegistry.sendP2pRequest` and never reach this helper.
- Pipes the orchestrator builds but never runs (no `init(true)`) —
  the helper has nothing to attach to. If a builder constructs a pipe
  for side effects (e.g. populating `ContextBank`), the helper is
  unnecessary because the pipe never executes.