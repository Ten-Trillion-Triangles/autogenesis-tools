# Validator / Branch Slot Pattern — Autogenesis Production Inventory

Session: 2026-07-29. The TPipe `Pipe` class exposes `setValidatorPipe(Pipe)`
and `setBranchPipe(Pipe)` slots that take a **Pipe** (not a lambda) as
the gate and the fallback. This file is the session-specific inventory
of every `setValidatorPipe` / `setBranchPipe` site in the Autogenesis
server module, the orchestrator that invokes each, and the underlying
TPipe API used. Use as the canonical "find me the validators / find me
the fallbacks" reference for this codebase.

## TPipe API surface (verified)

Extracted from `libs-local/TPipe-1.0.0.jar` with
`javap -public com/TTT/Pipe/Pipe.class`:

| Method | Purpose |
|---|---|
| `setValidatorPipe(Pipe)` | Attach a Pipe-shaped gate |
| `setValidatorPipe(Pipe, saveSnapshotAsPageKey: Boolean)` | Attach a Pipe-shaped gate AND auto-save the original user prompt under `USER_PROMPT_SNAPSHOT` ("validatorPipeUserPromptSnapshotTPipe") |
| `setBranchPipe(Pipe)` | Attach a Pipe-shaped fallback (runs when validator returns `isValid: false`) |
| `setValidatorFunction((MultimodalContent) -> Boolean)` | Lambda gate (sibling to `setValidatorPipe`, NOT a replacement) |
| `setPreValidationFunction` / `setPreValidationMiniBankFunction` | Context injection hooks that fire before the validator pipe runs |

There is no `BranchBuilder` or `PipeBranch` class. The "branch tree" is
a collection of plain `Pipe` instances attached to host pipes through
these slots.

## The three factory styles

Every gate-and-fallback pair in Autogenesis is built by one of three
factory idioms. When you see one of these in the wild, that is the
gate-and-fallback pattern — not a lambda hook.

### 1. `buildTPipeValidatorPipe` — the meta-validator gate

**File**: `server/src/main/kotlin/agent/builders/validateAction/ValidatorPipeAgent.kt:35`

```kotlin
fun buildTPipeValidatorPipe(
    instructions: String,
    context: String = "",
    pageKeys: String = "",
    schema: String = ""
): BedrockMultimodalPipe
```

Returns a `BedrockMultimodalPipe` configured as an LLM-as-judge gate. The
output schema is `ValidatorPipeResult(isValid: Boolean, assessment: String)`.
The pipe installs its own `validatorFunction` reading the `isValid` field
of its own output (line 114-117), so the host pipe only needs to call
`setValidatorPipe(buildTPipeValidatorPipe(...))` — the boolean dispatch
is internal.

Used as the gate in 21+ sites across the server module. See the
per-orchestrator map below.

### 2. `buildBranchFailureAgent` — the error-logging branch

**File**: `server/src/main/kotlin/agent/builders/validateAction/BranchFailureAgent.kt:20`

```kotlin
fun buildBranchFailureAgent(instructions: String = ""): BedrockMultimodalPipe
```

Returns a `BedrockMultimodalPipe` that emits `AgentRetry` JSON with an
error-classification enum (`RefusedTask`, `DidNotFollowInstructions`,
`IncorrectResult`). Captures the parent's snapshot via
`setPreValidationMiniBankFunction` and writes the error text into
`ContextBank` under the `errorStatus` page key so the orchestrator above
can read it. Calls `it.terminate()` to halt the pipeline cleanly on
error.

This is the **error-logging** branch — used when the validator rejects
a refusal, so the orchestrator can route the error upward.

### 3. `buildBranchPipeFromTemplate` — the model-swap retry branch

**File**: `server/src/main/kotlin/agent/builders/validateAction/BranchFailureAgent.kt:113`

```kotlin
fun buildBranchPipeFromTemplate(
    pipe: Pipe,
    model: String,
    budget: TokenBudgetSettings,
    copyFunctions: Boolean = false
): BedrockMultimodalPipe
```

Clones the parent pipe via `constructPipeFromTemplate<BedrockMultimodalPipe>(
pipe, copyMetadata = true, copyFunctions = copyFunctions)` and swaps
the model + token budget. Almost always paired with
`BedrockConfig.PalmyraX5` + `BedrockConfig.palmyraBudgetSettings`.

This is the **retry with a different model** branch — the canonical
fallback when the primary pipe refused or produced garbage.

### In-house variants

| Variant | File:Line | Note |
|---|---|---|
| `buildResourceFallbackPipe(player, action)` | `validateAction/resourceUsageDetectorAgent.kt:125` | Custom Qwen fallback for resource-usage detection. NOT a template — fresh `BedrockMultimodalPipe` with stricter refusal/JSON check. |
| `private inline fun buildPalmyraFallbackAgent(...)` | `judgeOutcome/npcJudge.kt:81` | Private inline factory local to `npcJudge.kt`. Same PalmyraX5 retry pattern as `buildBranchPipeFromTemplate` but locally scoped. Used three times (Pass/Fail, Gains/Losses, Karma) in the NPC adjudication pipeline. |

## Orchestrator-level composition patterns

### Pattern A — Parallel validators (Splitter)

When multiple validators must run side-by-side and their results are
joined later, wrap each validator pipeline in `Splitter.addPipeline(key, pipeline)`.

**Autogenesis example** (`server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt:387-441`):

```kotlin
val validationSplitter = Splitter().apply {
    val validatorPipeline = buildValidator(player).apply { ... }
    addPipeline("validator", validatorPipeline)
    addContent("validator", MultimodalContent(effectiveTurnAction))

    val railroadPipeline = buildRailroadAgent().apply { ... }
    addPipeline("railroad", railroadPipeline)
    addContent("railroad", MultimodalContent(effectiveTurnAction))

    init()
}
validationSplitter.executePipelines().awaitAll()
```

`buildValidator` (player legality) and `buildRailroadAgent` (narrative
hijack) run in parallel under one `validationSplitter`. Railroad result
drives an `act-of-god-points` side-effect; validator result drives a
legality-driven rectification pass downstream.

### Pattern B — Chained gate-then-repair (Pipeline)

When a validator failure must be repaired before the next phase, chain
pipes with `Pipeline.add(p1).add(p2)`. Each pipe's
`setValidatorPipe(...) + setBranchPipe(...)` provides its own
gate/fallback.

**Autogenesis example** (`validateAction/validator.kt:809-813`):

```kotlin
return Pipeline().apply {
    add(legalityCheckerPipe)
    add(legalityRectifierPipe)
    add(styleReapplyPipe)
}
```

Three-stage pipeline: `legalityCheckerPipe` → `legalityRectifierPipe`
→ `styleReapplyPipe`. The rectifier's `setPreInvokeFunction` returns
`false` to skip rectification when the prior pipe's result was already
legal (`validator.kt:639-664`). The `setTransformationFunction` on each
pipe reshapes the output (`Legal?` → text-only) before the next pipe
sees it.

## Per-orchestrator invocation map

### Player turn — `server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt`

| Validation pipe | Defined at | Invoked at | What it gates |
|---|---|---|---|
| `buildValidator(player)` | `validateAction/validator.kt:86` | `gameplayOrchestrator.kt:390` (Splitter) | Full player action legality — 3-pipe Pipeline: `legalityCheckerPipe` (validator+branch Palmyra), `legalityRectifierPipe`, `styleReapplyPipe`. Captures `captureAttempted` flag. |
| `buildRailroadAgent()` | `validateAction/railroadAgent.kt:20` | `gameplayOrchestrator.kt:426` (Splitter sibling to validator) | Detects narrative railroading → returns `TrueFalse`. Validator+branch at lines 67-80. |
| `buildPlayDetectionAgent(actor)` | `validateAction/identifyPlayAgent.kt:44` | `gameplayOrchestrator.kt:1025, 1190` | Classifies play type. No `setValidatorPipe`/`setBranchPipe`. |
| `buildTargetDetectorAgent(actor)` | `validateAction/targetDetectorAgent.kt:381` | `gameplayOrchestrator.kt:1129, 1525` | Resolves target entities. Uses internal `buildTargetRefinementPipe`; no TPipe slot primitives. |
| `buildCounterResponseIntentDetector(responseText)` | `validateAction/counterResponseIntentDetector.kt:38` | `gameplayOrchestrator.kt:1190` | Detects counter-play. Plain `BedrockMultimodalPipe`, no slot primitives. |
| `buildDefensiveValidator(def, atk, atkAction)` | `validateAction/defensiveValidator.kt:36` | `gameplayOrchestrator.kt:1472` (cascade def.) | 2-pipe Pipeline for defender responses: `defensiveLegalityCheckerPipe` + `defensiveRectifierPipe`; each has its own validator (TPipe) and branch (Palmyra template). |
| `buildPassFailAgent(player)` | `passFailAgent/passFailAgent.kt:33` | `gameplayOrchestrator.kt:728, 1849` | Single-pipe Pipeline `passOrFailPipe` (returns `Victory?`); uses `buildTPipeValidatorPipe` + Palmyra `buildBranchPipeFromTemplate` (lines 278-296). |
| `buildResourceUsageDetectorAgent(player, action)` | `validateAction/resourceUsageDetectorAgent.kt:36` | `gameplayOrchestrator.kt:743, 1872` | Uses **inline `setValidatorFunction`** (refusal/JSON check, lines 88-107) + custom `buildResourceFallbackPipe` as branch (line 110). |

### NPC turn — `server/src/main/kotlin/agent/runners/npcOrchestrator.kt`

| Validation pipe | Defined at | Invoked at | What it gates |
|---|---|---|---|
| `buildNPCValidator()` | `validateAction/npcValidationAgent.kt:35` | `npcOrchestrator.kt:394` | 3-pipe Pipeline: `npcLegalityCheckerPipe`, `npcLegalityRectifierPipe`, `npcStyleReapplyPipe`; each pipe uses `buildTPipeValidatorPipe` + `buildBranchFailureAgent`. |
| `buildDefensiveValidator(defender, attacker, action)` | `validateAction/defensiveValidator.kt:36` | `npcOrchestrator.kt:1371` | Same as player orchestrator — for NPC defender responses. |

### NPC adjudication — `server/src/main/kotlin/agent/builders/judgeOutcome/`

| Validation pipe | Defined at | What it gates |
|---|---|---|
| `buildPassFailAgent` (npcJudge uses judge.kt's shape) | `judgeOutcome/judge.kt:288, 313` + `judgeOutcome/npcJudge.kt:178, 185, 489, 496, 570, 577` | 3-step NPC turn adjudicator. `judge.kt` uses `buildTPipeValidatorPipe` + `buildBranchFailureAgent` / `buildBranchPipeFromTemplate`. `npcJudge.kt` uses the **private inline** `buildPalmyraFallbackAgent` factory (npcJudge.kt:81) for all three branch pipes — each called with the same instruction template but a distinct pipeName (`"Refusal Detection Pass/Fail"`, `"Refusal Detection Gains/Losses"`, `"Refusal Detection Karma"`). |

## Modifier / gameplay pipes that also use validator+branch pairs

These are scattered across the `modifyGameState`, `gameplayActions`,
`gatherContext`, `systemActions`, `writingAgent`, `lorebook` directories.
Each pipe that calls `setValidatorPipe(...)` immediately calls
`setBranchPipe(...)`.

| File | Validator pipe line(s) | Branch pipe line(s) | Pattern |
|---|---|---|---|
| `modifyGameState/actOfGodAgent.kt` | 72 | 74 | TPipe validator + `buildBranchFailureAgent` |
| `modifyGameState/reverseAgent.kt` | 150 | 205 | Local `validatorPipe` + local `repairPipe` (custom Bedrock pipes) |
| `modifyGameState/hardenAgent.kt` | 169 | 205 | TPipe validator + local `fallbackPipe` (custom) |
| `modifyGameState/worldupdates.kt` | — | 110 | `buildBranchFailureAgent` only |
| `modifyGameState/resourcedispatcher.kt` | — | 203 | `buildBranchFailureAgent` only |
| `modifyGameState/nemesisCreationBuilder.kt` | 190, 300, 399 | 215, 329, 432 | TPipe validator + `buildBranchFailureAgent` (3 stages) |
| `gameplayActions/elderGodAgent.kt` | 221 | 228 | TPipe validator + `buildBranchFailureAgent` |
| `gameplayActions/nemesisAgent.kt` | 163, 271 | 165 (inline Bedrock + Palmyra), 276 (`buildBranchFailureAgent`) | TPipe validator + branch (one inline, one via factory) |
| `gameplayActions/npcActorAgent.kt` | 101 | 105 | TPipe validator + `buildBranchFailureAgent` |
| `gameplayActions/npcHostileAgent.kt` | 148 | 154 | TPipe validator + `buildBranchFailureAgent` |
| `gatherContext/newcharacterscan.kt` | 673 | 304, 485, 583, 678, 862 (5 branch sites) | TPipe validator + `buildBranchPipeFromTemplate` (PalmyraX5) |
| `gatherContext/affectedPlayerAgent.kt` | — | 97 | `buildBranchFailureAgent` only |
| `systemActions/UserActionClassificationAgent.kt` | 197 | 199 | TPipe validator + `buildBranchPipeFromTemplate` (PalmyraX5) |
| `writingAgent/writerAgent.kt` | — | 429 | Local `branchPipe` (not via factory) |
| `lorebook/lorebookAgent.kt` | — | 164 | Local `branchPipe` (not via factory) |

## Verification recipes

```bash
# Find every validator/branch slot site in the server module
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
rg -n "setValidatorPipe\(|setBranchPipe\(" server/src/main/kotlin/ --type kotlin

# Find every invocation of the three production factories
rg -n "buildTPipeValidatorPipe\(|buildBranchFailureAgent\(|buildBranchPipeFromTemplate\(" \
    server/src/main/kotlin/ --type kotlin

# Find every invocation of the in-house variants
rg -n "buildResourceFallbackPipe\(|buildPalmyraFallbackAgent\(" \
    server/src/main/kotlin/ --type kotlin
```

## Lessons learned this session

1. **TPipe has TWO classes of "attach a gate" mechanism**: a lambda
   (`setValidatorFunction`) and a Pipe-shaped slot
   (`setValidatorPipe(Pipe)`). The skill `tpipe-pipe-internals` already
   documents the lambda; this reference documents the slot.

2. **The slot is a separate execution lane** — it has its own model,
   region, token budget, reasoning pipe, and DITL hooks. The
   `copyFunctions` flag on `buildBranchPipeFromTemplate` controls
   whether DITL hooks are copied forward; without it, the branch pipe
   runs without the host's pre/post hooks.

3. **There is no `BranchBuilder` class**. The "branch tree" is a graph
   of plain Pipes attached via the slot pattern. Multiple fallbacks
   are expressed by chaining (branch's branch is another branch) or
   by retries inside the branch's `transformationFunction`.

4. **The Autogenesis codebase uses two composition patterns**:
   Splitter (parallel validators) and Pipeline (chained
   gate-then-repair). The slot pattern operates AT THE PIPE LEVEL,
   inside either pattern.

5. **Branch outputs replace host outputs ONLY if the branch sets
   `passPipeline = true` on the returned content.** The Autogenesis
   Palmyra fallback at `npcJudge.kt:107-115` sets the flag explicitly;
   the generic `buildBranchPipeFromTemplate` does not.