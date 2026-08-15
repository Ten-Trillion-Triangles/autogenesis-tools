// templates/hello-pipe.kt
//
// Copy-and-modify starter for a STATELESS custom Pipe subclass.
// No external LLM backend — generateText just echoes. Useful as a starting
// point for testing pipeline mechanics, or for pipes that compute without
// an LLM (regex extractors, rule-based validators, deterministic
// transformers).
//
// What you MUST implement:
//   - generateText(prompt): String
//   - generateContent(content): MultimodalContent
//   - truncateModuleContext(): Pipe   (stub: return this)
//
// What you MAY override:
//   - init(): Pipe                    (only if you have setup to do)

package hello

import com.TTT.Pipe.MultimodalContent
import com.TTT.Pipe.Pipe
import kotlinx.coroutines.runBlocking

class HelloPipe(
    private val prefix: String = "echo: ",
) : Pipe() {

    init { setModel("hello-pipe-v1") }

    override suspend fun generateText(promptInjector: String): String =
        prefix + promptInjector

    override suspend fun generateContent(content: MultimodalContent): MultimodalContent =
        MultimodalContent(text = generateText(content.text))

    override fun truncateModuleContext(): Pipe = this
}

fun main() = runBlocking {
    val pipe = HelloPipe(prefix = "[hello] ")
    pipe.setTemperature(0.0)         // ignored by HelloPipe, kept to demonstrate fluent config
    pipe.init()
    val response = pipe.execute(MultimodalContent(text = "Hello, world!"))
    println(response.text)           // → [hello] Hello, world!
}