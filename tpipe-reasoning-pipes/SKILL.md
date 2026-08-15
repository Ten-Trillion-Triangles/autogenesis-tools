---
name: tpipe-reasoning-pipes
description: "TPipe reasoning pipe system — ReasoningBuilder, ReasoningPrompts, all ReasoningMethod variants, role-play mode, multi-round, cross-provider reasoning. Load when working with setReasoningPipe(), ReasoningSettings, ReasoningBuilder.reasonWithBedrock/reasonWithOllama/reasonWithOpenRouter/reasonWithGenericOpenAI, or any reasoning pipe that pre-processes input through a thinking model before the main pipe. Also use when debugging reasoning injection, choosing a ReasoningMethod for a given problem type, understanding how roleCharacter + depth + duration compose the final reasoning prompt, OR when extending the reasoning-builder factory surface with a new provider."
version: 1.2.0
author: Hermes Agent + Apex
license: MIT
metadata:
  tpipe:
    tags: [tpipe, reasoning-pipes, reasoning-builder, reasoning-prompts, chain-of-thought, role-play, multi-round, openrouter, generic-openai]
    homepage: https://github.com/ten-trillion-triangles/TPipe
---

# TPipe Reasoning Pipes

TPipe's reasoning pipe system runs a dedicated "thinking" model before the main pipe to generate structured reasoning that's injected into the main pipe's context. The main pipe sees the reasoning as a pre-processed enhancement layer, not as part of its own conversation history.

## Core Concepts

### Execution Flow
```
Input → Reasoning Pipe (thinks) → Reasoning content → Injected into Main Pipe → Main Pipe responds
```

### ReasoningSettings — All Config Knobs

```kotlin
data class ReasoningSettings(
    var reasoningMethod: ReasoningMethod = ReasoningMethod.StructuredCot,
    var depth: ReasoningDepth = ReasoningDepth.Med,
    var duration: ReasoningDuration = ReasoningDuration.Med,
    var roleCharacter: String = "You are a helpful assistant.",  // RolePlay only
    var reasoningInjector: ReasoningInjector = ReasoningInjector.SystemPrompt,
    var numberOfRounds: Int = 1,
    var focusPoints: MutableMap<Int, String> = mutableMapOf(),
    var roundDirectives: MutableMap<Int, ReasoningRoundDirective> = mutableMapOf(),
    var injectMiddlePrompt: Boolean = false,
    var injectFooterPrompt: Boolean = false,
    var reinforceSystemPrompt: Boolean = false
)
```

### ReasoningMethod — All Strategies

| Method | What it does | Best for |
|--------|--------------|----------|
| `StructuredCot` | 4-phase framework (analyze→plan→execute→validate) | General problem solving |
| `ExplicitCot` | Step-by-step with clear transitions | Complex logical problems |
| `processFocusedCot` | Methodological justification + adaptive thinking | Process optimization |
| `BestIdea` | Single best idea generation | Quick decisions, brainstorming |
| `ComprehensivePlan` | Substantial multi-phase planning | Strategic planning, roadmaps |
| `RolePlay` | Act as a character reasoning through the problem | Domain expertise simulation |
| `ChainOfDraft` | 5-word max per step, high-signal reasoning | Math, cost-sensitive, low-latency |
| `SemanticDecompression` | Reverse TPipe semantic compression | Compression round trips |

### ReasoningInjector — Where Reasoning Goes

| Injector | Effect |
|----------|--------|
| `SystemPrompt` | Appended to end of main pipe's system prompt |
| `BeforeUserPrompt` | Prepended before user message |
| `AfterUserPrompt` | Appended after user message |
| `BeforeUserPromptWithConverse` | Injected into ConverseHistory block (top) |
| `AfterUserPromptWithConverse` | Injected into ConverseHistory block (bottom) |
| `AsContext` | Injected as context to a designated page key |

### ReasoningDepth — Logical Complexity

- `Low`: 3-5 reasoning steps. Minimal analysis.
- `Med`: 6-10 reasoning steps. Balanced analysis.
- `High`: 10+ reasoning steps. Exhaustive exploration.

### ReasoningDuration — Verbosity

- `Short`: 40-60% of normal length.
- `Med`: 90-110% of normal length.
- `Long`: 150-200% of normal length.

---

## Builder Entry Point

`Defaults.reasoning.ReasoningBuilder.assignDefaults()` — `TPipe-Defaults/.../ReasoningBuilder.kt:163`

This is where the system prompt is built and JSON output type is assigned. Called by every `reasonWith<Provider>()` factory.

**`assignDefaults` is also the only writer of the reasoning-pipe metadata flags that the parent pipe reads at composition time.** Lines 307-319 unconditionally write:

```kotlin
targetPipe.pipeMetadata["reasoningRounds"]        = settings.numberOfRounds
targetPipe.pipeMetadata["focusPoints"]            = settings.focusPoints
targetPipe.pipeMetadata["roundDirectives"]        = settings.roundDirectives
targetPipe.pipeMetadata["injectionMethod"]        = settings.reasoningInjector.toString()
targetPipe.pipeMetadata["reasoningMethod"]        = settings.reasoningMethod.toString()
targetPipe.pipeMetadata["injectMiddlePrompt"]     = settings.injectMiddlePrompt   // Boolean
targetPipe.pipeMetadata["injectFooterPrompt"]     = settings.injectFooterPrompt   // Boolean
targetPipe.pipeMetadata["reinforceSystemPrompt"]  = settings.reinforceSystemPrompt // Boolean
```

If a reasoning pipe is constructed by code that does NOT go through `assignDefaults` (e.g. autogenesis's `BedrockConfig.buildMantleReasoningPipe` builds `GenericOpenAIPipe().setBedrockMantle(...)` directly without calling `assignDefaults`), all eight metadata keys are missing. The parent pipe then crashes when it reads `injectMiddlePrompt` or `injectFooterPrompt` as Boolean on an absent key — see Pitfall 7.

Key line at 256: `targetPipe.requireJsonPromptInjection()` — forces structured JSON output from the reasoning pipe.

## Provider Factories — The Cross-Provider Surface

`Defaults.providers.<Name>Defaults` objects (`TPipe-Defaults/src/main/kotlin/Defaults/providers/`) own the provider-specific constructor. `ReasoningBuilder.reasonWith<Provider>()` simply calls the factory then hands the result to `assignDefaults`:

```
ReasoningBuilder.reasonWithBedrock        -> BedrockDefaults.createBedrockPipe             -> assignDefaults
ReasoningBuilder.reasonWithOllama         -> OllamaDefaults.createOllamaPipe               -> assignDefaults
ReasoningBuilder.reasonWithOpenRouter     -> OpenRouterDefaults.createOpenRouterPipe       -> assignDefaults
ReasoningBuilder.reasonWithGenericOpenAI  -> GenericOpenAIDefaults.createGenericOpenAIPipe -> assignDefaults
```

Each factory takes a typed configuration dataclass (`BedrockConfiguration`, `OllamaConfiguration`, `OpenRouterConfiguration`, `GenericOpenAIConfiguration`) declared as a sealed-class member of `Defaults.ProviderConfiguration` in `TPipe-Defaults/src/main/kotlin/Defaults/ProviderConfiguration.kt`.

## Adding a New Provider to the Reasoning Builder — Established Spec

When the user asks for `reasonWith<NewProvider>` next to the four existing factories, the spec is fixed. Four files, additive only:

1. **`TPipe-Defaults/build.gradle.kts`** — add `implementation(project(":TPipe-<NewProvider>"))` next to the four existing provider lines (`:TPipe-Bedrock`, `:TPipe-Ollama`, `:TPipe-OpenRouter`, `:TPipe-GenericOpenAI`). Without this Gradle dep, the source set cannot import the provider's pipe class.

2. **`TPipe-Defaults/src/main/kotlin/Defaults/ProviderConfiguration.kt`** — add a `<NewProvider>Configuration` data class as a sealed member of `ProviderConfiguration`, mirroring `OpenRouterConfiguration`/`GenericOpenAIConfiguration` shape (model + API key or credentials + provider-specific knobs + `pipeCount` + `manifoldMemory` + `validate(): Boolean`). The consumer-facing surface.

3. **`TPipe-Defaults/src/main/kotlin/Defaults/providers/<NewProvider>Defaults.kt`** — new file, internal object, `create<X>Pipe(config)` returns a fully-wired pipe. Mirror `OpenRouterDefaults.kt:66-103` for the chained-setX() pattern with `apply { }`. This is where provider-specific knobs get applied.

4. **`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt`** — append a new function next to the four existing ones:

```kotlin
fun reasonWith<NewProvider>(
    config: <NewProvider>Configuration,
    reasoningSettings: ReasoningSettings,
    pipeSettings: PipeSettings?
): Pipe {
    val providerPipe = <NewProvider>Defaults.create<X>Pipe(config)
    assignDefaults(reasoningSettings, pipeSettings, providerPipe)
    return providerPipe
}
```

The function takes `PipeSettings?` (nullable) to match the established contract — null means "don't apply baseline settings, just bootstrap the reasoning defaults."

KDoc on every public function is mandatory per `apex-coder` style. Test with a `Defaults.reasoning.ReasoningBuilderProviderFactoriesTest`-style file that pins round-trip of `reasoningMethod` / `injectionMethod` / `reasoningRounds` into `pipeMetadata` (see pitfalls 1 and 2 below).

Do NOT introduce an invented mirror typealias, enum, or stub to soften an unsatisfied dependency on the provider package. The public surface stays in `Defaults`, the implementation surface stays in the provider module — keep the boundary clean.

## Field-Order Railroad — The Schema Is the Program

This is the architectural pattern that makes reasoning pipes deterministic. The LLM predicts tokens left-to-right. Kotlin serializes data class fields in declaration order. Therefore: the order of fields in the response data class is the order of commitments in the model's prediction.

The first field the model fills in constrains every field that comes after. Put boolean and integer commitments at the top of every response data class. Put hallucination-prone content fields at the bottom. The schema structurally prevents the model from reaching the rich content fields before it has committed to a position on the preconditions.

### The `doesLegendExist` pattern — anti-hallucination via boolean commitment

From `src/main/kotlin/Structs/ModelReasoning.kt:454-467`:

```kotlin
data class LegendAnalysis(
    var doesLegendExist: Boolean = false,        // First — forces the commitment
    var codesFound: List<String> = listOf(),    // Constrained by the boolean above
    var mappings: List<String> = listOf()       // Same
)
```

The source comment is the documentation: "Top labeled boolean used to force the llm to predict against weather there is or is not a legend present at all. This is required because without this smaller models tend to just hallucinate values to fulfil the desire to have non-empty values in the json output. But by forcing it to acknowledge that no legend exists when it's empty, it should prevent the hallucinated values from appearing."

Without the boolean, a smaller model receives a compressed prompt with no legend block, gets told to fill in JSON, and hallucinates non-empty `codesFound` and `mappings` lists just to satisfy the desire to fill the schema. With the boolean, the model commits `doesLegendExist: false` first. The lists stay empty as a structural consequence.

### Other reasoning methods — same railroad, different track

Every reasoning method's data class encodes its reasoning order through field order:

- `StructuredCot`: `componentIdentification` → `solutionDecomposition` → `systematicExecution` → `reasoningSynthesis`. Model commits to identifying components before decomposing. Cannot skip decomposition.
- `MethodActorResponse` (RolePlay): `characterProfile` → `problemView` → `inCharacterThinking` → `characterSolution` → `signatureStyle`. Character is locked in before the problem is even seen.
- `MultiPhasePlan` (ComprehensivePlan): `analysis` (with limitations/constraints) → `phases` (each with risks/mitigations/backups) → success metrics. Cannot propose phases without first acknowledging constraints. A happy-path plan is structurally impossible.
- `ChainOfDraftResponse`: `problemAnalysis` (5 words max) → `draftSteps` (5 words max each) → `finalCalculation` (5 words max) → `answer`. The token ceiling is structural, not prompt-based. 75% token reduction vs standard CoT, 78% latency reduction in production.
- `SemanticDecompressionResponse`: `legendAnalysis` → `contentIdentification` (with hypotheses/evidence/selectedInterpretation) → `taskIdentification` → restored content. The content identification gate cannot be skipped — the model must enumerate hypotheses and evidence before it can identify the task.

### Portable pattern (not just Kotlin)

The technique works in any typed-schema language:
- **Python Pydantic**: `Field(default=False)` booleans at the top of the model. Generate schema with `model_json_schema()`. Pydantic preserves declaration order in the generated JSON schema.
- **TypeScript Zod**: declare `z.boolean()` fields first. Generate schema with `zod-to-json-schema`. Zod preserves declaration order.
- **JSON Schema directly**: order `properties` keys by hand. Most generators preserve insertion order.

### The "no nulls" instruction in the prompt

`Pipe.kt:1944-1954` injects explicit output rules into the system prompt:

> "Never use null as a value — instead provide appropriate default values: empty strings for text fields, empty arrays for lists, empty objects for nested structures, 0 for numbers, and false for booleans."

That `false` for booleans is the default commitment the model is railroaded toward. Same trick as the field-order pattern — the instructions and the schema work together to constrain the model into the right shape.

### How to verify the pattern works

Test the field-order hypothesis explicitly: move the boolean to the bottom of the data class, re-run the same test, watch hallucinations return. Move it back to the top, watch them disappear. The order of fields in the JSON schema is doing real work. The prompt wording is not. Add a test that pins field order so refactors don't break the contract.

## Subsystem Boundaries

**Reasoning pipes are NOT part of Developer-in-the-Loop (DITL).** DITL is a separate subsystem with its own docs and mechanisms. Reasoning pipes are a separate subsystem focused on pre-processing input through a thinking model and producing structured JSON output. When writing copy, blog posts, or architectural documentation about TPipe, do not conflate the two. They sit alongside each other as separate intervention mechanisms, not as components of one system.

- Reasoning pipes: `TPipe-Defaults/.../reasoning/`, `Structs/ModelReasoning.kt`
- DITL pipes: `TPipe-Defaults/.../developer-in-the-loop/`, separate docs at `/docs/core-concepts/developer-in-the-loop/` and `/docs/core-concepts/developer-in-the-loop-pipes/`

## JSON Schema Ordering as Determinism Lever

The reasoning data classes are not just response shapes. They are **control mechanisms** that exploit the LLM's left-to-right token prediction to force commitments before hallucination-prone fields are emitted.

**The principle:** Kotlin serializes data class fields in declaration order. The LLM sees the JSON schema in that order and predicts tokens left-to-right. The first field is the first commitment. Position is the mechanism, not the prompt.

**The canonical example:** `LegendAnalysis.doesLegendExist` in `ModelReasoning.kt:464`. The KDoc on the field literally explains the trick — a single boolean at the top of the class forces the LLM to acknowledge whether a legend exists before emitting any codes or mappings, which kills the "desire to have non-empty values" hallucination in smaller models.

**The pattern repeats across every response class:**

| Response Class | First Field (Commitment) | Locks In |
|---|---|---|
| `LegendAnalysis` | `doesLegendExist: Boolean` | Legend present? |
| `MethodActorResponse` (RolePlay) | `characterProfile: CharacterPerspective` | Character identity |
| `MultiPhasePlan` | `analysis: TaskAnalysis` | Problem + limitations |
| `ExplicitReasoningDetailed` | `coreAnalysis: CoreAnalysis` | Subject + components |
| `StructuredCot` | `componentIdentification: ComponentIdentification` | Task + constraints |
| `ChainOfDraftResponse` | `problemAnalysis: String` (5 words max) | Problem in 5 words |
| `SemanticDecompressionResponse` | `legendAnalysis: LegendAnalysis` | Legend → content gate |

**Three reinforcement layers** stack to enforce this:
1. **Structural order** — fields are physically ordered in the data class declaration
2. **Default-value instructions** — `Pipe.kt:1944-1954` tells the LLM: "use `false` for booleans, `0` for numbers, empty arrays for lists"
3. **Footer prompt completion enforcement** — `ReasoningBuilder.kt:317-321` appends "You must fill all json values of your output"

When designing new response classes, put commitments first, structured analysis second, rich output last. See `references/json-railroad-pattern.md` for the full worked example, the before/after demo, and the article-ready thesis.

## Role-Play Reasoning — Full Chain

**Location:** `TPipe-Defaults/.../ReasoningBuilder.kt:214-218`

```kotlin
ReasoningMethod.RolePlay -> {
    targetSystemPrompt = rolePlayPrompt(settings.roleCharacter, settings.depth, settings.duration)
    jsonOutputObject = MethodActorResponse()
    jsonOutputClass = MethodActorResponse::class
    targetSystemPrompt += """ROLE PLAY AS THE FOLLOWING CHARACTER: ${settings.roleCharacter}"""
}
```

Two-stage construction: `rolePlayPrompt()` builds the scaffold, then `roleCharacter` is appended as a separate line. This matters because the scaffold and character are injected at different points.

### Three-Phase Scaffold — `ReasoningPrompts.kt:222-285`

**Phase I — THE IMMERSION PHASE**
```
You are a method actor fully embodying a character to solve problems. You do not *describe*
the character; you *become* them. Your entire cognitive process must be filtered through
the character's persona, expertise, and worldview.
```
Instructions: absorb `characterBackground`, `expertiseDomain`, `worldview`, `typicalTerminology` as your own history. Let the profile overwrite default responses.

**Phase II — THE PROBLEM-ENGAGEMENT PHASE**
```
1. Character-Centric Problem Analysis
   - problemInterpretation: how does character's worldview interpret this?
   - characterInsights: what biases/observations does expertise reveal?
   - methodology: what's the character's professional approach?

2. In-Character Cognitive Process (emit ALL thinking)
   - thoughtProcess: real-time first-person verbose internal monologue
   - appliedExpertise: explicitly state how domain knowledge is applied
   - reasoningStyle: character's unique reasoning style

3. Character-Driven Solution Crafting
   - proposedApproach: specific plan from character's perspective
   - characterRationale: why this approach makes sense given worldview
   - uniqueAdvantages: what persona-specific advantages generic would miss

4. Signature Flourish: concluding quote/gesture unique to the character
```

**Phase III — OUTPUT PROTOCOL**
```
- MUST output complete JSON matching the provided schema
- All nested levels filled from immersed character perspective
- ONLY raw JSON — no intro text, no markdown, no concluding remarks
```

### Depth Modifier — `selectDepth(ReasoningMethod.RolePlay)`

| Depth | Constraint |
|-------|-----------|
| `Low` | 3-5 total reasoning elements. characterInsights: 2-3, thoughtProcess: 2-3, uniqueAdvantages: 1-2. Surface-level. |
| `Med` | 6-10 total reasoning elements. characterInsights: 3-5, thoughtProcess: 4-6, uniqueAdvantages: 2-3. Thorough. |
| `High` | 10+ total reasoning elements. characterInsights: 5+, thoughtProcess: 7+, uniqueAdvantages: 3+. Exhaustive. |

### Duration Modifier — `selectDuration(ReasoningMethod.RolePlay)`

| Duration | Constraint |
|----------|-----------|
| `Short` | 40-60% of normal length. 1-2 sentences per thoughtProcess item. |
| `Med` | 90-110% of normal length. 2-3 sentences per thoughtProcess item. |
| `Long` | 150-200% of normal length. Detailed explanations throughout all fields. |

## Multi-Round Reasoning

When `numberOfRounds > 1`, the system uses `ConverseHistory` as the transport layer between rounds (legacy `focusPoints` path) OR routes through direct prompt envelopes (`roundDirectives` path with `Blind` / `Merge` round modes).

**Round Modes:**
- `Blind`: Harness withholds prior round content. Model sees only original user prompt + round's focus point.
- `Merge`: Harness supplies accumulated flattened thought stream. Model synthesizes into one conclusion.

**Configuration:**
```kotlin
val roundDirectives = mutableMapOf(
    1 to ReasoningRoundDirective(focusPoint = "risk assessment", mode = ReasoningRoundMode.Blind),
    2 to ReasoningRoundDirective(focusPoint = "cost analysis", mode = ReasoningRoundMode.Blind),
    3 to ReasoningRoundDirective(focusPoint = "timeline planning", mode = ReasoningRoundMode.Merge)
)
```

After each round, TPipe normalizes through the `unravel()` path and appends to a cumulative thought stream. The parent pipe receives the resolved stream, not a serialized history blob.

## Prompt Injection — Where It Lands

The reasoning pipe's output is injected into the main pipe at the location specified by `reasoningInjector`:

- `SystemPrompt`: `"... reasoning content ...\n"` appended to main pipe's system prompt
- `BeforeUserPrompt`: reasoning content prepended to the message list before user turn
- `AfterUserPrompt`: reasoning content appended after user turn
- `BeforeUserPromptWithConverse` / `AfterUserPromptWithConverse`: reasoning injected into ConverseHistory block
- `AsContext`: reasoning injected as context to a page key

## Key Files

| File | Role |
|------|------|
| `TPipe-Defaults/.../ReasoningBuilder.kt` | `assignDefaults()` — builds system prompt, sets JSON output type. Hosts `reasonWithBedrock`, `reasonWithOllama`, `reasonWithOpenRouter`, `reasonWithGenericOpenAI`. |
| `TPipe-Defaults/.../ReasoningPrompts.kt` | All prompt templates: `rolePlayPrompt()`, `chainOfThoughtSystemPrompt()`, `bestIdeaPrompt()`, etc. |
| `TPipe-Defaults/.../ReasoningPrompts.kt:400` | `selectDepth()` — depth constraints per method |
| `TPipe-Defaults/.../ReasoningPrompts.kt:463` | `selectDuration()` — duration constraints per method |
| `TPipe-Defaults/.../Defaults/providers/BedrockDefaults.kt` | `createBedrockPipe` — BedrockMultimodalPipe factory |
| `TPipe-Defaults/.../Defaults/providers/OllamaDefaults.kt` | `createOllamaPipe` — OllamaPipe factory |
| `TPipe-Defaults/.../Defaults/providers/OpenRouterDefaults.kt` | `createOpenRouterPipe` — OpenRouterPipe factory |
| `TPipe-Defaults/.../Defaults/providers/GenericOpenAIDefaults.kt` | `createGenericOpenAIPipe` — GenericOpenAIPipe factory |
| `TPipe-Defaults/.../Defaults/ProviderConfiguration.kt` | Sealed-class holder for `BedrockConfiguration`, `OllamaConfiguration`, `OpenRouterConfiguration`, `GenericOpenAIConfiguration`, plus grid-specific variants |
| `TPipe-Bedrock/.../BedrockMultimodalPipe.kt` | Extracts reasoning from Converse API responses |
| `TPipe/src/main/kotlin/Structs/PipeSettings.kt` | `ReasoningSettings` and `TokenBudgetSettings` |
| `docs/core-concepts/reasoning-pipes.md` | Full documentation of all reasoning methods |

## Common Patterns

### Basic Role-Play Pipe
```kotlin
val rolePlaySettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.RolePlay,
    roleCharacter = "You are an experienced business consultant with 20 years of strategic planning experience.",
    depth = ReasoningDepth.High,
    duration = ReasoningDuration.Med,
    reasoningInjector = ReasoningInjector.SystemPrompt
)

val consultantReasoningPipe = ReasoningBuilder.reasonWithBedrock(bedrockConfig, rolePlaySettings, pipeSettings)

val mainPipe = BedrockPipe()
    .setSystemPrompt("Solve problems systematically.")
    .setReasoningPipe(consultantReasoningPipe)
    .setTokenBudget(TokenBudgetSettings(reasoningBudget = 2000))
```

### Chain of Draft (low-latency)
```kotlin
val chainOfDraftSettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.ChainOfDraft,
    depth = ReasoningDepth.Med,
    duration = ReasoningDuration.Short,
    reasoningInjector = ReasoningInjector.SystemPrompt
)
```
Max 5 words per reasoning step. Up to 75% token reduction vs standard CoT.

### Cross-Provider Reasoning
```kotlin
// Ollama reasoning feeding Bedrock main pipe
val ollamaConfig = OllamaConfiguration(host = "localhost:11434", model = "llama3.1:70b")
val ollamaReasoningPipe = ReasoningBuilder.reasonWithOllama(ollamaConfig, reasoningSettings, null)

// OpenRouter reasoning across multiple upstream providers
val openRouterConfig = OpenRouterConfiguration(model = "anthropic/claude-3.5-sonnet", apiKey = "...")
val openRouterReasoningPipe = ReasoningBuilder.reasonWithOpenRouter(openRouterConfig, reasoningSettings, pipeSettings)

// GenericOpenAI reasoning against any OpenAI-compatible endpoint (OpenAI, MiniMax, Together, vLLM, llama.cpp)
val genericConfig = GenericOpenAIConfiguration(model = "gpt-4o-mini", apiKey = "...")
val genericReasoningPipe = ReasoningBuilder.reasonWithGenericOpenAI(genericConfig, reasoningSettings, pipeSettings)
```

---

## Session Note — 2026-07-09 OpenRouter + GenericOpenAI Extension

The 2026-07-09 cycle shipped `reasonWithOpenRouter` and `reasonWithGenericOpenAI` per the established four-file spec above. Worked example with file-level inventory, TDD red→green evidence (Unresolved reference → 35 tests / 7 classes / 0 failures), and four mistakes caught-and-reverted (pipeName-assertion failure, invented mirror types, wrong `ApiMode` package import, non-existent `setSessionId`/`setVerbosity` setters on `GenericOpenAIPipe`) lives at `references/2026-07-09-openrouter-genericopenai-extension.md`. Future "add `<NewProvider>` to the reasoning builder" tasks should read it before starting.

---

## Pitfalls — Lessons From Real Sessions

### Pitfall 1: Don't assert on `pipe.pipeName` — it's empty until parent `init()` fires

When TDD-testing the `reasonWith<Provider>` factory directly (without first attaching it to a parent pipe via `setReasoningPipe()` and calling `init()`), `pipe.pipeName` is the empty string. The pipe-name auto-setting happens at `Pipe.kt:4956`:

```kotlin
if(reasoningPipe?.pipeName?.isEmpty() == true) reasoningPipe?.pipeName = "$pipeName->reasoning pipe"
```

That block only runs when the parent pipe goes through `init()`. A standalone factory test never reaches it. Test asserts on `pipeMetadata["reasoningMethod"]` / `["injectionMethod"]` / `["reasoningRounds"]` instead — those are written unconditionally by `assignDefaults`, and that's the contract that matters at runtime.

### Pitfall 2: `Pipe.model` is `protected` — cannot read externally

External test code cannot read `pipe.model` directly because `Pipe.kt:830` declares `protected var model = ""`. The same `protected` visibility applies to `provider` on the same class. If the test pins "the model is gpt-4o-mini" via `assertEquals("gpt-4o-mini", pipe.model)`, it fails to compile with `Cannot access 'var model: String': it is protected in 'com.TTT.Pipe.Pipe'`. Workarounds, in order of preference:

1. Pin observable behavior — `pipeMetadata["reasoningMethod"]` round-trip, `pipe.pipeName` after attachment, or call `pipe.execute(MultimodalContent(text = "..."))` and inspect the post-injection `modelReasoning` field.
2. Have the factory itself write a `pipeMetadata["configuredProvider"]` marker (cheap, decouples the test from internals).

Do NOT use Kotlin reflection (`pipe.javaClass.getDeclaredField("model").apply { isAccessible = true }`) in tests — it bypasses the visibility for a reason and rots the moment the field is renamed.

### Pitfall 3: Don't invent mirror enums/typealiases to soften a real dependency

When the `Defaults/ProviderConfiguration.kt` shape needs to reference a type that lives in a provider module (e.g. `genericOpenAIPipe.api.ApiMode`), do NOT introduce a parallel enum or placeholder typealias in `Defaults` to avoid adding the Gradle dependency. The established spec is: add the Gradle `implementation` line, import the real type, and use it. Invented mirrors (e.g. `enum class ApiModeName { OpenAI, OpenAIResponses, Anthropic }`) duplicate the type's surface and rot the moment the upstream enum changes. If the factory needs a translation step (string → enum), do it inside the factory — keep the `Defaults` surface minimal. Confirmed 2026-07-09 in the GenericOpenAI extension cycle: initial draft included `openRouterPipeOpenAIEnvTypeAlias: String` and `enum ApiModeName`, both reverted before the green-light test in favor of a string `apiMode` field + factory-side translation.

### Pitfall 4: Always run the full module test suite after extending `TPipe-Defaults`

A new `implementation(project(":TPipe-...Provider"))` line in `TPipe-Defaults/build.gradle.kts` can shadow or accidentally re-export a class with the same simple name in another module's test (e.g. `Request` from OpenAI vs `Request` from Ktor). Run `./gradlew :TPipe-Defaults:test` (full suite, NOT `--tests` filter) after any builder extension. The TPipe-Defaults suite currently runs 35 tests across 7 classes; if any fails after a provider addition, suspect a transitive name conflict before suspecting the new factory.

### Pitfall 5: TDD red step — write the test that fails FIRST, before adding the provider dependency

The TDD loop on `reasonWith<NewProvider>`:

1. Write `ReasoningBuilderProviderFactoriesTest.kt` with `reasonWith<NewProvider>ReturnsPipeWithConfiguredReasoningMetadata` referencing the new factory and configuration dataclass.
2. Run `./gradlew :TPipe-Defaults:test --tests "<new class>"` — confirm the build fails with `Unresolved reference 'reasonWith<NewProvider>'` and `Unresolved reference '<NewProvider>Configuration'`. That is the red.
3. Add the four files from the established spec. Run again. Confirm 4/4 green.
4. Run the full TPipe-Defaults suite. Confirm the regression check is clean.

Skipping step 2 (writing the failing test before adding the imports) means the green step is unverifiable. If both red-and-green produce "BUILD SUCCESSFUL", the test never exercised the new surface — false-positive cover.

### Pitfall 6: `setReasoningPipe()` does not carry feature state across the main→reasoning boundary

`setReasoningPipe(reasoningPipe)` wires the reasoning pipe into the parent's `execute()` flow but does NOT copy any properties from the main pipe. The reasoning pipe owns its own `serviceTier` / `cacheControl` / `region` / `readTimeoutSeconds` / `guardrailIdentifier` / etc. Setting these on the main pipe has zero effect on the reasoning pipe.

For tier specifically: every `BedrockConfig.<builder>(...)` factory in `globals/BedrockConfig.kt:535-864` accepts a `useFlex: Boolean = false` parameter that, when true, calls `pipe.setServiceTier(BedrockPriorityTier.Flex)` on the reasoning pipe. This is the Autogenesis-specific escape hatch for reasoning-pipe tier propagation. If a pipe builder forgets to pass `useFlex = true` (or accepts the default), the reasoning pipe runs on Standard regardless of what tier the main pipe was set to.

This is a class-level silent-no-op that an audit will miss unless it explicitly traces features across the main→reasoning boundary. The `tpipe-pipe-feature-audit` skill captures the full methodology; the canonical worked example (Autogenesis qwen235B Flex-tier audit, 2026-07-25) lives at `software-development/tpipe-pipe-feature-audit/references/2026-07-25-autogenesis-flex-tier-eligibility.md`.

### Pitfall 7: A reasoning pipe constructed without `assignDefaults` NPEs the parent at prompt-composition time (cast of null to non-null Boolean)

`Pipe.getMiddlePromptForReasoning()` and `Pipe.getFooterPromptForReasoning()` (`Pipe.kt:8030-8050`) read three Boolean flags directly off the reasoning pipe's metadata:

```kotlin
fun getMiddlePromptForReasoning() : String
{
    if(reasoningPipe == null) return ""
    val usingMiddlePrompt = reasoningPipe?.pipeMetadata["injectMiddlePrompt"] as Boolean   // ← line 8033
    if(!usingMiddlePrompt) return ""
    return middlePromptInstructions
}
```

Both casts (`as Boolean` at 8033 and 8047) are unguarded. The rest of `Pipe.kt` uses the `is Boolean` guard pattern at lines 7166-7168 and 7208-7210 for the `reinforceSystemPrompt` flag — these two casts are the only `as Boolean` casts without a guard in the file.

When `assignDefaults` writes `injectMiddlePrompt = settings.injectMiddlePrompt` (a Boolean defaulting to `false`), everything works. When the reasoning pipe is built by code that bypasses `assignDefaults`, the key is absent and the cast crashes.

**Confirmed failure (2026-07-30, autogenesis gemma-swap test game, `~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/`):**

```
java.lang.NullPointerException: null cannot be cast to non-null type kotlin.Boolean
    at com.TTT.Pipe.Pipe.getMiddlePromptForReasoning(Pipe.kt:8033)
    at com.TTT.Pipe.Pipe.executeReasoningPipe(Pipe.kt:7201)
    at com.TTT.Pipe.Pipe$executeMultimodal$2.invokeSuspend(Pipe.kt:6496)
```

The reasoning pipes that triggered it: `mantle validator pipe` and `Play Detection Agent`, both constructed via `BedrockConfig.mantleExplicitCotBuilder(...)` / `mantleStructuredCotBuilder(...)`. Both builders (`BedrockConfig.kt:1116-1199` for authors, `BedrockConfig.kt:1313-1350` for reasoning) build `GenericOpenAIPipe().setBedrockMantle(...)` directly and never call `ReasoningBuilder.assignDefaults`, so the three Boolean flags (`injectMiddlePrompt`, `injectFooterPrompt`, `reinforceSystemPrompt`) are never written.

**Surface symptoms:** trace shows `PIPE_FAILURE` event with the NPE above, then three back-to-back `API_CALL_START` events (TPipe's `pipeFailure` retry logic), then a single `API_CALL_SUCCESS` whose reasoning injection was missing. In `Play Detection Agent` the missing-injection retry response is `{}` — an empty JSON object that satisfies `requireJsonPromptInjection` but has no schema fields, causing `extractJson<PlayTypeObj>` to return null downstream. Validator retries succeed because their prompts are smaller and degrade gracefully.

**Detection recipe.** After any new reasoning-pipe factory is added, check the trace file for that pipe's directory and grep for `PIPE_FAILURE` events with the NPE signature:

```bash
python3 -c "
import json, os, sys
needle = 'null cannot be cast to non-null type kotlin.Boolean'
hits = []
for root, _, files in os.walk(sys.argv[1]):
    for f in files:
        if not f.endswith('trace.json'):
            continue
        for ev in json.load(open(os.path.join(root, f))):
            md = ev.get('metadata') or {}
            if needle in (md.get('error') or ''):
                hits.append((ev.get('pipeName'), md.get('model'), md.get('pipeClass')))
for h in hits[:20]:
    print(h)
" /path/to/trace/dir
```

**Two valid fixes.** Pick one:

1. **Pipe.kt (the surgical two-line fix):** Replace the unguarded `as Boolean` casts at lines 8033 and 8047 with `as? Boolean ?: false`. This is consistent with the `is Boolean` guard pattern used at 7166 and 7208, and matches the defaults written by `assignDefaults` (`ReasoningSettings.kt:151-152`). Two lines change. Recommended when you can't touch every consumer of the missing-metadata pattern, or when you want a safety net independent of which reasoning-pipe factories exist now or later.

2. **At the factory call site:** Update any code path that constructs a reasoning pipe without calling `ReasoningBuilder.assignDefaults(...)` to either call `assignDefaults` or write the three Boolean keys (`injectMiddlePrompt = false`, `injectFooterPrompt = false`, `reinforceSystemPrompt = false`) to `pipeMetadata` itself. This is the "make every factory route through the standard entry point" fix. Do this when you own the factory and can verify all consumers benefit.

**The bug class.** This is a **reasoning-pipe metadata gap** — the parent pipe and the reasoning pipe agree on a contract ("eight metadata keys exist on the reasoning pipe, three of them Boolean"), but the contract is enforced only by `assignDefaults`. Any reasoning-pipe factory that bypasses `assignDefaults` (custom wrappers, direct `GenericOpenAIPipe().setBedrockMantle(...)` builders, test doubles, third-party extensions) silently violates the contract. The autogenesis Mantle builders are the first known instance; future "add a new provider without going through the standard pipeline" tasks are the next likely source.

**Canonical incident:** `references/2026-07-30-reasoning-metadata-npe.md` — autogenesis gemma-swap test game, full stack trace, line-level source references (Pipe.kt 8030-8050 vs 7166-7168/7208-7210), Mantle builder divergence (BedrockConfig.kt:1116-1199 and 1313-1350), two-event trace walk, `Play Detection Agent` `{}` cascade, and a grep-by-error-message detection script for any future "is this still broken?" verification.

### Pitfall 8: The Mantle extension pattern — `reasonWithGenericOpenAI(...)` + `.apply { ... }`

Mantle is intentionally not in the `reasonWith*` family. The framework's KDoc at `GenericOpenAIPipe.kt:644-672` documents that Mantle ships with `injectMiddlePrompt = false`, `injectFooterPrompt = false`, `reinforceSystemPrompt = false` defaults — the consumer must opt into JSON-completion enforcement manually. The consumer-side pattern that satisfies this contract while still routing through the framework integration is:

```kotlin
val pipe: GenericOpenAIPipe = ReasoningBuilder.reasonWithGenericOpenAI(
    GenericOpenAIConfiguration(
        model = modelId,
        baseUrl = BedrockMantleConfiguration.forRegion(region, modelId).endpoint(),
        apiMode = "OpenAI"
    ),
    ReasoningSettings(
        reasoningMethod = reasoningMethod,            // StructuredCot, RolePlay, etc.
        injectFooterPrompt = true,                    // <-- the gate flip
        // ...
    ),
    pipeSettings
) as GenericOpenAIPipe

pipe.apply {
    // Mantle auth: reasonWithGenericOpenAI builds via createGenericOpenAIPipe
    // which does NOT call configureBedrockMantle. configureBedrockMantle is
    // what wires BedrockMantleAuth + sets pipeMetadata["injectFooterPrompt"]
    // etc. Without the explicit auth wiring, init() throws at
    // GenericOpenAIPipe.kt:733 with "GenericOpenAI API key is required".
    BedrockMantleAuth.sigV4FromEnv(regionOverride = region)
        ?.let { setBedrockMantleAuth(it) }

    // Provider-specific metadata, transformation hooks, etc.
    setTransformationFunction { ... }
    pipeMetadata["showThinking"] = showThinking
}
```

The shape: `reasonWithXxx(...)` does the framework integration (calls `assignDefaults` which sets `requireJsonPromptInjection`, `setJsonOutput(class)`, and the JSON-completion footer prompt). `.apply { ... }` does the provider-specific wiring that the framework's `reasonWith*` family can't know about (Mantle auth, provider-specific metadata, call-site-dependent transformation hooks).

**Why this matters.** The Mantle builder's failure mode is broader than Pitfall 7's NPE. Without `reasonWithGenericOpenAI` + `injectFooterPrompt = true`:
- `RolePlay` builds emit markdown prose (model has no JSON schema rail, falls back to pre-trained roleplay behavior).
- `StructuredCot` / `processFocusedCot` / `ExplicitCot` builds return empty responses (model aborts without a JSON schema to fill).
- The `mantle author 31b` 0/12 JSON, `mantle structured cot` 6/6 empty, `mantle explicit cot` 6/6 empty symptom pattern observed in 2026-07-30 autogenesis trace audit. All five Mantle builders (`mantleAuthorBuilderE2B`, `mantleAuthorBuilder31B`, `mantleStructuredCotBuilder`, `mantleProcessFocusedBuilder`, `mantleExplicitCotBuilder`) shared the same hand-rolled `GenericOpenAIPipe().setBedrockMantle(...)` shape that bypassed `assignDefaults`.

**Detection recipe.** Before any Mantle reasoning-pipe factory lands, run a contract test that asserts the model response carries the JSON schema field names (`characterProfile`, `proposedApproach`, `componentIdentification`, etc.) and parses under `kotlinx.serialization`. Tolerate trailing-comma quirks with a lenient try-catch (Gemma 4 emits minor envelope malformations on terse prompts). Pin the contract in a `Build<Provider>ReasoningPipesContractTest.kt` file — five tests covering the five `ReasoningMethod` enum values relevant to the factory family.

**Verification recipe (post-fix).** Run `./gradlew :server:test --tests "*BuildMantleReasoningPipesContractTest*"` with `BEDROCK_MANTLE_LIVE_TEST=true`, `BEDROCK_AWS_PROFILE=<profile>`, `BEDROCK_MANTLE_REGION=<region>`. Confirm 5/5 GREEN. The JUnit XML at `server/build/test-results/test/TEST-<fqcn>.xml` is the canonical source of truth — gradle stdout PASSED markers can be lost to daemon-collision noise when test output is heavy.

**Auth fail-open guard.** When the auth check is `checkNotNull { ... }` at pipe construction, unit tests that call the factory without AWS credentials fail with `IllegalStateException`. Switch to a warn-only path (`Logger.warn(...)` + skip `setBedrockMantleAuth`) so the pipe constructs; `execute()` fails at wire time with a clearer error in that case. Production paths with credentials populated by `AwsCredentialsBootstrap.kt` (or whatever bootstrap is in place) are unaffected.

**Cross-reference.** The autogenesis bug report at `autogenesis/docs/bugs/MANTLE_GEMMA_JSON_ADHERENCE.md` carries the full pre-fix trace evidence (12 events: 4 prose, 8 empty, 0 JSON for the affected pipes; 6/6 JSON for the `mantle validator pipe` control case). The fix lives at `autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt:1115-1198` (buildMantleAuthorPipe) and `:1376+` (buildMantleReasoningPipe).
