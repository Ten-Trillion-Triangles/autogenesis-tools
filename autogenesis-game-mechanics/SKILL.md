---
name: autogenesis-game-mechanics
description: Autogenesis game mechanics audit.
category: software-development
tags: [autogenesis, game-design, stat-economy, pacing, nemesis-spawn, karma, swing-factors]
version: 1.0.0
---

# Autogenesis Game Mechanics — Quantitative Reference

## When to Load

Load when performing any of:
- "audit swing factors", "pacing mechanics", "game balance"
- "how does X action cost work", "what is the early round boost"
- "nemesis spawn rate", "karma accumulation", "NPC interference"
- "win conditions", "victory thresholds"
- "what stops a player from doing X in one turn", "multi-territory", "capture rules"
- "validator", "rectifier", "judge mandate", "Rule #1", "Rule #3"
- Modifying `GameMath.kt`, `TurnHarness.kt`, `judge.kt`, `validator.kt`, `npcOrchestrator.kt`
- Any gameplay balancing, feature design, or bug investigation involving game rules

---

## Core Files

| Mechanic | File | Lines |
|---|---|---|
| Action costs + deduct | `server/.../gameplayOrchestrator.kt` | 1084–1104 |
| Round-start replenishment | `server/.../TurnHarness.kt` | 1658–1662 |
| Stat decay (per-round) | `server/.../TurnHarness.kt` | 3044–3143 |
| Stat floors/caps | `server/.../TurnHarness.kt` | 94–96 |
| Early-round boost | `server/.../GameMath.kt` | 90, 582–625 |
| Base score formulas | `server/.../GameMath.kt` | 109–245 |
| Narrative override | `server/.../GameMath.kt` | 265–300 |
| Harden/Soften guidance | `server/.../GameMath.kt` | 311–333 |
| NPC conflict math | `server/.../GameMath.kt` | 754–848 |
| Karma accumulation | `server/.../judge.kt` | 1303–1307 |
| Karma → Nemesis spawn | `server/.../TurnHarness.kt` | 2923–2995 |
| Nemesis revival roll | `server/.../TurnHarness.kt` | 3000–3032 |
| NPC interference slots | `server/.../TurnHarness.kt` | 3162–3191 |
| NPC interference chances | `server/.../TurnHarness.kt` | 3151–3160 |
| Win thresholds | `server/.../TurnHarness.kt` | 3238–3262 |
| Long-range modifier | `sharedModel/.../World.kt` | 409–425 |
| Counterplay routing | `gameplayOrchestrator.kt` | 582–603 |
| Single-target clamp | `gameplayOrchestrator.kt` | 167–176 |
| Validator 5-rule gate | `server/.../validator.kt` | 118–372 |
| Rectifier minimal-change | `server/.../validator.kt` | 556–710 |
| Identify-play point gate | `server/.../identifyPlayAgent.kt` | 172–198 |
| Judge mandate (capture/depose/-40) | `server/.../judge.kt` | 449–464 |
| Player-to-player transfer rules | `server/.../judge.kt` | 515–533 |
| Automatic capture rule | `server/.../judge.kt` | 535–597 |
| Counter-play path auto-add | `gameplayOrchestrator.kt` | 582–602 |
| 12-phase turn pipeline | `gameplayOrchestrator.kt` | 339–364 |
| AI delegate skips validator | `BedrockConfig.kt:65` + `gameplayOrchestrator.kt` | 394–398 |
| Summit point grants | `TurnHarness.kt` | 92, 2979, 3028 |
| Player struct | `sharedModel/.../structs/Player.kt` | full |

---

## Action Point Economy

### Round-Start Replenishment
At the start of every round, all active players receive:
```
player.militaryPoints  = 100
player.diplomacyPoints = 100
player.researchPoints  = 100
```
Source: `TurnHarness.kt:1658-1662`

### Per-Action Costs (fixed, deducted at turn execution)
| Play Type | Cost | Pool |
|---|---|---|
| Military | **50 pts** | `militaryPoints -= 50` |
| Diplomatic | **50 pts** | `diplomacyPoints -= 50` |
| Research | **50 pts** | `researchPoints -= 50` |
| Summit | **1 pt** | `summitPoints -= 1` |

If insufficient points: `alwaysFailPlayerAction = true`, action is sabotaged without deducting. (`gameplayOrchestrator.kt:529-533`)

---

## Stat Decay (Post-Turn, Per-Round)

Applied to ALL players in `applyDecayForAllPlayers()` after every turn. (`TurnHarness.kt:3079-3143`)

### Military Readiness
| Trait | Action = Military | Action ≠ Military | Floor |
|---|---|---|---|
| Warlord | +0 | +0 | **30** |
| Balanced | +5 | −5 | **30** |
| Diplomatic | +10 | −10 | **30** |
| Researcher | +5 | −5 | **30** |

### Legitimacy
| Trait | Action = Diplo | Action ≠ Diplo | Floor |
|---|---|---|---|
| Warlord | +10 | −10 | **40** |
| Balanced | +5 | −5 | **40** |
| Diplomatic | +0 | +0 | **40** |
| Researcher | +5 | −5 | **40** |

### Stagnation
| Trait | Action = Research | Action ≠ Research | Cap |
|---|---|---|---|
| Researcher | −5 (→ 0) | +0 | **60** |
| All others | +5 | +5 | **60** |

### Passive Trait Bonuses (always applied, even out-of-turn)
- **Warlord**: `militaryReadiness += 10`
- **Diplomatic**: `legitimacy += 10`
- **Researcher**: `stagnation -= 5` (always, even on non-research turns)
- **Balanced**: `militaryReadiness += 5`

### Hard Caps
```kotlin
private const val MILITARY_FLOOR  = 30
private const val LEGITIMACY_FLOOR = 40
private const val STAGNATION_CAP   = 60
```
Source: `TurnHarness.kt:94-96`

---

## Early-Round Boost (Territory Actions Only)

Applies only when targeting **unowned or self-owned** territories (NOT rival-held).

| Round | Boost Added to Score |
|---|---|
| 1 | **+140** |
| 2 | **+100** |
| 3 | **+60** |
| 4+ | **0** |

Source: `GameMath.kt:582-625`, `EARLY_ROUND_BOOSTS` map at line 90.

---

## Narrative Override (Risk/Favor Swing)

### Override Probability
```kotlin
narrativeOverrideChance = (riskLevel − playerLuck).coerceIn(0, 100)
```
- High **luck** → low override chance (narrative can't save you).
- High **risk** → high override chance (story can override even bad stats).

### Momentum Shift
```kotlin
momentum = if (isSimulatedSuccess) +40 else −40
```
Source: `GameMath.kt:91, 265-300`

### Harden/Soften Outcome Guidance
| Favor | Win? | Guidance |
|---|---|---|
| Favored | Win | **Hardened Victory** (decisive) |
| Unfavored | Win | **Softened Victory** (costly/lucky) |
| Favored | Lose | **Softened Defeat** (near miss) |
| Unfavored | Lose | **Hardened Defeat** (catastrophic) |

Source: `GameMath.kt:311-333`

### Other Score Modifiers
| Modifier | Value | Condition |
|---|---|---|
| Asset Bonus | +5 each (max **+25**) | Used assets, capped at 5 |
| Overton Window Bonus | +20 | Unconventional play (non-standard action type) |

---

## Multi-Play (Multiple Unrelated PlayTypes) — 2026-08-09

Distinct from multi-target penalties below. Multi-play is about **multiple unrelated action types in one prompt** (e.g., "research dessert tanks AND invade Sudan"), not multiple targets of one type.

### Detection (IdentifyPlay pipe, `identifyPlayAgent.kt`)

The pipe picks **one primary PlayType** and bundles every other unrelated play into `additionalCharges`:
```kotlin
fun getAllCharges(): List<PlayType> = listOf(type) + additionalCharges
```

Per the prompt's own examples (`identifyPlayAgent.kt:91-99`):
- "I invade Player X AND research the ancient ruins" → `type=Military, additionalCharges=[Research]`
- "I move troops north AND build a new trade route AND recruit spies" → `type=Military, additionalCharges=[Diplomatic, Research]`
- "I declare war AND summon an elder god" → `type=Military, additionalCharges=[Research]`

Multi-target WITHIN one play stays a single charge (no additionalCharges):
- "I invade Player X and Player Y" → `type=Military, additionalCharges=[]` (both targets in `targets` list)

The heuristic for "unrelated": if the actions would each fall under different sections (Military vs Diplomatic vs Research), they're unrelated. Same kind of play just with multiple targets → related, put in `targets` list NOT in `additionalCharges`.

### Charges (per PlayType deduction, `gameplayOrchestrator.kt:1084-1104`)

Each entry in `getAllCharges()` deducts **50 points** from its matching pool. Detect receipts in the GAME log:
```
[INFO] [GENERAL]: Subtracting 50 military points from Lord Maple Tree
[INFO] [GENERAL]: Subtracting 50 research points from Lord Maple Tree
[INFO] [GENERAL]: Point deduction verified for Lord Maple Tree (2 charge(s): Military, Research)
```

If any charge pool is short (< 50), the action is sabotaged outright (`alwaysFailPlayerAction=true`) — none of the charges deduct. A short pool means the whole turn fails.

### Multi-Play Debuff (`identifyPlayAgent.kt:225`, applied in `GameMath.kt:400-401`)

```kotlin
result.multiPlayDebuff = (result.additionalCharges.size * 25).coerceAtMost(50)
val cappedDebuff = multiPlayDebuff.coerceAtMost(50)
val totalScore = preDebuffTotal - cappedDebuff
```

- `-25 per extra unrelated play`, capped at `-50` (honors AGENTS.md ±50 single-action outcome ceiling).
- 2 unrelated plays → `-50`. 3+ unrelated plays → still `-50` (cap).
- Applied AFTER all bonuses are summed (base + favor + momentum + assetBonus + overtonBonus + earlyRoundBoost). The debuff is the LAST thing subtracted before `totalScore > 0` is checked for `statVictory`.

### Receiveable in `GameMath.resolveAction` log breakdown

```
[INFO] [GENERAL]: GameMath.resolveAction: breakdown player=Lord Maple Tree, baseScore=-60,
  favor=0, momentum=-40, rawAssetBonus=0, assetBonus=0, overtonBonus=0,
  earlyRoundBoost=140, preDebuffTotal=40, multiPlayDebuff=25, totalScore=15, statVictory=true
```

Walking the math: `40 - 25 = 15`. Without the debuff, 40. With debuff, 15 (SOFTENED VICTORY per guidance).

### Counter-intuitive rule: math is MONOLITHIC, not per-front

`GameMath.resolveAction` is called **once per turn**, not per target or per play (`gameplayOrchestrator.kt:794`). The signature:
```kotlin
fun resolveAction(
    player: Player,
    playType: PlayType,              // ONE primary type, not per-target
    targetType: ActionTargetTypeObj, // ONE type, ONE intent, FLAT target list
    ...
)
```

**Math layer IS monolithic per turn (one totalScore)** — but the per-target scoring inside `calculateBaseScore` IS per-front as of 2026-08-09. See "Per-Target PlayType Math" below for the multi-front attack case.

`ActionTargetTypeObj` has a single `type` field, a single `actionIntent`, and a flat `targets: List<String>` — plus, as of 2026-08-09, a `targetPlayTypes: Map<String, PlayType>` field that the TargetDetector LLM populates alongside `targets` (fallback: empty → use primary playType for every target). Inside `calculateBaseScore` (GameMath.kt:109-253), the early-return path dispatches per-target:
- **Military attack**: `typeMod + traitMod - (100 - territory.militaryThreatStat) + might - 20*extraMilitaryTargets`
- **Diplomatic attack**: `typeMod + traitMod - (100 - territory.diplomacyThreatStat) + reputation - 15*extraDiplomaticTargets`
- **Research attack**: `typeMod + traitMod + wealth` (no defending stat — flat score)
- **Per-target type bonus**: `calculateTypeBonus` aggregates terrain/long-range across all targets, divided evenly per target for accounting purposes.

Per-target scores sum into one `totalScore`. The multi-target debuff is applied per PlayType bucket (e.g., 1 Military + 1 Diplomatic target = 0 debuff for each bucket, not the legacy global -20). When `targetPlayTypes` is empty or a target is missing, the primary playType is assumed.

If the player writes "diplomatically annex Tile A AND militarily invade Tile B," TargetDetector emits `targetPlayTypes: {A: Diplomatic, B: Military}` and the math dispatches each front against its own defending stat. The aggregate `totalScore` is still one number — the math is monolithic per turn but per-front within the turn.

**The judge handles per-front attribution at the narrative level** (especially after the AGENCY VERIFICATION + PARTIAL-WIN patch — see `autogenesis-prompt-debugging` § "Judge Prompt Hardening — AGENCY VERIFICATION"), but the math layer produces one `totalScore` and the judge applies it against the per-front winner/loser profile.

**Implication for player agents:** if a player wants Tile A scored as Diplomatic and Tile B as Military, they CAN now (as of 2026-08-09). The trade-off is the LLM must accurately tag each target — a vague prompt like "annex Sudan and Ethiopia" without verbs will default to Military for both. Frame the prompt with verbs that uniquely identify each front's attack vector.

**Implication for player→player interaction:** a mixed multi-front attack now scores each front against its own defending stat. The WORST front's difficulty no longer drags down the OTHER front — Tile A's Diplomatic capture is independent of Tile B's Military capture.

### Cross-cutting rule: ALWAYS check the `multiPlayDebuff` log line

If the player reports "I won the territory but lost the stat" or "the math should have favored me but it didn't," check `GameMath.resolveAction: breakdown` for the debuff. A `-50` debuff from 2 unrelated plays is invisible to the player but fully accounts for the discrepancy. The penalty is INTENDED — it punishes cramming. Verify the player didn't accidentally bundle two unrelated plays into one prompt.

### Provenance

R1T0 Lord Maple Tree verified end-to-end 2026-08-09:
- Prompt: "Research dessert tanks + invade Sudan + invade Ethiopia"
- IdentifyPlay output: `type=Military, additionalCharges=[Research], multiPlayDebuff=25, enoughPoints=true`
- Charges: 50 military + 50 research = 100 points deducted
- Resolve breakdown: `baseScore=-60, ..., preDebuffTotal=40, multiPlayDebuff=25, totalScore=15, statVictory=true`
- Verdict: SOFTENED VICTORY (favored at score 15, guidance "was unfavored but managed to eke out a win")

The R1T0 case confirms the multi-play math is wired correctly. The downstream bug (LLM misattributing capture) is a separate issue — see `autogenesis-prompt-debugging` § "Judge Prompt Hardening — AGENCY VERIFICATION."

## Multi-Target Penalties

When a single action targets **more than one territory** (extraTerritories = total targets − 1):

| Play Type | Penalty | Notes |
|---|---|---|
| Military | **−20 per extra target** | Linear, not multiplicative |
| Diplomatic | **−15 per extra target** | Softer than military; narrative framing matters more |
| Research | **None** | No multi-target penalty |

The penalty is applied AFTER the base score and trait modifiers are summed. It stacks linearly — a 3-territory military action (2 extras) loses 40 points from the penalty alone.

The orchestrator clamps base scores so they never drop below 0, but the multi-target penalty can still render a marginal play futile.

**Single-target clamp:** `gameplayOrchestrator.kt:167-175` filters multi-territory target lists to `targets.first()` only — this is the hard architectural ceiling, not the penalty math. The judge can still reward narrative success for a secondarily-targeted territory through the override system.

Source: `GameMath.kt:167-178, 201-208`

## Per-Target PlayType Math (2026-08-09)

For multi-front attacks where each front uses a different attack vector (e.g., one Diplomatic capture + one Military invasion), the math dispatches per-target as of 2026-08-09.

### Data flow
1. **TargetDetector LLM** emits `targetPlayTypes: Map<String, PlayType>` alongside `targets` — e.g. `{"Sudan": "Military", "Ethiopia": "Diplomatic"}`. When the player uses one attack vector against all targets, the map carries the same PlayType for every name. When a target has no clear attack verb, the LLM defaults to "Military" per the prompt.
2. **`ActionTargetTypeObj.targetPlayTypes`** carries the map through the orchestrator to `GameMath.resolveAction`. Default `emptyMap()` for backwards compatibility — single-PlayType turns flow through unchanged.
3. **`calculatePerTargetScore`** (`GameMath.kt`) walks each target, looks up its per-target PlayType (fallback to primary when missing), and computes:
   - `resourceBoost = when(playType) { Military → player.might; Diplomatic → player.reputation; Research → player.wealth }`
   - `traitMod` per the per-target PlayType (Warlord+Military=+20, Warlord+Diplomatic=-20, etc.)
   - `defendingStat = when(playType) { Military → territory.militaryThreatStat; Diplomatic → territory.diplomacyThreatStat; Research → 0 }`
   - `penalty = (100 - defendingStat).coerceAtLeast(0)`
   - `perTargetScore = typeBonusContribution + traitMod - penalty + resourceBoost`
4. **Per-PlayType multi-target debuff** (`calculatePerPlayTypeExtraTerritoryDebuff`): `-20` per extra UNOWNED Military target, `-15` per extra UNOWNED Diplomatic target, `0` for Research. Owned targets are excluded — the system does not penalize multi-attack actions against territories the player already owns.
5. **Aggregate**: `totalScore = sum(perTargetScore) - perPlayTypeExtraDebuff`. One number for the turn verdict.

### Per-target territory defending stats
- `territory.militaryThreatStat` (default 0): how threatening the territory is militarily. Used as the defending stat against Military attacks.
- `territory.diplomacyThreatStat` (default 0): how threatening the territory is diplomatically. Used as the defending stat against Diplomatic attacks.

These are TERRITORY-attached (per the `Structs.kt:Territory.kt:45-46` data class), not player-attached. The attack/defense pair is: `player.might → territory.militaryThreatStat` for Military, `player.reputation → territory.diplomacyThreatStat` for Diplomatic.

### Pitfall — multi-target debuff must filter on UNOWNED targets, not all targets

The legacy `calculateBaseScore` applied the multi-target debuff using `extraTerritories = (unownedTargetsCount - 1).coerceAtLeast(0)`. When refactoring to per-target dispatch, **the debuff counting must preserve the unowned-only filter** — owned targets (ruler = player name) do not contribute to the multi-target penalty.

The 2026-08-09 refactor initially dropped the unowned filter and broke the pre-existing `MultiTargetPenaltyTest` (5 tests, all failing with `-20 expected, got 0`). The fix at `calculatePerPlayTypeExtraTerritoryDebuff` in `GameMath.kt`:
```kotlin
val territory = world.mapTiles.firstOrNull { it.name.equals(targetName, ignoreCase = true) } ?: continue
if (territory.ruler.isNotBlank() && !territory.ruler.equals("Neutral", ignoreCase = true)) continue
```
This mirrors the legacy `!ruler.equals(normalizedPlayerName) && ruler.isNotBlank()` semantics. The `MultiTargetPenaltyTest` test setup uses `ruler = ""` for unowned and `ruler = "Commander"` for owned — the check correctly classifies them.

**Recipe for any future per-target math refactor:** always re-run `MultiTargetPenaltyTest` (8 tests covering 2/3/4-target military and 2/3-target diplomatic linear debuffs) as the regression gate. The unowned-only filter is the load-bearing semantic.

### Pitfall — per-target defending stat is territory-attached, not player-attached

The defending stat lives on the `Territory` data class (`militaryThreatStat`, `diplomacyThreatStat`), not on the `Player`. A common refactor mistake is to read `player.militaryReadiness` (player resource) as the defending stat — that's the ATTACKER's decay, not the DEFENDER's threat. The attack/defense pair is:

| Attack vector | Attacker resource | Defender threat |
|---|---|---|
| Military | `player.might` (+) | `territory.militaryThreatStat` |
| Diplomatic | `player.reputation` (+) | `territory.diplomacyThreatStat` |
| Research | `player.wealth` (+) | none (flat 0) |

For a fresh `Territory` (defaults `militaryThreatStat = 0`, `diplomacyThreatStat = 0`), the penalty is `100 - 0 = 100` — a heavy debuff. Territories with low defending stats are NOT easy targets in this math; the formula is monotone-decreasing in defending stat. A future "low-defense bonus" (inverted formula for low-defense targets) is a deliberate design change, not a bug.

### Provenance (R1T0 Lord Maple Tree, 2026-08-09)

- **Pre-refactor**: R1T0 was a single-PlayType Military turn (with Research as additional charge). `totalScore = 15`, `statVictory = true`.
- **Post-refactor**: TargetDetector emits `targetPlayTypes` with both targets tagged Military (since the player used "invade Sudan AND invade Ethiopia" — same attack vector). Per-target path: each target scored against its own `militaryThreatStat`, summed, minus `20*1` multi-target debuff. The math matches the pre-refactor totalScore within `calculateTypeBonus`'s per-target aggregation semantics.
- **Backwards-compat verified**: `MultiTargetPenaltyTest` (8 tests, 2/3/4-target linear debuffs) continues to pass. `PerTargetScoreTest` (5 new tests) covers the per-front multi-PlayType case.

### Live verification (deferred to operator)

The R1T0 fallback path (`targetPlayTypes` empty → use primary PlayType) is exercised by every existing capture in the trace history. To exercise the new per-target PlayType math live, the player must declare a turn like "invade Sudan AND negotiate with Ethiopia" — the LLM tags each target with its own attack vector, the math dispatches per-target. A fresh game session is required; out of scope for automated CI.

## Long-Range Targeting Modifier

For military attacks targeting a territory **not adjacent** to any player-owned territory, the system applies a long-range modifier instead of the adjacent terrain bonus. Computed per target in `calculateTypeBonus` (`GameMath.kt:467-480`):

```
longRangeModifier = (terrainAdvantage − distancePenalty + terrainTypeModifier).coerceIn(−40, +40)
distancePenalty  = BFS_distance × 5   // each intermediate tile costs 5 points
```

- **−5 per BFS step** between the closest owned territory and the target, capped at **−40**
- Terrain advantage is computed for the commander type vs. the terrain along the path (not the target terrain)
- `World.kt:409-425` — full formula; `World.kt:258-475` — BFS pathfinding

The long-range modifier **replaces** the adjacent-terrain bonus (lines 483-534). A non-adjacent target gets `longRangeModifier` added to its contribution; an adjacent target gets the terrain-border bonus instead. They do not stack.

**Implication for player agents:** The prompt in `playerAgent.kt` Stage 2 must explicitly tell the agent that multi-target plays are legal but penalized, and that long-range targeting has an explicit `distance × 5` cost. The prompt historically had vague "severe statistical penalties" language with no values — that gap was fixed in `playerAgent.kt` by adding explicit `-20`/`-15` per extra target and `-5 per BFS step` disclosures. Verify the Stage 2 prompt contains these values before trusting player agent strategic planning.

---

## Narrative & Legal Gates (Validator / Rectifier / Judge)

The math above answers "if the play is allowed, what does it score?" The narrative layer
answers "is the play allowed at all, and does it actually win?" — these are three separate
LLM-driven pipes plus the judge's hardcoded rule-following. They are the **primary ceiling**
on multi-territory turns, not the math.

| Gate | File | What it does |
|---|---|---|
| Validator (legality) | `validator.kt:118-372` | 5-rule gate: narrative control, resource plausibility, NPC ownership, commander removal, anti-retcon |
| Rectifier (repair) | `validator.kt:536-710` | Smallest-legal-change rewrite of illegal plays (pass-the-turn, not patch-the-play) |
| Identify-Play (point gate) | `identifyPlayAgent.kt:172-198` | Each play type requires matching pool ≥ 50 (Summit ≥ 1) |
| Target detector | `targetDetectorAgent.kt:601` | Classifies target as Player/NPC/Territory/Self/Abstract/NoTarget |
| Single-target clamp | `gameplayOrchestrator.kt:167-176` | Filters multi-territory targets to `targets.first()` — hard ceiling on multi-capture |
| Judge (gain/loss) | `judge.kt:449-597` | Mandate: hostile SUCCESS → capture / depose / −40 debuff. Auto-capture rule. |
| Player-to-player transfer | `judge.kt:515-533` | Only hostile military can transfer between players. Other intents auto-convert to neutral. |
| Counter-play auto-add | `gameplayOrchestrator.kt:582-602` | Non-adjacent attacks whose path crosses another player auto-add that player as a defender |

**The Quote Rule** (validator.kt:152-165): anything in `""` is automatically legal under
Rule #1 (narrative control). The world's *response* to that dialogue is still the judge's
domain.

**AI delegate skips the validator:** `BedrockConfig.skipValidationForAi = true`
(`BedrockConfig.kt:65`) — only human players hit the 5-rule gate. This is why the validator's
anti-censorship / anti-refusal clause is so heavily enforced.

**Point-spending discipline:** the validator doesn't touch action points. The orchestrator's
`deductPoints()` runs only if the play was not sabotaged for insufficient funds
(`gameplayOrchestrator.kt:529-538, 1084-1104`). A sabotaged play costs nothing.

Full reference with code-line citations, the 12-phase turn pipeline diagram, and a narrative-gate
quick-lookup table: `references/validator-and-judge-gates.md`.

---

## Long-Range Attack Modifier

For non-adjacent military attacks:
```kotlin
distancePenalty = distance × 5
terrainAdvantage = based on commander type vs path obstacles
modifier = (terrainAdvantage − distancePenalty + terrainTypeModifier).coerceIn(−40, +40)
```
BFS pathfinding: `World.kt:258-475`. Long-range calculation: `World.kt:409-425`.

---

## Karma & Nemesis Spawn System

### Karma Accumulation
When judge karma pipe returns `true` (hostile action vs NPC, attacking neutral territory, killing beings, property damage):
```kotlin
WorldManager.world.karmaPoints += 5
```
Source: `judge.kt:1303-1307`

### Nemesis Spawn Trigger
```kotlin
if (WorldManager.world.karmaPoints >= 100) {
    shouldSpawn = true
    WorldManager.world.karmaPoints = 0  // reset after spawn
}
```
- **20 qualifying actions** to fill karma bar.
- Nemesis resurrection: **1–5 turns** after death. (`nemesisAgent.kt:57`)
- Summit points granted on nemesis event: +1 per player. (`TurnHarness.kt:92`)

### Nemesis Revival Roll (per turn)
```kotlin
if (rng.nextInt(100) < 25) { /* revive */ }
```
25% chance per turn for any defeated nemesis to return.
Source: `TurnHarness.kt:3000-3032`

### Elder God Behavior
- Each turn: **must destroy one map tile permanently**. (`elderGodAgent.kt:79`)
- Cannot be killed/conventionally defeated — only banished or countered by another Elder God.
- Fixed 60% interference chance. (`TurnHarness.kt:3154`)

---

## NPC Interference (AI Behavior Per Round)

### Slot Roll (how many NPCs get to act)
```kotlin
roll = rng.nextDouble()
slots = when { roll < 0.50 -> 1; roll < 0.80 -> 2; roll < 0.95 -> 3; else -> 4 }
```
Source: `TurnHarness.kt:3162-3173`

### Per-NPC Interference Chance
| NPC Type | Chance |
|---|---|
| ElderGod | **60%** |
| Nemesis | **40%** |
| Hostile | **20%** |
| Active | **10%** |
| Subordinate | **5%** |

Source: `TurnHarness.kt:3151-3160`

---

## Victory Conditions & Win Thresholds

### Player Domination (by player count)
| Players | Threshold |
|---|---|
| 4 | **51%** of map (territory count OR point share) |
| 3 | **55%** |
| 2 | **60%** |

### NPC / Elder God Win
- **Nemesis or Elder God**: fixed **50%** of map.

### Max Rounds
- Hard cap at **round 25**.

### Tiebreaker
1. Resource scoring ($1 per resource)
2. Random roll

Source: `TurnHarness.kt:3238-3262`, `answerAgent.kt:211`

---

## Large Single-Turn Swing Summary

| Swing Factor | Magnitude | Direction | Trigger |
|---|---|---|---|
| Early-Round Boost R1 | +140 | Up | Own/unowned territory, round 1 |
| Early-Round Boost R2 | +100 | Up | Same, round 2 |
| Early-Round Boost R3 | +60 | Up | Same, round 3 |
| Narrative Momentum | ±40 | Either | Pass/Fail flip |
| Risk Override Roll | 0–100% | Either | High-risk surviving bad stats |
| Overton Window Bonus | +20 | Up | Unconventional play |
| Asset Bonus | +5 each (max 25) | Up | Up to 5 assets used |
| Long-Range Penalty | −5 per tile | Down | Non-adjacent attack |
| Multi-Target Military | −50% per extra | Down | Multiple rival territories |
| Karma → Nemesis Spawn | World-level threat | Down | 100 karma accumulated |
| Nemesis Revival | 25% chance | Down | Random per turn |
| Elder God Destruction | Permanent tile loss | Down | Each Elder God turn |

---

## NPC-vs-Player Conflict Formulas

Source: `GameMath.kt:754-848` (`resolveNpcVsPlayerConflict`)

| PlayType | NPC Pressure | Defender Pressure |
|---|---|---|
| Military | `militaryReadiness + (pointValue × 3)` | `avgReadiness + (avgMight / 2)` |
| Diplomatic | `legitimacy + (pointValue × 2)` | `avgLegitimacy + (avgReputation / 2)` |
| Research | `(100 − stagnation) + (pointValue × 2)` | `avgAntiStagnation + (avgWealth / 2)` |
| Summit | `(military+legitimacy)/2 + (pointValue×2)` | `avgAuthority + (avgReputation/3)` |

Asset bonus: `min(usedAssets × 5, 25)`.

---

## Summit Points

- Summit is a **cooperative** diplomatic play targeting all other active players simultaneously.
- Costs **1 summit point** per action.
- Summit points are granted during nemesis events (+1 per player, `SUMMIT_POINTS_ON_NEMESIS_EVENT = 1`).
- During active Nemesis/ElderGod threat, players receive `WorldManager.SUMMIT_POINTS_PER_ROUND` per round.
- Source: `TurnHarness.kt:92, 1711-1717, 2979, 3028`

---

## Quick Lookup: Stat-to-Formula Mapping

| Player Stat | Used In Formula | Decay Trait Modifier |
|---|---|---|
| `might` | Military resource boost (+), defender pressure (÷2) | — |
| `reputation` | Diplo resource boost (+), defender pressure (÷2) | — |
| `wealth` | Research resource boost (+), defender pressure (÷2) | — |
| `militaryReadiness` | Military readiness penalty (`100 − readiness`) | Trait-controlled decay |
| `legitimacy` | Diplo legitimacy penalty (`100 − legitimacy`) | Trait-controlled decay |
| `stagnation` | Research base (`100 − stagnation`) | Trait-controlled decay |
| `luckPoints` | Narrative override resistance (`risk − luck`) | — |

| Territory Stat | Used In Formula | Default |
|---|---|---|
| `militaryThreatStat` | Per-target Military attack penalty (`100 − stat`) | 0 |
| `diplomacyThreatStat` | Per-target Diplomatic attack penalty (`100 − stat`) | 0 |

Source: `GameMath.kt:109-245`, `Player.kt`, `Territory.kt:45-46`

---

## References

- `references/game-mechanics-audit.md` — full stat-economy audit (decay tables, formula source, early-round boost, karma, victory, NPC-vs-player).
- `references/validator-and-judge-gates.md` — narrative/legal layer that gates capture (single-target clamp, 5-rule validator, rectifier minimal-change semantics, judge mandate, transfer restrictions, counter-play auto-add, AI-skip behavior).
- `references/turn-wall-clock-budget.md` — empirical wall-clock-per-turn measurements (human/NPC/AI player) derived from `~/.tpipe/debug/trace/` and the recipe for computing them. Use when projecting game duration, capacity planning, or pricing cost-per-hour.
- `references/monetization-pricing-model.md` — cost basis, subscription tier design, free tier + credit economy, matchmaker subsidy ladder (hardcoded from `AccountSettingsMatchmaking.kt`). Load when building any pricing/monetization dashboard or projection for the game.
- `references/nemesis-vs-defender-math.md` — concrete direct-attack clash math: Nemesis military pressure = 130 (base), solo/3-player defender pressure = 70 (avg stats), the -100 raw gap that averaging does NOT close, luck-as-dead-weight in this conflict, the only realistic defense paths. **Key finding: 3 average players do not break even against a direct Nemesis attack.**

## Monetization & Pricing Models

Pricing model work for Autogenesis always has these inputs from real trace data + the operator's standing decisions:

### Active production model portfolio (4 models)
Confirmed from `server/.../globals/BedrockConfig.kt` and trace data. **Qwen3 235B A22B is dormant** (the operator removed it from the active gameplay path):
| Model | Concrete ID | Transport | Context | Role |
|---|---|---|---:|---|
| Qwen3 Coder 30B A3B | `qwen.qwen3-coder-30b-a3b-v1:0` | Bedrock Converse | 235K | Gameplay workhorse |
| Gemma 4 E2B | `bedrock-mantle.gemma4ModelId` | Bedrock Mantle | 128K | Request classification, refinement, OpenWidget |
| Gemma 4 31B | `bedrock-mantle.gemma31ModelId` | Bedrock Mantle | 235K | AI planning, high-context writing, maintenance |
| Llama 4 Scout 17B | `us.meta.llama4-scout-17b-instruct-v1:0` | Bedrock Converse | 3.5M | Answer Agent, UserActionClassificationAgent |

Qwen3 235B A22B is dead code: `BedrockConfig.kt:476` constant + uncalled `buildResourceDispatcher()` at `resourcedispatcher.kt:50` + dead locals at `nemesisCreationBuilder.kt:124-135`. Zero `qwen.qwen3-235b` matches in any trace.

### Credits (operator's standing decision — locked, not negotiable)
- **1 credit = 1,000 tokens.** Token-anchored, not per-call pricing.
- Tier design: $5/$10/$25/$50/$100 fixed packs, with $100 pack eligible for operator-set bulk discount.
- Bonuses (login/event/retention) are operator-issued and must be tracked as real cost at the blended $/M token rate.

### Subscription tier design (operator's intent)
- $25: 4-player multiplayer only (entry tier)
- $50: + 1v1 single-player unlocked
- $75: + 1v3 single-player unlocked (full single-player)
- $100: full access + creator/grinder overage headroom

This is a **feature-gate** model, not a cohort-affordability model. The margin/overage sliders change affordability annotations, NOT the unlock gate.

### Matchmaker subsidy ladder (hardcoded from `AccountSettingsMatchmaking.kt`)
Credits affect matchmaking placement via a hardcoded ladder. The COST CLASS determines how many slots a player subsidizes in matchmaking:
| Class | How earned | Subsidy slots |
|---|---|---:|
| BYO_KEY | Player brings own API key | 4 (cap) |
| PRO | $75/$100 plan + auto-renew | 2 |
| CASUAL | $25/$50 plan + auto-renew | 1 |
| CREDIT | Non-zero credit balance (≥1,000 cr) | 0 + bonus |
| FREE | No plan, no credits | 0 |

**CREDIT bonus formula** (`AccountSettingsMatchmaking.kt:46-57`): `floor(credits / 1000) × creditSubsidyPerThousand`, capped at 2 extra slots. A 2,000+ credit player is effectively CASUAL-level for matchmaking.

**Pricing-derivation pitfall:** Do not derive pricing from another tier. The operator caught me fabricating "Qwen Standard = Flex ÷ 0.75" math (Flex is stated as "discounted", not as a specific 25% discount). Always cross-check pricing against at least one external source (AWS Bedrock pricing page, `ModelPricing.kt`, or another operator-confirmed rate) before shipping any pricing-derived artifact. When in doubt, present the range and pin the bucket in writing.

**Token-derivation pitfall:** Use `inputTokens` (provider-billed) for cost/pricing, not `totalInputTokens` (cumulative rollup across retries and child pipes). Mixing them inflates per-turn cost by ~2-4×. See `tpipe-trace-parser` SKILL.md § "Token field taxonomy" for the bucket distinction.

**Margin semantics pitfall:** "Margin" in this model is the after-inference headroom fraction. It does NOT directly equal real profit margin — payment fees (~3%), infra/support (~5%), and taxes eat into it first. Below 50% margin is the loss-leader/break-even zone, not "still profitable with reduced margin." The model includes a `Target profit %` slider to make the actual profit visible after fixed costs.
