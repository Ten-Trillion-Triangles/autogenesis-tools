# Custom Pipe Subclass — Verified Hello-World Recipe

What every TPipe user needs to know when writing their own `Pipe` subclass. The TPipe docs (`Docs/getting-started/first-steps.md`) show `BedrockPipe` usage but don't document what a custom subclass must implement. This is the verified, runnable recipe.

## TL;DR

Subclassing `com.TTT.Pipe.Pipe` requires exactly **three overrides** (and optionally one more for non-trivial setup):

| Method | Signature | Required? | Purpose |
|---|---|---|---|
| `generateText` | `abstract suspend fun generateText(promptInjector: String): String` | YES | Run the model and return text |
| `generateContent` | `abstract suspend fun generateContent(content: MultimodalContent): MultimodalContent` | YES | Same, but accept the multimodal payload |
| `truncateModuleContext` | `abstract fun truncateModuleContext(): Pipe` | YES | Stub for context-window truncation (returns `this` for stateless pipes) |
| `init` | `open suspend fun init(): Pipe` | optional | Override only if you have provider setup (clients, caches, etc.) |

Source: `TPipe/src/main/kotlin/Pipe/Pipe.kt` — verified in this repo's checkout at the time of writing.

## The verified lifecycle (4 steps)

```kotlin
fun main() = runBlocking {
    // 1. Construct
    val pipe = MyPipe(...)

    // 2. Configure (fluent setters inherited from Pipe)
    pipe.setModel("...")
    pipe.setSystemPrompt("...")
    pipe.setTemperature(0.7)
    pipe.setUserPrompt("...")

    // 3. Init (suspend — needs runBlocking or coroutine context)
    pipe.init()

    // 4. Execute (suspend — returns MultimodalContent)
    val response: MultimodalContent = pipe.execute(MultimodalContent(text = "Hello, world!"))
    println(response.text)
}
```

`runBlocking { ... }` is the standard wrapper because `execute()` and `init()` are `suspend`. The framework's own tests use this pattern — see `TPipe-Bedrock/src/test/kotlin/BedrockTest.kt:20` (`runBlocking(Dispatchers.IO) { ... }`).

## Minimum complete Pipe subclass

```kotlin
import com.TTT.Pipe.MultimodalContent
import com.TTT.Pipe.Pipe
import kotlinx.coroutines.runBlocking

class HelloPipe : Pipe() {
    override suspend fun generateText(promptInjector: String): String =
        "echo: $promptInjector"

    override suspend fun generateContent(content: MultimodalContent): MultimodalContent =
        MultimodalContent(text = generateText(content.text))

    override fun truncateModuleContext(): Pipe = this
}
```

That compiles. `init()` is `open` with a default impl in `Pipe`, so you don't have to override it unless you need provider setup.

## Provider subclass — Ollama via hand-built payload

This is the recipe we verified end-to-end against a live local Ollama server:

```kotlin
import com.TTT.Pipe.MultimodalContent
import com.TTT.Pipe.Pipe
import com.TTT.Util.httpPost
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

class HelloOllamaPipe(
    private val host: String = "127.0.0.1",
    private val port: Int = 11434,
    modelName: String = "tinyllama",
) : Pipe() {

    init { setModel(modelName) }

    override suspend fun init(): Pipe = this   // no client to build for Ollama

    override fun truncateModuleContext(): Pipe = this

    override suspend fun generateText(promptInjector: String): String {
        val payload = JsonObject(mapOf(
            "model"  to JsonPrimitive(model),
            "prompt" to JsonPrimitive(promptInjector),
            "stream" to JsonPrimitive(false),
        ))
        val raw = httpPost("http://$host:$port/api/generate",
                           Json.encodeToString(JsonObject.serializer(), payload))
        val parsed = Json.parseToJsonElement(raw) as JsonObject
        return parsed["response"]?.jsonPrimitive?.content ?: raw
    }

    override suspend fun generateContent(content: MultimodalContent): MultimodalContent =
        MultimodalContent(text = generateText(content.text))
}
```

Run it:

```bash
./gradlew :TPipe-Ollama:test --tests "hello.HelloWorldTest"
```

## Gotchas that cost time

### 1. `truncateModuleContext` is abstract

Not in the README. Not in the first-steps doc. The compiler reminds you only when you try to subclass. Add a stub:

```kotlin
override fun truncateModuleContext(): Pipe = this
```

### 2. `OllamaPipe.setIP()` / `setPort()` return `Pipe` supertype

Both methods are declared on `OllamaPipe` with return type `Pipe`, not `OllamaPipe`. This breaks fluent chaining on a typed `OllamaPipe` reference:

```kotlin
// DOES NOT COMPILE — setIP() returns Pipe, .setPort() not on Pipe
val pipe = OllamaPipe()
    .setModel("tinyllama")
    .setIP("127.0.0.1")
    .setPort(11434)     // ← unresolved reference
```

Workarounds:

```kotlin
// Option A: keep the variable, call setters individually
val pipe = OllamaPipe()
pipe.setModel("tinyllama")
pipe.setIP("127.0.0.1")
pipe.setPort(11434)

// Option B: cast back after setIP
val pipe = OllamaPipe()
    .setModel("tinyllama")
    .setIP("127.0.0.1") as OllamaPipe
    .setPort(11434)
```

The same pattern affects any setter declared on a subclass that returns `Pipe` instead of `this`. The base `Pipe` setters (`setModel`, `setTemperature`, `setSystemPrompt`, `setUserPrompt`, `setMaxTokens`, etc.) all return `Pipe` for the same reason — use the variable-keep pattern when chaining.

### 3. `OllamaPipe.generateText()` has a wire-format bug

`OllamaPipe.generateText()` calls:

```kotlin
val inputs = InputParams(model).apply { prompt = promptInjector; ... }
val json = setJsonInput(inputs, false).jsonInput   // ← schema example, not payload
```

`setJsonInput(json, senddefaults)` does **not** serialize the provided object — it sets `this.jsonInput = exampleFor(T::class).toString()`, which is a JSON schema example. Ollama's `/api/generate` rejects this with `{"error":"format must be json"}`.

This is the same root cause documented in `references/json-prompt-injection-encoding.md` (the `senddefaults` dead-parameter footgun). For `OllamaPipe`, the consequence is more severe: `generateText` is currently broken against a live server. The verified workaround is to subclass `Pipe` directly with a hand-built payload, as shown above.

### 4. The first-steps doc is slightly out of date

`Docs/getting-started/first-steps.md` shows `pipe.generateText("Hello, world!")`. The actual signature is `suspend fun generateText(promptInjector: String = ""): String` — the call is valid, but the doc doesn't mention:

- `execute(MultimodalContent): MultimodalContent` (the more useful overload)
- That `init()` is `suspend` (needs `runBlocking`)
- That `truncateModuleContext()` must be implemented for any subclass

When writing custom subclasses, prefer the `execute(MultimodalContent)` form over the string overload — it composes cleanly with `Pipeline` content-flow control flags (`terminate`, `jumpToPipe`, `repeatPipe`, etc.).

### 5. `Pipe` setters return `Pipe`, not the concrete subtype

This is the same root cause as #2 but worth its own note. `Pipe.setModel(...)`, `Pipe.setTemperature(...)`, `Pipe.setSystemPrompt(...)`, etc. all return `Pipe`. If you write:

```kotlin
val pipe: MyPipe = MyPipe().setModel("...")  // ← type mismatch
```

...the compiler complains. Two patterns work:

```kotlin
// Pattern A: keep the variable, drop the type
val pipe = MyPipe()
pipe.setModel("...")
// pipe is inferred as MyPipe here, setters chain fine

// Pattern B: cast or use `apply { }`
val pipe = MyPipe().apply { setModel("..."); setTemperature(0.7) }
```

The `apply { }` pattern is what the framework's own tests use.

## Verifying a custom Pipe works end-to-end

The fastest verification path is a JUnit test that runs against a live local LLM:

```kotlin
package hello

import com.TTT.Pipe.MultimodalContent
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertTrue

class HelloWorldTest {
    @Test
    fun helloWorld() = runBlocking {
        val pipe = HelloOllamaPipe(modelName = "tinyllama")
        pipe.setSystemPrompt("Keep replies short.")
        pipe.setTemperature(0.7)
        pipe.init()
        val response = pipe.execute(MultimodalContent(text = "Hello, world!"))
        println("RESPONSE: ${response.text}")
        assertTrue(response.text.isNotBlank())
    }
}
```

Test result will appear in `TPipe-Ollama/build/test-results/test/TEST-hello.HelloWorldTest.xml` — grep `system-out` for the actual model output.

## See also

- `references/json-prompt-injection-encoding.md` — why `setJsonInput` does what it does (root cause of the OllamaPipe wire-format bug)
- `tpipe-token-budgeting` — `TokenBudgetSettings` for adding token budgets to your custom Pipe
- `templates/hello-pipe.kt` — copy-and-modify starter for a stateless custom Pipe
- `templates/hello-ollama-pipe.kt` — copy-and-modify starter for a working Ollama-backed Pipe