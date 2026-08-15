# Resume-game e2e flow — full lifecycle

The user's stated flow contract (verbatim):

1. Player leaves in single player.
2. Server detects this, saves a record to that player's accelbyte account of the game snapshot.
3. Player returns later, logs back in. Server-extend looks for this specific record. If it exists it sends a different rpc payload down to tell the client to ask the player if they want to resume.
4. A kvision pop up widget of some kind similar to widget flows for messages we use before shows up. If the player hits yes it proceeds.
5. It claims an ams server in live mode and handles the flow of session and all that to get the player in, otherwise it sets up the server in dev mode. The player connects, the server resumes the game, sends the full ui state and syncs everything including the music back up. The turn resumes where it left off.

**Test surface (`data-testid` / class)**

Added in 2026-06-25 to make Playwright probes robust to KVision re-renders:

- `data-testid="login-as-guest"` on the Login As Guest button
  (`ui/LoginWidgets.kt:269`).
- `data-testid="main-menu"` + `data-accelbyte-user-id` +
  `data-accelbyte-display-name` on the MainMenu root VPanel
  (`ui/MainMenu.kt:60-65`).
- `data-testid="gameplay-ui"` on the GameplayUI root SimplePanel
  (`ui/gameplay/GameplayUI.kt:73`).
- `data-testid="resume-or-new-dialog"` on the ResumeOrNewDialog root
  SimplePanel + `data-testid="resume-dialog-resume"` on the Resume
  button (`ui/ResumeOrNewDialog.kt`).

## Race conditions found and fixed (2026-06-25)

Multiple layers needed to be touched to make this flow work in dev.
**All are required together** — fix one without the others and the
flow still fails.

### Race 1 — server-extend was counted as PRIMARY

server-extend opens long-lived WS connections to the game server
(`notifyGameServer` for `setGameMode`, `pushToServer` for the resume
push). Previously the URL did NOT carry `role=CONTROLLER`, so
the main server registered these as PRIMARY. The shutdown-timer
gate in `Server.kt:466-516` only arms the 15-second exit when
`!hasAnyPrimarySession()`, so the long-lived server-extend sessions
blocked the snapshot-on-disconnect path. The snapshot was never
written and the user's flow deadlocked at step 2.

**Fix:** `WebSocketRpcClientConfig.role` field (Role.CONTROLLER /
PRIMARY / null) appended as `&role=...` in `buildWebSocketUrl`. Both
server-extend call sites pass `role = Role.CONTROLLER`. Production
(auto-restore in live mode) leaves role unset → defaults to PRIMARY
on the server.

### Race 2 — `hasAnyPrimarySession` counted any tab

After the dev server restarts, the user's Firefox browser
automatically reconnects ALL its Autogenesis tabs to the new server.
The 6+ WS connections that were never in a game but were still in
`sessions` made `hasAnyPrimarySession()` return true forever. The
snapshot was never written.

**Fix:** `PlayerConnectionManager.hasAnyPrimarySession` now filters
to only PRIMARY sessions whose `playerId` is in
`WorldManager.playerStats[*].playerID` (i.e. only sessions that
correspond to a player currently in the game). Stray browser tabs on
MainMenu don't count.

### Race 3 — WS rebind fires auto-restore before server-extend push

`Main.kt:125-127` rebinds both bridges after guest login. Even with
my SSE-first ordering fix, the WS rebind completes a few milliseconds
later. The auto-restore on connect consumes the snapshot before
server-extend can read it. Server-extend then sees the consumed
sentinel and skips the push.

**Fix:** `AUTOGENESIS_DISABLE_AUTO_RESTORE` env var (defaulted to
`true` in `start_servers.sh`). When set, `resolveAutoRestoreUserId`
returns null and the WS rebind does NOT auto-restore — only the
explicit `MatchmakingClient.requestResume` RPC path can restore. This
lets server-extend's push win the race and the modal can render.
`server/build.gradle.kts` and `server-extend/build.gradle.kts`
forward the env var to the JVM as
`-DAUTOGENESIS_DISABLE_AUTO_RESTORE=true` when set.

### Race 4 — 15-second shutdown timer was too short for dev

In dev the player needs to switch tabs and re-login — the 15-second
default was too short.

**Fix:** `AUTOGENESIS_SHUTDOWN_DELAY_MS` env var (defaulted to
600000 in `start_servers.sh`). Production keeps the 15-second default.

### Race 5 — listener registered AFTER push arrived

`ResumeAvailabilityListener.register()` previously called
`WebSocketRpcBridge.waitForConnection()` then `registerHandlers` in
a coroutine. The push from server-extend arrived ~500ms after the WS
handshake but the listener's coroutine took ~800ms+ on first
connect, so the push arrived at the client BEFORE the handler was in
the registry → `dispatchNotification` silently dropped it.

**Fix (a):** `register()` is now synchronous — it just writes to the
shared `RpcRegistry` (which is a process-global map, not
connection-scoped). Idempotent via `if (registered) return`.

**Fix (b):** `Main.kt` calls `ResumeAvailabilityListener.register()` at
`start()` BEFORE the first WS connect. So the handler is always in
the registry by the time any push can arrive.

### Race 6 — push arrived before MainMenu mounted the dialog callbacks

Even with the handler registered, if the push arrives 700ms before
`MainMenu.wireResumeDialog` runs, the dispatch fires
`mountResumeDialog` which finds `dialogOnResume == null` and warns
"modal mount skipped".

**Fix:** `mountResumeDialog` now queues the payload in
`pendingPayload` and retries via `setTimeout(50ms / 200ms)` until the
dialog callbacks are wired, or until `KEnv.mainRoot` is null (user
navigated away).

### Race 7 (2026-06-25 follow-up) — `applyRestoredWorldAndSync` used SAVED `stats.playerID` instead of CURRENT `ctx.connectionId`

**This was the critical bug that made `phase1` show `Active Players in Data: 2`
but `phase2` after Resume show `Active Players in Data: 0`.**

The original `applyRestoredWorldAndSync` called
`UiSignalRpcHandlers.sendInitialSync(connectionId = stats.playerID, ...)`,
where `stats.playerID` is the WS playerId of the browser that WROTE
the snapshot (e.g. `"kvision-ws-client-1234567890"`). After disconnect
+ a fresh login, the new browser's WS playerId is different. The push
was dispatched to a session that no longer existed, so the new browser
mounted an empty `GameplayUI` even though the server had the right
world.

**Fix:** Signature must be
`suspend fun applyRestoredWorldAndSync(ctx: RpcCallContext, userId: String, path: String)`,
and it must call `sendInitialSync(connectionId = ctx.connectionId, ...)`
(the calling WS). Both call sites (`fresh-restore` and
`race-recovered` branches) updated accordingly.

**Verification:** run the `resume-preserves-round.mjs` probe. The
JSON-encoded world payload written to
`/tmp/autogenesis-proxy/world-payload.json` should contain both
activePlayers names AND the client-side `updateWorldState` log
should show the same count.

## Manual smoke test (after a clean shutdown + start_servers.sh)

1. Open Firefox, navigate to `http://127.0.0.1:8080/`.
2. Click through the loading screen, log in as guest.
3. Click **PLAY**, pick the existing commander (AUongfa834nfa),
   click **Next**, click **Play**.
4. Wait ~5 seconds for a turn to run, then close the tab.
5. Reopen `http://127.0.0.1:8080/`, log in as guest.
6. **Expected:** the ResumeOrNewDialog appears within ~2 seconds
   with text "Saved game found" and the three buttons (Cancel /
   New Game / Resume).
7. Click **Resume**. **Expected:** a "Match Resumed" message box
   appears. Click OK. GameplayUI mounts with "Your Turn To Act"
   visible in the body text.

## Server-extend → main server → client route

When server-extend detects a snapshot:

1. `ResumeAvailabilityPushService.checkAndPush(userId)` fetches the
   record via `VFS.fetchUserRecord`, deserializes the JSON to
   `GameSnapshot`, and — if the snapshot is parseable — opens a
   short-lived WS to the main game server
   (`pushToServer`).
2. It calls the main server's `client.resumeAvailable` RPC with the
   `ResumeAvailabilityNotification` payload (userId, worldRound,
   turnIndex, hasAi, savedAt).
3. The main server's `UiSignalRpcHandlers.notifyResumeAvailable`
   looks up the user's WS session by AccelByte user id
   (`PlayerConnectionManager.findAllSessionsByAccelbyteId`).
4. The browser receives the notification frame,
   `RpcMessageHandler.handle` calls
   `rpcRegistry.dispatchNotification`, which finds the
   `ResumeAvailabilityListener` handler and invokes
   `onResumeAvailableRaw(payload)`.
5. `onResumeAvailableRaw` parses the JSON, logs "notification
   received", and defers `mountResumeDialog(parsed)` via
   `setTimeout(0)` so the DOM call runs after the WS dispatch
   completes.
6. `mountResumeDialog` mounts the `ResumeOrNewDialog` widget in
   `KEnv.mainRoot` with three callbacks wired: `dialogOnResume →
   MainMenu.beginResumeSession`, `dialogOnNewGame →
   MainMenu.openPlayFlow`, `dialogOnCancel → dialog hides itself`.

When the user clicks Resume:

1. `ResumeOrNewDialog.onResume()` → `invokeResumeCallback(payload)`
   → `MainMenu.beginResumeSession()`.
2. In dev: `MatchmakingClient.requestResume()` → `server.restoreRunningGame`
   RPC against the current WS. Returns
   `MatchmakingClient.ResumeOutcome.Restored` on success.
3. `MainMenu.beginResumeSession` shows a "Match Resumed" messageBox; the user clicks OK.
4. The onConfirm handler calls `mountGameplayUI()` which adds
   `GameplayUI` to the appStack and activates it.
5. `GameplayUI.init` triggers the existing `sendInitialSync` path
   (which was already sent in step 2 by the server), so the
   `World` + map pack + history + audio.syncState are all in place.
6. The user is back in the game on the same round, with the same
   world, with the menu music seamlessly transitioned to gameplay
   music via `audio.syncState`.

## The "compileSync UP-TO-DATE" trap when adding JS diagnostics

The `kvisionApp:jsBrowserDevelopmentRun` webpack-dev-server picks up new
JS source via the Gradle `compileSync` task writing to
`build/compileSync/js/main/developmentExecutable/kotlin/*.js`. If you
add a `logInfo("...")` in `sharedModel/.../WebSocketRpcClientJs.kt` and
the diagnostic **doesn't fire** in the browser, check:

1. `grep "your log string" build/compileSync/js/main/developmentExecutable/kotlin/Autogenesis-sharedModel.js` — if 0 hits, the compileSync task is in UP-TO-DATE state and didn't pick up the file change despite `touch`. Force with `./gradlew :kvisionApp:compileKotlinJs --rerun-tasks` (or kill the daemon with `pgrep -af "kotlin.daemon"` and restart).
2. If the string is in the bundle but the log still doesn't fire at runtime, the diagnostic is in a code path that's not being executed. Common cause: `completePayload` is going through the multipart branch (raw contains `"type":"multipart"`) — the diagnostic is BEFORE the multipart check, so multipart frames skip it. For large world-update frames (~110KB), the JS client doesn't chunk, so multipart isn't usually hit. Check by adding a `logInfo` OUTSIDE the `if` block.

## Chunked-frame timing for resume probes (2026-06-25)

When the server sends `sendInitialSync` after a Resume click, it dispatches
four notifications in this order:

1. `ui.setLocalPlayer` — ~5KB, single frame, **synchronous**. Triggers
   `triggerGameStarted()` which mounts `GameplayUI` (~10ms after click).
2. `ui.loadMapPack` — ~8MB, **chunked into ~282 frames of 30KB each**.
   Takes ~12-15s to arrive on localhost.
3. `ui.updateWorld` — ~110KB, **chunked into 4 frames of 30KB each**.
4. `audio.syncState` — small, single frame.

The client-side `MultipartAssembler` joins the chunks back into a
single payload per `messageId`. Only AFTER all chunks of a given
messageId arrive does the dispatcher fire
`UiSignalClientHandlers.handleUpdateWorld` which calls
`GameplayUI.updateWorldState(world)` which sets `globals.World.worldData`.

**Probe pattern that catches wire-level state preservation:**

```js
// 1. Wait for GameplayUI mount (proxy for "triggerGameStarted fired")
await page2.waitForFunction(() => !!document.querySelector('[data-testid="gameplay-ui"]'))

// 2. WAIT ADDITIONAL 20s for chunked-frame pipeline to drain
await page2.waitForTimeout(20_000)

// 3. Capture concrete state — leaderboard ranks/names/VP
const state2 = await page2.evaluate(() => {
    const lb = document.querySelector('.leaderboard, [data-testid="leaderboard"]')
    return { round: parseRound(lb?.innerText), leaderboard: parseLeaderboard(lb?.innerText) }
})

// 4. Assert state2 matches state1 (captured in phase 1)
assert(state1.leaderboard === state2.leaderboard)
```

**Without the 20s wait**, the probe will capture `state2.leaderboard = []`
because the leaderboard widget hasn't been populated yet. The
GameplayUI is mounted, but the world update is still in transit.

**Diagnosis cheat-sheet when `leaderboardPreserved: FAIL`:**

1. **First suspect — probe timing.** Add the 20s wait and re-run. If
   it now passes, you had a timing issue, not a code bug.
2. **Second suspect — server doesn't send chunks.** Check
   `/tmp/autogenesis-proxy/srv.log` for `Chunking large RPC message
   (N bytes) into K chunks for <playerId>`. If you see the message
   but the client never logs the matching `multipart-complete` log,
   the chunks aren't arriving at the client (transport issue).
3. **Third suspect — chunks arrive but don't assemble.** Verify by
   adding a temporary `logInfo("DIAG multipart-complete: ...",
   assembled.length)` right after `assembler.addChunk(multipart)` in
   `WebSocketRpcClientJs.kt` and re-run. If the log fires with a
   non-null `assembled`, the assembly works; if it never fires, the
   chunk ordering or `messageId` is broken.

## "Another agent working on TPipe" hazard

If `./gradlew :server:run` fails with "Detected multiple Kotlin
daemon sessions" or "Could not pack tree ... tree-destinationDirectory",
the TPipe subproject is being concurrently modified by another agent.
Use `./gradlew :server:run --rerun-tasks` to recover, or wait for the
other agent to finish. The `kvisionApp:compileKotlinJs` task is
independent of TPipe and is safe to retry.