# TPipe Bedrock Pipe Setup — API Call Shapes and Trace Schema

Captured 2026-08-10 from the map-upload safety agent live-test session (the
`server-extend` `mapSafetyBuilder.kt` + `MapUploadGate.kt` + live test against
real AWS Bedrock). Four non-obvious API surfaces that future pipe-setup tasks
will hit.

## 1. `setJsonOutput(KClass<*>)` and `setJsonInput(KClass<*>)` — the call shape is `Foo::class`, NOT `::Foo`

The TPipe `Pipe` base class declares these two as
`setJsonOutput(kclass: KClass<*>)` and `setJsonInput(kclass: KClass<*>)`
(verified at `TPipe/src/main/kotlin/Pipe/Pipe.kt:3021` and
`TPipe/src/main/kotlin/Pipe/Pipe.kt:2419` in the `abi-kickoff` worktree).
The parameter is `KClass<*>`, not a function reference.

The wrong call shape (CRASHES AT RUNTIME with
`Serializer for class 'KFunction' is not found`):

```kotlin
// WRONG — `::MapSafetyCheck` is a function reference (KFunction<...>),
// not a KClass.  Schema.examplePromptFor calls .serializer() on it which
// fails because KFunction has no @Serializable companion.
val imageChecker = BedrockMultimodalPipe().apply {
    setJsonOutput(::MapSafetyCheck)            // CRASHES
    setJsonInput(::MapData)                   // CRASHES
    setJsonInput(::MapSafetyCheck)            // CRASHES
}
```

The right call shape (compiles and runs):

```kotlin
val imageChecker = BedrockMultimodalPipe().apply {
    setJsonOutput(MapSafetyCheck::class)      // correct
    setJsonInput(MapData::class)             // correct
    setJsonInput(MapSafetyCheck::class)       // correct
}
```

**Why this fires at runtime, not compile-time:** Kotlin's
`::Foo` reference resolves to `KFunction<Foo>` when `Foo` is a
class with a synthetic function (e.g. a `data class` with
`componentN`, or a typed builder method), and to `KClass<Foo>`
when `Foo` is a class reference used in a `KClass<*>`-typed
parameter. The two are ambiguous at the call site, the compiler
defaults to the `KFunction` interpretation, the KSP codegen
passes that through, and the runtime `serializer()` call
explodes. The bug is silent at the build, fatal at the first
request through the pipe.

**Detection:** the live test surfaces it as
`kotlinx.serialization.SerializationException: Serializer for
class 'KFunction' is not found` in the JUnit XML
`Caused by:` chain. The fix is the `Foo::class` swap; no other
change is needed.

**Companion pitfall** (this file's `setJsonInput` is the same
trap): any `setJsonInput(::Foo)` or `setJsonOutput(::Foo)` is
the wrong shape, full stop. The token `::Foo` is read as a
function reference first; the only way to force the
`KClass<*>` reading is the `Foo::class` form.

## 2. `Pipeline.execute(...)` returns `MultimodalContent`; pass/fail is `result.shouldTerminate()`

The TPipe `Pipeline` class
(`TPipe/src/main/kotlin/Pipeline/Pipeline.kt:1387`) declares:

```kotlin
suspend fun execute(initialContent: MultimodalContent): MultimodalContent =
    executeMultimodal(initialContent)
```

It returns a `MultimodalContent`. The pass/fail signal is NOT a
typed return value or an exception — it's the
`terminatePipeline: Boolean` field on the returned
`MultimodalContent`, surfaced as
`MultimodalContent.shouldTerminate(): Boolean`
(`TPipe/src/main/kotlin/Pipe/BinaryContent.kt:252`).

```kotlin
val pipeline = buildMapSafetyAgent(playerId, payload)
val result: MultimodalContent = pipeline.execute(multimodal)
val passed: Boolean = !result.shouldTerminate()
```

**Why `setOnFailure` flips the flag** (verified
`TPipe/src/main/kotlin/Pipe/BinaryContent.kt:98` and the
canonical pipeline orchestrator at `TPipe/src/main/kotlin/Pipe/Pipe.kt:4838`):

1. The pipe's `setOnFailure { original, processed -> ... }` is the
   hook that fires on validation failure or JSON output rejection.
2. The lambda MUST return a `MultimodalContent` (signature is
   `suspend (original: MultimodalContent, processed: MultimodalContent) -> MultimodalContent`).
3. To mark the pipeline as failed, the lambda sets
   `processed.terminatePipeline = true` (or
   `processed.terminate()` is the helper, line 220) before
   returning.
4. The pipeline propagates the `terminatePipeline = true` up to
   the final `MultimodalContent` returned from `execute(...)`.
5. The caller checks `result.shouldTerminate()` to learn the
   outcome.

**The default state is `terminatePipeline = false` (pass).**
A pipe that never sets it produces a passing result even if
the LLM output was garbage — that's the canonical "no
`setOnFailure` = silent garbage" trap (already documented in
the umbrella SKILL.md under "Anti-pattern: the no-op
`setOnFailure` that swallows the failure").

**Companion**: the original-vs-processed distinction.
`original` is the `MultimodalContent` that flowed INTO the
pipe; `processed` is what the LLM produced. `setOnFailure`
returns `processed` (with the flag flipped) so downstream
pipes see the failure state. Reading from `original` inside
`setOnFailure` is fine for retrieving the input that triggered
the failure; the returned value should be `processed` (or
`processed.copy(terminatePipeline = true)`) for the
propagation to work.

## 3. Trace event field is `pipeName`, not `name`

When the live test extracted pipe names from the captured
trace JSON, the obvious regex on `"name"` matched zero events
because the canonical `TraceEvent` data class
(`TPipe/src/main/kotlin/Debug/TraceEvent.kt:17-35`) uses
`pipeName` as the field name:

```kotlin
@Serializable
data class TraceEvent(
    val id: String = generateEventId(),
    val timestamp: Long,
    val pipeId: String,
    val pipeName: String,        // <-- THIS is the per-pipe label
    val eventType: TraceEventType,
    val phase: TracePhase,
    val content: MultimodalContent?,
    val contextSnapshot: ContextWindow?,
    @Serializable(with = MapAnySerializer::class)
    val metadata: Map<String, Any> = emptyMap(),
    ...
)
```

For a regex-based trace inspector, target `pipeName` not
`name`:

```kotlin
// WRONG — matches zero events in a real trace
val nameRegex = Regex("\"name\"\\s*:\\s*\"([^\"]+)\"")

// RIGHT — picks up the per-pipe label for every event
val nameRegex = Regex("\"pipeName\"\\s*:\\s*\"([^\"]+)\"")
```

Other field names that are NOT what they look like:
`eventType` (string), `phase` (string), `metadata` (object,
key-value pairs), `pipeId` (UUID). The full schema is in
`TPipe/src/main/kotlin/Debug/TraceEvent.kt`.

**The `metadata` map serialization is non-trivial** —
`MapAnySerializer` (`TPipe/src/main/kotlin/Debug/TraceEvent.kt:37`)
serializes via `buildJsonObject` with type-specific encoders.
A `Map<String, Any>` field deserializes back to
`Map<String, String>` (line 89: `json.mapValues { it.value.toString() }`),
so test code that does `event.metadata["key"]` will get
stringified values, not the original types.

## 4. The map pack format: zip with `map.json` + image entry

`MapPackManager.pack/unpack` (the `expect` object in
`sharedModel/src/commonMain/kotlin/structs/MapPackManager.kt`)
defines a real zip format used by both the editor and the
runtime:

- **JVM side** (`sharedModel/src/jvmMain/kotlin/structs/MapPackManager.kt`):
  `java.util.zip.ZipOutputStream` writes two entries: `map.json`
  (the `MapPackData` JSON) and the image entry (named
  dynamically by `imageName`).
- **JS side** (`sharedModel/src/jsMain/kotlin/structs/MapPackManager.kt`):
  `JSZip` (npm) writes the same two entries, with the same
  `map.json` JSON shape.

The `MapPackData` shape
(`sharedModel/src/commonMain/kotlin/structs/MapPack.kt:14`):

```kotlin
@Serializable
data class MapPackData(
    val imageName: String,        // e.g. "arctica.png"
    val mapData: MapData
)
```

`MapData` (`sharedModel/src/commonMain/kotlin/structs/MapPack.kt:80`):
`pins: List<PinData>` (required, no default), `connections:
List<ConnectionData>` (required, no default), plus a long tail
of defaulted fields (`worldName`, `storyScenario`, `author`,
`writingInstructions`, `storyWeights`,
`selectionStrategy`, `authorEnabled`,
`alwaysApplyRulesEnabled`, `guardrailsEnabled`,
`writingAgentConfig`). The two `List` fields have NO default
— test code that does `MapData()` will fail to compile
without explicit `pins = emptyList(), connections = emptyList()`
arguments. This bites when constructing a `MapData` for a
unit test or a hand-built payload.

`UnpackedMapPack` (line 107):

```kotlin
data class UnpackedMapPack(
    val imageName: String,
    val imageBytes: ByteArray,
    val mapData: MapData
)
```

The `unpack` operation handles the image entry by reading any
non-`map.json` entry as the image bytes. The image filename
is recovered from `MapPackData.imageName` (not from the
zip-entry name). Don't hard-code "image.png" — the
`imageName` field is the source of truth.

**Real resource location for live tests**:
`server/src/main/resources/maps/<name>.map` contains seven
pre-saved maps (`Arctica.map`, `Europa.map`, `IO-map.map`,
`Laurasiagondwana.map`, `San_Martello.map`, `jupiter.map`,
`tutorial.map`). The classpath resource load pattern:

```kotlin
val resourceStream = javaClass.classLoader.getResourceAsStream("maps/Arctica.map")
    ?: error("map resource must exist on the classpath: maps/Arctica.map")
val mapBytes = resourceStream.use { it.readBytes() }
val unpacked = MapPackManager.unpack(mapBytes)
// unpacked.imageName = "arctica.png" (or similar)
// unpacked.imageBytes = the PNG bytes
// unpacked.mapData = the structured MapData
```

The `maps/<name>.map` files are real ZIP archives (magic
`PK\003\004` at offset 0). They unpack cleanly via the
JVM-side `MapPackManager.unpack`.

## Context-window overflow on image classifiers is real, not a bug

When a `BedrockMultimodalPipe` (e.g. `amazon.nova-2-lite-v1:0`) is
fed a 6.3 MB PNG via the multimodal payload, the
`BedrockMultimodalPipe` raises
`Exception: Context window size is too small to fit the
binary data. Please increase the context window size.
Context window size: 990000 Binary size: 1579206`.

The fix for real production traffic is to either downscale
the image at the upload client before packing, or pick a
model with a larger context window (Anthropic Claude has
200K tokens, Nova Lite has ~990K base64 tokens). For tests,
either pick a smaller map or stub the `BedrockMultimodalPipe`
with a `FakePipe` that returns synthetic responses.

This is NOT a code bug. The pipeline wiring is correct; the
model simply can't fit the image. The captured live-test
trace JSON shows the failure with the exact error string
under `metadata["error"]` for the `PIPE_FAILURE` event.

## Putting it together — the canonical "wire a safety agent on server-extend" recipe

```kotlin
internal data class MapSafetyPayload(
    val imageBytes: ByteArray,
    val mapData: MapData
)

internal suspend fun buildMapSafetyAgent(
    playerId: String,
    payload: MapSafetyPayload
): Pipeline {
    val imageChecker = BedrockMultimodalPipe().apply {
        setRegion("us-west-2")
        setModel(BedrockConfig.novaModelName)
        setTemperature(.6)
        setTopP(.7)
        setReasoning("high")
        setTokenBudget(BedrockConfig.novaBudgetSettings)
        setSystemPrompt(/* ... */)
        setJsonOutput(MapSafetyCheck::class)        // Foo::class, NOT ::Foo
        setFooterPrompt(/* ... */)
        setValidatorFunction { /* ... */ }
        setOnFailure { _, processed ->
            val result = extractJson<MapSafetyCheck>(processed.text) ?: MapSafetyCheck()
            MapUploadErrorHandlers.sendMapUploadError(playerId, result.reason)
            processed.terminatePipeline = true       // flip the flag, NOT just return
            processed
        }
    }
    val contentChecker = BedrockMultimodalPipe().apply {
        // ... same shape, different prompt ...
        setJsonInput(MapData::class)                 // Foo::class, NOT ::Foo
        setJsonInput(MapSafetyCheck::class)          // Foo::class, NOT ::Foo
    }
    return Pipeline().apply {
        add(imageChecker)
        add(contentChecker)
        init(true)
    }
}

// Caller pattern (the gate):
val result: MultimodalContent = pipeline.execute(multimodal)
val passed: Boolean = !result.shouldTerminate()        // <-- the pass/fail signal

// Trace capture (the gate's helper):
pipeline.enableTracing(TraceConfig(enabled = true, detailLevel = TraceDetailLevel.DEBUG))
// ... execute ...
MapUploadGate.captureAndSaveTrace(pipeline, playerId)  // writes trace.json + trace.html

// Reading the trace back (the live test):
val pipeNames = Regex("\"pipeName\"\\s*:\\s*\"([^\"]+)\"")
    .findAll(traceJson)
    .map { it.groupValues[1] }
    .toSet()
```

The four footguns — `Foo::class` not `::Foo`,
`shouldTerminate()` for pass/fail, `pipeName` for trace
field, the map pack zip format — are the load-bearing
mistakes that future sessions will hit. Pin them in
TDD-pinned tests; the live-test loop is the receipt that
they hold.
