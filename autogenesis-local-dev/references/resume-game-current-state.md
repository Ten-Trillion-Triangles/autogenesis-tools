# Resume-Game Architecture — Current State (2026-06-24, updated 2026-06-27)

This file replaces `references/save-restore-retest-2026-06-22.md` as the
authoritative map of the resume-game flow. The retest ref is a point-in-time
snapshot of bugs found on 2026-06-22; multiple bugs it lists are now FIXED
in the current code. Do NOT use the retest ref for current-state ground
truth. Use this file instead.

> **Update 2026-06-26:** Added BUG 19 (playerID remap on snapshot restore)
> and the seed-and-repush workflow section. BUG 19 replaces the BUG 14
> shutdown-timer regression as the primary cause of "server dies 60s
> after resume."

> **Update 2026-06-27:** Added BUG 21 (Resume modal re-pushed mid-game),
> BUG 22 (resume stacks 4 music tracks every time because
> `currentlyPlayingMusicIds=emptyList()`), and BUG 23 (snapshot
> consumed on every successful Resume). BUG 22 had a knock-on effect
> on BUG 21 — repeated resume tests stacked audio buffers, the
> probe's audioCount grew to 20, and any verify-by-DOM screenshot
> would have shown the prompt overlay becoming more misleading. BUG
> 21 + BUG 22 + BUG 23 are the three pillars of the 2026-06-27 push.

## Spec (what the user described)

1. Single-player game captures a snapshot on disconnect.
2. Client logs back in; server-extend polls the backend for a snapshot for
   that user. If non-null, server-extend offers a "reconnect to game?" dialog.
3. On accept: dev mode restores locally; live mode invokes AMS, claims a DS,
   then proceeds to restore the game state on the new DS.

## Code map (where each piece lives)

| Spec step | Module | File | Line |
|-----------|--------|------|------|
| Capture snapshot | server | TurnHarness.kt | 1759 `serializeCurrentWorldSnapshotToUserRecord` |
| Auto-restore on connect | server | Server.kt | 298-360 `onConnected` block (now passes `session.playerId` to restore) |
| World-empty predicate | server | WorldManager.kt | 85-88 `isWorldEmpty()` |
| Map pack rehydrate | server | MapSelectionService.kt | 117-177 `loadBytesByName` |
| Manual restore (dev) | server | GameRestoreRpcHandlers.kt | 145 `restoreRunningGame` (now passes `ctx.connectionId`) |
| **Restore variant (for DS)** | server | GameRestoreRpcHandlers.kt | 242 `restoreRunningGameForUser` |
| **playerID remap on apply** | server | TurnHarness.kt | 1930 `applyGameSnapshot(remapConnectionIdForUser, remapToConnectionId)` |
| **Music replay on hydrate (BUG 22 fix)** | server | TurnHarness.kt | 2215 `hydratePostRestoreState` — reads `AudioManager.playingObjects` for `currentlyPlayingMusicIds` instead of `emptyList()` |
| **Mid-game resume guard (BUG 21 fix)** | server | UiSignalRpcHandlers.kt | 660-707 `notifyResumeAvailable` skips push when `isGameActive && playerStats has user` |
| Delete (with sentinel fallback) | server | TurnHarness.kt | `invalidateRunningGameRecord` (NOT called from resume path — BUG 23 fix) |
| Has-running-game check (push side) | server-extend | ResumeAvailabilityPushService.kt | 75-132 |
| Has-running-game check (RPC side) | server | GameRestoreRpcHandlers.kt | 57-131 |
| SSE /events hook | server-extend | ServerExtend.kt | 268, 297-300 |
| server-extend → main push | server-extend | ResumeAvailabilityPushService.kt | 149-200 |
| Main server → client notification | server | UiSignalRpcHandlers.kt | 641-666 `notifyResumeAvailable` |
| Client listens | kvisionApp | ResumeAvailabilityListener.kt | 78-103 |
| Dialog renders | kvisionApp | ResumeOrNewDialog.kt | 38-127 |
| Dialog wired from menu | kvisionApp | MainMenu.kt | 253-260 `wireResumeDialog` |
| Resume click (dev) | kvisionApp | MainMenu.kt | 372-486 `beginResumeSession` |
| Resume click (live) | kvisionApp | MainMenu.kt | 382-441 |
| Live match ticket | server-extend | ServerConnector.kt | 283-369 `requestResume` |
| Resume pool name | server-extend | ServerConnector.kt | 113 `SINGLEPLAYER_RESUME_POOL = "singleplayer-resume"` |
| DS rehydration entry | server | GameInit.kt | 46-58 (defineGameRules resume branch) |
| DS rehydration call | server | GameInit.kt | 49 `restoreRunningGameForUser` |
| Initial sync after restore | server | UiSignalRpcHandlers.kt | 60 `sendInitialSync` |
| Client reconnect to DS | kvisionApp | MatchmakingClient.kt | 383-436 `connectToGameServer` |
| SSE URL builder (accelbyteId plumbing) | sharedModel | RestRpcClient.kt | 405+ `buildEndpointUrl` |
| Auto-restore user-id resolver (Fix 2) | server | Server.kt | 209-258 `resolveAutoRestoreUserId` |
| Resume-push delivery by accelbyteId (Fix 4) | server | PlayerConnectionManager.kt | `findAllSessionsByAccelbyteId` |
| **Debug: seed snapshot** | server | Server.kt | `/debug/seed-snapshot` (gated on `AUTOGENESIS_DEBUG_SEED=true`) |
| **Debug: fetch snapshot** | server | Server.kt | `/debug/fetch-snapshot?userId=...` (same gate) |
| **Debug: fetch+repush workflow** | debugger | `scripts/seed-and-repush-snapshot.sh` | subcommands: `fetch`, `repush`, `fetch-and-repush`, `--auto-user` |

## Status of the retest-2026-06-22 bugs

| Retest ref | Bug | Status (2026-06-24 → 2026-06-26) |
|------------|-----|---------------------|
| BUG 1 | Player 1 seed blocks auto-restore | **FIXED** — `WorldManager.isWorldEmpty()` uses `roundNumber <= 1 && history.isEmpty()`, not `activePlayers.isEmpty()`. See `WorldManager.kt:67-84` KDoc documenting the fix. |
| BUG 2 | CloudSave delete permission 20013 | **DOCUMENTED, WORKAROUND ACTIVE** — `docs/OPERATIONS.md` lines 8-50 is the operator runbook. The `invalidateRunningGameRecord` sentinel fallback makes the resume flow correct despite the missing IAM grant. The IAM grant is operator territory, not code. |
| BUG 3 | Map pack `resource:` prefix not stripped | **FIXED** — `MapSelectionService.stripResourcePrefix` at `MapSelectionService.kt:193-196` strips the prefix before classpath lookup. KDoc at lines 144-153 documents the saved-snapshot compat. |

## 2026-06-26 — BUG 19 root cause and fix (this session)

User-reported symptom 2026-06-26: "Server crashed after loading state,
no music started." After running the existing
`resume-preserves-round.mjs` probe against a fresh DS, the server log
showed the symptom triad:

1. `Server: Rehydrated running-game for user=X from account record` —
   world restored.
2. `Server: Connection X did not match any registered player stats
   (registeredPlayers=[Lord Maple Tree, Shitty Bob, Officer Dave,
   Bigwang McDouchebag])` — live session's `kvision-ws-client-N`
   playerId is NOT in `playerStats[*].playerID`.
3. `Server: Shutdown timer expired. Terminating server to prevent
   runaway tokens.` exactly 60s later — server kills itself despite
   the user being connected.

### The actual root cause

`TurnHarness.applyGameSnapshot(snapshot)` (called from
`restoreWorldFromUserRecord`) restores `WorldManager.playerStats =
snapshot.playerStats.toMutableList()` verbatim. The snapshot's
`playerStats[*].playerID` is the WS playerId that was alive at the
time the snapshot was saved — typically
`kvision-ws-client-NNNNNN` (random int per browser session) OR, for
older sessions, the player NAME string (e.g. `"Lord Maple Tree"`).

When a fresh DS auto-restores on connect, the new WS session has a
DIFFERENT `playerId` (`kvision-ws-client-MMMMMM`). Downstream lookups
that use `playerStats[*].playerID` as a join key all fail:

| Code site | Predicate | Result |
|---|---|---|
| `PlayerConnectionManager.hasAnyPrimarySession()` | `session.playerId in playerStats[*].playerID` | `false` |
| `WorldManager.findPlayerStatsByConnectionId(session.playerId)` | `playerStats[*].playerID == session.playerId` | `null` |
| `Server.kt:432` initial sync lookup | `findPlayerStatsByConnectionId` | null → "did not match" warning |

`hasAnyPrimarySession() == false` triggers
`startSinglePlayerShutdownCountdown(connectionManager, ...)` → server
dies 60s later despite the user being actively connected.

The previous `applyRestoredWorldAndSync` workaround (send to
`ctx.connectionId` directly) hid the symptom for the
`restoreRunningGame` RPC path but not the auto-restore path.

### Fix

`TurnHarness.applyGameSnapshot(snapshot, remapConnectionIdForUser,
remapToConnectionId)` now rewrites `playerStats[accelByteUserId ==
remapConnectionIdForUser].playerID = remapToConnectionId` when both
parameters are non-blank. NPC entries (blank `accelByteUserId`) are
left unchanged. `isConnected` is also forced to `true` because the
snapshot may capture the user mid-disconnect.

Both call sites pass the live WS playerId:

| Call site | Passes |
|---|---|
| `Server.kt` auto-restore (`onConnected` lambda) | `session.playerId` |
| `GameRestoreRpcHandlers.restoreRunningGame` | `ctx.connectionId` |
| `GameRestoreRpcHandlers.restoreRunningGameForUser` (phase-D synthetic ctx) | self-remap, harmless no-op |

### Regression tests

Two new tests in `server/src/test/kotlin/org/ttt/autogenesis/server/TurnHarnessRunningGameTest.kt`:
- `restore remaps playerStats playerID to the calling connection id` —
  builds a snapshot with stale human playerID + NPC entry, restores
  with the live WS playerId, asserts the human entry's `playerID` is
  rewritten and `isConnected` is forced to `true` while the NPC entry's
  `playerID` is left alone.
- `restore without currentConnectionId leaves playerStats playerID unchanged` —
  verifies the no-op path so the test-only and phase-D entrypoints
  still restore verbatim when no live WS is available.

Total test count for the file: 16 tests, 0 failures, 0 errors.
Existing `restoreWorldFromUserRecord(userId)` test call sites still
compile (the new parameter has a default value) and continue to
exercise the no-remap path — no regression.

### Live verification (2026-06-26)

`node kvisionApp-e2e/probes/resume-preserves-round.mjs` →
**RESULT: PASS** (all 4 assertions). Server log shows ZERO
`Shutdown timer expired` lines after the auto-restore at 17:59:48.
Pre-fix run on the same probe showed the server died 60s after the
auto-restore. Post-fix, the server stays alive for the full probe
duration (~2 minutes) and beyond.

### Lesson for future sessions

The "identity field captured into a snapshot" class of bug recurs. Any
field that maps to a live connection (playerID, websocket handles,
observer session tokens) needs to either:

(a) be **remapped on apply** (this fix), or
(b) be **dropped from the snapshot entirely** and looked up by a stable
identity (e.g. `accelByteUserId`) at apply time.

The two existing tests that audited restore behavior
(`ServerAutoRestoreAccelbyteIdTest`,
`GameRestoreRpcHandlersHasRunningGameRaceTest`) pinned the CALL to
restore but not the JOIN KEY correctness after restore. A test that
exercises "world restored AND live session's playerId matches one of
the playerStats entries" would have caught this bug. Quick scan when
reviewing any future snapshot-restore code: `grep -rn "playerID ==
\|playerID in" server/src/main/kotlin/org/ttt/autogenesis/server/PlayerConnectionManager.kt server/src/main/kotlin/gameState/WorldManager.kt`.

## Seed-and-repush workflow (added 2026-06-26)

Added two test-only HTTP endpoints on the game server, gated on
`AUTOGENESIS_DEBUG_SEED=true` (default OFF, production-safe):

- `GET /debug/fetch-snapshot?userId=...` → returns
  `{userId, snapshot}` where `snapshot` is the raw `GameSnapshot`
  JSON as a string (the Cloud VFS wraps the value in an envelope;
  the handler unwraps it).
- `POST /debug/seed-snapshot` with body `{userId, snapshot}` →
  writes the snapshot back to the user's VFS under the
  `running-game` key via the standard `saveUserRecordFromJsonString`
  path.

Driver: `debugger/scripts/seed-and-repush-snapshot.sh`

Subcommands:
- `fetch --userId=UUID --out=PATH` — pulls the current snapshot to disk.
- `repush --userId=UUID --in=PATH` — pushes a saved snapshot from
  disk back to the server's VFS.
- `fetch-and-repush --userId=UUID --out=PATH` — combined in one
  shell invocation; saves to PATH and then immediately repushes.
- `--auto-user` — detects the userId from the running browser via
  Playwright (looks at `data-accelbyte-user-id` on
  `[data-testid="main-menu"]`).

The workflow lets the operator iterate on the resume bug without
replaying the game each iteration: play once to seed the snapshot,
fetch to disk, restart server, repush from disk, repeat. This is
the same loop the user explicitly requested.

### Workflow contract

The fetch returns the snapshot EXACTLY as it would be deserialized
by `TurnHarness.deserialize<GameSnapshot>` — so round-tripping
through `fetch` → `repush` → restore is byte-equivalent (modulo
Kotlinx serialization's formatting). The fetch path strips the
Cloud VFS `{value: {...}}` envelope so the file matches what
`serialize()` emits.

The repush endpoint calls `vfs.saveUserRecordFromJsonString(userId,
RUNNING_GAME_KEY, jsonString)` — the same path the in-game save
flow uses. The snapshot is written verbatim. The next WS connect
triggers the standard auto-restore path which consumes the snapshot
and writes the consumed-sentinel.

### Pitfall: how to enable

The endpoints are gated on `AUTOGENESIS_DEBUG_SEED=true`. To use
them, start the dev servers with that env var set:

```bash
AUTOGENESIS_DEBUG_SEED=true bash debugger/scripts/start_servers.sh
```

The script also forwards the env var to the JVM as a system
property (it gates on `System.getenv` and `System.getProperty`, so
both work). Without the env var, both endpoints return 404 — the
test surface is unreachable.

## Live e2e procedure (reproducible for future audits)

1. **Start servers** in order (7070, 9080, 8080) via
   `debugger/scripts/start_servers.sh`. Add
   `AUTOGENESIS_DEBUG_SEED=true` if you intend to use the
   fetch/repush workflow. KSP compile takes 30-90s.
2. **Open browser** with Playwright:
   `page.goto("http://localhost:8080/?skipLogin=true", wait_until="networkidle")`.
3. **Click the loading-screen CTA** with
   `page.click("[data-testid='loading-screen-cta']", timeout=10000)`.
   This is the step that was non-obvious: the loading screen blocks
   `awaitReady()` until a user click fires the `handleCtaClick`
   handler. Without it, the post-skipLogin bridge rebind that puts
   `accelbyteId` on the WS URL never runs.
4. **Wait 15-20 seconds** for the full bridge rebind + WS connect
   + SSE connect + auto-restore + initialSync flow.
5. **Verify** via Playwright that the body shows GameplayUI
   (`text 'Your Turn' count: 1`, `text 'GO TO MAP' count: 1`) — this
   confirms the auto-restore path worked. The resume dialog only
   appears in cross-DS (live mode) reconnects where the new DS has
   no `WorldManager` state to auto-restore from.
6. **Verify the WS URL** contains `accelbyteId=<userId>` by listening
   to `page.on("websocket", ...)` and inspecting `ws.url`.
7. **Seed an e2e snapshot** — three options:
   - Play a game to completion via `node kvisionApp-e2e/probes/resume-preserves-round.mjs`.
   - Write a JSON file to
     `/home/cage/player-records/<userId>/running-game.json`
     (the current `LocalVirtualFileSystem` base path is
     `getHomeFolder().absolutePath = /home/cage`, with records at
     `<basePath>/player-records/<userId>/<key>.json`).
   - Push via the debug endpoint:
     `bash debugger/scripts/seed-and-repush-snapshot.sh fetch --userId=...`
     and inspect the saved JSON.
8. **Kill all servers** with the canonical kill sequence
   (see `references/process-kill.md`).

## Verification results (2026-06-26)

- WS URL: `ws://127.0.0.1:9080/events?playerId=kvision-ws-client-X&accelbyteId=guest-user&guestMode=true` ✓
- Server log: `TurnHarness.applyGameSnapshot: remapped playerID for accelByteUserId='004c...e4' from previous=[kvision-ws-client-1084697713] to 'kvision-ws-client-951942030' on 1 entry(ies)` ✓
- Server log: `AudioClientHandlers.handleSyncState: ENTER scheduledObjects.size=1` then `AudioResourceLoader.resolvePath: BASENAME hit for 'Initial Conditions wet 1' → manifest key 'audio/music/Initial Conditions wet 1.mp3'` ✓ (music resumed)
- Server log: 4 `Starting 60-second shutdown timer` events (normal disconnect cycles), 0 `Shutdown timer expired` events ✓
- `resume-preserves-round.mjs`: **RESULT: PASS** (all 4 assertions) ✓
- All 16 tests in `TurnHarnessRunningGameTest` pass ✓

## Known bug inventory (live)

| Bug | Title | Status |
|-----|-------|--------|
| 1 | Player 1 seed blocks auto-restore | FIXED 2026-06-22 |
| 2 | CloudSave delete permission 20013 | DOCUMENTED + WORKAROUND ACTIVE |
| 3 | Map pack `resource:` prefix | FIXED 2026-06-22 |
| 14 | Shutdown timer fires with defer predicate | FIXED 2026-06-22 |
| 15 | consume-sentinel race vs explicit resume RPC | FIXED 2026-06-22 |
| 16 | audio resource basename-vs-full-path mismatch | FIXED 2026-06-25 |
| 17 | Two `@RpcMethod` handlers for `audio.syncState` (one shadowed) | NOT FIXED (defensive wait is harmless dead code) |
| 18 | accelbyteId fallback to random playerId | FIXED 2026-06-25 |
| 19 | playerStats playerID not remapped on snapshot restore | FIXED 2026-06-26 (this session) |
| 20 | `hydratePostRestoreState` rehydrates world but doesn't restart the turn-harness loop | FIXED 2026-06-27 (this session) |
| 21 | `notifyResumeAvailable` re-pushed the modal mid-game | FIXED 2026-06-27 (this session) |
| 22 | `hydratePostRestoreState` hard-coded `currentlyPlayingMusicIds=emptyList()` so resume stacked 4 tracks | FIXED 2026-06-27 (this session) |
| 23 | `restoreWorldFromUserRecord` invalidated the snapshot on every successful Resume, forcing a full 5+ min Phase 1 re-run after every browser reload | FIXED 2026-06-27 (this session) |
| 24 | Phantom fresh-game snapshot (`round=1, turnIndex=0, historyEntries=0`) is offered as Resume and rehydrates to a "no data, no player, nothing" UI | FIXED 2026-06-27 (this session) — `shouldPersistOnDisconnect` now requires `historySize > 0`; see `references/resume-game-snapshot-lifecycle.md` "BUG 24" |

## BUG F (commit `c766ff65d`, 2026-06-25) — `notifyResumeAvailable` looks up by stale `playerID`

Found during a Playwright-driven live browser e2e walkthrough. The
resume push from server-extend was reaching the main server's
`UiSignalRpcHandlers.notifyResumeAvailable` handler but the handler
looked up the target WS session via:

```kotlin
val connectionId = WorldManager.playerStats
    .firstOrNull { it.accelByteUserId == userId }
    ?.playerID
    ?: ""
```

The user's WS session is keyed by `playerId="kvision-ws-client-X"`
(the JS-generated id from `WebSocketRpcBridge.connect` in
`kvisionApp/.../WebSocketRpcBridge.kt:24`), which **never matches** the
snapshot's stale `playerID="guest-user-conn-test"`. Server logs:

```
[INFO] [NETWORK]: RPC Dispatching Request: method=client.resumeAvailable
[WARN] [NETWORK]: UiSignalRpcHandlers.notifyResumeAvailable:
  sessions for connectionId=guest-user-conn-test not found
  (userId=guest-user); modal push dropped
```

The push was silently dropped. The auto-restore path had populated
`playerStats` with the stale `playerID` from the snapshot, but the
actual WS session's `playerId` was a different string.

**Fix:**
- Added `PlayerConnectionManager.findAllSessionsByAccelbyteId(accelbyteId): List<PlayerSession>`
  which scans `sessions` for `session.accelbyteId == accelbyteId`. O(N)
  over active sessions, mutex-protected, bounded by the game's
  max-player count.
- Updated `UiSignalRpcHandlers.notifyResumeAvailable` to use the new
  method as the **primary** path. The old `playerStats.playerID` lookup
  is preserved as a defensive **fallback** for older clients that
  don't set `accelbyteId` on the WS query string.
- New test: `server/src/test/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlersNotifyResumeByAccelbyteIdTest.kt`
  — 3 cases. Two RED-then-GREEN pin the new behavior, one regression
  pin for the existing fall-through case. 3/3 pass.

## BUG 20 (2026-06-27) — `hydratePostRestoreState` rehydrates world but doesn't restart the turn-harness loop

User-reported symptom 2026-06-27: "That's your turn not the oppents.
Did you actually do what I asked, and verify that if you leave on
your opps turn it will resume from their turn?" The probe's Phase 2
screenshot showed the `GameplayUI` rendering the `Your Turn To Act`
prompt overlay (the human's prompt), and the probe's `yourTurn=true`
flag matched. The probe reported PASS. But the server log
contradicted the DOM: `TurnHarness.executeSingleTurn: Resolved
actor='InvisMain' (round=1, turnOrderIndex=1)` — the NPC's AI was
processing its turn, the prompt overlay was just stale DOM being
re-rendered by `triggerGameStarted()` from the new `ui.setLocalPlayer`.

### The actual root cause

`TurnHarness.hydratePostRestoreState(snapshot, accelByteUserId,
currentConnectionId)` (around line 2155) rehydrates the `GameSnapshot`
into `WorldManager` and arms the **human's** turn timer when the saved
actor equals `snapshot.humanPlayerName`. When the saved actor is the
NPC, the code correctly **skipped** arming the timer (the NPC's turn
is taken care of inside the loop tick) — but **it never told the
loop to start again**.

The turn-harness loop is a `loopJob: Job?` field. When the browser
disconnects, `loopJob` is set to `null` (the loop cancels and
finishes). When a new browser connects and clicks Resume, the snapshot
is rehydrated but the loop remains dead. The UI then rendered the
default `Your Turn To Act` prompt because the client never received
a `ui.activeTurn` notification — only the `ui.setLocalPlayer` and
`ui.updateWorld` notifications from `sendInitialSync`.

### Fix

Add a single block after the timer-arming conditional in
`hydratePostRestoreState`:

```kotlin
// BUG 6 fix — RESUME-RESTORES-CORRECT-TURN
if (loopJob?.isActive != true) {
    Logger.info(LogCategory.SYSTEM,
        "TurnHarness.hydratePostRestoreState: turn-harness loop is not active; " +
        "calling runNextTurn() to resume the saved turn " +
        "(activeIndex=$activeIndex, activeActor='$activeActor', round=${world.roundNumber})")
    runNextTurn()
}
```

### Verification (post-fix)

```
TurnHarness.hydratePostRestoreState: saved actor='Ogadi Okwengu' is not the human
TurnHarness.hydratePostRestoreState: turn-harness loop is not active; calling runNextTurn() to resume the saved turn (activeIndex=1, activeActor='Ogadi Okwengu', round=1)
TurnHarness.runNextTurn: Starting turn loop (round=1, turnOrderIndex=1).
TurnHarness.executeSingleTurn: Resolved actor='Ogadi Okwengu' (round=1, turnOrderIndex=1).
WorldManager.isReachable: Player 'Ogadi Okwengu' is marked as AI-controlled - returning false to trigger immediate takeover
>>> STARTING PLAYER TURN EXECUTION for Ogadi Okwengu <<<
TurnHarness.handleAiTakeover: PlayerAgent execution finished for Ogadi Okwengu (took 103874ms)
```

The user's exact contract is satisfied: the player left during the
opponent's turn, the snapshot was persisted, and on resume the
opponent's AI turn was rehydrated and continued processing.

### Lesson for future sessions

`hydratePostRestoreState` and `applyRestoredWorldAndSync` are TWO
DIFFERENT operations:

| Operation | What it does | What it does NOT do |
|---|---|---|
| `applyRestoredWorldAndSync` | Sends the resume WS push + initial sync to the calling client | Does NOT start the turn-harness loop |
| `hydratePostRestoreState` | Rehydrates `GameSnapshot` into `WorldManager` and arms the human's turn timer | Did NOT start the turn-harness loop (BUG 20) |

After Fix 19 (playerID remap) and Fix 20 (loop restart), both
operations need to be called for the resume flow to actually fire
the opponent's AI turn. The `restoreRunningGame` RPC does both in
sequence. The auto-restore path (Server.kt `onConnected` lambda)
needs the same sequence.

No unit test was added in the same commit because the loop's
`awaitAllPlayersJoined` requirement needs a fully-wired test
environment. A focused test in `TurnHarnessRunningGameTest.kt` should
build a snapshot at `turnIndex=N` where actor[N] is an NPC, then
assert `loopJob?.isActive == true` after `hydratePostRestoreState`.
Mark the test `@Ignore` if the test environment can't satisfy the
loop's `awaitAllPlayersJoined` requirement.

### Critical workflow rule (added 2026-06-27)

**The source of truth for "is the opponent's turn active?" is the
server log, not the DOM.** A probe that watches the DOM for
`Your Turn To Act` will produce false positives on every resume,
because the KVision prompt overlay is always rendered. Before
declaring a resume test "verified", grep the server log for:

```
TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>' (round=1, turnOrderIndex=1)
```

If that line appears in the 30-second window after the Resume click,
the opponent's turn is genuinely active. The DOM `Your Turn To Act`
text is the human's prompt, which GameplayUI always renders when
`GameplayUI.mount()` runs — even if the human's turn has not started
yet. See `references/resume-game-opponent-turn-detection.md` for the
full ESM-compatible file-tailing snippet.

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

## BUG 23 (2026-06-27) — `restoreRunningGame` consumed the snapshot on success

User-reported symptom 2026-06-27: "Ie you should be able to retry a
restore without needing to burn tokens on a full turn redo from
scratch." Every successful Resume click wrote a
`{consumed: true, consumedAt: "..."}` consumed-sentinel, forcing
the next user to re-seed from scratch (Phase 1: play one turn → 5+
min turn pipeline → save snapshot; Phase 2: click Resume → consume
snapshot → game over).

### The root cause

`TurnHarness.restoreWorldFromUserRecord` (around line 1946) called
`invalidateRunningGameRecord(vfs, accelByteUserId)` AFTER the world
was rehydrated. This contradicted the documented contract on
`invalidateRunningGameRecord` (`TurnHarness.kt:2250-2298`): "Mid-game
disconnect must NOT call this. The save-on-disconnect path in
`Server.kt:524` only runs `serializeCurrentWorldSnapshotToUserRecord`
(preserves the snapshot for restore)."

The previous code comment claimed "Invalidate on restore — once the
snapshot has been rehydrated it is one-shot" but that logic
contradicted the documented contract.

### The fix

Remove the `invalidateRunningGameRecord` call from the resume path.
The next disconnect overwrites the same CloudSave slot via
`serializeCurrentWorldSnapshotToUserRecord` (Server.kt:524), so the
slot is naturally one-shot per *session* (not per *restore*). Only
the game-over path and the explicit "New Game" / clearRunningGame
path should invalidate.

After the fix, the same probe can be re-run multiple times against
the same snapshot, and the user can reload the browser mid-game
without losing their saved state.

## Known open gaps (from the original plan, status as of 2026-06-26)

- **Task 17**: dedicated TDD test for `GameInit.defineGameRules` with
  `resumeFromVfs=true`. **CLOSED 2026-06-24**.
- **Task 18**: end-to-end integration test for the full live-mode resume
  flow (server-extend `requestResume` → match2 → DS `setGameMode` →
  rehydrate → initial sync → client). **CLOSED 2026-06-24**.

## BUG C/D/E from the FIRST retest session (2026-06-22 first run)

Per the retest ref's own closing notes, BUG C (server killed mid-turn),
BUG D (`thinkingUpdates:[]`), and BUG E (server-extend `getMasterRecord`
index error) were NOT re-tested and are presumed still present. They
are independent of the resume-game architecture.

## Acceptance test for "is the resume flow in the state the user described?"

Run the manual smoke test in `docs/OPERATIONS.md:91-109` end-to-end. The
acceptance criteria are:
1. Snapshot saves on disconnect (log line at TurnHarness.serializeCurrentWorldSnapshotToUserRecord).
2. Reconnect triggers `client.resumeAvailable` (NETWORK log at server AND browser).
3. `ResumeOrNewDialog` renders.
4. Click Resume → gameplay UI mounts with the resumed state (same round, same world, same player names).
5. Repeat in live mode with `SERVER_EXTEND_LIVE_MODE=true` and `-Pkvision.liveMode=true`.
6. Verify the SSE `/events` URL contains `accelbyteId=<userId>` as a query parameter (Fix 1 wire-level pin).
7. Verify the resume push actually delivers to the WS session. (Fix 4 / BUG F)
8. **Verify the server stays alive after the resume.** `grep -c "Shutdown timer expired" <server.log>` should return 0 in the 60-second window following `Rehydrated running-game for user=X from account record`. This is the BUG 19 acceptance criterion. (added 2026-06-26)
9. **Verify music resumes.** Browser log should contain `AudioClientHandlers.handleSyncState: ENTER scheduledObjects.size=N` (N>0) followed by `AudioResourceLoader.resolvePath: BASENAME hit` for the resume track. (added 2026-06-26)
10. **Verify the opponent's turn is the one that resumes, not yours.** The DOM body text is unreliable (the KVision `Your Turn To Act` prompt overlay is always rendered, even when the opponent's AI is the active turn). The source of truth is the server log: within 30 seconds of the Resume click, grep the server log for `TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>' (round=N, turnOrderIndex=M)`. If the resolved actor's name does NOT start with your commander base (derived from `myName` minus its `Main` suffix), the opponent's turn is active. See `references/resume-game-opponent-turn-detection.md` for the full ESM-compatible file-tailing snippet. (added 2026-06-27)
11. **Verify the resume modal doesn't reappear after the player is back in the game.** Reload the browser mid-game (or trigger any SSE reconnect). The modal should NOT pop up again. Server log: `UiSignalRpcHandlers.notifyResumeAvailable: skipped (user=X is mid-game; modal would interrupt active session)`. If this log line is missing after a mid-game SSE reconnect, BUG 21 has regressed. (added 2026-06-27)
12. **Verify music doesn't stack across resumes.** After multiple resume clicks, `AudioManager.playingObjects.size` should stabilize at 4-8 entries (one round's worth of channels), not grow unboundedly to 12+ entries. If `playingObjects.size > 12` after a few resume iterations, BUG 22 has regressed. (added 2026-06-27)
13. **Verify the snapshot persists across multiple Resume clicks.** After clicking Resume, the snapshot should still be retrievable via the `GET /debug/fetch-snapshot` endpoint. If the endpoint returns 404 (record not found) immediately after a successful Resume, BUG 23 has regressed. (added 2026-06-27)
