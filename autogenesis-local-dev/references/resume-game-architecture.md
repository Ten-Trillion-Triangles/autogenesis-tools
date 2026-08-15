# Resume-game architecture — how snapshot + restore fit together

This is the **architecture-teaching doc** for the single-player resume
flow. It complements the two existing resume-game references:

- `references/resume-game-current-state.md` — bug audit + fix series
  (BUG 1/2/3, BUG F, Fix 1-4). Point-in-time ground truth.
- `references/music-state-on-resume.md` — narrow doc on why music is
  handled by `audio.syncState`, not by `GameSnapshot`.

This file explains **how the pieces fit together** so a future agent
reading any one of them has the surrounding context. All file:line
citations point to current code on `audio-system` (verified 2026-06-25).

## The two scenarios

The resume flow branches on **whether the new WS connection lands on the
same DS that wrote the snapshot, or a different one**:

- **Path A — in-place reconnect (same DS).** Most common in dev. The
  browser disconnects, the game server writes a snapshot, the browser
  reconnects → auto-restore runs silently and the user is back in
  gameplay with no UI prompt.
- **Path B — cross-DS resume (live mode, fresh DS).** The browser
  disconnects from DS #1, the snapshot lives in AccelByte CloudSave,
  the browser opens a fresh session → server-extend polls VFS on SSE
  connect and pushes a `client.resumeAvailable` notification → user
  clicks "Resume" in a modal → server-extend provisions a new DS that
  rehydrates from the snapshot → the browser reconnects to that DS.

Both paths converge on the same storage key, the same `GameSnapshot`
data shape, and the same restore kernel in
`TurnHarness.restoreWorldFromUserRecord`. Branching is in **who triggers
the restore** and **what transport rehydrates it**.

## Snapshot data shape

`server/src/main/kotlin/gameState/GameSnapshot.kt:22-36`:

```kotlin
@Serializable
data class GameSnapshot(
    val world: World,                              // map, players, NPCs
    val history: List<GameHistory>,                // full narrative
    val geopoliticalAssessment: String,           // AI summary
    val playerStats: List<PlayerStats>,
    val turnOrderIndex: Int,                       // position in turn order
    val npcInterferenceList: List<String>,
    val lastAnnouncedRound: Int,
    val lastActiveNemesisNames: Set<String>,
    val lastDefeatedNemesisNames: Set<String>,
    val mapPackName: String,                       // /res path
    val isSinglePlayer: Boolean,
    val humanPlayerName: String,
)
```

Everything to drop the user back into the exact turn they left on.
Music is intentionally NOT in the snapshot — gameplay music rides on
`audio.syncState` which `sendInitialSync` broadcasts on restore (see
`references/music-state-on-resume.md` for why no custom `musicState`
field on `GameSnapshot` is needed).

## Storage

Single source of truth: the **per-user AccelByte CloudSave (or local
VFS) record under the key `"running-game"`**.

Key constant: `sharedModel/src/commonMain/kotlin/structs/storage/RunningGameRecord.kt:14`:

```kotlin
const val RUNNING_GAME_KEY: String = "running-game"
```

VFS abstraction: `server/src/main/kotlin/org/ttt/autogenesis/server/vfs/VirtualFileSystem.kt:120-161`:

```kotlin
fun forUser(userId: String): VirtualFileSystem {
    if (!userId.startsWith("guest") && !userId.startsWith("rest-client")) return current()
    return guestLocalVfs ?: LocalVirtualFileSystem.create(getHomeFolder().absolutePath).also { ... }
}
```

Concretely:

- Cloud mode → AccelByte CloudSave player record `{namespace}/{userId}/running-game`
- Local mode → `<home>/player-records/<userId>/running-game.json`
  (`getHomeFolder().absolutePath = /home/cage` +
  `PLAYER_DIR_NAME = "player-records"` at
  `LocalVirtualFileSystem.kt:24-32, 219-222`)

Every component in the resume flow reads from this exact slot.

## Capture — when the snapshot is written

`server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:465-488`:

```kotlin
if (!hasAnyPrimary) {                        // last browser just left
    val humanUserId = WorldManager.findPlayerFromStats(WorldManager.humanPlayerName)
        ?.accelByteUserId.orEmpty()
    if (humanUserId.isNotBlank() && WorldManager.isGameActive) {
        CoroutineScope(Dispatchers.IO).launch {
            TurnHarness.serializeCurrentWorldSnapshotToUserRecord(humanUserId)
        }
    }
    // ... arm 15s shutdown timer
}
```

`serializeCurrentWorldSnapshotToUserRecord` at `TurnHarness.kt:1759-1807`:

1. `buildCurrentGameSnapshot()` (`:1682-1700`) under `WorldManager.worldMutex`
2. Serializes to JSON
3. `vfs.saveUserRecordFromJsonString(userId, RUNNING_GAME_KEY, json)`
4. Logs round/turnIndex/history count

Best-effort with respect to the shutdown timer — launched on
`Dispatchers.IO` so it doesn't block the 15-second
`startSinglePlayerShutdownCountdown`. A failed save is logged, not fatal.

## Restore kernel — `TurnHarness.restoreWorldFromUserRecord`

`server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt:1830-1922`
is the only function that actually rehydrates state. Every higher-level
restore path calls it.

```
1. vfs = VirtualFileSystemManager.forUser(userId)
2. response = vfs.fetchUserRecord(userId, RUNNING_GAME_KEY)
3. raw JSON → deserialize<GameSnapshot>
4. applyGameSnapshot(snapshot)              ← world + harness state mutation
5. invalidateRunningGameRecord(vfs, userId) ← one-shot TTL
6. return Result.success(true)
```

`applyGameSnapshot` at `TurnHarness.kt:1930-1950` mutates under two
mutexes:

```kotlin
WorldManager.worldMutex.withLock {
    WorldManager.world = snapshot.world
    WorldManager.history = snapshot.history.toMutableList()
    WorldManager.geopoliticalAssessment = snapshot.geopoliticalAssessment
    WorldManager.playerStats = snapshot.playerStats.toMutableList()
    WorldManager.activeMapPackName = snapshot.mapPackName
    WorldManager.isSinglePlayer = snapshot.isSinglePlayer
    WorldManager.humanPlayerName = snapshot.humanPlayerName
}
turnStateLock.withLock {
    turnOrderIndex = snapshot.turnOrderIndex
    npcInterferenceList = snapshot.npcInterferenceList
    lastAnnouncedRound = snapshot.lastAnnouncedRound
    lastActiveNemesisNames = snapshot.lastActiveNemesisNames
    lastDefeatedNemesisNames = snapshot.lastDefeatedNemesisNames
    gameOverDispatched = false
}
```

**One-shot TTL — `invalidateRunningGameRecord` at `:2064-2117`.**
Critical: as soon as the snapshot is applied, the storage slot is
consumed. Tries `vfs.deleteUserRecord(userId, RUNNING_GAME_KEY)` first.
On `errorCode 20013` (CLOUDSAVE:RECORD delete permission not granted on
the admin client — see `docs/OPERATIONS.md`), falls back to writing a
`{"consumed": true, "consumedAt": "..."}` sentinel. The sentinel is
JSON-shaped to deliberately **fail `GameSnapshot` deserialization** so
any future `hasRunningGame` lookup reports "no saved game." The next
disconnect overwrites the slot with a fresh snapshot, so the sentinel is
self-cleaning.

`invalidateRunningGameRecord` is also called by
`TurnHarness.clearRunningGameForUser` (the explicit "New Game" path), so
both flows share the same TTL contract.

## Path A — in-place reconnect (same DS)

Browser WS reconnects to the same game server. Trigger is in
`Server.kt:323-393`:

```kotlin
connectionCoordinator.apply {
    onConnected { session ->
        // ... shutdown-timer bookkeeping ...

        // Auto-restore on connect: rehydrate a saved running-game snapshot for the
        // calling player if the WorldManager is empty and the player has a saved game.
        val humanUserId = resolveAutoRestoreUserId(session)
        if (humanUserId != null) {
            CoroutineScope(Dispatchers.IO).launch {
                TurnHarness.restoreWorldFromUserRecord(humanUserId)
            }
        }

        // Initial Sync for real players
        val stats = gameState.WorldManager.findPlayerStatsByConnectionId(session.playerId)
        if (stats != null) {
            UiSignalRpcHandlers.sendInitialSync(session.playerId, ...)  // World + mapPack + audio.syncState
        }
    }
}
```

**Gating logic — `resolveAutoRestoreUserId` at `Server.kt:239-257`**
(extracted in commit `2f1094c3a` for direct unit-testability). Returns
null — and therefore suppresses the auto-restore — unless ALL THREE
are true:

1. `session.role == SessionRole.PRIMARY` (browser, not Python/CONTROLLER)
2. `WorldManager.isWorldEmpty()` returns true (a non-empty world means
   a game is in progress — never clobber it)
3. An AccelByte user id can be resolved, in priority order:
   - `session.accelbyteId` (set from the WS query string — Fix 1
     plumbing at `sharedModel/.../RestRpcClient.kt:415+` and
     `RestRpcBridgeJs.kt:77`)
   - `playerStats[accelByteUserId]` for the connection id
   - `humanPlayerName` lookup as last resort

After the async restore, `Server.kt:404-411` calls
`UiSignalRpcHandlers.sendInitialSync(...)` which broadcasts the entire
World + map pack bytes + history + `audio.syncState` over WS. The
client's `sendInitialSync` handler mounts `GameplayUI` and the user is
back in the round they left. **No UI prompt. No modal.** The auto-restore
path is silent.

The auto-restore happens concurrently with the initial sync (both fire
in `onConnected`). Race-recovery handles the inverse case (modal click
arriving after auto-restore already won) — see `Race recovery` below.

## Path B — cross-DS resume (live mode, fresh DS)

When the player reconnects to a **different** DS — old one shut down
after disconnect, or live mode provisions a new DS via match2. A
server-pushed modal is offered.

### B.a — server-extend polls VFS on SSE connect

`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:290-301`:

```kotlin
// Resume-game availability push (Phase B): if the SSE URL carried
// an accelbyteId, fire a one-shot check for that user's saved
// running-game record.
triggerSseResumePush(accelbyteId)
```

Gated on `accelbyteId` being non-blank in the SSE URL — exactly the
wire-level contract that Fix 1 added (`RestRpcClient.kt:415+`). Without
it the SSE handler reads `accelbyteId=""` and silently no-ops, and the
user never sees the modal.

### B.b — ResumeAvailabilityPushService

`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ResumeAvailabilityPushService.kt:75-132`:

```kotlin
val vfs = VirtualFileSystemManager.forUser(userId)
val fetch = vfs.fetchUserRecord(userId, RUNNING_GAME_KEY)
// ... deserialize<GameSnapshot>(jsonString) ...
if (snapshot == null) return  // consumed sentinel or empty
val notification = ResumeAvailabilityNotification(
    userId, snapshot.world.roundNumber, turnIndex, hasAi, savedAt
)
pushToMainServer(userId, notification)
```

`pushToMainServer` (`:149-200`) opens a short-lived WS to the main
server (URL from `serverExtend.mainServerWsUrl` JVM property →
`SERVER_EXTEND_MAIN_SERVER_WS_URL` env var → `ws://127.0.0.1:9080` dev
default) and invokes the `client.resumeAvailable` RPC.

### B.c — Main server routes the push to the right browser session

`server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt:642-702`:

```kotlin
@RpcMethod("client.resumeAvailable", RpcDirection.SERVER)
suspend fun notifyResumeAvailable(ctx: RpcCallContext, payload: ResumeAvailabilityNotification) {
    val userId = payload.userId
    // Primary lookup: by AccelByte id (the live WS session's stable key from handshake time)
    val sessions = connectionManager?.findAllSessionsByAccelbyteId(userId) ?: emptyList()
    if (sessions.isNotEmpty()) {
        // ... sendRpcMessage(notification) on each ...
        return
    }
    // Defensive fallback: scan playerStats for a matching entry by accelByteUserId
    val fallbackConnectionId = WorldManager.playerStats
        .firstOrNull { it.accelByteUserId == userId }?.playerID ?: ""
    // ...
}
```

**BUG F fix** from commit `c766ff65d` (2026-06-25). Previous code
looked up by `playerStats[accelByteUserId == userId].playerID`, which
was a stale `"guest-user-conn-test"`-style value that never matched
the live WS session's JS-generated `playerId="kvision-ws-client-X"`.
The fix added `PlayerConnectionManager.findAllSessionsByAccelbyteId`
(O(N) scan over the active session map) and made it the primary path.
The old path stays as defensive fallback for clients predating Fix 1.

### B.d — Client receives the push, mounts the dialog

`kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/ResumeAvailabilityListener.kt:78-165`:

```kotlin
fun register() {
    if (registered) return
    registered = true
    MainScope().launch {
        WebSocketRpcBridge.waitForConnection()
        WebSocketRpcBridge.registerHandlers {
            register("client.resumeAvailable", RpcDirection.CLIENT) { ctx, payload ->
                onResumeAvailableRaw(payload); null
            }
        }
    }
}
```

`onResumeAvailableRaw` (`:105-127`) parses, logs, defers
`mountResumeDialog` to next tick (never inside WS frame dispatch).
`mountResumeDialog` (`:134-165`) instantiates `ResumeOrNewDialog` with
three callbacks. The callbacks are bound by
`MainMenu.wireResumeDialog` at
`kvisionApp/src/jsMain/kotlin/ui/MainMenu.kt:253-260`:

```kotlin
private fun wireResumeDialog() {
    ResumeAvailabilityListener.dialogOnResume = { _ -> beginResumeSession() }
    ResumeAvailabilityListener.dialogOnNewGame = { openPlayFlow() }
    ResumeAvailabilityListener.dialogOnCancel = { /* dialog hides itself */ }
    ResumeAvailabilityListener.register()
}
```

### B.e — User clicks "Resume" → `beginResumeSession`

`MainMenu.kt:383-486` branches on `globals.LiveMode.liveMode`:

**Live mode branch (`:392-452`):**
```kotlin
val liveTicket = MatchmakingClient.requestResumeLive()   // server.extend.requestResume RPC
MatchmakingClient.connectToGameServer(liveTicket.serverUrl)  // WS reconnect to new DS
```

`MatchmakingClient.connectToGameServer(serverUrl)`
(`kvisionApp/.../ui/MatchmakingClient.kt:383-436`) closes the existing
WS, opens a fresh one to `ws://<serverUrl>/events?accelbyteId=<userId>`,
and waits up to `CONNECT_TIMEOUT_MS` for `isSessionReady`. Once ready,
`mountGameplayUI()` is called.

**Dev mode branch (`:454-484`):**
```kotlin
val outcome = MatchmakingClient.requestResume()           // server.restoreRunningGame RPC
when (outcome) {
    MatchmakingClient.ResumeOutcome.Restored   -> mount gameplay UI
    MatchmakingClient.ResumeOutcome.NoneSaved  -> message "No Saved Game"
    MatchmakingClient.ResumeOutcome.Failed(_)  -> message "Failed to resume"
}
```

`MatchmakingClient.requestResume` calls `server.restoreRunningGame`
directly against the current WS server (same DS in dev), which in turn
calls `GameRestoreRpcHandlers.restoreRunningGame` →
`TurnHarness.restoreWorldFromUserRecord` →
`applyRestoredWorldAndSync` (`:198-229`) →
`UiSignalRpcHandlers.sendInitialSync` to the calling connection. Same
effect as Path A but driven by an explicit user click.

### B.f — Live-mode `requestResume` provisions the DS

`server-extend/src/main/kotlin/matchmaking/ServerConnector.kt:283-369`:

```kotlin
@RpcMethod("server.extend.requestResume", RpcDirection.SERVER)
suspend fun requestResume(context: RpcCallContext, request: GameRequest): GameTicket {
    if (ExtendConfig.debugMode) {
        // Dev: build a local GameSessionStatus with resumeFromVfs=true,
        // notifyGameServer -> GameInit.defineGameRules on the local DS, return
        // ticket pointing at ws://127.0.0.1:9080
    }
    // Live: executeLiveMatchmaking(matchPool = SINGLEPLAYER_RESUME_POOL,
    //                              resumeFromVfs = true, resumeUserId = accelByteId)
    // -> claims a free DS, GameSessionStatus carries resumeFromVfs=true,
    // notifyGameServer sends server.setGameMode to that DS, return ticket
    // with the DS's serverUrl
}
```

`SINGLEPLAYER_RESUME_POOL = "singleplayer-resume"`
(`ServerConnector.kt:113`) keeps resume tickets in their own match
pool so they don't compete with normal single-player matches for DS
slots.

### B.g — DS rehydrates on `setGameMode`

`server/src/main/kotlin/gameInit/GameInit.kt:35-58`:

```kotlin
@RpcMethod("server.setGameMode", RpcDirection.SERVER)
suspend fun defineGameRules(context: RpcCallContext, sessionData: GameSessionStatus): Boolean {
    // Phase D (resume-game-architecture): if the incoming session is a resume
    // (resumeFromVfs=true), rehydrate the saved snapshot for resumeUserId
    // BEFORE the fresh-state reset below. The reset wipes WorldManager, so
    // the resume must run first.
    if (sessionData.resumeFromVfs && sessionData.resumeUserId.isNotBlank()) {
        val resumed = GameRestoreRpcHandlers.restoreRunningGameForUser(sessionData.resumeUserId)
        // ...
    }
    TurnHarness.resetState()  // wipes the just-rehydrated state if order is wrong
    // ...
}
```

**Call order matters**: rehydrate FIRST, then `TurnHarness.resetState()`.
The reset wipes `WorldManager`, so the snapshot must be applied before
the reset or it would be immediately clobbered.
`restoreRunningGameForUser` (`:242-257`) is the `userId`-keyed variant
of `restoreRunningGame` — same body but builds a synthetic
`RpcCallContext` because the bootstrap doesn't have a calling WS
connection.

After rehydration the new DS is in the resumed state. The player's WS
reconnect (from step B.e) triggers `onConnected` →
`resolveAutoRestoreUserId` returns null (world is non-empty,
`WorldManager.isWorldEmpty()` returns false) → standard `sendInitialSync`
delivers the World + mapPack bytes → the user is in gameplay.

## Race recovery

`GameRestoreRpcHandlers.restoreRunningGame` at `:160-184` handles the
case where the auto-restore on connect and the explicit Resume click
race against each other on the same WS connect:

```kotlin
val restored = TurnHarness.restoreWorldFromUserRecord(userId)
val success = restored.getOrDefault(false)
if (success) return applyRestoredWorldAndSync(userId, "fresh-restore")

// Race recovery: auto-restore on connect already applied the snapshot and
// wrote the consumed-sentinel. Detect that via WorldManager predicates.
val raceRecovered = isWorldAlreadyRestoredForUser(userId)
if (raceRecovered) return applyRestoredWorldAndSync(userId, "race-recovered")
```

`isWorldAlreadyRestoredForUser` (`:268-275`):

```kotlin
if (WorldManager.isWorldEmpty()) return false
return WorldManager.playerStats.any { it.accelByteUserId == userId }
```

The second `sendInitialSync` push is idempotent: the same world state
is re-broadcast, the client de-dupes on round number, and the modal
closes cleanly.

Mirrored in `hasRunningGame` (`:117-128`) so the modal renders even
when the snapshot has already been auto-applied but the consumed
sentinel is sitting in VFS.

## End-to-end summary

```
SHARED KERNEL
=============
snapshot        gameState/GameSnapshot.kt:22-36       (12 fields)
storage key     sharedModel/.../RunningGameRecord.kt:14  "running-game"
storage path    vfs/VirtualFileSystem.kt + LocalVirtualFileSystem.kt
                  local: <home>/player-records/<userId>/running-game.json
                  cloud: AccelByte CloudSave player record
serialize      server/.../TurnHarness.kt:1759         serializeCurrentWorldSnapshotToUserRecord
restore        server/.../TurnHarness.kt:1830         restoreWorldFromUserRecord
                  → applyGameSnapshot (TurnHarness.kt:1930)
                  → invalidateRunningGameRecord (TurnHarness.kt:2064)

PATH A — IN-PLACE RECONNECT (SAME DS)
======================================
disconnect  →  Server.kt:465-488  serializeCurrentWorldSnapshotToUserRecord
reconnect   →  Server.kt:323-393  onConnected
                → resolveAutoRestoreUserId  (Server.kt:239)
                  gates: PRIMARY role, world empty, accelbyteId resolvable
                → restoreWorldFromUserRecord  on Dispatchers.IO
                → sendInitialSync  (Server.kt:404)
result      →  user is back in gameplay, no UI prompt

PATH B — CROSS-DS RESUME (LIVE MODE)
====================================
disconnect  →  snapshot written to VFS (same as Path A)
new SSE     →  ServerExtend.kt:290-301  triggerSseResumePush(accelbyteId)
              ResumeAvailabilityPushService.kt:75-132
                fetch + deserialize GameSnapshot
                open short-lived WS to main server
                invoke client.resumeAvailable
              UiSignalRpcHandlers.kt:642-702
                lookup session by accelbyteId (BUG F fix)
                sendRpcMessage(client.resumeAvailable, payload)
modal       →  ResumeAvailabilityListener.kt:78-165
                onResumeAvailableRaw → mountResumeDialog → ResumeOrNewDialog
user clicks →  MainMenu.kt:383  beginResumeSession
live        →  requestResume → ServerConnector.kt:283
                build SINGLEPLAYER_RESUME_POOL match2 ticket
                notifyGameServer → GameInit.defineGameRules (GameInit.kt:35)
                  rehydrate from VFS FIRST, then resetState
              MatchmakingClient.connectToGameServer(ticket.serverUrl)
                reconnects WS to the resumed DS
              new DS's onConnected → world non-empty → sendInitialSync
dev         →  server.restoreRunningGame RPC against current DS
              GameRestoreRpcHandlers → restoreWorldFromUserRecord
              applyRestoredWorldAndSync → sendInitialSync
```

## Design choices worth knowing

**Snapshot is one-shot (TTL on apply).** `invalidateRunningGameRecord`
ensures you can never accidentally replay a stale snapshot. The
`consumed` sentinel fallback exists because the production CloudSave
admin client lacks the delete permission — the sentinel is shaped to
deliberately fail `GameSnapshot` deserialization so the rest of the
system treats it identically to a deletion.

**Auto-restore is intentionally outside the `isSinglePlayer` gate.**
`Server.kt:351-358` calls this out: the matchmaker sets
`isSinglePlayer=true` during `GameInit.configurePlayersFromSession`,
which only runs AFTER the player reconnects to a fresh DS — but
auto-restore needs to fire ON that reconnect, BEFORE the matchmaker
sets the flag. Putting auto-restore inside the `isSinglePlayer` guard
was a previous bug that meant the very first connect after a restart
never auto-restored.

**The server is the source of truth for "is there a saved game?"**
Path A's silent auto-restore and Path B's server-pushed modal both
read from the same VFS slot. The client never makes a `hasRunningGame`
poll in the live flow — that was a Phase A pull pattern
(`MatchmakingClient.hasRunningGame`) that raced the auto-restore and
was removed. `GameRestoreRpcHandlers.hasRunningGame` is still wired for
the dev-mode-only RPC fallback but is not on the modal path anymore.

**Three independent ways to compute `accelbyteId`.** `Server.kt:252-255`
and `GameRestoreRpcHandlers.resolveHumanUserId:316-330` both implement
the same priority chain — query-string metadata, playerStats by
connectionId, humanPlayerName lookup. This redundancy is defensive: any
single source can be missing (old clients pre-Fix 1 don't carry
accelbyteId on the query string; playerStats is only populated after
the matchmaker runs; humanPlayerName may not be set on a fresh DS) and
at least one will resolve. Fix 1 (commit `f16987684`) made the
query-string path the common case; Fix 4 (BUG F, commit `c766ff65d`)
made sure server-extend's push reaches the right session by looking up
via accelbyteId rather than via the stale `playerStats.playerID`.

## Where the fixes live

See `references/resume-game-current-state.md` for the four-fix series
(Fix 1 accelbyteId plumbing, Fix 2 auto-restore test surface, Fix 3
music-state regression pin, Fix 4 BUG F) and the BUG F discovery
walkthrough. The audit doc is the authoritative source for "what
changed, when, why" — this file is the authoritative source for "how
the architecture works end-to-end right now."