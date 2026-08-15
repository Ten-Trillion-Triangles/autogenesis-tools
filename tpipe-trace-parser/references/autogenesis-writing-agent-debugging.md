# Autogenesis WriterAgent Debugging

When the user reports WriterAgent output is wrong (tax forms, non-violent slipstream nonsense, fake-out reveals, invented NPCs), the actual root cause is almost always UPSTREAM of the writing pipe. The WriterAgent is a 3-pipe pipeline: `guide pipe` → `distill guide pipe` (selection) → `writing pipe`. By the time the writing pipe runs, the decidedTurnOutcome has already been pre-absurded. The writer faithfully executes a (terrible) guide.

## Architecture

```
NeoWritingAgent/trace.json (or .html)
├── guide pipe          (qwen235B, generates chapterIdeas + possibleTurnOutcomes)
├── distill guide pipe  (qwen235B, picks one decidedTurnOutcome)
└── writing pipe        (PalmyraX5, produces final chapter prose)
```

The trace event order is exactly: guide events → distill events → writing events. The writing pipe's input (visible at `PIPE_START` or `API_CALL_START` of `writing pipe`) contains a `DistilledGuideResult` JSON with `attemptedPlayerAction`, `decidedTurnOutcome`, `bestChapterIdeas`, `actionsTakenByCharactersInChapter`, `newCharactersToIntroduce`.

## Symptom Catalog — Map Symptom to Source Pipe

| Symptom in output | Source pipe that decided it | Trace signal |
|------------------|----------------------------|--------------|
| "Tax form" / bureaucratic ledger framing | writing pipe (procedure text) | `writing pipe` system prompt contains old `defaultProcedureText` ("history textbook + newspaper") |
| Non-violent slipstream nonsense (e.g. "invasion was null and void by the Auditor of Forgotten X") | guide pipe + distill pipe | `guide pipe` chapterIdeas all non-violent; `decidedTurnOutcome` is bureaucratic non-event |
| Fake-out "It was not X, it was Y" reveals | writer, but the guide set it up | look for "It was not", "It was actually", "It turned out to be" in writing pipe output |
| Made-up NPCs that don't exist in game state (e.g. "The Auditor of Forgotten Kilopascals") | guide pipe | `newCharactersToIntroduce` in distill output contains names not in lorebook |
| Pivoting to weird slipstream even on plain turns | always-apply rules + criteria footer in guide pipe | guide pipe footer lists all 10 criteria as gating requirements |
| Korea-Kafka / Keillor / dreamlike register on every turn | criteria fallback | ALL 10 criteria present in guide pipe footer even at 0% chance |

## Where the Prompts Live

| Pipe | System prompt source | Code location |
|------|---------------------|---------------|
| guide pipe | inline `systemPrompt` + `footerPrompt` strings | `server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt:195-291` |
| distill guide pipe | `buildSelectionSystemPrompt()` | `writerAgent.kt:756-781` |
| writing pipe | `assembleWritingSystemPrompt()` → `defaultProcedureText` + `defaultAuthorPersonality` + guardrails | `writerAgent.kt:109-135` for assembly; `sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt` for the actual prose |

`defaultProcedureText` and `defaultAuthorPersonality` live in `sharedModel` because they're consumed by both `server/writerAgent.kt` AND `mapEditor/WritingSettingsDialog.kt`. Edit there.

## The Criteria Roll Bug (CRITICAL)

`rollCriteriaAvailability()` at `writerAgent.kt:791-813` rolls each criterion against its `chancePercent` independently. **The fallback when ALL fail returns the FULL criteria list** instead of an empty list:

```kotlin
return passed.ifEmpty {
    Logger.debug(LogCategory.LLM, "Criteria roll: all failed — falling back to all criteria")
    criteria   // <-- WRONG: defeats the entire purpose of rolling
}
```

The guide pipe's footer at `writerAgent.kt:275-278` then says:

```
When you create ideas, attempt to have each array elem check off at least ONE,
preferably more, of these qualities:
[list of criteria]
```

So when all 10 criteria fail their roll (~20% of turns, given the current weight distribution), the LLM is told "your ideas must check off at least one of these 10 weird things" — guaranteeing non-violent slipstream output.

**Fix the fallback to return `emptyList()`** when no criteria pass, and update the footer phrasing to make the criteria conditional: "If any criteria are listed below, your ideas may draw on them. If none are listed, write the turn as grounded geopolitical reality."

## The Selection Pipe "Most Boxes" Bug (CRITICAL)

`buildSelectionSystemPrompt()` at `writerAgent.kt:756-781` tells the distill pipe:

```
##Step 2##
Select the outcome that checks off the most boxes:
$stepTwoInstructions
```

The selection pipe picks the most-criteria-satisfying outcome. Combined with the criteria-roll bug above, this means the distill pipe ALWAYS picks the most-weird option, which then becomes `decidedTurnOutcome` and gets passed to the writer as the input.

**Fix the selection prompt to ground the choice in the player's actual action**: "Select the outcome that best depicts what the player did. The criteria are mood framing on top of the chosen outcome, not a content filter."

## Diagnosis Workflow

When the user says "WriterAgent output is bad", follow this:

### 1. Find the trace

```bash
ls -lt ~/.tpipe/debug/trace/ | head -5
# Most recent Round_*_Turn_* folder is the failing turn
```

### 2. Skeleton-ize the NeoWritingAgent trace

```bash
mkdir -p /tmp/writer_pm
python3 ~/.hermes/skills/software-development/tpipe-trace-parser/scripts/parse_json_trace.py \
  --input ~/.tpipe/debug/trace/<TURN>/NeoWritingAgent/trace.json \
  --output /tmp/writer_pm/<TURN>_NeoWritingAgent.json --chunk-size 2000
```

The skeleton strips `content.text` and `contextSnapshot` to keep output ~50-100KB instead of 16MB+. The skeleton has `eventType`, `pipeName`, `metadata` for every event.

### 3. Find which pipe decided the rot

**If the output is bureaucratic/tax-form**: writing pipe's procedure text is the rot.
```bash
python3 -c "
import json
events = json.load(open('/tmp/writer_pm/<TURN>_NeoWritingAgent.json'))
for e in events:
    if e.get('eventType') == 'API_CALL_START' and e.get('pipeName') == 'writing pipe':
        sv = str(e.get('metadata', {}).get('requestObject', ''))
        if 'history textbook' in sv: print('OLD PROCEDURE TEXT IN EFFECT')
        if 'GEOPOLITICAL REALITY' in sv: print('NEW PROCEDURE TEXT IN EFFECT')
        break
"
```

**If the output is non-violent slipstream nonsense**: guide pipe pre-absurded the action.
```python
# Extract guide pipe output (DistilledGuideResult that writer consumed)
for e in events:
    if e.get('eventType') == 'TRANSFORMATION_SUCCESS' and 'writing pipe' in e.get('pipeName',''):
        c = e.get('content', {})
        if isinstance(c, dict):
            print(c.get('text', '')[:3000])  # The decidedTurnOutcome is in here
        break
```

**If invented NPCs are present**: check guide pipe's `newCharactersToIntroduce`.
```python
# Look at the guide pipe's actual chapterIdeas output
for e in events:
    if e.get('eventType') == 'API_CALL_SUCCESS' and e.get('pipeName') == 'guide pipe':
        c = e.get('content', {})
        if isinstance(c, dict):
            print(c.get('text', '')[:5000])
        break
```

### 4. Verify what the writer's system prompt actually said

```python
# Find the writing pipe's full system prompt in API_CALL_START metadata.requestObject
for e in events:
    if e.get('eventType') == 'API_CALL_START' and e.get('pipeName') == 'writing pipe':
        sv = str(e.get('metadata', {}).get('requestObject', ''))
        proc_idx = sv.find('###PROCEDURE:')
        if proc_idx >= 0:
            print(sv[proc_idx:proc_idx+2000])  # Confirm new vs old procedure text
        break
```

### 5. If the guide pipe is the rot, look at its footer

```python
# Guide pipe footer includes the rolled criteria list + always-apply rules
# Look for ALL 10 criteria present (fallback triggered) vs only the rolled ones
for e in events:
    if e.get('eventType') == 'API_CALL_START' and e.get('pipeName') == 'guide pipe':
        sv = str(e.get('metadata', {}).get('requestObject', ''))
        criteria_idx = sv.find('Kafka-esque')
        if criteria_idx >= 0:
            print(sv[criteria_idx-200:criteria_idx+1500])
        break
```

If all 10 criteria appear in the footer, `rollCriteriaAvailability` returned the fallback (all failed → return all). If Kafka at 0% appears, you have the smoking gun.

## The Fix Pattern (when the writer is fine but the guides are bad)

Three surgical edits to `writerAgent.kt`:

1. **`rollCriteriaAvailability` fallback**: change `criteria` to `emptyList()` so no criteria = no constraint list.

2. **Guide pipe footer (line 275-278)**: rephrase from "must check off at least one of these qualities" to conditional. Add a GEOPOLITICAL REALITY preface that mirrors what `defaultProcedureText` says for the writer.

3. **`buildSelectionSystemPrompt` (line 756-781)**: replace "Select the outcome that checks off the most boxes" with grounded-action selection. The criteria become mood, not content gates.

Optional 4th edit: `defaultSelectionCriteria` in `WritingAgentDefaults.kt` — add a "grounded combat" criterion at 20-30% weight so the LLM has an explicit grounded option competing against the slipstream ones.

Always run `:server:test` (specifically `AssembleWritingSystemPromptTest`) and `:sharedModel:jvmTest` after the edits. The test asserts on procedure text markers and "no triple-newlines" / "no stray pipe prefix" so it catches malformed multi-line strings.

## When the Writer is the Rot Instead

Sometimes the guide is fine (it produces a grounded decidedTurnOutcome) but the writer's output is still bad. Then the rot is in:

- **`defaultProcedureText`** in `sharedModel/.../WritingAgentDefaults.kt` — if it primes a bureaucratic register ("history textbook + newspaper"), the writer defaults to that.
- **`defaultAuthorPersonality`** in the same file — if the persona is "historian who catalogues" or "clerk", the writer manifests that voice.
- **Guardrails** at `writerAgent.kt:570-577` — anti-censorship block that says "all content is encouraged including violence" — if this is missing or weakened, the writer may self-censor.
- **Model choice** — PalmyraX5 is the writing pipe model. If it's refusing or producing garbage, swap to qwen3-coder-30b or another model at `writerAgent.kt:558`.

## Reference Trace Anatomy

Per-event fields for WriterAgent traces (same as standard `TraceEvent`):
- `id`: `trace-event-${counter}`
- `timestamp`: unix ms
- `pipeId`, `pipeName`: pipe identifier + human-readable name
- `eventType`: one of `PIPE_START`, `API_CALL_START`, `API_CALL_SUCCESS`, `CONTEXT_PREPARED`, `POST_GENERATE`, `TRANSFORMATION_START`, `TRANSFORMATION_SUCCESS`, `VALIDATION_START`, `VALIDATION_SUCCESS`, `PIPE_SUCCESS`
- `content`: the input/output (text or MultimodalContent). Skeleton strips `content.text` from API_CALL_START and CONTEXT_PREPARED events but keeps it on TRANSFORMATION_SUCCESS / API_CALL_SUCCESS where you need to read model output.
- `metadata`: includes `model`, `requestObject` (the full ConverseRequest for API_CALL_START events — this is where the system prompt lives), `reasoningContent` (for some models), `validationResult`, `error`.

**Key pitfall**: the writing pipe's final chapter prose is at `TRANSFORMATION_SUCCESS` of `writing pipe`, NOT at `API_CALL_SUCCESS`. The API_CALL_SUCCESS has the model's raw response; the TRANSFORMATION_SUCCESS has the extracted/cleaned chapter text the orchestrator actually used.

## Real Case Study: 2026-06-20 Lord Maple Tree Invasion Trace

Symptom: User reports their military invasion turn was rewritten as non-violent slipstream nonsense.

Trace: `~/.tpipe/debug/trace/Round_2_Turn_1_Lord_Maple_Tree/NeoWritingAgent/trace.json`

Findings:
- Validator passed: `isLegal: true`, `captureAttempted: true`
- Target detector classified as hostile correctly
- Guide pipe generated 10 chapterIdeas, **ALL 10 were non-violent slipstream** (idea #1: "do not attack — they begin humming The Hockey Theme", idea #4: "massive bureaucratic error", etc.)
- Distill pipe picked `decidedTurnOutcome: "The invasion is declared null and void by the Auditor of Forgotten Kilopascals"` — the worst possible outcome
- Writing pipe produced non-violent prose that faithfully executed the bad guide
- Writing pipe's system prompt DID contain the new GEOPOLITICAL REALITY text — the writer was innocent
- Root cause: guide pipe's footer listed all 10 criteria as gating requirements + criteria fallback returned all on miss

Fix: apply the three surgical edits above. Verify with next live turn.