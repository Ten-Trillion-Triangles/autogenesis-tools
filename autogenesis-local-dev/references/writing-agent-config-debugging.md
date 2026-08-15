# Debugging the WritingAgentConfig Flow

When the writing agent's settings (rule categories, selection criteria, story weights, selection strategy) don't behave as configured — geopolitics=100 doesn't surface enough, horror=0 still appears, a selection strategy is ignored — the bug is in the **map pack round-trip** or the **server-side effective config** computation. This reference walks the full data flow from the browser dialog to the prompt the model sees, with the exact code points to inspect and the verification commands that prove the values reached the server intact.

## Trace Locations

| Trace | Path Pattern |
|-------|-------------|
| Narrative writing (Nordold Trable) | `~/.tpipe/debug/trace/{TurnFolder}/NeoWritingAgent/trace.html` |
| AI player takeover | `~/.tpipe/debug/trace/{TurnFolder}/WritingAgents/trace.html` |

**Common mistake**: `WritingAgents/` contains AI player takeover subagents (named "Play Detection Agent", "explicit cot"), NOT the writing agent. Always use `NeoWritingAgent/` for narrative pipeline traces.

## WritingAgentConfig Data Flow

```
WritingSettingsDialog.buildConfigFromUI()
    ↓ (WritingAgentConfig with spinner-derived values)
MapCanvas.getMapData() → MapData.writingAgentConfig
    ↓ (serialized into .map pack via MapPackManager.pack)
MapPackManager.unpack() → MapData.writingAgentConfig
    ↓ (loaded by server)
WorldManager.activeWritingAgentConfig = unpacked.mapData.writingAgentConfig
    ↓ (injected into pipeline)
buildNeoWritingAgent(player, config) → effectiveRuleCategories, effectiveSelectionCriteria
    ↓ (used in pipeline)
rollCriteriaAvailability() → eligible criteria passed to Nordold's prompt
```

## Key Server-Side Code Points

### writerAgent.kt — effective config computation (~line 212-220)
```kotlin
val effectiveRuleCategories = if(config.ruleCategories.isNotEmpty()) config.ruleCategories else defaultRuleCategories()
val effectiveSelectionCriteria = if(config.selectionCriteria.isNotEmpty()) config.selectionCriteria else defaultSelectionCriteria()
```

### writerAgent.kt — criteria availability roll (~line 859-863)
```kotlin
fun rollCriteriaAvailability(criteria: List<InjectableCriterion>): List<InjectableCriterion> {
    return criteria.filter { kotlin.random.Random.nextInt(0, 101) < it.chancePercent }
}
```

### writerAgent.kt — selection strategy (~line 890-932)
```kotlin
private fun buildStepTwoInstructions(promptSeed: String?, strategy: WriterSelectionStrategy, criteria: List<InjectableCriterion>): String {
    val eligibleCriteria = rollCriteriaAvailability(criteria)
    // RANDOM sub-selects from: GEOPOLITICS_ONLY, RANDOM_UP_TO_FIVE, WEIGHTED, ORIGINAL
    // Result is logged: Logger.debug(LogCategory.LLM, "Selecting writing criteria: $selectedCriteria")
}
```

## Server Log Evidence

The server log at `~/.autogenesis/logs/autogenesis-YYYY-MM-DD-HHMMSS.log` contains:
```
[DEBUG] [LLM]: Selecting writing criteria: [InjectableCriterion(id=4, description=21st century type geopolitics., category=geopolitics, chancePercent=100), ...]
[DEBUG] [LLM]: Selecting writing strategy: WriterSelectionStrategy.RANDOM
```

**NOTE**: The log shows the ALREADY-ROLLED eligible criteria (after `rollCriteriaAvailability` filters by `chancePercent`), NOT the original `chancePercent` values from the config. You cannot verify spinner values reached the server from the log alone.

## Browser Log Evidence

```
[TOPBAR] exportMapPack: mapData.writingAgentConfig.ruleCategories.size=5
[TOPBAR] exportMapPack: mapData.ruleCategory[0] 'absurdity': chancePercent=1, rules=8
[TOPBAR] exportMapPack: mapData.ruleCategory[1] 'time_reality': chancePercent=8, rules=3
[TOPBAR] exportMapPack: mapData.ruleCategory[2] 'horror': chancePercent=7, rules=4
[TOPBAR] exportMapPack: mapData.ruleCategory[3] 'geopolitics': chancePercent=10, rules=4
[TOPBAR] exportMapPack: mapData.ruleCategory[4] 'general': chancePercent=5, rules=3
```

**NOTE**: These prove correct values at export time. They do NOT prove values survived server-side deserialization.

## Verification Methodology

1. Set `geopolitics=100` and `horror=0` on all criteria in Writing Settings dialog
2. Export the .map file
3. Restart the game server fresh
4. Load the .map file in the game
5. Trigger a single turn
6. Check `~/.tpipe/debug/trace/{TurnFolder}/NeoWritingAgent/trace.html`
7. Grep: "geopolitic" should appear many times, "horror" should NOT appear

```bash
grep -c "geopolitic" ~/.tpipe/debug/trace/{TurnFolder}/NeoWritingAgent/trace.html
grep -c "horror" ~/.tpipe/debug/trace/{TurnFolder}/NeoWritingAgent/trace.html
```

## Default Values (CANONICAL — `WritingAgentDefaults.kt`)

**The canonical source of truth is now a single file (added 2026-06-19, commit 0d0dc45d2 "adjust defaults for writer"):**
```
sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt
```

It exports `defaultRuleCategories()`, `defaultSelectionCriteria()`, `defaultWritingAgentConfig()`, `defaultAuthorPersonality`, `defaultAlwaysApplyRules`, and `defaultProcedureText`. Both the server (`writerAgent.kt`) and the mapEditor (`WritingSettingsDialog.kt`) consume this file — no more duplicated defaults across modules. **If you need to verify or change a default, edit this file, not the call sites.**

```kotlin
// defaultRuleCategories chancePercent (WritingAgentDefaults.kt:64-117)
absurdity    = 10%   (8 rules)
time_reality =  8%   (3 rules)
horror       =  7%   (4 rules)
geopolitics  = 10%   (4 rules)
general      =  5%   (3 rules)

// defaultSelectionCriteria chancePercent (WritingAgentDefaults.kt:128-139)
// Stable ids 1..10 — referenced by selection strategies, must NOT be reordered
id= 1  Kafka-esque bureaucracy      general      chance= 0%   // disabled
id= 2  Keillor-esque absurdity      absurdity    chance= 5%
id= 3  Pitigrilli-esque cynicism    general      chance=10%
id= 4  21st century geopolitics     geopolitics  chance=30%   // dominant
id= 5  Wallesian plot structuring   general      chance= 5%
id= 6  Joycean referencing          general      chance= 5%
id= 7  Rabellesian humour           absurdity    chance=10%
id= 8  Dreamlike logic              time_reality chance= 5%
id= 9  Kubrickian horror            horror       chance= 5%
id=10  Really dumb                  absurdity    chance= 5%

// Other defaults
storyWeights = (geopolitics=25, absurdity=25, dreamlikeQualities=25, unexpectedTwists=25)
selectionStrategy = WriterSelectionStrategy.RANDOM
authorEnabled / alwaysApplyRulesEnabled / guardrailsEnabled = true
alwaysApplyRules = 7 entries (phone-windows, photo-portals, magic-on-demand, resurrect, etc.)
authorPersonality = "Nordold Trable" viral-propagation historian (1800 chars)
procedure = history-textbook + newspaper-article block
```

**Approximate per-turn category-fire probability** (each rolls independently):
`P(any fires) ≈ 1 − (0.9)(0.92)(0.93)(0.9)(0.95) ≈ 35.7%`

**When the defaults change, existing shipped map packs become stale.** See `references/map-pack-update-pattern.md` for the safe in-place procedure to apply the new defaults to all 5 packaged maps without disturbing the PNG, pins, or other mapData fields.

## Missing Debug Logging

The server should log the effective config at pipeline build time. Add this to `writerAgent.kt` around line 220:
```kotlin
Logger.debug(LogCategory.LLM, "WriterAgent effective config: ruleCategories=${effectiveRuleCategories.map { "${it.name}=${it.chancePercent}" }}, selectionCriteria=${effectiveSelectionCriteria.map { "${it.id}=${it.chancePercent}" }}, weights=${effectiveWeights}")
```

## Related Skills

- `tpipe-trace-parser` — for parsing TPipe trace files (HTML/JSON/MARKDOWN/CONSOLE)
- `log-parser` — for parsing JVM/browser logs in this workspace
