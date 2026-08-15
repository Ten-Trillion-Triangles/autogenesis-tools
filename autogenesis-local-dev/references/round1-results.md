# Round 1 Results — Lord Maple Tree's First Campaign

## Session: 2026-05-07 21:19 — Complete

**Game server:** proc_6637ee775304 (PID 1499406), started 21:17
**Server-extend:** proc_655f308283da (PID 1500203), started 21:19
**Python script:** `/tmp/lmt_autogenesis.py` (threaded sync, pong-as-RESPONSE)
**Python process:** proc_6c06ed90a1f4 (PID 1502075), exited cleanly at ~01:33

## What Worked (Breakthroughs)

1. **CommanderType enum** — `"ENT"` → `"Land"` (was invalid, silently failed matchmaking)
2. **CommanderTrait enum** — `"MAPLE_SYRUP_MASTER"` → `"Researcher"` (was invalid, silently failed matchmaking)
3. **pong as RESPONSE** — Root cause of all prior ping timeouts. Server sends `client.pong` as REQUEST, client must reply with RESPONSE. Sending it as a REQUEST went to `rpcRegistry.dispatch()` → null → future never completed → 5s ping timeout.
4. **Turn detection** — `ui.setResolutionStep` with `step == "START"` + `"Lord Maple Tree"` in message
5. **Two-connection architecture** — SSE for matchmaking, WS for game state
6. **Threaded pong thread** — recv-first with `websocket-client` (NOT async `websockets`)
7. **game.submitAction RPC** — correct method name and `playerName` field

## Turn Order

`[Zeta, Gl'kr'kr'kr'k, BG, Lord Maple Tree]` — Lord Maple Tree is index 3.

## Round 1 Outcome

**Lord Maple Tree's action:** "The Ent army marches southward through the Atlantic Ocean, seeking to establish vegetative dominion and spread peace."

**Judge result:** `wasPlayerSuccessful: false`, `targetIntent: "Hostile"`, `outcome: "FAILURE"`
- `-15 Readiness, -15 Legitimacy`
- `territoryGained: []`, `territoryLost: []`
- No resources gained or lost

**Narrative summary:** The Ent army's attempt at "vegetative transcendence" above the so-called "Atlantic Ocean" — actually a vast salt flat — collapsed before formation. The biome "Arborealis Ioensis" (The Skygrove) never formed. The 14,300 peasants remained seated in perfect circles, brains unresponsive. The Kubrickian Monolith (98.6% pure crystallized Grade-A Dark Amber Maple Syrup) failed to emerge. The Syrup Prophet remained 40% translucent and buried in a dune crevasse. Zelgon Gweelysh remains officially unlocated.

**Server log excerpt:**
```
Action submitted by Lord Maple Tree: Photosynthetic Incursion against the Southern Coast
TurnHarness.executeSingleTurn: Executing turn for actor='Lord Maple Tree'
Action submitted by Lord Maple Tree: The Ent army marches southward through the Atlantic Ocean...
Lord Maple Tree's military expedition to establish vegetative dominion above the Atlantic Ocean
catastrophically failed... The action was classified as Hostile intent with a FAILURE outcome.
```

## Game State Flow (Verified)

```
Python WS connects → server sends client.ping → Python pong as RESPONSE
Python SSE connects → session.ready → REST POST server.extend.requestGame
Game server configures session → configurePlayersFromSession
TurnHarness.executeSingleTurn → awaitPlayerAction → reachability check
  → pong RESPONSE → WorldManager.isReachable: SUCCESS
  → turn timer starts (300s)
Lord Maple Tree's turn → ui.setResolutionStep: START
Python submits action → game.submitAction RPC
TPipe thinks (~4 min) → Judge evaluates → broadcast judgement
TurnHarness loops to next player (Zeta AI takeover)
All players done → Round 2 begins
```

## Key Server Log Markers

```
# Ping success (pong-as-RESPONSE working):
WorldManager.isReachable: Ping result for 'lord-232230-1778203466923': SUCCESS

# Action received:
RPC Dispatching Request: method=game.submitAction id=2 from playerId=lord-232230-1778203466923
GameRpcHandlers: submitAction entry (player=Lord Maple Tree)
Action submitted by Lord Maple Tree: Photosynthetic Incursion...

# Turn resolution:
Broadcasted judgement result for Lord Maple Tree (success=false)

# Player turn complete:
TurnHarness.executeSingleTurn: Executing turn for actor='Zeta' (round=1, turnOrderIndex=1)

# Python disconnected → shutdown:
Player Lord Maple Tree connection state updated: connected=false
Server: Only human player disconnected in single-player mode. Starting 15-second shutdown timer.
GrpcServer: Shutdown complete
```

## Python Exit

Python exited with code 0. Output at disconnect:
```
[WS] NOTIF ui.agentWorkStream (repeated ~80 times)
[WS] NOTIF ui.updateProgressBar
[WS] NOTIF ui.forceShowTurnResolution
[WS] NOTIF ui.turnComplete
[WS] NOTIF ui.prepareStory
[WS] NOTIF ui.agentWorkStream (repeated)
[Main] Monitor ended. game_over=False
[Main] Shutting down...
[PongThread] Exiting
[PongThread] Total pongs: 3
[Main] Done.
```

## Lessons Learned

1. **Enum validation is silent** — `CommanderType.ENT` and `CommanderTrait.MAPLE_SYRUP_MASTER` don't exist. Matchmaking silently fails with no error.
2. **pong.id must match ping.id** — even when server sends null, use `ping.get("id") or str(uuid.uuid4())`.
3. **SSE reader must use curl + stdbuf** — urllib3/requests buffered I/O cannot read SSE reliably.
4. **Two-connection architecture mandatory** — server-extend (7070) for matchmaking, game server (9080) for game state.
5. **Browser not required** — Python can run the entire game independently via REST matchmaking.
6. **Keep Python WS alive** — disconnecting WS triggers 15s shutdown timer and kills the game.
