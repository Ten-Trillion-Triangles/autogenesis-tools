# Save/Restore Game Retest #2 — 2026-06-22 (after second patch round)

**Scope:** Verified the patches for the three bugs found in the first retest (`save-restore-retest-2026-06-22.md`). Patches targeted `WorldManager.kt` (new `isWorldEmpty()` helper), `MapSelectionService.kt` (new `loadBytesByName` with `resource:` prefix stripping), and `TurnHarness.kt` (new `invalidateRunningGameRecord` with delete-then-sentinel fallback).

## Patches Verified Working ✓

**BUG #2 (retest #1) — Consumed-sentinel: FIXED.**
- `TurnHarness.invalidateRunningGameRecord` writes a consumed-sentinel when the AccelByte delete fails with `errorCode 20013`.
- Log evidence:
  ```
  [INFO] [DATABASE]: TurnHarness.invalidateRunningGameRecord: wrote consumed-sentinel for user=004c3eb02c0b4436b41b24d5d670b0e4 (delete failed with: HttpResponseException: { "errorCode": 20013, ... })
  ```
- Before restore: `hasRunningGame` → `True`
- After restore: `hasRunningGame` → `False` ✓
- The `server.clearRunningGame` RPC also works (thin wrapper around the same function).

**BUG #3 (retest #1) — Map pack prefix stripping: FIXED.**
- No more `MapSelectionService.loadBytesByName: no classpath resource for resource:maps/Laurasiagondwana.map` warning in the restore logs.
- The `resource:` prefix is now stripped before classpath lookup in `MapSelectionService.stripResourcePrefix`.

## Still Broken ✗

**BUG #1 (retest #2) — Auto-restore-on-connect: STILL NOT FIXED.**

Root cause: `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:236` gates the entire auto-restore block on `WorldManager.isSinglePlayer`. But `isSinglePlayer` defaults to `false` (`WorldManager.kt:92`) and is only set to `true` in `GameInit.kt:46` during `configurePlayersFromSession` (matchmaking). On a fresh server, `isSinglePlayer` is `false`, so the auto-restore is SKIPPED entirely.

Verified on a fresh server (PID 1710034) with `accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4`:
- `onConnected` fires: `[DEBUG] [NETWORK]: Server: onConnected invocation (playerId=test-r2b-...)`
- NO `Server: Rehydrated` or `Server: Failed to rehydrate` log appears
- `hasRunningGame` returns `True` (snapshot exists) but auto-restore is silently skipped

The `isWorldEmpty()` helper added in this patch round is correct — it properly handles the seed `Player 1` placeholder. But the outer `isSinglePlayer` guard prevents it from ever being called on a fresh server.

**Effect:** The "automatic resume on reconnect after server restart" path is dead. Only the explicit `server.restoreRunningGame` RPC works (which requires the client UI to reach the menu first).

**Fix sketch:** Remove the `if(gameState.WorldManager.isSinglePlayer)` guard from the auto-restore code at `Server.kt:236`. The auto-restore should work for any player with a saved snapshot, not just single-player players. Alternatively, set `isSinglePlayer = true` on server startup for single-player-mode servers, but this is fragile (multiplayer servers shouldn't be single-player).

## Verification Method

Browser login remains broken (KVision virtual DOM not firing handlers — pre-existing). Verified via direct WebSocket RPC using `scripts/ws_rpc_test.py`:

```bash
# 1. Check snapshot exists
python scripts/ws_rpc_test.py server.hasRunningGame --accelbyte-id 004c3eb02c0b4436b41b24d5d670b0e4

# 2. Restore
python scripts/ws_rpc_test.py server.restoreRunningGame --accelbyte-id 004c3eb02c0b4436b41b24d5d670b0e4

# 3. Verify consumed-sentinel
python scripts/ws_rpc_test.py server.hasRunningGame --accelbyte-id 004c3eb02c0b4436b41b24d5d670b0e4
# Result: False
```

## Test Artifacts

- `~/.autogenesis/logs/autogenesis-2026-06-22-153423.log` — main test run
- `~/.autogenesis/logs/server-extend-2026-06-22-153422.log` — server-extend run

## Cleanup

All servers shut down via `fuser 9080/tcp 9091/tcp | xargs -r kill -9` and `fuser 7070/tcp 9092/tcp | xargs -r kill -9` and `fuser 8080/tcp | xargs -r kill -9`. Ports verified free. Gradle daemon left running.

## Summary

| Bug | Status |
|-----|--------|
| Consumed-sentinel (delete permission fallback) | **FIXED** ✓ |
| Map pack `resource:` prefix stripping | **FIXED** ✓ |
| Auto-restore-on-connect (isSinglePlayer gate) | **STILL OPEN** — new root cause: `isSinglePlayer` defaults to `false` |

The save/restore system is close to working end-to-end. The save side is verified, the resume detection works, the consumed-sentinel prevents replay loops, the map pack resolves correctly. Only the auto-trigger on reconnect remains — blocked by the `isSinglePlayer` gate at `Server.kt:236`.