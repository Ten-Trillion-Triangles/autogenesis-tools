---
name: autogenesis-prompt-debugging
description: "Debug and improve the LLM prompt layer of Autogenesis game agents (WriterAgent, validator, judge, NPC agents). When the writer produces prose drift (tax forms, bureaucratic artifacts, fake-out reveals, no combat), when an agent hallucinates entities, when selection criteria bias toward the wrong tone, when author personality primes the wrong register, or when the writer fails to honor the rolled-rule system — start here. Covers the canonical prompt files in sharedModel/src/commonMain/kotlin/structs/, how actionIntent flows (or does not) from the validator to the writer, the guide->selection->writing pipeline, and the cost-vs-quality tradeoff that constrains fixes to single-pass system-prompt edits rather than additional agents."
metadata:
  hermes:
    tags: [autogenesis, prompt-engineering, llm, writer-agent, debugging, game-agent]
    related_skills: [autogenesis-local-dev, tpipe-pipeline-patterns, tpipe-reasoning-pipes, systematic-debugging]
---

# Autogenesis Agent Prompt Debugging

The Autogenesis game has ~30 LLM-driven agents across 12 builder directories. Their **PROMPT LAYER** (procedure text, author personality, selection criteria, always-apply rules) lives in `sharedModel/src/commonMain/kotlin/structs/`. Their **PIPE CODE** (BedrockMultimodalPipe configuration, validator/transformer functions) lives in `server/src/main/kotlin/agent/builders/`. When an agent misbehaves, the prompt layer is almost always the first place to look — the pipe code is mature and rarely wrong.

## Trigger Conditions

Load this skill when any of these appear in user reports or pipeline traces:

- Writer output is bureaucratic artifacts (tax forms, budget reports, statistical tables) instead of events
- Writer avoids depicting violence despite a military action intent
- Writer overuses "It was not X, it was Y" fake-out reveals
- Writer hallucinates entities (places, factions, characters) not in game state
- Writer fails to honor the rolled-rule system (always-apply rules, rule categories)
- Writer drift in tone away from the selected criteria
- Writer output is suspiciously short or long for the configured token budget
- Any agent (validator, judge, NPC, gathering-context) misfires and the pipe logs do not show a clear error

**Trace-driven patterns:** see `references/autogenesis-gemma-mantle-pipes.md` for the failure shapes produced when Mantle reasoning pipes bypass `ReasoningBuilder.assignDefaults` (Pipe.kt:8033 NPE → 3-attempt retry cluster → empty `{}` from `Play Detection Agent` → Mantle validator permissive-approves empty-`to` territory exchanges → orchestrator strips territory from the loser with no winner). Detection recipes for each step are listed there.

## The Diagnostic Pattern

### 1. Locate the agent and its prompt sources

For each agent, prompts come from two layers:

- **Agent builder file**: `server/src/main/kotlin/agent/builders/<agent>/<Agent>.kt` — pipe code, systemPrompt / middlePrompt / footerPrompt construction, assembler function
- **Defaults file**: `sharedModel/src/commonMain/kotlin/structs/<Defaults>.kt` — default strings (defaultProcedureText, defaultAuthorPersonality, defaultSelectionCriteria, defaultRuleCategories, defaultAlwaysApplyRules)

The agent's `buildNeo<Agent>()` function takes a `WritingAgentConfig` (or per-agent equivalent) which carries the prompt values. If config fields are empty, defaults are used. Map editor can also supply custom values via `WorldManager.activeWritingAgentConfig`.

### 2. Diagnose register priming in the procedure

`defaultProcedureText` is the **biggest lever** — it sets the prose register. Common wrong registers and their symptoms:

| Procedure framing | LLMs drift toward |
|---|---|
| "history textbook + newspaper article" | Tax forms, statistical tables, bureaucratic paper artifacts |
| "narrative fiction" with no concrete gamut listed | Generic safe third-person, refusal-flavored prose |
| Triple-negatives ("you should not constantly make non-violent") | Latches onto the negatives, produces the forbidden thing |
| Long "do not" lists without "do" lists | Latches onto forbidden behaviors |

Fix pattern: replace abstract framing with a **concrete list** of what TO produce. The WriterAgent's fix listed warfare, diplomacy, espionage, internal politics, economics, civilian life, terrain — the full spectrum. The procedure has to teach the LLM what an event looks like in this game.

### 3. Diagnose author voice

`defaultAuthorPersonality` is the second lever. Common wrong voices:

- "historian who catalogues" — primes cataloguing, list-making, paperwork
- "narrator" with no specifics — defaults to safe third-person
- Long tone descriptions without explicit "render as events, not documents" — drifts to whatever artifact shape the procedure primed

Fix: explicit positive-form directive. "Stage EVENTS, not DOCUMENTS. When a soldier dies, describe the ditch."

### 4. Trace actionIntent flow

If the agent is supposed to react to action type (Hostile / Friendly / Research / Diplomatic) but is not:

1. Find where `ActionIntent` is set — typically the validator or target detector
2. Trace whether the writer pipeline receives it
3. If absent, the writer is structurally blind to violence/peace based on prose alone

The WriterAgent's `GuideData` schema does **not** include `actionIntent`. The writer decides whether the action is violent by reading the player prose — and if the player wrote something ambiguous like "I position my forces" instead of "I attack," the writer defaults to bureaucratic framing.

### 5. Check selection criteria bias

`defaultSelectionCriteria` lists available criteria (Kafka, Keillor, Pitigrilli, geopolitics, Wallesian, Joycean, Rabellesian, dreamlike, Kubrickian, really-dumb) with per-criterion `chancePercent`. Common wrong tuning:

- All weights low except one -> LLM picks one mood, ignores others
- No "visceral combat" or "war correspondent" criterion -> combat gets reframed as diplomatic or dreamlike
- Kafka at 0% but the procedure text describes Kafkaesque output -> procedure/criterion conflict

The criterion id ordering is canonical and referenced by `WriterSelectionStrategy.GEOPOLITICS_ONLY` (id 4) and `WEIGHTED` (ids 4, 7, 10). Reordering ids will break those strategies.

### 6. Check rule system interaction

- Always-apply rules (defaultAlwaysApplyRules) — physical laws of the universe, ALWAYS in effect
- Rule categories (defaultRuleCategories) — RARE dice-roll events with per-category chancePercent

Most turns NO rule fires. If the LLM is self-injecting absurd events on every turn, it does not understand the rule system.

Add a "RULE MECHANICS" section to the procedure explaining the difference:

- Always-apply rules are physics, not flavor
- Rule categories are dice rolls, not defaults
- Selection criteria are mood, not content
- If no rule fires this turn, write a normal geopolitical turn

## Cost-vs-Quality Constraint (CRITICAL)

The user has stated: **"we cannot afford more LLM calls and input token ingress the way TPipeWriter solves this with extra agents."**

Implication: prefer single-pass system-prompt fixes over multi-agent solutions. The WriterAgent is already a 3-pipe pipeline (guide -> selection -> writing). Adding more agents means more LLM calls, more tokens, more cost.

This means:

- **Long system prompts ARE expected in this game.** The user has confirmed: "very long system prompts are often required in this game, alas." Do not pare the procedure text down for brevity.
- **Test by running a live game, not by adding more unit tests.** The user has confirmed: "we will just have to test it by running a live game." Unit tests on the prompt assembly are useful for catching assembly bugs (the AssembleWritingSystemPromptTest pattern) but they cannot validate LLM output quality.
- **Prefer text-only fixes.** Adding JSON schemas, new branches, retry logic, or new pipes is the LAST resort. Try the system prompt first.

## The "No Gotcha Reveals" Rule

The user has a strong preference against "It is not X, it is Y" fake-out reveals. This pattern appears in LLM prose even when not instructed, especially with high temperature / topP settings. The defense is an explicit REVEALS rule in the procedure text:

> Do not use the "It was not X, it was Y" fake-out reveal pattern. No last-page twists where the apparent meaning is flipped. If a real plot payoff requires revelation, write it as direct statement at the moment it happens. This is a ban on the cheap gotcha, not a ban on plot.

Do not remove this rule. It is the user's main defense and removing it makes the problem worse, not better.

## Test Patterns That Apply

The assembly test `AssembleWritingSystemPromptTest.kt` verifies the assembled systemPrompt structure. When changing `defaultProcedureText`:

- Update the anchor assertion (currently `result.contains("GEOPOLITICAL REALITY")`) to match the new framing
- The "no triple-newline" assertion (`result.contains("\n\n\n")` must be false) still applies — every line must be terminated with a single newline
- The "no stray pipe prefix" assertion (no line in the procedure block starts with `| `) still applies — use leading spaces or none, never `|`-prefixed trimMargin lines in the procedure block
- The defaults test in `WritingAgentDefaultsTest.kt` only checks for `###PROCEDURE:` and `###OVERALL:` markers — those must remain

## When NOT to Patch the Prompt Layer

- LLM is refusing output -> check the anti-censorship block in `server/src/main/kotlin/globals/BedrockConfig.kt` first (line 89-97 has the standard block)
- LLM is timing out -> check pipe timeout config; the standard is 3 minutes / 5 retries via `enablePipeTimeout`
- LLM is returning malformed JSON -> check the json schema, not the prompt text
- Pipe is throwing exceptions -> check the validator/transformer functions, not the prompt
- Agent is receiving unexpected context data (e.g. audio track lists, full World JSON) -> this is a **context-injection audit** problem, not a prompt-text problem. See `autogenesis-trace-analysis` skill, `references/audio-tracks-leak.md`. The fix is `@Transient` on the field in `World.kt` or selective field access in the agent builder, not a prompt edit.

## Judge Prompt Hardening — AGENCY VERIFICATION + PARTIAL-WIN RULE (2026-08-09)

The `judge.kt` gains/losses pipe extracts `territoryGained` from a prose summary. A chronic failure mode is the pipe **matching capture language without verifying the actor** of the winning verb. When the prose says "Ethiopian forces secured the area" (Ethiopia secured itself) in the same paragraph as "the territories captured" (generic player-win claim), the LLM emits `territoryGained: [Sudan, Ethiopia]` and the mechanical force-capture override downstream double-credits the contradiction.

**R1T0 trace trigger (2026-08-09):** Lord Maple Tree's Research play + Ent Army invasion produced prose that contradicted itself in the same paragraph. The judge awarded both Sudan and Ethiopia as captured. The mechanical `enforceMandatoryTerritoryCapture` force-captured both because `playType=Military && wasSuccessful=true`. The canonical fail signature: `LLM emits territoryGained=NAMED_TARGETS BUT the prose's winning-verb agent is the defending territory itself or a non-player force`.

The hardened judge prompt (`server/src/main/kotlin/agent/builders/judgeOutcome/judge.kt`, insertion before the existing Automatic Capture block at line ~792) adds:

- **AGENCY VERIFICATION block** — verbatim rule that capture language only counts when the grammatical agent of the winning verb is the player, a player-aligned force, or a player proxy. Capture DOES NOT APPLY when the agent is the defending territory itself, a non-player third party, the player's forces in a self-destructive state, or an NPC opposed to the player.
- **Prose Contradiction rule** — when the narrative contains BOTH player-capture language AND non-player-capture language for the same territory, the NON-PLAYER reading wins. Territory does NOT enter `territoryGained`. Document the contradiction in `resultSummary`.
- **PARTIAL-WIN RULE** — multi-front hostile actions are evaluated front-by-front. `territoryGained` is the union of fronts that pass BOTH Automatic Capture AND Agency Verification. A turn with mixed outcomes is still a SUCCESS — but `territoryGained` contains only the won fronts. Lost fronts get `territoryStatChanges` reflecting what actually happened on that front.
- **STAT SCALING FOR MIXED OUTCOMES** — when PARTIAL-WIN produces a partial win, base stat awards are scaled by `(fronts won) / (fronts declared)`. If all fronts are lost, stat awards = 0. If all fronts are won, scaling factor = 1.0 (no change).

The matching mechanical backstop is in `enforceMandatoryTerritoryCapture` (judge.kt line ~2338):
- New optional parameter `narrativeEvidence: String? = null` — preserves existing call sites (default null = no check).
- When evidence is supplied, scan for non-player-win signals (`"secured the area"`, `"secured its borders"`, `"secured itself"`, `"securing the area"`, `"securing its borders"`, `"securing itself"`, `"won the battle"`, `"took the capital"`, `"enemy secured"`, `"defending forces secured"`, `"rival secured"`) within a 300-character window of each named target's first occurrence.
- **Anchor rule:** a signal only counts for THIS territory if it's CLOSER to this territory's name than to any other declared target. Prevents a signal referring to Territory A from incorrectly blocking Territory B.
- Whitespace normalization (collapse `\s+` to single space) so signals like `"securing itself"` match even when the prose wraps mid-phrase across lines.
- The block is conservative — only suppresses capture when the narrative explicitly credits a non-player actor. Vague phrasing falls through to the existing capture path.

**Test fixture:** `server/src/test/kotlin/agent/builders/judgeOutcome/JudgeAgencyVerificationTest.kt` pins 4 cases against the R1T0 narrative verbatim. 29/29 tests pass in `:server:test --tests "agent.builders.judgeOutcome.*"`.

**Honest scope of the mechanical gate:** the gate catches **Ethiopia** (signal anchors to it) but does NOT catch Sudan in the R1T0 prose, because Sudan has no Sudan-specific non-player signal. The Sudan case is the LLM-level AGENCY VERIFICATION prompt rule's responsibility, not the mechanical backstop. The gate is a safety net, not a silver bullet — the prompt change is the primary fix.

**Three-step patch discipline for any future Judge prompt tightening:**
1. **Test the test first.** When writing the fixture, simulate the gate logic in Python with the actual evidence text before writing the assertion. My first run on this patch had 4 failures because I'd assumed the gate's signal-vs-name proximity window would catch the R1T0 case without verifying it. Multiple iterations of:
   - Tighten window → misses Ethiopia
   - Widen window → catches Sudan incorrectly
   - Add "securing itself" variant → catches partial-win test by accident
   - Add anchor rule (signal closer to this territory than to any other) → preserves partial-win semantics
   - Add whitespace normalization → handles line-wrapped prose
2. **Pin the LLM-rule-mechanical-gate split in the test comment.** The test fixture's KDoc must explicitly call out which slots the mechanical gate catches vs. which the LLM rule catches, so future maintainers don't expect more from the gate than it can deliver.
3. **Don't gate by quote-only.** The signal list must include present-tense and progressive variants (`"secured"` + `"securing"`) because the prose was written in present tense while the gate's first version only matched past tense.

**Trigger conditions for this skill section:** load when a player reports "the AI awarded me territory I didn't win" or "the AI didn't capture territory I clearly won." When the trace shows `territoryGained` populated with declared targets but the Judge's narrative-end log contradicts the capture, this is the AGENCY VERIFICATION failure mode. Walk the evidence: identify the prose's winning verb for each target, identify the verb's grammatical agent, ask whether the agent is player or non-player.

**Provenance:** full case study in `references/judge-agency-rule-2026-08-09.md`.

## Classification Prompt Hardening (2026-08-03)

The `UserActionClassificationAgent` classifies player input into `GAMEPLAY`, `QUESTION`, `UI_COMMAND`, or `CHAT`. A chronic failure mode is **research plays getting misclassified as QUESTION** — the classifier fails to distinguish "research the ruins" (a gameplay command) from "what is in the ruins?" (a 4th-wall question).

The hardened prompt (`UserActionClassificationAgent.kt:136-157`) adds:
- Explicit 4th-wall framing for QUESTION: target is THE GAME ITSELF, not characters within it
- Explicit target framing for GAMEPLAY: target is CHARACTERS or THINGS within the game world
- Verb list (attack, move, cast, scout, **research**, investigate) as GAMEPLAY indicators
- Character dialogue in quotes as GAMEPLAY indicator
- A dedicated "CRITICAL DISTINCTION — Research vs. Questions" section with paired examples:
  - `"research the ruins" = GAMEPLAY`
  - `"what is in the ruins?" = QUESTION`
- Strategic commands (move troops, establish trade route, capture territory) as GAMEPLAY

When patching this prompt, preserve the `CRITICAL DISTINCTION` section verbatim — it is the primary defense against research/question confusion. The `ACTION_TYPE_ROUTING` section in `PromptManager.kt:632-653` shows the downstream dispatch:
```
GAMEPLAY  -> executeGameplayAction()
QUESTION   -> executeAnswerAgent()
UI_COMMAND -> executeOpenAgent()
CHAT       -> executeChatAgent()
```

If adding new `ActionType` values, update both the enum in `UserActionClassificationAgent.kt` AND the `when` block in `PromptManager.kt`.

## Files of Interest

- `sharedModel/src/commonMain/kotlin/structs/WritingAgentDefaults.kt` — canonical defaults (procedure text, author personality, rules, criteria, config)
- `sharedModel/src/commonMain/kotlin/structs/World.kt` — the `World` data class. **The `audioTracks` field is NOT `@Transient`** — the full music catalog leaks into 8 agent prompts via `serialize(WorldManager.world)` at 10 call sites. See `autogenesis-trace-analysis` `references/audio-tracks-leak.md`. (procedure text, author personality, rules, criteria, config)
- `sharedModel/src/commonMain/kotlin/structs/AuthorPersonalities.kt` — the 3 author personalities (CSA, CGO, NDT) + dropdown helper. Shared between server and MapEditor (JS-only) modules.
- `sharedModel/src/commonMain/kotlin/structs/MapPack.kt` — per-map config overrides via `MapPack.writingAgentConfig`
- `sharedModel/src/jvmMain/kotlin/structs/MapPackManager.kt` — runtime config loader
- `server/src/main/kotlin/agent/prompts/prompts.kt` — `Prompts.promptMap` (runtime source of truth for CSA/CGO/NDT lookups via `Prompts.promptMap["csa"|"cgo"|"ndt"]`)
- `server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt` — WriterAgent pipe code (assembleWritingSystemPrompt, guide/selection/writing pipes); the `effectiveAuthorPersonality` / `effectiveGuideAuthorPersonality` / `effectiveWritingAuthorPersonality` chain at lines 153-169
- `server/src/main/kotlin/agent/builders/writingAgent/` — sibling agents (ResponseRefinement, etc.)
- `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt` — orchestrates turn, calls WriterAgent at phase 6
- `server/src/main/kotlin/agent/runners/npcOrchestrator.kt` — NPC turn orchestration
- `server/src/main/kotlin/gameState/WorldManager.kt` — `loadMapFromPack` at line 1868 sets `activeWritingAgentConfig` from the pack
- `server/src/main/kotlin/globals/BedrockConfig.kt` — anti-censorship block, gameDescription, model config
- `server/README.md` — env vars including RIG (AI opponent rigging), MAP
- `mapEditor/src/jsMain/kotlin/ui/WritingSettingsDialog.kt` — map editor UI for prompt config; the author dropdown wiring at lines 224-235 populates `config.authorPersonality` from `AuthorPersonalities.promptForKey()`
- `server/src/main/resources/maps/*.map` — the 5 bundled map packs (each carries a serialized `MapData` inside `map.json`)

## The Autogenesis Tonal Contract (CGO + CSA dual-author)

The WriterAgent's voice is not a single personality — it is a two-stage pipeline with a deliberate split between the guide author and the chapter author. Both stages are wired up in `server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt:153-169`:

```kotlin
val effectiveGuideAuthorPersonality = Prompts.promptMap["cgo"] ?: effectiveAuthorPersonality
val effectiveWritingAuthorPersonality = Prompts.promptMap["csa"] ?: effectiveAuthorPersonality
```

`defaultAuthorPersonality` is empty by default, so a misconfigured `effectiveAuthorPersonality` (the user's Nordold Trable override, for example) only kicks in if the runtime CGO/CSA lookups fail. Both source-of-truth files carry the same text and must stay in sync:

- `sharedModel/src/commonMain/kotlin/structs/AuthorPersonalities.kt:25-69` — the three `dropdownEntries` (`"csa"`, `"cgo"`, `"ndt"`) and their prompt bodies
- `server/src/main/kotlin/agent/prompts/prompts.kt:146-202` — `Prompts.promptMap` keys for the same three

### The dual voice, by stage

- **CGO (Core Guidance Operator)** plans the turn. Its directive is "cynical absurdist humor that comes from applying the grim logic of the real world to absurd characters and fantasy scenarios." It produces up to three chapter ideas. It does not write prose.
- **CSA (Core Story Agent)** writes the chapter. Its directive is "a serious account of events that actually happened in a real world with real consequences." No "It was not X, it was Y" reveals. No em dashes. No fabricated people, places, factions, or technologies.
- **Nordold Trable (NDT)** is the legacy self-aware viral-propagation author. It is selectable from the dropdown as a developer opt-in but is NOT the default. Don't ship NDT as the active voice unless the user explicitly asks for it.

### The tonal rule that binds them

The active tonal contract — captured in `defaultProcedureText` at `WritingAgentDefaults.kt:13-127` — is one sentence: **"The world takes itself seriously. The people in it speak like idiots."** This is the load-bearing aesthetic choice of Autogenesis and the source of its deadpan register.

- **Narration is grounded, visceral, concrete, in the geopolitical-reality register.**
- **Dialogue is ridiculous, absurd, anachronistic, profane, hilarious, and spoken by people who take themselves completely seriously.**
- **The absurd comes from the gap between the seriousness of the world and the stupidity of the people in it.** If nobody is speaking in a given moment, write normal grounded narration.
- **No "It was not X, it was Y" fake-out reveals.** This is banned in both directions (writing-pipe author's own voice, AND as a story pattern). Earned payoffs are fine; manufactured gotchas are not.
- **No em dashes in prose.** The CSA prompt explicitly bans them and pettily explains why. Code and H2 separators may still use them; body prose must not.
- **Maple syrup, dolphin supremacy, naval logistics, and the demolition of the sky all receive the same gravity.** A demonic takeover of a nation and a lemon-cured revolution are both reported as ordinary matters of state.

### Why this contract matters for prompt debugging

When the writer drifts, the failure almost always lives upstream of CSA — it lives in CGO's chapter ideas or in the procedure text priming the wrong register. Diagnose in this order:

1. **Is the writer producing bureaucratic documents (tax forms, ledgers, statistical tables)?** The procedure text is primed for "history textbook" or "narrator" framing. Fix by replacing abstract framing with the concrete event gamut list (warfare, diplomacy, espionage, internal politics, economics, civilian life, terrain).
2. **Is the writer avoiding violence on a military action?** CGO is producing non-violent chapter ideas. Audit CGO's `decidedTurnOutcome` — not the writer's output.
3. **Is the writer hallucinating NPCs the player never created?** CGO is injecting `newCharactersToIntroduce` not in the lorebook. Fix CGO's selection prompt to ground the choice in the player's actual action.
4. **Is the writer drifting into dreamlike / Kafkaesque tone on every turn?** The criteria roll fallback returned ALL criteria when none passed, and CGO is selecting the most-criteria-satisfying outcome. Fix the fallback in `rollCriteriaAvailability` and rephrase CGO's footer to make criteria conditional.
5. **Is the writer using "It was not X, it was Y" reveals?** The procedure text's REVEALS rule was weakened or removed. Restore it.

### Same contract for marketing/surface writing

The deadpan register is the game's voice in every customer-facing surface: landing pages, blog posts, comparison pages, the Commander creation screen. The contract is identical. A landing page that says "Step into the absurd" is wrong; a landing page that says "Your imagination is the action menu" is right. Maple-syrup empires and dolphin supremacy are reported with the same gravity as naval logistics. The page never steps outside the world to wink at the reader. The creative:humanizer skill carries the production version of the AI-ism ban list (copula avoidance, "things that bit me" closers, hedge phrases) — but the deadpan tone is the underlying aesthetic, not just an anti-pattern checklist.

If you are writing Autogenesis marketing copy, blog posts, comparison pages, or landing-page content, the autogenesis-game-mechanics and autogenesis-prompt-debugging skills together carry the tonal contract. Read both before drafting.

## References

- `references/judge-agency-rule-2026-08-09.md` — August 2026 case study: R1T0 Lord Maple Tree's prose-contradiction capture, AGENCY VERIFICATION + PARTIAL-WIN RULE prompt patch, mechanical backstop in `enforceMandatoryTerritoryCapture`, three-step patch discipline (test the test first, pin the LLM-rule-mechanical-gate split in the test comment, don't gate by quote-only).
- `references/writer-agent-tax-form-bug.md` — June 2026 case study: WriterAgent producing bureaucratic artifacts instead of combat prose. Diagnostic walkthrough, fix diff, and verification commands.
- `references/writer-agent-author-architecture.md` — June 2026 case study: the CGO/CSA/Trable author architecture, the four-layer storage model, the cross-module shared helper pattern.
- `references/game-mechanics.md` — NPC turn interference mechanics: type-based chance table (ElderGod 60% → Passive 0%), override semantics (field > 0.0 takes precedence), turn order construction per round, `insertInterferingNpcs` random-position splice logic, WorldManager orchestration overview.
- `references/autogenesis-turn-extraction.md` — Per-pipe extraction playbook for a single Autogenesis turn directory: action text, validator verdict, narrative prose, judge verdict, world updates, subsystem inventory. The recipe for turning a folder of trace.json files into the chapters you see in game history.
- `references/verifier-fixture-availability.md` — The tpipe-trace-parser verifier's "Ran 0 case(s); 10 failure(s)" output is a fixture-availability problem, not a parser regression. Distinguishing the two.