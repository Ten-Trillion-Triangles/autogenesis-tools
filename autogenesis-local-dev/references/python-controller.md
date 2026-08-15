# Python Game Controller — Architecture Reference

**Location:** `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller/controller.py`

Python game controller providing full headless gameplay automation for Autogenesis. Replaces the fragile browser-automation approach with direct protocol control.

## Key Architecture Decisions

### TPipe is NOT Externally Callable

**Critical discovery (2026-05-08):** TPipe is embedded in the Java game server as a Kotlin library — it runs inside the JVM process. There is NO standalone TPipe HTTP server. Python CANNOT call TPipe directly.

**What this means:**
- Python submits actions via `game.submitAction` RPC on the WebSocket
- The Java game server internally calls TPipe (via gRPC on port 9091) for ALL players
- TPipe calls from Python return HTTP 400 `MissingAuthenticationToken` because port 8000 is DynamoDB Local
- Python's role: connect, detect turns, submit text actions, keep alive with pongs

**The game server handles all AI reasoning internally.** Python just provides the player's action text. The server's internal TPipe processes it and streams results back.

### Two-Connection Architecture

```
SSE (server-extend, :7070) ← matchmaking, session.ready
WebSocket (game server, :9080) ← game state, ping/pong, actions
```

Matchmaking flow:
1. Connect WS to :9080, send `client.register`
2. Start SSE curl to :7070/events, wait for `session.ready`
3. POST `server.extend.requestGame` to :7070/rpc → HTTP 202
4. Game server broadcasts to WS → turn detection begins

### Pong Must Be RESPONSE (Not REQUEST)

```python
# CORRECT — server waits for RESPONSE:
pong = {
    "type": "response",           # "request" fails silently
    "id": ping["id"],             # must echo back the same ID
    "result": {"echo": player_id}
}

# WRONG — causes ping timeout:
{"type": "request", "method": "client.pong", ...}
```

Server invoke code (Kotlin):
```kotlin
// Server.kt — sends as REQUEST, waits for RESPONSE
session.invoker.request("client.pong", PingResponse(echo = echo))
val handle = pendingFutures.remove(pongId)
handle.await()  // 5s timeout, fails to UNREACHABLE if wrong
```

### Turn Detection

**Field is `actorName`, not `actor`** — all prior turn detection failed because of this field name mismatch:

```python
elif method == "ui.activeTurn":
    params = event.get("params", {})
    self.game_context.current_actor = params.get("actorName")  # NOT "actor"
```

The `ui.setResolutionStep` with `"START"` and player name in message fires for all players (broadcast). `ui.activeTurn` with matching `actorName` confirms it's actually our turn.

### MatchPool Must Be String

```python
# WRONG — array causes server rejection:
"matchPool": ["standard"]

# CORRECT — string:
"matchPool": match_pool[0] if match_pool else "standard"
```

### WS Registration ID Format

Format: `lord-{timestamp}-{random}` e.g. `lord-1778213499346-818104`

### Python Dependencies

```bash
uv pip install websocket-client requests --python ~/.hermes/hermes-agent/venv/bin/python3
```

Use `websocket-client` (sync), NOT `websockets` (async). Curses is stdlib on Linux/macOS.

## Controller Modes

### Headless Mode (--no-ui)

```bash
~/.hermes/hermes-agent/venv/bin/python3 controller.py --no-ui
```

No TUI, logs to `~/.autogenesis/logs/controller_YYYYMMDD_HHMMSS.log`. For CI/background use.

### TUI Mode (default)

```bash
~/.hermes/hermes-agent/venv/bin/python3 controller.py
```

Interactive terminal UI with real-time event display. Requires curses.

## Log Location

```
~/.autogenesis/logs/controller_YYYYMMDD_HHMMSS.log
```

Debug logging (VERY verbose — 7MB+ per session):
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

Production (INFO only):
```python
logging.basicConfig(level=logging.INFO, ...)
```

## Game State Events (WS channel, :9080)

Key events received during gameplay:
- `ui.setLocalPlayer` — full world state snapshot
- `ui.activeTurn` — turn started (params: actorName, round)
- `ui.setResolutionStep` — turn progress: START → PLAYER_ACTION → STRATEGIC_ANALYSIS → EXECUTION → NARRATION → COMPLETE
- `ui.updateTurnTimer` — countdown ticks (every 1s)
- `ui.narrativeChunk` — story text from WriterAgent (params: chunk, isComplete)
- `ui.agentWorkStream` — TPipe streaming tokens (params: content, isComplete, streamId)
- `ui.thinkingUpdate` — player reasoning text
- `ui.updateProgressBar` — progress steps (0=broadcasting, 4=calculating consequences, 7=updating physical world)
- `ui.forceShowTurnResolution` — turn result (wasPlayerSuccessful, territoryGained)

## Session Clean Shutdown

```bash
# Kill controller gracefully
kill $(ps aux | grep "controller.py" | grep -v grep | awk '{print $2}')

# Force kill if needed
kill -9 $(ps aux | grep "controller.py" | grep -v grep | awk '{print $2}')
```

## Game Server Stability

**Confirmed (2026-05-08):** Game server runs 30+ minutes, 27K+ events without crash. Much more stable than prior sessions (which died at 2-5 minutes). The earlier crashes may have been due to Python disconnects triggering graceful shutdown.

## Known Issues

1. **Round 2 action submission missed** — turn detection ordering issue when Round 2 doesn't start with Lord Maple Tree. `current_actor` must sync from `ui.activeTurn` before `ui.setResolutionStep` check.

2. **Fallback actions used instead of TPipe** — expected, since TPipe is embedded in Java server. Python submits text; server handles AI.

3. **WS recv blocking** — `ws.recv()` in pong thread must use timeout, never block indefinitely, or reconnect logic won't work.
