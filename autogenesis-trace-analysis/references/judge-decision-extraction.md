# Judge Decision Extraction — Why I Won/Lost That Territory

Use when the player asks "why did I win/lose territory X" or "the verdict doesn't match what I did" and the `Judge/trace.json` for that turn exists. The judge is a **narrative extractor**, not a battlefield adjudicator — once the writing agents decide a territory was "secured," the judge mechanically stamps it. This reference shows how to mine the 9-pipe Judge trace to reconstruct the verdict logic.

## The 9-pipe Judge chain (verified, 2026-08-08)

Every complete Judge trace contains the same 9 pipes. They fan out in parallel and each emits one `API_CALL_SUCCESS` (some twice). The order is determined by `BRANCH_PIPE_TRIGGERED` and `VALIDATION` events.

| # | Pipe | What it produces | Where the verdict lives |
|---|---|---|---|
| 1 | `explicit cot` | Free-form reasoning chain (the judge's "why") | `events[i].content.text` — look for `coreAnalysis.sequentialReasoning.steps[].conclusion` |
| 2 | `structured cot` | Mechanical reasoning, often repeats the same conclusion | Same shape as explicit cot |
| 3 | `gains and losses pipe` | The **decisive territory/resource JSON** | `territoryGained`, `territoryLost`, `assetsGained`, `assetsLost`, `territoryExchanges`, `assetExchanges` |
| 4 | `karma pipe` | Whether the action counts as "antagonizing the world" | `{isTrue: bool, reason: str}` |
| 5 | `resource classification pipe` | Tangible/abstract/NPC classification of resources | Per-resource `isTangible/isAbstract` flags |
| 6 | `stat change pipe` | Final stat deltas + **territoryStatChanges** | Look here for the why behind each territory's threat deltas |
| 7 | `process focused` | Process verification | Boilerplate |
| 8 | `mantle structured cot (gemma4ModelId)` | Mantle-backed reasoning pass | Same shape as explicit cot |
| 9 | `mantle validator pipe` | Schema validation of the mantle output | Schema pass/fail |

**The decisive pipes for "why did I win/lose X" are #3 + #6.** Pipe #3 declares the territory list; pipe #6 explains the per-territory deltas.

## The judge's verdict logic (the trap)

The judge does **not** adjudicate whether the action was a real-world military victory. It adjudicates **whether the narrative prose says it was**. The chain is:

1. **Writing agents** produce a turn narrative (the prose the player sees).
2. **Play Detection Agent** classifies the play as Military/Research/Diplomatic.
3. **Judge pipes** extract the verdict from the narrative:
   - Explicit cot pipe walks the logic: "enemy forces defeated, territory controlled... **meets automatic capture criteria**"
   - Gains/losses pipe emits `{territoryGained: [...]}`
   - Stat change pipe emits `{territoryStatChanges: [...]}` with reasoning strings

The decision rule is mechanistic: **if the prose names a target territory AND describes a military effect on it, the territory gets awarded.** The judge never re-derives whether the "military effect" was actually a victory — it took the writing agents' word for it.

**This is why you can win a turn where your tanks got stuck in cement.** The Writing Agents wrote "victory" into the prose (often padded by `General Flipper declared victory` or `Ethiopian forces recognized strategic value and secured the area`), and the judge stamped `territoryGained: [Sudan, Ethiopia]` because both names were in the narrative.

## Recipe: extract the verdict rationale

```python
import json
from pathlib import Path

trace_path = Path("~/.tpipe/debug/trace/Round_<N>_Turn_<M>_<Player>/Judge/trace.json").expanduser()
events = json.loads(trace_path.read_text())

# 1. Identify the gains/losses JSON (the territory verdict)
for i, e in enumerate(events):
    if e.get('eventType') == 'API_CALL_SUCCESS' and e.get('pipeName') == 'gains and losses pipe':
        text = (e.get('content') or {}).get('text', '')
        if 'territoryGained' in text or 'territoryLost' in text:
            print(f'=== Event {i} | gains and losses pipe ===')
            # Strip code fences if present
            clean = text.strip('`').strip()
            if clean.startswith('json'):
                clean = clean[4:].strip()
            verdict = json.loads(clean)
            print(json.dumps(verdict, indent=2))
            break

# 2. Identify the per-territory stat changes (the judge reasoning)
for i, e in enumerate(events):
    if e.get('eventType') == 'API_CALL_SUCCESS' and e.get('pipeName') == 'stat change pipe':
        text = (e.get('content') or {}).get('text', '')
        if 'territoryStatChanges' in text:
            print(f'=== Event {i} | stat change pipe ===')
            clean = text.strip('`').strip()
            if clean.startswith('json'):
                clean = clean[4:].strip()
            stats = json.loads(clean)
            for tc in stats.get('territoryStatChanges', []):
                print(f"  {tc['territoryName']}: "
                      f"military={tc.get('militaryThreatStat', 0):+d} "
                      f"diplomacy={tc.get('diplomacyThreatStat', 0):+d}")
                print(f"    reasoning: {tc.get('reasoning', '')}")
            break

# 3. Pull the explicit-cot reasoning (the judge's "why")
for i, e in enumerate(events):
    if e.get('eventType') == 'API_CALL_SUCCESS' and e.get('pipeName') == 'explicit cot':
        text = (e.get('content') or {}).get('text', '')
        if len(text) > 200:
            print(f'=== Event {i} | explicit cot ===')
            print(text[:3000])
            break
```

## Worked example: Round 1 Turn 0 Lord Maple Tree (2026-08-08)

Player declared: "fund research of dessert tanks, use full Ent army led by Moustache + Flipper, **invade and conquer @Sudan and @Ethiopia**"

Narrative produced (key excerpts):
- "Modified maple syrup lubricant reacted with heat to form a durable cement, **trapping the Ent army's tanks**"
- "**General Flipper declared victory**"
- "**Ethiopian forces recognized the tactical value and secured the area**"

Judge's gains/losses pipe emitted:
```json
{
  "territoryGained": ["Sudan", "Ethiopia"],
  "assetsGained": ["Saccharine Vanguard Technology"],
  "assetsLost": [],
  "territoryLost": [],
  "territoryExchanges": []
}
```

Judge's explicit cot reasoning:
> "Research play with hostile intent must award primary subject as resource per rules" → Saccharine Vanguard belongs to LMT
> "Enemy forces defeated, territory controlled. Narrative shows enemy tanks immobilized, Ethiopian forces recognize value, General Flipper declares victory. **Enemy forces defeated and territory controlled - meets automatic capture criteria**"
> "Sudan and Ethiopia mentioned as targets, narrative shows tank immobilization in Sudan, Ethiopian coordination"

Judge's stat change pipe (territory deltas):
```
Sudan:        militaryThreat -20  ← "assets immobilized by solidified syrup tanks"
Ethiopia:     diplomacyThreat +15 ← "Ethiopian forces recognized strategic value..."
South Sudan:  militaryThreat +25  ← (NOT awarded — wasn't in declared targets)
```

**The verdict landed because the writing agents' prose named both targets AND described a military effect.** The judge called it a victory because the prose called it a victory. The biological fact that my tanks got stuck in cement is irrelevant to the territory tally.

## How to explain the verdict to the player

When the player asks "why did I win/lose territory X despite the in-fiction mess," explain in three layers:

1. **What the judge actually reads:** the narrative prose, not the battlefield outcome. The judge pipes (gains/losses, stat change, explicit cot) extract from the writing agents' text.
2. **The mechanical rule:** if the narrative names a target AND describes a military effect, the territory gets awarded. The "effect" can be positive (conquest) or even neutral (immobilization, adoption) — the rule fires on presence, not gradient.
3. **The prose control lever:** victory is a narrative event. Players who want to win should write plays that produce clear, named "victory" lines in the writing-agent output. Players who want to disown a territory should write plays that make the target's defense explicit.

## Common confusion patterns

- **"I lost X but my action only targeted Y"** — The judge awards territories named in the narrative, not just the declared targets. If the writing agents mentioned any territory in passing, it can land in `territoryStatChanges` even if you didn't intend to attack it.
- **"My tanks got defeated, how did I win?"** — The judge never sees the in-fiction defeat. It sees "territory named + military effect described." Immobilization, sabotage, or even diplomatic adoption all count as "military effect" once the prose calls them such.
- **"The stat deltas don't match the territory list"** — Check `territoryStatChanges` separately from `territoryGained`. A territory can be in one but not the other if the writing agents only described territory-wide effects (not "captured by LMT" specifically).
- **"NPC capture vs. player capture"** — Player capture appears in `territoryGained`/`territoryExchanges[from: NPC, to: Player]`. NPC capture (NPC stole from player) appears in `territoryExchanges[from: Player, to: NPC]`. The gains/losses pipe handles both.

## Verification

After extracting a verdict, sanity-check it against the prose:

```python
# Pull the writing agent output for the same turn
narrative_path = trace_path.parent.parent / "TurnResolutionSplitter" / "narrative" / "trace.json"
# Or for the captured action:
writing_path = trace_path.parent.parent / "WritingAgents" / "trace.json"
```

If the judge awarded territories that aren't present in the prose at all, that's a bug — flag it. If the prose mentions the territory with a military-effect sentence, the judge did its job.

## Cross-reference

- **Pipe timing + token burn:** `references/gameplay-progression-and-swing-magnitude.md` — the 8-pipe Judge chain (now 9 with the explicit cot) and per-turn token costs.
- **What the validator pipeline does before the judge:** `references/validator-pipeline-nuke.md` — the legality checker + style reapply that shapes the play text the judge sees.
- **Game snapshot history (the canonical record):** `references/gameplay-progression-and-swing-magnitude.md` — `game_snapshot.json → history[]` is the ground truth for what was awarded.
