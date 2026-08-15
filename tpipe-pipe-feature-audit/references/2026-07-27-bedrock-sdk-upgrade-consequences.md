# Bedrock SDK Upgrade Audit — Streaming, Structured Output, and Mantle

**Date**: 2026-07-27
**Source repo**: `/home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Bedrock/`
**SDK pin at audit time**: `aws.sdk.kotlin:bedrockruntime:1.5.97`, `aws-core:1.5.97`, `aws.smithy.kotlin:http-client-engine-okhttp:1.5.4`
**Latest stable**: `bedrockruntime:1.8.15` (requires Kotlin 2.4.0). Last Kotlin-2.3.21-compatible: `bedrockruntime:1.6.107`.

This is the worked case study for the "Provider-SDK response events are silently dropped" pitfall in `tpipe-pipe-feature-audit`. It documents the actual findings from a TPipe-Bedrock audit run, against the aws-sdk-kotlin Converse / ConverseStream / InvokeModel response surfaces, ahead of an SDK upgrade.

## Why this audit was run

Operator requested research into which aws-sdk-kotlin versions support the recent Bedrock features (reasoning, citations, document/PDF, video, prompt caching, structured outputs, performance config, service tiers, prompt routers, cross-region inference, Guardrail policy types, ConverseMetrics). Two parallel research tracks ran:

1. SDK-side surface analysis (Maven Central + GitHub CHANGELOG + Kotlin API reference).
2. Bedrock feature/model surface analysis (Bedrock user guide + Anthropic docs + model cards).

The findings fed into a deeper audit of how our proprietary request builders and streaming infrastructure interact with the SDK response surfaces.

## Headline findings

1. **`ContentBlock` sealed class is identical between 1.5.97 and 1.8.15** — all 12 variants present in both versions. The 30+ proprietary `build*ConverseRequest` methods in `BedrockPipe.kt` are forward-compatible with no source changes required.
2. **Streaming event coverage is the load-bearing gap.** `executeConverseStream` at `BedrockPipe.kt:4300` handles 4 of 9+ `ConverseStreamResponse` events. The rest are silently dropped.
3. **Response-side `ContentBlock` dispatch is even narrower.** `BedrockMultimodalPipe.kt:357` drops everything except Text/Image/Document via `else -> trace(unknownContentBlockType)`.
4. **`toStreamRequest()` at `BedrockPipe.kt:2628` silently drops all guardrail policy fields** — the streaming path is effectively guardrail-trace-only for any model that uses topic/word/sensitive-info/contextual-grounding/automated-reasoning policies.
5. **Bedrock Mantle is not in the SDK.** Route Mantle calls through `GenericOpenAIPipe` with `baseUrl = "https://bedrock-mantle.{region}.amazonaws.com/openai/v1"`. Don't edit `BedrockPipe.kt`.
6. **`setJsonOutput()` vs native `outputConfig.jsonSchema` is incompatible when both are active.** Three concrete failure modes (double-prompting, PCP-merged-mode tool-call break, parser contract change). Needs a feature flag.

## Streaming event coverage gap (file:line)

`BedrockPipe.kt:4300` `executeConverseStream`:

```kotlin
val finalText = client.converseStream(request.toStreamRequest()) { response ->
    response.stream?.collect { event ->

        // ✅ HANDLED: ContentBlockDelta (Text + ReasoningContent only)
        event.asContentBlockDeltaOrNull()?.let { deltaEvent ->
            deltaEvent.delta?.asTextOrNull()?.let { deltaText ->
                textBuilder.append(deltaText)
                emitStreamingChunk(deltaText)
            }
            deltaEvent.delta?.asReasoningContentOrNull()?.asTextOrNull()?.let { reasoningDelta ->
                reasoningBuilder.append(reasoningDelta)
                if (streamModelReasoning) emitStreamingChunk(reasoningDelta)
            }
        }

        // ✅ HANDLED: MessageStop
        event.asMessageStopOrNull()?.let { stopEvent ->
            stopEvent.stopReason?.value?.let {
                stopReason = it
                overflowDetected = isMaxTokenStopReason(it)
            }
        }

        // ✅ HANDLED: Metadata (usage only — drops metrics.latencyMs)
        event.asMetadataOrNull()?.usage?.let { usage ->
            usageMetadata["inputTokens"] = usage.inputTokens
            usageMetadata["outputTokens"] = usage.outputTokens
            usageMetadata["totalTokens"] = usage.totalTokens
            usage.cacheReadInputTokens?.let { usageMetadata["cacheReadInputTokens"] = it }
            usage.cacheWriteInputTokens?.let { usageMetadata["cacheWriteInputTokens"] = it }
        }

        // ❌ NOT HANDLED: ContentBlockStart — loses toolUseId
        // ❌ NOT HANDLED: ContentBlockStop — no per-block boundary
        // ❌ NOT HANDLED: Trace — guardrail trace events dropped
        // ❌ NOT HANDLED: MessageStart — role not verified
        // ❌ NOT HANDLED: Citation delta — citation source attribution dropped
        // ❌ NOT HANDLED: ToolUse delta — tool-call JSON chunks dropped
    }
    textBuilder.toString()
}
```

The six unhandled event types map to seven concrete lost-data cases:

| Unhandled event | Lost data | Consequence |
|---|---|---|
| `ContentBlockStart.toolUse` | `toolUseId` + `toolUse.name` | Tool calls in streaming go to /dev/null — downstream code can't match delta fragments to a call ID. **Bug.** |
| `ContentBlockDelta` (ToolUse variant) | Tool-call input JSON chunks | Tool calls in streaming never reach the wire surface |
| `ContentBlockDelta` (Citations variant) | Citation source attribution | `MultimodalContent.citations` always null |
| `ContentBlockDelta` (Image variant) | Image bytes in delta | We only catch images in the non-streaming path |
| `ContentBlockStop` | Per-block completion signal | Text + reasoning concatenated with no separation boundary. If a model emits interleaved text + tool + reasoning, the boundaries are lost. |
| `MessageStart.role` | Role verification | We assume assistant by convention — first-block check missing |
| `Metadata.metrics.latencyMs` (1.6.x) | Per-call latency | We have `usage` for cost, no `latencyMs` for SLA / observability |
| `Trace` events | Guardrail trace | When guardrail is enabled and `trace = Enabled`, every trace event is dropped |

## Response-side `ContentBlock` dispatch drop-on-floor

`BedrockMultimodalPipe.kt:261-365` `responseContent?.forEach { contentBlock -> when (contentBlock) -> ... }`:

```kotlin
responseContent?.forEach { contentBlock ->
    when(contentBlock)
    {
        is ContentBlock.Text -> responseText.add(contentBlock.value)
        is ContentBlock.Image -> { /* convert to BinaryContent.Bytes / CloudReference */ }
        is ContentBlock.Document -> { /* convert with full format-to-mime map */ }
        else -> {
            // Log unknown content block types for debugging
            trace(TraceEventType.API_CALL_SUCCESS, TracePhase.EXECUTION,
                  metadata = mapOf<String, Any>(
                      "unknownContentBlockType" to (contentBlock::class.simpleName ?: "Unknown")
                  ))
        }
    }
}
```

The `else` branch silently drops: `ContentBlock.ToolUse`, `ContentBlock.ToolResult`, `ContentBlock.ReasoningContent`, `ContentBlock.GuardContent`, `ContentBlock.CachePoint`, `ContentBlock.CitationsContent`, `ContentBlock.SearchResult`, `ContentBlock.Video`, `ContentBlock.Audio`. Reasoning is recovered separately via `extractReasoningFromConverseResponse` at `BedrockPipe.kt:2959`, but every other dropped block stays dropped.

`BedrockPipe.kt:4030-4034` (the non-multimodal Converse path) is even narrower — only `ContentBlock.Text` is harvested:

```kotlin
when(contentBlock) {
    is ContentBlock.Text -> contentBlock.value
    else -> null
}
```

Reasoning is recovered separately. Citations, tool calls, guard assessments, cache points — all dropped.

## `toStreamRequest()` guardrail field-drop (the latent bug)

`BedrockPipe.kt:2628-2648`:

```kotlin
private fun ConverseRequest.toStreamRequest(): ConverseStreamRequest {
    val original = this
    return ConverseStreamRequest {
        modelId = original.modelId
        messages = original.messages
        inferenceConfig = original.inferenceConfig
        system = original.system
        additionalModelRequestFields = original.additionalModelRequestFields
        additionalModelResponseFieldPaths = original.additionalModelResponseFieldPaths
        performanceConfig = original.performanceConfig
        promptVariables = original.promptVariables
        requestMetadata = original.requestMetadata
        toolConfig = original.toolConfig
        original.guardrailConfig?.let { config ->
            guardrailConfig = GuardrailStreamConfiguration {
                guardrailIdentifier = config.guardrailIdentifier
                guardrailVersion = config.guardrailVersion
                trace = config.trace
                // MISSING: every policy field
            }
        }
    }
}
```

The forward mapping of `GuardrailConfiguration` → `GuardrailStreamConfiguration` only forwards `guardrailIdentifier`, `guardrailVersion`, and `trace`. It drops every policy field:

- `disallowedContentFiltering`
- `contentFilters` (content policy)
- `sensitiveInformationPolicyConfig`
- `topicPolicyConfig`
- `wordPolicyConfig`
- `contextualGroundingPolicyConfig`
- `automatedReasoningPolicyConfig`

A model call configured with inline guardrail policies on the non-streaming path (via `applyGuardrailConfig()` at `BedrockPipe.kt:2120-2130`) carries the policies correctly through `ConverseRequest`. The streaming path that consumes the SAME `ConverseRequest` via `toStreamRequest()` produces a `ConverseStreamRequest` with **no policy enforcement**. Bedrock treats the streaming request as trace-only — no topic filter, no word filter, no PII redaction, no contextual grounding check.

This is the documented-contract-without-enforcement pattern: `GuardrailStreamConfiguration` has the same field names as `GuardrailConfiguration`, and the SDK expects the mapping to be 1:1. The mapping extension doesn't enforce it. The bug is silent because the streaming call succeeds — it just doesn't enforce the policies.

### Diagnostic recipe

```bash
grep -nE 'guardrailConfig|GuardrailStreamConfiguration|GuardrailConfiguration' \
    TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
```

Expected findings:
- `BedrockPipe.kt:2120-2130` — `applyGuardrailConfig()` sets ALL fields on the `ConverseRequest.GuardrailConfiguration`.
- `BedrockPipe.kt:2641-2647` — `toStreamRequest()` only forwards 3 fields to `ConverseStreamRequest.GuardrailStreamConfiguration`. **Bug.**

### Fix shape

Extend the mapping block to forward every field present on `GuardrailConfiguration` to its `GuardrailStreamConfiguration` sibling. Same field names, same types. ~10-line patch.

### Test pinning recipe

| Test | What it pins |
|---|---|
| `toStreamRequest forwards all guardrailIdentifier/version/trace fields` | Basic identity mapping |
| `toStreamRequest forwards contentFilters` | Content policy enforcement on streaming |
| `toStreamRequest forwards topicPolicyConfig` | Topic policy |
| `toStreamRequest forwards wordPolicyConfig` | Word policy |
| `toStreamRequest forwards sensitiveInformationPolicyConfig` | PII redaction on streaming |
| `toStreamRequest forwards contextualGroundingPolicyConfig` | Contextual grounding |
| `toStreamRequest forwards automatedReasoningPolicyConfig` | Automated reasoning |
| `toStreamRequest forwards disallowedContentFiltering` | Block-list enforcement |
| Round-trip: ConverseRequest with policies → toStreamRequest → policies preserved | End-to-end |
| Streaming call with content-filter policies actually filters content | Live behavioral test |

The 10-test shape: one per policy field, plus the basic identity, plus the round-trip, plus a live behavioral test. Live test gated on `AllowTest=true` + `MINIMAX_API_KEY` per `tpipe-bedrock-live-test-env-gates`.

## Bedrock Mantle routing rule

**Mantle is NOT a Bedrock SDK feature.** Mantle is the OpenAI-compatible chat-completions / responses endpoint AWS added to Bedrock (`bedrock-mantle.{region}.amazonaws.com/openai/v1/...`). It uses OpenAI's wire protocol, not AWS Converse.

### What Mantle is

- A separate AWS endpoint serving OpenAI's `/v1/chat/completions` and `/v1/responses` API shape.
- Lets you call Bedrock-hosted models using the OpenAI SDK or raw HTTP.
- NOT generated by the `bedrockruntime` Smithy model.
- No `aws.sdk.kotlin:bedrockmantle` artifact exists on Maven Central.

### How to route Mantle calls in TPipe

Use `TPipe-GenericOpenAIPipe` (NOT `BedrockPipe`):

```kotlin
val mantlePipe = GenericOpenAIPipe()
    .setBaseUrl("https://bedrock-mantle.us-east-1.amazonaws.com/openai/v1")
    .setApiKey(bedrockApiKey)  // Bedrock API key, not OpenAI key
    .setModel("bedrock-mantle/anthropic.claude-sonnet-4-5")  // vendor-prefix style
    .applySystemPrompt()
// ... rest of pipe setup, including any tool calls, structured output, streaming
```

The OpenAI-protocol pipe doesn't need any Bedrock-specific request builders — it already speaks the protocol Mantle speaks. The only differences from a stock OpenAI pipe are:

| Setting | OpenAI | Bedrock Mantle |
|---|---|---|
| `baseUrl` | `https://api.openai.com/v1` | `https://bedrock-mantle.{region}.amazonaws.com/openai/v1` |
| Auth | `Bearer ${openaiApiKey}` | `bedrock-api-key` header with a Bedrock API key |
| Model IDs | `gpt-4`, `gpt-4o`, etc. | `bedrock-mantle/<vendor>.<model>` (vendor-prefix style — verify exact format) |
| IAM | None — OpenAI manages it | Bedrock API key has IAM permissions behind it (separate from `StaticCredentialsProvider`) |

### What Mantle does NOT give you

- The Converse API's structured `ContentBlock` variants (Document/PDF, Video, Audio, ToolUse with AWS-specific fields).
- The Bedrock Guardrail policy types (Topic/Word/SensitiveInfo/etc.) — Mantle is OpenAI-protocol only, no Bedrock-specific safety.
- Bedrock-specific inference profiles (`us.*` / `eu.*` / `apac.*` / `global.*`) — Mantle uses its own routing.
- Bedrock `serviceTier` / `performanceConfig` — OpenAI-protocol only.
- Bedrock `requestMetadata` / `promptVariables` / `outputConfig.jsonSchema` — use OpenAI `metadata` / template substitution / `response_format.json_schema` instead.

### Verification recipe

```bash
# Confirm no Mantle artifact exists in the SDK family
curl -sI 'https://repo1.maven.org/maven2/aws/sdk/kotlin/bedrockmantle/' | head -1
# Expected: 404 Not Found

# Confirm GenericOpenAIPipe has the surface to take a custom baseUrl
grep -nE 'setBaseUrl|baseUrl' TPipe-GenericOpenAIPipe/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt
# Expected: setter exists

# Confirm BedrockPipe does NOT import any Mantle references
grep -rn 'mantle\|Mantle' TPipe-Bedrock/src/main/kotlin/
# Expected: zero hits — Mantle is the wrong home for any Bedrock pipe edits
```

### Symptom of misuse

A future session adding Mantle support by editing `BedrockPipe.kt` will hit a wall — there is no Mantle-aware class in the bedrock SDK to import. The right shape is a `MantlePipe` factory in `TPipe-GenericOpenAIPipe` that wraps the existing OpenAI pipe with Mantle-specific config (URL, auth header, model-prefix parsing). When the request arrives, route to the Mantle pipe; do NOT try to extend `BedrockPipe`.

## Structured output conflict — `setJsonOutput()` vs native `outputConfig.jsonSchema`

TPipe's structured-output path is prompt-injection: `setJsonOutput(schema)` flips `supportsNativeJson = false` (`Pipe.kt:2780-2810`), and the schema is appended to the system prompt as English instructions. The model is TOLD to return JSON; nothing in the wire protocol enforces it.

The provider SDK's native structured output is wire-level enforcement: the service refuses to emit text outside the schema. The model is CONSTRAINED, not instructed.

Wiring BOTH at once on Bedrock causes three problems:

1. **Double-prompting**. The schema gets serialized into the system prompt verbatim by `Pipe.kt:2028-2150`, AND the service receives it again as a wire constraint. Token waste on the input side, latency waste on the model side. A user with a 5KB JSON schema pays that cost twice.
2. **PCP-merged-mode break**. When `hasPcpTools && hasJsonOutput`, `Pipe.kt:2034-2073` instructs the model to return tool calls as JSON in the text output (`return an array of the following json: [${pcpRequestExample}]`). If `outputConfig.jsonSchema` is wired, the service locks the text to the user-defined schema, and tool calls expressed as JSON-in-text are syntactically invalid against that schema. The model has to choose: native `ContentBlock.ToolUse` blocks (the right way), or break the schema contract.
3. **Downstream parser contract change**. `Pipe.kt:4893` parses the schema string (not the response) to populate pipeline templates. The response-parser path is `MultimodalContent.text` → consumer. With native `outputConfig`, the text is guaranteed JSON matching the schema — easier to parse, but every existing consumer that handled prose-or-JSON now sees JSON-only.

### Mitigation shape (when wiring native)

Gate behind a feature flag:

```kotlin
fun setNativeStructuredOutput(enabled: Boolean = true): BedrockPipe {
    this.useNativeStructuredOutput = enabled
    if (enabled) {
        this.supportsNativeJson = true    // skip prompt injection
        this.useMergedModeForTools = false // force native setTools() path
    }
    return this
}
```

Then in every `build*ConverseRequest`, conditionally set:

```kotlin
if (useNativeStructuredOutput && jsonOutput.isNotEmpty()) {
    outputConfig = OutputConfiguration {
        textFormat = TextFormat {
            jsonSchema = JsonSchemaDefinition {
                name = "TPipeOutput"
                schema = Document.Map(jsonObjectToMap(...))
            }
        }
    }
}
```

This is a BREAKING change for users who currently combine `setJsonOutput` + `pcpContext.tpipeOptions`. They must migrate to native `outputConfig` + native `setTools()`. Worth a release-note callout.

### Verification recipe

```bash
# Confirm prompt-injection is currently the path for BedrockPipe
grep -nE 'supportsNativeJson|outputConfig|outputFormat' \
    TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt
# Expected: zero hits for outputConfig/outputFormat on BedrockPipe side.
# Hit count of 0 = prompt-injection is the only path; native structured
# output is unimplemented.

# Confirm the Pipe base flips supportsNativeJson on setJsonOutput
grep -nE 'ensureJsonPromptInjectionEnabled|supportsNativeJson' \
    TPipe/src/main/kotlin/Pipe/Pipe.kt
# Expected: every setJsonOutput overload calls ensureJsonPromptInjectionEnabled.
```

## SDK version consequences (1.5.97 → 1.6.107 / 1.8.15)

| SDK field added | Affects our builders? | Risk |
|---|---|---|
| `additionalModelRequestFields` passthrough | No (unchanged shape) | None |
| `inferenceConfig` passthrough | No (unchanged shape) | None |
| `serviceTier` passthrough | Already wired at every Converse builder | None |
| `toolConfig` passthrough | Already wired | None |
| `guardrailConfig` passthrough | **Latent bug: drops policy fields in streaming** | Pre-existing, upgrade doesn't fix |
| `performanceConfig` | Not wired | No risk if ignored; future feature |
| `requestMetadata` | Not wired | No risk if ignored; future feature |
| `promptVariables` | Not wired | No risk if ignored; future feature |
| `outputConfig` (structured output) | **NOT wired; would conflict with prompt injection** | **High** if naively added; needs feature flag |
| `ConverseStreamMetrics.latencyMs` (new in 1.6.x) | **NOT consumed in `executeConverseStream`** | Lost-data; upgrade doesn't fix automatically |
| `ContentBlock.CitationsContent` (in SDK since 1.5.97) | **NOT consumed in response-side dispatch** | Lost-data; pre-existing |
| `ContentBlock.ToolUse` (in SDK since 1.5.97) | **NOT consumed in response-side dispatch** | Lost-data; pre-existing |

**Bottom line**: the 30+ proprietary request builders are forward-compatible with the SDK upgrade. None of them break. The upgrade is safe as a pure bug-fix (Guardrail deadlock + new optional fields) without touching any builder.

## Cross-references

- `tpipe-pipe-feature-audit` SKILL.md — the parent methodology.
- `tpipe-pipe-internals` SKILL.md — for the documented-contract-without-enforcement pattern (sibling of the toStreamRequest bug).
- `tpipe-context-pull-builder-repair` — fix-side companion for silent no-ops.
- `tpipe-reasoning-pipes` — reasoning-pipe mechanics.
- `tpipe-bedrock-live-test-env-gates` (memory note) — live test env vars `AllowTest=true` + `MINIMAX_API_KEY`.
- `tpipe-multimodal-content-copy` (memory note) — for `MultimodalContent` schema extension pitfalls when adding `toolUse`, `citations`, or other typed fields.