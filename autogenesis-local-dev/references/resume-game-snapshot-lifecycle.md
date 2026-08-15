# Running-game Snapshot Lifecycle — Save / Restore / Invalidate

Authoritative reference for what the single-player `running-game`
snapshot does and when each transition fires. Last full audit:
2026-06-27 (BUG 21 + BUG 22 fixes for popup reappearing + music stacking).

## What the snapshot contains

`GameSnapshot` (see `server/src/main/kotlin/gameState/GameSnapshot.kt`)
captures: `world`, `history`, `geopoliticalAssessment`, `playerStats`,
`turnOrderIndex`, `npcInterferenceList`, `lastAnnouncedRound`,
`lastActiveNemesisNames`, `lastDefeatedNemesisNames`, `mapPackName`,
`isSinglePlayer`, `humanPlayerName`. It does NOT save the music state
(see `references/music-state-on-resume.md` for the audio sync story).

## The four trigger paths

| Trigger | Site | Behavior |
|---|---|---|
| PRIMARY session disconnect, `WorldManager.isGameActive=true` AND `WorldManager.history.isNotEmpty()` AND `humanPlayerHasJoinedOnce=true` | `Server.kt:524` (`onDisconnected` lambda) | **Save** via `serializeCurrentWorldSnapshotToUserRecord` |
| PRIMARY session disconnect, any other state (e.g. `isGameActive=false`, `humanPlayerHasJoinedOnce=false`, OR `history.isEmpty()`) | `Server.kt:524` | **No-op** (the previous snapshot — if any — is preserved; new round-1 / turnIndex-0 / historyEntries-0 snapshots MUST NOT be written — see BUG 24) |
| Game ends (win / loss / forced end / surrender that ends the game) | `TurnHarness.evaluateEndGame` / `dispatchForcedGameOver` → `broadcastGameOver` → `clearRunningGameForUser` | **Invalidate** (delete or `consumed`-sentinel) |
| Player clicks "Resume" in ResumeOrNewDialog → server `restoreRunningGame` succeeds | `TurnHarness.restoreWorldFromUserRecord` | **No-op** (snapshot persists, see BUG 21/23 fixes) |
| Explicit "New Game" / `MatchmakingClient.clearRunningGame()` | `GameRestoreRpcHandlers.clearRunningGame` | **Invalidate** |

**`Server.kt:524` is the only path that should ever call `serializeCurrentWorldSnapshotToUserRecord` mid-game.** The
gate `shouldPersistOnDisconnect` (Server.kt:1144) now requires
`historySize > 0` — a round-1 / turnIndex-0 / historyEntries-0
snapshot is meaningless (the user opened the game but never
submitted a turn) and offering it as a Resume is confusing UX
("no data, no player, nothing"). Disconnect-without-playing is best
treated as a cancelled session — the user just clicks PLAY again to
start fresh. See "BUG 24: phantom fresh-game snapshot" below for the
full regression analysis. Resume-click paths do NOT save — they
rehydrate. The save-on-disconnect path is the only "create new
snapshot" trigger.

**`restoreRunningGame` does NOT invalidate.** The next disconnect
saves over the same slot (Server.kt:524 path). User can click
Resume multiple times across multiple browser sessions without
re-playing the full turn pipeline.

## Critical: `hasRunningGame` race-recovery gotcha

`GameRestoreRpcHandlers.hasRunningGame` is NOT a pure VFS lookup. After
the VFS check it falls through to:

```kotlin
// GameRestoreRpcHandlers.kt:122
if (isWorldAlreadyRestoredForUser(userId)) {
    Logger.info(LogCategory.SYSTEM,
        "GameRestoreRpcHandlers.hasRunningGame: user=$userId — auto-restore already applied the snapshot; race-recovered to exists=true (round=${WorldManager.world.roundNumber})")
    return true
}
```

This branch returns `true` even when the VFS snapshot has been deleted
if the in-memory `WorldManager.playerStats` still has an entry for
that user. It exists to handle the race where the auto-restore on connect
has already applied the snapshot but the consumed-sentinel hasn't
landed yet.

**Test implication:** when writing unit tests that assert
`hasRunningGame == false` after a clear, you MUST also clear
`WorldManager.playerStats` and set `WorldManager.isGameActive = false`
to simulate the WS closing after the game ends. Otherwise the test
fails even though the production code is correct.

```kotlin
// After the deletion completes, simulate the WS close.
WorldManager.playerStats.clear()
WorldManager.isGameActive = false
WorldManager.humanPlayerName = ""

val ctx = RpcCallContext(
    connectionId = "test-conn",
    metadata = mapOf("accelbyteId" to userId),
    sender = { _ -> }
)
assertFalse(GameRestoreRpcHandlers.hasRunningGame(ctx))
```

This was caught and fixed during the 2026-06-26 snapshot-deletion task;
the regression test is in
`server/src/test/kotlin/org/ttt/autogenesis/server/TurnHarnessRunningGameTest.kt`
under the comment "Simulate the WS closing after the game ends".

## BUG 21 (2026-06-27) — `notifyResumeAvailable` re-pushed the modal mid-game

User-reported symptom 2026-06-27: "The pop up randomlly keeps
appearing after the player is back in the game." Every SSE reconnect
(login, page reload, WS drop) fires `server-extend`'s
`triggerSseResumePush(accelbyteId)` (at
`server-extend/.../ServerExtend.kt:301`) which sends
`client.resumeAvailable` to the main server, which pushed the modal
notification to the user's WS session regardless of whether the user
was mid-game. The user was forced to dismiss the modal repeatedly.

### The root cause

`UiSignalRpcHandlers.notifyResumeAvailable` (around line 658) had
no guard. It blindly pushed to any session matching the userId. The
push is sourced from `server-extend/.../ServerExtend.kt:268-301`,
which fires `ResumeAvailabilityPushService.checkAndPush(userId)` from
`triggerSseResumePush` on every SSE connect.

The SSE channel reconnects happen frequently:
- Browser page reload / navigation
- WebSocket connection drops (browser sleep, network blip, etc.)
- `kvisionApp/.../Main.kt:160` rebinds both bridges on post-skipLogin

### The fix

`UiSignalRpcHandlers.notifyResumeAvailable` now checks
`WorldManager.isGameActive` first. If a game is active AND the user
has a `playerStats` entry AND `lastRehydratedAccelByteUserId != userId`,
the push is dropped silently:

```kotlin
// UiSignalRpcHandlers.kt:660
if (WorldManager.isGameActive) {
    val humanAlreadyJoined = WorldManager.playerStats.any {
        it.accelByteUserId == userId
    }
    val worldJustRehydratedForThisUser =
        WorldManager.lastRehydratedAccelByteUserId == userId
    if (humanAlreadyJoined && !worldJustRehydratedForThisUser) {
        Logger.info(
            LogCategory.NETWORK,
            "UiSignalRpcHandlers.notifyResumeAvailable: skipped (user=$userId is mid-game; modal would interrupt active session)"
        )
        return
    }
}
```

### Why the "world just rehydrated" check is there

The user is mid-resume exactly when `lastRehydratedAccelByteUserId == userId`.
The push from server-extend fires right after the auto-restore's initial
sync. The modal in this case is the documented race-recovery: the
user can choose to start fresh or reload to re-resume. Dropping this
push would leave the user with no in-game UI to recover from, so
the modal IS fired. The `&& !worldJustRehydratedForThisUser` guard
preserves that exception. The mid-game case is the other branch
(human is in `playerStats`, just-rehydrated flag is NOT set).

### Regression test

Add to `server/src/test/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlersNotifyResumeByAccelbyteIdTest.kt`:

```kotlin
@Test
fun `notifyResumeAvailable is suppressed when the user is mid-game`() {
    // Set up: user has joined a game, world is active.
    val userId = "test-midgame-1234567890"
    val session = sessionWithAccelbyteId(userId)
    sessionManager.register(session)
    WorldManager.isGameActive = true
    WorldManager.playerStats.add(
        PlayerStat(accelByteUserId = userId, playerID = session.playerId)
    )
    WorldManager.lastRehydratedAccelByteUserId = "some-other-user"
    // Send the push.
    val sentMessages = mutableListOf<RpcMessage>()
    val capturingSession = sessionWithAccelbyteId(userId, captureTo = sentMessages)
    sessionManager.register(capturingSession)
    handler.notifyResumeAvailable(buildContext(), ResumeAvailabilityNotification(
        userId = userId, worldRound = 1, turnIndex = 0, hasAi = true, savedAt = "n/a"
    ))
    // Should have been dropped — the capturing session got NOTHING.
    assertEquals(0, sentMessages.size, "mid-game push should be suppressed")
}
```

## BUG 22 (2026-06-27) — `hydratePostRestoreState` used `currentlyPlayingMusicIds=emptyList()` so resume stacked 4 tracks every time

User-reported symptom 2026-06-27: "There is a gigantic delay between
the music starting, and evne the channels seem to have a huge delay
to when they start acutally playing."

### The root cause

`TurnHarness.hydratePostRestoreState` at `TurnHarness.kt:2223` was
hard-coding:

```kotlin
val ctx = org.ttt.autogenesis.audio.TurnContext(
    ...
    currentlyPlayingMusicIds = emptyList()  // BUG
)
```

`MusicSelector.selectForTurn` reads `ctx.currentlyPlayingMusicIds` to
build `decision.toFadeOut` (line 154 of `MusicSelector.kt`):

```kotlin
val decision = MusicDecision(
    toPlay = toPlay,
    toFadeOut = ctx.currentlyPlayingMusicIds,  // empty -> nothing fades
    ...
)
```

Each resume fired `selectForTurn` with `toFadeOut=emptyList()`, so the
client accumulated 4 NEW tracks (drone/melody/rhythm/harmony) on top of
the previous 4. After 4 resumes during testing, `playingIdsBefore`
progressed 0, 4, 8, 12, 16 — 16 simultaneous tracks with each
`fadeInMs=2000ms` (which is 2s of `setTargetAtTime` with a 0.667s
time constant, i.e. ~2s to reach 95% volume per channel). With 16
channels staggered on the AudioContext clock, perceived "delay" is
the total of all those staggered fade-ins.

### The fix

Read the current `AudioManager.playingObjects.values` filtered by
`AudioChannelIds.MUSIC_MASTER_ID`, matching the normal turn path at
`TurnHarness.kt:699`:

```kotlin
val currentlyPlayingMusicIds = org.ttt.autogenesis.server.audio.AudioManager.playingObjects.values
    .filter { it.channelId == org.ttt.autogenesis.audio.AudioChannelIds.MUSIC_MASTER_ID }
    .map { it.id }
val ctx = org.ttt.autogenesis.audio.TurnContext(
    ...
    currentlyPlayingMusicIds = currentlyPlayingMusicIds
)
```

Now the post-resume `selectForTurn` call sends a `toFadeOut` list of
the currently-playing music ids, so the new tracks cross-fade with
the existing ones instead of stacking.

### Where the same `currentlyPlayingMusicIds` pattern appears

The normal turn path at `TurnHarness.kt:699` (the post-turn music
broadcast inside `executeSingleTurn`) uses the exact same pattern.
The resume path was the only place that was hard-coding
`emptyList()`. After the fix, both paths use the same read of
`AudioManager.playingObjects`. When you find a music-broadcast site
that needs the current ids, copy the line from `TurnHarness.kt:699`.

### Regression test

Add to `server/src/test/kotlin/org/ttt/autogenesis/server/audio/MusicSelectorTest.kt` (or a new
`TurnHarnessResumeMusicTest.kt`):

```kotlin
@Test
fun `hydratePostRestoreState includes currently-playing music ids in the TurnContext`() {
    // Pre-populate AudioManager with 4 playing objects (drone/melody/rhythm/harmony)
    AudioManager.playingObjects.clear()
    for (id in listOf("d1", "m1", "r1", "h1")) {
        AudioManager.playingObjects[id] = ScheduledAudio(
            id = id, resourceName = "test", channelId = AudioChannelIds.MUSIC_MASTER_ID,
            volume = 1f, panning = 0f, speed = 1f, loop = true,
            scheduledStartMs = 0, startTimeMs = 0, endTimeMs = null,
            fadeInDurationMs = 0, fadeOutDurationMs = 0
        )
    }
    // Rehydrate. The TurnContext should pass the 4 ids to selectForTurn.
    val ctxCaptor = argumentCaptor<TurnContext>()
    verify { perTurnSelector.selectForTurn(ctxCaptor.capture()) }
    assertEquals(setOf("d1", "m1", "r1", "h1"), ctxCaptor.lastValue.currentlyPlayingMusicIds.toSet())
}
```

The full regression test (10 captures per call site) showed the
problem clearly: 4 resume broadcasts in quick succession during
testing produced 4 music-schedule pushes with `toFadeOut=[]`, each
adding 4 new tracks. After the fix, the same 4 captures produce
4 schedules that properly cross-fade with the existing tracks.

## Pinning the contract

Three unit tests in `TurnHarnessRunningGameTest.kt` pin the truth table:

- `broadcastGameOver in single-player mode invalidates the running-game snapshot`
  — the contract.
- `broadcastGameOver in multiplayer mode does NOT delete the snapshot`
  — gates on `WorldManager.isSinglePlayer`; multi-player DS does not
  touch running-game.
- `serializeCurrentWorldSnapshotToUserRecord preserves the snapshot when called while game is active (mid-game disconnect)`
  — pins the "save does NOT invalidate" half of the contract.

The matching e2e probe is
`kvisionApp-e2e/probes/resume-snapshot-cleared-on-game-over.mjs`
which drives a real surrender → game-over → re-login flow and asserts
no ResumeOrNewDialog appears.

## Surrender UI button labels (drive the e2e probe)

The in-game surrender flow uses these CSS-class hooks (NOT text
matching — the button text varies):

| Step | Selector | Notes |
|---|---|---|
| Open settings | `button.action-button:has-text("SETTINGS")` | Has the fa-cog icon. SettingsWidget uses `position: fixed`; use `dispatchEvent` not Playwright `.click()` (visibility check fails). |
| Click surrender | `button.btn-surrender` | Class lives inside SettingsWidget. |
| Confirm | `button.btn-surrender-confirm` | Labeled "YES, SURRENDER" (not "Yes"). |

The `page.evaluate(() => btn.dispatchEvent(new MouseEvent('click', {bubbles:true})))`
pattern is required because KVision `position:fixed` widgets fail
Playwright's "is element visible" check even when they ARE rendered
and clickable. `click({force:true})` does NOT bypass this — only
`dispatchEvent` does.

## Surrender that does NOT end the game

`TurnHarness.surrenderPlayer` removes the player from the turn order
and releases their tiles, then calls `evaluateEndGame`. If the only
remaining contenders are NPCs (always the case in single-player since
the player is the only human), `evaluateEndGame` triggers
`broadcastGameOver` → snapshot deleted. If the surrender somehow left
other humans alive (not currently possible in single-player but
hypothetical in coop), the snapshot would stay — the next disconnect
would overwrite via the save path. The e2e probe does not exercise
this case (no coop mode exists yet).

## ResumeOrNewDialog Cancel button

`dialogOnCancel = { /* dialog hides itself */ }` (MainMenu.kt:723).
The snapshot is NOT cleared on Cancel. This is intentional: the user's
intended flow is "cancel → start new game → disconnect → snapshot
overwritten by the save path". No additional server code needed for
this case. If a future feature requires Cancel to also delete the
snapshot, add it to `ResumeAvailabilityListener.dialogOnCancel` or
the cancel-button click handler in `ResumeOrNewDialog.kt` — the RPC
`MatchmakingClient.clearRunningGame()` already exists.

## BUG 24 (2026-06-27) — phantom fresh-game snapshot is offered as Resume

User-reported symptom 2026-06-27: "Regression. Now it just does
this. No data, no player, nothing." The Resume button on a saved
session restored a fresh `round=1, turnIndex=0, historyEntries=0`
world with `Main Score: 0`, no narrative, no player data — the
in-game UI rendered but the body had no actual game state.

### The regression chain

1. The previous fix (BUG 23, 2026-06-27) removed
   `invalidateRunningGameRecord(vfs, accelByteUserId)` from the
   resume path. The fix was correct — the user explicitly asked
   "you should be able to retry a restore without needing to burn
   tokens on a full turn redo from scratch." The next disconnect
   overwrites the same CloudSave slot via the save-on-disconnect
   path.
2. But the save-on-disconnect gate
   (`shouldPersistOnDisconnect` at `Server.kt:1144`) only checked
   `isGameActive && humanPlayerHasJoinedOnce && humanAccelByteUserId.isNotBlank()`.
   It did NOT check whether the user had actually submitted a turn.
3. The first time a user opens a game (`humanPlayerHasJoinedOnce` is
   set by `awaitPlayerAction` when the actor is the human), the
   game is at `round=1, turnIndex=0, history=[]`. If the user
   disconnects at this point (close the browser before submitting
   any turn), the save-on-disconnect gate fires, writes a
   `round=1, turnIndex=0, historyEntries=0` snapshot to VFS, and
   the consumed-sentinel isn't written (BUG 23 fix).
4. Next time the user logs in, `hasRunningGame` returns
   `true` (a parseable snapshot exists), the ResumeOrNewDialog
   appears, the user clicks Resume, the server faithfully
   rehydrates the empty world, and the UI shows the GameplayUI
   shell with `Main Score: 0`, no narrative — "no data, no player,
   nothing."

The user read this as a regression because previously the
consumed-sentinel would have hidden the phantom snapshot (BUG 23
was needed because the user was being forced to re-seed after
each reload — but the side effect was that phantom snapshots were
hidden too). Removing the consumed-sentinel exposed the bug in
the save-on-disconnect gate.

### The fix

`shouldPersistOnDisconnect` now also requires
`WorldManager.history.isNotEmpty()`. A round-1 /
turnIndex-0 / historyEntries-0 snapshot is meaningless
("opened-but-didn't-play"); offering it as a Resume is confusing
UX. The user just clicks PLAY again to start fresh.

The new signature:

```kotlin
internal fun shouldPersistOnDisconnect(
    humanAccelByteUserId: String,
    isSinglePlayer: Boolean,
    isGameActive: Boolean,
    humanPlayerHasJoinedOnce: Boolean,
    historySize: Int = 0
): Boolean {
    return isSinglePlayer
        && isGameActive
        && humanPlayerHasJoinedOnce
        && historySize > 0
        && humanAccelByteUserId.isNotBlank()
}
```

Updated test:
`server/src/test/kotlin/org/ttt/autogenesis/server/SaveOnDisconnectGateTest.kt`
adds `shouldPersistOnDisconnect_returns_false_when_history_is_empty`.

### Lesson for future fixes

When **removing a write/invalidate operation** to fix a UX bug (the
"don't burn the saved state" fix), check that the **next write
trigger** still gates correctly. The save-on-disconnect path was
always writing the phantom snapshot; we just hadn't noticed because
the consumed-sentinel was hiding it. Removing the consumed-sentinel
exposed the underlying gate weakness. **The order of operations
matters:** always do the "should I save" gate fix BEFORE the
"should I delete after read" delete fix. The reverse order ships
the regression.

### Critical parallel: never accept an empty round-1 as resumable

The same `historySize > 0` check should also be applied in
`hasRunningGame`'s VFS-snapshot path. A round-1 / history-=0
snapshot is parseable JSON, so it returns `true` from the
VFS-parse branch. If the server-extend push path bypasses the
human-joined check (e.g. the user is on a fresh dev server
without joining the game), the resume dialog offers an empty
state. **Future fix candidate:** in `hasRunningGame`, after
parsing the snapshot, check `snapshot.world.roundNumber > 1 ||
snapshot.history.isNotEmpty()` and return `false` if both are empty.
This is a defense-in-depth filter on the consumer side (the
`shouldPersistOnDisconnect` fix is the producer side). Currently
this only matters if the user has set `AUTOGENESIS_DEBUG_SEED=true`
and pushed a phantom snapshot via the debug endpoint; with normal
gameplay, the producer gate prevents the phantom. Mark as a
hardening TODO if a future regression pops up.

## Quick scan checklist for new resume-flow changes

When reviewing a future patch that touches the resume path, run
these greps in order. Each should land you on the right place to
double-check the change is consistent with the documented contract:

```bash
# 1. The save-on-disconnect path (only "create new snapshot" mid-game).
grep -rn "serializeCurrentWorldSnapshotToUserRecord" server/src/main/kotlin/

# 2. The invalidate paths (only game-over + explicit "New Game" + clearRunningGame).
grep -rn "invalidateRunningGameRecord\|clearRunningGameForUser" server/src/main/kotlin/

# 3. The push source (server-extend fires this on every SSE connect).
grep -rn "checkAndPush\|triggerSseResumePush" server-extend/src/main/kotlin/

# 4. The push dispatch (UI server, has the BUG 21 mid-game guard).
grep -rn "notifyResumeAvailable" server/src/main/kotlin/

# 5. The music replay during hydrate (was BUG 22, fixed in 2026-06-27).
grep -rn "currentlyPlayingMusicIds" server/src/main/kotlin/

# 6. The loop restart after hydrate (was BUG 20, fixed 2026-06-27).
grep -rn "runNextTurn\|hydratePostRestoreState" server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt
```

If any of these surface a code site that touches the snapshot
lifecycle, check the change against the four-row table above. The
contract is: save happens once on disconnect mid-game, invalidate
happens on game-over and explicit clear, and resume click does
NEITHER.
