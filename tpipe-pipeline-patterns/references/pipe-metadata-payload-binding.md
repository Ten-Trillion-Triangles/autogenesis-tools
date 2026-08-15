# Per-Pipe Metadata Binding for Composite Payloads

When a multi-pipe agent receives a composite payload (e.g. `MapSafetyPayload(imageBytes, mapData)` from a gate layer), each pipe in the agent usually only needs *one fragment* of that payload. The idiomatic TPipe pattern is to bind the relevant fragment onto the pipe's own `pipeMetadata` map at construction time, so downstream readers (validators, failure callbacks, tracers, sibling pipes) can pull it from the pipe's local state instead of threading the wrapper through every site.

## The seam: `pipeMetadata`

`Pipe.kt:1933` declares:

```kotlin
val pipeMetadata = mutableMapOf<Any, Any>()
```

It is `protected var` — readable from inside the pipe's `.apply { }` block (where the builder runs) and from any subclass / external reader that has a handle to the pipe instance. The map accepts any value type (`Any`), so `ByteArray`, `String`, structured data classes, JSON strings, and arbitrary objects all bind cleanly.

Internal TPipe already uses the same map for: `USER_PROMPT_SNAPSHOT` (Pipe.kt:2917), `wrappedConverseHistory` (Pipe.kt:6269, 6273, 6393), `semanticCompressionApplied` + companion fields (Pipe.kt:5992-5995). It's the framework's blessed scratch pad.

## The pattern: top-of-function destructure + per-pipe bind

```kotlin
internal suspend fun buildMapSafetyAgent(
    playerId: String,
    payload: MapSafetyPayload         // composite: imageBytes + mapData
) : Pipeline
{
    // 1. Destructure the wrapper at the top so every pipe below has
    //    access to the fragments as named locals.
    val imageBytes = payload.imageBytes
    val mapData = payload.mapData

    val imageChecker = BedrockMultimodalPipe().apply {
        setPipeName("image pipe")
        setRegion("us-east-2")
        // ... region / model / tier / budget / temperature / reasoning ...

        // 2. Bind THIS pipe's fragment onto its own metadata.
        //    Downstream readers can do: pipe.pipeMetadata["imageBytes"] as ByteArray
        pipeMetadata["imageBytes"] = imageBytes

        setSystemPrompt(...)
        // ... validator, onFailure ...
    }

    val contentChecker = BedrockMultimodalPipe().apply {
        setPipeName("text pipe")
        // ... same configuration block ...

        // 3. The text pipe doesn't need raw bytes; it gets a SERIALIZED
        //    string it can later JSON-parse. Use com.TTT.Util.serialize,
        //    not kotlinx.serialization.json.Json.encodeToString — TPipe's
        //    serializer handles AI-malformed JSON repair and matches every
        //    other agent in the empire (elderGodAgent, nemesisAgent,
        //    npcHostileAgent, identifyPlayAgent, BranchFailureAgent).
        pipeMetadata["mapDataJson"] = serialize(mapData)

        // ...
    }

    return Pipeline().apply {
        add(imageChecker)
        add(contentChecker)
        init(true)
    }
}
```

## Where the bind goes inside the `.apply { }` block

Place `pipeMetadata[...] = ...` **immediately after the core configuration setters** (region, model, service tier, temperature, reasoning, token budget) and **before the system / middle / footer prompt set**. Rationale: the bind is part of "what this pipe knows about the world," grouped with model + region + tier, before "what this pipe says to the LLM."

A practical layout:

```kotlin
val pipe = BedrockMultimodalPipe().apply {
    setPipeName("...")
    setRegion("...")
    useConverseApi()
    setServiceTier(BedrockPriorityTier.Flex)
    setModel(...)
    setTemperature(...)
    setTopP(...)
    setReasoning("high")
    setTokenBudget(...)

    // <- bind here
    pipeMetadata["myFragment"] = myLocal

    setSystemPrompt(...)
    setFooterPrompt(...)
    setValidatorFunction { ... }
    setOnFailure { ... }
}
```

## Why destructure + bind instead of dereferencing the wrapper

Three concrete wins:

1. **Readability.** `pipeMetadata["mapDataJson"]` is self-describing at every read site; `payload.mapData` requires the reader to know what `payload` is and trust it's still in scope.
2. **Survival across the LLM round-trip.** `payload` is a function parameter — once the function returns the Pipeline, the payload reference is garbage-collected. `pipeMetadata` lives on the pipe instance and persists for the lifetime of the pipe (which can be reused across many `execute()` calls).
3. **Per-pipe filtering at construction time.** A two-pipe agent with `MapSafetyPayload(imageBytes, mapData)` shouldn't carry image bytes on the text pipe or map data on the image pipe. Binding at the apply-block scope makes the partitioning visible in code; dereferencing the wrapper at every call site would let bugs creep in if someone calls `payload.imageBytes` from inside the text pipe's validator.

## When NOT to use this pattern

- **Single-pipe agents** where the wrapper is the function's only output — destructure + bind is overkill; just pass the field directly.
- **Wrappers that are themselves the LLM input** (e.g. `MultimodalContent` flowing through the pipe). The `MultimodalContent.metadata` map is the right seam for runtime metadata; `pipeMetadata` is for pipe-local state set at construction.
- **Hot-path fields that change per-execute-call.** `pipeMetadata` is set once at construction. If the value differs per execute, store it on `MultimodalContent.metadata` instead.

## Reading from `pipeMetadata`

```kotlin
// Inside a validator / failure callback / transformer — same apply-block scope:
val bytes = pipeMetadata["imageBytes"] as ByteArray
val json = pipeMetadata["mapDataJson"] as String

// From outside (you have a `pipe: BedrockMultimodalPipe` handle):
val bytes = pipe.pipeMetadata["imageBytes"] as ByteArray

// Trace inspection: the trace JSON emits metadata.pipeClass and metadata.model,
// but per-pipe custom binds are NOT auto-promoted to trace metadata. Read them
// off the pipe handle after captureAndSaveTrace if needed.
```

## Anti-patterns

### Don't bind at every execute-call site

If you find yourself writing `pipe.pipeMetadata["..."] = ...` inside `setOnFailure` or a streaming callback, you are probably trying to communicate per-execute state across boundaries. That belongs on `MultimodalContent.metadata`. Per-pipe `pipeMetadata` is construction-time state.

### Don't skip the destructure step and bind the wrapper itself

```kotlin
// BAD — couples the pipe's lifetime to the wrapper's
pipeMetadata["payload"] = payload
```

If the wrapper goes out of scope, the pipe holds a dangling reference. Destructure to the fragments; bind the fragments.

### Don't use raw `Json.encodeToString` for serializable data classes

TPipe's `com.TTT.Util.serialize(...)` is the canonical serializer across every agent in the Autogenesis empire (verified 2026-08: `elderGodAgent`, `nemesisAgent`, `npcHostileAgent`, `identifyPlayAgent`, `BranchFailureAgent` all use it). It wraps `kotlinx.serialization` with AI-malformed-JSON repair. Consistency beats micro-optimization.

## Cross-references

- `references/multimodal-content-flow.md` — `MultimodalContent.metadata` for runtime control flags (contrast with `pipeMetadata` for construction-time state)
- `references/json-prompt-injection-encoding.md` — `setJsonInput/Output` for feeding typed objects into the prompt as text
- `tpipe-pipeline-patterns` SKILL.md section "Pattern 1: The Builder" — the `.apply { }` block where the bind lives
