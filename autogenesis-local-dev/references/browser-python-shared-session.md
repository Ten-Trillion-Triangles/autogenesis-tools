# Browser + Python Shared-Session Architecture (2026-05-08)

## Problem Being Solved

Python drives the game via REST (matchmaking) + WebSocket (game state + pong). The browser must show visuals to the agent (observer) — but browser and Python were using DIFFERENT playerIds, so the game server routed state to Python's WS connection, while the browser had its own separate (non-game) WS connections. **Result:** browser stayed on main menu; Python played the game invisibly.

The goal is **single-session coherence**: browser AND Python share the same playerId, so the game server pushes state to ONE WebSocket that both the browser (visually) and Python (logically) observe.

## Architecture

```
Browser (Playwright)                      Python Controller
     |                                           |
     ├─ SSE: http://:7070/events?playerId=X  ←──┤
     └─ WS:  ws://:9080/events?playerId=X    ←───┤  (SAME playerId)
              ↑ game state routed here
              └─ Browser renders state changes
              └─ Python reads events + pong keepalive
```

Browser and Python share the same `playerId=X`. The game server routes all state to that WS session. Browser's DOM updates as it receives frames. Python reads the same frames from the same WS and also handles pong.

**HOWEVER:** This only works if the browser itself initiates the WS connection to the game server. The KVision app handles this automatically when it connects — but it uses its OWN internally-generated playerId (kvision-ws-client-*). If Python uses a DIFFERENT playerId, the game server routes to Python's connection and the browser sees nothing.

**Critical insight from testing:** The browser's KVision app internally manages WS connections to the game server. Python cannot "inject" a second WS connection for the same playerId on top of an existing browser WS session — the game server's `ConnectionManager` tracks one WS per playerId. Multiple connections with the same playerId conflict.

## Two Approaches Tested

### Approach A: Python-Only (No Browser) — CONFIRMED WORKING

Python handles everything. Browser is NOT needed for visuals — the game runs server-side, Python reads state and submits actions, and the game server's internal TPipe pipeline does all the AI processing.

```bash
# 1. Start servers
./gradlew :server-extend:run &
./gradlew :server:run &
./gradlew runKvisionNoHotReload &   # optional, for manual observation

# 2. Run Python controller
cd .../controller
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py --no-ui
```

**Pros:** Fully automated, reliable, Python controls everything.
**Cons:** Browser shows nothing useful — the game is "headless" from the visual perspective.

### Approach B: Browser + Python Shared Session — IN PROGRESS

The correct implementation requires:
1. Browser launches with `skipLogin=true` and navigates to `http://127.0.0.1:8080/?skipLogin=true`
2. KVision connects to game server WS with `kvision-ws-*` playerId
3. Python reads that SAME playerId from server logs or browser console
4. Python uses the browser's playerId for its SSE + WS connections
5. Python submits actions that the game server processes and broadcasts BACK through the same WS
6. Browser renders the state updates visually

**Key finding:** KVision generates `kvision-ws-client-<timestamp>` IDs internally. These are NOT predictable in advance. The current approach of having Python generate its own ID and inject a WS connection does not work because:
- The game server only allows one WS per playerId
- The browser already has that playerId's WS slot
- Python connecting with the same ID causes `ConnectionManager` conflicts

**The correct approach for shared session:**
1. Python MUST use the browser's `kvision-ws-*` ID as its playerId
2. Python registers with the game server using that same ID
3. But this means Python and the browser are now the SAME logical "player" — the game server treats them as one connection
4. The game server broadcasts to that single WS session (shared by browser + Python)
5. Python and browser both receive the same game state frames

**Problem:** `websocket-client` library (sync) and Playwright's async WS handling conflict when sharing the same socket. The browser and Python would need to coordinate reading from the same socket — not feasible.

## What Actually Works for Visual Observation

**The browser observer pattern (NOT shared session):**
- Browser uses its own IDs (kvision-ws-*), connects normally
- `browser_observer.py` watches the browser's console/network via CDP (Chrome DevTools Protocol)
- `browser_observer.py` captures screenshots via Playwright's `page.screenshot()`
- Screenshots are saved and sent to MiniMax for vision analysis
- Python runs separately as the game controller

This is the architecture that was fixed today (async screenshot capture bug). The browser provides visuals; Python provides game logic.

**Key fix applied (2026-05-08):** `take_screenshot()` in `browser_observer.py` was sync but `page.screenshot()` in Playwright is async. All calls were silently failing. Fixed to:
```python
async def take_screenshot(page, label):
    await page.screenshot(path=path)  # must await!

# Called from sync context:
asyncio.get_event_loop().create_task(take_screenshot(page, label))
```

## Screenshot Capture Results (2026-05-08)

- **39 periodic screenshots** captured at 30s intervals
- **1 event screenshot** captured on game event detection
- **1 initial screenshot** (4,993 bytes — the browser was on main menu)
- All subsequent screenshots: 777,363 bytes (dark purple — likely the AUTOGENESIS main menu or a loading screen)

**Root cause of stale visuals:** The browser's WebSocket connected to the game server, but the game server never routed game state to it because the Python controller (using a different playerId) was the one that triggered matchmaking. Without `session.ready` matching the browser's playerId, the game server's game state went only to Python's WS connection. Browser stayed on main menu.

**The only way to get visuals:** Browser MUST be the one to trigger matchmaking (or use the SAME playerId as the Python controller). Currently these are separate.

## Next Steps for True Shared Session

To get the browser to visually track what Python is doing:

1. **Python generates a playerId** first (e.g., `lord-{ts}-{random}`)
2. **Python opens SSE to server-extend** with that playerId, waits for `session.ready`
3. **Browser opens** to `http://127.0.0.1:8080/?skipLogin=true&playerId=<python's id>`
4. **KVision needs to accept external playerId** — currently it generates its own `kvision-ws-*` IDs internally
5. **This requires a code change** in `UiSignalClientHandlers.kt` or `Main.kt` to read `window.playerId` from URL params and use it for WS connections

**OR alternatively:** Python drives matchmaking and action, browser observes passively without being a "player" — use the CDP-based browser observer, not KVision's game state connections.

## Key Files

- `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/observer/browser_observer.py` — async screenshot capture
- `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/unified_session.py` — attempted unified browser+controller (not yet working)
- `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller/controller.py` — production Python controller
- `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/Main.kt` — where KVision reads URL params and initializes connections