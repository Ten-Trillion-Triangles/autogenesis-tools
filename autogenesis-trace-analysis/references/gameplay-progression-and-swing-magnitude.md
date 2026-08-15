# Gameplay Progression and Swing Magnitude — Empirical Extraction

Session-derived reference. Use when asked to extract "gameplay progression", "swing magnitude", "territory trajectory", "empirical gameplay from traces", or to build a game progression report from trace data.

## The Two Complementary Data Sources

To reconstruct what actually happened in a game session, use **both**:

| Source | Path | What it gives you |
|---|---|---|
| `game_snapshot.json → history[]` | `~/.tpipe/debug/trace/saved-games/<uuid>/game_snapshot.json` | The canonical game-history record: every turn's action text, success/fail, territory changes, resource gains, stat buffs, territory exchanges. **Start here for progression.** |
| `world.json` | Same directory as above | Current (post-game) world state: active players, captured territories, NPC roster, karma points, map tiles. Use for the endpoint state. |
| Per-turn Judge traces | `~/.tpipe/debug/trace/Round_<N>_Turn_<M>_<Player>/Judge/trace.json` | Judge pipeline mechanics (142 events, 8 API calls per complete turn). Use for token burn and pipeline failure investigation. |

## game_snapshot.json structure

```json
{
  "history": [ /* 8 entries in Round 4 game */ ],
  "world": { ... },          // same as world.json
  "playerStats": [ /* 2 */ ], // playerData + stats per active player
  "turnOrderIndex": 0,
  "npcInterferenceList": [],
  "lastAnnouncedRound": 4,
  "lastActiveNemesisNames": [],
  "lastDefeatedNemesisNames": [],
  "mapPackName": "Jupiter: South Pole",
  "isSinglePlayer": false,
  "humanPlayerName": "Lord Maple Tree"
}
```

### history[] entry shape

```json
{
  "turnPlayer": "Lord Maple Tree",
  "turnAction": "...full action narrative text...",
  "wasPlayerSuccessful": true,
  "turnResult": "...outcome narrative...",
  "territoryGained": ["Wrakghor"],
  "resourcesWon": ["Maple Syrup Bomb Technology"],
  "statBuffsGained": {
    "Lord Maple Tree": "+15 Luck, +20 Reputation, +10 Might",
    "General Moustache": "-15 Readiness",
    "Wrakghor": "-15 Readiness"
  },
  "territoryExchanges": [{"territoryName": "Wrakghor", "from": "Jeum Myojmeotlg", "to": "Lord Maple Tree"}],
  "affectedPlayers": {
    "Jeum Myojmeotlg": {"playerName": "...", "territoriesLost": ["Wrakghor"], "netOutcome": "Negative"},
    "Lord Maple Tree": {"playerName": "...", "territoriesGained": ["Wrakghor"], "resourcesGained": [...], "netOutcome": "Positive"}
  },
  "targetIntent": "Hostile",   // or "Friendly"
  "targetEntities": ["Wrakghor"],
  "id": "..."
}
```

**Key:** `territoryExchanges` captures hand-over events (diplomatic flips, NPC interference). `territoryGained` alone misses diplomatic steals. Always check both.

## Recipe: Extract full progression report

```python
import json
from pathlib import Path

snap_path = Path("~/.tpipe/debug/trace/saved-games/<uuid>/game_snapshot.json").expanduser()
world_path = snap_path.parent / "world.json"

snap = json.loads(snap_path.read_text())
world = json.loads(world_path.read_text())

history = snap["history"]

# 1. Territory ownership trajectory
players = {p["name"]: p for p in world["activePlayers"]}
print(f"Game: {world['name']} | Round {world['roundNumber']} | {len(history)} turns completed")
print(f"Turn order: {world['turnOrder']}")
print(f"Karma pool: {world['karmaPoints']}")
print()

# 2. Per-turn summary
for i, h in enumerate(history):
    player = h["turnPlayer"]
    success = h["wasPlayerSuccessful"]
    tga = h.get("territoryGained") or []
    tex = h.get("territoryExchanges") or []
    resources = h.get("resourcesWon") or []
    buffs = h.get("statBuffsGained") or {}
    intent = h.get("targetIntent", "?")

    print(f"history[{i}] {player} | success={success} | intent={intent}")
    if tga:
        print(f"  territoryGained: {tga}")
    for tx in tex:
        print(f"  territoryExchange: {tx['territoryName']} {tx['from']} → {tx['to']}")
    if resources:
        print(f"  resources: {resources}")
    for entity, change in buffs.items():
        print(f"  {entity}: {change}")
    print()
```

## Judge pipeline token burn (complete turns, Round 3-4 confirmed)

All complete turns use the same 8-pipe chain in the Judge trace:

| # | Pipe name | Purpose |
|---|---|---|
| 1 | explicit cot | Contextual reasoning |
| 2 | gains and losses pipe | Resource outcome classification |
| 3 | mantle structured cot (gemma4ModelId) | Mantle/gemma structured reasoning |
| 4 | mantle validator pipe | Validates mantle output |
| 5 | structured cot | Standard structured reasoning |
| 6 | resource classification pipe | Classifies resources gained |
| 7 | karma pipe | Karma/Overton window assessment |
| 8 | process focused / stat change pipe | Stat delta application |

All three sampled Judge traces (R3T0 LMT, R3T2 Robert, R4T0 LMT) show:
- 142 events total
- 8 API_CALL_SUCCESS with `inputTokens` + `outputTokens` (the billed calls)
- 1 `BRANCH_PIPE_TRIGGERED` (the mantle validator always fails its first attempt, triggering Palmyra X5 fallback)
- R3T2 Robert's `AI_Player_Takeover` additionally shows `PIPE_FAILURE + API_CALL_FAILURE + PIPE_RETRY` — the reversal/harden path encounters errors

Confirmed token burn (from sampled traces):

| Turn | Input Tokens | Output Tokens |
|---|---|---|
| R3T0 LMT | 446,907 | 4,180 |
| R3T2 Robert | 446,940 | 4,800 |
| R4T0 LMT | 474,245 | 3,131 |

The R4T0 higher input is from more context loaded (longer game state = larger map + history).

## NPC-only turns (no Judge trace)

Some turns execute only NPC behavior — no human-player Judge pipeline runs. The directory will have NPC-prefixed subdirectories only:

```
Round_3_Turn_1_Syrup_Whisperer/
├── NPC_CascadeTargetDetector_Lord_Maple_Tree_Depth0/
├── NPC_Judge/
├── NPC_LorebookUpdate/
├── NPC_Narrative/
├── NPC_PlayType/
├── NPC_ResponseRefinement_Lord_Maple_Tree/
├── NPC_TargetDetectors/
├── NPC_TargetDetectors_Retry/
└── NPC_Validation/
```

**There is no `Judge/` subdirectory.** The `NPC_Judge/` trace records NPC judgment, not a human play validation. When investigating "what happened in turn X", check whether the human's `Judge/` trace exists before diving in. If only NPC-prefixed directories are present, that turn was an NPC turn.

## Incomplete turns (partially-written trace)

Some turns fail mid-pipeline and only partial traces exist:

```
Round_4_Turn_1_Robert/
├── AI_Player_Takeover/
├── TargetDetectors/
└── WritingAgents/
```

No `Judge/`, no `ValidationSplitter/`, no `ReversalAgent/`. When you encounter this pattern, the turn was interrupted or rolled back. Use the `game_snapshot.json` to see what the game history records for the preceding turn — the snapshot is written after each *completed* turn and represents the last fully-resolved state.

## Territory exchange patterns (from Round 3-4)

Two empirically confirmed swing patterns:

1. **Hostile conquest** — `territoryExchanges: []`, `territoryGained: [...]`, attacker stats buffed, defender NPC ruler legitimacy drained
2. **Diplomatic flip** — `territoryExchanges: [{from: <previousOwner>, to: <newOwner>}]`, `territoryGained: [...]` (the new owner gained it). This is how NPCs steal territories from players mid-game.

The Syrup Whisperer (NPC) in history[5] flipped `Greexshilmrmendett` from Lord Maple Tree via "friendly diplomatic influence" — a `targetIntent: Friendly` action that still transferred the territory.
