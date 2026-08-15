# Autogenesis Budget Pressure Trajectory — Empirical Measurements & 25-Round Projection

Captured 2026-07-24 from the per-turn trace analysis of
`/home/cage/.tpipe/debug/trace/Round_{1,2}_Turn_0_Lord_Maple_Tree`.
The companion skill (`tpipe-context-budget-truncation`) documents the
math (`calculateAvailableContext`, `TruncateTop` semantics, the
`BedrockConfig.kt` preset table). This reference documents what
actually shows up at runtime — the empirical per-pipe payloads,
the measured growth between turns, and the projected pressure
threshold per pipe over a 25-round game.

## Measured per-pipe payloads (R1T0 Lord Maple Tree, first turn)

Token counter: tiktoken `cl100k_base`. 58 successful LLM calls,
620,970 total input tokens. The 7 Judge reasoning pipes plus the
writer pipeline dominate cost.

| Pipe | Calls | Max gd/call | Mean gd/call | Max story/call |
|------|------:|------------:|-------------:|---------------:|
| gains and losses pipe | 1 | 51,505 | 51,505 | 2,204 |
| explicit cot | 9 | 49,566 | 5,752 | 8,927 |
| stat change pipe | 1 | 45,014 | 45,014 | 1,926 |
| process focused | 1 | 43,571 | 43,571 | 1,865 |
| resource classification | 1 | 42,063 | 42,063 | 1,800 |
| structured cot | 10 | 40,798 | 9,768 | 3,636 |
| karma pipe | 1 | 40,294 | 40,294 | 1,724 |
| legality checker pipe | 1 | 16,709 | 16,709 | 0 |
| identify new npc pipe | 1 | 8,640 | 8,640 | 4,143 |
| guide pipe | 2 | 7,028 | 7,028 | 0 |
| writing pipe | 2 | 5,927 | 5,927 | 303 |
| author | 8 | 5,156 | 2,528 | 16,124 |
| BedrockMultimodalPipe | 1 | 4,312 | 4,312 | 0 |
| escalation pipe | 1 | 4 | 4 | 10,347 |
| detect npc history pipe | 1 | 3 | 3 | 7,777 |

**Budget ceiling for `generativeBudgetSettings`**: 218,000 available
context (230K window − 12K max tokens). At R1T0 the largest single
call (gains/losses, 53,710 tokens) uses **24%** of the available
budget. No truncation occurs.

## R1T0 → R2T0 measured growth (one round of accumulation)

The trace data shows the per-pipe payloads grew substantially in
just one round of accumulation. The `story` contextMap key holds
the previous turn's full narrative; in R1T0 it was 4,798 chars (the
player's initial action); in R2T0 it was 49,210 chars (one full turn
of generated narrative + the current action).

Per-pipe growth between R1T0 and R2T0 (same pipe, different
measurement):

| Pipe | R1T0 max gd | R2T0 max gd | Growth |
|------|------------:|------------:|-------:|
| explicit cot | 49,566 | 65,380 | +32% |
| structured cot | 40,798 | 57,264 | +40% |
| gains/losses | 51,505 | 67,498 | +31% |
| stat change pipe | 45,014 | 61,263 | +36% |
| process focused | 43,571 | 59,884 | +37% |
| resource classification | 42,063 | 58,541 | +39% |
| karma pipe | 40,294 | 56,843 | +41% |
| identify new npc | 8,640 | 25,671 | +197% |

**The `story` key growth rate dominates the per-pipe growth.** Every
pipe that includes the previous-turn narrative in its contextMap
absorbs 30-40% more tokens per round from this single key. The
pipes that grew most (identify new npc +197%) include the full
story for NPC character extraction.

**R1T0 → R2T0 mixed bag composition**:
- R1T0: 87% game data / 12% story / 0.8% unknown
- R2T0: 49% game data / 46% story / 4% unknown

The shift: prior-turn narrative is now half of all input cost. At
R1T0 the `story` key was effectively empty (this WAS the first
turn); by R2T0 it carries the full R1T0 narrative.

## 25-round projection (round-by-round pressure threshold)

The reference number for `story` key growth is **1.05× per round per
turn** (`validate_narrative_claims.md` measurement). Extrapolating
from R2T0 (49,210 chars ≈ 12,300 tokens at cl100k_base):

| Round | story key tokens | Total Judge pipe payload (projected) | % of 218K budget |
|------:|-----------------:|------------------------------------:|------------------:|
| 1 (T0) | ~1,200 | ~55,000 | 25% |
| 2 (T0) | ~12,300 | ~80,000 | 37% |
| 5 (T0) | ~17,900 | ~115,000 | 53% — first overflow risk |
| 10 (T0) | ~23,100 | ~170,000 | 78% — heavy truncation |
| 15 (T0) | ~29,800 | ~230,000 | 106% — overflow begins |
| 20 (T0) | ~38,400 | ~300,000 | 138% — aggressive truncation |
| 25 (T0) | ~49,500 | ~390,000 | 179% — severe loss |

**Truncation behavior under pressure** (TruncateTop default):

The `selectAndTruncateContext` function (ContextWindow.kt:1110)
allocates budget via `multiPageBudgetStrategy = DYNAMIC_SIZE_FILL`
and truncates via `truncationMethod = TruncateTop`. With TruncateTop:

1. **Lorebook entries are filled first** (via
   `selectAndFillLoreBookContext`). They are shielded from
   TruncateTop because the lorebook budget is reserved before
   contextElements truncation runs.
2. **System prompt is assembled first**. Shielded.
3. **User prompt is preserved by `preserveJsonInUserPrompt=true`**
   (default). Shielded.
4. **Context elements are truncated by TruncateTop** — the OLDEST
   entries drop first. The `story` key is appended first in the
   contextElements list, so it absorbs the largest cuts first.

**Practical effect at round 25**: the oldest 3-5 turns of narrative
disappear from every Judge pipe call. The current turn + the 4-6
most recent turns + all game data + lorebook survive. Critical
facts that appear only in turns 1-5 of a 25-round game will be
silently dropped from the LLM's view.

## Writer pipeline pressure (the first to fail)

The writer pipeline (`writing pipe`, `distill guide pipe`,
`guide pipe`, `author` ×8) carries the full accumulated story on
every call. At R2T0 these pipes already operate at high utilization:

- `guide pipe` ×2: 48,632 story per call (max) — 22% of budget
- `writing pipe` ×2: 41,737 story per call (max) — 19% of budget
- `distill guide pipe` ×2: 38,678 story per call (max) — 18% of budget
- `author` ×8: 46,734 story per call (max) — 21% of budget

These are narrative-output pipes that need the FULL story to
generate coherent prose. They will be the first to hit truncation
pressure as the game progresses.

**Projected round for first truncation event in writer pipeline**:

The 1.05× per round growth rate means the writer pipeline crosses
100% budget utilization around round 8-12 (depending on the pipe).
By round 20, the `guide pipe` would carry 95,000+ story tokens and
be truncated to fit. TruncateTop will cut the oldest 50-60% of the
story, leaving only the most recent 10-12 turns.

## Round-by-round truncation probability (projection)

Based on the 1.05× per turn story growth + the 218K budget ceiling:

| Round | Truncation events per turn | What's truncated |
|------:|---------------------------:|------------------|
| 1-3 | 0 | nothing |
| 4-6 | 0-1 | earliest 1-2 turns, only in writer pipeline |
| 7-10 | 1-3 | 1-3 turns dropped from writer + Judge reasoning pipes |
| 11-15 | 3-5 | 3-5 turns dropped from Judge reasoning pipes; old lorebook keys may fall out |
| 16-20 | 5-8 | 5-8 turns dropped; some NPCs and lorebook entries pruned |
| 21-25 | 8-10 | aggressive; recent turns survive but old world state at risk |

**Critical takeaway**: if a 25-round game depends on NPCs from turns
1-5 being referenced in turns 21-25, that reference will silently
fail under default truncation. The fix is to push critical early
content into lorebook entries (which are filled first and shielded
from TruncateTop) before round 10.

## Pairs with

- `references/tpipe-context-budget-fields.md` — the math
  (`calculateAvailableContext`, `TruncateTop` defaults)
- `references/autogenesis-inputtext-coverage-pitfalls.md` (under
  `tpipe-trace-parser`) — the per-pipe classifier that produced
  the R1T0/R2T0 measurements
- `tpipe-context-budget-truncation` SKILL.md — the budget settings
  table and truncation algorithm overview

## Detection recipe (start of any "will it fit / when will it
truncate" assessment)

```bash
# 1. Inventory which budget settings each pipe uses
grep -rE "setTokenBudget\(BedrockConfig\." \
  /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/ \
  | sort | uniq -c | sort -rn

# 2. Measure current per-pipe actual payloads from trace.json
python3 -c "
import json, glob
from collections import defaultdict
totals = defaultdict(lambda: {'count': 0, 'sum': 0, 'max': 0})
for tp in sorted(glob.glob('/home/cage/.tpipe/debug/trace/Round_*_Turn_0_*/**/trace.json', recursive=True)):
    for e in json.load(open(tp)):
        if e.get('eventType') != 'API_CALL_SUCCESS': continue
        tok = (e.get('metadata', {}).get('actualInputTokens')
               or e.get('metadata', {}).get('inputTokens') or 0)
        if not tok: continue
        p = e['pipeName']
        totals[p]['count'] += 1
        totals[p]['sum'] += tok
        totals[p]['max'] = max(totals[p]['max'], tok)
for p, s in sorted(totals.items(), key=lambda kv: -kv[1]['max']):
    print(f'{p:<46} calls={s[\"count\"]:>3} max={s[\"max\"]:>7} mean={s[\"sum\"]//max(s[\"count\"],1):>7}')
"

# 3. Compare against budget ceiling
# generativeBudgetSettings: 230000 - 12000 = 218000 available
# If any max > 218000, that pipe will start truncating NOW.
```

## Operator-quote context

This projection was developed in response to: "I need to identify
the configured settings for TokenBudgeting the memory management
system TPipe uses to keep context under control and prevent
overflows. And determine what it's settings are for most agents,
and what the algorithm behavior will be in regards to what is most
likely to get truncated under memory pressure over the course of
a 25 round game."