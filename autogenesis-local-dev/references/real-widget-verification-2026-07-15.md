# Real-Widget Mobile Verification — Proven Recipe (2026-07-15)

This is a focused supplement to `kvision-mobile-portrait-css.md`
capturing the recipe that ACTUALLY drove a real KVision widget
(CommanderSelectionDialog Step 2) through real AccelByte OAuth and
got a real screenshot at iPhone 12 dimensions — proven by 8/8 PASS
on the opponent-cards fix verification probe
(`/tmp/hermes-verify-opponent-cards-reallive-20260715.mjs`).

The skill's `references/kvision-mobile-portrait-css.md` contains
an incorrect pitfall claiming "AccelByte OAuth backend unreachable
from sandbox" — that diagnosis was wrong and has been replaced by
the "Missing dist config files" pitfall below. This file documents
what actually works end-to-end.

---

## The insight

`kvisionApp-e2e/probes/guest-login.mjs` uses a DESKTOP viewport
(1280x800) because that's what reliably reaches MainMenu after OAuth.
Mobile viewport (390x844) gets to the same OAuth success, but the
LoadingScreen takes 30s for the music-asset 404 timeout either way
— no win. **Start the browser at desktop viewport, do the entire
desktop-tested flow, then resize to mobile right before the widget
you want to verify. The widget's matchMedia listener fires on
viewport resize and re-applies mobile CSS.**

---

## Prerequisites (one-time setup, persistent after that)

### 1. Copy the AccelByte SDK config files into dist/

The static server at `:8080` serves from
`kvisionApp/build/dist/js/productionExecutable/`. The SDK's
`/kvision-iam.local.properties` and `/kvision-global.local.properties`
endpoints need to be present there for the OAuth flow to start.
Without these, OAuth stalls at "Please Wait" forever:

```bash
cp kvisionApp/build/processedResources/js/main/kvision-iam.local.properties \
   kvisionApp/build/dist/js/productionExecutable/
cp kvisionApp/build/processedResources/js/main/kvision-global.local.properties \
   kvisionApp/build/dist/js/productionExecutable/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/kvision-iam.local.properties
# Expect: 200
```

Make these `cp` commands persistent — re-run after every gradle
build that produces a new dist. The CSS-only bypass pattern in
`kvision-mobile-portrait-css.md` does NOT copy these; add them to
that recipe too.

### 2. Confirm the AccelByte endpoints actually work

Don't trust prior diagnosis. The real endpoints work from this network:

```bash
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 5 \
  https://echoofmaridia-autogenesis.prod.gamingservices.accelbyte.io/auth/oauth/token
# Verified 2026-07-15: 200 in 0.46s
```

The earlier DNS failure on `accounts.accelbyte.io` is because the
new AccelByte auth endpoints live under the per-namespace URL
(`<baseUrl>/auth/...`), not the shared host. Don't use the shared
host as a connectivity check.

---

## The proven recipe

```javascript
import { chromium, devices } from '@playwright/test'

const DESKTOP = { width: 1280, height: 800 }
const MOBILE  = { width: 390,  height: 844 }

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: DESKTOP })
const page = await context.newPage()

// === STEP 1: LoadingScreen CTA click + wait for full dismiss ===
// The 30s music-asset 404 timeout means the loading screen stays up
// even after CTA click. Use a polling loop, not waitForSelector.
await page.getByTestId('loading-screen-cta').waitFor({ state: 'visible', timeout: 30000 })
await page.getByTestId('loading-screen-cta').click()

const start = Date.now()
while (Date.now() - start < 90000) {
    const gone = await page.evaluate(() => {
        const root = document.querySelector('.loading-screen-root')
        return !root || root.offsetWidth === 0 || getComputedStyle(root).display === 'none'
    })
    if (gone) break
    await page.waitForTimeout(2000)
}

// === STEP 2: LoginPage mounted (uses proven desktop path) ===
await page.locator('.login-widget-window').waitFor({ state: 'visible', timeout: 30000 })

// === STEP 3: Real AccelByte OAuth via Login As Guest button ===
await page.getByTestId('login-as-guest').click()

// === STEP 4: Poll for MainMenu, handling ResumeOrNewDialog + OK messageBoxes ===
const deadline = Date.now() + 120_000
let menuFound = false
while (Date.now() < deadline) {
    // ResumeOrNewDialog appears for accounts with saved games — dismiss with New Game
    const resume = page.locator('[data-testid="resume-or-new-dialog"]')
    if (await resume.count() > 0 && await resume.first().isVisible()) {
        await page.getByRole('button', { name: /^New Game$/i }).first().click({ force: true })
        await page.waitForTimeout(2000)
    }
    if (await page.locator('.btn.btn-play').count() > 0) { menuFound = true; break }
    const okBtn = page.getByRole('button', { name: /^OK$/ })
    if (await okBtn.count() > 0) {
        try { await okBtn.first().click({ timeout: 1000 }) } catch {}
    }
    await page.waitForTimeout(300)
}
if (!menuFound) throw new Error('MainMenu never appeared within 120s')

// === STEP 5: Verify real accelbyteId (NOT synthetic "guest-user") ===
const accelbyteId = await page.locator('[data-testid="main-menu"]')
    .getAttribute('data-accelbyte-user-id')
if (!accelbyteId || accelbyteId === 'guest-user') {
    throw new Error(`accelbyteId is ${accelbyteId}, expected real UUID`)
}
console.log(`accelbyteId=${accelbyteId}`)

// === STEP 6: Navigate to target widget (CommanderSelectionDialog Step 2 example) ===
await page.locator('[data-testid="main-menu"] .btn-play').first().click()
await page.waitForSelector('[data-testid="commander-selection-root"]', { timeout: 15000 })
await page.waitForSelector('.commander-selection-card', { timeout: 15000 })
await page.locator('.commander-selection-card').first().click()
await page.waitForTimeout(500)
await page.getByRole('button', { name: /^Next$/i }).first().click()
await page.waitForSelector('.commander-selection-step-2', { timeout: 10000 })
await page.waitForTimeout(800)

// === STEP 7: RESIZE TO MOBILE right before screenshot ===
// The widget's matchMedia listener fires on viewport resize and sets
// data-mobile-layout="portrait". This is the SAME listener path that
// real phone users hit on portrait mount.
await page.setViewportSize(MOBILE)
await page.waitForFunction(() => {
    const root = document.querySelector('[data-testid="commander-selection-root"]')
    return root?.getAttribute('data-mobile-layout') === 'portrait'
}, { timeout: 5000 }).catch(() => {})
await page.waitForTimeout(1000)  // CSS transition settle

// === STEP 8: Screenshot + diagnostic dump ===
await page.screenshot({ path: '/path/to/screenshots/realwidget-viewport-390x844.png', fullPage: false })
await page.screenshot({ path: '/path/to/screenshots/realwidget-fullpage-390x844.png', fullPage: true })

const diag = await page.evaluate(() => {
    const root = document.querySelector('[data-testid="commander-selection-root"]')
    return {
        dataMobileLayout: root?.getAttribute('data-mobile-layout'),
        // ... target-widget-specific checks ...
    }
})
console.log('DIAGNOSTIC:', JSON.stringify(diag, null, 2))

await browser.close()
```

---

## Required probe additions vs the naive "skipLogin + mobile viewport" approach

1. **Wait for LoadingScreen to fully dismiss** (music 404 takes 30s)
   before expecting LoginPage — use a 75-90s polling loop, not a
   `waitForSelector` with 30s timeout.
2. **Handle ResumeOrNewDialog** when KingCandy13 (or any account
   with a saved game) logs in — it overlays MainMenu and intercepts
   PLAY clicks. Click "New Game" with `force: true` to dismiss.
3. **Use desktop viewport for the entire login flow** — the
   `guest-login.mjs` proven pattern is at desktop viewport. Don't
   switch to mobile until AFTER the target widget mounts.
4. **Resize to mobile AFTER mounting the target widget**, then wait
   for `data-mobile-layout="portrait"` attribute (the matchMedia
   listener's response).
5. **Take both `fullPage: true` AND `fullPage: false` screenshots**
   — the full-page one shows all sections (title + Game Type + Match
   Configuration + footer), the viewport one shows what the user
   sees without scrolling.

---

## What you must do BEFORE this recipe works

1. `cp kvisionApp/build/processedResources/js/main/kvision-iam.local.properties kvisionApp/build/dist/js/productionExecutable/`
2. `cp kvisionApp/build/processedResources/js/main/kvision-global.local.properties kvisionApp/build/dist/js/productionExecutable/`

Without these, the OAuth stalls at "Please Wait" forever. These are
the only required environmental prep; everything else is in the recipe.

---

## What to do when this recipe fails

1. Check `tail -f /tmp/autogenesis-proxy/srv.log` for OAuth completion
   or auth failures. Look for `accelbyteId=<real-uuid>` entries.
2. Check the browser console via the probe: capture console output,
   look for `console.error` after the Login As Guest click. Common
   failures: `Failed to fetch`, `NetworkError`, `401 Unauthorized`
   from AccelByte (the test guest account's password may have
   rotated).
3. If ResumeOrNewDialog blocks PLAY: your probe missed handling it.
   The polling loop in the recipe catches it via the `resume.count()`
   check, but if your probe doesn't have that check, add it.
4. If matchMedia listener doesn't fire on resize: the widget's
   Kotlin init block needs the `GlobalScope.launch { matchMedia(...).addEventListener }`
   pattern (see `kvision-mobile-portrait-css.md` Step 2). Without
   it, `data-mobile-layout="portrait"` never gets set.

---

## Verified probe

`/tmp/hermes-verify-opponent-cards-reallive-20260715.mjs` implements
the full recipe. Run with all three dev services up:

```bash
mkdir -p /home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-15-opponent-cards
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
timeout 300 node /tmp/hermes-verify-opponent-cards-reallive-20260715.mjs
```

Expected result (verified 2026-07-15):

```
[19:30:46.591]   PASS: Step 2 visible
[19:30:46.591]   PASS: Opponent row found via :has() structural selector
[19:30:46.591]   PASS: Opponent row has exactly 3 cards
[19:30:46.591]   PASS: Opponent row flex-direction is column
[19:30:46.591]   PASS: Active card box-shadow tightened (18px not 50px)
[19:30:46.591]   PASS: Active card overflow: hidden
[19:30:46.591]   PASS: Active card ::after display: none
[19:30:46.591]   PASS: All 3 opponent cards full-width (>= 280px)
Result: ALL PASS (8 pass)
```

---

## Why this approach

The naive "use mobile viewport from the start" approach has three
failure modes the desktop-first approach avoids:

1. **Mobile LoadingScreen takes 30s for music 404 anyway.** No win.
2. **Mobile LoginPage CSS rules interact with KVision's reactive
   state in subtle ways.** The `.login-widget-window` mobile rule
   sets `transform: none` which can interfere with KVision's
   positioning. Desktop bypasses all of this.
3. **Mobile viewport makes the `LoadingScreen` cover more screen
   and harder to debug.** Desktop viewport gives you the canonical
   proven login path.

Desktop-login-then-resize is the proven path. It works because the
widget's matchMedia listener fires on viewport resize — same code
path that real phone users hit when they rotate their device.

---

## ResumeOrNewDialog details

The KingCandy13 test guest account has a saved game from a prior
session. After OAuth completes, `MainMenu.kt` checks for an active
snapshot and mounts `ResumeOrNewDialog` on top of MainMenu. The
dialog has three buttons:

- **Resume** — loads the saved game (NOT what you want for testing
  a fresh mobile-portrait fix)
- **New Game** — clears the snapshot and stays on MainMenu (use this)
- **Cancel** — stays on MainMenu without clearing

In probes, dismiss with:

```javascript
await page.getByRole('button', { name: /^New Game$/i }).first().click({ force: true })
```

The `force: true` is required because the dialog overlay intercepts
pointer events. Wait 2 seconds after the click for MainMenu to
re-render before continuing.

---

## The wrong diagnosis this file replaces

Earlier in this session, I assumed the AccelByte OAuth backend was
unreachable from this network because `curl https://accounts.accelbyte.io`
failed DNS and `curl https://echoofmaridia-autogenesis.prod.gamingservices.accelbyte.io`
returned 404. The user pushed back hard: *"stop using the word sandbox
as an excuse to do a bad job, not your acutal research, and not obey
skills, memory, and instructions."* They were right.

The actual cause was the missing dist config files. Real OAuth works
fine from this network once those files are in place.

The lesson generalizes beyond this session: **do NOT diagnose
environmental blockers before checking the bundle.** When OAuth
stalls, when assets 404, when a feature appears broken, check
`/path/to/dist/` first. The bundle is the source of truth for what
runs in the browser.