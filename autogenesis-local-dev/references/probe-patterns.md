# Reusable KVision e2e probe patterns

Patterns that came up repeatedly while writing the resume-game
probes. Each is a small but recurring trap; capturing them here
saves the next session from rediscovering them.

## 1. Dismissing a stale modal overlay before clicking the target

`commander-selection-overlay` is shared between
`CommanderSelectionDialog` and `ResumeOrNewDialog`. When a prior
probe run left a snapshot in VFS, phase 1 of the next probe opens
a `ResumeOrNewDialog` on top of `MainMenu`, which then
`intercepts pointer events` on the underlying `.btn.btn-play` and
the CommanderSelectionDialog's commander rows.

The robust pattern:

```js
async function dismissResumeDialogs(page) {
    for (let i = 0; i < 5; i++) {
        const dialog = page.locator('[data-testid="resume-or-new-dialog"]')
        if (await dialog.count() > 0 && await dialog.first().isVisible()) {
            try {
                await page.locator(
                    '[data-testid="resume-or-new-dialog"] button:has-text("New Game")'
                ).first().click({ timeout: 2_000, force: true })
                await page.waitForTimeout(500)
            } catch (_) {}
        }
        await page.waitForTimeout(200)
    }
}
```

`click({ force: true })` bypasses Playwright's pointer-event
intercept check, which would otherwise block the click on the
"New Game" button when the dialog is partially obscured. After
`dismissResumeDialogs` returns, the underlying MainMenu is reachable.

Use the same pattern for any future KVision `SimplePanel(className =
"commander-selection-overlay")` modal — they all intercept
pointer events on whatever's beneath.

## 2. `data-testid` overlay vs. inner click

A `data-testid` overlay mounted in `KEnv.mainRoot` (the
`commander-selection-overlay` family) will intercept clicks on
inner elements even when those elements are children of the
overlay's own DOM tree. Symptoms:

```
- waiting for locator('text=/AUongfa834nfa/').first()
  - locator resolved to <span>AUongfa834nfa</span>
  - attempting click action
    - <div class="commander-selection-overlay">…</div> intercepts pointer events
```

The fix is `click({ force: true })`:

```js
await page.locator('text=/AUongfa834nfa/').first().click({ force: true, timeout: 5_000 })
```

Force-click is correct here because the click target IS visible
and inside the dialog — Playwright's "intercept" check is too eager
for KVision's overlay DOM.

## 3. Detecting a stable "post-action" messageBox after a submit

`MessageBox` in KVision renders an OK button on success. The probe
needs to wait for the button to appear, click it, and only then
verify the post-action state (e.g. "GameplayUI mounted"). Pattern:

```js
for (let i = 0; i < 30; i++) {
    const okByText = page.getByRole('button', { name: /^OK$/ })
    if (await okByText.count() > 0 && await okByText.first().isVisible()) {
        try { await okByText.first().click({ timeout: 2_000, force: true }) } catch (_) {}
    }
    // also poll for the post-action signal
    const gp = await page.locator('[data-testid="gameplay-ui"]').count()
    if (gp > 0) break
    await page.waitForTimeout(500)
}
```

The poll breaks on whichever signal fires first. If the OK click
chains into the post-action (via `messageBox.onConfirm`), the
post-action signal arrives within 1-2 iterations. If the OK never
appears (e.g. action failed), the loop times out and the probe
asserts on `gameplayPresent: false`.

## 4. Hooking WS frames on the page

To inspect actual WS frames received by the browser, override
`window.WebSocket` BEFORE the page script runs (use
`page.addInitScript`):

```js
await page.addInitScript(() => {
    const origWS = window.WebSocket
    window.__wsFrames = []
    window.WebSocket = function(...args) {
        const ws = new origWS(...args)
        const origAdd = ws.addEventListener.bind(ws)
        ws.addEventListener = function(type, fn, opts) {
            if (type === 'message') {
                const wrapped = (event) => {
                    try {
                        const data = typeof event.data === 'string' ? event.data : '<binary>'
                        window.__wsFrames.push({ url: args[0], data: data.slice(0, 500), ts: Date.now() })
                    } catch(_) {}
                    return fn(event)
                }
                return origAdd(type, wrapped, opts)
            }
            return origAdd(type, fn, opts)
        }
        return ws
    }
    Object.assign(window.WebSocket, origWS)
})

// later, in the probe:
const wsFrames = await page.evaluate(() => window.__wsFrames || [])
for (const f of wsFrames.slice(0, 20)) {
    console.log(`[${new Date(f.ts).toISOString().slice(11,23)}] ${f.url} :: ${f.data.slice(0,200)}`)
}
```

This caught a 700ms race in 2026-06-25 where the
`client.resumeAvailable` notification arrived at the client
BEFORE the listener was registered, and `dispatchNotification`
silently dropped it. Without the frame log, the bug looked like
"the server never pushed" because the modal didn't mount.

## 5. Page-level console filtering for e2e probes

Many false-positive errors come from infrastructure noise:
- `[webpack-dev-server]` HMR warnings
- `Failed to load resource: 504 Gateway Timeout` (HMR polling)
- `WebSocket connection to 'ws://127.0.0.1:8080/ws' failed: Invalid frame header` (HMR WS)
- `bootstrap.min.css` integrity hash mismatch (intentional, see kvision-modal-layout)

Filter these in the probe's `pageerror`/`console` handler:

```js
function isPreExistingNetworkError(text) {
    return text.includes('ERR_CONNECTION_REFUSED') ||
        text.includes('ERR_FAILED') ||
        text.includes('Failed to load resource') ||
        text.includes('coi-serviceworker') ||
        text.includes('favicon.ico') ||
        text.includes('[webpack-dev-server]') ||
        text.includes('integrity') ||
        text.includes('bootstrap.min.css') ||
        ...
}
```

Otherwise the probe's "console errors" tally catches them all and
falsely fails the test. A run that produced zero real errors but
matched 12 of these false positives looks identical to a run that
hit 12 real errors.

## 6. Working with prior session state in VFS

If a prior probe (or manual session) left a snapshot in the
user's AccelByte CloudSave, the next probe's phase 1 may open a
`ResumeOrNewDialog` on top of MainMenu. Two options:

1. **Dismiss in phase 1** (cleanest): use pattern #1 above to click
   "New Game" before starting the seed game. The "New Game" button
   calls `MatchmakingClient.clearRunningGame()` (best-effort) which
   writes a consumed sentinel, so the next phase 2 doesn't see a
   stale snapshot either. (See `MainMenu.kt:301`.)
2. **Seed deterministically**: before phase 1, hit
   `MatchmakingClient.clearRunningGame()` directly via
   `page.evaluate(() => window.MatchmakingClient.clearRunningGame())`
   if the bridge is exposed for testing. (Currently NOT exposed —
   only MainMenu's flow can call it. So pattern #1 is the
   workaround.)

Pattern #1 is preferred — it tests the real flow including the
"discard the save" path, and doesn't require additional test
surface on the bridge.

## 7. Probe file location and naming

`kvisionApp-e2e/probes/` is the directory for new e2e probes.
Naming convention: `<verb>-<subject>.mjs` or `<what-it-tests>.mjs`.
Existing examples:
- `guest-login.mjs` — just guest login + MainMenu mount
- `wait-for-modal.mjs` — minimal: wait for ResumeOrNewDialog
- `resume-e2e.mjs` — full resume-game lifecycle

Each probe should be runnable standalone with `node <name>.mjs`
and exit 0 on success / 1 on failure. Set `BASE_URL` env var to
override the default `http://127.0.0.1:8080`.

## 8. KVision `position: fixed` widgets need `dispatchEvent`, not `click()`

KVision modals / dialogs / settings widgets commonly use
`position: fixed`. When you drive them through Playwright, the
`.click({ force: true })` shortcut does NOT bypass Playwright's "is
element visible" check — the widget can be rendered and clickable
from the user's perspective yet fail the visibility check
(off-viewport, transform-ancestor, etc.).

**Symptom:**
```
Error: locator.click: Element is not visible
Call log:
  - waiting for locator('button.btn-surrender').first()
  - locator resolved to <button ...>…</button>
  - attempting click action
  - scrolling into view if needed
```

**Fix:** dispatch the click directly from `page.evaluate`:
```js
await page.evaluate(() => {
    const btn = document.querySelector('button.btn-surrender')
    if (!btn) return { ok: false, error: 'btn-surrender not in DOM' }
    btn.dispatchEvent(new MouseEvent('click', {
        bubbles: true, cancelable: true, view: window
    }))
    return { ok: true }
})
```

`dispatchEvent` invokes the registered KVision onClick handler without
Playwright's visibility check. Confirmed 2026-06-26 with the
surrender-flow probe — `click({ force: true })` failed with
"Element is not visible" but `dispatchEvent` succeeded.

**Text-content matching vs CSS-class hooks:**
KVision buttons frequently use `<button>YES, SURRENDER</button>`
where the actual class is `btn btn-surrender-confirm`. CSS-class
selectors are more stable than text matches because translators and
styling changes can rename the text. The match buttons in
`SurrenderConfirmDialog.kt:148-180` are labeled "NO" / "YES, SURRENDER"
with classes `btn-secondary` / `btn-surrender-confirm`.

## 9. Detecting the local player name from Playwright DOM

Three sources exist for the local player's name; only one is
reliably reachable from DOM scraping:

- **Trace log** (`[TRACE] [GameplayUI.updateWorldState] LocalPlayerName: 'X'`) —
  written to browser console, NOT the DOM. `document.body.textContent`
  does not see it.
- **Leaderboard entry** (`1. AUongfa834nfa 17 VP`) — inside a modal
  with `display: none` but DOM-present. Regex works after
  `document.body.innerText` (which collapses whitespace).
- **Footer span** (`Active actor: AUongfa834nfa`) — always visible
  while gameplay is mounted. Most reliable signal.

Pattern from `resume-snapshot-cleared-on-game-over.mjs`:
```js
return await page.evaluate(() => {
    const text = document.body.innerText
    const m1 = text.match(/Active actor:\s*([A-Za-z0-9_]+)/)
    if (m1) return m1[1]
    // Fallback: leaderboard regex (text must collapse whitespace first)
    const re = /(\d+)\.\s*([A-Za-z0-9_]+)\s+(\d+)\s+VP/g
    let m, first = ''
    while ((m = re.exec(text)) !== null) {
        if (!first) first = m[2]
    }
    return first
})
```

When all DOM detection fails, fall back to a hardcoded known name
("AUongfa834nfa" for the test master record) and let the RPC
response or visible error detect a mismatch with a loud failure.

## 10. Chaining UI clicks through `page.evaluate` for hidden modals

When the e2e flow requires clicking through a chain of modals
(e.g., SETTINGS button → opens SettingsWidget → click SURRENDER
→ opens SurrenderConfirmDialog → click YES, SURRENDER), the
cleanest pattern is to chain `page.evaluate` calls with explicit
waits for the next modal's DOM:

```js
// 1. SETTINGS gear (Playwright .click works here — button is in viewport)
const settingsBtn = page.locator('button.action-button:has-text("SETTINGS")').first()
await settingsBtn.click({ force: true, timeout: 5_000 })

// 2. Wait for the settings widget to mount
await page.waitForFunction(() =>
    Array.from(document.querySelectorAll('h4')).some(h =>
        h.textContent.includes('Game Settings')),
    { timeout: 5_000 }).catch(() => {})

// 3. SURRENDER (KVision position:fixed widget — use dispatchEvent)
const surrenderResult = await page.evaluate(() => {
    const btn = document.querySelector('button.btn-surrender')
    if (!btn) return { ok: false, error: 'btn-surrender not in DOM' }
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    return { ok: true }
})

// 4. Wait for the confirm dialog
await page.waitForFunction(() =>
    !!document.querySelector('button.btn-surrender-confirm'),
    { timeout: 5_000 }).catch(() => {})

// 5. Confirm (same position:fixed widget)
await page.evaluate(() => {
    const yesBtn = document.querySelector('button.btn-surrender-confirm')
    yesBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
})
```

`waitForFunction` with `.catch(() => {})` on a timeout is intentional
— it lets the next `evaluate` fail with a clear "X not in DOM"
message instead of throwing on the wait itself. Captured 2026-06-26
while writing the surrender-driven game-over probe.

## 11. `matchMedia` mobile-layout attribute pattern

When adding mobile-portrait support to a KVision widget, the CSS lives
in `night-mode.css` under the `@media (max-width: 600px)` block — NOT in
KVision's `Style.create` DSL. The Kotlin/JS widget attaches a
`matchMedia` listener that sets `data-mobile-layout` on the widget's root
DOM node. This pattern is used by LoadingScreen and CollectionOverlay.

**Why not `Style.create`:** `io.kvision.core.Style` in kvision-js 9.1.1
does not expose a static `create` method to the Kotlin/JS target. The
documented API path is on a separate kvision sub-module not present in
the JS-only runtime. night-mode.css is the load-bearing source of truth.

**Comment block to include (verbatim, widget-name-adapted):**
```kotlin
// Note: The mobile-portrait CSS rules live in night-mode.css under the
// `@media (max-width: 600px)` block at the end of the file. We do not
// mirror them via KVision's Style.create DSL here because the
// io.kvision.core.Style class in kvision-js 9.1.1 does not expose a
// static `create` method to the Kotlin/JS target (the documented API
// path is on a separate kvision sub-module not present in the JS-only
// runtime). The CSS file approach is the load-bearing source of truth
// and is loaded by the browser before this widget mounts.

// Live rotation handling: when the viewport width crosses the 600px
// breakpoint (typically a phone rotation), update the data-mobile-layout
// attribute on the root so e2e probes can verify the layout state and
// any future code that needs to react to layout change has a stable hook.
```

**Listener block (inside `init { }` of a `SimplePanel` subclass):**
```kotlin
kotlinx.coroutines.GlobalScope.launch {
    try {
        val mediaQuery = kotlinx.browser.window.matchMedia(
            "(max-width: 600px), (max-height: 600px) and (orientation: portrait)"
        )
        val updateAttribute: (Boolean) -> Unit = { matches ->
            setAttribute("data-mobile-layout", if (matches) "portrait" else "desktop")
        }
        updateAttribute(mediaQuery.matches)
        mediaQuery.addEventListener("change", { event ->
            val mql = event.asDynamic()
            updateAttribute(mql.matches as Boolean)
        })
        Logger.info(LogCategory.UI, "WidgetName: matchMedia listener attached, current state=${if (mediaQuery.matches) "portrait" else "desktop"}")
    }
    catch (err: Throwable) {
        Logger.warn(LogCategory.UI, "WidgetName: matchMedia listener failed to attach (non-fatal): ${err.message}")
    }
}
```

**Important: receiver qualification** — the receiver inside `GlobalScope.launch`
is the coroutine, not the widget. Inside `launch { ... }`, use
`this@ClassName.setAttribute(...)` explicitly so the attribute is set on
the SimplePanel root DOM node, not on `Unit`.

**The `data-mobile-layout` attribute convention:**
- `"portrait"` — matches the night-mode.css mobile breakpoint
- `"desktop"` — everything else (including landscape tablets)
- Probes assert `data-mobile-layout="portrait"` to confirm the
  listener fired

**`CollectionOverlay` specifics (verified 2026-07-10):**
- `class CollectionOverlay : SimplePanel(className = "collection-overlay")`
  — root has `className = "collection-overlay"`, NO `data-testid`
  (probes must use `.collection-overlay` class selector)
- Sub-windows use `className = "login-widget-window"`
  (CommanderDetailWindow, StoryDetailWindow both extend this)
- Tab buttons use `.collection-tab-button` /
  `.collection-tab-button-active` CSS classes
- The mobile-portrait probe:
  `kvisionApp-e2e/probes/collection-overlay-mobile-portrait.mjs`
- iPhone 12 (390x844) viewport; tap-target assertions:
  tab button height ≥ 48px, width ≥ 44px

## 12. Reference

See `references/resume-game-snapshot-lifecycle.md` for the snapshot's
four trigger paths and the `hasRunningGame` race-recovery gotcha
that bit a unit test in 2026-06-26 (must clear
`WorldManager.playerStats` after the deletion to simulate WS-close
when asserting `hasRunningGame == false`).
