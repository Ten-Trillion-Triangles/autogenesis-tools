// templates/hello-ollama-pipe.kt
//
// Copy-and-modify starter for an Ollama-backed custom Pipe subclass.
// Subclasses Pipe directly to sidestep the OllamaPipe.generateText wire-
// format bug (OllamaPipe.generateText uses setJsonInput which returns a
// schema example instead of the serialized payload — Ollama responds
// {"error":"format must be json"}).
//
// Tested against:
//   - ollama serve on 127.0.0.1:11434
//   - tinyllama (pulled via `ollama pull tinyllama`)
//
// To run:
//   1. Drop this file into TPipe-Ollama/src/main/kotlin/hello/
//   2. Add a test under TPipe-Ollama/src/test/kotlin/hello/HelloWorldTest.kt
//      that calls pipe.execute(MultimodalContent(text = "Hello, world!"))
//   3. ./gradlew :TPipe-Ollama:test --tests "hello.HelloWorldTest"

package hello

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

    // No client construction needed for Ollama. Override only if you want
    // to pre-warm a connection or validate the server here.
    override suspend fun init(): Pipe = this

    // Abstract on Pipe. Stateless pipes return `this`.
    override fun truncateModuleContext(): Pipe = this

    override suspend fun generateText(promptInjector: String): String {
        val payload = JsonObject(
            mapOf(
                "model"  to JsonPrimitive(model),
                "prompt" to JsonPrimitive(promptInjector),
                "stream" to JsonPrimitive(false),
            )
        )
        val url = "http://$host:$port/api/generate"
        val raw = httpPost(url, Json.encodeToString(JsonObject.serializer(), payload))
        val parsed = Json.parseToJsonElement(raw) as JsonObject
        return parsed["response"]?.jsonPrimitive?.content ?: raw
    }

    override suspend fun generateContent(content: MultimodalContent): MultimodalContent =
        MultimodalContent(text = generateText(content.text))
}

fun main() = runBlocking {
    val pipe = HelloOllamaPipe(modelName = "tinyllama")
    pipe.setSystemPrompt("You are a friendly assistant. Keep replies short.")
    pipe.setUserPrompt("User says:")
    pipe.setTemperature(0.7)

    pipe.init()

    val prompt = "Hello, world! Respond in one sentence."
    val response: MultimodalContent = pipe.execute(MultimodalContent(text = prompt))
    println("PROMPT  : $prompt")
    println("RESPONSE: ${response.text}")
}