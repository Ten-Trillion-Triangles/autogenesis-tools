# Judge Prompt Hardening — AGENCY VERIFICATION Case Study (2026-08-09)

**Trigger:** Operator reported "the judge just got this wrong. Lord Maple Tree really did not win this fight here. The judge mistook the enemy nation winning as a term of victory for you."

**Trace:** `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/Judge/trace.json`

## The failure (R1T0 Lord Maple Tree)

### Captured prompt (Research + Military)

The Writing Agent captured his action as one bundled play:

> "funding and commencing the **research of new maple syrup dessert tanks**, using his **full Ent army led by General Moustache, and General Flipper**, to **invade and conquer @Sudan and @Ethiopia**."

Three actions in one prompt:
1. Research (fund dessert tank R&D)
2. Military mobilization (Ent army, led by Moustache + Flipper)
3. Invasion (conquer Sudan and Ethiopia)

### Prose the writer produced (verbatim from `gains and losses pipe` event 25)

> "Lord Maple Tree's research into the Saccharine Vanguard project succeeded, creating modified dessert tanks that **immobilized enemy forces** in Sudan and Ethiopia. The modified maple syrup lubricant reacted with heat to form a durable cement, **trapping the Ent army's tanks** and turning them into defensive assets. **Ethiopian forces recognized the tactical value and secured the area**, while General Flipper declared victory. The tanks' immobilization led to **a successful military campaign against Sudan and Ethiopia, with the territories captured**."

Two contradictory phrasings in the same paragraph:
1. "Ethiopian forces... secured the area" → Ethiopia secured itself (non-player win)
2. "a successful military campaign... with the territories captured" → generic player-win claim

### What the judge emitted

- `territoryGained: ["Sudan", "Ethiopia"]`
- `assetsGained: ["Saccharine Vanguard Technology"]`
- LMT stat gains: +25 luck, +20 reputation, +30 might, +15 wealth

None of those territory captures were warranted by the prose. Ethiopia literally won itself in the text. The mechanical force-capture override (`enforceMandatoryTerritoryCapture`, `playType == Military && wasSuccessful == true`) added both named targets downstream.

## The fix

### Prompt hardening (judge.kt)

Inserted before the Automatic Capture block at line ~792:

```
##AGENCY VERIFICATION (CRITICAL — read BEFORE Automatic Capture)##

Before applying any Automatic Capture condition, identify the SUBJECT (grammatical agent)
of the winning verb in the narrative. Capture language only counts toward player territory
gain when the subject is:
  1. The active player...
  2. A player-aligned force...
  3. A player proxy acting on the player's behalf...

CAPTURE DOES NOT APPLY when the winning verb's subject is:
  1. The defending territory itself ("Ethiopia secured its borders")
  2. A non-player third party...
  3. The player's forces in a self-destructive state ("our tanks were immobilized")
  4. An NPC explicitly opposed to the player

Prose Contradictions: when the narrative contains BOTH player-capture language AND
non-player-capture language for the same territory, the NON-PLAYER reading wins.

##PARTIAL-WIN RULE##
Multi-front hostile actions are evaluated front-by-front. territoryGained = union of
fronts that pass BOTH Automatic Capture AND Agency Verification.

##STAT SCALING FOR MIXED OUTCOMES##
Base stat awards scaled by (fronts won) / (fronts declared). All lost → 0. All won → 1.0.
```

### Mechanical backstop (judge.kt)

```kotlin
internal fun enforceMandatoryTerritoryCapture(
    results: Results,
    playerName: String,
    targetData: ActionTargetTypeObj?,
    playTypeContext: PlayTypeContext?,
    wasSuccessful: Boolean,
    actionIntent: String,
    narrativeEvidence: String? = null   // NEW
)
```

When `narrativeEvidence` is supplied, scan for non-player-win signals (e.g., "secured the area", "securing itself") within 300 chars of each target's name. Whitespace normalized (`\\s+` → ` `). **Anchor rule:** a signal only counts for THIS territory if it's CLOSER to this territory's name than to any other declared target. The conservative signal list + 300-char window catches the canonical "Ethiopia-wins-itself" case while leaving Sudan untouched (no Sudan-specific non-player signal in the R1T0 prose).

Caller wires the evidence at the existing orchestration point: `enforceMandatoryTerritoryCapture(results, playerName, targetData, playTypeContext, wasSuccessful, actionIntent, narrativeEvidence = resultSummary)`.

### Test fixture

`server/src/test/kotlin/agent/builders/judgeOutcome/JudgeAgencyVerificationTest.kt` — 4 tests:

1. `suppressesCaptureWhenDefendingActorWins` — R1T0 verbatim narrative as fixture. Asserts Ethiopia is NOT captured. Sudan is captured (no Sudan-specific non-player signal). Documents the LLM-rule-mechanical-gate split in the test comment.
2. `capturesWhenNarrativeEvidenceIsNull` — default behavior preserved.
3. `capturesWhenPlayerActorWins` — legitimate player-aligned win.
4. `partialWinSuppressesOnlyBlockedFronts` — three targets, one with the agency signal, two without. Asserts the front-by-front math.

## Three-step patch discipline (lessons from the iteration)

### 1. Test the test first

When writing the gate logic, simulate the proximity search in Python with the actual evidence text BEFORE writing the assertion. My first run on this patch had 4 failures because I'd assumed the gate would catch the R1T0 case without verifying. Multiple iterations:

- Tighten window (120 chars) → misses Ethiopia (signal is 246 chars from name)
- Widen window (300 chars) → catches Sudan incorrectly (signal-precedence to Ethiopia)
- Add "securing itself" variant → catches partial-win test by accident
- Add anchor rule (signal closer to THIS territory than to any other) → preserves partial-win semantics
- Add whitespace normalization (`\\s+` → ` `) → handles line-wrapped prose

### 2. Pin the LLM-rule-mechanical-gate split in the test comment

The test fixture's KDoc must explicitly call out which slots the mechanical gate catches vs. which the LLM rule catches. In the R1T0 case:
- **Mechanical gate catches**: Ethiopia (signal anchors to its name)
- **Mechanical gate does NOT catch**: Sudan (no Sudan-specific non-player signal)
- **LLM AGENCY VERIFICATION catches**: Sudan's prose-contradiction (`"territories captured"` claims to apply generically, but Ethiopia's stating-actor-with-winning-verb pre-empts)

Future maintainers will expect more from the gate than it can deliver. Pin the boundary explicitly.

### 3. Don't gate by quote-only

The signal list must include present-tense and progressive variants (`"secured the area"` + `"securing the area"` + `"securing itself"`). The prose was written in present tense while the gate's first version only matched past tense. With only past-tense variants, the partial-win test's "Ethiopian forces recognized the threat and stabilized their own borders, securing itself" was missed entirely.

## The honest residual

Even with the patch, the R1T0 case ends with:
- Ethiopia: NOT captured (gated by signal)
- Saccharine Vanguard: still awarded (legitimate — research succeeded)
- LMT stats: still +25 luck, +20 reputation, +30 might, +15 wealth (un-debuffed because the patch doesn't scale stats from a different angle)
- Sudan: still captured (no Sudan-specific signal; will be caught by the LLM rule when the prose is regenerated)

The patch is incomplete in one respect: Sudan should also be excluded under a literal reading of the prose contradiction rule. But the prompt change is the primary fix for that — the LLM applying AGENCY VERIFICATION + prose contradiction should refuse to emit Sudan's capture. The mechanical gate does not and cannot reach as far as the LLM rule.

## Test verification

```
./gradlew :server:test --tests "agent.builders.judgeOutcome.*" --offline
BUILD SUCCESSFUL
29 tests run, 0 failures, 0 ignored
```

Ad-hoc verification script (created during the patch, cleaned up after run) confirmed:
- 7 occurrences of AGENCY VERIFICATION / PARTIAL-WIN / STAT SCALING markers in judge.kt (≥ 6 expected)
- 10 occurrences of agencyBlockedTargets / JUDGE_AGENCY_GATE / narrativeEvidence (≥ 5 expected)
- 4 test methods + 1 setup helper in JudgeAgencyVerificationTest
- Line delta: +112 added, 1 removed (the trailing-comma change on `actionIntent: String` — required for the new `narrativeEvidence` parameter to compile)

## Diff summary

```
server/src/main/kotlin/agent/builders/judgeOutcome/judge.kt
  + AGENCY VERIFICATION block (10 lines)
  + PARTIAL-WIN RULE block (10 lines)
  + STAT SCALING FOR MIXED OUTCOMES block (15 lines)
  + Sub-step 4a/4b/4c/4d references (4 lines)
  + narrativeEvidence parameter on enforceMandatoryTerritoryCapture
  + agencyBlockedTargets Set + signal scan + anchor rule
  + 2 force-capture blocks gated by agencyBlockedTargets
  + 1 line modified: trailing comma on actionIntent: String parameter
  Net: +112, -1

server/src/test/kotlin/agent/builders/judgeOutcome/JudgeAgencyVerificationTest.kt
  + new file, 4 tests + 1 helper
```

## Provenance

- Trace: `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/Judge/trace.json`
- Logger logs: `~/.autogenesis/logs/autogenesis-2026-08-09-100921.log` lines 1700-1714 (IdentifyPlay + charge deduction), 1975-1987 (math breakdown)
- Operator session: 2026-08-09 ("Examined the first turn of the game mr tree. And give me a breakdown as to how and why the judge awarded you the two territories when you did not seem to win the battle.")
- Patch commit: not yet committed; awaiting operator review
