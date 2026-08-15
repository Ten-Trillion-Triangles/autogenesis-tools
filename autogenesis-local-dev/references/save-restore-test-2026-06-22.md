# Save/Restore Game Test — 2026-06-22

**Scope:** Verified the new single-player "save on disconnect, resume on reconnect" feature wired to the AccelByte Cloud Save backend via the in-house VFS layer.

## What was verified working ✓

**Disconnect save to AccelByte Cloud:**
- Logged in as guest (`Login As Guest` button on port 8080) — userId becomes real AccelByte ID `004c3eb02c0b4436b41b24d5d670b0e4`, NOT `guest-user`.
- Started single-player match via curl `server.extend.requestGame` (browser UI automation is broken — see skill).
- Played Round 1, submitted action "Lord Maple Tree commands the great Entmarch eastward..." via the browser textbox + SEND button.
- Server logged at the shutdown event:
  ```
  [INFO] [DATABASE]: TurnHarness: Persisted running-game snapshot for user=004c3eb02c0b4436b41b24d5d670b0e4 (round=1, turnIndex=0, historyEntries=0)
  ```
- The save used the **real AccelByte userId**, confirming it routed to the **Cloud Save VFS** (not the local guest-user VFS). Routing lives in `server/src/main/kotlin/org/ttt/autogenesis/server/vfs/VirtualFileSystem.kt:154`:
  ```kotlin
  if (!userId.startsWith("guest") && !userId.startsWith("rest-client")) return current()
  ```

## Critical bugs blocking resume ✗

**BUG A: `GameRestoreRpcHandlers.hasRunningGame` returns false on fresh server even when snapshot exists.**
- File: `server/src/main/kotlin/org/ttt/autogenesis/server/GameRestoreRpcHandlers.kt:191-200`
- `resolveHumanUserId(ctx)` consults `WorldManager.playerStats` and `WorldManager.humanPlayerName` — both empty on a fresh server after restart.
- `RpcCallContext` (`sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcRuntime.kt:67`) only carries `connectionId` (the `kvision-ws-*` playerId), NOT the AccelByte userId.
- Log evidence: `GameRestoreRpcHandlers.hasRunningGame: no human userId for connection=kvision-ws-client-1581643333, returning false`
- **Effect:** `ResumeOrNewDialog` in `kvisionApp/src/jsMain/kotlin/ui/ResumeOrNewDialog.kt` never appears, even when a valid snapshot is sitting in the AccelByte record.
- **Fix sketch:** populate `RpcCallContext.metadata` with `accelbyteId` at the call site (`Server.kt:568-571` and `Server.kt:595-598`), and have `resolveHumanUserId` look it up there. The WebSocket query string already provides the value (logged at connection time: `accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4`).

**BUG B: Same root cause in `Server.kt` auto-restore-on-connect.**
- File: `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:251-285`
- `findPlayerStatsByConnectionId(session.playerId)` returns null on fresh server. Fallback `findPlayerFromStats(humanPlayerName)` is also empty. Restore path can never fire.
- **Effect:** A player who reconnects after a server restart never has their state rehydrated, even though the snapshot is on AccelByte.

## Other bugs found during this session

**BUG C: Game server killed itself mid-turn during narrative generation.**
- At 16:28:08, `Player session deregistered: kvision-ws-client-1919116982 (role=PRIMARY)` while the player was actively playing (TPipe was generating narrative).
- Triggered `hasAnyPrimarySession()=false` → 15s shutdown timer → `Server: Shutdown timer expired. Terminating server to prevent runaway tokens.`
- Root cause of the deregistration is unknown — the browser WebSocket should have stayed alive. Possibly related to the prior shutdown (`Server.kt:392` calls `exitProcess(0)` and the JVM takes a moment to release the port).
- **Workaround in tests:** If you see the game die mid-narrative, restart the server and the ResumeOrNewDialog path is the verification target.

**BUG D (CONFIRMED): `thinkingUpdates:[]` in TurnComplete.**
- `TurnHarness.kt: Broadcasting TurnComplete. Story Length: 0` with serialized payload showing `"thinkingUpdates":[]`.
- Same as known Bug #2 in the skill root (History.thinkingUpdates is never written by the broadcast path).

**BUG E (server-extend): `getMasterRecord` returns `RpcError(code=500, message=Index -1 out of bounds for length 0)` for users without a master record.**
- File: `server-extend/proxy/CloudSaveProxy.kt` — the getMasterRecord path crashes on an empty record list. Not blocking for the save/restore test, but it breaks the commander-collection flow for fresh AccelByte users.

## Workflow gotchas confirmed this session

1. **Port 8080 is mandatory for the static JS bundle** — server-extend CORS allowlist (`server-extend/ServerExtend.kt:197-219`) only permits `127.0.0.1:8080`, `localhost:8080`, `127.0.0.1:4173`, `localhost:4173`, etc. Port 8888 returns `403 Forbidden` with `Vary: Origin` from server-extend, and the browser shows `Failed to fetch` for `getMasterRecord`/commander fetches.

2. **Real AccelByte login is required to verify cloud save.** `?skipLogin=true` mode hijacks the userId to `guest-user`, which the VFS routes to local storage — defeating the whole point of the test. Click `Login As Guest` on the login form so the AccelByte SDK mints a real OAuth token and populates `AccelByteEnv.userId` with the real AccelByte userId.

3. **KVision virtual DOM means DOM `.click()` from JS may not fire the reactive handler.** When `Login As Guest` doesn't progress after `document.querySelector('button').click()`, check console for `[AUTH] DEBUG: [Login] Creating singleton SDK instance` to confirm the handler actually fired. If it didn't, fall back to `browser_click` on the accessibility ref — sometimes Playwright's CDP-level event reaches the handler where the JS `.click()` does not.

4. **First `Login As Guest` click triggers a multi-second OAuth round-trip** (the AccelByte IAM `oauth/token` call). Wait 5–8 seconds before snapshotting again. After login completes, a `Login Complete` modal appears — click OK to advance to the main menu.

5. **KVision matchmaking UI is fundamentally broken for automation** (already documented in skill root). Curl with `server.extend.requestGame` is the only reliable path:
   ```bash
   curl -s -X POST "http://127.0.0.1:7070/rpc?playerId=<rest-id>&guestMode=false" \
     -H "Content-Type: application/json" \
     -d '{
       "type":"request","id":"match-1","method":"server.extend.requestGame",
       "params":{
         "userName":"<any>","gameType":"SINGLEPLAYER",
         "accelByteId":"<accelbyte-user-id>","websocketId":"<ws-id>",
         "selectedCommander":null,"aiOpponentCount":1,"aiOnly":false
       }
     }'
   ```

## Round 2 bugfixes (2026-06-22, later session)

**BUG A & B (above)**: FIXED in the user's first patch round. Verified working: `hasRunningGame` returns `true` with `RpcCallContext.metadata["accelbyteId"]`, `restoreRunningGame` rehydrates the world, and the auto-restore-on-connect code runs (but was blocked by BUG #1 round 2 below).

**BUG 1 (round 2) — Auto-restore-on-connect blocked by `isSinglePlayer` gate (ROOT CAUSE):**
- The previous patch added `WorldManager.isWorldEmpty()` (correct fix for the seed-player issue) and wired the auto-restore in `Server.kt:236-295`. BUT the entire auto-restore block was nested inside `if (gameState.WorldManager.isSinglePlayer)`.
- `WorldManager.isSinglePlayer` defaults to `false` (`WorldManager.kt:92`). It is only set to `true` in `GameInit.kt:46` during `configurePlayersFromSession`, which runs DURING matchmaking — AFTER the player reconnects to a fresh DS.
- **Effect:** On a fresh server, the auto-restore block is skipped entirely. No `Server: Rehydrated` log appears. The player gets a blank world instead of their saved snapshot.
- **Verification:** Connected via WebSocket with `accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4` to a fresh server. `onConnected` fired, `isSinglePlayer=false`, auto-restore did NOT fire. Explicit `server.restoreRunningGame` RPC worked correctly (rehydrated to round 1).
- **Fix:** Move the auto-restore code OUTSIDE the `if (isSinglePlayer)` guard. Keep the shutdown-timer cancellation INSIDE the guard (shutdown is single-player-only). The auto-restore should fire for ALL PRIMARY connections regardless of `isSinglePlayer`.
- **Test pattern:** `server/src/test/kotlin/org/ttt/autogenesis/server/BugFixesServerAutoRestoreTest.kt` uses a **code-structure assertion** — it parses `Server.kt` and verifies the `val worldIsEmpty` line is NOT inside an `if (isSinglePlayer)` block by walking brace nesting. This is the pragmatic test approach when the production code is deeply embedded in a Ktor `webSocket()` handler and can't be invoked directly from a unit test. RED → GREEN → verify, all 4s build time.

**BUG 2 — Delete-on-restore fails with AccelByte permission error (FIXED via delete-then-sentinel strategy):**
- `TurnHarness.restoreWorldFromUserRecord` tried `vfs.deleteUserRecord(accelByteUserId, RUNNING_GAME_KEY)` after a successful restore. AccelByte Cloud Save returns `errorCode 20013: access forbidden: insufficient permissions` for the `ADMIN:NAMESPACE:{namespace}:USER:{userId}:CLOUDSAVE:RECORD` resource with `action: 8` (DELETE). The server's client_credentials token can WRITE user records but cannot DELETE them.
- **Effect (pre-fix):** The snapshot was never deleted after restore. `hasRunningGame` returned `true` both before and after `restoreRunningGame` — every reconnect replayed the same restore, and the `ResumeOrNewDialog` always offered "Resume" even after a successful resume.
- **Fix:** `TurnHarness.invalidateRunningGameRecord()` uses a **delete-then-sentinel** strategy: try `deleteUserRecord`, and on failure write a `consumed-sentinel` record that `hasRunningGame` treats as "no saved game". The sentinel is a marker value that the `hasRunningGame` check recognises and returns `false` for.
- **Verification:** Before restore: `hasRunningGame` → `true`. After restore: `hasRunningGame` → `false`. Log evidence:
  ```
  [INFO] [DATABASE]: TurnHarness.invalidateRunningGameRecord: wrote consumed-sentinel for user=004c3eb02c0b4436b41b24d5d670b0e4 (delete failed with: HttpResponseException: { "errorCode": 20013, ... })
  ```

**BUG 3 — Map pack bytes not resolved after restore (FIXED):**
- Saved snapshot stores `activeMapPackName = "resource:maps/Laurasiagondwana.map"`. `MapSelectionService.loadBytesByName` couldn't find it — no classpath resource at that path.
- **Effect (pre-fix):** World state rehydrated (round, playerStats, history) but the map render was blank. Dark void where the map should be.
- **Fix:** `MapSelectionService.loadBytesByName()` now strips the `resource:` prefix before classpath lookup via `stripResourcePrefix()`. A new `loadBytesByName` function was added that handles both uploaded map repository lookups AND classpath fallbacks.
- **Verification:** No more `MapSelectionService.loadBytesByName: no classpath resource for resource:maps/Laurasiagondwana.map` warnings in the restore logs.

### Code-structure test pattern (for deeply-embedded callbacks)

When the production code is inline in a Ktor `webSocket()` handler (like `Server.kt` `onConnected`), it's not easily testable via direct invocation from a unit test — the test would need to spin up a full Ktor server. The pragmatic alternative is a **code-structure assertion** test:

1. Find the line containing the guard pattern (e.g., `val worldIsEmpty`)
2. Find the enclosing `if (...) {` block by walking backwards
3. Verify the target line appears AFTER the closing `}` of the guard block
4. Use brace-depth counting to handle nested blocks correctly

See `BugFixesServerAutoRestoreTest.kt` for a working example. This pattern is useful for any future bug where a guard has been added in the wrong scope — it's faster than spinning up a full integration test and more reliable than a code review.

### Server startup args for retest

```
JAVA_HOME=/home/cage/.sdkman/candidates/java/24.0.2-graalce/ \
PATH=/home/cage/.sdkman/candidates/java/24.0.2-graalce/bin:$PATH \
MAP=gond RIG=bob,dave,bigwang \
nohup ./gradlew :server:run --console=plain > /tmp/server-r2-$(date +%H%M%S).log 2>&1 &
```

## Test artifacts

- `~/.autogenesis/logs/autogenesis-2026-06-22-120913.log` — first run, save fired at 16:28:09
- `~/.autogenesis/logs/autogenesis-2026-06-22-123720.log` — restarted server, hasRunningGame returned false at 16:38:35
- `~/.autogenesis/logs/server-extend-2026-06-22-121514.log` — server-extend log showing getMasterRecord error
- `~/.autogenesis/logs/autogenesis-2026-06-22-153423.log` — round 2 retest, consumed-sentinel + map pack fix verified
- `server/src/test/kotlin/org/ttt/autogenesis/server/BugFixesServerAutoRestoreTest.kt` — code-structure regression test for the isSinglePlayer gate fix
