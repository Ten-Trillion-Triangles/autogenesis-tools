# WriterAgent Tax-Form Bug — Case Study (June 2026)

Symptom: WriterAgent was producing bureaucratic artifacts (tax forms, budget reports, statistical tables) instead of military combat prose. A player attacking a neighboring tile would get a casualty ledger in return, not a battle.

## Six Root Causes Identified

1. **"History textbook + newspaper article" framing** primed a paper-artifact register. LLMs pattern-match "dry, clinical, statistics, dates" to the most anodyne bureaucratic form available — government forms, tax records, census tables.

2. **Triple-negative combat rule** ("you should not constantly make the conflict non-violent and avoid decribing the battle") was unparseable. Triple-negatives confuse LLMs and they latch onto the "should not" pattern.

3. **actionIntent never reaches the writer.** The validator classifies actionIntent as Hostile/Friendly at phase 4, but `GuideData` schema (writerAgent.kt:65-71) does not include actionIntent. The writer is structurally blind to violence.

4. **Selection criteria bias toward diplomacy/absurdity.** No "visceral combat" criterion. 21st-century geopolitics at 30% pushes war into diplomatic framing. Kafka at 0% but procedure text describes Kafkaesque output.

5. **Author personality ("historian who catalogues")** reinforced the cataloguing register. Five-character beats primed paperwork.

6. **High temperature (1.0) + topP (.9) + always-apply rules** (portrait portals, totemic objects) pushed slipstream drift. The LLM treated "weird" as the dominant mode of "interesting."

## The Fix (Two Files)

### `sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt`

**defaultProcedureText** (lines 13-44 in original):
- Replaced "history textbook + newspaper article" with "GEOPOLITICAL REALITY (full spectrum)"
- Listed the actual gamut: warfare, diplomacy, espionage, internal politics, economics, civilian life, terrain, weather
- Added explicit anti-paperwork directive: "You do not summarize a battle as a budget report. You do not write a tax form when a soldier is dying in a ditch."
- Document-shaped details OK only when they advance reader understanding (casualty list yes, tax form no)
- Rewrote combat rule as positive-form directive: "WHEN THE PLAYER CHOSE VIOLENCE — you MUST depict the violence with grounded, visceral, concrete prose."
- Added RULE MECHANICS section explaining always-apply rules, rule categories, selection criteria, story weights
- Added CRITICAL DEFAULT paragraph: "If your footer contains no extra rule and no always-apply rule is relevant this turn, you are writing a normal turn of a geopolitical strategy game."

**defaultAuthorPersonality** (lines 49-56 in original):
- Removed "historian who catalogues" framing
- Replaced with "a puppeteer, not a clerk — you control the strings of reality by staging EVENTS, not by producing DOCUMENTS"
- Added concrete examples: "When a soldier dies in a ditch, you describe the ditch, the soldier, the moment. When a treaty is signed, you describe the room, the hands, the ink. When a tax revolt ignites, you show the faces, the streets, the fire. NOT the tax form. NOT the budget appendix. The EVENT."
- Kept the viral-propagation cosmic-horror persona intact

### `server/src/test/kotlin/agent/builders/writingAgent/AssembleWritingSystemPromptTest.kt`

Line 44: changed anchor from `"history textbook + newspaper"` to `"GEOPOLITICAL REALITY"`. Tests still pass because the no-triple-newline and no-stray-pipe-prefix assertions still hold.

## Verification Commands

```bash
# Compile and unit-test the change
./gradlew :server:test --tests "agent.builders.writingAgent.AssembleWritingSystemPromptTest"
./gradlew :sharedModel:jvmTest --tests "structs.WritingAgentDefaultsTest"

# Live-game verification (per user direction: "we'll just have to test it by running a live game")
# Start server, run a turn where player makes a military attack, inspect:
# - Does it describe attack, defense, casualties, terrain, weather, aftermath? (should be yes)
# - Does it default to a tax form / paper artifact? (should be no)
# - Does it slipstream into a portal/totemic without a fired rule? (should be no)
# - Does it use "It was not X, it was Y" reveals? (should be no, REVEALS rule forbids)
```

## Diff Stats

- 2 files changed
- defaultProcedureText: 11 lines -> ~108 lines
- defaultAuthorPersonality: 8 lines -> 6 lines (more concise)
- AssembleWritingSystemPromptTest.kt: 1 line changed
- Net: +121/-38 lines

## User Preferences Encoded in This Fix

- "very long system prompts are often required in this game, alas" — accepted the ~3x procedure text expansion
- "we'll just have to test it by running a live game" — no new unit tests for LLM output quality
- "we can't afford more LLM calls and input token ingress" — single-pass system prompt fix, no new agents/pipes
- "outright ban constant babbling on tax forms" — explicit anti-paperwork directive in both procedure and personality
- "Removing it's not X it's Y is really important or it'll be vomitted everywhere" — kept the REVEALS rule, made it explicit

## Not Fixed (Still On The Table)

- actionIntent not in GuideData schema (root cause #3) — would require schema change and pipe code update
- No "visceral combat" criterion in defaultSelectionCriteria (root cause #4)
- Writing pipe still runs at temperature 1.0 / topP .9 — no parameter change

These are deliberate deferrals per the cost-vs-quality constraint. Address only if the live-game verification shows the prompt fix is insufficient.