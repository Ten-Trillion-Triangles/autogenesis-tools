# The "Validator Pipeline Nuke" — Worked Example

Real session: Round 1 Turn 0, Lord Maple Tree, June 20 2026 13:29 UTC.
Files in `/tmp/autogenesis_pm/`.

## What the Player Reported

> "It looks like it passed the check, but then something ran twice or something? And then failed the check and nukeed my play."

Three observable symptoms:
1. The legality check appeared to pass.
2. Some component "ran twice" in the trace viewer.
3. The play text in the final turn was different from what was originally submitted.

## The Trace Walkthrough

The validator file (`Round_1_Turn_0_Lord_Maple_Tree_validator_1781972028865.json`) had 124 events over 96.5 seconds. Six distinct `pipeId` UUIDs were present, covering the three outer pipes plus three nested validator pipes.

### Stage 1: legalityCheckerPipe (events 0-59)

| Events | What |
|---|---|
| 0-3 | PIPE_START + CONTEXT_PULL + CONTEXT_PREPARED (16,442 input tokens) |
| 4-18 | `author` pipe run #1 (Qwen Coder 30B, 4947 char response) — produces the legality-check reasoning |
| 19-28 | legality checker pipe's own LLM call; 28 = `BRANCH_PIPE_TRIGGERED` |
| 29-31 | `legality checker pipe->validator pipe` PRE_VALIDATION SUCCESS |
| 32-56 | `legality checker pipe->validator pipe` full LLM run (`author` #2, 4655 chars) + VALIDATION SUCCESS |
| 57-59 | TRANSFORMATION + PIPE_SUCCESS |

**Branch trigger at event 28** is normal here — the legality checker pipe always has both a main and a branch pipe configured. The branch (Palmyra X5) ran and produced a passing validation. Result: `{isLegal: true}`.

### Stage 2: legalityRectifierPipe (events 60-63)

| Events | What |
|---|---|
| 60 | PIPE_START |
| 61 | CONTEXT_PULL |
| 62 | PRE_INVOKE (enter) |
| 63 | PRE_INVOKE (exit) |
| — | **Nothing. No PIPE_SUCCESS, no CONTEXT_PREPARED, no LLM call.** |

This is the "silent skip." The pre-invoke saw `{isLegal: true}`, restored the original user prompt from the context bank, returned `true` to skip the pipe, and the pipe's body never executed. The 2 PRE_INVOKE events are normal enter+exit logging — they are 1ms apart.

**This is what the player saw as "something ran twice."** It was one pre-invocation function, logged twice.

### Stage 3: styleReapplyPipe (events 64-123)

| Events | What |
|---|---|
| 64-66 | PIPE_START + CONTEXT_PULL + CONTEXT_PREPARED (610 input tokens — small because the snapshot was already in the context) |
| 67-81 | `author` pipe run #3 (Qwen Coder 30B, 2819 chars) — third-person conversion |
| 82-91 | API_CALL_SUCCESS + POST_GENERATE |
| 92 | **`BRANCH_PIPE_TRIGGERED` in style reapply pipe** ← the critical event |
| 93-97 | style reapply's validator pipe PIPE_START + PRE_VALIDATION SUCCESS |
| 98-110 | `author` pipe run #4 (Qwen Coder 30B, 2708 chars) — branch pipe's reasoning |
| 111-120 | API_CALL_SUCCESS + POST_GENERATE + VALIDATION SUCCESS + PIPE_SUCCESS |
| 121-123 | TRANSFORMATION + PIPE_SUCCESS |

**The nuke happens at events 121-123.** The transformation function read `result.newOutput` from the LLM's JSON response and used it as the new play text. Because the branch pipe's `newOutput` came from a different model (Palmyra X5) interpreting the same play, the rewritten play was substantively different from the original.

The player's original play was NEVER modified by the legality rectifier (it was legal, so the rectifier was skipped). It WAS modified by the style reapply pipe's branch fallback, because the main pipe's third-person conversion failed its own validator and the branch was invoked.

## Why the Main Style Reapply Failed Validation

The main Qwen Coder 30B output (2819 chars) was rejected by the validator pipe (the nested `style reapply pipe->validator pipe` at events 93-120). The validator's LLM is asked to assess the third-person conversion's fidelity. It returned a failing assessment, triggering the branch.

The exact failure mode is not recorded in the trace (the `validationResult` field is not in this trace's metadata). It could be:
- The conversion introduced content the validator considered out of bounds.
- The validator LLM was overly strict.
- The output format (JSON wrapping) tripped a check.

## Code References

| Behavior | File | Lines |
|---|---|---|
| legalityRectifierPipe skip-on-legal | `server/src/main/kotlin/agent/builders/validateAction/validator.kt` | 600-625 |
| styleReapplyPipe transformation function | same file | 748-762 |
| styleReapplyPipe branch pipe setup | same file | 739-746 |
| gameplayOrchestrator reads validator output | `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt` | 484 |

## How to Reproduce the Diagnosis

```bash
# 1. List the trace files for the affected player
ls /tmp/autogenesis_pm/ | grep -i "<playername>"

# 2. Look for the validator file (has "validator" in the name + timestamp suffix)
# 3. Count pipeId UUIDs to identify distinct pipe runs
python3 -c "
import json
with open('/tmp/autogenesis_pm/<validator_file>.json') as f:
    events = json.load(f)
from collections import Counter
ids = Counter(e['pipeId'] for e in events)
print(f'{len(ids)} distinct pipes:')
for pid, n in ids.most_common():
    names = set(e['pipeName'] for e in events if e['pipeId'] == pid)
    print(f'  {pid[:8]}: {n} events, {names}')
"

# 4. List all TRANSFORMATION events — these are the only places the play text is rewritten
python3 -c "
import json
with open('/tmp/autogenesis_pm/<validator_file>.json') as f:
    events = json.load(f)
for i, e in enumerate(events):
    if e['eventType'] in ('TRANSFORMATION_SUCCESS', 'BRANCH_PIPE_TRIGGERED'):
        print(f'[{i}] {e[\"eventType\"]} in {e[\"pipeName\"]}')
"
```

If you see `BRANCH_PIPE_TRIGGERED` in `style reapply pipe` followed by a `TRANSFORMATION_SUCCESS` in the same pipe, the branch pipe's output is what wrote the final play.

## Takeaway

The legality rectifier is NOT the nuke for legal plays. It correctly skips when `isLegal=true` and never modifies the text. The style reapply pipe IS the nuke for legal plays — it runs unconditionally, and its branch fallback can rewrite the play even when the original was perfectly legal. Future investigations of "my play got changed" complaints on legal actions should focus on the style reapply branch path, not the legality rectifier.
