# AgentCoroutineScope and the WorldManager Mutex — Orchestrator Pattern

Source: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/AgentCoroutineScope.kt` (5 lines) and the orchestrator-level state-mutation pattern in `gameplayOrchestrator.kt`.

This is the production convention for orchestrating 12-phase game turns safely under coroutines + state-mutation mutexes. The pattern has four parts that fit together; getting any one wrong serializes turns or corrupts state.

## Part 1 — AgentCoroutineScope (the shared coroutine scope)

```kotlin
// agent/builders/AgentCoroutineScope.kt
package agent.builders

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

object AgentCoroutineScope
{
    val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
}
```

Five lines. Three properties:

- `object` (Kotlin singleton) — application-wide, one instance.
- `SupervisorJob` — failure of one child coroutine does NOT cancel siblings. Critical for parallel builders where one failing shouldn't kill the others.
- `Dispatchers.Default` — CPU-bound pool. LLM orchestration is mostly thread-blocking on the wire, but the surrounding orchestration work is CPU-bound (content transformation, JSON parsing, world snapshot diffing).

The scope is used by builders that need to launch parallel sub-work without holding the orchestrator's coroutine. Most production builders don't launch anything — they just return a `Pipeline`. The scope exists for the cases where a builder needs to fan out across multiple pipes asynchronously.

## Part 2 — per-orchestrator coroutineScope (the turn scope)

```kotlin
// gameplayOrchestrator.kt:phase entry
suspend fun runGameplayTurn(player: Player, turnAction: String) {
    val worldSnapshot = WorldManager.withMutex { world.copy() }  // ← read under mutex, work outside

    coroutineScope {                                              // ← structured concurrency
        val classificationDeferred = async { classifyAction(turnAction) }
        val playTypeDeferred = async { detectPlayType(turnAction, worldSnapshot) }
        val validatorDeferred = async { validateAction(turnAction, worldSnapshot) }

        val classification = classificationDeferred.await()
        val playType = playTypeDeferred.await()
        val validatorResult = validatorDeferred.await()

        // ... sequential phases that depend on the above
    }
}
```

Each turn gets its own `coroutineScope` for structured concurrency. If any phase throws, the scope cancels its siblings and propagates the failure. The orchestrator's caller sees the failure as a normal exception.

The `async { ... }.await()` pattern is the canonical way to run independent phases in parallel. `coroutineScope` is preferred over `AgentCoroutineScope.scope.launch(...)` because:

1. **Structured concurrency** — the parent waits for all children. No fire-and-forget.
2. **Failure propagation** — one child's exception cancels siblings and reaches the parent.
3. **Cancellation** — when the orchestrator's parent is cancelled, all `async` children are cancelled.

`AgentCoroutineScope` is reserved for cross-turn work (background tasks that outlive a single turn, like audio track scheduling).

## Part 3 — WorldManager mutex (state-mutation serialization)

```kotlin
// worldState/WorldManager.kt (pattern)
class WorldManager {
    private val mutex = Mutex()
    private var world: World = loadDefaultWorld()

    suspend fun <T> withMutex(block: suspend () -> T): T = mutex.withLock(block)

    suspend fun commitWorldUpdate(updates: WorldUpdates) {
        mutex.withLock {
            world = world.apply(updates)
            serializeWorldForCloudSave(world)
        }
    }
}
```

The mutex is held ONLY for state mutation. The pattern is:

1. **Take a snapshot under the mutex at the start of the turn.**
2. **Release the mutex.**
3. **Run all LLM calls against the snapshot (no mutex held).**
4. **Re-acquire the mutex to commit the final world state.**

```kotlin
// CORRECT — snapshot, work, commit
suspend fun runTurn() {
    val snapshot = WorldManager.withMutex { world.copy() }    // ← brief mutex hold
    // ... 30s of LLM calls, no mutex ...
    WorldManager.commitWorldUpdate(buildUpdates(snapshot))    // ← brief mutex hold
}

// WRONG — mutex held for entire turn
suspend fun runTurn() {
    WorldManager.withMutex {
        // ... 30s of LLM calls, mutex held the entire time ...
        world = world.apply(updates)
    }
}
```

The wrong pattern serializes all turns — turn B cannot start until turn A's LLM calls finish. This is the #1 cause of "the game feels slow" reports.

## Part 4 — Retry-swaps and runtime pipe mutation

```kotlin
// gameplayOrchestrator.kt:retry-swap pattern
private suspend fun classifyWithRetry(content: MultimodalContent): Classification {
    val primary = createUserActionClassificationPipeline()  // qwen235B
    val fallback = createFallbackClassifier()                // haiku or gemma31

    return try {
        withTimeoutOrNull(180_000) { primary.execute(content) }
            ?: throw TimeoutException()
    } catch (e: Exception) {
        Logger.warn(LogCategory.SYSTEM, "primary classifier failed, swapping to fallback")
        withTimeoutOrNull(180_000) { fallback.execute(content) }
            ?: throw TimeoutException("fallback classifier failed too")
    }
}
```

The retry-swap pattern:

1. Try the primary (high-quality model, longer timeout).
2. On exception OR timeout, build a NEW pipeline with a fallback model.
3. Try the fallback (cheaper model, same timeout).
4. If fallback also fails, surface to the user.

The retry-swap does NOT mutate the existing pipeline — it builds a fresh one. Mutating a pipe mid-execution is unsafe (TPipe explicitly forbids it; see `tpipe-pipe-internals` for the threading rules).

## What this pattern is NOT

- **Not a synchronization primitive across JVMs.** `WorldManager` is a single-process singleton. Multi-JVM coordination uses `P2PHostedRegistry`, not a local mutex.
- **Not a queue.** Concurrent turns are not queued; they are serialized by the mutex. The convention is: one turn at a time, with the snapshot pattern minimizing mutex hold time.
- **Not a transaction.** If a phase fails mid-turn, the orchestrator may commit a partial world update. For game turns this is usually fine (the world just stays in its pre-turn state if the orchestrator fails before commit). For financial transactions this would be wrong — use a real transaction system.

## Common gotchas

### Gotcha 1 — holding the mutex during async pipe.execute()

```kotlin
// WRONG — mutex held for entire 30s of LLM work
WorldManager.withMutex {
    val validatorResult = validatorPipeline.execute(content)  // 30s of LLM calls
    world = world.apply(updates)
}
```

Fix: snapshot first, work outside the mutex.

### Gotcha 2 — using `GlobalScope.launch { ... }` instead of `coroutineScope { ... }`

```kotlin
// WRONG — fire-and-forget, no parent cancellation
GlobalScope.launch {
    val classification = async { classifyAction(turnAction) }
    // ... never awaited, structured concurrency violated ...
}
```

Fix: use `coroutineScope { ... }` so the parent waits and cancellation propagates.

### Gotcha 3 — sharing a pipeline instance across concurrent turns

```kotlin
// WRONG — two turns sharing the same pipeline
val sharedPipeline = createUserActionClassificationPipeline()
async { turn1(sharedPipeline) }
async { turn2(sharedPipeline) }  // ← pipe.execute is not re-entrant-safe
```

Fix: each turn builds its own pipeline instance. The builder function is cheap; calling it twice per turn is fine.

### Gotcha 4 — forgetting to call `pipeline.init()` before `execute()`

```kotlin
// WRONG — pipe.execute throws because init() was skipped
val pipeline = builder()
pipeline.execute(content)  // throws NullPointerException on bedrockClient
```

Fix: the orchestrator calls `.init()` after building, before execute. See `tpipe-pipeline-patterns` for the lifecycle contract.

### Gotcha 5 — using `runBlocking` inside a `suspend fun`

```kotlin
// WRONG — blocks the calling thread
suspend fun runTurn() {
    runBlocking { pipeline.execute(content) }  // ← blocks the coroutine thread
}
```

Fix: `pipeline.execute(content)` is already a `suspend fun`; just `await` it.

## Verification recipe

After writing a new orchestrator, run this verification:

```bash
# 1. Confirm no GlobalScope usage
grep -n "GlobalScope" server/src/main/kotlin/agent/runners/*.kt
# Expected: 0 matches.

# 2. Confirm WorldManager.withMutex is used (not direct mutex access)
grep -nE "WorldManager\.withMutex|mutex\.withLock" server/src/main/kotlin/agent/runners/*.kt
# Expected: every state mutation goes through withMutex.

# 3. Confirm withTimeoutOrNull wraps every pipe.execute
grep -nE "pipe\.execute|pipeline\.execute" server/src/main/kotlin/agent/runners/*.kt -A 1 | grep -E "withTimeout|withTimeoutOrNull"
# Expected: every execute is inside a withTimeout block.

# 4. Confirm pipeline.init() is called
grep -nE "\.init\(\)" server/src/main/kotlin/agent/runners/*.kt
# Expected: every build*Pipeline() result is followed by .init() before execute.
```

## See also

- `tpipe-pipeline-patterns` — the `.init()` lifecycle contract and the `Pipeline.init()` signature
- `tpipe-pipe-internals` — pipe threading rules (why mutating a pipe mid-execution is forbidden)
- `tpipe-ditl-hook-design` — the runner-level `failureFunction` and `validationFunction` hooks for Manifold containers