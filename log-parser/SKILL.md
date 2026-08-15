---
name: log-parser
description: "Scans project to identify logging framework and log locations; generates Python scripts to parse/search logs. Triggers on: parse logs, search logs for, analyze application logs, scan logs, find in logs, log parser, extract log entries, investigate bugs in logs. ALSO USE for structural source-code assertions against deleted/renamed helpers — match the function-call shape (e.g. `fun X\\s*\\(`) not the bare token, otherwise KDoc comments and historical-context references false-positive the test."
---

# Log Parser Skill

## Overview

This skill discovers the logging system used in a project by examining the codebase, then generates a tailored Python script to parse, search, and analyze log entries. The Python script is written to disk and executed via `terminal()` to avoid context window overflow.

## When to Use This Skill

**Trigger phrases:**
- "parse logs"
- "search logs for [term]"
- "analyze application logs"
- "scan logs"
- "find in logs"
- "log parser"
- "extract log entries"
- "investigate bugs in logs"

**Use this skill when:**
- You need to search for specific patterns or errors in log files
- You want to analyze logging output from your application
- You need to extract and filter log entries by level, time, or content
- You want to understand what logging framework a project uses

## Hermes Tool Mapping

| Claude Code | Hermes |
|-------------|--------|
| `find`/`grep` | `search_files(target="files")` / `search_files(target="content")` |
| `read` | `read_file()` |
| `write` | `write_file()` |
| `task(run_in_background=True)` | `delegate_task(role="leaf", ...)` |
| `bash` | `terminal()` |

## Workflow

### Step 1: Discover Logging System (MANDATORY)

**Search the codebase to learn how logging works:**

1. **Find logging-related files:**
   ```
   search_files(target="files", file_glob="*.kt", path=".", pattern="Logger|LogWriter|LogCategory|logging")
   search_files(target="files", file_glob="*.py", path=".", pattern="import logging|from loguru|from structlog")
   search_files(target="files", file_glob="*.js", path=".", pattern="logger|logWriter|console\\.log")
   ```

2. **Examine logging implementation:**
   - Read `Logger.kt`, `LogWriter.kt`, `LogCategory.kt`, `LogPriority.kt` if they exist
   - Look for `expect`/`actual` patterns (Kotlin multiplatform)
   - Identify `LogEntry` data class structure
   - Find log format pattern (timestamp, level, category, message)

3. **Find log storage configuration:**
   - Search for `FileWriter`, `add_file`, `FileHandler` patterns
   - Look for directory paths like `~/.autogenesis/logs/` or project-specific locations
   - Find file naming patterns (timestamps, prefixes)

4. **Document what you learned:**
   - Log format structure
   - Log directory path
   - File pattern naming
   - Categories if applicable

### Step 2: Generate Python Parser Script

**Create a Python script tailored to the discovered format:**

Write to `/tmp/log_parser_<timestamp>.py` with:
- Regex pattern matching the discovered format
- Filtering by level, category, time range
- Pattern search functionality
- Streaming to handle large files

**Template structure:**
```python
#!/usr/bin/env python3
"""Auto-generated log parser for discovered logging system."""

import re
import sys
from datetime import datetime
from pathlib import Path

# Discovered log format — adapt regex to actual format found
LOG_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2}T[\d:.]+Z) \[(\w+)\] \[(\w+)\]: (.+)$')

LOG_DIRECTORY = Path.home() / ".autogenesis" / "logs"
LOG_FILES = []  # discovered files

def parse_line(line):
    """Parse a single log line."""
    match = LOG_PATTERN.match(line.strip())
    if match:
        return {
            'timestamp': match.group(1),
            'level': match.group(2),
            'category': match.group(3),
            'message': match.group(4)
        }
    return None

def filter_logs(lines, level=None, category=None, pattern=None):
    """Filter log lines by criteria."""
    for line in lines:
        entry = parse_line(line)
        if not entry:
            continue
        if level and entry['level'] != level.upper():
            continue
        if category and entry['category'] != category.upper():
            continue
        if pattern and pattern.lower() not in entry['message'].lower():
            continue
        yield entry

def main():
    # ... implement filtering logic
    # ... print formatted results
```

### Step 3: Execute the Script

**Run the generated Python script via terminal:**
```bash
python3 /tmp/log_parser_<timestamp>.py [options] > /tmp/log_results.txt
cat /tmp/log_results.txt
```

**Common options:**
- `--level DEBUG|INFO|WARN|ERROR` - Filter by log level
- `--category CATEGORY` - Filter by log category
- `--pattern TEXT` - Search for text in messages
- `--file FILENAME` - Analyze specific log file
- `--limit N` - Limit output to N lines
- `--show-errors` - Show lines that failed to parse

### Step 4: Report Results

**Present findings clearly:**
- Show matching log entries with context
- Summarize counts by level, category
- Highlight error patterns
- Provide file paths for further investigation

## Discovery Checklist

When exploring a codebase, look for:

| File Pattern | Purpose |
|--------------|---------|
| `**/Logger.kt` | Main logging interface |
| `**/LogWriter.kt` | Log writing implementation |
| `**/LogCategory.kt` | Log categorization enum |
| `**/LogPriority.kt` | Log level priorities |
| `**/LogEntry.kt` | Log entry data class |
| `**/logging/*.kt` | Logging package files |

| Configuration | Where to Look |
|---------------|---------------|
| Log directory | In LogWriter implementation |
| File naming | In log file creation code |
| Format pattern | In `formatEntry()` or similar method |
| Categories | In LogCategory enum |

**Autogenesis-specific references:**
- `references/autogenesis-logging.md` — log format, categories, trace file lifecycle, VALIDATOR_TRUTH pipe lifecycle interpretation.
- `references/browser-log-disconnect-patterns.md` — browser WebSocket disconnect patterns, `StandaloneCoroutine was cancelled` interpretation, browser vs server log correlation.

- **Autogenesis bug investigation:** `references/autogenesis-bug-investigation.md` — confirmed/partial/unconfirmed bug inventory (currently 26 entries as of 2026-07-01 — the original 19 plus BUG 20/21 from the auto-restore race family, BUG 22/23/24 from the post-restore state family, BUG 25 from the disconnect-time-persistence-saves-empty-world family, and BUG 26 from the resume-dialog-reappears-on-every-SSE-reconnect family), grep patterns per bug, trace directory inventory, and the Session-Lifetime vs In-Flight Signal anti-pattern write-up. BUG 22/23/24 fixed 2026-06-26 in the same session as the report (post-restore state hydration via `hydratePostRestoreState`); BUG 25 discovered and fixed 2026-06-27 in a single session (gated save-on-disconnect on `WorldManager.humanPlayerHasJoinedOnce` set inside `awaitPlayerAction`); **BUG 26 is the OPEN entry as of 2026-07-01** (NOT YET FIXED — dialog re-mounts every ~45-60s; two stacked bugs: server-extend push fires on every SSE reconnect, AND client `ResumeAvailabilityListener.mountResumeDialog` lacks idempotency). The Session-Lifetime anti-pattern from BUG 14 has been reinforced multiple times — by BUG 25 (save-gate case) and now by BUG 26 (push-on-reconnect case, which is a different but related family: "side effect fires inside a per-request handler for a long-lived connection without dedup"). **Post-restore state hydration (BUG 22/23/24):** `references/post-restore-state-fixes-2026-06-26.md` — the "applyGameSnapshot is a state-RESTORE funnel, not a state-INITIALIZE funnel" lesson, the diagnostic grep recipes for all three symptoms, the fix shape, and the deliberately-deferred follow-up (consolidate per-turn setup into a single `rehydratePostRestoreState` funnel).

**Trace save execution patterns:** `references/promptmanager-trace-saving.md` — correct pattern (after extractJson + catch block), broken pattern (before extractJson), debugging missing traces.

## Bug Investigation Workflow

This skill has a **second mode** beyond general log parsing: **bug investigation from user-reported issues**. When a user says "investigate these bugs from logs" or provides a list of reported issues, follow this workflow.

### Trigger Distinction

| Goal | Use |
|------|-----|
| Find general patterns/errors | Standard Steps 1-4 above |
| Investigate specific user-reported bugs | Bug Investigation Mode below |

### Bug Investigation Mode

**Step 0: Parse the bug list**
The user provides bugs as a list with symptom descriptions. Some include hints about cause or severity.

**Step 1: Identify key search terms per bug**
For each bug, derive 2-3 grep/search patterns that would appear in logs if the bug exists. Common patterns:
- Bug-specific error strings
- State indicators like `"thinkingUpdates":[]` (thinking capture failure)
- Placeholder values like `turnResult: "(Planning...)"` (JSON truncated mid-stream)
- Category + level combinations (e.g., `ERROR [SYSTEM]`)

**Step 2: Search across log files, not just the most recent**

**First, check which Autogenesis servers are running** — there are TWO servers with different port assignments:

| Server | Gradle task | REST/WS port | gRPC port |
|--------|-------------|---------------|-----------|
| **`server-extend`** | `:server-extend:run` | **7070** | 9092 |
| **`server` (main)** | `:server:run` | **9080** | 9091 |

**This is the actual mapping** — verified against `debugger/scripts/start_servers.sh` which starts `:server-extend:run` first on 7070 then `:server:run` on 9080. (Earlier versions of this skill had the ports reversed — that was wrong.)

Browser's `WebSocketRpcBridge` connects to **port 9080 (main server)**. Browser's `CommanderDataSync` REST calls go to the **AccelByte production URL** (`https://prod.gamingservices.accelbyte.io/rpc`), NOT to local server-extend. `server-extend` (port 7070) handles matchmaking, cloud save proxy, and commander creation pipeline; the account hydration path goes through production.

**Which log file maps to which port?**

| Port | Server | Log file | Useful for |
|------|--------|----------|-------------|
| 7070 | server-extend | `~/.autogenesis/logs/server-extend-*.log` | ResumeAvailabilityPushService, hasRunningGame fallback, CloudSaveProxy calls |
| 9080 | main (server) | `~/.autogenesis/logs/autogenesis-*.log` | Auto-restore on connect, GameRestoreRpcHandlers, TurnHarness state, audio.syncState, agent work stream |
| 8080 | webpack dev server | `~/.autogenesis/logs/webpack-*.log` | HMR / build errors only — NOT useful for game-state investigation |
| (browser) | Playwright probe | `~/.autogenesis/logs/browser-*.log` | Client-side errors, RPC handler registration order, signal handling |

When the user reports "Resume fails" or "world not restored," start by checking `autogenesis-*.log` (where the consumed-sentinel and restore-failed errors live), then `browser-*.log` (for the client's `restored=true/false` log), then `server-extend-*.log` (to confirm whether the resumeAvailable push even fired).

```bash
# Check all relevant ports
ss -tlnp 2>/dev/null | grep -E "7070|9080|9092"

# To start Autogenesis servers (both required for full game):
cd /path/to/Autogenesis
./gradlew :server-extend:run --no-daemon   # ports 7070 + 9092
./gradlew :server:run --no-daemon          # port 9080 (separate terminal)
```

**Common false-positive: "login account data not loading"**
- Browser's `CommanderDataSync` calls `https://prod.gamingservices.accelbyte.io/rpc` (AccelByte production REST endpoint) — this is NOT `server-extend` on 7070
- `Fail to fetch` on that production URL = network/CORS issue in the browser environment, not a server being down
- `server-extend` (port 7070) handles matchmaking, cloud save proxy, and commander creation pipeline — the account hydration path goes through production

Then search:
```bash
# Sort by recency first
ls -lt ~/.autogenesis/logs/*.log | head -20
# Then grep across all matching files
grep -n "PATTERN" ~/.autogenesis/logs/*.log 2>/dev/null | head -N
```

**Step 3: Parse JSON payload sections carefully**
Autogenesis logs embed serialized JSON payloads in `HISTORY DEBUG` lines — these can be 50KB+ per line. Grep truncates them. Instead:
- Use `grep -o` with a regex to extract the specific field you need
- Or pipe to `python3 -c "import sys,json; ..."` for structured parsing
- Be aware: multi-line `turnStory` content is `\n`-escaped inside the JSON string

**Step 4: Trace directory confirmation**
Many bugs require TPipe traces, not just logs. Always verify:
```bash
ls -la ~/.tpipe/debug/trace/                        # list turn folders by recency
ls -la ~/.tpipe/debug/trace/Round_N_Turn_X_Name/   # check agent dirs present
```
Trace directories are **cleaned/rotated** — old runs may have no files.

**Step 5: Classify findings per bug**
For each bug, classify:
- **CONFIRMED**: Direct evidence in logs/traces (quote specific lines + timestamps)
- **PARTIAL**: Indirect evidence, or behavior correct per documented rules but rules may be wrong
- **UNCONFIRMED**: No evidence found in available logs/session
- **UI-ONLY**: Bug is client-side (KVision UI) and not visible in server logs

**Output format:**
```
### BUG N: [Short Title]
- **Severity**: HIGH/MEDIUM/LOW
- **Evidence**: [specific log lines, timestamps]
- **Root cause (if visible)**: [code location or mechanism]
```

### Pitfalls in Autogenesis Bug Investigation

These are recurring anti-patterns that have produced real regressions. Surface them when you see the trigger conditions.

- **Session-lifetime flag misused as an in-flight signal.** `WorldManager.isGameActive` is set `true` at game start (`TurnHarness.kt:864`, `GameInit.kt:235`) and only flipped to `false` on game-over paths. It is NOT a "a turn is currently executing" flag. Any predicate that combines `|| WorldManager.isGameActive` with the intent "wait for the busy thing to finish" will short-circuit forever. This bit BUG 14 (shutdown timer 15s path unreachable). Quick scan: `grep -rn "isGameActive\s*||\||| \s*isGameActive" server/src/main/kotlin`. Full write-up: `references/autogenesis-bug-investigation.md` § "Session-Lifetime vs In-Flight Signal Anti-Pattern".
- **`loopJob.isActive` is not a per-turn in-flight signal either.** The obvious follow-up fix is to swap `isGameActive` for `TurnHarness.isRunning()` (which is `loopJob?.isActive == true`). That is ALSO wrong: the `loopJob` coroutine is alive from `runNextTurn()` launch until game-over, including the entire range where it is suspended on `deferred.await()` waiting for player input inside `awaitPlayerAction`. Suspending a coroutine does NOT flip `Job.isActive` to false — only completion or cancellation does. So `isRunning()` has the same lifetime as `isGameActive` for any in-progress game. The "in-flight signal" must track per-turn execution (e.g. an `isExecuting` flag in `gameplayOrchestrator.kt`), not the per-loop coroutine. When the per-turn signal does not exist and inventing it requires threading a flag through the orchestrator call chain, the right answer is usually to **drop the defer logic** rather than ship a flawed predicate (BUG 14 fix, 2026-06-22).
- **A test that only toggles one Boolean at a time will miss the broken composition.** BUG 14's old test only checked `isGameActive = true/false` directly, never the realistic "game started, harness idle, last human just left" case. When reviewing shutdown / defer / cleanup logic, demand a test that exercises the realistic steady-state, not just each flag in isolation. The replacement regression coverage is `server/src/test/kotlin/org/ttt/autogenesis/server/ServerShutdownCountdownTest.kt` — which exercises the new `startSinglePlayerShutdownCountdown` helper directly with a mock connection manager and a no-op `onExpire` (the `delayMs` and `onExpire` test seams let the test verify "fires within delayMs" without calling `exitProcess(0)` in the test JVM).
- **"Save then defer" wrappers can hide a dead branch.** A common fix shape is "snapshot the state, then defer the destructive action until the busy thing finishes." If the defer predicate is broken (see above), the snapshot saves correctly but the destructive action never fires, and the test suite still passes. Always verify the destructive path actually executes under the realistic conditions, not just the snapshot path. The fix to BUG 14 broke this wrapper: keep the snapshot save, drop the defer, run the destructive path unconditionally.
- **The same RPC can race against its own server-side recovery.** BUG 15 surfaced the inverse shape: server-side auto-restore on WS connect (`Server.kt:295`) and the Resume click from `ResumeOrNewDialog` (`MainMenu.kt:127`) both legitimately want to load the same snapshot. When auto-restore wins, the consumed-sentinel armsthe VFS for the resume RPC, which then fails because the sentinel intentionally fails `GameSnapshot` deserialization. The recovery pattern is **idempotent success on observable post-conditions**: if `WorldManager.isWorldEmpty() == false` AND `playerStats.any { it.accelByteUserId == userId }`, the world is already in the resumed state — return `true` and push `sendInitialSync` without trying to re-fetch. The recovery MUST gate on both predicates (non-empty world AND a playerStats match); gating on just `isWorldEmpty()` would silently swallow genuine "stale save" failures. The 4-test suite in `GameRestoreRpcHandlersRaceTest.kt` covers all four combinations of `worldEmpty × savedSnapshotExists`.
- **TDD for race conditions: collapse the race into a deterministic sequence.** You don't need real concurrency in the test. The setup is: (1) save a real snapshot, (2) call the racing side's underlying helper *directly and synchronously* (here: `TurnHarness.restoreWorldFromUserRecord(userId)`, which is what `Server.kt:298` runs on the IO dispatcher), (3) call the handler that would race against it (`GameRestoreRpcHandlers.restoreRunningGame(ctx)`). This collapses the race window to "the racing side finished before the handler was called," which is the realistic worst case. If the handler is buggy, the test fails on the first run; if it recovers correctly, the test passes without any timing-sensitive coroutine primitives. Add the 3 negative-control tests in the same file (empty world, fresh DS, sentinel-only with empty world) so the recovery cannot over-reach — they pin the boundaries of the idempotent path.
- **Verify a proposed predicate fix against the same realistic steady-state before applying it.** During the BUG 14 fix, the first proposal was "use `TurnHarness.isRunning()` alone instead of `isRunning() || isGameActive`." That would have been a no-op fix because both operands have the same lifetime. The mistake was caught by reading the `loopJob` lifecycle at `TurnHarness.kt:857-901` BEFORE applying the patch. When proposing a fix to a broken predicate, trace each operand to its writer and verify the proposed fix actually changes the predicate's value in the realistic scenario — not just in the test case the original bug report describes.
- **Wire format mismatches need an explicit normalization step.** When the server's wire format and the client's lookup format don't match (e.g. basename `"Initial Conditions wet 1"` vs full path `"audio/music/Initial Conditions wet 1.mp3"`), a resolver that only matches the canonical form will silently 404 every other form (BUG 16, 2026-06-25). It is not safe to assume either side will be coerced. If the field is documented as "fuzzy-matched," the resolver must actually fuzzy-match — including case-insensitive, basename-without-extension, dotted-vs-underscore namespace, and parent-prefix fallbacks. Quick scan: `grep -rn "no audio file matches resourceName\|no fuzzy match" kvisionApp/src`.
- **Two `@RpcMethod(name=X, direction=Y)` registrations for the same X is a footgun.** When two handler classes register the same RPC method name, one is silently shadowed (BUG 17, 2026-06-25, NOT FIXED — `AudioClientHandlers.handleSyncState` shadows `UiSignalClientHandlers.handleAudioSyncState` for `audio.syncState`). Symptom: defensive code (e.g. flush waits for `pendingAudioSyncState`) "always times out" because the work is actually being done elsewhere. Diagnosis: `grep -rn '@RpcMethod.*name="' sharedModel kvisionApp server | sort | awk -F'name=' '{print $2}' | awk -F',' '{print $1}' | sort | uniq -c | sort -rn | head -20` — any method with count > 1 has a shadow.
- **WS handlers that gate on an auth identity must define both a default and a failure mode.** Defaulting `accelbyteId` to a random `kvision-ws-client-N` (BUG 18, 2026-06-25) makes the server think the random client IS the authenticated user, silently breaking playerStats routing during the WS-bridging window. The right shape: when `accelbyteId` is missing/blank, fall back to `playerId` (session-stable placeholder) AND mark the connection as `guestMode=true` so subsequent lookups know to skip identity resolution. Quick scan: `grep -rn "call.parameters\[.accelbyteId.\] *?:" server/src/main/kotlin`.
- **Identity fields captured into a snapshot must be re-bound to the current session on restore.** Any field that identifies the live WS connection — most importantly `PlayerStats.playerID`, but also connection-scoped session handles, sockets, and observer-registration tokens — gets serialized into the snapshot as the OLD session's value. After restore on a fresh DS the new session has a DIFFERENT value for that field. Downstream code that uses the field as a join key (e.g. `PlayerConnectionManager.hasAnyPrimarySession()` filtering by `session.playerId in playerStats[*].playerID`) silently returns the wrong answer (BUG 19, 2026-06-26). Two correct shapes: (1) **remap on apply** — `applyGameSnapshot` accepts a `currentConnectionId` and rewrites the matching playerStats entry's playerID so the live session resolves itself; (2) **never use the snapshot value as a join key** — look up by `accelByteUserId` (which IS stable across sessions) instead of `playerID`. Shape (1) is correct when the snapshot's stale value IS used as a join key elsewhere and you don't want to audit every call site; shape (2) is correct when you can audit every call site. NPC entries (blank `accelByteUserId`) MUST be left alone by the remap — they have no human identity to bind to. Quick scan: `grep -rn "playerID == \|playerID in" server/src/main/kotlin/org/ttt/autogenesis/server/PlayerConnectionManager.kt server/src/main/kotlin/gameState/WorldManager.kt`.
- **`applyGameSnapshot` is a state-RESTORE funnel, not a state-INITIALIZE funnel — and that distinction is exactly where post-restore UX bugs hide.** (BUG 22/23/24 family, CONFIRMED 2026-06-26 22:12, FIXED 2026-06-26 in same session, plan at `.hermes/plans/reload-post-restore-state-2026-06-26.md`, probe at `kvisionApp-e2e/probes/music-timer-restore.mjs`.) The restore path copies durable world fields from the snapshot (history, playerStats, turnOrderIndex, mapPackName) and remaps identity fields (playerID, isConnected — BUG 19 fix). It does NOT re-run any of the per-turn setup that fires inside `executeSingleTurn` / `awaitPlayerAction`. Symptoms when the restore path skips that setup: (a) **music silent until first action** — `AudioManager.playingObjects` is empty on a fresh JVM, `GameSnapshot` doesn't capture the current MusicDecision, and `MusicSelector.selectForTurn` is only called from `TurnHarness.selectAndBroadcastMusicForTurn` (`TurnHarness.kt:662`) which only runs when `executeSingleTurn` runs. (b) **"Your turn" but AI moves** — `PlayerStats.isControlledByNpc=true` round-trips through the snapshot (the saved game may have captured the human mid-AI-takeover or the original GameInit just set it that way), and the existing remap loop only writes `playerID` and `isConnected`, never `isControlledByNpc`. The live session is then routed through `handleAiTakeover` instead of `executePlayerTurn`. (c) **turn timer never starts** — `WorldManager.startTurnTimer` is only called from `awaitPlayerAction` (`TurnHarness.kt:610`), and that path only fires from inside `executeSingleTurn`. A rehydrated world with no `executeSingleTurn` in flight has no timer. **Rule for any future post-restore addition:** if the runtime state is normally established by a per-turn setup call (music selection, timer arm, focus/scroll, modal, audio channel volume push, etc.), the restore path MUST re-establish it. Two acceptable shapes: (1) **call the same per-turn helper** the per-turn code uses (e.g. `TurnHarness.selectAndBroadcastMusicForTurn` is the same call shape for restore as for turn start — gate on the snapshot's frozen turn state, not the live state); (2) **introduce a single `TurnHarness.rehydratePostRestoreState(snapshot, currentConnectionId)` funnel** that lists every transient setup step in one place and runs them after `applyGameSnapshot` returns — easier to audit, harder to forget a step. Shape (2) is preferable because it makes the "what gets restored" checklist explicit instead of hidden inside `restoreWorldFromUserRecord`. **Diagnostic signature in `autogenesis-*.log`:** user reports "X is broken after reload" → grep the latest log for `TurnHarness: Rehydrated running-game snapshot` followed by an ABSENCE of the expected post-restore setup log line (`Music schedule broadcast`, `TurnHarness: Starting turn timer`, `Server: Human player ... joined, triggering initial sync`, `TurnHarness.applyGameSnapshot: flipped isControlledByNpc`, etc.). If the user sees a "Your turn" or "ACTIVE TURN" UI element but the corresponding server-side setup log is missing, the symptom is BUG 22/23/24 family. Quick scan: `grep -n "applyGameSnapshot\|Music schedule broadcast\|Starting turn timer\|isControlledByNpc" server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt | head -30` — every "setup" log inside `executeSingleTurn` and `awaitPlayerAction` should have a sibling inside `restoreWorldFromUserRecord`.
- **Session-lifetime flags make bad persistence gates.** (BUG 25, 2026-06-27, FIXED same session.) The symmetric inverse of BUG 22/23/24: the **save** side of the snapshot lifecycle, not the **restore** side, was firing on a never-played bridge disconnect. `Server.kt:558` had `WorldManager.isGameActive=true` as one of two operands in its save-on-disconnect predicate. `isGameActive` flips true the moment `GameInit` finishes — long before the human's WebSocket connects. The server-extend bridge (`server-extend-client`, role=CONTROLLER) calls `setGameMode` and disconnects 1-2s later. With `isGameActive=true` and no PRIMARY WS, the predicate fired, persisting a `round=1, turnIndex=0, historyEntries=0` snapshot — overwriting any prior real save. The user's resume then loaded the phantom empty game. **Symmetry with BUG 14 and BUG 22/23/24:** all three are "session-lifetime flag misinterpreted as a 'should I do X right now?' gate". BUG 14 was the defer/timer case (`isGameActive || isRunning` for the shutdown timer). BUG 22/23/24 was the restore case (per-turn setup that didn't re-fire). BUG 25 is the save case (a gate that fired before the human ever joined). **Fix shape:** add a "did the human take at least one action?" flag (`WorldManager.humanPlayerHasJoinedOnce`) set inside the canonical "player is reachable" point (`TurnHarness.awaitPlayerAction`), and gate the persistence on that. The flag is "ever set, not unset" — a one-shot signal that mirrors the human's first interaction with the game. **Cross-cutting rule for any future persistence gate:** if the predicate doesn't require "X happened at least once" (a player action, a score change, a history entry), it's probably wrong. **Audit signature:** cross-log grep the user's saves for `(round=1, turnIndex=0, historyEntries=0)` patterns — if EVERY save is that shape, the user has never successfully played, and the gate is firing on every bridge disconnect. Quick scan: `grep -rn "WorldManager.isGameActive && " server/src/main/kotlin | grep -i "persist\|save\|serialize"` — any predicate that uses `isGameActive` as a persistence gate is suspect.

- **Side effects inside per-request handlers for long-lived connections fire on every reconnect.** (BUG 26, 2026-07-01, NOT FIXED.) `triggerSseResumePush(accelbyteId)` lives inside the per-request Ktor `get("/events")` handler at `Autogenesis/server-extend/.../ServerExtend.kt:347-350`. SSE is a long-lived stream — but the browser's `RestRpcClient` auto-reconnects whenever the underlying TCP idles or drops, and each reconnect runs the entire `/events` handler again. Result: the `client.resumeAvailable` push fires every 45-60 seconds (in the active 2026-07-01 session, three pushes in 3 minutes, all carrying the same `savedAt`). Combined with `ResumeAvailabilityListener.mountResumeDialog` not checking whether a dialog is already mounted, every reconnect creates a fresh `ResumeOrNewDialog` and `mainRoot.add()`s it. The user sees the dialog stack on top of itself mid-gameplay. **Two independent fixes are both needed** — server-extend dedup by `savedAt`+cooldown, and client idempotent mount. Either alone masks the visible symptom but leaves the other wart in place. **Cross-cutting rule for any long-lived-connection surface** (SSE, WebSocket, polling): a per-request handler that runs setup/teardown/side-effect logic on the connection establishment will run that logic again on every reconnect, which is almost never the intent. The dedup signal should be derived from the underlying state (here: the snapshot's `savedAt` is invariant under reconnects) — a wall-clock cooldown is the second-best option. **Companion to the listener-side pitfall:** even if the server is fully idempotent, a UI listener that doesn't guard against already-mounted state will stack widgets on every push. Always verify both ends when the symptom is "UI element appears N times for one event." Quick scan: any `get("/events")`, `app.get("/sse")`, `WebSocket("...")` handler body that calls a notification/registration/RPC emit function — and any UI listener that calls `parent.add(widget)` on push receipt.

### Known Bug Indicators in Autogenesis Logs

These patterns reliably signal specific bug categories:

| Pattern | What It Indicates |
|---------|-------------------|
| `Failed to extract JSON in legality rectifier pipe transformation` | JSON parsing failure during validation — causes truncated payloads |
| `"thinkingUpdates":[]` in serialized payload | Thinking capture failed for that turn |
| `turnResult: "(Planning...)"` + `turnStory: ""` | JSON truncated mid-stream — partial data only |
| `showThinking=false` in `[THINKING_CAPTURE]` logs | Pipe configured to skip capture — expected for some agents, not a bug |
| `[WARN] [SYSTEM]: [THINKING_CAPTURE] Reasoning response is default - skipping broadcast` | extractJson returned isDefault=true — JSON parsing found no valid reasoning block |
| `nemesis=0` across all player assets | Nemesis/elder god spawn logic not triggering — fixed already or trigger conditions not met |
| `targetIntent:""` + `targetEntities:[]` in completed turns | Intent/targeting extraction failed |
| `[WARN] [SYSTEM]: [THINKING_CAPTURE] Reasoning response is default` | Reasoning parsing failed — may indicate downstream cascade failure |
| `RestRpcClient.send: Failed to send to ...prod.gamingservices.accelbyte.io/rpc - Fail to fetch` | Browser cannot reach AccelByte production backend — network unreachable or `server-extend` not running locally |
| `server-extend bridge connection failed: Fail to fetch` | Browser's `CommanderDataSync` RPC to local `server-extend` failed — **check if `server-extend` is running on port 9080** |
| `Local server detection failed: NetworkError when attempting to fetch resource` | Browser's HTTP health check to local server failed (WebSocket may still connect fine — detection uses a separate HTTP call, not WS) |
| WebSocket connects to `ws://127.0.0.1:9080` **successfully** but HTTP health check fails | Normal dev pattern — WebSocket works but browser HTTP/CORS blocked; `server-extend` IS running, client falls back to production endpoint |
| `StandaloneCoroutine was cancelled` in browser logs | Normal WebSocket cycling during login or network hiccup — NOT a crash. Check if followed by `Starting WebSocket connection` to confirm clean reconnect |
| Browser log ends abruptly without `WebSocket connection closed` | Browser tab was killed/crashed — NOT a server crash. Correlate with server's `Player session deregistered` |
| `Player session deregistered` + `No PRIMARY sessions remain` | Normal server shutdown sequence after last client disconnects. Server exited gracefully, not crashed. |
| `[WARN] [SYSTEM]: Server: No PRIMARY sessions but a turn is in progress. Deferring shutdown timer until the turn loop exits.` | **Shutdown regression** (BUG 14, **FIXED 2026-06-22**): defer predicate was `WorldManager.isGameActive` (session-lifetime flag) ORed with `TurnHarness.isRunning()` (loop-level `Job.isActive` — also has session lifetime, since suspending on `deferred.await()` does not flip `isActive` to false). Both operands stay `true` for the entire game lifetime, so the 15-second countdown path was unreachable; the defer block ran every disconnect and waited up to 10 minutes. **Fix:** dropped the defer logic entirely; the new `startSinglePlayerShutdownCountdown(connectionManager, existingJob, delayMs, onExpire): Job` helper in `Server.kt` fires the timer unconditionally. If you see this log line on a current session, the server is running pre-fix code. Confirmed in `autogenesis-2026-06-22-162707.log:3571`. |
| `[INFO] [DATABASE]: TurnHarness: Persisted running-game snapshot for user=...` followed by repeated `[WARN] [NETWORK]: UiSignalRpcHandlers: Cannot send agent work stream` | Snapshot saved, but shutdown never fires (same root cause as BUG 14). Server keeps broadcasting into a dead session every ~500ms. The "Persisted" log only fires inside the onSuccess branch of `Result.fold` in `serializeCurrentWorldSnapshotToUserRecord`, so seeing it confirms the AccelByte Cloud Save PUT succeeded. Absence of a `➡/✅ CloudVFS.saveUserRecord*` line before it is **expected** — `saveUserRecordFromJsonString` in `CloudVirtualFileSystem.kt:61-109` does NOT use `logOperation` (only `saveUserRecord`/`fetchUserRecord` do). Verify the save by the outer `Persisted` log + the VFS-routing evidence in startup logs (`VirtualFileSystemManager initialized in CLOUD mode`). |
| `[INFO] [SYSTEM]: GameRestoreRpcHandlers.restoreRunningGame (race-recovered): user=...` | Auto-restore-on-connect won the race against the ResumeOrNewDialog click (BUG 15, fixed 2026-06-22). The user clicked Resume after the consumed-sentinel was already in place; the server detected the world was already restored and treated the RPC as idempotent success. If you see this on a current session, the user has the resumed game and the dialog closed cleanly — NOT a failure. Pair with `[INFO] [SYSTEM]: Server: Rehydrated running-game for user=...` earlier in the same session to confirm auto-restore ran. |
| `❌ CloudVFS.deleteUserRecord [userId=... key=running-game]: ... errorCode 20013 ... access forbidden: insufficient permissions` followed by `[INFO] [DATABASE]: TurnHarness.invalidateRunningGameRecord: wrote consumed-sentinel` | The AccelByte admin scope can't delete the user's player record (CLOUDSAVE:RECORD action 8 missing). `invalidateRunningGameRecord` falls back to writing a `{"consumed":true,"consumedAt":"..."}` sentinel in place of the real snapshot. This is the **mechanism that arms the BUG 15 race**: the next `restoreWorldFromUserRecord` call returns `Result.failure` because the sentinel intentionally fails `GameSnapshot` deserialization. If you see this pairing, the auto-restore path on connect is producing a state the explicit-resume RPC cannot recover from without the idempotent recovery in `GameRestoreRpcHandlers.restoreRunningGame`. **Re-test impact (2026-06-24, surrender-disconnect fix):** the sentinel persists across server restarts. If you drive a surrender test and then try to drive a second surrender test in the same AccelByte user account, the auto-restore-on-connect path will fail with `TurnHarness.restoreWorldFromUserRecord: running-game record deserialized to null`, and the user's browser shows the `ResumeOrNewDialog`. If the user clicks Resume: the server logs `[WARN] GameRestoreRpcHandlers.restoreRunningGame: restore failed for user=X: running-game record deserialized to null` then returns `false`, and the client shows `MatchmakingClient.requestResume: restored=false` followed by the "No saved game found on the server." messageBox (`MainMenu.kt:480`). The race-recovery branch at `GameRestoreRpcHandlers.kt:177` SHOULD fire for this case (the world IS non-empty and `playerStats.any { accelByteUserId == userId }` is true), BUT it short-circuits on `WorldManager.isWorldEmpty()` which returns `true` for any restored game at round 1 with no history. To re-test surrender cleanly, use a fresh browser session per test, OR clear the consumed-sentinel record via the AccelByte admin SDK before re-testing. Do NOT rely on the same `kvision-ws-client-*` connection ID between tests — it is regenerated per session but the accelbyteId persists. |
| `[WARN] [SYSTEM]: TurnHarness.restoreWorldFromUserRecord: failed to fetch for user=kvision-ws-client-NNNNN: AccelByte API error: 400 - ... userId : kvision-ws-client-NNNNN is not valid uuid v4 without hyphen format` | **Pre-OAuth WS connect with raw playerId as accelbyteId** (transient, expected during login). The browser's `WebSocketRpcBridge.connect` runs BEFORE AccelByte OAuth completes (so MainMenu can mount immediately). The first WS connection has `accelbyteId=null` (or = playerId fallback). The server-side `call.parameters["accelbyteId"]` is blank, so the auto-restore lookup tries to use the playerId as the userId, which AccelByte rejects with `errorCode 20002` because `kvision-ws-client-N` is not a UUID v4. The next WS connection (~1-2s later) carries the real OAuth UUID and the auto-restore succeeds. The 400 error in this gap is NORMAL — do not flag it. Pair with the next connection's `accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4` to confirm the post-OAuth retry. |
| `[INFO] [DATABASE]: TurnHarness: Rehydrated running-game snapshot for user=...` followed by `[WARN] [NETWORK]: Server: Connection kvision-ws-client-X did not match any registered player stats (registeredPlayers=[])` (no `[INFO] Server: Human player ... joined, triggering initial sync` between them) — followed later by `ResumeOrNewDialog mounted` and user clicks Resume → `MatchmakingClient.requestResume: restored=false` | **BUG 20: Auto-restore completes after WS session is registered — initial sync never sent** (CONFIRMED 2026-06-26, NOT FIXED). The auto-restore at `Server.kt:408` runs in `CoroutineScope(Dispatchers.IO).launch` (fire-and-forget). The synchronous `onConnected` block then reads `findPlayerStatsByConnectionId(session.playerId)` at `Server.kt:443` — which returns `null` because the restore hasn't completed. The WS session is registered as PRIMARY but never receives `sendInitialSync`. The auto-restore eventually finishes (~600ms later) and writes the consumed-sentinel, but the user is stuck on a blank MainMenu because no GameplayUI was mounted automatically. Then server-extend pushes `client.resumeAvailable` (the snapshot was real when it was read), the browser mounts `ResumeOrNewDialog`, the user clicks Resume, the server reads the sentinel, and the race-recovery check at `GameRestoreRpcHandlers.kt:177` returns `false` for round-1 games (BUG 21, same family). The user sees "No saved game found on the server." even though the world IS restored. **Diagnostic signature:** in `autogenesis-*.log`, look for the sequence `TurnHarness.applyGameSnapshot: remapped playerID ...` AND a `did not match any registered player stats (registeredPlayers=[])` line EARLIER (at WS connect, before the auto-restore completes) — with no `Human player ... joined, triggering initial sync` between them. **Fixes (any one):** (a) Chain `sendInitialSync` to fire AFTER the auto-restore IO-launch completes (collapse the two paths into one coroutine — cleanest); (b) have `onConnected` `delay(N ms)` and re-check `findPlayerStatsByConnectionId`; (c) introduce a transient `WorldManager.lastRehydratedAccelByteUserId: String?` set inside `applyGameSnapshot` and have `findPlayerStatsByConnectionId` fall through to it during a short window after auto-restore. **Companion to BUG 19 (playerID remap fix); both must land together** because (a) without BUG 19 the live session's playerId never matches the restored playerStats. |
| `[WARN] [SYSTEM]: GameRestoreRpcHandlers.restoreRunningGame: restore failed for user=X: running-game record deserialized to null` followed by `RPC Sending Response: method=server.restoreRunningGame ... restored=false`, AND the auto-restore earlier in the same session showed `Rehydrated running-game snapshot ... round=1, turnIndex=0, historyEntries=0` (with no intervening WS reconnect) | **BUG 21: Race-recovery short-circuits on round-1 games** (CONFIRMED 2026-06-26, NOT FIXED). `GameRestoreRpcHandlers.isWorldAlreadyRestoredForUser` (`GameRestoreRpcHandlers.kt:283-289`) checks `WorldManager.isWorldEmpty() == false` BEFORE the `playerStats.any { accelByteUserId == userId }` check. `WorldManager.isWorldEmpty()` returns `roundNumber <= 1 && history.isEmpty()` — i.e. the default state of a fresh world. ANY restored game that starts at round 1 with no committed history looks identical to "no restore happened" and the recovery returns `false`. Combined with BUG 20 (the auto-restore happens but the live session never received the sync), the user lands on the ResumeOrNewDialog, clicks Resume, and gets `restored=false` even though the world IS in the resumed state on the server. **Diagnostic:** confirm with `grep "Rehydrated running-game snapshot"` earlier in the same `autogenesis-*.log` — if a rehydrate for the same userId appears within ~5s of the failed restore, BUG 21 fired. **Fix:** replace the `isWorldEmpty()` predicate with one that specifically detects "world was just auto-restored for this user" — e.g. add `lastAutoRestoredAccelByteUserId: String?` to `WorldManager`, set it inside `applyGameSnapshot`, and have `isWorldAlreadyRestoredForUser` check `(lastAutoRestoredAccelByteUserId == userId)`. The semantic is "did the auto-restore on connect win the race" — not "is the world non-empty." **Companion to BUG 20; both must land together** because BUG 20's symptom (no initial sync) drives the user to click Resume, which triggers BUG 21's broken recovery. |
| `[WARN] >>> [CLIENT] FLUSH: No pending audio sync state after 10000ms wait — audio will resync on next turn` | **Audio.syncState handler shadowed** (BUG 17, NOT FIXED). Two `@RpcMethod(name = "audio.syncState", direction = CLIENT)` handlers are registered — `AudioClientHandlers.handleSyncState` (active path) and `UiSignalClientHandlers.handleAudioSyncState` (consumes `pendingAudioSyncState`). Only one fires. If you see this warning repeat on every resume, the audio IS being applied (by the active handler); the warning is from a stale defensive wait in the flush coroutine. Fix would be to delete the shadow handler and the dead wait. **Diagnostic:** when this warning fires, check for `AudioClientHandlers.handleSyncState: ENTER` in the same log — if both fire, only the active one matters; if only the warning fires (no handleSyncState), audio is genuinely broken. |
| `[INFO] WebSocket /events connection attempt for playerId=kvision-ws-client-NNNNN (accelbyteId=kvision-ws-client-NNNNN, guestMode=false, ...)` followed by `[WARN] Server: Could not resolve player identity for connection kvision-ws-client-NNNNN (accelbyteId=kvision-ws-client-NNNNN)` | **Server falls back to random playerId for missing accelbyteId** (BUG 18, FIXED 2026-06-25). The WS handler reads `call.parameters["accelbyteId"] ?: playerId`; with no accelbyteId query param, `playerId` defaults to `"kvision-ws-client-N"` (random int), and `accelbyteId == playerId` (also random). The server treats this as a real identity match attempt — `guestMode=false` because the fallback `accelbyteId` doesn't start with `"guest"` — and fails to resolve any playerStats. Breaks playerStats-based routing during the WS-bridging window (typically 1-2s before the post-auth rebind fires). Fix: treat the missing case as `guestMode=true` and fall back to `playerId` only as a session-stable placeholder, not as an identity match. |
| `[WARN] [SYSTEM]: Server: No PRIMARY sessions remain ... Starting 60-second shutdown timer.` immediately followed by `[ERROR] [SYSTEM]: Server: Shutdown timer expired. Terminating server to prevent runaway tokens.` | Working dev-mode configuration (post-BUG-14 fix, raised default 15s → 60s on 2026-06-25). The 60-second timer gives the player 1 minute to switch tabs and log back in. Dev mode sets this to 600000 (10 minutes) via `start_servers.sh`. If you see `Starting 15-second shutdown timer` instead, the JVM is running a pre-fix build (default still 15s); set `AUTOGENESIS_SHUTDOWN_DELAY_MS` explicitly or rebuild with `start_servers.sh`. |
| `[INFO] [SYSTEM]: Server: Rehydrated running-game for user=X from account record; round=N, stats.size=K` immediately followed by `[WARN] [SYSTEM]: Server: No PRIMARY sessions remain ... Starting 60-second shutdown timer.` despite an active WS connection in the same log | **Shutdown timer fires despite active user — playerID remap missing** (BUG 19, FIXED 2026-06-26). The auto-restore path on connect restores `WorldManager.playerStats = snapshot.playerStats.toMutableList()` verbatim. The snapshot's `playerStats[*].playerID` is the OLD session's WS playerId (a random `kvision-ws-client-N` from when the snapshot was saved). The new WS session has a DIFFERENT playerId. `PlayerConnectionManager.hasAnyPrimarySession()` filters `session.playerId in playerStats[*].playerID` and returns `false` because the snapshot's stale playerID never matches the live session's playerId. Server arms the 60-second shutdown timer despite the user being actively connected and kills the server under their feet. Fix: `TurnHarness.applyGameSnapshot` now takes `currentConnectionId` and remaps `playerStats[accelByteUserId == userId].playerID` to the live WS playerId (forces `isConnected=true` too — the snapshot may capture the user mid-disconnect with `isConnected=false`). Both call sites pass the live id: `Server.kt` auto-restore path passes `session.playerId`; `GameRestoreRpcHandlers.restoreRunningGame` passes `ctx.connectionId`. Post-fix log line: `TurnHarness.applyGameSnapshot: remapped playerID for accelByteUserId='X' from previous=[kvision-ws-client-OLD] to 'kvision-ws-client-NEW' on 1 entry(ies)`. NPC entries (blank `accelByteUserId`) are left UNCHANGED. Without the fix, the symptom is "the player comes back, world looks restored, music plays, but server dies 60 seconds later without explanation." To diagnose: search for the auto-restore log line followed within ~60s by `Shutdown timer expired` while a WS connection from the same user is still in the `Player kvision-ws-client-X registered as PRIMARY` set. |
| `Player kvision-ws-client-X registered as PRIMARY` followed by `Server: Connection kvision-ws-client-X did not match any registered player stats (registeredPlayers=[Lord Maple Tree, Shitty Bob, ...])` where the registered names are the playerStats names from a just-restored snapshot | The snapshot's `playerStats[*].playerID` was set to OLD session playerId; the LIVE session's playerId is the WS connection id (e.g. `kvision-ws-client-X`). The world WAS restored (you can see `Rehydrated running-game` earlier in the log), but the live session can't find itself in playerStats because the IDs don't match. This is the BUG 19 same-conditions failure path: the session is registered as PRIMARY but `findPlayerStatsByConnectionId` returns null. The shutdown timer fires 60s later (see above row). The fix remaps playerStats[*].playerID on snapshot apply so the live session finds itself. |
| `[INFO] [DATABASE]: TurnHarness: Rehydrated running-game snapshot for user=...` followed (in the same log) by `[INFO] [SYSTEM]: AudioManager: singleton initialized with 2 default channels (Music, Sfx) ... AudioManager.buildSyncState: globalVolume=1.0 channels=2 scheduledObjects=0` — and `MusicSelector.selectForTurn: ENTER ... currentlyPlayingMusicIds.size=0` does NOT appear until AFTER the user's first action submission | **BUG 22: Music silent on restore** (CONFIRMED 2026-06-26 22:12, FIXED same session, plan `.hermes/plans/reload-post-restore-state-2026-06-26.md`). The `AudioManager.playingObjects` map is empty on a freshly-started JVM, `GameSnapshot` does not capture the current MusicDecision, and `MusicSelector.selectForTurn` is only called from `TurnHarness.selectAndBroadcastMusicForTurn` (`TurnHarness.kt:662`) which only runs inside `executeSingleTurn`. The user sees a silent world until they submit an action — at which point the per-turn music selector fires and the music starts. **Diagnostic:** the gap between `Rehydrated running-game snapshot` and the first `MusicSelector.selectForTurn: rule 1 fired → bucket=initialConditions` log line tells you whether music is missing on restore. If the gap is > 0 and there's no intervening action submission, music is missing. **Fix shape:** call `TurnHarness.selectAndBroadcastMusicForTurn` (or a thin rehydrate wrapper) immediately after `applyGameSnapshot` returns, with the snapshot's frozen round/actor state and `isFirstTurn=(round==1)` semantics. The user (round 1) gets the `initialConditions` bucket — same as a fresh game. |
| `[INFO] [DATABASE]: TurnHarness: Rehydrated running-game snapshot for user=...` followed by `[DEBUG] [NETWORK]: Server: Identified connection ... as player 'X' (isNpc=true)` (note: `isNpc=true` for the user's own player name) | **BUG 23: Human treated as AI on restore** (CONFIRMED 2026-06-26 22:12, FIXED same session). `PlayerStats.isControlledByNpc` round-trips through the snapshot — when the user reloaded, the snapshot had them marked `isNpc=true` (the GameInit path sets it that way for the human entry on first game start, or any AI takeover mid-game keeps it true). The `applyGameSnapshot` remap loop at `TurnHarness.kt:1996-2005` writes `playerID` and `isConnected` but NOT `isControlledByNpc`. Live session is routed through `handleAiTakeover` (`TurnHarness.kt:1029`) instead of `executePlayerTurn`. The user's first action lands in `submitPlayerPlay` → buffers → "AI is formulating a strategy..." message visible to the user, or `WorldManager.isReachable` returns `false` and the system spawns an AI agent immediately. **Diagnostic:** `Identified connection ... (isNpc=true)` for the user's own playerStats entry right after a rehydrate is the smoking gun. **Fix shape:** inside the remap loop, also write `entry.isControlledByNpc = false` for the human's remap target (the entry matched by `accelByteUserId == remapConnectionIdForUser`). NPC entries (blank `accelByteUserId`) untouched. Log line: extend the existing "remapped playerID" line to also include the `isControlledByNpc` flip. |
| `[INFO] [DATABASE]: TurnHarness: Rehydrated running-game snapshot for user=...` followed (within ~2s) by `[INFO] [SYSTEM]: UiSignalRpcHandlers: broadcasting ResolutionStep: START, Message: 'It is X's turn'` (or any `activeTurn` broadcast naming the human) — and the user reports no countdown / no `[data-test-turn-timer]` element on the UI | **BUG 24: Turn timer not armed on restore** (CONFIRMED 2026-06-26 22:12, FIXED same session). `WorldManager.startTurnTimer` is called from `TurnHarness.awaitPlayerAction` (`TurnHarness.kt:610`), which only fires from inside `executeSingleTurn`. The rehydrate path returns without invoking any per-turn setup. The UI mounts with "Your turn" visible (the activeTurn broadcast fired from the same `executeSingleTurn`) but the countdown never starts. **Diagnostic:** look for `Rehydrated running-game snapshot` followed by `activeTurn` broadcast naming the human, but NO `TurnHarness: Starting turn timer` log line. The pattern is unmistakable — the user is told it's their turn but the timer is never armed. **Fix shape:** inside `restoreWorldFromUserRecord`, after `applyGameSnapshot` completes, check `WorldManager.world.turnOrder[turnOrderIndex]` — if it matches the human (accelByteUserId == current human), call `WorldManager.startTurnTimer(humanPlayerName, TURN_DURATION_SECONDS)`. If the NPC was up when the game shut down, no timer arms — that matches the saved state. The timer arm is idempotent with the `awaitPlayerAction` arm later; both go through the same `WorldManager.startTurnTimer` / `stopTurnTimer` API. |
| `Server: Skipped save-on-disconnect ... humanPlayerHasJoinedOnce=false` | **BUG 25: Disconnect-time save gate** (CONFIRMED + FIXED 2026-06-27). Log line introduced by the fix at `Server.kt:558`. Fires when the bridge disconnects with no human WS yet joined — prevents persisting a never-played fresh-init snapshot. **Healthy:** the line does NOT appear for human-joined games. **Regressed:** the line DOES appear for a human-joined game (gate too restrictive). To diagnose a "user can never play past round 1" report, cross-log grep the user's `Persisted running-game snapshot` lines for `(round=1, turnIndex=0, historyEntries=0)` patterns — if every line is that shape, BUG 25 (or a regression of it) is firing on every bridge disconnect. See `references/autogenesis-bug-investigation.md` § "BUG 25" for the fix and the audit checklist. |
| `TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true for 'X'` | **BUG 25 fix signal** (introduced 2026-06-27). Fires inside `awaitPlayerAction` when the human is reachable. If this line never fires for a session, the human never reached a playable turn — and any subsequent save would have been correctly skipped by the new gate. To verify the gate is functioning end-to-end, pair this line with the `Persisted running-game snapshot` line in the same log file: both must appear for human-joined games, only the skip line for never-joined bridge disconnects. |
| `ResumeOrNewDialog mounted for userId=X` appearing 2+ times in the same browser-*.log (with identical `savedAt` in server-extend `pushed resumeAvailable for user=X` lines) | **BUG 26: ResumeOrNewDialog re-mounts on every SSE reconnect** (CONFIRMED + FIXED 2026-07-01, plan .hermes/plans/fix-resume-dialog-reappearing.md). The `client.resumeAvailable` push fires from inside the per-request `get("/events")` handler (`ServerExtend.kt:347-350`), so it re-fires on every SSE reconnect (~45-60s). `ResumeAvailabilityListener.mountResumeDialog` lacks idempotency — it does not check whether a dialog is already mounted before `mainRoot.add(dialog)`. Each reconnect stacks a fresh `ResumeOrNewDialog` widget (zIndex 9100, full-viewport backdrop) on top of the previous. The visible symptom is the resume dialog reappearing every ~45-60s mid-gameplay. **Diagnostic:** `grep -c "ResumeOrNewDialog mounted" browser-*.log` should return `1` per user session; anything `>= 2` is BUG 26. Cross-check: `grep -oE "pushed resumeAvailable for user=[a-z0-9]+" server-extend-*.log | sort | uniq -c` should also return `1` per user per log file. **Fix:** (A) dedup the push in `ResumeAvailabilityPushService.checkAndPushBlocking` by `savedAt` (invariant under reconnects) plus a wall-clock cooldown, AND (B) add a `currentDialog: ResumeOrNewDialog?` module-level reference to `ResumeAvailabilityListener` and gate `mountResumeDialog` on `currentDialog?.parent == null` plus a MainMenu-stack check. **Companion to the auto-restore race family (BUG 19-24)** — same architectural lesson (listener handlers must be idempotent against repeated triggers) applied to the push side instead of the WS-handler side. |

## Error Handling

| Problem | Resolution |
|---------|------------|
| No logging files found | Search more — try different file patterns, check home directory |
| Parse error | The log format may have changed — inspect raw lines |
| Empty results | Broaden filters, check different log files |
| Permission denied | Report path and suggest chmod or checking file ownership |
- **Very long log lines (>50KB) truncate grep output** | Use Python script with streaming parse, or `grep -o` to extract specific field |
| **Regex `contains` check false-positives on KDoc/historical-context comments** | When the implementation references a removed helper by name in KDoc for historical context (e.g. `// the previous X helper that did Y`), a structural test that scans for the bare token `X` in the source WILL false-positive. Always match the function-call shape (`fun X\s*\(` or `X\s*\(`) rather than the bare token. Captured after the 2026-06-27 Autogenesis session where a test for "helper X is removed" failed because the file's KDoc comment referenced X by name. Fix was a 1-line regex change (`X` → `fun X\s*\(`), and the comment was kept for historical context. |
| Trace directories missing | Trace dirs are rotated/cleaned — check `ls -lt ~/.tpipe/debug/trace/` for available rounds |

## Technical Notes

- **Always generate a Python script** — never try to parse large logs in memory
- **Script location**: `/tmp/log_parser_<unique_id>.py`
- **Run scripts with output redirection** to avoid terminal flooding:
  ```bash
  python3 /tmp/log_parser_xxx.py > /tmp/log_results.txt
  ```
- **For very large logs (>50MB)**: Use `search_files` with `output_mode="content"` and `limit` to sample, or split into chunks with multiple script invocations

## Agent Trace Files (JSON/HTML) — Companion to Log Entries

When logs contain `"Saved agent traces (JSON/HTML) to {path}/{baseFileName}.*"`, the actual `.json` and `.html` trace files are saved to `~/.tpipe/debug/trace/{turnFolder}/{agentType}/{connectionId}/`.

**Path pattern from log to actual files:**
```
Log entry: .../Round_N_Turn_X_PlayerName/PromptClassification/kvision-ws-client-123456789/_1777760961878.*
Actual:    ~/.tpipe/debug/trace/Round_N_Turn_X_PlayerName/PromptClassification/kvision-ws-client-123456789/_1777760961878.json
Actual:    ~/.tpipe/debug/trace/Round_N_Turn_X_PlayerName/PromptClassification/kvision-ws-client-123456789/_1777760961878.html
```

**Always check `~/.tpipe/debug/trace/` directly** — trace directories are cleaned/rotated and old files may not exist. Use `ls -la ~/.tpipe/debug/trace/` to enumerate available turn folders before assuming trace files are present.

**Critical: Trace files may not exist.**
- If validation fails BEFORE `saveAgentTrace()` is called in the code, no trace files are written — the log entry references files that were never saved
- Trace directories are cleaned up/rotated — old runs may have no files remaining
- Always check `~/.tpipe/debug/trace/` directly when investigation depends on trace content

**Known agent types that produce traces:** `PromptClassification`, `Judge`, `ChatAgent`, `AnswerAgent`, `OpenAgent`, `ValidationSplitter`, `TurnResolutionSplitter`, `AnalysisSplitter`, `MaintenanceSplitter`, `NeoWritingAgent`, `TargetDetectors`, `LorebookUpdate`

## Known Log Locations

| Project | Log Location | Notes |
|---------|-------------|-------|
| Autogenesis | `~/.autogenesis/logs/` (server logs: `autogenesis-*.log`, `server-extend-*.log`, `webpack-*.log`; browser logs: `browser-*.log` — browser POSTs console to `http://localhost:9080/api/browser-log` in DEBUG mode, server keeps 10 most recent; browser also writes to localStorage) |
| TPipe (traces) | `~/.tpipe/debug/trace/` |
| System services | `/var/log/` |
| Application logs | `./logs/` or `./data/logs/` |

## VALIDATOR_TRUTH Pipe Start Interpretation

The `VALIDATOR_TRUTH` category logs pipe lifecycle events from `hookValidatorPipeStart`. Understanding the naming pattern is critical for diagnosing thrash vs. normal execution:

```
[VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe'
[VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe->validator pipe'
```

### Pipe Name Syntax

- `'legality checker pipe->validator pipe'` — nested validator inside a parent pipe (`->` indicates validator sub-pipe)
- `'style reapply pipe->validator pipe'` — same nesting pattern
- Single-level: `'legality checker pipe'` — top-level pipe without nested validator

### Thrash vs. Branch Pipe Execution

**Duplicate "Pipe Started" with same name does NOT always mean thrash.** When `buildBranchPipeFromTemplate(..., copyFunctions=true)` creates a branch pipe (validator.kt:479), the new pipe inherits the template's `pipeName`. This creates log entries that look like restarts but are actually branch pipe execution:

```
23:49:07.105  [VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe->validator pipe'  <- Nested validator runs
23:49:08.075  AgentWorkStreamStreaming: Pipeline 'railroad' completed                     <- Main pipeline done
23:49:09.467  [VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe'                      <- Branch pipe (same name inherited)
23:49:09.467  BranchFailure: buildBranchPipeFromTemplate.setPreInitFunction entry          <- Confirms branch pipe
```

**Key indicators of branch pipe execution (not thrash):**
- Line shows `BranchFailure: buildBranchPipeFromTemplate.setPreInitFunction entry` immediately after
- Timing is ~1 second after a pipeline completes (too fast for timeout/retry which is 3+ minutes)
- Branch pipe configured with `copyFunctions=true` at validator.kt:479 as "Fallback agent in the event of a refusal"

**Key indicators of actual thrash/restart:**
- `PIPE_RETRY` or `Attempt` entries in logs
- Timing consistent with 3-minute timeout (restart every ~3 min)
- `repeatPipe` signal entries

### Timeout vs. Branch Pipe Timing

| Pattern | Timing | Cause |
|---------|--------|-------|
| Branch pipe re-execution | ~1-5 seconds after completion | `copyFunctions=true` + `setBranchPipe` |
| Timeout retry | ~3 minutes (configured timeout) | `enablePipeTimeout` with `autoRetry=true` |

## Related Skills

- `systematic-debugging` — for root-cause analysis methodology
- `hindsight-recall` — to check if similar issues were seen before
- `tpipe-trace-parser` — for parsing actual trace JSON/HTML files once found
- `log-writer` — the **inverse** of this skill. When the user asks to *add* logging, instrument a function, or expand log coverage, load `log-writer` instead — it discovers the project's Logger API and inserts log calls using the existing system. Use this skill (`log-parser`) when the user wants to *read* what's already been logged; use `log-writer` when the user wants to *write* new logs.
- `log-parser` (this skill) — for understanding pipe lifecycle patterns in VALIDATOR_TRUTH logs