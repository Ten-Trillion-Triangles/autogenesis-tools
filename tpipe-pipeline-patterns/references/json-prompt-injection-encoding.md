# TPipe JSON Prompt Injection & Default-Encoding Footguns

What every TPipe user needs to know about how JSON schemas become prompts, and where defaults silently inflate your token bill.

## TL;DR

TPipe's `setJsonInput(T)` / `setJsonOutput(T)` injects a **fully-populated schema example** into the LLM prompt, including every default value. The `serialize(obj)` function used elsewhere defaults to `encodeDefaults = true`. Both are documented, but both are footguns for cost-sensitive or schema-sensitive callers.

## Prompt-injection path (the LLM-facing path)

`setJsonOutput(Legal?())` does NOT serialize your instance. It calls `examplePromptFor(Legal?::class)` (`TPipe/src/main/kotlin/Util/Schema.kt:953-968`), which uses `JsonSchemaGenerator` to build a synthetic example JSON showing the LLM what shape to emit.

`JsonSchemaGenerator.exampleForDescriptor` (`Schema.kt:200-255`) walks every property of the class descriptor and emits a placeholder:

| Kotlin type | Placeholder emitted |
|---|---|
| `String` | `"example_string"` |
| `Boolean` | `false` |
| `Int / Long / Short / Byte` | `0` |
| `Float / Double` | `0.0` |
| `Enum` | first enum value (e.g. `"Land"`) |
| `List<T>` | `[<element placeholder>]` |
| `Map<K,V>` | `{"example_key": <value placeholder>}` |

Then `formatExampleWithLegend` (`Schema.kt:157-189`) renders the example with a hardcoded:

```kotlin
val jsonFormatter = Json {
    this.prettyPrint = prettyPrint
    encodeDefaults = true  // Schema.kt:163
}
```

So the LLM is shown:

```json
{
    "isLegal": false,
    "changesToMake": "example_string",
    "captureAttempted": false
}
```

...even when `isLegal` has the Kotlin default `false`. The KDoc at `Pipe.kt:2401-2406` and `Pipe.kt:2456-2458` documents this as intentional — "This ensures the entire json method is made available to the AI model." Fine for prompt-injection, but two side effects:

1. The LLM learns that empty fields are "expected output" and faithfully echoes them back. Verified in real traces: when the schema had `changesToMake: String = ""`, the LLM emitted `"changesToMake": ""` in its response even when the field was semantically irrelevant.
2. Defaults drive token cost on every turn.

## Dead-parameter footgun: `setJsonInput`'s `senddefaults`

`Pipe.kt:2407` declares:

```kotlin
inline fun <reified T> setJsonInput(json: T, senddefaults: Boolean = true): Pipe {
    ensureJsonPromptInjectionEnabled()
    this.jsonInput = examplePromptFor(T::class)   // ← senddefaults ignored
    return this
}
```

The `senddefaults` parameter is **never read**. The behavior is hardcoded inside `examplePromptFor` -> `formatExampleWithLegend` (`Schema.kt:163`). Writing `setJsonInput(Legal?(), senddefaults = false)` compiles, runs, and does nothing. Misnamed too (`senddefaults` instead of `sendDefaults`).

## `serialize()` instance path (the runtime path)

`Util.kt:48-75`:

```kotlin
inline fun <reified T> serialize(obj: T, encodedefault : Boolean = true): String {
    val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = encodedefault   // <- defaults to TRUE
        ...
    }
    return try { json.encodeToString(obj) } catch (e: Exception) { "" }
}
```

Default is `true`. Every caller that writes bare `serialize(someObj)` emits all default-valued fields. Caller survey in `TPipe/src/main/kotlin/Pipe/Pipe.kt`:

- **Leak defaults** (no second arg): lines 4937, 4944, 4957, 5762, 5763, 5815, 5845, 5966, 5972, 6146, 7218, 7267, 7358, 7365 — these serialize context windows, mini-bank snapshots, and todo/task objects into trace metadata and prompt text.
- **Opt out** (`encodedefault = false`): lines 1733, 1777, 2013, 2059, 2138, 2169, 6730 — these are P2P/ConverseHistory internal paths. Plus `Util.kt:81-84` `serializeConverseHistory` which explicitly calls out: "use the compact form so default-valued history fields do not leak into prompt payloads or traces."

If you're building a caller that serializes large context objects and notice `"field": ""` / `"field": 0` bloat in trace metadata, this is why. Pass `encodedefault = false` explicitly, or wrap a project-side helper that does.

## Pattern: when to flip defaults off

| Caller | Recommended `encodeDefaults` |
|---|---|
| Schema example shown to LLM (prompt injection) | `true` (current behavior, intentional) |
| Serializing context windows / mini-banks into trace metadata | `false` — trace already shows what was set |
| Serializing object into a prompt payload the LLM will read and act on | `false` — don't waste tokens on `""` and `false` |
| Serializing the LLM's response back to a Kotlin object | N/A — use `deserialize()` which is lenient by design |
| Logging/debug snapshots | `false` — compact logs are easier to read |

## Where to look in the source

| File | Lines | What |
|---|---|---|
| `TPipe/src/main/kotlin/Util/Util.kt` | 48-75 | `serialize(obj, encodedefault = true)` |
| `TPipe/src/main/kotlin/Util/Util.kt` | 81-84 | `serializeConverseHistory` — opt-out example |
| `TPipe/src/main/kotlin/Util/Schema.kt` | 51-189 | `JsonSchemaGenerator` class + `formatExampleWithLegend` with `encodeDefaults = true` hardcoded at 163 |
| `TPipe/src/main/kotlin/Util/Schema.kt` | 200-255 | `exampleForDescriptor` — placeholder per type |
| `TPipe/src/main/kotlin/Util/Schema.kt` | 953-968 | `examplePromptFor` entry points |
| `TPipe/src/main/kotlin/Pipe/Pipe.kt` | 2400-2412 | `setJsonInput(T, senddefaults)` — `senddefaults` is dead |
| `TPipe/src/main/kotlin/Pipe/Pipe.kt` | 2454-2466 | `setJsonOutput(T)` — KDoc documents the encode-defaults behavior |