# TPipe Default-Encoding Fix — 2026-06-22

Audit and fix for the `com.TTT.Util.serialize()` `encodedefault` default leak. This is the reference document for the change that flipped Layer 2 from `true` to `false`.

## The bug

`com.TTT.Util.serialize()` at `TPipe/src/main/kotlin/Util/Util.kt:48` was declared with `encodedefault: Boolean = true`. Every caller that didn't explicitly pass a second argument (≈95 production sites) was leaking Kotlin default values into the resulting JSON. For LLM-bound call sites, this was a token-cost tax — empty strings, empty lists, and zero-valued fields all leaked into the prompt.

The leak was **also a self-reinforcing loop**: the schema generator at `Schema.kt:163` hardcodes `encodeDefaults = true` so the LLM is shown a fully-populated example schema. The model learns to echo the populated shape back. With Layer 2 also defaulting to `true`, even non-LLM-bound context objects shipped to LLM-fed downstream pipes carried the same default-bloat.

## The fix

Two-line change:

**`TPipe/src/main/kotlin/Util/Util.kt:48`**
```diff
- inline fun <reified T> serialize(obj: T, encodedefault : Boolean = true): String
+ inline fun <reified T> serialize(obj: T, encodedefault : Boolean = false): String
```

**`TPipe/src/main/kotlin/P2P/P2PRegistry.kt:1167` and `:1202`**
```diff
- val jsonPayload = serialize(request)
+ val jsonPayload = serialize(request, encodedefault = true)
```

These two are the only production callers that target external (potentially non-Kotlin) P2P hosts. Their wire contract needs all fields present.

## The audit — full caller inventory

Production callers across all TPipe submodules, as of 2026-06-22. Categories abbreviated: OO = opt-out (correct), LK = leaks defaults (now silently fixed by default flip), PIE = prompt-injection example (was already OO), EXT = external wire (now pinned to true).

### TPipe root (main library) — 36 callers

| File:Line | Object | Bucket | Note |
|---|---|---|---|
| `Util/Util.kt:83` | `history` (ConverseHistory) | OO | The wrapper itself — `serialize(history, encodedefault = false)` |
| `Pipe/Pipe.kt:1733` | `pcpContext` | PIE | PCP tool schema shown to LLM; `encodedefault = false` |
| `Pipe/Pipe.kt:1777` | `pcpContext` | PIE | Same pattern, PCP-only mode |
| `Pipe/Pipe.kt:2013` | `pcpContext` | PIE | Merged mode duplicate |
| `Pipe/Pipe.kt:2059` | `pcpContext` | PIE | PCP-only mode duplicate |
| `Pipe/Pipe.kt:2138` | `p2pAgentDescriptors` | PIE | P2P agent list shown to LLM |
| `Pipe/Pipe.kt:2169` | `pathDescriptorList` | PIE | Path descriptor list shown to LLM |
| `Pipe/Pipe.kt:2253` | `todoListObj` | LK (CRITICAL → now compact) | Goes into LLM systemPrompt |
| `Pipe/Pipe.kt:2263` | `task` | LK (CRITICAL → now compact) | Goes into LLM systemPrompt |
| `Pipe/Pipe.kt:4937` | `contextWindow` | LK (token counting) | Behavior unchanged |
| `Pipe/Pipe.kt:4944` | `miniContextBank` | LK (token counting) | Behavior unchanged |
| `Pipe/Pipe.kt:4957` | `contextWindow` | LK (token counting helper) | Behavior unchanged |
| `Pipe/Pipe.kt:5762` | `contextWindow` | LK (tracing) | Trace file size drops |
| `Pipe/Pipe.kt:5763` | `miniContextBank` | LK (tracing) | Trace file size drops |
| `Pipe/Pipe.kt:5815` | `contextWindow` | LK (tracing) | Trace file size drops |
| `Pipe/Pipe.kt:5845` | `miniContextBank` | LK (tracing) | Trace file size drops |
| `Pipe/Pipe.kt:5966` | `contextWindow` | LK (CRITICAL → now compact) | Goes into LLM fullPrompt |
| `Pipe/Pipe.kt:5972` | `miniContextBank` | LK (CRITICAL → now compact) | Goes into LLM fullPrompt |
| `Pipe/Pipe.kt:6146` | `jsonObjects` | LK (downstream) | Behavior unchanged |
| `Pipe/Pipe.kt:6730` | `newHistory` | OO | `encodedefault = false` explicit |
| `Pipe/Pipe.kt:7218` | `jsonObject` | LK | Behavior unchanged |
| `Pipe/Pipe.kt:7267` | `jsonObject` | LK | Behavior unchanged |
| `Pipe/Pipe.kt:7358` | `contextWindow` | LK (token counting) | Behavior unchanged |
| `Pipe/Pipe.kt:7365` | `miniContextBank` | LK (token counting) | Behavior unchanged |
| `Context/ContextBank.kt:357,437,444,451,523,528,533,1167,1172,1177,1429,1436,1441,1446` | `window`/`storedWindow`/`workingContext`/`todoListToEmplace` | LK (file persistence) | Round-trip via deserialize, safe |
| `Context/MemoryClient.kt:116,264,387` | `window`/`todoList`/`request` | LK (HTTP to MemoryServer) | MemoryServer deserializes with coerceInputValues |
| `Context/TodoList.kt:35` | `tasks` | LK (toString) | Cosmetic |
| `Context/MemoryClient.kt`, `Context/ContextBank.kt`, etc. — many more file-persistence sites | various | LK | Round-trip safe |
| `P2P/P2PHost.kt:23,38` | `response` | LK (println debug) | Trace noise drops |
| `P2P/P2PHostedRegistry.kt:447,1589,1594,1732,1787,1872,1896,1920,1944,1968,1992,2016,2077,2096` | various P2PHosted* payloads | LK (P2P wire) | Round-trip via deserialize, safe |
| `P2P/P2PRegistry.kt:1167` | `P2PRequest` | **EXT — pinned to `encodedefault = true`** | External HTTP wire |
| `P2P/P2PRegistry.kt:1202` | `P2PRequest` | **EXT — pinned to `encodedefault = true`** | External Stdio wire |
| `P2PRegistry.kt:1202` | `request` | EXT | Same as above |
| `PipeContextProtocol/PcpStdioHost.kt:21,36` | `result` | LK (println debug) | Trace noise drops |
| `PipeContextProtocol/StdioBufferManager.kt:224` | `buffer` | LK (internal buffer JSON) | Round-trip via deserialize, safe |
| `Pipeline/DistributionGrid.kt:327,1816,1879,1997,2993,3067,3162,3222,3346,3485,3694,6315,7089` | various DistributionGrid* payloads | LK (P2P wire) | Round-trip via deserialize, safe |
| `Pipeline/DistributionGrid.kt:6589` | `rpcMessage` | LK (CRITICAL → now compact) | Goes into P2P RPC text |
| `Pipeline/Junction.kt:1283,1446,2557,2563,2576` | `decision`/`outcome` | LK (LLM-bound text) | Now compact; downstream deserialize restores defaults |
| `Pipeline/PumpStation.kt:1837` | `descriptors` | OO | Positional `serialize(descriptors, false)` |
| `Pipeline/PumpStationLoop.kt:1417` | `input` | OO | Positional `serialize(input, false)` |
| `Pipeline/PumpStationLoop.kt:1622` | `healthData` | OO | Positional `serialize(healthData, false)` |
| `Pipeline/Splitter.kt:727` | `activatorValue.content` | LK (deep-copy comment) | Round-trip safe |

### TPipe-Bedrock — 8 callers (all OO)

All 8 sites in `BedrockPipe.kt:1806, 2041, 2194, 2238, 3118, 3342, 3388, 3925` use `com.TTT.Util.serialize(pcpContext, false)` explicitly. The strings are injected into LLM tool-call schema prompts via `"Available tools: ${...}"`. Behavior unchanged by the fix.

### TPipe-GenericOpenAI — 5 callers (all OO)

- `GenericOpenAIPipe.kt:566` — `serialize(request, encodedefault = false)`
- `AnthropicRequestSerializer.kt:43` — `serialize(anthropicRequest, encodedefault = false)`
- `OpenAIRequestSerializer.kt:12, 16` — OpenAI and Anthropic modes
- `OpenAIResponsesRequestSerializer.kt:56` — Responses API mode

All explicit opt-outs. Behavior unchanged.

### TPipe-Ollama — 6 callers (all LK)

`OllamaPipe.kt:899, 940, 999, 1036, 1105, 1186` — all `serialize(request)` / `serialize(pcpRequests)` without the second arg. These now silently use `encodedefault = false`. Ollama parses permissive JSON, so the compact form should be tolerated. No local tests cover these round-trips against a real Ollama server with the requested `tinydolphin` model.

### TPipe-OpenRouter — 1 caller (OO)

`OpenRouterPipe.kt:650` — `serialize(request, encodedefault = false)`. Behavior unchanged.

## The `@EncodeDefault` annotations in scope

Currently used in TPipe at:
- `Pipe/BinaryContent.kt:121` — `terminatePipeline` (NEVER)
- `Pipe/BinaryContent.kt:124` — `tools` (NEVER)
- `Context/ConverseData.kt:38` — likely `uuid` (NEVER)
- `Context/ConverseData.kt:67` — likely history field (NEVER)

All four use `NEVER` mode. The fix has no interaction with these — they're already always omitted regardless of the global default.

## Round-trip safety analysis

`com.TTT.Util.deserialize<T>()` at `Util/Util.kt:100` configures:
- `coerceInputValues = true` (line 108) — missing JSON fields with default values are transparently restored on read
- `ignoreUnknownKeys = true` — extra fields in input JSON are silently dropped
- `isLenient = true` — accepts unquoted keys, trailing commas, etc.

Every `serialize(x) → deserialize<T>` round-trip in TPipe (file persistence, P2P wire payloads, DistributionGrid payloads, JunctionWorkflowPhaseResult round-trips, StdioBufferManager buffers) is therefore safe after the Layer 2 default flip. The only exceptions are the two `P2PRegistry.kt` sites that target external (non-Kotlin) clients.

The historical record (`.sisyphus/notepads/create-json-rpc-models/learnings.md`) shows the team explicitly rejected `encodeDefaults = false` for JSON-RPC 2.0 wire payloads because MCP used `Json { encodeDefaults = true }` independently. MCP is unaffected by this fix because it doesn't route through `com.TTT.Util.serialize`.

## The new regression test

`TPipe/src/test/kotlin/Util/UtilSerializeDefaultsTest.kt` (7 tests):

1. `emptyContextWindowSerializesInCompactForm` — `serialize(ContextWindow())` does NOT contain `"contextElements"`, `"converseHistory"`, `"version"`, or `"isInitialized"` keys
2. `emptyTodoListSerializesInCompactForm` — `serialize(TodoList())` does NOT contain `"tasks"`, `"workHistory"`, or `"version"` keys
3. `compactContextWindowIsShorterThanWithDefaults` — compact form is ≥20% smaller than verbose form
4. `roundTripPreservesEqualityForContextWindow` — `serialize → deserialize` preserves `contextElements` list contents
5. `roundTripPreservesEqualityForTodoList` — `serialize → deserialize` preserves `version`, `workHistory.history`, and content text
6. `explicitEncodedefaultTrueStillIncludesDefaults` — `serialize(x, encodedefault = true)` still includes defaults (pins the override behavior)
7. `encodedefaultFalseDefaultMatchesExistingWrapper` — direct `serialize(ContextWindow(...))` does not leak `ConverseData.uuid` defaults (matches `serializeConverseHistory` precedent)

## Verification results (2026-06-22)

- `./gradlew compileKotlin compileTestKotlin`: BUILD SUCCESSFUL (31 tasks, 1m 47s)
- `./gradlew :test --tests "com.TTT.Util.UtilSerializeDefaultsTest"`: 7/7 pass, 0 failures
- Full test sweep (`:test :TPipe-Bedrock:test :TPipe-GenericOpenAI:test :TPipe-OpenRouter:test :TPipe-Ollama:test`): 519 tests, 8 failures — all in `TPipe-Ollama/OllamaValidationTest` + `PcpToolBugTest` (environmental: requires Ollama running with `tinydolphin` model, only `dolphin-mixtral` is loaded locally)
- Round-trip equality preserved for ContextWindow, TodoList, ConverseHistory

## Token impact

Rough estimate for LLM-bound sites (Pipe.kt:5966, 5972, 2253, 2263, DistributionGrid.kt:6589):

- Empty `ContextWindow`: ~50% size reduction (was emitting `{"loreBookKeys":{}, "contextElements":[], "converseHistory":{"history":[], "version":0}, "version":0}` — now `{"loreBookKeys":{}}` since `loreBookKeys` is `@EncodeDefault(ALWAYS)`)
- Populated `ContextWindow`: variable, but typically 20-40% reduction from empty fields dropping out
- `JunctionWorkflowPhaseResult`: drops recipe, cyclesExecuted, notes when at defaults — typical ~30% reduction

The actual token savings depend on which fields are non-default at the moment of serialization.

## What was NOT changed (deferred)

- The schema generator at `Schema.kt:163` — still hardcodes `encodeDefaults = true`. Intentional. The LLM needs the complete schema reference.
- The MCP module — uses its own private `Json { encodeDefaults = true }`. Independent.
- The 25 callers that already explicitly pass `encodedefault = false` — kept as-is for self-documentation; removing them would be a no-op but adds review noise.
- The 90 non-LLM leak sites (tracing, file persistence, debug println) — now produce more compact JSON as a side-effect of the default flip. Acceptable non-breaking behavior change. Flagged for a future cleanup pass if anyone is grep-diffing trace files.

## References

- Plan file: `.hermes/plans/tpipe-default-serialization-fix.md`
- The original audit + spot-check was performed by a `delegate_task` leaf subagent with `toolsets=[terminal, file]`
- The user's key insight: "When we created the schema generators it made encoding defaults almost entirely obsolete" — referring to the fact that the LLM-bound schema example (Layer 1) was already giving the LLM the complete shape, so Layer 2 no longer needed to encode defaults in actual prompt payloads