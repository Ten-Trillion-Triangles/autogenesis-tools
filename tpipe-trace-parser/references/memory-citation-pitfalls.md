# Memory-Citation Pitfalls (v1.8)

Captured 2026-07-23 from the path-safety rejection triage session. The
user issued a direct correction when the agent pulled claims from
prior-session memory without verifying against the live source code:

> "Given you pulled that from memory I do not trust that statement.
> The other traces do not behave like the llm does not know the task
> in anyway. So you need to prove beyond a shadow of a doubt that's
> true."

This file consolidates the three memory-citation pitfalls captured
this session. Each pitfall was burned by the agent in real-time; the
user corrected the agent on each one.

## Pitfall: Memory-cited line numbers and API shapes are not evidence

**Symptom**: Agent cites `PumpStationHelpers.kt:796-823` as evidence
that `buildUserMessageForTurn()` does NOT include `originalInput`.
Agent cites `PumpStationLoop.kt:610` as evidence that
`buildPathInput()` prefers `pathSchema` over `originalInput`. Agent
cites `requestPassPipeline()` as a station method. Agent cites
`passPipeline = true` as a constructor parameter. All four claims
were wrong.

**Truth at the live source**:
- `buildUserMessageForTurn()` at `PumpStationHelpers.kt:895-922`
  DOES include `originalInputPrefix`. The test at
  `BuildContentTest.kt:35-40` already pins this behavior.
- `buildPathInput()` at `PumpStationLoop.kt:883-887` DOES prefer
  `originalInput` over `pathSchema` (the prior fix from 2026-07-08
  is in the working tree).
- There is no `requestPassPipeline()` method on `PumpStation`.
- `passPipeline` is a `@kotlinx.serialization.Transient var` on
  the class body (`BinaryContent.kt:153`), NOT a primary constructor
  parameter. The established pattern to set it is
  `.also { it.passPipeline = true; it.terminatePipeline = true }`
  (the idiom at `PumpStation.kt:3081`).

**Root cause**: Default-to-memory reflex. When the agent has
prior-session memory about a system, it reaches for the memory rather
than re-verifying against the live source. Memory decays; code does
not.

**The rule**: For every claim that involves a file:line, function
signature, method name, or constructor parameter:
1. Open the file at the cited location and read the actual code.
2. If the cited location doesn't match, run `grep -rn` for related
   strings to find where the symbol actually lives.
3. If the cited function name doesn't exist, run `grep -rn
   "fun <name>"` to find the actual name (or confirm it doesn't
   exist).
4. If the cited constructor parameter doesn't exist, run `grep -n
   "var " on the class` to find the actual field declarations.
5. THEN cite the line and quote the actual code.

**What is NOT evidence of a claim**:
- A line number remembered from a prior session (the line may have
  shifted, the function may have moved, the symbol may have been
  renamed).
- A method name remembered from a prior session (the method may have
  been renamed or removed).
- A constructor parameter shape remembered from a prior session
  (data class fields are body-level vars in this codebase, not
  constructor params).
- A fix claim sourced from prior-session transcript.

**Pairs with**: v1.3 "Fix claims need source-code evidence, not
trace observation" (the fix-claim special case), and v1.7
"Hint-Injection Test Pattern" reference.

## Pitfall: In-process state is NOT pipe-facing input

**Symptom**: The agent wrote a test that:
1. Appends a hint to `station.turnHistory`
2. Asserts the hint is in `turnHistory.history`
3. Calls `buildTurnContent()` and asserts the hint survives the
   `[CONVERSATION HISTORY]` serialization

The test passed (4/4 green). The agent declared "the hint reaches
the LLM" as a finding. The user corrected:

> "the bug we were looking for was weather hints were reaching the
> llm IE: the pipe, it's user prompt/context or not. So you faileed
> on that account too"

**Root cause**: `buildTurnContent()` is a *builder* — it produces a
`MultimodalContent` object that the pipe then receives. The pipe may
further transform, filter, or augment the input before logging it
in `agent-*.html`.

**The rule**: When a feature claims "the LLM is informed about X,"
verification has three levels, in order:
1. **Data structure level**: the feature's side effect is present
   in the harness's data structures (e.g. `turnHistory`). This
   proves the feature ran.
2. **Prompt-builder level**: the prompt-builder function (e.g.
   `buildTurnContent()`) serializes the data structure into the
   user-message text. This proves the prompt builder didn't drop
   the feature's signal. (The v1.7 "Hint-Injection Test Pattern"
   reference covers levels 1 and 2.)
3. **Pipe-facing input level**: the `agent-*.html` file's
   `API_CALL_START` event's `content.text` field contains the
   signal. This proves the LLM actually consumed it. (This pitfall
   adds level 3.)

**Verification recipe for level 3**:
```bash
AGENT_TRACE=$(find ~/.tpipe/debug/trace/<test-dir> \
  -name "agent-<pipe>.html" | head -1)
grep -o "<signal-marker-substring>" "$AGENT_TRACE"
```

The 2026-07-23 session proved the path-safety rejection hint reached
the dispatch LLM by grepping `agent-dispatch.html` for "rejected by
the path-safety gate" and finding 2 occurrences — the LLM had been
told, twice, to pick a different path. The LLM ignored the hint
and picked `gather` 47 times anyway, but the hint *was* in the
input.

**Pairs with**: v1.7 "Hint-Injection Test Pattern" reference (which
covers levels 1 and 2; this pitfall adds level 3).

## Pitfall: Amend the live test, don't create a stub-based equivalent

**Symptom**: The agent found a bug in
`live_04_multiPathRiskLevels_postGoalFiresAfterFullLoop` (47
path-safety rejections with 47 identical `gather` selections). The
agent created a new test file `GiveUpPathHypothesisTest.kt` that
used a `StubOpenAIServer` to reproduce the behavior deterministically.
The user corrected:

> "this is a live test, so you have to update THAT LIVE TEST WHICH
> YOU CLAIMED A BUG WAS FOUND IN"

**Root cause**: Default-to-stub reflex. When asked to verify a
hypothesis, the agent reached for the deterministic stub-server path
because it's faster, more controllable, and doesn't require a live
API key. But the bug was found in a *live* trace; the fix's *value*
comes from the live trace running end-to-end with the real LLM. A
stub-based test that passes doesn't prove the live behavior changes.

**The rule**: When a bug is found in a *live* test (any test that
depends on a real LLM API call and gates on
`TPIPE_LIVE_LLM_TEST=true`), the hypothesis-verification test or
the regression test must amend the *same live test class*. Specifically:
1. The hypothesis-test path (e.g. a new `giveUp` path) goes into the
   existing `registerMultiPathRiskLevelPaths()` function, not a new
   test file.
2. The regression assertion goes into the existing test method
   (`live_04_multiPathRiskLevels_postGoalFiresAfterFullLoop`), not a
   new test class.
3. If a new assertion is needed, add it to the test's
   `runPostGoalHarness` call's config (e.g. a new flag, a new
   expected-exit enum).

**When stub-based tests are appropriate**:
- For new feature work where there's no live behavior to amend.
- For regression pinning of a fix that was already shipped and is
  independent of the live trace.
- For unit tests of internal helper functions that don't reach
  the LLM.

**When stub-based tests are NOT appropriate**:
- To verify a hypothesis about behavior found in a *live* trace.
  The hypothesis is about live behavior; amend the live test.
- To "speed up" a slow live test. The slowness is the cost of LLM
  service calls; speedup loses the signal the live trace provides.

**Pairs with**: the diagnostic gate
(`references/diagnostic-gate.md` v1.8) — the gate's results come
from the live trace; a stub-based replica of the gate would not
catch the same bugs.
