---
name: tpipe-json-serialization
description: "TPipe JSON serialization model — the 3-layer system (schema generator / instance serializer / wire payload), the `com.TTT.Util.serialize()` default-encoding behavior, the `coerceInputValues` round-trip safety net, and the `@EncodeDefault` annotation. Load when investigating why LLM-bound prompts are bigger than expected, when fixing default-encoding bugs, when auditing what gets sent over P2P/DistributionGrid/MemoryServer wire protocols, or when designing new data classes whose JSON shape matters for token cost or wire contract."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [tpipe, serialization, json, kotlinx, defaults, encodedefault, wire, prompt, token-cost]
---

# TPipe JSON Serialization

TPipe does not use a single JSON serializer. It has three distinct serialization layers, each with different defaults and contracts. Conflating them is the most common source of "why is this JSON so big?" / "why are these defaults missing?" / "why did the wire payload break?" bugs.

## The 3-layer model

| Layer | Function | Default `encodeDefaults` | Purpose | File |
|---|---|---|---|---|
| 1. Schema generator (prompt injection) | `JsonSchemaGenerator.formatExampleWithLegend` | **true (hardcoded)** | Renders a JSON example showing the LLM the expected output shape | `TPipe/src/main/kotlin/Util/Schema.kt:163` |
| 2. Instance serializer (runtime) | `com.TTT.Util.serialize<T>(obj, encodedefault)` | **`false`** (after 2026-06-22 fix; was `true` before) | Serializes an in-memory Kotlin instance to a JSON string | `TPipe/src/main/kotlin/Util/Util.kt:48` |
| 3. Wire payload (P2P/DistributionGrid/MemoryServer) | Same `serialize()` but explicitly pinned | Caller's choice | Serializes data sent to a remote endpoint | varies |

Layer 1 is **always** fully populated (every property gets a placeholder — `false`, `0`, `"example_string"`). The point is to give the LLM a complete reference.

Layer 2 used to be fully populated by default. The 2026-06-22 fix flipped the default to omit Kotlin defaults, matching the prior `serializeConverseHistory` opt-out pattern. The change saves input tokens shipped to LLMs in `serialize(contextWindow)`, `serialize(miniContextBank)`, `serialize(todoListObj)`, `serialize(rpcMessage)` and similar LLM-bound call sites in `Pipe.kt` and `DistributionGrid.kt`.

Layer 3 needs to be checked per call site. External P2P hosts may be non-Kotlin clients that don't tolerate missing fields — those call sites should pass `encodedefault = true` explicitly.

## The `serialize()` function

Signature at `Util/Util.kt:48` (post-fix):
```kotlin
inline fun <reified T> serialize(obj: T, encodedefault: Boolean = false): String
```

The companion `deserialize<T>(jsonString)` at `Util/Util.kt:100` has these key options:
- `coerceInputValues = true` — missing JSON fields with default values are transparently restored on read. This is what makes the round-trip safe after the Layer 2 default flip.
- `ignoreUnknownKeys = true` — extra fields in input JSON are silently dropped.
- `isLenient = true` — accepts unquoted keys, trailing commas, etc.
- `allowComments = true` — JSONC-style comments accepted.

If your code does `serialize(x) → deserialize<T>` (file persistence, P2P wire payloads, internal round-trips), the round-trip is safe regardless of which defaults Layer 2 chose to encode. Don't assume a strict equality check on the deserialized object against the original will pass — it will, because the defaults get restored.

## The `@EncodeDefault` annotation

Per-field annotation that takes precedence over the global `encodedefault` setting:
- `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` — field is always written, regardless of value
- `@EncodeDefault(EncodeDefault.Mode.NEVER)` — field is never written, regardless of value

Currently used in TPipe at:
- `Pipe/BinaryContent.kt:121,124` — `terminatePipeline`, `tools` (both NEVER)
- `Context/ConverseData.kt:38,67` — likely `uuid` and history fields (both NEVER)

When auditing a data class for default-encoding behavior, **check for `@EncodeDefault` first** — these fields override whatever Layer 2 does.

## Layer 1 vs Layer 2 — the conflation trap

A common misunderstanding: "the schema generator shows defaults to the LLM, so the LLM learns to echo defaults back, so we don't need to encode defaults in the actual prompt." This is **mostly true** but not always.

The schema generator emits placeholders like `"example_string"`, `false`, `0`. The model **may** echo these literal values back. In practice, models generally emit sensible values for the field (e.g., empty strings, actual booleans) because they understand the field semantics from the surrounding prompt. But the more default fields the schema shows, the more the model's output grows to "match" the schema — which is a real token cost.

The 2026-06-22 fix flips Layer 2 to `false` so the model receives a smaller, less-default-heavy payload. Layer 1 is unchanged (intentional, for LLM reference completeness).

## The 2-pin pattern

When you flip the Layer 2 default to `false`, the only production callers that need to be pinned back to `encodedefault = true` are external-wire sites targeting non-Kotlin clients. As of 2026-06-22, there are exactly two:

1. `P2P/P2PRegistry.kt:1167` — HTTP transport to external P2P host
2. `P2P/P2PRegistry.kt:1202` — Stdio transport to external P2P host

Both pin `serialize(request, encodedefault = true)` explicitly. These are the only production wire-payload sites where the round-trip partner may not be a Kotlin `deserialize()` with `coerceInputValues = true`.

**All other production wire sites round-trip through TPipe's own `deserialize<...>`** (P2P payloads, DistributionGrid payloads, MemoryServer payloads, ContextBank files, StdioBufferManager), and the round-trip is safe via `coerceInputValues = true`.

## Audit recipe

To find all default-leaking call sites:

```bash
grep -rn "import com.TTT.Util.serialize" --include="*.kt" \
  /home/cage/Desktop/Workspaces/TPipe/TPipe/src \
  /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Bedrock/src \
  /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-GenericOpenAI/src \
  /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Ollama/src \
  /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-OpenRouter/src
```

Then for each match, classify:
- `serialize(x)` → **LEAKS DEFAULTS** if it's NOT a Layer 1 schema example AND not already explicitly opt-out
- `serialize(x, encodedefault = false)` → OPT-OUT (correct)
- `serialize(x, encodedefault = true)` → FORCES DEFAULTS (only needed for external wire)
- `serialize(x, false)` → positional OPT-OUT (also correct)

After the Layer 2 default flip, the "LEAKS DEFAULTS" bucket shrinks significantly — any caller that didn't pass an explicit arg now silently stops leaking.

## Verification recipe

When changing the Layer 2 default:

1. `./gradlew compileKotlin compileTestKotlin` — confirm compile passes
2. `./gradlew :test --tests "*UtilSerializeDefaults*"` — confirm the regression test passes
3. `./gradlew :test :TPipe-Bedrock:test :TPipe-GenericOpenAI:test :TPipe-OpenRouter:test` — confirm no existing test fails
4. Spot-check: `serialize(ContextWindow()).length < serialize(ContextWindow(), encodedefault = true).length` — visual sanity that the compact form is smaller

The TPipe-Ollama test failures (OllamaValidationTest, PcpToolBugTest) are **environmental** — they require Ollama running with the `tinydolphin` model, not the `dolphin-mixtral:latest` typically installed. They do NOT relate to default-encoding changes.

### Gradle module name gotcha (read this first)

The TPipe root project is **also named "TPipe"** (see `settings.gradle.kts:1` — `rootProject.name = "TPipe"`). This means `./gradlew :TPipe:test` fails with `project 'TPipe' is ambiguous in root project 'TPipe'. Candidates are: 'TPipe-Bedrock', 'TPipe-Defaults', 'TPipe-GenericOpenAI', 'TPipe-MCP', 'TPipe-Ollama', 'TPipe-OpenRouter', 'TPipe-TraceServer', 'TPipe-Tuner'`.

Use the bare `:test` (or `:compileKotlin`, `:compileTestKotlin`) to target the root project — the submodules keep their prefix:

```bash
./gradlew compileKotlin compileTestKotlin      # root project (where Util.kt lives)
./gradlew :test --tests "*UtilSerializeDefaults*"   # root project test
./gradlew :TPipe-Bedrock:test :TPipe-GenericOpenAI:test   # submodules keep their prefix
```

## `com.TTT.Util.extractJson` — the canonical tool for LLM-facing JSON extraction

When you need to extract a structured object out of text that *may* be malformed LLM output (extra prose around the JSON, unquoted keys, trailing commas, code fences, the whole zoo), use the project's canonical helper:

```kotlin
import com.TTT.Util.extractJson

val payload: PathRequest? = extractJson(llmOutput)
val profile: UserProfile? = extractJson(mixedTextAndJsonBlob)
```

Signature at `Util/JsonExtractor.kt:377`:
```kotlin
inline fun <reified T> extractJson(input: String): T?
```

Internally:
1. Calls `extractAllJsonObjects(input)` to scan the string for every balanced `{...}` region using bracket-matching (handles nested objects).
2. Sorts candidates by range size — complete objects first, fragments last — so the most plausible JSON wins.
3. Calls `deserializeFirstMatch<T>(candidates)` which tries each candidate against the target schema using the project's lenient Json config (`ignoreUnknownKeys = true`, `isLenient = true`, etc.) plus the `repairAndDeserialize` fallback.
4. Returns the first successful deserialization, or `null`.

### When to use `extractJson` vs `deserialize`

| Scenario | Tool |
|---|---|
| Known-good JSON from a TPipe-internal source (your own data class, a config file, a P2P wire body you produced yourself) | `deserialize<T>(json)` — strict round-trip with `coerceInputValues` |
| Mixed text + JSON (LLM output, log lines, anything where the JSON might be wrapped in prose or have leading/trailing junk) | `extractJson<T>(input)` — finds the object first, then deserializes |
| You already have a clean JSON string and just want to deserialize | `deserialize<T>(json)` |

The TPipe project convention (validated by operator steering): **when the input could be a blob the LLM produced, default to `extractJson`** — it handles the malformed-output zoo that an LLM realistically emits (missing braces, trailing commas, extra commentary, fences). Don't try to manually escape-nest a JSON literal inside a Kotlin string when the canonical helper does the extraction.

### Canned-response stub design bug surfaced 2026-07-08 (`PumpStationF1PathInjectionTest`)

Real bug from session 2026-07-08. The test's local HTTP stub was hand-rolling the OpenAI Responses wire body as a triple-quoted Kotlin string:

```kotlin
// BROKEN: hand-rolled wire literal, missing required fields, escape nesting nightmare
"""{"output":[{"content":[{"text":"{\"pathName\":\"report\",\"pathSchema\":\"\"}","type":"output_text"}],"role":"assistant","type":"message"}]}"""
```

Problems:
- The `\"` escapes inside `text` collapsed into raw `"` on the wire, breaking the outer JSON (unbalanced inner quotes terminated the string early, leaving the outer `{...}` structurally invalid).
- Required fields `id` and `model` on `OpenAIResponsesResponse` are missing — kotlinx.serialization returns null for them, the parser throws `P2PException("Failed to deserialize ... Deserialization returned null")`.

**The canonical fix:** build a real instance via the data class hierarchy and serialize via `com.TTT.Util.serialize()`. The data class guarantees conformance to the schema the parser expects, by construction:

```kotlin
import com.TTT.Util.serialize
import genericOpenAIPipe.env.OpenAIResponsesContentPart
import genericOpenAIPipe.env.OpenAIResponsesOutputItem
import genericOpenAIPipe.env.OpenAIResponsesResponse

val textJson = """{"pathName":"report","pathSchema":""}"""
val textPart = OpenAIResponsesContentPart.OutputText(text = textJson)
val messageItem = OpenAIResponsesOutputItem.Message(content = listOf(textPart))
val response = OpenAIResponsesResponse(
    id = "stub-id",
    model = "stub-model",
    status = "completed",
    output = listOf(messageItem)
)
val responseJson = serialize(response, true)  // encodedefault = true: emit all wire fields
```

Why `encodedefault = true` here: the receiver is `OpenAIResponsesResponseParser`, which feeds into the production request path. Wire sites need every required field present. The local stub is a *wire* payload, not an LLM-bound prompt — pin defaults on.

## Pitfalls

### Pitfall: Kotlin data-class properties declared in the class body (not the primary constructor) cannot be passed as named constructor arguments

`MultimodalContent` (`Pipe/BinaryContent.kt`) is the canonical example of this pattern in TPipe. Its primary constructor declares 9 fields (lines 118-128), but the class body declares additional properties further down (lines 130-188): `jumpToPipe`, `repeatPipe`, `passPipeline`, `interuptPipeline`, `skipReasoningPipe`, `metadata`, `currentPipe`, `useSnapshot`. None of these are constructor parameters.

**Symptom:** the compiler rejects

```kotlin
MultimodalContent(text = "x", passPipeline = true)   // "No parameter with name 'passPipeline' found"
```

even though `passPipeline: Boolean` is clearly a public `var` on the class. The cause: named-argument syntax only consults the **primary constructor's** parameter list. Class-body properties are settable only via instance access (`someMultimodalContent.passPipeline = true` or `.apply { passPipeline = true }`).

**Incident 2026-07-08 (PumpStationF1PathInjectionTest):** the test used the named-arg form for two `setExecutionFunction` blocks; both compile errors blocked the test source set. Operator correction verbatim: "passPipeline is a real function on that object. Wtf are you smoking? Go dig into TPipe before doing somehtinng like that. At least determine that your output is legit."

**Detection recipe** when seeing "No parameter with name 'X' found" on a class whose `.kt` you haven't read:

```bash
# Find every property declared in the class body of a @Serializable data class.
# Class-body props are declared AFTER the closing `)` of the primary constructor
# and BEFORE the class's first `fun` or `companion object`.
grep -nE '^\s*(var|val)\s+[a-zA-Z]+\s*:' Path/To/Class.kt
```

Then read past the primary constructor's closing `)` to see the full property set. Never conclude an API "doesn't exist" because it wasn't visible in the first constructor block — always grep for the field across the whole file.

**The right idiom for `passPipeline` (and similar class-body flags):**

```kotlin
MultimodalContent(text = "x").apply { passPipeline = true }     // canonical
// or
val content = MultimodalContent(text = "x")
content.passPipeline = true
```

Both are used in production (e.g. `Junction.kt:1287`: `workingContent.passPipeline = true`; `PumpStation.kt:700` documents `apply { passPipeline = true }`). The `apply` form is preferred when you need to set multiple flags inline.

**Applies to ANY data class that mixes primary-constructor fields with class-body flags** (TPipe examples: `MultimodalContent.terminatePipeline` is in the primary constructor, but `MultimodalContent.passPipeline`, `.interuptPipeline`, `.skipReasoningPipe`, `.repeatPipe`, `.metadata`, `.currentPipe`, `.useSnapshot` are class-body). Same pattern likely in custom user data classes.

### Pitfall: `serialize()`'s second parameter is `encodedefault` (lowercase `d`, no separator), not `encodeDefault`

`Util/Util.kt:48`:
```kotlin
inline fun <reified T> serialize(obj: T, encodedefault : Boolean = false): String
```

The parameter name is `encodedefault`, not `encodeDefault`. Calling with a CamelCase named arg is a compile error:

```kotlin
serialize(response, encodeDefault = true)   // "No parameter with name 'encodeDefault' found."
```

Two correct call styles:

```kotlin
serialize(response, true)                    // positional — fine for one-arg sites
serialize(response, encodedefault = true)   // named — explicit at cost-of-typo-risk
```

Incident 2026-07-08 (`PumpStationF1PathInjectionTest`): I called `serialize(response, encodeDefault = true)` (CamelCase) after the comment in this skill at the time said "explicit opt-in". The compiler rejected it. Fix was to drop the named arg (`serialize(response, true)`).

**Mitigation:** when in doubt, use positional form for boolean flags. The skill body and call-site comments should preserve the exact spelling from the source — never assume Kotlin convention (CamelCase param names) overrides the actual declaration.


### Pitfall: `setJsonInput`'s `senddefaults` parameter is DEAD

`Pipe/Pipe.kt:2407` declares:
```kotlin
inline fun <reified T> setJsonInput(json: T, senddefaults: Boolean = true): Pipe {
    ensureJsonPromptInjectionEnabled()
    this.jsonInput = examplePromptFor(T::class)   // ignores `json` and `senddefaults`!
    return this
}
```

The `json` and `senddefaults` arguments are NEVER USED. The function only calls `examplePromptFor(T::class)` which generates a synthetic schema via `JsonSchemaGenerator` — a separate path from `com.TTT.Util.serialize()`. `setJsonOutput` at line 2461 has the same dead-parameter pattern.

**Implication for audit:** when classifying a call site as "OPT-OUT / LEAKS DEFAULTS / PROMPT-INJECTION-EXAMPLE", a `setJsonInput(someClass)` call is NOT instance serialization — it's a schema-example call and falls into the PROMPT-INJECTION-EXAMPLE bucket regardless of any default flip. Don't waste audit time on these.

**Implication for fixes:** if you ever want to actually skip defaults in `setJsonInput`'s output, you have to modify `examplePromptFor` / `JsonSchemaGenerator` directly, not the `senddefaults` parameter.

### Pitfall: `coerceInputValues` makes round-trips safe even for null-default fields

`deserialize()` at `Util/Util.kt:100-136` sets `coerceInputValues = true` (line 108). This means:

- A field `var field: String = "default"` that is missing from input JSON gets the Kotlin default value back on read.
- A field `var field: Int? = null` that is missing from input JSON becomes `null` (not the Kotlin default — `coerceInputValues` only coerces when the field is missing AND the receiver type has a sensible default).
- Round-trip equality (`serialize(x) → deserialize<T>(...) → == x`) holds for data classes whose defaults are simple values (strings, numbers, booleans, empty collections, data class instances with all-default state).

This is what makes the Layer 2 default flip safe. Without `coerceInputValues = true`, every Kotlin-to-Kotlin round-trip (file persistence, P2P wire, DistributionGrid, MemoryClient↔MemoryServer) would break.

**What this means for the audit:** when classifying a call site, you don't need to trace its receiver in detail if you can confirm:
1. The receiver is a TPipe `deserialize<...>()` call (Kotlin), AND
2. The data class has simple defaults (no custom getters, no lateinit, no `init {}` blocks that mutate state from defaults)

Both conditions met → safe. The only sites that need explicit pinning are receivers that are NOT Kotlin `deserialize<...>()` calls — i.e., the 2 P2PRegistry external-wire sites.

### Pitfall: `null` defaults are encoded as JSON `null` even with `encodedefault=false`

The `encodedefault` parameter controls whether fields equal to their Kotlin default are written. It does NOT control whether `null` values are written — those are controlled by `explicitNulls`. TPipe's `serialize()` sets `explicitNulls = false` (Util.kt:55), which means explicit `null` values in the object are DROPPED. So:

- `field: String = "default"` with current value `"actual"` → written
- `field: String = "default"` with current value `"default"` → NOT written (with encodedefault=false)
- `field: String? = null` with current value `null` → NOT written (explicitNulls=false)
- `field: String? = null` with current value `"x"` → written as `"x"`

If a downstream receiver expects `"field": null` in the JSON (a non-Kotlin client that distinguishes absent-vs-null), the `explicitNulls = false` setting in `serialize()` will silently break it. The 2 P2PRegistry pins use `encodedefault = true` but that doesn't help with this — they're relying on the receiver either being lenient (the Kotlin test agents are) or genuinely tolerating absent-null fields. If you ever add a wire site to a strict external client, you may also need to override `explicitNulls = true` via a custom Json instance — `serialize()` doesn't expose that knob.

### Pitfall: explicit `encodedefault = false` callers are now redundant but should NOT be removed

After the 2026-06-22 fix, every `serialize(x, encodedefault = false)` caller (GenericOpenAI/Anthropic/OpenAIResponses request serializers, OpenRouterPipe, PumpStation, etc.) is passing the same value as the new default. **Don't remove them in a cleanup pass.** They serve as:
1. Self-documentation at call sites where defaults-being-omitted is a load-bearing property
2. A safety net if someone ever re-flips the default
3. Pinning for tests / snapshots that compare serialized output byte-for-byte

Keep them as-is. The "redundant" argument is a stylistic preference, not a correctness fix.

### Pitfall: required-on-the-wire discriminator fields can be silently dropped

Some data class fields look like normal defaults but the **remote API requires them to be present in the JSON** — even if the value is "the default". The `encodedefault = false` Layer 2 default silently drops these.

**Status (2026-06-24 update):** BUG FIXED. Applied `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` annotation on `ToolDefinition.type` at `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/ToolDefinition.kt:17`. Verified by re-running `MiniMaxFeaturesLiveTest.testFunctionCallingOpenAIChatMode` against live MiniMax endpoint — the test now passes (was previously `@Disabled` with this pitfall as the cause). The fix is contained to one line of source code plus the import; no call sites needed to change.

**Concrete example (real bug, surfaced and fixed 2026-06-24 by `MiniMaxFeaturesLiveTest`):**

`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/ToolDefinition.kt`:
```kotlin
@Serializable
data class ToolDefinition(
    val type: String = "function",   // <-- default looks innocuous
    val function: FunctionSchema
)
```

When a user calls `pipe.setTools(listOf(ToolDefinition(function = ...)))` (omitting `type` to use the default), the wire payload becomes:
```json
{"function": {"name": "get_weather", "description": "...", "parameters": {...}}}
```

The `"type": "function"` key is dropped because `type` matches its Kotlin default. **MiniMax rejects this** with `"invalid tool type:  (2013)"` — it requires the discriminator field to be present. OpenAI and most other providers tolerate the missing field, which is why this bug stayed hidden through unit tests.

**The fix (one-liner):**
```kotlin
import kotlinx.serialization.EncodeDefault
@Serializable
data class ToolDefinition(
    @EncodeDefault(EncodeDefault.Mode.ALWAYS)
    val type: String = "function",
    val function: FunctionSchema
)
```

**Three ways to fix, in order of preference:**

1. **Per-field annotation on the discriminator:** `@EncodeDefault(EncodeDefault.Mode.ALWAYS)` on `type` forces it to be written regardless of value.
   ```kotlin
   import kotlinx.serialization.EncodeDefault
   @Serializable
   data class ToolDefinition(
       @EncodeDefault(EncodeDefault.Mode.ALWAYS)
       val type: String = "function",
       val function: FunctionSchema
   )
   ```
2. **Per-call-site override** of `serialize()`:
   ```kotlin
   serialize(ToolDefinition(function = ...), encodedefault = true)
   ```
   This requires the call site to know `ToolDefinition` is special — error-prone.
3. **Remove the default** and force callers to pass `type` explicitly. Brittle, not recommended.

**Audit recipe — find other data classes that might have this bug:**

```bash
# Look for @Serializable data classes with defaulted String fields
# where the field name is `type`, `kind`, `role`, `format`, `mode`, etc.
# — common discriminator names that the wire API may require.
grep -rn "val type: String = \"" --include="*.kt" \
  /home/cage/Desktop/Workspaces/TPipe/TPipe
```

Then for each match, ask: "if the field is omitted from the JSON, does the receiver break?" For OpenAI-compatible providers and most public APIs, `type` defaults to `function` and they're lenient. For stricter APIs (MiniMax's tool calls, Anthropic's `cache_control.type`, etc.) the field is required.

**Live test pattern that surfaced this bug:** `MiniMaxFeaturesLiveTest.testFunctionCallingOpenAIChatMode` (now PASSING as of 2026-06-24 after the `@EncodeDefault` fix; was previously `@Disabled` with comment pointing at this pitfall). Re-enable is no longer needed — the test now passes against live MiniMax.

### Pitfall: `@JsonClassDiscriminator` must be on sealed response types that emit a `type` field
kotlinx.serialization sealed-class polymorphism needs explicit configuration to dispatch on a discriminator field like `"type"`. Without it, the default is to dispatch on the class FQN — which never matches the JSON.

**Status (2026-06-24 update):** BUG FIXED. Three changes to `AnthropicMessagesResponse.kt`:
1. Added `@JsonClassDiscriminator("type")` on the sealed class `ResponseContentBlock` (line 50)
2. Added `@SerialName("text")` on `TextContentBlock` data class
3. Added `@SerialName("thinking")` on `ThinkingBlock` data class

Also hardened Json config in `ResponseParser.kt:39-51` (added `ignoreUnknownKeys = true`, `isLenient = true`, `coerceInputValues = true`) to mirror `Util.serialize()` defaults — forward-compatible against future Anthropic/MiniMax content block types.

Verified by re-running `MiniMaxFeaturesLiveTest.testPromptCachingAnthropicMode` against live MiniMax endpoint — the test now passes (was previously `@Disabled` with this pitfall as the cause). The model returned `"The capital of France is **Paris**."` cleanly through the now-discriminating parser.

**Concrete example (real bug, surfaced and fixed 2026-06-24 by `MiniMaxFeaturesLiveTest`):**

`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/AnthropicMessagesResponse.kt`:
```kotlin
@Serializable
sealed class ResponseContentBlock
{
    @Serializable
    data class TextContentBlock(
        val type: String = "text",
        val text: String
    ) : ResponseContentBlock()

    @Serializable
    data class ThinkingBlock(
        val type: String,            // <-- expects "type":"thinking" on the wire
        val thinking: String
    ) : ResponseContentBlock()
}
```

When the MiniMax /anthropic endpoint returns a response containing a thinking block (`{"type": "thinking", "thinking": "...", "signature": "..."}`), kotlinx.serialization fails with `"Serializer for subclass 'thinking' is not found in the polymorphic scope of 'ResponseContentBlock'"`. The sealed class has no `@JsonClassDiscriminator("type")` annotation, so the dispatcher doesn't know to look at the `type` field.

**The fix (three annotations):**
```kotlin
import kotlinx.serialization.json.JsonClassDiscriminator

@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
@Serializable
@JsonClassDiscriminator("type")
sealed class ResponseContentBlock
{
    @Serializable
    @SerialName("text")
    data class TextContentBlock(...) : ResponseContentBlock()

    @Serializable
    @SerialName("thinking")
    data class ThinkingBlock(...) : ResponseContentBlock()
}
```

**Why both `@JsonClassDiscriminator` AND `@SerialName` are needed:**
- `@JsonClassDiscriminator("type")` on the sealed class tells kotlinx.serialization WHICH JSON field to read for dispatch (the `"type"` field).
- `@SerialName("text")` / `@SerialName("thinking")` on the subclasses tell kotlinx.serialization WHAT value of that field maps to which subclass. Without these, the default serial name is the class FQN (`"genericOpenAIPipe.api.AnthropicMessagesResponse.ThinkingBlock"`) which never matches the wire JSON's `"thinking"` value.

This is the two-annotation dance that makes polymorphic sealed-class deserialization work for JSON discriminators.

> **STREAMING-PATH REVISION (2026-06-25, REVISED 2026-06-25 round 2)**: the earlier note that "the streaming path handles thinking deltas separately and didn't need this fix" was CORRECT only at the data-model layer — `AnthropicDelta.ThinkingDelta` exists with `@SerialName("thinking_delta")`. It was WRONG at the application layer — the production caller (`GenericOpenAIPipe.executeStreamingDirect` Anthropic branch and `executeStreamingAnthropic` Ktor branch) did NOT actually use the `AnthropicSseParser` wrapper. They called `deserialize<AnthropicStreamEvent>` directly, which returns null for every Anthropic SSE event for three structural reasons that `@JsonClassDiscriminator` alone CANNOT fix: (1) the annotation is informational metadata that `Json {}` config must opt into, (2) the subclasses don't share a uniform discriminator field shape at the outer level, and (3) `ContentBlockDelta(val chunk: AnthropicStreamingChunk)` doesn't match the wire shape (wire has `index`/`delta` outer, not `chunk` nested). The REAL fix at the streaming-path application layer is to replace the direct `deserialize` call with `AnthropicSseParser.parseAnthropicLine` — the wrapper at `SseParser.kt:197` manually dispatches by the outer `type` field and is the canonical streaming parser. See `tpipe-generic-openai` skill pitfall "MiniMax-M2.7 Anthropic streaming — REAL root cause is sealed-class dispatch" for the full breakdown. The moral: when a sealed class doesn't share a uniform outer-shape with its wire JSON, polymorphic dispatch via `@JsonClassDiscriminator` cannot rescue it — use a wrapper that manually dispatches by the discriminator value, or restructure the class to match the wire shape.

**Audit recipe — find other sealed response classes that might need the discriminator:**

```bash
# Find all sealed classes annotated @Serializable — these are the candidates
grep -rn "sealed class" --include="*.kt" \
  /home/cage/Desktop/Workspaces/TPipe/TPipe | grep -i Serializable

# Cross-check with response DTOs that handle polymorphic content blocks
grep -rn "List<.*ContentBlock>\|List<.*ResponseBlock>" --include="*.kt" \
  /home/cage/Desktop/Workspaces/TPipe/TPipe
```

Then for each match, ask: "does the wire JSON include a discriminator field like `type`, `kind`, or `event` that the receiver needs to dispatch on?"

**Live test pattern that surfaced this bug:** `MiniMaxFeaturesLiveTest.testPromptCachingAnthropicMode` (now PASSING as of 2026-06-24 after the `@JsonClassDiscriminator` fix; was previously `@Disabled` with comment pointing at this pitfall). Re-enable is no longer needed — the test now passes against live MiniMax.

**Live test pattern that surfaced the streaming-side twin:** `AnthropicStreamingLiveTest.testAnthropicStreamingLive` (FAILING as of 2026-06-25, observed during a live-test run against MiniMax-M2.7 with prompt `"Say hello in 5 words."`). Symptom: `Response: []`, `Total chunks: 0`. The trace shows `streaming: true` and HTTP 200, but the SSE parser produces nothing. The `text_delta` content block is on the wire — proven by direct curl against `https://api.minimax.io/anthropic/v1/messages` returning `{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello there, how are you?"}}` — but `deserialize<AnthropicStreamEvent>` returns null because the discriminator is missing.

**Diagnostic technique (writes-the-bug-in-30-seconds pattern)**: when a streaming response is unexpectedly empty, write a focused JUnit test that calls `Json.decodeFromString<T>(wirePayload)` with **NO try/catch** and prints the throwable. The exception type and message pinpoint the root cause in one run. Pattern:

```kotlin
@Test fun diagnose() {
    val json = Json { ignoreUnknownKeys = true; isLenient = true }
    val payload = """{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}"""
    try {
        val result: AnthropicStreamEvent = json.decodeFromString(payload)
        println("OK -> ${result::class.simpleName}")
    } catch (e: Throwable) {
        println("THREW ${e::class.qualifiedName}: ${e.message?.take(300)}")
    }
}
```

For the streaming-side bug this prints:
`THREW kotlinx.serialization.json.internal.JsonDecodingException: Unexpected JSON token at offset 0: Serializer for subclass 'content_block_delta' is not found in the polymorphic scope of 'AnthropicStreamEvent'`

— the discriminator-miss message is unambiguous. **The first place this fails is the first place the bug exists.**

**Why the production caller never sees the exception:** `com.TTT.Util.deserialize<T>()` at `TPipe/src/main/kotlin/Util/Util.kt:100-136` has its own internal try/catch that calls `repairAndDeserialize` on failure, and returns `null` if BOTH attempts fail. So callers that wrap `deserialize` in `try { ... } catch (_: Exception) { null }` have **dead-code catch blocks** — the exception is consumed inside `deserialize` and never propagates. The streaming parser at `GenericOpenAIPipe.kt:955-957` has exactly this dead-defense pattern. Defensive fix: add a `System.err.println` inside `Util.deserialize`'s catch block (line 130-135) so future "deserialize returned null" bugs surface at first run instead of after a 30-second gradle test round-trip.

### Pitfall: `Pipe.init()` unconditionally clobbers `injectHttpClientForTest()` mocks

**Status (2026-06-24):** PRE-EXISTING BUG, not yet fixed. Documented here for future cleanup.

The `GenericOpenAIPipe` test helpers `injectHttpClientForTest()`, `initForTest()`, and `generateTextForTest()` look like they let you swap in a `MockEngine` for unit testing, but `initForTest()` calls `init()` which **unconditionally** assigns a real `HttpClient(CIO)` at `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:427`:

```kotlin
override suspend fun init(): Pipe
{
    super.init()
    // ...
    httpClient = HttpClient(CIO)   // <-- CLOBBERS any mock injected before init()
    { install(HttpTimeout) { ... } }
    // ...
}
```

So the test pattern in `OpenAIResponsesPipeDispatchTest.kt` is **broken**:
```kotlin
val pipe = GenericOpenAIPipe()
    .setApiKey("mock-key")
    .setBaseUrl("https://mock.local/v1")
    // ...
pipe.injectHttpClientForTest(HttpClient(mockEngine))   // sets mock
pipe.initForTest()                                      // calls init() → CLOBBERS mock
try {
    val text = pipe.generateTextForTest("hi")           // uses real CIO, tries to dial mock.local
    // → throws java.nio.channels.UnresolvedAddressException
}
```

**Two pre-existing failing tests in `OpenAIResponsesPipeDispatchTest` as of 2026-06-24:**
- `testNonStreamingMockEngineRoundTrip()` — FAILED with `UnresolvedAddressException`
- `testStreamingMockEngineAccumulatesTextAndTerminatesOnCompleted()` — FAILED with same error

Verified pre-existing by `git stash` + re-run: both fail identically without the 2026-06-24 changes.

**Detection:** any new GenericOpenAIPipe test that calls `pipe.injectHttpClientForTest(mockEngine)` then `pipe.initForTest()` will fail with `UnresolvedAddressException` when the mock host (e.g. `mock.local`) isn't resolvable. The error masks the test's actual intent.

**Two ways to fix, in order of preference:**

1. **Make `init()` respect a pre-injected client** — wrap the `httpClient = HttpClient(CIO)` assignment in a `if (httpClient == null) { ... }` guard. The test injection becomes a real "use this instead" override.

2. **Add a separate `initForTestNoHttpClient()` method** that skips the HTTP client creation entirely. Tests call that instead of `initForTest()` after `injectHttpClientForTest()`.

Option 1 is cleaner because it generalizes — production code that already constructed a client and just wants validation/trace init wouldn't have to throw it away.

**Why this didn't bite earlier:** the existing test suite was dominated by live tests against real MiniMax endpoints (where `init()` creating a real CIO client is correct), and the few unit tests that used `MockEngine` worked because they accidentally relied on a prior code state where `init()` didn't unconditionally overwrite. The regression happened silently and was masked by the test failure mode (`UnresolvedAddressException` reads as "you have a bad URL" rather than "the test infrastructure is broken").

## Subagent audit pattern

When changing a default that has 100+ callers (like the Layer 2 `encodedefault` flip), delegate the exhaustive caller audit to a subagent via `delegate_task`. The subagent should:

1. Grep for all imports and call sites of the target function across every TPipe submodule
2. Read the function definition to understand the parameter semantics
3. For each call site, classify it into one of: `OPT-OUT` (explicit false), `OPT-IN` (explicit true), `LEAKS DEFAULTS` (no arg, default behavior), `NON-INSTANCE-SERIALIZATION` (e.g., `setJsonInput` which is dead-parameter), `INTERNAL RECONSTRUCTION` (e.g., repair helpers with their own Json instance)
4. For each `LEAKS DEFAULTS` site, determine if it's a wire format / LLM payload / tracing / file persistence / debug print destination
5. Identify any site where the receiver is non-Kotlin and could break
6. Return a structured report with file:line, classification, and risk level

The 2026-06-22 audit took one subagent task (50 tool calls, 250s wall time) to fully classify 257 callers across all 8 TPipe modules. The result identified the 2 P2PRegistry pins that needed explicit `encodedefault = true` and confirmed the rest were safe via `coerceInputValues`.

**Why delegate instead of doing it inline:** the agent's context window can't hold 257 file:line references plus the data class definitions plus the round-trip pairing analysis. The subagent has its own context and returns only the structured summary.

## Post-implementation review checklist

After making any encoding/format/wire-contract change in TPipe, run this checklist BEFORE reporting completion. The user expects a structured "did we miss any cases that absolutely did need the old behavior?" report.

1. **Prove the negative.** Re-grep for every explicit `encodedefault = true` caller in the codebase. There should be exactly the pinned sites — no others. If you find a new `encodedefault = true` outside the pins, that site may now be inconsistent.
2. **Re-grep for `setJsonInput` / `setJsonOutput` call sites.** Confirm none of them serialize a real instance — they're all schema-example calls (see Pitfall above). If you find one that does, the audit missed it.
3. **Re-grep for HTTP/Stdio request body construction (`body = ...`, `requestBody = ...`).** Every such body that uses `serialize(...)` needs verification that the receiver tolerates missing defaults. Kotlin-to-Kotlin = safe. Non-Kotlin = pin.
4. **Re-grep for `setJsonInput` and `examplePromptFor`** to confirm they're routed through `JsonSchemaGenerator` (Layer 1) and not `serialize()` (Layer 2). They should be.
5. **Verify the dead parameters are still dead.** `setJsonInput`'s `senddefaults`, `setJsonOutput`'s `json` argument — confirm no one is using them as if they worked (in case a future refactor accidentally wires them up).
6. **Run the test suite** and separate environmental failures (Ollama model not loaded, network unavailable) from genuine regressions. Document both.
7. **Re-read the diff.** 3 source lines for this fix. If your fix is larger, ask whether the scope creep is justified.
8. **Report findings as a categorized list** — what was changed, what was verified unaffected, what was pinned, what the test results showed, edge cases found during the review. The user will ask "did we get them all?" — the answer is the report.

## See Also

- `references/default-encoding-fix.md` — the 2026-06-22 audit and fix (file:line catalog of all serialize() callers, the 2-pin pattern, the round-trip safety analysis)
- `tpipe-pipeline-patterns` — pipe and container configuration
- `tpipe-generic-openai` — request serializer classes in GenericOpenAIPipe (already correct: all explicit `encodedefault = false`)
- `tpipe-trace-parser` — for parsing TPipe trace files which contain the serialized context payloads