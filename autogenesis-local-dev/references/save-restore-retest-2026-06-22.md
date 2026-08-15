# Save/Restore Game Retest — 2026-06-22 (after patches)

**Scope:** Verified the patches to the single-player save/restore system after the first session's bug report. Patches targeted `Server.kt` (accelbyteId propagation + auto-restore + disconnect-save deferral), `TurnHarness.kt` (public `serializeCurrentWorldSnapshotToUserRecord` / `restoreWorldFromUserRecord` + `buildCurrentGameSnapshot` helper), and the new `GameRestoreRpcHandlers.kt`.

## Patches Verified Working ✓

**BUG A from first session (RpcCallContext missing accelbyteId) — FIXED.**
- `server.hasRunningGame` now returns `true` on a fresh server when a snapshot exists.
- Verified via direct WebSocket RPC at `ws://127.0.0.1:9080/events?accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4`:
  ```
  === Sent server.hasRunningGame ===
  *** hasRunningGame result: True ***
  ```
- `GameRestoreRpcHandlers.resolveHumanUserId` at `server/src/main/kotlin/org/ttt/autogenesis/server/GameRestoreRpcHandlers.kt:201-204` now checks `ctx.metadata["accelbyteId"]` FIRST. The metadata is populated by `Server.kt:619-637` inside `handleFrame`.

**BUG B from first session (auto-restore-on-reconnect) — PARTIALLY FIXED.**
- `server.restoreRunningGame` now rehydrates the world state correctly:
  ```
  [INFO] [DATABASE]: TurnHarness: Rehydrated running-game snapshot for user=004c3eb02c0b4436b41b24d5d670b0e4 (round=1, turnIndex=0, historyEntries=0)
  [INFO] [SYSTEM]: GameRestoreRpcHandlers.restoreRunningGame: user=004c3eb02c0b4436b41b24d5d670b0e4 resumed round=1
  ```
- BUT: the automatic on-connect path (in `onConnected`) does NOT fire — see BUG 1 below.

## Three New Bugs Found ✗

**BUG 1 (CRITICAL) — Auto-restore-on-connect never fires on a fresh server.**

`server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:194-199` seeds a default `Player 1` into `WorldManager.world.activePlayers` during startup:
```kotlin
if(gameState.WorldManager.world.activePlayers.isEmpty())
{
    Logger.info(LogCategory.GENERAL, "Seeding default 'Player 1'")
    gameState.WorldManager.world.activePlayers.add(structs.Player(name = "Player 1"))
}
```

The auto-restore guard at `Server.kt:251-253` then rejects every connection:
```kotlin
val worldIsEmpty = gameState.WorldManager.world.activePlayers.isEmpty() &&
        gameState.WorldManager.world.roundNumber <= 1 &&
        gameState.WorldManager.history.isEmpty()
```

`activePlayers.isEmpty()` is **always false** because of the seed. Verified: on a fresh server, connected with `accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4`, NO `Server: Rehydrated` or `Server: Failed to rehydrate` log appeared. `hasRunningGame` returned `true` (snapshot exists) but auto-restore was silently skipped.

**Effect:** The "automatic resume on reconnect after server restart" path is dead. Only the explicit `server.restoreRunningGame` RPC from the client UI works.

**Fix sketch:** Either drop the seed (and let `activePlayers` actually be empty until matchmaking runs), or change the guard to `roundNumber == 0 && history.isEmpty()` (drop the `activePlayers.isEmpty()` check), or add a `WorldManager.isWorldEmpty()` helper that knows about the seed player.

**BUG 2 (CRITICAL) — Delete-on-restore fails with AccelByte permission error.**

`TurnHarness.restoreWorldFromUserRecord` calls `vfs.deleteUserRecord(accelByteUserId, RUNNING_GAME_KEY)` after a successful restore. This fails:
```
[ERROR] [DATABASE]: ❌ CloudVFS.deleteUserRecord [userId=004c3eb02c0b4436b41b24d5d670b0e4 key=running-game]: {
  "errorCode": 20013,
  "errorMessage": "access forbidden: insufficient permissions",
  "requiredPermission": {
    "resource": "ADMIN:NAMESPACE:{namespace}:USER:{userId}:CLOUDSAVE:RECORD",
    "action": 8
  }
}
[WARN] [DATABASE]: TurnHarness.restoreWorldFromUserRecord: failed to delete running-game for user=004c3eb02c0b4436b41b24d5d670b0e4 after restore
```

Verified: `hasRunningGame` returns `true` BEFORE and AFTER `restoreRunningGame` — the snapshot is never deleted.

**Asymmetric permissions:** The server CAN write user records (the previous session's save worked) but CANNOT delete them. `action: 8` is DELETE. The AccelByte client in `server/accelbyte.local.properties` needs the `CLOUDSAVE:RECORD` delete permission granted on the admin role, OR the delete path needs to use the user's own OAuth token instead of the admin client_credentials token.

**Effect:** Every reconnect replays the same restore. The `ResumeOrNewDialog` in the UI will always offer "Resume" even after a successful resume. No way to clear the stale snapshot short of a manual `server.clearRunningGame` call or a direct AccelByte API call.

**BUG 3 (HIGH) — Map pack bytes not resolved after restore.**

```
[WARN] [GENERAL]: MapSelectionService.loadBytesByName: no classpath resource for resource:maps/Laurasiagondwana.map
[WARN] [SYSTEM]: TurnHarness.applyGameSnapshot: could not resolve map pack bytes for name='resource:maps/Laurasiagondwana.map'; UI map render will be missing until the pack is restored.
```

The saved snapshot stores the map pack name as `resource:maps/Laurasiagondwana.map`, but `MapSelectionService.loadBytesByName` can't find it. World state rehydrates (round, playerStats, history) but the map render will be blank.

**Effect:** A resumed game will have the right numbers (round, territories, resources) but no visible map. The player will see a dark void where the map should be (this is the same "dark void" symptom from BUG #7 in the bug-hunt history, but triggered by restore rather than initial render).

**Fix sketch:** Normalize the map pack name before save (strip `resource:maps/` prefix and `.map` suffix), or extend `MapSelectionService.loadBytesByName` to strip the prefix before lookup.

## New Technique: Direct WebSocket RPC Testing

Browser login was broken (KVision virtual DOM not firing handlers — pre-existing, documented in the skill root). Worked around by bypassing the browser UI entirely with a Python WebSocket client. The pattern:

1. Open a raw WebSocket to `ws://127.0.0.1:9080/events` with query params:
   `playerId=<unique>&accelbyteId=<accelbyte-id>&guestMode=false&role=PRIMARY`
2. Drain initial frames (CONNECTED notification + first ping). **CRITICAL: auto-respond to `client.pong` with a matching `id`** — see `references/dual-control-architecture.md` for why.
3. Send `{"type":"request","id":"<id>","method":"<method>","params":{...}}`
4. Drain responses, looking for the matching `id`.

The reusable script is at `scripts/ws_rpc_test.py`. Usage:
```bash
python scripts/ws_rpc_test.py server.hasRunningGame
python scripts/ws_rpc_test.py server.restoreRunningGame
python scripts/ws_rpc_test.py server.hasRunningGame --accelbyte-id 004c3eb02c0b4436b41b24d5d670b0e4
```

This script is the fastest path to verifying server-side code without a working browser UI. Use it whenever the browser is stuck and you need to confirm a server fix actually works.

## Test Artifacts

- `~/.autogenesis/logs/autogenesis-2026-06-22-140812.log` — fresh server run for auto-restore test (BUG 1 confirmed)
- `~/.autogenesis/logs/autogenesis-2026-06-22-140056.log` — first run, hasRunningGame + restoreRunningGame verified (BUG 2, 3 confirmed)
- `~/.autogenesis/logs/browser-2026-06-22-140117.log` — browser log, shows login click did not fire KVision handler

## Cleanup

All servers shut down via `fuser 9080/tcp 9091/tcp | xargs -r kill -9` and `fuser 7070/tcp 9092/tcp | xargs -r kill -9` and `fuser 8080/tcp | xargs -r kill -9`. Ports verified free. Gradle daemon (PID 1639538) left running.

## BUG C/D/E from first session — Still Present

The first session also found BUG C (server killed mid-turn), BUG D (`thinkingUpdates:[]`), and BUG E (server-extend `getMasterRecord` index error). These were not re-tested in this session and are presumed still present — they are independent code paths that the patches did not touch.