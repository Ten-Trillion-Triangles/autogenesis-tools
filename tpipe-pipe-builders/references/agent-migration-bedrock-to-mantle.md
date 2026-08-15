# Bedrock → Mantle agent migration recipe

**Use when**: migrating an existing TPipe pipe-based agent from
`BedrockMultimodalPipe` (Converse API) to `GenericOpenAIPipe` (Mantle
endpoint), or porting a reasoning builder from `BedrockConfig.*Builder`
to its Mantle sibling.

**Verified**: 2026-07-29, Autogenesis LOW-agent batch — 8 agents migrated
end-to-end (`buildRailroadAgent`, `buildPlayDetectionAgent`,
`buildNPCValidator`, `buildReverseAgent`, `buildResponseRefinementAgent`,
`buildCharacterAgent`, `createUserActionClassificationPipeline`,
`buildOpenWidgetPipeline`).

## Rule: 1-to-1 swap, drop Bedrock-only knobs

| Bedrock knob (REMOVE) | Mantle equivalent |
|---|---|
| `useConverseApi()` | (drop — Mantle is OpenAI-native) |
| `setServiceTier(BedrockPriorityTier.Flex)` | (drop — Flex is Bedrock-runtime only) |
| `setModel(BedrockConfig.qwenCoder30B)` | `setBedrockMantle(region, BedrockConfig.mantleModelId("gemma4ModelId"))` |
| `setReasoningPipe(BedrockConfig.structuredCotBuilder(...))` | `setReasoningPipe(BedrockConfig.mantleStructuredCotBuilder(...))` |
| `setReasoningPipe(BedrockConfig.explicitCotBuilder(...))` | `setReasoningPipe(BedrockConfig.mantleExplicitCotBuilder(...))` |
| `enableStreaming()` | `setStreamingEnabled(true)` |
| `.enableStreaming().streamingCallbacks { add(cb) }` | `setStreamingEnabled(true)` + `setStreamingCallback(cb)` (no callback builder DSL) |
| `BedrockMultimodalPipe()` constructor | `GenericOpenAIPipe()` constructor |

All other `setX()` calls (`setTemperature`, `setTopP`, `setMaxTokens`,
`setTokenBudget`, `setSystemPrompt`, `setPipeName`,
`setJsonOutput`, `setPreInitFunction`, `setTransformationFunction`) are
provider-agnostic on the base `Pipe` class — leave them unchanged.

## Rule: Branch pipes stay on Bedrock when the model is Bedrock-only

The error-logging and retry factories are intentionally hardcoded to
`BedrockMultimodalPipe`:

- `agent.builders.validateAction.buildBranchFailureAgent(...)` returns
  `BedrockMultimodalPipe` with an `AgentRetry` JSON envelope (Standard
  Converse API contract). **Keep using it** even when the host pipe
  moves to Mantle.
- `agent.builders.validateAction.buildBranchPipeFromTemplate(...)`
  returns `BedrockMultimodalPipe` (hardcoded signature) — cannot
  follow a Mantle host. **Construct the Bedrock branch pipe inline**
  instead:

```kotlin
setBranchPipe(
    BedrockMultimodalPipe().apply {
        useConverseApi()
        setRegion("us-west-2")
        setServiceTier(BedrockPriorityTier.Standard)
        setModel(BedrockConfig.PalmyraX5)
        setTokenBudget(BedrockConfig.palmyraBudgetSettings)
        setReasoningPipe(
            BedrockConfig.authorBuilder(BedrockConfig.zetaReasoning).apply {
                setTokenBudget(BedrockConfig.palmyraBudgetSettings)
                setModel(BedrockConfig.PalmyraX5)
            }
        )
    }
)
```

**Symptom of using `buildBranchPipeFromTemplate` with a Mantle host**:

```
e: Unresolved reference 'setServiceTier'.
e: Unresolved reference 'BedrockPriorityTier'.
```

The factory calls `setServiceTier(BedrockPriorityTier.Standard)` and
returns `BedrockMultimodalPipe` even when the host pipe is
`GenericOpenAIPipe`. Construct the branch manually.

## Rule: Mantle factories call `init()` inside the factory body

`mantleStructuredCotBuilder`, `mantleExplicitCotBuilder`,
`buildMantleAuthorPipe`, `buildMantleReasoningPipe` all invoke
`runBlocking { pipe.init() }` inside the factory. `init()` throws
`IllegalStateException("GenericOpenAI API key is required. Call
setApiKey(), genericOpenAIEnv.setApiKey(), or set
GENERIC_OPENAI_API_KEY environment variable before init().")` if no
credentials are resolvable.

**Two implications:**

1. **Test fixtures** must install dummy credentials in `@BeforeTest`
   before invoking the factory:

   ```kotlin
   @BeforeTest
   fun installBearerCredentials() {
       GenericOpenAIEnv.setApiKey("test-key-not-used-for-network")
   }
   ```

2. **Production callers** must install AWS SigV4 credentials via
   `BedrockMantleEnv.setAccessKeyId(...)` /
   `setSecretAccessKey(...)` before constructing any agent. The
   `BedrockConfig.mantleRegion()` /
   `BedrockConfig.mantleModelId(...)` helpers resolve region and model
   ID from `bedrock-mantle.*` properties in `bedrock.local.properties`.

   Promote both helpers from `private` to `public` if agent files call
   them directly — they were `private` for the factories' internal
   use but agents outside the object need access.

## Rule: `mantleStructuredCotBuilder` / `mantleExplicitCotBuilder` return `Pipe`

The public API returns `Pipe`, not `GenericOpenAIPipe`. If a caller
declares its return type as `GenericOpenAIPipe` (because it needs to
chain Mantle-specific methods like `setStreamingCallback`), cast:

```kotlin
private fun createExplicitCotPipe(): GenericOpenAIPipe {
    return BedrockConfig.mantleExplicitCotBuilder(
        depth = ReasoningDepth.High,
        duration = ReasoningDuration.Short
    ) as GenericOpenAIPipe
}
```

Compile error without the cast:

```
e: Return type mismatch: expected 'GenericOpenAIPipe', actual 'Pipe'.
```

## TDD assertions for pipe type / Mantle wiring

`GenericOpenAIPipe.bedrockMantleAuth` is **private**;
`Pipe.model` is **protected** — can't assert via reflection. Assert
through the public observable surface:

```kotlin
val pipeline = buildRailroadAgent()
val host = pipeline.getPipes().first()

// Host pipe type
assertIs<GenericOpenAIPipe>(host, "host must be GenericOpenAIPipe for Mantle")

// Reasoning pipe type and Mantle factory identity
val reasoning = host.reasoningPipe
assertNotNull(reasoning, "host must wire a reasoning pipe")
assertIs<GenericOpenAIPipe>(reasoning, "reasoning must be GenericOpenAIPipe")
assertTrue(
    reasoning.pipeName.contains("mantle", ignoreCase = true),
    "reasoning name must reflect Mantle factory: ${reasoning.pipeName}"
)

// Branch pipe stays on Bedrock
val branch = host.branchPipe
assertIs<BedrockMultimodalPipe>(branch, "branch must remain on Bedrock")
```

## Mantle streaming API differences

```kotlin
// Bedrock: builder DSL
pipe.enableStreaming().streamingCallbacks {
    add(callback)
}

// Mantle: direct setter, NO callback builder DSL
pipe.setStreamingEnabled(true)
pipe.setStreamingCallback(callback)
```

The Mantle pipe's `streamingCallbacks` DSL does not exist. `setStreamingCallback`
takes a single `suspend (String) -> Unit` lambda; multiple callbacks must
be chained manually with a multiplexer lambda.

## Step-by-step recipe

1. **RED**: write a `Build<AgentName>MantleTest` asserting host + reasoning
   pipe types. Run it — it fails because host is still
   `BedrockMultimodalPipe`.
2. **GREEN host pipe**: replace `BedrockMultimodalPipe().apply { ... }`
   with `GenericOpenAIPipe().apply { setBedrockMantle(region, modelId); ... }`.
   Drop `useConverseApi()` and `setServiceTier(BedrockPriorityTier.Flex)`.
   If `setModel(BedrockConfig.qwenCoder30B)` was used, swap to
   `setBedrockMantle(BedrockConfig.mantleRegion(), BedrockConfig.mantleModelId("gemma4ModelId"))`.
3. **GREEN reasoning pipe**: swap `BedrockConfig.structuredCotBuilder(...)`
   → `BedrockConfig.mantleStructuredCotBuilder(...)` (preserve depth/duration
   kwargs). Same swap for `explicitCotBuilder`.
4. **GREEN branch pipe**: if the agent has a Bedrock-only branch (PalmyraX5
   retry or `AgentRetry` error logger), construct it inline as
   `BedrockMultimodalPipe().apply { ... }`. Do NOT use
   `buildBranchPipeFromTemplate` for Mantle hosts.
5. **GREEN streaming**: swap `enableStreaming()` → `setStreamingEnabled(true)`
   and `streamingCallbacks { add(cb) }` → `setStreamingCallback(cb)`.
6. **GREEN imports**: remove `bedrockPipe.BedrockMultimodalPipe` and
   `bedrockPipe.BedrockPriorityTier` if no longer used; add
   `genericOpenAIPipe.GenericOpenAIPipe`.
7. **Visibility**: if `BedrockConfig.mantleRegion()` /
   `mantleModelId()` are called from agent files, promote them from
   `private` to `public` in `globals/BedrockConfig.kt`.
8. **Re-run the test**: it passes.

## Live integration test scaffolding

For end-to-end verification, create
`server/src/test/kotlin/org/ttt/autogenesis/server/BedrockMantle<Scope>LiveTest.kt`:

```kotlin
@EnabledIfEnvironmentVariable(named = "BEDROCK_MANTLE_LIVE_TEST", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class BedrockMantleLowAgentsLiveTest {
    private fun installCredentials() { /* parse ~/.aws/credentials, push to BedrockMantleEnv */ }
    private fun clearCredentials() { /* BedrockMantleEnv.clearAccessKeyId / SecretAccessKey */ }

    @Test
    fun liveMantle_build<AgentName>() = runBlocking {
        installCredentials()
        try {
            val pipeline = build<AgentName>()
            val host = pipeline.getPipes().first() as GenericOpenAIPipe
            // Assert pipe type, reasoning pipe type, etc.
        } finally { clearCredentials() }
    }
}
```

Run with:

```bash
BEDROCK_MANTLE_LIVE_TEST=true \
BEDROCK_AWS_PROFILE=BedrockKey \
./gradlew :server:test --tests "*BedrockMantleLowAgentsLiveTest" --rerun-tasks
```

`--rerun-tasks` is required to bypass the test cache.

## Pre-existing failure baselining

If a regression check surfaces failures that look migration-related,
baseline against the source branch tip:

```bash
git stash --include-untracked
./gradlew :server:test --tests "<failing-class>"   # run on source tip
git stash pop
```

If the failures persist with identical exception (same `MockKException`,
same trace, same `at World(#N).copy(...)` site), they are pre-existing
and not migration regressions. **Document and move on.**

Known pre-existing (verified 2026-07-29):
`SummitOrchestratorTest` has 5–9 `MockKException: World.copy`
failures that predate any provider migration. Do NOT attribute these
to a Mantle migration commit.

## See Also

- `references/mantle.md` — Mantle endpoint, auth, model IDs, live-test gating
- `BedrockConfig.kt` — `mantleRegion()`, `mantleModelId()`,
  `mantleStructuredCotBuilder`, `mantleExplicitCotBuilder`,
  `mantleAuthorBuilderE2B/31B`, `MANTLE_TRUNCATION_SETTINGS`
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`
  — pipe API surface (setters, validators, branches, transformations)
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleConfiguration.kt`
  — Mantle config record