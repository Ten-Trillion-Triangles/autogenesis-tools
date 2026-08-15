# Mantle author / reasoning-pipe framework integration

The lesson from the 2026-07-30 Mantle bug triage: porting the Qwen
`authorBuilder` to Mantle by hand-rolling a `GenericOpenAIPipe` chain
silently bypasses the framework integration that `reasonWithBedrock`
+ `assignDefaults` provides. The Mantle pipe runs and emits text, but
the model produces markdown narrative instead of the contract JSON
because the schema rail is never wired. This reference documents the
symptom catalog, the cross-pipe audit, the fix recipe, and the
hermetic verifier that proves the integration is wired.

## Why the hand-rolled pattern fails

The Qwen `authorBuilder` (`autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt:639-738`)
calls:

```kotlin
val pipe = reasonWithBedrock(
    bedrockSettings,                       // line 668-671
    reasoningSettings,                     // line 658-666 — ReasoningMethod.RolePlay, roleCharacter = author
    pipeSettings                           // line 673-679
) as BedrockMultimodalPipe
```

`reasonWithBedrock(...)` at `TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:344-352`
does two things:

1. `createBedrockPipe(bedrockConfig)` — the underlying `BedrockMultimodalPipe`
2. `assignDefaults(reasoningSettings, pipeSettings, bedrockPipe)` — the
   wiring that makes the pipe actually behave as a RolePlay / StructuredCoT /
   ExplicitCoT / ProcessFocused / ChainOfDraft / SemanticDecompression pipe

`assignDefaults` at `ReasoningBuilder.kt:178-302` wires the framework
integration. The Mantle equivalent `reasonWithGenericOpenAI` at
`ReasoningBuilder.kt:419-427` does the same thing for the OpenAI
Chat-Completions wire format that Mantle uses. The four first-party
builders (`reasonWithBedrock`, `reasonWithOllama`, `reasonWithOpenRouter`,
`reasonWithGenericOpenAI`) all share this shape; the only thing that
varies is the wire layer.

The hand-rolled Mantle port at `BedrockConfig.kt:1115-1198`
(`buildMantleAuthorPipe`) skipped `reasonWithGenericOpenAI` and
constructed a `GenericOpenAIPipe` directly. The result is a pipe that:

- Has no `requireJsonPromptInjection()` — model never sees the JSON rail
- Has no `setJsonOutput(MethodActorResponse::class)` — typed output schema
  never wired
- Has no `setSystemPrompt(rolePlayPrompt(...) + "ROLE PLAY AS THE
  FOLLOWING CHARACTER: ${author}")` — the role Character is passed
  verbatim into `setSystemPrompt(author)` without the roleplay
  system-prompt prefix
- Has no `pipeMetadata["reasoningMethod"]` — the metadata downstream
  consumers read via `extractJson<MethodActorResponse>(pipeContent.text)`
  is absent

The pipe still runs and produces text — the model just produces markdown
narrative instead of the expected JSON. The downstream consumer's
`extractJson<T>(pipeContent.text)` returns null, the consumer falls back
to a default `T()`, and the bug only surfaces as "thinking vanished" or
"validators silently passing" in production logs.

## Symptom catalog (the user-visible failure shapes)

Cross-pipe audit on `~/.tpipe/debug/trace/Round_*_Turn_*` using
`extract_pipeline.py --format per_pipe`:

| Pipe                              | Model              | JSON | Prose | Empty | Total |
|-----------------------------------|--------------------|-----:|------:|------:|------:|
| `mantle author 31b` (RolePlay)    | `google.gemma-4-31b` | 0 | 4 | 8 | 12 |
| `mantle writing pipe (g31b)`      | `google.gemma-4-31b` | 1 | 4 | 2 | 7 |
| `mantle structured cot` (E2B)     | `google.gemma-4-e2b` | 0 | 0 | 6 | 6 |
| `mantle explicit cot` (E2B)       | `google.gemma-4-e2b` | 0 | 0 | 6 | 6 |
| `mantle validator pipe` (control) | `google.gemma-4-e2b` | 6 | 0 | 0 | 6 |

The `mantle validator pipe` is the working Mantle pipe that produces
JSON on every call. The difference between the working and broken
Mantle pipes is:

- `mantle validator pipe` is built via `reasonWithGenericOpenAI` indirectly
  (the `ValidatorPipeAgent` construct uses `setReasoningPipe(mantleStructuredCotBuilder(...))`
  on a `GenericOpenAIPipe` outer that has `requireJsonPromptInjection()` + `setJsonOutput(ValidatorPipeResult::class)` — the framework integration minus the `assignDefaults` call, but with the JSON contract manually re-applied).
- `mantle author 31b` / `mantle writing pipe (g31b)` / `mantle structured cot`
  are built via direct `GenericOpenAIPipe().setBedrockMantle(...)` chains
  without the framework integration.

The legacy Qwen path is the control case for the same shape:

| Pipe                              | Model            | JSON | Prose | Empty | Total |
|-----------------------------------|------------------|-----:|------:|------:|------:|
| `author` (Bedrock / Qwen)         | `qwen3-coder-30b-a3b` | 9 | 0 | 0 | 9 |
| `Synthesis Stage (Robert)`        | `qwen3-coder-30b-a3b` | 3 | 6 | 0 | 9 |
| `Execution Stage (Robert)`        | `qwen3-coder-30b-a3b` | 3 | 6 | 0 | 9 |

(The "Prose" rows on Qwen `*Stage` pipes are the post-`MethodActorResponse.unravel()`
projection at `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:365-389` — expected
role-play output, not a bug.)

## The fix recipe (per call site)

### 1. Replace `buildMantleAuthorPipe`/`buildMantleReasoningPipe` wholesale

The cleanest fix is to delete the hand-rolled factories and route
everything through `reasonWithGenericOpenAI`. Two factory rewrites,
both at `BedrockConfig.kt`:

```kotlin
// Before (hand-rolled, ~80 lines, missing the framework integration)
private fun buildMantleAuthorPipe(
    modelKey: String, /* ... 14 params ... */
): Pipe {
    val pipe = GenericOpenAIPipe()
        .setBedrockMantle(region, modelId)
        .setPipeName(pipeName)
        .setMaxTokens(maxTokens)
        .setTemperature(temperature)
        .setTopP(topP)
        .setSystemPrompt(author)
        .setTokenBudget(...)
    pipe.apply { setTransformationFunction { ... } }
    runBlocking { pipe.init() }
    pipe.pipeMetadata["showThinking"] = showThinking
    /* ... */
    return pipe
}

// After (framework-integrated, ~25 lines, mirrors authorBuilder exactly)
fun mantleAuthorBuilder31B(
    author: String,
    depth: ReasoningDepth = ReasoningDepth.High,
    duration: ReasoningDuration = ReasoningDuration.Short,
    /* ... */
): Pipe {
    val genericConfig = GenericOpenAIConfiguration(
        model = mantleModelId("gemma31ModelId"),
        baseUrl = "https://bedrock-mantle.${mantleRegion()}.api.aws/openai/v1",
        apiMode = "OpenAI",
        apiKey = ""
    )
    val reasoningSettings = ReasoningSettings(
        reasoningMethod = ReasoningMethod.RolePlay,
        roleCharacter = author,
        depth = depth,
        duration = duration,
        reasoningInjector = ReasoningInjector.AfterUserPrompt,
        numberOfRounds = 1,
        focusPoints = mutableMapOf()
    )
    val pipeSettings = PipeSettings(
        model = genericConfig.model,
        temperature = /* ... */,
        topP = /* ... */,
        maxTokens = /* ... */,
        pipeName = "mantle author 31b"
    )
    val pipe = reasonWithGenericOpenAI(genericConfig, reasoningSettings, pipeSettings)
        as GenericOpenAIPipe

    // The transformation function still needs the Mantle-specific
    // ThinkingUpdateData broadcast hook. apply it AFTER the framework
    // integration so the framework metadata is preserved.
    pipe.apply {
        setTransformationFunction { pipeContent -> /* ... */ }
    }
    pipe.pipeMetadata["showThinking"] = showThinking
    /* ... */
    return pipe
}
```

### 2. Patch Mantle reasoning-method builders the same way

`mantleStructuredCotBuilder`, `mantleExplicitCotBuilder`,
`mantleProcessFocusedBuilder` (lines 1214-1288 currently) all hand-roll
the same shape. Each picks a `ReasoningMethod` and the corresponding
typed output schema:

```kotlin
fun mantleStructuredCotBuilder(...) = reasonWithGenericOpenAI(
    genericConfig,
    ReasoningSettings(reasoningMethod = ReasoningMethod.StructuredCot, depth = depth, duration = duration, reasoningInjector = ReasoningInjector.AfterUserPrompt),
    pipeSettings
).apply { setPipeName("mantle structured cot (${modelKey})") }
```

The `ReasoningMethod → KClass` mapping at `ReasoningBuilder.kt:268-278`
is what `assignDefaults` uses to pick the typed output:

| ReasoningMethod | OutputSchema |
|---|---|
| `StructuredCot` | `StructuredCot` |
| `ProcessFocusedCot` | `ProcessFocusedResult` |
| `ExplicitCot` | `ExplicitReasoningDetailed` |
| `BestIdea` | `BestIdeaResponse` |
| `RolePlay` | `MethodActorResponse` |
| `ComprehensivePlan` | `MultiPhasePlan` |
| `ChainOfDraft` | `ChainOfDraftResponse` |
| `SemanticDecompression` | `SemanticDecompressionResponse` |

### 3. The `.apply { ... }` opt-in shape (when you can't refactor)

If a hand-rolled factory already exists and you can't refactor it into
the framework path, patch it with the three-line `.apply { ... }` opt-in:

```kotlin
val pipe = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    .apply {
        requireJsonPromptInjection()
        setJsonOutput(MethodActorResponse::class)  // or per ReasoningMethod
        pipeMetadata["injectFooterPrompt"] = true
        setSystemPrompt(buildString {
            append(rolePlayPrompt(depth, duration))
            append("\n\nROLE PLAY AS THE FOLLOWING CHARACTER:\n")
            append(author)
        })
    }
```

This is the same shape the `mantle json-completion-opt-in` pitfall
in SKILL.md describes. It's a patch, not a fix — the framework
integration is still missing, just the visible symptoms are suppressed.

## Cross-pipe audit (which Mantle calls need the fix)

Walking every `setReasoningPipe(BedrockConfig.mantleXxxBuilder(...))` site
in `autogenesis/server/src/main/kotlin/agent/builders/`:

| File | Line | Mantle builder | Status |
|---|---|---|---|
| `gameplayActions/nemesisAgent.kt` | 130 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `gameplayActions/nemesisAgent.kt` | 140 | `mantleStructuredCotBuilder` | needs recipe #2 |
| `gameplayActions/nemesisAgent.kt` | 187 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `gameplayActions/nemesisAgent.kt` | 235 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `gameplayActions/nemesisAgent.kt` | 258 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `playerAgent/playerAgent.kt` | 135 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `writingAgent/writerAgent.kt` | 393 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `writingAgent/writerAgent.kt` | 597 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `validateAction/ValidatorPipeAgent.kt` | 91 | `mantleStructuredCotBuilder` | **already correct** (control case) |
| `validateAction/npcValidationAgent.kt` | 58, 197, 287 | `mantleStructuredCotBuilder` / `mantleExplicitCotBuilder` | needs recipe #2 |
| `validateAction/railroadAgent.kt` | 42 | `mantleStructuredCotBuilder` | needs recipe #2 |
| `validateAction/identifyPlayAgent.kt` | 143 | `mantleExplicitCotBuilder` | needs recipe #2 |
| `writingAgent/ResponseRefinementAgent.kt` | (per buildXxx) | uses `mantleValidatorPipe` / `mantleExplicitCotBuilder` | needs recipe #2 |
| `systemActions/CreateUserActionClassificationPipeline` | (per buildXxx) | `mantleExplicitCotBuilder` | needs recipe #2 |
| `systemActions/BuildOpenWidgetPipeline` | (per buildXxx) | `mantleStructuredCotBuilder` | needs recipe #2 |
| `judgeOutcome/geoPoliticsAssessmentAgent.kt` | 117, 259, 313 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `lorebook/lorebookAgent.kt` | 150 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `modifyGameState/worldupdates.kt` | 38 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `modifyGameState/hardenAgent.kt` | 185 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `modifyGameState/nemesisCreationBuilder.kt` | 151 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `passFailAgent/passFailAgent.kt` | 299 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `systemActions/UserActionClassificationAgent.kt` | 187 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `gatherContext/newcharacterscan.kt` | 317, 498, 597, 689, 874 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `judgeOutcome/judge.kt` | 1069 | `mantleAuthorBuilder31B` | needs recipe #1 |
| `judgeOutcome/npcJudge.kt` | 103, 565 | `mantleAuthorBuilder31B` | needs recipe #1 |

`recipe #1` = replace the `buildMantleAuthorPipe` factory with the
`reasonWithGenericOpenAI` pattern. `recipe #2` = replace the
`buildMantleReasoningPipe` factory with the same pattern.

## Hermetic verifier

A re-runnable shell script captures the framework-integration
attributes on every Mantle builder site:

```bash
bash /tmp/hermes-verify-mantle-author-framework-integration.sh
```

The script checks:

1. **Cast safety at `Pipe.kt:8033/8047`** — `as? Boolean` not `as Boolean`
2. **Mantle structural wiring in `configureBedrockMantle`** — the contract
   keys are populated by default
3. **`reasonWithGenericOpenAI` is used by every Mantle reasoning/author
   builder** — grep `bedrockConfig` for the Mantle builder sites and
   assert each one routes through `reasonWithGenericOpenAI`
4. **`assignDefaults` reachability** — call `assignDefaults` on a
   Mantle-shaped pipe and assert the metadata contract is populated
5. **JSON output schema is set** — for every Mantle builder, assert
   the call site either passes through `assignDefaults` (which sets
   `setJsonOutput`) or applies the `.apply { setJsonOutput(...) }`
   opt-in

Output captures per-check trace to
`/tmp/hermes-verify-mantle-author-framework-integration.log` and a
human-readable summary to
`/tmp/hermes-verify-mantle-author-framework-integration.summary.txt`.

Source of truth is the JUnit XML attributes (`tests`, `skipped`,
`failures`, `errors`), not the gradle stdout `PASSED` markers — stdout
can drop `PASSED` lines when tests produce heavy stdout output. JUnit
XML is hermetic and survives the daemon-collision noise that gradle
stdout can mask.

## Layered reasoning (the design behind the fix)

The fix has three layers, each independently necessary:

1. **Cast safety at `Pipe.kt:8033/8047`** — `as? Boolean ?: false`
   instead of `as Boolean`. Defense in depth. Closes the NPE for any
   current or future reasoning-pipe constructor that omits the metadata
   keys. Matches the guarded pattern at `Pipe.kt:7166-7168` for
   `reinforceSystemPrompt`. This layer alone is not the goal — it
   silently degrades the feature to "no injection" on Mantle.

2. **Mantle structural wiring at `configureBedrockMantle` time** —
   `pipeMetadata["injectMiddlePrompt"] = false` and
   `pipeMetadata["injectFooterPrompt"] = false` written by default,
   matching `ReasoningSettings` defaults. This is the layer that
   `references/mantle-reasoning-metadata.md` documents. Mantle-shaped
   pipes from this repo carry the contract by construction.

3. **Consumer-side framework integration via `reasonWithGenericOpenAI`** —
   the missing piece on the autogenesis consumer side. Without it,
   the Mantle reasoning/author builders ship without the JSON I/O
   contract, the typed output schema, the roleplay character baked into
   the system prompt, and the reasoning-method metadata. This is the
   layer this reference documents.

A fix that lands only layer 1 + 2 clears the NPE but leaves the pipes
emitting prose. A fix that lands only layer 3 (consumer-side) makes the
consumer repo correct but doesn't help new providers that arrive later.
The right ordering is land all three; this reference is the consumer-side
layer 3.

## Out of scope for this reference

The autogenesis `buildMantleAuthorPipe` and `buildMantleReasoningPipe`
factories in `server/src/main/kotlin/globals/BedrockConfig.kt` are
where the fix lands. The in-repo `TPipe-GenericOpenAI` and
`TPipe-Defaults` changes are layer 1 + 2 (cast safety + structural
metadata) and are documented in `references/mantle-reasoning-metadata.md`.
This reference is exclusively the consumer-side layer 3 — the
framework integration that the Mantle builder factories must reach for
via `reasonWithGenericOpenAI`.

## When this reference applies

- Auditing a new Mantle reasoning-builder or author-builder factory.
  Symptom: pipe emits prose instead of the contract JSON. Look for
  the hand-rolled `GenericOpenAIPipe().setBedrockMantle(...)` shape
  and confirm the factory either reaches `reasonWithGenericOpenAI`
  or applies the `.apply { ... }` opt-in. If neither is present, the
  pipe is missing the framework integration.

- Reviewing a refactor that touches `ReasoningBuilder.assignDefaults`
  or the four first-party builders. The provider-parity test class
  (`ReasoningBuilderParityTest`) catches regressions on the four
  first-party builders but NOT on new consumer-side builders. Audit
  any new Mantle builder for the same shape.

- Adding a new provider to TPipe (e.g. a hypothetical "Mantle-2" or
  a different OpenAI-compatible endpoint). The pattern is the same:
  add a `reasonWith<Provider>` factory to `ReasoningBuilder` that
  calls `createXxxPipe(config)` then `assignDefaults(...)`, exposing
  the framework integration to consumer-side builder code.
