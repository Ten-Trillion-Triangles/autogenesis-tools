# Autogenesis Game Mechanics Audit — Full Quantitative Reference

## Audit Scope
Quantitative reverse-engineering of swing factors and pacing mechanics from live source code.
Code paths verified: `GameMath.kt`, `TurnHarness.kt`, `judge.kt`, `npcOrchestrator.kt`, `World.kt`, `Player.kt`, `gameplayOrchestrator.kt`.

---

## Action Point Economy

### Round-Start Replenishment (`TurnHarness.kt:1658-1662`)
```kotlin
world.activePlayers.forEach { player ->
    player.militaryPoints  = 100
    player.diplomacyPoints = 100
    player.researchPoints  = 100
    player.summitPoints += 0  // summit points do NOT reset each round
}
```

### Per-Action Costs (`gameplayOrchestrator.kt:1084-1104`)
```kotlin
private suspend fun deductPoints(player: Player, type: PlayType) {
    when(type) {
        PlayType.Military  -> { player.militaryPoints  -= 50 }
        PlayType.Diplomatic-> { player.diplomacyPoints -= 50 }
        PlayType.Research  -> { player.researchPoints  -= 50 }
        PlayType.Summit    -> { player.summitPoints   -= 1  }
    }
}
```

### Insufficient Points → Sabotage (`gameplayOrchestrator.kt:529-533`)
```kotlin
var alwaysFailPlayerAction = !playType.doesPlayerHaveEnoughPoints
if (alwaysFailPlayerAction) {
    Logger.warn(..."Player ${player.name} does not have enough points for ${playType.type}. Sabotaging play.")
}
// deductPoints is NOT called when alwaysFailPlayerAction is true
```

---

## Stat Decay — Full Tables (`TurnHarness.kt:3079-3143`)

### applyDecayForActor() logic
For the **active player** (the one who just acted), the action category is used to decide direction.
For **all other players**, `ActionCategory.OTHER` is used (all deltas apply as "not matching").

```kotlin
private fun applyDecayForActor(player: Player, actionCategory: ActionCategory) {

    // --- Military Readiness ---
    val militaryDelta = when(player.trait) {
        CommanderTrait.Diplomatic -> 10
        CommanderTrait.Balanced -> 5
        CommanderTrait.Warlord   -> 0
        CommanderTrait.Researcher-> 5
    }
    player.militaryReadiness = if (actionCategory == ActionCategory.MILITARY)
        (player.militaryReadiness + militaryDelta).coerceIn(30, 100)
    else
        (player.militaryReadiness - militaryDelta).coerceIn(30, 100)

    // --- Legitimacy ---
    val legitimacyDelta = when(player.trait) {
        CommanderTrait.Warlord   -> 10
        CommanderTrait.Balanced  -> 5
        CommanderTrait.Diplomatic-> 0
        CommanderTrait.Researcher-> 5
    }
    player.legitimacy = if (actionCategory == ActionCategory.DIPLOMATIC)
        (player.legitimacy + legitimacyDelta).coerceIn(40, 100)
    else
        (player.legitimacy - legitimacyDelta).coerceIn(40, 100)

    // --- Stagnation ---
    val stagnationDelta = if (player.trait == CommanderTrait.Researcher) 0 else 5
    player.stagnation = if (actionCategory == ActionCategory.RESEARCH)
        (player.stagnation - stagnationDelta).coerceIn(0, 60)
    else
        (player.stagnation + stagnationDelta).coerceIn(0, 60)

    // --- Passive Trait Bonuses (always applied) ---
    when(player.trait) {
        CommanderTrait.Warlord   -> { player.militaryReadiness += 10 }
        CommanderTrait.Diplomatic-> { player.legitimacy        += 10 }
        CommanderTrait.Researcher -> { player.stagnation        -= 5  }
        CommanderTrait.Balanced   -> { player.militaryReadiness += 5  }
    }
}
```

### traitCategorizeAction() — used to classify the action (`TurnHarness.kt:3061-3077`)
```kotlin
private fun categorizeAction(action: String): ActionCategory {
    val text = action.lowercase()
    return when {
        text.contains("attack") || text.contains("invade") ||
        text.contains("military") || text.contains("defend") -> ActionCategory.MILITARY
        text.contains("alliance") || text.contains("treaty") ||
        text.contains("diplom") || text.contains("negot")    -> ActionCategory.DIPLOMATIC
        text.contains("research") || text.contains("develop") ||
        text.contains("invent") || text.contains("science")   -> ActionCategory.RESEARCH
        else -> ActionCategory.OTHER
    }
}
```

---

## Early-Round Boost (`GameMath.kt:582-625`)

```kotlin
private val EARLY_ROUND_BOOSTS: Map<Int, Int> = mapOf(1 to 140, 2 to 100, 3 to 60)

private fun earlyRoundBoostAmount(player: Player, targetType: ActionTargetTypeObj): Int {
    val round = WorldManager.world.roundNumber
    val boost = EARLY_ROUND_BOOSTS[round] ?: return 0

    // Only for territory targets
    if (targetType.type != ActionTargetType.Territory) return 0

    // Only if ALL targets are unowned or self-owned (NOT rival-held)
    val normalizedPlayerName = player.name.trim()
    targetType.targets.forEach { targetName ->
        val territory = world.mapTiles.firstOrNull { it.name.equals(targetName, ignoreCase = true) } ?: return@forEach
        val ruler = territory.ruler.trim()
        if (ruler.isNotEmpty() && !ruler.equals(normalizedPlayerName) && !ruler.equals("Unowned"))
            return 0  // rival-held target → no boost
    }
    return boost
}
```

---

## Narrative Override Math (`GameMath.kt:265-300`)

```kotlin
private fun calculateNarrativeOverrideChance(risk: Int, playerLuck: Int): Int =
    (risk - playerLuck).coerceIn(0, 100)

private fun applyNarrativeOverride(
    statVictory: Boolean,
    narrativeVictory: Boolean,
    narrativeOverrideChance: Int,
    rng: Random
): NarrativeOverrideResult {
    if (statVictory == narrativeVictory || narrativeOverrideChance <= 0)
        return NarrativeOverrideResult(statVictory, narrativeOverrideChance)
    val roll = rng.nextInt(0, 100)
    val finalSuccess = if (roll < narrativeOverrideChance) narrativeVictory else statVictory
    return NarrativeOverrideResult(finalSuccess, narrativeOverrideChance)
}
```

### Score total in resolveAction() (`GameMath.kt:359-412`)
```kotlin
val baseScore = calculateBaseScore(player, playType, targetType)
val momentum = if(isSimulatedSuccess) +40 else -40
val assetBonus = min(usedAssets.size * 5, 25)
val overtonBonus = if(!assessment.isConventionalForOvertonWindow) 20 else 0
val earlyRoundBoost = earlyRoundBoostAmount(player, targetType)
val totalScore = baseScore + assessment.favorPoints + momentum + assetBonus + overtonBonus + earlyRoundBoost
val statVictory = totalScore > 0
```

---

## Karma System

### Karma Pipe Trigger (`judge.kt:1257-1310`)
Karma is incremented when the judge karma agent returns `true` for these conditions:
- Player took hostile action toward an NPC
- Player attacked neutral territory (not owned by another player)
- Player destroyed, killed, or inflicted damage to NPCs/beings/property

```kotlin
if (fromJson.isTrue) {
    WorldManager.world.karmaPoints += 5
    Logger.info(..."Judge: karma increased by 5 (total=${WorldManager.world.karmaPoints})")
}
```

### Nemesis Spawn Logic (`TurnHarness.kt:2923-2995`)
```kotlin
private suspend fun handleNemesisFromKarma(seedText: String) {
    var shouldSpawn = false
    WorldManager.worldMutex.withLock {
        if (WorldManager.world.karmaPoints >= 100) {
            shouldSpawn = true
            WorldManager.world.karmaPoints = 0  // reset after spawn
        }
    }
    if (!shouldSpawn) return
    // ... spawn nemesis via buildNemesisCreationAgent() ...
}
```

### Nemesis Revival Roll (`TurnHarness.kt:3000-3032`)
```kotlin
private suspend fun rollNemesisRevival() {
    val revivedName = WorldManager.worldMutex.withLock {
        val defeated = WorldManager.world.npc.filter { it.type == NpcType.Nemesis && it.isDefeated }
        if (defeated.isEmpty()) return@withLock null
        if (rng.nextInt(100) >= 25) return@withLock null  // fail → no revive
        val chosen = defeated.random(rng)
        chosen.isDefeated = false
        chosen.name
    } ?: return
    // broadcast revival announcement
}
```

---

## NPC Interference System

### Slot Roll (`TurnHarness.kt:3162-3173`)
```kotlin
private fun rollNpcInterference(npcs: List<Npc>): List<String> {
    val roll = rng.nextDouble()
    val maxSlots = when {
        roll < 0.50 -> 1
        roll < 0.80 -> 2
        roll < 0.95 -> 3
        else        -> 4
    }
    val eligibleNpcs = npcs.filter { !it.isDefeated && it.type != NpcType.Passive }.shuffled(rng)
    val results = mutableListOf<String>()
    for (npc in eligibleNpcs) {
        if (results.size >= maxSlots) break
        val chance = interferenceChanceFor(npc)
        if (rng.nextDouble() < chance) results.add(npc.name)
    }
    return results
}

private fun interferenceChanceFor(npc: Npc): Double =
    npc.interferenceChance.takeIf { it > 0.0 } ?: when (npc.type) {
        NpcType.ElderGod   -> 0.60
        NpcType.Nemesis    -> 0.40
        NpcType.Hostile    -> 0.20
        NpcType.Active     -> 0.10
        NpcType.Subordinate-> 0.05
        NpcType.Passive    -> 0.0
    }
```

### insertInterferingNpcs() — random insertion into turn order (`TurnHarness.kt:3194-3204`)
```kotlin
private fun insertInterferingNpcs(order: MutableList<String>, interfering: List<String>) {
    interfering.forEach { npcName ->
        if (order.contains(npcName)) return@forEach  // already in order
        val insertAt = rng.nextInt(0, order.size + 1)
        order.add(insertAt, npcName)
    }
}
```

---

## Victory Conditions

### Win Thresholds (`TurnHarness.kt:3238-3262`)
```kotlin
private fun playerWinThreshold(playerCount: Int): Double = when(playerCount.coerceIn(1, 4)) {
    4 -> 51.0
    3 -> 55.0
    else -> 60.0
}
private const val NPC_WIN_THRESHOLD_PERCENT: Double = 50.0

private fun ownerHitsShareThreshold(ownerName: String, thresholdPercent: Double): Boolean =
    WorldManager.hasOwnerTerritoryCountShare(ownerName, thresholdPercent) ||
    WorldManager.hasOwnerTerritoryPointShare(ownerName, thresholdPercent)
```

### selectDominantOwner — used in single-player surrender path (`TurnHarness.kt:507-516`)
```kotlin
private fun selectDominantOwner(exclude: Set<String>): String? {
    val owners = WorldManager.world.mapTiles
        .asSequence()
        .filter { !it.isDestroyed }
        .map { it.ruler.trim() }
        .filter { it.isNotBlank() && !exclude.contains(it) }
        .distinct()
    return owners.maxByOrNull { owner -> WorldManager.getOwnerActiveTerritoryPoints(owner) }
}
```

---

## Long-Range Modifier (`World.kt:409-425`)

```kotlin
fun calculateLongRangeModifier(player: Player, territoryA: Territory, territoryB: Territory): Int {
    val distance = getTerritoryDistance(territoryA, territoryB)
    val terrainAdvantage = calculateTerrainAdvantage(player, distance)
    val distancePenalty = distance.distance * 5

    var terrainTypeModifier = 0
    val path = getPathBetween(territoryA, territoryB)
    for (i in 1 until path.size - 1) {  // skip start and end tiles
        terrainTypeModifier += getTerrainTypeModifier(player.commanderType, path[i].type)
    }

    return (terrainAdvantage - distancePenalty + terrainTypeModifier).coerceIn(-40, 40)
}
```

---

## NPC-vs-Player Conflict (`GameMath.kt:754-848`)

```kotlin
fun resolveNpcVsPlayerConflict(
    npc: Npc,
    defenders: List<Player>,
    playType: PlayType,
    isSimulatedSuccess: Boolean,
    usedAssets: List<String> = emptyList(),
    riskLevel: Int = 50,
    rng: Random = Random.Default
): NpcConflictMathOutcome {
    val npcPressure = when(playType) {
        PlayType.Military  -> npc.militaryReadiness + (npc.pointValue * 3)
        PlayType.Diplomatic-> npc.legitimacy          + (npc.pointValue * 2)
        PlayType.Research  -> (100 - npc.stagnation).coerceAtLeast(0) + (npc.pointValue * 2)
        PlayType.Summit   -> ((npc.militaryReadiness + npc.legitimacy) / 2) + (npc.pointValue * 2)
    }

    val defenderPressure = if(defenders.isEmpty()) 0 else when(playType) {
        PlayType.Military  -> defenders.map { it.militaryReadiness }.average().toInt()
                               + defenders.map { it.might }.average().toInt() / 2
        PlayType.Diplomatic-> defenders.map { it.legitimacy }.average().toInt()
                               + defenders.map { it.reputation }.average().toInt() / 2
        PlayType.Research  -> defenders.map { (100 - it.stagnation).coerceAtLeast(0) }.average().toInt()
                               + defenders.map { it.wealth }.average().toInt() / 2
        PlayType.Summit    -> defenders.map { (it.legitimacy + it.militaryReadiness) / 2 }.average().toInt()
                               + defenders.map { it.reputation }.average().toInt() / 3
    }

    val momentum = if(isSimulatedSuccess) +40 else -40
    val assetBonus = (usedAssets.size * 5).coerceAtMost(25)
    val totalScore = npcPressure - defenderPressure + momentum + assetBonus

    val statVictory = totalScore > 0
    val defenderLuck = if(defenders.isEmpty()) 0 else defenders.map { it.luckPoints }.average().toInt()
    val narrativeOverrideChance = calculateNarrativeOverrideChance(riskLevel, defenderLuck)
    // ... applyNarrativeOverride ...
}
```

---

## Player Struct (key fields only) (`sharedModel/.../structs/Player.kt`)

```kotlin
data class Player(
    var name: String = "",
    var commanderType: CommanderType = CommanderType.Land,
    var trait: CommanderTrait = CommanderTrait.Balanced,
    var startingTile: Territory = Territory(),
    var victoryPoints: Int = 0,
    var militaryPoints: Int = 0,    // action pool — refilled to 100 at round start
    var diplomacyPoints: Int = 0,   // action pool — refilled to 100 at round start
    var researchPoints: Int = 0,    // action pool — refilled to 100 at round start
    var summitPoints: Int = 0,       // cooperative play pool
    var resources: MutableList<Resource> = mutableListOf(),
    var capturedTerritory: MutableList<Territory> = mutableListOf(),
    var capturedNemesis: MutableList<Npc> = mutableListOf(),
    var luckPoints: Int = 0,         // resist narrative override
    var reputation: Int = 0,        // 0-100; buffs diplo resource
    var might: Int = 0,             // 0-100; buffs military resource
    var wealth: Int = 0,            // 0-100; buffs research resource
    var militaryReadiness: Int = 70, // 0-100; decays, floor=30
    var legitimacy: Int = 70,        // 0-100; decays, floor=40
    var stagnation: Int = 0,         // 0-100; grows, cap=60
    var isSurrendered: Boolean = false,
    var delegateInstructions: String? = null,
)
```
