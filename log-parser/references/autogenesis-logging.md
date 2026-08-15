# Autogenesis Logging & Trace Reference

## Log Format

```
TIMESTAMP [LEVEL] [CATEGORY]: message
Example: 2026-05-16T02:58:25.256691858Z [DEBUG] [SYSTEM]: UserActionClassification: validateClassificationResult entry
```

- Timestamp: ISO-8601 with nanosecond precision (`Z` suffix = UTC)
- Level: `DEBUG`, `INFO`, `WARN`, `ERROR`
- Category: `SYSTEM`, `NETWORK`, `GENERAL`, `DATABASE`, `AUTH`, `UI`, `LLM`

## Log Files

| Source | Location | Pattern |
|--------|----------|---------|
| Autogenesis server | `~/.autogenesis/logs/` | `autogenesis-YYYY-MM-DD-HHmmss.log` |
| Controller | `~/.autogenesis/logs/` | `controller_YYYYMMDD_HHmmss.log` |
| Server-extend | `~/.autogenesis/logs/` | `server-extend-YYYY-MM-DD-HHmmss.log` |
| Webpack | `~/.autogenesis/logs/` | `webpack-YYYY-MM-DD-HHmmss.log` |
| Browser logs | `~/.autogenesis/logs/` | `browser-YYYY-MM-DD-HHmmss.log` |
| Test | `~/.autogenesis/logs/` | `test-YYYY-MM-DD-HHmmss.log` |

## Agent Trace Files

Traces saved by `PromptManager.saveAgentTrace()` (PromptManager.kt:109-137) and similar functions:

```
~/.tpipe/debug/trace/{turnFolder}/{agentType}/{connectionId}/{baseFileName}.json
~/.tpipe/debug/trace/{turnFolder}/{agentType}/{connectionId}/{baseFileName}.html
```

Example from logs:
```
.../Round_1_Turn_0_Lord_Maple_Tree/PromptClassification/kvision-ws-client-869291157/_1777760961878.*
```

**Important:** The wildcard `*` in log messages means BOTH `.json` and `.html` exist, but NOT that they are guaranteed to exist. See "Trace File Lifecycle" below.

## Trace File Lifecycle

Traces are saved at specific code points. If the code path fails before reaching the save call, the log entry references files that were never written.

### PromptManager.kt saveAgentTrace() flow:
```kotlin
// Line 99 — only reached if no exception thrown earlier
saveAgentTrace("PromptClassification", connectionId, pipe)
return extractJson<UserActionClassification>(result.text)  // line 100
```

**If validation fails at line 100 (extractJson returns null):** No error — method returns null gracefully.
**If validation fails BEFORE line 99 (exception thrown):** `saveAgentTrace()` is never called, but earlier logs may show `"Saved agent traces..."` if it was called in a prior successful run.

### Common failure: validateClassificationResult

When `UserActionClassificationAgent.validateClassificationResult()` throws (line 83-104), the exception propagates up and `saveAgentTrace()` at PromptManager.kt:99 is never reached. Log shows:

```
UserActionClassification: validateClassificationResult entry
UserActionClassification: validateClassificationResult failed: result is null
UserActionClassification: validateClassificationResult exception: Validator Pipe Failed: Unable to extract valid UserActionClassification JSON from response
```

No trace files saved for this run.

## Known Categories

From `LogCategory.kt`:
- `AUTH` — Authentication and authorization
- `NETWORK` — Network operations (RPC bridges, WebSocket, gRPC, HTTP)
- `DATABASE` — Database operations (CloudSave, commander sync, data persistence)
- `UI` — UI interactions and rendering
- `SYSTEM` — System-level operations (initialization, configuration)
- `LLM` — LLM/AI operations (prompts, responses)
- `GENERAL` — General purpose logging

## VALIDATOR_TRUTH Pipe Truth Logging

The gameplayOrchestrator hooks all validator pipes with `[VALIDATOR_TRUTH]` logging at `gameplayOrchestrator.kt:401-412`. This tracks the full validator pipe lifecycle:

```
[VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe'
[VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe->validator pipe'
[VALIDATOR_TRUTH] Pipe Completed: 'legality checker pipe'
```

### Pipe Name Suffixes

| Suffix | Meaning |
|--------|---------|
| `->validator pipe` | Nested validator sub-pipe inside a parent pipe |
| No suffix | Top-level pipe without nested validator |

### Validator Sequence (Full 6-Pipe Chain)

When railroad detects railroading or a refusal occurs, the validator runs this full sequence:
1. `legality checker pipe` (primary or branch pipe)
2. `legality checker pipe->validator pipe` (nested validator)
3. `legality rectifier pipe`
4. `legality rectifier pipe->validator pipe`
5. `style reapply pipe`
6. `style reapply pipe->validator pipe`

### Branch Pipe Fallback (Not Thrash)

The `legalityCheckerPipe.setBranchPipe(buildBranchPipeFromTemplate(..., copyFunctions=true))` at `validator.kt:479` configures a PalmyraX5 fallback. When triggered, it produces logs that look like restarts:

```
23:49:08.075  AgentWorkStreamStreaming: Pipeline 'railroad' completed  <- Railroad detects railroading
23:49:09.467  [VALIDATOR_TRUTH] Pipe Started: 'legality checker pipe'   <- Branch pipe starts (PalmyraX5)
23:49:09.467  BranchFailure: buildBranchPipeFromTemplate.setPreInitFunction entry  <- Branch construction log
23:49:22.324  [VALIDATOR_TRUTH] Pipe Completed: 'legality checker pipe'  <- Branch completes
```

**Why the same name?** `copyFunctions=true` causes the branch pipe to inherit `pipeName` from the template. The preInitFunction hook also gets copied, triggering the same `[VALIDATOR_TRUTH]` log.

**Timing distinguishes crash from design:**
- Branch pipe fallback: ~1.4 seconds after railroad completes
- Timeout retry: 3+ minutes (configured `enablePipeTimeout(..., duration = 180000)`)

No `PIPE_RETRY` or `attempt` logs means timeout system is NOT triggering — it's the branch pipe mechanism.

### Branch Pipe Trigger Conditions

Branch pipe at `validator.kt:479-490` is configured as "Fallback agent in the event of a refusal" but also runs when:
- Railroad detects railroading (the branch pipe runs as additional validation pass with different model)
- The main pipe refuses to generate content

## VFS / CloudSave Log Patterns

The VFS layer (server/src/main/kotlin/org/ttt/autogenesis/server/vfs/) wraps AccelByte Cloud Save and a local-dev fallback. Log lines let you reconstruct the per-user routing and the save/fetch lifecycle.

### Routing at startup

Look for this line near server boot to determine which backend is active for a given session:

```
[INFO] [DATABASE]: VirtualFileSystemManager initialized in CLOUD mode (AccelByte Cloud Save (namespace=echoofmaridia-autogenesis))
```

`CLOUD` mode → real AccelByte Cloud Save; `LOCAL` mode → local file system. This applies globally, but per-user routing still happens (see next section).

### Per-user routing — `forUser(userId)` at VirtualFileSystem.kt:150-160

```
guest...      → LocalVFS (always, regardless of global mode)
rest-client...→ LocalVFS (always, regardless of global mode)
anything else → current() (CLOUD if global mode is CLOUD)
```

So a real AccelByte UUID routes to CloudVFS even in local dev mode. Use this to know which VFS a given log line came from: the userId prefix tells you the path, the global mode line tells you what `current()` returns for everyone else.

### Fetch lifecycle (logs via `logOperation`)

`fetchUserRecord` is wrapped in `logOperation` (CloudVirtualFileSystem.kt:131-140) and emits two lines per call:

```
[DEBUG] [DATABASE]: ➡ CloudVFS.fetchUserRecord [userId=004c... key=running-game]
[INFO]  [DATABASE]: ✅ CloudVFS.fetchUserRecord [userId=004c... key=running-game] result=PlayerRecordResponse(...)
```

The `result=` line includes `createdAt` and `updatedAt`. A `❌` variant fires on error with the AccelByte errorCode. A `record not found` WARN fires for a clean miss (first-time visit) — this is **not an error**, it is the expected normal-case response when a player has no saved game yet.

### Save lifecycle — TWO different code paths, only ONE logs

The VFS exposes two save methods, with **different logging behavior**. This is non-obvious and has tripped up log analysis:

| Method | Lines | Emits `➡/✅` log via `logOperation`? | Where called from |
|---|---|---|---|
| `saveUserRecord(userId, key, payload: JsonElement)` | CloudVirtualFileSystem.kt:111-129 | **Yes** | Most direct callers |
| `saveUserRecordFromJsonString(userId, key, jsonPayload: String)` | CloudVirtualFileSystem.kt:61-109 | **No** — bare `runCatching` over a raw `HttpClient.send` PUT | `TurnHarness.serializeCurrentWorldSnapshotToUserRecord` (disconnect path) |

`saveUserRecordFromJsonString` does NOT emit a `➡/✅ CloudVFS.saveUserRecordFromJsonString` line. To verify a successful save via that path, look for the **outer** confirmation log:

```
[INFO] [DATABASE]: TurnHarness: Persisted running-game snapshot for user=<id> (round=N, turnIndex=M, historyEntries=K)
```

This log fires only inside the `onSuccess` branch of `Result.fold` in `serializeCurrentWorldSnapshotToUserRecord` (TurnHarness.kt). Seeing it confirms:
1. The HTTP PUT to AccelByte succeeded (`response.statusCode() in 200..299`).
2. The save routed to CloudVFS (proved by an earlier `✅ CloudVFS.fetchUserRecord` line for the same userId, or by the boot-time `CLOUD mode` initialization).

The opposite — a failed save — emits `TurnHarness: Failed to persist running-game snapshot for user=<id>: <message>` instead, with no Persisted log.

### Delete lifecycle and the consumed-sentinel fallback

`deleteUserRecord` (CloudVirtualFileSystem.kt:153-162) wraps `AdminUserRecord.deleteRecord`. When the server lacks the `CLOUDSAVE:RECORD` delete permission, AccelByte returns errorCode `20013` ("access forbidden: insufficient permissions"). The `invalidateRunningGameRecord` helper in `TurnHarness` catches this and falls back to writing a `{"consumed":true,"consumedAt":"<iso8601>"}` sentinel payload. Log evidence of the fallback:

```
[ERROR] [DATABASE]: ❌ CloudVFS.deleteUserRecord [userId=<id> key=running-game]: { "errorCode": 20013, ... }
[INFO]  [DATABASE]: TurnHarness.invalidateRunningGameRecord: wrote consumed-sentinel for user=<id> (delete failed with: HttpResponseException: ...)
```

The sentinel is designed to fail `GameSnapshot` deserialization so `GameRestoreRpcHandlers.hasRunningGame` treats it as "no saved game." A subsequent fetch of the slot will return the sentinel and a `hasRunningGame: exists=false (round=null)` line.

## Useful Grep Patterns

```bash
# Validator pipe lifecycle
grep "VALIDATOR_TRUTH.*Pipe (Started|Completed)" ~/.autogenesis/logs/*.log

# Branch pipe triggers
grep "BranchFailure: buildBranchPipeFromTemplate" ~/.autogenesis/logs/*.log

# Pipeline completion events
grep "AgentWorkStreamStreaming: Pipeline '.*' completed" ~/.autogenesis/logs/*.log

# Railroading detection
grep "Railroading detected\|Act of God points" ~/.autogenesis/logs/*.log

# All trace saves for a specific agent type
grep "Saved agent traces.*PromptClassification" ~/.autogenesis/logs/*.log

# Validation failures
grep "validateClassificationResult" ~/.autogenesis/logs/*.log

# Turn trace directories (may not exist)
grep "Turn trace directory not found" ~/.autogenesis/logs/*.log

# Get last N log files
ls -t ~/.autogenesis/logs/*.log | head -5

# VFS routing / save / fetch / delete for a specific user
grep "VirtualFileSystemManager initialized\|CloudVFS\.\|LocalVFS\." ~/.autogenesis/logs/*.log | grep -i "userId=<id>\|initialized"

# Running-game snapshot lifecycle (BUG 14 verification recipe)
grep "Persisted running-game snapshot\|Failed to persist running-game\|invalidateRunningGameRecord" ~/.autogenesis/logs/*.log
```