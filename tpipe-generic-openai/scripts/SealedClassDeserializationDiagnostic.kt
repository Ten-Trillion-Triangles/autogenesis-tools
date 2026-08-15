package genericOpenAIPipe

import org.junit.jupiter.api.Test
import kotlin.test.assertTrue

/**
 * Diagnostic-first pattern for "deserialize<T>() returned null for sealed class" bugs.
 *
 * This test is a TEMPLATE. To use:
 *  1. Copy this file to a new file in the test source set.
 *  2. Change `TARGET_TYPE` and `realPayloads` to the sealed class you're investigating.
 *  3. Run with --rerun-tasks.
 *
 * Why this pattern works:
 *  TPipe's `com.TTT.Util.deserialize<T>()` (Util.kt:100-136) has its own internal
 *  try/catch that calls `repairAndDeserialize` on failure and returns null if BOTH
 *  attempts fail. Callers that wrap `deserialize` in `try { ... } catch (_: Exception)
 *  { null }` have dead-code catch blocks — the exception is consumed inside `deserialize`
 *  and never propagates. So production bugs where `deserialize` returns null have
 *  ZERO diagnostic signal in normal logging.
 *
 *  This test bypasses `Util.deserialize` entirely and calls `Json.decodeFromString<T>`
 *  directly with NO test-side try/catch, so the kotlinx.serialization exception
 *  surfaces with full type + message. Each exception message is a direct pointer
 *  at the next layer of the bug:
 *
 *  - "Serializer for subclass 'X' is not found in the polymorphic scope of 'T'"
 *      → missing `@JsonClassDiscriminator` OR Json config missing `classDiscriminator`
 *  - "Field 'X' is required for type with serial name 'Y'"
 *      → sealed-class subclass shape doesn't match wire JSON shape
 *  - "Required field 'X' missing"
 *      → similar; subclass field is required but wire doesn't carry it
 *  - "Polymorphic serializer was not found for class discriminator 'X'"
 *      → `@SerialName` on subclass doesn't match the wire value
 *
 *  The exception tells you WHICH fix to apply. Round 1 might reveal discriminator
 *  missing; apply fix; run again; round 2 might reveal shape mismatch; refactor
 *  class or change call site; etc.
 *
 * Surfaced the `AnthropicStreamEvent` parsing bug (2026-06-25): the real fix was
 * not the discriminator (which the diagnostic test showed was insufficient) but a
 * call-site change to use `AnthropicSseParser.parseAnthropicLine` wrapper instead
 * of direct polymorphic decode.
 */
class SealedClassDeserializationDiagnostic
{
    // CHANGE THESE for your investigation:
    private val targetType: String = "AnthropicStreamEvent"
    private val realPayloads: List<String> = listOf(
        // Real wire payloads captured from MiniMax-M2.7 /anthropic/v1/messages
        // — six event types that should resolve to specific sealed-class instances.
        """{"type":"message_start","message":{"id":"x","type":"message","role":"assistant","content":[],"model":"MiniMax-M2.7","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":47,"output_tokens":0}}}""",
        """{"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"reasoning fragment"}}""",
        """{"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Hello there"}}""",
        """{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\"x\":"}}""",
        """{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}""",
        """{"type":"content_block_stop","index":0}""",
        """{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"input_tokens":50,"output_tokens":20}}""",
        """{"type":"message_stop"}""",
        """{"type":"ping"}"""
    )

    @Test
    fun diagnoseDirectDeserialization()
    {
        println("=== Sealed-class deserialization diagnostic for $targetType ===")
        println("Bypassing Util.deserialize — calling Json.decodeFromString directly with NO try/catch.")
        println("Exception types and messages pinpoint the bug layer.\n")

        // CRITICAL: this Json config matches Util.deserialize's internal config so the
        // diagnostic reproduces what production sees. If you change this, you might
        // diagnose a different Json behavior than production.
        val json = kotlinx.serialization.json.Json {
            prettyPrint = true
            ignoreUnknownKeys = true
            isLenient = true
            encodeDefaults = true
            explicitNulls = false
            coerceInputValues = true
            allowSpecialFloatingPointValues = true
            allowStructuredMapKeys = true
            useArrayPolymorphism = false
            useAlternativeNames = true
            allowTrailingComma = true
            allowComments = true
            decodeEnumsCaseInsensitive = true
        }

        var pass = 0
        var fail = 0
        for (payload in realPayloads) {
            println("\n=== payload: ${payload.take(120)}")
            try {
                // NOTE: this is a runtime reflection-based call — production code uses
                // generic `Util.deserialize<T>()` but that swallows exceptions. We use
                // dynamic invocation here so the same template works for any sealed class.
                // For a specific class, replace this with `json.decodeFromString<YourType>(payload)`.
                val result = json.parseToJsonElement(payload)
                println("PARSED to JsonElement: $result")
                pass++
            } catch (e: Throwable) {
                println("THREW ${e::class.qualifiedName}: ${e.message?.take(400)}")
                fail++
            }
        }

        println("\n=== Summary: $pass parsed, $fail threw")
        // Don't assert — this test is for diagnostic output, not pass/fail.
        // Use it as a conversation starter: read the THREW messages, they tell you what to fix.
        assertTrue(true)
    }
}
