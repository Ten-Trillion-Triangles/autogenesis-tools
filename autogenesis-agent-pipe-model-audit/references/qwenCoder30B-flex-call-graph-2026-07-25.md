# qwenCoder30B Flex-Tier Eligibility Audit (2026-07-25)

Evidence-backed snapshot from the post-migration audit of the Autogenesis source tree at `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis`. Companion to `qwen235B-call-graph-2026-07-25.md` — that one tracks model replacement scope; this one tracks Bedrock `setServiceTier(BedrockPriorityTier.Flex)` eligibility on the post-migration qwenCoder30B fleet.

## Scope

36 total `setModel(BedrockConfig.qwenCoder30B)` occurrences in `server/src/main/kotlin`. After excluding reasoning-pipe model assignments (11) and the unrelated reasoning-factory defaults in `BedrockConfig.kt:654, 658, 696, 700`, **25 main pipes** are in scope.

## Methodology

The audit applies the "strict-simple" filter (see SKILL.md §"Bedrock service-tier (Flex) audit — second dimension") to each main pipe's `setJsonOutput(T)` DTO. The DTO is strict-simple if it contains ONLY: booleans, enums, small-range numbers, short identifier strings, and shallow lists of those — no narrative-prose fields, no nested world-domain objects, no `Map<String, *>` over a domain type.

For each strict-simple main pipe, the audit classifies `setServiceTier(BedrockPriorityTier.Flex)` state as: (a) active, (b) commented-out ready to uncomment, (c) absent (must add new line).

## Live main pipes (25)

### Strict-simple ELIGIBLE for Flex (17)

| File:line | Pipe | Output DTO | Flex state | Recommended action |
|---|---|---|---|---|
| `validateAction/identifyPlayAgent.kt:132` | `identifyPipe` | `PlayTypeObj` (enum + Boolean) | commented L130 | Uncomment L130 |
| `validateAction/validator.kt:97` | `legalityCheckerPipe` | `Legal?` (Boolean, String reason, Boolean) | absent | Insert before L97 |
| `validateAction/resourceUsageDetectorAgent.kt:42` | `detectorPipe` | `UsedAssets` (List<String>) | absent | Insert before L42 |
| `validateAction/targetDetectorAgent.kt:207` | `universalRefinementPipe` | `TargetCandidateList` (List<TargetCandidate> classifier) | commented L202 | Uncomment L202 |
| `validateAction/targetDetectorAgent.kt:305` | `disambiguatorPipe` | `ActionTargetTypeObj` (enum + List<String> + Boolean) | commented L301 | Uncomment L301 |
| `validateAction/targetDetectorAgent.kt:389` | `detectorPipe` (broad-intent) | `ActionTargetTypeObj` | absent | Insert before L389 |
| `validateAction/ValidatorPipeAgent.kt:42` | `buildTPipeValidatorPipe` (meta-validator) | `ValidatorPipeResult` (Boolean + short assessment) | commented L40 | Uncomment L40 |
| `validateAction/railroadAgent.kt:26` | `railroadPipe` | `TrueFalse` (Boolean) | commented L25 | Uncomment L25 |
| `judgeOutcome/judge.kt:258` | `passOrFailPipe` | `Victory?` (Boolean) | absent | Insert before L258 |
| `judgeOutcome/judge.kt:1258` | `karmaPipe` | `TrueFalse` (Boolean) | commented L1257 | Uncomment L1257 |
| `judgeOutcome/judge.kt:1913` | `resourceClassificationPipe` | `ClassifiedResources` (lists of strings + List<ResourceClassification>) | commented L1911 | Uncomment L1911 |
| `judgeOutcome/npcJudge.kt:150` | `passOrFailPipe` | `Victory?` (Boolean) | absent | Insert before L150 |
| `judgeOutcome/npcJudge.kt:775` | `resourceClassificationPipe` | `ClassifiedResources` (same as judge.kt:1913) | commented L773 | Uncomment L773 |
| `systemActions/UserActionClassificationAgent.kt:184` | `classificationPipe` | `UserActionClassification` (enum + Double + String reason) | absent | Insert before L184 |
| `gatherContext/newcharacterscan.kt:1052` | `detectNpcHistoryChangesPipe` | `StringListWrapper` (List<String>) | absent | Insert before L1052 |
| `modifyGameState/reverseAgent.kt:108` | `validatorPipe` (sub-pipe in qwen235B agent) | `ReversalFailure` (Boolean + short reasons) | commented L106 | Uncomment L106 |
| `passFailAgent/passFailAgent.kt:40` | `passOrFailPipe` | `Victory?` (Boolean) | absent | Insert before L40 |

**Insertion-state distribution: 5 commented → uncomment, 12 absent → insert, 0 already active.** (Three more "active" pipes appear below in the "already Flex" section — but those are non-strict-simple and are deliberately being left alone.)

### Already-Flex (4 strict-simple, no action) + 3 already-Flex non-strict-simple (leaving as-is)

Already-Flex strict-simple (verifies the methodology — these were Flex before the audit started, and remain so):

| File:line | Pipe | Output DTO | Notes |
|---|---|---|---|
| `gatherContext/newcharacterscan.kt:153` | `identifyNewNPCPipe` | `NewCharacterList` (List<{name, createdBy}>) | active L152 |
| `gatherContext/newcharacterscan.kt:388` | `characterIdentifyClassPipe` | `NpcClassificationArray` (List<NpcClassification>) | active L387 |
| `gatherContext/newcharacterscan.kt:731` | `escalationPipe` | `NpcEscalationArray` (List<{name, newNpcStatus}>) | active L730 |

Already-Flex but NON-strict-simple (Pitfall 10 — leave as-is, document only):

| File:line | Pipe | Output DTO | Why not strict-simple |
|---|---|---|---|
| `gatherContext/newcharacterscan.kt:549` | `descriptionBuilderPipe` | `CharacterDescriptionArray` | 7 narrative prose fields per entry (description, history, personality, abilities, assets) |
| `gatherContext/newcharacterscan.kt:639` | `newNpcResourcePipe` | `NpcResourceMapWrapper` | `Map<String, List<Resource>>` — Resource is a domain object |
| `gatherContext/newcharacterscan.kt:927` | `existingNpcResourceUpdatePipe` | `NpcResourceMapWrapper` | Same as L639 |

### Excluded — NOT strict-simple (8)

| File:line | Pipe | Output DTO | Why excluded |
|---|---|---|---|
| `validateAction/validator.kt:539` | `legalityRectifierPipe` | (no setJsonOutput — emits narrative text) | Narrative action rewrite |
| `validateAction/validator.kt:719` | `styleReapplyPipe` | `ThirdPersonChanges.newOutput` | Full third-person narrative rewrite |
| `judgeOutcome/judge.kt:326` | `gainsAndLossesPipe` | `Results` | Nested world domain: TerritoryExchange + AssetExchange + TerritoryStatChange + ClassifiedResources |
| `judgeOutcome/judge.kt:1317` | `statChangePipe` | `MultiActorStatChanges` | `Map<String, StatBuff>` where StatBuff has 7 nested Int fields |
| `judgeOutcome/npcJudge.kt:222` | `gainsAndLossesPipe` | `Results` | Same as judge.kt:326 |
| `judgeOutcome/npcJudge.kt:599` | `statChangePipe` | `MultiActorStatChanges` | Same as judge.kt:1317 |
| `gatherContext/newcharacterscan.kt:1114` | `updateNpcHistoryPipe` | `NpcHistoryUpdate.newHistory` | Narrative lore history addendum |
| `modifyGameState/hardenAgent.kt:124` | `hardenPipe` | `StoryOutput.story` | Full narrative prose rewrite (the whole point of hardenAgent) |

### Excluded — no setJsonOutput, raw text (2)

| File:line | Pipe | Notes |
|---|---|---|
| `playerAgent/playerAgent.kt:54` | `analysisPipe` (Stage 1) | Raw strategic synthesis narrative; no JSON output |
| `playerAgent/playerAgent.kt:270` | `executionPipe` (Stage 3) | Raw third-person player action text; no JSON output |

### Excluded — DEAD code (1)

| File:line | Builder / Pipe | Why dead |
|---|---|---|
| `gatherContext/affectedPlayerAgent.kt:46` | `affectedPlayersPipe` (in `buildAffectedPlayerAgent`) | Function defined at L38, never called from any orchestrator. Verified via `grep -rn "buildAffectedPlayerAgent" server/src/main/kotlin/agent/runners/` returning empty. |

## Reasoning-pipe model assignments (excluded by task rule)

11 occurrences of `setModel(BedrockConfig.qwenCoder30B)` are inside `setReasoningPipe(...)` builders — these are CoT reasoners, NOT main pipes, and are explicitly excluded from the Flex scope per task rules. Do not mark them Flex.

| File:line | Reasoning builder | Main pipe it serves |
|---|---|---|
| `validateAction/ValidatorPipeAgent.kt:50` | `authorBuilder` | `buildTPipeValidatorPipe` main |
| `validateAction/validator.kt:103, 547, 727` | `authorBuilder` | `legalityChecker` / `legalityRectifier` / `styleReapply` |
| `validateAction/identifyPlayAgent.kt:139` | `explicitCotBuilder` | `identifyPipe` |
| `judgeOutcome/judge.kt:264, 337, 1262, 1328, 1922` | `explicitCotBuilder` / `structuredCotBuilder` / `processFocusedBuilder` | judge pipes |
| `judgeOutcome/npcJudge.kt:157, 231, 607, 784` | reasoning builders | npc judge pipes |
| `gatherContext/newcharacterscan.kt:164, 397, 558, 649, 738, 1059, 1120` | reasoning builders | newchar pipes |
| `gatherContext/affectedPlayerAgent.kt:50` | `explicitCotBuilder` | (in dead builder — moot) |
| `playerAgent/playerAgent.kt:60, 275` | `authorBuilder` / `structuredCotBuilder` | analysis / execution |
| `passFailAgent/passFailAgent.kt:46` | `explicitCotBuilder` | passOrFailPipe |

The 4 `applyModelBudget(qwenCoder30B)` calls in `BedrockConfig.kt` (L673, 715, 764, 811) are inside `obsessivePlannerBuilder` / `bestIdeaBuilder` / `structuredCotBuilder` / `processFocusedBuilder` — all reasoning factory defaults, excluded.

## Verifying call sites (orchestrator wiring for each Flex recommendation)

All 17 strict-simple recommendations are LIVE — verified call site:

| Recommendation | Live orchestrator wiring |
|---|---|
| identifyPlayAgent:132 | `gameplayOrchestrator.kt:1025`, `npcOrchestrator.kt:438` |
| validator:97 (legalityChecker) | `gameplayOrchestrator.kt:390` (inside `buildValidator`) |
| resourceUsageDetector:42 | `gameplayOrchestrator.kt:743` |
| targetDetector:207 (universalRefinement) | `targetDetectorAgent.kt:611` (chain call) |
| targetDetector:305 (disambiguation) | `targetDetectorAgent.kt:614` (chain call) |
| targetDetector:389 (broad-intent detector) | `targetDetectorAgent.kt:611` (chain call) |
| ValidatorPipeAgent:42 | Called as `setValidatorPipe(buildTPipeValidatorPipe(...))` from ~10 sites: validator.kt:396/673/771, railroadAgent.kt:67, judge.kt:288/1031, npcJudge.kt:177/488/569, hardenAgent.kt:169 |
| railroadAgent:26 | `gameplayOrchestrator.kt:426` |
| judge:258 (passOrFail) | `gameplayOrchestrator.kt:728` (inside `buildJudge`) |
| judge:1258 (karma) | `gameplayOrchestrator.kt` (inside `buildJudge`) |
| judge:1913 (resourceClassification) | `gameplayOrchestrator.kt` (inside `buildJudge`) |
| npcJudge:150 (passOrFail) | `npcOrchestrator.kt:706` |
| npcJudge:775 (resourceClassification) | `npcOrchestrator.kt:706` (inside `buildNpcJudge`) |
| UserActionClassification:184 | `PromptManager.kt:90` |
| newcharacterscan:1052 (detectNpcHistory) | `gameplayOrchestrator.kt:2526` (inside `buildNewCharacterScanPipeline`) |
| reverseAgent:108 (validatorPipe sub-pipe) | `gameplayOrchestrator.kt:1982` (parent `buildReverseAgent` is live; this validator sub-pipe is attached to it) |
| passFailAgent:40 | `gameplayOrchestrator.kt:728` |

## Schemas explicitly excluded by the task brief — verified NOT on qwenCoder30B

`NemesisStrategyList` (nemesisAgent.kt:39), `ResourceArray` (resourcedispatcher.kt:28), `NemesisConceptResponse` (nemesisCreationBuilder.kt:76) are all wired to **qwen235B** pipes, NOT qwenCoder30B. The task's "exclude" list does not overlap with this audit's scope. No conflict.

## Summary

- **Total qwenCoder30B `setModel` occurrences in production code**: 36
- **Main pipes (production)**: 25
- **Reasoning-pipe model assignments (excluded per task)**: 11
- **Strict-simple eligible main pipes (already Flex)**: 3
- **Strict-simple eligible main pipes (NOT yet Flex)**: **17** (5 uncomment, 12 insert)
- **Already-Flex non-strict-simple (leaving as-is)**: 3
- **Excluded (narrative / nested-domain)**: 8
- **Excluded (no setJsonOutput, raw text)**: 2
- **Excluded (dead code)**: 1
