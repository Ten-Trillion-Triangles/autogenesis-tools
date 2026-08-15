# Mantle JSON-completion opt-in pattern for consumer author/reasoning pipes

The TPipe framework deliberately leaves Mantle JSON-completion enforcement
OFF by default. Consumers that want `MethodActorResponse`, `StructuredCot`,
`GameStoryResult`, or any other typed JSON output from a Mantle-shaped pipe
must opt in explicitly via `.apply { ... }` after `setBedrockMantle(...)`.

This is the documented extension pattern. The full citation is the
KDoc on `configureBedrockMantle` at
`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:644-672`:

> "Mantle has no settings object (it is wired directly, not through
> `ReasoningBuilder.assignDefaults`), so we write the
> `Defaults.reasoning.ReasoningSettings` defaults by hand here:
> `injectMiddlePrompt = false`, `injectFooterPrompt = false`,
> `reinforceSystemPrompt = false`."

And then:

> "Callers that want JSON-completion enforcement on a Mantle reasoning
> pipe should set `injectFooterPrompt=true` after construction and then
> call `setFooterPrompt(...)` themselves."

The defaults match `ReasoningSettings` (pipe is built without a
ReasoningSettings object on Mantle). The reasoning-pipe metadata
contract at `Pipe.kt:8033/8047` reads `injectFooterPrompt` to decide
whether to emit the JSON-completion footer prompt that contains the
schema injected via `setJsonOutput(...)`. With the default `false`,
the JSON schema is never appended to the system prompt and the model
emits prose instead of JSON.

## The opt-in shape

The minimum fix is three lines inside `.apply { ... }`:

```kotlin
val pipe = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    .apply {
        // 1. Flip the gate that configureBedrockMantle() left at false.
        pipeMetadata["injectFooterPrompt"] = true

        // 2. Wire the JSON output rail. setJsonOutput(kclass) writes
        //    this.jsonOutput = examplePromptFor(kclass) and calls
        //    ensureJsonPromptInjectionEnabled() which sets
        //    supportsNativeJson = false. The footer prompt machinery
        //    emits this.jsonOutput into the system prompt when
        //    injectFooterPrompt is true (Pipe.kt:8044-8050).
        setJsonOutput(MethodActorResponse::class)

        // 3. Reinforce the roleplay framing. Skip for pure reasoning
        //    pipes (StructuredCot etc.) — they use the reasoning
        //    method's own prompt template.
        setSystemPrompt(buildString {
            append(rolePlayPrompt(depth, duration))
            append("\n\nROLE PLAY AS THE FOLLOWING CHARACTER:\n")
            append(author)
        })
    }
    .setPipeName(pipeName)
    .setMaxTokens(maxTokens)
    .setTemperature(temperature)
    .setTopP(topP)
    .setTokenBudget(
        TokenBudgetSettings(
            contextWindowSize = contextWindowSize,
            maxTokens = maxTokens,
            truncationSettings = tunedTruncation
        )
    )
```

Three steps, all required:

1. **Flip the metadata gate.** `pipeMetadata["injectFooterPrompt"] = true`.
   Without this, `getFooterPromptForReasoning()` at `Pipe.kt:8044-8050`
   returns `""` and the JSON schema never reaches the wire.

2. **Wire the JSON output rail.** `setJsonOutput(kclass)` populates
   `this.jsonOutput` with the example JSON schema. The footer machinery
   reads this and emits the schema into the system prompt. Calling
   `requireJsonPromptInjection()` is also valid but redundant — `setJsonOutput`
   calls `ensureJsonPromptInjectionEnabled()` internally at `Pipe.kt:2879`.

3. **(Roleplay author pipes only) Reinforce the framing.** Qwen's
   `authorBuilder` at `BedrockConfig.kt:639-738` goes through
   `reasonWithBedrock(...)` which calls `assignDefaults`
   (`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:218-223`)
   to set the system prompt to `rolePlayPrompt(...) + "ROLE PLAY AS THE FOLLOWING CHARACTER: ${roleCharacter}"`.
   Mantle bypasses `assignDefaults`, so the consumer must reproduce the
   framing manually. For reasoning pipes (StructuredCot, ExplicitCot,
   etc.), this step is unnecessary — the reasoning method's own prompt
   template is what the framework injects.

The KClass passed to `setJsonOutput` must match the JSON output contract
the downstream consumer expects. Mapping from `ReasoningMethod` to KClass
is enumerated at `ReasoningBuilder.kt:268-278`:

| ReasoningMethod | KClass |
|---|---|
| `RolePlay` | `MethodActorResponse::class` |
| `StructuredCot` | `StructuredCot::class` |
| `ExplicitCot` | `ExplicitReasoningDetailed::class` |
| `ProcessFocused` | `ProcessFocusedResult::class` |
| `BestIdea` | `BestIdeaResponse::class` |
| `ChainOfDraft` | `ChainOfDraftResponse::class` |
| `SemanticDecompression` | `SemanticDecompressionResponse::class` |

## Common failure mode — the pipe is the INNER reasoning pipe, not the outer

The opt-in gates the JSON output on the **reasoning pipe**, not the
parent. `getFooterPromptForReasoning()` at `Pipe.kt:8044-8050` reads:

```kotlin
val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false
```

`reasoningPipe` here is the inner pipe attached via `setReasoningPipe(...)`.
When consumer code does:

```kotlin
val outer = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    .requireJsonPromptInjection()
    .setJsonOutput(GameStoryResult::class)
    .setReasoningPipe(BedrockConfig.mantleAuthorBuilder31B(author = ...))
```

…the JSON contract is on `outer`, but the gate is read from
`outer.reasoningPipe` (the Mantle author pipe). Setting `injectFooterPrompt=true`
on `outer` does nothing. The opt-in must be applied INSIDE the
`mantleAuthorBuilder31B(...)` factory — i.e., on the Mantle-shaped pipe
that the factory returns.

This is the failure mode that bit autogenesis on 2026-07-30 in
`server/src/main/kotlin/globals/BedrockConfig.kt:1115-1198`. The factory
hand-rolled a `GenericOpenAIPipe` analogue of `authorBuilder` and missed
the `.apply { ... }` extension. Every call site that wrapped the factory
output in an outer pipe with `requireJsonPromptInjection() + setJsonOutput(...)`
plus `setReasoningPipe(mantleAuthorBuilder31B(...))` looked correct at
the call site but failed at the wire because the inner pipe's
`injectFooterPrompt` was `false`.

## Why the framework doesn't call `assignDefaults` on Mantle

`assignDefaults` at `ReasoningBuilder.kt:178-302` is designed for the
four first-party reasoning builders (`reasonWithBedrock`,
`reasonWithOllama`, `reasonWithOpenRouter`, `reasonWithGenericOpenAI`).
Each of these constructs a pipe via `createBedrockPipe(...)`,
`createOllamaPipe(...)`, etc. — pipe-construction helpers that take a
provider-specific config object and return a properly-typed pipe.

Mantle does not have a `createMantlePipe(...)` helper inside
`ReasoningBuilder`. The framework's Mantle entry point is
`GenericOpenAIPipe.setBedrockMantle(...)` (a setter on a subclass that
the consumer constructs themselves). `assignDefaults` accepts a
generic `Pipe` and would happily write the metadata on a Mantle pipe,
but the framework chose to encode the defaults at the subclass level
via `configureBedrockMantle` instead of routing every Mantle consumer
through `assignDefaults`. This is the design choice that makes the
opt-in pattern the consumer's responsibility.

`reasonWithGenericOpenAI` at `ReasoningBuilder.kt:419-427` would work
for Mantle if a `GenericOpenAIConfiguration` could be constructed for
the Mantle endpoint (the `baseUrl` and `apiMode` fields cover it
— `TPipe-Defaults/src/main/kotlin/Defaults/ProviderConfiguration.kt:281-295`).
Adding a `reasonWithMantle` factory to `ReasoningBuilder` that wraps
`configureBedrockMantle + assignDefaults` is the framework-side fix
that would eliminate the need for consumer-side opt-in. Out of scope
for this reference — the consumer-side fix is local and shippable
without framework changes.

## Verification recipe

For a Mantle author pipe that emits prose instead of JSON, the
diagnosis is three checks:

1. **Is the JSON output class set on the reasoning pipe?** Read
   `reasoningPipe?.jsonOutput` after construction. Empty string means
   `setJsonOutput(...)` was never called on the reasoning pipe.

2. **Is `injectFooterPrompt=true` on the reasoning pipe?** Read
   `reasoningPipe?.pipeMetadata?.get("injectFooterPrompt")`. `false`
   or `null` means the footer won't be injected.

3. **Does the wire-level system prompt contain the JSON schema?** Run
   the pipe with a captured request trace and grep the system prompt
   for the schema's class name. If absent, the footer didn't reach
   the wire — re-check steps 1 and 2.

The TDD discipline for the fix is to write a unit test that asserts the
raw `API_CALL_SUCCESS` content parses as the contract JSON. The test
fails today (proving the gap) and passes after the fix (proving the
contract holds). JUnit XML attribute checks are the source of truth
(`tests=N failures=0 errors=0`), not stdout `PASSED` markers — stdout
can drop lines when tests produce heavy output.

## When to apply this pattern

- Adding a new Mantle consumer author pipe. The factory must include
  the `.apply { pipeMetadata["injectFooterPrompt"] = true; setJsonOutput(...); setSystemPrompt(...) }` block. Without it, the pipe emits prose and downstream consumers silently degrade to empty/default values.
- Migrating an existing wire-level pipe from prose to JSON output. The
  same three-line `.apply` block applies; the only change is the KClass
  argument.
- Auditing a Mantle pipe that emits prose. The check is
  `pipeMetadata["injectFooterPrompt"] == true` (and the matching
  `setJsonOutput(...)` call). If either is missing, the wire prompt
  will not include the JSON schema.

## Out of scope

The infrastructure-side fix (Layer A cast safety at `Pipe.kt:8033/8047`
and Layer B structural wiring in `configureBedrockMantle`) is documented
in `references/mantle-reasoning-metadata.md`. Those keys are
**populated to default `false`** by the framework to match
`ReasoningSettings` defaults — opt-in is the consumer's responsibility.
This reference covers the consumer-side opt-in only.
