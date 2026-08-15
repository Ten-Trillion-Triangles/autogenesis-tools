# Nemesis vs. Defenders — Direct Attack Math

## Source
Derived from live code analysis, `gameplayOrchestrator.kt`, `npcOrchestrator.kt`, `nemesisAgent.kt`, `npcJudge.kt`, `GameMath.kt`, `BedrockConfig.kt`.

---

## Does the Player Get Counter-Play Against a Nemesis?

**Yes.** When a Nemesis targets a Player directly (`ActionTargetType.Player`), the flow at `npcOrchestrator.kt:570` calls `handleNpcCounterPlay`. This resolves the Player owner and triggers `generateAiCounterResponse` — the same 3-stage AI pipeline as any NPC attack. The player gets a response window.

However: this counter-play is **AI-generated**, not the player themselves composing it. A connected human player would see the counter-play UI and respond in person; a disconnected/AI-controlled player gets the `buildPlayerAgent` pipeline.

---

## The Clash Resolution Path

When `fairnessScopeApplied && fairnessDefenders.isNotEmpty()` at `npcOrchestrator.kt:781`:

```
riskLevel = intentMismatch ? 80 : (targets.size > 1 ? 65 : 45)
isSimulatedSuccess = judgeContextSuccess  // from npcJudge pass/fail
outcome = GameMath.resolveNpcVsPlayerConflict(
    npc, defenders, playType, isSimulatedSuccess, emptyList(), riskLevel
)
judgeContextSuccess = outcome.finalSuccess  // stat outcome can flip the judge result
```

The narrative success from the judge (`isSimulatedSuccess`) feeds ±40 momentum into the clash math.

---

## Core Formulas

### Nemesis Military Pressure
```kotlin
npcPressure = militaryReadiness + (pointValue × 3)
// Default: 70 + (20 × 3) = 130
```

### Defender Military Pressure
```kotlin
defenderPressure = avg(militaryReadiness) + avg(might / 2)
```

### Total Score and Momentum
```kotlin
momentum = isSimulatedSuccess ? +40 : -40   // NARRATIVE_MOMENTUM = 40
assetBonus = min(usedAssets.size × 5, 25)   // capped at 5 assets
totalScore = npcPressure - defenderPressure + momentum + assetBonus
statVictory = totalScore > 0
```

### Narrative Override (Defender Luck)
```kotlin
narrativeOverrideChance = (riskLevel - avgLuck).coerceIn(0, 100)
// Only fires when: statVictory != narrativeVictory AND narrativeOverrideChance > 0
// Roll 0-99: if roll < narrativeOverrideChance → narrative wins, else stat wins
```

**Key insight:** A high-luck defender is *worse* at resisting the override when risk is high. Low luck means the narrative roll is more likely to override the stat result — which can help when the Nemesis's narrative is favorable. But the override only flips who wins, it doesn't close the raw stat gap.

---

## Nemesis Default Stats
```kotlin
// From Npc struct (npc.kt:30-35)
pointValue = 4          // LLM picks; clamped to ≥15 for Nemesis (nemesisCreationBuilder.kt:450)
militaryReadiness = 70 // default NPC
legitimacy = 70
stagnation = 0

// After nemesisCreationBuilder enforcement:
pointValue = max(LLM-picked, 20)  // minimum 20 for Nemesis
```

Nemesis military pressure is effectively **130 base** (70 + 20×3).

---

## Concrete Scenarios: Solo Player vs. 3 Players

| Defenders | Avg Readiness | Avg Might | Defender Pressure | Raw Gap (after -40) | Override | Win Path |
|---|---|---|---|---|---|---|
| 1 solo (typical) | 50 | 40 | 70 | -100 | 0% | Must win stat gap outright (impossible) |
| 1 solo (maxed) | 100 | 100 | 150 | **+20** | 0% | Stat win by 20 pts — razor thin |
| 3 avg | 50 | 40 | 70 | **-100** | 0% | Same as solo — no improvement |
| 3 high-might | 50 | 80 | 90 | -80 | 0% | Still can't win outright |
| 3 maxed | 100 | 100 | 150 | **+20** | 0% | Same razor margin as solo maxed |
| 3 avg + high risk (multi-target intent) | 50 | 40 | 70 | -100 | 0% | Risk 65 → override 15% — tiny flip chance |
| 3 avg + low luck (intent mismatch) | 50 | 40 | 70 | -100 | **40% flip** | Flips momentum to +40, but 130 vs 70 = still -30 final |

**Critical findings:**

1. **3 average players do not break even.** Averaging spreads pressure across players but does NOT close the 60-point base gap. The 130 vs 70 math is identical for 1 solo or 3 averaged.

2. **Luck is a dead weight in this conflict.** To get a flip, `avgLuck < riskLevel`. But flipping momentum only reverses the ±40 momentum swing — it does NOT close the stat gap. A player who specs luck is simultaneously: (a) reducing their override chance and (b) not improving the stat gap. Luck is only useful as a stat-booster for resource rolls in other contexts, not as a Nemesis defense stat.

3. **The only realistic solo path:** max readiness (100) + max might (100) = defender pressure 150. TotalScore = 130 - 150 + momentum + 0 = -20 + momentum. With momentum +40 (favorable narrative) = +20. Stat win by 20 points. Thin, but exists.

4. **The realistic 3-player coordination path:** same as above, but all 3 must spec military simultaneously. Opportunity cost: none of them are investing in diplomacy, research, or luck.

5. **The intent-mismatch exploit:** if the Nemesis's narrative is favorable to the defender (e.g., the Nemesis overreaches and the narrative sounds implausible), `riskLevel = 80` and `avgLuck = 40` gives `overrideChance = 40`. That 40% flip reverses momentum, but the defender still loses the stat gap 130 vs 70 unless they've also maxed their military stats.

---

## The Fifth-Wall Advantage

The Nemesis prompt (`nemesisAgent.kt:54`) explicitly claims fifth-wall access:
> "perfect knowledge of what will happened in the past, including prior to the start of the game's story, and perfect knowledge of what will happen in the future, including alternate timelines and possible end-game scenarios"

This advantage is **not reflected in the math.** There is no numerical bonus for fifth-wall omniscience in `resolveNpcVsPlayerConflict`. The advantage is structural:
- The Nemesis knows the player's stats before they commit to a play
- The Nemesis can choose the moment of attack (when the player is low on readiness, when a key resource is depleted)
- The player cannot reciprocate this knowledge

The fifth-wall advantage is a **timing and targeting lever**, not a numerical bonus. A Nemesis with fifth-wall knowledge would rationally choose to attack when `defenderPressure` is minimized — e.g., immediately after the player spent their military points on another action.

---

## Summary: What Actually Works

| Strategy | Effectiveness | Why |
|---|---|---|
| Solo player at max military stats | Thin win (~20 pts) if narrative favorable | Gap closed to +20 but razor thin |
| 3 players averaging max military | Same razor margin | Averaging doesn't close the base gap |
| 3 players suppressing luck to trigger override | Won't work | Override only flips momentum, not the stat gap |
| 3 players speccing different stats | Won't work | Military is the only axis that matters for the clash |
| Exploit Nemesis intent-mismatch (high risk narrative) | Small boost | riskLevel=80 → overrideChance=40, but stat gap remains |
| Race to 50% territory (ignoring Nemesis) | The actual design answer | Nemesis is a clock, not a boss — outrun it |
| Multiple players pressuring simultaneously | The design answer | Forces Nemesis to spread thin across narrative fronts |

---

## Key Files
- `server/.../gameplayOrchestrator.kt:570` — `handleNpcCounterPlay` → player counter-play dispatch
- `server/.../npcOrchestrator.kt:781-802` — fairness resolution for NPC-vs-player
- `server/.../agent/math/GameMath.kt:762-856` — `resolveNpcVsPlayerConflict`
- `server/.../agent/math/GameMath.kt:273-308` — `calculateNarrativeOverrideChance`, `applyNarrativeOverride`
- `server/.../agent/math/GameMath.kt:91` — `NARRATIVE_MOMENTUM = 40`
- `server/.../agent/builders/gameplayActions/nemesisAgent.kt:45-118` — Nemesis system prompt
- `server/.../agent/builders/modifyGameState/nemesisCreationBuilder.kt:449-450` — Nemesis pointValue floor = 20
- `server/.../agent/builders/playerAgent/playerAgent.kt` — AI player counter-play pipeline
- `server/.../agent/runners/gameplayOrchestrator.kt:2850` — `generateAiCounterResponse`
- `sharedModel/.../structs/Npc.kt:30-35` — Npc defaults (pointValue=4, militaryReadiness=70)
