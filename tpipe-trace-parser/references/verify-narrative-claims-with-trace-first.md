# Verify Narrative Claims with Trace First

**Captured:** 2026-07-24 from the path-safety rejection triage session. The prior session's agent made two unfalsifiable claims to the user: "the test called the give up path 19 times" and "the give up path should be terminating." The user explicitly said "I can't tell if anything it says is true or a lie." Both claims were structurally false — the first was unfalsifiable without the trace data; the second was contradicted by the production code at the time.

## The Rule

**When a prior session makes narrative claims about runtime behavior (counts, exits, "should be" assertions, "the bug is X" hypotheses), the first action is to extract evidence from the trace, not to build on the prior session's narrative.**

The trace artifacts are the only ground truth. They are persistent (`~/.tpipe/debug/trace/PumpStation/<runId>/pumpstation-*.html`), they are queryable, and they record what the harness actually did — not what the prior session said it did.

## Recipe (5 steps)

1. **List the trace directory for the run in question.** Find the most recent harness run that matches the bug:
   ```bash
   ls -lt ~/.tpipe/debug/trace/PumpStation/ | head -20
   ```

2. **Pick the harness HTML and the per-agent HTMLs.** The harness HTML is `pumpstation-ps-<runId>.html` (the high-level container events). The per-agent HTMLs are `agent-judge.html`, `agent-dispatch.html`, `agent-gather.html`, etc. — they show the actual LLM-facing prompts and responses.

3. **Count the event types.** `grep -oE "PUMP_STATION_[A-Z_]+" <trace.html> | sort | uniq -c | sort -rn` gives the event histogram. This is the structural basis for any "X happened N times" claim.

4. **Verify the LLM-facing prompt actually contained the path/menu the prior session claimed.** `grep -A20 "The available paths are:" agent-dispatch.html` shows the path menu the LLM was given. If the prior session said "the LLM saw X in the visible-paths list," this grep confirms or refutes it on the operator's machine.

5. **Verify the dispatch payload matches the harness's actual contract.** `grep -B2 -A5 "selectedPathName" pumpstation-ps-*.html` shows what the dispatch agent picked, and the dispatch parser at `PumpStationHelpers.kt:639` is strict about field names (`pathName`, not `path`). A prior session that said "the dispatch payload was `{"path": "X"}` and the harness should have accepted it" is wrong twice: the field name is wrong AND the harness is strict about it.

## Worked Example (2026-07-24)

Prior-session claim 1: "the test called the give up path 19 times." True — but only as a consequence of the dispatch parser being strict about `path` vs `pathName` (or, in the case-insensitive fix path, the registry being case-sensitive). The 19 was the consequence, not the cause.

Prior-session claim 2: "the give up path should be terminating." Structurally false. The path IS supposed to terminate (it sets `terminatePipeline=true` and `passPipeline=true` in `PumpStationPostGoalLiveTest.kt:914-919`). But the prior session never checked whether the harness actually reached the path. Trace evidence showed the harness was failing at the `resolvePath()` call (`UnknownPath: 'giveUp' not found`) before the path body ever ran. The path's termination contract was correct; the harness was never reaching it.

**What the prior session should have done first**: open the trace HTML, count the `PUMP_STATION_PATH_FAILED` events with `error: UnknownPath`, and that single grep would have ended the speculation.

## Why the Operator's Trust Erodes

The operator's verbatim correction — "I can't tell if anything it says is true or a lie" — is the worst possible signal in a debugging session. It means the prior session produced confident narrative without trace evidence, and the operator has no way to verify. Future sessions inherit that trust deficit: every claim the agent makes is now viewed as potentially-fabricated until proven otherwise.

The only fix is **structural**: every claim about runtime behavior must cite the trace artifact (file path + line count + grepped evidence) at the moment the claim is made. Not in a follow-up — in the same turn. The claim "the test failed because X" is a fabrication unless it's followed by "and here's the trace line that shows X."

## When This Rule Applies

- A prior session claimed "the test called X N times" — verify with `grep -c` on the trace HTML.
- A prior session claimed "the harness should have terminated" — verify by finding the actual `taskState.exitReason` in the trace footer.
- A prior session claimed "the LLM ignored the hint" — verify by extracting the LLM-facing prompt from `agent-<role>.html` and checking that the hint is present in the `[CONVERSATION HISTORY]` block.
- A prior session claimed "the system prompt was missing X" — verify by extracting the `applySystemPrompt()` output from the trace.

## When This Rule Does NOT Apply

- Pure code-level hypotheses that don't depend on trace data ("the `pathList` map is case-preserved at insert but case-insensitive at lookup"). Trace data is irrelevant; the source code is the evidence.
- Configuration claims that depend on env vars or build files — read the env, don't grep a trace.
- Hypotheses about a system that doesn't produce traces (e.g., design discussions, refactoring plans).

## Captured From

The 2026-07-24 TPipe path-safety rejection triage session, where the prior session produced two narrative claims that the operator could not verify and asked the current session to take over. The fix workflow went:

1. Open `~/.tpipe/debug/trace/PumpStation/live-04-multi-path-risk-levels/pumpstation-ps-178484965.html`.
2. `grep -oE "PUMP_STATION_[A-Z_]+" | sort | uniq -c | sort -rn` → 50 dispatches, 31 path-starts, 19 `PUMP_STATION_PATH_FAILED` events.
3. `grep -oE "pathName\":\"([^\"]+)"` and `grep -oE "Path 'X' not found"` → all 19 failures were `pathName='giveUp', error=UnknownPath`.
4. `grep "available paths" agent-dispatch.html` → confirmed the LLM genuinely saw `giveUp` listed.
5. `read_file` `PumpStation.kt:2773` and `PumpStationHelpers.kt:770-774` → case-sensitivity mismatch at the map boundary.

Total: 4 tool calls, ~30 seconds. The bug was identified in step 5. The trace was the disambiguator, not the source code.
