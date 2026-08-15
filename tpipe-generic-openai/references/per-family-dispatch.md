# Per-Family Strategy Dispatch (BedrockPipe Architecture)

The `GenericOpenAIPipe` is provider-agnostic because OpenAI-compatible APIs share a wire format. The `BedrockPipe` is provider-agnostic through a **different mechanism** — a per-family strategy dispatch keyed on `requestedModelId`. This file documents the architecture so a future session knows what it is, why it exists, and how to extend it.

## Why dispatch exists

Bedrock routes through 14+ model families that all invented their own JSON shape: Anthropic Claude, Amazon Nova, Llama, Mistral, AI21 Jamba, Cohere Command, Titan, Qwen3, DeepSeek, GLM 4.7, GPT-OSS, Kimi, Writer, and a generic fallback. **None of them share a wire format.** So unlike the GenericOpenAIPipe (which leans on OpenAI's universal spec), BedrockPipe has to translate the same TPipe API into 14 different JSON dialects.

## The anchor: `requestedModelId`

```kotlin
// BedrockPipe.kt:130-135
/**
 * Canonical model identifier that the user asked for before inference profiles/ARN binding.
 * Used to keep the per-family builders and extractors aligned with the requested model.
 */
@kotlinx.serialization.Transient
private var requestedModelId: String = ""

private fun getRequestedModelId(): String {
    if(requestedModelId.isNotEmpty()) return requestedModelId
    val fallback = model.ifEmpty { "anthropic.claude-3-sonnet-20240229-v1:0" }
    requestedModelId = fallback
    return fallback
}
```

**Critical insight:** the actual `modelId` sent over the wire can be rewritten by Bedrock inference profile resolution and ARN rebinding. All family-specific dispatch needs to know what family the USER originally asked for, so `requestedModelId` is captured at `setModel()` time and frozen. It survives both profile rewrites and ARN rebinds.

## The four axes of dispatch

| Concern | Per-family customization | BedrockPipe.kt location |
|---|---|---|
| Request body shape (Invoke API) | `buildXxxRequest()` per family | ~line 1051-1083 |
| Converse API request | `buildXxxConverseRequest()` per family | BedrockMultimodalPipe.kt ~line 222-234 |
| Reasoning parameters | `getModelSpecificOpenAIParameterValues()` inner `when` | ~line 2307-2395 |
| Reasoning response field | `extractReasoningContent()` inner `when` | ~line 4838-5008 |
| Stop-reason vocabulary | `isMaxTokenStopReason()` | ~line 4710-4720 |
| Token usage field | `extractTokenUsageFromInvokeResponse()` inner `when` | ~line 4745-4812 |
| Context window size | `truncateModuleContext()` | ~line 1211-1420 |
| Validation rules | `validateOpenAIParametersForModel()` | ~line 2401-2465 |

## The request builder pattern

```kotlin
// BedrockPipe.kt:1065-1084 (Invoke API path)
val requestJson = when
{
    requestedModelId.contains("openai.gpt-oss") -> buildGptOssRequest(fullPrompt)
    requestedModelId.contains("amazon.nova") -> buildNovaRequest(fullPrompt)
    requestedModelId.contains("minimax") -> buildMiniMaxRequest(fullPrompt)
    requestedModelId.contains("moonshot.kimi") -> buildKimiRequest(fullPrompt)
    requestedModelId.contains("anthropic.claude") -> buildClaudeRequest(fullPrompt)
    requestedModelId.contains("amazon.titan") -> buildTitanRequest(fullPrompt)
    requestedModelId.contains("ai21.j2") -> buildJurassicRequest(fullPrompt)
    requestedModelId.contains("cohere.command") -> buildCohereRequest(fullPrompt)
    requestedModelId.contains("meta.llama") -> buildLlamaRequest(fullPrompt)
    requestedModelId.contains("mistral") -> buildMistralRequest(fullPrompt)
    requestedModelId.contains("qwen") -> buildQwenRequest(fullPrompt)
    isGlmModel(requestedModelId) -> buildGlmRequest(fullPrompt)
    requestedModelId.contains("deepseek") -> buildDeepSeekRequest(fullPrompt)
    else -> buildGenericRequest(fullPrompt)
}
```

A parallel dispatch in `BedrockMultimodalPipe.kt:222-234` builds `ConverseRequest` objects (the unified Bedrock SDK abstraction) instead of raw JSON. Same family detection, different output type.

## The reasoning/thinking vocabulary (the "non-standard behaviors")

The cleanest example of why this dispatch exists. Each model family has a different way to enable and expose reasoning:

**How to TURN ON reasoning for each family** (`getModelSpecificOpenAIParameterValues`):

```kotlin
when {
    modelId.contains("openai.gpt-oss") -> {
        parameterValues["reasoning_effort"] = modelReasoningSettingsV3.ifEmpty { "low" }
        parameterValues["include_reasoning"] = true
    }
    modelId.contains("qwen") -> {
        if(isQwen3Model(modelId)) {
            parameterValues["reasoning_config"] = getNormalizedReasoningEffort()
        } else {
            parameterValues["enable_thinking"] = true
            parameterValues["thinking_budget"] = computeOpenAIReasoningBudget()
        }
    }
    modelId.contains("deepseek") || isGlmModel(modelId) -> {
        parameterValues["reasoning_config"] = getNormalizedReasoningEffort()
    }
}
```

Each family has a **different parameter name, different value space, and different default**. TPipe normalizes these behind a single `useModelReasoning` + `modelReasoningSettingsV3` API.

**How to EXTRACT reasoning from responses** (`extractReasoningContent`):

```kotlin
when {
    modelId.contains("qwen") -> {
        // Qwen3 uses reasoning_content; Qwen3 VL uses thinking; legacy uses reasoning
        // Priority: reasoning_content > reasoning > thinking > fallbacks
        json["choices"]?.jsonArray?.firstOrNull()?.jsonObject?.let { choice ->
            choice.get("message")?.jsonObject?.get("reasoning_content")?.jsonPrimitive?.content
                ?: choice.get("message")?.jsonObject?.get("reasoning")?.jsonPrimitive?.content
                ?: choice.get("message")?.jsonObject?.get("thinking")?.jsonPrimitive?.content
        } ?: ""
    }
    modelId.contains("anthropic.claude") -> {
        // Claude embeds thinking in content[] array as separate blocks
        json["content"]?.jsonArray?.mapNotNull { item ->
            if(item.jsonObject["type"]?.jsonPrimitive?.content == "thinking")
                item.jsonObject["thinking"]?.jsonPrimitive?.content else null
        }?.joinToString("\n") ?: ""
    }
    modelId.contains("minimax") -> {
        // MiniMax exposes reasoning_details[] array with text parts
        val reasoningDetails = message?.get("reasoning_details")?.jsonArray
        reasoningDetails?.mapNotNull { it.jsonObject["text"]?.jsonPrimitive?.content }
            .joinToString("\n")
    }
    // ... 6+ more families
}
```

Per the doc comment at line 4827-4832:
> "Qwen models use different field names depending on the model variant: Qwen3 Next 80B A3B uses `reasoning_content`, Qwen3 VL 235B A22B uses `thinking`, Legacy Qwen models may use `reasoning`. Priority order: reasoning_content > reasoning > thinking > fallbacks"

**Stop-reason vocabulary translation** (`isMaxTokenStopReason`):

```kotlin
when(stopReason.lowercase()) {
    "length" -> true           // GPT-OSS, DeepSeek
    "max_tokens" -> true       // Claude
    "max_length" -> true       // some variants
    "token_limit" -> true      // alternatives
    else -> false
}
```

Same conceptual event ("model stopped because it ran out of tokens"), four different names across families.

## The pattern, named

This is a **per-family strategy dispatch** — not a Builder pattern in the GoF sense, but functionally identical. Each model family gets:

1. A request builder (`buildXxxRequest()` for Invoke, `buildXxxConverseRequest()` for Converse)
2. A response field extractor (the inner `when` in `extractReasoningContent()`, `extractTextFromResponse()`, `extractTokenUsageFromInvokeResponse()`)
3. A reasoning activation strategy (the inner `when` in `getModelSpecificOpenAIParameterValues()`)
4. A context window configuration (a `when` arm in `truncateModuleContext()`)
5. A validation rule (a `when` arm in `validateOpenAIParametersForModel()`)

All five axes share the same anchor: `getRequestedModelId()`.

## How to add a new model family

To add a new family, the dispatch table grows by **one row in five places**:

1. Add `requestedModelId.contains("new.family") -> buildNewFamilyRequest(...)` to the `executeInvokeApi()` `when` (and the parallel Converse API `when`)
2. Add the family to the inner `when` in `extractReasoningContent()` if it produces reasoning
3. Add it to `getModelSpecificOpenAIParameterValues()` if it has family-specific parameters
4. Add a `truncateModuleContext()` arm for the context window size
5. Add a `validateOpenAIParametersForModel()` arm for parameter validation

No inheritance hierarchy churn. No SDK lock-in. Five branches added, one new `buildNewFamilyRequest()` function written.

## Family detectors (helper predicates)

The module has a small set of family-detection helpers used throughout:

- `isGlmModel(modelId)` — GLM 4.7 / Flash
- `isQwen3Model(modelId)` — Qwen3 specific
- `isDeepSeekR1(modelId)` — R1 reasoning model
- `isDeepSeekV31(modelId)` — V3.1 with thinking
- `isKimiModel(modelId)` / `isKimi25Model(modelId)` — Moonshot Kimi
- `isNovaAdvancedModel(modelId)` — Nova 2.x or Nova Sonic
- `getNormalizedNovaReasoningEffort()` — normalizes TPipe's `modelReasoningSettingsV3` to Nova's expected vocabulary

When adding a new family, add a corresponding detector if the family has sub-variants with different behavior (like Qwen3 vs older Qwen).

## Why this isn't in GenericOpenAIPipe

GenericOpenAIPipe has no per-family dispatch because OpenAI-compatible providers share a wire format. Its only "dispatch" is the three `ApiMode` data objects (OpenAI / Anthropic / OpenAIResponses), which differ in **wire format and authentication**, not in **field-level quirks**. Bedrock's 14+ families all need **field-level** translation because vendors invented their own JSON dialects.

The two pipes are the yin and yang of TPipe integration:
- `GenericOpenAIPipe` — protocol dispatch (3 wire formats) × uniform field shape
- `BedrockPipe` — uniform wire format (Bedrock SDK) × per-family field shape
