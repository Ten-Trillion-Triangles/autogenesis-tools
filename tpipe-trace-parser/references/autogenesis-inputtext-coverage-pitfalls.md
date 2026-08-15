# Autogenesis InputText Coverage & Story/Game-Data Split

Captured 2026-07-24 from the Autogenesis per-pipe token cost audit
session. The user asked for per-pipe breakdown of input token cost
split between "game data" (world, player, NPC, tile) and "story"
(narrative). The agent wrote three classifier versions, each wrong,
before landing on an honest one. Two structural pitfalls emerged.

## Pitfall: Trace inputText Snapshot Coverage Is Partial

`inputText` on `PIPE_START` / `API_CALL_START` is a PARTIAL snapshot
of the actual prompt the LLM receives. Coverage varies wildly per
pipe. Measured across the 4 Autogenesis turn traces
(`~/.tpipe/autogenesis-trace/Round_1_Turn_*`), per-pipe coverage
(`tok_count(inputText) / inputTokens`) was:

| Pipe                            | Coverage |
| ------------------------------- | -------- |
| structured cot                  | 73%      |
| explicit cot                    | 73%      |
| process focused                 | 72%      |
| author (validator)              | 66%      |
| lorebook extraction pipe        | 51%      |
| reversal-pipe                   | 36%      |
| validator-pipe                  | 24%      |
| ->validator pipe                | 14%      |
| gains and losses pipe           | 1%       |
| stat change pipe                | 0%       |
| resource classification pipe    | 1%       |
| karma pipe                      | 1%       |
| writing pipe                    | 2%       |
| distill guide pipe              | 3%       |
| guide pipe                      | 0%       |
| BedrockMultimodalPipe           | 4%       |
| identify new npc pipe           | 3%       |
| escalation pipe                 | 3%       |
| detect npc history pipe         | 6%       |
| pass or fail pipe               | 6%       |
| update history pipe             | 0%       |
| Planning/Execution Stage pipes  | 2-5%     |
| character identify class pipe   | 1%       |
| Target Detector Pipe            | 1%       |
| legality checker pipe           | 0%       |
| description builder pipe        | 2%       |
| Universal Target Refinement     | 2%       |
| Play Detection Agent            | 3%       |
| Target Disambiguation Pipe      | 3%       |
| existing resource update pipe   | 0%       |
| railroad/style reapply pipes    | 1%       |
| resource detection pipe         | 8%       |

Only 5 pipes (out of 41+) have coverage >= 50%. The other 36 pipes
have an `inputText` snapshot that captures 0-14% of what the LLM
actually receives. Scaling up the partial measurement to match
`inputTokens` produces fabricated numbers — the agent ran this
mistake three times before the user pushed back ("feels very off
compared to how much story gets generated overtime").

**Why low coverage?** Downstream pipes receive LLM-generated
outputs from upstream pipes (analysis JSON, full narratives,
character sheets). The trace framework captures the first ~2K chars
of the wrapping context, but the bulk of the prompt (the upstream
LLM's full output text) isn't echoed back. For example, `stat
change pipe` reports 116K input tokens but the captured inputText is
only ~640 chars — it's a `{isTrue: true, reason: "..."}` object
plus an enormous value the trace framework truncated.

**The rule** for any per-pipe token attribution task:

1. **Compute coverage first** — `snapshot_tok / inputTokens` per pipe.
   A pipe with coverage < 50% is "opaque"; don't classify it.
2. **Report only on the trustworthy subset** — pipes with coverage
   >= 50%. State the subset size as a fraction of total input
   tokens (e.g. "5 pipes cover 41% of total cost; 36 pipes cover
   the remaining 59% but their inputText snapshots are partial and
   cannot be split").
3. **For opaque pipes, report the format hint from the captured
   slice** — first 80 chars of inputText shows whether it's JSON
   narrative, raw prose, multimodal, or format-C prose. This tells
   the user WHAT flows in without fabricating HOW MUCH.
4. **Never scale partial measurements to match `inputTokens`** — the
   captured slice is not a representative sample of the full
   prompt. Even when the slice shows JSON keys, the unsampled
   portion may be entirely prose or entirely different keys.

**Detection recipe**:
```bash
python3 << 'PY'
import json, glob, tiktoken
ENC = tiktoken.get_encoding("cl100k_base")
def tc(t): return len(ENC.encode(t)) if t else 0

ratios = {}
for t in sorted(glob.glob("/path/Round_*_Turn_*")):
    for tp in glob.glob(f"{t}/**/trace.json", recursive=True):
        for e in json.load(open(tp)):
            if e.get("eventType") != "API_CALL_SUCCESS": continue
            p = e.get("pipeName","?")
            tok = (e["metadata"].get("inputTokens")
                   or e["metadata"].get("totalInputTokens") or 0)
            if not tok: continue
            # find the most recent API_CALL_START for this pipe
            last_text = ""
            ratios.setdefault(p, []).append(
                tc(last_text) / max(tok, 1))
# (In a real run, walk events in order to capture each API_CALL_START's inputText.)
PY
```

**Why this matters for cost attribution**: when the user asks "what
fraction of token cost is game data vs story," the answer must be
honest about coverage. A common false-positive pattern is to inflate
the partial-measurement subset by a coverage factor and report it as
the total cost — this can shift "game data 30% / story 50%" to
"game data 80% / story 5%" purely because of which pipes have
full snapshots.

## Pitfall: Story Must Be Split Into New vs Accumulated

The user pushed back when the "story in prompts" number felt too
high compared to how much story gets generated each turn:

> "you need to clearly, very clearly distinguish between old story
> data saved as history here too. Since that number feels very off
> compared to how much story gets generated overtime"

The agent had been tagging all narrative prose as "story" without
distinguishing whether it was the current turn's action narrative
or accumulated history re-fed from previous turns. The contextMap
keys separate these cleanly:

| contextMap key          | What it contains                          | Cost bucket       |
| ----------------------- | ----------------------------------------- | ----------------- |
| `user prompt`           | The CURRENT turn's action narrative       | New story         |
| `userPromptSeed`        | Seed for the current turn's narrative     | New story         |
| `story`                 | Accumulated narrative history (re-fed)    | Old story         |
| `previous turn`         | The previous turn's narrative             | Old story         |
| `world`                 | World state + scenario backstory          | Game data (mostly) |
| `player stats`          | Player stats JSON                         | Game data         |
| `target_data`           | Current turn's target/territory info      | Game data         |
| `action_intent`         | Hostile/Friendly intent tag               | Game data         |
| `current turn`          | Current-turn metadata                     | Game data         |
| `known NPCs`            | NPC list                                  | Game data         |
| `player` / `player_data`| Current player description               | Game data         |
| `character list` / `player list` | Lorebook entity sheets          | Game data         |
| `new chars`             | Newly introduced character lore           | Game data         |
| `valid_territories`     | Territory ownership map                   | Game data         |
| `geopoliticalAssessment` / `overtonWindow` | World state analysis | Game data         |
| `history`               | Turn-by-turn action log (NOT narrative)   | Game data         |
| `delegate_guidance`     | Player delegate instructions              | System            |
| `weights`               | LLM weights config                        | System            |
| `validatorPipeUserPromptSnapshotTPipe` | Cross-pipe snapshot    | System            |
| `player_name_context`   | Active player name                        | Game data         |

Unknown keys (NPC names like "Lord Maple Tree", lorebook entry
titles like "Awakening of Mother Syrup") need content-based
classification: a JSON object with `"description": "..."` and
`"name"`/`"type"` is an NPC character sheet (game data); a prose
fragment with `". [A-Z]"` sentences and no JSON keys is a lorebook
narrative entry (old story).

**The rule** for any per-key attribution:

1. **Identify the keys explicitly** by scanning every prompt in the
   trace folder and listing the top-level keys actually present.
   Don't assume a fixed taxonomy — the keys vary per pipe family.
2. **Walk each key** in the order it appears in the prompt. For
   format-A prompts (`##DEVELOPER PROMPT## / ##USER PROMPT## +
   {"contextMap": {...}}`), extract each top-level key's
   `contextElements[0]` value (a JSON-encoded string).
3. **Bucket by key name** when the name is meaningful (`story`,
   `previous turn`, `user prompt`). For unknown keys, fall back to
   content-shape classification.
4. **Separate new vs accumulated**: the user prompt / userPromptSeed
   is THIS turn's content; story / previous turn / lorebook entry
   titles are accumulated. These grow at different rates and have
   different cost-reduction strategies (truncation vs summarization).

## Worked example: full prompt structure

A format-A prompt (validator / judge pipes) looks like:
```
##DEVELOPER PROMPT##
MODUS OPERANDI: ...
##FUNDAMENTAL PRINCIPLE##
...
##USER PROMPT##
Turn Outcome: FAILURE

{The full narrative text of the player's action this turn}

{
    "contextMap": {
        "world": { "loreBookKeys": {}, "contextElements": [
            "{ \"name\": \"Io\", \"storyScenario\": \"In orbit around...\" }"
        ]},
        "story": { "loreBookKeys": {}, "contextElements": [
            "<accumulated narrative history>"  // 60K-120K chars, grows per turn
        ]},
        "user prompt": { "loreBookKeys": {}, "contextElements": [
            "<this turn's action narrative>"  // ~5K chars
        ]},
        "target_data": { ... },
        "action_intent": { ... },
        "player stats": { ... }
    }
}
```

**Cost growth pattern across 4 turns** (from the trustworthy
4-pipe subset):
- Old story (`story` key): 145K → 159K → 283K → 354K BPE tokens
- New story (`user prompt` key): ~13K-66K BPE tokens per turn
- Game data (`world`, `player stats`, `target_data`): ~250K-590K
  BPE tokens per turn, roughly stable

## Pairs with

- "Trace inputText Snapshot Coverage Is Partial" — apply the
  contextMap-key split ONLY to the trustworthy (>=50% coverage)
  pipe subset. Otherwise you're classifying a partial snapshot
  that doesn't represent the full prompt.
- The "When to Trace-Verify a Live Agent" section in SKILL.md —
  this reference adds the cost-attribution specialization.

## Correction (2026-07-24 v1.9): `metadata.fullPrompt` Captures the Full Prompt

The previous version of this reference treated `inputText` as the
only available prompt snapshot and concluded that 36/41+ pipes
could not be classified because `inputText` covered 0-14% of their
inputTokens. **That conclusion was wrong.** The trace framework
records the full prompt in a different field. The agent missed
it across three rounds and kept writing fabricated or zero
numbers; the user called this out directly ("you wrote shitty
python code to read the traces, plain and simple").

**The field is `metadata.fullPrompt` on `PIPE_START` events.**

Measured coverage when using `fullPrompt` instead of `inputText`
on the same 4 Autogenesis turn traces:

| Pipe                       | inputText cov | fullPrompt cov |
| -------------------------- | ------------- | -------------- |
| structured cot              | 73%          | full           |
| explicit cot                | 73%          | full           |
| author (validator)          | 66%          | full           |
| process focused             | 72%          | full           |
| gains and losses pipe       | 1%           | **full (119K-358K chars)** |
| stat change pipe            | 0%           | full           |
| resource classification     | 1%           | full           |
| karma pipe                  | 1%           | full           |
| writing pipe                | 2%           | full           |
| distill guide pipe          | 3%           | full           |
| guide pipe                  | 0%           | full           |
| identify new npc pipe       | 3%           | full           |
| BedrockMultimodalPipe       | 4%           | full           |
| escalation pipe             | 3%           | full           |
| detect npc history pipe     | 6%           | full           |
| pass or fail pipe           | 6%           | full           |
| update history pipe         | 0%           | full           |
| legality checker pipe       | 0%           | full           |
| description builder pipe    | 2%           | full           |
| Planning/Execution Stage    | 2-5%         | full           |
| character identify class    | 1%           | full           |
| Target Detector Pipe        | 1%           | full           |

`fullPrompt` is captured on the **second `PIPE_START` event** for
each pipe (the first one typically has only `inputText`; the second
one, after the pipeline has assembled the full context, has
`fullPrompt`). Some pipes have only one `PIPE_START` — for those,
the single event's `inputText` IS the full prompt (e.g. the COT
pipes).

**The corrected per-pipe-per-turn game-data attribution** (using
`fullPrompt`, world/player/NPC/tile contextMap keys + NPC character
sheets):

```
Pipe                       R1T0   R1T1   R1T2   R1T3   TOTAL
structured cot           151,693 247,503 266,356 314,601  980,153
explicit cot              80,220 123,119 146,244 124,259  473,842
author                    13,060 182,068  12,846 222,094  430,068
process focused           71,107  81,389  87,560  93,390  333,446
gains and losses pipe     38,560  42,077  43,405  46,053  170,095
stat change pipe          34,463  37,870  39,892  41,918  154,143
resource classification   31,835  35,293  37,377  39,466  143,971
karma pipe                30,253  33,850  36,056  38,044  138,203
identify new npc pipe      5,476   9,860  12,561  13,801   41,698
escalation pipe            1,369   6,185   7,737   8,328   23,619
detect npc history pipe      996   4,845   6,608   7,006   19,455
update history pipe        1,137   5,107   6,869       -   13,113
legality checker pipe     11,488       -       -       -   11,488
PER-TURN GAME-DATA TOTAL 414,649 816,915 716,112 965,117 2,912,793
```

**The rule for any per-pipe token attribution**:

1. **Walk every `PIPE_START` event for the pipe** in document order.
   Capture the first one that has `metadata.fullPrompt`. If none,
   fall back to `metadata.inputText` and report coverage.
2. **Use `CONTEXT_PREPARED` events as a fallback** — they have
   `metadata.actualInputTokens` (the real reported number) and
   sometimes `metadata.inputText`. Pair them with `API_CALL_SUCCESS`
   for the same pipe.
3. **Do NOT use `API_CALL_START.inputText` as the primary source**
   for pipes that have `fullPrompt` on `PIPE_START`. The API_CALL
   start's inputText is the **user-prompt portion only** — system
   prompt and contextMap are stripped, which is why coverage was
   0-14% for the format-B pipes.
4. **The pairing rule for API_CALL_SUCCESS → prompt**: walk events
   in document order. The most recent `PIPE_START` (with fullPrompt)
   or `CONTEXT_PREPARED` (with inputText + actualInputTokens)
   before the `API_CALL_SUCCESS` is its prompt source.
5. **The classifier from the previous sections still applies** —
   contextMap key whitelist, NPC character-sheet detection, format
   B JSON key whitelist. The data was there; the agent just wasn't
   reading the right field.

**Detection recipe** (start of any per-pipe attribution task):
```bash
python3 << 'PY'
import json, glob
# For each pipe, find the maximum fullPrompt size across all PIPE_START events
for tp in sorted(glob.glob("/path/**/trace.json", recursive=True)):
    for e in json.load(open(tp)):
        if e.get("eventType") != "PIPE_START": continue
        fp = e.get("metadata", {}).get("fullPrompt", "")
        if fp and len(fp) > 100:
            print(f"{e['pipeName']:<40} fullPrompt={len(fp):>7}")
            break  # one per pipe per trace
PY
```

If `fullPrompt` is populated for a pipe, USE IT. If only `inputText`
is available (older traces, certain pipe types), apply the
coverage-based honesty rule from the previous pitfall.

**Why this matters**: the previous version of this reference
recommended scaling partial measurements and reporting only the
trustworthy subset. That was honest given the data the agent had,
but the data was incomplete — the framework DOES capture the full
prompt, just in a different field. The corrected answer
(~2.91M game-data tokens across 4 turns, distributed across 12+
pipes instead of 4) is materially different and actionable for
cost reduction work.

**User-correction quote** (2026-07-24): "you are giving an unclear
answer, despite the fact that the tracing system clearly has the
data you claim it does not. You wrote shitty python code to read
the traces, plain and simple."

## Correction (2026-07-24 v2.0): Two More Prompt Formats, Opaque Heuristic, "Longest Capture" Rule

The v1.9 classifier left 8 pipes in R1T0 un-attributed
(`character identify class pipe`, `description builder pipe`,
`Play Detection Agent`, `Target Disambiguation Pipe`,
`reversal-pipe`, `physics changes and map tiles removed pipe`,
`lorebook extraction pipe`, `railroad detection pipe`,
`style reapply pipe`, `resource detection pipe`). v2.0 closes
those by recognizing three additional prompt formats and a
content-shape heuristic for genuinely-partial captures.

### New rule: take the LONGEST `fullPrompt` per pipe, not the first

The v1.9 rule was "capture the first `PIPE_START` with
`fullPrompt`." On R1T0, several pipes emit multiple `PIPE_START`
events — the first has `fullPrompt=""` (placeholder) and the second
has the real prompt of 9-13K chars. Capturing the first yields 0
tokens; capturing the longest yields the real prompt. Always walk
every `PIPE_START` for the pipe in document order and keep the
longest non-empty capture.

### New format: Format D — `{}` + stringified-JSON contextElements

`existing resource update pipe` uses this pattern. The prompt opens
with `{}` followed by a JSON object whose `contextElements` array
contains a STRINGIFIED JSON object with keys like `turnPlayer`,
`turnAction`, `turnStory`, `wasPlayerSuccessful`, `turnResult`,
`territoryGained`, `resourcesWon`, `statBuffsGained`,
`territoryExchanges`, `affectedPlayers`, `targetIntent`,
`targetEntities`, `id`. Bucket these inner keys explicitly:

- `turnStory`, `story`, `narrative`, `previous turn`, `user prompt` → story
- `turnPlayer`, `turnAction`, `turnOutcome`, `player`, `world`, `history` → game data
- Everything else → unknown

### New format: multi-JSON Format C — JSON object followed by another JSON

`character identify class pipe` and `description builder pipe` use
this pattern. The prompt is `{"characters": [...]}` followed by
`{}` followed by another JSON object with `contextElements`
containing a stringified inner JSON. The v1.9 format-C parser
captured ONLY the first balanced JSON object and missed the rest
of the prompt. v2.0 walks ALL balanced JSON objects in the prompt
and aggregates bucket shares across all of them. For prompts with
mixed structure (`characters` array + `contextElements` wrapper),
both objects contribute to the totals.

### New rule: opaque-pipe content-shape heuristic (closes the residual gap)

For pipes where the trace framework captured only a partial
prompt (max `fullPrompt` length < 500 chars OR coverage
`inputPrompt_tokens / actualInputTokens` < 10%), apply a
content-shape heuristic on the captured slice instead of reporting
"opaque":

- **Pure prose (capture does not start with `{` or `##`)**: the
  captured slice is the player's action text or a narrative
  paragraph. Bucket as 100% story. (Affected: `reversal-pipe`,
  `lorebook extraction pipe`, `Play Detection Agent`,
  `railroad detection pipe`, `style reapply pipe`,
  `resource detection pipe`, `physics changes and map tiles removed pipe`.)
- **`PLAYER ACTION:` / `PLAYER INVENTORY:` schema**: the captured
  slice is the player action with empty inventory. Bucket as 100%
  story. (Affected: `resource detection pipe`.)
- **JSON starting with `candidates` or other format-C game-data key**:
  the partial capture IS the game's classification output schema.
  Re-run format-C parsing on the partial; bucket by key.
  (Affected: `Target Disambiguation Pipe` — partial captured
  `candidates` + `user prompt`; both bucket correctly.)

The rule: **never leave a pipe at 0 attribution if its captured
slice has any content-shape signal**. A partial slice still tells
you WHAT flows in, and "what" is enough to put it in the right
bucket even when "how much" is unknown.

### Verified v2.0 R1T0 output (Lord Maple Tree, 620,970 input tokens)

```
PIPE                              Calls  InputTok  GameData  Story
structured cot                      10    112,128   107,520   4,598
explicit cot                         9     86,861    83,293   3,559
gains and losses pipe                1     53,710    51,505   2,204
author                               8     47,111    47,111       0
stat change pipe                     1     46,941    45,014   1,926
process focused                      1     45,437    43,571   1,865
resource classification pipe         1     43,864    42,063   1,800
karma pipe                           1     42,019    40,294   1,724
legality checker pipe                1     16,709    16,709       0
guide pipe                           2     14,132    14,056       0
identify new npc pipe                1     12,784     8,640   4,143
writing pipe                         2     12,462    11,854     606
escalation pipe                      1     10,352         4  10,347
pass or fail pipe                    1      8,185     2,925   5,259
distill guide pipe                   2      8,140     8,140       0
detect npc history pipe              1      7,781         3   7,777
update history pipe                  1      7,233         3   7,229
character identify class pipe        1      6,033     1,778   4,224
existing resource update pipe        1      5,204        93   3,775
Target Detector Pipe                 1      5,177     5,177       0
description builder pipe             1      4,685     1,471   3,190
BedrockMultimodalPipe                1      4,312     4,312       0
Universal Target Refinement Pipe     1      3,178     3,178       0
Play Detection Agent                 1      2,960         0   2,960
Target Disambiguation Pipe           1      2,752     1,146   1,605
reversal-pipe                        1      2,558         0   2,558
physics changes/map tiles pipe       1      2,250         0   2,250
lorebook extraction pipe             1      2,239         0   2,239
railroad detection pipe              1      1,635         0   1,635
style reapply pipe                   1      1,208         0   1,208
resource detection pipe              1        930         0     930
TOTAL                                58    620,970   539,860  76,371
                                                       (86.9%) (12.3%)
                                          + 4,699 unknown (0.8%)
                                          = 99.2% accounted
```

**R1T0 conclusion**: ~87% of first-turn input cost is game data
(world, player, NPC character sheets, target/territory, mechanical
state). ~12% is story (the narrative prose flowing through pipes
like escalation, pass-or-fail, npc history, character
classification). Top-5 game-data pipes: structured cot, explicit
cot, gains/losses, stat change, process focused. Top-5 story pipes:
escalation, pass-or-fail, detect-npc-history, update-history,
character-identify-class.

### Re-runnable classifier

`scripts/autogenesis_attribution.py` (added in this revision)
bakes in the v2.0 classifier. Usage:

```bash
python3 scripts/autogenesis_attribution.py \
    --dir /home/cage/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/
```

Requires `tiktoken` (install with `python3 -m venv /tmp/venv &&
/tmp/venv/bin/pip install tiktoken` if not on PATH). Outputs
per-pipe game-data / story / unknown split to stdout, plus a JSON
report at `/tmp/r1t0-attribution.json`. The classifier is
parameterized by `STORY_KEYS`, `GAME_DATA_KEYS_A`, and
`GAME_DATA_KEYS_C` dicts at the top of the file — extend these
when a new pipe family introduces a new key.

### Pairs with

- v1.8 `inputText` partial-coverage rules — those still apply
  for older traces that lack `fullPrompt`.
- v1.9 `fullPrompt` field-discovery rule — that's the load-bearing
  improvement; v2.0 just refines the classifier that consumes it.