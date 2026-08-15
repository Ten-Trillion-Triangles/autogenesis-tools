# Autogenesis Server Architecture

## Port Layout

| Service | Port | Protocol | Role |
|---------|------|----------|------|
| Game server | 9080 | HTTP/WebSocket | Main gameplay, turn processing, TPipe orchestration |
| Game server gRPC | 9091 | gRPC | Internal IPC |
| Server-extend | 7070 | REST/SSE | Matchmaking, session management |
| Server-extend gRPC | 9092 | gRPC-web | Internal IPC |
| KVision webpack | 8080 | HTTP | Browser UI dev server |

## Game Server (9080) — WebSocket RPC

### Connection
```
ws://127.0.0.1:9080/events?playerId=<id>&guestMode=true
```
- `playerId` becomes `connectionId` in all RPC handlers
- `guestMode=true` enables guest authentication
- First message is always `client.pong` with echo of playerId

### Key RPC Methods (SERVER direction)

**`game.submitAction`** — The working turn submission method (confirmed by server logs). `server.sendPrompt` returns null and is not processed by TurnHarness.

```json
{
  "type": "request",
  "id": "action-1",
  "method": "game.submitAction",
  "params": {
    "action": "The Entmarch: Lord Maple Tree commands...",
    "playerName": "Lord Maple Tree"
  }
}
```

Server-side handler: `GameRpcHandlers.submitAction` reads `request.playerName` and `request.action`. Must be sent as a request (not notification).

**`server.sendPrompt`** — Legacy method. Returns `null` if no active game. Not processed by TurnHarness. Do NOT use.
```json
{
  "type": "request",
  "id": "prompt-1",
  "method": "server.sendPrompt",
  "params": "The Entmarch: Lord Maple Tree commands..."
}
```
Response: `{"type": "response", "id": "prompt-1", "result": null, "error": null}` — immediate, then async game processing begins.

Returns `null` if no active game session exists AND demo mode is not enabled.

**`game.submitAction`** — Alternative turn submission
```json
{
  "type": "request",
  "id": "action-1",
  "method": "game.submitAction",
  "params": {
    "playerName": "LordMapleTree",
    "actions": [{"type": "march", "target": "The Golden Forest"}]
  }
}
```
Returns `{"result": false}` when `WorldManager.world.activePlayers` is empty (no active game).

**`server.setGameMode`** — Internal use only, called by server-extend during matchmaking.

### Game State Messages (SERVER→CLIENT push)

- `connection_state` — WebSocket connection acknowledgment with playerId and CONNECTED status
- `ui.setLocalPlayer` — Full world state including territories, resources, points, playerId
- `ui.updateTurnTimer` — Countdown ticks every 1s while waiting for player action
- `ui.setResolutionStep` — Turn phase progression: PLAYER_ACTION → STRATEGIC_ANALYSIS → EXECUTION → STORY
- `ui.updateProgressBar` — TPipe pipeline progress
- `ui.narrativeChunk` — Story/narrative text chunks
- `ui.agentWorkStream` — TPipe AI streaming tokens
- `ui.thinkingUpdate` — Player's internal reasoning/thinking
- `ui.forceShowTurnResolution` — Turn result: `{wasPlayerSuccessful, territoryGained, resultType, storyLength, story}`

## Server-Extend (7070) — REST/SSE

### SSE Connection
```
http://127.0.0.1:7070/events?playerId=<id>&guestMode=true
```
Event types: `notification`, `connection_state`, `session.ready`, `MatchFoundNotification`, `GameStartNotification`.

### REST RPC
```
POST http://127.0.0.1:7070/rpc?playerId=<id>&guestMode=true
Content-Type: application/json

{"method": "server.extend.requestGame", "params": {...}}
```

## Matchmaking Flow (Dev Mode)

1. Browser WebSocket connects to game server (9080) → gets `kvision-ws-*` ID
2. Browser SSE connects to server-extend (7070) → gets `rest-client-*` ID
3. Browser calls `server.extend.requestGame` via REST with `websocketId` = kvision-ws ID
4. Server-extend calls `server.setGameMode` on game server WebSocket
5. Game server initializes game session, stores player by `websocketId`
6. Server-extend confirms to browser via REST response
7. Game server begins streaming state to browser's WebSocket

## Critical: isDemoMode is Dead Code

`PromptManager.isDemoMode` is hardcoded to `false` and never set to `true` anywhere in the codebase. The demo mode code path in `server.sendPrompt` that auto-initializes a world is unreachable. **Games can only run through proper matchmaking.** There is no fallback for Python-only connections.

## Python WebSocket-Only Can Now Work End-to-End

The old limitation ("Python WebSocket-only doesn't work") is STALE. With the **threaded sync** SSE+WS concurrency pattern (NOT async) and proper pong ID handling, Python can run end-to-end autonomously. See `scripts/lmt_autogenesis.py` and the "Python Autonomous Gameplay" section in SKILL.md.

Key requirements:
- Same playerId on both SSE (7070) and WS (9080)
- Pong ID must match ping ID (server checks pong.id == ping.id) — send as RESPONSE, not REQUEST
- SSE reader must be non-blocking with curl + stdbuf (NOT async websockets)
- Must restart servers to clear stale TTL timers
- Use `websocket-client` (sync) — NOT `websockets` (async, breaks with API incompatibilities)
