# Autogenesis qwen235B Flex-Tier Eligibility Audit — Case Study

**Date**: 2026-07-25
**Source repos (read-only)**:

- Autogenesis: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis`
- TPipe: `/home/cage/Desktop/Workspaces/TPipe/TPipe`

This is the canonical worked example for the `tpipe-pipe-feature-audit` skill.
It documents the actual findings from one audit run, against one feature
(Bedrock service tier = Flex), in one consumer codebase (Autogenesis).

## What was audited

Every production `BedrockConfig.qwen235B` use under
`server/src/main/kotlin/agent/` — 23 line-level references across 18 files.

## What was found

### Plumbing audit (Passes 1–3, 5)

**Pass 1 — Provider class.** `BedrockPriorityTier` enum is defined at
`TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:44-50`. Default tier on
`BedrockPipe` is `Standard` (line 272). The setter is `setServiceTier(...)` at
line 588. The mapping to AWS SDK is `mapServiceTier()` at line 598, invoked at
20+ call sites in `BedrockPipe.kt` and once in `BedrockMultimodalPipe.kt:414`.

**Pass 2 — Defaults dataclasses.** `BedrockConfiguration`
(`TPipe-Defaults/.../ProviderConfiguration.kt:71-93`) has NO `serviceTier`
field. `OpenRouterConfiguration` (line 224) DOES — `var serviceTier: String?`
— and `OpenRouterDefaults.createOpenRouterPipe` reads it at line 89.
**Bedrock tier cannot be declared declaratively through any Defaults
configuration surface.** It must be set via the setter on the returned pipe.

**Pass 3 — PipeSettings.** `PipeSettings` (`Structs/PipeSettings.kt:20-72`)
has no tier field. Bedrock tier does NOT round-trip through serialization.

**Pass 5 — setReasoningPipe boundary.** `setReasoningPipe()` does NOT copy
properties from the main pipe to the reasoning pipe. Reasoning pipes have
their own independent `serviceTier` state. Autogenesis wires the reasoning
pipe tier via a `useFlex: Boolean = false` parameter on six reasoning-pipe
factories in `server/src/main/kotlin/globals/BedrockConfig.kt:535-864`
(authorBuilder, obsessivePlannerBuilder, bestIdeaBuilder,
structuredCotBuilder, processFocusedBuilder, explicitCotBuilder).

### Consumer audit (Pass 4)

#### The 23 qwen235B uses, classified

Of 23 unique line-level references, 4 verdict buckets. 34 judged units total
because several pipe builders contain multiple `setJsonOutput` references
and several class definitions span multiple constructors.

##### 13 ELIGIBLE main pipes (small JSON, Flex-appropriate)

| Site | `setJsonOutput` class | Field shape |
|---|---|---|
| `npcHostileAgent.kt:79` | `HostileNpcPlan` (2 strings) | `idea`, `reason` |
| `nemesisAgent.kt:215` | `NemesisStrategyList` (list of 3-string records) | `strategies: List<NemesisStrategy>` where each is `target`, `method`, `reason` |
| `elderGodAgent.kt:124` | `ElderGodTarget` (1 string + 1 reason) | `territoryToDestroy`, `reason` |
| `BranchFailureAgent.kt:27` | `AgentRetry` (1 enum + 1 short prompt) | `failureReason: BranchCase`, `retryUserPrompt` |
| `defensiveValidator.kt:46` | `DefenseLegal?` (1 bool + 1 reason) | `isLegal`, `changesToMake` |
| `npcValidationAgent.kt:48` | `NPCLegal?` (1 bool + 1 reason) | `isLegal`, `changesToMake` |
| `npcValidationAgent.kt:279` | `NPCThirdPersonChanges` (1 bool + 1 text) | `needsChanges`, `newOutput` |
| `counterResponseIntentDetector.kt:46` | `CounterResponseIntent` (1 string, 2-value enum) | `intent: String` |
| `resourceUsageDetectorAgent.kt:129` | `UsedAssets` (1 list-of-strings) | `usedAssets: List<String>` |
| `geoPoliticsAssessmentAgent.kt:365` | `TrueFalse` (1 bool + 1 reason) | `isTrue`, `reason` |
| `geoPoliticsAssessmentAgent.kt:619` | `AgentAssessmentLevel` (4 numeric/bool fields) | `favorPoints`, `riskLevel`, `isConventionalForOvertonWindow`, `playTargetDefensePoints` |
| `OpenWidgetAgent.kt:120` | `OpenUiDecision` (mostly enums + bools + short strings) | `isActionable`, `widget: OpenWidgetType?`, `confidence`, `reasoning`, `suggestions: List<OpenWidgetType>`, etc. |
| `ResponseRefinementAgent.kt:46` | `TrueFalse` (1 bool + 1 reason) | `isTrue`, `reason` |

Every one of these produces a small structured-output JSON. Every one is
currently configured at `Standard` tier (the `setServiceTier(BedrockPriorityTier.Flex)`
line is commented out at each site that previously had one). Each is a
candidate for uncommenting the line, or for hoisting the call to a single
helper in `BedrockConfig`.

##### 17 NARRATIVE main pipes (prose / world-object output, Flex is the wrong tool)

| Site | What it produces |
|---|---|
| `lorebookAgent.kt:84` | `LorebookExtraction` — `List<CharacterEntry>`, `List<EventEntry>`, `List<LocationEntry>`, `List<ItemEntry>`, `List<FactionEntry>`, `List<RelationshipEntry>` (each with multi-sentence description) |
| `npcActorAgent.kt:69` | Free-text NPC action prose (1–2K chars) |
| `npcHostileAgent.kt:120` | Free-text 3rd-person NPC action prose |
| `nemesisAgent.kt:241` | Free-text 3rd-person nemesis action prose (1–3K chars) |
| `elderGodAgent.kt:175` | Free-text 3rd-person destruction narrative |
| `defensiveValidator.kt:339` | Free-text 3rd-person rewrite of illegal counter-response |
| `npcValidationAgent.kt:162` | Free-text 3rd-person rewrite of illegal NPC action |
| `ResponseRefinementAgent.kt:94` | `RefinedResponse.refinedProse` (the rewritten narrative) |
| `chatAgent.kt:40` | Free-text NPC chat reply streamed to UI |
| `actOfGodAgent.kt:27` | Free-text act-of-god rewrite of an entire story chapter |
| `resourcedispatcher.kt:50` | `ResourceArray.adjustments: List<ResourceAdjustment>` with `description` (≥50 chars) and `abilities` (≥50 chars) per item |
| `nemesisCreationBuilder.kt:260` | `NemesisConceptResponse` (full concept with `personalityTraits`, `memorableQuirks`, etc.) |
| `nemesisCreationBuilder.kt:371` | `NpcDataResponse` (full NPC data class) |
| `writerAgent.kt:193` | `GuideData` (chapter plan: `chapterIdeas`, `possibleTurnOutcomes`, character action map, etc.) |
| `writerAgent.kt:436` | `DistilledGuideResult` (committed story direction) |
| `geoPoliticsAssessmentAgent.kt:457` | Free-text political-scholar essay |
| `reverseAgent.kt:77` | `FinalReversalOutcome.storyAfterReversal` (entire reversed chapter) |

##### 4 REASONING / RETRY-SWAP sites (governed by separate mechanisms)

| Site | Mechanism |
|---|---|
| `chatAgent.kt:48` | Reasoning pipe (`authorBuilder`). Tier governed by `useFlex` flag, not main setter. |
| `UserActionClassificationAgent.kt:59` | Reasoning pipe (`explicitCotBuilder`). Tier governed by `useFlex` flag. |
| `playerAgent.kt:280` | Reasoning pipe (`structuredCotBuilder`). Tier governed by `useFlex` flag. |
| `nemesisCreationBuilder.kt:125` | Config object (model field only), consumed elsewhere. |
| `gameplayOrchestrator.kt:2759` | Runtime retry-swap. Inherits prior pipe state. |

#### Notable pre-baked-but-disabled Flex sites

The following qwen235B sites had a `// setServiceTier(BedrockPriorityTier.Flex)`
comment IMMEDIATELY above the `setModel(...)` call — indicating the original
developer intended Flex but rolled back before merging:

- `defensiveValidator.kt:45` (legality checker) — ELIGIBLE → matches `DefenseLegal?`
- `defensiveValidator.kt:338` (rectifier) — NARRATIVE → no JSON output
- `counterResponseIntentDetector.kt:43` — ELIGIBLE → matches `CounterResponseIntent`
- `actOfGodAgent.kt:25` — NARRATIVE → free-text rewrite
- `reverseAgent.kt:70` — NARRATIVE → `FinalReversalOutcome` is a single narrative string
- `reverseAgent.kt:106` (validator — qwenCoder30B, not qwen235B)
- `playerAgent.kt:52` (analysis — qwenCoder30B)
- `playerAgent.kt:268` (execution — qwenCoder30B)

Pattern: where the developer drafted Flex, the output contract was small
enough to justify it. Narrative-side pipes were drafted aspirationally and
rolled back before merging. The signal of "drafted intent that was rolled
back" is the strongest pointer to where enabling Flex is safe.

#### Verification grep (Pass 4 follow-up)

```bash
grep -rn "setServiceTier(BedrockPriorityTier\." server/src/main/kotlin/agent/
```

Before audit: zero active calls on qwen235B sites. Every match was either:
- A comment (`// setServiceTier(...)`), OR
- An active call on a non-qwen235B site (e.g. `newcharacterscan.kt` on qwenCoder30B pipes), OR
- An active call on a non-qwen-tier setter (e.g. `setServiceTier(BedrockPriorityTier.Standard)` in template-copy code that clamps the branch pipe to Standard).

The Autogenesis codebase is in the canonical "feature available, documented,
drafted, but never active" state at audit time.

#### Reasoning-pipe side companion — `useFlex`

Every call site that wires a qwen235B into a main pipe's reasoning pipe
**explicitly passes `useFlex = false`** (or omits the parameter, defaulting to
`false`):

- `identifyPlayAgent.kt:139` — `explicitCotBuilder(useFlex = false, ...)`
- `affectedPlayerAgent.kt:50` — `explicitCotBuilder(useFlex = false, ...)`
- `nemesisCreationBuilder.kt:136, 150, 267` — three `useFlex = false`
- `worldupdates.kt:37` — `explicitCotBuilder(useFlex = false, ...)`
- `nemesisAgent.kt:178, 181` — two `useFlex = false`

Even if a future change uncommented Flex on a qwen235B main pipe, the
reasoning pipe would still run on Standard until each of these explicit
`useFlex = false` calls is changed to `useFlex = true`.

## Indirect configuration paths

- `ExtendModelDefaults.kt:38` declares `qwen235B = "qwen.qwen3-235b-a22b-2507-v1:0"`
  but **no production pipe in `server-extend` references `ExtendModelDefaults.qwen235B`**.
  Model is provisioned for cross-server use but currently unused in the extend service.
- The only indirect path that hard-codes a tier is `buildBranchPipeFromTemplate(...)`
  at `BranchFailureAgent.kt:113-132`, which explicitly calls
  `setServiceTier(BedrockPriorityTier.Standard)` at line 120 — clamping to Standard
  rather than inheriting Flex. This is the opposite of a Flex opt-in: it is a
  hard-coded Standard guard against the templated branch pipe accidentally
  inheriting a Flex tier from the failed parent.

## Recommended roll-out sequence

If the goal is to enable Flex on every qwen235B main pipe where the JSON
output is small + non-narrative:

1. `counterResponseIntentDetector.kt:46` — single counter-response intent
   classifier (highest-volume, lowest-risk). Uncomment line 43.
2. `resourceUsageDetectorAgent.kt:129` — fallback pipe for inventory usage
   detection. Add `setServiceTier(BedrockPriorityTier.Flex)` after the
   `setModel(BedrockConfig.qwen235B)` block at line 129.
3. `geoPoliticsAssessmentAgent.kt:619` — numeric scoring pipe. Add Flex
   after the `setModel` at line 619.
4. `geoPoliticsAssessmentAgent.kt:365` — overton-window normalcy pipe.
   Add Flex after the `setModel` at line 365.
5. `BranchFailureAgent.kt:27` — error-tagging pipe. Add Flex.
6. The remaining seven ELIGIBLE pipes (`defensiveValidator.kt:46`,
   `npcValidationAgent.kt:48`, `npcValidationAgent.kt:279`,
   `ResponseRefinementAgent.kt:46`, `OpenWidgetAgent.kt:120`,
   `npcHostileAgent.kt:79`, `nemesisAgent.kt:215`, `elderGodAgent.kt:124`)
   follow the same one-line change.

**Hold-for-decision**: `nemesisCreationBuilder.kt:125` is actually a config
object whose model field is repurposed elsewhere; do not add a tier call
here without first verifying it is wired into a pipe builder.

**Do not change**: the 17 NARRATIVE pipes and the 4 REASONING/RETRY-SWAP
sites — Flex is the wrong tool for prose and already covered by `useFlex`
on the reasoning-pipe factories.

## Lessons that generalize beyond this audit

1. **Commented-out setters signal rolled-back intent.** Sites with
   `// setServiceTier(BedrockPriorityTier.Flex)` immediately above `setModel(...)`
   are the highest-confidence Flex candidates. The developer already knew
   the feature applied here.

2. **`setJsonOutput` target shape is the right rubric.** Classifying pipes
   by their output's field shape (enums/bools/lists vs prose vs world objects)
   is more reliable than classifying by file location or pipe name.

3. **Every Defaults-style runtime override inherits prior state.** The
   orchestrator's retry-swap to qwen235B does not set tier, so it inherits
   Standard. To change the tier on the retry-swapped pipe, the originating
   pipe must have had the tier set first.

4. **The reasoning-pipe side is a separate decision.** Even with Flex
   enabled on a qwen235B main pipe, the reasoning pipe still runs on
   Standard unless each `useFlex = false` is changed to `useFlex = true`
   at the reasoning-pipe factory call site. Audit both sides.

5. **`constructPipeFromTemplate` does not copy feature state.** Branch
   pipes built from templates reset to the default tier. Clamping to
   Standard explicitly is the right pattern — it prevents accidental
   inheritance of Flex from a failed parent.

## Cross-references

- `tpipe-pipe-feature-audit` SKILL.md — the parent methodology.
- `references/ditl-hook-decision-tree.md` (in `tpipe-pipe-internals`) — for
  reasoning about hook lifecycle when reasoning pipes interact with DITL.
- `tpipe-reasoning-pipes` SKILL.md — reasoning-pipe mechanics, factory
  surface, and the `useFlex`-style escape-hatch pattern.