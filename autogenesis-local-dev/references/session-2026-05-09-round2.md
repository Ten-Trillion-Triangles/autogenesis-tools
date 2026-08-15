# Session: Round 2 Bug Hunt — 2026-05-09 (Evening)

**Outcome:** BROWSER STUCK ON MAIN MENU — halted after ~7 minutes, servers stopped.

## What Was Run
- server-extend (7070) + game server (9080) + webpack (8080) — all confirmed clean startup
- Python controller in `--no-ui` mode with `--player-alias guest-user`
- Matchmaking via Python REST call → succeeded
- Lord Maple Tree turn detected at 20:05:20 → fallback action submitted
- TPipe returned DynamoDB 400 (expected fallback)
- Rounds 1 and 2 both executed server-side

## New Findings This Session

### findAllSessions Fix Is Working (but browser can't display gameplay)

Server logs confirm `findAllSessions` fix broadcasts to ALL 6 sessions:
```
Broadcasting message Notification to 6 sessions
AgentWorkStreamStreaming: Resolved 6 broadcast recipients
```

The browser IS receiving WebSocket payloads (confirmed by `Received WebSocket payload (length=N)` in browser log). But KVision's game event handlers aren't processing them because `World.localPlayer` was never set.

### World.localPlayer Never Set in skipLogin=true Mode

The browser uses `skipLogin=true` which bypasses the matchmaking flow. `World.localPlayer` is only set when:
1. Browser goes through `server.extend.requestGame` REST flow
2. `GameInit.configurePlayersFromSession` registers the player's session
3. `DebugConsole.triggerGameStarted()` is called via `GAME_STARTED` signal

In `skipLogin=true` mode, step 1 is bypassed. The `GAME_STARTED` signal tries to set `World.localPlayer` but the game event dispatch still doesn't reach the UI because the game state pipeline (`ui.setLocalPlayer`, `ui.setResolutionStep`) never fires without proper matchmaking.

### Agent Work Stream Drops — NOT a Bug

All browser log entries like:
```
AgentWorkStreamManager.handleStream: Dropping data because window not visible (window=null, visible=null)
```
Are EXPECTED. The stream only activates when user opens `AgentWorkStreamWindow` via `/agentstream`. Saves bandwidth.

### BROWSER_SESSION_ID Literal — NOT a Bug

Server log shows `BROWSER_SESSION_ID` as a connection ID in `WorldManager.isReachable` calls. This is a fallback literal used when no real playerId is available. Expected in `skipLogin=true` mode.

## Bug Status After Round 2

| Bug | Status | Notes |
|-----|--------|-------|
| #1 Server 15s shutdown | PROBABLE | Python holds WS connection; server stayed up all session |
| #2 AI thinking vanishes | PARTIAL FIX | `findAllSessions` works; browser can't display gameplay |
| #3 NPC thinking capture | CANNOT PROVE | Browser never reached gameplay |
| #4 Writing UI stuck | CANNOT PROVE | Browser never left main menu |
| #5 Reasoning [] | CANNOT PROVE | Browser never in gameplay |
| #6 Nemesis alert | CANNOT PROVE | Karma low (5) |
| #7 Blue person icon | CANNOT PROVE | Browser never in gameplay |
| #8 Eligible NPC flood | FIXED 2026-05-09 | `!isDefeated` added at line 1530 |
| #9 Too many nemesis | NOT OBSERVED | Karma low |
| #10 Counterplay cascade | NOT OBSERVED | No counterplay occurred |
| #11 Elder God generic | CANNOT PROVE | No Elder God spawned |

## Architecture Incompatibility Identified

`skipLogin=true` + `GAME_STARTED` signal was designed for **observer mode** (browser as passive visual display). For the browser to show actual gameplay, it must go through the full REST matchmaking flow.

**Two valid debugging architectures:**
1. **Observer mode:** Python drives game, browser shows screenshots via CDP (current approach, working)
2. **Full gameplay mode:** Browser through proper matchmaking, Python as secondary controller

These are incompatible — mixing them (Python matchmaking + browser observer) caused the browser to stay on main menu.

## Server Log Key Entries

```
2026-05-10T00:05:20.513: TurnHarness.handleAiTakeover: AI TAKEOVER INITIATED for actor='Lord Maple Tree'
2026-05-10T00:05:20.721: GameRpcHandlers.submitAction: About to call TurnHarness.runNextTurn()
2026-05-10T00:05:29.056: UiSignalRpcHandlers: Internal Broadcast -> Method: 'ui.thinkingUpdate'
2026-05-10T00:06:39.162: WorldManager.isReachable: Player 'Lord Maple Tree' is marked as AI-controlled
2026-05-10T00:06:39.165: UiSignalRpcHandlers: broadcasting ResolutionStep: PLAYER_ACTION
2026-05-10T00:09:03.554: UiSignalRpcHandlers: Cannot send agent work stream, session 'kvision-ws-client-126102094' not found
```

The `Cannot send agent work stream` warnings appear for TWO old session IDs that were from the PREVIOUS session's browser connections. The CURRENT browser session ID is `kvision-ws-client-47381661`. The fix (findAllSessions) works for the current session — the warnings are for stale IDs.

## Key Files Changed

- `server/.../UiSignalRpcHandlers.kt` — `findAllSessions` fix (2026-05-09)
- `server/.../TurnHarness.kt` — `!isDefeated` filter (2026-05-09)
- `kvisionApp/.../DebugSignalBridge.kt` — new UI signals (OPEN_WIDGET, CLOSE_WIDGET, EXECUTE_COMMAND)
- `kvisionApp/.../DebugConsole.kt` — `currentGameplayUI` registration, new trigger methods
- `kvisionApp/.../KEnv.kt` — `currentGameplayUI` global reference
- `kvisionApp/.../CommandBox.kt` — `setAndSubmit(text)` public method
- `controller/controller.py` — new `send_*` signal methods (2026-05-09)