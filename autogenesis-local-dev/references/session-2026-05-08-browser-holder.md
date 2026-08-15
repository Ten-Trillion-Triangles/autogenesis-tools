# Session 2026-05-08 — Playwright Browser Holder + Server Recovery

## What Happened Today

A day of recovering from earlier context compaction, re-establishing server state, and confirming the canonical workflow is solid.

### Server Restart Cycle

Repeated game server crashes required restarts. Pattern:
```
game server dies → port 9080 goes down → restart via ./gradlew :server:run
```

Game server started with `:server` project (NOT `:game` — that doesn't exist):
```
./gradlew :server:run  # correct
./gradlew :game:run    # WRONG — "project 'game' not found"
```

Startup wait: ~100s for game server (TPipe compilation), then verify with `ss -tlnp | grep 9080`.

### Controller Run — Canonical Pattern

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py --no-ui
```

Expected output:
```
Session ready detected!
Starting matchmaking...
Matchmaking complete, game should be starting...
Connecting to ws://127.0.0.1:9080/events?playerId=lord-...
It's Lord Maple Tree's turn!
My turn - generating TPipe action
TPipe returned status 400 → using fallback
Action submitted: <text>
```

TPipe 400 error is expected — TPipe embedded in Java, DynamoDB at :8000 is separate.

### What Worked

- **Python-only gameplay** — fully confirmed. No browser needed.
- **controller.py** — clean pipeline every time: SSE → REST → WS → pong → turn detection → action submit
- **SSE via curl + stdbuf** — not websocket-client (websocket-client only handles ws:// scheme)
- **Threaded sync pong** — ws.recv() FIRST then queue.put(), not the reverse
- **Python 3.13 venv** at `/tmp/autogenesis-dev` — system Python 3.14 incompatible with some packages

### What Didn't Work

#### browser_holder.py / autogenesis_dual.py — Browser UI Click Failure

```html
<div class="collection-tab-strip">…</div> from <div class="collection-overlay">…</div>
subtree intercepts pointer events
```

Playwright CAN:
- Launch Chromium, navigate, capture console logs
- Connect WebSockets to game server (9080)

Playwright CANNOT:
- Make KVision reactive state reflect DOM clicks
- Dismiss collection overlay blocking PLAY button
- Select commanders in matchmaking dialog

This is a known KVision limitation. Python REST matchmaking is the workaround.

#### controller_browser_match.py — SSE via websocket-client

```python
websocket-client library error:
"scheme http is invalid"

SSE endpoint is HTTP, not WS.
Must use: curl + stdbuf -oL  OR  requests.get(..., stream=True)
```

This script tried to use `websocket-client` for SSE — fundamentally wrong library.

### Background Process Management

Server start commands with `background=true` generate Gradle build notifications (`BUILD SUCCESSFUL`) that arrive after the command completes. These are informational — the actual servers keep running. Key PIDs to track:

```
server-extend  pid 1693951  port 7070
game server    pid 1703229  port 9080
webpack        pid 1696063  port 8080
```

Port check: `ss -tlnp | grep -E "7070|9080|8080"`

### Log Files

- `/tmp/srv.log` — game server Gradle output (check for BUILD SUCCESSFUL)
- `/tmp/se.log` — server-extend Gradle output
- `/tmp/kv.log` — webpack output
- `~/.autogenesis/logs/autogenesis-YYYY-MM-DD*.log` — detailed game server runtime logs

### Confirmed Turn This Session

```
Action: "I deploy the shadow assassins to disrupt enemy supply lines."
Status: TPipe 400 → fallback text used (expected)
Game: running server-side, TPipe embedded in Java
```

## Key Lessons

1. **Python-only is canonical** — no browser needed, no Playwright needed
2. **`:server` not `:game`** — multiple failed attempts from misremembering project name
3. **SSE ≠ WebSocket** — `websocket-client` cannot do SSE; use curl/requests
4. **KVision browser automation is broken** — confirmed again; don't waste time
5. **Python 3.13 venv at /tmp/autogenesis-dev** — system Python 3.14 is incompatible

## Files Created/Modified This Session

- `/tmp/browser_holder.py` — Playwright browser session holder
- `/tmp/browser_holder2.py` — improved browser holder with overlay dismiss
- `/tmp/autogenesis_dual.py` — combined browser + Python controller
- `/tmp/controller_browser_match.py` — SSE via websocket-client (BROKEN)

All `/tmp/` scripts are superseded by `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller/controller.py`.