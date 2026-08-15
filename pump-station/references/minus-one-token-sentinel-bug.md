# PumpStation -1 Token Sentinel Bug Class

When every phase-completed event in a PumpStation trace HTML renders `inputTokens: -1, outputTokens: -1, totalTokens: -1` (the user's screenshot for `PUMP_STATION_JUDGE_COMPLETED` in the `pumpstation-ps-<runId>.html` meta-row), the bug is a sealed-event field-population issue at the emit site — not an LLM call failure, not a Pipe-level token counting bug, not a transport flake.

This is a distinct, recurring bug class. Reference case: 2026-07-06, `PumpStationLoop.kt:290` `JudgeCompleted` emit site passing only 4 of 7 constructor args; the `inputTokens`/`outputTokens`/`totalTokens` fields defaulted to `null`; the trace helper at `PumpStationHelpers.kt:161-164` substituted `-1` as the sentinel for null fields. Fix was 6 lines (route `agentTokenUsage(judgeAgent)` into the constructor), exactly mirroring how `DispatchCompleted` was already wired correctly at `PumpStationLoop.kt:385, 397`.

## How the bug class works

Each phase-completed event in `PumpStationEvent` (sealed interface, defined in `PumpStationModels.kt`) has token fields that default to `null`:

```kotlin
data class JudgeCompleted(
    override val runId: String,
    override val turnIndex: Int,
    ...
    val isComplete: Boolean,
    val shouldTerminate: Boolean,
    val result: MultimodalContent? = null,
    val inputTokens: Int? = null,    // <-- null when emit site forgets to pass it
    val outputTokens: Int? = null,   // <--
    val totalTokens: Int? = null     // <--
) : PumpStationEvent
```

The trace helper at `PumpStationHelpers.kt:147-165` (JudgeCompleted branch) writes them to the trace metadata map with a `-1` sentinel for null:

```kotlin
is JudgeCompleted ->
{
    eventType = TraceEventType.PUMP_STATION_JUDGE_COMPLETED
    baseMetadata["isComplete"] = event.isComplete
    baseMetadata["shouldTerminate"] = event.shouldTerminate
    agentContent = event.result
    ...
    event.inputTokens?.let { baseMetadata["inputTokens"] = it } ?: baseMetadata.put("inputTokens", -1)
    event.outputTokens?.let { baseMetadata["outputTokens"] = it } ?: baseMetadata.put("outputTokens", -1)
    event.totalTokens?.let { baseMetadata["totalTokens"] = it } ?: baseMetadata.put("totalTokens", -1)
}
```

Same pattern at all 5 phase-completed emit handlers in `PumpStationHelpers.kt`:
- `JudgeCompleted`         (line 147-165)
- `DispatchCompleted`      (line 167-185)
- `PathCompleted`          (line 212-230)
- `InterventionCompleted`  (line 258-276)
- `ForegroundAgentCompleted` (line 277-294)

## Two sub-classes of the bug, distinct root causes

**Sub-class A: emit site doesn't pass the token fields.** The constructor is called with fewer than 7 args; the token fields default to `null`; the helper substitutes `-1`. Diagnostic: the emit site at the loop (e.g. `PumpStationLoop.kt:290`) does NOT call `agentTokenUsage(agent)` or the equivalent before constructing the event. The 2026-07-06 reference case was this sub-class for `JudgeCompleted`. Fix is to mirror the working emit site: 4 lines + 1 import.

**Sub-class B: emit site passes the token fields but the helper returns null.** The emit site IS calling `agentTokenUsage(agent)` and routing the result into the event constructor, but the helper at `PumpStationLoop.kt:2696` is:

```kotlin
internal fun agentTokenUsage(agent: P2PInterface?): Pair<Int, Pair<Int, Int>>? {
    val pipeline = agent as? Pipeline ?: return null   // <-- non-Pipeline agents get null
    val usage = pipeline.getTokenUsage()
    val input = usage.totalInputTokens
    val output = usage.totalOutputTokens
    if (input <= 0 && output <= 0) return null
    val total = input + output
    return input to (output to total)
}
```

A `P2PInterface` that is NOT a `Pipeline` (e.g. `PathObject`, default `interventionAgent`) makes `agent as? Pipeline` return null, so the helper returns null, the emit site passes null, the trace layer substitutes `-1`. Fix is either (a) widen `agentTokenUsage` to handle non-Pipeline `P2PInterface` implementations, or (b) define a `P2PInterface` token-usage accessor implementations can override. The 2026-07-06 follow-up finding: 17 of the `-1` occurrences in live runs were sub-class B, attached to `PATH_*` and `INTERVENTION_*` events whose agents are non-Pipeline `P2PInterface` instances.

**Diagnostic to disambiguate:** for each `-1` occurrence, find the corresponding emit site in production code and check whether `agentTokenUsage(...)` is being called. If yes → sub-class B. If no → sub-class A.

## How to fix sub-class A (emit-site bug)

The fix is mechanical: copy the pattern from a working sibling. For `JudgeCompleted`, the working sibling is `DispatchCompleted` at `PumpStationLoop.kt:385, 397` which already calls `agentTokenUsage(dispatchAgent)` and routes the result into the event constructor. Mirror that:

```kotlin
// BEFORE (sub-class A bug at PumpStationLoop.kt:290):
val result = runAgent(judgeAgent, input)
val postResult = postJudgeFunctionInternal?.invoke(result, this) ?: result
val parsed = if (judgeExpectsJsonContract) parseJudgeVerdict(postResult) else JudgeVerdict.empty()
val verdict = parsed.withFlagCheck(postResult)
taskState.latestContent = postResult
emitEventInternal(JudgeCompleted(
    runId = taskState.runId,
    turnIndex = taskState.turnIndex,
    isComplete = verdict.isComplete,
    shouldTerminate = verdict.shouldTerminate
    // inputTokens/outputTokens/totalTokens default to null
))

// AFTER (matches DispatchCompleted pattern at PumpStationLoop.kt:385, 397):
val result = runAgent(judgeAgent, input)
val judgeUsage = agentTokenUsage(judgeAgent)   // <-- add this line
val postResult = postJudgeFunctionInternal?.invoke(result, this) ?: result
val parsed = if (judgeExpectsJsonContract) parseJudgeVerdict(postResult) else JudgeVerdict.empty()
val verdict = parsed.withFlagCheck(postResult)
taskState.latestContent = postResult
emitEventInternal(JudgeCompleted(
    runId = taskState.runId,
    turnIndex = taskState.turnIndex,
    isComplete = verdict.isComplete,
    shouldTerminate = verdict.shouldTerminate,
    result = postResult,                            // <-- also pass result so visualizer can render the verdict text
    inputTokens = judgeUsage?.first,                // <-- route token usage
    outputTokens = judgeUsage?.second?.first,
    totalTokens = judgeUsage?.second?.second
))
```

Net diff: 6 lines added (1 helper call + 4 emit-site args), 0 removed. The `result = postResult` add is bonus — it also makes the judge's `MultimodalContent` available to the visualizer for the per-event detail panel (was previously `null` at the same time the helper layer was reading `event.result?.text` for `contentPreview`).

## How to TDD the fix

The test must drive the actual emit site, not just synthetic event construction. Three layers of test, ordered by bug-surface coverage:

**Layer 1: drive the real emit site.** This is the test that catches the bug at the source. Build a `PumpStation` with a scripted test judge agent that simulates LLM token usage, call `runJudgePhase()`, capture emitted events via `setEventObserver`, assert the event's token fields are non-null. The 2026-07-06 reference test `judgeCompletedEventCarriesRealTokenCounts` in `src/test/kotlin/Pipeline/PumpStationJudgeTokenTrackingTest.kt` does exactly this. RED assertion: `expected: <240> but was: <null>`. GREEN after the fix above.

**Layer 2: drive the helper layer directly.** Construct a `JudgeCompleted` with explicit non-null token fields, route it through `tracePumpStationEvent`, read back the resulting `TraceEvent` from `PipeTracer`, assert the metadata map contains the real values. This pins the contract between the emit site (Layer 1) and the visualizer (Layer 3). If the helper layer ever silently starts substituting `-1` for non-null, this test catches it. The 2026-07-06 reference test `judgeCompletedMetadataRendersRealTokensNotMinusOneSentinel` does this.

**Layer 3: pin the upstream sentinel contract.** The helper's `?: baseMetadata.put("inputTokens", -1)` branch is a deliberate contract — when the field is null, render `-1`. If anyone removes the sentinel (e.g. trying to "clean up" the `-1`), the visualizer's downstream consumers may break. The defense-in-depth test reads `PumpStationHelpers.kt` source and asserts the sentinel literal is still present at all 5 phase-completed handler sites. The 2026-07-06 reference test `judgeCompletedEventDoesNotProduceMinusOneSentinelInTraceMetadata` does this.

Three tests, three layers, each catches a different class of regression. Skipping any one leaves a gap.

## Build the test pipe correctly

The test pipe must populate `pipeTokenUsage` AFTER the Pipe base class's `countTokens` reset (Pipe.kt:5715) and AFTER its own `countActualInputTokens` overwrite (Pipe.kt:6130). The Pipe base class's flow during `execute()` is:

1. `pipeTokenUsage = TokenUsage()` (reset, Pipe.kt:5715) if `comprehensiveTokenTracking` is enabled
2. `actualInputTokens = countActualInputTokens(processedContent)` → `pipeTokenUsage.inputTokens = actualInputTokens` (Pipe.kt:6130)
3. `generateText(...)` runs — **THIS is where the test pipe overrides values**
4. `outputTokens = countTokens(false, generatedContent)` → `pipeTokenUsage.outputTokens = outputTokens` (Pipe.kt:6254) — **THIS overwrites what the test pipe set**
5. `recalculateTotals()` → aggregates

If the test pipe sets tokens in `generateText()` then they get overwritten by step 4 (output) and possibly step 2 (input). Two options:
- Set tokens AFTER `generateText` returns (not currently possible without extending Pipe)
- Set tokens to a value that matches what `countTokens` will produce for the test's known input/output text. For 50-char response text, `Dictionary.countTokens` returns ~25 — pin the test to the actual tokenized value, not to the simulated value.

The 2026-07-06 reference test sets `simulatedInputTokens = 240` and `simulatedOutputTokens = 50` but the actual emitted values are 240/25 (50 is overwritten by 25). The test does NOT hardcode the expected values; it asserts `inputTokens > 0` and `totalTokens == input + output`. This is the safer pattern: pin invariants, not implementation-detail numbers.

Also: `skipJudgeOnFirstTurnInternal` defaults to `true` (PumpStationLoop.kt:236), so calling `runJudgePhase()` on `turnIndex == 0` short-circuits to a `JudgeSkipped` event without ever emitting `JudgeCompleted`. Tests must call `.setSkipJudgeOnFirstTurn(false)` on the test station before driving `runJudgePhase()`. This is a recurring test fixture pitfall — pre-existing tests like `RunJudgePhaseTest` and `MagicContractOptOutTest` were failing on `main` before this fix landed, because they don't set this flag.

## How to verify the fix at the rendered HTML level

After patching and running the live test suite, scan the freshly-written `pumpstation-ps-<runId>.html` files for `-1` occurrences attached to the right event types:

```bash
# Count -1 in ps-meta-val blocks per event type (Python 3.10+ f-string safe)
python3 -c "
import re
from pathlib import Path
from collections import Counter
TRACES = Path.home() / '.tpipe/debug/trace/PumpStation'
hits = Counter()
for pf in sorted(TRACES.rglob('pumpstation-ps-*.html')):
    text = pf.read_text()
    for m in re.finditer(r\"<div class='ps-detail-label'>([^<]+)<span class='ps-detail-type'>\(([^)]+)\).{0,1500}?\", text, re.DOTALL):
        event_type = m.group(2).strip()
        if chr(39) + 'ps-meta-val' + chr(39) + '>-1' in m.group(0):
            hits[event_type] += 1
for k, v in hits.most_common():
    print(f'  {k}: {v}')
"
```

Expected after a clean run:
- `PUMP_STATION_JUDGE_COMPLETED`: 0 occurrences (sub-class A fix verified)
- `PUMP_STATION_DISPATCH_COMPLETED`, `PUMP_STATION_PATH_COMPLETED`, `PUMP_STATION_FOREGROUND_AGENT_COMPLETED`: 0 occurrences (these were already wired correctly)
- `PUMP_STATION_INTERVENTION_COMPLETED`, `PUMP_STATION_PATH_*` events backed by non-Pipeline `P2PInterface` agents: may still show `-1` (sub-class B, separate fix)

If a fresh run still shows `-1` for the event you fixed, the fix did not land or the test was looking at cached trace HTML — re-run the live test with `--rerun-tasks`.

## Quick triage command

```bash
# Find all -1 sentinel occurrences in pumpstation-*.html with surrounding context
python3 -c "
import re
from pathlib import Path
TRACES = Path.home() / '.tpipe/debug/trace/PumpStation'
for pf in sorted(TRACES.rglob('pumpstation-ps-*.html')):
    for m in re.finditer(r'.{50}-1.{50}', pf.read_text()):
        snippet = m.group(0).replace(chr(10), ' ')
        print(f'  {pf.name}: ...{snippet[:150]}...')
" | head -20
```

This shows the rendered meta-row that contains the `-1` value. The event-type span (`<span class='ps-detail-type'>(PUMP_STATION_*_COMPLETED)</span>`) appears 0-100 chars before the `-1`, so it's immediately obvious which event class is affected.

## Why this skill needs the rule

The five `*Completed` events all share the same shape (token fields default to null) and the same helper-side sentinel. The bug class WILL recur as the harness grows new phase-completed events. A new `SummaryCompleted` or `LorebookCompleted` added in 2026Q3 will ship the same `*: Int? = null` defaults and a helper that writes `-1` for nulls — and a future session will hit this exact class of bug. Encoding the pattern in the skill means the fix template is already on file.

The "emit-site passes fields, helper returns null" sub-class is broader: it's a `P2PInterface` API gap. Any future `P2PInterface` implementation that wants to expose token usage needs an accessor the helper can call. The 2026-07-06 follow-up: widen `agentTokenUsage` to fall back on a `P2PInterface.tokenUsage` accessor, or define a default `TokenUsage()` for non-`Pipeline` implementors.
