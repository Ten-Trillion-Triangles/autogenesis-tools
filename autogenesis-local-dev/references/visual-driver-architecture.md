# Visual Driver Architecture — Browser as Observer (2026-05-08)

## The Core Problem

Python drives the game (matchmaking via REST, gameplay via WS) but the browser shows nothing — it stays on the main menu. The browser and Python have **different playerIds**, so the game server routes all game state to Python's WS connection. The browser's WS connections are separate and never receive game events.

**Result:** Server log proves the game runs end-to-end (TurnHarness processes turns, TPipe generates 5341-char narrative for Round 1, Story Length: 5341 in `Broadcasting TurnComplete`). But the browser's screenshot shows only the main menu.

## What the Server Log Proves

```
2026-05-08T20:31:07.317Z [LLM]: TurnHarness.handleAiTakeover: PlayerAgent execution finished (took 80416ms)
2026-05-08T20:31:07.495Z [DEBUG] [NETWORK]: UiSignalRpcHandlers: Internal Broadcast -> Method: 'ui.updateTurnTimer'
2026-05-08T20:32:38.093Z [INFO] [NETWORK]: Broadcasting TurnComplete. Story Length: 0
2026-05-08T20:35:03.776Z [INFO] [NETWORK]: Broadcasting TurnComplete. Story Length: 5341
2026-05-08T20:35:03.778Z [INFO] [SYSTEM]: Phase 13: End of Turn Maintenance...
```

The game is FULLY RUNNING server-side. `ui.updateTurnTimer`, `TurnComplete`, narrative — all broadcast by the game server. But to WHICH playerId?

## The Routing Problem

```
PlayerConnectionManager.register(playerId=lord-1778272175274-696704, session=<WS session>)
  → stores session at sessions[lord-1778272175274-696704]

Broadcasting ui.updateTurnTimer to playerId=lord-1778272175274-696704:
  → findSession(lord-1778272175274-696704) → FOUND → sends to Python WS

Broadcasting TurnComplete:
  → WorldManager.isReachable: CONNECTED → confirmed reachable
```

Python registered with `lord-*` playerId. Game server found that session. All state went to Python.

Meanwhile the browser registered with `kvision-ws-client-*` IDs. The browser's WS sessions exist but the game server doesn't know to route game state to them — because the MATCHMAKING was done by Python's playerId, not the browser's.

## The Screenshot Evidence

- All periodic screenshots: **777,363 bytes** (dark purple — likely the main menu or loading screen)
- Initial screenshot: **4,993 bytes** (small — browser was on the AUTOGENESIS logo screen)
- Event screenshot (on game event detection): **777,363 bytes**
- MiniMax analysis confirmed: shows the AUTOGENESIS main menu

The game server is generating game state. The browser never receives it because the playerId mismatch.

## The Fix: Make Browser and Python Share the Same PlayerId

**Option A — Browser drives matchmaking, Python observes:**
1. Browser opens to `skipLogin=true` → KVision generates `kvision-ws-*` ID
2. Python reads browser's ID from server logs (`kvision-ws-client-353176120 registered`)
3. Python uses that ID for its SSE + WS connections
4. Game state goes to that WS — both browser and Python read it
5. Python submits actions as the same player

**Problem:** Requires reading ID from server logs in real-time. Feasible but complex.

**Option B — Python drives, browser observes passively:**
1. Python generates a known playerId in advance
2. Browser receives that ID somehow (requires KVision code change to accept URL param)
3. Game state goes to shared WS — both read it

**Problem:** KVision generates IDs internally. Currently no URL param override.

**Option C — CDP-based browser observer (working):**
- Browser runs normally (its own IDs)
- `browser_observer.py` uses Playwright CDP to capture screenshots on game events
- Game events detected via **Python's WS connection**, not browser's
- Python drives; browser observes via screenshots
- This is what was fixed today (async screenshot bug)

## Screenshot Capture Bug (FIXED)

`take_screenshot()` in `browser_observer.py` was synchronous but `page.screenshot()` is async. All screenshots silently failed. Fixed:

```python
# WRONG (sync, but page.screenshot() is a coroutine):
def take_screenshot(page, label):
    page.screenshot(path=path)  # returns coroutine, never executed!

# CORRECT (async):
async def take_screenshot(page, label):
    await page.screenshot(path=path)

# Calling from sync context:
asyncio.get_event_loop().create_task(take_screenshot(page, label))
```

## Screenshot Trigger Events (working)

Monitor these in Python's WS event stream for `browser_observer.py` screenshot triggers:
- `ui.activeTurn` — turn started
- `ui.setResolutionStep` — turn progress  
- `ui.forceShowTurnResolution` — turn result shown
- `ui.narrativeChunk` — story streaming
- `ui.turnComplete` — round finished
- `ui.thinkingUpdate` — AI reasoning output

## Current Best Architecture

```
Python Controller (playerId=lord-*)
  ├─ SSE (7070) → matchmaking, session.ready
  ├─ WS (9080) → game state, pong keepalive, action submission
  └─ browser_observer.py (same WS stream)
        └─ captures screenshots on game events
             └─ saved to /tmp/autogenesis-proxy/screenshots/
                  └─ sent to MiniMax for vision analysis
```

Python reads game state from its WS, detects game events, triggers browser screenshots via `browser_observer.py`. Browser remains passive observer (its own WS connections show main menu only). This is the **observer pattern** — works but browser doesn't show game UI.

**For true game UI in browser**, Option A or B needs implementing.