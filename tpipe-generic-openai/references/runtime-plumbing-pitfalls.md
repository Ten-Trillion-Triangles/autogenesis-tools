# TPipe Application Runtime Plumbing Pitfalls

Lessons learned from debugging an interactive TPipeWriter TUI (2026-06-25).
These pitfalls surface when wiring streaming + tracing + runBlocking across
many command handlers — the kind of work that doesn't happen in pipe-level
unit tests.

The user repeated the same instruction three different ways during the
debugging session: "every commandn thatt involves an llm MUST WORK FULLY
and equal to the bedrock version on main", "THINK OUTSIDE THE BOX AND
TRY SOMETHING NEW. Get it right this time", and the earlier
"I'm not sure you've tested eerything at this stagee". The lesson:
**per-command-handler patches are a trap. Fix the runtime helper once.**

**And the deeper lesson** (2026-06-25, second session): when the same
fix has to be applied to multiple call sites AND the same bug recurs
across different commands, **the fix belongs in the framework**, not in
the application. The user said "the big issue I see is that it does
eventually arrive, but it doesn't steram in real time att all, andn the
reasonning pipes are not at all being streamed" — that was the signal
to stop patching TPipeWriter and fix TPipe itself.

## Architecture: the runtime helper pattern

When you have many command handlers all wrapping `pipeline.execute(...)`
in `runBlocking { ... }`, do NOT sprinkle streaming/tracing setup across
each call site. Build ONE helper that:

1. Registers the streaming callback on every pipe in the pipeline
2. Spawns a periodic trace flush coroutine (separate from the executor's
   coroutine scope) that writes to a user-visible trace file
3. Wraps `runBlocking { pipeline.execute(...) }` with the above
4. Writes the FINAL trace file after the pipeline returns (in case the
   periodic flush missed something)

```kotlin
// Util/PipelineRuntime.kt
fun <T> runWithLiveTrace(pipeline: Pipeline, traceFileName: String, block: () -> T): T {
    // Wire streaming once
    pipeline.getPipes().forEach { pipe ->
        if (pipe is GenericOpenAIPipe) {
            pipe.setStreamingCallback(STREAMING_CALLBACK)
        }
    }
    pipeline.enableTracing(TraceConfig(HTML))

    // Periodic flush on Dispatchers.IO (separate dispatcher from
    // the executor to avoid dispatcher contention)
    val flushScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val flushJob = flushScope.launch {
        while (isActive) {
            delay(2000)
            try {
                val trace = pipeline.getTraceReport(TraceFormat.HTML)
                writeStringToFile("~/TPipeWriter/$traceFileName", trace)
            } catch (_: Exception) { /* best-effort */ }
        }
    }

    val result: T = try {
        block()
    } finally {
        flushJob.cancel()
        try {
            val finalTrace = pipeline.getTraceReport(TraceFormat.HTML)
            writeStringToFile("~/TPipeWriter/$traceFileName", finalTrace)
        } catch (_: Exception) { /* best-effort */ }
    }
    return result
}
```

For Connectors (multiple branches), use a separate variant:

```kotlin
fun <T> runWithLiveTraceAll(pipelines: List<Pipeline>, traceFileName: String, block: () -> T): T {
    pipelines.forEach { it.getPipes().forEach { pipe ->
        if (pipe is GenericOpenAIPipe) pipe.setStreamingCallback(STREAMING_CALLBACK)
    }}
    pipelines.forEach { it.enableTracing(TraceConfig(HTML)) }
    // ... same flush pattern, flushes the first pipeline's trace ...
}
```

For Connectors that may need a separate flush thread (see pitfall below),
use a daemon `Thread` with `AtomicBoolean` instead of a coroutine:

```kotlin
val stopFlag = AtomicBoolean(false)
val flushThread = Thread {
    while (!stopFlag.get()) {
        try {
            val trace = activePipeline?.getTraceReport(TraceFormat.HTML) ?: ""
            if (trace.isNotEmpty()) writeStringToFile("~/TPipeWriter/$traceFileName", trace)
        } catch (_: Exception) {}
        try { Thread.sleep(2000) } catch (_: InterruptedException) { break }
    }
}.apply { isDaemon = true; start() }
```

Then in the finally block:
```kotlin
stopFlag.set(true)
flushThread.join(2000)
```

## Pitfall 1: Streaming callback duplication from init-time wiring

**Symptom**: Every chunk appears TWICE in the TUI:
```
HelloHello I'm your story discussion assistant, ready to help...
```

**Cause**: `Env.init()` calls `enablePipelineStreaming(pipeline)` which
registers a callback that writes each chunk to `FileDescriptor.out`.
Then `runWithLiveTrace` ALSO registers a callback (via
`pipe.setStreamingCallback`). Both callbacks fire per chunk → duplicate
output.

**Fix**: Pick ONE place to register the callback.
- If using `runWithLiveTrace`, REMOVE all `enablePipelineStreaming`
  calls from `Env.init` and Builders/*.
- If using `enablePipelineStreaming` directly, do not use
  `runWithLiveTrace`.

**Diagnostic**: `grep -rn "enablePipelineStreaming\|setStreamingCallback" src/main/kotlin/`
should return ONE location per pipeline. Two locations = bug.

## Pitfall 2: `System.out.print` is line-buffered on TTY

**Symptom**: Streaming output appears all-at-once at the END of the
pipeline instead of chunk-by-chunk in real-time.

**Cause**: Java's `System.out` is a `PrintStream` that buffers stdout
when connected to a TTY (waits for newline before flushing the line
buffer). Streaming chunks from OpenAI Responses API have no newlines
(they're JSON delta tokens like `{"delta":"Hello"}`). The chunks
accumulate in the buffer until something else writes a newline.

**Fix**: Bypass `System.out` entirely. Write directly to
`FileDescriptor.out` (fd 1) via a SINGLE shared `FileOutputStream`:

```kotlin
import java.io.FileDescriptor
import java.io.FileOutputStream

private val rawStdout = FileOutputStream(FileDescriptor.out)

val streamingCallback: suspend (String) -> Unit = { chunk ->
    if (chunk.isNotEmpty()) {
        rawStdout.write(chunk.toByteArray(Charsets.UTF_8))
        rawStdout.flush()
    }
}
```

**Critical**: Keep ONE FileOutputStream across all callbacks. Opening
a new FileOutputStream(FileDescriptor.out) per chunk and closing it
causes "Stream Closed" errors after the first chunk. Never close
FileDescriptor.out — it permanently breaks stdout for the rest of the
JVM.

**Verification**: Write a test that streams 5 chunks with 1-second
delays. With `FileDescriptor.out`, chunks appear chunk-by-chunk in
real-time. With `System.out.print`, they appear all-at-once after
the loop completes.

## Pitfall 3: `runBlocking { pipeline.execute(...) }` hangs forever
after removing `setPipeCompletionCallback`

**Symptom**: Pipeline completes its API calls, full output appears
in TUI scrollback, but `runBlocking` never returns. JVM at `%CPU: 0.0`
forever. No exceptions, no logs, no way to debug without JDWP stack
dump.

**Cause**: This is the most subtle pitfall. The OLD code (before any
refactor) had:
```kotlin
writerLevelConnector.get(writingStrength)?.setPipeCompletionCallback(::debugPipeCallback)
val result = writerLevelConnector.execute(...)
```

The `setPipeCompletionCallback` looks optional — it just notifies when
each pipe in the connector finishes. But REMOVING it causes the
connector's internal coroutines to dead-lock. The connector orchestrates
multiple pipes and needs an external signal (the callback fires from
each pipe's completion) to keep its internal coroutine machinery
progressing. Without the signal, all pipes complete but the runBlocking
parks indefinitely with `BlockingCoroutine.joinBlocking` waiting for
a continuation that never arrives.

**Fix**: Install a no-op callback before `runBlocking`:
```kotlin
val result = runBlocking {
    writerLevelConnector.get(writingStrength)
        ?.setPipeCompletionCallback { _, _ -> /* no-op */ }
    writerLevelConnector.execute(writingStrength, content)
}
```

The callback signature `(Pipe, MultimodalContent) -> Unit` is preserved
so the connector's internal signal mechanism receives a continuation.

**Diagnostic**: If you see `BlockingCoroutine.joinBlocking` parked in
a SIGQUIT thread dump, AND the pipeline produced visible output
(streaming worked), AND the JVM is at 0% CPU, this is your bug.

## Pitfall 4: `runBlocking` + coroutine flush = dispatcher deadlock

**Symptom**: `runBlocking { pipeline.execute(...) }` with a
`GlobalScope.launch(Dispatchers.IO) { while(isActive) { delay(2000); ... } }`
flushing the trace file. Flush coroutine never runs because Default
Dispatcher's workers are blocked by the runBlocking's blocking
coroutine. `runWithLiveTrace`'s flush runs on `Dispatchers.IO` and
starves because the main thread holds the blocking coroutine which
holds workers indirectly.

**Cause**: This is a subtle interaction between `runBlocking`, the
default dispatcher, and per-thread coroutine scheduling. The exact
mechanism depends on Kotlin coroutines version, but the symptom is
that `launch(Dispatchers.IO) { while(isActive) { delay(...) } }`
inside `runWithLiveTrace`'s lambda gets starved when the executor
holds threads.

**Fix**: Use a daemon `Thread` for the periodic flush, NOT a
coroutine:

```kotlin
val stopFlag = AtomicBoolean(false)
val flushThread = Thread {
    while (!stopFlag.get()) {
        try { /* write trace */ } catch (_: Exception) {}
        try { Thread.sleep(2000) } catch (_: InterruptedException) { break }
    }
}.apply { isDaemon = true; start() }

// ... runBlocking ...

stopFlag.set(true)
flushThread.join(2000)
```

The thread runs on the OS scheduler, independent of Kotlin coroutine
dispatchers. The runBlocking holds the main thread but the daemon
thread still runs. Daemon threads auto-terminate when the JVM exits.

For `runWithLiveTrace` (non-Connector path), `GlobalScope.launch +
Dispatchers.IO` works because the pipeline's executor completes
between commands and the dispatcher is freed up. The deadlock
specifically affects Connector-based commands where the executor
keeps the dispatcher busy for 2+ minutes.

## Pitfall 5: API key visibility — silent hang vs clear error

**User feedback**: "I can't tell if the api key is missing or broken or
whatever". A silent hang on the first API call wastes 2+ minutes of
debugging time per session.

**Fix**: Print API key status at startup, BEFORE any pipeline
construction. Mask the key (show last 4 chars):

```bash
# In run.sh
KEY_LEN=${#MINIMAX_API_KEY}
KEY_LAST4="${MINIMAX_API_KEY: -4}"
echo "[run.sh] API key: OK (sk-...${KEY_LAST4}, ${KEY_LEN} chars)"
```

```kotlin
// In Main.kt
val envKey = System.getenv("MINIMAX_API_KEY")
if (envKey.isNullOrBlank()) {
    println("[main] WARNING: MINIMAX_API_KEY environment variable is not set.")
    println("[main]   Wire one via: export MINIMAX_API_KEY=\"sk-...\" before running.")
    println("[main]   The pipes will fail at the first API call until this is set.")
} else {
    val masked = "sk-..." + envKey.takeLast(4)
    println("[main] API key in env: OK ($masked, ${envKey.length} chars)")
}

// After Env.init():
val resolvedKey = GenericOpenAIEnv.resolveApiKey()
if (resolvedKey.isBlank()) {
    println("[main] WARNING: GenericOpenAIEnv.resolveApiKey() is BLANK after init.")
    println("[main]   Pipes will fail with 'API key is required' on first call.")
} else {
    println("[main] GenericOpenAIEnv.resolveApiKey(): OK (sk-..." +
            resolvedKey.takeLast(4) + ", ${resolvedKey.length} chars)")
}
```

Add a clear error block in run.sh if no key:
```bash
if [ -z "$MINIMAX_API_KEY" ]; then
    if [ -z "$AUXILIARY_VISION_API_KEY" ]; then
        echo "============================================="
        echo "ERROR: No MiniMax API key configured"
        echo "============================================="
        echo "Set one of:"
        echo "  export MINIMAX_API_KEY=\"sk-...\"             # canonical"
        echo "  export AUXILIARY_VISION_API_KEY=\"sk-...\"   # dev fallback"
        echo ""
        echo "Get a key at https://platform.minimax.io"
        exit 1
    fi
fi
```

## Pitfall 6: Post-stream `println(result.text)` duplicates streamed output

**Symptom**: Streaming output appears chunk-by-chunk in real-time,
THEN the full response appears again as a single block at the end.

**Cause**: Both the streaming callback AND the post-execute
`println(result.text)` write the response to stdout.

**Fix**: Pick one. With streaming enabled, the streaming callback is
the sole writer. Remove the post-stream print:

```kotlin
// WRONG
runBlocking {
    result = pipeline.execute(input)
}
if (result.text.isNotEmpty()) {
    println("\n\n\n" + result.text)  // duplicates streamed output
}

// RIGHT
val result = runWithLiveTrace(pipeline, "Trace.html") {
    runBlocking { pipeline.execute(input) }
}
// Streaming callback already wrote chunks to stdout.
// Only print failure messages:
if (result.text.isEmpty()) {
    println("The model failed to return a result")
}
```

## Pitfall 7: Streaming callback set on parent pipe does NOT fire for child pipe chunks (FRAMEWORK-LEVEL bug, fixed in TPipe)

**Symptom**: Streaming output for the parent pipe (e.g. `Chat Pipe`)
works chunk-by-chunk. Streaming output for child pipes (validator,
transformation, branch, **reasoning**) is COMPLETELY MISSING. The user
sees the final answer stream in but never sees the reasoning pipe's
thinking content, the validator's retries, or the transformation's
post-processing. Symptom is often invisible — the final answer still
arrives, it just lacks the intermediate steps.

**Cause**: `Pipe.streamingCallbackManager` is a per-pipe instance field.
When the user calls `pipe.setStreamingCallback(cb)`, the callback is
added ONLY to that pipe's manager. The pipe's child pipes (reasoning,
validator, transformation, branch) each have their OWN manager. When
the child pipe's API call streams chunks, the child invokes
`streamingCallbackManager.emitToAll(chunk)` on ITS manager — which has
no listeners.

This is a FRAMEWORK-level architectural bug, not an application-level
plumbing issue. The user explicitly diagnosed this in a 2026-06-25
session:

> "the big issue I see is that it does eventually arrive, but it doesn't
> steram in real time att all, andn the reasonning pipes are not at all
> being streamed... Examine the api docs for minimax as well in real
> time to verify we've got this figured out and solved this time"

The user was right. Patching TPipeWriter command handlers is the wrong
fix layer. The fix belongs in TPipe's `Pipe.kt`.

**Framework fix** lives in TPipe's `Pipe.kt` (callback propagation to
descendants) AND in `GenericOpenAIPipe.executeStreamingDirect` (Ktor
CIO `bodyAsChannel` bypass via direct `HttpURLConnection`). For the
full implementation, three-test empirical validation table, and the
Ktor source-level root cause trace, see the umbrella SKILL.md section
"Critical Pitfall: Ktor CIO `bodyAsChannel` buffers chunked SSE until
stream close — bypass Ktor for streaming" and the existing
"Streaming callback set on parent pipe does NOT fire for child pipe
chunks" framework-fix snippet above. This reference focuses on
application-level plumbing — the next subsection covers what
TPipeWriter does WITH the framework fix in place.

```kotlin
// In Pipe.kt — propagate callback to all descendants when set on a pipe
open var streamingEnabled: Boolean = false  // hoisted from GenericOpenAIPipe

fun propagateStreamingCallback(
    callback: suspend (String) -> Unit,
    visited: MutableSet<String> = mutableSetOf()
) {
    if (pipeId in visited) return
    visited.add(pipeId)
    obtainStreamingCallbackManager().addCallback(callback)
    setStreamingEnabled(true)
    listOfNotNull(validatorPipe, transformationPipe, branchPipe, reasoningPipe)
        .forEach { it.propagateStreamingCallback(callback, visited) }
}

// In GenericOpenAIPipe.setStreamingCallback — propagate after registering
fun setStreamingCallback(callback: suspend (String) -> Unit): GenericOpenAIPipe {
    this.streamingEnabled = true
    obtainStreamingCallbackManager().addCallback(callback)
    propagateStreamingCallback(callback)   // NEW
    return this
}

// In Pipe.kt — child setters inherit parent's existing callbacks
fun setReasoningPipe(pipe: Pipe): Pipe {
    this.reasoningPipe = pipe
    reasoningPipe?.setParentPipe(this)
    streamingCallbackManager?.let { manager ->
        manager.getCallbacks().forEach { cb ->
            pipe.obtainStreamingCallbackManager().addCallback(cb)
        }
    }
    return this
}
// (Same pattern for setValidatorPipe, setTransformationPipe, setBranchPipe)

// In StreamingCallbackManager.kt — dedup by reference equality
fun addCallback(callback: suspend (String) -> Unit) {
    if (!callbacks.contains(callback)) {
        callbacks.add(callback)
    }
}
```

The `streamingEnabled` field was hoisted from `GenericOpenAIPipe` up
to the base `Pipe` class so all subclasses share one propagation
target. Each subclass (GenericOpenAI, OpenRouter, Ollama, Bedrock)
gets `override fun setStreamingEnabled(...)` to preserve its typed
fluent chain return value.

**Application fix (TPipeWriter side, working with the framework fix)**:
Once the framework propagation is in place, your `runWithLiveTrace`
helper just calls `setStreamingCallback` on each pipe in the pipeline
once. The framework handles propagation. No need to walk child pipes
from application code.

**Diagnostic** — if you suspect this is happening, check the trace file:
```bash
# Find pipes that have streaming=true in their API_CALL_SUCCESS
grep -oE 'data-pipe="[^"]+"' trace-*.html | sort -u
grep -B1 'streaming: true' trace-*.html | grep -oE 'data-pipe="[^"]+"' | sort -u
```
If a pipe name appears in the second grep (streaming: true) but NOT in
the first (event occurred), that pipe IS streaming. If a pipe appears
in the first but NOT the second, the streaming flag was never set —
that's the regression. For reasoning pipes specifically, look for
`isReasoningPipe: true` AND `streaming: true` together.

**Regression coverage**: `StreamingPropagationTest.kt` in TPipeWriter
has 7 unit tests covering: own-pipe chunk emission, child chunk
propagation, all-4-child-types propagation, late-attached child
inheritance, callback dedup, the exact reasoning-pipe scenario, and
cycle detection in the pipe tree.

## Pitfall 8: `streaming: true` in the trace is NOT proof of real-time delivery — write the timing test FIRST

**Symptom**: After fixing Pitfall 7, every pipe in the trace reports
`streaming: true`. The user watches the terminal — and chunks STILL
arrive in bursts every few seconds instead of token-by-token as the
model generates them.

**Canonical fix lives in the TPipe framework, not in application code**:
`GenericOpenAIPipe.executeStreamingDirect` (introduced in commit
`8e4b8d76 fix(tpipe-genericopenai): repair AnthropicSSE compile errors`)
bypasses Ktor entirely for streaming by opening a direct
`java.net.HttpURLConnection` with `setChunkedStreamingMode(0)` and reading
SSE line-by-line via `BufferedReader.lineSequence()`. See the umbrella
SKILL.md "Critical Pitfall: Ktor CIO `bodyAsChannel` buffers chunked SSE
until stream close — bypass Ktor for streaming" section for the full
mechanism and three-test empirical validation. This pitfall (8) covers
the verification methodology + the three-layer buffer trap that
surrounds that fix.

### Diagnostic-first rule (learned the hard way)

When the user reports "streaming isn't working" or "chunks arrive all at once", **write the timing test FIRST** — before any surface-level patch. Specifically, write a test that records `System.nanoTime()` per chunk and prints the inter-chunk deltas. This produces the diagnosis in 30 seconds:

- All deltas ≈ 0ms at the same timestamp → transport-level buffering (Ktor, curl, framework)
- Some deltas, median < 100ms → real streaming working
- One chunk or N chunks all at once → HTTP transport isn't streaming at all

Without this test, the temptation is to apply surface fixes (flush, dedup, FD.out, callback registration) and verify "looks like streaming" — which can persist for many rounds when the actual bug is in the HTTP transport layer. The 2026-06-25 session that produced this reference applied FOUR surface patches before finally writing `MiniMaxStreamingTimingTest` which proved all chunks arrived within 0ms of each other — instantly pointing to Ktor's `bodyAsChannel`. The user explicitly demanded this debugging approach:

> "Use the jwdp debugger if you have to compare how bedrock handles
> streaminng vs generic, and figure out a real way to prove we have
> real time streaming to the terminal pushing tokens as they come,
> not when the llm stops generating them."

JDWP works (the user's suggestion) but is heavier than needed. A wall-clock timing test against the suspect transport layer (curl, raw `HttpURLConnection`, Ktor SSE plugin) is faster and gives the same answer.

**User's exact words** (2026-06-25, the post-Pitfall-7 session):
> "the issue is still here. It needs to stream teh tokens in real time.
> As they come, not the entire llm output once it arrives. THAT'S NOT
> STREAMING!! I need you to figure wtf is going on here. Use the jwdp
> debugger if you have to compare how bedrock handles streaminng vs
> generic, and figure out a real way to prove we have real time
> streaming to the terminal pushing tokens as they come, not when the
> llm stops generating them."

**Why this trap exists**: the trace's `streaming: true` boolean tells
you the framework registered a callback on that pipe. It does NOT
tell you:
1. Whether the model is actually streaming tokens (vs. emitting one
   big JSON chunk and pretending it's SSE)
2. Whether the application's stdout is being flushed per chunk (vs.
   buffering until the executor returns)
3. Whether the Ktor CIO client's HTTP layer is line-buffering the
   network stream before handing it to your parser

Three independent buffers can each swallow chunks. A `streaming: true`
flag survives all three. The boolean is a NECESSARY but NOT SUFFICIENT
proof of streaming.

**Verification standard (memorize this)**:
> Real-time streaming = the terminal shows new characters appearing
> during the model's generation window, with multiple flushes per
> second. NOT a `streaming: true` flag. NOT `chunks.size > 0`. NOT
> visible end-of-pipeline output.

**Diagnostic: prove real-time delivery with wall-clock deltas**:

```kotlin
import java.io.FileDescriptor
import java.io.FileOutputStream

private val rawStdout = FileOutputStream(FileDescriptor.out)

val chunkTimes = mutableListOf<Long>()
val callback: suspend (String) -> Unit = { chunk ->
    if (chunk.isNotEmpty()) {
        chunkTimes.add(System.nanoTime())
        rawStdout.write(chunk.toByteArray(Charsets.UTF_8))
        rawStdout.flush()
    }
}

// ... run pipeline ...

// After completion:
val deltasMs = chunkTimes.zipWithNext { a, b -> (b - a) / 1_000_000 }
println("Chunk deltas (ms): " + deltasMs.joinToString(", "))
println("Min/Median/Max: ${deltasMs.minOrNull()}/${deltasMs[deltasMs.size / 2]}/${deltasMs.maxOrNull()}")
```

**Interpretation**:
- Healthy real-time streaming: median delta < 100ms with frequent
  small deltas (10-50ms). You see a steady dribble of bytes.
- Buffered (still broken): most deltas are near-zero in clusters
  separated by 500ms+ gaps (chunks arrived together, then a long
  pause, then more chunks together).
- Single-chunk (no streaming at all): only one delta entry, or all
  chunks have timestamps within a few ms of each other at the very
  end of the run.

**Three buffer sources to suspect in order**:

1. **Ktor CIO client — `bodyAsChannel` buffers until response close**
   (CONFIRMED BUG, fixed in TPipe 2026-06-25). `client.post{}.bodyAsChannel()`
   on the Ktor 3.1.3/3.3.x CIO engine returns a `ByteReadChannel` that
   does NOT deliver bytes incrementally for chunked transfer-encoded
   SSE responses. All bytes arrive in one batch when the response
   stream closes — verified via three diagnostic tests in TPipeWriter:

   - `RawHttpStreamingTest` — `java.net.HttpURLConnection` with
     `setChunkedStreamingMode(0)` and `BufferedReader.lineSequence()`
     streams chunks 200-700ms apart as the server sends them. Real
     streaming works.
   - `RawKtorStreamingTest` — same request via Ktor 3.3.3 CIO
     `bodyAsChannel`. Every chunk arrives at +4541ms with 0ms gaps
     between adjacent chunks. Buffer until end-of-stream.
   - `KtorSsePluginTest` — Ktor 3.3.3's SSE plugin
     (`install(SSE)` + `client.sse { incoming.collect }`) streams
     chunks 200-715ms apart. The SSE plugin reads through an internal
     channel that doesn't suffer from bodyAsChannel's buffering.

   **Root cause (traced through Ktor source)** — `ktor-http-cio/HttpBody.kt:90`
   `parseHttpBody()` routes the body through `skipCancels` which uses
   `HttpClientDefaultPool.useInstance` to buffer chunks. The
   `readUTF8Line()` that the user's code calls reads from the buffered
   `ByteReadChannel`, not from the socket. By the time `readUTF8Line()`
   unblocks, all the data has been pulled into the pool buffer,
   defeating the whole point of streaming. The `parseHttpBody()` body
   branch also throws `IllegalStateException` if `contentLength == -1`
   AND `transferEncoding` is null AND the connection isn't closing —
   but the BufferedChannel swallows this exception, so users never see
   it.

   **Why this is invisible from the trace** — every pipe's
   `API_CALL_SUCCESS` event records `streaming: true` because the
   `streamingEnabled` flag is set. The flag tells you the framework
   ATTEMPTED to stream. It doesn't tell you whether the transport
   actually delivered bytes incrementally. Two equally
   "streaming: true" calls can have completely different chunk
   delivery semantics.

   **Fix** (applied in `GenericOpenAIPipe.executeStreamingDirect`):
   bypass Ktor entirely for the streaming call. Open a direct
   `java.net.HttpURLConnection` with `setChunkedStreamingMode(0)`,
   write the request body, then read SSE events line-by-line via
   `BufferedReader.lineSequence()`. Each `readLine()` blocks until the
   socket receives bytes, so `emitStreamingChunk` fires per SSE delta
   as it arrives — preserving real-time streaming semantics. Keep the
   Ktor client for non-streaming calls (where it works fine). See the
   `executeStreamingDirect` function in `GenericOpenAIPipe.kt` for the
   reference implementation.

   **Alternative if you can't bypass Ktor** — use the Ktor SSE plugin
   (requires Ktor 3.2+). Add `install(SSE)` to the HttpClient config
   and call `client.sse { incoming.collect { event -> ... } }` instead
   of `client.post{}.bodyAsChannel()` + `readUTF8Line()`. The SSE
   plugin's event-stream transport streams incrementally. Verified via
   `KtorSsePluginTest` in TPipeWriter. The downside: SSE plugin
   only works on the `/v1/responses` and `/v1/chat/completions`
   endpoints that emit true SSE; for raw streaming chunk downloads,
   you'd still need to handle the body yourself.

2. **`System.out` line buffering** (already covered in Pitfall 2) — fix
   is `FileOutputStream(FileDescriptor.out)` with explicit
   `.flush()` per chunk.

3. **Application-side buffering in `runBlocking` + dispatcher** —
   if the streaming callback runs on a dispatcher that's blocked by
   the executor, chunks queue until the executor returns. Fix: use
   the daemon `Thread` flush pattern from Pitfall 4, OR register the
   callback on `Dispatchers.Unconfined` so it runs immediately on
   emission.

**JDWP comparison recipe** (the user's suggested debugging path —
useful when buffers 1-3 don't explain the symptom):
- Run the OLD Bedrock-backed TPipeWriter under JDWP attach. Capture
  the stack frame at the moment of each chunk emission.
- Run the NEW GenericOpenAIPipe-backed TPipeWriter under JDWP attach.
  Capture the same.
- Diff: where does the Bedrock version call `flush()` or
  `emitStreamingChunk()` that the GenericOpenAIPipe version skips or
  defers?

Note: shadowJar strips debug symbols by default and produces
obfuscated stack traces like `cage.tpipe.tpipewriter.TPipeWriterApplication`
and `0xc1` thread IDs. For meaningful JDWP comparison, build without
shadowJar: `./gradlew installDist` produces an unpacked distribution
with real class names. Attach with
`java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005`.

**Lesson**: when verifying streaming, the user's terminal — watched
in real time during the model run — is the source of truth. Trace
flags are evidence, not proof. If the trace says `streaming: true`
but the terminal shows chunked output, dig into Ktor buffering
(Pitfall 8 layer 1) and stdout flushing (Pitfall 2) before assuming
the framework is broken.

## Verification recipe — drive EVERY command

After implementing the runtime helper, verify with this workflow:

1. **Enumerate every command** from `/help` output (typically 24-30).
2. **Build a tmux test script** that sends each command and waits an
   appropriate amount of time (longer for LLM-driven commands).
   Example structure:
   ```bash
   for cmd in "/help" "/style" "/settings" "/llm-settings" "/write 'prompt'" \
              "/idea 'topic'" "/chat 'hello'" "/character" "/lorebook" \
              "/summary" "/save" "/export" "/load file" "/clear" \
              "/clear-chat" "/test 'prompt'" "/lore" "/chapters" \
              "/tokens" "/rewrite" "/guide" "/exit"; do
       tmux send-keys -t tpipe "$cmd" Enter
       sleep ${WAIT_FOR[$cmd]:-30}
   done
   ```
3. **Restart the TUI fresh** before the script so the trace file is
   clean for parsing afterward.
4. **Trace parser + grep for FAILURE** events after the script. The
   trace filename contains a hash that changes per restart (e.g.,
   `trace-57cb0ee7-html.html`), so find the latest via `ls -t`.
5. **Check `/llm-settings` status** for every pipe to confirm model
   names actually resolved to the expected value (catches
   local-variable-shadow bugs).
6. **Verify persistence** — `/save`, `/export`, `/load`, `/settings`
   actually write to disk and round-trip. Don't trust "looks right in
   TUI" — `ls -la ~/.TPipeWriter/` and `stat <file>`.
7. **For hangs**: the user suggested JDWP attach with debug
   symbols. Add to your test script:
   ```bash
   java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005 \
        -jar build/libs/TPipeWriter-1.0.0-all.jar
   ```
   Then attach from a separate call. Note: shadowJar strips debug
   symbols by default — for unobfuscated stack traces, build without
   shadowJar (`./gradlew installDist` produces an unpacked distribution
   with real class names).

**Tmux capture technique** (the only way to read scrollback):
```bash
tmux capture-pane -t <session> -p -S -N   # -N = last N scrollback lines
```
Without `-S`, you only see the current viewport. For deep scrollback
use `-S -200` or higher.

**For hangs** the user suggested JDWP attach with debug symbols. Add to
your test script:
```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005 \
     -jar build/libs/TPipeWriter-1.0.0-all.jar
```
Then attach from a separate call. Note: shadowJar strips debug
symbols by default — for unobfuscated stack traces, build without
shadowJar (`./gradlew installDist` produces an unpacked distribution
with real class names).

## What "drive every command" actually found

In the TPipeWriter session that produced this reference:

**Bugs that would have been missed by spot-checking**:
1. `setPipeCompletionCallback` removal caused `runBlocking` to hang
   silently on the writer pipeline (only `/continue` and `/write` would
   surface this — `/chat` worked fine because it doesn't use a Connector)
2. Two pipes had `setModel(gptOssModelName)` shadow bugs (caught by
   `/llm-settings` status, not by visible output)
3. Streaming callback duplication caused duplicate output on every
   `/chat` response (visual, but easy to dismiss as "model glitch")
4. **Reasoning pipe streaming was completely invisible** (Pitfall 7) —
   the user explicitly diagnosed this and pushed back to investigate
   the TPipe library itself, not the application code

**Bugs that wouldn't have been missed** (visible in any test):
- All `compileKotlin` errors caught by gradle
- Smoke tests caught basic API call failures

**Lesson**: The visible-output-only verification approach catches
roughly 50% of bugs. The trace-parser + drive-every-command approach
catches 100%. But when a bug recurs across multiple commands in the
same family (reasoning pipe streams missing across ALL `/chat`,
`/write`, `/continue`, etc.), the bug is in the FRAMEWORK, not in the
application. **Stop patching the app. Patch the framework.**

## Related

- `tpipe-trace-parser` — parse TPipe trace files for the FAILURE grep
- `references/minimax-m3-tpipewriter-pattern.md` — surgical refactor
  patterns (this reference complements it; that one is about the
  cutover, this one is about the runtime plumbing AFTER the cutover)
- `references/minimax-api-quirks.md` — provider-specific API quirks
- `references/live-test-verification.md` — proving a live test is real
- `references/per-family-dispatch.md` — Bedrock-specific dispatcher
  pattern (NOT applicable to GenericOpenAIPipe but useful context)
