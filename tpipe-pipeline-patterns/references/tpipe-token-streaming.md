# TPipe Token Streaming — End-to-End Map

Source-tree evidence: branch `main`, HEAD `84ae4774`. All file:line citations verified by direct read.

## Architecture in one paragraph

Token streaming in TPipe is a four-layer stack: **(1) provider-specific public registration** (`setStreamingCallback` or `enableStreaming`) → **(2) per-pipe `StreamingCallbackManager`** that holds N callbacks with error-isolated fan-out → **(3) the `Pipe.emitStreamingChunk` hook** that funnels every wire-format delta through `manager?.emitToAll(chunk)` → **(4) the transport** (HTTP+SSE parsed by a mode-specific `SseParser`, AWS SDK `converseStream` callbacks, or Ktor `bodyAsChannel`). Callback propagation walks the tree of validator / transformation / branch / reasoning children so chunks from any pipe in the family reach the same sink. Reasoning tokens are gated onto a separate `MultimodalContent.modelReasoning` field, not the default text stream.

## Layer 1 — public registration per provider

| Provider | Entry point | File:line |
|----------|-------------|-----------|
| GenericOpenAI | `setStreamingCallback(callback): GenericOpenAIPipe` | `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:424` |
| Bedrock | `enableStreaming(callback?, showReasoning, streamReasoning): BedrockPipe` | `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:630` |
| Bedrock | `setStreamingCallback(callback): BedrockPipe` (suspend) | `BedrockPipe.kt:700` |
| Bedrock | `setStreamingCallback(callback): BedrockPipe` (non-suspend wrapper) | `BedrockPipe.kt:725` |
| Ollama | `enableStreaming(callback, showReasoning, streamReasoning): OllamaPipe` | `TPipe-Ollama/src/main/kotlin/ollamaPipe/OllamaPipe.kt:232` |
| Base | `setStreamingEnabled(enabled): Pipe` (just flips the flag, no callback) | `Pipe/Pipe.kt:902` |

Every provider's `setStreamingCallback` does three things: (a) sets `streamingEnabled = true`, (b) calls `obtainStreamingCallbackManager().addCallback(callback)`, (c) calls `propagateStreamingCallback(callback)` to recurse into descendant pipes.

## Layer 2 — callback fan-out

`StreamingCallbackManager` (`src/main/kotlin/Pipe/StreamingCallbackManager.kt`):
- `addCallback(suspend (String) -> Unit)` — line 40 — dedups by reference equality (without dedup, chunks appear as duplicates "HelloHello" per the KDoc)
- `getCallbacks(): List<...>` — line 58 — used by parent pipes to seed descendants
- `emitToAll(chunk)` — line 98 — branches on `executionMode: SEQUENTIAL | CONCURRENT` (CONCURRENT uses `coroutineScope` + `launch`)
- `onError: (Exception, String) -> Unit` — line 30 — invoked per callback if it throws, isolates failures from breaking the stream

`StreamingCallbackBuilder.kt` is the fluent façade: `.add { chunk -> ... }` overloads (suspend + non-suspend), `.sequential() / .concurrent()`, `.onError { ... }`, `.build()`.

## Layer 3 — `Pipe.emitStreamingChunk` and the propagation tree

`src/main/kotlin/Pipe/Pipe.kt`:
- `streamingCallbackManager: StreamingCallbackManager?` — line 884 — `@Transient` per-pipe slot
- `streamingEnabled: Boolean = false` — line 895
- `setStreamingEnabled(enabled)` — line 902 — base just flips the flag
- `obtainStreamingCallbackManager()` — line 1754 — lazy
- `propagateStreamingCallback(callback, visited)` — line 1776 — recurses into `validatorPipe`, `transformationPipe`, `branchPipe`, `reasoningPipe`
- `protected suspend fun emitStreamingChunk(chunk)` — line 1808 — `manager?.emitToAll(chunk)`
- Propagation-to-attached-pipe hooks — lines 4447, 4469, 4490, 4505 — `setValidatorPipe`, `setTransformationPipe`, `setBranchPipe`, `setReasoningPipe` each copy parent callbacks into the new child's manager. Mirrors `propagateTracingRecursively`.

Without propagation, a callback registered on a parent pipe would not fire when a child pipe's API call streams. The tree walk is what makes `setReasoningPipe(reasoning)` + `setStreamingCallback { ... }` actually stream both pipes to the same sink.

## Layer 4 — three wire formats

### Format A — HTTP + SSE (GenericOpenAIPipe)

The dispatch in `generateContent` (`GenericOpenAIPipe.kt:793, 798`):

```
val stream = streamingEnabled                              // request body field
if (streamingEnabled) {
    return withContext(Dispatchers.IO) { executeStreamingDirect(jsonRequest) }
} else { /* normal non-streaming Ktor post → responseParser.parse(...) */ }
```

**The non-obvious carve-out** — `executeStreamingDirect` at line 935 bypasses Ktor entirely:

> BUG FIX: Ktor CIO 3.x does NOT deliver bytes incrementally for chunked transfer-encoded SSE responses through 3.3.x. All data arrives as one batch when the stream closes. Workaround: bypass Ktor entirely for the streaming call and open a direct `HttpURLConnection` with chunked transfer encoding. We feed the JSON body and read the response line-by-line. The InputStream blocks per line read, so each SSE delta fires `emitStreamingChunk` as it arrives on the socket — verified empirically via `RawHttpStreamingTest` (chunks arrive hundreds of ms apart rather than all in one batch).

This is the most important comment in the streaming subsystem. Anyone encountering a "streaming only emits once at the end" bug has hit the Ktor buffering path. The Ktor path `executeStreaming` at line 1217 still exists (`bodyAsChannel()` + mode dispatch) but is not on the streaming hot path.

Mode dispatch inside `executeStreamingDirect`:

| `apiMode` | Dispatch | Delta source |
|-----------|----------|--------------|
| `OpenAI` (Chat Completions) | inline SSE parse at lines 1357-1364 | `SseParser.extractContent(chunk)` |
| `OpenAIResponses` | polymorphic `OpenAIResponsesStreamEvent` at lines 991-1043 | `ResponseOutputTextDelta.delta`, `ResponseReasoningTextDelta.delta`, terminal `ResponseCompleted` |
| `Anthropic` | `executeStreamingAnthropic` at line 1378 | `AnthropicStreamEvent.ContentBlockDelta.TextDelta.text` |

Anthropic reasoning (`AnthropicDelta.ThinkingDelta`) accumulates into a parallel `reasoningBuilder` — not emitted to the default text callback.

Final accumulation at line 1153-1177: `streamingReasoning` is captured only for `OpenAIResponses` and `Anthropic` apiModes and placed into `MultimodalContent.modelReasoning`. `text = resultText` is the `StringBuilder.toString()` of every text delta. Streaming usage captured only in `OpenAIResponses` mode.

### Format B — AWS SDK callbacks (BedrockPipe)

`BedrockPipe.kt:4277 executeConverseStream(client, modelId, request, apiLabel): MultimodalContent?`:
- Opens `client.converseStream(request.toStreamRequest()) { response -> ... }`
- Inside the SDK callback: `response.stream?.collect { event -> ... }` — Kotlin Flow from AWS SDK
- Each `event.asContentBlockDeltaOrNull()?.let { ... asTextOrNull()?.let { textBuilder.append(it); emitStreamingChunk(it) } }` at lines 4310-4313
- Reasoning: `asReasoningContentOrNull()?.asTextOrNull()?.let { reasoningBuilder.append(it); if (streamModelReasoning) emitStreamingChunk(it) }` at lines 4315-4321 — note the `streamModelReasoning` gate (default true at base Pipe.kt:1337; BedrockPipe checks the value at the call site)
- Stop reason + token usage captured from `event.asMessageStopOrNull()` and `event.asMetadataOrNull()?.usage`

`BedrockMultimodalPipe.kt:144-156, 239-250` is the bridge: if `streamingEnabled` is true, calls `executeConverseStream(...)` and wraps the returned `MultimodalContent(text, modelReasoning, binaryContent)` for the consumer.

Bedrock-specific quirk — BedrockPipe retains a **legacy single-callback field** in addition to the manager:

```
BedrockPipe.kt:188      private var streamingCallback: (suspend (String) -> Unit)? = null
BedrockPipe.kt:674      disableStreaming() — clears streamingCallback AND streamingCallbackManager
```

The new path is the manager; the legacy field is a vestige. Both fire if both are set — usually fine because they're the same callback.

`StreamingTerminal.kt` is the one-liner helper for terminal printing: `pipe.enableStreaming().setStreamingCallback({ chunk -> print(chunk); out.flush() })`.

### Format C — Ktor channel (Ollama, OpenRouter)

Both use Ktor `client.post(...).bodyAsChannel()` and read SSE/NDJSON directly via line iteration. The Ktor buffering bug does not surface here because Ollama and OpenRouter don't use chunked-transfer SSE the same way — Ktor delivers bytes incrementally over plain Content-Length or HTTP/1.1. If you saw "chunks arrive as one batch" on an Ollama pipe, the cause is NOT the Ktor issue — check the backend's response headers.

### Format D — same-shape hybrid (OpenRouter)

OpenRouter's `TPipe-OpenRouter/` is structurally a clone of GenericOpenAI: same `SseParser.kt` lineage, same `apiMode` dispatch (a two-mode subset of GenericOpenAI's three). The streaming path is `executeStreamingDirect` if you see it; otherwise the Ktor channel path. OpenRouterPipe's `enableStreaming(callback)` mirrors OllamaPipe's fluent shape.

## Reasoning channel separation

`MultimodalContent.modelReasoning` (`src/main/kotlin/Pipe/BinaryContent.kt:118-127`):
- `@Transient` — does NOT survive serialization, one-call lifetime
- `merge()` at line 388-393 lets downstream pipes take the richer `modelReasoning` from `other` when both halves have content
- Reasoning never appears in `text` by default — only lifted when `splitInterleavedReasoning` finds `` ... `` tags in the streamed text and the native field is empty (`BedrockPipe.kt:5035`)

Three capture points:
1. **Native provider field** — Bedrock `contentBlockDelta.reasoningContent.text`, Anthropic `ThinkingDelta.thinking`, OpenAIResponses `ResponseReasoningTextDelta.delta`. Captured in apiMode-specific code paths.
2. **`streamModelReasoning` gate** — `BedrockPipe.kt:4317` checks the base-Pipe flag. Off means reasoning is captured into the returned `MultimodalContent.modelReasoning` but not streamed chunk-by-chunk.
3. **Tag-based post-split** — `splitInterleavedReasoning(content)` runs after stream close on the final `MultimodalContent`. Lifts `` ... `` to `modelReasoning` if the native field was empty.

## Consumer-side patterns

```kotlin
// 1. Single callback, suspend
val pipe = GenericOpenAIPipe()
    .setApiKey(...)
    .setModel("gpt-4o")
    .setStreamingCallback { chunk ->
        print(chunk); stdout.flush()
    }
    .init()

val result: MultimodalContent = pipe.execute(MultimodalContent(text = "..."))
// result.text           -> accumulated streamed output
// result.modelReasoning -> captured reasoning (apiMode-dependent)

// 2. Multi-callback via manager
val manager = pipe.obtainStreamingCallbackManager()
manager.addCallback { chunk -> writeToFile(chunk) }   // sibling sink
pipe.setStreamingCallback { chunk -> print(chunk) }     // primary

// 3. Multi-pipe tree (parent sets callback, descendants inherit)
parent.setStreamingCallback { ... }
parent.setReasoningPipe(reasoning)
parent.setValidatorPipe(validator)
// chunks from reasoning AND validator pipes flow to the same sink
// (propagateStreamingCallback walks validator/transformation/branch/reasoning)

// 4. Bedrock fluent
val bedrock = BedrockPipe()
    .setRegion("us-east-1")
    .setModel("anthropic.claude-3-7-sonnet-20250219-v1:0")
    .enableStreaming()                                  // no callback yet
    .setStreamingCallback { chunk -> print(chunk) }     // or
    .enableStreaming({ chunk -> print(chunk) })         // one-shot
```

## Pitfalls

### Chunks arrive as a single batch (Ktor CIO buffering)

Symptom: streaming-enabled GenericOpenAIPipe emits the entire response once at the end, not token-by-token. The fix is already wired: GenericOpenAIPipe routes through `executeStreamingDirect` which bypasses Ktor. If you see this symptom on a **different** provider, check whether that provider has a similar carve-out. If not, you are hitting the Ktor CIO buffering bug — add an `executeStreamingDirect`-style raw socket path. Do NOT try to "fix" `executeStreamingDirect` to use Ktor — the existing comment in `GenericOpenAIPipe.kt:800-810` documents why that doesn't work.

### Reasoning isn't streamed even with streamModelReasoning=true

Two failure modes:
- Wrong apiMode — chat completions don't expose a reasoning channel natively. You need `ApiMode.OpenAIResponses` (OpenAI) or `ApiMode.Anthropic` (Anthropic extended thinking). Chat-completions with `ReasoningConfig` will only carry reasoning in the final non-streaming response.
- Bedrock without flag — `streamModelReasoning` is per-pipe. On `BedrockPipe.kt:4317`, `if (streamModelReasoning) emitStreamingChunk(...)` — if your Bedrock model supports reasoning but reasoning chunks don't arrive, this flag is off.

### Callback fires twice for the same chunk

Two failure modes:
- Same callback registered twice (once via parent `setStreamingCallback`, once via child) — `StreamingCallbackManager.addCallback` dedups by reference equality (`StreamingCallbackManager.kt:47`). If you're using distinct lambdas, dedup misses.
- Two pipes in a tree both stream — that's correct behavior for two separate deltas, not duplication. Confirm by checking each `emitStreamingChunk` source.

### Manager is null at emit time

`emitStreamingChunk` checks `streamingCallbackManager?.emitToAll(chunk)` — null-safe. If no callback is registered, chunks silently disappear. This is by design: providers that don't support streaming emit nothing. To verify a pipe is actually streaming, set a `setStreamingCallback { println("[$it]") }` before execute.

### Disable doesn't clear Bedrock legacy field

`disableStreaming()` clears `streamingCallback` AND `streamingCallbackManager` on BedrockPipe (line 671-676). Other providers only clear the manager. If you're migrating a BedrockPipe to manager-only and seeing stale emissions, the legacy field is the leak source.

## End-of-stream behavior

| Wire format | End signal | Side effects |
|-------------|-----------|--------------|
| HTTP+SSE OpenAI Chat | last `data: { ... finish_reason: "stop" ... }` | `textBuilder.toString()` returned |
| HTTP+SSE OpenAI Responses | `response.completed` event | Captures `usage.inputTokens/outputTokens`, calls `applyResponsesTerminalTextFallback` |
| HTTP+SSE Anthropic | `message_delta` or `message_stop` | `executeStreamingAnthropic` breaks out of loop |
| AWS SDK ConverseStream | `MessageStop` event in collect block | Captures `stopReason`, calls `splitInterleavedReasoning`, returns `MultimodalContent(text, modelReasoning)` |

Failure events throw `P2PException(P2PError.transport, ...)`. The streaming manager's `onError` callback isolates per-callback exceptions — a single throwing callback doesn't kill the stream.

## File index

| File | Role |
|------|------|
| `src/main/kotlin/Pipe/Pipe.kt` | Base pipe, `emitStreamingChunk`, propagation tree |
| `src/main/kotlin/Pipe/StreamingCallbackManager.kt` | Multi-callback fan-out, error isolation, sequential/concurrent modes |
| `src/main/kotlin/Pipe/StreamingCallbackBuilder.kt` | Fluent builder over the manager |
| `src/main/kotlin/Pipe/BinaryContent.kt` | `MultimodalContent` with `text` + `modelReasoning` separation |
| `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt` | 3-mode SSE dispatch, `executeStreamingDirect`, Ktor-CIO bypass |
| `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/SseParser.kt` | OpenAI Chat SSE parser |
| `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/AnthropicStreaming.kt` | Anthropic SSE parser + delta types |
| `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/OpenAIResponsesSseParser.kt` | OpenAI Responses SSE parser + sealed events |
| `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt` | AWS SDK `converseStream` consumer + legacy field |
| `TPipe-Bedrock/src/main/kotlin/bedrockPipe/StreamingTerminal.kt` | One-line terminal-print helper |
| `TPipe-Ollama/src/main/kotlin/ollamaPipe/OllamaPipe.kt` | Ktor channel + NDJSON line iteration |
| `TPipe-OpenRouter/src/main/kotlin/openrouterPipe/` | OpenRouter's GenericOpenAI-clone shape |
