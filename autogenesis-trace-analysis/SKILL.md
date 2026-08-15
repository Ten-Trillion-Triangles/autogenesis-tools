---
name: autogenesis-trace-analysis
description: "Analyze autogenesis game trace files to debug why a player's play got modified/rewritten/'nuked' by the validator pipeline, OR to understand what a real game session looked like. POST-MANTLE-CUTOVER covered too: pipe-level Mantle/gemma reasoning failures (Pipe.kt:8033 NPE cascade producing empty {}), territoryExchanges schema-vs-orchestration mismatches, the gemma-4-e2b / gemma-4-31b swap audit, AND the strategic-pipe in-flight stall with token-delta duplication runaway. Also covers the audioTracks field leaking via serialize(WorldManager.world). Triggers on 'why did my play get changed', 'trace said it passed but then', 'check what happened to my turn', 'gemma produced wrong schema', 'validator flyby', 'why did X lose territory when Y repelled', 'after the gemma swap', 'mantle reasoning pipe crashed', 'agent work stream stuck', 'token duplication', 'streaming never completes', 'turn never resolves', or any trace/context-injection read."
version: 1.4.0
changelog:
  - '1.4.0 (2026-08-08): Added Pitfall 10 (the judge is a narrative extractor, not a battlefield adjudicator — winning/losing territory is a function of what the writing agents wrote, not what actually happened in-fiction). Added references/judge-decision-extraction.md with the 9-pipe chain mapping, gains/losses + stat-change extraction recipe, and the Round 1 Turn 0 Lord Maple Tree worked example (Sudan + Ethiopia awarded despite tanks being immobilized in cement).'
  - '1.3.0 (2026-08-02): Added Pitfall 9 (strategic-pipe in-flight stall with token-delta duplication runaway — broken Bedrock llamaScout17B config, browser-log + server-log-only diagnostic since AUTOGENESIS_DEBUG_TRACE=false clears the trace dir at boot). Added references/strategic-pipe-stall-2026-08-02.md covering the 2026-08-02 4m35s stall, 22-second inter-pipe silence, 248×N chunk-size fan-out math, and the Bedrock Mantle config error at server log L254.'
  - '1.2.0 (2026-07-31): Added Pitfalls 7 (NPC-only turns have no Judge trace) and 8 (incomplete turns may have no Judge trace at all). Added references/gameplay-progression-and-swing-magnitude.md covering game_snapshot.json → history[] extraction, territory exchange patterns, and Round 3-4 Judge pipeline token burn numbers.'
  - '1.1.0 (2026-07-30): Post-Mantle-cutover procedure plus 4-bug worked example from Round 1 Turn 0/1 (Lord Maple Tree -> Robert). Added Pitfall 7 (Mantle reasoning-pipe NPE cascade at Pipe.kt:8033, retry path can produce empty JSON), Pitfall 8 (territoryExchanges schema-vs-orchestration mismatch), and a new post-cutover investigation procedure. New references file: mantle-gemma-cutover-bugs.md'
metadata:
  hermes:
    tags: [autogenesis, traces, tpipe, game-debug, validator, pipeline, json, mantle, gemma, reasoning-pipe, post-cutover, territory-exchange]
    related_skills: [dogfood]
---

# Autogenesis Game Trace Analysis

When an autogenesis player reports their play got "changed," "nuked," "rewritten," or "passed the check but failed later," the cause is almost always the validator pipeline running a fallback path. This skill covers how to read the trace files, what each pipe does, and how to identify which pipe actually overwrote the play.

## Where the Traces Live — Two Complementary Surfaces

Autogenesis leaves traces in **two independent locations**, and they answer different questions:

| Surface | Path | Records | Use for |
|---|---|---|---|
| **Pipeline traces** | `~/.tpipe/debug/trace/Round_<N>_Turn_<M>_<player>/` | Mechanical events: pipe starts, LLM calls, validator decisions, transformations, branch triggers | "Why did my play get rewritten?" "Which pipe actually overwrote it?" "How long did the LLM stall?" |
| **Lorebank narrative traces** | `~/.tpipe/TPipe-Default/memory/lorebook/*.bank` | The actual in-character text every persona/commander spoke, plus the per-session dialogue history | "What did Lord Maple Tree actually SAY last game?" "What does this game look like in play?" "Which personas have been used?" "What did the AI judge write in this verdict?" |

If you're debugging a play-modification bug, start with the pipeline traces. If you're trying to understand the gameplay experience, document the game design, or build a public-facing description, start with the lorebank traces. They complement each other: the pipeline traces tell you what the validators *did* to a play, the lorebank traces show you what the play *was* before and after.

### Pipeline traces

(Older sessions may also have used `/tmp/autogenesis_pm/` — verify with `ls ~/.tpipe/debug/trace/` first; the autogen project switched the writer to the `~/.tpipe/` root.)

The directory is NOT a flat list of `<pipe>.json` files. It is organized by **pipeline component**, with one subdirectory per top-level pipeline that ran during the turn. Each subdirectory contains a `trace.json` plus, for splitters/branches, nested timestamped subdirectories for each fan-out branch.

Real example from `Round_1_Turn_0_Lord_Maple_Tree/` (Lord Maple Tree, 2026-06-22):

```
Round_1_Turn_0_Lord_Maple_Tree/
├── AnalysisSplitter/1782161242332/
│   ├── resources/trace.json
│   ├── analysis/trace.json
│   └── trace.json
├── Judge/trace.json
├── LorebookUpdate/trace.json
├── MaintenanceSplitter/1782162200743/
│   ├── updates/trace.json
│   ├── scan/trace.json
│   └── trace.json
├── NeoWritingAgent/trace.json
├── TargetDetectors/trace.json
├── TurnResolutionSplitter/
│   ├── narrative/trace.json
│   └── trace.json
├── ValidationSplitter/1782160943357/
│   ├── validator/trace.json          ← the 3-stage validator pipeline (most detail)
│   ├── railroad/trace.json
│   └── trace.json
└── WritingAgents/trace.json
```

The `1782160943357`-style numbers are Unix-ms timestamps. In the validator case, the timestamp is the Splitter's PIPE_START time; `validator/` and `railroad/` are the two branches the splitter fanned out to.

**How to find the right file for a given investigation:**

| Looking for… | Path |
|---|---|
| Validator's 3-stage pipeline (legalityChecker, legalityRectifier, styleReapply) | `ValidationSplitter/<ts>/validator/trace.json` |
| The Splitter that dispatched them | `ValidationSplitter/<ts>/trace.json` |
| The branch (e.g. Palmyra X5 fallback) | `ValidationSplitter/<ts>/railroad/trace.json` |
| The Judge's outcome resolution | `Judge/trace.json` |
| The NeoWritingAgent's writing pipe | `NeoWritingAgent/trace.json` |
| NPC writers | `WritingAgents/trace.json` |
| NPC target detection | `TargetDetectors/trace.json` |
| Turn narrative | `TurnResolutionSplitter/<narrative>/trace.json` |
| Lorebook updates | `LorebookUpdate/trace.json` |

A file containing `validator` in its path (at any nesting level) is the one with the most detail and is the right entry point when investigating play modifications.

These are NOT the HTML `trace.html` files parsed by `parse_traces.py` at the repo root — that script is for the browser pipeline viewer. Game traces are plain JSON arrays.

## Trace File Format

Each file is a JSON array of events. Every event has:

```json
{
  "id": "trace-event-13",
  "timestamp": 1781971932323,
  "pipeId": "ddfd75bf-fa86-46df-9879-afe8b6d8bb16",
  "pipeName": "legality checker pipe",
  "eventType": "PIPE_START",
  "phase": "INITIALIZATION",
  "metadata": { ... }
}
```

Key fields:
- `pipeId` — UUID; identical across events from the same pipe instance. Different events with the same `pipeId` = same run.
- `pipeName` — names nested pipes as `<outer>-><inner>`, e.g. `style reapply pipe->validator pipe`.
- `eventType` — see event taxonomy below.
- `metadata.actualInputTokens` / `outputTokens` / `responseLength` — token + char accounting.
- `metadata.modelId` — `arn:aws:bedrock:...foundation-model/...` for the model that actually answered.

## Event Taxonomy

| Event | Phase | What it means |
|---|---|---|
| `PIPE_START` | INITIALIZATION / EXECUTION | Pipe entry. INITIALIZATION runs pre-init, EXECUTION is the LLM call. |
| `PIPE_SUCCESS` | CLEANUP | Pipe finished its body successfully. |
| `CONTEXT_PULL` / `CONTEXT_PREPARED` | CONTEXT_PREPARATION | Context loaded; `CONTEXT_PREPARED` includes `actualInputTokens`. |
| `API_CALL_START` / `API_CALL_SUCCESS` | EXECUTION | One LLM call. `API_CALL_SUCCESS` includes `responseLength` and `outputTokens`. |
| `PRE_INVOKE` | PRE_VALIDATION | Pre-invocation function called. **Logs TWICE per call** — see pitfall below. |
| `VALIDATION_START` / `VALIDATION_SUCCESS` | PRE_VALIDATION / VALIDATION | Validator LLM result. |
| `BRANCH_PIPE_TRIGGERED` | VALIDATION | Main pipe's validator FAILED; fallback pipe is being invoked. |
| `POST_GENERATE` | VALIDATION | Pipe produced its final output. |
| `TRANSFORMATION_START` / `TRANSFORMATION_SUCCESS` | TRANSFORMATION | Transformation function ran on the pipe's output. This is where the play text gets REPLACED. |
| `PIPE_SUCCESS` | CLEANUP | Pipe's body finished; the next pipe in the pipeline can start. |

## The Validator Pipeline — What Each Pipe Does

Defined in `server/src/main/kotlin/agent/builders/validateAction/validator.kt`. Three pipes run in sequence:

### 1. legalityCheckerPipe
- LLM call against the rulebook. Outputs JSON `{isLegal, changesToMake, captureAttempted}`.
- `setTransformationFunction` (lines 449-472) stashes `captureAttempted` to the context bank and, if `isLegal=false && changesToMake.isEmpty()`, fabricates a "do nothing" fallback.
- Has a `validatorPipe` and a `branchPipe` (lines 358, 479-490). The branch uses Palmyra X5 instead of Qwen Coder.
- `BRANCH_PIPE_TRIGGERED` here = main legality check FAILED validation; branch re-check ran.

### 2. legalityRectifierPipe
- Has a `setPreInvokeFunction` (lines 600-625) that:
  - If `isLegal=true`: restores the original user prompt from `"user prompt"` context-bank entry, logs `"true - skip"`, returns true → pipe is SKIPPED.
  - If `isLegal=false`: returns false → pipe body runs and rewrites the play.
- **If the legality check passed, the rectifier's body never executes. There is NO `PIPE_SUCCESS` for this pipe when it skips.** It will show `PIPE_START` → `CONTEXT_PULL` → 2× `PRE_INVOKE` → and then nothing.
- Only this pipe can REWRITE a play due to illegality.

### 3. styleReapplyPipe
- LLM call converts the play to third person. Outputs JSON `{needsChanges, newOutput}`.
- `setTransformationFunction` (lines 748-762) **unconditionally replaces `it.text` with `result.newOutput`** — even when `needsChanges=false`. If JSON extraction fails, restores the snapshot.
- Has its own `validatorPipe` and `branchPipe` (lines 732-746). Branch also uses Palmyra X5.
- `BRANCH_PIPE_TRIGGERED` here = third-person conversion FAILED validation; branch (different model) re-generates it. **This is the most common "nuke" path for legal plays.**

## Pitfalls (READ THESE FIRST)

### Pitfall 1: PRE_INVOKE is logged TWICE per call
The trace logs `PRE_INVOKE` once when the function is entered (metadata has `invokeFunctionName`) and once when it exits (metadata has `exitingInvoke`). These are 1ms apart. **Do not mistake this for "the pipe ran twice."** It is one invocation that the trace emitter wraps in enter + exit events. If you see only those two PRE_INVOKE events with no PIPE_SUCCESS afterward, the pre-invoke returned `true` (skip) or threw — the pipe body never ran.

### Pitfall 2: author pipe appearing 4× is normal
The `author` pipe is a generic LLM-call wrapper reused by:
1. The original play-generation call.
2. The legality checker pipe's reasoning pipe.
3. The legality checker pipe's validator pipe (its own LLM call).
4. The style reapply pipe's reasoning pipe.
5. The style reapply pipe's validator pipe.
6. The style reapply pipe's branch pipe's reasoning pipe.

If you see 4-6 `author` events in a single trace file, that is NOT a bug. Each has a distinct `pipeId` (UUID). The play text only changes at `TRANSFORMATION_SUCCESS` events of the outer pipe (legality checker, legality rectifier, style reapply) — not at intermediate author calls.

### Pitfall 3: Silent skip vs PIPE_SUCCESS
A pipe that skips via pre-invoke has NO `PIPE_SUCCESS`. The trace just... ends. If you see a `PIPE_START` followed by 1-2 events and then a different pipe starts, the first one was skipped, not failed. There is no error.

### Pitfall 4: BRANCH_PIPE_TRIGGERED = the validator REJECTED the main output
Do not confuse `BRANCH_PIPE_TRIGGERED` (in metadata) with the branch pipe's successful run. The trigger event means: "main pipe's validator said no; we are now invoking the fallback." The branch pipe then runs, validates, and either passes or fails.

### Pitfall 5: The third-person "nuke" can happen even when the play is legal
The style reapply pipe runs UNCONDITIONALLY — it does not check whether the play is already in third person. Its LLM is asked to convert the play; even if it makes no changes, the LLM is asked to produce a `newOutput` field. If the validator rejects that output, the branch pipe (Palmyra X5) re-generates it, and the transformation function replaces the play with the branch's `newOutput`. This is the dominant "my play got changed" failure mode.

### Pitfall 6: Validator pipeline output is what downstream uses
`gameplayOrchestrator.kt:484` reads the validator pipeline's final output as the user's validated play. Anything the rectifier or style reapply wrote is what the Judge, NeoWritingAgent, and outcome resolvers all see. If the play "got nuked," the nuke happened in one of those two pipes' transformation functions.

### Pitfall 7: NPC-only turns have no Judge trace
Some turns are NPC-only — the player didn't act, only NPCs did. The turn directory contains only `NPC_*` subdirectories (e.g. `NPC_Judge/`, `NPC_TargetDetectors/`, `NPC_Validation/`). **There is no `Judge/` subdirectory.** The `NPC_Judge` trace records NPC adjudication, not human play validation. When asked "what happened in turn X", check whether `Judge/trace.json` exists before assuming the human played. Confirmed pattern: `Round_3_Turn_1_Syrup_Whisperer/` has only NPC-prefixed directories — it was an NPC turn.

### Pitfall 8: Incomplete turns may have no Judge trace at all
Some turns fail mid-pipeline and only partial traces exist: `AI_Player_Takeover/`, `TargetDetectors/`, `WritingAgents/` but no `Judge/`, no `ValidationSplitter/`, no `ReversalAgent/`. Confirmed pattern: `Round_4_Turn_1_Robert/` is incomplete. When the game history says one thing but no Judge trace exists for that turn, the turn was interrupted. The `game_snapshot.json` is written after each *completed* turn and represents the last fully-resolved state — use it as the source of truth for what actually happened.

### Pitfall 9: Strategic-pipe in-flight stall with token-delta duplication runaway (POST-MANTLE-CUTOVER)
Distinct from Pitfalls 7 and 8 — those are early-exit errors (PIPE_FAILURE / API_CALL_FAILURE). This stall **never fails**: the strategic pipe's LLM call starts, returns partial 248-byte deltas, but never emits a completion signal. The streaming emitter broadcasts the deltas at the normal 250ms cadence, and an accumulator bug causes each delta to be re-broadcast 1–12× per tick before advancing. Visible to the user as token/subword duplication (`II must must balance balance`, `ApplyingApplying structural structural`).

**Key signals** (in order of confidence):
1. Browser log shows > 500 `AgentWorkStreamManager.handleStream ... isComplete=false` chunks, **0 with `isComplete=true`** (the stream never closes).
2. Server log shows `analysisPipe.setTransformationFunction success` but no equivalent log line for `strategicPlanningPipe` for the same turn — the strategic pipe is stuck in initialization or stalled mid-LLM-call.
3. Chunk sizes are exact multiples of 248: 248, 496 (2×), 744 (3×), 992 (4×), 1240 (5×), 1488 (6×), 1736 (7×), 1984 (8×), 2232 (9×), 2728 (11×), 2976 (12×).
4. Server log shows `[WARN] Cannot send agent work stream, session not found` continuing for 1–2s AFTER the client disconnects — the streaming emitter is still trying to push chunks to the dead session.
5. Server log shows `[ERROR] Failed to initialize Bedrock inference config: bedrock.local.properties missing key 'bedrock.llamaScout17B'` near pipeline-build time. The Mantle/Bedrock fallback inference client failed to initialize, leaving the strategic pipe calling an uninitialized or stub client.

**Likely root cause**: broken Bedrock inference client initialization (missing config key) → strategic pipe's LLM call returns a degenerating stream of partial deltas → stream emitter re-broadcasts each delta N× per tick → no completion event ever fires → TurnHarness coroutine waits forever (the only safety net is the cosmetic `scheduleMusicRerollFallback` 5-min timer, not a pipeline-level timeout).

**No TPipe trace breadcrumbs** when `AUTOGENESIS_DEBUG_TRACE=false` (the default). The trace directory is cleared at boot (`Trace directory cleared (1 entries)` in server log). The failure is observable only via the **server log + browser log** — not via the per-pipe trace files described elsewhere in this skill. Full reproduction recipe in `references/strategic-pipe-stall-2026-08-02.md`.

**Distinct from Round_4_Turn_1_Robert trace gap in Pitfall 8**: Pitfall 8's incomplete trace was an *early-exit* failure (turn interrupted). The 2026-08-02 stall is a *late-exit* failure (turn never exits). Both produced a `Round_4_Turn_1_Robert/` partial trace if `AUTOGENESIS_DEBUG_TRACE=true` had been set — but the failure-mode diagnostics (early-exit vs. late-exit) require the server/browser logs, not the trace directory.

### Pitfall 11: For `BedrockMultimodalPipe` consumers, the LLM verdict lives in `metadata.outputText` of `PIPE_SUCCESS` — NOT in `content.text` (2026-08-11)

When reading trace JSON for a pipe built with `BedrockMultimodalPipe().apply { setJsonOutput(...) }`, do not extract the LLM verdict from `content.text` — that field often contains the INBOUND content that flowed into the pipe, not the response. For non-streaming or single-shot pipes, the actual LLM verdict lives in `metadata.outputText` of the `PIPE_SUCCESS` event.

**The recipe:**

```python
import json
with open('<trace>.json') as f:
    events = json.load(f)
for target in ['<pipe-name-1>', '<pipe-name-2>']:
    # Walk backwards through events to find the LAST PIPE_SUCCESS for this pipe
    for ev in reversed(events):
        if ev.get('pipeName') == target and ev.get('eventType') == 'PIPE_SUCCESS':
            ot = ev.get('metadata', {}).get('outputText', '')
            print(f"{target} outputText: {ot[:1500]}")
            break
```

**Symptom when missed:** the `extractJson<T>(result.text)` call on the inbound `MultimodalContent` returns a stub verdict with empty fields (the inbound map JSON gets parsed as if it were the verdict). The trace `PIPE_SUCCESS.metadata.outputText` carries the real verdict.

**Why this happens:** `BedrockMultimodalPipe` carries the inbound `MultimodalContent` (which the `setPreInitFunction` rebuilt to hold the pipe's own artifact — image bytes for the image pipe, serialized map JSON for the text pipe) through `API_CALL_SUCCESS` events with the same `content.text`. The LLM's actual response is captured into `metadata.outputText` separately. Reading `content.text` gives you the pipe's input, not its output.

**Verified pattern:** the safety-agent live test (`MapUploadSafetyAgentLiveTest`, trace dir `~/.tpipe/debug/trace/MapUploadGate/`) extracts distinct image-pipe and text-pipe verdicts this way. Each pipe's `outputText` carries the LLM's JSON response, while `content.text` carries the rebuilt inbound content (image bytes echo via metadata in `API_CALL_SUCCESS`, or the map JSON echoed in `content.text` for the text pipe).

**When `content.text` IS the verdict:** for `GenericOpenAIPipe` pipes or pipes built without `setJsonOutput`, the LLM response may land directly in `content.text`. Always probe `metadata.outputText` first; fall back to `content.text` only when `outputText` is empty.



When the player asks "why did I win/lose territory X even though my action clearly failed in-fiction," the answer is that the Judge pipes never see the in-fiction outcome. They extract the verdict from the writing agents' prose. The decision rule is mechanistic:

1. **Writing agents** produce the turn narrative (the prose the player reads).
2. **Play Detection Agent** classifies the play as Military/Research/Diplomatic.
3. **Judge pipes** (`gains and losses pipe`, `stat change pipe`, `explicit cot`) extract the verdict:
   - `gains and losses pipe` emits `{territoryGained: [...], territoryLost: [...], ...}` — the canonical territory tally.
   - `stat change pipe` emits `{territoryStatChanges: [...]}` with per-territory `militaryThreatStat`/`diplomacyThreatStat` deltas and `reasoning` strings explaining each.
   - `explicit cot` emits the step-by-step reasoning ("meets automatic capture criteria" is the key recurring phrase).

**The rule fires on presence, not gradient.** If the prose names a target territory AND describes *any* military effect on it (immobilization, sabotage, even diplomatic adoption), the territory gets awarded. The judge never re-derives whether the "effect" was a real victory. Confirmed worked example: Round 1 Turn 0 Lord Maple Tree was awarded Sudan + Ethiopia despite the writing agents explicitly stating his tanks got stuck in cement ("General Flipper declared victory" + "Ethiopian forces recognized strategic value and secured the area" were the trigger phrases).

**Symptom signaling this fired:**
- Player says "I won territory X but my action clearly failed" or "the verdict doesn't match what I described."
- `gains and losses pipe` output contains territory names that match the prose but not the declared intent.
- `stat change pipe` `territoryStatChanges[*].reasoning` strings read like the LLM massaging a defeat into a victory ("successful military campaign", "secured the area", "tactical success").

**What to do:** Extract the gains/losses JSON, the stat-change JSON, and the explicit-cot reasoning from the Judge trace. Show the player the exact pipeline step that assigned the territory (it is always "named in prose + military-effect sentence present"). Point them at the prose lines that triggered the verdict. Do not try to "re-adjudicate" — the judge will give the same answer if you re-run it. Full recipe + worked example in `references/judge-decision-extraction.md`.

## Investigation Procedure

1. **Find the trace files.** `ls ~/.tpipe/debug/trace/ | grep -i <playername>` (legacy: `ls /tmp/autogenesis_pm/ | grep -i <playername>`). Look for any file with `validator` in its name — that is the one with the most detail.
2. **Read the validator trace in chronological order.** Group events by `pipeId` (UUID) to identify which runs are which.
3. **Identify PIPE_STARTs of the three outer pipes:**
   - `legality checker pipe` PIPE_START → legality check
   - `legality rectifier pipe` PIPE_START → only proceeds if legality failed
   - `style reapply pipe` PIPE_START → always runs; this is the third-person conversion
4. **For each pipe, look at its TRANSFORMATION_SUCCESS.** That is where the play text was rewritten. If no TRANSFORMATION event exists for the pipe, the pipe's body never ran (skipped via pre-invoke).
5. **Look for `BRANCH_PIPE_TRIGGERED` events.** The pipe containing this event had its main validator fail; the branch pipe's output is what replaced the play.
6. **For style reapply, also check the `style reapply pipe->validator pipe` events.** This nested pipe validates the third-person conversion. Its `VALIDATION_SUCCESS` is what the framework uses to decide whether to keep the main output or invoke the branch.
7. **Compare responseLengths across LLM calls in the same pipe.** A radically different length between main and branch calls = branch produced substantively different output. The branch's `newOutput` is what wrote the play.
8. **If you need the actual play text, it is NOT in the trace metadata** — `generatedContent` fields are truncated to ~200 chars. The real play is held in pipeline internal state and only persisted as the validator pipeline's final output. To inspect it, look at downstream pipes' `CONTEXT_PULL` metadata, which embeds the prior output.

## Lorebank Narrative Surface — What a Real Game Session Actually Looked Like

When you need to understand the **gameplay experience** (not the pipeline mechanics), the lorebank `.bank` files at `~/.tpipe/TPipe-Default/memory/lorebook/` are the closest thing to a play-by-play recording. They capture the actual in-character text that every persona, commander, and NPC produced during a session — verbatim, with no truncation or post-hoc summarization.

### File naming

Two filename patterns:

| Pattern | What it is | Example |
|---|---|---|
| `chat-kvision-ws-client-<id>-<persona>.bank` | A specific persona/commander's in-character dialogue history in one chat session. The `<id>` is the kvision websocket session id; the `<persona>` is the named character. | `chat-kvision-ws-client-1935385562-Judge Null.bank`, `chat-kvision-ws-client-1221884115-Zeta.bank` |
| `kvision-ws-client-<id>.bank` | The "world bank" for a session — the running game-state narrative, often including operator Q&A introspections ("Who is winning?", "What resources does each player have?"). The `<id>` is the same session id as above. | `kvision-ws-client-1012021450.bank` (56KB — a long-running Mass Effect-themed session) |

A persona can appear in multiple chat-`*.bank` files if the same character was used in different sessions (e.g. `Wilfred Brimley` shows up in three different sessions). When you see the same persona name across files, you've found a recurring NPC.

### Known personas confirmed in the lorebanks (as of mid-2026)

These are the characters that have actually been played in real game sessions. Use this list as a vocabulary reference when the user mentions a persona by name and you want to find their session traces:

- **Bigwang McDouchebag** (CEO of Ten Trillion Triangles — the operator playing as their own persona)
- **Shitty Bob** (chaotic-crude persona, scripted NPC variant)
- **Wilfred Brimley** (1980s diabeetus-medication-commercial actor NPC, weaponized by Lord Maple Tree as a propaganda spokesman)
- **Narjodo Bazingazooka** (cosmic intergalactic bureaucrat NPC; files Supreme Tribunal lawsuits citing Cosmic Statute 1.0.1Γ)
- **Judge Null** (eldritch cosmic judge NPC; procedurally unpersons litigants; "no sound when the gavel falls")
- **Nordold** (metafictional author-of-reality NPC; "I am already in your syntax"; infects names with Narrative Compliance Strain-Ω)
- **Zeta** (Commander archetype running pure 4X military-expansion strategy)
- **The Illusive Man, Commander Shepard** (Mass-Effect-themed commanders — confirming that fictional-IP commanders are playable)

### File format

Each `.bank` is a JSON object with a `converseHistory.history` array. Each history entry has `role` (mostly `"assistant"` for NPC/persona output, occasionally `"user"` for the human player's prompt) and `content.text` containing the verbatim in-character prose. The `loreBookKeys` and `contextElements` arrays are typically empty — the lorebanks are dialogue-only, not full game-state.

```json
{
  "loreBookKeys": {},
  "contextElements": [],
  "converseHistory": {
    "history": [
      {"role": "assistant", "content": {"text": "...the full in-character text..."}}
    ]
  },
  "version": 0
}
```

### How to find lorebanks for a given persona

Use `scripts/find_lorebanks.py <persona-substring>` (or `grep` directly) to list matching files. Then read the file with offset/limit — most are 1-30KB; the longest session banks are 50-80KB and may need paging.

**Always pair chat-`*.bank` with the world-`kvision-ws-client-<id>.bank` of the same `<id>`** — the chat bank shows what the persona said, the world bank of the same id shows the game's response and the broader turn narrative. Together they reconstruct the full turn.

### When the lorebank surface beats the pipeline traces

| If you need to… | Use |
|---|---|
| Debug "my play got changed" | Pipeline traces (legalityRectifier / styleReapply) |
| Show the user what the game feels like in practice | Lorebank traces — they're the play-by-play |
| Confirm whether a persona has ever been played | `ls ~/.tpipe/TPipe-Default/memory/lorebook/chat-*.bank \| grep -i '<persona>'` |
| Extract canonical examples of in-character narration for documentation/marketing | Lorebank traces — pull the verbatim text |
| Trace which LLM model produced a specific pipe's output | Pipeline traces (metadata.modelId) |
| Reconstruct what a persona would say in a NEW context | Lorebank traces — they're the persona's voice sample |

For a worked example showing what each persona's bank actually contains (full dialogue excerpts, turn-by-turn flow, cross-referenced with the matching world bank), see `references/lorebank-narrative-surface.md`.

## When to Load References

- The pipe-3rd-person-nuke case study: see `references/validator-pipeline-nuke.md` for a full worked example with trace event numbers, code line references, and a 3-pipe event-by-event walkthrough from a real session (Lord Maple Tree Turn 0, June 20 2026).
- The lorebank narrative surface worked example: see `references/lorebank-narrative-surface.md` for a tour of every confirmed persona's in-character dialogue, a cross-reference of `chat-<id>-<persona>.bank` to the matching `kvision-ws-client-<id>.bank` world bank, and the exact grep recipes for finding lorebanks by persona.
- **Gameplay progression and swing magnitude:** see `references/gameplay-progression-and-swing-magnitude.md` — the `game_snapshot.json → history[]` extraction path, territory exchange patterns, NPC-only turn detection, incomplete turn patterns, and Judge pipeline token burn numbers for Round 3-4 turns.

- **Strategic-pipe in-flight stall (2026-08-02 worked example):** see `references/strategic-pipe-stall-2026-08-02.md` — the full server-log + browser-log timeline of the 4m35s Round-4-Turn-1 Robert stall, the 22-second inter-pipe silence, the 248×N chunk-size fan-out math (visible as `II must must balance balance` / `ApplyingApplying structural structural`), and the broken Bedrock `llamaScout17B` config error at server log L254. **Required reading** when the user reports the Agent Work Stream stuck / streaming never completing / turn never resolving — these symptoms leave no TPipe trace breadcrumbs when `AUTOGENESIS_DEBUG_TRACE=false`, so the server + browser logs are the only diagnostic surface.

- **Agent Work Stream callback duplication (2026-08-02):** see `references/agent-work-stream-duplication.md` — when the Agent Work Stream shows per-token doubling (`II`, ` must must`, malformed JSON) but the stream *does* complete normally (the opposite of the strategic-pipe stall above). Cause: the work-stream factory and `ResponseRefinementAgent`'s self-registration both attach dispatcher callbacks to nested `GenericOpenAIPipe` reasoning pipes, and TPipe's `propagateStreamingCallback` already walks descendants — same lambda-reference dedupe gap as Bedrock's but unmitigated by Bedrock's single-source-of-truth pattern. Fixes touch `AgentWorkStreamStreaming.kt:107` (drop explicit reasoning recursion) and `ResponseRefinementAgent.kt:99-110` / `:181-192` (remove duplicate self-registration).

- **Judge decision extraction (2026-08-08):** see `references/judge-decision-extraction.md` — the 9-pipe Judge chain mapping (gains/losses, stat change, explicit cot are the decisive pipes), the territory verdict extraction recipe, and the Round 1 Turn 0 Lord Maple Tree worked example (Sudan + Ethiopia awarded despite tanks being immobilized in cement). Required reading when the player asks "why did I win/lose territory X despite the in-fiction mess" — the judge is a narrative extractor, not a battlefield adjudicator.

- The `audioTracks` field leaking into agent prompts: see `references/audio-tracks-leak.md` for the full end-to-end audit — all 10 `serialize(WorldManager.world)` call sites, the kotlinx.serialization `encodeDefaults = false` behavior that causes the full catalog to serialize, the snapshot/restore path that preserves it, and the `@Transient` fix.

## Diagnostic Scripts

**Pipeline traces** — run `scripts/analyze_validator_trace.py <path-to-validator-trace.json>` to automatically print:
- All distinct pipe runs (by UUID) and their completion status
- Top-level PIPE_STARTs in chronological order
- All play-rewriting events (TRANSFORMATION_SUCCESS, BRANCH_PIPE_TRIGGERED)
- The legality-rectifier silent-skip detection (PIPE_START + 2 PRE_INVOKE + no PIPE_SUCCESS)
- The style-reapply branch trigger with an explanation
- All author-pipe LLM calls with model and response length

This is faster than reading the trace by hand and catches the patterns the pitfalls section describes.

**Lorebank narrative traces** — run `scripts/find_lorebanks.py [persona-substring]` to list all lorebank files matching a persona name (or omit the substring to list everything). Output is one row per file: filename, size, persona name (or "—world—" for the world banks), session id, and a one-line preview of the latest in-character text. Use this to jump straight from "what does Lord Maple Tree actually say" to the file that proves it.
