# Hint-Injection Test Pattern

**Captured:** 2026-07-23 from the PumpStation path-safety rejection triage session.

## The Question

When the harness appends a hint to `turnHistory` (e.g., a path-safety rejection hint, a steering nudge, an empty-pathName hint), does that hint actually reach the LLM-facing input on the next dispatch? Three sub-possibilities to rule out:

1. The hint is appended to `turnHistory` but never makes it into the pipe's prompt context.
2. The hint reaches context but gets buried under accumulated entries.
3. The hint reaches context correctly and the LLM sees it, but ignores it.

## The Test Pattern

Build a `PumpStation` with a no-op path, append the hint to `turnHistory` directly (mirroring the production append site), then assert three things:

### Assertion 1: Hint is in `turnHistory` directly
```kotlin
station.turnHistory.add(
    ConverseData(
        role = ConverseRole.user,
        content = MultimodalContent(text = hintText)
    )
)
val matchingEntries = station.turnHistory.history.filter { turn ->
    turn.content.text?.contains("rejected by the path-safety gate") == true
}
assertEquals(1, matchingEntries.size)
assertTrue(matchingEntries[0].content.text!!.contains("too vague"))
```

### Assertion 2: Hint survives `buildTurnContent()` serialization
```kotlin
station.taskState.phase = PumpStationPhase.Dispatch
val content = station.buildTurnContent()
val userText = content.text
assertTrue(userText!!.contains("[CONVERSATION HISTORY]"))
assertTrue(userText.contains("rejected by the path-safety gate"))
assertTrue(userText.contains("Select a different path from the visible list"))
```

The `buildTurnContent()` function at `src/main/kotlin/Pipeline/PumpStationHelpers.kt:863` serializes `turnHistory` into a `[CONVERSATION HISTORY]` block embedded in the user-message text. If the hint survives that serialization, it reaches the LLM.

### Assertion 3: Visible paths metadata is populated alongside the hint
```kotlin
val visiblePaths = content.metadata["visiblePaths"]
assertNotNull(visiblePaths)
```

If the hint says "select a different path from the visible list" but `visiblePaths` is empty, the LLM has a hint but no menu.

## The Idempotency Gate (capture-current-behavior test)

Pin the current `alreadyNudged` gate at `PumpStation.kt:3025-3026` so any future change requires updating the test:

```kotlin
val productionGateSubstring = "rejected by the path-safety gate"
val alreadyNudged = station.turnHistory.history.any { turn ->
    turn.content.text?.contains(productionGateSubstring) == true
}
assertTrue(alreadyNudged, "After first hint is appended, alreadyNudged must be true")
```

The gate checks for the constant substring `"rejected by the path-safety gate"` (the unchanging tail of the marker), NOT the full marker string. Test must use the same substring to match production behavior.

## Imports

```kotlin
import com.TTT.Context.ConverseData       // NOT com.TTT.Pipe — the file is Context/ConverseData.kt
import com.TTT.Context.ConverseRole
```

## Live test reference

See `src/test/kotlin/Pipeline/PathSafetyHintInjectionTest.kt` (6 tests, all green as of 2026-07-24 — 4 original case-lookup + visibility tests, plus 1 end-to-end dispatch test and 1 reserve-reveal test added when the case-insensitive path-lookup fix landed). The "4 tests" count is stale in any prior transcript.

## Reserve-reveal test gotcha (added 2026-07-24)

When extending this test class to cover the reserve-path reveal flow (`revealWhen { _, _ -> true }`), the build will throw `IllegalArgumentException: At least one path is required` at `PumpStationDsl.kt:1097` if the test wires ONLY a `reservePath` and no `path`. The `pumpStation` builder's `build()` enforces "at least one path" before it even considers reserves — reserves are an additive layer, not a replacement.

**The shape that compiles and runs**:

```kotlin
val station = pumpStation("reserve-case-${System.nanoTime()}") {
    dispatchAgent = Pipeline()
    path("sentinel") {                              // ← MANDATORY: at least one normal path
        risk = PathRiskLevel.Low
        setExecutionFunction { content, _, _, _ -> content }
    }
    reservePath("hiddenOne") {
        risk = PathRiskLevel.Low
        revealWhen { _, _ -> true }
        setInternalAgent(SgTestAgent(agentTag = "..."))  // ← MANDATORY: reserve paths need an execution mechanism
    }
}
runBlocking { station.P2PInit() }
station.getPaths()  // ← MANDATORY: triggers the reserve-reveal loop in [getVisiblePathDescriptorsInternal]
val visible = station.getVisiblePathNames()
```

**Why `getPaths()` after `P2PInit()`**: `P2PInit()` (the public init) populates `pathDescriptors` but does NOT iterate reserve paths to call `revealWhen`. The reserve-reveal loop lives inside `getVisiblePathDescriptorsInternal()` (the private method called by `getPaths()` and `getVisiblePathDescriptorsForDispatch()`). If a test only calls `P2PInit()` and reads `getVisiblePathNames()`, the set stays empty. The shape above calls `getPaths()` (which is the public surface that triggers the internal reveal loop) to populate `revealedReservePaths` before the assertion.

**Why `setInternalAgent` is mandatory on a `reservePath`**: `PathObject.init()` throws `IllegalArgumentException: no execution mechanism configured` if the path has no `executionFunction`, `internalAgent`, `agentBuilderFunction`, or bound PCP function. `ReservePathBlock` does NOT have `setExecutionFunction` (only `PathBlock` does) — use `setInternalAgent(SgTestAgent(agentTag = "..."))` (the canonical `P2PInterface` impl in `PumpStationSetGetTest.kt:29`).

**Diagnostic recipe when a reserve-reveal test silently returns an empty visible list**:

1. Check whether `P2PInit()` ran. If `runBlocking { station.P2PInit() }` throws, the build is broken (most likely: missing sentinel normal path, or missing execution mechanism on the reserve path).
2. Check whether `getPaths()` was called. Without it, `revealedReservePaths` stays empty. Add `station.getPaths()` between `P2PInit()` and the `getVisiblePathNames()` call.
3. Check the trace HTML at `~/.tpipe/debug/trace/PumpStation/<testName>/pumpstation-*.html` for `PUMP_STATION_RESERVE_PATH_REVEALED` events. If absent, the reveal loop didn't run.

## Reuse for Other Hints

This pattern works for any hint type that flows through `turnHistory`:

- **Steering nudges** — `steerPersistent()` and `steer()` append to `turnHistory` via `injectSteeringForPhase`. Same `buildTurnContent()` serialization path. Test pattern identical.
- **Empty-pathName hints** — appended at `PumpStationLoop.kt:406-430`. Same path.
- **Kill-switch hints** — if any are appended to turnHistory, same path.

The pattern is: append → assert in history → assert in serialized text → assert metadata is populated alongside.
