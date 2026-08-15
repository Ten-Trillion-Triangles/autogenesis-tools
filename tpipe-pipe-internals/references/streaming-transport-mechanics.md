# TPipe Streaming — Provider Transport Mechanics

**Scope**: How streaming chunks travel from each provider's API to `emitStreamingChunk(String)`.
Not a wiring/pitfall guide (see `tpipe-pipe-feature-audit` for that).

## Architecture layers

| Layer | Where | Role |
|---|---|---|
| `StreamingCallbackManager` | `Pipe/StreamingCallbackManager.kt` | Holds `suspend (String) → Unit` callbacks, sequential/concurrent emission, per-callback error isolation |
| `StreamingCallbackBuilder` | `Pipe/StreamingCallbackBuilder.kt` | Fluent builder wrapping the manager |
| `emitStreamingChunk(String)` | `Pipe.kt:1865` base; overridden per provider | Entry point for all chunk delivery |
| `propagateStreamingCallback(callback)` | `Pipe.kt:1833` | Walks validator/transformation/branch/reasoning pipes; adds callback + calls `setStreamingEnabled(true)` on each descendant |
| Per-provider transport | Provider `Pipe` subclass | Reads the wire, parses deltas, calls `emitStreamingChunk` |

All four providers ultimately call `emitStreamingChunk(String)`. The base class handles callback propagation and management; provider code handles transport and parsing.

---

## GenericOpenAI (`TPipe-GenericOpenAI/.../GenericOpenAIPipe.kt`)

### Why HttpURLConnection, not Ktor

Ktor CIO 3.3.x `ByteReadChannel.readUTF8Line()` only releases bytes **after the response stream closes** — buffering the entire body before delivering it, defeating streaming entirely. `executeStreamingDirect` (`GenericOpenAIPipe.kt:1259`) bypasses Ktor and uses `java.net.HttpURLConnection` + `BufferedReader.lineSequence()` which blocks per line. Verified empirically by `RawHttpStreamingTest`: chunks arrive hundreds of ms apart. The Ktor SSE plugin has its own internal channel that reads bytes as they arrive (confirmed by `KtorSsePluginTest`), but the plain `bodyAsChannel()` path does not.

### Mantle chunked-encoding SigV4

When `bedrockMantleAuth is BedrockMantleAuth.Streaming`, `executeStreamingDirect` is **required** over Ktor because Mantle needs per-chunk AWS SigV4 signing via `ChunkedSigV4Signer` (`TPipe-GenericOpenAI/.../mantle/ChunkedSigV4Signer.kt`). The AWS streaming SigV4 algorithm signs the initial request normally, then each subsequent chunk carries `x-amz-content-sha256: STREAMING-AWS4-HMAC-SHA256-PAYLOAD` plus a per-chunk signature derived from the previous chunk. Ktor's body-writing path doesn't expose the low-level chunked-encoding primitives needed.

### SSE parsing by ApiMode

The SSE line-by-line loop at `GenericOpenAIPipe.kt:1318` dispatches on `apiMode`:

**`ApiMode.OpenAIResponses`** → `OpenAIResponsesSseParser.parseLine`:
- Sealed class events: `ResponseOutputTextDelta`, `ResponseReasoningTextDelta`, `ResponseCompleted`, `ResponseFailed`, `ResponseOutputTextDone`, etc.
- `ResponseOutputTextDelta.delta` → `textBuilder.append(delta); emitStreamingChunk(delta)`
- `ResponseReasoningTextDelta.delta` → `reasoningBuilder.append(delta)` (not emitted unless `streamModelReasoning`)
- `ResponseCompleted.usage` → captures `inputTokens`, `outputTokens`, `outputTokensDetails.reasoningTokens`

**`ApiMode.OpenAI`** → inline JSON parse:
- Legacy chat-completions SSE: `choices[].delta.content` extracted directly
- No dedicated `StreamEvent` class; parsed inline at lines 1395-1415

**`ApiMode.Anthropic`** → `AnthropicSseParser.parseAnthropicLine`:
- Manual outer-`type` field dispatch (polymorphic deserialization doesn't work because `content_block_delta` carries `index` + `delta` at outer level, not nested under a `chunk` key)
- `AnthropicStreamEvent.ContentBlockDelta` → `delta` is `AnthropicDelta.TextDelta` / `ThinkingDelta` / `InputJsonDelta`
- TextDelta → `emitStreamingChunk`; ThinkingDelta → `reasoningBuilder`; InputJsonDelta → caller handles separately

### Return-type widening for reasoning capture

`executeStreamingDirect` returns `MultimodalContent` (not `String`) so `streamingReasoningText` survives the streaming boundary. The `generateText` callers at lines 949-950 unwrap `.text`. The `generateTextMultimodal` callers use the full `MultimodalContent` including `modelReasoning`. This is the same sibling-helper override-return-type-widening pattern documented in `tpipe-pipe-internals`: `override suspend fun executeStreaming(): MultimodalContent` on a private method, with a public wrapper that unwraps.

---

## Bedrock (`TPipe-Bedrock/.../BedrockPipe.kt`)

### Transport: AWS SDK `invokeModelWithResponseStream`

The SDK returns `invokeModelWithResponseStream(request) { response → response.body?.collect { event → ... } }`. The callback fires per SDK event. No manual HTTP parsing — the SDK handles the SSE拆包.

`executeInvokeStream` at `BedrockPipe.kt:5145`:
1. Creates `InvokeModelWithResponseStreamRequest`
2. Calls `client.invokeModelWithResponseStream(request) { response → ... }`
3. Inside the lambda: `event.asChunkOrNull()?.let { chunk → ... }`
4. Decodes `chunk.bytes.decodeToString()` → `extractInvokeStreamDeltas(chunkString, modelId)` → `(textDelta, reasoningDelta)`
5. `textBuilder.append(textDelta); emitStreamingChunk(textDelta)`
6. `reasoningBuilder.append(reasoningDelta); if(streamModelReasoning) emitStreamingChunk(reasoningDelta)`

### Delta extraction

`extractInvokeStreamDeltas` (`BedrockPipe.kt:5307`) handles multiple JSON field shapes in a single chunk:
- `obj["text"]`, `obj["completion"]`, `obj["outputText"]` — model-specific field names
- `choices[].delta` — OpenAI style
- `delta` object — bare delta
- Reasoning: `obj["reasoningContent"]`, `choices[].delta.reasoning`

### emitStreamingChunk override

`BedrockPipe.kt:5274` override fires **both** the legacy `streamingCallback` field AND `streamingCallbackManager.emitToAll(chunk)`:
```kotlin
override suspend fun emitStreamingChunk(chunk: String) {
    streamingCallback?.let { callback → callback(chunk) }  // legacy, direct
    streamingCallbackManager?.emitToAll(chunk)             // manager, multi-callback
}
```
The legacy field is the single source of truth on BedrockPipe. Adding the same callback to both would double-fire — the manager adds the callback from `setStreamingCallback` but NOT from `enableStreaming`.

### Error handling: null vs MultimodalContent("")

Prior version returned `null` on stream exception, which parent `executeInvokeApi` interpreted as "fall back to non-streaming InvokeModel" — wasting a round-trip AND skipping all callback fan-out. Fix: return `MultimodalContent("")` so streaming errors surface as empty responses without retry.

---

## Ollama (`TPipe-Ollama/.../OllamaPipe.kt`)

### Transport: Ktor ByteReadChannel — works directly here

Unlike GenericOpenAI, Ollama's server delivers newline-delimited JSON (not SSE `data:` prefix) one object per line. Ktor's `ByteReadChannel.readUTF8Line()` reads line by line without the buffering problem — because the data arrives as discrete JSON objects rather than chunked-transfer SSE. No HttpURLConnection workaround needed.

### Two streaming endpoints

**`/api/chat`** (`executeChatStream`, `OllamaPipe.kt:973`):
```
client.preparePost(Endpoints.chatEndpoint).execute { response →
    val channel = response.bodyAsChannel()
    while(!channel.isClosedForRead) {
        val line = channel.readUTF8Line() ?: break
        val chunk = deserialize<ChatResponse>(line)
        val delta = chunk.message?.content ?: ""
        if(delta.isNotEmpty()) { textBuilder.append(delta); emitStreamingChunk(delta) }
        if(chunk.done) break
    }
}
```
Ollama's native streaming format — no SSE framing, just `ChatResponse` per line with `message.content` delta + `done` bool.

**`/api/generate`** (`executeGenerateStream`, `OllamaPipe.kt:1162`):
Same pattern, `GeneratedResponse.response` field instead of `ChatResponse.message.content`.

Tool calls accumulate in-band and surface at end of stream (not per-chunk). `executeGenerateApi` (`OllamaPipe.kt:1074`) dispatches to `executeGenerateStream` when `streamingEnabled = true`.

---

## OpenRouter (`TPipe-OpenRouter/.../OpenRouterPipe.kt`)

### Transport: Ktor ByteReadChannel via SseParser

OpenRouter uses SSE `data:` framing with the standard `[DONE]` sentinel. Ktor's `readUTF8Line()` works here because OpenRouter's SSE delivers lines incrementally — unlike GenericOpenAI's Ktor path which buffered. No HttpURLConnection needed.

### executeStreaming (`OpenRouterPipe.kt:765`)

```
client.post("$baseUrl/chat/completions").execute { response →
    val channel = response.bodyAsChannel()
    while(!channel.isClosedForRead) {
        val line = channel.readUTF8Line() ?: break
        val sseLine = SseParser.parseLine(line)  // data: / [DONE] / :comment / empty
        when(sseLine) {
            is SseLine.Done → break
            is SseLine.Data → {
                // SSE error events arrive inline and must be checked before StreamingChunk parse
                val sseError = try { deserialize<OpenRouterErrorResponse>(sseLine.content) } catch(_) { null }
                if(sseError != null) throw P2PException(...)
                val chunk = SseParser.parseChunk(sseLine.content) ?: continue
                val delta = SseParser.extractContent(chunk)
                if(delta.isNotEmpty()) { textBuilder.append(delta); emitStreamingChunk(delta) }
            }
            else → continue
        }
    }
}
```

Key difference from GenericOpenAI: SSE **error events** arrive as `data: {"error": {...}}` inline in the stream and must be detected before attempting `StreamingChunk` deserialization. These map to `P2PError` types (`auth_error → auth`, `rate_limit_error → transport`, etc.) and throw immediately.

### SseParser (`env/SseParser.kt`)

`SseParser` is the reusable SSE parsing library:
- `parseLine(line: String): SseLine` — classifies `data: {...}`, `data: [DONE]`, `:comment`, empty, invalid
- `parseChunk(json: String): StreamingChunk?` — deserializes to OpenAI chat-completions shape
- `extractContent(chunk: StreamingChunk): String` — `chunk.choices.firstOrNull()?.delta?.content ?: ""`
- `extractContentFromLine(line: String): String?` — convenience: parseLine + parseChunk + extractContent in one
- `iterateLines(lines: Iterator<String>, onChunk, onDone): String` — full iterator with callbacks

`StreamingChunk` is OpenAI chat-completions format: `choices[].delta.content`. OpenRouter is fully OpenAI-compatible on the streaming event shape.

---

## Cross-provider comparison

| Provider | Transport | Per-chunk read | SSE framing | Error events in stream |
|---|---|---|---|---|
| **GenericOpenAI** | `HttpURLConnection` direct | `BufferedReader.readLine()` blocking | Yes (`data:` prefix) | No (errors return HTTP status) |
| **Bedrock** | AWS SDK callback | SDK `collect { event → }` per event | Yes (SDK handles) | No (SDK surface) |
| **Ollama** | Ktor `ByteReadChannel` | `readUTF8Line()` per JSON line | No (raw NDJSON) | No |
| **OpenRouter** | Ktor `ByteReadChannel` | `readUTF8Line()` via `SseParser` | Yes (`data:` prefix) | Yes (`data: {"error": ...}` inline) |

### Callback API surface per provider

```
GenericOpenAI:
  setStreamingEnabled(Boolean): GenericOpenAIPipe
  setStreamingCallback(suspend (String) → Unit): GenericOpenAIPipe
  streamingCallbacks(StreamingCallbackBuilder.() → Unit): GenericOpenAIPipe

Bedrock:
  enableStreaming(callback, showReasoning, streamReasoning): BedrockPipe
  setStreamingCallback(suspend (String) → Unit): BedrockPipe

Ollama:
  enableStreaming(callback, showReasoning, streamReasoning): OllamaPipe
  setStreamingCallback(suspend (String) → Unit): OllamaPipe   (inherited from Pipe)

OpenRouter:
  setStreamingEnabled(Boolean): OpenRouterPipe
  setStreamingCallback(suspend (String) → Unit): OpenRouterPipe
```

All use `obtainStreamingCallbackManager()` from the base class. All call `propagateStreamingCallback` to push to child pipes. The provider-specific override points are `setStreamingEnabled` (wires the flag into the API request body/params) and `emitStreamingChunk` (Bedrock needs dual-fire suppression).

---

## Key design invariants

1. **`emitStreamingChunk` is the only chunk-delivery method.** Provider transports never call callbacks directly. All chunks go through `emitStreamingChunk` so the base class's manager/trace instrumentation applies uniformly.

2. **propagateStreamingCallback enables streaming on descendants.** Setting a callback on a parent pipe automatically calls `setStreamingEnabled(true)` on every descendant pipe, so streaming is requested from the provider even when the API call is issued by a child pipe.

3. **Dedup by reference in StreamingCallbackManager.** The same lambda registered twice (e.g., once via `setStreamingCallback` on the parent and once propagated to a child) would fire twice without dedup. The `callbacks.contains(callback)` check prevents it.

4. **HttpURLConnection vs Ktor is provider-specific, not universal.** GenericOpenAI needed it for SSE buffering and Mantle SigV4; Ollama and OpenRouter work fine with Ktor. Adding a new provider that uses SSE should try Ktor first and only fall back to HttpURLConnection if buffering is observed.

5. **Streaming without a callback is silent.** `setStreamingEnabled(true)` with no `setStreamingCallback` → the provider API runs in streaming mode, text accumulates in `textBuilder`, but no side effect fires. This is a common misconfiguration — the pipe appears to work but no chunks are delivered.
