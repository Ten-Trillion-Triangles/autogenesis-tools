# Browser Observer — Playwright + Screenshot + MiniMax

`browser_observer.py` launches Chromium, captures console+network via CDP, and saves screenshots to `/tmp/autogenesis-proxy/screenshots/` for MiniMax vision analysis.

## Screenshot Capture — CRITICAL FIX (2026-05-08)

**`page.screenshot()` is async in Playwright.** Calling it synchronously silently fails — no exception, no file, just nothing.

```python
# WRONG — sync call, silently fails, zero-byte file:
def take_screenshot(page, label):
    page.screenshot(path=path)  # no await!

# RIGHT — async function, awaited properly:
async def take_screenshot(page, label):
    await page.screenshot(path=path)

# Call from sync context (inside async def launch_observer):
asyncio.get_event_loop().create_task(take_screenshot(page, f"event_{label}"))
```

**Three places this matters:**
1. Initial page load screenshot
2. Periodic 30s heartbeat screenshot
3. Game event triggers (`activeTurn`, `turnComplete`, `setResolutionStep`, `thinkingUpdate`, `announceTurn`)

## Screenshot Triggers

```python
# From console message text (sync handler — use create_task):
if any(k in text for k in ["activeTurn", "turnComplete", "forceShowTurnResolution",
                            "Resolution", "Narrative", "thinkingUpdate", "announceTurn"]):
    asyncio.get_event_loop().create_task(take_screenshot(page, f"event_{ts}"))

# From CDP WebSocket frame (sync handler — use create_task):
if any(k in str(params) for k in ["ui.activeTurn", "ui.turnComplete",
                                    "ui.setResolution", "ui.forceShowTurn"]):
    asyncio.get_event_loop().create_task(take_screenshot(page, f"ws_event_{ts}"))

# Periodic 30s (inside async main loop — await directly):
asyncio.get_event_loop().create_task(take_screenshot(page, f"periodic_{elapsed}s"))
```

## Screenshot Output

- **Dir:** `/tmp/autogenesis-proxy/screenshots/`
- **Format:** `{HHMMSS}_{label}.png` — e.g. `160220_event_160220.png`
- **Size:** ~777KB per PNG (1920×1080 Chromium)

## MiniMax Vision Pipeline

```python
# 1. Screenshot saved by browser_observer
# 2. Send to MiniMax MCP for description:
mcp_MiniMax_understand_image(
    image_source="/tmp/autogenesis-proxy/screenshots/160220_event_160220.png",
    prompt="Describe this screenshot in detail. What game UI elements are visible? "
           "What text is shown? What screen/mode is the game in?"
)
```

**MiniMax correctly identifies:** AUTOGENESIS logo, Guest Commander label, 1,250 diamonds currency, COLLECTION/PLAY buttons, background circuit-pattern aesthetic, version v1.0.0.

## What Browser Observer Captures

**CDP events collected:**
- `Page.console` — all browser JS `console.log/warn/error` output
- `Page.webSocketCreated/Sent/Received/Closed` — WebSocket lifecycle on :9080
- `Page.requestWillBeSent/responseReceived/loadingFinished` — HTTP traffic to :7070/:8080/:9080

**Logs:**
- `/tmp/autogenesis-proxy/browser-YYYYMMDD-HHMMSS.log` — console log
- `/tmp/autogenesis-proxy/network-YYYYMMDD-HHMMSS.jsonl` — HTTP frames

## What It CANNOT Do

KVision's reactive state management has no synchronization layer between DOM click events and internal component state in an automated browser context. Playwright CAN:
- Launch Chromium and navigate
- Read DOM elements and page state
- Capture console logs and network traffic
- Observe WebSocket connections

Playwright CANNOT:
- Make KVision reactive state reflect click events
- Select commanders in collection overlay
- Advance the matchmaking dialog flow

**Implication:** Use browser_observer for passive observation + screenshots. Use Python REST matchmaking for gameplay.

## Entry Point

```bash
/tmp/autogenesis-dev/bin/python debugger/observer/browser_observer.py --visible --hold 900
```

Flags: `--visible` (show browser), `--headless` (run hidden), `--hold N` (keep open N seconds), `--base-url` (default `http://127.0.0.1:8080`).

## mitm_proxy.py Bug Fixed (2026-05-08)

HTTP relay crashed on full URLs: `method, path, _ = request.split()` failed on `GET http://host:port/path HTTP/1.1` (4 tokens vs 3). Fixed with `len(parts) == 4` check. Commit made.