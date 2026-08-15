# Visual Driver Testing Session — 2026-05-08

Attempted to build a "Visual Driver" that uses Playwright browser + Python SSE/WS together to capture game screenshots. **Failed** — but produced actionable architectural insights.

## What Was Tried

Multiple test scripts (`autogenesis-test.py` through `autogenesis-test4.py`) attempted to:

1. Launch Playwright Chromium → navigate to KVision UI (skipLogin)
2. Start Python SSE thread → wait for `session.ready`
3. POST `server.extend.requestGame` via Python REST
4. Inject game WebSocket into browser via JS
5. Poll browser for game events → screenshot on state changes

## What Failed

**All attempts failed to get game state screenshots.** Browser showed main menu (777,363 bytes, dark purple) in every screenshot. Server logs proved the game ran correctly (`TurnHarness`, `TurnComplete Story Length: 5341`) but the browser never received game state.

### Root Cause — PlayerId Mismatch

Python and browser use DIFFERENT playerIds:

```
Python SSE:     playerId=lord-1778275801032-874203  → RestPlayerConnectionManager
Browser SSE:    playerId=rest-client-1084151496     → Different session, different push channel
Browser WS:     playerId=kvision-ws-client-2105283463 → Different session
```

When `server.extend.requestGame` configures the game, it routes game state to the playerId in the `GameRequest.accelByteId` field — which is Python's `lord-*` playerId. The browser's kvision-ws-* sessions exist but never receive game events.

### Second Failure Mode — Playwright SSE Connection Kills Python Session

At 17:32:46, the Playwright browser launched and its SSE connection (`rest-client-1084151496`) **replaced** Python's SSE session in `RestPlayerConnectionManager`:

```
RestPlayerConnectionManager deregistering session for playerId=lord-1778275801032-874203
Player lord-... disconnected
WorldManager.isReachable: Final reachability for 'Lord Maple Tree': DISCONNECTED
```

The browser's SSE connection for the same playerId caused a session swap. Python's WS remained connected but its SSE session was gone. Even though the game server showed DISCONNECTED, the actual WS was still alive — `WorldManager.isReachable` checks the SSE session state, not the WS session state.

**Additionally:** The browser's WebSocket (`kvision-ws-*`) disconnected after initial page load, triggering the "Only human player disconnected" 15s shutdown timer. Browser tab staying open doesn't count — the WS session must be active.

## What Works

### Working Architecture: Python Controller Only

`controller/controller.py` is the canonical Python gameplay script. It runs independently without any Playwright browser involvement. Game state routes to Python's WS via matching playerId in `GameRequest`.

### Working Architecture: Browser Observer (Passive)

Browser opens the KVision UI as a **passive observer** — separate from the Python controller. Python drives the game; browser is just a visual window. Browser and Python have different playerIds, so they see different game sessions. The browser doesn't participate in the Python-driven game.

To capture screenshots from the Python-driven game, use `browser_observer.py` with CDP (Chrome DevTools Protocol) — it can attach to an existing browser tab and capture screenshots without creating new WS sessions.

### SSE Reader Implementation That Works

The SSE reader must be a `threading.Thread` that uses `requests.get(stream=True)` — NOT `urllib.request.urlopen`:

```python
class SSEReader(threading.Thread):
    def __init__(self, player_id, event_queue):
        super().__init__(daemon=True)
        self.player_id = player_id
        self.event_queue = event_queue
        self.stop_event = threading.Event()

    def run(self):
        import requests
        sse_url = f"http://{SE_HOST}:{SE_PORT}/events?playerId={self.player_id}&guestMode=true"
        try:
            resp = requests.get(sse_url, headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache"
            }, stream=True, timeout=30)
            for line in resp.iter_lines(decode_unicode=True):
                if self.stop_event.is_set():
                    break
                if line.startswith('data: '):
                    content = line[6:].strip()
                    if content:
                        data = json.loads(content)
                        method = data.get("method") or data.get("type", "unknown")
                        self.event_queue.put_nowait(("sse", method, data))
        except Exception as e:
            log(f"SSE[thread]: Error: {e}")
        finally:
            self.event_queue.put_nowait(("sse", "__done__", None))
```

**Why `urllib.request.urlopen` fails:** It has different buffering behavior — the stream doesn't yield line-by-line with `resp.read(4096)`. The `session.ready` event arrives but the Python code's buffering split the data incorrectly, causing silent drops.

**Why `requests.get(stream=True)` works:** `resp.iter_lines(decode_unicode=True)` gives true line-by-line iteration. SSE blank lines (just `data: ` with no content) must be skipped explicitly — they flood the stream otherwise.

## Test Scripts Created

- `/tmp/autogenesis-test4.py` — Last visual driver attempt. SSE reader works (session.ready confirmed at 17:30:01) but game state never reached browser due to playerId mismatch.
- `/tmp/autogenesis-test3.py` — Attempt with asyncio SSE reader. Same outcome.
- `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller/controller.py` — **Canonical working script.** Threaded sync (pong thread + SSE thread + main), `websocket-client` (NOT `websockets`), pong-as-RESPONSE, headless mode.

## Key Findings

1. **Do NOT mix Playwright browser automation with Python controller sessions** — the browser's SSE connection replaces Python's, killing the game server's reachability check for Python.

2. **`session.ready` detection via thread works** — SSE reader in `threading.Thread` using `requests.get(stream=True)` successfully receives `session.ready` and `connection_state` events.

3. **REST RPC via curl subprocess works** — `subprocess.run(['curl', '-s', '-X', 'POST', ...], ...)` reliably sends `server.extend.requestGame`. `urllib.request.Request` with `POST` method silently returned empty responses.

4. **PlayerId is the gating factor** — game state routes to whichever playerId is in `GameRequest.accelByteId`. Python's WS with matching playerId receives state; browser's WS with different playerId does not.

5. **Browser WS disconnects after page load** — KVision closes its WebSocket after initial connect (or the connection becomes idle). This triggers the "Only human player disconnected" 15s shutdown timer even if the browser tab stays open.

## Session Log Summary

```
17:29:05 autogenesis-test4.py started, SSE reader connecting...
17:29:05 SSE[thread]: Connection open, reading stream...
17:29:35 Timeout waiting for session.ready  ← urllib buffering bug
17:30:01 Restart with requests.get(stream=True)
17:30:01 SSE[thread]: HTTP 200, streaming...
17:30:01 SSE[thread]: session.ready  ← WORKS
17:30:01 SSE[thread]: connection_state
17:30:01 saveCommander: HTTP 0  ← urllib POST bug
17:30:01 requestGame: HTTP 0, JSON parse error  ← urllib POST bug
17:30:36 Switch to curl subprocess for REST
17:32:40 Game server registered lord-... playerId
17:32:41 WorldManager.isReachable: DISCONNECTED  ← SSE session deregistered by Playwright
17:33:19 Game server shutdown (BUILD SUCCESSFUL in 4m 44s)
```