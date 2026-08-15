# Session Binding: How Python Receives Game State

## Update (Round 1 Results Confirmed)

Python CAN receive full game state including `ui.agentWorkStream`, `ui.narrativeChunk`, and `ui.forceShowTurnResolution`. Round 1 confirmed this works. The key is using the SAME playerId for both SSE and WS connections, and completing matchmaking via server-extend REST.

## How It Works

1. Python connects WS to game server (9080) with `playerId=LMT-X`
2. Python connects SSE to server-extend (7070) with `playerId=LMT-X`
3. Python sends `server.extend.requestGame` via REST POST to server-extend
4. server-extend calls `server.setGameMode` on game server with `websocketId=LMT-X`
5. Game server registers `LMT-X` as a player in `WorldManager.playerStats`
6. Game server broadcasts game state to `LMT-X` via WS
7. Python receives all game events

## Key Requirement

Python's WS and SSE connections MUST use the SAME playerId. This is what binds the matchmaking session to the WS game connection.
