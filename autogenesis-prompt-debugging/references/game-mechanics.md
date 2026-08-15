# Game Mechanics Reference

Game simulation mechanics that are not prompt-layer issues — NPC turn interference, turn order, game math, and WorldManager orchestration.

## NPC Turn Interference — `interferenceChanceFor` (TurnHarness.kt)

Determines which NPCs get a turn each round and at what probability.

### Type-based chance table

`rollNpcInterference()` in `TurnHarness.kt` uses `interferenceChanceFor()` to determine per-NPC roll chances:

| NPC Type | Interference Chance |
|---|---|
| ElderGod | 60% |
| Nemesis | 40% |
| Hostile | 20% |
| Active | 10% |
| Subordinate | 5% |
| Passive | 0% (excluded from rolls entirely) |

The roll loop at `TurnHarness.kt:3164–3172` iterates shuffled eligible NPCs (`!isDefeated && type != Passive`) and fills up to `maxSlots` slots (1–4, rolled fresh each round).

### Override semantics — `Npc.interferenceChance` field

The `Npc` struct has a field `interferenceChance: Double = 0.2` (Npc.kt:38). The `interferenceChanceFor()` function applies this priority:

```
field > 0.0  → use field value (designer override)
field == 0.0  → fall back to type-based table
```

This means:
- Serialized worlds with explicitly set `interferenceChance` values keep those overrides.
- Map editors can tune individual NPCs by setting the field.
- The type-based table is the default for all NPCs with an unset (0.0) field.

### Key code locations

| What | File | Line |
|---|---|---|
| `interferenceChanceFor()` | `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt` | ~3145 |
| `rollNpcInterference()` | `TurnHarness.kt` | ~3164 |
| `insertInterferingNpcs()` | `TurnHarness.kt` | ~3166 |
| `Npc.interferenceChance` field | `sharedModel/src/commonMain/kotlin/structs/Npc.kt` | 38 |
| `NpcType` enum | `sharedModel/src/commonMain/kotlin/enums/NpcType.kt` | 49 |
| Test (override path) | `server/src/test/kotlin/org/ttt/autogenesis/server/TurnHarnessTest.kt` | 60 |

## Turn Order Construction (per-round)

`announceRoundStartIfNeeded()` at `TurnHarness.kt:1705–1707` rebuilds the turn order each round:

1. Start with `world.turnOrder` (player names), deduplicated.
2. Prune AI players with no territories (`pruneTerritorylessAiPlayers`).
3. Enforce single-player human-first (`enforceSinglePlayerActorFirst`).
4. `rollNpcInterference(world.npc)` → get list of NPCs interfering this round.
5. `insertInterferingNpcs(order, interferenceList)` → splice each interfering NPC at a random position in the order.

Each interfering NPC is inserted at `rng.nextInt(0, order.size + 1)` — fully random position, can interrupt anywhere in the player sequence.

## Key Game Math (GameMath.kt)

Scoring formulas, outcome resolution, and numeric caps live in `server/src/main/kotlin/agent/math/GameMath.kt`.

Hard numeric caps enforced at the judge/agent level (not in GameMath itself):
- Max 30 abstract resource points per single resource
- Max ±50 outcome delta per single action

## WorldManager orchestration

`WorldManager` (`server/src/main/kotlin/gameState/WorldManager.kt`) owns:
- `world: World` — the canonical game state (players, NPCs, map tiles, turn order, history)
- `playerStats`, `history`, `actionHistoryLog`
- Turn timer management (`startTurnTimer`, `stopTurnTimer`)
- `humanPlayerName`, `humanPlayerHasJoinedOnce`
- `isSinglePlayer`, `isGameActive`
- `geopoliticalAssessment`
