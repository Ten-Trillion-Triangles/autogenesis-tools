# Defect 28 — LLM stuck on a non-existent path bypasses every loop guard (BUG B, FIXED 2026-07-24)

**Status:** ✅ FIXED 2026-07-24 — fix landed on `main` in commits `e9e22b64` (test RED), `06eb0935` (state + DSL surface), `e1aa3dc4` (runPathFlow wiring).
**Severity:** MEDIUM-HIGH (was) — now CLOSED.
**Source:** `Pipeline/PumpStationLoop.kt:700-720` (`runPathFlow` UnknownPath branch) and `Pipeline/PumpStation.kt:1760-1762, 1855-1861` (new state fields).

## Symptom (pre-fix)

The dispatch LLM in live-04 trace (2026-07-24) dispatched `giveUp` 19 times in a row, every dispatch failed with `PumpStationError.UnknownPath, errorMessage="Path 'giveUp' not found"`, harness exited with `PumpStationExitReason.MaxTurnsHit, status=Failed`. Bug A (case-insensitive lookup) made `giveUp` resolvable, but the second-order bug is broader: **any name with no registered path** (e.g. `flarble`, a hallucinated name, a typo) hits the same failure mode and the harness loops to `MaxTurnsHit`.

The existing `maxConsecutiveSamePath` loop guard (`PumpStation.kt:3047-3093`) does NOT catch this. `consecutivePathCount` only increments on resolved paths (after `lastSelectedPathName` is updated), so 100 consecutive `flarble` dispatches leave `consecutivePathCount = 0`. The LLM is stuck in an unbounded retry loop, and the harness has no termination signal for the "stuck on unknown path" failure mode.

## Root cause (post-Bug-A fix verified on 2026-07-24)

`runPathFlow` at `PumpStationLoop.kt:700` emits `PathFailed(error=UnknownPath, ...)` and returns `null` for any non-resolved dispatch. The dispatch loop at `runTurn` (`PumpStationLoop.kt:2864`) sees `pathResult == null`, continues to the next turn, never touches the loop-guard machinery:

```kotlin
// Pre-fix runPathFlow UnknownPath branch
if (path == null) {
    emitEventInternal(PathFailed(... error = UnknownPath ...))
    taskState.latestContent = MultimodalContent(text = buildLlmErrorMessage(UnknownPath, ...))
    return null  // ← no loop-guard accounting
}
```

The `alreadyNudged` dedup at the **path-safety** hint site (`PumpStation.kt:3037-3052`) prevents duplicate `[Path Safety]` hints, but the **UnknownPath** branch has no equivalent hint-with-dedup, no counter, no exit signal. The LLM gets one error message (turn 0), then silence (turns 1-18) — no further guidance, no escape hatch.

## Fix applied (2026-07-24)

Add a new loop guard `maxConsecutiveUnknownPaths: Int?` (default `null` = unbounded, preserves today's behavior for all existing test sites). The wiring mirrors the existing `maxConsecutiveSamePath` trip at `PumpStation.kt:3074-3098`:

1. **State surface** (`PumpStation.kt:1760-1762, 1855-1861`):
   ```kotlin
   private var maxConsecutiveUnknownPaths: Int? = null
   internal var consecutiveUnknownPathCount: Int = 0
   ```
   The counter is `internal var` (not `private var`) because the writer is a helper function in `PumpStationLoop.kt`, not a member of `PumpStation`. Internal accessors via `maxConsecutiveUnknownPathsInternal` for tests in the same module (mirroring the `consecutivePathCountInternal` pattern at `PumpStation.kt:2549-2550`).

2. **DSL surface** (`PumpStationDsl.kt:558-565, 1041, 1239`):
   - `var maxConsecutiveUnknownPaths: Int? = null` field declaration adjacent to `maxTotalPathCallsPerPath` (`PumpStationDsl.kt:557`).
   - `copyFrom` preservation line at `PumpStationDsl.kt:1041` — **Pitfall 8** (the `xxxConfiguration = source.xxxConfiguration` silent-drop bug). Without this line, a `pumpStation { maxConsecutiveUnknownPaths = N; path("name") { } }` build silently loses the guard because `path()` promotes the initial builder.
   - `build()` integration via `setMaxConsecutiveUnknownPaths(maxConsecutiveUnknownPaths)` at `PumpStationDsl.kt:1239`, chained after the existing `.setMaxConsecutiveSamePath(...)` and `.setMaxTotalPathCallsPerPath(...)` calls.
   - `setMaxConsecutiveUnknownPaths(max: Int?): PumpStation` setter at `PumpStation.kt:4221-4229` — the public setter on `PumpStation` for the DSL to call.

3. **Counter wiring** (`PumpStationLoop.kt:720-771`):
   - **Increment** on every UnknownPath outcome: `consecutiveUnknownPathCount += 1`.
   - **Trip** when `maxConsecutiveUnknownPaths != null && consecutiveUnknownPathCount >= limit`: emit `LoopGuardTripped(guard="maxConsecutiveUnknownPaths", metric="consecutive", observed, limit)`, set `taskState.lastError = LoopGuardTriggered`, `taskState.exitReason = LoopGuardTripped`, mark `taskState.latestContent.terminatePipeline = true`, **reset the counter to 0** (so a subsequent run on a different station doesn't inherit the streak), and return a non-null `MultimodalContent` with `terminatePipeline = true` so the existing `runTurn` halt path at `PumpStationLoop.kt:2897-2900` stops the harness.
   - **Reset on every resolved path**: `consecutiveUnknownPathCount = 0` at the top of the `path != null` branch. An alternating `flarble` / `realPath` / `flarble` / `realPath` pattern is fine (forward progress); only an unbroken streak trips the guard.

## Trip mechanic — mirrors maxConsecutiveSamePath

```kotlin
// PumpStationLoop.kt:720-771 (post-fix)
if (path == null) {
    emitEventInternal(PathFailed(... error = UnknownPath ...))
    taskState.latestContent = MultimodalContent(text = buildLlmErrorMessage(UnknownPath, ...))
    consecutiveUnknownPathCount += 1
    val limit = maxConsecutiveUnknownPathsInternal
    if (limit != null && consecutiveUnknownPathCount >= limit) {
        emitEventInternal(LoopGuardTripped(
            runId = taskState.runId,
            turnIndex = taskState.turnIndex,
            guard = "maxConsecutiveUnknownPaths",
            pathName = request.pathName,
            detail = "consecutive=$consecutiveUnknownPathCount, limit=$limit",
            metric = "consecutive",
            observed = consecutiveUnknownPathCount,
            limit = limit
        ))
        emitEventInternal(PathFailed(
            runId = taskState.runId,
            turnIndex = taskState.turnIndex,
            phase = PumpStationPhase.PathExecution,
            pathName = request.pathName,
            riskLevel = PathRiskLevel.Low,
            error = PumpStationError.LoopGuardTriggered,
            errorMessage = "maxConsecutiveUnknownPaths exceeded for path '${request.pathName}'"
        ))
        taskState.latestContent = (taskState.latestContent ?: MultimodalContent())
            .also { it.terminatePipeline = true }
        taskState.lastError = PumpStationError.LoopGuardTriggered
        taskState.exitReason = PumpStationExitReason.LoopGuardTripped
        consecutiveUnknownPathCount = 0
        return MultimodalContent(text = request.pathName)
            .also { it.terminatePipeline = true }
    }
    return null
}
consecutiveUnknownPathCount = 0  // resolved path — reset the streak
```

**Return shape**: non-null `MultimodalContent` with `terminatePipeline = true`, NOT a custom error object. This matches the existing `maxConsecutiveSamePath` trip at `PumpStation.kt:3093-3098` which returns `input` and lets the runTurn halt path at `PumpStationLoop.kt:2897-2900` (`if (pathResult.terminatePipeline) return TurnResult.Halt(...)`) do the halt. **Critical pitfall** (captured 2026-07-24 during the fix): if you return `null` from the trip path (or return a content without `terminatePipeline`), `runTurn` sees `pathResult == null` and continues to the next turn — the trip is silently a no-op. The test `PumpStationUnknownPathLoopGuardTest::consecutive UnknownPath dispatches halt the harness when limit is set` pins this contract.

## Why `internal var` not `private var` + `var` accessor

`PumpStationLoop.kt:runPathFlow` (helper function, not member of `PumpStation`) needs to MUTATE `consecutiveUnknownPathCount`. The existing `consecutivePathCount` is `private var` and only mutated within the `PumpStation` class (in `invokePath` at `PumpStation.kt:3100-3105`). The unknown-path counter must be mutated from a different file, so the access pattern is different.

**Two options**:
1. `private var consecutiveUnknownPathCount: Int = 0` + `internal val consecutiveUnknownPathCountInternal: Int get() = ...` (the val-only accessor, mutator is a separate setter helper method). This is verbose and the existing `consecutivePathCountInternal` pattern matches it for read access. But for WRITE access, you need either (a) a setter helper method, or (b) change to a `var` accessor.
2. `internal var consecutiveUnknownPathCount: Int = 0` — directly mutable from sibling files in the same module. Smaller surface, no setter helper, no access dance.

Option 2 was the right choice for the Bug B fix (commit `e1aa3dc4`). The original commit `06eb0935` used option 1 with a separate `internal val` accessor, but the test class couldn't write to the counter from outside the class, which broke the test. **Generalization** (for future loop-guard state fields that need cross-file mutation): prefer `internal var` over `private var` + accessor when the writer is a helper function in a sibling file. The `private` → `internal` change is a single keyword; the accessor + setter helper pattern is 3 lines of boilerplate that doesn't pay for itself.

**When to use the accessor pattern instead**: when the field is read by tests but only written from within the class (e.g. `consecutivePathCount` is read by `consecutivePathCountInternal` from the test, but only written by `invokePath` which is a member of `PumpStation`). The accessor is the correct read-only-from-outside-the-class surface; mutating from a different file is the rare case that needs `internal var`.

## Test contract (`src/test/kotlin/Pipeline/PumpStationUnknownPathLoopGuardTest.kt`)

4 tests, all green:

1. `consecutive UnknownPath dispatches halt the harness when limit is set` — 3 dispatches with `maxConsecutiveUnknownPaths = 3`, asserts the third returns non-null with `terminatePipeline = true`, `taskState.exitReason == LoopGuardTripped`, `taskState.lastError == LoopGuardTriggered`.
2. `counter resets when a resolved path runs` — 2 UnknownPath dispatches, then 1 resolved, asserts counter at 0; then 3 more UnknownPath dispatches, asserts the third trips (confirms reset is real, not state leak).
3. `null maxConsecutiveUnknownPaths preserves unbounded behavior` — 5 UnknownPath dispatches with no guard, asserts all return null, counter accumulates to 5, exitReason stays null (preserves today's behavior).
4. `guard trip event names the dispatched path` — `maxConsecutiveUnknownPaths = 1`, asserts the emitted `LoopGuardTripped` event has `guard = "maxConsecutiveUnknownPaths"`, `pathName = "specificName"` (the actual dispatched name), `observed = 1`, `limit = 1`. Uses the `eventObserver` callback to capture events (NOT `PipeTracer.getAllTraces()` — that requires `enableTracing()` and is not necessary for unit testing the guard's behavior).

## Verification

`PumpStationUnknownPathLoopGuardTest` (4 tests): all green.
`PumpStationPathCaseInsensitiveTest` (6 tests, Bug A fix): all green — Bug A and Bug B fixes are independent.
`PathSafetyHintInjectionTest` (4 tests): all green — the prior-session hint-flow contract unaffected.
13 non-live `com.TTT.Pipeline.PumpStation*` test classes (≈140 tests): all green — no regressions from the new state field or DSL surface.

**Hermes-verify receipt**: `/tmp/hermes-verify-pumpstation-case-fix.sh` 9/9 PASS (updated to include `PumpStationUnknownPathLoopGuardTest`).

## Cross-references

| Related | Why |
|---|---|
| `harness-defect-catalog.md` Defect 11 (loop-guard fires before path-safety) | Same loop-guard trip mechanic (LoopGuardTripped event + LoopGuardTriggered error + LoopGuardTripped exitReason + terminatePipeline propagation), but for a different failure surface (path-safety rejection vs UnknownPath) |
| `harness-defect-catalog.md` Defect 13 (LoopGuardTripped meta-key split) | Reuses the additive `metric` / `observed` / `limit` fields added by Defect 13 — the new `maxConsecutiveUnknownPaths` trip sets these the same way |
| `references/case-insensitive-path-registry.md` | Bug A's case-insensitive fix made `giveUp` (mixed-case path) resolvable. Bug B's loop guard protects against the failure mode that surfaces when Bug A's fix isn't enough (LLM picks a name that has no registered path at all) |
| `pump-station/SKILL.md` "Adding a new DSL block to `PumpStationBuilder` (recipe, added 2026-07-23)" | The same 5-anchor pattern (field + copyFrom + build() + setter) applies to every new DSL field including this one |
| `pump-station/SKILL.md` "Path-name case-insensitive registry" | Bug A's lesson on the map-key boundary contract — the same shape applies to the loop-guard registry: insert and lookup must use the same normalization, or the harness drifts |
| `pump-station/SKILL.md` "Sandbox-tuned TDD recipe" | The unit-test pivot pattern — drive `runPathFlow` directly (the patched helper), skip the `executeLocal` chain that hits the kotlinx-serialization compiler-plugin wall |

## How to add a similar loop guard in the future

The pattern is mechanical — 5 sites, all matching the existing `maxConsecutiveSamePath` shape:

1. **State field** on `PumpStation` (private if only same-class mutation; `internal var` if cross-file mutation needed).
2. **DSL field** on `PumpStationBuilder` with the `copyFrom` preservation line (Pitfall 8) and `build()` integration via a `setXxx(value)` setter.
3. **Setter** on `PumpStation` for the DSL to call.
4. **Counter + trip wiring** in the relevant helper (the dispatch site, NOT the post-fact evaluation site). The trip is symmetric to the existing `maxConsecutiveSamePath` trip: emit `LoopGuardTripped(guard, pathName, detail, metric, observed, limit)`, set `lastError = LoopGuardTriggered`, `exitReason = LoopGuardTripped`, mark `latestContent.terminatePipeline = true`, return non-null with `terminatePipeline = true` so the runTurn halt path stops the harness.
5. **Test** that pins the trip contract: `assertTrue(result.terminatePipeline)`, `assertEquals(exitReason, ...)`, `assertEquals(lastError, ...)`. Plus a `null` default test that confirms unbounded behavior is preserved.

If the new guard needs cross-file mutation (the counter increments in a helper function, not a `PumpStation` member function), the field is `internal var` not `private var` — see "Why `internal var` not `private var`" above. This is the only case where the new guard diverges from the `maxConsecutiveSamePath` pattern, which is fully PumpStation-internal.
