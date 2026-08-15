# Stub-test failure modes for the post-goal hook (added 2026-07-24)

A `PUMP_STATION_POST_GOAL_COMPLETED` assertion in a stub-mode PumpStation test can fail for any of three distinct reasons. The error message alone doesn't disambiguate. The right diagnostic is to check which layer actually executed.

## Layer 1: Wire shape (parser-format mismatch)

**Symptom**: `P2PException: Failed to deserialize OpenAI Responses body: {raw snippet}` on the first LLM call.

**Cause**: Stub server returned a non-envelope body. The strict `OpenAIResponsesResponseParser` (`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/OpenAIResponsesResponseParser.kt:73`) requires the full wire shape: `id`, `object`, `created_at`, `status`, `model`, plus a polymorphic `output` list of typed items. A raw snippet like `{"path":"report"}` deserializes to `null` and trips this branch.

**Fix**: Add a `stubResponsesJson(text: String): String` helper that wraps arbitrary content in a valid envelope:

```kotlin
private fun stubResponsesJson(text: String): String
{
    val escaped = text.replace("\\", "\\\\").replace("\"", "\\\"")
    return """{"id":"stub-resp","object":"response","created_at":0,"status":"completed","model":"stub","output":[{
        "type":"message",
        "role":"assistant",
        "content":[{"type":"output_text","text":"$escaped"}]
    }]}"""
}
```

Refactor every `loopEnqueue(role) { """{...}""" }` call site and the existing `stubJson(...)` helper to route through it.

See also the prior `Stub-server wire-shape fixtures` section in the main SKILL.md body for the full recipe and the chat-completions-mode history.

## Layer 2: Dispatch contract field name

**Symptom**: Layer 1 is gone (no more `Failed to deserialize`), HTML is now 500KB+ (real harness ran), but `PUMP_STATION_POST_GOAL_COMPLETED` still missing.

**Cause**: Stub returns a valid envelope but the dispatch JSON inside uses `{"path":"..."}` instead of `{"pathName":"...","inputData":{...}}`. `parseDispatchOutput` at `PumpStationHelpers.kt:639` deserializes into `PathRequest(pathName, pathSchema, pathSelectionRationale)`. A wrong-field-name payload silently produces a default-initialized `PathRequest` with empty `pathName`, which `isDefault()` rejects → returns `null` → repair exhaustion.

**Fix**: Update the dispatch payload to match the contract documented in `PumpStationDefaults.kt:46-64`:

```kotlin
// Wrong (Layer 2 trap)
stub.loopEnqueue("dispatch") { stubResponsesJson("""{"path":"report"}""") }

// Right
stub.loopEnqueue("dispatch") { stubResponsesJson("""{"pathName":"report","inputData":{}}""") }
```

The dispatch prompt requires `pathName` (the exact visible-path name) and `inputData` (path-specific input). Field names other than `pathName` silently produce an empty `PathRequest`.

## Layer 3: Termination signal never fires

**Symptom**: HTML contains the dispatch and path-safety events but `PUMP_STATION_POST_GOAL_COMPLETED` is still missing; the harness exits with `MaxTurnsHit` and `Failed`.

**Cause**: `runExitFlow` (which fires the post-goal hook at `PumpStationLoop.kt:2645`) is reached **only** when the judge emits `isComplete=true` OR a path returns `passPipeline=true` on its `MultimodalContent`. If the judge stub returns `isComplete=false` indefinitely AND no path sets `passPipeline=true`, the harness loops until the turn budget runs out and never reaches `runExitFlow`. The post-goal hook isn't broken — it's never invoked.

**Fix**: Either
1. Add `.apply { passPipeline = true }` to the path's `setExecutionFunction` result (mirrors the pattern at `registerSinglePathPassPipelinePath` in `PumpStationPostGoalLiveTest.kt:843-854`).
2. Change the judge stub to return `isComplete=true` at some point (requires a call-counting mechanism, since the current `StubOpenAIServer.loopEnqueue` registers a single fallback per role).

The diagnostic on Layer 3 is reading the trace HTML's `ps-status-banner` for the harness's final exit reason. If it's `Failed` with `MaxTurnsHit` and no `PUMP_STATION_POST_GOAL_COMPLETED` in the body, the test is missing a termination signal — not failing the post-goal hook itself.

## Worked example: stub_04 in PumpStationPostGoalLiveTest.kt

The `stub_04_multiPathRiskLevels_postGoalFiresAfterFullLoop` test hit all three layers in sequence:

1. `{"path":"report"}` not wrapped → `Failed to deserialize` on the first dispatch call → fix: `stubResponsesJson("""{...}""")` wrapper
2. Wrapped but field name still `path` instead of `pathName` → `parseDispatchOutput` returns null, dispatch repair exhaustion, harness loops to `MaxTurnsHit` → fix: rename field to `pathName` and add `inputData:{}`
3. Field name correct but path's `setExecutionFunction` returned `MultimodalContent(text = "...")` without `passPipeline = true` → harness still never reached `runExitFlow` → fix: `.apply { passPipeline = true }` on the report path's response

Each layer's fix was a 1-line patch. Each layer's error was misleading without the trace to disambiguate. The trace's HTML size is the disambiguator: < 100KB = harness didn't really run (Layer 1), 100-500KB = harness ran but didn't terminate (Layer 2 or 3), > 500KB with all events = harness ran the full loop (Layer 3 case is fixed).

## Related: `useRiskLevels` does NOT set `pathExecutionShape = MultiPath`

`useRiskLevels = true` adds a `pathSafetyAgent` to the harness but does **not** change the dispatch mode. The harness continues to run in `pathExecutionShape = SinglePath` (the default), and the dispatch prompt is the SinglePath shape requiring `{"pathName":"...","inputData":{...}}`. Test names containing the substring "multi-path" can be misleading — verify by reading the test's actual `configurePaths` and `configureGoal` lambdas rather than trusting the name.

For example, `stub_04_multiPathRiskLevels_postGoalFiresAfterFullLoop` (PumpStationPostGoalLiveTest.kt:271) is **single-path with a path-safety agent**, not multi-path. The "multi" in the name refers to the multiple registered paths (`gather`, `analyze`, `report`, `giveUp`) available for risk-level selection, not to the dispatch execution shape. To actually exercise multi-path dispatch, the test would need `pathExecutionShape = PathExecutionShape.MultiPath` set explicitly in the builder, plus the dispatch prompt switches to the multi-path variant and the payload becomes `{"paths":[{...}],"batchRationale":"..."}`.

## Related: `wrapPipelineAsPassingGoal` default baseUrl breaks stub-mode routing

`PumpStationPostGoalLiveTest.kt:812-840`'s `wrapPipelineAsPassingGoal()` calls `createMiniMaxPipe("goal-pass", systemPrompt = "...")` WITHOUT passing the `baseUrl` argument. `createMiniMaxPipe` (`PumpStationPostGoalLiveTest.kt:607-628`) defaults to `MINIMAX_BASE_URL` (the real MiniMax API), so the goal-agent pipe hits the real network even in stub-mode tests. The stub server's `detectRole` doesn't recognize the goal agent's prompt ("you are a goal-verification agent") — it falls through to the `report` role fallback, and the canned `report` payload (a non-JSON plain-text string) doesn't deserialize cleanly.

**Symptom**: `P2PException: OpenAI Responses error: login fail: Please carry the API secret key in the 'Authorization' field of the request header (1004)` when the harness reaches the goal-gate phase. Auth-failure 1004 is what MiniMax returns when the API key is missing or invalid — which the real API sees because the goal pipe is routing there, not the stub.

**Fix**: thread the test's `baseUrl` parameter through `wrapPipelineAsPassingGoal` and `wrapPipelineAsFailingGoal` to `createMiniMaxPipe` so the goal pipe routes to the stub. The signature should be:

```kotlin
private fun wrapPipelineAsPassingGoal(baseUrl: String = MINIMAX_BASE_URL): P2PInterface
```

and the call sites in `stubGoalAgentThatPasses` / `stubGoalAgentThatFails` should pass `baseUrl` from the test's harness-runnable scope. Without this fix, stub-mode tests that route through the goal agent (`stub_04`, `stub_05`, `stub_06`) cannot pass on hosts without a real `MINIMAX_API_KEY`.

**Workaround for verification**: stub-01 (`stub_01_passPipelineNoGoal_postGoalFiresOnNoGoalAgentExit`) doesn't wire a goal agent, so it exercises the post-goal hook without triggering this pitfall. When a stub-mode test is hitting auth-failure 1004 and is gated on a goal agent, verify with stub-01 first to confirm the post-goal hook itself is reachable, then fix the goal-pipe routing separately.
