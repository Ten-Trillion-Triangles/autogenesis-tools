---
name: tpipe-pipe-builders
description: Use when wiring TPipe pipes or reasoning factories.
tags: [tpipe, bedrock, mantle, llm, kotlin]
---

# TPipe Pipe Builder Patterns

Class-level patterns for constructing `Pipe` instances in the TPipe
ecosystem. Use when the task is "wire a new LLM provider through TPipe,"
"port a Bedrock Converse pipe to Mantle," "add a reasoning-pipe factory,"
or "treat TPipe-Tuner output correctly."

## Choose the right Pipe class

| Provider | Pipe class | Where |
|---|---|---|
| Bedrock Converse (standard) | `bedrockPipe.BedrockMultimodalPipe` | `TPipe-Bedrock/` |
| Bedrock Mantle (OpenAI-compatible regional) | `genericOpenAIPipe.GenericOpenAIPipe` | `TPipe-GenericOpenAI/` |
| Ollama (local) | `ollamaPipe.OllamaPipe` | `TPipe-Ollama/` |
| OpenRouter | `openrouterPipe.OpenRouterPipe` | `TPipe-OpenRouter/` |

**Bedrock Mantle is NOT Converse.** Mantle uses an OpenAI-compatible
endpoint on a different host (`bedrock-mantle.{region}.api.aws` vs
`bedrock-runtime.{region}.amazonaws.com`). Use `GenericOpenAIPipe`
even when the underlying model is "a Bedrock model" — Mantle-only
models (e.g. Gemma 4 family) cannot be reached through Converse.

The setX() chain is identical across providers because they all extend
the base `Pipe` class. Differences:

| Knob | BedrockMultimodalPipe | GenericOpenAIPipe (Mantle) |
|---|---|---|
| Region | `setRegion(...)` | `setRegion(...)` (passed to `setBedrockMantle`) |
| API flavor | `useConverseApi()` (default) | `setBedrockMantle(region, modelId)` |
| Model ID | `setModel(<arn-or-id>)` | `setModel(<plain-id>)` — Mantle has no ARNs |
| Priority tier | `setServiceTier(BedrockPriorityTier.Flex)` | NOT supported — Flex is Bedrock-runtime only |
| Caching | `enableCaching(...)` | NOT supported |
| Mantle auth | n/a | Auto: env-var keys → Bearer; else SigV4 fallback |

## Reasoning-pipe factory pattern

The 6 reasoning-builder functions in `BedrockConfig.kt`
(`authorBuilder`, `obsessivePlannerBuilder`, `bestIdeaBuilder`,
`structuredCotBuilder`, `processFocusedBuilder`, `explicitCotBuilder`)
all share a 4-line skeleton:

```kotlin
val reasoningSettings = ReasoningSettings(reasoningMethod=…, depth=…, duration=…, reasoningInjector=…, numberOfRounds=…, focusPoints=…)
val config = BedrockConfiguration(region=…, model=…)
val pipeSettings = PipeSettings(model=…, temperature=…, topP=…, maxTokens=…, pipeName=…)
val pipe = reasonWithBedrock(config, reasoningSettings, pipeSettings) as BedrockMultimodalPipe
```

When porting any of these to Mantle, replace the bottom three lines with
a `GenericOpenAIPipe` chain. The `ReasoningSettings` and
`ReasoningMethod` enums stay valid — TPipe's reasoning layer is
provider-agnostic; only the wire layer changes.

### Mantle reasoning-builder skeleton — use `reasonWithGenericOpenAI`, not hand-rolled

The hand-rolled `GenericOpenAIPipe().setBedrockMantle(...).setMaxTokens(...)` chain
that an earlier version of this section taught is **wrong by default** for any
author-style pipe (RolePlay) or reasoning-method pipe (StructuredCoT, ExplicitCoT,
ProcessFocused, ChainOfDraft, SemanticDecompression, BestIdea). The
reasoning layer (CoT / structured / explicit / RolePlay) is **not** "applied
via system prompt injection by TPipe itself once the pipe is initialized" —
that note was incorrect. The reasoning layer is wired by
`ReasoningBuilder.assignDefaults` at
`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:178-302`,
and `assignDefaults` is only invoked by the four first-party builders
(`reasonWithBedrock`, `reasonWithOllama`, `reasonWithOpenRouter`,
`reasonWithGenericOpenAI`). Hand-rolling the `GenericOpenAIPipe` chain
skips `assignDefaults` entirely.

**Port the Qwen `authorBuilder` (or any reasoning-method builder) to Mantle by
replacing `reasonWithBedrock(...)` with `reasonWithGenericOpenAI(...)` and
passing a `GenericOpenAIConfiguration` that targets the Mantle endpoint. Do
not hand-roll the `GenericOpenAIPipe` chain.**

```kotlin
val genericConfig = GenericOpenAIConfiguration(
    model = modelIdRaw,
    baseUrl = "https://bedrock-mantle.${region}.api.aws/openai/v1",
    apiMode = "OpenAI",
    apiKey = ""  // setBedrockMantle resolves auth via env vars / SigV4
)
val reasoningSettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.RolePlay,         // or StructuredCot, ExplicitCot, etc.
    roleCharacter = author,                             // for RolePlay
    depth = depth,
    duration = duration,
    reasoningInjector = ReasoningInjector.AfterUserPrompt,
    numberOfRounds = rounds,
    focusPoints = focusPoints
)
val pipeSettings = PipeSettings(
    model = modelIdRaw,
    temperature = temperature,
    topP = topP,
    maxTokens = maxTokens,
    pipeName = pipeName
)
val pipe = reasonWithGenericOpenAI(genericConfig, reasoningSettings, pipeSettings)
    as GenericOpenAIPipe
```

`reasonWithGenericOpenAI` lives at
`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:419-427`.
It calls `createGenericOpenAIPipe(genericConfig)` then
`assignDefaults(reasoningSettings, pipeSettings, pipe)`. `assignDefaults`
wires seven things the hand-rolled chain silently skips:

1. `requireJsonPromptInjection()` — the JSON I/O rail
2. `setJsonOutput(...)` — typed output schema (e.g. `MethodActorResponse`,
   `StructuredCot`, `ExplicitReasoningDetailed`, `ChainOfDraftResponse`, etc.)
3. `setSystemPrompt(rolePlayPrompt(...) + "ROLE PLAY AS THE FOLLOWING CHARACTER: ...")` —
   the role Character baked into the system prompt at the right priority
4. `targetPipe.pipeMetadata["reasoningMethod"] = settings.reasoningMethod.toString()` —
   the metadata the downstream consumers read via `extractJson<T>(pipeContent.text)`
5. `targetPipe.pipeMetadata["injectMiddlePrompt"] = settings.injectMiddlePrompt`
6. `targetPipe.pipeMetadata["injectFooterPrompt"] = settings.injectFooterPrompt`
7. `targetPipe.applyPipeSettings(pipeSettings)` — baseline settings copy

Skipping any of 1–4 means the model never sees the JSON schema rail, never
returns the JSON shape the consumer expects, and the downstream JSON parser
silently degrades to defaults. This is the failure mode that produced the
"Gemma 4 31B returns prose instead of JSON" bug on Mantle author and writing
pipes (verified 2026-07-30 against `~/.tpipe/debug/trace/Round_*_Turn_*`): the
same prompt that returned valid `MethodActorResponse` JSON on the Qwen path
returned markdown narrative on the Mantle path because the
`buildMantleAuthorPipe` port skipped `reasonWithGenericOpenAI`.

The Mantle-specific knobs (region, model ID, auth) plug into
`GenericOpenAIConfiguration` via `baseUrl` and `apiMode`. The actual Mantle
endpoint is `https://bedrock-mantle.${region}.api.aws/openai/v1` and the
`apiMode` is `"OpenAI"` (OpenAI Chat Completions wire format). The
`BedrockMantleConfiguration` record at
`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleConfiguration.kt:34-74`
exposes the right shape; convert it to `GenericOpenAIConfiguration` at the
call site. Mantle auth still resolves via `setBedrockMantle` — pass empty
`apiKey` and let `createGenericOpenAIPipe` install the env-var / SigV4
fallback as the construction-time default.

**Pitfall — hand-rolled `GenericOpenAIPipe().setBedrockMantle(...)` for a
RolePlay or reasoning-method pipe silently bypasses the framework
integration that the Qwen `authorBuilder` gets for free.** A Mantle
reasoning-builder that constructs a `GenericOpenAIPipe` directly, sets
`setBedrockMantle`, sets a few basic knobs, and returns, ships a pipe that
does not have the JSON I/O contract, the reasoning-method metadata, the
roleplay character baked into the system prompt, or the typed output schema.
The pipe still runs and produces text — the model just produces markdown
narrative instead of the expected JSON. The downstream
`extractJson<T>(pipeContent.text)` call returns null, the consumer falls
back to a default `T()`, and the bug only surfaces as "thinking vanished"
or "validators silently passing" in production logs. Verified 2026-07-30:
the autogenesis `buildMantleAuthorPipe` and `buildMantleReasoningPipe` (in
the consumer repo, `server/src/main/kotlin/globals/BedrockConfig.kt`) had
this exact shape and the live traces showed 4/4 `mantle author 31b` calls
returning prose where JSON was expected, plus 6/6 `mantle structured cot`
(E2B) calls returning empty `{}`. **Fix:** route the Mantle builder through
`reasonWithGenericOpenAI` with the appropriate `ReasoningMethod`.

The two completion patterns that DO work when hand-rolling (because they
inline what `assignDefaults` would have wired):

```kotlin
val pipe = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    .apply {
        requireJsonPromptInjection()
        setJsonOutput(MethodActorResponse::class)              // or per ReasoningMethod
        pipeMetadata["injectFooterPrompt"] = true              // enables JSON completions
        setSystemPrompt(buildString {
            append(rolePlayPrompt(depth, duration))
            append("\n\nROLE PLAY AS THE FOLLOWING CHARACTER:\n")
            append(author)
        })
    }
```

But the right answer for any new builder is still `reasonWithGenericOpenAI`
— that's the framework integration the Qwen path consumes. Use the
`.apply { ... }` opt-in shape only when patching an existing hand-rolled
factory that you can't refactor into the framework path. See
`references/mantle-author-pipe-framework-integration.md` for the full
symptom catalog, the cross-pipe audit, the per-call-site fix recipe, and
the hermetic verifier that proves the integration is wired.

**When the bare hand-rolled chain is still correct:** a Mantle pipe that is
NOT a reasoning-method pipe (just a chat-completions call with no RolePlay,
no StructuredCoT, no chain-of-thought) can use the bare
`GenericOpenAIPipe().setBedrockMantle(...)` chain — there is no reasoning
method to wire. Example: a plain content-generation pipe that takes a
user prompt and emits prose. The hand-rolled shape is appropriate when
`reasoningMethod` would be `null` / unset. For any pipe that the Qwen
counterpart builds via `reasonWithBedrock(...)`, the Mantle counterpart
must use `reasonWithGenericOpenAI(...)`.

**Pitfall — `Pipeline.enableStallDetector(...)` only reaches entry pipes;
consumer-side recursion is required to cover reasoning, validator,
branch, and transformation children.** `Pipeline.init()` propagates the
stall config to every pipe in `pipeline.getPipes()`, but the in-tree
comment at `Pipeline.kt:1217-1226` explicitly states that stall detection
does NOT recursively cascade — each pipe owns its own
`StreamingStallDetector` and the config is merely propagated to the same
level. Reasoning, validator, transformation, and branch children set via
`setReasoningPipe` / `setValidatorPipe` / `setTransformationPipe` /
`setBranchPipe` (`Pipe.kt:1683-1711`) are NOT reachable through that
mechanism. Verified on Autogenesis 2026-08-02: relying on
`Pipeline.enableStallDetector` left the reasoning child of
`reversal-pipe`, the validator/rectifier chain of
`defensive legality checker pipe`, and the karma-fallback branch of
`mantle npc karma pipe (g31b)` unprotected — the same silence pattern
the live trace audit surfaced (1/232 non-streaming provider calls would
have been the upper bound). **Fix shape** — a `BedrockConfig`-style helper
that walks the public child graph with cycle protection and calls
`pipe.enableStallDetector(...)` on every node:

```kotlin
fun configureGameplayStallDetection(
    pipeline: Pipeline,
    callback: StallCallback? = null
): Pipeline {
    val visited = IdentityHashMap<Pipe, Boolean>()
    pipeline.getPipes().forEach { pipe ->
        walkAndConfigure(pipe, callback, visited)
    }
    return pipeline
}

private fun walkAndConfigure(
    pipe: Pipe,
    callback: StallCallback?,
    visited: IdentityHashMap<Pipe, Boolean>
) {
    if (visited.put(pipe, true) != null) return
    pipe.enableStallDetector(gameplayStallDetectorConfig, callback)
    listOfNotNull(
        pipe.validatorPipe,
        pipe.transformationPipe,
        pipe.branchPipe,
        pipe.reasoningPipe
    ).forEach { child -> walkAndConfigure(child, callback, visited) }
}
```

Constraints observed in the working autogenesis patch: (a) use
`IdentityHashMap<Pipe, Boolean>` for cycle protection — `pipeId` is
`protected var` on `Pipe`, not callable from the consumer; (b) apply
the helper inside every `.apply { ... }` builder block right before
`init(true)` so the policy lands before children traverse; (c) keep the
helper generic — both `BedrockPipe` and `GenericOpenAIPipe` extend
`com.TTT.Pipe.Pipe`, so the same recursion covers Mantle and Bedrock
pipes uniformly without any pipe-type filter. Companion TDD test recipe
and the wiring audit that proved 24/24 + 10/10 coverage of the
orchestrator sites lives at
`references/stall-detection-recursive-config.md`.

## TPipe-Tuner output → source, not runtime JSON

`TPipe-Tuner` (`gradle :TPipe-Tuner:run --expected-tokens N`) produces a
JSON `TruncationSettings` blob. The user-correct handling is:

1. Run once with the project's default stress-test string and a known
   token count for the target tokenizer.
2. Take the `OPTIMAL CONFIGURATION` block field-by-field.
3. **Promote to source** as a Kotlin `private val` constant next to
   other per-model configuration:
   ```kotlin
   private val MANTLE_TRUNCATION_SETTINGS = TruncationSettings(
       multiplyWindowSizeBy = 0,
       countSubWordsInFirstWord = true,
       // ... 15 fields total
   )
   ```
4. Reference the constant from the builder body via `setTokenBudget(TokenBudgetSettings(..., truncationSettings = MANTLE_TRUNCATION_SETTINGS))`.

**Anti-pattern (corrected 2026-07-29):** storing the tuner output as
`resources/.../truncation.json` and loading via `getResourceAsStream`
on every builder call. The optimized values are static for the lifetime
of the model family — Google does not silently ship tokenizer changes.
The JSON never mutates at runtime, so the resource loader is dead code.

**When to re-run the tuner:** when the model family changes (Gemma 4 →
Gemma 5), not when token counts drift on the same family.

## Payload destructuring + `pipeMetadata` as per-pipe carrier

When a builder receives a structured payload data class (e.g.
`MapSafetyPayload(imageBytes, mapData)`) but the pipeline has multiple
pipes that each need only one fragment of it, the canonical shape is:

1. Destructure at the top of the builder into named locals — `val
   imageBytes = payload.imageBytes; val mapData = payload.mapData`.
2. Bind each fragment onto the matching pipe's `pipeMetadata` map
   inside that pipe's `.apply { ... }` block:
   ```kotlin
   val imageChecker = BedrockMultimodalPipe().apply {
       // ... config setters ...
       pipeMetadata["imageBytes"] = imageBytes
   }
   val contentChecker = BedrockMultimodalPipe().apply {
       // ... config setters ...
       pipeMetadata["mapData"] = mapData
   }
   ```
3. The downstream pipe reads with
   `pipe.pipeMetadata["imageBytes"] as ByteArray` (the map is
   `MutableMap<Any, Any>` per `Pipe.kt:1933`).

This is cleaner than threading the full payload through the
`MultimodalContent` because:

- Each pipe carries only what it needs — no risk of a downstream pipe
  accidentally consuming a fragment meant for an upstream sibling.
- The metadata survives the LLM round-trip via the pipe's own state.
- Read sites are explicit (`pipeMetadata["imageBytes"]`) instead of
  hidden in a payload wrapper.

**Pitfall — bind via `pipeMetadata["<key>"] = <val>`, NOT via the
multimodal payload's `addBinary`.** `MultimodalContent.addBinary` puts
bytes onto the *input* of the next LLM call. `pipeMetadata` puts them
onto the pipe's own state, readable by every callback attached to that
pipe (`setOnFailure`, validator, transformation, etc.). For safety
agents where the validator and failure callback both need access to
the artifact (the validator to judge it, the failure callback to send
the rejection reason to the client), `pipeMetadata` is the right seam
— `addBinary` would push the bytes back into the LLM input on every
validator invocation.

**Why the locals exist.** The locals aren't strictly required — the
binding could be `pipeMetadata["imageBytes"] = payload.imageBytes`
inline. But the local at the top of the function makes the data flow
visible at a glance: "this function takes these two things, splits
them here, hands one to each pipe." Future readers don't have to
scroll to each pipe block to discover what data exists.

## TruncationSettings → TokenBudgetSettings

There is no `Pipe.setTruncationSettings(...)` setter. The correct entry
point is `setTokenBudget(TokenBudgetSettings(...))` where
`TokenBudgetSettings.truncationSettings` is the carved-out field. TPipe
reads truncation settings via `TokenBudgetSettings.toTruncationSettings(pipe)`
internally; the budget setter is the public hook.

```kotlin
val budget = TokenBudgetSettings(
    contextWindowSize = 128_000, // or 256_000 for Gemma 4 31B
    maxTokens = 8000,
    truncationSettings = MANTLE_TRUNCATION_SETTINGS
)
pipe.setTokenBudget(budget)
```

## Mantle model ID authoritative list

Gemma 4 family on Mantle — verified live 2026-07-29 against
`https://bedrock-mantle.us-east-1.api.aws/openai/v1/chat/completions`:

| Model ID | Params | Context | Reasoning |
|---|---|---|---|
| `google.gemma-4-e2b` | 5.1B total / 2.3B effective (PLE) | 128K | yes |
| `google.gemma-4-26b-a4b` | 25.2B MoE / 3.8B active | 256K | yes |
| `google.gemma-4-31b` | 30.7B dense | 256K | yes |

Confused IDs that DO NOT EXIST (404 from Mantle):

- `google.gemma-4-e4b` — small variant is named E2B (PLE), not E4B
- `google.gemma-4-4b` — no such model

Standard Bedrock `aws bedrock list-foundation-models --by-provider GOOGLE`
does NOT list the Mantle-only subset. Gemma 4 family is Mantle-only.

## Streaming API parity — unified as of 2026-07-30 (TPipe commit `3e5d94d2`)

The streaming surfaces are **symmetric across providers** since the
unification landed. `StreamingCallbackBuilder` lifted to `com.TTT.Pipe`
(`GenericOpenAIPipe.kt:10` import); both `BedrockPipe.streamingCallbacks`
and `GenericOpenAIPipe.streamingCallbacks` use the same DSL. Anything
that worked on Bedrock works on Mantle identically:

| Surface | BedrockPipe | GenericOpenAIPipe (Mantle) |
|---|---|---|
| Enable flag | `streamingEnabled: Boolean = false` (default) | `streamingEnabled: Boolean = false` (default) |
| Setter | `enableStreaming()` (no-arg) OR `setStreamingEnabled(Boolean)` | `enableStreaming()` (no-arg) OR `setStreamingEnabled(Boolean)` — both available since `GenericOpenAIPipe.kt:522-532` |
| Single callback | `setStreamingCallback(suspend (String) -> Unit)` | `setStreamingCallback(suspend (String) -> Unit)` |
| Multi-callback builder | `streamingCallbacks { add(cb1); add(cb2); concurrent() }` | **`streamingCallbacks { add(cb1); add(cb2); concurrent() }` at `GenericOpenAIPipe.kt:494-505`** — identical DSL lifted from base package |
| Propagate to descendant pipes | None | `propagateStreamingCallback(callback)` — auto on both `setStreamingCallback` AND `streamingCallbacks { add(cb) }` |

**Pre-unification pitfall (historical, do not re-introduce):** before
`3e5d94d2`, Mantle's only working streaming pattern was a single
`setStreamingCallback(cb)` because `streamingCallbacks { add(...) }`
didn't exist on Mantle. "Single callback + fan-out scope" worked but
forced every multi-listener caller to write a multiplexer lambda. The
unification eliminated that constraint.

**Consumer-side wiring — the autogenesis `AgentWorkStreamStreaming`
factory (`server/src/main/kotlin/org/ttt/autogenesis/server/AgentWorkStreamStreaming.kt`)
was hard-typed `BedrockPipe` via `if(pipe !is BedrockPipe) return` at
line 110, which silently dropped every Mantle pipe. Fixed by adding a
parallel `configureGenericOpenAiStreaming(connectionIds, pipe)` that
dispatches on the same DSL. With both branches using the lifted
`streamingCallbacks { add(cb) }` builder, callers can swap a Bedrock
pipe for a Mantle pipe without restructuring the sink plumbing.
See `references/mantle-streaming-consumer-wiring.md` for the full
consumer-side fix recipe (factory dispatch, sibling-pipe gap, mockk
stub signature mismatch, filterIsInstance callsite relaxation).

**Pitfall — `StreamingCallbackBuilder.add(callback)` has overload
ambiguity between `suspend (String) -> Unit` and `(String) -> Unit`
lambdas.** Calling `add { chunk -> ... }` as a single-expression
lambda fails with "Overload resolution ambiguity" because Kotlin can't
infer which overload matches. **Fix:** use a typed local val:

```kotlin
val callback: (String) -> Unit = { chunk ->
    AgentWorkStreamDispatcher.appendChunkToMany(ids, chunk)
}
streamingCallbacks {
    add(callback)
}
```

The single-line lambda form only resolves when the body has a
non-`Unit`-returning expression (e.g. `add { chunk: String -> ... }`
also ambiguous). The typed-val form always resolves and matches the
existing pattern at `server/src/main/kotlin/agent/builders/systemActions/answerAgent.kt:401-405`.

**Pitfall — factory pattern `if(pipe !is X) return` silently drops
new pipe types.** When a consumer factory uses type-test early-return
to gate provider-specific streaming setup, adding a new pipe type
later means instant silent regression — no compile error, no runtime
exception, just no streaming. The autogenesis consumer factory had
this shape for Bedrock-only; the Mantle migration surfaced
30+ Mantle pipes streaming to nobody in production. **Always dispatch
explicitly with `when (pipe) { is X -> ...; is Y -> ...; else -> noop }`**
when the factory covers multiple providers, and add a unit test that
asserts the new type gets a callback registered.

**Pitfall — `Pipeline.getPipes()` returns entry-level pipes only;
sibling pipes in the same Pipeline are invisible to type-agnostic
consumers.** TPipe `Pipeline` exposes no
`getAllChildPipes()` / `getAllPipes()` / `getChildren()` API — only
`getPipes()` (entry level). A consumer factory that walks
`pipeline.getPipes()` and registers a streaming callback on each pipe
will NOT see sibling pipes inside the same pipeline. **Two fixes:**

1. The SDK's `propagateStreamingCallback(callback)` walks
   `reasoningPipe` / `transformationPipe` / `branchPipe` /
   `validatorPipe` on a single pipe, so registering on the entry
   pipe propagates to its descendants. This covers the single-pipe
   "Mantle pipe has children" case.
2. For multi-pipe pipelines (`pipeline.add(pipeA); pipeline.add(pipeB)`)
   the consumer factory cannot reach sibling `pipeB`. **Fix at the
   agent-builder level:** self-register callbacks inside the agent
   builder for the non-entry pipes, with the connection scope passed
   in as an `connectionIds: Collection<String> = emptyList()` parameter.
   `buildResponseRefinementAgent(connectionIds)` in
   `server/src/main/kotlin/agent/builders/writingAgent/ResponseRefinementAgent.kt`
   is the working example.

**Pitfall — `filterIsInstance<X>()` scattered across orchestrators
hides cross-provider streaming gaps.** A grep for
`filterIsInstance<BedrockPipe>()` in orchestrator files surfaced
8 callsites across `gameplayOrchestrator.kt:1499/1550/1633/1788/1979/2023/2067`
and `npcOrchestrator.kt:639` — each hard-codes Bedrock and drops
Mantle. **Two-step fix:** (a) dispatch with `when` for sites that have
mixed-type pipelines (Bedrock codepath byte-identical, Mantle pipes get
the analogous wiring); (b) add a parallel `filterIsInstance<GenericOpenAIPipe>()`
line for narrative-throttler sites (Bedrock line preserved, Mantle line
added). Verify parity with
`grep -rnE 'filterIsInstance<(BedrockPipe|GenericOpenAIPipe)>\(\)'` — counts
must show Bedrock and Mantle matching across the orchestrator files.

**Pitfall — mockk stub signature mismatch on signature change.** When
a production callsite adds an argument (e.g. `buildResponseRefinementAgent()`
→ `buildResponseRefinementAgent(connectionIds)`), mockk stubs matching
the old zero-arg shape (`every { buildResponseRefinementAgent() } returns mockPipeline`)
silently fall through to the real function — which then calls
`pipe.init()` on a Mantle pipe without API credentials and throws
`GenericOpenAIPipe.init: GenericOpenAI API key is required`. Symptom
looks unrelated but the cause is the mockk stub. **Fix:** update
mockk stubs to `every { buildResponseRefinementAgent(any()) }` or
match the exact new signature. Re-run focused tests after any
signature change to catch this regression class.

**Pitfall — fluent chain on `GenericOpenAIPipe` widens type to `Pipe`
when a base-class setter sits mid-chain.** `Pipe.setMaxTokens(max: Int)`,
`Pipe.setTemperature(...)`, `Pipe.setTopP(...)`, and `Pipe.setTokenBudget(...)`
return the base `Pipe`, not the subclass. A chain like
`GenericOpenAIPipe().setPipeName(...).setBedrockMantle(...).setMaxTokens(64)`
infers the post-`setMaxTokens` type as `Pipe`, so any subsequent
`setApiKey(...)`, `setBedrockMantleAuth(...)`, or any other method only
declared on `GenericOpenAIPipe` fails to compile with "Unresolved
reference." This bites hardest in test files written as one-shot
builder expressions. **Two fixes:**

1. Put base-class setters inside `apply { ... }` so the receiver stays
   the subclass:
   ```kotlin
   val pipe = GenericOpenAIPipe()
       .setBedrockMantle(region = "us-east-2", modelId = "google.gemma-4-31b")
       .apply {
           setPipeName("...")
           setApiKey("...")
           setMaxTokens(64)              // base-class setter, OK inside apply
           pipeMetadata["injectMiddlePrompt"] = true  // subclass field, OK inside apply
       }
   ```
2. If chaining continues outside `apply`, put all subclass-only setters
   before any base-class setter that widens.

Same shape applies to any `GenericOpenAIPipe` fluent chain that mixes
subclass methods (`setBedrockMantle`, `setBedrockMantleWithResponses`,
`setBedrockMantleAuth`, `setApiKey`, `setApiMode`, `setPipeName` only
because it returns `Pipe` too) with base-class setters. When in doubt,
the `.apply { ... }` form is the safest.

**Pitfall — Mantle reasoning-pipe metadata contract is populated
infrastructure-side by default `false`; consumers must opt in for
JSON-completion.** The framework deliberately leaves
`injectMiddlePrompt = false` and `injectFooterPrompt = false` on
every Mantle-shaped pipe (matching `ReasoningSettings` defaults per
the KDoc on `configureBedrockMantle` at
`GenericOpenAIPipe.kt:644-672`). These defaults are NOT a bug — they
match the documented `ReasoningSettings` defaults. But constructor
code that wants JSON-completion enforcement (a `MethodActorResponse`
or `GameStoryResult` from a Mantle author/reasoning pipe) must
opt in by setting `pipeMetadata["injectFooterPrompt"] = true` and
calling `setJsonOutput(kclass)` after `setBedrockMantle(...)`. Without
the opt-in, the JSON schema footer never reaches the wire and the
model emits prose — the model has no schema rail to follow. The
opt-in shape is the three-line `.apply { ... }`:

```kotlin
val pipe = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    .apply {
        pipeMetadata["injectFooterPrompt"] = true
        setJsonOutput(MethodActorResponse::class)
        // For roleplay author pipes: also wrap the author in the
        // roleplay system prompt prefix. Skip for reasoning pipes.
        setSystemPrompt(buildString {
            append(rolePlayPrompt(depth, duration))
            append("\n\nROLE PLAY AS THE FOLLOWING CHARACTER:\n")
            append(author)
        })
    }
```

Critical: the gate is read from the **reasoning pipe**, not the
parent. `getFooterPromptForReasoning()` at `Pipe.kt:8044-8050` reads:

```kotlin
val usingFooterPrompt = reasoningPipe?.pipeMetadata["injectFooterPrompt"] as? Boolean ?: false
```

When `mantleAuthorBuilder31B(...)` is wired as the inner reasoning
pipe via `setReasoningPipe(mantleAuthorBuilder31B(...))`, the opt-in
must be INSIDE the `mantleAuthorBuilder31B(...)` factory — on the
Mantle-shaped pipe that the factory returns. Setting
`injectFooterPrompt=true` on the outer parent pipe does nothing.
The autogenesis `buildMantleAuthorPipe` at
`server/src/main/kotlin/globals/BedrockConfig.kt:1115-1198` shipped
without the `.apply { ... }` block, causing every Mantle author pipe
to emit prose and every downstream consumer to silently degrade to
empty/default values. See `references/mantle-json-completion-opt-in.md`
for the full pattern, the consumer-side diagnosis recipe, the
ReasoningMethod → KClass mapping at `ReasoningBuilder.kt:268-278`,
and the framework-side alternative (a `reasonWithMantle` factory
added to `ReasoningBuilder` that wraps `configureBedrockMantle +
assignDefaults`).

**Pitfall — parent/child pipe alignment: when a host pipe's model
changes, the inner `setReasoningPipe(authorBuilder(...))` slot
silently inherits the `authorBuilder` default model if the call site
doesn't pass an explicit `model=` kwarg or wrap in `.apply {
setModel(...) }`. The parent and reasoning pipe models diverge
without compile error.** Verified 2026-07-30 during the Autogenesis
PalmyraX5 → qwenCoder30B cutover — every host pipe that had migrated
its `setModel(...)` line still wrapped its reasoning pipe in
`authorBuilder(...)` with no explicit model argument, leaving the
reasoning pipe on the prior default (which happened to be `PalmyraX5`
for these pipes). The `PalmyraX5ToG31bMigrationTest` and the
qwenCoder30B-style tests both passed because they only asserted pipe
*types*, never the reasoning pipe's model. **Detection recipe**:

```bash
# For each host pipe whose setModel line changed in the diff, find the
# matching setReasoningPipe and check whether the inner authorBuilder
# call passes model= explicitly OR wraps in .apply { setModel(...) }.
git diff --unified=3 server/src/main/kotlin/agent/builders/ | \
    grep -B2 -A6 'setReasoningPipe(BedrockConfig\.authorBuilder'
```

A site is **misaligned** when the inner call has neither `model =`
nor a `.apply { setModel(...) }` following it. **Fix shape**: wrap
each misaligned `authorBuilder(...)` in
`.apply { setModel(BedrockConfig.<parent-model>); setTokenBudget(BedrockConfig.<parent-budget>) }`
so the source reads unambiguously even if `authorBuilder`'s default
ever changes. See
`references/parent-child-pipe-alignment.md` for the full audit +
hardening recipe, the 7-site example list from the PalmyraX5 cutover,
and the post-edit verification script shape.
`configureBedrockMantle(config)` in `GenericOpenAIPipe.kt` writes the
keys directly with default `false` (matching
`ReasoningSettings.injectMiddlePrompt = false`), so any Mantle-shaped
pipe from this repo carries the contract by construction. See
`references/mantle-reasoning-metadata.md` for the full pattern, the
3-layer TDD verification recipe (cast-safety + structural + provider
parity), and the red→green discipline that proves a Mantle-shaped pipe
is first-class — not a silent empty-string fallback for the
provider-coupling hole the bug report named.

## Mantle auth resolution order

`GenericOpenAIPipe.setBedrockMantle(...)` auto-detects auth in this order:

1. `BEDROCK_MANTLE_API_KEY` env var → Bearer fallback
2. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars → SigV4
   with service identifier `bedrock-mantle`
3. (no fallback beyond env vars)

For programmatic / CI use, set the AWS env vars at test-run time
through an INI-credentials-file parser — never hardcode keys in source.

## Live-test gating pattern

When wiring Mantle or any live LLM provider, gate the test class with
JUnit 5's `@EnabledIfEnvironmentVariable(named = "...LIVE_TEST...",
matches = "true")` AND per-method `assumeTrue` on credential presence.
The two-stage gate produces `tests=N skipped=N failures=0` on JUnit
XML when the gate is off — the proper "skip, not fail" behavior for
optional live integration tests.

For Mantle: the gate env var is conventionally
`BEDROCK_MANTLE_LIVE_TEST=true`. The credential-file env var is
conventionally `BEDROCK_AWS_CREDENTIALS_FILE=~/.aws/credentials`, with
the profile name resolved via `BEDROCK_AWS_PROFILE` (defaults to
`"bedrock"`).

**Pitfall — `@Ignore` on the class is a source-edit trap. Gate the
class on the env var alone, not on `@Ignore` + source removal.**
A live test marked `@Ignore("set X=true to enable")` will be skipped
silently EVERY time someone runs gradle without first deleting the
annotation. The operator has to edit source to enable it, the test
runs, and then someone has to remember to put the `@Ignore` back. That
"edit-source-to-inspect" cycle compounds across iterations and is a
source-control noise generator.

**Correct shape** (verified on Autogenesis `MapUploadSafetyAgentLiveTest`,
2026-08-10):

```kotlin
class MapUploadSafetyAgentLiveTest {
    private fun liveTestEnabled(): Boolean =
        System.getenv("BEDROCK_MANTLE_LIVE_TEST") == "true"

    @Test
    fun runSafetyAgentEndToEndAgainstLiveAws(): Unit = runBlocking {
        assumeTrue(
            "set BEDROCK_MANTLE_LIVE_TEST=true to enable the live test",
            liveTestEnabled()
        )
        // ... test body
    }
}
```

No `@Ignore` annotation on the class. The `assumeTrue` inside the test
method is the only gate. Inspection runs become a single shell
command — no source edits:

```bash
BEDROCK_MANTLE_LIVE_TEST=true \
  AWS_PROFILE=BedrockKey \
  ./gradlew :server-extend:test --tests 'network.MapUploadSafetyAgentLiveTest' --rerun-tasks
```

Subshells don't inherit `.bashrc`, so the env var MUST be exported in
the same shell that runs gradle (use `export` ahead of the gradle
invocation, or chain with `&&`). Running `gradle test` with the var
set inline but not exported will silently skip the gate.

The Autogenesis codebase has 11+ live tests using the env-var gate as
the idiomatic answer. Match that shape; do not introduce `@Ignore`.

## See Also

- `references/mantle.md` — Mantle endpoint, auth, model IDs, live-test gating
- `references/mantle-reasoning-metadata.md` — Mantle reasoning-pipe metadata contract: construction-time wiring of `injectMiddlePrompt` / `injectFooterPrompt` in `configureBedrockMantle`, the override path for callers who want injection, the 3-layer TDD verification recipe (cast safety at `Pipe.kt:8033/8047` + structural metadata presence + provider parity across all five builders), and the red→green discipline that proves the test would catch a regression if the structural fix were removed.
- `references/mantle-author-pipe-framework-integration.md` — Consumer-side Mantle author/reasoning-pipe framework integration. The lesson from the 2026-07-30 bug triage: hand-rolling `GenericOpenAIPipe().setBedrockMantle(...)` for a RolePlay or reasoning-method pipe silently bypasses the framework integration that `reasonWithBedrock` + `assignDefaults` provides. The correct Mantle port is `reasonWithGenericOpenAI(genericConfig, reasoningSettings, pipeSettings)` with a `GenericOpenAIConfiguration` that targets the Mantle endpoint. Covers the symptom catalog (4/4 `mantle author 31b` calls returning prose, 6/6 `mantle structured cot` E2B calls returning empty), the cross-pipe audit of every Mantle builder site (~22 calls across `agent/builders/`), the per-call-site fix recipe (replace the factory wholesale, or patch with the `.apply { ... }` opt-in), the 3-layer design (cast safety + structural metadata + framework integration), and the hermetic verifier that proves the integration is wired. Triggered when a Mantle pipe emits prose instead of the contract JSON, or when adding a new Mantle consumer author pipe.
- `references/mantle-json-completion-opt-in.md` — Mantle JSON-completion opt-in pattern for consumer author/reasoning pipes. The three-line `.apply { pipeMetadata["injectFooterPrompt"]=true; setJsonOutput(...); setSystemPrompt(...) }` shape after `setBedrockMantle(...)`, the consumer-side diagnosis recipe (read `jsonOutput` + `pipeMetadata["injectFooterPrompt"]` on the reasoning pipe, not the parent), the `ReasoningMethod → KClass` mapping at `ReasoningBuilder.kt:268-278`, and the framework-side alternative (`reasonWithMantle` factory). Triggered when a Mantle pipe emits prose instead of the contract JSON, or when adding a new Mantle consumer author pipe.
- `references/agent-migration-bedrock-to-mantle.md` — full recipe for
  porting an existing agent pipe from `BedrockMultimodalPipe` (Converse)
  to `GenericOpenAIPipe` (Mantle), including the 1-to-1 setter swap
  table, branch-pipe fallback strategies, the `init()` credential
  trap, TDD assertions, and the pre-existing-failure baselining
  discipline. Verified on 8 Autogenesis LOW agents (2026-07-29).
- `references/mantle-streaming.md` — Mantle streaming API reference:
  the unified DSL surface (`streamingCallbacks { add(cb); concurrent() }`,
  `enableStreaming()`), the `setStreamingCallback` / descendant
  propagation pattern, the `BedrockMantleAuth.Streaming` auth shape,
  and the streaming chunk-emission semantics. Verified during the
  2026-07-30 Mantle streaming unification.
- `references/mantle-streaming-consumer-wiring.md` — Autogenesis
  consumer-side patterns produced during the 2026-07-30 streaming
  parity work: factory pipe-type dispatch (the silent-drop bug from
  `if(pipe !is BedrockPipe) return`), the
  `Pipeline.getPipes()`-only-traversal limit and sibling-pipe fix
  via `connectionIds: Collection<String>` parameter, the
  `filterIsInstance<X>()` callsite relaxation across orchestrators,
  the mockk stub signature-mismatch regression on signature changes,
  and the `StreamingCallbackBuilder.add(lambda)` overload-ambiguity
  disambiguation pattern (typed local val).
- `references/bedrock-bindings-local-override.md` — Bedrock model
  binding ritual when adding a new model: the two-property-file
  pattern (`~/.autogenesis/config/bedrock.properties` runtime + `server/bedrock.local.properties` test fallback), the `ConfigSource.property` + `bindInferenceProfile` chain in `BedrockConfig.kt`, and the recipe for keeping account-bound ARNs out of source.
- `references/parent-child-pipe-alignment.md` — When a host pipe's `setModel(...)` line changes, the inner `setReasoningPipe(authorBuilder(...))` slot silently inherits the `authorBuilder` default unless the call site passes `model = ...` or wraps in `.apply { setModel(...) }`. The audit recipe (per-host-pipe grep + alignment check), the 7-site example list from the 2026-07-30 PalmyraX5 cutover (writerAgent.kt:200/445, elderGodAgent.kt:130/181, npcHostileAgent.kt:88/130, npcActorAgent.kt:73), and the post-edit hermetic verifier script shape that proved the alignment.
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleConfiguration.kt`
  — canonical Mantle config record
- `TPipe-Tuner/src/main/kotlin/com/TTT/Tuner/TunerApp.kt` — tuner CLI
- `scripts/hermetic-pipe-cutover-verifier.sh` — starter template for
  post-edit pipe-family cutover verification. Copy to
  `/tmp/hermes-verify-<topic>.sh`, edit the CHECK blocks to anchor on
  the cutover's specific files/lines, and run. Captures per-check
  trace to `/tmp/hermes-verify-<topic>.log` and a human-readable summary
  to `/tmp/hermes-verify-<topic>.summary.txt`. Use as a re-runnable
  verification surface when the existing test suite doesn't pin the
  surface you actually changed (e.g. parent/child pipe alignment where
  pipe *types* are tested but reasoning pipe *models* aren't).
- `references/stall-detection-recursive-config.md` — recursive
  `StreamingStallConfig` helper recipe: cycle-safe walk over
  `validatorPipe / transformationPipe / branchPipe / reasoningPipe` via
  `IdentityHashMap`, the wiring rule that every orchestrator
  `.apply { ... }` block must call the helper before `init(true)`, the
  `DummyPipe`-based TDD test that proves a shared child is configured
  exactly once, and the source-coverage audit that pinned 24/24
  `gameplayOrchestrator` + 10/10 `npcOrchestrator` initialization sites
  on the 2026-08-02 autogenesis rollout.
- `references/tpipe-trace-capture.md` — the canonical pattern for
  "enable tracing on a pipeline, capture as JSON + HTML, and write
  to `TPipeConfig.getTraceDir()/<subFolder>/trace.{json,html}` via
  `com.TTT.Util.writeStringToFile`." Three-piece shape: `enableTracing`
  before `execute(...)`, `getTraceReport(TraceFormat.JSON/HTML)` for
  capture, the `saveSystemTrace` shape from
  `server/.../agent/runners/traceCleanup.kt`, the I/O-failure
  swallow-the-write pattern that keeps the orchestrator's response
  path live, and the test shape that pins the file-write contract via
  an empty `Pipeline()` (since `Pipeline` is `final` and cannot be
  subclassed for a stub). Triggered when the user asks to instrument
  an agent-running function with trace capture to the default TPipe
  trace dir.