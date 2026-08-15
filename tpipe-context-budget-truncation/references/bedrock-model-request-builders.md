# TPipe Bedrock — Per-Model Request Builders & Truncation

Captured 2026-07-26 from `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt` (5,164 lines).

This is the **provider-side** extension of the truncation system. Where `tpipe-context-budget-fields.md` covers the JAR-level budgeting primitives, this file covers how `BedrockPipe` applies those primitives per-model at request-build time.

---

## Two-Layer Architecture

| Layer | Location | What it does |
|-------|----------|--------------|
| **Layer 1 — Truncation** | `truncateModuleContext()` `BedrockPipe.kt:1211`<br>`truncateModuleContextSuspend()` `BedrockPipe.kt:1446` | Configures `contextWindowSize`, `tokenCountingBias`, and sub-word counting flags per model. Runs before prompt assembly. |
| **Layer 2 — Request Building** | `executeInvokeApi()` `BedrockPipe.kt:1031`<br>`generateWithConverseApi()` `BedrockPipe.kt:3965` | Routes to model-specific builders that map `maxTokens` → model-specific field names and call AWS. |

Both `truncateModuleContext()` and `truncateModuleContextSuspend()` have **duplicated `when` blocks** — nearly identical per-model logic at lines 1223 and 1460. Adding a new model to one without the other is a maintenance hazard.

---

## Layer 1 — Truncation Settings Per Model

The `when` block on `modelId` string patterns sets these fields:

```
contextWindowSize          — model context window in tokens
multiplyWindowSizeBy       — multiplier (0 = fixed window)
contextWindowTruncation    — always TruncateTop
countSubWordsInFirstWord   — sub-word counting at word boundary
favorWholeWords            — prefer not splitting words
countOnlyFirstWordFound   — default false
splitForNonWordChar        — default false
alwaysSplitIfWholeWordExists — default false
countSubWordsIfSplit       — count sub-words when split occurs
nonWordSplitCount          — non-word chars that trigger split
tokenCountingBias          — per-model correction offset (Qwen only)
```

### Per-model context window sizes

The per-model `when` block in `truncateModuleContext()` was historically responsible for stamping `contextWindowSize` and `multiplyWindowSizeBy` on top of whatever the user set. As of 2026-07-26, those overrides were removed from all Bedrock models — the user's `setContextWindowSize()` value and the budget's `contextWindowSize` now flow through without being silently overwritten. The `when` block retained responsibility for counting-flag tuning only:

```
Model                  Counting flags set by when block?   tokenCountingBias
─────────────────────────────────────────────────────────────────────────────
Claude (any)           yes (defaults)                      none
Nova Micro            yes (defaults)                      none
Nova Lite/Pro         yes (defaults)                      none
Nova Premier          yes (defaults)                      none
Llama                 yes (defaults)                      none
DeepSeek R1           yes (countSubWordsIfSplit=false)    none
DeepSeek V3.1         yes (countSubWordsIfSplit=false)    none
DeepSeek default      yes (truncation only)               none
Palmyra X4            yes (defaults)                      none
Palmyra X5            yes (defaults)                      none
GPT-OSS               yes (defaults)                      none
Qwen                  yes (favorWholeWords=false,         -0.036641221374045754
                            countSubWordsIfSplit=false)
GLM                   yes (defaults)                      none
```

**Do not add `contextWindowSize = N` or `multiplyWindowSizeBy = 0` back to the `when` block.** The user's budget is the authoritative source for window size. The provider layer should only stamp per-model TUNING (counting flags, truncation strategy), not size.

### Qwen special case

```kotlin
// BedrockPipe.kt:52
private const val QWEN_TUNED_TOKEN_COUNTING_BIAS = -0.036641221374045754
```

Qwen uses `favorWholeWords = false`, `countSubWordsIfSplit = false`, and a tuned `tokenCountingBias` to correct systematic token overcounting. Calibrated via TPipe-Tuner against a 631-token stress string. **Do not change the bias constant without re-running the tuner.**

### The TruncationSettings override via TokenBudgetSettings

As of 2026-07-26, `TokenBudgetSettings` carries a nullable `truncationSettings: TruncationSettings?` field. When set, the supplied `TruncationSettings` overrides the per-model defaults that the `when` block would apply. This is the supported path for users who want full control of tokenizer tuning without losing the model's default behavior elsewhere.

The override is applied at THREE points — missing any one of them is a bug:

1. **`setTokenBudgetInternal()` in the base `Pipe` class** (`Pipe.kt:~3220`): applied BEFORE `getTruncationSettings()` is called, so downstream `Dictionary.countTokens()` math during budget validation uses the user's actual tuning values, not stale model defaults.

2. **`BedrockPipe.truncateModuleContext()`** (`BedrockPipe.kt:~1216`): applied at the top of the sync function, BEFORE the model-default `when` block. Short-circuits with `return this` if the override is present.

3. **`BedrockPipe.truncateModuleContextSuspend()`** (`BedrockPipe.kt:~1462`): applied at the top of the suspend function, BEFORE the model-default `when` block. This is the runtime call site — `generateText()` calls `truncateModuleContextSuspend()` at line 6293 of Pipe.kt, which would otherwise re-apply the model defaults and stomp the override.

The override copies all truncation tuning fields onto the pipe instance:

```kotlin
tokenBudgetSettings?.truncationSettings?.let { settings ->
    multiplyWindowSizeBy = settings.multiplyWindowSizeBy
    countSubWordsInFirstWord = settings.countSubWordsInFirstWord
    favorWholeWords = settings.favorWholeWords
    countOnlyFirstWordFound = settings.countOnlyFirstWordFound
    splitForNonWordChar = settings.splitForNonWordChar
    alwaysSplitIfWholeWordExists = settings.alwaysSplitIfWholeWordExists
    countSubWordsIfSplit = settings.countSubWordsIfSplit
    nonWordSplitCount = settings.nonWordSplitCount
    tokenCountingBias = settings.tokenCountingBias
    loreBookFillMode = settings.fillMode
    loreBookFillAndSplitMode = settings.fillAndSplitMode
    return this
}
```

**The override does NOT touch `contextWindowSize`.** The window size is user/budget-controlled via `setContextWindowSize()` and `tokenBudgetSettings.contextWindowSize`. The override only owns tuning, not size. This matches the user's mental model: tuning (how the tokenizer counts) and size (how big the window is) are independent concerns.

**The override does NOT touch `contextWindowTruncation`.** That stays on `TokenBudgetSettings` directly (`budget.truncationMethod`) and is the only surface for controlling truncation strategy — there's no plumbing from `TruncationSettings.truncationMethod` to the pipe instance because `TruncationSettings` doesn't carry that field.

Usage example:

```kotlin
val budget = TokenBudgetSettings(
    contextWindowSize = 128000,
    maxTokens = 4096,
    userPromptSize = null,
    truncationSettings = TruncationSettings(
        favorWholeWords = false,
        countSubWordsIfSplit = true,
        tokenCountingBias = 0.05,
        nonWordSplitCount = 3
    )
)
bedrockPipe.setTokenBudget(budget)
```

The supplied `TruncationSettings` values will survive every `truncateModuleContext()` and `truncateModuleContextSuspend()` call — the model-default `when` block is skipped entirely when the override is set.

### DeepSeek special cases

```kotlin
// BedrockPipe.kt:1317-1354
modelId.contains("deepseek") → when {
    isDeepSeekR1(modelId)   → contextWindowSize=126000, countSubWordsIfSplit=false
    isDeepSeekV31(modelId)  → contextWindowSize=128000, countSubWordsIfSplit=false
    else                     → contextWindowSize=126000
}
```

DeepSeek always uses `countSubWordsIfSplit=false` regardless of variant. R1 and V3.1 differ only in `contextWindowSize`.

### Nova advanced models — maxTokens suppression

```kotlin
// BedrockPipe.kt:3176
private fun shouldSkipNovaMaxTokens(modelId: String): Boolean {
    return isNovaAdvancedModel(modelId) && useModelReasoning &&
           getNormalizedNovaReasoningEffort() == "high"
}
```

When `useModelReasoning=true` on Nova 2 or Nova Sonic with `reasoningEffort="high"`, `maxTokens` is **not sent** in the request — high reasoning already consumes the full budget.

---

## Layer 2 — Request Builders

### Invoke API path routing

```kotlin
// BedrockPipe.kt:1065
when {
    contains("openai.gpt-oss")    → buildGptOssRequest()
    contains("amazon.nova")       → buildNovaRequest()
    contains("minimax")           → buildMiniMaxRequest()
    contains("moonshot.kimi")     → buildKimiRequest()
    contains("anthropic.claude")  → buildClaudeRequest()
    contains("amazon.titan")      → buildTitanRequest()
    contains("ai21.j2")           → buildJurassicRequest()
    contains("cohere.command")    → buildCohereRequest()
    contains("meta.llama")        → buildLlamaRequest()
    contains("mistral")           → buildMistralRequest()
    contains("qwen")             → buildQwenRequest()
    isGlmModel(modelId)           → buildGlmRequest()
    contains("deepseek")         → buildDeepSeekRequest()
}
```

### Converse API path routing

```kotlin
// BedrockPipe.kt:3968
when {
    contains("qwen")                   → buildQwenConverseRequest()
    isGlmModel(modelId)                → buildGlmConverseRequest()
    contains("anthropic.claude")       → buildClaudeConverseRequest()
    contains("amazon.nova")            → buildNovaConverseRequest()
    contains("minimax")               → buildMiniMaxConverseRequest()
    isKimiModel(modelId)               → buildKimiConverseRequest()
    contains("amazon.titan")           → buildTitanConverseRequest()
    contains("ai21.j2")               → buildAI21ConverseRequest()
    contains("cohere.command")         → buildCohereConverseRequest()
    contains("meta.llama")             → buildLlamaConverseRequest()
    contains("mistral")               → buildMistralConverseRequest()
    contains("deepseek")              → buildDeepSeekConverseRequestObject()
    contains("openai.gpt-oss")        → buildGptOssConverseRequest()
    else                               → buildGenericConverseRequest()
}
```

### maxTokens field name mapping (Invoke API)

```
Model         Field name        Request location
─────────────────────────────────────────────────────────────────────
Claude        maxTokens         Messages API / inferenceConfig
Titan         maxTokenCount     textGenerationConfig
Jurassic      maxTokens         top-level
Cohere        max_tokens        top-level
Llama         max_gen_len       top-level
Mistral       max_tokens        top-level
Nova          maxTokens         inferenceConfig
MiniMax       maxTokens         inferenceConfig
GPT-OSS       maxTokens         inferenceConfig
GLM           maxTokens         InferenceConfiguration (Converse)
```

### Model-specific detection helpers

```kotlin
// BedrockPipe.kt:3493-3545
protected fun isKimiModel(modelId: String) =
    modelId.contains("kimi", ignoreCase = true)

protected fun isDeepSeekR1(modelId: String) =
    modelId.contains("deepseek.r1", ignoreCase = true) ||
    modelId.contains("us.deepseek.r1", ignoreCase = true)

protected fun isDeepSeekV31(modelId: String) =
    modelId.contains("deepseek.v3", ignoreCase = true) ||
    modelId.contains("us.deepseek.v3", ignoreCase = true)

protected fun isGlmModel(modelId: String) =
    modelId.contains("glm-4.7", ignoreCase = true)

private fun isNovaAdvancedModel(modelId: String) =
    modelId.lowercase().contains("amazon.nova-2") ||
    modelId.lowercase().contains("amazon.nova-sonic")
```

### GLM Converse example — the most complete builder

```kotlin
// BedrockPipe.kt:2244
inferenceConfig = InferenceConfiguration {
    if(this@BedrockPipe.maxTokens > 0) maxTokens = this@BedrockPipe.maxTokens
    if(this@BedrockPipe.temperature > 0) temperature = this@BedrockPipe.temperature.toFloat()
    if(this@BedrockPipe.topP > 0) topP = this@BedrockPipe.topP.toFloat()
    if(this@BedrockPipe.stopSequences.isNotEmpty()) stopSequences = this@BedrockPipe.stopSequences
}
additionalModelRequestFields = Document.Map(getModelSpecificOpenAIParameters(modelId))
```

`additionalModelRequestFields` carries OpenAI-style params (`frequency_penalty`, `presence_penalty`, `seed`, `logit_bias`) for GPT-OSS, Qwen, DeepSeek, and GLM.

### OpenAI-style extra params for GPT-OSS / Qwen / DeepSeek / GLM

```kotlin
// BedrockPipe.kt:2307
getModelSpecificOpenAIParameterValues(modelId)
```

Only set for models matching:
```kotlin
modelId.contains("openai.gpt-oss") ||
modelId.contains("qwen") ||
modelId.contains("deepseek") ||
isGlmModel(modelId)
```

---

## Maintenance Hazards

### Duplicated truncation `when` blocks

`truncateModuleContext()` (line 1223) and `truncateModuleContextSuspend()` (line 1460) are nearly identical. Any new model added to one **must** be added to the other. The suspend version additionally passes `tokenCountingBias` through to `combineAndTruncateAsStringWithSettingsSuspend()`. Refactor target: extract to a shared `configureTruncationForModel(modelId)` method.

### `useConverseApi` is a global flag

`BedrockPipe.useConverseApi` is a single `Boolean` that switches the **entire pipe** between Converse and Invoke APIs. There is no per-model override — once set, all subsequent requests use that API path. The Converse path routes via `generateWithConverseApi()` which has its own second-level `when` block. If a model is missing from the Converse routing, it falls through to `buildGenericConverseRequest()`.

### No model-specific `maxTokens` field name translation at the budget layer

The JAR-level `TokenBudgetSettings` stores a generic `maxTokens`. The field-name translation (`maxTokens` → `maxTokenCount` for Titan, `max_gen_len` for Llama) happens **only** in the request builders, not in the budget layer. This means the budget layer always uses the concept "maxTokens" while the wire format translates. If you add a new model with a non-standard max-tokens field name, you must update (a) the truncation `when` block, (b) the Invoke API `when` block, (c) the Converse API `when` block, and (d) the field-name mapping in the appropriate builder.

---

## Adding a New Bedrock Model

1. Add model detection to `isKimiModel` / `isGlmModel` style helper, or add `contains()` clause to both routing `when` blocks.
2. Add truncation settings to **both** `truncateModuleContext()` and `truncateModuleContextSuspend()` — do not skip the suspend version.
3. Add `buildXxxRequest()` for Invoke API and `buildXxxConverseRequest()` for Converse API if the model needs special wire format.
4. If the model uses OpenAI-style extra params, add it to the `getModelSpecificOpenAIParameterValues()` `when` block.
5. If the model has a non-standard `maxTokens` field name, add the translation in the builder.
6. If the model has a unique context window size, set `contextWindowSize` in the truncation block.
7. If the model has systematic token-counting bias (like Qwen), calibrate `tokenCountingBias` via TPipe-Tuner.
