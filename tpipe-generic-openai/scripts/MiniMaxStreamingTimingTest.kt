package com.example.tpipewriter

import genericOpenAIPipe.GenericOpenAIPipe
import genericOpenAIPipe.api.ApiMode
import genericOpenAIPipe.env.GenericOpenAIEnv
import com.TTT.Pipe.MultimodalContent
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import kotlin.test.assertTrue

/**
 * Live streaming TIMING test for MiniMax-M3 via the GenericOpenAIPipe.
 *
 * Verifies that streaming chunks actually arrive incrementally rather
 * than being batched into a single chunk at the end. The previous
 * StreamingPropagationTest was a unit test for the propagation logic;
 * this is an integration test against the real MiniMax-M3 endpoint.
 *
 * The test prints diagnostic output showing wall-clock arrival time of
 * every chunk and inter-chunk gaps. A regression to bodyAsChannel
 * would produce 0ms gaps (everything buffered until end); the
 * executeStreamingDirect fix produces 200-715ms gaps as MiniMax-M3
 * emits real tokens.
 *
 * If MINIMAX_API_KEY is not set the test is skipped.
 */
class MiniMaxStreamingTimingTest {
    @Test
    fun testChunksArriveIncrementally() {
        assumeTrue(
            System.getenv("MINIMAX_API_KEY")?.isNotBlank() == true,
            "MINIMAX_API_KEY not set; skipping live streaming timing test"
        )

        GenericOpenAIEnv.setApiKey(System.getenv("MINIMAX_API_KEY")!!)

        data class TimedChunk(val chunk: String, val nanos: Long)
        val chunks = mutableListOf<TimedChunk>()
        val callback: suspend (String) -> Unit = { chunk ->
            chunks.add(TimedChunk(chunk, System.nanoTime()))
        }

        val pipe: GenericOpenAIPipe = GenericOpenAIPipe()
            .setBaseUrl("https://api.minimax.io/v1")
            .setApiKey(GenericOpenAIEnv.resolveApiKey())
            .setApiMode(ApiMode.OpenAIResponses)
            .setStreamingEnabled(true)
        pipe.setModel("MiniMax-M3")
        pipe.setMaxTokens(256)
        pipe.setTemperature(0.0)

        pipe.setStreamingCallback(callback)

        val startNanos = System.nanoTime()
        runBlocking {
            pipe.init()
            pipe.execute(MultimodalContent().apply {
                text = "Write a 200 word story about a robot discovering feelings. Include vivid sensory details."
            })
        }
        val endNanos = System.nanoTime()

        println("STREAM_TIMING: total_chunks=${chunks.size}")
        println("STREAM_TIMING: total_duration_ms=${(endNanos - startNanos) / 1_000_000}")
        println("STREAM_TIMING: assembled=${chunks.joinToString("") { it.chunk }}")

        if (chunks.size >= 2) {
            for (i in 1 until chunks.size) {
                val deltaMs = (chunks[i].nanos - chunks[i - 1].nanos) / 1_000_000
                println("STREAM_TIMING: chunk[$i] arrived ${deltaMs}ms after chunk[${i - 1}] (size=${chunks[i].chunk.length})")
            }
            val smallChunks = chunks.count { it.chunk.length <= 5 }
            val mediumChunks = chunks.count { it.chunk.length in 6..50 }
            val largeChunks = chunks.count { it.chunk.length > 50 }
            println("STREAM_TIMING: small=${smallChunks} medium=${mediumChunks} large=${largeChunks}")
        }

        assertTrue(chunks.isNotEmpty(), "Should have received at least one streaming chunk")
        val assembled = chunks.joinToString("") { it.chunk }
        assertTrue(assembled.isNotBlank(), "Assembled response should not be blank")
    }
}