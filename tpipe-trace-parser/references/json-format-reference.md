# JSON Trace Format Reference

TPipe trace JSON files are `List[TraceEvent]` serialized by kotlinx-serialization + a custom `MapAnySerializer`. This reference covers what the parser must handle, what's lossy, and what's preserved.

## Top-level shape

```json
[
    {
        "id": "trace-event-1047",
        "timestamp": 1784845644440,
        "pipeId": "fa199aca-9d97-41ae-a0f2-20d8dc4314f5",
        "pipeName": "reversal-pipe",
        "eventType": "API_CALL_SUCCESS",
        "phase": "EXECUTION",
        "content": { "text": "...", "binaryContent": [...] } | null,
        "contextSnapshot": { ... } | null,
        "metadata": { ... }
    },
    ...
]
```

Some test runners wrap the array in an envelope:
```json
{ "events": [...], "metadata": { ... } }
```

The parser handles both — see `parse_json_trace.py:parse_json`.

## Field-by-field

### `id`

`trace-event-{counter}` where `{counter}` is a process-global Long incremented under no synchronization. Multi-threaded emit can produce duplicate IDs; this is a known PipeTracer issue (`Debug/PipeTracer.kt:32`). Don't trust uniqueness.

### `timestamp`

Unix epoch milliseconds (`System.currentTimeMillis()`).

### `pipeId`

A string identifier for the pipeline or path. Often a UUID; sometimes a stable name.

### `pipeName`

A human-readable identifier. Examples: `judge`, `dispatch`, `gather`, `report`, `PumpStation`, `Splitter-2keys`. This is what you group by for per-pipe aggregation.

### `eventType`

One of 230+ values from `Debug/TraceEventType.kt`. Organized in families:

- Pipe: `PIPE_START`, `PIPE_END`, `PIPE_SUCCESS`, `PIPE_FAILURE`, `PIPE_TIMEOUT`, `PIPE_RETRY`, `CONTEXT_PULL`, `CONTEXT_TRUNCATE`, `CONTEXT_PREPARED`, `PRE_INVOKE`, `POST_GENERATE`, `VALIDATION_*`, `TRANSFORMATION_*`, `API_CALL_*`, `BRANCH_PIPE_TRIGGERED`, `PIPELINE_TERMINATION`
- Manifold: `MANIFOLD_*`, `MANAGER_*`, `TASK_*`, `AGENT_*`, `P2P_REQUEST_*`
- PumpStation: `PUMP_STATION_*` (50+ events; the largest family)
- Junction: `JUNCTION_*`
- Splitter: `SPLITTER_*`
- DistributionGrid: `DISTRIBUTION_GRID_*`
- KillSwitch: `KILLSWITCH_CHECK`, `KILLSWITCH_TRIPPED`

### `phase`

One of 14 from `Debug/TracePhase.kt`:

```
INITIALIZATION, CONTEXT_PREPARATION, PRE_VALIDATION, EXECUTION, POST_PROCESSING,
VALIDATION, TRANSFORMATION, CLEANUP, MONITORING, ERROR,
ORCHESTRATION, AGENT_COMMUNICATION, TASK_MANAGEMENT, P2P_TRANSPORT  (Manifold-only)
```

### `content`

A `MultimodalContent` object or `null`. Shape:

```json
{
    "text": "...",
    "modelReasoning": "...",
    "binaryContent": [...],
    "useSnapshot": false,
    "context": { ... ContextWindow ... },
    "pipeError": null,
    "tools": { ... PcPRequest ... },
    ...
}
```

`binaryContent` and `tools` can be large nested objects. Use `simplify_event(max_content_str=N)` to truncate when serializing.

### `contextSnapshot`

A `ContextWindow` object or `null`. Contains the full conversation history at the moment of the event. Often large (10-100KB). Default-skip in summary output.

### `metadata`

A `Map<String, Any>` serialized by `MapAnySerializer`. **This is where tokens, request details, and per-event context live.** See the metadata section below.

### `error`

**NOT serialized.** `@Transient val error: Throwable? = null` is excluded by kotlinx-serialization. If a producer wants error info in the metadata, they lift it into a key (e.g. `errorMessage`, `error.name`).

## Metadata (`Map<String, Any>`)

### Serialization (write side)

`MapAnySerializer` (`Debug/TraceEvent.kt:37`) preserves:
- `String`, `Number`, `Boolean` → native JSON types
- `Map<*, *>` → nested JSON object (recursive)
- `List<*>` → JSON array (recursive)
- `null` → JSON null
- everything else → `v.toString()` (lossy fallback)

### Deserialization (read side)

```kotlin
override fun deserialize(decoder: Decoder): Map<String, Any> {
    val json = decoder.decodeSerializableValue(JsonObject.serializer())
    return json.mapValues { it.value.toString() }   // LOSES TYPE
}
```

**You CANNOT round-trip a metadata map through JSON without losing type.** Native ints come back as ints (because kotlinx-serialization preserves scalar types in the JSON tree), but complex nested objects come back as `Map<String, JsonElement>` and must be coerced.

The Python parser (`parse_json_trace.py`) coerces token fields back to int via `_coerce_int(v)`:

```python
def _coerce_int(v):
    if isinstance(v, bool): return None  # bool is a subclass of int in Python
    if isinstance(v, (int, float)): return int(v)
    if isinstance(v, str):
        try: return int(v)
        except: return None
    return None
```

### Token keys (the only fields you can reliably round-trip)

These are the token-bearing keys the parser aggregates:

| Key | Emitted by | Scope |
|-----|-----------|-------|
| `inputTokens` | standard pipeline + PumpStation funnel | Prompt tokens sent |
| `outputTokens` | same | Tokens generated |
| `totalTokens` | same | `inputTokens + outputTokens` (when both present) |
| `actualInputTokens` | standard pipeline `CONTEXT_PREPARED` | Model-reported prompt tokens (USE FOR BILLING) |
| `reasoningTokens` | standard pipeline `API_CALL_SUCCESS` | Reasoning-model tokens (subset of `actualInputTokens`) |
| `totalInputTokens` | standard pipeline aggregate events | Cumulative prompt tokens across run |
| `totalOutputTokens` | standard pipeline aggregate events | Cumulative output tokens across run |
| `responseLength` | standard pipeline `API_CALL_SUCCESS` | Character length of response text |
| `reasoningLength` | standard pipeline `API_CALL_SUCCESS` | Character length of reasoning text |
| `promptLength` | standard pipeline `API_CALL_START` | Character length of prompt sent |

**Scope gotcha**: a single Pipe run emits TWO `API_CALL_SUCCESS` events:

1. First: `inputTokens=1705, outputTokens=311, totalTokens=2016` (per-call)
2. Second: `totalInputTokens=2328, totalOutputTokens=116` (cumulative across retries)

If you naively sum `outputTokens` across all `API_CALL_SUCCESS` for a Pipe, you get ~2× the actual spend. Use `totalInputTokens` / `totalOutputTokens` for billing.

### Other common metadata keys (non-token)

From real JSON traces on disk (`~/.tpipe/autogenesis-trace/`):

- `pipeClass`, `model`, `provider` — Pipe configuration
- `promptLength`, `responseLength`, `reasoningLength`, `reasoningTokens` — token-adjacent
- `streaming`, `apiType`, `baseUrl`, `success`, `finishReason` — API call config
- `responseId`, `systemFingerprint`, `stopReason` — response metadata
- `validatorFunction`, `transformationFunction`, `preValidationFunction`, `onFailure` — Pipe wiring
- `useModelReasoning`, `reasoningEnabled`, `modelSupportsReasoning` — reasoning model config
- `activatorKeyCount`, `totalPipelines`, `splitterClass`, `splitterId`, `pipelineCount`, `pipelineDetails`, `pipelineName`, `resultCount`, `resultLength`, `resultSize`, `success`, `successfulPipelines`, `totalJobs`, `totalPipelines`, `totalResults` — Splitter metadata

From PumpStation funnel (`Pipeline/PumpStationHelpers.kt:110+`):

- `turnIndex` — integer, which turn this event belongs to (0-indexed)
- `phase` — string, the PumpStation phase name (e.g. `Judge`, `Dispatch`, `PathExecution`)
- `runId` — string, the PumpStation runId
- `originalInputPreview` — HarnessStarted only, clipped to 8KB
- `warningCode`, `mechanisms` — HarnessWarning
- `exitReason`, `finalOutput` — HarnessCompleted
- `error`, `errorMessage`, `exitReason` — HarnessFailed
- `pausedAt`, `reason` — HarnessSuspended
- `boundaryPhase`, `droppedCount`, `firstDroppedText` — InterruptOverflowDropped
- `status`, `warnings`, `terminateHarness` — HealthCheckCompleted
- `judgeRunMode` — JudgeStarted/JudgeSkipped ("Always" or "FlagTriggered")
- `isComplete`, `shouldTerminate`, `result` — JudgeCompleted (the verdict)
- `selectedPathName`, `pathRequest` — DispatchCompleted
- `pathName`, `riskLevel` — PathSelected/PathStarted/PathSafety/PathCompleted
- `approved`, `approvedAsInt`, `reason` — PathSafetyCompleted
- `contentPreview`, `contentLength`, `modelReasoning`, `modelReasoningLen`, `binaryCount` — content-bearing events

## Parsing JSON traces — the workflow

1. **Read** with `json.load(open(path))`.
2. **Detect** envelope: if dict with `events` key, extract `events`; else assume root is the array.
3. **For each event, extract tokens** from `metadata` using `_coerce_int`.
4. **Aggregate** by `pipeName` (per-pipe) and `eventType` (per-event-type).
5. **Sort** by `timestamp` for timeline.

## Verifying extraction

Run `python3 scripts/verify_extraction.py --strict` against the seven pinned cases. All pass at v3.0.

## Anti-patterns

### Don't read the trace JSON into Python via `json.load(open(path))` and treat it as a normal dict

`metadata` keys can have values of arbitrary types (nested dicts, lists, scalars). A naive `sum(int(m["inputTokens"]) for m in events if "inputTokens" in m)` works for the simple case but breaks when `inputTokens` is `None`, `False` (which is `int(0)` in Python!), or a stringified number from a different producer.

### Don't `try_recover_json(content)` with a greedy `re.search(r'\[.*\]', content)`

A trace file can contain JSON examples inside content text. Greedy `\[.*\]` will match from the first `[` in any string content to the last `]` in the file, swallowing the entire rest of the document.

### Don't assume `event_count = len(events)`

The parser counts events in the `events` array. For wrapped envelopes, use `len(parsed["events"])`, not `len(json.load(...))`.