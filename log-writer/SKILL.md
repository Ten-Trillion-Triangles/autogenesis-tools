---
name: log-writer
title: Log Writer
description: "Discovers the project's logging system (Logger, LogCategory, LogPriority, format) and expands logging coverage by inserting new log calls in the right places, at the right level, with the right category. Triggers on: add logging, instrument this, log when, expand logging, add debug logs, trace this code, add error logging, instrument function, log entry exit."
---

# Log Writer Skill

## Overview

This skill is the inverse of `log-parser`. Instead of reading logs, it **writes** them.

It discovers the project's existing logging system (Logger class, log levels, categories, configuration), verifies the API surface, then inserts new log calls into source code using that same system — never raw `console.log`, `println`, or `printStackTrace`.

The agent never invents a logging API. It reads the project's `Logger`, mirrors its signature, and uses it. If the project does not have a logging system, the skill installs/uses the conventional one for that language (Python `logging`, JS `console` via a wrapper, Kotlin `Logger`).

## When to Use This Skill

**Trigger phrases:**
- "add logging to X"
- "instrument this function"
- "log when Y happens"
- "expand logging in Z"
- "add debug logs"
- "trace this code path"
- "add error logging for failure case"
- "I want to see when this runs"
- "log the inputs/outputs of X"
- "add a log line for state transition"

**Use this skill when:**
- The user wants visibility into code that is currently silent
- A bug is hard to reproduce and needs a log trail at a decision point
- A pipeline/agent/state machine has black-box steps that need markers
- Production code is missing error context (errors caught but not logged)
- A retry loop, branch, or idempotency gate has no trace of which path fired

**Do NOT use this skill for:**
- Reading/parsing existing logs (use `log-parser`)
- Removing or silencing log calls (manual edit)
- Changing the log format or Logger class itself (architectural change, not expansion)

## Hermes Tool Mapping

| Claude Code | Hermes |
|-------------|--------|
| `find`/`grep` | `search_files(target="files")` / `search_files(target="content")` |
| `read` | `read_file()` |
| `edit` | `patch()` |
| `write` | `write_file()` |
| `bash` | `terminal()` |
| `task(run_in_background=True)` | `delegate_task(role="leaf", ...)` |

## Workflow

### Step 1: Discover the Logging System (MANDATORY)

**Never guess the API. Never assume `console.log` is acceptable.** Find the project's logger first.

1. **Find logger files:**
   ```
   search_files(target="files", pattern="Logger\\.kt|LogWriter|LogCategory|logging/.*\\.kt")
   search_files(target="files", file_glob="*.py", pattern="import logging|from loguru|from structlog")
   search_files(target="files", file_glob="*.js", pattern="logger|logWriter")
   search_files(target="content", pattern="Logger\\.(debug|info|warn|error)\\(")
   ```

2. **Read the Logger implementation:**
   - `Logger.kt` (or `logger.py`, `logger.js`) — the public API
   - `LogCategory.kt` — the available categories (AUTH, NETWORK, DATABASE, UI, SYSTEM, LLM, GENERAL, etc.)
   - `LogPriority.kt` — the level enum (DEBUG, INFO, WARN, ERROR)
   - `LogWriter.kt` — where logs land (file path, rotation, console, localStorage)
   - The `Logger.configure(...)` call site — confirms minPriority and `saveToDisk`

3. **Verify the call signature** (read at least one existing call site):
   ```kotlin
   Logger.debug(LogCategory.NETWORK, "Connected to ${url}")
   Logger.error(LogCategory.DATABASE, "Save failed: ${error.message}")
   ```
   Note: level is a method, not an argument. Category is mandatory. Interpolation uses `${}`.

4. **Note platform behavior** (JVM vs JS, browser vs server) — affects what sinks are available.

5. **Check existing call sites in the target file** before adding new ones:
   ```
   search_files(target="content", path="<target-file>", pattern="Logger\\.(debug|info|warn|error)")
   ```
   Match the style already used (category choice, message format, multi-line vs single-line).

### Step 2: Identify the Target Code

Locate the file/function the user wants instrumented. Read enough context to understand:
- **Entry points** — function start, request received, job started
- **Decision points** — `if`/`when` branches, retry, fallback
- **I/O boundaries** — external calls, DB writes, network
- **Error paths** — `catch` blocks, Result.failure, null returns
- **State transitions** — state machine steps, mode changes
- **Exit points** — return, completion, abort

If the user did not specify what to log, ask. The skill is for *expansion* — it needs a target.

### Step 3: Pick the Right Level and Category

**Level rules:**

| Level | Use for |
|-------|---------|
| `DEBUG` | Verbose tracing of normal flow. Inputs, intermediate state, decision branches. Off in production by default — must be safe to leave on. |
| `INFO` | One-time lifecycle events: started, completed, connected, restored. Major state transitions the operator wants to see. |
| `WARN` | Recoverable problems: retry triggered, stale cache used, fallback path, deprecated API. The system kept going. |
| `ERROR` | Unrecoverable failures that need human attention. Caught exceptions, failed commits, broken invariants. Must include cause/message. |

**Category rules** (use the project's existing enum, do not invent):
- `NETWORK` — RPC bridges, HTTP, WebSocket, gRPC
- `DATABASE` — CloudSave, persistence, VFS
- `AUTH` — login, token, session
- `UI` — KVision widgets, user actions, render
- `SYSTEM` — initialization, shutdown, config
- `LLM` — prompts, responses, agent orchestration
- `GENERAL` — anything that does not fit above

**Default if unsure:** `DEBUG` + `SYSTEM` (operator can filter up later).

### Step 4: Insert the Log Calls

**Use `patch()` to add log lines. Match existing style in the file.**

**Template for a Kotlin function (TTTStyle):**
```kotlin
fun fetchSnapshot(userId: String): Result<Snapshot> {
    Logger.debug(LogCategory.DATABASE, "fetchSnapshot: start userId=${userId}")
    val result = cloudSave.get(userId)
    return result.fold(
        onSuccess = { snapshot ->
            Logger.info(LogCategory.DATABASE, "fetchSnapshot: ok userId=${userId} bytes=${snapshot.size}")
            Result.success(snapshot)
        },
        onFailure = { error ->
            Logger.error(LogCategory.DATABASE, "fetchSnapshot: failed userId=${userId} cause=${error.message}")
            Result.failure(error)
        },
    )
}
```

**Template for Python:**
```python
logger.debug(f"fetchSnapshot: start userId={user_id}")
try:
    snapshot = cloud_save.get(user_id)
    logger.info(f"fetchSnapshot: ok userId={user_id} bytes={len(snapshot)}")
    return snapshot
except Exception as e:
    logger.error(f"fetchSnapshot: failed userId={user_id} cause={e}")
    raise
```

**Template for JS/TS:**
```typescript
logger.debug("fetchSnapshot: start userId=" + userId)
try {
    const snapshot = await cloudSave.get(userId)
    logger.info("fetchSnapshot: ok userId=" + userId + " bytes=" + snapshot.size)
    return snapshot
} catch (error) {
    logger.error("fetchSnapshot: failed userId=" + userId + " cause=" + error.message)
    throw error
}
```

**Message format conventions** (pick one, mirror the file's existing style):
- `"functionName: action key=value key=value"` — most common, parseable
- `"action context message"` — when no inputs to show
- Lowercase, no trailing period, no emoji
- Include enough context to correlate (userId, requestId, turnId) — never secrets

**What to include in a log line:**
- Function name (so the operator knows where)
- Action verb (start/ok/failed/retry/skip)
- 1-3 key=value pairs that distinguish this call (id, count, state, cause)
- Error cause for failures; stack only if Logger implementation does not already include it

**What NOT to include:**
- Tokens, passwords, session secrets
- Full payload bodies (use a size/count instead; log payloads at a deeper level)
- PII unless the project already does
- High-cardinality IDs that prevent grouping (hash them if needed)

### Step 5: Verify the Build

After inserting logs, confirm the project still compiles. The log line must be syntactically valid and the import must be in place.

```bash
# Autogenesis example
./gradlew :server:compileKotlin 2>&1 | tail -20
```

If the build fails, fix the log line (missing import, wrong category, wrong level signature) before claiming done.

### Step 6: Report

Brief summary of what was added. Per the user's project style guide: file lists only — absolute paths + 1-line change summary each. No defensive prose.

```
- /abs/path/Foo.kt:123 — added DEBUG start + INFO ok + ERROR failed around fetchSnapshot
- /abs/path/Bar.kt:45 — added WARN retry with attempt count
```

## Logging Style Rules (TTT convention)

These match the project AGENTS.md "Logging Guidelines" section. The skill enforces them — do not insert log calls that violate them.

- **Use the Logger system for ALL logging.** No raw `console.log`, `println`, `printStackTrace`, `System.out`, `e.printStackTrace()`. No `@ts-ignore` to silence logging-related type errors.
- **Logger initialization is one-time at startup** — never call `Logger.configure(...)` inside a function. The agent's job is to add log *calls*, not reconfigure the logger.
- **Every log call needs a category.** No `Logger.info("hello")` — must be `Logger.info(LogCategory.X, "hello")`.
- **No log spam in tight loops.** If a function runs per-frame or per-message, log once per N (sampling) or only on state transitions.
- **No log calls inside the Logger itself** (infinite recursion).
- **Naming in messages:** `camelCase` for identifiers in messages, `UPPER_SNAKE_CASE` for constants. Never `snake_case` in log strings.
- **No emoji, no "***" decoration, no ANSI color escapes** in the message body.

## Anti-Patterns

| Anti-pattern | Why it is wrong |
|---|---|
| `println("got here")` | Bypasses the Logger, no category, no level control, no file sink, breaks grep conventions. |
| `try { ... } catch (e: Exception) { /* swallow */ }` | If the user asked for logging, log the exception. Silent catches are the opposite of expansion. |
| `Logger.info("starting")` (no category) | Will not compile in the Autogenesis Logger. |
| Logging full request/response bodies at INFO | Token cost + log size + PII risk. Log size/hash, log body at DEBUG. |
| `Logger.error(e)` (just the throwable) | Logger signature wants a string. Include `cause=${e.message}` or `error=${e}`. |
| Adding logs in a hot retry loop without sampling | One retry per second × 10 minutes = 600 log lines. Use sampling or aggregate. |
| Re-`configure`-ing the Logger at runtime | Configuration is startup-only. Calling `Logger.configure(...)` from a code path resets state. |
| Logging inside the Logger's own sink/serializer | Infinite recursion. The Logger is the boundary. |
| Inventing a new category | Add to `LogCategory.kt` if needed, but prefer existing categories. Never type-cast strings as categories. |
| Logging secrets / tokens / session IDs in plaintext | Strip before logging or use a hash. |

## Multi-tier flows (UI → RPC → server → agent → LLM)

When the data crosses multiple process boundaries (e.g., a KVision UI widget → WebSocket RPC → JVM RPC handler → state mutation → server broadcast → agent pipeline → LLM context), the standard single-tier log guidance above is **insufficient**. You need additional log calls at the BOUNDARIES between tiers, plus ENTRY/EXIT pairs around pure-function transforms, to prove the round trip end-to-end.

**The three log points that prove a UI→LLM round trip:**

1. **Sender-side emission** — proves the user gesture produced a payload (already covered by the standard patterns: `save()` or button-click handler gets a DEBUG entry log).
2. **Receiver-side ENTRY, BEFORE any early-return** — proves the request arrived at the server. Place this BEFORE the first `if(blank).return` so it fires even for invalid input.
3. **Receiver-side STATE MUTATION log** — proves the state was actually written. Log AFTER the mutex lock release, AFTER the broadcast.
4. **Pure-function transform ENTRY/EXIT** — proves the value was rendered into the next format (e.g., `buildDelegateGuidanceBlock(rawInstructions): ENTRY rawLength=N trimmedLength=M branch=populated` and `: EXIT blockLength=K`).
5. **Pipeline injection log** — proves the transformed value landed in the context the next consumer reads (e.g., `injected delegate_guidance into strategicPlanningPipe context for ${name} (rawPlayerLength=N blockLength=M)`).
6. **Pre-build snapshot on the orchestrator** — proves the consumer actually READ the value. Log `player.delegateInstructionsLength` immediately before the consumer runs (`TurnHarness.handleAiTakeover: Pre-build snapshot for ${name} — delegateInstructionsLength=N`).

**Why receiver-side ENTRY before early-return matters:** A common mistake is to log only the success path. If `setDelegateInstructions(blankName)` returns early, the operator sees nothing — was the request not sent? sent but rejected? sent and lost in transit? Logging BEFORE the first guard makes every arrival visible.

**Real-world pattern (delegate flow, 2026-06-24):**

```kotlin
// Tier 1: UI sender — DelegateWidget.save()
Logger.debug(LogCategory.UI, "DelegateWidget.save: start player='$playerName' toSendLength=${toSend?.length ?: 0}")
try {
    invoker.invoke("player.setDelegateInstructions", SetDelegateInstructionsRequest(playerName = playerName, instructions = toSend))
    Logger.info(LogCategory.UI, "DelegateWidget.save: submitted player='$playerName' length=${toSend?.length ?: 0}")
} catch (e: Exception) {
    Logger.error(LogCategory.UI, "DelegateWidget.save: failed player='$playerName' cause=${e.message}")
}

// Tier 2: UI receiver — GameplayUI.updateWorldState re-stamping localPlayer
// (proves the server broadcast came back with the new value)
Logger.info(LogCategory.UI, "[TRACE] [GameplayUI.updateWorldState] localPlayer reassigned for '$name' — delegateInstructionsLength=${updatedLocalPlayer.delegateInstructions?.length ?: 0}")

// Tier 3: RPC receiver — PlayerDelegateRpcHandlers.setDelegateInstructions
// (proves the request arrived; log BEFORE the first early-return)
Logger.debug(LogCategory.NETWORK, "PlayerDelegateRpcHandlers.setDelegateInstructions: ENTRY player='${request.playerName}' conn=${ctx.connectionId} incomingLength=${request.instructions?.length ?: 0}")
// ... validation ...
WorldManager.worldMutex.withLock {
    player.delegateInstructions = normalizedInstructions
}
Logger.info(LogCategory.NETWORK, "PlayerDelegateRpcHandlers.setDelegateInstructions: player='${player.name}' length=${normalizedInstructions?.length ?: 0} (conn=${ctx.connectionId})")
UiSignalRpcHandlers.broadcastWorldUpdate(WorldManager.world)

// Tier 4: Pure-function transform — buildDelegateGuidanceBlock
Logger.debug(LogCategory.LLM, "buildDelegateGuidanceBlock: ENTRY rawLength=${rawLength} trimmedLength=${text.length} branch=${branch}")
// ... compute block ...
Logger.debug(LogCategory.LLM, "buildDelegateGuidanceBlock: EXIT branch=${branch} blockLength=${block.length}")

// Tier 5: Pipeline injection — strategicPlanningPipe.preValidationMiniBankFunction
Logger.info(LogCategory.LLM, "PlayerAgent: injected delegate_guidance into strategicPlanningPipe context for ${playerData.name} (rawPlayerLength=${rawDelegateLength} blockLength=${delegateBlock.length})")

// Tier 6: Orchestrator pre-build — TurnHarness.handleAiTakeover
Logger.info(LogCategory.LLM, "TurnHarness.handleAiTakeover: Pre-build snapshot for ${player.name} — delegateInstructionsLength=${player.delegateInstructions?.length ?: 0} hasDelegateGuidance=${!player.delegateInstructions.isNullOrBlank()}")
```

**Verification recipe — confirm the round trip in browser DevTools:**

After clicking SAVE in the UI, search the captured logs for each tier's signature:

```javascript
// From the autogenesis_logs localStorage key or a console-hook capture
window.__capturedLogs
  .filter(l => /Delegate|DELEGATE|delegateGuidance|inject/.test(l.msg))
  .map(l => `[${l.level}] ${l.msg.substring(0, 250)}`)
// Should produce 7 entries in order:
// 1. ScoreDisplay: DELEGATE button clicked
// 2. GameplayUI: Opening Delegate Widget from score bar
// 3. DelegateWidget.show: opening for player='...' priorLength=N
// 4. DelegateWidget.save: submitted delegate instructions for '...' (length=N)
// 5. DelegateWidget.hide: closing for player='...'
// 6. (server log, not browser) PlayerDelegateRpcHandlers.setDelegateInstructions: ENTRY player='...' incomingLength=N
// 7. (browser, on broadcast roundtrip) [TRACE] [GameplayUI.updateWorldState] localPlayer reassigned for '...' — delegateInstructionsLength=N
```

Then on the server log:
```bash
grep -E "PlayerDelegateRpcHandlers|setDelegateInstructions|delegate_guidance|injected delegate" /tmp/server-dev.log
# Should produce 3+ entries: ENTRY, INFO success, buildDelegateGuidanceBlock ENTRY/EXIT, injection INFO
```

If any tier is silent, the round trip is broken at that boundary.

**Anti-pattern: only logging the success path.** If the only log calls are on the happy path, you cannot distinguish "request never sent" from "sent but server rejected" from "server wrote but broadcast failed." Tier 2 (RPC receiver ENTRY) is the single most valuable log — it answers "did the request arrive at all?"

## What to Log — Decision Guide

When the user says "add logging to X" without specifying what, use this checklist on the function/file:

| Signal in the code | Add a log at |
|---|---|
| Function entry with non-trivial inputs | `DEBUG` start with key params |
| `try { ... } catch (...)` | `ERROR` failed with cause |
| `Result.fold(onSuccess, onFailure)` | Both arms |
| `if (retryCount < max) { retry() }` | `WARN` retrying with attempt |
| State machine transition (`when (state)` arms) | `DEBUG` entering state, `INFO` on terminal state |
| External call (RPC, DB, network) | `DEBUG` start + `INFO` ok / `ERROR` failed |
| Cache miss / fallback path | `WARN` fallback used |
| Idempotency / consumed-sentinel gate | `DEBUG` gate result (ok / re-armed / skipped) |
| Shutdown / cleanup path | `INFO` lifecycle event |
| Performance-critical section | `DEBUG` enter + `DEBUG` exit with elapsed ms |

If the function does not have any of these, the user may be over-requesting — confirm before adding cosmetic logs.

### Multi-Layer Data Flow Tracing

When the same payload flows through several layers (UI click → WebSocket → RPC handler → world state → agent context → LLM prompt), the goal is to **prove end-to-end delivery**, not just instrument each function in isolation:

- Add a log at every layer boundary on the path
- Use the same stable correlation key (player name, request id, session id) in every log line so a single grep reconstructs the trace
- Log the payload **summary** (length, count, type) — not the full content — at the outer layers; reserve full-content logging for the deepest DEBUG level
- Tag each line with its layer (`ClassName.method:` prefix is already standard — keep it)
- Pick the layer's natural `LogCategory` (UI for client events, NETWORK for RPC, LLM for agent context)

Example trace for "delegate instructions reach the player agent":

- UI: `DelegateWidget.save: submitting length=234`
- RPC: `PlayerDelegateRpcHandlers.setDelegateInstructions: ENTRY player='X' incomingLength=234`
- Agent: `PlayerAgent: injected delegate_guidance for X rawPlayerLength=234 blockLength=312`

Three lines, one correlation key (`X`), the payload length carried through every hop. A single `grep 'X' ~/.autogenesis/logs/server-*.log` proves the data made it.

## Examples

**Example 1: User says "add logging to the snapshot save path"**

Discovery:
- `server/src/main/kotlin/.../CloudVFS.kt:saveUserRecordFromJsonString` — the target
- `Logger.debug/info/warn/error(LogCategory, String)` — the API
- File already uses `Logger.info(LogCategory.DATABASE, ...)` elsewhere — mirror it

Inserted:
```kotlin
// before: silent
fun saveUserRecordFromJsonString(userId: String, key: String, json: String): Result<Unit> {
    Logger.debug(LogCategory.DATABASE, "saveUserRecordFromJsonString: start userId=${userId} key=${key} bytes=${json.length}")
    val result = cloudSaveClient.put(userId, key, json)
    return result.fold(
        onSuccess = { Logger.info(LogCategory.DATABASE, "saveUserRecordFromJsonString: ok userId=${userId} key=${key}"); Result.success(Unit) },
        onFailure = { e -> Logger.error(LogCategory.DATABASE, "saveUserRecordFromJsonString: failed userId=${userId} key=${key} cause=${e.message}"); Result.failure(e) },
    )
}
```

**Example 2: User says "log the retry attempts in this loop"**

```kotlin
for (attempt in 1..maxRetries) {
    if (attempt > 1) Logger.warn(LogCategory.NETWORK, "rpc: retry attempt=${attempt} of ${maxRetries}")
    val result = rpc.invoke()
    if (result.isSuccess) return result
    delay(backoff(attempt))
}
Logger.error(LogCategory.NETWORK, "rpc: exhausted retries maxRetries=${maxRetries}")
```

**Example 3: User says "I cannot tell which branch fired in this when"**

```kotlin
when (decision) {
    Decision.ACCEPT -> {
        Logger.debug(LogCategory.LLM, "decision: ACCEPT reason=${reason} confidence=${confidence}")
        accept()
    }
    Decision.REJECT -> {
        Logger.debug(LogCategory.LLM, "decision: REJECT reason=${reason} confidence=${confidence}")
        reject()
    }
    Decision.DEFER -> {
        Logger.info(LogCategory.LLM, "decision: DEFER reason=${reason}")
        defer()
    }
}
```

## Discovery Output (Mental Checklist)

After Step 1, you should be able to answer:

- What is the logger class? (e.g., `org.ttt.autogenesis.logging.Logger`)
- What is the call signature? (e.g., `Logger.debug(LogCategory.X, "msg")`)
- What categories exist? (read `LogCategory.kt`)
- What levels exist? (read `LogPriority.kt` or method names)
- Where do logs land? (JVM file? browser localStorage? both?)
- What is the current minPriority? (from `Logger.configure(...)` startup call)
- Are there existing log calls in the target file? (mirror their style)
- Is the target on the JVM or JS side? (changes file sink)

If any answer is "I don't know," re-run Step 1. Do not proceed with assumptions.

## Error Handling

| Problem | Resolution |
|---|---|
| No logger found in project | The project does not have a logging convention. STOP — ask the user how to log, do not invent one. |
| Logger found but no categories defined | Read the existing call sites to see what categories are in use. Use those. |
| Build fails after insertion | Missing import for `Logger` or `LogCategory`. Add the import. |
| Logger is `expect`/`actual` (KMP) | The call site works the same in commonMain; verify the actual implementation exists for the target platform. |
| Log call inside a coroutine | Logging is suspending-safe in most impls; verify by reading `LogWriter`. If unsafe, wrap in `withContext(Dispatchers.IO)`. |
| User asks for log spam removal | This skill is for expansion. Point them at the log-parser to see what is being emitted, then manually trim. |

## Related Skills

- `log-parser` — the inverse. Discovers the log format and parses existing logs.
- `systematic-debugging` — for root-cause analysis when deciding *where* to add logs.
- `ttt-code-styler` — for KDoc/brace rules applied to the modified code.
- `codebase-spec-generator` — for projects where the logging system itself needs documenting.
- `simplify-code` — for follow-up cleanup if expansion produced redundant calls.
