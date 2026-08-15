# WriterAgent Author Architecture — Case Study (June 2026)

This case study covers the second-generation WriterAgent prompt architecture: the separation of guide-pipe and writing-pipe author personalities, the migration path off Nordold Trable, and the cross-module shared helper pattern required to keep the JS-only MapEditor in sync with the JVM server.

## The Problem This Solves

The original WriterAgent (pre-June 2026) used a single `defaultAuthorPersonality` string ("Nordold Trable — viral propagation puppeteer") shared across:

- The guide pipe (chapterIdeas)
- The selection/distill pipe (bestChapterIdeas → decidedTurnOutcome)
- The writing pipe (the chapter prose)

This meant the same personality primed the planning phase AND the prose phase, which biased both toward the same slipstream register. Worse, every newly-created map inherited Nordold Trable as the default — there was no way to opt out without manually editing the prompt text inside the map pack.

## The New Architecture: Three Personalities, Three Pipes

### Core Guidance Operator (CGO) — guide + selection pipes

```
You are Core Guidance Operator (CGO). You are an AL (artificial lifeform)
agent designed to produce a concise and coherent plan for the next set
of events in the evolving gamestate/gameplay of Autogenesis, a
geopolitical strategy and war simulation game. ... Provide no more
than three array elems, each one describing one of the events that
will occur in the next turn of gameplay ... drive the story forward
to an endgame state, one where one player controls most or all of
the territory on the map ...
```

- Stored at: `Prompts.promptMap["cgo"]` (server) AND `AuthorPersonalities.CGO_PROMPT` (sharedModel)
- Used by: guide pipe, guide branch fail pipe, selection/distill pipe (all 3 look up `effectiveGuideAuthorPersonality` from `Prompts.promptMap["cgo"]`)
- Tone: cynical endgame-driver, absurd humor from real-world logic, ≤3 array elems hard cap
- Key principle: drives story forward to one-player-controls-all endgame state

### Core Story Agent (CSA) — writing pipe

```
You are Core Story Agent. You are an AL (artificial lifeform) agent
designed with the express purpose of writing the next chapter of
gameplay in the evolving gamestate/gameplay of Autogenesis, a
geopolitical strategy and war simulation game. ... Execute faithfully
on the plan provided by the guide pipe before you ... You despise
revelations ... You can't stand em dashes ... Include some ridiculous
gag no more than ONCE per chapter ... go absolutely ham on violence ...
```

- Stored at: `Prompts.promptMap["csa"]` (server) AND `AuthorPersonalities.CSA_PROMPT` (sharedModel)
- Used by: writing pipe (looks up `effectiveWritingAuthorPersonality` from `Prompts.promptMap["csa"]`)
- Tone: faithful executor of the guide plan, no reveals, no em dashes, exactly one gag per chapter
- Key principles: explicit bans on "it's not X, it's Y" reveals and em dashes (the user has strong opinions on both)

### Nordold Trable — fallback only, opt-in for devs

- Stored at: `Prompts.promptMap["ndt"]` (server) AND `AuthorPersonalities.NDT_PROMPT` (sharedModel)
- Used by: `effectiveAuthorPersonality` only as a fallback when the CGO/CSA lookups fail OR when a dev explicitly selects Trable in the MapEditor dropdown
- Tone: viral-propagation puppeteer, "stage EVENTS not DOCUMENTS"
- Status: dormant for new maps. A dev can pick Trable from the dropdown and it becomes the fallback for CGO/CSA (i.e., only fires if CGO/CSA are missing from promptMap).

## The Four-Layer Storage Model

The writer agent's author personality resolves through a four-layer chain. Every layer has a distinct purpose.

```
Layer 1: Prompts.promptMap (server)
  - Mutable map keyed by "csa" / "cgo" / "ndt" / 28+ AI player descriptors
  - Source of truth at runtime — the writerAgent.kt reads from HERE
  - Lives in: server/src/main/kotlin/agent/prompts/prompts.kt

Layer 2: AuthorPersonalities (sharedModel)  ← NEW
  - Read-only object holding the 3 author personalities + dropdown entries
  - Used by MapEditor (JS-only) to populate authorPersonality on dropdown change
  - Lives in: sharedModel/src/commonMain/kotlin/structs/AuthorPersonalities.kt
  - Mirrors the 3 entries in Prompts.promptMap (manual duplication, ~4KB each)

Layer 3: WritingAgentDefaults (sharedModel)
  - defaultAuthorPersonality (now empty string)
  - The fallback for CGO/CSA lookups — empty by default so CGO/CSA always take precedence
  - Lives in: sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt

Layer 4: WritingAgentConfig.authorPersonality (per-map)
  - String stored inside each map pack's writingAgentConfig
  - Empty string = "use CGO/CSA via promptMap lookups"
  - Non-empty = "use this text as fallback for CGO/CSA"
  - Loaded at: WorldManager.loadMapFromPack → writerAgent builds with this config
```

Resolution chain at runtime (writerAgent.kt:153-169):

```kotlin
val effectiveAuthorPersonality =
    if (config.authorEnabled && config.authorPersonality.isNotEmpty())
        config.authorPersonality            // Layer 4 override
    else
        ""                                  // Layer 3 (empty by default — was Trable puppeteer)

val effectiveGuideAuthorPersonality =
    Prompts.promptMap["cgo"] ?: effectiveAuthorPersonality   // Layer 1 → 4

val effectiveWritingAuthorPersonality =
    Prompts.promptMap["csa"] ?: effectiveAuthorPersonality   // Layer 1 → 4
```

For a default map (Layer 4 empty): guide pipe uses CGO from Layer 1, writing pipe uses CSA from Layer 1. Trable is dormant.

For a map where a dev picked Trable in the MapEditor dropdown: Layer 4 holds the Trable text. The chain becomes: CGO prompt OR Trable fallback for guide pipe, CSA prompt OR Trable fallback for writing pipe. CGO/CSA still take precedence. Trable only fires if CGO/CSA are removed from promptMap.

## The Cross-Module Shared Helper Pattern (CRITICAL)

The mapEditor module is JS-only KVision. The server module is JVM Kotlin. The mapEditor cannot import `agent.prompts.Prompts` because that lives in the server module (which mapEditor does not depend on).

The original naive solution was: the MapEditor hardcoded the dropdown options, and selecting one did NOTHING (the dropdown was decorative). Selecting "Nordold Trable" displayed Trable in the dropdown but did not populate `config.authorPersonality`. The map pack was saved with whatever text the dialog happened to have, which was usually the Trable puppeteer from `defaultAuthorPersonality`.

The fix introduced `AuthorPersonalities` in sharedModel (which both mapEditor AND server depend on):

```kotlin
// sharedModel/src/commonMain/kotlin/structs/AuthorPersonalities.kt
object AuthorPersonalities {
    val dropdownEntries: List<Pair<String, String>> = listOf(
        "Core Story Agent (CSA)" to "csa",
        "Core Guidance Operator (CGO)" to "cgo",
        "Nordold Trable" to "ndt"
    )

    fun promptForKey(key: String): String? = when (key) {
        "csa" -> CSA_PROMPT
        "cgo" -> CGO_PROMPT
        "ndt" -> NDT_PROMPT
        else -> null
    }

    private val CSA_PROMPT: String = """..."""
    private val CGO_PROMPT: String = """..."""
    private val NDT_PROMPT: String = """..."""
}
```

The mapEditor can now:
1. Use `AuthorPersonalities.dropdownEntries.map { it.first }` to build the dropdown
2. On dropdown change, call `AuthorPersonalities.promptForKey(key)` and populate `config.authorPersonality`
3. None of this requires importing server code

This is the correct pattern for sharing data between the JS-only mapEditor and the JVM server: put it in sharedModel.

## The MapEditor Dropdown Wiring

Before this fix: selecting an author in the MapEditor dropdown set only a display-name string that was dropped on save. The map pack ended up with whatever text was in `config.authorPersonality` (which was usually the Trable puppeteer from the default config).

After this fix: the dropdown onChange handler in `WritingSettingsDialog.kt` translates the selected display name to a promptMap key and populates the actual prompt text:

```kotlin
onChange {
    val selected = this.value ?: ""
    author = selected
    val promptKey = authorToPromptKey[selected]
    if (promptKey != null) {
        val promptText = AuthorPersonalities.promptForKey(promptKey) ?: ""
        config = config.copy(authorPersonality = promptText)
    }
    clearError()
}
```

Where `authorToPromptKey` is built from `AuthorPersonalities.dropdownEntries.toMap()`. Selecting any of the 3 valid entries (CSA, CGO, NDT) populates the prompt text. The other 27 decorative entries in the dropdown (zuzusarogorata, haematemesis, etc.) still do nothing on selection — they are pre-existing leftovers from earlier experiments; cleaning them up is out of scope.

## Migrating Existing Map Packs Off Trable

The 5 bundled map packs in `server/src/main/resources/maps/` (jupiter, Laurasiagondwana, fixedUSamerica, IO-map, San_Martello) had Nordold Trable's puppeteer text (~1800 chars) baked into their `mapData.writingAgentConfig.authorPersonality` field. The migration sets that field to empty string and clears `mapData.author` to empty string. Pins, connections, worldName, storyScenario, territories, npc, activePlayers are UNTOUCHED.

Python script (run from repo root):

```python
import json, zipfile, os

def migrate(path):
    tmp = path + ".tmp"
    with zipfile.ZipFile(path, "r") as zin:
        map_json = zin.read("map.json").decode("utf-8")
        data = json.loads(map_json)
        other_entries = [n for n in zin.namelist() if n != "map.json"]
        other_payloads = {n: zin.read(n) for n in other_entries}

    data["mapData"]["author"] = ""
    data["mapData"]["writingAgentConfig"]["authorPersonality"] = ""

    new_json = json.dumps(data, separators=(",", ":"))

    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("map.json", new_json)
        for name, payload in other_payloads.items():
            zout.writestr(name, payload)

    os.replace(tmp, path)

for f in ["jupiter.map", "Laurasiagondwana.map", "fixedUSamerica.map",
          "IO-map.map", "San_Martello.map"]:
    migrate(f"server/src/main/resources/maps/{f}")
```

Verification script (single pass over all 5):

```python
import zipfile, json, os
for fname in sorted(os.listdir("server/src/main/resources/maps")):
    if not fname.endswith(".map"): continue
    with zipfile.ZipFile(f"server/src/main/resources/maps/{fname}") as z:
        data = json.loads(z.read("map.json").decode("utf-8"))
    md = data["mapData"]
    assert md.get("author") == "", f"{fname}: author not cleared"
    assert len(md["writingAgentConfig"].get("authorPersonality", "")) == 0, \
        f"{fname}: authorPersonality not cleared"
    print(f"OK  {fname}  pins={len(md['pins'])}  conns={len(md['connections'])}")
```

## Test Pattern: Statistical Assertions for Global Random

`rollCriteriaAvailability` in `writerAgent.kt` uses `kotlin.random.Random.nextInt(0, 101)` — the global Random instance, which cannot be seeded from tests. Naive test patterns that assert "every trial produces X" flake ~1-40% of the time depending on the pass rate.

The fix is statistical assertions over many trials with explicit bounds:

```kotlin
@Test
fun multipleCriteriaReturnsPassingOnes() {
    // 100% + 50% criteria. Expected over 200 trials:
    // - Both pass: ~99 (49.5%)
    // - Only 100% passes: ~100 (50%)
    // - Only 50% passes: ~1 (0.5%)
    // - Neither (empty): ~1 (0.5%)
    val criteria = listOf(
        InjectableCriterion(id = 1, description = "Hundred", category = "test", chancePercent = 100),
        InjectableCriterion(id = 2, description = "Fifty", category = "test", chancePercent = 50)
    )

    var bothPassed = 0
    var onlyFirstPassed = 0
    var empty = 0
    repeat(200) {
        val result = rollCriteriaAvailability(criteria)
        when {
            result.size == 2 -> bothPassed++
            result.size == 1 && result[0].id == 1 -> onlyFirstPassed++
            result.isEmpty() -> empty++
        }
    }

    // Both pass should be common (49% expected)
    assertTrue(bothPassed >= 70, "bothPassed should be common")
    // Only-first should also be common (50% expected)
    assertTrue(onlyFirstPassed >= 70, "onlyFirstPassed should be common")
    // Empty should be RARE (0.5% expected)
    assertTrue(empty < 10, "empty should be rare")
}
```

Key rules for these tests:

- Use 100+ trials for tight bounds (3σ coverage)
- Count branches explicitly and assert bounds
- Total across branches must equal trial count
- Avoid asserting on rare branches (loose upper bound or skip)
- Document expected probabilities in comments

This pattern applies to ANY test of code that uses `kotlin.random.Random.nextInt()` or `Random.nextDouble()` without a seedable parameter.

## The Diff Stats From The Full Migration

- 8 files modified, 1 file created (AuthorPersonalities.kt)
- 4 test files updated (statistical assertions + id 11 in criteria roundtrip)
- 5 map packs migrated (binary, content preserved)
- Total: 198 insertions, 94 deletions in tracked Kotlin code
- Plus the 3 new promptMap entries ("csa", "cgo", "ndt" — earlier turns)

## User Preferences Encoded In This Architecture

- "A developer can set him in the map editor if they really want him" — Trable stays in the dropdown, dormant for new maps but reachable for devs who opt in
- "Removing it's not X it's Y is really important" — CSA explicitly bans the fake-out reveal pattern in its prompt
- "I can't stand em dashes" — CSA explicitly bans em dashes in its prompt
- The "no more than three array elems" cap — CGO's principle #1, the hard limit on chapterIdeas, possibleTurnOutcomes, actionsTakenByCharactersInChapter
- "drive the story forward to an endgame state" — both CGO and CSA include endgame-driver language; CGO is the primary enforcer, CSA is faithful to whatever the guide produces

## Related Files

- `sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt` — defaultAuthorPersonality (empty by default), defaultProcedureText, defaultSelectionCriteria, defaultRuleCategories, defaultAlwaysApplyRules
- `sharedModel/src/commonMain/kotlin/structs/AuthorPersonalities.kt` — the 3 author personalities + dropdown helper (NEW)
- `sharedModel/src/commonMain/kotlin/structs/MapPack.kt` — MapData schema (author field, writingAgentConfig.authorPersonality)
- `server/src/main/kotlin/agent/prompts/prompts.kt` — Prompts.promptMap (the runtime source of truth)
- `server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt` — effectiveAuthorPersonality / effectiveGuideAuthorPersonality / effectiveWritingAuthorPersonality chain
- `mapEditor/src/jsMain/kotlin/ui/WritingSettingsDialog.kt` — MapEditor dropdown wiring
- `server/src/main/kotlin/gameState/WorldManager.kt` — loadMapFromPack at line 1868 sets activeWritingAgentConfig from the pack
- `server/src/main/resources/maps/*.map` — the 5 bundled map packs

## Known Gaps (Deferred)

- The kvisionApp `systemCharacters` autocomplete list in `CommandBox.kt:216-222` is NOT updated. It serves a different purpose (AI player @mention autocomplete, not author personalities) and was out of scope.
- The 27 non-CSA/CGO/NDT entries in the MapEditor authorCharacters dropdown remain decorative (selecting them does nothing). Cleaning them up is out of scope.
- The guide pipe's system prompt in writerAgent.kt:195-200 still says "dungeon master/fiction writing system." The CGO reasoning pipe overrides this in practice, but the outer framing could be cleaned up.
- The guide pipe's `actionIntent` field is still NOT in `GuideData` schema. The writer infers violence from prose alone. This is the same gap noted in the prose drift case study.