# PCP Pipe-side wiring — `Pipe.setSystemPrompt` → `processPcpResponse` → `PcpExecutionDispatcher`

The umbrella SKILL.md covers the executor half of PCP (sandboxes, security managers, output capture). This reference covers the other half: how a `Pipe` exposes PCP to the LLM, parses the LLM response back into `PcPRequest`s, and feeds the dispatcher.

Module locators:
- `Pipe/Pipe.kt:2131-2260` — `setSystemPrompt` (the three-mode injection block)
- `Pipe/Pipe.kt:4891-4919` — `processPcpResponse` (LLM text → dispatcher)
- `Pipe/Pipe.kt:4891-4919` — `pcpDispatcher` field (one per pipe)
- `PipeContextProtocol/Pcp.kt:500-514` — `PcPRequest` wire shape
- `PipeContextProtocol/PcpResponseParser.kt` — `extractPcpRequests` / `validatePcpRequest` / `determineTransport`
- `PipeContextProtocol/PcpRegistry.kt` — global-context singleton for standalone PCP services

## The wire shape the LLM emits

`PcPRequest` (`Pcp.kt:500-514`) carries exactly one of the six transport context-options populated, plus the universal `argumentsOrFunctionParams` and `callParams`:

```kotlin
data class PcPRequest(
    var stdioContextOptions: StdioContextOptions = …,
    var tPipeContextOptions: TPipeContextOptions = …,
    var httpContextOptions: HttpContextOptions = …,
    var pythonContextOptions: PythonContext = …,
    var kotlinContextOptions: KotlinContext = …,
    var javascriptContextOptions: JavaScriptContext = …,
    var argumentsOrFunctionParams: List<String> = emptyList(),  // positional args
    var callParams: Map<String, String> = emptyMap()             // named args (preferred)
)
```

The LLM is taught to return an **array** of these — `PcPRequestList` is the deserialization root. Three fields matter by precedence:

- `callParams` (named) — preferred path. The `PcpFunctionHandler.convertArgumentsToParameters` zip-merges `callParams` *over* positional arguments (`PcpFunctionHandler.kt:178-181`).
- `argumentsOrFunctionParams` (positional) — zipped onto `signature.parameters[*].name` in order.
- `params` — **not an argument bag**. It's a description of the function's expected parameters used in the prompt schema. The prompt explicitly forbids putting values in `params`.

## `setSystemPrompt` — three modes

`Pipe.setSystemPrompt` (`Pipe.kt:2131`) detects mode via two booleans:

```kotlin
val hasPcpTools = !pcpContext.tpipeOptions.isEmpty() ||
                  !pcpContext.httpOptions.isEmpty() ||
                  !pcpContext.stdioOptions.isEmpty() ||
                  pcpContext.pythonOptions.availablePackages.isNotEmpty()

val hasJsonOutput = !this.supportsNativeJson && jsonOutput.isNotEmpty()
val useMergedMode = hasPcpTools && hasJsonOutput
```

| Mode | Condition | Appended to system prompt |
|---|---|---|
| **Merged** | `hasPcpTools && hasJsonOutput` | JSON-output schema + PCP tool list + `[{PcPRequest}]` template |
| **PCP-only** | `hasPcpTools && !hasJsonOutput` | PCP tool list + `[{PcPRequest}]` template only |
| **JSON-only** | `!hasPcpTools && hasJsonOutput` | JSON-output schema only |
| **None** | Neither | (no injection) |

The PCP block (`Pipe.kt:2197-2221`) teaches the model the four rules it must follow when emitting tool calls:

1. The serialized `PcpContext` describes each available tool — only those names are callable.
2. Tool calls are an **array** of `PcPRequest` JSON.
3. For `Tpipe` calls, arguments go in `callParams` (preferred) or `argumentsOrFunctionParams` (positional); never in `params`.
4. Each transport's context-options object is named: `stdioContextOptions`, `httpContextOptions`, `pythonContextOptions`, `kotlinContextOptions`, `javascriptContextOptions`.

The injection only re-runs when `setSystemPrompt` is called again. Most setters that touch `pcpContext` (e.g. `setPcpContext`, `setTools` on the provider, `addAgentRequestSettings`) require a follow-up `setSystemPrompt` / `applySystemPrompt` to refresh the prompt.

**Note**: `hasPcpTools` does NOT check `kotlinOptions` or `javascriptOptions` — only `tpipeOptions`, `httpOptions`, `stdioOptions`, and `pythonOptions.availablePackages`. If a pipe is configured exclusively for Kotlin or JavaScript execution, the prompt block will not be appended and the LLM will not know tool calls are available. Mode-detection gap.

## `processPcpResponse` — LLM text → `PcpExecutionResult`

`Pipe.processPcpResponse(llmResponse)` (`Pipe.kt:4891-4919`):

```kotlin
val parser = PcpResponseParser()
val parseResult = parser.extractPcpRequests(llmResponse)

if (!parseResult.success) { /* surface errors */ }

pcpDispatcher.executeRequests(parseResult.requests, pcpContext)
```

`PcpResponseParser.extractPcpRequests` (`PcpResponseParser.kt:40-97`):

1. Try `extractJson<PcPRequest>(llmResponse)` first — looks for a single object.
2. Fall back to `extractJson<List<PcPRequest>>(llmResponse)` — array of objects.
3. Each candidate is `validatePcpRequest`'d before being added to the result list.
4. Parser uses `com.TTT.Util.extractJson` which auto-repairs malformed JSON (trailing commas, unquoted keys, etc.) — partial recovery is the norm, not the exception.

`validatePcpRequest` (`PcpResponseParser.kt:106-175`) checks transport-specific required fields:

| Transport | Required field |
|---|---|
| `Tpipe` | `tPipeContextOptions.functionName` non-empty |
| `Stdio` | `stdioContextOptions.command` non-empty |
| `Http` | `httpContextOptions.baseUrl` non-empty |
| `Python` | `argumentsOrFunctionParams` non-empty (script body) |
| `Kotlin` | `argumentsOrFunctionParams` non-empty (script body) |
| `JavaScript` | `argumentsOrFunctionParams` non-empty (script body) |

`determineTransport` (`PcpResponseParser.kt:183-217`) — first-match by populated options, then a regex heuristic on the first script line for code-execution transports:

- Python — `^(import|from|def|class)\s+` or `print(`
- Kotlin — `^(import|val|var|fun|package)\s+` or `println(`
- JavaScript — `^(const|let|var|function|import|require)\s+` or `console.log(`
- Fallback `Transport.Unknown` — request is rejected.

The dispatcher's `executeRequests` fans out via `coroutineScope { requests.map { async { … } } }` and aggregates into `PcpExecutionResult(success, results, executionTimeMs, errors)`. The pipe then re-injects the results into the conversation (typically as a user-role follow-up turn carrying the serialized `PcpExecutionResult`).

## `PcpRegistry` — global access for standalone PCP services

Outside a `Pipe`, the same dispatcher is reachable via `PcpRegistry` (`PcpRegistry.kt`):

```kotlin
PcpRegistry.globalContext = PcpContext().apply { /* addStdioOption / addTPipeOption / addHttpOption */ }
val result = PcpRegistry.executeRequests(listOf(req))         // or pass a per-call context
```

- Singleton with a `Mutex` around every dispatch — `globalContext` is `@Volatile`.
- `executeRequests(requests, context)` overload accepts a per-call context, so a hosted PCP service can isolate sessions while sharing the registry.
- Used by the MCP server (so an external MCP host can call TPipe-bound functions) and by any standalone PCP service exposed over HTTP / stdio.

## Known gaps in the Pipe wiring (research notes)

These are concrete enough to be durable patterns, not session-specific observations:

1. **`StdioExecutor.executeSecure` does not route through `SubprocessOutputCapture`.** `StdioExecutor.kt:396-397` uses `process.inputStream.bufferedReader().readText()` then `process.errorStream.bufferedReader().readText()` sequentially — the historical deadlock pattern past ~64KB stdout. The same applies to the INTERACTIVE / CONNECT / BUFFER_REPLAY paths. The pipe-side output capture contract is documented but the Stdio one-shot path is the gap.

2. **`StdioExecutor` does not use `PcpThreadPool`.** Every `executeSecure` is its own `ProcessBuilder.start()` on the calling coroutine. Stdio currently has no concurrency bound — pipe-level concurrency is the only ceiling. Python and JavaScript executors route through `PcpThreadPool` (`PcpThreadPool.create()`); Stdio's constructor is `class StdioExecutor : PcpExecutor` with no executor parameter.

3. **No outer `withTimeoutOrNull` for the Kotlin executor leak.** `KotlinExecutor` documents the leak (`engine.eval()` is uninterruptible — daemon thread survives until JVM exit). The remedy called out in the source comment is "wrap the dispatcher's coroutine in an outer `withTimeoutOrNull` at the pipe/manifold layer." `processPcpResponse` does not have that wrapper. For untrusted Kotlin scripts, the timeout is cosmetic at the dispatch level and the leak persists.

4. **`hasPcpTools` mode detection does not include Kotlin or JavaScript options.** A pipe configured with only `kotlinOptions` or `javascriptOptions` populated will not trigger PCP prompt injection — the LLM will not know tool calls are available. Fix is to extend the `hasPcpTools` predicate at `Pipe.kt:2137-2140`.

5. **Stdio path-only configs don't trip `hasPcpTools`.** `setSystemPrompt` is gated on `stdioOptions`, not on the four path/file restriction lists. If a pipe is configured only via the four lists (no `stdioOptions` entries), the LLM-side block will not be appended.

## Anti-patterns anchored to this layer

1. **Never edit `pcpContext` after `setSystemPrompt` without re-calling `setSystemPrompt`.** The serialized PCP block is built once at injection time. Adding a function or stdio option after the prompt is frozen produces a desync where the LLM sees one set and the dispatcher validates against another.
2. **Never hand-construct `PcPRequest` JSON outside the `PcpResponseParser` repair path.** The parser handles malformed JSON, transport detection, and per-transport validation. Raw `Json.decodeFromString` skips all three.
3. **Never put argument values inside the `params` field of a PCP request.** The schema treats `params` as a description, not a value bag. Use `callParams` or `argumentsOrFunctionParams`.
4. **Never share `PcpRegistry.globalContext` across untrusted sessions without per-call context overrides.** Use the `executeRequests(requests, context)` overload to inject per-session isolation.
5. **Never assume `hasPcpTools == true` means the LLM can call every transport.** The prompt block lists each transport's available options — if a transport has no entries in the context, the LLM cannot call it (the dispatcher will reject the request with "not in security whitelist").
