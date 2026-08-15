# Playwright Screenshot Capture Recipe — Autogenesis UI Documentation

## Goal
Capture a screenshot album of the entire Autogenesis UI flow for documentation / debugging / QA:
- Loading screen
- Login screen (all auth buttons)
- Main menu (incl. resume dialog overlay, menu items)
- Commander selection wizard (step 1 + step 2 + match-starting modal)
- Active gameplay UI (leaderboard, turn order, phase tracker, widgets)
- Game-state map view (after clicking "Go To Map" from the "Your Turn To Act" splash)
- Phase screens (Start / Action / Planning / Writing / Judging / Dispatch / NPCs / World)
- Widget overlays (RESOURCES, STATS, WORLD, SETTINGS)
- Stats menu tabs (Player Stats / NPC Stats / Territories / Turn Order)
- Game History tabs (Story / Details / Geopolitics / Work Stream)

Output: PNGs to `~/Desktop/Workspaces/Autogenesis/screenshots/` (one above repo root) — works equally well for any other one-level-up output path.

## Prerequisites
- All three servers up: `:server:run` (port 9080), `:server-extend:run` (port 7070), `:kvisionApp:jsBrowserDevelopmentRun` (port 8080)
- `@playwright/test` import path: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/@playwright/test/index.mjs`
- Viewport: **1920x1080** — captures full UI including bottom command bar; 1280x800 cuts off widgets
- Start `:server:run` with `AUTOGENESIS_SHUTDOWN_DELAY_MS=1800000` (30 min) for phase-capture workflows — the default 10-minute window is too tight once the WebSocket session ends and the AI pipeline takes ~5 minutes per cycle

## Reference starting point
Existing pattern at `~/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/capture-screenshot.mjs` already shows:
- Loading screen CTA click via `getByTestId('loading-screen-cta')`
- Login As Guest via `getByTestId('login-as-guest')` or button role
- Resume dialog force-click (`{ force: true, timeout: 10_000 }`)
- Match Resumed modal OK-button dismissal (`dismissMessageBoxes` helper)

For a full GUI walk-through (not just resume probe), you need the additional wizard + gameplay UI steps below.

## Critical Gotchas

### 1. KVision reactive handlers need DOM-event dispatch OR real mouse click
Playwright's `force: true` `.click()` is unreliable on KVision `onClick` handlers. Two reliable patterns:

```js
// Pattern A — DOM click with event dispatch (works for most buttons)
await page.evaluate(() => {
    const el = document.querySelector('.commander-selection-card')
    if (el) { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); el.click() }
})

// Pattern B — REAL MOUSE CLICK at element center (most reliable; use this for clickable cards)
const card = await page.evaluate(() => {
    const c = document.querySelector('.commander-selection-card')
    if (!c) return null
    const r = c.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
})
if (card) await page.mouse.click(card.x, card.y)
```

### 2. Dialog-scoped button queries — wizard overlay looks identical to main menu
When the commander wizard (or any dialog) is open, it overlays the main menu. The wizard and main menu both have buttons named "Play" / "Cancel" / "Back". ALWAYS scope queries to the dialog:

```js
// WRONG — pages have TWO "Play" buttons; first match might be main menu's
await page.evaluate(() => {
    for (const b of document.querySelectorAll('button'))
        if (b.textContent.trim() === 'Play') { b.click(); return }
})

// RIGHT — wizard dialog has distinct CSS class to scope to
await page.evaluate(() => {
    const dialog = document.querySelector('.commander-selection-overlay, .commander-selection-window')
    if (!dialog) return
    for (const b of dialog.querySelectorAll('button'))
        if (b.textContent.trim() === 'Play') { b.click(); return }
})
```

### 3. Resume dialog appears from server-extend SSE, NOT a direct click
On fresh login, `client.resumeAvailable` RPC fires ~50-200ms after WS rebind. The Resume dialog (`[data-testid="resume-or-new-dialog"]`) overlays the main menu. Handle this **before** any other flow — otherwise the modal's pointer-event capture blocks main-menu PLAY clicks.

The right way to dismiss: click **"New Game"** specifically (NOT "OK", which is generic and might dismiss unrelated modals):

```js
await page.evaluate(() => {
    const d = document.querySelector('[data-testid="resume-or-new-dialog"]')
    if (d && d.offsetWidth > 0) {
        for (const b of d.querySelectorAll('button'))
            if (b.textContent.trim() === 'New Game') { b.click(); return }
    }
})
```

Polling version (waits up to 15s for the dialog to appear):
```js
for (let i = 0; i < 30; i++) {
    const clicked = await page.evaluate(() => {
        const d = document.querySelector('[data-testid="resume-or-new-dialog"]')
        if (!d || d.offsetWidth === 0) return false
        for (const b of d.querySelectorAll('button'))
            if (b.textContent.trim() === 'New Game') { b.click(); return true }
        return false
    })
    if (clicked) break
    await sleep(500)
}
```

### 4. THREE different "Play" buttons with different casing
Confirmed 2026-07-01 — three buttons all called "Play" exist on the same page during wizard flow:
- **Main menu PLAY** (all caps): `<button>PLAY</button>` — open the wizard
- **Wizard step 1 Next → step 2 Play** (title case): `button("Play", ...)` at `TurnResolutionWidget.kt:235` INSIDE `.commander-selection-window` dialog only
- **Gameplay command Send** (title case, *but it says "Send"*): `button("Send", ...)` at `CommandBox.kt:106` — submits the player's action to the AI work stream

Always read `.textContent.trim()` exact-match. Lowercasing the comparison will mix them up. The Send button is TITLE CASE not all-caps — be exact.

### 5. "Go To Map" button — character-case sensitive
The button in the "Your Turn To Act" prompt is exactly **"Go To Map"** (camelCase, not "GO TO MAP"). After initial capture runs used uppercase match and missed it; the case-insensitive regex `/Go To Map/i` is safer:

```js
await page.evaluate(() => {
    for (const b of document.querySelectorAll('[data-testid="gameplay-ui"] button'))
        if (/Go To Map/i.test(b.textContent) && b.offsetWidth > 0) { b.click(); return }
})
```

### 6. After wizard Play, "Match Ready" modal appears
`beginSinglePlayerSession` shows a MessageBox:
- Title: `"Matchmaking"` → `"Match Ready"`
- Body: `"Local session configured. Opening gameplay."`
- Single OK button (no throbber / no spinner on the success modal)

Dismiss via the standard `dismissMessageBoxes` helper (already in `kvisionApp-e2e/capture-screenshot.mjs`). The modal ONLY has an OK button after the RPC resolves — earlier dismissals may dismiss nothing.

### 7. Chunked pipeline populates map + leaderboard SLOWLY
`gameplay-ui` mount is fast (~1-3s), but the leaderboard widget and map views take ~12-15s more to populate (chunked WS frames reassembled by `MultipartAssembler`). After `gameplay-ui` appears, **wait AT LEAST 25 seconds** before screenshotting full state. Less than 20s and you'll capture empty widgets.

```js
await page.waitForFunction(() => document.querySelector('[data-testid="gameplay-ui"]') !== null, { timeout: 45000 })
await sleep(3000)               // initial mount
await shot('gameplay-initial')
await sleep(25000)              // chunked pipeline settles
await shot('gameplay-state-populated')
```

### 8. Game-state map only opens after clicking "Go To Map"
The initial gameplay splash shows "Your Turn To Act" with the Send button at the bottom. The **map view with territory icons** (40-50 territory DIVs all marked `data-testid="territory-icon"`, some with class `territory-idle-owned` for owned) appears ONLY after clicking the "Go To Map" button on that splash. Pins inside (crown / castle / cactus / pink numbered badges / skull threats) are CSS-styled descendants — no separate testid.

### 9. KVision controlled-input needs native-value-setter bypass for "Send"
The CommandBox textarea has `onInput { applyCommanderFilter() }` (and the wizard's search field has similar KVision-style controlled inputs). Plain `input.value = "..."` + `dispatchEvent(new Event('input', {bubbles: true}))` is intercepted and the value never reaches internal state. Use the React-style native-setter pattern:

```js
const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
    || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
if (setter) setter.call(input, text)
else input.value = text
input.dispatchEvent(new Event('input', { bubbles: true }))
input.dispatchEvent(new Event('change', { bubbles: true }))
```

### 10. Server shutdown: only kill what you started
When running screenshot capture, the user has likely left their own webpack (port 8080 or 8081) and server-extend (port 7070 / 9092) running. ONLY kill the `:server:run` JVM (port 9080 / 9091) you started yourself.

```bash
# CORRECT — only stop the game server you started
pkill -f ":server:run"      # or use process.kill on the background session

# WRONG — kills user's webpack and server-extend too
pkill -f webpack
pkill -f "java.*server-extend"
```

**Verification pattern (don't just say "shut down" — show the receipt):**

```bash
ss -tlnp | grep -E ":(7070|8080|9080|9091|9092)"
# Expected after a clean screenshot-capture shutdown:
#   7070, 8080, 9092 still listening (user's pre-existing services, preserved)
#   9080, 9091 NOT in the list (your game-server JVM, killed)
```

Lead the post-shutdown message with the `ss -tlnp` output, then the killed PID(s), then a one-line summary. Phrasing like "stands down" / "Ent Army rests" / "war council adjourned" reads as ambiguous — the operator has flagged passive narrative as a shutdown failure mode. An actual receipt (port check + PIDs + exit code) is what counts.

### 11. Game server has self-shutdown timer
Without `AUTOGENESIS_SHUTDOWN_DELAY_MS=600000`, the game server self-terminates 15s after the last session disconnects. For phase-capture workflows that need 5+ minutes per AI cycle, bump to 1800000 (30 min). Setting 600000 (10 min) is enough for ~2 full cycles.

## Wizard Flow Cheat Sheet

| Step | Visible UI | Button text | Notes |
|---|---|---|---|
| 1 | "Select Commander" dialog with commander list | Card click → "Next" | NEXT is disabled until a card is clicked |
| 2 | "Choose Game Settings" — Game Type cards, Match Configuration | "Back" / "Play" | Default: Single Player + 1 AI opponent (Players: 2) |
| — | (no separate step 3 — wizard step 2's "Play" starts matchmaking) | (Play clicked) | Server RPC `requestSinglePlayerMatch` runs after click |
| Post | "Contacting local game server..." throbber → "Match Ready" | OK on Match Ready | Dismisses modal + instantiates GameplayUI on the stack |
| Gameplay splash | "Your Turn To Act" + Send button | "Send" (title case) + "Go To Map" (camelCase) | Send submits command; Go To Map opens the game-state map |
| Gameplay tabs | Game History (Story/Details/Geopolitics/Work Stream) + Resources/Stats/World/Settings widgets | various | See "Game History tabs" section below |

## Full Capture Recipe (Node.js)

```js
import { chromium } from '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/@playwright/test/index.mjs'

const OUT_DIR = '/home/cage/Desktop/Workspaces/Autogenesis/screenshots'
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
let i = 0
const shot = async (name) => {
    const fn = `${String(++i).padStart(2,'0')}-${name}.png`
    await page.screenshot({ path: `${OUT_DIR}/${fn}`, fullPage: true })
    console.log(`SAVED ${fn}`)
}

const dismissMessageBoxes = async () => {
    for (let i = 0; i < 30; i++) {
        const ok = await page.evaluate(() => {
            for (const ov of document.querySelectorAll('.autogenesis-message-box-overlay, [class*="modal"], [class*="popup"]')) {
                if (ov.offsetWidth === 0) continue
                for (const b of ov.querySelectorAll('button'))
                    if (/^ok$/i.test(b.textContent.trim())) { b.click(); return true }
            }
            return false
        })
        if (ok) return
        await sleep(300)
    }
}

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
const page = await ctx.newPage()

// 1. Loading screen
await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'domcontentloaded' })
await page.getByTestId('loading-screen-cta').waitFor({ state: 'visible' })
await sleep(2000)
await shot('loading-screen')

// 2. Click through to Login
await page.getByTestId('loading-screen-cta').click()
await page.getByRole('button', { name: 'Login As Guest' }).waitFor({ state: 'visible' })
await sleep(1500)
await shot('login-screen')

// 3. Login As Guest + dismiss Resume dialog via "New Game"
await page.getByTestId('login-as-guest').first().click()
await sleep(2500)
const resumeDismissed = await page.evaluate(() => {
    const d = document.querySelector('[data-testid="resume-or-new-dialog"]')
    if (!d || d.offsetWidth === 0) return false
    for (const b of d.querySelectorAll('button'))
        if (b.textContent.trim() === 'New Game') { b.click(); return true }
    return false
})
if (resumeDismissed) console.log('Resume dialog dismissed via New Game')
await sleep(3000)

// 4. Main menu
await page.locator('[data-testid="main-menu"]').waitFor({ state: 'visible' })
await sleep(2000)
await shot('main-menu')

// 5. Click PLAY (main menu's button, all caps)
await page.evaluate(() => {
    for (const b of document.querySelectorAll('[data-testid="main-menu"] button'))
        if (b.textContent.trim() === 'PLAY') { b.click(); return }
})
await sleep(3000)
await shot('wizard-step1-commander-select')

// 6. Click first commander card via real mouse click
const card = await page.evaluate(() => {
    const c = document.querySelector('.commander-selection-card')
    if (!c) return null
    const r = c.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
})
if (card) await page.mouse.click(card.x, card.y)
await sleep(1500)
await shot('wizard-step1-commander-clicked')

// 7. Click Next INSIDE dialog
await page.evaluate(() => {
    const dialog = document.querySelector('.commander-selection-overlay, .commander-selection-window')
    for (const b of dialog.querySelectorAll('button'))
        if (b.textContent.trim() === 'Next') { b.click(); return }
})
await sleep(2500)
await shot('wizard-step2-game-settings')

// 8. Click Play INSIDE dialog (NOT main menu)
await page.evaluate(() => {
    const dialog = document.querySelector('.commander-selection-overlay, .commander-selection-window')
    for (const b of dialog.querySelectorAll('button'))
        if (b.textContent.trim() === 'Play') { b.click(); return }
})
await sleep(4000)
await shot('match-starting')

// 9. Dismiss Match Ready modal
await dismissMessageBoxes()
await sleep(3500)

// 10. Wait for gameplay-ui + populate state
await page.waitForFunction(() => document.querySelector('[data-testid="gameplay-ui"]') !== null, { timeout: 45000 })
await sleep(3000)
await shot('gameplay-initial')
await sleep(25000) // chunked pipeline populates leaderboard + map
await shot('gameplay-state-populated')

// 11. Click "Go To Map" (camelCase!) — opens the GAME-STATE map
await page.evaluate(() => {
    for (const b of document.querySelectorAll('[data-testid="gameplay-ui"] button'))
        if (/Go To Map/i.test(b.textContent) && b.offsetWidth > 0) { b.click(); return }
})
await sleep(8000)
await shot('gameplay-map-view')
await sleep(5000)
await shot('gameplay-map-with-pins')

// 12. Widget overlay shots
for (const label of ['RESOURCES', 'STATS', 'WORLD', 'SETTINGS']) {
    await page.evaluate((l) => {
        for (const b of document.querySelectorAll('[data-testid="gameplay-ui"] button'))
            if (new RegExp(l, 'i').test(b.textContent) && b.offsetWidth > 0) { b.click(); return }
    }, label)
    await sleep(2500)
    await shot(`gameplay-${label.toLowerCase()}-widget`)
}

await browser.close()
```

## Stats Widget tabs (Player Stats / NPC Stats / Territories / Turn Order)

The StatsWidget has 4 tabs (defined at `kvisionApp/src/jsMain/kotlin/ui/gameplay/StatsWidget.kt:44`). After clicking the main STATS button (step 12 above), iterate the tab buttons inside the dialog:

```js
// Open stats dialog first (already done in step 12)
// Now cycle the tabs — buttons are inside the `.login-widget-window` dialog
for (const tabText of ['Player Stats', 'NPC Stats', 'Territories', 'Turn Order']) {
    await page.evaluate((t) => {
        const dialogs = document.querySelectorAll('.login-widget-window')
        for (const d of dialogs) {
            if (d.offsetWidth === 0) continue
            for (const b of d.querySelectorAll('button'))
                if (b.textContent.trim() === t) { b.click(); return }
        }
    }, tabText)
    await sleep(2500)
    await shot(`stats-${tabText.toLowerCase().replace(/\s+/g, '-')}-tab`)
}
```

All 4 tabs populate even when the underlying world data is partial (Player list shows the local player + opponent without further data — verify the screenshot includes both name rows + Resources/Territories/Info buttons per player).

## Game History tabs (Story / Details / Geopolitics / Work Stream)

Same pattern but the history tabs are inside the GameplayUI root (NOT inside a `.login-widget-window` modal):

```js
for (const tabText of ['Story', 'Details', 'Geopolitics', 'Work Stream']) {
    await page.evaluate((t) => {
        for (const b of document.querySelectorAll('[data-testid="gameplay-ui"] button'))
            if (b.textContent.trim() === t && b.offsetWidth > 0) { b.click(); return }
    }, tabText)
    await sleep(2000)
    await shot(`history-tab-${tabText.toLowerCase().replace(/\s+/g, '-')}`)
}
```

These tabs appear above the phase tracker (NOT in a modal); the `.gh-tab-button` class is the visual hook but the click handler reads the same button text.

## Capturing the 9 phase pages (Start / Action / Planning / Writing / Judging / Dispatch / NPCs / World / Counter)

The phase pages live inside `TurnResolutionWidget` (`kvisionApp/src/jsMain/kotlin/ui/gameplay/TurnResolutionWidget.kt:40`). The class has a `demoMode: Boolean` constructor parameter and `showStart() / showPlayerAction() / showIntent() / showStory() / showJudgement() / showDispatch() / showNpcs() / showWorld() / showCounter()` methods that drive the StoryStreamingPage / JudgementSummaryPage / DispatchResourcesPage / etc. inner pages.

### Phase-page captures ARE scriptable today via real-turn polling

**Discovered 2026-07-01 (after 4 failed attempts):** the breakthrough path is to submit a real turn through the UI, then poll `.fa-pulse` on the phase icons as the AI cycle advances. Two non-obvious gotchas — both worth their own paragraphs because they broke every earlier attempt:

1. **The Send button is exactly `"Send"` (title case), not `"SEND"`.** See `kvisionApp/src/jsMain/kotlin/ui/gameplay/CommandBox.kt:106`: `button("Send", className = "btn btn-play") { ... }`. The wizard Play button is `"Play"` (line 235 of TurnResolutionWidget.kt — title case, used INSIDE dialog only). The main-menu Play button is `"PLAY"` (all caps). Three different Play buttons — all with different casing. ALWAYS read `.textContent.trim()` exact-match, never lowercase.

2. **The CommandBox textarea needs a native setter bypass for KVision's controlled-input handling.** Plain `input.value = "..."` followed by `input.dispatchEvent(new Event('input', {bubbles: true}))` is intercepted by KVision's `onInput { applyCommanderFilter() }` handler (TurnResolutionWidget.kt) and the value never reaches internal state. The right pattern:

```js
const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
    || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
if (setter) setter.call(input, text)
else input.value = text
input.dispatchEvent(new Event('input', { bubbles: true }))
```

This is the same React-controlled-input pattern (because KVision is the React-equivalent on the JS side). After typing + Send click, the AI work stream fires and the phase icons advance cyan-color with `.fa-pulse`.

### Working capture recipe (verified end-to-end 2026-07-01)

Captures all 8 of the operator-named phases (Start through World — Counter is the 9th, normally skipped because the loop returns to player after World) plus `phase-writing-screen.png` and `phase-writing-screen-streaming.png` snapshots during the Writing phase. Total cycle time was ~5 minutes from typing the command to capturing World.

```js
// After gameplay-ui is mounted, find the visible textarea in the command box
const inputInfo = await page.evaluate(() => {
    const inputs = document.querySelectorAll('[data-testid="gameplay-ui"] input, [data-testid="gameplay-ui"] textarea')
    for (const i of inputs) {
        if (i.offsetWidth > 0 && !i.disabled) {
            return { tag: i.tagName, type: i.type, w: i.offsetWidth }
        }
    }
    return null
})

// Type the command via native setter
await page.evaluate((text) => {
    const input = document.querySelector('[data-testid="gameplay-ui"] input[type="text"], [data-testid="gameplay-ui"] textarea')
    if (!input) return
    input.focus()
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
        || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    if (setter) setter.call(input, text)
    else input.value = text
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
}, 'Establish a forward outpost in the southern territory and dispatch scouts to map the local resources.')

// Click Send (TITLE CASE — NOT "SEND")
await page.evaluate(() => {
    for (const b of document.querySelectorAll('[data-testid="gameplay-ui"] button, button')) {
        if (b.textContent.trim() === 'Send' && b.offsetWidth > 0) {
            b.click()
            return
        }
    }
})

// Poll for phase transitions via .fa-pulse class on active phase icon
const phaseClasses = {
    Start: 'fa-flag', Action: 'fa-terminal', Planning: 'fa-brain',
    Writing: 'fa-pen-nib', Judging: 'fa-gavel', Dispatch: 'fa-truck-loading',
    NPCs: 'fa-users', World: 'fa-globe-americas', Counter: 'fa-exclamation-triangle'
}
const phaseNames = Object.keys(phaseClasses)
let lastPhaseIdx = -1

for (let elapsed = 0; elapsed < 25 * 60 * 1000; elapsed += 2000) {
    const state = await page.evaluate((pc) => {
        const active = []
        for (const ic of document.querySelectorAll('.fa-pulse')) {
            const cn = ic.className
            for (const [phase, cls] of Object.entries(pc)) {
                if (cn.includes(cls)) { active.push(phase); break }
            }
        }
        return {
            active,
            isMyTurn: /Your Turn To Act/i.test(document.body.textContent),
            hasNarrative: /atmospheric|displacement|unnatural|sequence|narrative|suddenly/i.test(document.body.textContent)
        }
    }, phaseClasses)
    for (const phase of state.active) {
        const idx = phaseNames.indexOf(phase)
        if (idx > lastPhaseIdx) {
            lastPhaseIdx = idx
            await page.screenshot({ path: `${OUT_DIR}/phase-${String(idx).padStart(2,'0')}-${phase.toLowerCase()}.png`, fullPage: true })
            console.log(`SAVED phase-${idx}-${phase}`)
        }
    }
    // Stop early when loop completes (back to player turn)
    if (state.isMyTurn && lastPhaseIdx >= 6) break
    await new Promise(r => setTimeout(r, 2000))
}
```

### What you'll see in each captured phase (verified 2026-07-01)

- **phase-00-start.png**: game history panel populated for Turn 1, prompt text: "Establish a forward outpost in the southern territory..."
- **phase-01-action.png**: early Action processing
- **phase-02-planning.png**: "Agent Planning... / Analyzing world state and formulating strategy" with rotating gear icon
- **phase-03-writing.png**: Writing icon highlighted BLUE, "Generating narrative..." status, green cursor blinking in the central black box — **THE WRITING SCREEN** (this is what the operator wanted)
- **phase-04-judging.png**: "Evaluating Outcomes... / The AI is judging the consequences of actions" with circular loading spinner
- **phase-05-dispatch.png**: "Dispatching Resources..." with full narrative visible in Game History (Arkansas outpost, "The First Silence", Free Memphis Enclave militia), acquired items: Bottled Tears, The Map That Sees, Alien Transmitter, "Secured: Arkansas" hyperlink
- **phase-06-npcs.png**: NPC updates
- **phase-07-world.png**: "Updating World State... / Applying global changes and territory shifts" with spinning globe

### Server requirements for the phase capture

- `:server:run` started with `-DAUTOGENESIS_SHUTDOWN_DELAY_MS=1800000` (30 minutes) — the default 10-minute window is too tight once the WebSocket session ends (the operator's `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000` env var shortens the AI's turn cycle to 5s, but the overall pipeline still takes ~5 minutes). For longer AI work cycles, bump to 30min.
- Wait for the AI work stream actually running — the `.gh-tab-glow` class on the Geopolitics tab is the live indicator. If absent for >30s after Send click, the AI provider timed out and the phase loop will stall.

### Why this works where earlier attempts failed

Two earlier attempts to drive phase screens from Playwright failed; both blocked by the same root cause but different surface symptoms:

1. **`window.gameplayUI.turnResolutionWidget_1.showStory()` returns undefined.** When `?testMode=true` is in the URL, `window.gameplayUI` is exposed (`GameplayUI.kt:84`); the field name is `<fieldName>_1` per KVision's compiled wrapper. But the `showStory/showStart/etc.` methods are NOT callable directly from JS because KVision's compiled output wraps every styled-property as `$delegate_1`. The only thing callable on `turnResolutionWidget_1` is the KVision property setters (`width$delegate_1`, `display$delegate_1`, etc.). To prove what's reachable, dump: `Object.getOwnPropertyNames(window.gameplayUI).filter(k => !k.includes('$delegate'))` — the actual widget method names do not appear.

2. **`TurnResolutionWidget` has `demoMode = false` hardcoded in `GameplayUI.kt:298`.** No URL parameter, query string, env var, or runtime flag toggles it. `DemoFixtures.buildDemoWorld()` exists at `kvisionApp/src/jsMain/kotlin/ui/gameplay/DemoFixtures.kt:261` and is the canonical seed for demo-mode — but GameplayUI never instantiates the widget with `demoMode = true`.

The path forward if the operator wants repeatable phase captures without LLM latency:
- **(b) Patch `GameplayUI.kt:298` to flip `demoMode = true` and rebuild `:kvisionApp:compileSync`.** NOT a screenshot-tool change — it's a product change. Only do this if the operator explicitly approves a code change for demo-mode support.
- **(c) Add a URL parameter `?turnDemoMode=true` that wires to `GameplayUI.kt:298`.** Same scope as (b). The right long-term answer if the operator wants repeatable phase captures without LLM latency.

The new option (a) recipe above captures all 9 phase pages reliably within ~5 minutes per cycle (LLM call times dominate) — so for documentation purposes, this is the path to take until demoMode support lands.

## Known UI Oddities (observed 2026-07-01)

- **Commander AUongfa834nfa's bio is keyboard-smash gibberish** (`EEEEEEEEEEE EE EEEEEEEEEEEE EEE EEEEEEEEEEEEEEEEE EE, E, EE, EEE...`). Pre-existing placeholder in user's saved commander profile. Not a parser bug — the data really is that text. Likely worth a cleanup PR but unrelated to capture workflow.
- **AI work stream glow** (`.gh-tab-glow` class) appears on the Geopolitics tab while the AI is processing turns. Use as positive signal that the AI agent is actively thinking, independent of any body-text indicator (the `Your Turn To Act` overlay is always re-rendered regardless of whose turn it is).
- **`Active actor: AUongfa834nfa`** appears in the gameplay UI. This is the HUMAN player's identity string, shown during BOTH the human's turn AND while waiting for the AI (the prompt overlay is always rendered). Don't use it as a turn-state signal — use `.gh-tab-glow` presence or server logs (`Resolved actor='...'`) instead.

## Cheat Sheet: capturing additional UI elements that the basic recipe misses

- **`Go To Map`** → opens Map Viewer with territory pins (already in recipe step 11)
- **`STATS` button** → Stats Widget with 4 tabs (Player Stats / NPC Stats / Territories / Turn Order) — see "Stats Widget tabs" section above
- **`RESOURCES` / `WORLD` / `SETTINGS` buttons** → single-screen widget overlays (already in recipe step 12)
- **Game History tabs** (`Story / Details / Geopolitics / Work Stream`) — see "Game History tabs" section above
- **Phase screens** (9 phases from Start to Counter) — see "Capturing the 9 phase pages" section above
- **Commander bio keyboard-smash text** — captured incidentally in the main-menu screenshot as part of the commander selection wizard step 1

The basic recipe captures: loading, login, main menu, wizard (step 1 + step 2 + match-starting), gameplay (initial + populated), map (view + with-pins), and the 4 widget overlays. To get the stats tabs + history tabs + phase pages, fold in the additional scripts above.
