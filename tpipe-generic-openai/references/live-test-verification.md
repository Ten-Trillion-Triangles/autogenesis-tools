# Verifying TPipe GenericOpenAIPipe Live Tests Are Real

When a user asks "is this test actually calling the API, or is it returning canned data?", the trace artifacts in `/tmp/trace_report_console.txt` and `/tmp/trace_report.html` (written by `OpenAIResponsesTracingLiveTest.kt`) are the first place to look. But the file existing doesn't prove the test ran — it just proves the test wrote something. Use these four checks to verify the trace is real output from a real LLM call.

## 1. responseId format and uniqueness (the real smoking gun)

MiniMax returns a 32-character lowercase hex string per request — e.g. `0673d6212457ad022438c2d6a2e55e53`. Two properties prove it's a real API call:

- **Format:** exactly 32 hex chars, lowercase, no dashes.
- **Uniqueness:** the same test run twice produces *different* responseIds. If you re-run the test and grep for the old id, you should NOT find it.

A hardcoded stub would either omit the field or repeat the same constant. This is the most reliable single check — a real responseId cannot be faked without actually calling the API.

## 2. EXPIRED: outputTokens vs responseLength gap as "smoking gun"

**The previous version of this reference claimed a 63-token gap (outputTokens=73, responseLength=10) was proof of a real reasoning model call. That was wrong.** The user verified the actual cause: a **tracing-instrumentation bug** in `GenericOpenAIPipe.kt` that emitted a duplicate `API_CALL_SUCCESS` event for the same call — first event with the full provider usage (`outputTokens=73` including reasoning), second event with a separate post-generation metric (`outputTokens=5` = the visible text). MiniMax does also babble policy preamble in its raw reasoning stream (the "63 tokens" the model produced are real, just not all reasoning), but the trace recorded them as ONE call and then split them across two events.

**Lesson:** A token-count gap in the trace is a signal to investigate the trace, not a proof of a real call. Use check #1 (responseId) as the authoritative signal. If you see a gap, check whether the trace contains duplicate `API_CALL_SUCCESS` events for the same call — if so, that's a tracing bug to fix, not a model signature to celebrate.

## 3. Duplicate API_CALL_SUCCESS event bug (tracing pitfall)

Symptom in `/tmp/trace_report_console.txt`:
```
[SUCCESS] GenericOpenAIPipe - API_CALL_SUCCESS (EXECUTION)
  Metadata: {inputTokens=51, outputTokens=73, totalTokens=124, responseLength=10, ..., responseId=0673d6...}
...
[SUCCESS] GenericOpenAIPipe - API_CALL_SUCCESS (EXECUTION)
  Metadata: {outputTokens=5, totalInputTokens=63, totalOutputTokens=5, ...}    # duplicate, no responseId
```

The second event is the post-generation summary that the streaming/reasoning path emits. It conflicts with the first event and pollutes downstream consumers of the trace (dashboards, tests asserting on `outputTokens`). The fix: the `POST_GENERATE` phase should reuse the metrics from the `API_CALL_SUCCESS` event, not re-record them as a second success. See `tpipe-pipeline-patterns` for the canonical event sequence.

## 4. TCP connection evidence

A live test makes a real socket connection to `api.minimax.io` (resolved IPs `47.89.128.168` and `47.252.72.253` at time of writing). While a test is running:

```bash
ss -tn '( dport = :443 and dst 47.89.128.168 or 47.252.72.253 )'
```

You should see ESTABLISHED connections with non-zero byte counts. Zero connections = stub. Note: `localhost` or `127.0.0.1` traffic = also stub.

## 5. Live regenerate and compare (the definitive check)

If a user is still suspicious, the definitive proof is to **re-run the test and check that the responseId changed**. If the id is different, the test is hitting the live API. If it's identical, something is faking it.

```bash
# Run once
MINIMAX_API_KEY=... ./gradlew :TPipe-GenericOpenAI:test --tests "*OpenAIResponsesTracingLiveTest"
grep responseId /tmp/trace_report_console.txt

# Run again
MINIMAX_API_KEY=... ./gradlew :TPipe-GenericOpenAI:test --tests "*OpenAIResponsesTracingLiveTest"
grep responseId /tmp/trace_report_console.txt
```

Two different ids = real. Same id = faked.

## The "test that proves the test" pattern

The trace files exist because `OpenAIResponsesTracingLiveTest.kt` explicitly writes them to `/tmp/` as a side effect of running:

```kotlin
val consoleReport = pipeline.getTraceReport(TraceFormat.CONSOLE)
val htmlReport = pipeline.getTraceReport(TraceFormat.HTML)

// Write trace reports to files for inspection (before assertions to capture state even on failure)
java.io.File("/tmp/trace_report_console.txt").writeText(consoleReport)
java.io.File("/tmp/trace_report.html").writeText(htmlReport)
```

This is intentional — it lets a human (or another agent) inspect what the trace system recorded without rerunning the test. The pattern: **live tests that record observable state to disk make their work auditable. Stubbed tests that only print to stdout do not.**

## Anti-pattern: the verification theater response

When asked to "prove this test is real", a common failure mode is to run `javap` on the compiled class, `find` for `MockEngine`, `grep` for `respond(`, and dump TCP captures — none of which prove the trace wasn't faked. They prove the production code uses a real HTTP client, but that's a different question. The four checks above are what actually answer "is this trace real output from a real API call".

The fastest way to answer is to `cat` the trace file. If the file contains the smoking gun from check #1 and a properly-formatted responseId from check #2, the trace is real. If the user asks to see it, **show it** — don't summarize, don't offer `file://` links, don't run five rounds of secondary verification.

## Session context

This technique was developed in response to a 2026-06-06 session where a subagent (Codex CLI) had been asked to prove a TPipe test was real. The subagent went through 5+ rounds of `javap`/`grep`/`ss` theater instead of `cat`'ing the trace file when the user asked to see it. The data was actually real — the responseId was properly formatted, the outputTokens/responseLength gap matched M2.7's reasoning signature — but the subagent's behavior pattern was so evasive that the user's suspicion was reasonable. The lesson: when the user asks to see evidence, show the evidence. Treat any evasion as a tell about the underlying data, then verify the data directly.

## Surfacing wire-protocol bugs via live tests

The most valuable use of live tests against external providers is **catching wire-protocol bugs that unit tests cannot see**. A unit test that deserializes a hand-written JSON string passes even when the production request never produces that JSON. A live test exercises the full path: code → serializer → wire → provider's parser → response.

The 2026-06-24 MiniMax audit session demonstrated this twice in one run:

1. **`ToolDefinition.type` default-drop bug** — unit tests passed because the test data included `type = "function"` explicitly. Live `setTools()` from a user never sets `type` (it uses the default), so the wire payload lacked the field. MiniMax rejected it. Fix: `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` on the `type` field, or remove the default.

2. **`AnthropicMessagesResponse.ResponseContentBlock` missing polymorphic discriminator** — unit tests passed because the test data only used `TextContentBlock`. MiniMax /anthropic returns `ThinkingBlock` content blocks in non-streaming mode, which kotlinx.serialization cannot dispatch to without `@JsonClassDiscriminator("type")` on the sealed class. Streaming path (`AnthropicSseParser`) handled thinking deltas correctly because it parses line-by-line rather than via the sealed-class mapper.

**Pattern for finding the next bug:** write a live test for the "obvious" feature (cache control, function calling, JSON output, system prompt hoisting, multimodal input), run it against the real provider, and read the failure carefully. Provider error messages are usually specific enough to point at the bug.

**Anti-pattern:** using `@Disabled` to silence failing tests. `@Disabled` is fine when the test infrastructure is broken (e.g., no API key), but **not** when the production code is broken. Use `@Disabled` only as a temporary marker with a source comment pointing at the specific bug, and re-enable the test as soon as the bug is fixed. `MiniMaxFeaturesLiveTest` uses this pattern with the two known-bug tests.
