# Autogenesis Python Matchmaking Reference

## Architecture Summary

Two connections required, both to `127.0.0.1`:
- **SSE** (`server-extend` port 7070): `GET /events?playerId=X&guestMode=true` — matchmaking push events
- **WebSocket** (`game server` port 9080): `ws://127.0.0.1:9080/events?playerId=X&guestMode=true` — game state, ping/pong keepalive

Both connections MUST use the same `playerId`.

## REST RPC Format for `server.extend.requestGame`

```python
import urllib.request, json

player_id = f"lmt-{os.getpid()}-{int(time.time()*1000)}"
body = json.dumps({
    "type": "request",           # Kotlin serialization discriminator
    "id": "match-1",
    "method": "server.extend.requestGame",
    "params": {
        "userName": "Lord Maple Tree",
        "gameType": "SINGLEPLAYER",   # UPPERCASE enum
        "accelByteId": "guest-user",   # non-null string
        "websocketId": player_id,       # same as SSE playerId
        "selectedCommander": {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Lord Maple Tree",
            "type": "Land",
            "trait": "Researcher",    # NOT "Balanced" — Lord Maple Tree is a Researcher
            "imageUrl": "",
            "rarity": "LEGENDARY"    # uppercase
        },
        "aiOpponentCount": 1,
        "aiOnly": False
    }
}).encode()

req = urllib.request.Request(
    f"http://127.0.0.1:7070/rpc?playerId={player_id}&guestMode=true",
    data=body, headers={"Content-Type": "application/json"}, method="POST"
)
with urllib.request.urlopen(req, timeout=10) as resp:
    print(f"HTTP {resp.status}")  # 202 = accepted
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| HTTP 404 | SSE not open before REST POST | Open SSE first, keep it open |
| `Class discriminator missing` | Used JSON-RPC 2.0 format | Use `{"type":"request",...}` |
| `GameType does not contain 'single_player'` | Lowercase enum | Use `"SINGLEPLAYER"` |
| `Fields [userName, gameType, accelByteId] required` | `accelByteId` was `null` | Use `"guest-user"` |
| SSE receives no events | Blocking urllib3 stream | Use async subprocess curl |

## GameType Enum Values

- `SINGLEPLAYER` (NOT `"single_player"`)
- `MULTIPLAYER`
- `FRIEND`

## Pong ID Bug (CRITICAL)

Server sends `client.ping` with optional `id` field (may be null, a UUID, or absent). Python MUST echo back the same id, but also generate a fallback when null to avoid sending `"id": null`:

```python
# CORRECT — handles null ids safely
pong = {
    "type": "response",
    "id": ping.get("id") or str(uuid.uuid4()),  # generate only if server sends null/absent
    "result": {"echo": player_id}
}

# WRONG — sends null id when server provides none
pong = {"type": "response", "id": ping.get("id"), ...}  # sends null!

# WRONG — always generates new ID (ID mismatch causes UNREACHABLE)
pong = {"type": "response", "id": str(uuid.uuid4()), ...}
```

Server log when pong ID is wrong:
```
WorldManager.isReachable: Ping result for Lord Maple Tree: false (took 5000ms)
```
Pong arrives (latency ~2ms) but ID mismatch means server ignores it.

## Threaded SSE + WS Pattern (VERIFIED WORKING)

SSE and WS must run as concurrent threads (NOT async tasks). The working pipeline:

1. **Pong thread** — dedicated `websocket-client` (sync) thread. Calls `recv()` FIRST with timeout, then puts messages on a queue. This prevents the blocking-pong issue.
2. **SSE thread** — `curl` subprocess with `stdbuf -oL` for line-buffered SSE.
3. **Main thread** — reads pong queue, runs TPipe, sends RPCs.

```python
import threading, queue, json, subprocess, uuid, time, os
from websocket import create_connection

PONG_QUEUE = queue.Queue()
WS = None  # global set by main

def pong_thread(ws_url, player_id):
    """Handle game server WS pong keepalive — MUST recv FIRST."""
    global WS
    ws = create_connection(ws_url, timeout=5)
    WS = ws
    ws.settimeout(2.0)  # recv timeout — prevents blocking forever
    ws.send(json.dumps({
        "type": "request", "id": "init",
        "method": "client.register",
        "params": {"playerName": player_id}
    }))
    while True:
        try:
            msg = ws.recv()  # recv FIRST with timeout — then queue
            if msg:
                PONG_QUEUE.put(msg)
        except Exception:
            pass  # timeout or disconnect — loop continues

def sse_monitor(sse_url):
    """Watch server-extend SSE for session.ready."""
    proc = subprocess.Popen(
        ["stdbuf", "-oL", "curl", "-s", "-N", sse_url,
         "-H", "Accept: text/event-stream", "--max-time", "20"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    for line in proc.stdout:
        line = line.decode().strip()
        if line.startswith("data: "):
            obj = json.loads(line[6:])
            if obj.get("method") == "session.ready":
                SESSION_READY.set()

# Main thread reads from PONG_QUEUE, handles game events, submits actions
while True:
    msg = PONG_QUEUE.get(timeout=900)
    obj = json.loads(msg)
    # handle ping, game state, turn events...
```

## Key Game State Events (via WS on port 9080)

| Event | Meaning |
|-------|---------|
| `ui.setLocalPlayer` | Full world state snapshot |
| `ui.setResolutionStep` | Turn progress — **this is the correct turn detection signal** |
| `ui.activeTurn` | Player's turn started (less reliable than setResolutionStep) |
| `ui.updateTurnTimer` | Countdown ticks |
| `ui.agentWorkStream` | TPipe streaming tokens |
| `ui.thinkingUpdate` | Player internal reasoning |
| `ui.forceShowTurnResolution` | Turn result (wasPlayerSuccessful, territoryGained) |
| `ui.narrativeChunk` | Story output from WriterAgent |
| `ui.judgementResult` | JudgeAgent success/failure |

**Turn detection:** Monitor for `ui.setResolutionStep` with `step == "START"` and `"Lord Maple Tree"` in the message. The server broadcasts this when Lord Maple Tree's turn begins. The `ui.activeTurn` event may also fire but `setResolutionStep: START` is more reliable.

The turn resolution lifecycle: `START → PLAYER_ACTION → STRATEGIC_ANALYSIS → EXECUTION → NARRATION → COMPLETE`

## Game Server Shutdown Triggers

1. **Python WS disconnect → 15s timer → shutdown** — When Python disconnects its WebSocket, server logs "Only human player disconnected in single-player mode. Starting 15-second shutdown timer." This killed the game mid-session. Keep Python WS alive throughout gameplay.
2. **Runaway token guard** — gRPC bridge hard-shuts server when inference exceeds safe budget (~250k tokens). This is the Round 2+ blocker.
3. **Stale TTL timers** — Old matchmaking sessions from previous runs set 5-second TTL. Restart servers before each Python run.

## Working Full Script

See `scripts/lmt_autogenesis.py` in the parent skill directory.
