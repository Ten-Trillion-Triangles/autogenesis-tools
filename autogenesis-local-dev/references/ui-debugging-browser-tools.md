# UI Debugging via Browser Tools (No Playwright/Python Required)

When the Python controller is unavailable, the venv is broken, or you just need to verify a UI fix quickly, the built-in browser tools (`browser_navigate`, `browser_console`, `browser_snapshot`, `browser_vision`) are sufficient to reach gameplay and inspect the DOM. This reference documents the full workflow that worked in 2026-06-23 for verifying a DELEGATE button + modal fix.

## Triggering Gameplay UI from the Browser Console

The `?skipLogin=true` mode by itself keeps the browser on the main menu (known limitation: `World.localPlayer` is never set, so `GameplayUI` never initializes). To get to gameplay, fire the matchmaking RPC directly from the browser console using `fetch`:

```javascript
// 1. Get the current SSE playerId from server-extend logs:
//    tail -1 ~/.autogenesis/logs/server-extend-*.log | grep "rest-client"
//
// 2. From the browser console (after navigating to ?skipLogin=true&playerId=YOUR_WS_ID):
fetch('/rpc?playerId=rest-client-XXXXXXXXX&guestMode=true', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    type: 'request', id: 'm1',
    method: 'server.extend.requestGame',
    params: {
      userName: 'LordMapleTree',
      gameType: 'SINGLEPLAYER',
      accelByteId: 'guest-user',
      websocketId: 'YOUR_WS_ID',       // the ?playerId= value
      selectedCommander: null,
      aiOpponentCount: 1,
      aiOnly: false
    }
  })
}).then(r => r.text()).then(t => 'match: [' + t + ']')
```

Empty `[]` response = success. Wait ~8s, then `browser_snapshot` should show the gameplay UI (Game History panel, "Your Turn To Act", score bar, etc.).

**Key pitfall:** the REST/SSE channel uses `rest-client-<timestamp>` playerIds, NOT the `?playerId=` value. The `websocketId` param in the request body must be the `?playerId=` value. Mixing these up returns `"player not connected"`.

## DOM Verification Patterns

Once gameplay UI is loaded, use `browser_console` to inspect elements:

```javascript
// Check if a CSS class is present (e.g., after adding a new button):
document.querySelector('.score-delegate-button')
// Returns the element or null. If null, the JS wasn't reloaded or the add() was missed.

// Check element position and visibility:
const r = document.querySelector('.score-delegate-button').getBoundingClientRect();
// r = {x, y, width, height, top, right, bottom, left} in viewport pixels

// Check computed styles:
const s = window.getComputedStyle(modalEl);
// s.maxHeight, s.overflow, s.position, etc.

// Check what's at a specific viewport point:
document.elementFromPoint(640, 413)?.className

// Find all modals and identify by text:
Array.from(document.querySelectorAll('.login-widget-window'))
  .find(m => m.textContent.includes('DELEGATE INSTRUCTIONS'))
```

## Webpack Cache vs Browser Cache — The Real Culprit

When new code compiles but doesn't appear in the browser, the issue is almost always **browser caching**, not webpack caching. The webpack dev server serves the new bundle immediately after `compileDevelopmentExecutableKotlinJs` finishes. The browser holds onto the old `kvisionApp.js`.

**Verification that webpack is serving new code:**
```bash
# Check if a unique string from your new code is in the served bundle
curl -s "http://127.0.0.1:8080/kvisionApp.js" | grep -c "your-unique-string"
# 1 = new code served. 0 = stale.
```

**Force browser to pick up the new bundle:**
1. Kill webpack: `kill $(ps aux | grep webpack | grep -v grep | awk '{print $2}')`
2. Restart: `./gradlew runKvisionNoHotReload --no-daemon &`
3. Wait for "compiled" message (~35s)
4. Navigate with a cache-busting param: `?skipLogin=true&playerId=YOUR_ID&_=fresh`
5. If still stale, use `browser_console` to clear and re-fetch:
   ```javascript
   caches.keys().then(keys => keys.forEach(k => caches.delete(k)));
   ```

## Screenshot Analysis — Resize Before Sending to Vision

`browser_vision` fails with 413/404 on screenshots > ~500KB. The fix is to resize with ffmpeg first, then analyze with the MiniMax MCP:

```bash
# Resize to 1280px wide (keeps aspect ratio)
ffmpeg -y -i /home/cage/.hermes/cache/screenshots/browser_screenshot_XXXXX.png \
  -vf "scale=1280:-1" -update 1 /tmp/ui_check.png
```

Then use the `mcp_MiniMax_understand_image` tool with `/tmp/ui_check.png` — it's more reliable than the built-in vision for this use case (the built-in vision also times out with "Connection aborted" on complex layouts).

## KVision `add()` Pitfall — Orphaned Panels

A new widget can be created and fully configured but never actually appear in the UI if you forget to call `add()` on the parent. This happened in ScoreDisplay.kt:192 — the DELEGATE button was a `SimplePanel().apply { ... }` with no `add()` call, so it was garbage-collected / never rendered.

**Pattern to watch for:**
```kotlin
// WRONG — panel is created and configured but never added:
SimplePanel().apply {
    addCssClass("my-button")
    // ... configure ...
    span("CLICK ME")
}
// (missing: add(this@ScoreDisplay))

// CORRECT — capture the reference and add it:
val myButton = SimplePanel().apply {
    addCssClass("my-button")
    // ... configure ...
    span("CLICK ME")
}
add(myButton)
```

**How to detect:** if `document.querySelector('.your-css-class')` returns null in the browser console after the page loads, the panel was likely orphaned. Search the Kotlin source for `SimplePanel().apply` or similar factory calls that don't assign to a variable followed by `add()`.

## Modal Positioning Pattern for KVision

The original `DelegateWidget` used `top: 50%; margin-top: -320px` to center a 640px modal. This works for a full-viewport calculation but breaks when the screen has fixed UI bands (score bar at top, command box at bottom). The modal overlaps the command box.

**Robust pattern using CSS inset properties:**
```kotlin
// Anchor the modal to the safe zone between fixed UI bands.
position = Position.FIXED
top = (SCORE_BAR_HEIGHT + MARGIN).px       // e.g., 120px
bottom = (COMMAND_BOX_HEIGHT + MARGIN).px  // e.g., 220px
left = 50.perc
setStyle("transform", "translateX(-50%)")
setStyle("max-height", "calc(100vh - ${SCORE_BAR_HEIGHT + COMMAND_BOX_HEIGHT + 2*MARGIN}px)")
height = io.kvision.core.CssSize(100, io.kvision.core.UNIT.perc)  // fill the safe zone
setStyle("box-sizing", "border-box")
overflow = Overflow.HIDDEN  // clip any content that exceeds the safe zone
```

Combined with `overflow: auto` on the content vPanel, the modal always fits in the safe zone and scrolls internally if content is too tall.
