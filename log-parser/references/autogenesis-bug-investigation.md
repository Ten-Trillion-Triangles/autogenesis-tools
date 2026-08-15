# Autogenesis Bug Investigation Reference

Compiled from log scans across multiple sessions. Last updated 2026-06-27 (BUG 25 fixed; cross-cutting lesson "session-lifetime flags make bad persistence gates" added).

## Confirmed Bugs with Log Evidence

### BUG 1: JSON Failures During Judgement (HIGH)
- 3x `Failed to extract JSON in legality rectifier pipe transformation` at 02:32:47, 02:52:25 (May 22), 14:15:08 (May 18)
- Also evidenced by `turnResult: "(Planning...)"` + `turnStory: ""` in multiple payloads (truncated JSON mid-stream)
- Root cause: `LegalityRectifierPipe` transformation stage — extractJson returns default/isDefault=true

### BUG 2: Thinking Vanishes After Turn (HIGH)
- `2026-05-22T03:08:44.636612657Z [WARN] [SYSTEM]: [THINKING_CAPTURE] Reasoning response is default - skipping broadcast`
- Multiple `"thinkingUpdates":[]` in completed turn payloads (lines 974, 2201, 3535, 9172, 10935)
- Two failure modes:
  1. `showThinking=false` on author pipes (lines 828-882) — capture skipped entirely
  2. `extractJson result - isDefault=true` — valid JSON not found in response

### BUG 3: NPC Thinking Not Fully Captured (MEDIUM)
- NPC `showThinking=true` correctly set (line 2009: `attempting to extract thinking for actor=Robert`)
- Thinking extracted successfully (lines 1992-1994: length 2463) but `thinkingUpdates:[]` in final broadcast
- Root cause: extraction happens but result not passed into `thinkingUpdates` array in serialized payload

### BUG 4: Writing UI Stuck on Prior Output (MEDIUM — client-side)
- Server correctly sends broadcast (`Broadcasting thinking update` confirmed at lines 1993, 2011)
- Client doesn't re-render — confirmed client-side issue, not server
- Cannot verify from server logs alone

### BUG 5: Server Shutdown Timer (REGRESSED 2026-06-22 → FIXED 2026-06-22)
- Originally worked: `[WARN] [SYSTEM]: Server: No PRIMARY sessions remain... Starting 15-second shutdown timer.` fired correctly on disconnect.
- Regression introduced 2026-06-22: uncommitted changes replaced the 6-line unconditional `delay(15_000L); exitProcess(0)` with a defer block. The defer predicate was wrong — see BUG 14.
- Fix shipped 2026-06-22 (same day): defer block deleted, `startSinglePlayerShutdownCountdown` extracted, `ServerShutdownCountdownTest` added (4 cases), `TurnHarnessShutdownTest` removed. See BUG 14 for the full write-up.

### BUG 6: Counterplay Self-Target + Cascade (HIGH)
- No guard in logs preventing: (a) player targeting themselves, (b) cascade flag set on self-target
- `counterResponses` present in payloads (line 6460: `Lord Maple Tree: ... retaliates`)
- Self-target case not captured in this session but mechanism confirmed missing

### BUG 7: Eligible NPCs Empty Handling (MEDIUM — indirect)
- `nemesis=0` consistently across all players (lines 799, 2040, 4431, 6601, 10772)
- `handlePostTurn` calls nemesis logic (lines 1917, 3675, 5433, 6493, 9022, 10086) but spawn logic not triggering
- Downstream symptom: elder god AI returns generic response (Bug 8)

### BUG 8: Elder God AI Generic Response (HIGH)
- `Round_2_Turn_1_Ghor'lax_the_Hollow/TargetDetectors/` — agent produces generic "hostile military" without Deep Ring identity
- `Waffle Archivist` (Round 3) — generic bureaucratic archetype, not properly instantiated character
- Eligible NPC pool returning generic archetypes instead of character-specific NPCs

### BUG 9: Too Many Nemesis/Elder God Spawned (LOW — not in this session)
- All entries show `nemesis=0` — either fixed before this session or trigger conditions not met

## Partially Evidenced

### BUG 10: Judge Bad Military Call (MEDIUM — partial)
- Lord Maple Tree's invasion of Hydroponic Gardens: `territoryGained:[]` despite success
- Judge applied `-40 military threat debuff` — correct per documented rules (unopposed invasion still needs additional resolution)
- Tension: bug report says "invasion not opposed = automatic capture" — not what code does
- Either rules not implemented correctly, or invasion wasn't sufficiently "unopposed" per code interpretation

## UI-Only (Cannot Verify from Server Logs)

### BUG 11: Character Icons Jumble to Blue Person
- Icon rendering is purely KVision client-side
- No server logs contain sprite/icon data
- **Cannot confirm from server logs**

### BUG 12: Nemesis/Elder God Alert Screen Didn't Appear
- Alert UI is purely client-side
- No alert-screen logging in server
- **Cannot confirm from server logs**

## Design Concern (Not Hard Bug)

### BUG 13: NPC Strange Incoherent Plays
- `Waffle Archivist` "playing god" and controlling Robert's fate (Round 3)
- NPCs dictating outcomes rather than responding organically
- Some may be emergent narrative, some may be coherence issue
- Logs show creative but non-linear behavior

## Confirmed Regression (2026-06-22) — FIXED 2026-06-22

### BUG 14: Server Shutdown Timer — 15s Path Unreachable (FIXED)
- **Symptom:** After the last human disconnects in single-player mode, server does NOT shut down in 15 seconds. Stays alive up to 10 minutes (or until the 10-minute safety cap) spamming `UiSignalRpcHandlers: Cannot send agent work stream` every ~500ms.
- **Location:** `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:423`
- **Buggy predicate:** `val turnInProgress = TurnHarness.isRunning() || gameState.WorldManager.isGameActive`
- **Root cause:** `WorldManager.isGameActive` is a **session-lifetime** flag, not a "turn pipeline currently executing" signal. It is set to `true` at `TurnHarness.kt:864` (after `awaitAllPlayersJoined()`) and `GameInit.kt:235`, and only ever flipped to `false` on game-over paths (`TurnHarness.kt:215, 2106, 2144`). Once any turn has ever run, `isGameActive` stays `true` for the rest of the server's lifetime, even when the harness is idle waiting for human input. So `turnInProgress` is permanently `true`, the 15-second branch (`Server.kt:455-471`) is unreachable, and the defer block (`Server.kt:424-454`) always runs instead.
- **Correct predicate:** `TurnHarness.isRunning()` alone (which checks `loopJob?.isActive == true` at `TurnHarness.kt:436`). That is the actual "a turn pipeline is mid-flight" signal the defer block was meant to protect.
- **Actual fix (2026-06-22):** drop the defer logic entirely. There is no flag in the codebase that distinguishes "LLM orchestrator is currently executing a turn" from "turn loop is alive but idle waiting for player input" — `gameplayOrchestrator.kt` has no `isExecuting` field. The defer was over-engineering on top of a broken predicate. The snapshot save (the real new feature) is kept; the 15-second timer is restored to the pre-regression unconditional form.
- **New function (testable):** `startSinglePlayerShutdownCountdown(connectionManager, existingJob, delayMs, onExpire): Job` added to `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt`. `delayMs` and `onExpire` are test seams (production: `delayMs = 15_000L`, `onExpire = { exitProcess(0) }`).
- **Regression coverage:** `server/src/test/kotlin/org/ttt/autogenesis/server/ServerShutdownCountdownTest.kt` (4 tests, all passing) — fires onExpire, skips onExpire on reconnect, cancels existing job, completes within delayMs (not 10-minute cap).
- **Obsolete test removed:** `server/src/test/kotlin/org/ttt/autogenesis/server/TurnHarnessShutdownTest.kt` (asserted the buggy `turnInProgress()` predicate — pinning the wrong invariant in place).
- **The snapshot save is fine** — the new `serializeCurrentWorldSnapshotToUserRecord` call at `Server.kt:403-412` correctly persists the running game to the user's VFS record. The bug was only in the predicate that chose between the 15s and the defer path.
- **Log evidence (session `autogenesis-2026-06-22-162707.log:3571`):**
  ```
  21:21:00.303  [INFO]  [NETWORK]: Player session deregistered: kvision-ws-client-1720812863 (role=PRIMARY)
  21:21:00.304  [WARN]  [SYSTEM]: Server: No PRIMARY sessions but a turn is in progress. Deferring shutdown timer until the turn loop exits.
  21:21:01.722  [INFO]  [DATABASE]: TurnHarness: Persisted running-game snapshot for user=004c3eb0... (round=1, turnIndex=1, historyEntries=2)
  21:21:02+     [WARN]  [NETWORK]: UiSignalRpcHandlers: Cannot send agent work stream, session 'AI_CONNECTION_1' not found  (repeats every ~500ms, no shutdown)
  ```
- **Pre-regression behavior** (HEAD: `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:327-332`): 6-line unconditional `delay(15_000L); exitProcess(0)` after the `!hasAnyPrimary` check. Working as designed.
- **Multiplayer (NOT a regression, BY DESIGN):** the entire disconnect branch is gated by `if (gameState.WorldManager.isSinglePlayer)` (`Server.kt:389`). The comment at `Server.kt:236-239` ("Multiplayer dedicated servers keep running regardless of connection churn") reflects deliberate operator design (upcoming async feature will complicate shutdown semantics). If multi-player shutdown is wanted later, that is a behavior change, not a regression fix.

## Confirmed Regression (2026-06-22) — FIXED 2026-06-22

### BUG 15: Auto-Restore vs ResumeOrNewDialog Race — "Resume Failed" on a Resumed Game (FIXED)
- **Symptom:** After reconnect, the user sees the ResumeOrNewDialog, clicks Resume, and immediately gets "Resume Failed" — even though the game is in fact already resumed and ready to play on the server.
- **Location:** `server/src/main/kotlin/org/ttt/autogenesis/server/GameRestoreRpcHandlers.kt:120` (the `restoreRunningGame` RPC handler).
- **Two actors racing on a single WebSocket connect:**
  1. **Server-side auto-restore** (`Server.kt:295`): `onConnected` fires → launches `TurnHarness.restoreWorldFromUserRecord(humanUserId)` on `Dispatchers.IO`. That call applies the snapshot AND writes the consumed-sentinel (`TurnHarness.kt:1861`) — delete-on-restore TTL.
  2. **Client-side resume check** (`MainMenu.kt:127`): `scope.launch { MatchmakingClient.hasRunningGame() }` on `MainScope`. If it beats the IO invalidate, the dialog is shown because the snapshot is still real in VFS.
- **The losing side:** if (1) wins, the dialog isn't shown — correct. If (2) wins, the dialog is shown and the user clicks Resume. By the time `server.restoreRunningGame` runs, the consumed-sentinel is in place. `restoreWorldFromUserRecord` fetches the sentinel, the sentinel intentionally fails `GameSnapshot` deserialization (it's the design — see `GameRestoreRpcHandlers.kt:51-55`), and the RPC returns `false` → user sees "Resume Failed" with the game actually resumed on the server.
- **Log evidence (session `autogenesis-2026-06-22-181423.log:70-91`):** two `CloudVFS.deleteUserRecord` calls both fail with `errorCode 20013 access forbidden: insufficient permissions`, so `invalidateRunningGameRecord` falls back to writing the consumed-sentinel. This is the mechanism that arms the race — once the sentinel is in place, a subsequent `restoreWorldFromUserRecord` returns `Result.failure` even though the world is fully restored.
- **Fix:** detect the race in `restoreRunningGame` via two cheap `WorldManager` predicates — `isWorldEmpty() == false` AND `playerStats.any { it.accelByteUserId == userId }`. If both hold, the auto-restore already won; treat the RPC call as idempotent success, push `sendInitialSync`, and return `true`. The fetch failure is not surfaced to the UI. If the world is empty AND the VFS holds a sentinel, the recovery does NOT trigger — that is the genuine "stale save" path and the RPC correctly returns `false`.
- **Fix implementation:** extracted shared tail `applyRestoredWorldAndSync(userId, path)` in `GameRestoreRpcHandlers.kt:173` (the helper is `suspend` because `sendInitialSync` is `suspend`). `path` distinguishes the two callers in logs (`fresh-restore` vs `race-recovered`).
- **Regression coverage:** `server/src/test/kotlin/org/ttt/autogenesis/server/GameRestoreRpcHandlersRaceTest.kt` (4 tests):
  1. `restoreRunningGame returns true when auto-restore has already applied the snapshot` — the failing-then-passing TDD test that pinned the fix.
  2. `restoreRunningGame returns false when there is no snapshot and the world is empty` — genuine no-save case (regression guard against over-reaching recovery).
  3. `restoreRunningGame restores from VFS when no auto-restore has run` — fresh-DS happy path (existing behavior unchanged).
  4. `restoreRunningGame returns false when sentinel is in place but world is also empty` — guards the "the world got reset between auto-restore and Resume click" edge case; recovery must NOT swallow a real failure.
- **TDD pattern that surfaced this:** the failing test is deterministic without real concurrency. Setup a real snapshot, run `TurnHarness.restoreWorldFromUserRecord` directly (which is what `Server.kt:298` does — no coroutine orchestration needed), then call `GameRestoreRpcHandlers.restoreRunningGame(ctx)`. The auto-restore coroutine's completion is synchronous in test scope, so the race window collapses to "auto-restore ran before the RPC was called" — which is the realistic worst case the production code can hit. No real concurrency needed in the test.
- **Related:** the snapshot save in the disconnect branch (`Server.kt:406`, `TurnHarness.serializeCurrentWorldSnapshotToUserRecord`) was not touched — it still runs before the shutdown timer fires. BUG 14 fixed the timer firing; BUG 15 fixed the resume side of the same lifecycle.

## Grep Patterns for Bug Investigation

```bash
# JSON failures
grep -n "Failed to extract JSON" ~/.autogenesis/logs/*.log

# Thinking capture failures
grep -n "THINKING_CAPTURE.*default\|thinkingUpdates.*\[\]" ~/.autogenesis/logs/*.log

# Planning placeholder (truncated JSON)
grep -n "turnResult.*Planning\|turnStory.*\"\"\|wasPlayerSuccessful.*false" ~/.autogenesis/logs/*.log | head -30

# Nemesis spawn
grep -n "nemesis=0\|handlePostTurn.*Decay.*handling nemesis" ~/.autogenesis/logs/*.log

# Self-target cascade
grep -n "targetIntent.*Hostile\|counterResponses" ~/.autogenesis/logs/*.log | head -20

# Turn folders
ls -lt ~/.tpipe/debug/trace/ | head -10

# Shutdown defer / running-game snapshot / agent-work-stream loop (BUG 14)
grep -n "Deferring shutdown timer\|Persisted running-game snapshot\|Cannot send agent work stream" ~/.autogenesis/logs/*.log

# Auto-restore vs Resume race (BUG 15): the sentinel-fallback path that arms the race
grep -n "Consumed-sentinel\|invalidateRunningGameRecord.*wrote consumed\|CloudVFS.deleteUserRecord.*20013\|access forbidden: insufficient permissions" ~/.autogenesis/logs/*.log

# Resume RPC outcomes (BUG 15): look for the "race-recovered" log line emitted by the fix
grep -n "race-recovered\|fresh-restore\|treat.*Resume.*idempotent" ~/.autogenesis/logs/*.log
```

## Session-Lifetime vs In-Flight Signal Anti-Pattern

The BUG 14 investigation surfaced a recurring semantic mismatch that is worth flagging as a general debugging pattern, not just a one-off fix:

**When a predicate needs to ask "is X currently busy?", check whether it is using a session-lifetime flag instead of an in-flight signal.**

In Autogenesis:

| Flag | Type | Set true at | Set false at | Use for |
|------|------|-------------|--------------|---------|
| `WorldManager.isGameActive` | session-lifetime | `TurnHarness.kt:864`, `GameInit.kt:235` | game-over paths only (`TurnHarness.kt:215, 2106, 2144`) | "is the game still going?" |
| `TurnHarness.isRunning()` | in-flight | `loopJob?.isActive == true` (`TurnHarness.kt:436`) | when the loop coroutine ends | "is a turn pipeline executing right now?" |
| `WorldManager.worldMutex` | mutex lock | acquired | released | serialization barrier |

**Rule of thumb for this codebase:** "is X busy right now" should consult a Job/coroutine/job-state field, never a top-level `Boolean` whose only writers are state-transition hooks. Any predicate that combines `|| WorldManager.isGameActive` with the intent "wait for the busy thing to finish" is almost certainly wrong — the boolean will short-circuit the wait indefinitely.

**Second-order pitfall (BUG 14, 2026-06-22):** even an in-flight signal can have the wrong *scope*. `TurnHarness.isRunning()` reports whether the **turn loop** is alive, not whether a specific **turn** is being processed. A loop coroutine that suspends on `CompletableDeferred.await()` while waiting for player input is still "running" by `Job.isActive`. So the in-flight signal can be just as unhelpful as the session-lifetime one if its scope is the loop instead of the per-turn unit. Before reaching for `isRunning()` as a fix, verify the coroutine's suspension points are the only "idle" states the predicate needs to ignore — if it also needs to ignore player-wait, the predicate is still wrong.

**Third-order lesson (BUG 14 fix, 2026-06-22):** if no clean "actively executing" signal exists and inventing one requires a non-trivial refactor (adding a flag in `gameplayOrchestrator.kt`, threading it through the call chain, exposing it on `WorldManager`), the right answer is usually to **drop the defer logic**, not to ship a flawed predicate. The defer was over-engineering to protect an in-progress narrative snapshot — the snapshot save itself is async and well within the 15-second window for typical turns.

**Quick scan commands to find similar bugs:**
```bash
# Session-lifetime flag used as in-flight signal
grep -rn "isGameActive\s*||\|||\\s*isGameActive" server/src/main/kotlin

# Loop-level `Job.isActive` used as turn-level predicate
grep -rn "loopJob.*isActive\|isActive\s*=.*loopJob" server/src/main/kotlin
```

**Audit checklist when reviewing shutdown / cleanup / defer logic:**
1. What is the predicate's semantic intent? (in-flight vs. session-lifetime vs. per-turn vs. per-loop)
2. What does each operand actually represent? Trace each one to its writer — is it a one-shot state-transition boolean, a `Job.isActive` check (note the scope), or something else?
3. After the first turn has run, does the predicate collapse to `true` forever?
4. Does the test for that logic only exercise the "game never started" case, or does it cover the "game started, harness idle" case too? (BUG 14's test only checks `isGameActive = true/false` directly, never the realistic "loopJob == null, isGameActive == true" combination that triggers the bug.)
5. If the predicate scope is the loop (`loopJob.isActive`) rather than the per-turn unit, can the coroutine be in a state where it's "alive but suspended" that the predicate needs to ignore? If yes, the predicate is still wrong.

## Trace File Locations

Trace directories by round (recency order):
```
Round_3_Turn_1_Lord_Maple_Tree  (10 agent dirs)
Round_3_Turn_0_Waffle_Archivist  (7 agent dirs)
Round_2_Turn_2_Robert            (10 agent dirs)
Round_2_Turn_1_Ghor'lax_the_Hollow (11 agent dirs)
Round_2_Turn_0_Lord_Maple_Tree   (9 agent dirs)
Round_1_Turn_1_Robert            (10 agent dirs)
Round_1_Turn_0_Lord_Maple_Tree   (10 agent dirs)
```

Known agent types producing traces: `PromptClassification`, `Judge`, `ChatAgent`, `AnswerAgent`, `OpenAgent`, `ValidationSplitter`, `TurnResolutionSplitter`, `AnalysisSplitter`, `MaintenanceSplitter`, `NeoWritingAgent`, `TargetDetectors`, `LorebookUpdate`

## Confirmed (2026-06-25) — Resume-game Audio Sync Failure

### BUG 16: Music doesn't resume after restoreRunningGame (HIGH) — FIXED 2026-06-25
- **Symptom:** After resume, `audio.syncState` arrives at the client and `AudioClientHandlers.handleSyncState` is called, but `AudioEngine.play` logs `preload FAILED for resource='Initial Conditions wet 1' (took 0ms) — bufferCache still empty, no audio will play (loadBuffer returned null; check AudioResourceLoader logs for the underlying reason)`. The user sees a silent game even though the audio system "applied" the snapshot.
- **Location:** `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/audio/AudioResourceLoader.kt:653` (`fun resolvePath(name: String): List<String>?`).
- **Root cause:** The audio manifest uses full file paths with extension as keys (e.g. `audio/music/Initial Conditions wet 1.mp3` → `listOf("audio/music/Initial Conditions wet 1.mp3", ".aac", ".ogg", ".wav")`). The server's audio-tracks catalog stores tracks by their **bare basename** (`"resourceName": "Initial Conditions wet 1"` in `sharedModel/src/commonMain/resources/audio/audio-tracks.json`). When the server emits `AudioObject.resourceName = "Initial Conditions wet 1"` and the client calls `AudioResourceLoader.loadBuffer("Initial Conditions wet 1")`, the `resolvePath` lookup fails all five fallback steps: the name is not a manifest key (1), not a manifest value (2), not underscore-equivalent (3), not a key prefix (4), and not a parent-prefix match (5). The track silently 404s.
- **Fix (2026-06-25):** Added step 2b — strip directory and extension from every manifest value and compare case-insensitively to `name`. Diagnostic log line emitted on hit: `AudioResourceLoader.resolvePath: BASENAME hit for 'Initial Conditions wet 1' → manifest key 'audio/music/Initial Conditions wet 1.mp3'`.
- **Lesson (cross-cutting):** When a server's wire format and a client's lookup format don't match (basename vs full path, dotted namespace vs underscore, etc.), the resolver needs an explicit normalization step — it is not safe to assume either side will be coerced. The KDoc on `AudioObject.resourceName` calls the field "fuzzy-matched" but the resolver only matched the canonical catalog-key shape, not the catalog-name shape the server actually emits.
- **Log evidence (`browser-2026-06-25-232526.log` and later):**
  ```
  [WARN] AudioResourceLoader.loadBuffer: no audio file matches resourceName='Initial Conditions wet 1' (not in manifest, no fuzzy match) — returning null
  [WARN] AudioEngine.preloadBuffer: loadBuffer returned null for 'Initial Conditions wet 1' — draining pending plays for this queue
  [WARN] AudioEngine.play: preload FAILED ... — bufferCache still empty, no audio will play
  ```
- **Verification (post-fix):** `AudioResourceLoader.resolvePath: BASENAME hit for 'Initial Conditions wet 1' → manifest key 'audio/music/Initial Conditions wet 1.mp3'` followed by `AudioResourceLoader.loadBuffer: OK resourceName='Initial Conditions wet 1' loaded from path='audio/music/Initial Conditions wet 1.mp3' (duration=335.592s, channels=2, sampleRate=48000)`. The `resume-preserves-round.mjs` probe passes end-to-end including all 4 assertions (`gameplayResumed`, `roundPreserved`, `leaderboardPreserved`, `turnOrderPresent`).

### BUG 17: Two `@RpcMethod(name="audio.syncState")` handlers registered — one is silently shadowed (MEDIUM, latent) — NOT FIXED
- **Symptom:** During BUG 16 investigation, the audio.syncState frame was observed being handled by `AudioClientHandlers.handleSyncState` (the active path). The other handler `UiSignalClientHandlers.handleAudioSyncState` (which would populate `pendingAudioSyncState` for the flush coroutine to consume) is registered with the same RPC method name but never fires. The flush's "No pending audio sync state after 10000ms wait" warning logs forever, because the audio is actually being applied by the OTHER handler.
- **Location:** `AudioClientHandlers.kt:144` and `UiSignalClientHandlers.kt:749` — both register `@RpcMethod(name = "audio.syncState", direction = RpcDirection.CLIENT)`.
- **Status:** NOT fixed. The 10-second wait in `attachGameplayUI`'s flush is a no-op today (the audio is applied via the other path), but it leaves dead code that future maintainers will assume is load-bearing. Recommendation: pick one. If `AudioClientHandlers` is the canonical sink, delete `UiSignalClientHandlers.handleAudioSyncState` and the `pendingAudioSyncState` field + flush wait entirely.
- **Lesson:** When you find a defensive wait that "always times out," check whether the work is being done elsewhere. Defensive code that never exercises its happy path is a smell — either the code it's protecting is gone, or the work moved.

### BUG 18: Server-side `accelbyteId` falls back to random `kvision-ws-client-N` when query param is absent (HIGH, latent) — FIXED 2026-06-25
- **Symptom:** When the browser opens a WebSocket without an `accelbyteId` query parameter (e.g. the `KEnv.skipLogin` guest flow before the post-auth rebind, or any code path that calls `WebSocketRpcBridge.connect(accelbyteId = null)`), the server's `WebSocket /events` handler reads `call.parameters["accelbyteId"] ?: playerId`. The `playerId` defaults to `"kvision-ws-client-N"` (a random int). The server then logs `Could not resolve player identity for connection kvision-ws-client-1767892177 (accelbyteId=kvision-ws-client-1767892177)` — `accelbyteId == playerId`, both random, neither matches `WorldManager.playerStats[*].accelByteUserId`.
- **Downstream damage:** Breaks playerStats-based routing for `sendInitialSync` and `audio.syncState` during the WS-bridging window. The browser's `Main.kt` rebinds the WS with the real accelbyteId 1-2 seconds later (`MainScope().launch { RestRpcBridge.connect(...); WebSocketRpcBridge.connect(accelbyteId = globals.AccelByteEnv.userId) }` at line 130), but any server-side resolution that runs against the FIRST connection (before the rebind) cannot find the player.
- **Location:** `Server.kt:634-635` — `val playerId = call.parameters["playerId"] ?: UUID.randomUUID().toString()` and `val accelbyteId = call.parameters["accelbyteId"] ?: playerId`.
- **Fix (2026-06-25):** `Server.kt:633-645` — when `accelbyteId` is missing/blank, fall back to `playerId` (preserves identity within a session) AND treat the missing case as `guestMode = true` so the lookup knows not to expect a playerStats match.
- **Lesson:** WS handlers that gate on an auth identity MUST have a clearly-defined default and a clearly-defined failure mode. "Fall back to the playerId and pretend it's the same identity" is wrong — it makes the server think the random WS client IS the authenticated user. The fix is "fall back to playerId AND mark as guest so the lookup knows to skip playerStats matching."
- **Log evidence (pre-fix):**
  ```
  [INFO] WebSocket /events connection attempt for playerId=kvision-ws-client-1767892177 (accelbyteId=kvision-ws-client-1767892177, guestMode=false, role=PRIMARY)
  [WARN] Server: Could not resolve player identity for connection kvision-ws-client-1767892177 (accelbyteId=kvision-ws-client-1767892177)
  ```
  Note `guestMode=false` — the missing accelbyteId was treated as a real identity match attempt, which is the bug.

## Confirmed (2026-07-01) — ResumeOrNewDialog Reappears on Every SSE Reconnect

### BUG 26: `ResumeOrNewDialog` re-mounts every ~45-60s after the user resumes (HIGH, NOT FIXED 2026-07-01)
- **Symptom (user-reported, 2026-07-01 16:13):** *"after resuming the game, the pop-up that asks the player to resume keeps randomly appearing over and over again once the player has rejoined the server."* The dialog appears to be the same "Saved game found" Resume/New/Cancel modal. It reappears mid-gameplay — even after the user has clicked Resume and is playing. The reappearance happens roughly every 45-60 seconds, not on a fixed timer.
- **Two stacked root causes (both must be fixed together):**

  **(A) Push fires on every SSE reconnect, not just the first connect.** `ResumeAvailabilityPushService.checkAndPush` is called from `triggerSseResumePush(accelbyteId)` inside the per-request Ktor `get("/events")` handler at `Autogenesis/server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:347-350`. SSE is a long-lived stream, but when the underlying TCP connection idles/drops, the browser's `RestRpcClient` auto-reconnects — and each reconnect runs the entire `/events` handler again, including the push. There is no per-user push dedup, no `savedAt` check, no cooldown.

  **(B) Client-side mount is not idempotent.** `ResumeAvailabilityListener.mountResumeDialog` (`Autogenesis/kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/ResumeAvailabilityListener.kt:133-174`) checks only whether `KEnv.mainRoot` and the three dialog callbacks (`dialogOnResume`/`dialogOnNewGame`/`dialogOnCancel`) are non-null. It does NOT check whether a `ResumeOrNewDialog` is already mounted. Every push creates a brand-new widget and `mainRoot.add(dialog)`s it. The previous dialog is never removed from the parent (only its own `hide()` removes itself — and `hide()` only fires when a button is clicked).

- **Log evidence (active session, 2026-07-01 20:13-20:16):** three SSE reconnects, three pushes, three dialog mounts — same user, same snapshot (saved at 2026-06-30T21:36:52Z), all ~45-60s apart:
  ```
  server-extend-2026-07-01-161245.log:
   20:14:51.371  ResumeAvailabilityPushService: connecting to ws://127.0.0.1:9080 for resumeAvailable push user=004c3eb02c0b4436b41b24d5d670b0e4
   20:14:51.532  ResumeAvailabilityPushService: pushed resumeAvailable for user=004c3eb02c0b4436b41b24d5d670b0e4 round=2 hasAi=true
   20:15:36.998  ResumeAvailabilityPushService: connecting ... user=004c3eb02c0b4436b41b24d5d670b0e4   ← reconnect #1
   20:15:37.012  ResumeAvailabilityPushService: pushed resumeAvailable ... round=2 hasAi=true
   20:16:38.208  ResumeAvailabilityPushService: connecting ... user=004c3eb02c0b4436b41b24d5d670b0e4   ← reconnect #2
   20:16:38.224  ResumeAvailabilityPushService: pushed resumeAvailable ... round=2 hasAi=true

  browser-2026-07-01-161328.log:
   20:14:51.530  ResumeAvailabilityListener: notification received for userId=004c3eb02c0b4436b41b24d5d670b0e4 round=2
   20:14:51.531  ResumeAvailabilityListener: dialog callbacks not yet set; queuing payload for retry
   20:14:51.985  ResumeAvailabilityListener: ResumeOrNewDialog mounted for userId=004c3eb02c0b4436b41b24d5d670b0e4 round=2
   20:15:03.877  MainMenu: GameplayUI already exists (from identity sync), activating existing instance   ← user clicks Resume, gameplay mounts
   20:15:37.012  ResumeAvailabilityListener: notification received for userId=004c3eb02c0b4436b41b24d5d670b0e4 round=2
   20:15:37.018  ResumeAvailabilityListener: ResumeOrNewDialog mounted ... round=2                         ← NEW DIALOG mid-gameplay
   20:16:38.224  ResumeAvailabilityListener: notification received ... round=2
   20:16:38.229  ResumeAvailabilityListener: ResumeOrNewDialog mounted ... round=2                          ← ANOTHER NEW DIALOG mid-gameplay
  ```
  Note the **`savedAt` is identical** across all three pushes (`2026-06-30T21:36:52.908Z`) — the snapshot hasn't changed; we're pushing the same notification over and over. That is the entire signal needed to dedupe.

- **Why both fixes are needed:**
  - Fix (A) alone: if any future code path legitimately needs to re-push (e.g. user starts a new game and saves it mid-session), the dialog could re-mount once per save, which is still wrong.
  - Fix (B) alone: the user pays the network/IO cost of every redundant push even though the visible symptom is masked.
- **Fix shape (A — server-extend push dedup):** Inside `ResumeAvailabilityPushService.checkAndPushBlocking`, after building the notification but before calling `pushToMainServer`, look up a `ConcurrentHashMap<String, LastPush>` keyed by `userId`. If the cached entry's `savedAt == notification.savedAt` AND `now - lastPushAt < COOLDOWN_MS` (e.g. 5 minutes), skip the push with a DEBUG log. Otherwise update the cache and push. The `savedAt` check is the cleanest dedup signal — it changes only when the user actually saves a new game.
- **Fix shape (B — client-side idempotent mount):** Add a module-level `private var currentDialog: ResumeOrNewDialog? = null` to `ResumeAvailabilityListener`. At the top of `mountResumeDialog`, if `currentDialog?.parent != null` (i.e. it's still in the DOM), return. On dismiss (the three button `onClick` handlers), set `currentDialog = null`. Additionally, gate on "is the user still on MainMenu?" by checking `KEnv.appStack?.activeIndex == MAIN_MENU_INDEX` — if the user is mid-gameplay, do not mount even if `currentDialog == null` (defense-in-depth against a future code path that pushes during gameplay for a different reason).
- **Pre-existing structural-test pitfall:** `server-extend/src/test/kotlin/org/ttt/autogenesis/serverextend/SseResumePushOnConnectTest.kt:69` uses `Regex("""triggerSseResumePush\s*\(""")` — i.e. it asserts the helper IS called from the SSE handler. The fix for (A) must NOT delete the call; it must add dedup *inside* the push path. Otherwise the structural test will fail spuriously.
- **Quick scan commands:**
  ```bash
  # Count mount events per session — any count > 1 in a single user session is BUG 26 firing
  grep -c "ResumeOrNewDialog mounted" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"

  # Count SSE reconnects — the underlying trigger rate
  grep -c "RestRpcClient.connect: Opening SSE channel" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"

  # Same userId appearing in multiple pushes within one log file
  grep -oE "pushed resumeAvailable for user=[a-z0-9]+" ~/.autogenesis/logs/server-extend-*.log \
    | sort | uniq -c | sort -rn | head -10
  ```
  Healthy: `1` push per user per log file (one per session). Bug 26 firing: `>= 2`.
- **Lesson (cross-cutting, extends the "session-lifetime vs in-flight signal" family):** Any code path that **fires a side effect inside a per-request handler for a long-lived connection** (SSE, WebSocket, polling endpoint) without dedup will repeat that side effect on every reconnect. The dedup signal should be derived from the underlying state (here: `savedAt`), not from a clock — `savedAt` is invariant under reconnects, so a same-value check survives the reconnect cycle cleanly. If you don't have a stable invariant signal, a wall-clock cooldown is the second-best option (accept that during a long-running session you may fire one extra push per cooldown window).
- **Companion bug-hunting principle (the "listener lacks idempotency" anti-pattern):** When a listener/mount handler in the UI layer is triggered by a server push, check whether the handler has a guard against already-mounted state. The `ResumeAvailabilityListener` example here would also have failed with one push per session if there had been any retry logic that re-fired the push — the `pendingPayload` retry path at `ResumeAvailabilityListener.kt:178-200` is similarly unchecked. Quick scan: `grep -rn "mainRoot.add\|parent.add\|this.add" kvisionApp/src/jsMain/kotlin | grep -i "dialog\|modal\|overlay"`. For each, verify the handler either (a) checks for an existing instance first, or (b) is called from a path where the previous instance is guaranteed to have been torn down.

## Confirmed (2026-06-26) — Resume-game Race + Round-1 Recovery Gap

### BUG 19: Auto-restore race + round-1 race-recovery short-circuit (HIGH, FIXED 2026-06-26)

This is a **two-bug compound** that produces the visible symptom: *"the server picks up the saved game and pushes ResumeOrNewDialog, but clicking Resume errors with 'No saved game found' even though the world is restored on the server."* Both halves were shipped together in the 2026-06-26 fix.

#### BUG 19a: Auto-restore completes after WS session is registered — initial sync never sent (FIXED)

- **Fix location:** `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:415-474` — changed `CoroutineScope(Dispatchers.IO).launch { ... }` to `async { ... }` returning a `Deferred`, with the `onConnected` lambda `await()`-ing the handle before reading `findPlayerStatsByConnectionId` and calling `sendInitialSync`.
- **Fix shape:** Awaitable IO. The `onConnected` lambda in `ServerConnectionCoordinator.onConnected` is already `suspend`, so the change is a `runBlocking`-free rewrite. `beginRestore`/`endRestore` calls bracket the IO and feed `WorldManager.activeRestores` (ConcurrentHashMap keyed by accelByteUserId).
- **Diagnostic signature (post-fix):** `TurnHarness.applyGameSnapshot: remapped playerID ... on 1 entry(ies)` AND `Human player ... joined, triggering initial sync` arrive in the correct order with no gap.

#### BUG 19b: Race-recovery short-circuits on round-1 games (FIXED)

- **Fix location:** `server/src/main/kotlin/gameState/WorldManager.kt:107-160` (new `lastRehydratedAccelByteUserId: String?` flag, `@Volatile` with private setter), `TurnHarness.kt:1892-1909` (set inside `applyGameSnapshot`), `GameRestoreRpcHandlers.kt:283-297` (`isWorldAlreadyRestoredForUser` now reads `WorldManager.lastRehydratedAccelByteUserId == userId` instead of `isWorldEmpty()`).
- **Fix shape:** Transient rehydrated flag on WorldManager. Set by `applyGameSnapshot` after a successful snapshot apply. Cleared by `applyRestoredWorldAndSync` (after the sync lands) and `clearRunningGameForUser` (on game-over paths).
- **Diagnostic signature (post-fix):** `WorldManager.lastRehydratedAccelByteUserId: $accelByteUserId` log line at `TurnHarness.kt:1909` confirms the flag was set during the auto-restore path.

#### Combined fix verification (live run, 2026-06-26 21:42)

Server log lines confirming both fixes fired in sequence:
```
TurnHarness.applyGameSnapshot: remapped playerID for accelByteUserId='004c3eb0...' 
  from previous=[kvision-ws-client-OLD] to 'kvision-ws-client-NEW' on 1 entry(ies)
TurnHarness: Rehydrated running-game snapshot for user=004c3eb0... (round=1, ...)
gameState.WorldManager.markRehydratedFromSnapshot: 004c3eb0...
Server: Rehydrated running-game for user=004c3eb0... from account record; round=1, stats.size=2
Server: Human player AUongfa834nfa joined, triggering initial sync        ← BUG 19a fix
UiSignalRpcHandlers: Syncing audio state to kvision-ws-client-NEW
UiSignalRpcHandlers: Initial sync notifications dispatched
```
No "No saved game found" messageBox. Resume click was idempotent — confirmed at `autogenesis-2026-06-26-225609.log`.

#### BUG 19a: Auto-restore completes after WS session is registered — initial sync never sent

- **Symptom:** `autogenesis-*.log` shows the auto-restore successfully rehydrating the snapshot (e.g. `TurnHarness.applyGameSnapshot: remapped playerID ... on 1 entry(ies)` then `TurnHarness: Rehydrated running-game snapshot ... round=1, turnIndex=0`), but the user's browser never gets `sendInitialSync`. The next log line for the WS session is `Connection kvision-ws-client-X did not match any registered player stats (registeredPlayers=[])`, followed by `Player kvision-ws-client-X registered as PRIMARY` — with NO `Human player ... joined, triggering initial sync` in between. The user lands on a blank MainMenu (no GameplayUI). Then server-extend pushes `client.resumeAvailable` (the snapshot was real when server-extend read it), the browser mounts `ResumeOrNewDialog`, the user clicks Resume.
- **Location:** `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:408` (auto-restore launch) and `Server.kt:443` (`val stats = gameState.WorldManager.findPlayerStatsByConnectionId(session.playerId)` inside `onConnected`).
- **Root cause:** The auto-restore at `Server.kt:408` is fire-and-forget on `CoroutineScope(Dispatchers.IO).launch`. The synchronous `onConnected` block at line 443 reads `findPlayerStatsByConnectionId(session.playerId)` BEFORE the restore completes — `WorldManager.playerStats` is still empty at that moment, so `stats == null`, the `else` branch fires, and no `sendInitialSync` is sent. By the time the auto-restore IO-launch finishes (~600ms later) and writes the consumed-sentinel, the WS session has already been registered as PRIMARY but never told the world was restored.
- **Diagnostic signature:** In `autogenesis-*.log`, look for `TurnHarness.applyGameSnapshot: remapped playerID ...` AND an EARLIER `Connection kvision-ws-client-X did not match any registered player stats (registeredPlayers=[])` for the SAME session — with no `Human player ... joined, triggering initial sync` between them. The time delta between the two events is typically 500-900 ms (the IO dispatcher latency).

#### BUG 19b: Race-recovery short-circuits on round-1 games

- **Symptom:** After BUG 19a (no initial sync), user clicks Resume. Server reads the consumed-sentinel → `restoreWorldFromUserRecord` returns `Result.failure`. `GameRestoreRpcHandlers.restoreRunningGame` falls through to the race-recovery check at `GameRestoreRpcHandlers.kt:177` — but returns `false` because the check uses `WorldManager.isWorldEmpty() == false` as the FIRST predicate, and `isWorldEmpty()` returns `roundNumber <= 1 && history.isEmpty()`. The user's restored game starts at round 1 with no committed history, so `isWorldEmpty()` returns `true` and the recovery short-circuits BEFORE checking `playerStats.any { it.accelByteUserId == userId }`. The world IS in the resumed state on the server, but the recovery can't detect it.
- **Location:** `server/src/main/kotlin/org/ttt/autogenesis/server/GameRestoreRpcHandlers.kt:283-289` (`private fun isWorldAlreadyRestoredForUser(userId: String): Boolean`).
- **Root cause:** The race-recovery predicate conflates "the world was just auto-restored for this user" (which should fire recovery) with "the world is non-empty" (which is the existing condition). For round-1 games with empty history, both look the same — the predicate cannot distinguish "fresh world" from "resumed world that happens to start at round 1." The second predicate (`playerStats.any { it.accelByteUserId == userId }`) WOULD distinguish them, but it's gated behind the failing first predicate.
- **Diagnostic signature:** In `autogenesis-*.log`, look for `restoreRunningGame: restore failed for user=X: running-game record deserialized to null` IMMEDIATELY followed by `RPC Sending Response: method=server.restoreRunningGame ... restored=false`, AND within ~5 seconds earlier in the SAME log file, `TurnHarness: Rehydrated running-game snapshot for user=X (round=1, turnIndex=0, historyEntries=0)`. The combination proves the restore succeeded and the recovery failed.

#### Combined user-visible symptom (timeline from a real run on 2026-06-26 21:19:40Z)

1. `21:19:40.193` — Browser WS connects. `onConnected` runs synchronously; `findPlayerStatsByConnectionId` returns null because world is empty. No initial sync.
2. `21:19:41.085` — Auto-restore IO-launch completes. World IS restored (round=1, history=0, playerID remapped). But the WS session is already registered; no sync is re-sent.
3. `21:19:41.146` — server-extend reads the VFS (snapshot still real at this moment).
4. `21:19:41.476` — Main server writes the consumed-sentinel (delete failed with errorCode 20013, fallback to sentinel).
5. `21:19:41.522` — server-extend pushes `client.resumeAvailable`. Browser mounts `ResumeOrNewDialog`.
6. `21:19:43.001` — User clicks Resume.
7. `21:19:43.322` — `restoreRunningGame: restore failed ... deserialized to null` (sentinel). Race-recovery check returns `false` for round-1 game.
8. `21:19:43.328` — Browser logs `MatchmakingClient.requestResume: restored=false`. UI shows "No saved game found on the server." messageBox.

#### Suggested fix shape (NOT YET APPLIED — requires plan-mode confirmation)

- **For BUG 19a:** Chain `sendInitialSync` to fire AFTER the auto-restore IO-launch completes. The cleanest shape is to collapse the two paths into one coroutine — the IO-launch acquires the restore, applies the snapshot, then immediately calls `sendInitialSync` for the calling session. No new field needed. An alternative (less clean but simpler) is to add a transient `WorldManager.lastRehydratedAccelByteUserId: String?` set inside `applyGameSnapshot` and have the `onConnected` synchronous block poll for it (with a short timeout) before deciding to skip the sync.
- **For BUG 19b:** Replace the `isWorldEmpty()` predicate in `isWorldAlreadyRestoredForUser` with a check against `WorldManager.lastAutoRestoredAccelByteUserId == userId`. The semantic becomes "did the auto-restore on connect win the race" — not "is the world non-empty." The second predicate (`playerStats.any { accelByteUserId == userId }`) stays as a backup. Both must land together: BUG 19b's predicate alone would let it fire for any non-empty world with a matching user (false-positive); BUG 19a's sync-after-restore is needed so the user doesn't have to click Resume in the first place.
- **Combined regression coverage:** Add a test in `GameRestoreRpcHandlersRaceTest.kt` that exercises the realistic steady-state: `applyGameSnapshot` for a round-1 zero-history game → `restoreRunningGame` on the same user → expect `true` (race-recovered). The existing 4-test suite does NOT cover this case because it uses a real game with non-trivial round/history, which masks the round-1 failure. Also add a test in `TurnHarnessRunningGameTest.kt` that asserts `applyGameSnapshot` sets the `lastAutoRestoredAccelByteUserId` field (whichever shape the fix lands on) so the next refactor cannot silently remove the signal.

#### Lesson extracted (cross-cutting)

The pattern in BUG 19 is: **fire-and-forget IO launches that gate a synchronous block's behavior on the IO's side-effect**. The synchronous block reads a state that the IO is about to mutate but hasn't yet. Two ways to avoid this in future code:

1. **Don't fire-and-forget IO launches that produce a state the synchronous path needs to read.** Either inline the work in the synchronous block (use `runBlocking` or `Dispatchers.Unconfined.runBlocking` for IO-bound work that must complete before continuing) or chain the synchronous work into the same coroutine as a continuation.
1. **Wire-format normalization is a resolver responsibility, not a documentation promise.** "Fuzzy-matched" KDoc without an actual normalization step is a latent bug waiting for a server-emit/client-lookup format mismatch. If the resolver falls back to null on a known catalog shape, the manifest shape is wrong — fix the resolver, don't paper over with the server.

2. **Defensive code that "always times out" is a smell.** Trace where the work actually goes before adding a wait. If the work is gone, delete the wait; if the work moved, delete the duplicate consumer.

3. **Two registrations of the same identifier is a footgun in any plugin/registry pattern.** This generalises beyond `@RpcMethod` to `@app.route`, `app.post`, Express middleware ordering, OS service registration, etc. Always audit for duplicate registrations before assuming the new code path is live.

4. **Auth-gate defaults must be conservative AND distinguishable.** Defaulting `accelbyteId` to a random placeholder is wrong on two axes: it's not a real identity AND it makes downstream lookups think it's a real identity. The right shape: when an auth param is missing, treat the connection as `guestMode=true` so identity-required operations are skipped, not attempted with a fake identity.

5. **Session-lifetime flags make bad persistence gates.** (BUG 25, 2026-06-27) If a "should I save right now?" predicate is `WorldManager.isGameActive`, it will fire on the bridge disconnect that follows GameInit-before-human-arrives — capturing an empty fresh-init world and overwriting any prior real save. The fix is a "did the human take at least one action?" flag, not a session-lifetime boolean. Diagnostic: cross-log grep for the user's saves — if every save is `round=1, historyEntries=0`, BUG 25 is firing.

## Updated Grep Patterns (BUG 16/18/25)

```bash
# Audio resource resolution failure (BUG 16)
grep -n "no audio file matches resourceName\|preload FAILED.*no audio will play\|loadBuffer returned null" ~/.autogenesis/logs/browser-*.log | head -20

# Audio basename resolution success (post-BUG-16 fix)
grep -n "AudioResourceLoader.resolvePath: BASENAME hit" ~/.autogenesis/logs/browser-*.log | head -10

# WS connection with random accelbyteId (BUG 18)
grep -n "accelbyteId=kvision-ws-client-" ~/.autogenesis/logs/*.log | head -20

# Server's "Could not resolve player identity" warning (BUG 18 symptom)
grep -n "Could not resolve player identity" ~/.autogenesis/logs/*.log | head -20

# Defensive-flush timeout (BUG 17 — confirms the flush path is dead)
grep -n "FLUSH: No pending audio sync state after.*wait" ~/.autogenesis/logs/browser-*.log | head -10

# Generic handler-shadowing check (BUG 17 pattern)
grep -rn '@RpcMethod' sharedModel kvisionApp server \
  | awk -F'name=' '{print $2}' | awk -F',' '{print $1}' | sort | uniq -c | sort -rn | head -20
# Any count > 1 means a handler is being shadowed.

# Generic WS-auth-default check (BUG 18 pattern)
grep -rn 'call.parameters\["accelbyteId"\]\s*?:' server/src/main/kotlin

# BUG 25 — distribution of historical saves by round/historyEntries for one user.
# Replace the accelbyteId; if the output is dominated by `round=1, turnIndex=0, historyEntries=0`,
# the user has never successfully played and BUG 25 is firing on bridge disconnect.
grep -h "Persisted running-game snapshot for user=<ACCELBYTE_ID>" \
    ~/.autogenesis/logs/autogenesis-*.log \
  | grep -oE "round=[0-9]+, turnIndex=[0-9]+, historyEntries=[0-9]+" \
  | sort | uniq -c | sort -rn

# BUG 25 — all-time count of never-played saves across all logs (sanity check)
grep -hc "Persisted running-game snapshot.*historyEntries=0" ~/.autogenesis/logs/autogenesis-*.log \
  | awk -F: 'BEGIN{total=0} {total+=$2} END{print total, "saves with historyEntries=0"}'
```

1. **Wire-format normalization is a resolver responsibility, not a documentation promise.** "Fuzzy-matched" KDoc without an actual normalization step is a latent bug waiting for a server-emit/client-lookup format mismatch. If the resolver falls back to null on a known catalog shape, the manifest shape is wrong — fix the resolver, don't paper over with the server.

2. **Defensive code that "always times out" is a smell.** Trace where the work actually goes before adding a wait. If the work is gone, delete the wait; if the work moved, delete the duplicate consumer.

3. **Two registrations of the same identifier is a footgun in any plugin/registry pattern.** This generalises beyond `@RpcMethod` to `@app.route`, `app.post`, Express middleware ordering, OS service registration, etc. Always audit for duplicate registrations before assuming the new code path is live.

4. **Auth-gate defaults must be conservative AND distinguishable.** Defaulting `accelbyteId` to a random placeholder is wrong on two axes: it's not a real identity AND it makes downstream lookups think it's a real identity. The right shape: when an auth param is missing, treat the connection as `guestMode=true` so identity-required operations are skipped, not attempted with a fake identity.

## Confirmed (2026-06-26) — Reload-game State Hydration Gap

A reload-game session surfaced three symptoms that all share one root cause: `TurnHarness.applyGameSnapshot` restores `WorldManager.playerStats` + `turnOrderIndex` + `history` + `world` + `mapPack`, but does NOT post-restore the per-turn UI hooks (music, turn timer, AI-vs-human flag). The user lands on a rehydrated world that looks "stuck" — no music, no timer, NPC moves first.

### BUG 20: Music doesn't start until first action after reload (HIGH) — FIXED 2026-06-26
- **Symptom:** After reload-and-restore, the world mounts silent. Audio only starts when the user submits their first action, at which point `MusicSelector.selectForTurn` fires the rule-1 "initialConditions" bucket.
- **Root cause:** `GameSnapshot` (`gameState/GameSnapshot.kt:23-36`) does NOT capture `AudioManager.playingObjects` or the current `MusicDecision`. After `applyGameSnapshot` completes, the server's `AudioManager.playingObjects` map is still empty (it was constructed by the fresh DS's startup with zero audio resources). On the client, the `audio.syncState` push that arrives in `sendInitialSync` carries `scheduledObjects=0`, so no audio plays.
- **Diagnostic signature:** `AudioManager.buildSyncState: globalVolume=1.0 channels=2 scheduledObjects=0` in the server log, immediately after `Rehydrated running-game snapshot`.
- **Fix:** New `TurnHarness.hydratePostRestoreState(snapshot, accelByteUserId, currentConnectionId)` helper called immediately after `applyGameSnapshot`. Mirrors `selectAndBroadcastMusicForTurn` — builds the same `TurnContext` (with `isFirstTurn = roundNumber == 1 && turnOrderIndex == 0`) and calls `MusicSelector.selectForTurn` + `AudioManager.broadcastMusicSchedule`. For round 1 this fires the rule-1 "initialConditions" bucket, matching what a fresh round-1 game does at log line `MusicSelector.selectForTurn: rule 1 fired → bucket=initialConditions (1 tracks: Initial Conditions wet 1) for actor='AUongfa834nfa' round=1`.
- **Lesson:** Snapshots that rehydrate a live runtime (audio, UI hooks, timers) must re-run the runtime's "post-state-applied" hooks. Snapshotting just the data model leaves the user staring at a half-mounted world.

### BUG 21: Reload makes the live session an AI-controlled NPC (HIGH) — FIXED 2026-06-26
- **Symptom:** After reload, the user is treated as AI-controlled. Either (a) the AI takes over the user's turn on the very next round, or (b) the OTHER AI player moves the moment the user submits their first action.
- **Root cause:** `PlayerStats.isControlledByNpc` round-trips through the snapshot. When the user reloaded, the snapshot's `isControlledByNpc` was `true` for the user's stats entry (because the player was mid-AI-turn when saved). The `applyGameSnapshot` remap loop only wrote `playerID` and `isConnected`, NOT `isControlledByNpc`. So `Server.kt:482` (`if(!stats.isControlledByNpc)`) skipped the "Human player joined" branch and the session routed through `handleAiTakeover`.
- **Diagnostic signature:** `Identified connection kvision-ws-client-X as player 'AUongfa834nfa' (isNpc=true)` in the server log, immediately followed by `Player 'AUongfa834nfa' is marked as AI-controlled - returning false to trigger immediate takeover`.
- **Fix:** Inside the `applyGameSnapshot` remap loop (`TurnHarness.kt:1996-2016`), write `entry.isControlledByNpc = false` on the remap target alongside the existing `playerID` and `isConnected` writes. NPC entries (blank `accelByteUserId`) are never in the `remapTargets` filter list, so they remain untouched. The log line is extended to capture the flip.
- **Lesson:** Snapshot fields that the runtime resets per-session (identity flags, session handles, scope tokens) must be REMAPPED on apply, not just preserved. The BUG 19 fix already did this for `playerID`; this fix extends the pattern to `isControlledByNpc`. The general shape: any field that snapshots the live session's role/scope/identity must be rewritten on apply so the live session resolves correctly. Search `grep -rn "var isControlledByNpc\|playerID == \|playerID in" server/src/main/kotlin/` to find other snapshot fields that may need the same treatment.

### BUG 25: Disconnect-time persistence saves a never-played game (HIGH) — DISCOVERED 2026-06-27, FIXED 2026-06-27 (same session)
- **Symptom (visible from UI):** A user "resumes" a saved game and gets a completely fresh-looking world: Main Score 0, all resource counters 0, empty Story panel, empty Map, no leaderboard, no round indicator. Server-side rehydrate path completes successfully (`Rehydrated running-game snapshot ... round=1, turnIndex=0, historyEntries=0`) and music/timer/AI-flag all initialize correctly (BUG 20/21/22 fixes fired) — the world being rehydrated is just genuinely empty.
- **Root cause:** `Server.kt:558` fired `TurnHarness.serializeCurrentWorldSnapshotToUserRecord(humanUserId)` on every `onDisconnected` whenever `WorldManager.isGameActive=true` and `!hasAnyPrimarySession()`. But `WorldManager.isGameActive` is set to `true` the moment GameInit finishes (`TurnHarness.kt:864`, `GameInit.kt:235`) — long before the human's WebSocket connects. So when `server-extend-client` (CONTROLLER role, the bridge that calls `setGameMode`) disconnects 1-2s after setting up the game, the save fires. The human WS hasn't joined yet, so the save captures the just-initialized world (empty history, no turns played) and overwrites any prior real save. When the human finally connects, rehydrate loads the empty fresh-init snapshot.
- **Why this is invisible from the rehydrate side:** the rehydrate path correctly reads back what was saved. The BUG 20/21/22 hydration helpers fire correctly. The state being hydrated is empty because the state that was saved was empty. The bug is upstream in the **save gate**, not the **restore gate**.
- **Real observed case (2026-06-27, user `004c3eb02c0b4436b41b24d5d670b0e4`):** across all `autogenesis-*.log` files from March 2026 through 2026-06-27, **every single persistence event was `round=1, turnIndex=0, historyEntries=0`**. The user had never made it past the AI's first turn. The 2026-06-27 reconnect was symptomatic of a multi-month latent bug, not a new regression.
- **Fix (applied 2026-06-27, plan `.hermes/plans/fix-never-played-persistence-2026-06-27.md`):** Option A from the original design gate — added `WorldManager.humanPlayerHasJoinedOnce: Boolean` (volatile, near `humanPlayerName`) set to `true` inside `TurnHarness.awaitPlayerAction` when `isReachable` returns true for the human player (specifically: `player.name == WorldManager.humanPlayerName`). Extracted the gate predicate into a pure top-level helper `shouldPersistOnDisconnect(humanAccelByteUserId, isSinglePlayer, isGameActive, humanPlayerHasJoinedOnce)` at the bottom of `Server.kt`. Replaced the `Server.kt:558` predicate with a call to that helper. Added an audit log line `Server: Skipped save-on-disconnect ... (humanPlayerHasJoinedOnce=false)` so future regressions are immediately auditable.
- **Why this gate shape, not B/C/D from the original design:** the simplest correct behavior is "don't save garbage". `running-game` should mean "a game the user actually started playing" — not "a world that GameInit spun up and immediately shut down". Downstream `restoreRunningGame` and `MainMenu.kt:480` "No saved game found" branch already handle the no-record case cleanly. Option A catches all "user never played" cases with one boolean + one helper, no schema changes, no consumed-sentinel cascades.
- **Per-session diagnostic signature (post-fix):**
  - Healthy: `TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true for 'X'` followed by `TurnHarness: Persisted running-game snapshot ... round=N, turnIndex=K, historyEntries=M` (with non-zero M).
  - BUG 25 firing (regression): `Server: Skipped save-on-disconnect ... humanPlayerHasJoinedOnce=false` followed by NO `Persisted running-game snapshot` for that user.
- **Fix shapes NOT applied (alternative designs considered, rejected for this case):**
  - **B. Delete the snapshot on `humanPlayerHasJoinedOnce=false` disconnect instead of saving:** would arms-race with the consumed-sentinel path in `invalidateRunningGameRecord` (consumed-sentinel is already added by `applyGameSnapshot` earlier in the lifecycle).
  - **C. Add `firstPlayerActionAt` to `GameSnapshot`; on load, if `null`, fall through to "no resume available":** requires a `GameSnapshot` schema change and a restore-time gate, more moving parts than option A.
  - **D. Move persistence from `onDisconnected` to the `markTurnAsProcessed` post-commit hook:** most architecturally correct but touches 4+ call sites in TurnHarness. Deferred — option A is sufficient for the BUG 25 symptom.
- **Regression coverage:**
  - `server/src/test/kotlin/org/ttt/autogenesis/server/SaveOnDisconnectGateTest.kt` (3 tests, all passing) — exercises the `shouldPersistOnDisconnect` helper directly: never-joined → false; joined-once → true; blank humanUserId → false.
  - `kvisionApp-e2e/probes/never-played-resume.mjs` (new) — drives a full human-joined play cycle, asserts the `marked humanPlayerHasJoinedOnce=true` log line fires, asserts the `Persisted running-game snapshot` log fires, asserts the `Skipped save-on-disconnect` log does NOT fire (regression guard against over-restrictive gate). 4/4 assertions pass.
- **Lesson (cross-cutting — extends the Session-Lifetime vs In-Flight Signal anti-pattern):**
  The BUG 14 anti-pattern showed that `WorldManager.isGameActive` is **session-lifetime** and conflates "game started" with "game currently being played by a human." BUG 25 shows the second-order failure mode: that same flag was being used as a **persistence gate**, which is also wrong. The semantic check should be "did a human player actually take at least one action in this game session?" — that's a flag that flips only when a player action commits. Treating `isGameActive` as "the world is interesting enough to persist" silently captures the empty fresh-init state on bridge disconnect.
  **General rule:** any time a session-lifetime boolean is used as a "should I do X right now?" gate, ask whether X requires more than "the session started." If yes, the gate is wrong.
  **Symmetric lesson for the restore side (BUG 22/23/24):** the restore path is also a state-RESTORE funnel, not a state-INITIALIZE funnel — every per-turn setup step that fires inside `executeSingleTurn` / `awaitPlayerAction` must also fire on restore, or the user lands on a half-mounted world. The `hydratePostRestoreState` helper introduced for BUG 22/23/24 is the restore-side analog of the `shouldPersistOnDisconnect` gate introduced for BUG 25 — both are "snapshot/RESTORE funnel is incomplete; what other runtime hooks need to fire alongside the data copy?" audits.
- **Audit checklist when reviewing save/persist/disconnect-time cleanup logic:**
  1. What does the gate predicate actually require? Trace the writers of every operand.
  2. Does the predicate require "X happened at least once" (e.g., player action, score change, history entry)? If yes, you need a counter or timestamp, not a session-lifetime boolean.
  3. Does the predicate fire on the bridge disconnect (`server-extend-client`, role=CONTROLLER) where no human WS is connected yet? If yes, the gate fires before the human ever arrives.
  4. After fixing, verify with the cross-log grep above that the user's distribution of saves shifts away from "100% round=1, historyEntries=0" toward a real spread.

### BUG 22: Turn timer doesn't arm on reload (MEDIUM) — FIXED 2026-06-26
- **Symptom:** After reload, the UI shows "Your turn" but the countdown is absent — no `[data-testid="turn-timer"]` element renders with a "M:SS" countdown.
- **Root cause:** `WorldManager.startTurnTimer` is only called from `TurnHarness.awaitPlayerAction` (`TurnHarness.kt:610`), which only fires when `executeSingleTurn` runs. On rehydrate, no turn is executing, so no timer is armed. The UI mounts the world with `activeTurnActor` set (from the snapshot) but the timer widget's countdown never starts because `gameTimer.start(...)` is never called.
- **Fix:** Inside `hydratePostRestoreState`, if the saved snapshot's `turnOrder[turnOrderIndex] == humanPlayerName`, call `WorldManager.startTurnTimer(snapshot.humanPlayerName, TURN_DURATION_SECONDS)`. If the NPC was up when the game shut down, no timer arms — the loop tick on the next submit will fire `executeSingleTurn` which arms it.
- **Diagnostic signature (post-fix):** `TurnHarness.hydratePostRestoreState: armed turn timer for human='AUongfa834nfa' (saved turnOrderIndex=0, round=1)` in the server log.
- **Lesson:** UI hooks that depend on a per-turn runtime (countdown timers, status indicators, "your turn" banners) need to be re-armed after any snapshot apply, not just first-time world setup.

## Updated Grep Patterns (BUG 20/21/22/26)

```bash
# Post-restore hydration (BUG 20/21/22 — verify all three fixes fired)
grep -n "hydratePostRestoreState" ~/.autogenesis/logs/autogenesis-*.log | head -10

# Music scheduled on restore (BUG 20 fix signal)
grep -n "Music schedule broadcast.*+1 tracks.*Initial Conditions wet 1" ~/.autogenesis/logs/autogenesis-*.log | head -5

# Turn timer armed on restore (BUG 22 fix signal)
grep -n "armed turn timer for human=" ~/.autogenesis/logs/autogenesis-*.log | head -5

# AI-takeover post-restore (BUG 21 — should NOT appear after fix)
grep -n "is marked as AI-controlled - returning false to trigger immediate takeover" ~/.autogenesis/logs/autogenesis-*.log | head -5

# isControlledByNpc flip log (BUG 21 fix signal)
grep -n "flipped isControlledByNpc from.*to \[false\]" ~/.autogenesis/logs/autogenesis-*.log | head -5

# BUG 26 — dialog mount count per browser log file. Healthy: 1. BUG firing: >= 2.
grep -c "ResumeOrNewDialog mounted" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"

# BUG 26 — push count per userId per server-extend log file. Healthy: 1. BUG firing: >= 2.
grep -oE "pushed resumeAvailable for user=[a-z0-9]+" ~/.autogenesis/logs/server-extend-*.log \
  | sort | uniq -c | sort -rn | head -10

# BUG 26 — SSE reconnect rate (the underlying trigger cadence)
grep -c "RestRpcClient.connect: Opening SSE channel" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"
```

## Probe Pattern: Reload-Game State (2026-06-26 / 2026-06-27)

Two e2e probes cover the reload-game lifecycle from different angles. Both run via `kvisionApp-e2e/probes/`:

**`music-timer-restore.mjs`** — verifies the post-restore UI state hydration (BUG 22/23/24 fixes):
- **Phase A** — music. Reads the browser console for `MusicRunner.playSchedule: applied ... played=N` (with `played >= 1`). Music is delivered via Web Audio API buffers, NOT `<audio>` DOM elements, so the probe must observe the console log line, not query the DOM.
- **Phase B** — turn timer. `document.querySelector('[data-testid="turn-timer"]')` is visible and `textContent` matches `/^\d+:\d{2}$/`.
- **Phase C** — turn ownership. No `[data-testid="ai-think"]` element visible after Resume. Body text contains "Your turn" or "Awaiting your decision".
- **Phase D** — gameplay mount. `[data-testid="gameplay-ui"]` element present after Resume.

**`never-played-resume.mjs`** — verifies the save-side gate (BUG 25 fix) by driving a full human-joined play cycle and asserting:
- `TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true` log line fires (gate is reachable).
- `TurnHarness: Persisted running-game snapshot` log line fires (gate is permissive for human-joined games — regression guard against over-restrictive gate).
- `Server: Skipped save-on-disconnect` log line does NOT fire (regression guard — must only fire for never-joined bridge disconnects).
- `ResumeOrNewDialog` reappears on Phase C reconnect (cloud save IS real for human-joined games).

The never-joined-disconnect path itself is hard to drive from Playwright (the bridge session is server-internal, not browser-accessible), so this probe verifies the gate's two valid states (permissive for human-joined, would-skip for never-joined) rather than driving the never-joined disconnect directly. To verify the skip path fires, drive it manually by booting the dev servers, watching `/tmp/autogenesis-proxy/srv.log`, and grepping for the skip line within 60s of `GameInit: Game world initialized and active`.

**Probe-author pitfall:** Don't probe the DOM for audio. Audio in this app is delivered through Web Audio API buffers cached in `AudioEngine`, not `<audio>` DOM elements (those exist only during the initial `Mp3AssetLoader` preload and are removed once the buffer is cached). For audio state, observe the console log or the server log.

## Static-State Leak Across Tests (lesson extracted from BUG 22 unit test)

1. **Wire-format normalization is a resolver responsibility, not a documentation promise.** "Fuzzy-matched" KDoc without an actual normalization step is a latent bug waiting for a server-emit/client-lookup format mismatch. If the resolver falls back to null on a known catalog shape, the manifest shape is wrong — fix the resolver, don't paper over with the server.

2. **Defensive code that "always times out" is a smell.** Trace where the work actually goes before adding a wait. If the work is gone, delete the wait; if the work moved, delete the duplicate consumer.

3. **Two registrations of the same identifier is a footgun in any plugin/registry pattern.** This generalises beyond `@RpcMethod` to `@app.route`, `app.post`, Express middleware ordering, OS service registration, etc. Always audit for duplicate registrations before assuming the new code path is live.

4. **Auth-gate defaults must be conservative AND distinguishable.** Defaulting `accelbyteId` to a random placeholder is wrong on two axes: it's not a real identity AND it makes downstream lookups think it's a real identity. The right shape: when an auth param is missing, treat the connection as `guestMode=true` so identity-required operations are skipped, not attempted with a fake identity.

5. **Session-lifetime flags make bad persistence gates.** (BUG 25, 2026-06-27) If a "should I save right now?" predicate is `WorldManager.isGameActive`, it will fire on the bridge disconnect that follows GameInit-before-human-arrives — capturing an empty fresh-init world and overwriting any prior real save. The fix is a "did the human take at least one action?" flag, not a session-lifetime boolean. Diagnostic: cross-log grep for the user's saves — if every save is `round=1, historyEntries=0`, BUG 25 is firing.

## Updated Grep Patterns (BUG 16/18/25)

```bash
# Audio resource resolution failure (BUG 16)
grep -n "no audio file matches resourceName\|preload FAILED.*no audio will play\|loadBuffer returned null" ~/.autogenesis/logs/browser-*.log | head -20

# Audio basename resolution success (post-BUG-16 fix)
grep -n "AudioResourceLoader.resolvePath: BASENAME hit" ~/.autogenesis/logs/browser-*.log | head -10

# WS connection with random accelbyteId (BUG 18)
grep -n "accelbyteId=kvision-ws-client-" ~/.autogenesis/logs/*.log | head -20

# Server's "Could not resolve player identity" warning (BUG 18 symptom)
grep -n "Could not resolve player identity" ~/.autogenesis/logs/*.log | head -20

# Defensive-flush timeout (BUG 17 — confirms the flush path is dead)
grep -n "FLUSH: No pending audio sync state after.*wait" ~/.autogenesis/logs/browser-*.log | head -10

# Generic handler-shadowing check (BUG 17 pattern)
grep -rn '@RpcMethod' sharedModel kvisionApp server \
  | awk -F'name=' '{print $2}' | awk -F',' '{print $1}' | sort | uniq -c | sort -rn | head -20
# Any count > 1 means a handler is being shadowed.

# Generic WS-auth-default check (BUG 18 pattern)
grep -rn 'call.parameters\["accelbyteId"\]\s*?:' server/src/main/kotlin

# BUG 25 — distribution of historical saves by round/historyEntries for one user.
# Replace the accelbyteId; if the output is dominated by `round=1, turnIndex=0, historyEntries=0`,
# the user has never successfully played and BUG 25 is firing on bridge disconnect.
grep -h "Persisted running-game snapshot for user=<ACCELBYTE_ID>" \
    ~/.autogenesis/logs/autogenesis-*.log \
  | grep -oE "round=[0-9]+, turnIndex=[0-9]+, historyEntries=[0-9]+" \
  | sort | uniq -c | sort -rn

# BUG 25 — all-time count of never-played saves across all logs (sanity check)
grep -hc "Persisted running-game snapshot.*historyEntries=0" ~/.autogenesis/logs/autogenesis-*.log \
  | awk -F: 'BEGIN{total=0} {total+=$2} END{print total, "saves with historyEntries=0"}'
```

1. **Wire-format normalization is a resolver responsibility, not a documentation promise.** "Fuzzy-matched" KDoc without an actual normalization step is a latent bug waiting for a server-emit/client-lookup format mismatch. If the resolver falls back to null on a known catalog shape, the manifest shape is wrong — fix the resolver, don't paper over with the server.

2. **Defensive code that "always times out" is a smell.** Trace where the work actually goes before adding a wait. If the work is gone, delete the wait; if the work moved, delete the duplicate consumer.

3. **Two registrations of the same identifier is a footgun in any plugin/registry pattern.** This generalises beyond `@RpcMethod` to `@app.route`, `app.post`, Express middleware ordering, OS service registration, etc. Always audit for duplicate registrations before assuming the new code path is live.

4. **Auth-gate defaults must be conservative AND distinguishable.** Defaulting `accelbyteId` to a random placeholder is wrong on two axes: it's not a real identity AND it makes downstream lookups think it's a real identity. The right shape: when an auth param is missing, treat the connection as `guestMode=true` so identity-required operations are skipped, not attempted with a fake identity.

## Confirmed (2026-06-26) — Reload-game State Hydration Gap

A reload-game session surfaced three symptoms that all share one root cause: `TurnHarness.applyGameSnapshot` restores `WorldManager.playerStats` + `turnOrderIndex` + `history` + `world` + `mapPack`, but does NOT post-restore the per-turn UI hooks (music, turn timer, AI-vs-human flag). The user lands on a rehydrated world that looks "stuck" — no music, no timer, NPC moves first.

### BUG 20: Music doesn't start until first action after reload (HIGH) — FIXED 2026-06-26
- **Symptom:** After reload-and-restore, the world mounts silent. Audio only starts when the user submits their first action, at which point `MusicSelector.selectForTurn` fires the rule-1 "initialConditions" bucket.
- **Root cause:** `GameSnapshot` (`gameState/GameSnapshot.kt:23-36`) does NOT capture `AudioManager.playingObjects` or the current `MusicDecision`. After `applyGameSnapshot` completes, the server's `AudioManager.playingObjects` map is still empty (it was constructed by the fresh DS's startup with zero audio resources). On the client, the `audio.syncState` push that arrives in `sendInitialSync` carries `scheduledObjects=0`, so no audio plays.
- **Diagnostic signature:** `AudioManager.buildSyncState: globalVolume=1.0 channels=2 scheduledObjects=0` in the server log, immediately after `Rehydrated running-game snapshot`.
- **Fix:** New `TurnHarness.hydratePostRestoreState(snapshot, accelByteUserId, currentConnectionId)` helper called immediately after `applyGameSnapshot`. Mirrors `selectAndBroadcastMusicForTurn` — builds the same `TurnContext` (with `isFirstTurn = roundNumber == 1 && turnOrderIndex == 0`) and calls `MusicSelector.selectForTurn` + `AudioManager.broadcastMusicSchedule`. For round 1 this fires the rule-1 "initialConditions" bucket, matching what a fresh round-1 game does at log line `MusicSelector.selectForTurn: rule 1 fired → bucket=initialConditions (1 tracks: Initial Conditions wet 1) for actor='AUongfa834nfa' round=1`.
- **Lesson:** Snapshots that rehydrate a live runtime (audio, UI hooks, timers) must re-run the runtime's "post-state-applied" hooks. Snapshotting just the data model leaves the user staring at a half-mounted world.

### BUG 21: Reload makes the live session an AI-controlled NPC (HIGH) — FIXED 2026-06-26
- **Symptom:** After reload, the user is treated as AI-controlled. Either (a) the AI takes over the user's turn on the very next round, or (b) the OTHER AI player moves the moment the user submits their first action.
- **Root cause:** `PlayerStats.isControlledByNpc` round-trips through the snapshot. When the user reloaded, the snapshot's `isControlledByNpc` was `true` for the user's stats entry (because the player was mid-AI-turn when saved). The `applyGameSnapshot` remap loop only wrote `playerID` and `isConnected`, NOT `isControlledByNpc`. So `Server.kt:482` (`if(!stats.isControlledByNpc)`) skipped the "Human player joined" branch and the session routed through `handleAiTakeover`.
- **Diagnostic signature:** `Identified connection kvision-ws-client-X as player 'AUongfa834nfa' (isNpc=true)` in the server log, immediately followed by `Player 'AUongfa834nfa' is marked as AI-controlled - returning false to trigger immediate takeover`.
- **Fix:** Inside the `applyGameSnapshot` remap loop (`TurnHarness.kt:1996-2016`), write `entry.isControlledByNpc = false` on the remap target alongside the existing `playerID` and `isConnected` writes. NPC entries (blank `accelByteUserId`) are never in the `remapTargets` filter list, so they remain untouched. The log line is extended to capture the flip.
- **Lesson:** Snapshot fields that the runtime resets per-session (identity flags, session handles, scope tokens) must be REMAPPED on apply, not just preserved. The BUG 19 fix already did this for `playerID`; this fix extends the pattern to `isControlledByNpc`. The general shape: any field that snapshots the live session's role/scope/identity must be rewritten on apply so the live session resolves correctly. Search `grep -rn "var isControlledByNpc\|playerID == \|playerID in" server/src/main/kotlin/` to find other snapshot fields that may need the same treatment.

### BUG 25: Disconnect-time persistence saves a never-played game (HIGH) — DISCOVERED 2026-06-27, FIXED 2026-06-27 (same session)
- **Symptom (visible from UI):** A user "resumes" a saved game and gets a completely fresh-looking world: Main Score 0, all resource counters 0, empty Story panel, empty Map, no leaderboard, no round indicator. Server-side rehydrate path completes successfully (`Rehydrated running-game snapshot ... round=1, turnIndex=0, historyEntries=0`) and music/timer/AI-flag all initialize correctly (BUG 20/21/22 fixes fired) — the world being rehydrated is just genuinely empty.
- **Root cause:** `Server.kt:558` fired `TurnHarness.serializeCurrentWorldSnapshotToUserRecord(humanUserId)` on every `onDisconnected` whenever `WorldManager.isGameActive=true` and `!hasAnyPrimarySession()`. But `WorldManager.isGameActive` is set to `true` the moment GameInit finishes (`TurnHarness.kt:864`, `GameInit.kt:235`) — long before the human's WebSocket connects. So when `server-extend-client` (CONTROLLER role, the bridge that calls `setGameMode`) disconnects 1-2s after setting up the game, the save fires. The human WS hasn't joined yet, so the save captures the just-initialized world (empty history, no turns played) and overwrites any prior real save. When the human finally connects, rehydrate loads the empty fresh-init snapshot.
- **Why this is invisible from the rehydrate side:** the rehydrate path correctly reads back what was saved. The BUG 20/21/22 hydration helpers fire correctly. The state being hydrated is empty because the state that was saved was empty. The bug is upstream in the **save gate**, not the **restore gate**.
- **Real observed case (2026-06-27, user `004c3eb02c0b4436b41b24d5d670b0e4`):** across all `autogenesis-*.log` files from March 2026 through 2026-06-27, **every single persistence event was `round=1, turnIndex=0, historyEntries=0`**. The user had never made it past the AI's first turn. The 2026-06-27 reconnect was symptomatic of a multi-month latent bug, not a new regression.
- **Fix (applied 2026-06-27, plan `.hermes/plans/fix-never-played-persistence-2026-06-27.md`):** Option A from the original design gate — added `WorldManager.humanPlayerHasJoinedOnce: Boolean` (volatile, near `humanPlayerName`) set to `true` inside `TurnHarness.awaitPlayerAction` when `isReachable` returns true for the human player (specifically: `player.name == WorldManager.humanPlayerName`). Extracted the gate predicate into a pure top-level helper `shouldPersistOnDisconnect(humanAccelByteUserId, isSinglePlayer, isGameActive, humanPlayerHasJoinedOnce)` at the bottom of `Server.kt`. Replaced the `Server.kt:558` predicate with a call to that helper. Added an audit log line `Server: Skipped save-on-disconnect ... (humanPlayerHasJoinedOnce=false)` so future regressions are immediately auditable.
- **Why this gate shape, not B/C/D from the original design:** the simplest correct behavior is "don't save garbage". `running-game` should mean "a game the user actually started playing" — not "a world that GameInit spun up and immediately shut down". Downstream `restoreRunningGame` and `MainMenu.kt:480` "No saved game found" branch already handle the no-record case cleanly. Option A catches all "user never played" cases with one boolean + one helper, no schema changes, no consumed-sentinel cascades.
- **Per-session diagnostic signature (post-fix):**
  - Healthy: `TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true for 'X'` followed by `TurnHarness: Persisted running-game snapshot ... round=N, turnIndex=K, historyEntries=M` (with non-zero M).
  - BUG 25 firing (regression): `Server: Skipped save-on-disconnect ... humanPlayerHasJoinedOnce=false` followed by NO `Persisted running-game snapshot` for that user.
- **Fix shapes NOT applied (alternative designs considered, rejected for this case):**
  - **B. Delete the snapshot on `humanPlayerHasJoinedOnce=false` disconnect instead of saving:** would arms-race with the consumed-sentinel path in `invalidateRunningGameRecord` (consumed-sentinel is already added by `applyGameSnapshot` earlier in the lifecycle).
  - **C. Add `firstPlayerActionAt` to `GameSnapshot`; on load, if `null`, fall through to "no resume available":** requires a `GameSnapshot` schema change and a restore-time gate, more moving parts than option A.
  - **D. Move persistence from `onDisconnected` to the `markTurnAsProcessed` post-commit hook:** most architecturally correct but touches 4+ call sites in TurnHarness. Deferred — option A is sufficient for the BUG 25 symptom.
- **Regression coverage:**
  - `server/src/test/kotlin/org/ttt/autogenesis/server/SaveOnDisconnectGateTest.kt` (3 tests, all passing) — exercises the `shouldPersistOnDisconnect` helper directly: never-joined → false; joined-once → true; blank humanUserId → false.
  - `kvisionApp-e2e/probes/never-played-resume.mjs` (new) — drives a full human-joined play cycle, asserts the `marked humanPlayerHasJoinedOnce=true` log line fires, asserts the `Persisted running-game snapshot` log fires, asserts the `Skipped save-on-disconnect` log does NOT fire (regression guard against over-restrictive gate). 4/4 assertions pass.
- **Lesson (cross-cutting — extends the Session-Lifetime vs In-Flight Signal anti-pattern):**
  The BUG 14 anti-pattern showed that `WorldManager.isGameActive` is **session-lifetime** and conflates "game started" with "game currently being played by a human." BUG 25 shows the second-order failure mode: that same flag was being used as a **persistence gate**, which is also wrong. The semantic check should be "did a human player actually take at least one action in this game session?" — that's a flag that flips only when a player action commits. Treating `isGameActive` as "the world is interesting enough to persist" silently captures the empty fresh-init state on bridge disconnect.
  **General rule:** any time a session-lifetime boolean is used as a "should I do X right now?" gate, ask whether X requires more than "the session started." If yes, the gate is wrong.
  **Symmetric lesson for the restore side (BUG 22/23/24):** the restore path is also a state-RESTORE funnel, not a state-INITIALIZE funnel — every per-turn setup step that fires inside `executeSingleTurn` / `awaitPlayerAction` must also fire on restore, or the user lands on a half-mounted world. The `hydratePostRestoreState` helper introduced for BUG 22/23/24 is the restore-side analog of the `shouldPersistOnDisconnect` gate introduced for BUG 25 — both are "snapshot/RESTORE funnel is incomplete; what other runtime hooks need to fire alongside the data copy?" audits.
- **Audit checklist when reviewing save/persist/disconnect-time cleanup logic:**
  1. What does the gate predicate actually require? Trace the writers of every operand.
  2. Does the predicate require "X happened at least once" (e.g., player action, score change, history entry)? If yes, you need a counter or timestamp, not a session-lifetime boolean.
  3. Does the predicate fire on the bridge disconnect (`server-extend-client`, role=CONTROLLER) where no human WS is connected yet? If yes, the gate fires before the human ever arrives.
  4. After fixing, verify with the cross-log grep above that the user's distribution of saves shifts away from "100% round=1, historyEntries=0" toward a real spread.

### BUG 22: Turn timer doesn't arm on reload (MEDIUM) — FIXED 2026-06-26
- **Symptom:** After reload, the UI shows "Your turn" but the countdown is absent — no `[data-testid="turn-timer"]` element renders with a "M:SS" countdown.
- **Root cause:** `WorldManager.startTurnTimer` is only called from `TurnHarness.awaitPlayerAction` (`TurnHarness.kt:610`), which only fires when `executeSingleTurn` runs. On rehydrate, no turn is executing, so no timer is armed. The UI mounts the world with `activeTurnActor` set (from the snapshot) but the timer widget's countdown never starts because `gameTimer.start(...)` is never called.
- **Fix:** Inside `hydratePostRestoreState`, if the saved snapshot's `turnOrder[turnOrderIndex] == humanPlayerName`, call `WorldManager.startTurnTimer(snapshot.humanPlayerName, TURN_DURATION_SECONDS)`. If the NPC was up when the game shut down, no timer arms — the loop tick on the next submit will fire `executeSingleTurn` which arms it.
- **Diagnostic signature (post-fix):** `TurnHarness.hydratePostRestoreState: armed turn timer for human='AUongfa834nfa' (saved turnOrderIndex=0, round=1)` in the server log.
- **Lesson:** UI hooks that depend on a per-turn runtime (countdown timers, status indicators, "your turn" banners) need to be re-armed after any snapshot apply, not just first-time world setup.

## Updated Grep Patterns (BUG 20/21/22/26)

```bash
# Post-restore hydration (BUG 20/21/22 — verify all three fixes fired)
grep -n "hydratePostRestoreState" ~/.autogenesis/logs/autogenesis-*.log | head -10

# Music scheduled on restore (BUG 20 fix signal)
grep -n "Music schedule broadcast.*+1 tracks.*Initial Conditions wet 1" ~/.autogenesis/logs/autogenesis-*.log | head -5

# Turn timer armed on restore (BUG 22 fix signal)
grep -n "armed turn timer for human=" ~/.autogenesis/logs/autogenesis-*.log | head -5

# AI-takeover post-restore (BUG 21 — should NOT appear after fix)
grep -n "is marked as AI-controlled - returning false to trigger immediate takeover" ~/.autogenesis/logs/autogenesis-*.log | head -5

# isControlledByNpc flip log (BUG 21 fix signal)
grep -n "flipped isControlledByNpc from.*to \[false\]" ~/.autogenesis/logs/autogenesis-*.log | head -5

# BUG 26 — dialog mount count per browser log file. Healthy: 1. BUG firing: >= 2.
grep -c "ResumeOrNewDialog mounted" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"

# BUG 26 — push count per userId per server-extend log file. Healthy: 1. BUG firing: >= 2.
grep -oE "pushed resumeAvailable for user=[a-z0-9]+" ~/.autogenesis/logs/server-extend-*.log \
  | sort | uniq -c | sort -rn | head -10

# BUG 26 — SSE reconnect rate (the underlying trigger cadence)
grep -c "RestRpcClient.connect: Opening SSE channel" ~/.autogenesis/logs/browser-*.log | grep -v ":0$"
```

## Probe Pattern: Reload-Game State (2026-06-26 / 2026-06-27)

Two e2e probes cover the reload-game lifecycle from different angles. Both run via `kvisionApp-e2e/probes/`:

**`music-timer-restore.mjs`** — verifies the post-restore UI state hydration (BUG 22/23/24 fixes):
- **Phase A** — music. Reads the browser console for `MusicRunner.playSchedule: applied ... played=N` (with `played >= 1`). Music is delivered via Web Audio API buffers, NOT `<audio>` DOM elements, so the probe must observe the console log line, not query the DOM.
- **Phase B** — turn timer. `document.querySelector('[data-testid="turn-timer"]')` is visible and `textContent` matches `/^\d+:\d{2}$/`.
- **Phase C** — turn ownership. No `[data-testid="ai-think"]` element visible after Resume. Body text contains "Your turn" or "Awaiting your decision".
- **Phase D** — gameplay mount. `[data-testid="gameplay-ui"]` element present after Resume.

**`never-played-resume.mjs`** — verifies the save-side gate (BUG 25 fix) by driving a full human-joined play cycle and asserting:
- `TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true` log line fires (gate is reachable).
- `TurnHarness: Persisted running-game snapshot` log line fires (gate is permissive for human-joined games — regression guard against over-restrictive gate).
- `Server: Skipped save-on-disconnect` log line does NOT fire (regression guard — must only fire for never-joined bridge disconnects).
- `ResumeOrNewDialog` reappears on Phase C reconnect (cloud save IS real for human-joined games).

The never-joined-disconnect path itself is hard to drive from Playwright (the bridge session is server-internal, not browser-accessible), so this probe verifies the gate's two valid states (permissive for human-joined, would-skip for never-joined) rather than driving the never-joined disconnect directly. To verify the skip path fires, drive it manually by booting the dev servers, watching `/tmp/autogenesis-proxy/srv.log`, and grepping for the skip line within 60s of `GameInit: Game world initialized and active`.

**Probe-author pitfall:** Don't probe the DOM for audio. Audio in this app is delivered through Web Audio API buffers cached in `AudioEngine`, not `<audio>` DOM elements (those exist only during the initial `Mp3AssetLoader` preload and are removed once the buffer is cached). For audio state, observe the console log or the server log.

## Static-State Leak Across Tests (lesson extracted from BUG 22 unit test)

When a test class has a `@BeforeTest setUp()` that resets a static field on `WorldManager`, audit the OTHER static fields the production code mutates. BUG 22's first unit-test run failed with `assertEquals "Commander Shepard", WorldManager.activeTurnActor` because `activeTurnActor` is a static field on `WorldManager` and the prior test (which DID arm the timer) leaked its value. The setUp reset `WorldManager.world`, `history`, `playerStats`, etc., but not `activeTurnActor`. Adding `WorldManager.activeTurnActor = ""` to setUp fixed the leak.

Quick scan for related leaks in this codebase:
```bash
grep -rn "WorldManager\.\(activeTurnActor\|isGameActive\|humanPlayerName\|playerStats\|history\)" \
  server/src/test/kotlin/ | grep -v "WorldManager\." | head -20
```
If a test reads or writes a static `WorldManager` field but doesn't reset it in setUp/tearDown, you have a static-leak candidate.