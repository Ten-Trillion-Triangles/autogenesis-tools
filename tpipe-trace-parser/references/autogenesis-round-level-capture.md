# Autogenesis Round-Level Capture — geoplitics, Overton Window, and once-per-round generations

Session-derived reference for the `tpipe-trace-parser` skill. Use this when the user asks "how many tokens did the geoplitics agent burn", "tally the round-capture cost", or anything about state that is generated **once per round** rather than once per turn.

## The trap: "the geoplitics pipe" doesn't exist by that name

Autogenesis does not emit a pipe called `geoPoliticsAssessmentAgent` or any self-titled functional pipe for round-level captures. The geoplitics assessment, the Overton window, and any other "once per round, then consumed as context by every downstream pipe" content lives inside the per-player `Synthesis Stage (<PlayerName>)` pipes in `AI_Player_Takeover/trace.json`.

Verification recipe: `grep -c "Geopolitical Assessment Summary" /home/cage/.tpipe/debug/trace/Round_3_Turn_<N>_<Player>/AI_Player_Takeover/trace.json` returns 1+ for every per-player synthesis trace that ran in a round-3+ turn. The producing event is the **first** `API_CALL_SUCCESS` on `Synthesis Stage (<PlayerName>)` — not the second one (the second is the cumulative marker with `inputTokens=None` and `totalInputTokens/totalOutputTokens` populated, per the v3.3 skill pitfall on the cumulative vs. per-call bucket).

## Pipe-name anatomy

The capture happens via per-player orchestrator pipes:

- `Synthesis Stage (Robert)` — AI opponent
- `Synthesis Stage (Officer Dave)` — AI opponent variant
- `Synthesis Stage (Bigwang McDouchebag)` — operator-controlled player
- `Planning Stage (<PlayerName>)` — consumes the synthesis output as inputText, produces the player's turn plan
- `Execution Stage (<PlayerName>)` — consumes the plan, produces the final action/narrative

Only ONE of `Synthesis Stage` runs per player per turn. Geoplitics capture for the round happens inside it once. Confirmed via Round 3 Turns 2/4/6 in a real session: one `Synthesis Stage (<Player>)` API_CALL_SUCCESS per turn, all of them producing a "Geopolitical Assessment Summary" output block.

## Identifying the billed event

For geoplitics capture, the billed API call is:

- **Event type:** `API_CALL_SUCCESS`
- **pipeName:** `Synthesis Stage (<PlayerName>)` — first occurrence in the trace (index 26 in Round_3_Turn_6_Bigwang_McDouchebag/AI_Player_Takeover, all 99 events; the second occurrence at index 29 is the cumulative marker)
- **Fields present:** `inputTokens`, `outputTokens`, `totalTokens`, `responseLength`, `modelId`, `apiType`
- **Skip event 29:** it carries `outputTokens` but `inputTokens=None` and `totalInputTokens`/`totalOutputTokens` populated. Per the v3.3 pitfall, that is the cumulative bucket; summing it with event 26 double-counts.

Verified values from Round_3_Turn_6_Bigwang_McDouchebag (2026-07-25):

```
event 26: Synthesis Stage (Bigwang McDouchebag) | API_CALL_SUCCESS
  model: arn:aws:bedrock:us-west-2::foundation-model/qwen.qwen3-coder-30b-a3b-v1:0
  inputTokens:  2,401
  outputTokens: 1,513
  totalTokens:  3,914
  responseLength: 7,348 (chars, NOT tokens — never mix into token totals)
```

## Detection script (copy-paste)

```python
import json
from pathlib import Path

target = Path("/home/cage/.tpipe/debug/trace/Round_<N>_Turn_<M>_<Player>/AI_Player_Takeover/trace.json")
events = json.loads(target.read_text())

# Find the geoplitics producer: Synthesis Stage with the geopolitical content
for i, ev in enumerate(events):
    if ev.get("pipeName") != f"Synthesis Stage (<PlayerName>)":
        continue
    meta = ev.get("metadata") or {}
    if "inputTokens" in meta and meta["inputTokens"] is not None:
        # This is the billed API call
        print(f"event[{i}]: input={meta['inputTokens']} output={meta['outputTokens']} model={meta.get('modelId')}")
        break
```

Replace `<PlayerName>` with the actual player name from the folder (e.g. `Bigwang McDouchebag`, `Robert`, `Officer Dave`). Confirmed working across Round_3_Turn_2_Robert, Round_3_Turn_4_Officer_Dave, Round_3_Turn_6_Bigwang_McDouchebag.

## Consumers (do NOT add to the producer tally)

Once the `Synthesis Stage` produces the geoplitics content, it gets embedded as `inputText` into:

- `Planning Stage (<PlayerName>)`
- `Execution Stage (<PlayerName>)`
- `explicit cot` (PIPE_START and API_CALL_START)
- `Play Detection Agent` (API_CALL_START)

Those events have `Geopolitical Assessment Summary` in their `inputText` field but `inputTokens=None` at the call site (the PIPE_START/API_CALL_START events don't carry billed tokens). The actual billed cost is on the consumer's own API_CALL_SUCCESS, where `inputTokens` is inflated by the embedded synthesis text — but those tokens are the consumer's, not the geoplitics producer's. Do not attribute them to the geoplitics check.

## Where this lands in the "once per round" rule

The user stated the rule: "once per round starting at round 3+ a geopolitical state will be captured". Translation for trace extraction:

- **Rounds 1-2:** no geoplitics synthesis produced (or it produces an empty/no-op event)
- **Rounds 3+:** exactly one billed `Synthesis Stage (<Player>)` API_CALL_SUCCESS per player per turn, output includes a "Geopolitical Assessment Summary" section

To compute the round-level geoplitics cost: sum the `Synthesis Stage` API_CALL_SUCCESS `inputTokens + outputTokens` for each player turn in that round. Across round 3 in the verified session: 3 producer calls (one per player turn).

## Cross-reference

- See `references/autogenesis-game-traces.md` for the broader Autogenesis trace layout and the `AI_Player_Takeover` subdirectory contract.
- See SKILL.md "Token field taxonomy" for the cumulative-vs-per-call bucket distinction (v3.3 pitfall).
