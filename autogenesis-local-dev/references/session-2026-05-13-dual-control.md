# Dual-Control Test Session — 2026-05-13

## Goal
Full round of gameplay via dual-control: Python controller drives gameplay, browser receives game state via shared `playerId`, Lord Maple Tree visible in browser.

## Server Startup
```
server-extend → :server:run → webpack → Python controller
```

### Ports confirmed clear
```bash
ss -tlnp | grep -E "7070|7075|8000|8080|9080"
# → all empty
```

### Startup sequence
1. `./gradlew :server-extend:run --no-daemon &` — server-extend claims 7070 after ~55s
2. `./gradlew :server:run --no-daemon &` — game server claims 9080 after ~100s (TPipe compiles on first run)
3. `./gradlew runKvisionNoHotReload --no-daemon &` — webpack claims 8080 after ~60s
4. Python controller started with `--no-ui` mode

### Python venv setup (this system)
```bash
uv venv /tmp/autogenesis-dev --python /home/linuxbrew/.linuxbrew/bin/python3.13
uv pip install --python /tmp/autogenesis-dev playwright websocket-client requests
/tmp/autogenesis-dev/bin/python -m playwright install chromium
```

Note: `stdbuf` not available on this system — controller runs without it.

## Dual-Control Setup
Python controller generates playerId: `lord-1778709764713-631087`

Browser navigated to:
```
http://127.0.0.1:8080/?skipLogin=true&playerId=lord-1778709764713-631087
```

## What Worked
- server-extend startup (port 7070) ✓
- Game server startup (port 9080) ✓
- Python matchmaking (`session.ready` detected, `POST /rpc` returned 202) ✓
- Python turn detection (`ui.setResolutionStep: START "It is Lord Maple Tree's turn"`) ✓
- Python `SHOW_MAP` signal sent to debug signal server (port 7075) ✓
- Browser connecting with matching `?playerId=` ✓
- Browser receiving `ui.updateTurnTimer` ticks (game state flowing via WebSocket) ✓
- Browser briefly showing "Your Turn To Act" + gameplay UI (GameplayUI visible) ✓

## What Failed
- **"Your Turn To Act" disappeared** — debug signal was auto-cleared before browser polled; `triggerGameStarted()` never called → browser reverted
- **Server shut down prematurely** — browser WebSocket dropped → `hasAnyPrimarySession()=FALSE` → 15s shutdown timer fired despite CONTROLLER session still alive
- **Dark void map** — map area not rendered (known bug, separate from dual-control issue)

## Root Cause Analysis

### Shutdown timeline (UTC)
```
22:02:45.160  TurnHarness: Round 1 started. Turn order: Lord Maple Tree, Quag, Invis, Bigwang
22:02:45.182  TurnHarness: broadcasting ResolutionStep: START, "It is Lord Maple Tree's turn"
22:02:45.186  TurnHarness: awaitPlayerAction() for Lord Maple Tree — reachable, timer started (300s)
22:02:55.240  Controller sends GAME_STARTED:LordMapleTree:3 to debug signal server
22:02:55.233  Browser WS connects — 10 seconds late
22:02:55.184  ui.setResolutionStep: START broadcast — received by browser
22:02:55.240  Controller sends SHOW_MAP
22:03:05+     Browser receives ui.updateTurnTimer ticks — game state IS flowing
22:03:11.249  Browser WS drops (connection closed)
22:03:11.250  hasAnyPrimarySession()=FALSE — 15s shutdown timer starts
22:03:26     Server shuts down — CONTROLLER session still alive and pong-responsive
```

### SessionRole regression confirmed
The server logged:
```
Server: No PRIMARY sessions remain for any playerId in single-player mode.
Starting 15-second shutdown timer.
```

This fired while the Python CONTROLLER WebSocket was still connected and pong-responsive. The `hasAnyPrimarySession()` check is returning FALSE despite the CONTROLLER session being alive, OR there is a shutdown path that fires when the LAST session disconnects regardless of role.

**Likely cause:** The `onReconnected` callback may not be guarded by `session.role == SessionRole.PRIMARY`, or there is a separate shutdown trigger that fires when the LAST session disconnects regardless of role.

### Debug signal race
The debug signal server (port 7075) appears to have cleared `GAME_STARTED` before the browser polled it. The signal-persistence fix from 2026-05-10 should prevent this — the signal server may not have been restarted with the fix applied, or the browser navigated too late.

## Server Log Markers (confirmed game state)
```
TurnHarness: Round 1 started. Turn order: Lord Maple Tree, Quag, Invis, Bigwang
TurnHarness.executeSingleTurn: Resolved actor='Lord Maple Tree' (round=1, turnOrderIndex=0)
TurnHarness.executeSingleTurn: Executing turn for actor='Lord Maple Tree'
TurnHarness: broadcasting ResolutionStep: START, Message: 'It is Lord Maple Tree's turn'
TurnHarness.awaitPlayerAction: Player 'Lord Maple Tree' is reachable, proceeding to wait for action
TurnHarness.awaitPlayerAction: Starting turn timer for Lord Maple Tree (300s)
TurnHarness.awaitPlayerAction: Suspending for Lord Maple Tree's action (timeout=302000ms)
UiSignalRpcHandlers: Dispatching 'ui.updateTurnTimer' to lord-1778709764713-631087
Server: No PRIMARY sessions remain for any playerId in single-player mode.
Starting 15-second shutdown timer.
```

## Key Finding
The game server correctly routes game state to the browser's WebSocket (confirmed by `ui.updateTurnTimer` ticks being received). The dual-control routing via shared `playerId` IS working. The failure is purely on the session lifecycle management side — the server kills itself when the browser's WebSocket drops, even though the Python CONTROLLER is still alive and responsive.

## Fix Required
The `Server.kt` shutdown logic needs to account for CONTROLLER sessions: a game should survive as long as ANY session (PRIMARY or CONTROLLER) for a human player remains connected. The current `hasAnyPrimarySession()` check excludes CONTROLLER sessions from the liveness check.

## Shutdown
```bash
pkill -9 -f "autogenesis|server-extend|webpack|gradlew.*server|gradlew.*kvision"
kill -9 $(fuser 7070/tcp 7075/tcp 8000/tcp 8080/tcp 9080/tcp 2>/dev/null)
# All ports confirmed clear after shutdown
```
