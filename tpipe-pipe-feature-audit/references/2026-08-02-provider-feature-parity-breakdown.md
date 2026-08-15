# Provider parity breakdown — stop reasons, connection drops, errors, tracing
Date: 2026-08-02
Scope: All five `TPipe-*` modules in `/home/cage/Desktop/Workspaces/TPipe/TPipe/`

This is an audit, not a fix. The shape of each provider's lifecycle hookup to TPipe controls is mapped below; gaps are called out where they exist. Companion to `tpipe-pipe-feature-audit/SKILL.md` § "Cross-provider feature parity audit (the COMPARE side)".

---

## TL;DR scorecard

| Module | Stop-reason capture | Connection-drop handling | Error → `P2PException` propagation | Tracing hookup |
|---|---|---|---|---|
| **TPipe-Bedrock** | Full (Invoke + Converse + ConverseStream) | SDK-level only; no manual reconnect | SDK exceptions surface uncaught; PIPE_FAILURE traced but no P2P wrapping | **Full** — `trace()` at every boundary |
| **TPipe-GenericOpenAI** | Full (OpenAI ChatAPI, ResponsesAPI, Anthropic streaming) | Custom: 1-shot retry on `IOException` with 100 ms backoff (`runRequestWithRetry`); client recreated on `abort()` | Full mapping: `HttpRequestTimeoutException`, `SocketTimeoutException`, `ConnectException` → `P2PException(P2PError.transport, …)` | **Full** — `trace()` at every boundary |
| **TPipe-Ollama** | Full (`doneReason` → `metadata["stopReason"]`) | None — bare `HttpClient(CIO)` per call, single-attempt, throws on failure | **None** — `throw e` with no P2P wrap; `IOException`, `SocketTimeoutException` reach callers as raw `Exception` | **Full** — `trace()` at every boundary |
| **TPipe-OpenRouter** | **None** — `finish_reason` is never read from any chunk | None — bare `HttpClient(CIO)`, single-attempt, throws on failure | Partial: `HttpRequestTimeoutException`, `SocketTimeoutException`, `ConnectException` → `P2PException(P2PError.transport, …)`. SSE mid-stream network errors are NOT caught and surface as raw `IOException` from `channel.readUTF8Line()` | **Full** — `trace()` at every boundary |
| **TPipe-MCP** | n/a (no LLM provider) | n/a | n/a | **None** — module does not call `trace()` anywhere. Errors are returned as JSON-RPC error envelopes only |

---

## TPipe-Bedrock — Full

### Stop-reason capture (full)
- `BedrockCallMetadata.kt:34` — `stopReason: String?` typed on the per-call metadata struct
- `BedrockMultimodalPipe.kt:477` — pulls `response.stopReason.value` after a Converse call
- `BedrockPipe.kt:1505-1508` — extracts stop reason from `InvokeModel` response, adds to `responseMetadata["stopReason"]`
- `BedrockPipe.kt:4804, 4956-4959` — ConverseStream `MessageStop` event captures `stopReason?.value` and runs `isMaxTokenStopReason`
- `BedrockPipe.kt:5016-5019` — surfaces the captured value into trace metadata
- `BedrockPipe.kt:5448-5458` — `isMaxTokenStopReason` classifies `end_turn | max_tokens | tool_use | stop_sequence` (max-token overflow detection)
- `BedrockPipe.kt:5485-5498` — `extractStopReasonFromInvokeResponse` knows three wire shapes: GPT-OSS / DeepSeek `choices[0].finish_reason`, Claude `stop_reason`, others `choices[0].finish_reason`

### Connection-drop handling (SDK-level only)
- Uses `aws.sdk.kotlin.services.bedrockruntime.BedrockRuntimeClient` exclusively — TCP/HTTP failure modes are absorbed by the SDK
- `setReadTimeout(timeoutSeconds)` (`BedrockPipe.kt:588-592`) sets the per-request timeout
- No manual retry/reconnect path; SDK raises on transport failure
- Streaming failure (`executeInvokeStream` at `BedrockPipe.kt:5244-5261`) catches and returns `MultimodalContent("")` rather than null — the parent `executeInvokeApi` interprets null as "fall back to non-streaming InvokeModel", which would skip callback fan-out and waste a round-trip. Patch is documented in the catch block.

### Error propagation
- Bedrock SDK exceptions (network, throttling, validation) are caught by per-method `catch(e: Exception)` blocks — `BedrockPipe.kt:797, 804, 845, 909, 1270, 1310, 1349, 1374, 1524, 1531, 1571, 3453, 4596, 5071, 5244, 5284, 5434, 5502, 5557, 5753, 5903` (22+ sites)
- All caught exceptions go through `trace(TraceEventType.API_CALL_FAILURE, …, error = e)` then either re-thrown as-is or returned as `MultimodalContent("")`
- **No `P2PException` wrapping anywhere in the Bedrock module** — the framework's typed-error contract is not honoured for transport failures, max-token overflow, or guardrail failures. Callers that key off `P2PError.transport` / `P2PError.prompt` / etc. will never see those codes from Bedrock.

### Tracing hookup (full)
- `trace(TraceEventType.PIPE_START / PIPE_SUCCESS / PIPE_FAILURE / API_CALL_START / API_CALL_SUCCESS / API_CALL_FAILURE / CONTEXT_TRUNCATE / VALIDATION_FAILURE)` invoked at every method boundary
- 60+ trace call sites in `BedrockPipe.kt` alone; `BedrockMultimodalPipe.kt` adds another 14
- `VALIDATION_FAILURE` events emitted for region/credentials/inference-profile validation (`BedrockPipe.kt:2902-2927`)
- `CONTEXT_TRUNCATE` events emitted at `BedrockPipe.kt:1579, 1825`

---

## TPipe-GenericOpenAI — Full + custom retry

### Stop-reason capture (full)
- Non-streaming: `GenericOpenAIPipe.kt:1211-1212` — `finishReason` and `stopReason` (both bound to `choices[0].finishReason`) flow into trace metadata
- Streaming ChatAPI: `GenericOpenAIPipe.kt:1537-1551` — first non-null `finish_reason` is captured from the terminal chunk into `streamingFinishReason`
- Streaming Anthropic: `env/SseParser.kt:238-243` parses `message_delta` events and emits `AnthropicStreamEvent.MessageDelta(stopReason, usage)`; consumed at `GenericOpenAIPipe.kt:1601`
- Streaming OpenAI Responses: `api/OpenAIResponsesResponseParser.kt:103` derives `finish_reason` from `status` (`completed` → `"stop"`, `incomplete` → `"incomplete"`, refusal → `"refusal"`)
- `streamingFinishReason` is a `var` on the pipe (line 154) with `setStreamingFinishReason()` setter (line 611-614) so the reasoning pipe can seed it before its own turn
- `metadata["streamingFinishReason"]` is emitted at line 1744 alongside `PIPE_SUCCESS`

### Connection-drop handling (custom)
- `GenericOpenAIPipe.kt:2393-2411` — `runRequestWithRetry` wraps the request, retries exactly once on `IOException` after a 100 ms backoff (`RETRY_BACKOFF_MILLIS = 100L` at line 45)
- Catches `SocketTimeoutException`, `EOFException`, `HttpRequestTimeoutException`, `ConnectException` — all are `IOException` subclasses
- Does NOT retry on HTTP error responses, parse failures, or programmer errors
- `abort()` at `GenericOpenAIPipe.kt:826-842` closes and recreates the Ktor `HttpClient` (closing and reusing the same handle triggers `IOException: connection closed` on the next request — bug was previously `httpClient = null` which broke retry; current shape honours `ownsHttpClient` to avoid closing injected test clients)
- The Mantle path (Bedrock-style SigV4) shares the same `createHttpClient()` / `runRequestWithRetry` / `abort()` infrastructure — no separate retry story

### Error propagation (full)
- `HttpRequestTimeoutException` → `P2PException(P2PError.transport, "Request timeout", e)` (`GenericOpenAIPipe.kt:1250`)
- `SocketTimeoutException` → `P2PException(P2PError.transport, "Socket timeout", e)` (`GenericOpenAIPipe.kt:1251`)
- `ConnectException` → `P2PException(P2PError.transport, "Connection failed", e)` (`GenericOpenAIPipe.kt:1252`)
- SSE parser-level errors (`api/OpenAIResponsesSseParser.kt:274`, `api/OpenAIResponseParser.kt:37`) deserialize `GenericOpenAIErrorResponse` envelopes and surface as typed exceptions
- Streaming catch block at `GenericOpenAIPipe.kt:1612` re-throws `IOException` raw — outer catch wraps it via the `when(e)` arm
- `SseParser.kt:310` re-throws `P2PException` explicitly so error codes survive the parser

### Tracing hookup (full)
- 15 trace call sites covering `PIPE_START / PIPE_SUCCESS / PIPE_FAILURE / API_CALL_START / API_CALL_SUCCESS / API_CALL_FAILURE`
- Every error path emits `trace(API_CALL_FAILURE, …, error = e, metadata = { errorType, errorMessage, streaming })`

---

## TPipe-Ollama — Stop-reason + tracing, no error mapping

### Stop-reason capture (full)
- `OllamaPipe.kt:1405` — `extractOllamaMetadata(ChatResponse)` reads `response.doneReason` and writes `metadata["stopReason"]`
- `OllamaPipe.kt:1418-1428` — `extractOllamaMetadata(GeneratedResponse)` covers the legacy `/api/generate` path
- `OllamaPipe.kt:1203` — streaming loop terminates on `chunk.done` (Ollama's wire-level "done" flag, NOT a stop-reason string)

### Connection-drop handling (none)
- Bare `HttpClient(CIO)` allocated per request — `OllamaPipe.kt:910-913, 983, 1114-1120, 1171-1177` (4 separate call sites each create their own client)
- No retry, no reconnect — a single `SocketTimeoutException` or `EOFException` aborts the whole pipe turn
- `connectTimeoutMillis = 30_000`, `socketTimeoutMillis = 600_000` (10 min) for chat/generate; streaming chat is `requestTimeoutMillis = 300_000` (5 min)
- The `finally { client.close() }` pattern ensures no leak, but no recovery

### Error propagation (none)
- `OllamaPipe.kt:817, 877, 955, 1051, 1144, 1219` — six `catch(e: Exception)` blocks
- All six do `trace(API_CALL_FAILURE, error = e)` then `throw e` — no P2P wrapping, no exception type discrimination
- A local Ollama server dying mid-stream surfaces as a raw `IOException` to the parent pipeline; downstream code that expects `P2PException(P2PError.transport, …)` will misclassify it

### Tracing hookup (full)
- 20 trace call sites — `PIPE_START / PIPE_SUCCESS / PIPE_FAILURE / API_CALL_START / API_CALL_SUCCESS / API_CALL_FAILURE`
- `extractOllamaMetadata` populates `inputTokens / outputTokens / totalTokens / totalDuration / loadDuration / promptEvalDuration / evalDuration / apiType` for every successful response

---

## TPipe-OpenRouter — Tracing only

### Stop-reason capture (NONE)
- `search_files` for `finish_reason | stop_reason | finishReason | stopReason` against the entire `TPipe-OpenRouter` module: **0 matches**
- The streaming method at `OpenRouterPipe.kt:765-829` calls `SseParser.parseChunk` → `SseParser.extractContent` and breaks on `SseParser.SseLine.Done` — `choices[0].finish_reason` is never read
- Non-streaming path at `OpenRouterPipe.kt:715-737` deserializes `OpenRouterChatResponse` and pulls `choices[0].message.content` but never reads `finish_reason`
- Consequence: a model that hits `finish_reason: "length"` (truncation) is indistinguishable from `finish_reason: "stop"`; max-token overflow detection does not exist for OpenRouter

### Connection-drop handling (none)
- `OpenRouterPipe.kt:556-564` — single `HttpClient(CIO)` allocated in `init()` and held for the pipe's lifetime
- `HttpTimeout` installed with `requestTimeoutMillis = 120_000 / connectTimeoutMillis = 30_000 / socketTimeoutMillis = 120_000`
- No retry; no reconnect; no streaming-error recovery
- `abort()` at `OpenRouterPipe.kt:575-584` closes and nulls the client — like the OLD GenericOpenAI bug at `BedrockPipe.kt:1351`, this leaves the pipe with `httpClient = null` and the next call throws `IllegalStateException("OpenRouterPipe not initialized. Call init() first.")`

### Error propagation (partial)
- `OpenRouterPipe.kt:750-756` — `HttpRequestTimeoutException / SocketTimeoutException / ConnectException` → `P2PException(P2PError.transport, …)`
- HTTP error envelope parsing at `OpenRouterPipe.kt:699-712` maps `auth_error / rate_limit_error / invalid_request_error / invalid_api_key / api_error / server_error` and HTTP codes 400/401/429/5xx to P2P error codes
- Streaming SSE error events at `OpenRouterPipe.kt:790-802` mirror the same mapping for in-band errors
- **Gap:** mid-stream `IOException` from `channel.readUTF8Line()` is NOT caught in `executeStreaming` — only the outer `try { … } catch(e: Exception)` at `generateText:606` catches it. SSE streaming network blips surface as raw `IOException`, not `P2PException`

### Tracing hookup (full)
- 8 trace call sites covering init, exec, streaming, and abort
- `PIPE_FAILURE` is emitted in `abort()` at `OpenRouterPipe.kt:577` regardless of whether abort was intentional or a forced shutdown — caller can't distinguish "I asked to abort" from "the framework aborted me"

---

## TPipe-MCP — Not a provider; no trace hookup

- Module is the bridge (converts MCP manifests to PCP options, hosts the stdio/HTTP server). It does not call LLM APIs.
- `search_files` for `trace | TraceEvent | TracePhase` across `TPipe-MCP`: **0 matches**
- Errors propagate via JSON-RPC error envelopes (`Models/JsonRpcModels.kt`) — TPipe's `trace()` is never called

If you want MCP tool executions to show up in TPipe traces, that's a separate wiring job (would need `PcpExecutionDispatcher` to emit `PIPE_START / PIPE_SUCCESS / PIPE_FAILURE` per dispatched tool call). For the purpose of the cross-provider parity scorecard, exclude MCP — see the "MCP is a bridge, not a provider" pitfall in the parent skill.

---

## Connection-drop & error-mapping parity matrix

| Failure mode | Bedrock | GenericOpenAI | Ollama | OpenRouter |
|---|---|---|---|---|
| TCP connect refused / DNS failure | SDK → caught at outer, `API_CALL_FAILURE` trace, no P2P wrap | `ConnectException` → `P2PException(transport)` | Caught, rethrown raw | `ConnectException` → `P2PException(transport)` |
| Socket timeout | SDK → outer catch, no P2P wrap | `SocketTimeoutException` → `P2PException(transport)` | Caught, rethrown raw | `SocketTimeoutException` → `P2PException(transport)` |
| HTTP request timeout | SDK → outer catch, no P2P wrap | `HttpRequestTimeoutException` → `P2PException(transport)` | Caught, rethrown raw | `HttpRequestTimeoutException` → `P2PException(transport)` |
| SSE mid-stream drop | SDK raises on `body.collect { }`, outer catch, `MultimodalContent("")` (no re-call) | Caught by `runRequestWithRetry` (1 retry) or raw rethrow | Caught, rethrown raw | NOT caught in `executeStreaming` — raw `IOException` from `readUTF8Line()` |
| HTTP 4xx/5xx error envelope | SDK exception, outer catch, no P2P wrap | `GenericOpenAIErrorResponse` parsed → `P2PException(auth/prompt/transport)` | None — only deserialization succeeds or throws | `OpenRouterErrorResponse` parsed → `P2PException(auth/prompt/transport)` |
| Stop reason `max_tokens` | `isMaxTokenStopReason` → `API_CALL_FAILURE` trace + `MultimodalContent("")` | `streamingFinishReason` → metadata only, no overflow action | `doneReason` → metadata only, no overflow action | **Not captured at all** |
| Stop reason `tool_use` / `stop_sequence` | Captured, surfaced in metadata | Captured, surfaced in metadata | `doneReason` → metadata | **Not captured** |
| Auth failure (401) | SDK exception, outer catch | `P2PException(auth)` | None — raw exception | `P2PException(auth)` |
| Rate limit (429) | SDK exception, outer catch | HTTP error envelope → `P2PException(transport)` | None | `P2PException(transport)` |
| Abort (intentional) | `abort()` → `PIPE_FAILURE` trace | `abort()` → closes+recreates client, `PIPE_FAILURE` trace | Not surfaced; pipe re-init only | `abort()` → closes+nulls client, `PIPE_FAILURE` trace |

---

## Parity gaps worth raising

1. **Bedrock has no `P2PException` mapping at all** — every error path is a rethrow-as-is. Operators that key off `P2PError.transport / auth / prompt / rateLimit / json` get `null` from Bedrock and have to inspect the raw exception type.
2. **OpenRouter does not capture `finish_reason`** at all — cannot distinguish natural stop from `length` truncation. The `executeStreaming` method only reads `DONE` and `error` events from `SseParser`.
3. **OpenRouter `abort()` nulls the HTTP client** — same shape as the previously-fixed GenericOpenAI bug (`BEDROCK_PIPE_GENERICOPENAI_ABORT_NULLS_HTTPCLIENT.md` per the comment at `GenericOpenAIPipe.kt:823`). Next `generateText` after abort throws `IllegalStateException("OpenRouterPipe not initialized")` even though the pipe WAS initialized.
4. **Ollama does no error mapping and no retry** — six catch blocks all `throw e`. A flaky local Ollama server will surface raw `IOException`/`SocketTimeoutException` to parent pipelines that expect `P2PException`.
5. **GenericOpenAI retry is one-shot, no exponential backoff** — fixed 100 ms. For Mantle mid-stream blips this is sufficient; for longer outages the second attempt will hit the same wall.
6. **Bedrock streaming-error returns `MultimodalContent("")` rather than throwing** — intentional, to avoid the parent dispatcher's null-interpreted-as-retry fallback. But it means callers that branch on "did the model return text or empty" can't tell streaming failure from "model said nothing."
7. **TPipe-MCP emits zero trace events** — out of scope as a "provider" but means tool executions are invisible in TPipe traces.

---

## File:line reference index

- Bedrock stop reason: `BedrockPipe.kt:1505-1508, 3194-3195, 4509-4510, 4804, 4956-4959, 5016-5019, 5448-5458, 5485-5498`
- Bedrock streaming-error recovery: `BedrockPipe.kt:5244-5261`
- Bedrock client error site count: 22 `catch(e: Exception)` blocks
- GenericOpenAI retry: `GenericOpenAIPipe.kt:2393-2411`
- GenericOpenAI abort+recreate: `GenericOpenAIPipe.kt:826-842`
- GenericOpenAI error mapping: `GenericOpenAIPipe.kt:1250-1254`
- GenericOpenAI streaming finish_reason: `GenericOpenAIPipe.kt:1537-1551, 1601`
- GenericOpenAI Responses finish_reason: `api/OpenAIResponsesResponseParser.kt:103, 189-194`
- GenericOpenAI Anthropic stop_reason: `env/SseParser.kt:238-243`, `api/AnthropicResponseParser.kt:61`
- Ollama stop reason: `OllamaPipe.kt:1405, 1203`
- Ollama catch sites (no mapping): `OllamaPipe.kt:817, 877, 955, 1051, 1144, 1219`
- OpenRouter error mapping (partial): `OpenRouterPipe.kt:699-712, 750-756, 790-802`
- OpenRouter abort nulls client: `OpenRouterPipe.kt:575-584`
- OpenRouter streaming: `OpenRouterPipe.kt:765-829`
- OpenRouter stop-reason capture: NONE
- MCP trace hookup: NONE