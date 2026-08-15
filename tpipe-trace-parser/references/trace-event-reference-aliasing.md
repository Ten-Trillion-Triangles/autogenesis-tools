# Trace-event reference aliasing — the "later mutate overwrites earlier" trap

## Symptom

You open an HTML trace and see something that doesn't make sense at the recorded timestamp. Examples from real sessions:

- A `POST_GENERATE` event at +204.330s shows `terminatePipeline=true` in its
  MultimodalContent dump, but the API call at the same timestamp reported
  `success=true, responseLength=0`. The pipe then ran a `VALIDATION_FAILURE`
  with `reason: "Validator pipe returned content with terminate flag"`, but
  `validatorPipe` was `null` and `validatorFunction` had never been invoked.

- An earlier `CONTEXT_PREPARED` event embeds a `MiniBank` whose `new page`
  text is the FINAL page content rather than the content at the time of
  context preparation.

- A `VALIDATION_SUCCESS` event shows the post-correction text rather than
  the text that was actually validated.

The pattern: the trace shows state that DID NOT exist at the timestamp.

## Root cause

`TraceEvent` stores the mutable `MultimodalContent` and `ContextWindow`
objects by reference, not by snapshot.

- `TraceEvent.kt:16-29` — `TraceEvent` data class holds `content:
  MultimodalContent?` and `contextSnapshot: ContextWindow?` directly.
- `Pipe.kt:4803-4812` — `Pipe.trace()` builds the event by passing the
  pipe's CURRENT `content` and `contextWindow` into the `TraceEvent`
  constructor; no `.deepCopy()`.
- `MultimodalContent` is a Kotlin `data class` with mutable `var` fields
  (`text`, `binaryContent`, `terminatePipeline`, `metadata`,
  `miniBankContext`, etc.). All writers downstream mutate the same
  instance.
- `ContextWindow` and `MiniBank` are likewise mutable containers; the
  banked elements mutate in place when downstream code calls
  `ContextBank.emplaceWithMutex(...)`.

The trace exporter renders each event's `content` and `contextSnapshot`
at export time (which is post-hoc, after the whole pipeline has finished).
The renderer reads the LIVE state of those mutable objects, which has
already been mutated by every subsequent step.

## How to recognize it in triage

Three signals, all required together:

1. The event metadata's reported TIMESTAMPED values contradict the
   current state of the displayed content/context. (e.g. POST_GENERATE
   shows `terminatePipeline=true` but its sibling API_CALL_SUCCESS at the
   same timestamp reports `success=true, responseLength=0`.)
2. A LATER event shows a CAUSE for the state (e.g. an onFailure callback
   that set `terminate()`, or a `preInvoke*` that parsed malformed input
   and called `terminate()`).
3. The trace exporter does NOT distinguish "state at timestamp" from
   "state at export" — it just renders the live object.

The hypothesis is almost always: **the rendered content reflects the
final mutated state of the object, not the state at the event's
timestamp.**

## Worked example (TPipeWriter logical progression pipe, 2026-07-12)

Timeline reconstructed from a single trace:

```
+204.328s  API_CALL_SUCCESS  responseLength=0  (empty streaming result)
+204.330s  POST_GENERATE    content.terminatePipeline=true  <-- ALIASED
+204.334s  VALIDATION_FAILURE reason="Validator pipe returned content with terminate flag"
           (truth: validatorFunction was isValidGptOssResponse, but it was NEVER called)
+204.334s  POST_PROCESSING failure: restored prior "new page" prose via onFailure callback
+204.335s  PIPE_SUCCESS     output: the restored prose (7526 chars)
```

When the HTML exporter renders event 168 (`POST_GENERATE` at +204.330s),
it reads `content` from the LIVE `MultimodalContent` object. By that time,
the onFailure callback at +204.334s has already overwritten `content.text`
with the prior "new page" prose AND set `terminatePipeline=true` (via the
`preInvokeLoreRepairPipe` call in the next pipe's pre-invoke, which fails
to parse the restored prose as JSON and calls `terminate()`).

So the rendered `POST_GENERATE` event shows `terminatePipeline=true` and
~7500 chars of prose, neither of which existed at +204.330s. The trace
gives you a misleading picture of state-at-time.

## Implications for triage

When you see "impossible state" in an event, don't trust the rendered
event in isolation. Always cross-reference:

1. Sibling events at the same timestamp (especially `API_CALL_SUCCESS`
   metadata, which is built BEFORE content mutation).
2. Later events that show what caused the state change.
3. Source-code grep for the field that "shouldn't be set yet".

The fact that the trace lies about state-at-time is itself a real bug
(see Finding 6 in the TPipeWriter investigation report), but during
triage it means: **don't read the rendered content/context as
authoritative for time T**. Read it as authoritative for the LAST
mutation that touched those fields.

## The fix (out of scope for triage but worth knowing)

`Pipe.trace()` should deep-copy `content` and `contextSnapshot` at the
moment of the event:

```kotlin
val event = TraceEvent(
    timestamp = System.currentTimeMillis(),
    pipeId = pipeId,
    pipeName = if(pipeName.isNotEmpty()) pipeName else (this::class.simpleName ?: "UnknownPipe"),
    eventType = eventType,
    phase = phase,
    content = if(shouldIncludeContent(traceConfig.detailLevel)) content?.deepCopy() else null,
    contextSnapshot = if(shouldIncludeContext(traceConfig.detailLevel)) contextWindow.deepCopy() else null,
    metadata = if(traceConfig.includeMetadata) enhancedMetadata else emptyMap(),
    error = error
)
```

`MultimodalContent.deepCopy()` exists on the `Pipe` API surface (used
by the reasoning pipe at `Pipe.kt:6866`). `ContextWindow` and `MiniBank`
would need their own deep-copy implementations. Until those ship, treat
the rendered trace's `content` and `contextSnapshot` blocks as
"eventually-consistent" rather than "timestamp-accurate".

## Why this matters for the "validator pipe" misdiagnosis

A common investigation lands here: trace shows
`VALIDATION_FAILURE reason="Validator pipe returned content with terminate flag"` but
the pipe had no `validatorPipe` configured and `validatorFunction` was a
real function that should have been called. The investigation dead-ends
on "did the validator function reject?" — but the answer is "no, the
validator function was never called because content was empty".

`Pipe.kt:6483` short-circuits before `validatorFunction`:

```kotlin
if(!validatorPipeContent.shouldTerminate()) {
    // validatorFunction runs here
} else {
    trace(VALIDATION_FAILURE, ..., reason = "Validator pipe returned content with terminate flag")
}
```

And `MultimodalContent.shouldTerminate()` returns true when EITHER
`terminatePipeline` is set OR `isEmpty()`. So an empty streaming result
flips the branch, and the diagnostic message ("Validator pipe returned
content with terminate flag") is wrong — no validator pipe exists; the
content was just empty. The real cause is upstream (streaming assembly
returned 0 chars).

When you see this exact failure pattern (empty result + this validator
error message), the trail leads upstream to the streaming consumer, not
to the validator.
