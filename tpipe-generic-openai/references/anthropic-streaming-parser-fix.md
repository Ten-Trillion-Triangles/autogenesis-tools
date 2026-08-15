# Anthropic Streaming Parser Fix — Full Investigation Log (2026-06-25)

This is the session-specific detail behind the SKILL.md pitfall "MiniMax-M2.7 Anthropic streaming — REAL root cause is sealed-class dispatch". It captures the false leads, the diagnostic test that pinpointed the real bug, and the fix pattern. Read the SKILL.md pitfall first; this file is the deep log.

## The Symptom

`AnthropicStreamingLiveTest.testAnthropicStreamingLive` failed against MiniMax-M2.7 with:
```
Final response: []
Total chunks received: 0
AssertionFailedError: Response should not be empty, got: []
```

Trace showed `streaming: true` and HTTP 200. Framework said it was streaming. It wasn't.

## Round 1 (WRONG): Hypothesis = thinking-only + text-only filter

Initial theory: M2.7 is a reasoning model that emits `thinking_delta` blocks first, the parser filters for `TextDelta` only, so thinking blocks are silently dropped, hence 0 chunks.

**Disproof**: curl against `https://api.minimax.io/anthropic/v1/messages` with the same model + same prompt + same `max_tokens=512` showed the model ALSO emits `text_delta` blocks at higher token counts — e.g. `"Hello there, how are you?"` at index 1 after the thinking block finished. So text_delta IS reachable; the parser's text-only filter is NOT the only problem.

## Round 2 (WRONG): Hypothesis = `@JsonClassDiscriminator("type")` missing on `AnthropicStreamEvent`

Added the annotation. Reran the live test. Still failed.

**Why**: three structural reasons, none of which `@JsonClassDiscriminator` can fix:

1. **Annotation isn't respected without explicit `Json { classDiscriminator = "..." }`.** TPipe's `com.TTT.Util.deserialize<T>()` constructs `Json { ... }` without `classDiscriminator` set. The annotation is informational metadata only. Verified: `Json.decodeFromString<AnthropicStreamEvent>(payload)` with default Json config throws even with the annotation present.
2. **Subclasses don't share a uniform discriminator field at the outer level.** `MessageDelta` has `stopReason` + `usage`, `Error` has `type` + `error`, `Done`/`Unknown` are empty. No uniform wrapper.
3. **`ContentBlockDelta(val chunk: AnthropicStreamingChunk)` doesn't match the wire shape.** Wire format for `content_block_delta` is `{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}` — chunk fields at OUTER level, not nested under `chunk`. Decode fails with `MissingFieldException: Field 'chunk' is required`.

## Round 3 (RIGHT): The actual fix — use the existing `AnthropicSseParser` wrapper

`AnthropicSseParser.parseAnthropicLine` at `SseParser.kt:197` manually dispatches by the outer `type` field:
- `content_block_delta` → `parseAnthropicChunk(json)` → wraps in `ContentBlockDelta` (parseAnthropicChunk decodes the inner AnthropicStreamingChunk which IS polymorphic-decodable because its `delta: AnthropicDelta` subclasses all have a uniform `type` field with `@SerialName(...)`)
- `message_delta` → direct field extraction via `extractJsonString("stop_reason")`
- `error` → throws P2PException
- everything else → `Unknown`

The wrapper has been working correctly since it was written. The production caller was bypassing it with `deserialize<AnthropicStreamEvent>`, which cannot succeed.

**Why the bypass was added in the first place**: unclear from git blame without deeper archaeology. The bypass at `GenericOpenAIPipe.kt:955` is wrong; the right call is `AnthropicSseParser.parseAnthropicLine(...)`.

## Round 4 (SUBTLE): Double-parse bug in the original code

Original production code did:
```kotlin
val sseLine = SseParser.parseLine("data: $dataLine")            // strips "data: " prefix
val parsed = if (sseLine is SseParser.SseLine.Data)
    AnthropicSseParser.parseAnthropicLine(sseLine.content)    // expects "data: …" PREFIX
else AnthropicStreamEvent.Unknown
```

`SseParser.parseLine` strips the `data: ` prefix. Then `parseAnthropicLine` checks for the prefix and returns `Done` if absent. Result: `parsed=Done` for every event line, including valid content_block_delta. The wrapper was being CALLED but always taking the `else -> Done` branch.

Fix: pass `"data: $dataLine"` directly to `parseAnthropicLine` (it strips its own prefix).

## Round 5: Add ThinkingDelta capture into streamingReasoning

With the parser dispatch working, the next opportunity was to capture `AnthropicDelta.ThinkingDelta` into `streamingReasoning` (the existing accumulator used for OpenAI Responses reasoning content).

Extended the parser's `when(val delta)` to handle three subtypes:
```kotlin
when (val delta = parsed.chunk.delta) {
    is AnthropicDelta.TextDelta       -> textBuilder + emitStreamingChunk
    is AnthropicDelta.ThinkingDelta   -> reasoningBuilder (new)
    is AnthropicDelta.InputJsonDelta  -> ignore (caller handles structured output)
}
```

Also widened the `streamingReasoning` gate at `GenericOpenAIPipe.kt:1003` and `:1091` from `if (apiMode is ApiMode.OpenAIResponses)` to `when (apiMode) { is ApiMode.OpenAIResponses, is ApiMode.Anthropic -> ... }`. Without this widening, captured Anthropic reasoning content was being built up in `streamingReasoning` but never surfaced via `MultimodalContent.modelReasoning`.

## The Diagnostic Test Pattern (30-second root-cause identification)

The pattern that broke the investigation open: write a focused JUnit test that calls `Json.decodeFromString<T>(payload)` with NO try/catch:

```kotlin
@Test
fun diagnoseDirectDeserialization() {
    val payload = """{"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Hello"}}"""
    val json = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true }
    try {
        val result: AnthropicStreamEvent = json.decodeFromString(payload)
        println("OK -> ${result::class.simpleName}")
    } catch (e: Throwable) {
        // ← exception type and message pinpoint the root cause in one run
        println("THREW ${e::class.qualifiedName}: ${e.message?.take(400)}")
    }
}
```

With the test caught in try/catch at the test level (NOT inside `Util.deserialize`), the kotlinx.serialization exception surfaces with full type + message:
- Round 1 (no annotation): `JsonDecodingException: Serializer for subclass 'content_block_delta' is not found`
- Round 2 (annotation added): `MissingFieldException: Field 'chunk' is required for type with serial name 'content_block_delta'`
- Round 3 (real fix applied): `OK -> ContentBlockDelta`

Each iteration immediately pointed at the next layer of the problem. Without this test, each round would have required a 30-second curl + gradle test cycle to discover the same fact.

**Why this test pattern matters more than the production code fix**: any future "deserialize<T> returns null for sealed class" bug can be root-caused in one test run by bypassing `Util.deserialize`'s internal try/catch (which silently swallows exceptions) and calling `Json.decodeFromString` directly with NO test-side try/catch.

## Final Fix Shape (5 hunks)

1. **`GenericOpenAIPipe.kt` `executeStreamingDirect` Anthropic branch** — replace direct `deserialize<AnthropicStreamEvent>` with `AnthropicSseParser.parseAnthropicLine("data: $dataLine")`. Extend `when(val delta)` to handle TextDelta/ThinkingDelta/InputJsonDelta.
2. **`GenericOpenAIPipe.kt` `executeStreamingAnthropic` (Ktor path)** — same parser swap. Pass `dataLine` directly (the Ktor path already passes bare JSON without prefix, which `parseAnthropicLine` accepts).
3. **`GenericOpenAIPipe.kt` lines 1003 and 1091** — widen `streamingReasoningText` gate to include `ApiMode.Anthropic`.
4. **`env/AnthropicStreaming.kt:73-88`** — add doc comment on `AnthropicStreamEvent` explaining why direct polymorphic decode is not supported (subclass shape mismatch + uniform-outer-field requirement).
5. **Test updates** — `AnthropicStreamingLiveTest`: bump `MAX_TOKENS` from 256 to 2048, change prompt to "Respond with exactly the word: HELLO", accept either text chunks OR non-blank result in the assertion (handles thinking-only models).

## New Test Added

`AnthropicStreamingDispatchTest.kt` (5 tests, no network required, pins the wrapper contract):
1. `parseAnthropicLine_resolves_text_delta_to_content_block_delta` — text_delta → ContentBlockDelta(TextDelta)
2. `parseAnthropicLine_resolves_thinking_delta_to_thinking_delta_inner` — pins the thinking-capture contract
3. `parseAnthropicLine_resolves_message_delta_with_stop_reason` — message_delta dispatch with nested stop_reason extraction
4. `parseAnthropicLine_maps_lifecycle_events_to_unknown` — message_start/ping/etc. → Unknown (no abort)
5. `direct_deserialize_of_streaming_event_remains_unsupported` — diagnostic guard that flags if anyone removes the parser wrapper and reverts to direct deserialize

## False Leads To Avoid (Lessons)

1. **Don't trust `streaming: true` trace flag alone** — it means the framework attempted streaming, not that bytes actually flowed. The wall-clock timing test (`MiniMaxStreamingTimingTest`) is the only reliable verification of real-time delivery.
2. **Don't trust a test that passes after a partial fix** — adding `@JsonClassDiscriminator` made the data-model layer "correct" but the bug was at the application layer. Verify the end-to-end test passes against real wire bytes.
3. **Don't assume the fix layer matches the bug layer** — the discriminator-miss diagnosis was about the model; the actual fix was about the call site. Diagnose by reading the actual code path, not by analogy.
4. **Pre-existing pitfall in `Util.deserialize`**: its internal try/catch + repair fallback (Util.kt:100-136) silently consumes exceptions and returns null. The caller's `try { ... } catch (_: Exception) { null }` becomes dead-code defense. Future fix: add `System.err.println` inside `Util.deserialize`'s catch block so deserialize-null bugs surface at first run instead of after a 30-second gradle round-trip.

## MiniMax /anthropic reasoning behavior (independent of the fix)

With the parser fix in place, M2.7 streaming behavior:
- `max_tokens=256`, simple prompt: emits only `thinking_delta` blocks within budget; no `text_delta`
- `max_tokens=2048`, trivial prompt ("Respond with exactly the word: HELLO"): emits thinking then `text_delta "HELLO"` at index 1

If your test prompt is too open-ended for the model's reasoning budget, you'll get thinking-only output even with the parser fix in place. Test prompts need to be either (a) trivial enough to fit text after reasoning within `max_tokens`, or (b) the test needs to assert on captured reasoning rather than text chunks.

## References

- `tpipe-generic-openai` SKILL.md pitfall: "MiniMax-M2.7 Anthropic streaming — REAL root cause is sealed-class dispatch"
- `tpipe-json-serialization` SKILL.md pitfall: "STREAMING-PATH REVISION (2026-06-25, REVISED 2026-06-25 round 2)" — the corrected streaming-side advice
- `tpipe-generic-openai` `scripts/SealedClassDeserializationDiagnostic.kt` — reusable diagnostic test template
