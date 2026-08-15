Post-hardening capture snippets (after the 2026-06-25 PCP hardening). The pre-hardening snippets in the SKILL.md were deleted because they describe the now-removed `readText()`-deadlock pattern. Use these instead.

## SubprocessOutputCapture (Python, JavaScript — and anything subprocess-based)

`TPipe/src/main/kotlin/PipeContextProtocol/SubprocessOutputCapture.kt`:

```kotlin
object SubprocessOutputCapture {
    suspend fun capture(
        process: Process,
        timeoutMs: Long,
        maxInMemoryBytes: Int
    ): BufferedOutput = coroutineScope {
        // Parallel readers prevent pipe-buffer deadlock past ~64KB
        val stdoutDeferred = async(Dispatchers.IO) {
            process.inputStream.readAllBytes()
        }
        val stderrDeferred = async(Dispatchers.IO) {
            process.errorStream.readAllBytes()
        }

        val completed = withTimeoutOrNull(timeoutMs) {
            process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
        } ?: false

        if (!completed) {
            process.destroyForcibly()
            stdoutDeferred.await()
            stderrDeferred.await()
            return@coroutineScope BufferedOutput(stdout = null, stderr = null,
                binary = null, totalBytes = 0L, truncated = false)
        }

        val stdoutBytes = stdoutDeferred.await()
        val stderrBytes = stderrDeferred.await()

        val totalBytes = stdoutBytes.size.toLong() + stderrBytes.size.toLong()
        val stdoutResult = stdoutBytes.toBufferedText(maxInMemoryBytes)

        BufferedOutput(
            stdout = stdoutResult.text,
            stderr = String(stderrBytes, Charsets.UTF_8),
            binary = stdoutResult.binaryTail,
            totalBytes = totalBytes,
            truncated = stdoutResult.truncated,
            overflowPath = stdoutResult.overflowPath
        )
    }
}
```

`toBufferedText(maxInMemoryBytes)` (private helper):
- Tries UTF-8 decode with `Charset.forName("UTF-8").newDecoder()` (default `CodingErrorAction.REPORT`).
- On `MalformedInputException` → returns `binaryTail = bytes`, `text = null`.
- On valid UTF-8 + size <= maxInMemoryBytes → returns `text = decoded`.
- On valid UTF-8 + size > maxInMemoryBytes → writes full bytes to `File.createTempFile("pcp_overflow_", ".bin")` (deleteOnExit), returns `text = String(first maxInMemoryBytes)`, `truncated = true`, `overflowPath = absolutePath`.

## PcpThreadPool

`TPipe/src/main/kotlin/PipeContextProtocol/PcpThreadPool.kt`:

```kotlin
class PcpThreadPool private constructor(private val delegate: ThreadPoolExecutor) {
    val maxConcurrency: Int get() = delegate.corePoolSize

    fun <T> submit(task: () -> T): Future<T> = delegate.submit(task)

    fun shutdown() {
        delegate.shutdown()
        if (!delegate.awaitTermination(30, TimeUnit.SECONDS)) {
            delegate.shutdownNow()
        }
    }

    companion object {
        fun create(): PcpThreadPool {
            val size = Runtime.getRuntime().availableProcessors() * 2
            val delegate = ThreadPoolExecutor(
                size, size,
                0L, TimeUnit.MILLISECONDS,
                SynchronousQueue(),
                { r -> Thread(r, "pcp-worker").apply { isDaemon = true } },
                ThreadPoolExecutor.AbortPolicy()
            )
            return PcpThreadPool(delegate)
        }
    }
}
```

The point: `SynchronousQueue` + `AbortPolicy` means saturated `submit()` throws `RejectedExecutionException` immediately. No unbounded queue, no `DiscardPolicy` swallowing the signal.

## PythonExecutor.executeSecure (post-hardening)

Three things changed vs the pre-hardening version:

1. Constructor takes `private val threadPool: PcpThreadPool = PcpThreadPool.create()`.
2. `processBuilder.start()` is wrapped in `threadPool.submit<Process> { ... }.get()` with a `try/catch(RejectedExecutionException)` returning `Executor saturated` error.
3. The old `readText()` + `process.waitFor(timeoutMs)` + `destroyForcibly()` block is replaced by a single `SubprocessOutputCapture.capture(process, options.timeoutMs.toLong(), maxInMemoryBytes = 256 * 1024)` call.
4. Error precedence: timeout detection (`captureBuffer.totalBytes == 0L && stdout == null`) is checked BEFORE the exit-code branch, because `destroyForcibly()` produces exit code 137 (SIGKILL) which is also a non-zero exit.

## KotlinExecutor.execute (post-hardening — daemon thread + Thread.join)

```kotlin
val captureOutcome = withContext(Dispatchers.IO) {
    val resultHolder = arrayOfNulls<Any>(1)
    val stdoutHolder = arrayOfNulls<StringWriter>(1)
    val stderrHolder = arrayOfNulls<StringWriter>(1)
    val exceptionHolder = arrayOfNulls<Throwable>(1)

    val engineThread = Thread({
        // Set up two StringWriters (separate stdout / stderr channels)
        // Build SimpleScriptContext with both writers
        // Run engine.eval(script, scriptContext)
        // Store result, exception, writers
    }, "kotlin-engine-thread").apply { isDaemon = true }

    engineThread.start()

    // Thread.join(timeoutMs) — NOT withTimeoutOrNull, because join() is a
    // synchronous blocking call that coroutine cancellation can't interrupt
    val deadline = System.currentTimeMillis() + timeoutMs
    engineThread.join(timeoutMs)
    val joined = System.currentTimeMillis() < deadline && !engineThread.isAlive

    if (!joined) {
        null  // timeout marker
    } else {
        EvalOutcome(stdout, stderr, returnValue, timedOut = false, error = ex)
    }
}
```

Key design decisions:

- **Daemon thread**: prevents JVM from hanging on a leaked engine thread. The thread keeps running but doesn't block shutdown.
- **Thread.join with deadline**: `withTimeoutOrNull` would NOT interrupt the inner `join()` because synchronous blocking calls don't respond to coroutine cancellation. Use a deadline check + `Thread.join(timeoutMs)` directly.
- **Two StringWriters**: the pre-hardening code used a single `StringWriter` for both `writer` and `errorWriter`, merging stdout and stderr with no separator. Post-hardening uses separate writers so `outputBuffer.stdout` and `outputBuffer.stderr` are properly channel-separated.
- **ThreadLocal state via arrayOfNulls**: the engine runs on a different thread, so we can't capture locals in the outer scope. Use single-element arrays as thread-safe handoff boxes.

The acknowledged leak: the JSR-223 engine thread is uninterruptible. When timeout fires, the dispatcher returns a clean error but the daemon thread keeps running until the script returns or the JVM exits. Document this in any context that exposes `Transport.Kotlin`. For untrusted scripts, wrap the dispatcher call in an outer `withTimeoutOrNull` at the pipe layer.