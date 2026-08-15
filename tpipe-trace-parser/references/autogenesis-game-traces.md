# Autogenesis Game Trace Layout

Session-derived reference for the `tpipe-trace-parser` skill. Use this when the user asks for a per-turn game post-mortem (e.g. "what happened in the game", "post-mortem of the last match", "give me a recap of each turn").

## Turn folder inventory pattern

Autogenesis sessions write one folder per turn under `~/.tpipe/autogenesis-trace/` (NOT `~/.tpipe/debug/trace/` — that root holds PumpStation + TPipe harness test traces, not game turns):

```
Round_{N}_Turn_{M}_{PlayerName}/
```

- `N` is the round number (starts at 1)
- `M` is the turn index within that round (0-based)

**Always inventory both roots** when asked for Autogenesis traces — `~/.tpipe/autogenesis-trace/` for game turns, `~/.tpipe/debug/trace/` for harness/test traces. Confusing them produces empty reports.
- `PlayerName` is one of:
  - `Lord_Maple_Tree` / `Dr._Ebenezer_Syrupwell` / `Syrup_Shield` — the human player or player-controlled NPCs
  - `Robert` — the AI player (opponent)
  - Sometimes other AI / NPC opponents

Not every turn is a player turn. A typical game has 3-4 turns per round (mix of player + NPC + AI). Always inventory first.

## Subagent directory → what it contains

| Directory | Purpose | Size hint | How to extract |
|---|---|---|---|
| `ValidationSplitter/{ts}/validator/` | Player's action + isLegal verdict | 10-700KB | `legality checker pipe` PIPE_START text + `API_CALL_SUCCESS` JSON |
| `ValidationSplitter/{ts}/railroad/` | Sub-router log | small | usually ignore |
| `Judge/` | Player turn stat changes | 4-25MB | last `reasoningConclusion` in API_CALL_SUCCESS.reasoningContent |
| `NeoWritingAgent/` | Player turn narrative | 1-30MB | TRANSFORMATION_SUCCESS text on the largest pipe |
| `MaintenanceSplitter/{ts}/updates/` | Committed world-state changes (map tiles, tech) | small | outputText from `physics changes and map tiles removed pipe` |
| `TargetDetectors/` | Which territories the action targets | small | mostly metadata |
| `HardenAgent/` | Only on retry/escalation | small | only present if validator failed |
| `ReversalAgent/` | Only on action rejection | small | only present if action was rejected |
| `LorebookUpdate/` | World knowledge changes | 0.5-1MB | usually skip for narrative recaps |
| `AnalysisSplitter/` | Splitter routing + sub-pipeline | small/medium | SPLITTER routing only |
| `TurnResolutionSplitter/` | Splitter routing only | ~25KB | **DO NOT extract action from here** |
| `WritingAgents/` | AI player takeover (Robert) | ~150KB | sometimes contains synthesis |
| `AI_Player_Takeover/` | Full AI player synthesis | 3-13MB | `Execution Stage (Robert)` TRANSFORMATION_START |
| `NPC_Turn/` | NPC subordinate turn (autonomous) | 1-13MB | `npc actor pipe` API_CALL_SUCCESS (skip characterProfile) |
| `NPC_Judge/` | NPC stat changes | 0.4-1MB | reasoningConclusion same as Judge |
| `NPC_Narrative/` | NPC narrative | 2-13MB | TRANSFORMATION_SUCCESS text |
| `NPC_PlayType/` | Play classification (research/military/diplomatic) | 50-70KB | `Play Detection Agent` fullPrompt in metadata |
| `NPC_TargetDetectors/`, `NPC_LorebookUpdate/` | NPC sub-pipelines | small | usually skip |
| `AI_Counter_Response/` | Counter-play narrative | 2-7MB | rarely used in post-mortem |
| `NPC_ResponseRefinement_*/` | NPC response polish | 100-300KB | usually skip |

## Critical pitfalls

1. **TurnResolutionSplitter `trace.json` is just routing** — 11 events showing `SPLITTER_START → CONTENT_DISTRIBUTION → PARALLEL_START → END`. It does NOT contain the action. The action is deeper: in `ValidationSplitter/{ts}/validator/trace.json` (player) or `AI_Player_Takeover/trace.json` (Robert) or `NPC_Turn/trace.json` (NPC).

2. **MaintenanceSplitter has nested timestamp dirs** — `MaintenanceSplitter/{ts}/trace.json` is the splitter's routing; the actual subagent outputs are in `MaintenanceSplitter/{ts}/updates/trace.json` and `MaintenanceSplitter/{ts}/scan/trace.json`. Walk the tree.

3. **WritingAgents ≠ NeoWritingAgent** — the former is for AI player takeover, the latter is the actual narrative writing pipeline (Nordold Trable). Don't confuse them.

4. **Bundled `parse_json_trace.py` strips `content.text`** — the skeleton output is great for finding failures, model IDs, pipe names, and `reasoningContent`. But you MUST re-read the original `trace.json` (or use targeted grep) to get the actual action/narrative text.

5. **Some turns are mid-pipeline** — R4T3 Robert had no Judge trace. Only `AI_Player_Takeover` and `WritingAgents`. Means the turn was interrupted before judging. Mark as "No Judge trace — outcome not recorded" rather than guessing.

6. **NPC action text is buried in characterProfile boilerplate** — when looking for the NPC's action, skip short entries containing `characterBackground`. The actual narrative is 200-5000 chars and doesn't start with that pattern.

## Failure patterns we see in this game

Across 12 turns / 4 rounds, only 2 actual failures occurred. Both recovered automatically:

1. **`API_CALL_FAILURE` on `author` pipe with `stopReason=max_tokens`** — Palmyra writer hit token limit. `responseLength=38367`, `outputTokens=8003`, `maxTokenOverflow=true`. The system retried the call and the next `API_CALL_SUCCESS` recovered.

2. **`PIPE_FAILURE` on `npc gains and losses pipe->validator pipe`** — qwen3-coder refused to validate the output. The system ran the `Refusal Detection Gains/Losses (Palmyra Fallback)` pipe and recovered.

If you see a failure, look for the recovery pipe name — Autogenesis has fallback pipes for most of the LLM stages.

## Recurring narrative motifs in this game

(Lord Maple Tree's Autogenesis session — pancakes, syrup, Robert the Destroyer.)

When the user asks for a post-mortem of a *different* Autogenesis session, these won't apply — but the *pattern* of recurring motifs being identified in the report is useful:

- Track 3-5 imagery patterns that recur across multiple turns (e.g. 7.83 Hz, pancakes, mummified engineers)
- Note which entities/objects appear repeatedly (e.g. Ocular Engineer #7, Form 11X-Λ, the fax machine in Corridor 13B)
- Note tone shifts (e.g. "ceremonial absurdity" pattern in invasions)

## Report shape

The user wants a per-turn breakdown. Suggested output structure:

1. **Headline stats** — turn count, failure count, validator pass rate
2. **Per-turn sections** — Action / Validator / Narrative / Judge verdict / Failures
3. **Pattern analysis** — per-player run, recurring motifs, system health
4. **Net outcome** — what actually changed in the game world

Don't try to summarize in <100 words. The user is asking for a *post-mortem* — they want detail. ~3-5KB is a reasonable report size for 12 turns.
