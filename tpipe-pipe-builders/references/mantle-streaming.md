# Mantle Streaming — Detailed Reference

Class-level reference for the `GenericOpenAIPipe` streaming surface.
Read this when wiring streaming callbacks on a Mantle pipe, debugging
chunk-loss symptoms, or porting a streaming-enabled Bedrock pipe.

## Complete API surface

### `setStreamingEnabled(enabled: Boolean): GenericOpenAIPipe`

Standard boolean setter inherited from the base `Pipe` class. Default
`streamingEnabled = false`. Setting this **without** also calling
`setStreamingCallback` is a silent bug — chunks flow through the wire
but no listener is registered.

```kotlin
override fun setStreamingEnabled(enabled: Boolean): GenericOpenAIPipe
{
    streamingEnabled = enabled
    return this
}
```

### `setStreamingCallback(callback: suspend (String) -> Unit): GenericOpenAIPipe`

The single-callback registration. Auto-enables streaming (`streamingEnabled = true`)
and **auto-propagates to every descendant pipe** so chunks emitted by
child pipes (validator, transformation, branch, reasoning) flow through
the same callback.

```kotlin
fun setStreamingCallback(callback: suspend (String) -> Unit): GenericOpenAIPipe
{
    this.streamingEnabled = true
    obtainStreamingCallbackManager().addCallback(callback)
    // Propagate to every descendant pipe so chunks emitted by child
    // pipes (validator, transformation, branch, reasoning) flow through
    // the same callback. Without this, callbacks registered on a parent
    // pipe are silently ignored when its child pipe's API call streams.
    propagateStreamingCallback(callback)
    return this
}
```

Critical: **second call supersedes the first.** The callback manager
holds a single callback. If you need multiple callbacks, write a
single dispatcher callback that fans out internally.

## Auth shape: `BedrockMantleAuth.Streaming`

Separate from batch auth. The `Streaming` data class is defined at
`TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleAuth.kt:94`.

```kotlin
data class Streaming(
    val region: String,
    val accessKeyId: String,
    val secretAccessKey: String,
    val sessionToken: String?,
    val modelId: String
)
```

The streaming path reads this field via `setBedrockMantle(...)` —
ensure the pipe is initialized BEFORE `setStreamingCallback` so the
streaming-specific auth is populated.

## Internal streaming paths

`GenericOpenAIPipe` exposes three streaming execution paths:

| Path | API family | Source |
|---|---|---|
| `executeStreamingDirect` | Direct HTTP SSE | `GenericOpenAIPipe.kt:1144` |
| `executeStreamingOpenAI` | OpenAI Chat Completions | `GenericOpenAIPipe.kt:1638` |
| `executeStreamingAnthropic` | Anthropic Messages | `GenericOpenAIPipe.kt:1692` |
| `executeStreamingOpenAIResponses` | OpenAI Responses | `GenericOpenAIPipe.kt:1804` |

All four paths emit via `emitStreamingChunk` (inherited from `Pipe`),
which fans out to the `StreamingCallbackManager`.

## Test injection

`GenericOpenAIPipe` supports a `HttpStreamingConnectionFactory` for
test injection (no real network):

```kotlin
internal fun injectStreamingConnectionFactoryForTest(
    factory: HttpStreamingConnectionFactory
)
```

Used by `RawHttpStreamingTest` (chunked SSE) and `MockStreamingConnectionFactory`
(empty response). Without an injected factory, the production default
wraps a real Ktor HTTP client — production deployment requires valid
Mantle credentials.

## Verified chunk-emission behavior

Per the streaming code at `GenericOpenAIPipe.kt:984-988`:

```kotlin
// the response line-by-line. The InputStream blocks per
// line read, so each SSE delta fires emitStreamingChunk as
// it arrives on the socket — verified empirically via
// RawHttpStreamingTest (chunks arrive hundreds of ms apart
// rather than all in one batch).
```

This is the key behavior the Ktor `bodyAsChannel` path does NOT exhibit
— `bodyAsChannel` releases chunks in batches. The Mantle pipe buffers
via `BufferedReader.readLine()` so chunks emit one-at-a-time as they
arrive on the socket.

## Production fix recipe — porting a Bedrock streaming pipe to Mantle

When a Bedrock pipe has:

```kotlin
pipe.enableStreaming()
    .streamingCallbacks {
        add(uiCallback)
        add(workStreamCallback)
    }
```

The Mantle equivalent is:

```kotlin
val pipe = GenericOpenAIPipe()
    .setBedrockMantle(region, modelId)
    // Single callback only — fan out internally
    .setStreamingCallback { chunk ->
        scope.launch {
            uiCallback(chunk)
            workStreamCallback(chunk)
        }
    }
```

**The fan-out scope is required.** Without it, the second
`setStreamingCallback` call supersedes the first and `workStreamCallback`
never receives chunks.

## Common bug patterns

| Symptom | Root cause | Fix |
|---|---|---|
| Pipe completes but UI never sees chunks | `setStreamingEnabled(true)` called without `setStreamingCallback` | Add the callback |
| Work-stream subscriber receives chunks but UI doesn't | Two `setStreamingCallback` calls — second supersedes first | Use single callback + fan-out scope |
| Validator/branch pipe emits chunks but parent doesn't see them | `propagateStreamingCallback` not firing | Use `setStreamingCallback` (which auto-propagates) instead of `setStreamingEnabled` directly |
| `enableStreaming()` no-arg compile error on Mantle pipe | Bedrock-only API | Use `setStreamingEnabled(true)` |
| `streamingCallbacks { add(...) }` compile error on Mantle pipe | Bedrock-only DSL | Use `setStreamingCallback` (single) |

## Test mocking the streaming parser

When writing a unit test for `executeStreamingDirect` (or any of the
three other streaming execution paths), the test must reproduce the
production condition: the socket stays alive after the SSE stream
ends. Vanilla `ByteArrayInputStream`-based mocks EOF naturally; the
parser exits the loop on EOF and the production bug does not surface.
The two key pitfalls captured during the 2026-08-02 [DONE] fix:

### Pitfall — `Sequence.forEach` cannot be broken via `return@label`

`reader.lineSequence().forEach { rawLine -> ... }` is implemented as
`while (iterator.hasNext()) action(iterator.next())` in Kotlin stdlib.
A `return@lineLoop` from inside the action lambda only returns from
the **action** — the next iteration's `iterator.hasNext()` then calls
`readLine()`, which blocks until the socket has more data (or the
custom-mock stream times out). The labeled `return` therefore does NOT
exit the loop.

**Fix — use a labeled `while` loop on the iterator directly:**

```kotlin
val lineIterator = reader.lineSequence().iterator()
lineLoop@ while(lineIterator.hasNext())
{
    val rawLine = lineIterator.next()
    // ... process line ...
    if(terminalCondition) break@lineLoop   // exits the while loop entirely
}
```

A `break@lineLoop` calls `iterator.hasNext()` zero additional times,
which is what you want when the stream stays open after the terminal
signal. Verified against the OpenAI Chat Completions `[DONE]` sentinel
fix (2026-08-02): the production parser was hanging for 120 s
(`HttpURLConnection.readTimeoutMs`) because a `return@lineLoop` from
inside the `data:` branch fell back to `iterator.hasNext()` →
`readLine()` blocking on the still-alive Mantle socket. Switching to
the labeled-while pattern reduced the same conditional exit from
120 s to 5 ms.

### Pitfall — custom `InputStream` mocks must honor socket-level `readTimeoutMs` semantics

The production parser reads via `BufferedReader.readLine()` over a
real TCP socket. The socket has `readTimeoutMs = 120_000` set via
`HttpURLConnection.setReadTimeout(...)`. When the socket is alive
but the server has sent the SSE terminal signal, `readLine()` blocks
until the socket's `SO_TIMEOUT` fires — production hangs for
120 s, not forever.

A custom mock `InputStream` that wraps a `PipedInputStream` (or
`wait()` / `notify()`) must reproduce the same wall-clock deadline,
otherwise the test either:

- **Hangs forever** if the mock has no timeout (the test JVM must
  be killed externally to unblock), or
- **Exits immediately with `IOException: Write end dead`** if the
  producer thread dies before the consumer reads — but the production
  bug is "socket stays open forever," not "producer thread dies."

**Fix — make the mock honor `readTimeoutMs` and throw
`SocketTimeoutException` on idle.** Pattern:

```kotlin
private class BlockingInputStream(
    private val body: ByteArray,
    private val readTimeoutMs: Long
) : InputStream()
{
    private var position = 0
    @Volatile private var closed = false
    private val lock = Any()

    override fun read(): Int
    {
        while(!closed)
        {
            if(position < body.size) return body[position++].toInt() and 0xff
            val waitStart = System.currentTimeMillis()
            synchronized(lock) {
                try { (lock as java.lang.Object).wait(readTimeoutMs) }
                catch(e: InterruptedException) { Thread.currentThread().interrupt() }
            }
            val elapsed = System.currentTimeMillis() - waitStart
            if(elapsed >= readTimeoutMs - 50 && !closed)
            {
                throw java.net.SocketTimeoutException(
                    "Read timed out after ${readTimeoutMs}ms"
                )
            }
        }
        return -1
    }

    override fun close()
    {
        closed = true
        synchronized(lock) { (lock as java.lang.Object).notifyAll() }
    }
}
```

Three non-obvious details:

1. **`close()` must NOT be `@Synchronized` on `this`.** If
   `close()` acquires the `this` monitor and the reader is in
   `wait()` holding the monitor, `close()` deadlocks until the
   wait times out. Use a separate `lock` object for
   `synchronized(lock)` so close/notify can run while the reader
   is waiting.

2. **Mock `readTimeoutMs` should be 5_000 (5 s) in tests, not
   120_000.** A RED test that "hangs for the production timeout"
   takes 2 minutes per test run. 5 s is enough to demonstrate the
   hang in CI; the production `120_000` is verified by the live
   integration tests, not the unit tests.

3. **`kotlinx.coroutines.withTimeoutOrNull` does NOT preempt a
   blocking `BufferedReader.readLine()` call.** Coroutines check
   cancellation at suspension points; `readLine()` is a true JVM
   blocking call that does not suspend. The cancellation reaches
   the `Dispatchers.IO` worker thread via `Thread.interrupt()`
   which unblocks `wait()` / `read()` — but only if the underlying
   stream is interruptible. A custom `InputStream` using
   `wait()` *is* interruptible; one using native `socket.read()`
   is too. A `ByteArrayInputStream` is not (already at EOF).

### How these two pitfalls interact

The RED test for the `[DONE]` fix on 2026-08-02 hit both:

1. With a `PipedInputStream`-based mock that had no timeout, the
   patched parser's `break@lineLoop` (after the labeled-while
   fix) correctly exited the loop — but the `use { reader -> ... }`
   block then tried to close the reader, which tried to drain
   StreamDecoder's internal buffer, which called `read()` on the
   still-blocked mock, which hung. The mock's missing timeout
   turned the test into a wall-clock hang.

2. With a `BlockingInputStream` that uses `wait()`, `withTimeoutOrNull`
   propagates via `Thread.interrupt()` to the `wait()` call, which
   throws `InterruptedException`. But the `Sequence.forEach`
   pitfall was already hit: the patched code's `return@lineLoop`
   from inside the action lambda fell back to `iterator.hasNext()`
   → `readLine()` → `wait()` → interruptible. The interrupt
   happens, but the next `hasNext()` call enters the same wait
   again, and the loop never exits.

Fixing pitfall 1 (labeled-while) makes pitfall 2 matter less —
`break@lineLoop` exits the while loop without any further
`hasNext()` calls, so the interrupt has somewhere to land. But
pitfall 2 still matters for the failure-path tests (mid-stream
transport failure before the terminal signal) where the parser
IS still inside the loop when the timeout fires.

A reusable `BlockingSocketConnectionFactory` + `BlockingInputStream`
template that encodes all of the above is at
`scripts/streaming-test-mock-template.kt`. Copy the file into a new
test class, replace the `body` construction with the SSE fixture,
and the test reproduces the production socket-stays-open condition
without re-deriving the mock infrastructure.

## See Also

- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:438-465` — streaming setters
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleAuth.kt:94` — `Streaming` auth shape
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt:1144-1200` — `executeStreamingDirect` + `BufferedReader` chunking
- `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:961-1090` — Bedrock `enableStreaming()` + `streamingCallbacks` DSL (the gap)
- `references/agent-migration-bedrock-to-mantle.md` — full porting recipe
- `scripts/streaming-test-mock-template.kt` — copy-paste starting point for test mocks
