# Bedrock SDK Upgrade — Wiring Streaming Response Event Handlers (SINK side)

**Date**: 2026-07-28
**Branch**: `bedrock-sdk-1.6.107-upgrade` at HEAD `8b8254bf`
**Source repo**: `/home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Bedrock/`
**SDK pin**: `aws.sdk.kotlin:bedrockruntime:1.6.107`, `aws-core:1.6.107`
**Task reference**: Task 7 of `.hermes/plans/2026-07-28_123101-bedrock-sdk-1.6.107-upgrade.md`

This is the worked case study for the SINK-side fix to the gap documented in `references/2026-07-27-bedrock-sdk-upgrade-consequences.md`. That audit identified that `executeConverseStream` at `BedrockPipe.kt:4300` handled 4 of 9+ `ConverseStreamResponse` events and silently dropped `ContentBlockStart`, `ContentBlockStop`, `MessageStart`, the ToolUse variant of `ContentBlockDelta`, and the Citations variant. Task 7 wired the first three of those (MessageStart, ToolUse delta + start, and ContentBlockStop). Task 8 wires `ConverseStreamMetrics.latencyMs` and citation deltas. Task 9 wires the non-streaming response-side dispatch in `BedrockMultimodalPipe`.

The complement of this SINK-side fix is the SOURCE-side worked example in `references/2026-07-28-bedrock-sdk-upgrade-wiring-source-side.md` (Task 3 — `performanceConfig` wire).

## What Task 7 wired

The four event handlers added to `executeConverseStream` (`BedrockPipe.kt:4300`):

| Event | New handler purpose | Field it populates on `BedrockCallMetadata` |
|---|---|---|
| `ConverseStreamOutput.MessageStart` | Acknowledge for tracing (no payload captured yet) | (none — first-block role-verification reserved for follow-up) |
| `ConverseStreamOutput.ContentBlockStart` | Capture `toolUseId` + `toolUse.name` from the `start.toolUse` variant | `toolUse[i].toolUseId`, `toolUse[i].name` (after finalization at Stop) |
| `ConverseStreamOutput.ContentBlockDelta` (ToolUse variant) | Accumulate input JSON fragments across many deltas | `toolUse[i].input` (assembled at Stop) |
| `ConverseStreamOutput.ContentBlockStop` | Finalize `ToolUseBlock` from the captured `toolUseId`/`name` + accumulated JSON, add to `collectedToolUse` | `toolUse[i]` (whole `ToolUseBlock` instance) |

After the stream ends, `BedrockCallMetadata` is populated with the closed `collectedToolUse` list + `cacheReadInputTokens` / `cacheWriteInputTokens` (from the existing `usageMetadata` map) + `stopReason` (already captured at `MessageStop`).

## The five-site change

### Site 1 — the per-block tracking accumulators (added at the top of `executeConverseStream`)

`BedrockPipe.kt:4745-4756`. Six local-state variables, all keyed by the wire's `contentBlockIndex`:

```kotlin
val perBlockToolUseIds = mutableMapOf<Int, String>()                // blockIndex -> toolUseId
val perBlockToolUseNames = mutableMapOf<Int, String>()               // blockIndex -> tool name
val perBlockStopReasons = mutableMapOf<Int, String>()                // blockIndex -> stop reason (reserved)
var currentBlockIndex = 0
val toolUseAccumulator = mutableMapOf<Int, StringBuilder>()          // blockIndex -> accumulated input JSON
val collectedToolUse = mutableListOf<aws.sdk.kotlin.services.bedrockruntime.model.ToolUseBlock>()
```

The `perBlockXxx` maps are necessary because a single message can contain multiple content blocks interleaved in any order. The wire's `contentBlockIndex` is the only ordering key — the wire does not promise sequentiality. Using a flat `var currentToolUseId` would silently lose blocks 1+ if a model interleaves text + tool-use blocks in a single stream.

`currentBlockIndex` is updated on every `ContentBlockStart` event. The `toolUseAccumulator` pre-creates an empty `StringBuilder` per block at start time so a zero-fragment tool-use (a model that emits Start + Stop with no Delta in between) doesn't fail to append.

### Site 2 — the four new event handlers in `response.stream?.collect { event -> }`

`BedrockPipe.kt:4766-4856`. The existing 3-event collect block (ContentBlockDelta / MessageStop / Metadata) gains 4 new handlers. The order matters: Start must come before Delta (Delta fragments must be associated with the Start's toolUseId), and Stop must come after Delta (Stop finalizes the accumulated JSON).

```kotlin
response.stream?.collect { event ->
    // NEW: MessageStart
    event.asMessageStartOrNull()?.let {
        // no-op for now; reserved for first-block role verification
    }

    // NEW: ContentBlockStart — capture toolUseId + name per block
    event.asContentBlockStartOrNull()?.let { startEvent ->
        currentBlockIndex = startEvent.contentBlockIndex
        startEvent.start?.asToolUseOrNull()?.let { toolStart ->
            perBlockToolUseIds[currentBlockIndex] = toolStart.toolUseId
            perBlockToolUseNames[currentBlockIndex] = toolStart.name
            toolUseAccumulator.getOrPut(currentBlockIndex) { StringBuilder() }
        }
    }

    // EXISTING + EXTENDED: ContentBlockDelta
    event.asContentBlockDeltaOrNull()?.let { deltaEvent ->
        val blockIndex = deltaEvent.contentBlockIndex
        // EXISTING: text deltas
        deltaEvent.delta?.asTextOrNull()?.let { deltaText -> ... }
        // EXISTING: reasoning deltas
        deltaEvent.delta?.asReasoningContentOrNull()?.asTextOrNull()?.let { reasoningDelta -> ... }
        // NEW: tool-use input JSON fragments
        deltaEvent.delta?.asToolUseOrNull()?.let { toolDelta ->
            val acc = toolUseAccumulator.getOrPut(blockIndex) { StringBuilder() }
            acc.append(toolDelta.input)
        }
    }

    // NEW: ContentBlockStop — finalize ToolUseBlock
    event.asContentBlockStopOrNull()?.let { stopEvent ->
        val blockIndex = stopEvent.contentBlockIndex
        perBlockToolUseIds[blockIndex]?.let { toolId ->
            val toolName = perBlockToolUseNames[blockIndex] ?: ""
            val inputJson = toolUseAccumulator[blockIndex]?.toString() ?: ""
            collectedToolUse.add(
                aws.sdk.kotlin.services.bedrockruntime.model.ToolUseBlock {
                    this.toolUseId = toolId
                    this.name = toolName
                    this.input = if (inputJson.isNotEmpty()) {
                        aws.smithy.kotlin.runtime.content.Document(inputJson)
                    } else {
                        null
                    }
                }
            )
            perBlockStopReasons[blockIndex] = "tool_use_block_closed"
        }
    }

    // EXISTING: MessageStop
    event.asMessageStopOrNull()?.let { ... }

    // EXISTING: Metadata
    event.asMetadataOrNull()?.usage?.let { ... }
}
```

The `asXxxOrNull()` extension functions on `ConverseStreamOutput` are auto-generated by the SDK. The names on 1.6.107 (verified by `javap` on `bedrockruntime-jvm-1.6.107.jar`):

| Event | Extension method on `ConverseStreamOutput` | Returns |
|---|---|---|
| `MessageStart` | `asMessageStartOrNull()` | `MessageStartEvent` |
| `MessageStop` | `asMessageStopOrNull()` | `MessageStopEvent` |
| `ContentBlockStart` | `asContentBlockStartOrNull()` | `ContentBlockStartEvent` |
| `ContentBlockDelta` | `asContentBlockDeltaOrNull()` | `ContentBlockDeltaEvent` |
| `ContentBlockStop` | `asContentBlockStopOrNull()` | `ContentBlockStopEvent` |
| `Metadata` | `asMetadataOrNull()` | `ConverseStreamMetadataEvent` |

On the inner `ContentBlockDelta.Delta` sealed class (verified):

| Delta variant | Extension method | Returns |
|---|---|---|
| `Text` | `asTextOrNull()` | `String` |
| `Image` | `asImageOrNull()` | `ImageBlockDelta` |
| `ReasoningContent` | `asReasoningContentOrNull()` | `ReasoningContentBlockDelta` (then `.asTextOrNull()` for the text fragment) |
| `Citation` | `asCitationOrNull()` | `CitationsDelta` |
| `ToolResult` | `asToolResultOrNull()` | `List<ToolResultBlockDelta>` |
| `ToolUse` | `asToolUseOrNull()` | `ToolUseBlockDelta` (then `.input` for the JSON fragment) |

On `ContentBlockStart` sealed class (verified):

| Start variant | Extension method | Returns |
|---|---|---|
| `ToolUse` | `asToolUseOrNull()` | `ToolUseBlockStart` (then `.toolUseId`, `.name`) |
| `ToolResult` | `asToolResultOrNull()` | `ToolResultBlockStart` |
| `Image` | `asImageOrNull()` | `ImageBlockStart` |

The variant constructors (`ConverseStreamOutput.MessageStart(...)`, `ConverseStreamOutput.ContentBlockStart(...)`, etc.) — these are sealed-class member constructors, not nested-class constructors on `ConverseStreamResponse`. See gotcha #1 below.

### Site 3 — populate `BedrockCallMetadata` after the stream ends

`BedrockPipe.kt:4873-4881`. Must come AFTER `client.converseStream(...)` returns (so `collectedToolUse` is fully assembled) but before the `metadata` trace map is built (so the `lastCallMetadata` field and the trace are consistent).

```kotlin
// NEW: Populate BedrockCallMetadata with per-call wire-level details.
lastCallMetadata = BedrockCallMetadata(
    toolUse = collectedToolUse.toList(),
    cacheReadInputTokens = (usageMetadata["cacheReadInputTokens"] as? Long),
    cacheWriteInputTokens = (usageMetadata["cacheWriteInputTokens"] as? Long),
    stopReason = stopReason.ifEmpty { null }
)
```

`stopReason.ifEmpty { null }` collapses the empty-string default into `null` so the `BedrockCallMetadata.stopReason` field's nullable type round-trips cleanly through `data class` equality / hashCode.

### Site 4 — the test seam (the testability hook)

`BedrockPipe.kt:4868-4903`. The protected `executeConverseStream` takes a `BedrockRuntimeClient` parameter — production callers pass `this.bedrockClient`, but the seam needs to inject a fake. The seam accepts the client as a parameter and reverses the `toStreamRequest()` mapping:

```kotlin
internal suspend fun executeConverseStreamForTest(
    client: BedrockRuntimeClient,
    modelId: String,
    request: ConverseStreamRequest,
    apiLabel: String
): MultimodalContent? = executeConverseStream(
    client,
    modelId,
    request.toConverseRequestForTest(),
    apiLabel
)

private fun ConverseStreamRequest.toConverseRequestForTest(): ConverseRequest {
    return ConverseRequest {
        this.modelId = this@toConverseRequestForTest.modelId
        this.messages = this@toConverseRequestForTest.messages
        this.inferenceConfig = this@toConverseRequestForTest.inferenceConfig
        this.system = this@toConverseRequestForTest.system
        this.additionalModelRequestFields = this@toConverseRequestForTest.additionalModelRequestFields
        this.additionalModelResponseFieldPaths = this@toConverseRequestForTest.additionalModelResponseFieldPaths
        this.performanceConfig = this@toConverseRequestForTest.performanceConfig
        this.promptVariables = this@toConverseRequestForTest.promptVariables
        this.requestMetadata = this@toConverseRequestForTest.requestMetadata
        this.toolConfig = this@toConverseRequestForTest.toolConfig
        this@toConverseRequestForTest.guardrailConfig?.let { gc ->
            this.guardrailConfig = aws.sdk.kotlin.services.bedrockruntime.model.GuardrailConfiguration {
                guardrailIdentifier = gc.guardrailIdentifier
                guardrailVersion = gc.guardrailVersion
                trace = gc.trace
            }
        }
    }
}
```

The seam is `internal` (not `private`, not `protected`) so same-module tests can call it. `internal` covers both `TPipe-Bedrock/src/main` and `TPipe-Bedrock/src/test` since they're in the same Gradle module.

The seam's reverse map is symmetric with the forward `toStreamRequest()` at `BedrockPipe.kt:3016`. **Critical**: every field that `toStreamRequest()` forwards must have a corresponding read in `toConverseRequestForTest()`. Asymmetric reverse maps lose fields. A future agent extending `ConverseRequest` (e.g. adding `outputConfig` for structured output) must update BOTH maps.

The seam does NOT need a visibility change to `bedrockClient`. The seam takes the client as a parameter and never reads the field. The plan's worry that `bedrockClient = fakeClient` would require making the field `internal` is unfounded for this design — the field stays `protected var` and is untouched.

### Site 5 — the unit + live tests

`TPipe-Bedrock/src/test/kotlin/bedrockPipe/StreamingBlockEventTest.kt` (2 unit tests, hand-crafted fixtures) and `TPipe-Bedrock/src/test/kotlin/bedrockPipe/StreamingToolUseLiveTest.kt` (1 live test, gated on `AllowTest=true`).

The unit test fixture uses a `FakeBedrockRuntimeClient` that implements the `BedrockRuntimeClient` interface directly. The canned `Flow<ConverseStreamOutput>` is what the fake returns from `converseStream()`. Every other operation on the client throws `UnsupportedOperationException` so a regression in test wiring is loud, not silent.

## The seven gotchas (the painful part)

### Gotcha 1 — `ConverseStreamOutput` vs `ConverseStreamResponse`

The streaming events live on `ConverseStreamOutput`, NOT on `ConverseStreamResponse`. The two are different classes in the SDK:

- `ConverseStreamResponse` — the wrapper class returned by `client.converseStream(...)`. Has a single field: `stream: Flow<ConverseStreamOutput>`. Has no sealed-class member variants.
- `ConverseStreamOutput` — the sealed class that represents each event in the stream. Has 7 variants: `MessageStart`, `MessageStop`, `ContentBlockStart`, `ContentBlockDelta`, `ContentBlockStop`, `Metadata`, `SdkUnknown`.

The plan's pseudocode wrote `ConverseStreamResponse.MessageStart(...)` etc., which does NOT compile. The constructors are `ConverseStreamOutput.MessageStart(...)`, `ConverseStreamOutput.ContentBlockStart(...)`, etc.

```bash
# Verify: which class has the streaming event constructors?
unzip -p ~/.gradle/caches/modules-2/files-2.1/aws.sdk.kotlin/bedrockruntime-jvm/1.6.107/*/bedrockruntime-jvm-1.6.107.jar \
  | javap -public aws/sdk/kotlin/services/bedrockruntime/model/ConverseStreamOutput.class | grep -E 'public.*\$'
# Expected: 7 nested classes (one per variant).
```

```bash
# And NOT on ConverseStreamResponse:
unzip -p ... | javap -public aws/sdk/kotlin/services/bedrockruntime/model/ConverseStreamResponse.class | grep -E 'public.*\$'
# Expected: NO nested classes. The wrapper is just a data class with a stream field.
```

### Gotcha 2 — `MessageStartEvent.role` is `ConversationRole`, not `String`

The plan's fixture wrote `role = "assistant"`. This compiles to:

```
e: Assignment type mismatch: actual type is 'String', but 'ConversationRole?' was expected.
```

The correct form is `role = ConversationRole.Assistant`. `MessageStartEvent.role` is typed as `ConversationRole` (the SDK enum: `User` / `Assistant` / `System` / `UserContent` / `AssistantContent`, etc.). The string "assistant" only works via the `value: String` getter on the `ConversationRole` enum.

```bash
# Verify the field type:
javap -public .../MessageStartEvent.class | grep -E 'public final.*getRole'
# Expected: public final aws.sdk.kotlin.services.bedrockruntime.model.ConversationRole getRole();
```

This is true for every Smithy-generated event class where the wire model has a `role` enum. The pattern recurs on `MessageStopEvent.stopReason` (typed as `StopReason`), `ToolUseBlockStart.toolUseId` (typed as `String`), `ContentBlockStart.start` (typed as `ContentBlockStart` — the sealed class itself), etc. Always check the getter's return type before writing a fixture.

### Gotcha 3 — `contentBlockIndex` is non-nullable `Int`, not nullable

The plan's pseudocode used `startEvent.contentBlockIndex ?: 0` and `stopEvent.contentBlockIndex ?: 0`. These compile but emit `w: Elvis operator (?:) always returns the left operand of non-nullable type 'Int'`. The SDK generator makes the field non-nullable because the wire format always includes it (it's a protocol-required field, not optional).

```bash
javap -public .../ContentBlockStartEvent.class | grep getContentBlockIndex
# Expected: public final int getContentBlockIndex();   (primitive int -> Kotlin Int, non-nullable)
```

The correct form is `startEvent.contentBlockIndex` (no elvis). Same for `ContentBlockStopEvent.contentBlockIndex` and `ContentBlockDeltaEvent.contentBlockIndex`.

The build does not FAIL on the elvis (just warns), so a future agent copy-pasting the pattern from older code may not notice. The warning is the only signal that the elvis is dead code.

### Gotcha 4 — `Document` is abstract; use `asString()`, not `asStringNode()`

`ToolUseBlock.input` is typed as `aws.smithy.kotlin.runtime.content.Document?` (nullable). `Document` is the abstract base class; concrete subclasses are `Document$String`, `Document$Number`, `Document$Boolean`, `Document$List`, `Document$Map`. There is NO `asStringNode()` method.

The plan's pseudocode wrote `captured.input?.asStringNode()?.value`. This does NOT compile — there is no `asStringNode()` accessor on `Document`.

The correct way to extract a string from a `Document`:

```bash
javap -public .../Document.class | grep asString
# Expected: public final java.lang.String asString();  (no throw variant)
#           public final java.lang.String asStringOrNull();  (nullable-safe variant)
```

So:
- `document.asString()` — returns the string value, throws if the document is not a string variant.
- `document.asStringOrNull()` — returns `String?`, null if not a string variant.

The right assertion for the streaming tool-use test (where `input` was constructed via `Document(inputJson)`):

```kotlin
val actualInputString: String? = captured.input?.asStringOrNull()  // or .asString() when known to be String
assertEquals(expectedInput, actualInputString)
```

`Document` is also constructed via a top-level factory function:

```bash
javap -public .../DocumentKt.class | grep 'public static.*Document('
# Expected: public static final Document Document(java.lang.String);
#           public static final Document Document(java.lang.Number);
#           public static final Document Document(boolean);
#           public static final Document Document(java.util.List<? extends Document>);
#           public static final Document Document(java.util.Map<java.lang.String, ? extends Document>);
```

So `Document(stringValue)` (no `fromString`, no `.String(...)`) is the constructor. The plan's `Document.fromString(inputJson)` does NOT compile. The correct form is `Document(inputJson)`.

### Gotcha 5 — `BedrockRuntimeClient` is a Kotlin interface with a `close(): Unit` (non-suspend)

When writing a fake `BedrockRuntimeClient`, you must override EVERY abstract method. The interface (verified on 1.6.107):

```bash
javap -public .../BedrockRuntimeClient.class | grep -E 'public abstract'
# Expected:
#   public abstract <T> converseStream(...);
#   public abstract converse(...);
#   public abstract invokeModel(...);
#   public abstract applyGuardrail(...);
#   public abstract invokeGuardrailChecks(...);
#   public abstract countTokens(...);
#   public abstract startAsyncInvoke(...);
#   public abstract getAsyncInvoke(...);
#   public abstract listAsyncInvokes(...);    <-- single arg, NOT (input, limit: Int?)
#   public abstract <T> invokeModelWithResponseStream(...);
#   public abstract <T> invokeModelWithBidirectionalStream(...);
# Plus: override val config: Config, and override fun close(): Unit  (non-suspend, from java.io.Closeable)
```

Three concrete traps:

1. **`listAsyncInvokes(input: ListAsyncInvokesRequest)` has NO `limit: Int?` parameter.** The Kotlin default-parameter handling lives in `BedrockRuntimeClient$DefaultImpls.listAsyncInvokes$default(...)`, NOT in the interface itself. The fake that takes `(input, limit: Int?)` does NOT override anything (silent no-op). Correct: `override suspend fun listAsyncInvokes(input: ListAsyncInvokesRequest): ListAsyncInvokesResponse`.

2. **`close(): Unit` is non-suspend.** It comes from `java.io.Closeable` (which `SdkClient` extends transitively). The fake that declares `override suspend fun close()` does NOT override (suspend vs non-suspend is a different JVM signature; Kotlin emits a warning but the build may pass with a no-op). Correct: `override fun close() { /* no-op */ }`.

3. **`config: Config` is a property getter, not a method.** Correct: `override val config: BedrockRuntimeClient.Config get() = throw ...`. Writing `override fun getConfig(): Config` does NOT override (different arity).

The pattern that works:

```kotlin
private class FakeBedrockRuntimeClient(
    private val cannedEvents: List<ConverseStreamOutput>
) : BedrockRuntimeClient {
    override val config: BedrockRuntimeClient.Config
        get() = throw UnsupportedOperationException("...")

    override suspend fun <T> converseStream(
        input: ConverseStreamRequest,
        block: suspend (ConverseStreamResponse) -> T
    ): T {
        val response = ConverseStreamResponse {
            stream = flowOf(*cannedEvents.toTypedArray())
        }
        return block(response)
    }

    override suspend fun converse(input: ConverseRequest): ConverseResponse = throw ...
    override suspend fun invokeModel(input: InvokeModelRequest): InvokeModelResponse = throw ...
    override suspend fun applyGuardrail(input: ApplyGuardrailRequest): ApplyGuardrailResponse = throw ...
    override suspend fun invokeGuardrailChecks(input: InvokeGuardrailChecksRequest): InvokeGuardrailChecksResponse = throw ...
    override suspend fun countTokens(input: CountTokensRequest): CountTokensResponse = throw ...
    override suspend fun startAsyncInvoke(input: StartAsyncInvokeRequest): StartAsyncInvokeResponse = throw ...
    override suspend fun getAsyncInvoke(input: GetAsyncInvokeRequest): GetAsyncInvokeResponse = throw ...
    override suspend fun listAsyncInvokes(input: ListAsyncInvokesRequest): ListAsyncInvokesResponse = throw ...
    override suspend fun <T> invokeModelWithResponseStream(...): T = throw ...
    override suspend fun <T> invokeModelWithBidirectionalStream(...): T = throw ...

    override fun close() {
        // no-op
    }
}
```

Throwing `UnsupportedOperationException` on every method that the test doesn't exercise makes a regression in test wiring LOUD — if a future change causes `executeConverseStream` to call e.g. `client.invokeModel(...)` (shouldn't happen, but the fake catches it), the test fails immediately with a clear stack trace instead of silently passing because the fake returns null/empty.

### Gotcha 6 — The seam is asymmetric with `toStreamRequest()`

The seam's `toConverseRequestForTest()` reverse-map and the production `toStreamRequest()` forward-map must be field-symmetric. Every field that `toStreamRequest()` writes must be read back in `toConverseRequestForTest()`. If `toStreamRequest()` starts forwarding a new field (e.g. `outputConfig` added in 1.8.x), the reverse-map must add a corresponding read, or the seam will silently drop the field on test paths.

**Verification gate** (after any future ConverseRequest field addition):

```bash
# Compare the two lists
sed -n '/private fun ConverseRequest.toStreamRequest/,/^    }/p' BedrockPipe.kt | grep -E 'original\.|\.let'
sed -n '/private fun ConverseStreamRequest.toConverseRequestForTest/,/^    }/p' BedrockPipe.kt | grep -E 'this@|this@toConverse'
# The sets must match (modulo the GuardrailStreamConfiguration->GuardrailConfiguration block).
```

### Gotcha 7 — `internal` vs `protected` vs the `TestableBedrockPipe` subclass pattern

The existing test idiom (e.g. `StreamingCallbackTest.kt`) uses a `private class TestBedrockPipe : BedrockPipe() { public suspend fun testEmit(chunk: String) { emitStreamingChunk(chunk) } }` subclass to expose protected members. This pattern is necessary when the test needs to call a `protected` method on `BedrockPipe`.

For Task 7, the seam is on `BedrockPipe` itself (not a subclass). The seam method is `internal`, not `protected`. So the test can call `pipe.executeConverseStreamForTest(fakeClient, ...)` directly — no subclass needed.

When to use which:

- **Protected member + no production caller**: use the `TestableBedrockPipe` subclass to expose. Cleaner because it doesn't pollute the production class with test-only surface.
- **Method that production calls via a different signature but the test needs a parallel entry point**: add an `internal` seam on the production class. The seam calls the production method internally, so behavior is identical.
- **`protected` field needed for direct read/write**: the seam pattern requires the field to remain protected; the seam takes the value via a parameter. If the test needs to read the field, expose a getter or use the subclass pattern.

For Task 7, the seam pattern was chosen because the test needs to inject the client (not just read state). Subclassing to override the protected `bedrockClient` setter would require the field to be `open var`, which is more invasive than an `internal suspend fun` seam.

## Verification chain (executed and captured)

| Gate | Command | Expected | Actual |
|---|---|---|---|
| 1 | `grep -c 'asMessageStartOrNull\|asContentBlockStartOrNull\|asContentBlockStopOrNull\|asToolUseOrNull' BedrockPipe.kt` | >= 5 | 6 ✓ |
| 2 | `grep -qE 'fun executeConverseStreamForTest' BedrockPipe.kt` | yes | yes ✓ |
| 3 | `grep -c lastCallMetadata BedrockPipe.kt` | >= 1 (incl. populate call) | 4 ✓ |
| 4 | `./gradlew :TPipe-Bedrock:compileKotlin` | BUILD SUCCESSFUL | BUILD SUCCESSFUL ✓ |
| 5 | `./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.StreamingBlockEventTest" --rerun-tasks` | 2 tests, 0 failures | 2 tests, 0 failures (XML: tests=2 failures=0 errors=0 skipped=0) ✓ |
| 6 | `./gradlew :TPipe-Bedrock:test --rerun-tasks` (full) | 153 testcases, 1 failure (baselined `BedrockPcpBugTest`) | 153 testcases, 1 failure (`BedrockPcpBugTest.testPcpNamedArgumentsBugWithAws`) ✓ |
| 7 | `git log -1 --pretty=%s` | `feat(bedrock): add ContentBlockStart/Stop + ToolUse streaming handlers` | matches ✓ |

The baselined `BedrockPcpBugTest.testPcpNamedArgumentsBugWithAws` failure is pre-existing on the branch and unrelated to Task 7 — it's a PCP/Bedrock integration test failure that surfaces as "LLM failed to respond or API error occurred" because the test requires real Bedrock credentials (no AllowTest=true gating on this particular test) and runs into an empty / unavailable AWS environment in the test runner.

## Test coverage

- **Unit (2 tests, `StreamingBlockEventTest`)**:
  - `streamingToolUseIsCapturedIntoBedrockCallMetadata` — hand-crafts a stream with `MessageStart` -> `ContentBlockStart(toolUse)` -> 2x `ContentBlockDelta(toolUse input)` -> `ContentBlockStop` -> `MessageStop(stopReason=ToolUse)` -> `Metadata`. Asserts: `metadata.toolUse.size == 1`, the captured `toolUseId` and `toolName` match the start event, the accumulated input JSON is the verbatim concatenation of the two delta fragments, `metadata.stopReason == "tool_use"`.
  - `streamingTextOnlyNoToolUseHasEmptyToolUseList` — hand-crafts a text-only stream with `MessageStart` -> `ContentBlockDelta(text)` -> `ContentBlockStop` -> `MessageStop(stopReason=EndTurn)` -> `Metadata`. Asserts: `metadata.toolUse.size == 0` (no tool-use captured on a text-only stream), `metadata.stopReason == "end_turn"`.

  Both tests use a private `FakeBedrockRuntimeClient` that implements the `BedrockRuntimeClient` interface directly (see gotcha #5). Every method other than `converseStream` throws `UnsupportedOperationException`.

- **Live (1 test, `StreamingToolUseLiveTest`)**:
  - `liveStreamingClaudeToolCallPopulatesMetadata` — gated on `AllowTest=true`, configures a `BedrockPipe` with `anthropic.claude-3-5-sonnet-20241022-v2:0`, registers a `get_weather` tool via `setTools()`, runs a streaming Converse call, asserts `getLastCallMetadata().toolUse.isNotEmpty()` and every captured toolUse has a non-empty `toolUseId`. Skipped under default test run.

## Cross-references

- `tpipe-pipe-feature-audit` SKILL.md — the parent methodology. The "Provider-SDK response events are silently dropped when not subscribed" pitfall names exactly what Task 7 fixes.
- `tpipe-pipe-feature-audit/references/2026-07-27-bedrock-sdk-upgrade-consequences.md` — the SINK-side audit (the gap). This case study is the SINK-side fix.
- `tpipe-pipe-feature-audit/references/2026-07-28-bedrock-sdk-upgrade-wiring-source-side.md` — the SOURCE-side worked example (Task 3, `performanceConfig` wire). Sibling reference for the request-side complements.
- `tpipe-pipe-internals` — for `protected var` vs `internal` vs `TestableBedrockPipe` subclass visibility choices on `BedrockPipe`.
- `tpipe-test-patterns` — for the same-package test idiom (FakeBedrockRuntimeClient pattern is similar in shape to the P2PInterface test doubles the skill describes).
- `interactive-plan` — the workflow that produced the multi-task plan this case study executes.