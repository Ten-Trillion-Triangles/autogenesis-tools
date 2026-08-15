---
name: tpipe-pcp-code-execution
description: "TPipe PCP (Pipe Context Protocol) — the multi-transport tool/function execution surface that turns LLM tool calls into sandboxed actions. Covers the six transports (Stdio/Http/Tpipe/Python/Kotlin/JavaScript), four security managers with their threat models, the dispatcher and transport-validation policy lock, output capture behavior across the three code-execution sandboxes, and the prompt-injection surface that tells the LLM what it can do. Load when explaining how PCP works, when debugging PCP execution (output empty, deadlock, timeout not enforced, validation reject), when extending PCP with a new transport or language executor, when auditing a security manager's defaults, or when wiring PCP into a pipe/agent context."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tpipe, pcp, code-execution, sandbox, python, kotlin, javascript, subprocess, security, dispatcher, output-capture, deadlock]
    homepage: https://github.com/ten-trillion-triangles/TPipe
---

# TPipe PCP — Pipe Context Protocol

PCP is the tool-execution surface that turns a TPipe LLM call into a sandboxed action. Every tool an LLM can invoke inside a TPipe pipeline — every shell command, every Python snippet, every HTTP request, every native TPipe function call — passes through PCP. It is not a single sandbox; it is a dispatch protocol with six execution transports, four independently-configurable security managers, a transport router the dispatcher enforces, and a prompt-injection generator that tells the LLM what it can do.

Module location: `TPipe/src/main/kotlin/PipeContextProtocol/` (~7,900 lines, 27 files).

## The Rule

**PCP is a router, not an authority.** All state lives in the executors and their security managers. The dispatcher's only job is to enforce "this context allows transport X" — bypass the dispatcher and the cross-transport policy is gone.

## The six transports

| Transport | Executor | Subprocess? | Sandbox model |
|---|---|---|---|
| `Stdio` | `StdioExecutor` | yes (shell) | command-name allowlist + canonical-path boundary + per-level command classification + injection regex |
| `Http` | `HttpExecutor` | no (Ktor) | host allowlist + SSRF IP block + header scan + per-level resource caps + auth type validation |
| `Tpipe` | `PcpFunctionHandler` | no (in-process) | function-name whitelist + parameter signature validation |
| `Python` | `PythonExecutor` | yes (subprocess) | AST subprocess validator + regex import/function/pattern gates + package allowlist + size/timeout caps |
| `Kotlin` | `KotlinExecutor` | no (JSR-223) | regex import/function/pattern gates + six capability flags (reflection, classloader, file, network, process, TPipe introspection) |
| `JavaScript` | `JavaScriptExecutor` | yes (Node) | module allowlist + size/timeout caps |

The cross-cutting constant: **every transport that crosses a process or network boundary is strict-by-default; the transport that runs inside the JVM is capability-flagged; the transport that is a syscall is allowlist-classified.** Threat models differ, defenses match.

## The request lifecycle

```
PcPRequest → PcpExecutionDispatcher.executeRequest()
  → validateTransport(request, context)            # policy lock
    → routeRequest(transport) → PcpExecutor       # pure switch
      → executor.mergeContextOptions(req, ctx)    # ctx wins for security
        → executor's SecurityManager.validate()   # per-language rules
          → executor.run()                        # ProcessBuilder / JSR-223 / in-process
            → PcpRequestResult { success, output, executionTimeMs, transport, error? }
```

`PcpExecutionDispatcher.kt` is the single chokepoint. `validateTransport()` rejects mismatches between `context.transport` and the request's effective transport unless the context is `Auto`. `routeRequest()` is a pure switch over the `Transport` enum — anything other than the six real transports throws `IllegalArgumentException`. Multi-request batches run in parallel via `coroutineScope { async { ... } }`.

## Output capture across the code-execution sandboxes

The user-facing wire format is two-field: `PcpRequestResult.output: String` (legacy merged string, back-compat) and `PcpRequestResult.outputBuffer: BufferedOutput?` (channel-separated payload — see "BufferedOutput contract" below).

Every subprocess executor (Python, JavaScript) routes through the shared `SubprocessOutputCapture` helper. The Kotlin in-process JSR-223 executor uses a separate `engine.eval()` on a daemon thread + `Thread.join(timeoutMs)`. See `references/executor-output-capture.md` for the post-hardening capture snippets.

| Sandbox | Subprocess / in-process | Capture path | Deadlock past ~64KB stdout | Timeout enforced | stdout/stderr channels |
|---|---|---|---|---|---|
| **Python** | subprocess (`ProcessBuilder`) | `SubprocessOutputCapture.capture()` parallel `async(IO) { readAllBytes() }` | **no** (parallel + drain) | yes (`waitFor` + `destroyForcibly`) | separated in `outputBuffer`; legacy `output` is `stdout + "\nSTDERR: " + stderr` |
| **Kotlin** | in-process (JSR-223) | daemon thread + `Thread.join(timeoutMs)` — engine thread is **uninterruptible** | n/a | yes (dispatcher returns at `timeoutMs`; engine keeps running until JVM exit) | separated via two `StringWriter`s |
| **JavaScript** | subprocess (`ProcessBuilder`) | `SubprocessOutputCapture.capture()` parallel `async(IO) { readAllBytes() }` | **no** | yes | separated in `outputBuffer` |

All three executors now run their process starts through `PcpThreadPool`, which is capped at `Runtime.availableProcessors() * 2` workers with `SynchronousQueue` + `AbortPolicy`. Saturated submissions throw `RejectedExecutionException` and the executor converts to `PcpRequestResult(success=false, error="Executor saturated: ...")`.

## BufferedOutput contract

```kotlin
@Serializable
data class BufferedOutput(
    val stdout: String?,         // populated when stdout bytes are valid UTF-8
    val stderr: String?,         // populated from the dedicated stderr pipe
    val binary: ByteArray?,      // populated when stdout bytes are NOT valid UTF-8
                                 // (exactly one of stdout/binary is set, never both)
    val totalBytes: Long,        // full stream byte count, even when overflowed
    val truncated: Boolean,      // true when stdout was held to the in-memory cap
                                 // and the remainder spilled to a temp file
    val overflowPath: String? = null  // path to the temp file holding the full
                                       // stdout bytes (deleteOnExit)
)
```

`PcpRequestResult.outputBuffer` is nullable with a default of `null`. Every existing construction site (`PcpRequestResult(success, output, executionTimeMs, transport, error)`) keeps compiling and working unchanged — back-compat is preserved by the default.

**Wire-format back-compat**: callers reading `result.output: String` get the same merged string as before (`stdout + "\nSTDERR: " + stderr` when stderr non-empty). New code should prefer `result.outputBuffer` for channel separation.

**Overflow-to-temp-file behavior**: any output past the executor's `maxInMemoryBytes` cap (256 KB default) spills to a temp file. `outputBuffer.totalBytes` always reflects the full stream content, even when overflowed. `outputBuffer.truncated = true` and `outputBuffer.overflowPath` references the spill file. Output size is therefore unbounded while resident memory stays bounded.

**UTF-8 auto-detect**: the capture helper uses `Charset.forName("UTF-8").newDecoder()` with the default `CodingErrorAction.REPORT`. On `MalformedInputException`, the raw bytes are surfaced as `binary: ByteArray?` instead of substituting U+FFFD.

## The three concrete failure modes — RESOLVED

The pre-hardening PCP had three blocking bugs. All three are fixed in this revision.

**1. Python — deadlock past ~64KB stdout. RESOLVED.**
The capture helper now reads stdout and stderr **in parallel** via `async(Dispatchers.IO) { stream.readAllBytes() }`, so the OS pipe buffer never fills before the parent can drain it. Output past `maxInMemoryBytes` spills to a temp file so size is unbounded. The pre-fix pattern `process.inputStream.bufferedReader().readText()` followed by `process.errorStream.bufferedReader().readText()` (sequential blocking) is gone from every executor.

**2. Kotlin — timeout not enforced. RESOLVED (with documented leak).**
`KotlinExecutor.execute()` now runs `engine.eval()` on a daemon thread and joins with `Thread.join(timeoutMs)`. When the timeout fires, the dispatcher returns a clean `PcpRequestResult(success=false, error="Kotlin script timed out after Xms")`. **Acknowledged leak**: JSR-223's `engine.eval()` is uninterruptible, so the daemon engine thread keeps running until the script returns or the JVM exits. For untrusted Kotlin scripts, wrap the dispatcher call in an outer `withTimeoutOrNull` at the pipe/manifold layer.

**3. Binary output corruption. RESOLVED.**
`SubprocessOutputCapture` decodes via UTF-8 with `CodingErrorAction.REPORT`. Invalid UTF-8 bytes surface as `outputBuffer.binary: ByteArray?` with `outputBuffer.stdout = null`. Subprocess script files are written with `Charsets.UTF_8` so non-ASCII source survives platform-default charset transcoding.

### Dead config: `PythonContext.captureOutput` — RESOLVED

The previous `PythonContext.captureOutput: Boolean` field is now honored. Setting `captureOutput = false` skips capture entirely (returns empty `outputBuffer`). The legacy field still defaults to `true` for back-compat.

## The four security managers — at a glance

| Manager | Mode | Default | Strictness driver |
|---|---|---|---|
| `CommandSecurityManager` | Allowlist + 4-tier command classification (SAFE/RESTRICTED/DANGEROUS/FORBIDDEN) + injection regex | RESTRICTED | Command name + arg injection |
| `HttpSecurityManager` | Allowlist + SSRF IP check + header scan + per-level resource caps | BALANCED | Network egress to internal services |
| `PythonSecurityManager` | AST subprocess + regex + per-level caps | BALANCED | Script-level dynamic exec |
| `KotlinSecurityManager` | Regex + 6 capability flags | All flags off | JVM-internal access |
| `JavaScriptSecurityManager` | Module allowlist | Blocklist mode | Node.js fs/net/child_process |

The Python AST validation is **defense-in-depth**: `PythonSecurityManager.performAstValidation()` writes the script and a blocked-list to a Python subprocess running `ast_validator.py` (loaded from `src/main/resources/ast_validator.py`, cached to temp file with `deleteOnExit()`), runs with a 10-second timeout, parses the JSON `{isValid, errors, warnings}`, returns the verdict. Catches what regex misses (dynamic imports via `__import__("os".replace("o","s"))`). The regex layer still runs after, as belt-and-suspenders.

The HTTP SSRF protection is fail-closed: `checkSsrfProtection()` resolves the URL's host via `InetAddress.getByName()` and tests against `127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, ::1/128, fc00::/7, fe80::/10`. On resolution failure returns `SsrfCheckResult(true, null)` — the comment is explicit: "an attacker might use a non-resolvable host that resolves to a private IP during the actual request window."

## The prompt-injection surface — `PcpInstructionGenerator`

`PcpInstructionGenerator.kt` converts a `PcpContext` into a markdown-shaped instruction block for the system prompt. Sections per language:

- **MEMORY ACCESS** — TPipe introspection on/off; exposed bindings list (Kotlin only).
- **FILE SYSTEM ACCESS** — read/write/delete allowed/blocked; allowed + forbidden directory lists; working directory.
- **IMPORTS AND PACKAGES** — allowlist vs blocklist mode with current entries.
- **CAPABILITIES** — network, process exec, reflection, classloader, timeout, versions, paths.

Each language has its own formatter (`generateKotlinInstructions`, `generatePythonInstructions`, `generateJavaScriptInstructions`) and a code-execution-guide block showing the LLM the JSON shape of a request. The other half of the LLM-facing contract is `setJsonInput(PcPRequest::class)` at the pipe level, which injects the schema so the model knows the JSON shape.

## Anti-patterns

From the module's `AGENTS.md` plus the post-hardening contract:

1. **Never bypass `PcpExecutionDispatcher.routeRequest()`.** The dispatcher's transport-validation is the single point that enforces "this context allows Http but not Python." Skipping it = sandbox escape.
2. **Never share a `SecurityManager` across language executors.** Each language has its own because the threat models differ — Python's regex+AST is wrong for Kotlin (block `::class`, not `__import__`), and Kotlin's regex-only is wrong for Python (AST catches what regex can't).
3. **Never call `FunctionInvoker.invoke()` without validating parameters first.** Function invocations run in the host JVM with full TPipe access. Parameter validation is the only barrier.
4. **Context options override request options for security settings.** `mergeContextOptions()` always favors the developer-set context over what the LLM requested. The request can request anything; the context decides what's allowed.
5. **Never call `process.inputStream.readText()` / `process.errorStream.readText()` directly.** Always route through `SubprocessOutputCapture.capture()` to avoid the pipe-buffer deadlock.
6. **Never call `process.waitFor()` without `timeoutMs`.** The timeout is the only signal the dispatcher can give — without it the JVM hangs on a stuck child.
7. **Never start a `ProcessBuilder` outside `threadPool.submit { ... }`.** Bypasses the concurrency bound and can spawn unbounded OS processes.
8. **Never expect Kotlin's `while (true) {}` to be killed by `timeoutMs`.** It isn't — the JSR-223 engine thread is uninterruptible and leaks until JVM exit. Wrap untrusted Kotlin scripts in an outer `withTimeoutOrNull` at the pipe layer.

## Key files

| File | Role |
|---|---|
| `PipeContextProtocol/Pcp.kt` | Transport / Permissions / ParamType / StdioContextOptions enums + PcpContext |
| `PipeContextProtocol/PcpExecutionDispatcher.kt` | Transport validation + routeRequest + parallel executeRequests |
| `PipeContextProtocol/PcpFunctionHandler.kt` | Tpipe transport — function-name whitelist + signature validation |
| `PipeContextProtocol/FunctionInvoker.kt` | Native function invocation with parameter validation + type conversion |
| `PipeContextProtocol/FunctionRegistry.kt` | Function + type converter registry |
| `PipeContextProtocol/StdioExecutor.kt` | Shell executor (ONE_SHOT/INTERACTIVE/CONNECT/BUFFER_REPLAY modes) |
| `PipeContextProtocol/HttpExecutor.kt` | HTTP executor (Ktor via TPipe `httpRequest`) |
| `PipeContextProtocol/PythonExecutor.kt` | Subprocess executor with temp-file script + parallel-stream capture |
| `PipeContextProtocol/KotlinExecutor.kt` | JSR-223 executor with single-StringWriter capture |
| `PipeContextProtocol/JavaScriptExecutor.kt` | Subprocess executor with parallel-stream capture |
| `PipeContextProtocol/SubprocessOutputCapture.kt` | Parallel stdout/stderr capture + UTF-8 auto-detect + overflow-to-temp-file |
| `PipeContextProtocol/PcpThreadPool.kt` | Bounded executor (`availableProcessors() * 2`) with `RejectedExecutionException` backpressure |
| `PipeContextProtocol/PythonSecurityManager.kt` | AST subprocess + regex + per-level caps |
| `PipeContextProtocol/KotlinSecurityManager.kt` | Regex + 6 capability flags |
| `PipeContextProtocol/CommandSecurityManager.kt` | Command allowlist + 4-tier classification + injection regex |
| `PipeContextProtocol/HttpSecurityManager.kt` | SSRF IP block + host allowlist + header scan + resource caps |
| `PipeContextProtocol/PcpInstructionGenerator.kt` | Converts PcpContext → system prompt injection block |
| `PipeContextProtocol/PcpRegistry.kt` | PCP registry operations |
| `PipeContextProtocol/PcpResponseParser.kt` | Parses response transport |
| `PipeContextProtocol/PcpStdioHost.kt` | STDIO host implementation (external systems call TPipe via stdin/stdout) |
| `PipeContextProtocol/StdioSessionManager.kt` | Persistent session lifecycle |
| `PipeContextProtocol/StdioBufferManager.kt` | Per-channel ring buffer (BufferType.INPUT/OUTPUT/ERROR) |

## See Also

- `references/executor-output-capture.md` — post-hardening capture snippets
- `references/security-managers.md` — per-manager threat model, validation gates, and defaults
- `references/pcp-pipe-wiring.md` — `Pipe.setSystemPrompt` three-mode injection block, `processPcpResponse` parse path, `PcpRegistry` global access, and the five known gaps in the Pipe-side wiring (Stdio not in `SubprocessOutputCapture`, Stdio not in `PcpThreadPool`, no outer `withTimeoutOrNull` for Kotlin leak, `hasPcpTools` missing Kotlin/JS, path-only configs not detected).
- `references/build-gotchas.md` — TPipe build/gradle/test quirks
- `references/arkvcs-rpc-fix-parallel.md` — **Closure-serialization → name-registry dispatch** fix for ArkVcs. Documents how `Request.function` carrying a `kotlin.coroutines` closure is unserializable, and how PCP's `FunctionRegistry` + `FunctionInvoker` + string-name request pattern solves it. Apply when diagnosing any RPC system that tries to send function references over the wire.
