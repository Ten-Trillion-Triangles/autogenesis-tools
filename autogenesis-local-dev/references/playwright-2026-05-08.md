# Playwright Browser Automation — 2026-05-08 Session Results

## Setup

```bash
uv pip install playwright --python ~/.hermes/hermes-agent/venv/bin/python3
# Install browsers (one-time):
~/.hermes/hermes-agent/venv/bin/python3 -m playwright install chromium
```

Test connection:
```python
~/.hermes/hermes-agent/venv/bin/python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); print('OK'); b.close(); p.stop()"
```

## What Works

Playwright successfully:
- Launches Chromium headless
- Navigates to `http://127.0.0.1:8080/?skipLogin=true`
- Authenticates (skipLogin bypasses AccelByte IAM)
- Establishes WebSocket connections to game server (9080)
- Reads DOM elements and page state
- Captures browser console logs and network traffic
- Reads `window.__kv_state` from the page (returns `{}` — KVision state is internal)
- Finds and reads commander data in `CommanderDataSync` logs

## What Doesn't Work

**KVision reactive state does NOT update from external clicks.** The root cause: KVision uses a reactive state management system where UI components are bound to internal `ref` handles. DOM click events reach the browser engine but do NOT propagate to KVision's internal reactive model. There is no synchronization layer between DOM clicks and KVision state in an automated context.

**Specific failures:**
- Clicking commander cards in `CollectionOverlay` — overlay stays open, selection never registers
- Clicking the matchmaking dialog OK button — stays disabled regardless of commander selection
- Double-clicking, forced clicks, JavaScript evaluation — none update KVision state

**Browser error dialog "Please create a commander before playing":** Occurs because no commander is selected. Python REST matchmaking bypasses this entirely.

## Implications

**Use Python REST matchmaking, not browser automation.** The Python controller (`controller/controller.py`) handles matchmaking via `POST http://127.0.0.1:7070/rpc` + SSE `session.ready` detection. This is more reliable than any browser approach.

**Playwright is useful for:**
- Headless observation of game state
- Traffic capture (WS/SSE traffic inspection)
- Verifying server startup and WebSocket connection establishment
- Reading console logs for debugging

## Key Session Log

```python
# Navigation confirmed:
goto("http://127.0.0.1:8080/?skipLogin=true")
# → "LocalDevDetector: result = true"
# → "Starting client in local mode"

# Collection overlay opened — Lord Maple Tree found:
# → "CommanderDataSync: Fetching commanders from server..."
# → "CommanderDataSync: Found 3 commanders"
# → "Lord Maple Tree" visible in DOM

# Clicking commander card — overlay stays open:
click("[data-testid='commander-item-Lord Maple Tree']")
# → overlay still open, selection not registered

# Error dialog appears:
# "Please create a commander before playing"
```

## Recommendation

Do not invest time in browser automation for matchmaking or gameplay. The Python controller approach is production-ready and handles the full game loop (matchmaking → turn detection → action submission → event logging). Playwright can be used as an optional observation tool, not a driver.
