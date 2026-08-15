# Reasoning-Builder Extension Cycle — 2026-07-09

Worked example of adding `reasonWithOpenRouter` and `reasonWithGenericOpenAI` to TPipe-Defaults, alongside the existing Bedrock and Ollama factories. Use this as a session-specific reference when the next "add another provider" request lands.

## Trigger

User asked: "Yes we need both implemented per the standard spec that has been established." — referencing an explicit preference for spec-driven, pattern-matching additions rather than re-deriving the design each time.

## Live File Inventory (TPipe project at /home/cage/Desktop/Workspaces/TPipe/TPipe/)

Four files touched, all in TPipe-Defaults module:

1. `TPipe-Defaults/build.gradle.kts:30-37` — added `implementation(project(":TPipe-GenericOpenAI"))` next to the four existing provider Gradle lines.

2. `TPipe-Defaults/src/main/kotlin/Defaults/ProviderConfiguration.kt` — added `GenericOpenAIConfiguration` data class as sealed member of `ProviderConfiguration`. Mirrors `OpenRouterConfiguration` (model + apiKey + pipeCount + baseUrl + provider-specific knobs + manifoldMemory + validate).

3. `TPipe-Defaults/src/main/kotlin/Defaults/providers/GenericOpenAIDefaults.kt` (NEW) — internal object, `createGenericOpenAIPipe(config): GenericOpenAIPipe`. Mirrors `OpenRouterDefaults.kt:66-103`. Translates config string `apiMode` ("OpenAI" | "OpenAIResponses" | "Anthropic") to `genericOpenAIPipe.api.ApiMode` sealed class via factory-side mapping.

4. `TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt` — appended two functions after `reasonWithOllama`:

```
reasonWithOpenRouter(openRouterConfig, reasoningSettings, pipeSettings?): Pipe
reasonWithGenericOpenAI(genericConfig, reasoningSettings, pipeSettings?): Pipe
```

Both delegate to the new `Defaults/providers/` factories, then to existing `assignDefaults`.

## New Test File

`TPipe-Defaults/src/test/kotlin/Defaults/reasoning/ReasoningBuilderProviderFactoriesTest.kt` (NEW) — four `@Test` methods:

- `reasonWithBedrockReturnsPipeWithConfiguredReasoningMetadata` — pins existing reference behavior.
- `reasonWithOllamaReturnsPipeWithConfiguredReasoningMetadata` — pins existing reference behavior.
- `reasonWithOpenRouterReturnsPipeWithConfiguredReasoningMetadata` — pins new factory.
- `reasonWithGenericOpenAIReturnsPipeWithConfiguredReasoningMetadata` — pins new factory.

All assert on `pipe.pipeMetadata` (NOT `pipe.pipeName` or `pipe.model` — see Pitfalls 1 and 2 in SKILL.md).

## TDD Red→Green Evidence

Red (initial test, no implementation):

```
> Task :TPipe-Defaults:compileTestKotlin FAILED
e: ReasoningBuilderProviderFactoriesTest.kt:59:33 Unresolved reference 'reasonWithOpenRouter'.
e: ReasoningBuilderProviderFactoriesTest.kt:90:33 Unresolved reference 'reasonWithGenericOpenAI'.
e: ReasoningBuilderProviderFactoriesTest.kt:91:22 Unresolved reference 'GenericOpenAIConfiguration'.
```

Green (after four-file implementation):

```
> Task :TPipe-Defaults:test
BUILD SUCCESSFUL in 2s
```

Per-class breakdown:
- `DistributionGridDslDefaultsTest` — 5/5
- `HostedRegistryDefaultsTest` — 4/4
- `ManifoldDefaultsTest` — 7/7
- `ManifoldDslDefaultsTest` — 6/6
- `PumpStationDefaultsTest` — 6/6
- `ReasoningBuilderProviderFactoriesTest` (NEW) — 4/4
- `ReasoningPromptsSemanticDecompressionTest` — 3/3

Total: 35 tests across 7 classes, 0 failures, 0 errors, 0 skipped.

## Mistakes Caught and Reverted

### Mistake 1: Trying to assert on `pipe.pipeName.isNotEmpty()`

Initial test draft included `assertTrue(pipe.pipeName.isNotEmpty())` for all four cases. Three of four failed with `AssertionError: Expected value to be true`. The fourth (Ollama) happened to be set already because `OllamaConfiguration` had a `pipeCount` driven manual path. Root cause: `Pipe.kt:4956` only sets `reasoningPipe.pipeName` when the parent goes through `init()`, and the standalone factory test never reaches that code path. Fix: pin contract on `pipeMetadata` round-trip only.

### Mistake 2: Initial draft of `ProviderConfiguration.kt` included invented mirror types

First pass added `enum class ApiModeName { OpenAI, OpenAIResponses, Anthropic }` and `typealias openRouterPipeOpenAIEnvTypeAlias = String` to "soften" the dependency on `genericOpenAIPipe.api.ApiMode`. Apex skill explicitly forbids this — `Defaults` is the public Defaults surface, the implementation lives in `TPipe-GenericOpenAI`. Reverted both: `apiMode: String = "OpenAI"` in the dataclass + factory-side `when(config.apiMode)` translation.

### Mistake 3: Wrong package import for `ApiMode`

`genericOpenAIPipe.ApiMode` is not the path — it's `genericOpenAIPipe.api.ApiMode` (sealed class with `data object` subclasses). Search via `class ApiMode|^sealed class ApiMode` returned only the `api/ApiMode.kt` location. Caught before compile.

### Mistake 4: GenericOpenAIPipe does not expose `setSessionId` or `setVerbosity`

First factory draft called `setSessionId(...)` and `setVerbosity(...)` on `GenericOpenAIPipe`. These setters don't exist — they appeared in earlier Bedrock/Ollama/OpenRouter patterns. Confirmed via `grep -E "fun set(.*)\(.*\): GenericOpenAIPipe"` then removed. Only the verified-public setters were kept: `setModel`, `setApiKey`, `setBaseUrl`, `setApiMode`, `setParallelToolCalls`, `setStructuredOutputs`.

## Pattern for Future Additions

To add `reasonWith<X>` for a new provider:

1. Confirm the provider module exists at `:TPipe-<X>` with root `settings.gradle.kts` include and a public pipe class (open `X>Defaults.kt` precedents).
2. Write the failing test first — `./gradlew :TPipe-Defaults:test --tests "<your new test class>"` should show `Unresolved reference` errors against `reasonWith<X>` and the new configuration dataclass.
3. Apply the four-file spec from SKILL.md "Adding a New Provider to the Reasoning Builder — Established Spec".
4. Run the targeted test class — expect all green.
5. Run the full TPipe-Defaults suite — expect 35+ tests, 0 failures.

If the new provider's pipe class has setters that differ in name or signature from the OpenRouter/GenericOpenAI examples, search them out via `grep -E "fun set[A-Z][a-zA-Z]+\(.*\): <X>Pipe"` against the provider's source before writing the factory. Each setter call must compile against the real signature, not a guess.

## What Did NOT Need to Change

- `assignDefaults()` in `ReasoningBuilder.kt:163` — already provider-agnostic. The two new factories just feed it.
- `ReasoningSettings`, `ReasoningMethod`, `ReasoningInjector`, `ReasoningDepth`, `ReasoningDuration` — none touched.
- Any test that already used `reasonWithBedrock` or `reasonWithOllama` — none touched.
- Runtime code paths in `Pipe.kt` (executeReasoningPipe, injectTPipeReasoning) — none touched. Confirms the load-bearing extension point is `assignDefaults`, not the runtime.
