---
name: tpipe-agent-architecture
description: "TPipe agent architecture in production: 3-layer convention."
version: 1.0.0
metadata:
  hermes:
    tags: [tpipe, agent, architecture, builder-pattern, orchestrator, coroutines, autogenesis, production-example]
    related_skills: [tpipe-pipeline-patterns, tpipe-pipe-feature-audit, tpipe-reasoning-pipes, tpipe-context-budget-truncation, autogenesis-prompt-debugging]
---

# TPipe Agent Architecture in Production

A TPipe agent is not a class — it is a convention. Across production codebases (the canonical example is the Autogenesis server with 30+ agents), the shape is the same: a top-level `fun build<AgentName>(...): Pipeline` builder function returns a `Pipeline` of 1–N pipe instances wired via `.apply { }` blocks; a runner function calls those builders in sequence under coroutines + a state-mutation mutex. There is no `Agent` base class, no `AgentFactory`, no marker interface. The convention IS the framework.

This skill captures the architectural convention at class level — what every TPipe-backed production codebase does, why, and where the seams are.

## The 3-layer convention

```
Layer 1 — Builder functions    (agent/builders/<group>/<Agent>.kt)
Layer 2 — Pipes + Pipelines    (BedrockMultimodalPipe / GenericOpenAIPipe composed into Pipeline)
Layer 3 — Runners              (agent/runners/<Orchestrator>.kt — coroutine sequences over builders)
```

The builder returns the assembled pipeline. The runner consumes the pipeline. Pipes never call each other across layers — they hand a `MultimodalContent` to the next pipe in their own pipeline. The orchestrator never instantiates pipes — it calls `build<AgentName>(...)` and treats the result as opaque.

## Layer 1 — The builder function

Every agent is a top-level function:

```kotlin
fun buildUserActionClassificationPipeline(): Pipeline {
    val pipeline = Pipeline()

    val classificationPipe = GenericOpenAIPipe().apply {
        setBedrockMantle(region = ..., modelId = ...)
        setTemperature(0.5)
        setTopP(0.7)
        setTokenBudget(BedrockConfig.e2bBudgetSettings)
        requireJsonPromptInjection()
        setJsonOutput(UserActionClassification(ActionType.QUESTION, 0.0, ""))
        setReasoningPipe(createExplicitCotPipe())
        setValidatorPipe(buildTPipeValidatorPipe(systemPrompt))
        setValidatorFunction(::validateClassificationResult)
        setBranchPipe(/* fallback pipe on a different model */)
        setSystemPrompt(systemPrompt)
        setPipeName("user action classifier")
        enableTracing()
    }

    pipeline.add(classificationPipe)
    return pipeline
}
```

### The standard kit (most builders chain 12+ of these)

| Call | Why it shows up | Optional? |
|---|---|---|
| `useConverseApi()` | BedrockConverse path; needed for tool use / citations / Converse-only features | Yes, but the default Invoke path loses tool/citation support |
| `setRegion(...)` / `setBedrockMantle(region, modelId)` | Provider host binding | Required |
| `setModel(...)` / `setBedrockMantle(..., modelId)` | Model selection. The argument is a `String` from `BedrockConfig.<model>`, NOT a Kotlin enum | Required |
| `setTemperature(...)` + `setTopP(...)` | Sampling control. Almost always paired (e.g. `0.6/0.7`, `0.5/0.7`, `1.0/0.9`) | Required |
| `setTokenBudget(BedrockConfig.<...>BudgetSettings)` | Per-pipe context budget. The argument is a project-level `TokenBudgetSettings` constant | Required |
| `setServiceTier(BedrockPriorityTier.Flex/Standard)` | Bedrock priority tier. Default Standard; Flex is opt-in per pipe role | Optional |
| `setReasoningPipe(<reasoning pipe>)` | Pre-process input through a thinking model before the main pipe fires. The reasoning pipe is itself a `BedrockMultimodalPipe` (or generic), built via `BedrockConfig.authorBuilder(...)` with a `ReasoningDepth` + `ReasoningDuration` | Strongly recommended for any non-trivial task |
| `setJsonOutput(<@Serializable data class>())` | The schema the LLM is told to return via prompt injection. The Kotlin type is the contract — `extractJson<T>()` parses the result | Required when output is structured |
| `setJsonInput(<...>())` | If the LLM is given structured input | Optional |
| `requireJsonPromptInjection()` | Forces the schema to be appended to the system prompt verbatim. Combined with `setJsonOutput` | Required when output is structured |
| `allowEmptyContentObject()` / `allowEmptyUserPrompt()` | Defensive flags for inputs that may be empty (e.g. when the parent pipe fails) | Optional |
| `setValidatorPipe(<validator pipe>)` | A separate small pipe that judges whether the main pipe fulfilled its task. This is the LLM-as-judge layer | Recommended for high-stakes decisions |
| `setValidatorFunction { content -> ... }` | A Kotlin-function validator (post-parse). For schema/contract checks. Often paired with `setValidatorPipe` (the pipe runs first; the function runs after extraction) | Recommended for any structured output |
| `setBranchPipe(<fallback pipe>)` | A second pipe on a DIFFERENT model used if the primary fails. The two pipes share the same `MultimodalContent` input and produce independent outputs | Recommended for any production agent |
| `setSystemPrompt(...)` | The system prompt. Often a multi-thousand-character instruction block with embedded guardrail prompts | Required |
| `setPipeName(...)` | Human-readable name. Appears in traces, logs, kill-switch reports. Use a sentence fragment, not an identifier | Required |
| `enableTracing()` | Pipe-level tracing for `PipeTracer.exportTrace(...)`. Every pipe in production has this | Required |
| `pullGlobalContext()` / `setPageKey(...)` / `forceSaveSnapshot()` | ContextBank integration — see `tpipe-context-budget-truncation` for the merge-order contract | Optional, depends on context needs |

A builder that uses only 5 of these calls is probably too small (missing reasoning/validator/branch) or too large (one builder doing what should be 3+).

### The reasoning pipe — its own `BedrockMultimodalPipe`

`setReasoningPipe(...)` takes a fully-built pipe. The reasoning pipe has its own model, temperature, budget, system prompt — it is not a property copy from the parent. The Autogenesis convention is to use a `BedrockConfig.<X>Builder(...)` factory:

```kotlin
setReasoningPipe(
    BedrockConfig.explicitCotBuilder(
        depth = ReasoningDepth.High,
        duration = ReasoningDuration.Short
    )
)
```

Where `explicitCotBuilder(...)` returns a fresh `BedrockMultimodalPipe` configured for explicit chain-of-thought reasoning. See `tpipe-reasoning-pipes` for the full factory surface.

### The validator pipe — an LLM-as-judge layer

`setValidatorPipe(buildTPipeValidatorPipe(systemPrompt))` builds a SEPARATE small pipe that takes the main pipe's output as input and returns a True/False judgment on whether the main pipe fulfilled its task. This is the most surprising element of the convention for first-time readers: production agents run TWO LLM calls per turn (main + validator) for any decision worth checking.

```kotlin
val validatorPipe = BedrockMultimodalPipe().apply {
    useConverseApi()
    setRegion("us-west-2")
    setModel(BedrockConfig.qwenCoder30B)
    setTokenBudget(BedrockConfig.generativeBudgetSettings)
    setTemperature(0.6)
    setTopP(0.7)
    requireJsonPromptInjection()
    setJsonOutput(TrueFalse())
    setSystemPrompt("""
        You are a validation pipe. Your job is to validate your input which was created
        from a prior agent. And determine if it fulfilled its designed task. ...
    """.trimIndent())
    setValidatorFunction { content ->
        extractJson<TrueFalse>(content.text)?.isTrue ?: false
    }
}
```

The main pipe also gets a `setValidatorFunction { ... }` for post-parse schema/contract checks. The two validators run in sequence: pipe first, function second.

### The branch pipe — same schema, different model

`setBranchPipe(...)` is a SECOND main pipe on a different model that gets invoked when the primary fails. Same `setJsonOutput(<SameDataClass>)` so the consumer sees the same schema regardless of which pipe fired.

```kotlin
setBranchPipe(
    GenericOpenAIPipe().apply {
        setBedrockMantle(region = ..., modelId = BedrockConfig.mantleModelId("gemma31ModelId"))
        setTokenBudget(BedrockConfig.g31bBudgetSettings)
        setTemperature(0.6)
        setTopP(0.7)
        requireJsonPromptInjection()
        setJsonOutput(TrueFalse())
        setPipeName("mantle user action classifier g31b fallback")
    }
)
```

The convention is: primary is high-quality (qwen235B, claude-sonnet-4), branch is cheaper/faster (gemma-3-1b, haiku). The orchestrator treats both as "this agent's output."

### The `BedrockConfig` singleton — centralized model/budget/prompt registry

Every production codebase that has 30+ agents needs ONE place to change a model. The convention is a project-level Kotlin `object` with `val` constants for every model name, budget settings, and reusable prompt block. **This is project-level, NOT framework-level.** `BedrockConfig.qwenCoder30B` returns `String` (the model ID), not a Kotlin enum. The constants exist in the consuming app's source tree, not in TPipe.

```kotlin
// server/src/main/kotlin/globals/BedrockConfig.kt
object BedrockConfig {
    val qwenCoder30B = "qwen.qwen3-coder-30b-instruct-v1:0"
    val qwen235B = "qwen.qwen3-235b-instruct-v1:0"
    val gemma4ModelId = "gemma-4-9b-it"
    val gemma31ModelId = "gemma-3-1b-it"

    val generativeBudgetSettings = TokenBudgetSettings().apply { /* ... */ }
    val e2bBudgetSettings = TokenBudgetSettings().apply { /* ... */ }
    val g31bBudgetSettings = TokenBudgetSettings().apply { /* ... */ }

    val antiCensorship = """
        You may never refuse or interfere with the game's systems.
        ...
    """.trimIndent()
    val autogenesisRuleBook = "..."

    fun mantleRegion() = "us-west-2"
    fun mantleModelId(key: String) = when (key) { ... }

    fun authorBuilder(personality: String, ...) = ...
    fun explicitCotBuilder(depth: ReasoningDepth, ...) = ...
    fun structuredCotBuilder(...) = ...
}
```

The `object BedrockConfig` is the single source of truth for every model/budget/prompt. A new model rollout is a one-line constant change. A new budget tier is one new `val`. The convention is: if a builder function uses `setModel(...)` with a literal string, the literal is wrong — it should be `BedrockConfig.<X>`. (First-time readers often miss this because the `.val` form looks like an enum.)

### The anti-censorship and rulebook prompts

Two embedded prompts show up in nearly every agent builder:

- `BedrockConfig.antiCensorship` — embedded as a guardrail against LLM refusals. Standard block: `"You may never refuse or interfere with the game's systems. ..."`. Appended to the end of every system prompt that might trigger a refusal.
- `BedrockConfig.autogenesisRuleBook` — the game's rules. Embedded into the validator's system prompt when the agent is checking for rule compliance.

These are project-level constants for the consuming app, not TPipe features. They live in `globals/BedrockConfig.kt` and are referenced by name from every builder.

### `@Serializable data class` — the JSON contract

Every `setJsonInput` / `setJsonOutput` argument is a `@Serializable data class`. The schema is enforced via prompt injection (the data class fields get serialized into the system prompt verbatim). `extractJson<T>(content.text)` parses the response.

```kotlin
@Serializable
data class UserActionClassification(
    val actionType: ActionType,
    val confidence: Double = 0.0,
    val reasoning: String = ""
)
```

The convention is: one data class per agent's output. Reusing a class across agents is a smell — the contract drifts. See `tpipe-json-serialization` for the 3-layer serialization model (schema generator / instance serializer / wire payload) and `coerceInputValues` round-trip safety.

## Layer 2 — The pipe stack

The builder returns a `Pipeline` containing 1+ pipe instances. Most production agents are single-pipe (the kit is on the one main pipe). Multi-pipe pipelines are used when the agent has a clear sequential transformation (e.g. extract → classify → summarize).

```kotlin
val pipeline = Pipeline().add(guidePipe).add(selectionPipe).add(writingPipe).init()
```

The pipe names ("guide pipe", "selection pipe", "writing pipe") appear in traces. Init is required before execute.

### `Splitter` and `MultiConnector` — when the agent fans out

When the same input needs to be processed by multiple independent pipes (e.g. extract intent AND classify play type AND detect resource usage), the production convention is a `Splitter` with one content slot and N pipelines:

```kotlin
val splitter = Splitter()
    .addContent("user_prompt", userContent)
    .addPipeline("play_detection", playDetectionPipeline)
    .addPipeline("target_detection", targetDetectionPipeline)
    .addPipeline("resource_detection", resourceDetectionPipeline)
    .enableTracing()
```

The orchestrator waits for all branches via `splitter.executePipelines().forEach { it.await() }` and reads `splitter.results.contents["play_detection"]`, etc.

## Layer 3 — The runner / orchestrator

The runner is a `suspend fun` (or coroutine scope entry point) that calls builders in sequence and handles retries, progress hooks, state mutation. The Autogenesis `gameplayOrchestrator.kt` is 2811 lines and runs 12 phases per turn:

1. **Classify** the user action (play / question / UI / chat) via `buildUserActionClassificationPipeline`
2. **Detect play type** (hostile / friendly / research / etc.) via Splitter of multiple detection agents
3. **Validate** the action against rules via `buildValidator`
4. **Gather context** (territories, NPCs, world state) via Splitter of gatherers
5. **Judge outcome** via `buildJudge` (a 121KB pipe — the heaviest single agent)
6. **Write narrative** via the 3-pipe WriterAgent (guide → selection → writing)
7. **Apply world updates** via `worldUpdatesPipeline`
8. **Mutate state** under `WorldManager` mutex
9. **Stream narrative to UI** via `streamPipelineOutputToAgentWorkBuffer`
10. **Emit RPC signals** via `UiSignalRpcHandlers`
11. **Persist** to CloudSave via AccelByte SDK
12. **Update audio track state**

Each phase is `await`-ed. Phases that don't depend on each other run in parallel under `coroutineScope { val a = async { ... }; val b = async { ... }; a.await(); b.await() }`.

### `AgentCoroutineScope` — the shared coroutine scope

```kotlin
// agent/builders/AgentCoroutineScope.kt
object AgentCoroutineScope {
    val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
}
```

A single application-wide coroutine scope with a supervisor job (one failing builder does not cancel siblings). `Dispatchers.Default` for CPU-bound LLM pipe orchestration. Used by builders that need to run parallel pipes without holding the orchestrator's coroutine.

### `WorldManager` mutex — state-mutation serialization

Every state mutation goes through a mutex so two concurrent turns do not corrupt the world:

```kotlin
WorldManager.withMutex {
    world = world.copy(territories = updatedTerritories)
    serializeWorldForCloudSave(world)
}
```

The mutex is held for the duration of the state-mutation phase (8-12 above). It is NOT held during LLM calls (those are read-only against the world snapshot taken at phase 4). Holding the mutex during LLM calls would serialize turns and defeat the parallelism.

### Progress hooks — broadcasting pipe lifecycle to UI

The orchestrator hooks pipe-lifecycle events to broadcast real-time status to the client:

```kotlin
private val pipeProgressMap = mapOf(
    "Play Detection Agent" to "Analyzing player intent...",
    "resource detection pipe" to "Verifying asset usage...",
    "user action classifier" to "Classifying your action...",
    // ... 30+ entries
)
```

Each entry maps a pipe name (set via `setPipeName(...)` in the builder) to a user-facing progress string. The orchestrator listens to `pipe.onPhaseStart` / `pipe.onPhaseEnd` events and emits RPC messages keyed by pipe name. The convention is: pipe names are sentence fragments the user will read, not identifiers.

### Timeouts and retries

Every pipe call is wrapped:

```kotlin
withTimeoutOrNull(180_000) { pipe.execute(content) }
    ?: throw TimeoutException("pipe ${pipe.pipeName} exceeded 180s")
```

The standard is **3 minutes / 5 retries** (`enablePipeTimeout`). Per-pipe retry counters are tracked in `AgentRetry` struct; orchestrator-level retries are handled by a parent loop that swaps the model on subsequent attempts.

### Failure function / DITL hooks

The runner-level `failureFunction` (passed to `Manifold` containers) is the developer-in-the-loop escape hatch — when a builder fails irrecoverably, the failure function decides whether to retry, swap models, escalate to a different orchestrator phase, or surface the error to the user. See `tpipe-ditl-hook-design` for the field/setter/invocation contract.

## Standard anti-patterns

### Anti-pattern 1 — builder that returns a `Pipe` instead of a `Pipeline`

The runner calls `pipeline.execute(content)`. A builder that returns a single `Pipe` breaks the contract. The fix is `Pipeline().add(pipe)` wrapping — even when there's only one pipe. This keeps the runner's `pipeline.execute(...)` call site uniform across 30+ agents.

### Anti-pattern 2 — pipe names as identifiers

```kotlin
// BAD
setPipeName("classifier")

// GOOD
setPipeName("user action classifier")
```

The name appears in trace dumps, kill-switch reports, progress broadcasts. "user action classifier" tells the operator what failed; "classifier" tells them nothing.

### Anti-pattern 3 — embedding literal model strings in builders

```kotlin
// BAD
setModel("qwen.qwen3-coder-30b-instruct-v1:0")

// GOOD
setModel(BedrockConfig.qwenCoder30B)
```

The convention is: every model name lives in `BedrockConfig.<X>`. A new model rollout is a one-line constant change. A literal string in a builder is a marker of work that was rushed through without the standard kit.

### Anti-pattern 4 — sharing a `setJsonOutput` data class across agents

```kotlin
// BAD
setJsonOutput(LegalResult())  // used by 4 agents

// GOOD
@Serializable data class ClassificationResult(...) // one per agent
```

When two agents share a class, the next schema change breaks both. The class IS the contract; one per agent.

### Anti-pattern 5 — calling `extractJson` in the builder

The builder returns a `Pipeline`. Parsing the response happens at the consumer (the runner). The builder does `setValidatorFunction { content -> extractJson<T>(content.text)?.<check> }` for validation but does not extract for return. Exceptions: builders that pre-validate AND re-serialize (rare).

### Anti-pattern 6 — holding the WorldManager mutex during LLM calls

The mutex is for state mutation, not for LLM orchestration. Holding it during a 30-second pipe.execute(...) call serializes all turns and is the #1 cause of "the game feels slow" reports. Take a world snapshot at the start of the turn (under mutex), release the mutex, run all LLM calls against the snapshot, re-acquire the mutex only to commit the final world state.

### Anti-pattern 7 — orchestrator that doesn't `enableTracing`

Every pipe in production has `enableTracing()` in the builder. The orchestrator reads trace events for progress hooks, kill-switch reporting, debug dumps. A pipe without tracing is invisible to the operator.

## When this skill applies

Use this when:

- Designing a new TPipe-backed agent. The kit list above is the menu; almost every agent uses 12+ of the 19 calls.
- Auditing an existing app's agent pattern. Compare against the kit list; missing `setValidatorPipe` / `setReasoningPipe` / `setBranchPipe` is a smell.
- The orchestrator has concurrency bugs. The `AgentCoroutineScope` + `WorldManager` mutex pattern is the production convention; deviations are the bug source.
- Centralizing model/budget/prompt references. The `BedrockConfig` object is the convention; an app that doesn't have one will grow 30 copies of every model string.
- Onboarding a new contributor to a TPipe-backed codebase. The 3-layer convention is the mental model.

## When NOT to use this

- Pipe-level configuration patterns (use `tpipe-pipeline-patterns`)
- Cross-cutting feature propagation audits (use `tpipe-pipe-feature-audit`)
- Lorebook / context mechanics (use `tpipe-lorebook-system`)
- Reasoning-pipe mechanics specifically (use `tpipe-reasoning-pipes`)
- JSON serialization model details (use `tpipe-json-serialization`)
- Prompt-text debugging for a specific app (e.g. autogenesis writer drift — use `autogenesis-prompt-debugging`)

## Reference: the Autogenesis builder directory map

```
agent/builders/
├── AgentCoroutineScope.kt              # the shared coroutine scope
├── validateAction/                     # 11 agents
│   ├── validator.kt                    # 814 lines, legality checker
│   ├── ValidatorPipeAgent.kt           # 226 lines, validator-pipe wrapper
│   ├── BranchFailureAgent.kt           # branch-failure recovery
│   ├── DefensiveValidator.kt           # defensive wrapper
│   ├── railroadAgent.kt                # railroad detection
│   ├── resourceUsageDetectorAgent.kt   # resource-usage detection
│   ├── targetDetectorAgent.kt          # target resolution
│   ├── targetResolution.kt             # target resolver helper
│   ├── identifyPlayAgent.kt            # play-type detection
│   ├── npcValidationAgent.kt           # NPC-side validation
│   └── counterResponseIntentDetector.kt
├── systemActions/                      # 5 agents
│   ├── UserActionClassificationAgent.kt  # 213 lines, REFERENCE EXAMPLE
│   ├── answerAgent.kt                  # 431 lines, Q&A responder
│   ├── chatAgent.kt
│   ├── characterAgent.kt
│   └── OpenWidgetAgent.kt
├── judgeOutcome/                       # outcome resolution
│   └── judge.kt                        # 121KB, the heaviest single agent
├── gatherContext/                      # context extraction
│   └── newcharacterscan.kt             # 61KB
├── gameplayActions/                    # NPC generation
│   ├── nemesisAgent.kt
│   ├── elderGodAgent.kt
│   ├── npcActorAgent.kt
│   └── npcHostileAgent.kt
├── modifyGameState/                    # state mutations
│   ├── worldUpdatesPipeline.kt
│   ├── hardenAgent.kt
│   ├── reverseAgent.kt
│   ├── resourceDispatcher.kt
│   └── nemesisCreationAgent.kt
├── writingAgent/                       # 3-pipe pipeline
│   ├── writerAgent.kt                  # guide → selection → writing
│   └── ResponseRefinementAgent.kt
├── playerAgent/
├── passFailAgent/
└── lorebook/
```

Total: 30+ agents across 12 builder directories. Every agent follows the 3-layer convention; the kit list above is what each builder chains.

## Reference files

- `references/autogenesis-builder-canonical-example.md` — annotated walkthrough of `UserActionClassificationAgent.kt` line-by-line, calling out every call from the kit list and why
- `references/agent-coroutine-scope-and-mutex.md` — the `AgentCoroutineScope` + `WorldManager` mutex pattern with the gotchas that bite first-time orchestrators (mutex during LLM calls, snapshot-vs-mutate timing)
- `references/bedrock-config-singleton-pattern.md` — the `BedrockConfig` object structure, the canonical constant names, and the migration recipe for an app that has scattered literal model strings

## See also

- `tpipe-pipeline-patterns` — the configuration pattern side (builder vs scope DSL). This skill covers the agent-kit side.
- `tpipe-pipe-feature-audit` — auditing cross-cutting feature propagation. Different class.
- `tpipe-reasoning-pipes` — reasoning-pipe mechanics (the `setReasoningPipe(...)` half of the kit).
- `tpipe-context-budget-truncation` — the `setTokenBudget(...)` half of the kit and the per-pipe budget pattern.
- `autogenesis-prompt-debugging` — prompt-layer debugging for Autogenesis specifically. Useful when the kit is right but the prompt text is wrong.