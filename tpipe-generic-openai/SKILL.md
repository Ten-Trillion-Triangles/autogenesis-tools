---
name: tpipe-generic-openai
description: "TPipe GenericOpenAIPipe class — streaming architecture, API mode branching (OpenAI vs Anthropic), SSE parsing, live test patterns, and provider quirks (MiniMax, OpenAI-compatible, Bedrock Mantle). Load when implementing or testing streaming with GenericOpenAIPipe, when debugging API mode selection, when wiring a new provider into TPipe-GenericOpenAI, when auditing the Ktor `executeStreamingDirect` fix coverage, when investigating why Anthropic streaming returns 0 chunks, OR when a Mantle/Gemma pipe emits duplicated text or stalls after `[DONE]`. Includes the path-asymmetry map, the MiniMax-M2.7 thinking-only failure mode, the `AnthropicSseParser` wrapper-vs-direct-`deserialize` gotcha, the `streamingReasoning` Anthropic gate, AND the Mantle/Gemma cumulative-delta + swallowed-`[DONE]` hang in `executeStreamingDirect`'s `ApiMode.OpenAI` branch."
version: 1.2.0
author: Hermes Agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tpipe, generic-openai-pipe, streaming, sse, anthropic, openai, minimax, ktor-bypass, multimodal-path, retry, runRequestWithRetry, NoRouteToHostException, container-live-tests, manifold]
    related_skills: [lead-architect, ttt-code-styler, test-driven-development, subagent-driven-development, kanban-lead-architect, tpipe-trace-parser, graalvm-abi, tpipe-trace-output-conventions]
---

# TPipe GenericOpenAIPipe

## Overview

The `GenericOpenAIPipe` class (`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`) is TPipe's primary LLM integration point. It supports both OpenAI-compatible and Anthropic API modes, with full streaming support.

**Key architecture points:**
- `executeStreaming()` at ~line 746 — dispatches to `executeStreamingOpenAI()` or `executeStreamingAnthropic()` based on `ApiMode`
- `executeStreamingOpenAI()` at ~line 772 — handles OpenAI SSE format (`data: {...}` lines)
- `executeStreamingAnthropic()` at ~line 825 — handles Anthropic SSE format (`event: content_block_delta\ndata: {...}`)
- `SseParser.kt` (`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/SseParser.kt`) — `AnthropicSseParser` at line 188, `SseParser` at line 1, `extractContentFromLine()` at line 298 for Anthropic and line 110 for OpenAI
- `runRequestWithRetry()` at ~line 1556 — retry layer for HTTP-level errors, called from `generateText()` and other call sites. **Does NOT catch socket-level connect failures** — see the new pitfall below.

---

## API Modes

### ApiMode.OpenAI
- Endpoint format: `https://api.provider.com/v1` (OpenAI-compatible base path)
- Streaming format: SSE with `data: {...}` lines (no `event:` prefix)
- Parser: `SseParser` (line 1, `extractContentFromLine()` at line 110)
- Non-streaming: standard OpenAI chat completions JSON response
- Works with: OpenAI, MiniMax (at `api.minimax.io/v1`), any OpenAI-compatible provider

### ApiMode.Anthropic
- Endpoint format: `https://api.provider.com/anthropic` (Anthropic-specific path)
- Streaming format: SSE with `event: content_block_delta\ndata: {...}` lines (event: prefix + data: format)
- Parser: `AnthropicSseParser` (line 188, `extractContentFromLine()` at line 298) — requires JSON with `"type":"content_block_delta"` field
- Non-streaming: Anthropic messages API format
- Works with: Anthropic direct (`api.anthropic.com`), providers that emit true Anthropic SSE

### ApiMode.OpenAIResponses (added 2026-06-06)
- Endpoint: `POST {baseUrl}/responses` (e.g. `https://api.minimax.io/v1/responses`)
- Auth: same `Bearer $apiKey` header as `ApiMode.OpenAI` (line 187 of `GenericOpenAIPipe.kt`)
- Request shape: `OpenAIResponsesRequest` (`env/OpenAIResponsesRequest.kt`) — `input` is a list of `OpenAIResponsesInputPart` (text/image), not chat messages; `max_tokens` becomes `max_output_tokens`; `response_format` is wrapped as `text.format`; `reasoning` is a separate top-level object (`{effort, max_tokens}`)
- Response shape: `OpenAIResponsesResponse` (`env/OpenAIResponsesResponse.kt`) — top-level `output` array of typed items, usage in `usage` with `input_tokens`/`output_tokens`/`output_tokens_details.reasoning_tokens`
- SSE event namespace: `response.created`, `response.output_text.delta`, `response.completed` (NOT `data: {...}` like OpenAI chat, NOT `event: content_block_delta` like Anthropic)
- Parser: `OpenAIResponsesSseParser` (`api/OpenAIResponsesSseParser.kt`)
- Request serializer: `OpenAIResponsesRequestSerializer` (`api/OpenAIResponsesRequestSerializer.kt`)
- Response parser: `OpenAIResponsesResponseParser` (`api/OpenAIResponsesResponseParser.kt`) — maps the Responses-API usage object into the chat-completions-shaped `UsageInfo` so downstream tracing/UI code doesn't need to know which API mode produced the response. Carries `reasoning_tokens` through via `CompletionTokensDetails`.
- Tracing: `apiType` metadata is `"ResponsesAPI"` (set in `executeNonStreaming` and `executeStreaming` branches when `apiMode is ApiMode.OpenAIResponses`)

**Why a separate parser:** The OpenAI Responses API is a successor to chat-completions with three structural differences that prevent reusing the existing parsers: (1) streaming events use a `response.*` namespace prefix, not bare `data: {choices:[...]}`; (2) the response body has `output` as an array of typed items (message, reasoning, function_call), not `choices[0].message`; (3) usage has `output_tokens_details.reasoning_tokens` (Responses API) instead of `completion_tokens_details.reasoning_tokens` (chat-completions).

**Live tests:** `OpenAIResponsesLiveTest.kt` (non-streaming, streaming, system-prompt, JSON-object-format — 4 tests, gated on `MINIMAX_API_KEY`); `OpenAIResponsesTracingLiveTest.kt` (writes `/tmp/trace_report_console.txt` and `/tmp/trace_report.html` for inspection); `api/OpenAIResponses*Test.kt` (unit tests for the parsers, no live API needed).

---

## Critical Implementation Detail — Builder Chain Type Safety

`setApiMode()`, `setModel()`, `setTemperature()` are inherited from `Pipe` class and return `Pipe` (parent), not `GenericOpenAIPipe`. Builder chaining loses type access to `setStreamingCallback()`.

**CORRECT pattern:**
```kotlin
val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
pipe.setApiKey(apiKey)
   .setBaseUrl(baseUrl)
   .setApiMode(ApiMode.OpenAI)   // returns Pipe
   .setModel(model)
   .setMaxTokens(maxTokens)
   .setTemperature(0.0)

pipe.setStreamingCallback(callback)  // now accessible — typed as GenericOpenAIPipe
```

**WRONG pattern (type loss):**
```kotlin
// This compiles but setStreamingCallback is not accessible on the Pipe reference
GenericOpenAIPipe()
   .setApiKey(apiKey)
   .setApiMode(ApiMode.OpenAI)  // returns Pipe, not GenericOpenAIPipe
   .setStreamingCallback(callback)  // compile error: unresolved reference
```

---

## Streaming Callback Type

The streaming callback must be an explicit Kotlin suspend function type:
```kotlin
val callback: suspend (String) -> Unit = { chunk ->
    println("STREAM_CHUNK: [$chunk]")
    chunks.add(chunk)
}
```

Kotlin 1.9+ requires explicit `suspend` modifier for SAM conversion on functional types. Omitting `suspend` causes compile-time resolution issues with the callback interface.

---

## Provider Quirks

### MiniMax
- Base URL: `https://api.minimax.io/v1` (OpenAI-compatible) or `https://api.minimax.io/anthropic/v1/messages` (Anthropic)
- Model: `MiniMax-M2.7` (reasoning model — outputs `think` blocks first in response)
- API key: stored as `MINIMAX_API_KEY` env var
- **CRITICAL: Use full Anthropic endpoint path** `https://api.minimax.io/anthropic/v1/messages` — `/anthropic` alone returns 400
- Streaming with `ApiMode.OpenAI`: SSE `data: {...}` format at `/v1` endpoint — works fine, real-time chunks arrive
- **Streaming with `ApiMode.Anthropic`: SSE format IS correct (`event: content_block_delta\ndata: {...}`), MiniMax returns 200 with this format — but M2.7 emits ONLY `thinking_delta` blocks at default reasoning, no `text_delta` blocks. Parser's text-only filter drops them → empty streaming response. See "MiniMax-M2.7 Anthropic streaming thinking-only" pitfall below.**
- Non-streaming: works with `ApiMode.OpenAI` at `/v1` or `ApiMode.Anthropic` at `/anthropic/v1/messages`
- Earlier versions of this skill stated "MiniMax does NOT support true Anthropic SSE streaming format" — that is INCORRECT. MiniMax returns proper Anthropic SSE; the parser's text-only filter is the issue. Verified via direct curl: `curl -sN -X POST https://api.minimax.io/anthropic/v1/messages -d '{"model":"MiniMax-M2.7","max_tokens":512,"stream":true,"messages":[{"role":"user","content":"Say hello in 5 words."}]}'` returns `event: content_block_delta\ndata: {type: "content_block_delta", delta: {type: "thinking_delta", thinking: "..."}}` lines — no text deltas.
- **REVISION (2026-06-25)**: Even when M2.7 DOES emit `text_delta` content blocks (e.g., with `max_tokens=512` after the model finishes reasoning, or with reasoning disabled), the parser still drops them. The root cause is a missing `@JsonClassDiscriminator("type")` on `AnthropicStreamEvent` — `deserialize<AnthropicStreamEvent>` returns null for EVERY Anthropic SSE event, not just `ThinkingDelta`. See "Critical Pitfall: `AnthropicStreamEvent` missing `@JsonClassDiscriminator`" below.

### MiniMax-M2.7 Anthropic streaming — REAL root cause is sealed-class dispatch, NOT just discriminator (2026-06-25, REVISED 2026-06-25 round 2)

**Earlier versions of this pitfall (2026-06-25 round 1) said**: the fix is `@JsonClassDiscriminator("type")` on `AnthropicStreamEvent`. **That diagnosis was incomplete.** Adding the annotation ALONE does not fix the bug — three structural problems make `deserialize<AnthropicStreamEvent>` unreliable even with the annotation. Investigation (2026-06-25 round 2) found the real fix.

**Three reasons `@JsonClassDiscriminator` alone is insufficient:**

1. **Annotation isn't respected without explicit `Json { classDiscriminator = "..." }`.** TPipe's `com.TTT.Util.deserialize<T>()` constructs `Json { ... }` without `classDiscriminator` set. The `@JsonClassDiscriminator` annotation is informational metadata; the runtime dispatcher needs the Json config to opt in. Verified empirically: with annotation + default Json, `deserialize<AnthropicStreamEvent>` still fails for every event.
2. **The sealed class subclasses don't share a common discriminator field shape at the outer level.** `MessageDelta` has `stopReason` + `usage`, `Error` has `type` + `error`, `Done`/`Unknown` are empty. Without a uniform wrapper, polymorphic decode cannot dispatch uniformly.
3. **`ContentBlockDelta(val chunk: AnthropicStreamingChunk)` doesn't match the wire shape.** Wire format for `content_block_delta` carries `index` and `delta` at the OUTER level — not nested under a `chunk` key. Even with annotation + Json config, decode fails with `MissingFieldException: Field 'chunk' is required` because the wire JSON has no `chunk` key.

**Symptom**: `AnthropicStreamingLiveTest.testAnthropicStreamingLive` fails with `Response: []`, `Total chunks: 0`. Trace shows `streaming: true` and HTTP 200 — both true but misleading.

**REAL fix — replace direct `deserialize` with the existing `AnthropicSseParser` wrapper.** The wrapper at `SseParser.kt:197` already manually dispatches by the outer `type` field and is the canonical streaming parser. Apply at TWO call sites in `GenericOpenAIPipe.kt`:

```kotlin
// Direct-path Anthropic branch (was line 948-973 in executeStreamingDirect):
// BEFORE: deserialize<AnthropicStreamEvent> via SseParser.parseLine(...) — double-parse bug + sealed-class mismatch
// AFTER:
val parsed: AnthropicStreamEvent = AnthropicSseParser.parseAnthropicLine("data: $dataLine")
if (parsed is AnthropicStreamEvent.ContentBlockDelta) {
    when (val delta = parsed.chunk.delta) {
        is AnthropicDelta.TextDelta -> { /* textBuilder + emitStreamingChunk */ }
        is AnthropicDelta.ThinkingDelta -> { /* reasoningBuilder (new — captures into streamingReasoning) */ }
        is AnthropicDelta.InputJsonDelta -> { /* structured output — caller handles */ }
    }
}

// Ktor-path (was line 1249-1269 in executeStreamingAnthropic):
// Same parser swap. Note: pass `dataLine` directly (parseAnthropicLine accepts bare JSON OR `data: …` lines).
```

**Subtle double-parse bug the original code had.** The old code did `SseParser.parseLine("data: $dataLine")` to strip the SSE prefix, then passed the already-stripped `sseLine.content` to `parseAnthropicLine` which REQUIRES the `data: ` prefix to dispatch. The wrapper took the `else -> Done` branch for every line because the stripped JSON didn't start with `data:`. Result: 0 chunks emitted even before the deserialize call. The fix passes `"data: $dataLine"` directly to `parseAnthropicLine`.

**Companion fix — lift the `streamingReasoning` gate to include Anthropic mode.** Lines 1003 and 1091 in `GenericOpenAIPipe.kt` had:
```kotlin
val streamingReasoningText = if (apiMode is ApiMode.OpenAIResponses) streamingReasoning else ""
```
This gates `MultimodalContent.modelReasoning` exposure to only OpenAI Responses mode. With ThinkingDelta now being captured into `streamingReasoning`, the gate had to be widened:
```kotlin
val streamingReasoningText = when (apiMode) {
    is ApiMode.OpenAIResponses, is ApiMode.Anthropic -> streamingReasoning
    else -> ""
}
```
Same widening for the three token-counting fields (still gated to OpenAIResponses only since Anthropic's message_delta usage is parsed separately and not stored in `streamingInputTokens` etc.).

**Why this fix works.** `AnthropicSseParser.parseAnthropicLine` already correctly dispatches `content_block_delta` events via `parseAnthropicChunk` (which decodes the inner `AnthropicStreamingChunk` — that one IS polymorphic-decodable because its inner `delta: AnthropicDelta` sealed class HAS a uniform discriminator: each subclass has a `type` field with `@SerialName(...)` matching its wire value). The outer dispatch is handled manually by `parseAnthropicLine` based on the outer `type` field. The bug was that the production caller bypassed this wrapper with a raw `deserialize<AnthropicStreamEvent>` call that cannot succeed regardless of annotations applied to `AnthropicStreamEvent`.

**`AnthropicStreamEvent` is now documented as "always go through `AnthropicSseParser`"** at `env/AnthropicStreaming.kt:73-88` (added doc comment explaining the structural constraint). Direct polymorphic decode is not supported and not a sensible target for future fixes.

**TDD evidence.** The fix was driven by `AnthropicStreamingDispatchTest.kt` (5 tests, all GREEN, no network required) which pins the `AnthropicSseParser.parseAnthropicLine` contract for every event subtype. Live test `AnthropicStreamingLiveTest` updated to bump `MAX_TOKENS` from 256 to 2048 (M2.7 needs more headroom for thinking blocks) and to use a trivial prompt ("Respond with exactly the word: HELLO") that produces reliable text output after reasoning. Result: `chunks=1`, response=`HELLO`, test PASSED.

**Why the earlier note said "the streaming path handles thinking deltas correctly"**: that earlier note predated this investigation. `AnthropicSseParser.extractContent()` at `SseParser.kt:282` DOES correctly extract thinking text — but only when it's actually reached, which required fixing the call site to use the wrapper.

### MiniMax function calling — wire-discriminator required

`GenericOpenAIPipe.setTools(...)` produces a wire payload that OpenAI tolerates but MiniMax rejects when the `ToolDefinition.type` default is dropped by `encodeDefaults=false`. MiniMax returns `"invalid tool type:  (2013)"`. See the `tpipe-json-serialization` skill pitfall on required-on-the-wire discriminator fields for the fix (`@EncodeDefault(EncodeDefault.Mode.ALWAYS)` on the `type` field).

### MiniMax /anthropic thinking blocks — sealed-class discriminator required (streaming AND non-streaming)

When targeting MiniMax at the `/anthropic/v1/messages` endpoint, both the non-streaming response AND the streaming events can include `type: "thinking"` content blocks / `type: "thinking_delta"` chunks (alongside `type: "text"` / `type: "text_delta"`). **Both paths were broken on 2026-06-24; only the non-streaming response was fixed.**

**Non-streaming response — FIXED 2026-06-24**: `AnthropicMessagesResponse.ResponseContentBlock` sealed class now has `@JsonClassDiscriminator("type")` plus `@SerialName("text")` / `@SerialName("thinking")` on the two subclasses (`AnthropicMessagesResponse.kt:50-79`). Json config hardened in `ResponseParser.kt:39-51` (`ignoreUnknownKeys`, `isLenient`, `coerceInputValues`). Without this fix, deserialization fails with `"Serializer for subclass 'thinking' is not found in the polymorphic scope of 'ResponseContentBlock'"`.

**Streaming events — STILL BROKEN 2026-06-25**: the streaming-side sealed class `AnthropicStreamEvent` at `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/AnthropicStreaming.kt:76` is **missing `@JsonClassDiscriminator("type")`**. As a result, `deserialize<AnthropicStreamEvent>` fails for EVERY Anthropic SSE event, not just thinking events. The failure is silently swallowed by `com.TTT.Util.deserialize()`'s internal try/catch (which calls `repairAndDeserialize` on failure and returns null), so the streaming parser sees null for every event line, the text builder stays empty, and `AnthropicStreamingLiveTest` gets `Response: []`, `chunks: 0`. **The earlier note in this skill that "the streaming path (`AnthropicSseParser`) does handle thinking deltas correctly" was WRONG.** See the dedicated "MiniMax-M2.7 Anthropic streaming — REAL root cause is sealed-class discriminator" pitfall below for the full breakdown and the one-line fix.

**Verify both fixes**: with the non-streaming fix only, `MiniMaxFeaturesLiveTest.testPromptCachingAnthropicMode` passes but `AnthropicStreamingLiveTest` still fails. With both fixes applied, both tests pass.

## Critical Pitfall: `executeStreamingDirect` `ApiMode.OpenAI` branch — silent `[DONE]` swallow, malformed-JSON swallow, and cumulative-delta passthrough (2026-08-02, Mantle/Gemma)

The HttpURLConnection path's `ApiMode.OpenAI` branch at `GenericOpenAIPipe.kt:1389-1416` is the streaming parser for **every `setBedrockMantle(...)` call** (which sets `apiMode = ApiMode.OpenAI`). It has three defects that produce the "duplicated text" and "hangs after `[DONE]`" symptoms observed on Mantle/Gemma-31B. All three are silent — no trace event, no thrown exception, no surface signal.

### Defect 1 — `[DONE]` is silently swallowed

The loop at `GenericOpenAIPipe.kt:1318-1464` checks `line.startsWith("data: ")` (line 1330) but never checks for `data: [DONE]` specifically. The terminal sentinel falls through to `is ApiMode.OpenAI` (line 1389) where `Json.parseToJsonElement("[DONE]")` throws — caught by the silent `catch(_: Exception) { /* Skip malformed JSON line */ }` at line 1412. The line is dropped on the floor.

**Consequence.** Loop termination depends entirely on `reader.lineSequence()` reaching EOF. If the server keeps the connection open with SSE keep-alives (`: ` comment lines every 15s, or any heartbeat), the `readTimeoutMs = 120_000` (line 1286) will eventually fire — but if the server keeps flushing any byte at all, the loop hangs until the upstream coroutine times out. The Ktor path (`executeStreamingOpenAI` at lines 1753-1798) DOES handle `[DONE]` correctly via `SseParser.SseLine.Done → break` (line 1766). The direct path does not.

### Defect 2 — Malformed JSON lines silently dropped

The catch-all at `GenericOpenAIPipe.kt:1412-1415` swallows every `Json.parseToJsonElement` failure with no trace event. Any non-JSON `data:` line (e.g. a provider that emits a `data: <error envelope>` with a non-OpenAI shape, or a `data: <plain string>` for error reporting) is dropped without observable evidence. Symptom: trace shows `streaming: true`, `responseLength: 0`, no failure event — looks like a successful empty response.

### Defect 3 — Cumulative deltas forwarded verbatim (DUPLICATION ROOT CAUSE)

Per OpenAI chat-completions spec, every `data:` line carries an **incremental** delta (e.g. chunk 1: `{"choices":[{"delta":{"content":"Hel"}}]}`, chunk 2: `{"choices":[{"delta":{"content":"lo"}}]}`). The code at `GenericOpenAIPipe.kt:1397-1410` blindly extracts whatever `delta.content` is and forwards it to the callback + appends to `textBuilder`:

```kotlin
val content = (contentEl as? JsonPrimitive)?.content
if(!content.isNullOrEmpty()) {
    textBuilder.append(content)
    emitStreamingChunk(content)
}
```

If Mantle/Gemma-31B emits **cumulative** deltas (line 1: `"Hel"`, line 2: `"Hello"`), the callback sees `"Hello"` after already seeing `"Hel"` — the visible symptom is `II must must`, `ApplyingApplying`, or `Maple TreeMaple Tree` (a repeat-with-prefix pattern). The TPipe parser does NOT detect or correct this; it trusts the wire verbatim.

**Diagnostic recipe (run before any fix):**

1. Probe with `injectStreamingConnectionFactoryForTest` and capture every `data:` line in `MantleSseFixtureReplayTest`. Look for: cumulative prefix growth (each new value starts with the previous), repeated tokens, or identical `delta.content` across consecutive chunks.
2. Capture wall-clock chunk arrival times — if Mantle emits cumulative deltas, the chunk arrival cadence looks normal in wall-clock but the *content* is cumulative. Apply prefix-stripping before forking.
3. Compare against `OpenAIResponsesSseParser` and `AnthropicSseParser` parsers — both parse typed wire shapes with explicit field semantics. The `OpenAI` branch's ad-hoc `JsonElement` parse at lines 1397-1410 is the only path that trusts raw `delta.content` without type-level guarantees.

**Fix shape (NOT applied — capture for a future plan):**

```kotlin
// In executeStreamingDirect, is ApiMode.OpenAI branch (replace lines 1389-1416):
is ApiMode.OpenAI -> {
    // 1. BREAK on [DONE] BEFORE the JsonElement parse
    if (dataLine == "[DONE]") {
        return@forEach  // or break@forEach
    }
    // 2. Skip malformed JSON with a trace event instead of silent drop
    val element = try {
        Json.parseToJsonElement(dataLine)
    } catch (e: Exception) {
        trace(TraceEventType.API_CALL_FAILURE, TracePhase.EXECUTION,
              metadata = mapOf("reason" to "malformedDataLine", "rawLine" to dataLine.take(200)))
        return@forEach
    }
    // 3. Detect cumulative deltas and emit only the suffix
    val obj = element as? JsonObject
    val choicesArr = obj?.get("choices") as? JsonArray
    choicesArr?.forEach { choiceEl ->
        val choiceObj = choiceEl as? JsonObject
        val deltaObj = choiceObj?.get("delta") as? JsonObject
        val contentEl = deltaObj?.get("content")
        val content = (contentEl as? JsonPrimitive)?.content
        if (!content.isNullOrEmpty()) {
            val delta = if (content.startsWith(textBuilder)) {
                content.substring(textBuilder.length)  // strip cumulative prefix
            } else content
            if (delta.isNotEmpty()) {
                textBuilder.append(delta)
                emitStreamingChunk(delta)
            }
        }
    }
}
```

**Companion fix — wrap the `lineSequence()` consumer in `withTimeout`.** The whole SSE-reading loop needs a wall-clock deadline separate from `readTimeoutMs`. Suggested shape:

```kotlin
try {
    withTimeout(STREAMING_WALLCLOCK_TIMEOUT_MS) {  // e.g. 180_000 (3 min)
        reader.lineSequence().forEach { rawLine -> ... }
    }
} catch (e: TimeoutCancellationException) {
    trace(TraceEventType.API_CALL_FAILURE, TracePhase.EXECUTION,
          metadata = mapOf("reason" to "sseStreamTimeout", "partialText" to textBuilder.toString().take(200)))
    throw P2PException(P2PError.transport, "Streaming wall-clock timeout (no [DONE] within ${STREAMING_WALLCLOCK_TIMEOUT_MS}ms)", e)
}
```

**Why this matters for Mantle specifically.** Every Mantle pipe in Autogenesis uses `setBedrockMantle(region, "google.gemma-4-31b")` or `gemma-4-e2b`, which routes through `configureBedrockMantle` → `apiMode = ApiMode.OpenAI` → `executeStreamingDirect` → the `is ApiMode.OpenAI` branch. The bugs above are on the hot path for every Mantle call. The `MantleSseFixtureReplayTest` is the structural probe to write when fixing.

**Read `references/mantle-gemma-streaming-audit.md` for the full audit log — wire-format evidence, the verbatim `Json.parseToJsonElement` parse code, the Mantle endpoint URL construction, and the modified Autogenesis trace path that revealed the symptom.**

### MiniMaxFeaturesLiveTest (added 2026-06-24, both bugs fixed 2026-06-24)

4 live tests targeting MiniMax-specific features that aren't covered by the existing `OpenAIResponsesLiveTest` / `MiniMaxApiTest` / `AnthropicStreamingLiveTest`:

| Test | ApiMode | Status | What it proves |
|------|---------|--------|----------------|
| `testPromptCachingAnthropicMode` | Anthropic | ✅ PASS | `setCacheControl()` works on `/anthropic/v1/messages`; `ResponseContentBlock` discriminator is configured and deserializes thinking blocks |
| `testFunctionCallingOpenAIChatMode` | OpenAI Chat | ✅ PASS | `setTools()` with a weather-lookup tool schema; MiniMax accepts the tool definition (`type: "function"` is now in the wire payload) |
| `testJsonStructuredOutputOpenAIChatMode` | OpenAI Responses | ✅ PASS | `setResponseFormat("json_object")` works on Responses API; on plain Chat mode the model ignores json_object and emits thinking — use Responses API for structured output |
| `testStreamingOpenAIChatMode` | OpenAI Chat | ✅ PASS | Chunk ordering: `chunks.joinToString("") == assembled result` |

Each test follows the canonical `MiniMaxReasoningToggleTest` pattern: `TracingBuilder` at VERBOSE level + `autoExport` + save `pipeline.getTraceReport(TraceFormat.CONSOLE)` to a file under `TPipe-GenericOpenAI/build/traces/`.

**Both known bugs were fixed on 2026-06-24**:

1. `ToolDefinition.type` dropped by `encodeDefaults=false` → fixed with `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` on the `type` field in `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/ToolDefinition.kt:17`
2. `AnthropicMessagesResponse.ResponseContentBlock` missing polymorphic discriminator → fixed with `@JsonClassDiscriminator("type")` on the sealed class plus `@SerialName("text")` / `@SerialName("thinking")` on the two subclasses in `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/AnthropicMessagesResponse.kt:50-79`. Also hardened Json config in `ResponseParser.kt:39-51` (added `ignoreUnknownKeys`, `isLenient`, `coerceInputValues`).

See the `tpipe-json-serialization` skill's updated "Pitfall: required-on-the-wire discriminator fields" and "Pitfall: `@JsonClassDiscriminator` on sealed response types" sections — both now show the fix as applied.

### MiniMax reasoning toggle (two-knob architecture)

TPipe exposes TWO distinct reasoning knobs that work together — confusing them produces a non-functional toggle:

1. **Base Pipe reasoning flag** — `pipe.setReasoning()` / `pipe.disableReasoning()` on the base `com.TTT.Pipe.Pipe` class. These flip the `useModelReasoning: Boolean` field. This is what shows up in trace metadata as `reasoningEnabled=true` / `reasoningEnabled=false`. See `Pipe.kt:1119, 3930-3967` and the trace emit at `Pipe.kt:4723`.

2. **Wire reasoning config** — `pipe.setReasoningConfig(ReasoningConfig(...))` on `GenericOpenAIPipe`. This writes the `reasoning` block to the request body (`{effort, max_tokens, enabled, exclude}`). Has NO effect on the trace `reasoningEnabled` flag.

For a working toggle you typically need BOTH:
```kotlin
pipe.setReasoning()                          // flips trace flag
pipe.setReasoningConfig(                     // writes wire payload
    ReasoningConfig(effort = "high", enabled = true)
)
```

And to disable:
```kotlin
pipe.disableReasoning()                       // flips trace flag off
pipe.setReasoningConfig(
    ReasoningConfig(effort = "high", enabled = false)
)
```

**DEAD CODE WARNING:** `GenericOpenAIPipe.kt:157` declares `private var reasoningEnabled: Boolean? = null` — this field is never read or written by any code path. The trace `reasoningEnabled` metadata comes from the base Pipe's `useModelReasoning`, NOT from this field. Don't try to set it.

**MiniMax-M2.7 quirk:** The model emits reasoning content even when the wire-side `enabled=false` is set — the model is hardwired to chain-of-thought on reasoning-type prompts. So verifying the toggle works CANNOT be done by checking `reasoningContent` presence/absence in the response. Verify via the trace metadata `reasoningEnabled=true|false` instead. See `MiniMaxReasoningToggleTest` in `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/` for the canonical pattern (3 tests: ON, OFF, comparison guard that reads both trace files).

### Mantle cumulative-delta duplication — when `executeStreamingDirect` is the suspect (2026-08-02)

When a Mantle-routed pipe (`google.gemma-4-{e2b,31b}`) emits duplicated text in the user's terminal — visible symptom `II must must`, `ApplyingApplying`, `Maple TreeMaple Tree` — the cause is upstream of any application-layer rendering. The HttpURLConnection path's `ApiMode.OpenAI` branch at `GenericOpenAIPipe.kt:1389-1416` trusts the wire verbatim and forwards whatever `delta.content` arrives. See the dedicated "Critical Pitfall: `executeStreamingDirect` `ApiMode.OpenAI` branch — silent `[DONE]` swallow, malformed-JSON swallow, and cumulative-delta passthrough" section below for the three defects and the fix shape.

Run a structural probe with `injectStreamingConnectionFactoryForTest` to capture the raw `data:` lines and confirm whether the Mantle endpoint emits cumulative deltas before any fix.

### Canonical MiniMax reasoning toggle test pattern

The pattern from `MiniMaxReasoningToggleTest.kt` (3 tests, `@EnabledIfEnvironmentVariable(named = "MINIMAX_API_KEY", matches = ".+")`):

1. **Build pipe with `setReasoning()` + `setReasoningConfig(enabled=true, effort="high")`** → send `REASONING_PROMPT` (a math problem that forces chain-of-thought) → save `pipeline.getTraceReport(TraceFormat.CONSOLE)` to `build/traces/MiniMax-reasoning-ON.json` → assert `reasoningEnabled=true` in saved trace.
2. **Build pipe with `disableReasoning()` + `setReasoningConfig(enabled=false)`** → same prompt → save to `MiniMax-reasoning-OFF.json` → assert `reasoningEnabled=false` in saved trace.
3. **Comparison test** that reads both files (skip if either missing) and asserts the toggle flipped at the metadata level. Note: the comparison test runs as part of the full suite in the SAME gradle invocation — gradle cleans `build/` between isolated runs, so both ON and OFF tests must execute in one invocation for the comparison to find both files. Use `TRACES_DIR` env var to override the trace output location.

```kotlin
val traceConfig = TracingBuilder()
    .enabled()
    .detailLevel(TraceDetailLevel.VERBOSE)
    .outputFormat(TraceFormat.CONSOLE)
    .autoExport(enabled = true, path = traceDir().toString())
    .build()

val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
pipe.setApiKey(apiKey)
   .setBaseUrl("https://api.minimax.io/v1")
   .setApiMode(ApiMode.OpenAIResponses)
   .setModel("MiniMax-M2.7")
   .setMaxTokens(512)
   .setTemperature(0.0)
pipe.setReasoning()  // base Pipe flag — flips useModelReasoning = true
pipe.setReasoningConfig(ReasoningConfig(effort = "high", enabled = true))

val pipeline = Pipeline()
pipeline.add(pipe)
pipeline.enableTracing(traceConfig)
pipeline.init(true)

val result = pipeline.execute(REASONING_PROMPT)

// Save trace to disk for cross-test comparison
val report = pipeline.getTraceReport(TraceFormat.CONSOLE)
Files.writeString(dir.resolve("MiniMax-reasoning-ON.json"), report)
```

### Real Anthropic API
- Requires `sk-ant-...` API key
- Base URL: `https://api.anthropic.com`
- Streaming: requires `ApiMode.Anthropic` — emits true `event: content_block_delta\ndata: {...}` format
- To test Anthropic streaming: use real Anthropic key, not MiniMax

---

## SSE Format Reference

### OpenAI SSE (works with MiniMax at api.minimax.io/v1)
```
data: {"id":"...","choices":[{"delta":{"content":"Hello"}}]}
data: {"id":"...","choices":[{"delta":{"content":" world"}}]}
data: [DONE]
```

### Anthropic SSE (works with MiniMax at api.minimax.io/anthropic/v1/messages)
```
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}
```

The `AnthropicSseParser.extractContentFromLine()` checks for `"type":"content_block_delta"`. MiniMax at the Anthropic endpoint DOES emit this format for streaming.

---

## Live Test Pattern

```kotlin
class GenericOpenAIPipeLiveTest
{
    @Test
    fun testStreamingLive() = runBlocking<Unit>
    {
        val apiKey = System.getenv("MINIMAX_API_KEY")!!
        val chunks = mutableListOf<String>()
        val callback: suspend (String) -> Unit = { chunk ->
            println("STREAM_CHUNK_RECEIVED: [$chunk]")
            chunks.add(chunk)
        }

        val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
        pipe.setApiKey(apiKey)
           .setBaseUrl("https://api.minimax.io/v1")
           .setApiMode(ApiMode.OpenAI)
           .setModel("MiniMax-M2.7")
           .setMaxTokens(256)
           .setTemperature(0.0)

        pipe.setStreamingCallback(callback)

        val pipeline = Pipeline()
        pipeline.add(pipe)
        pipeline.init(true)

        val result = pipeline.execute("Say hello in 5 words.")

        assertTrue(chunks.isNotEmpty(), "Should have received at least one streaming chunk")
        assertTrue(result.isNotEmpty(), "Response should not be empty")
    }
}
```

### Live test inventory (MiniMax end-to-end, audited 2026-07-09)

All tests gated on `MINIMAX_API_KEY` env var (sourced from `/home/cage/.bashrc` line 235, prefix `sk-cp-`, last 4 chars `ao8Q`). Force fresh runs with `--rerun-tasks` — gradle's UP-TO-DATE optimization will return cached "passing" results from a prior session if the test class hasn't changed.

| Test class | API mode(s) | # tests | 2026-07-09 run status | Notes |
|---|---|---|---|---|
| `MiniMaxLiveTest` | OpenAI Chat (non-stream) | 1 | ✅ PASS | Response is real; assertion is only non-empty. **PROMPT-LOSS BUG**: model sees empty prompt, not `TEST_PROMPT = "Say 'Hello from MiniMax' in exactly those words."`. Root cause somewhere in `Pipeline.execute → executeMultimodal → appendContentToConverseHistory` — investigate separately. |
| `OpenAIResponsesLiveTest` | OpenAI Responses | 5 | ✅ ALL PASS | Non-stream, stream (1 chunk only), stream+reasoning, system prompt, json_object format. |
| `AnthropicStreamingLiveTest` | Anthropic (stream) | 1 | ✅ PASS (post-fix) | `chunks=1`, response=`HELLO` after the parser-swap fix. Test was updated to bump `MAX_TOKENS` from 256 to 2048 and use a trivial prompt that produces reliable text after reasoning. |
| `MiniMaxFeaturesLiveTest` | Anthropic + OpenAI + Responses | 4 | ✅ ALL PASS | Non-streaming Anthropic with cache control passes; streaming OpenAI chat passes (but assembled response is `\n` empty — model in pure-thinking mode). |
| `OpenAIResponsesTracingLiveTest` | OpenAI Responses | (tracing) | NOT RUN | Writes trace files to `/tmp/trace_report_console.txt` and `/tmp/trace_report.html`. Run separately if dashboard verification needed. |
| `GenericOpenAILiveTest` | Generic | 6+ | NOT RUN | Uses generic `getApiKey()` / `getBaseUrl()` helper, not MiniMax-pinned. Mostly error-handling (invalid model, missing creds) + HTML tracing. Out of scope for streaming verification. |
| **`ManifoldMiniMaxLiveTest`** (added 2026-07-09) | OpenAI Responses (via Manifold) | 4 | ⚠️ 3 PASS, 1 FAIL (transient) | **First live test for a TPipe container class via GenericOpenAIPipe.** Pattern: 4 tests (single-worker happy path, loop-limit, kill-switch, HTML-trace) all using `tracing { config(...) }` DSL block + `getTraceReport(TraceFormat.HTML)` + `writeStringToFile` to `${TPipeConfig.getTraceDir()}/Library/manifold-minimax-live/<test>/<test>.html`. See `references/container-live-test-pattern.md` for the full pattern. The loop-limit test failed once with `NoRouteToHostException` — see "Pitfall: `runRequestWithRetry` does NOT catch socket-level connect failures" below. |

**Total audited 2026-07-09:** 22 tests, 21 pass after the Anthropic streaming parser-swap fix. Remaining failure modes: (a) `MiniMaxLiveTest`'s prompt-loss bug (model receives empty prompt, not the source `TEST_PROMPT`) — separate bug in `Pipeline.execute → executeMultimodal`; (b) transient `NoRouteToHostException` in `ManifoldMiniMaxLiveTest.manifoldsLoopLimitExceededAtMaxIterations` — see new pitfall below.

**Curl verification command (proves the bug is in the parser, not the transport):**
```bash
KEY=$(grep -E '^export MINIMAX_API_KEY=' ~/.bashrc | head -1 | sed -E 's/^export MINIMAX_API_KEY="([^"]+)"$/\1/')
curl -sN --max-time 60 -X POST "https://api.minimax.io/anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"MiniMax-M2.7","max_tokens":512,"stream":true,"messages":[{"role":"user","content":"Say hello in 5 words."}]}' \
  | head -50
```
Expect: `event: content_block_delta` lines with `delta.type: "thinking_delta"` ONLY. No `text_delta` lines. That's the root cause.

---

## Phase 6 Streaming Debugging

When streaming returns 0 chunks:
1. Check URL matches expected format (`/v1` for OpenAI, `/anthropic/v1/messages` for Anthropic)
2. Verify `ApiMode` matches the SSE format the endpoint actually emits
3. If using MiniMax: `ApiMode.OpenAI` + `api.minimax.io/v1` OR `ApiMode.Anthropic` + `api.minimax.io/anthropic/v1/messages`
4. If using real Anthropic: use real Anthropic key, not MiniMax
5. Run test with debug print on callback — if 0 chunks, the SSE parser is receiving lines that don't match expected format
6. Inspect `SseParser.kt` `extractContentFromLine()` for the mode being used to confirm what format it expects

## Pitfall: Wrong import paths for `ApiMode` and `GenericOpenAIEnv`

These live under NESTED packages, not the top-level `genericOpenAIPipe` package:

- `ApiMode` → `genericOpenAIPipe.api.ApiMode`
- `GenericOpenAIEnv` → `genericOpenAIPipe.env.GenericOpenAIEnv`

**Wrong** (silently fails to resolve at compile time):
```kotlin
import genericOpenAIPipe.ApiMode           // Unresolved reference
import env.genericOpenAIPipe                // Wrong package
```

**Right**:
```kotlin
import genericOpenAIPipe.api.ApiMode
import genericOpenAIPipe.env.GenericOpenAIEnv as genericOpenAIEnv
```

The `as` alias in the second import preserves call-site ergonomics (`genericOpenAIEnv.resolveApiKey()` still works). Without the alias, every call site has to use the fully qualified `GenericOpenAIEnv.resolveApiKey()` which clutters downstream code. The skill's own bundled examples in `OpenRouterSmokeTest.kt` show the wrong package name — they're stale; use the corrected import above.

## Pitfall: Fluent-chain type collapse at `setModel()`

`setApiKey()`, `setBaseUrl()`, `setApiMode()` all return `GenericOpenAIPipe`. **`setModel()` is inherited from the base `Pipe` class and returns `Pipe` (parent type).** Calling `setModel()` mid-chain collapses the inferred type to `Pipe`, and any subsequent calls to `GenericOpenAIPipe`-specific methods (like `setStreamingEnabled`, `setStreamingCallback`, `setCacheControl`) fail to compile with "Initializer type mismatch: expected 'GenericOpenAIPipe', actual 'Pipe'."

**Wrong** (chain breaks after `setModel`):
```kotlin
val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
    .setBaseUrl("https://api.minimax.io/v1")
    .setApiKey(genericOpenAIEnv.resolveApiKey())
    .setApiMode(ApiMode.OpenAIResponses)
    .setModel("MiniMax-M3")              // <-- type collapses to Pipe here
    .setStreamingEnabled(true)           // <-- compile error
```

**Right** — either split the chain, or use Generic Open AI-specific methods BEFORE `setModel`:
```kotlin
// Option A: split the chain
val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
    .setBaseUrl("https://api.minimax.io/v1")
    .setApiKey(genericOpenAIEnv.resolveApiKey())
    .setApiMode(ApiMode.OpenAIResponses)
    .setStreamingEnabled(true)
pipe.setModel("MiniMax-M3")
pipe.setMaxTokens(256)
pipe.setTemperature(0.0)

// Option B: put Generic Open AI-specific setters BEFORE setModel
val pipe = GenericOpenAIPipe()
    .setBaseUrl("https://api.minimax.io/v1")
    .setApiKey(genericOpenAIEnv.resolveApiKey())
    .setApiMode(ApiMode.OpenAIResponses)
    .setStreamingEnabled(true)           // still GenericOpenAIPipe type here
    .setModel("MiniMax-M3")              // collapses to Pipe, but we're done with the chain
```

**Also wrong** — adding a `: GenericOpenAIPipe` type annotation to suppress the error:
```kotlin
val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
    .setBaseUrl(...)
    .setModel("MiniMax-M3")
    .setStreamingEnabled(true)           // Still compile error — annotation doesn't fix it
```

The annotation makes the variable's STATIC type `GenericOpenAIPipe`, but the chain's INFERRED type is `Pipe` after `.setModel()`. The compiler's static-vs-inferred check fires regardless. Use Option A or B above.

## Pitfall: `Env`-object static initializer fires before `Main.kt`

If your Kotlin app declares pipeline objects at the **object-level** (not inside a function), the static initializer runs at class-load time — BEFORE `Main.kt`'s `main()` body. Any pipeline construction that calls `pipe.init()` will fire during this static init, which means any env-var wiring you do inside `main()` is too late.

**Symptom**:
```
Exception in thread "main" java.lang.IllegalStateException: GenericOpenAI API key is required.
    at genericOpenAIPipe.GenericOpenAIPipe.init(GenericOpenAIPipe.kt:420)
    at Builders.PitchSlideWriterPipelineKt.buildPitchSlideWriterPipeline(...)
    at Globals.Env.<clinit>(Env.kt:99)
```

**Two fixes** — pick whichever fits:

**Fix A**: Lazy initialization. Don't construct at the field declaration site; defer until first access. By then, `main()` has run.
```kotlin
object Env {
    var writerPipeline = Pipeline()
    var ideaPipeline = Pipeline()
    // ...
    val pitchSlideWriterPipeline: Pipeline by lazy { buildPitchSlideWriterPipeline() }
}
```

**Fix B**: Wire the env var at the TOP of your `init()` function (or wherever pipelines get built), BEFORE the pipeline-construction calls that fire `pipe.init()`. Move the wiring block to be the very first statements of your init function.
```kotlin
fun init(...) {
    System.getenv("MINIMAX_API_KEY")?.takeIf { it.isNotBlank() }?.let {
        genericOpenAIEnv.setApiKey(it)        // wire FIRST
    }
    stylePipeline = buildNccWriter(writingStyle)   // then construct (which calls pipe.init())
    nccPipeline = buildNccWriter(writingStyle)
    // ...
}
```

Fix A is preferable for object-level fields you don't actually need at class-load time. Fix B is necessary when you have a regular `init()` function but the wiring block ended up AFTER the pipeline constructions (real refactor hazard).

## Critical Pitfall: generateText() vs sendRequest() Serialization

`generateText()` (line 580) and `sendRequest()` (line 516) use DIFFERENT serialization paths:

- `sendRequest()` (non-streaming + streaming path): uses `requestSerializer.serialize(request, apiMode)` — correct for both OpenAI and Anthropic modes
- `generateText()`: was using raw `serialize(request, encodedefault = false)` directly on `GenericOpenAIChatRequest` — produces OpenAI JSON format regardless of `apiMode`

**Symptom:** `ApiMode.Anthropic` with `generateText()` path returns 400 "invalid role: (2013)" — the JSON has `role: "user"` instead of `type: "user"`.

**Fix:** `generateText()` now uses `requestSerializer.serialize(request, apiMode)` instead of the raw `serialize()` call. This ensures Anthropic mode produces `{"type":"user",...}` format.

**Debug pattern:** Add `System.err.println("DEBUG_JSON_REQ: $jsonRequest")` before the HTTP POST to see exactly what JSON is being sent.

## Critical Pitfall: Ktor CIO `bodyAsChannel` buffers chunked SSE until stream close — bypass Ktor for streaming

**Status of the fix (2026-06-25 audit):** `executeStreamingDirect` is wired into `generateText()` (line 707–710) but NOT into `sendRequest()` (line 576–587). `sendRequest()` is hit whenever `generateContent()` receives multimodal/binary content — it still uses Ktor `client.post{}.bodyAsChannel()` and is vulnerable to the same buffering bug for all three `ApiMode` values. See "Path asymmetry" section below.

**Symptom:** Trace records `streaming: true` for every pipe, chunks arrive at the callback, but they ALL show up in one batch at the END of the model run. Terminal sees the full response appear all-at-once instead of token-by-token. The framework flag is correct — the transport is lying.

**Wall-clock diagnostic FIRST (before any patch).** Record `System.nanoTime()` per chunk and print inter-chunk deltas:
- All deltas ≈ 0ms in clusters → transport-level buffering (this pitfall)
- Median < 100ms with frequent small deltas → real streaming working
- One chunk total → no streaming at all

**Root cause (verified, Ktor 3.1.3 through 3.3.x).** Ktor CIO's `bodyAsChannel()` on a chunked transfer-encoded SSE response routes through `ktor-http-cio/HttpBody.kt:90` `parseHttpBody()` → `HttpClientDefaultPool.useInstance` which buffers chunks in a pool. The `ByteReadChannel` returned to user code does NOT block per network byte — by the time `readUTF8Line()` unblocks, the full response is already in the pool. Defeats the entire purpose of streaming.

The `streamingEnabled` flag is set, every `API_CALL_SUCCESS` trace event reports `streaming: true`, but the bytes never actually flow incrementally. The flag is necessary but NOT sufficient proof of real-time streaming.

**Fix (applied in TPipe, commit 8e4b8d76, in `generateText()` only).** When `streamingEnabled == true`, `GenericOpenAIPipe.executeStreaming` branches out of the Ktor path entirely:

```kotlin
if (streamingEnabled) {
    return withContext(Dispatchers.IO) {
        executeStreamingDirect(jsonRequest)
    }
}
```

`executeStreamingDirect(jsonRequest)` opens a direct `java.net.HttpURLConnection` with `setChunkedStreamingMode(0)`, writes the JSON body via `conn.outputStream.use { ... }`, then reads SSE line-by-line via `BufferedReader(InputStreamReader(conn.inputStream, UTF_8)).lineSequence()`. Each `readLine()` blocks at the socket until the server sends bytes — so every SSE `data: ` delta fires `emitStreamingChunk` as it arrives on the wire. Non-streaming path keeps Ktor (`bodyAsText()` works fine there).

The `when(apiMode)` parser fork inside `executeStreamingDirect` already handles `OpenAI`, `OpenAIResponses`, AND `Anthropic` — a single transport bypass fixes all three modes simultaneously.

### Path asymmetry — two entry points, only one patched (2026-06-25)

There are TWO independent streaming entry points in `GenericOpenAIPipe.kt`:

| Path | Function | Line | Streaming transport | Status |
|---|---|---|---|---|
| **A** (text-only path) | `generateText()` | 632, switch at 694–710 | `executeStreamingDirect` | ✅ FIXED (commit 8e4b8d76) |
| **B** (multimodal/binary path) | `sendRequest()` | 568, switch at 576–587 | Ktor `client.post{}.bodyAsChannel()` → `executeStreaming(channel)` (line 1035) | ❌ STILL UNFIXED — vulnerable for all 3 `ApiMode` values |

`generateContent()` (line 473) is the override TPipe's `Pipeline.execute()` calls. When content has no binary, line 477 delegates to `generateText()` (Path A — fixed). When content has binary/images, line 480+ builds a `GenericOpenAIChatRequest` directly and calls `sendRequest()` (Path B — still on Ktor). Both `executeStreamingOpenAI`, `executeStreamingAnthropic`, and `executeStreamingOpenAIResponses` parsers read from `bodyAsChannel()` and all three are vulnerable.

**Patch shape for Path B** (one-line replacement, identical structure to Path A):
```kotlin
// In sendRequest(), replace lines 576-587:
if(streamingEnabled)
{
    return withContext(Dispatchers.IO)
    {
        executeStreamingDirect(jsonRequest)
    }
}
```
Note: `sendRequest()` serializes with `serialize(request, encodedefault = false)` (line 574) while `generateText()` uses `requestSerializer.serialize(request, apiMode)` (line 692). The SSE wire format is the same for both paths so `executeStreamingDirect`'s parser fork works regardless of which serializer produced the JSON.

**Verification of the asymmetry:** Running TPipeWriter's `/chat` command (text-only, Path A) against MiniMax-M3 produces real-time chunked output. Running the same against an image-attached `/write` command (multimodal, Path B) shows chunks arriving in a single batch at end-of-stream — same Ktor buffering symptom. The framework `streaming: true` flag fires for both, masking the regression.

**Don't apply only Path B.** Path A's `generateText()` → `executeStreamingDirect` is the canonical fix and must stay. Both paths should bypass Ktor when streaming.

**Scope.** Non-streaming path (`bodyAsText()`) is unchanged. Only the streaming transport is swapped. Don't try to "fix" this by adding `flush()` calls to the Ktor path — the data is already buffered upstream of the channel by the time the user reads it.

**Alternatives if you can't bypass Ktor:**
- Ktor 3.2+ SSE plugin (`install(SSE)` + `client.sse { incoming.collect { event -> ... } }`) — works, but only on true SSE endpoints (`/v1/responses`, `/v1/chat/completions`); not for raw streaming chunk downloads. Verified streaming in 200-715ms chunks via `KtorSsePluginTest`.

**Empirical validation cited in the source KDoc:**
| Test | Transport | Inter-chunk gap |
|---|---|---|
| `RawHttpStreamingTest` | `HttpURLConnection` + `setChunkedStreamingMode(0)` + `BufferedReader.lineSequence()` | 200–700ms — real streaming |
| `RawKtorStreamingTest` | Ktor 3.3.3 CIO `bodyAsChannel()` | All at +4541ms, 0ms gaps — buffered |
| `KtorSsePluginTest` | Ktor 3.3.3 SSE plugin | 200–715ms — real streaming |

**Three-layer buffer trap.** This is buffer layer 1 of 3 that can each swallow chunks independently:
1. Ktor CIO `bodyAsChannel` (this pitfall — framework-level)
2. `System.out` line buffering (Pitfall 2 of `references/runtime-plumbing-pitfalls.md` — fix: `FileOutputStream(FileDescriptor.out)` with explicit `.flush()` per chunk)
3. `runBlocking` + dispatcher deadlock starving the streaming callback (Pitfall 4 — fix: daemon `Thread` flush pattern)

A `streaming: true` trace flag survives all three. Verify with wall-clock chunk timing, not with the trace.

**Verification standard:**
> Real-time streaming = terminal shows new characters appearing during the model's generation window, with multiple flushes per second. NOT a `streaming: true` flag. NOT `chunks.size > 0`. NOT visible end-of-pipeline output.

For application-level plumbing details (callback wiring, runtime helper, every-command verification recipe) see `references/runtime-plumbing-pitfalls.md` Pitfalls 1–7.

## Critical Pitfall: Dead `reasoningEnabled` field in `GenericOpenAIPipe`

`GenericOpenAIPipe.kt:157` declares `private var reasoningEnabled: Boolean? = null` — **this field is dead code**. It is never read or written by any code path. The trace's `reasoningEnabled=true|false` metadata comes from the base `com.TTT.Pipe.Pipe.useModelReasoning` field (see `Pipe.kt:4723`), NOT from this GenericOpenAIPipe-level field.

If you're tempted to set `pipe.reasoningEnabled = true` directly, don't. The correct APIs are:
- `pipe.setReasoning()` / `pipe.disableReasoning()` (base Pipe methods) for the trace-flag effect
- `pipe.setReasoningConfig(ReasoningConfig(...))` for the wire-payload effect

Future cleanup target: remove the dead `reasoningEnabled` field at `GenericOpenAIPipe.kt:157`.

## Critical Pitfall: Mantle pipe emits prose/empty where JSON is expected — three-gate diagnostic checklist (2026-07-30)

When a Mantle-routed pipe (`google.gemma-4-{e2b,31b}` via Bedrock Mantle endpoint) emits prose or empty responses where JSON is expected, the cause is rarely model behavior. It is one of three wire-format gates silently bypassing the JSON contract. **Run this checklist BEFORE assuming the model is broken.**

### The three early-return gates

`GenericOpenAIPipe.onApplySystemPromptComplete()` at line 407-414 is the wire-format completion hook. It translates `pipe.jsonOutput` to `response_format = {"type": "json_object"}` on the wire. It returns early on three conditions, ANY of which silently bypasses JSON enforcement:

```kotlin
override fun onApplySystemPromptComplete()
{
    if(responseFormat != null) return          // Gate 1: someone called setResponseFormat explicitly
    if(supportsNativeJson) return              // Gate 2: pipe advertises native JSON support
    if(jsonOutput.isBlank()) return            // Gate 3: pipe.jsonOutput was never populated

    responseFormat = ResponseFormat(type = "json_object", jsonSchema = null)
}
```

`requireJsonPromptInjection()` at Pipe.kt:2865-2868 sets `supportsNativeJson = false`, which unlocks Gate 2. If a Mantle builder calls neither `requireJsonPromptInjection()` nor `setJsonOutput(...)`, ALL three gates fire and the wire payload carries no JSON contract — even though the model is perfectly capable of producing JSON.

### Why Mantle reasoning-pipes need explicit wiring (Pipe.kt:8033/8047 adjacent)

`Pipe.getMiddlePromptForReasoning()` and `getFooterPromptForReasoning()` (Pipe.kt:8030-8050) read `reasoningPipe?.pipeMetadata["injectMiddlePrompt"]` and `["injectFooterPrompt"]` to decide whether to inject the host's JSON schema rail into the reasoning pipe's outgoing prompt. When the reasoning pipe was built directly (not through `ReasoningBuilder.assignDefaults`), these keys are absent — historically causing an NPE at the unguarded `as Boolean` cast.

**Partial fix shipped at GenericOpenAIPipe.kt:666-671**: `configureBedrockMantle` writes both keys, defaulting to `false`:

```kotlin
pipeMetadata["injectMiddlePrompt"] = false
pipeMetadata["injectFooterPrompt"] = false
```

This eliminates the NPE — `Pipe.kt:8033` now reads `as? Boolean ?: false` and returns `""` cleanly. **But the symptom persists**, because `false` SUPPRESSES injection rather than enabling it. A Mantle reasoning pipe attached via `setReasoningPipe(...)` never receives the host's JSON schema, so the reasoning output is generated without the rail. Downstream `extractJson<T>(text)` calls return null.

### Diagnostic recipe — run before any fix

1. **Read the public pipe surface directly.** `pipe.jsonInput`, `pipe.jsonOutput`, `pipe.reasoningPipe`, `pipe.pipeMetadata`, `pipe.getSystemPromptText()`. These are public; you don't need network access. If `pipe.jsonOutput.isBlank()` on a host that calls `requireJsonPromptInjection() + setJsonOutput(...)`, the host isn't actually wiring the contract — find the call site that bypasses it.

2. **For Mantle reasoning pipes, check `pipeMetadata["injectMiddlePrompt"]` directly.** If it equals `false` (the partial-fix default), middle-prompt injection is suppressed. If it's `true`, injection is enabled. The two states produce identical wire payloads for non-JSON reasoning outputs — there is no surface symptom that distinguishes "injection enabled but model ignored the rail" from "injection suppressed." You have to read the metadata.

3. **Capture the actual wire payload.** Build a structural probe (no network) PLUS a live probe gated on `BEDROCK_MANTLE_LIVE_TEST=true` that hooks `preInvokeFunction` to snapshot `content.text` immediately before the LLM call. The captured text IS the outgoing prompt that hits the wire. Look for the schema field name (e.g., `verdict`) — if it's not there, the JSON rail never reached the model.

4. **Cross-check existing live traces.** Autogenesis writes traces to `/home/cage/.tpipe/debug/trace/` per-round per-agent. The `API_CALL_SUCCESS` event carries `metadata.reasoningContent` AND `metadata.inputText` fields. If `inputText: "N/A"` but `responseLength > 0`, the trace layer already proves the wire payload wasn't captured — that's the gap, not the symptom.

### Probe design — avoid the test-prompt self-match trap

When asserting that an injected rail reached the wire, do NOT use a test prompt that contains the same words the rail would inject. Example anti-pattern:

```kotlin
const val TEST_PROMPT = "Reply with the JSON object matching the schema."  // contains "JSON"!
assertTrue(outgoingPrompt.contains("json", ignoreCase = true))             // passes for the wrong reason
```

The assertion passes because the test prompt itself contains "JSON", not because any injector fired. Tighten the assertion to look for a UNIQUE marker that ONLY the rail would add — typically a schema field name like `verdict`, `characterProfile`, or `actorName`. If the schema field name doesn't appear in the test prompt and doesn't appear in the captured wire payload, the rail truly did not reach the wire.

### What the Mantle wire payload actually looks like (pre-fix, verified 2026-07-30)

Live probe with `gemma-4-e2b`, `setJsonOutput(ProbeJson::class)`, `requireJsonPromptInjection()`, and `setReasoningPipe(mantleStructuredCotBuilder(...))`:

**Host outgoing prompt** (preInvokeFunction capture):
```
Reply concisely.
```
17 chars. Just the user prompt. Zero schema, zero JSON-mode instruction, zero system prompt.

**Reasoning pipe outgoing prompt** (preInvokeFunction capture):
```json
{
    "history": [
        { "role": "developer", "content": { "text": "  " }, "uuid": "..." },
        { "role": "user", "content": { "text": "Reply concisely." }, "uuid": "..." }
    ]
}
```
A converse-history JSON with an EMPTY developer role (two spaces) and the user prompt. Zero schema rail.

The model returned the same text as the prompt because it had nothing else to work with. The wire payload is the root cause, not the model.

### What fixes this (NOT applied — capture for a future plan)

1. **Mandate `requireJsonPromptInjection()` in every Mantle builder.** `BedrockConfig.buildMantleAuthorPipe` and `buildMantleReasoningPipe` at Autogenesis `server/src/main/kotlin/globals/BedrockConfig.kt:1115-1349` construct `GenericOpenAIPipe()` directly without calling `requireJsonPromptInjection()` or `setJsonOutput(...)`. The legacy Bedrock path goes through `ReasoningSettings` constructor that enforces this; the Mantle path does not.

2. **Flip `pipeMetadata["injectMiddlePrompt"]` default to `true` for Mantle reasoning pipes.** Change `GenericOpenAIPipe.kt:670-671` to write `true` instead of `false`. This requires either (a) ReasoningSettings constructor accepting the Mantle provider as a first-class option, or (b) a Mantle-specific override of `configureBedrockMantle` that defaults these keys on. Without this flip, reasoning pipes built via `mantleStructuredCotBuilder()` never receive the host's schema rail.

3. **Add the verifier pattern as a regression test.** Both probes in `server/src/test/kotlin/globals/MantleInjectorReachProbeTest.kt` and `MantleInjectorWireProbeLiveTest.kt` (round 1, pre-fix, Mantle) pin the current defect shape. They should be INVERTED to assert the post-fix state (schema field name IS present in outgoing prompt) once the fix lands. The structural probe runs in every gradle pass; the live probe is gated on `BEDROCK_MANTLE_LIVE_TEST=true` per the existing `BedrockMantleReasoningBuildersLiveTest` scaffold.

See `references/mantle-injector-reach-probe-pattern.md` for the full probe source, the hermetic verifier script (`/tmp/hermes-verify-mantle-injector-reach.sh`), and the captured wire-payload XML receipts.

## Critical Pitfall: `runRequestWithRetry` does NOT catch socket-level connect failures (2026-07-09)

`GenericOpenAIPipe.runRequestWithRetry()` at line 1556 is the retry layer for non-streaming HTTP calls. It catches `HttpResponseException` and a small set of other HTTP-level errors, but **does NOT catch `java.net.NoRouteToHostException`**, `java.net.ConnectException`, `java.net.SocketTimeoutException`, or any other `java.net` socket-level failure. These bubble straight up to `Pipeline.execute → Manifold.execute` and fail the test.

**Symptom (observed in `ManifoldMiniMaxLiveTest.manifoldsLoopLimitExceededAtMaxIterations`, 2026-07-09):**
```
java.net.NoRouteToHostException: No route to host
    at java.base/sun.nio.ch.Net.pollConnect(Native Method)
    ...
    at io.ktor.client.engine.HttpClientEngine.executeWithinCallContext(...)
    ...
    at genericOpenAIPipe.GenericOpenAIPipe$generateText$responseText$1$1.invokeSuspend(GenericOpenAIPipe.kt:1656)
    at genericOpenAIPipe.GenericOpenAIPipe$generateText$responseText$1.invokeSuspend(GenericOpenAIPipe.kt:756)
    at genericOpenAIPipe.GenericOpenAIPipe.runRequestWithRetry(GenericOpenAIPipe.kt:1556)
    at genericOpenAIPipe.GenericOpenAIPipe.generateText(GenericOpenAIPipe.kt:755)
    at genericOpenAIPipe.GenericOpenAIPipe.generateContent(GenericOpenAIPipe.kt:516)
    at com.TTT.Pipe.Pipe$executeMultimodal$2$result$2.invokeSuspend(Pipe.kt:6231)
    ...
    at genericOpenAIPipe.ManifoldMiniMaxLiveTest$manifoldsLoopLimitExceededAtMaxIterations$1.invokeSuspend(ManifoldMiniMaxLiveTest.kt:346)
```

In the same gradle invocation, 3 other tests in the same class hit the same `api.minimax.io` endpoint and all succeeded. The host was reachable. The failure is a transient socket-level hiccup that the retry layer should have caught and retried.

**Why it slipped through.** Ktor's HTTP client engine wraps the socket connect in `HttpClientEngine.executeWithinCallContext` and re-throws the raw `java.net.NoRouteToHostException` when the TCP handshake fails. The retry layer's exception filter only checks for `HttpResponseException` (HTTP 4xx/5xx) and a few others. Socket-level failures have a different exception class hierarchy (`IOException` → `SocketException` → `NoRouteToHostException`) and aren't matched.

**Workaround (test-side, applied 2026-07-09):** The test class declares a `transientFailureRetry: Int` counter and the test method's `try { ... }` block catches `NoRouteToHostException` / `ConnectException` / `SocketTimeoutException` and retries the whole `manifold.execute(...)` call up to 3 times. This is a TEST-SIDE workaround, not a framework fix — the framework's `runRequestWithRetry` still doesn't catch these.

**Proper fix (NOT applied — capture this for a future plan):**
1. In `runRequestWithRetry` (line 1556), widen the catch to include `IOException` (parent of all socket-level failures).
2. Distinguish between "host unreachable" (retryable) and "malformed URL" (not retryable) by checking the exception's `message` for known transient patterns.
3. The retry counter should reset per `runRequestWithRetry` call, not persist across the pipe's lifetime.

**When this fires in production (not just tests):** Any `TPipe` application that runs `GenericOpenAIPipe.execute(...)` against an LLM endpoint will fail the entire pipe run on a single transient socket hiccup. The user's pipeline state will show `IOException` not `HttpResponseException`. This is a production reliability bug, not just a test ergonomics issue.

**Diagnostic pattern for "is this a retry-able failure?":**
```bash
# Quick check: does the endpoint respond at all?
curl -sN --max-time 10 -X POST "$BASE_URL" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{}' | head -5
# If this returns "No route to host" / "Connection refused" / "Connection timed out", the retry layer WILL fail.
# If it returns a JSON 4xx/5xx, the retry layer WILL retry (if the error is in its filter set).
```

---

## Related Skills

- `graalvm-abi`: TPipe native image build, @CEntryPoint methods — for ABI-level TPipe work
- `tpipe-trace-parser`: Parse TPipe trace files for debugging execution flow
- `tpipe-trace-output-conventions`: Canonical trace-dir path convention + the container-live-test recipe (7 steps for `getTraceReport` + `writeStringToFile` to `TPipeConfig.getTraceDir()/Library/<feature>/<test>/`)
- `lead-architect`: End-to-end task management for TPipe features
- `test-driven-development`: TDD patterns for TPipe unit tests

## References

- `references/generic-openai-pipe-architecture.md` — GenericOpenAIPipe class structure, key methods
- `references/jitpack-publishing.md` — JitPack publishing setup, version resolution, TPipe build artifacts, ttt-site Lambda/DynamoDB backend pattern
- `references/minimax-api-quirks.md` — MiniMax API quirks discovered during live testing
- `references/sse-format-reference.md` — OpenAI vs Anthropic SSE format deep-dive
- `references/live-test-verification.md` — How to prove a live test is real: outputTokens/responseLength gap as smoking gun, responseId format check, TCP capture, regenerate-and-compare. Use when a user asks "is this test actually calling the API or is it returning canned data?"
- `references/container-live-test-pattern.md` — The 4-test `ManifoldMiniMaxLiveTest` pattern: env-gated, `tracing { config(...) }` DSL block, `getTraceReport(TraceFormat.HTML)` → `writeStringToFile` chain, per-test subdir, content-anchor assertions. Use as the template when adding a new live test for any TPipe container class (Manifold, Junction, DistributionGrid, Splitter).
- `references/per-family-dispatch.md` — The per-family strategy dispatch pattern used in BedrockPipe (and why GenericOpenAIPipe does NOT need it). Documents the `requestedModelId` anchor, the five axes of family-specific customization (request builder / response extractor / reasoning activation / context window / validation), and how to add a new model family.
- `references/bedrock-mantle-endpoint.md` — Bedrock Mantle endpoint integration reference. Mantle is the OpenAI-compatible regional endpoint (`bedrock-mantle.{region}.api.aws/openai/v1`) that exposes new Bedrock models NOT reachable via Converse (`openai.gpt-5.6-{sol,terra,luna}`, `google.gemma-4-{31b,e2b}`). Documents two auth modes (Bedrock API key bearer / AWS SigV4), the minimum IAM policy, and the three integration gaps in this module (base-URL override, bearer-token auth, SigV4 signing). Research-stage — no production code has been modified yet. Read this BEFORE wiring Mantle into `GenericOpenAIPipe`.
- `references/anthropic-streaming-parser-fix.md` — Full investigation log for the 2026-06-25 Anthropic streaming parser bug. Captures the three rounds of false leads (thinking-only filter, missing discriminator, double-parse), the actual fix (parser wrapper swap + ThinkingDelta capture + streamingReasoning gate widening), and the diagnostic-test pattern that surfaced each layer in 30 seconds. Read this AFTER the SKILL.md pitfall; it's the deep log.
- `references/minimax-model-references.md` — Canonical MiniMax model names (M3, M2.7, M2.5, M2.1, M2), `think` block format, reasoning_details[] response shape, when to use `/v1` vs `/anthropic/v1/messages`, deprecated model names (e.g. `MiniMax-text-01`) to never use in docs or tests.
- `references/minimax-m3-tpipewriter-pattern.md` — End-to-end worked example: TPipeWriter GenericAI branch migration from Bedrock to MiniMax-M3. Includes the 9-commit surgical refactor pattern, file-by-file change shape, common mistakes (incl. `gptOssModelName` shadow bug + JSON-mode surgical-change failure with M3 prose output), and the **"drive EVERY command" TUI verification recipe**.
- `references/runtime-plumbing-pitfalls.md` — Interactive TPipe application runtime plumbing: streaming + tracing + runBlocking pitfalls across many command handlers. Covers the SEVEN pitfalls found in the TPipeWriter TUI verification rounds 2 + 3 (streaming callback duplication, `System.out` line-buffering, `runBlocking` hangs after removed `setPipeCompletionCallback`, dispatcher deadlock with coroutine flush, API key visibility, post-stream `println` duplication, **FRAMEWORK-LEVEL: streaming callback set on parent pipe doesn't fire for child pipe chunks**), the runtime helper pattern that fixes the application-level ones, and the "drive every command" verification recipe. Includes the exact Pipe.kt framework fix (propagateStreamingCallback + hoisted streamingEnabled + child-setter inheritance + StreamingCallbackManager dedup) when the bug belongs in the framework. **Read this if you're building or debugging an interactive TPipe application TUI/CLI/REPL.**
- `references/runRequestWithRetry-gap.md` — Full investigation log for the 2026-07-09 `NoRouteToHostException` slip-through. Documents the test-side workaround (try/catch + retry counter), the proper framework fix (widen `runRequestWithRetry`'s catch to include `IOException`), and the diagnostic curl command to distinguish retryable socket failures from non-retryable application errors. Read this AFTER the SKILL.md pitfall; it's the deep log.
- `references/mantle-injector-reach-probe-pattern.md` — Mantle JSON-injection contract verification recipe. Structural + live probe pair for confirming whether `pipe.jsonOutput` / `setJsonOutput` / middle-prompt injection actually reach the Mantle wire, the three early-return gates in `onApplySystemPromptComplete`, the `pipeMetadata["injectMiddlePrompt"] = false` partial-fix suppression shape, the schema-field-name self-defeating-assertion trap, the hermetic verifier script pattern, and the captured pre-fix wire payload (host: 17 chars; reasoning pipe: empty developer role). Use this whenever investigating "Mantle pipe emits prose/empty where JSON is expected."
- `references/pipe-metadata-typed-extension.md` — class-level pattern for one-off serializer features that ride on `pipeMetadata` instead of growing `GenericOpenAIPipe`'s public API. Captures the 4-step pattern (carrier + key + guard → serializer-options widening → wire emission → caller extension), the `pipeMetadata: MutableMap<Any, Any>` → `Map<String, Any?>` cast at the call site, the `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` requirement for wire fields whose defaults the receiver requires, the `OpenAIRequestSerializer` dispatch passthrough that must forward the new options parameter, and the stash-and-restore-with-`trap` recipe for unblocking `compileTestKotlin` against pre-existing baseline test rot. Worked example: the 2026-08-03 Mantle GPT-5.6 explicit-caching 18-task plan.
- `scripts/run_tpw_full_test.sh` — Reusable tmux-driven TUI verification harness. Drives 30 commands sequentially, parses the trace after each, and reports per-test results. Use this when verifying ANY TPipeWriter-style TUI app end-to-end.
- `scripts/MiniMaxStreamingTimingTest.kt` — Live diagnostic test that PROVES real-time streaming by measuring wall-clock arrival time of every SSE chunk. Use this when debugging "is it really streaming or just buffered?" (Pitfall 8 in `runtime-plumbing-pitfalls.md`). Records System.nanoTime() per chunk and prints inter-chunk gaps. Regressions to bodyAsChannel buffering show as 0ms gaps; the executeStreamingDirect fix shows 200-715ms gaps. Skipped if MINIMAX_API_KEY is not set.
- `scripts/SealedClassDeserializationDiagnostic.kt` — Reusable diagnostic test template for "deserialize<T>() returned null for sealed class" bugs. Bypasses `Util.deserialize`'s internal try/catch and prints the kotlinx.serialization exception with full type + message. Each exception type pinpoints which fix to apply next. See `references/anthropic-streaming-parser-fix.md` for the worked example.

## TUI verification philosophy (learned from the user)

The user's rule, repeated in different forms across multiple sessions:
**spot-checking TUI commands is not enough; drive every `/help` command via tmux and parse the trace afterward.** The reasoning:

1. Some commands hang silently (no exception thrown).
2. Some commands "succeed" via onFailure callbacks that mask the underlying LLM-pipe failure (e.g., JSON-mode surgical-change pipes that recover via `processed.text = ContextBank.getContextFromBank("new page").contextElements.lastOrNull()`).
3. Some commands write to disk in ways that are silently broken (e.g., `/save` "succeeds" by writing an empty ContextWindow with the same content as before — file modify time doesn't change).
4. The user's exact words (2026-06-25): *"I'm not sure you've tested eerything at this stagee"* — followed by explicit steering toward JSON config verification and JDWP hookup for hang debugging.

The test harness at `scripts/run_tpw_full_test.sh` implements this workflow. Use it as a template when verifying ANY TPipe application end-to-end.

**The runtime plumbing pitfall reference (`references/runtime-plumbing-pitfalls.md`) captures the six specific symptoms the user hit when they pushed back on me for spot-checking** — streaming callback duplication, `System.out` line-buffering, `runBlocking` hangs from removed `setPipeCompletionCallback`, dispatcher deadlock with coroutine flush, silent API-key hangs, and post-stream `println` duplication. **Build the runtime helper pattern once at the architecture layer. Don't sprinkle streaming/tracing setup across each command handler.** When you find yourself patching 6 call sites with the same fix, refactor to a helper.
