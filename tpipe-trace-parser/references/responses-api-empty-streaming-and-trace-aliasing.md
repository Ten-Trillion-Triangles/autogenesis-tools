# Pitfalls: GenericOpenAI Responses API empty-result bug + trace-event reference aliasing

These two pitfalls come from the same investigation (TPipeWriter logical progression
pipe, 2026-07-12) and are tightly coupled — the empty streaming result causes the
misleading validator error, AND the rendered trace's state at that timestamp is
itself unreliable due to reference aliasing.

## Pitfall: GenericOpenAI Responses API streaming returns 0 chars but reports success — empty `responseLength` + `apiType=ResponsesAPI` is the smoking gun

**Symptom in the trace.** A `POST_GENERATE` / `API_CALL_SUCCESS` pair shows:

```
responseLength: 0
outputTokens: 0
inputTokens: 0
totalTokens: 0
streaming: true
success: true
apiType: ResponsesAPI
model: MiniMax-M3 (or any other Responses-API model)
```

followed downstream by a `VALIDATION_FAILURE reason="Validator pipe returned content with terminate flag"`
on a pipe that has NO `validatorPipe` configured. The validator message is wrong;
the real cause is upstream.

**Root cause.** The GenericOpenAI streaming consumer
(`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`)
only appends text from `response.output_text.delta` events. The parser ALSO produces
`ResponseOutputTextDone.text` (`OpenAIResponsesStreamEvent.kt:68-73`) and the final
`ResponseCompleted.response.output[*].content[*].text`
(`OpenAIResponsesResponse.kt:47-73`), but neither streaming execution path consumes
them. If the model only sends its final text through `response.output_text.done` or
only inside `response.completed`, the assembled result is empty while the HTTP/API
layer reports success.

**Trace-level fingerprints that confirm this hypothesis (not just suspicion):**

1. Sibling `API_CALL_SUCCESS` shows `responseLength: 0`, `success: true`,
   `streaming: true`, `apiType: ResponsesAPI`.
2. The pipe has `validatorFunction` configured but NOT `validatorPipe`.
3. The trace shows `VALIDATION_FAILURE` with `reason` containing
   "terminate flag" or "Validator pipe returned content with terminate flag".
4. The trace's `POST_GENERATE` event shows `terminatePipeline=true` on its
   rendered content — but this is **reference aliasing**, not actual state at
   that timestamp. (See "Trace-event reference aliasing" pitfall below and
   `references/trace-event-reference-aliasing.md`.)

**Why the validator error message is misleading.** `Pipe.kt:6483` short-circuits:

```kotlin
if(!validatorPipeContent.shouldTerminate()) {
    // validatorFunction runs here
} else {
    trace(VALIDATION_FAILURE, ..., reason = "Validator pipe returned content with terminate flag")
}
```

`MultimodalContent.shouldTerminate()` returns true when `terminatePipeline` is set
OR `isEmpty()`. An empty streaming result flips the branch into the "validator pipe
terminated" diagnostic — but no validator pipe exists; the content is just empty.
The next pipe then runs with empty input, and its `preInvoke*` parser calls
`terminate()` on JSON-parse failure, producing a second misleading
`terminatePipeline=true` in the rendered trace.

**Do not conclude "the validator rejected the output".** The validator was never
called. Cross-reference upstream to the streaming consumer in `GenericOpenAIPipe.kt`
(the `executeStreamingDirect` and `executeStreamingOpenAIResponses` paths). The fix
lives there: consume `ResponseOutputTextDone.text` and fall back to
`ResponseCompleted.response.output[*].content[*].text` when no deltas arrived.

## Pitfall: Trace-event reference aliasing — rendered event shows LATER state, not timestamp state

**Symptom.** The rendered HTML trace shows state in an event that contradicts what the
event's timestamp and siblings say. Examples:

- A `POST_GENERATE` event at +204.330s shows `terminatePipeline=true` and ~7500
  chars of prose, but its sibling `API_CALL_SUCCESS` at the same timestamp reports
  `responseLength=0, success=true`.
- A `CONTEXT_PREPARED` event shows the FINAL page text rather than the text that
  was banked at context preparation time.
- A `VALIDATION_SUCCESS` event shows the post-correction text rather than what
  was validated.

**Root cause.** `TraceEvent` (`TPipe/src/main/kotlin/Debug/TraceEvent.kt:16-29`)
holds the live `MultimodalContent` and `ContextWindow` references, not snapshots.
`Pipe.trace()` (`Pipe.kt:4803-4812`) passes the pipe's current mutable objects into
the event. The HTML exporter renders the event's `content`/`contextSnapshot` at
export time — which is post-pipeline — and reads the LIVE state of those mutable
objects, which has been mutated by every subsequent step.

**Triage rule.** When you see "impossible state" in an event, do NOT trust the
rendered event in isolation. Cross-reference:

1. Sibling events at the same timestamp (especially `API_CALL_SUCCESS` metadata,
   which is built BEFORE later mutations land).
2. Later events showing what mutated the state.
3. Source-code grep for the field that "shouldn't be set yet".

**The fix (out of scope for triage).** `Pipe.trace()` should deep-copy `content`
and `contextSnapshot` at event creation. `MultimodalContent.deepCopy()` exists
(`Pipe.kt:6866`, used by the reasoning pipe); `ContextWindow` and `MiniBank` would
need equivalents. Until those ship, treat the rendered trace's `content` and
`contextSnapshot` blocks as eventually-consistent (last-mutation state) rather
than timestamp-accurate.

## Why these two pitfalls travel together

In the TPipeWriter investigation, the trace showed BOTH:

1. An empty streaming result (Pitfall 1, real TPipe bug).
2. A `POST_GENERATE` event at the same timestamp that looked like it had
   terminatePipeline=true and ~7500 chars of prose (Pitfall 2, aliasing of the
   rendered event to the live object AFTER downstream mutation).

Reading Pitfall 2 alone would suggest the pipe terminated itself. Reading
Pitfall 1 alone would suggest the validator was wrong. Reading them TOGETHER,
with the cross-reference workflow (sibling events at same timestamp), reveals
the actual chain: empty streaming result → misleading validator error →
onFailure callback restores prior page → next pipe's pre-invoke JSON parser
fails → second terminate() → rendered POST_GENERATE shows that later state.

When you see both symptoms in the same trace, this is the fingerprint.
When you see only one, run the cross-reference workflow to confirm which
direction the cause flows before concluding.

## Worked triage sequence (apply in order)

1. Open the trace. Find any event with `responseLength: 0` paired with
   `success: true, streaming: true, apiType: ResponsesAPI`. Tag the pipe and
   timestamp.
2. Walk forward in time from that timestamp. Look for:
   - `VALIDATION_FAILURE reason: "Validator pipe returned content with terminate flag"`
   - `POST_PROCESSING failure` events
   - `terminate()` calls from any preInvoke* that received malformed input
3. Verify the pipe had `validatorFunction` but NOT `validatorPipe`. If
   validatorPipe is null, the "validator pipe returned content with terminate flag"
   message is wrong by construction — the framework fell into the else branch
   because content was empty (Pitfall 1).
4. Look for `terminatePipeline=true` on EARLIER events than the actual
   terminate() call. If found, this is reference aliasing (Pitfall 2). The
   "impossible" state is the live object mutated by later code, not state
   at the earlier timestamp.
5. Conclude: the streaming consumer is the load-bearing defect. The validator
   branch and the pre-invoke branch are downstream consequences. The fix is in
   the streaming consumer; the symptoms elsewhere are correct framework
   behavior given an empty input.

## Source-code landmarks for verification

When publishing the "fixed?" verdict for either pitfall, the operator-side
verification grep points:

- Empty streaming result fix:
  `grep -n "is ResponseOutputTextDone\|response.output_text.done" TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`
  → expect a `when` branch that appends `done.text` into `textBuilder`.
- Fallback on completed-output assembly:
  `grep -n "ResponseCompleted\|response.output" TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`
  → expect a `when` branch that walks `response.output[*].content[*].text`
  and appends when `textBuilder` is empty.
- Trace deep-copy fix:
  `grep -n "content.deepCopy\|contextWindow.deepCopy" TPipe/src/main/kotlin/Pipe/Pipe.kt`
  → expect the `trace()` function to invoke `.deepCopy()` on both before
  constructing the `TraceEvent`.
