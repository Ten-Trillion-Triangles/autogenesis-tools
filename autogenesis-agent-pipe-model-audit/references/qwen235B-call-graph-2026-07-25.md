# qwen235B Live Call Graph (audit 2026-07-25)

Evidence-backed snapshot from the 2026-07-25 audit of the Autogenesis source tree at `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis`.

## Scope

37 total `BedrockConfig.qwen235B` references in `server/src/main` + `server-extend/src/main`. After excluding non-source occurrences and dead config, **35 live occurrences** are candidates for replacement. The recommended target is `BedrockConfig.qwenCoder30B` (the same constant at `BedrockConfig.kt:436`, already the default for `buildTPipeValidatorPipe`, `buildPassFailAgent`, `buildPlayerAgent` analysis/execution pipes, `buildResourceUsageDetectorAgent` main, `buildReverseAgent` validator, and the `authorBuilder`/`processFocusedBuilder`/`explicitCotBuilder`/`structuredCotBuilder` reasoning factory defaults).

## Live occurrences by slot

### Main pipes (28)

| File:line | Builder / Pipe | Orchestrator wiring |
|---|---|---|
| `systemActions/OpenWidgetAgent.kt:120` | `configureBasePipe` (decision + pcp) | PromptManager.kt:846 |
| `systemActions/chatAgent.kt:40` | `chatPipe` | PromptManager.kt:777 |
| `modifyGameState/reverseAgent.kt:77` | `reversalPipe` | gameplayOrchestrator.kt:1982 |
| `modifyGameState/actOfGodAgent.kt:27` | `actOfGodPipe` | gameplayOrchestrator.kt:1940 |
| `modifyGameState/nemesisCreationBuilder.kt:260` | `storyAnalysisPipe` | gameplayOrchestrator.kt:2695 |
| `modifyGameState/nemesisCreationBuilder.kt:371` | `characterDesignPipe` | gameplayOrchestrator.kt:2695 |
| `modifyGameState/resourcedispatcher.kt:50` | `dispatchPipe` | gameplayOrchestrator.kt handleTurnMaintenance |
| `gameplayActions/elderGodAgent.kt:124` | `targetPipe` | npcOrchestrator (per ElderGod turn) |
| `gameplayActions/elderGodAgent.kt:175` | `actionPipe` | npcOrchestrator (per ElderGod turn) |
| `gameplayActions/nemesisAgent.kt:215` | `schemesPipe` | npcOrchestrator (per Nemesis turn) |
| `gameplayActions/nemesisAgent.kt:241` | `promptPipe` | npcOrchestrator (per Nemesis turn) |
| `gameplayActions/npcActorAgent.kt:69` | `npcActorPipe` | npcOrchestrator → buildNpcActorAgent |
| `gameplayActions/npcHostileAgent.kt:79` | `optionsPipe` | npcOrchestrator → buildHostileNpcAgent |
| `gameplayActions/npcHostileAgent.kt:120` | `actionsPipe` | npcOrchestrator → buildHostileNpcAgent |
| `validateAction/npcValidationAgent.kt:48` | `npcLegalityCheckerPipe` | npcOrchestrator.kt:394 |
| `validateAction/npcValidationAgent.kt:162` | `npcLegalityRectifierPipe` | npcOrchestrator.kt:394 |
| `validateAction/npcValidationAgent.kt:279` | `npcStyleReapplyPipe` | npcOrchestrator.kt:394 |
| `validateAction/defensiveValidator.kt:46` | `defensiveLegalityCheckerPipe` | gameplayOrchestrator.kt:1472 / npcOrchestrator.kt:1340 |
| `validateAction/defensiveValidator.kt:339` | `defensiveRectifierPipe` | gameplayOrchestrator.kt:1472 / npcOrchestrator.kt:1340 |
| `validateAction/counterResponseIntentDetector.kt:46` | `buildCounterResponseIntentDetector` | gameplayOrchestrator.kt:1190 / npcOrchestrator.kt:1070 |
| `judgeOutcome/geoPoliticsAssessmentAgent.kt:365` | `playNormalcyPipe` | gameplayOrchestrator.kt:1681 |
| `judgeOutcome/geoPoliticsAssessmentAgent.kt:457` | `writtenAssessmentPipe` | gameplayOrchestrator.kt:1681 |
| `judgeOutcome/geoPoliticsAssessmentAgent.kt:619` | `numericScoringPipe` | gameplayOrchestrator.kt:1681 |
| `lorebook/lorebookAgent.kt:84` | `extractionPipe` | gameplayOrchestrator.kt:1800 / npcOrchestrator.kt:652 |
| `writingAgent/writerAgent.kt:193` | `guidePipe` | gameplayOrchestrator.kt:1738 / npcOrchestrator.kt:612 |
| `writingAgent/writerAgent.kt:436` | `selectionPipe` (distill guide pipe) | gameplayOrchestrator.kt:1738 / npcOrchestrator.kt:612 |
| `writingAgent/ResponseRefinementAgent.kt:46` | `detectPipe` | gameplayOrchestrator.kt:1603 / npcOrchestrator.kt:1448 / SummitOrchestrator.kt:114 |
| `writingAgent/ResponseRefinementAgent.kt:94` | `refinePipe` | gameplayOrchestrator.kt:1603 / npcOrchestrator.kt:1448 / SummitOrchestrator.kt:114 |

### Reasoning pipes (3)

| File:line | Builder / Pipe | Notes |
|---|---|---|
| `systemActions/UserActionClassificationAgent.kt:59` | `createExplicitCotPipe()` reasoning for `createUserActionClassificationPipeline` | The MAIN pipe at L184 is already `qwenCoder30B`; this is the reasoning step |
| `systemActions/chatAgent.kt:48` | `chatPipe.setReasoningPipe(authorBuilder { ... setModel(qwen235B) })` | Both main and reasoning on chat pipe are qwen235B |
| `playerAgent/playerAgent.kt:280` | `executionPipe.setReasoningPipe(structuredCotBuilder { ... setModel(qwen235B) })` | Execution pipe MAIN (L270) is already `qwenCoder30B`; this is the reasoning step |

### Branch / Fallback pipes (3)

| File:line | Builder / Pipe | Blast radius |
|---|---|---|
| `validateAction/BranchFailureAgent.kt:27` | `buildBranchFailureAgent` shared factory | **~12 callers** — every `setBranchPipe(buildBranchFailureAgent(...))` call site inherits this model. Major amplifier. |
| `validateAction/resourceUsageDetectorAgent.kt:129` | `buildResourceFallbackPipe` | 1 caller (main at L42 already on `qwenCoder30B`) |
| `gameplayOrchestrator.kt:2759` | `swapPipelineModels` (swap from deepseek/novaPro → qwen235B) | 3 callers (gameplayOrchestrator.kt:1045, :1149; npcOrchestrator.kt:484). The swap LOG at L2760 says "QwenCoder480B" but the actual code uses `qwen235B` — misleading log. |

### Dead config (1)

| File:line | Variable | Why dead |
|---|---|---|
| `modifyGameState/nemesisCreationBuilder.kt:125` | `qwenBedrockSettings` | `BedrockConfiguration` constructed but never passed to any pipe. The 3 pipes in the same file explicitly set their own model at L148 (PalmyraX5), L260 (qwen235B), L371 (qwen235B). |

### Constant definition (1) — keep symbol, change value

| File:line | Symbol | Recommendation |
|---|---|---|
| `server/src/main/kotlin/globals/BedrockConfig.kt:421` | `val qwen235B = "qwen.qwen3-235b-a22b-2507-v1:0"` | Change the string value to alias, OR keep symbol and rename references. Renaming references preferred for self-documenting diff. |

## Non-source occurrences (excluded from scope)

| Path | Reason |
|---|---|
| `game_cost_estimator.py:9, 23, 32-50, 59-65, 165, 222` | Pricing file. Update when billing model changes |
| `plan_tiers.py:161` | Pricing tier commentary. Update alongside `game_cost_estimator.py` |
| `unlock_before_refactor_changes.md:119` | Historical context doc |
| `docs/gameplay-agent-pipe-reasoning.md` | Skill audit doc, informational |
| `BUG_INVESTIGATION_REPORT.md`, `AGENTS.md`, `CLAUDE.md`, `PLANS/*` | Markdown docs |
| `server/src/test/kotlin/agent/builders/ExtractJsonStreamingFailureTest.kt` | Test pin — review before changing |
| `server/src/test/kotlin/agent/builders/gameplayActions/NpcActorShowThinkingPropagationTest.kt` | Test pin |
| `server/src/test/kotlin/agent/builders/gameplayActions/ElderGodNpcPromptContextSufficiencyTest.kt` | Test pin |
| `server/src/test/kotlin/org/ttt/autogenesis/gameState/BedrockConfigThinkingCaptureTest.kt` | Test pin |
| `server/src/test/kotlin/org/ttt/autogenesis/gameState/BedrockConfigEmptyThoughtProcessTest.kt` | Test pin |
| `server-extend/src/main/kotlin/globals/ExtendModelDefaults.kt:38` | Mirror constant, unused in server-extend |

## Agents already on qwenCoder30B (no action needed)

- `validateAction/ValidatorPipeAgent.kt:42` (`buildTPipeValidatorPipe` main)
- `validateAction/ValidatorPipeAgent.kt:50` (reasoning)
- `passFailAgent/passFailAgent.kt:40`
- `systemActions/UserActionClassificationAgent.kt:184` (main — reasoning at L59 still qwen235B)
- `playerAgent/playerAgent.kt:54` (analysisPipe), `:270` (executionPipe main — reasoning at L280 still qwen235B)
- `validateAction/resourceUsageDetectorAgent.kt:42` (main — fallback at L129 still qwen235B)
- `modifyGameState/reverseAgent.kt:108` (validatorPipe)
- `BedrockConfig.kt:654, 658, 673, 696, 700, 715, 730, 779, 828` (reasoning factory defaults)

## Agents already on PalmyraX5 (no action needed)

- `defensiveValidator.kt:325, 406` (branch/validator pipes)
- `lorebookAgent.kt:139` (branch pipe)
- `writerAgent.kt:381, 518, 578` (guide-branch, transformed-thinking, writingPipe)
- `geoPoliticsAssessmentAgent.kt:109, 252, 304` (essay/overton/conflict-level pipes)
- `nemesisAgent.kt:123, 169, 130, 178-184` (assessmentPipe + branchPipe)
- `nemesisCreationBuilder.kt:148, 150` (dataCollectionPipe + reasoning)
- `reverseAgent.kt:159` (repairPipe / branch)
- `UserActionClassificationAgent.kt:118` (custom validator pipe)

## Orchestrator → builder wiring (evidence)

`gameplayOrchestrator.executePlayerTurn` (12-phase player turn) wires:
- `buildPlayerAgent` (L916) → reasoning at :280
- `buildValidator`, `buildRailroadAgent` (L390, L426)
- `buildPlayDetectionAgent` (L1025) → `swapPipelineModels` at L1045
- `buildTargetDetectorAgent` (L1129) → `swapPipelineModels` at L1149
- `buildCounterResponseIntentDetector` (L1190)
- `handleCounterPlay` → `buildDefensiveValidator` (L1472)
- `buildResponseRefinementAgent` (L1603)
- `buildNeoWritingAgent` (L1738) → guidePipe + selectionPipe
- `buildAssessmentAgent` (L1681) → playNormalcy + writtenAssessment + numericScoring
- `buildPassFailAgent` (L1849)
- `buildResourceUsageDetectorAgent` (L1872) → main + fallback
- `buildReverseAgent` (L1982), `buildHardenAgent`, `buildActOfGodAgent` (L1940)
- `buildJudge` (L2107)
- `buildNewCharacterScanPipeline` (L2526)
- `buildNemesisCreationAgent` (L2695) → storyAnalysis + characterDesign
- `buildLorebookUpdateAgent` (L1800)
- `runSummitOrchestration` (L650) → `buildResponseRefinementAgent` (L114) + `buildJudge` (L180)

`npcOrchestrator.executeNpcTurn` wires:
- `buildNPCValidator` (L394) → 3 pipes
- `buildPlayDetectionAgent` (L438)
- `buildTargetDetectorAgent` (L459) → swap at L484
- `buildNeoWritingAgent` (L612)
- `buildLorebookUpdateAgent` (L652)
- `buildNpcJudge` (L706)
- `buildCounterResponseIntentDetector` (L1070)
- `buildDefensiveValidator` (L1340)
- `buildResponseRefinementAgent` (L1448)

`SummitOrchestrator.runSummitOrchestration` wires:
- `buildResponseRefinementAgent` (L114) — qwen235B exposure
- `buildJudge` (L180) — does NOT directly reference qwen235B; inner pipes use PalmyraX5 and qwenCoder30B

Server-extend commander creation wires `buildCommanderCreationAgent` (commanderCreationBuilder.kt) — uses `ExtendModelDefaults.novaModelName` exclusively. **No qwen235B exposure.**

## Findings worth re-reading

- **Log message lie:** `gameplayOrchestrator.kt:2760` logs "QwenCoder480B" while swapping to `qwen235B`. The log was either aspirational (intended target) or a copy-paste error from a prior migration. Code is the source of truth.
- **Reasoning pipes hide inside `.apply { ... }`:** three occurrences (chatAgent.kt:48, playerAgent.kt:280, UserActionClassificationAgent.kt:59) — these are easy to miss in a grep because the surrounding call is the builder. Always inspect `.apply { ... }` blocks.
- **Shared factory amplifier:** `buildBranchFailureAgent` is the most-used branch-failure factory. Migrating this single line cascades to ~12 callers. Audit-friendly pattern but high blast radius.
- **Symlinked secrets directory:** `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/autogenesis-secrets` is a symlink — not relevant to model audit but useful note for finding `bedrock.local.properties` if you need the actual model IDs at runtime.