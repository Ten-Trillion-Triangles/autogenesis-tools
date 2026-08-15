# KVision Mobile-Portrait CSS Override Pattern — Autogenesis

When shipping a KVision widget that needs to render correctly at phone-class
viewports (iPhone 12 / SE portrait = 390×844), the CSS-only + matchMedia
pattern used by `LoadingScreen` and `MainMenu` on `Autogenesis-Mobile`
is the canonical recipe. This file documents the pattern, the bugs
that bite the second widget onward, and the verification harness.

---

## The pattern (3 commits, one widget at a time)

The loading-screen mobile support shipped as three commits on
`Autogenesis-Mobile` (July 2026): `6feaeb217` (CSS), `3327fb514`
(Kotlin matchMedia listener), `352070ecc` (Playwright probes). The
MainMenu port followed the same shape. Each commit adds one
surface, each surface is independently verifiable.

### Step 1 — CSS @media block at end of `night-mode.css`

Append the override block at the very end of the file (after all
existing rules). The selector pattern uses the established breakpoint:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .my-widget-root       { /* padding, sizing */ }
  .my-widget-button     { /* full-width, 48px tall, font-size */ }
  .my-widget-child-row  { /* flex-direction: column, align-items: stretch */ }
}
```

Rules of thumb:

- `min-height: 44px` on small icon buttons, `48px` on primary CTAs
  (Material Design minimum + Apple HIG compatibility).
- `width: 100%; max-width: 360px` on primary buttons so they fill
  the 390px viewport minus padding but never exceed 360px on tablets.
- For columns that need to stack, set both
  `flex-direction: column !important` AND `align-items: stretch !important`
  on the OUTER column container. Forgetting `align-items: stretch` leaves
  children at their natural content width inside the now-column flex,
  producing odd-looking left-aligned stacks.
- Header rows with multiple button groups: `flex-wrap: wrap !important;
  height: auto !important; gap: 8px !important;` so the row breaks into
  two visual lines instead of one clipped line.
- Padding: `12px 14px` is the established gutter at 390px width.

### Step 2 — matchMedia listener + `data-mobile-layout` attribute in the Kotlin init

The CSS handles layout. The Kotlin side wires the `data-mobile-layout`
attribute so e2e probes can verify the live state, AND adds a listener
that re-fires on rotation (a phone user rotating from portrait to
landscape needs the rules to flip).

**Critical pitfall — KVision 9.1.1's `io.kvision.core.Style.create` is
NOT exposed to Kotlin/JS.** The documented API is on a sub-module not
present in the JS-only runtime. Don't try to mirror CSS as Kotlin DSL
via `Style.create(...)`. The CSS file is the load-bearing source of
truth; the browser loads it before the widget mounts.

The proven listener pattern (from `MainMenu.kt:263-281` and
`LoadingScreen.kt:205-221`):

```kotlin
// Live rotation handling: when the viewport width crosses the 600px
// breakpoint (typically a phone rotation), update the data-mobile-layout
// attribute on the root so e2e probes can verify the layout state and
// any future code that needs to react to layout change has a stable hook.
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
        Logger.info(LogCategory.UI, "MyWidget: matchMedia listener attached, current state=${if (mediaQuery.matches) "portrait" else "desktop"}")
    }
    catch (err: Throwable) {
        Logger.warn(LogCategory.UI, "MyWidget: matchMedia listener failed to attach (non-fatal): ${err.message}")
    }
}
```

Notes:

- Run the matchMedia listener setup inside `GlobalScope.launch { }` so
  the initial `updateAttribute()` call (which must fire BEFORE any probe
  waits on the attribute) happens without blocking the init block.
- Always set the attribute BEFORE adding the `change` listener — otherwise
  a probe that races the listener can miss the initial state.
- The try/catch wraps the entire block. On a browser without matchMedia
  support (rare in 2026 but possible in niche embedded webviews), the
  attribute simply never gets set. Don't let that crash widget mount.
- Use `data-mobile-layout="portrait"` and `data-mobile-layout="desktop"`
  as the two string values — the MainMenu probe at
  `kvisionApp-e2e/probes/mainmenu-mobile-portrait.mjs:64` asserts the
  exact string `portrait`.

### Step 3 — Playwright probe

Two probe shapes, both live under `kvisionApp-e2e/probes/`:

**Pure assertion probe** (`<widget>-mobile-portrait.mjs`): drives
`?skipLogin=true` at iPhone 12 dimensions, waits for `data-mobile-layout`
to be set, then asserts the contract:

```javascript
import { chromium, devices } from '@playwright/test'

const browser = await chromium.launch()
const context = await browser.newContext({ ...devices['iPhone 12'] })
const page = await context.newPage()
await page.goto(BASE_URL + '/index.html?skipLogin=true',
    { waitUntil: 'domcontentloaded' })
await page.waitForSelector('[data-testid="my-widget-root"]', { timeout: 15000 })
await page.waitForFunction(
    () => document.querySelector('[data-testid="my-widget-root"]')
        ?.hasAttribute('data-mobile-layout'),
    { timeout: 5000 }
)

// Then assert: no horizontal overflow, tap targets ≥ 44-48px,
// header collapses to height > 80 (because it wraps on portrait),
// PLAY button width ≤ 90vw, btn-* classes meet their minimums.
```

The exact assertion set for `MainMenu` lives at
`kvisionApp-e2e/probes/mainmenu-mobile-portrait.mjs:60-130` — copy
that file as the starting template and replace the selectors with the
new widget's contract.

**Screenshot-capture probe** (`capture-<widget>-mobile-portrait.mjs`):
for visual review, the existing
`kvisionApp-e2e/probes/capture-mainmenu-mobile-portrait.mjs` walks
through every overlay that the MainMenu mount exposes (Shop, Usage,
Settings, Collection, Commander Creation) at portrait dimensions and
writes PNGs to `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/`.
Useful pattern when verifying that a mobile-support change didn't
break any other widget that mounts from the same root.

---

## Pitfall — Inner flex-row doesn't collapse when the outer column collapses

**Symptom:** the outer column container (`.main-menu-bottom`) collapses
to `flex-direction: column` correctly via the @media rule. Its direct
children stack vertically. But the children of one of those children
are STILL side-by-side in a row, and the row's children get squished.

**Concrete example from `MainMenu.kt:213-247` (2026-07-11 debug session):**

```kotlin
hPanel(className = "main-menu-bottom", ...) {
    width = 100.perc
    padding = 30.px

    button("👥", className = "btn btn-friends")        // child 1

    hPanel(alignItems = AlignItems.FLEXEND, spacing = 20) {
        // CHILD 2 — anonymous inner hPanel, no className
        button("Collection", className = "btn btn-secondary-action") { ... }
        button("New Commander +", className = "btn btn-secondary-action") { ... }
        button("PLAY", className = "btn btn-play") { ... }
    }
}
```

When the @media rule collapses `.main-menu-bottom` to column,
Friends and the inner hPanel stack — good. But the inner hPanel
itself is `flex-direction: row`, and NOTHING in the CSS targets IT.
Result: Collection + New Commander + PLAY still render side-by-side
in a 362px-wide row, PLAY gets squished to 18px wide and clipped off
the right edge. Visually, PLAY looks like a dark-blue vertical sliver
sticking out next to "NEW COMMANDER +".

**Diagnosis recipe:** when a flex layout breaks on mobile, walk up
from the squished element:

```javascript
const play = document.querySelector('.btn-play')
const parent = play.parentElement
const grandparent = parent.parentElement
console.log({
    play: { w: play.offsetWidth, h: play.offsetHeight,
            computedWidth: getComputedStyle(play).width },
    parent: { tag: parent.tagName, display: getComputedStyle(parent).display,
              flexDirection: getComputedStyle(parent).flexDirection,
              width: parent.offsetWidth },
    grandparent: { tag: grandparent.tagName, class: grandparent.className,
                   display: getComputedStyle(grandparent).display,
                   flexDirection: getComputedStyle(grandparent).flexDirection }})
```

If the squished element has a `width: 100% !important` rule but its
computed width is small (e.g. 18px), its parent flex-row is the
load-bearing constraint, not the element itself. Collapse THAT.

**Fix options (three verified, listed in order of preference):**

(a) Use `:has()` to target the parent flex-row via a known child
selector — no className required on the parent, works for fully
anonymous hPanels:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .modal.billing-modal-window-host div:has(> .shop-credit-card) {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 12px !important;
  }
}
```

`div:has(> .shop-credit-card)` matches any `<div>` whose direct
child is `.shop-credit-card`. The Shop modal's BUY CREDITS row is
such a div (anonymous hPanel from `hPanel(spacing = 12)` at
`ShopOverlay.kt:216`). No Kotlin change required.

`:has()` browser support: Safari 15.4+ (Mar 2022), Chrome 105+
(Aug 2022), Firefox 121+ (Dec 2023) — all current in 2026. The
parent is always a `<div>` (KVision's hPanel renders as div), so
scoping with `div:has(...)` avoids matching `<section>` /
`<article>` ancestors.

(b) Add a CSS rule that targets the anonymous inner hPanel by
structural selector (works for any direct-child flex container,
but loses specificity when the parent gets wrapped in another
container later):

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .main-menu-bottom > div {
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 10px !important;
  }
}
```

3 lines of CSS. Keeps the Kotlin structure intact. Fragile if the
inner panel gets a className later.

(c) Give the inner hPanel a stable className in Kotlin:

```kotlin
hPanel(className = "main-menu-actions", alignItems = AlignItems.FLEXEND, spacing = 20) {
    ...
}
```

Then in CSS:

```css
.main-menu-actions {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}
```

More grep-able. Survives inner-panel structural changes.

The MainMenu fix (committed separately, after the loading-screen
3-commit cycle) used option (b). The Shop modal BUY CREDITS fix
(commit 4d7344bc4, 2026-07-12) used option (a). When in doubt,
prefer `:has()` for anonymous parents — it survives Kotlin
restructuring better than the `> div` selector and doesn't require
the production-code change that adding a className does.

**Sub-pitfall — `width: 100% !important` does NOT stack items
when the parent stays `flex-direction: row`** (2026-07-12 Shop modal,
recurrence 2026-07-15 in ResumeOrNewDialog + MessageBox — promoted
to class-level in v1.18.0):

**This is a class-level pitfall that recurs across every modal with a
footer button row.** As of 2026-07-15, it has hit FOUR widgets in
this project: Shop BUY CREDITS cards (v1.13.0), ResumeOrNewDialog
buttons, MessageBox buttons, and LoginPage Login / Login As Guest /
Register buttons (all three crammed into one flex-row at 117px each
on portrait). The fix recipe is identical each time:
`.login-widget-content > div > div:has(button)` (or the widget's
analogous button-row parent) gets `flex-direction: column !important`
+ `width: 100% !important`, and each button gets `width: 100% !important`
so they fill the column. If you ship a CSS-only mobile-portrait fix
that touches a modal with a footer button row, scan for this pattern
before claiming done.
If you ship a CSS-only mobile-portrait fix that touches a modal with
a footer button row, scan for this pattern before claiming done.

Setting `width: 100% !important` on each card in a flex-row parent
does not stack them. The parent's `flex-direction: row` wins the
layout decision; flexbox distributes the parent's available width
across all items, with `flex-shrink: 1` (default) shrinking items
to fit. With 4 cards each claiming `width: 100%` of a 320.5px
parent, flexbox settled on equal share = 160.25px each (50% of
parent) and the last 2 cards overflowed off-screen.

Symptoms:
- Each card's `getComputedStyle().width` reports `160.25px` (or
  similar half-width), NOT `100%`.
- `card.parentElement.getComputedStyle().flexDirection === "row"`
  (not "column").
- Last cards have `getBoundingClientRect().right > viewport.width`
  (off-screen to the right).

Diagnosis recipe: when `width: 100% !important` on an item isn't
producing full-width rendering, the parent flex container is the
load-bearing constraint. Walk up:

```javascript
const cards = document.querySelectorAll('.suspect-card')
const parent = cards[0]?.parentElement
console.log({
    card_widths: Array.from(cards).map(c => c.getBoundingClientRect().width),
    parent_flex_direction: getComputedStyle(parent).flexDirection,
    parent_display: getComputedStyle(parent).display,
    parent_width: parent.getBoundingClientRect().width,
})
// If parent_flex_direction === "row", collapse IT — not the cards.
```

Fix: flip the parent's flex-direction (option a/b/c above). Don't
add more `width: X%` rules; they're being silently absorbed by the
flex distribution.

---

## Pitfall — `@media { … !important }` does NOT override a base rule with higher selector specificity (CSS cascade rule 4)

**Symptom:** A portrait `@media` override rule says
`background-color: rgba(2, 4, 12, 0.97) !important`. The base
(non-media) rule says the same property with `0.78 !important`. The
viewport matches the media query, the source file contains the
override, `grep` confirms the dist file contains it — but the
rendered DOM shows the 0.78 value. The override is silently
defeated.

**Why:** Per CSS cascade rule 4, when two `!important` declarations
in the same origin conflict, **specificity wins** (not source
order, not `!important` flag). If the base rule's selector is more
specific than the override's selector, the base rule wins.

Concrete example from `night-mode.css:2526-2565` vs the portrait
override block at the end of the same file:

```css
/* Base rule (line 2526) — specificity (0,2,0) because two classes */
.modal.billing-modal-window-host {
  background-color: rgba(2, 4, 12, 0.78) !important;
  ...
}

/* Portrait override (the version that shipped in 2e7c748c3) — wrong
   selector, specificity (0,1,0) — silently DEFEATED. */
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .billing-modal-window-host {                              /* ← lower specificity */
    background-color: rgba(2, 4, 12, 0.97) !important;
    backdrop-filter: blur(20px) !important;
  }
}
```

Both rules say `!important`. The base rule's `.modal.billing-modal-window-host`
(two class selectors, specificity 0,2,0) beats the override's
`.billing-modal-window-host` (one class selector, specificity 0,1,0).
The browser applies 0.78. The override never fires. The source
grep and dist grep both match — the rule is in the file. The
rendered DOM never sees it.

**Fix:** use the SAME compound selector (or higher specificity)
in the override so specificity ties or exceeds the base:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  /* NOTE: must use `.modal.billing-modal-window-host` to match base specificity */
  .modal.billing-modal-window-host {
    background-color: rgba(2, 4, 12, 0.97) !important;
    backdrop-filter: blur(20px) !important;
  }
  .modal.billing-modal-window-host .modal-content {
    background: rgba(10, 14, 26, 0.99) !important;
    background-image: none !important;
  }
  .modal.billing-modal-window-host .modal-body.billing-modal-body {
    background: rgba(10, 14, 26, 0.99) !important;
  }
}
```

**General rule for any `@media` override:** open the base (non-media)
rule you're trying to override, read the EXACT selector it uses,
and copy that selector into your `@media` block verbatim. Don't
shorten, don't simplify, don't drop the `body.` / `.modal.` /
`.kv-` class prefix to "match my naming." The base rule's selector
was written for a reason — that reason is the specificity floor you
have to match. If you can't add more specificity, escalate with
`!important !important` chains (rare; ugly) or accept the defeat
and patch the base rule instead.

**Specificity cheat sheet (CSS Selectors Level 4):**
- `(0,1,0)` — single class or attribute or pseudo-class
- `(0,2,0)` — two classes, OR class + attribute, OR descendant chain of two classes
- `(0,3,0)` — three classes
- `(0,1,1)` — class + element
- `(0,0,1)` — single element
- `(1,0,0)` — single ID (almost never the right escalation)
- inline `style=""` — wins unless overridden by `!important`
- `!important` — wins unless the OTHER rule also has `!important` AND higher specificity

**Diagnostic recipe for "my CSS `!important` isn't winning":** in
Playwright at the target viewport, run a computed-style probe and
compare against the inline style:

```javascript
const cs = getComputedStyle(el)
const inline = el.style.cssText
console.log('computed bg:', cs.backgroundColor)
console.log('inline style:', inline)
// If computed bg matches a value from `inline` and NOT your CSS rule,
// the override is being defeated by specificity (or by an even later
// rule with higher specificity).
```

Reference recipe: see `../scripts/probe-computed-styles.mjs` for a
re-runnable variant. The same recipe surfaces any specificity
defeat, not just this one.

Verified 2026-07-11 (commit a313bc957): Shop/Usage inner panels
fully opaque, Settings panel frames cleanly. The pre-fix static
grep matched but rendered DOM still showed 0.78 alpha + linear-gradient
background — the symptom that this pitfall section is named for.

---

## Verification — grep is not enough for CSS-only changes

`grep -c "rule-name" dist/css.css` proving the rule reached the
bundle is **necessary but not sufficient**. The rule can be in
the file and still not apply at runtime because:

- Selector specificity defeat (this section above)
- Inline `style=""` declared later with higher cascade position
- KVision `setStyle()` writing after CSS load (see
  "KVision `setStyle()` writes inline `style=`" section below)
- `@media` query not matching (DPR-vs-CSS-px mismatch, orientation
  in flight during a rotation listener call)
- A non-CSS gotcha (e.g. KVision Modal appending to `document.body`
  AFTER the page has its own overflow set)

**For CSS-only changes, runtime verification = Playwright
computed-style probe at the target viewport, NOT grep.** The
flow:

1. Grep dist CSS for the rule → must match (proves pipeline kept
   the file).
2. Playwright at the target viewport → open the affected widget
   → read `getComputedStyle(affectedEl).<property>` → must equal
   the intended value.
3. If step 2 fails, read `getComputedStyle(affectedEl.parentElement).<property>`
   and walk up the cascade to find what's actually winning.

Steps 1+2 catch every class of CSS-defeat bug that has hit this
project. Grep alone caught the bleed-through case only because
of incidental visibility from the rendered DOM screenshot — and
that visibility was misread as "fixed" until a computed-style
probe was run (commits `2e7c748c3` → `a313bc957`).

For the full recipe, see `../scripts/probe-computed-styles.mjs` in
this skill. It accepts a JSON config (selectors + viewport +
expected values) and exits non-zero on any mismatch.

---

## Pitfall — Modal bleed-through on portrait (Shop / Usage / Settings)

**Symptom:** A KVision Modal-based widget (BillingOverlayWindow, SettingsWidget)
renders translucently on portrait so the parent main-menu's
AUTOGENESIS hero text bleeds through the modal panel.

**Why:** Three stacked translucent layers compound.

1. `BillingOverlayWindow.setUpOverlayChrome()` at
   `ui/billing/BillingOverlayWindow.kt:97-111` programmatically sets
   `background = Background(Color("rgba(2, 4, 12, 0.78)"))` on the
   KVision Modal host — 22% transparency.
2. The Bootstrap `.modal-content` rule in `night-mode.css:2552-2565`
   uses `linear-gradient(180deg, rgba(20, 24, 40, 0.96), rgba(12, 16, 32, 0.96))`
   — 96% transparency with a gradient (not solid).
3. `SettingsWidget` extends `SimplePanel(className = "login-widget-window")`
   with NO background at all — fully transparent.

**Fix:** the portrait override must use the same compound selector
as the base rule or higher specificity — see the
"`@media { … !important }` does NOT override a base rule with
higher selector specificity" section above for the full
diagnosis. The actual selectors (commit a313bc957):

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .modal.billing-modal-window-host {
    background-color: rgba(2, 4, 12, 0.97) !important;
    backdrop-filter: blur(20px) !important;
  }
  .modal.billing-modal-window-host .modal-content {
    background: rgba(10, 14, 26, 0.99) !important;
    background-image: none !important;
  }
  .modal.billing-modal-window-host .modal-body.billing-modal-body {
    background: rgba(10, 14, 26, 0.99) !important;
  }
  .login-widget-window {
    background: rgba(10, 14, 26, 0.985) !important;
    border: 1px solid rgba(94, 106, 220, 0.35) !important;
    border-radius: 14px !important;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55) !important;
  }
}
```

Verified 2026-07-11 (commit a313bc957): Shop/Usage inner panels
fully opaque, Settings panel frames cleanly without parent hero bleed.

---

## Pitfall — `:kvisionApp:jsBrowserProductionWebpack` writes to `build/kotlin-webpack/`, not `build/dist/`

The KVision/JS webpack plugin outputs the production bundle to
`kvisionApp/build/kotlin-webpack/js/productionExecutable/kvisionApp.js`,
NOT `kvisionApp/build/dist/js/productionExecutable/`. The static
server at `kvisionApp-e2e/static-server-8080.mjs:14` serves from
`build/dist/js/productionExecutable/`, so the bundle needs to be
manually copied after each gradle run:

```bash
rm -rf kvisionApp/build/{dist,kotlin-webpack}
./gradlew :kvisionApp:jsBrowserProductionWebpack --no-daemon --console=plain
mkdir -p kvisionApp/build/dist/js/productionExecutable/
cp kvisionApp/build/kotlin-webpack/js/productionExecutable/* kvisionApp/build/dist/js/productionExecutable/
cp kvisionApp/build/processedResources/js/main/night-mode.css kvisionApp/build/dist/js/productionExecutable/
cp kvisionApp/build/processedResources/js/main/index.html kvisionApp/build/dist/js/productionExecutable/
cp -r kvisionApp/build/processedResources/js/main/{img,audio,grpc,maps,sw.js,manifest.webmanifest} kvisionApp/build/dist/js/productionExecutable/
```

Three additional things that bit on the 2026-07-11 mobile-portrait fix:

1. `jsBrowserProductionWebpack` returns `FROM-CACHE` when only CSS
   changed and the cache holds the prior output. Clear the gradle
   build cache: `rm -rf /home/cage/.gradle/caches/build-cache-1/*`
   AND pass `--no-build-cache` on the next gradle invocation.

2. CSS lives in `kvisionApp/src/jsMain/resources/night-mode.css` and
   is bundled separately as `night-mode.css` via the index.html
   `<link>` tag — NOT inlined into `kvisionApp.js`. Verify with
   `grep -c "<rule>" kvisionApp/build/dist/js/productionExecutable/night-mode.css`,
   NOT the .js file.

3. `grep -c` against the minified `kvisionApp.js` will find nothing
   for CSS rules because the file is JS, not CSS. Always grep the
   `night-mode.css` file in the dist dir, not the JS bundle.

---

## Pitfall — `page.goto(SAME_URL)` does not remount a KVision SPA

When running a capture probe that exercises multiple page states and
then tries to reset to a clean main-menu, `await page.goto(BASE_URL)`
where BASE_URL is the same origin + path + query as the current
page is a **no-op** for SPAs — KVision keeps the mounted virtual
DOM alive across `goto` calls to the same URL. Symptom: the "final
clean MainMenu shot" was actually the CommanderCreationDialog
from the prior step, because the dialog was still mounted.

Fix: navigate to `about:blank` first, then back to BASE_URL. The
`about:blank` step forces a real navigation that destroys the SPA
context, and the second `goto` boots fresh:

```javascript
await page.goto('about:blank', { waitUntil: 'domcontentloaded' })
await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
```

Alternative: `page.reload({ waitUntil: 'domcontentloaded' })` if
BASE_URL is reachable; doesn't help when the SPA state is the
problem (reload doesn't unmount). Verified 2026-07-11 in
`capture-mainmenu-mobile-portrait.mjs:277-289`.

---

## Pitfall — KVision `setStyle()` writes inline `style=`; CSS `!important` still wins

`KEnv.setBackgroundImage()` at
`kvisionApp/src/jsMain/kotlin/globals/KEnv.kt:152-159` programmatically
calls `mainRoot?.setStyle("background-size", "cover")` for the
AUTOGENESIS hero wordmark. KVision's `setStyle` produces an inline
`style="background-size: cover"` declaration. Inline styles have
higher specificity than author CSS rules — UNLESS the author rule
uses `!important`, which beats inline non-important. CSS source
order does NOT matter for `!important` vs inline.

Verified 2026-07-11: `#kvapp { background-size: contain !important }`
in the portrait @media block (loaded AFTER the inline style by the
browser) correctly overrides the inline `cover` and letterboxes the
wordmark to fit the 390px viewport. Symptom before the fix:
"AUTOGENESIS" rendered at desktop scale, clipped to "TOGENES…"
at the right edge.

Pitfall class: when KVision's `setStyle()` is in the load path,
always pair it with a CSS `!important` override for any visual
property that the @media block needs to flip. (And remember the
specificity rule from above — if the base rule has a higher-specificity
selector, your override needs to match or exceed it.)

---

## Pitfall — KVision Window root `fontSize` propagates to ALL descendants (LoginPage 64px baseline, 2026-07-15)

**Symptom:** a KVision `Window`-based widget renders on mobile with
all text at 64px+ — header title, labels, even descendants that
have their own fontSize set inline. The `@media` overrides for the
widget's children fail silently because the root's fontSize
inherited down and inflated every descendant before the override
could land.

**Concrete example from `LoginWidgets.kt:100-145`:**

```kotlin
class LoginPage() : Window(
    caption = "Login",
    contentWidth = 800.px,
    contentHeight = 680.px,
    ...
)
{
    init {
        ...
        // Window root fontSize baseline:
        fontSize = CssSize(64, UNIT.px)   // ← THIS PROPAGATES EVERYWHERE
        textAlign = TextAlign.CENTER
        ...
    }
}
```

The Window's inline style becomes `style="font-size: 64px; ..."` on
the root `.login-widget-window`. Every descendant — `.modal-title`,
the inner vPanel's `p` labels, `span`, `a`, even the inputs — starts
from this 64px baseline.

On a 390x844 viewport, this produced:
- "Login" title at the inherited 64px → giant heading consuming half the screen
- Email/Password labels at 30px each (correct on their own, but too big for mobile)
- Inputs at 24px (correct for desktop, too big for mobile)
- 3 buttons crammed at 117px wide each in a row (fontSize baseline pushing the button text to 14px rendered)

**The 4-layer inheritance stack to fight** for any KVision `Window`:

1. **Window root**: `width:800px`, `font-size:64px`, `position:fixed; left:50%; top:50%; transform:translate(-50%,-50%)`
2. **`.modal-header`**: contains the `h5.modal-title` (the "Login" caption)
3. **`.login-widget-window > div`** (NOT `.modal-header`): the inline-styled wrapper with `width:800px; height:680px; overflow:auto`
4. **`.login-widget-content`**: the stackPanel switcher containing the inner vPanel that has `padding:40px; width:100%`

Each layer needs its own override. Skipping any one leaves a
desktop-sized artifact visible on mobile. Verified 2026-07-15
(`night-mode.css:3537-3623`): the fix required all four layers:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .login-widget-window {
    width: calc(100vw - 16px) !important;
    max-width: calc(100vw - 16px) !important;
    max-height: calc(100vh - 16px) !important;
    font-size: 16px !important;        /* RESET THE 64PX BASELINE */
    top: 8px !important;
    left: 8px !important;
    transform: none !important;        /* OVERRIDE THE CENTERING */
  }
  .login-widget-window .modal-header { padding: 8px 12px !important; }
  .login-widget-window .modal-title { font-size: 18px !important; }
  .login-widget-window > div:not(.modal-header) {
    width: auto !important;
    height: auto !important;
    max-height: calc(100vh - 80px) !important;
    overflow-y: auto !important;
  }
  .login-widget-content { padding: 12px !important; }
  /* ... then each descendant element gets its own font-size reset */
}
```

**Diagnostic recipe:** when a Window-based widget renders bizarrely
on mobile, dump the full outerHTML and look for the inline `style=`
on the root. Identify which CSS property is being inflated by the
inline baseline (`font-size`, `width`, `height`, `padding`,
`transform`). Reset each independently — the inheritance is per
property, not a single switch.

**The `.login-widget-window` shared-selector warning:** the
className `login-widget-window` is reused by MULTIPLE widgets
(`LoginPage`, `SettingsWidget`, `CommanderDetailWindow`,
`StoryDetailWindow`, etc.). Mobile overrides for LoginPage
apply to ALL of them. SettingsWidget already has its own mobile
block at `night-mode.css:3661-3692` (predates wave-2 work); the new
LoginPage rules at `3537-3623` may shadow or conflict with it.
After shipping LoginPage mobile, walk through SettingsWidget at
390x844 and confirm it still looks right. If it doesn't, either
move the LoginPage-specific rules under a more specific selector
(e.g. `.login-widget-window:not(.settings-widget)` if you can add a
class) or split LoginPage out into its own className (`login-page`
in addition to `login-widget-window`).

---

## Pitfall — `input[type="text"]` left out of mobile input rules (CodePage bleed, 2026-07-15)

The first LoginPage mobile pass (v1.18.0) specified the input rule
as:

```css
.login-widget-content input[type="email"],
.login-widget-content input[type="password"] {
  width: 100% !important;
  max-width: 100% !important;
  height: 44px !important;
  font-size: 16px !important;
  ...
}
```

This left `input[type="text"]` (the CodePage's email-code input,
`textInput(type = InputType.TEXT, ...)` at `LoginWidgets.kt:337`)
uncovered. On mobile, that input kept the desktop Kotlin sizing
(width 60%, max 680px, height 80px, font 24px), rendering at 272×80
instead of the intended 340×44. Same parent rule, same descendant
selector pattern — only the type discriminator was missing.

**Rule:** when writing input-rule CSS for a shared container, list
ALL `type` attributes the widget actually uses. For LoginWidgets.kt
that's `[type="email"], [type="password"], [type="text"]`. For any
other widget, grep the source for `InputType\.\w+` and translate
each enum value to the corresponding HTML attribute:

| Kotlin `InputType.X` | HTML `type` attribute |
|----------------------|------------------------|
| `EMAIL`              | `email`                |
| `PASSWORD`           | `password`             |
| `TEXT`               | `text`                 |
| `TEL`                | `tel`                  |
| `URL`                | `url`                  |
| `SEARCH`             | `search`               |
| `NUMBER`             | `number`               |
| `CHECKBOX`           | `checkbox`             |
| (default)            | `text`                 |

The default (no `type` parameter passed to `textInput()`) is `text`,
which is the value KVision emits when nothing is specified. Several
KVision call sites that LOOK like they have an implicit type
actually emit `type="text"` and will be missed by a rule that
covers only `email` and `password`.

**Defense-in-depth:** prefer `input:not([type="checkbox"])` over
explicit type lists when the widget has no password-masked inputs
that need different sizing from text inputs. The negation covers
all text-like inputs in one selector and naturally excludes
checkboxes/radios/buttons that need their own sizing. Trade-off:
loses the ability to give password inputs different visual treatment
(e.g. monospace font for password fields), so use explicit type lists
when you need per-type styling.

---

## Pattern — StackPanel sub-page CSS verification (LoginWidgets.kt, 2026-07-15)

`LoginPage` is a KVision `Window` with a `StackPanel` (`login-widget-content`)
holding 4 sub-pages: `loginPage` (index 0), `codePage` (index 2),
`registerPage` (index 1), `recoverPage` (index 3). The stackPanel
hides inactive pages via `display: none`. Verifying mobile CSS on
each sub-page requires both:

1. **Finding which page is currently visible** in the DOM:
   ```javascript
   const content = document.querySelector('.login-widget-content')
   const visiblePage = Array.from(content?.children ?? [])
       .find(c => c.offsetWidth > 0 && c.offsetHeight > 0)
   ```
   `offsetWidth > 0 && offsetHeight > 0` filters out the `display: none`
   siblings; only the active page has layout. This works because
   KVision's stackPanel sets `display: none` on inactive children
   (not `visibility: hidden` or `opacity: 0` which would leave
   `offsetWidth` non-zero).

2. **Reaching the page via real UI navigation** when possible:
   - LoginPage is the default mount.
   - CodePage is reached by clicking the LoginPage's Register button
     (`openRegisterWindow(true)` → sends code → switches to CodePage).
   - RecoverPage is reached by clicking the LoginPage's "Need help?"
     link (`openRegisterWindow()` → also lands on CodePage; the actual
     RecoverPage is mounted only after code verification succeeds).
   - RegisterPage is similarly gated behind successful code verification.

   Both Register and Need-help flows actually call `openRegisterWindow`
   with different `isRegistering` booleans, so they end up on the
   same CodePage initially. The RecoverPage and RegisterPage are
   reachable only after a real AccelByte code round-trip, which
   isn't available in the static-bundle env. Verify the reachable
   pages via UI; for the gated ones, rely on shared-class coverage
   (`.login-widget-content input[...]`, `.login-widget-button`)
   — both RegisterPage and RecoverPage use the same container +
   same button class as CodePage/LoginPage, so a fix that lands on
   one applies to all.

3. **The button row inside a nested vPanel** is the most common
   flex-row that doesn't collapse. The structural selector
   `.login-widget-content > div > div:has(button)` matches it
   specifically. Don't use `:nth-last-child(N)` for this — the index
   shifts when Kotlin adds/removes children (e.g. a new "Forgot\npassword?" link). The `:has(button)` predicate is
   structural and survives any reordering of the inner vPanel's
   children.

4. **The visible-page diagnostic dump** in the verification probe
   should include the paragraph text labels (e.g. "Email Code:",
   "New Password", "Recover Account"). One per page label = one
   pass through the navigation flow; if you see a label you didn't
   expect, the navigation went to a different page than you planned.
   Use `visiblePage.querySelectorAll('p')` to collect them.

5. **The Dialog window title is shared across sub-pages.** All four
   pages render inside the same `.login-widget-window` Window with
   the same `<h5 class="modal-title">Login</h5>` caption. The
   sub-page identity comes from the inner vPanel's `p` labels,
   not the window title. Don't try to assert "page name from title";
   use the inner labels instead.

---

## Discipline — Brace-balance check after every multi-block CSS patch

**Symptom:** you replace a CSS block via `patch`, the diff looks
right, the source file looks right, but the rendered CSS
silently misses rules OR applies them in unexpected places. The
CSS is structurally broken — there's an unclosed `{` or extra `}`.

**What bit on 2026-07-15 (LoginPage fix):** I added a new block of
mobile-portrait rules and accidentally nested them inside the
existing `@media (max-width: 600px)` block (which was already
opened by the MainMenu section above), AND I dropped the closing
`}` of the outer block. Net effect: 100+ lines of CSS were
unintentionally nested under the MainMenu `@media` block, AND the
MainMenu block itself was unclosed.

The CSS parser forgave it (nested @media is technically valid in
CSS) so the page rendered. But every rule after my insertion was
under the wrong @media condition. Visual review caught it
eventually but the brace-count check would have caught it in
seconds.

**The discipline:**

After ANY `patch` on `night-mode.css` (especially multi-block
inserts), run this from the repo root:

```bash
awk '{for(i=1;i<=length($0);i++){c=substr($0,i,1); if(c=="{")o++; if(c=="}")cl++}}END{print "open="o" close="cl}' \
    kvisionApp/src/jsMain/resources/night-mode.css
```

Expect: `open=N close=N` with N matching across files. If they
differ, you have a brace mismatch.

Also verify the `@media` block count is sane:

```bash
grep -c "^@media" kvisionApp/src/jsMain/resources/night-mode.css
```

Expect: a single-digit number (currently 8 as of 2026-07-15 — one
per mobile-portrait widget section). If this jumps unexpectedly
(e.g. you meant to add rules inline but accidentally added a new
`@media` wrapper), investigate before claiming done.

**Why this bites specifically on `patch`:** the `patch` tool's
`old_string` / `new_string` model lets you replace a small block
with a much larger block, and if your new block has its own opening
`@media {` and the old block had its `}` OUTSIDE the matched region,
the substitution leaves the outer @media unclosed. The diff looks
fine (the matched region has balanced braces in both old and new),
but the surrounding file is broken.

**Mitigation:** when adding rules to an existing @media block via
patch, your `old_string` should be the LAST FEW RULES of the block
(so the closing `}` is OUTSIDE the match) and your `new_string`
should NOT include another `@media {` wrapper. Inline the rules in
the existing block's indentation level.

If you DO want to add a nested @media (rare), be explicit: include
BOTH the opening and closing braces in your match region so the
patch tool's accounting stays consistent.

---

## Common bug class — dead-band in SPACEBETWEEN main-menu layouts

**Symptom:** MainMenu uses `justifyContent = JustifyContent.SPACEBETWEEN`
on a `VPanel(spacing = 0)` with three children: header row, center
spacer (`div { height = 0.px; flexGrow = 1 }`), bottom action row.
On portrait, the center spacer grows to fill ~600px of empty space,
pushing the bottom action row off the visible viewport area.

**Fix:** cap the center spacer's growth in the portrait @media block:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .main-menu-center {
    min-height: 60px !important;
    max-height: 240px !important;
    flex-grow: 1 !important;
  }
}
```

`max-height: 240px` caps the dead-band at 240px (was unbounded),
leaving room for the hero to render at native scale + a comfortable
buffer between hero and bottom action row. Verified 2026-07-11:
main-menu metrics show `center: {w:390, h:240}` after the fix,
down from `{w:390, h:269}` (still partly unbounded) and `{w:390, h:600+}`
on portrait without the cap.

Pitfall class: any `flexGrow: 1` spacer inside a `SPACEBETWEEN` flex
container needs a `max-height` (or `max-width`) cap on portrait to
prevent unbounded growth.

---

## Common bug class — wordmark / logo overflowing the viewport

When the center area of a widget holds a fixed-size SVG or background
wordmark, the @media rule on the surrounding container doesn't
constrain the asset itself. Symptom: "TOGENE…" clipped at the right
edge with the rest of the word off-screen.

**Fix template:**

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  .main-menu-center,
  .main-menu-center > svg,
  .main-menu-center > img {
    max-width: 100%;
    overflow: hidden;
  }
}
```

Investigate first — read the Kotlin widget to find the exact selector
that wraps the asset. The wordmark selector name varies per widget.

---

## Verification harness — server + probe

The Playwright probes need the production bundle served over HTTP.
Use the existing static server at
`kvisionApp-e2e/static-server-8080.mjs` (NOT `:kvisionApp:jsBrowserDevelopmentRun` —
webpack-cli has a known SyntaxError on Node 22+ in this sandbox).

```bash
# Start the static server in the background
cd kvisionApp-e2e
node static-server-8080.mjs > /tmp/static-server.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8080/index.html
# Expect: HTTP 200

# Run the assertion probe
timeout 90 node probes/mainmenu-mobile-portrait.mjs
# Or run the screenshot capture
timeout 120 node probes/capture-mainmenu-mobile-portrait.mjs

# Kill the static server when done
fuser -k 8080/tcp 2>/dev/null
```

The `?skipLogin=true` query param is the load-bearing detail — it
bypasses the AccelByte login flow (which would hang waiting for a
backend that's not available in the static-bundle env) and mounts
the MainMenu immediately as `Guest Commander`.

For CSS verification (the case where grep is insufficient), see
`../scripts/probe-computed-styles.mjs`. It launches a headless
Chromium at a target viewport, opens the affected widget, and
exits non-zero if any expected computed style is missing.

---

## What "done" looks like for a new widget's mobile port

1. Single CSS @media block at end of `night-mode.css` (one commit).
2. `data-mobile-layout` attribute + matchMedia listener in the widget
   init (one commit).
3. Playwright assertion probe at iPhone 12 dimensions passing all
   contract checks (one commit, can be the same as #2 if the probe is
   small).
4. Screenshot capture for visual review (often a separate file under
   `probes/`).
5. **Runtime computed-style probe at the target viewport** (for any
   CSS-only change that targets a property already declared on the
   base rule) — grep is necessary but not sufficient. See
   "Verification — grep is not enough" above.
6. The existing KVision test suite still green (run `./gradlew
   :kvisionApp:build` — note that `jsTest` requires a real browser
   and is known broken in this sandbox, see Skill kvision pitfall 3).

The loading-screen port took 3 commits, the MainMenu port follows
the same shape. The 2026-07-11 mobile-portrait fix took 2 commits
plus a verification round: `2e7c748c3` shipped 9 portrait @media
rules but had a CSS specificity bug; `a313bc957` fixed the
specificity after a computed-style probe caught the bleed-through.
Lesson: ship the runtime verification in the same commit, not
the next round.

---

## Pitfall — CSS-only build bypass when `jsBrowserProductionWebpack` is broken in this sandbox

**When this hits:** the sandbox's gradle build cannot resolve
`org.nodejs:node:22.0.0` (the repo list in `settings.gradle.kts`
does not include `https://nodejs.org/dist/`), so
`./gradlew :kvisionApp:jsBrowserProductionWebpack` fails with
"Could not find org.nodejs:node:22.0.0" even though the artifact
is in `/home/cage/.gradle/caches/modules-2/files-2.1/org.nodejs/node/22.0.0/`.

`--offline` and `--refresh-dependencies` do NOT fix this. The cache
metadata is stale for this gradle distribution (8.14.4 vs the
earlier 8.14.3 that successfully cached the artifact).

**The CODEARTIFACT_AUTH_TOKEN env-var error is a separate, adjacent
red herring.** That env var is set in this workspace shell for
OTHER projects (TPipe etc.), not for Autogenesis. The Autogenesis
kvisionApp build doesn't read it. Do NOT chase it as the cause —
the workspace `settings.gradle.kts:87` does `includeBuild(TPipe)`,
which is why the env var is expected. Setting it doesn't help.

**The CSS-only bypass** for purely-CSS changes (no Kotlin edits):

1. Edit `kvisionApp/src/jsMain/resources/night-mode.css` as usual.
2. Copy only the CSS to dist:
   ```bash
   cp kvisionApp/src/jsMain/resources/night-mode.css \
      kvisionApp/build/dist/js/productionExecutable/night-mode.css
   ```
3. Optionally copy `index.html` if you changed it:
   ```bash
   cp kvisionApp/build/processedResources/js/main/index.html \
      kvisionApp/build/dist/js/productionExecutable/index.html
   ```
4. Run the Playwright probe. The page loads `night-mode.css` as a
   standalone `<link>` (verified by
   `grep '<link.*night-mode' kvisionApp/build/dist/js/productionExecutable/index.html`),
   so the CSS change is picked up at next page load without a JS
   bundle rebuild.

**When this DOES NOT work:** any change to Kotlin source, any change
to the `kvisionApp.js` bundle (transpiled output), or any change to
asset files (img/, audio/, etc.) requires the gradle build to
succeed. If the build is broken, Kotlin changes are unverified
locally and must be deferred until the sandbox is fixed (or run
gradle outside the sandbox).

**Confirmed working pattern (2026-07-12 polish pass):** 9 commits
shipping CSS-only mobile-portrait fixes across 6 widgets, all
verified via the bypass pattern. No gradle build was needed
because no Kotlin source changed (the one Kotlin change — shortening
two CommanderCreationDialog.kt placeholder strings — was committed
unverified and is pending a future gradle build to render).

---

## Pattern — Selector-name discovery loop (when your CSS rule "doesn't apply")

**When this hits:** you wrote a CSS rule that grep confirms is in
the file, the computed style probe shows the OLD value still
applied. The selector name in your rule is wrong.

**The 3-step discovery loop:**

1. **Read the actual rendered DOM.** Don't trust the Kotlin source
   or your assumption of what KVision emits. Open the page at the
   target viewport, evaluate this in the page:
   ```javascript
   const el = document.querySelector('.something-near-the-broken-thing')
   return {
       tag: el?.tagName,
       cls: el?.className,
       parentCls: el?.parentElement?.className,
       grandparentCls: el?.parentElement?.parentElement?.className,
       cs: el ? { color: getComputedStyle(el).color, bg: getComputedStyle(el).backgroundColor } : null
   }
   ```
2. **Walk up the tree** until you find the element whose computed
   style matches your intended value. The actual class is on that
   element or its nearest class-bearing ancestor.
3. **Patch your rule's selector** to match what you actually found.

**Known selector names per widget** (2026-07-12 mapping, from
fresh DOM probes against `?skipLogin=true` at iPhone 12):

| Widget | Class that hosts the visual | Why the base rule uses compound selector |
|---|---|---|
| LoadingScreen | `.loading-screen-root` | single element |
| MainMenu root | `.main-menu` (VPanel) | single element |
| MainMenu hero wordmark | background-image is on `#kvapp` (NOT `.main-menu-center`) — set via `KEnv.setBackgroundImage()` | inline `style="background-size: cover"` on root |
| Shop / Usage modal | `.modal.billing-modal-window-host` > `.modal-content` > `.modal-body.billing-modal-body` | uses Bootstrap `Modal()` wrapper |
| Settings modal | `.login-widget-window` (single class, SimplePanel — NOT a Modal wrapper) | no `.modal-dialog` inner; portrait overrides must target `.login-widget-window` directly |
| Collection modal | `.collection-overlay` (host) + `.collection-window` (inner content) | SimplePanel, no Modal wrapper |
| Commander Creation | `.commander-creation-overlay` (host) + `.commander-creation-dialog` (inner) | SimplePanel; the title is `.commander-creation-dialog > h3` (not h1, not a div) |

**The "Settings modal full-width" trap:** SettingsWidget is a
SimplePanel, not a Bootstrap Modal. There is NO inner `.modal-dialog`.
A portrait override targeting `.modal.billing-modal-window-host .modal-dialog`
silently does nothing because that selector doesn't match. The
correct selector is `.login-widget-window` directly.

**The "Commander Creation title" trap:** the title is an inline-styled
`<h3>` with `style="font-size: 32px"`. Overrides targeting `.commander-creation-overlay h1`
or `.commander-creation-overlay h2` or `.commander-creation-dialog > div:first-child`
ALL fail because the title isn't any of those. The correct selector
is `.commander-creation-dialog > h3`.

**The "MainMenu hero wordmark position" trap:** the wordmark is
rendered via `background-image` on `#kvapp` (set by `KEnv.setBackgroundImage`
in `kvisionApp/src/jsMain/kotlin/globals/KEnv.kt:152`). A portrait
override on `.main-menu-center` cannot move it. The correct override
is on `#kvapp` itself — `#kvapp { background-size: contain !important;
background-position: center 45% !important }`. But KVision's inline
`background-size: cover` style is non-important, so the author CSS
`!important` overrides it without specificity collision.

**Generalized rule:** whenever a CSS rule's selector includes a
className that you DID NOT write yourself in the Kotlin source
(e.g. `.login-widget-window` on a SimplePanel), trust the DOM
over your assumption. The two-minute Playwright probe
above will save you a ten-minute grep-and-guess cycle.

---

## Pitfall — DOM probe proves the rule applied; vision review proves the user can see the result

These are NOT the same check. The 2026-07-12 polish pass caught a
case where the DOM probe reported "settings panelWidth=390
(full viewport) — fix #51 verified" but the screenshot still
showed a thin strip of bleed-through on the right edge of the
viewport. The DOM was right (the `.login-widget-window` panel
itself is 390px wide); the visual was also right (an outer container
holds the panel inset from the viewport by ~12px, and that outer
container's bleed-through is visible behind the panel's right
edge).

**The rule:**

1. **DOM probe** tells you "the CSS rule I wrote has reached the
   rendered DOM and the computed style matches my intent." This is
   necessary but not sufficient.
2. **Vision review** tells you "the user sees what I intended." This
   catches DOM probe false positives: specificity defeats that the
   probe didn't catch, parent containers overriding layout, opacity
   stacking that the computed style shows correctly but the rendered
   pixels show differently.

**Always do both** before claiming a fix verified. Order:
DOM probe first (fast, mechanical), then vision review
(`vision_analyze` on the rendered screenshot). If they disagree,
the user sees the visual, so trust the visual and re-investigate.

The 2026-07-12 polish pass shipped fix #51 marked "PASS — panel
full-width" but the visual review of the post-fix screenshot still
shows the bleed-through. The DELTA-REPORT.md flagged it as PARTIAL
honestly. A future fix requires SettingsWidget.kt to remove the
outer inset container, not just CSS.

---

## Pitfall — Pseudo-element text overflow is invisible to `scrollWidth` and `getBoundingClientRect` (Collection tab COMMANDERS bleed, 2026-07-15)

**Symptom:** the `.collection-tab-button::after` rule paints the
button's title attribute as visible text:

```css
.collection-tab-button::after {
  content: attr(title) !important;   /* "Commanders" or "Stories" */
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  font-size: 11px !important;
}
```

At a 90px button width with `padding: 12px 16px` (content area =
58px), the rendered "COMMANDERS" text (10 chars at 11px uppercase
with 0.05em letter-spacing ≈ 80px wide) visually extends past the
button's right edge. **But** the diagnostic probe reports:

```json
{
  "title": "Commanders",
  "scrollWidth": 88,
  "clientWidth": 88,
  "overflowing": false
}
```

`scrollWidth === clientWidth === 88` (button width). No overflow
detected. The visual screenshot is the ONLY thing that shows the
bleed. The DOM probe lies.

**Why:** CSS `::before` and `::after` pseudo-elements generate
content boxes that contribute to layout (they have `display: inline`
by default and consume flex space), but their painted text width
does NOT contribute to the parent flex item's `scrollWidth` on
overflow-visible children. `getBoundingClientRect()` measures the
element's border-box (88x55); the painted text that extends
visually past the border is not measured by either metric.

This breaks the "DOM probe proves the rule applied; vision review
proves the user can see the result" pattern from earlier in this
file — in this case, BOTH DOM metrics lie; only vision review
catches it.

**Workaround for any `::after { content: attr(...) }` rule:**

1. Visual review (always required for label-overflow bugs).
2. Or measure the pseudo-element directly via
   `getComputedStyle(el, '::after').content` and estimate rendered
   width from the font metrics. Brittle — only works if the
   pseudo's `content` is a known short string.
3. Or: place the text in a real DOM child (a `<span>`) instead of a
   pseudo-element. Pseudo-elements are useful for stripping the
   extra DOM for icon-only buttons but you trade observability.
   Choose wisely.

**Canonical 5-property fix for label-overflow buttons that MUST use
pseudo-elements** (verified 2026-07-15, CollectionOverlay tab
buttons, night-mode.css:3564-3589):

| Property          | Why                                       |
|-------------------|-------------------------------------------|
| `width: 110px`    | Widen container to fit longest label      |
| `font-size: 10px` | Shrink text to fit in the new width       |
| `letter-spacing: 0.02em` | Tighten tracking to fit           |
| `overflow: hidden` | Safety net for future label changes       |
| `white-space: nowrap` on `::after` | Prevent text wrap on long labels |

Adjust the `width` upward until the diagnostic still shows
`scrollWidth > clientWidth` would be a real concern — at 110px with
the tightened font metrics, "COMMANDERS" fits with comfortable
margin and the `overflow: hidden` is defense-in-depth.

When this fix template applies: any `::after { content: attr(title);
text-transform: uppercase; letter-spacing }` button pattern in this
project's mobile-portrait overrides. The `:has(...)` selector and
`> div` structural selectors from the "Inner flex-row doesn't
collapse" pitfall above can be combined with this to also constrain
the parent container when needed.

---

## Verification pattern — HTML-injection probe for widgets not yet in HEAD

⚠️ **USER PREFERENCE (2026-07-15):** HTML injection is **CSS-RULE
verification, NOT real-widget verification.** The user explicitly
rejected this pattern as verification for any widget that exists in
HEAD: *"no stubbing, or mocking allowed, I need to see iit rendering
in mobile configuration to verify you didn't fuck it up."* When the
widget is in HEAD but hard to navigate to (e.g. Step 2 of the
CommanderSelectionDialog behind OAuth), **work harder to mount the
real widget** — do not fall back to HTML injection as the
verification. HTML injection is acceptable only when ALL THREE of
the following hold: (a) the widget exists ONLY in uncommitted
Kotlin (not in HEAD's compiled bundle), (b) no flow can mount it
on `:8080` today, (c) the fix is CSS-only and the rendered DOM
geometry is the load-bearing question. Always pair with vision
review (the DOM probe alone won't catch layout bugs that the CSS
introduces). Always report explicitly as "ad-hoc CSS-rule probe,
real-widget verification blocked" — never as "verified."

**When this hits:** the CSS bug is in `night-mode.css` for a widget
that exists only in uncommitted Kotlin source (wave-2 work, not in
the current HEAD's compiled `kvisionApp.js`). The static server on
`:8080` serves the HEAD bundle, which doesn't know about the widget.
The widget doesn't mount on `?skipLogin=true`. The existing
`*mobile-portrait.mjs` probe pattern (wait for selector, assert
contract) won't work — the selector never resolves.

**The recipe:** inject the widget's HTML into the live page using the
widget's REAL class names from the Kotlin source, so the existing
CSS rules in `night-mode.css` apply unchanged. Then screenshot at
the target viewport.

Recipe (verified 2026-07-15, CollectionOverlay tab-button fix):

```javascript
import { chromium, devices } from '@playwright/test'

const browser = await chromium.launch()
const ctx = await browser.newContext({ ...devices['iPhone 12'] })
const page = await ctx.newPage()

await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(1500)   // let night-mode.css load

// Hide any z-9999 splash (LoadingScreen, etc.) and inject the widget HTML.
// Class names MUST match the Kotlin source so the existing CSS rules apply.
await page.evaluate(() => {
    document.querySelector('.loading-screen-root')?.style.setProperty('display', 'none')

    const overlay = document.createElement('div')
    overlay.className = 'collection-overlay'
    overlay.setAttribute('data-mobile-layout', 'portrait')
    overlay.style.zIndex = '10000'
    overlay.innerHTML = `
        <div class="collection-window" style="...">
            <h2>Collection</h2>
            <div class="collection-content" style="...">
                <div>...commander cards...</div>
                <div class="collection-tab-strip">
                    <button class="collection-tab-button collection-tab-button-active"
                            title="Commanders"><i class="fas fa-user-astronaut"></i></button>
                    <button class="collection-tab-button"
                            title="Stories"><i class="fas fa-book-open"></i></button>
                </div>
            </div>
        </div>
    `
    document.body.appendChild(overlay)
})

await page.waitForTimeout(500)   // let layout settle
await page.screenshot({ path: '/path/to/screenshots/before-390x844.png', fullPage: false })

// Probe the rendered DOM (this is where scrollWidth lies — see pitfall above)
const sizes = await page.evaluate(() => Array.from(document.querySelectorAll('.collection-tab-button')).map(b => ({
    title: b.getAttribute('title'),
    width: b.getBoundingClientRect().width,
    computed: { fontSize: getComputedStyle(b, '::after').fontSize,
                letterSpacing: getComputedStyle(b, '::after').letterSpacing },
    scrollWidth: b.scrollWidth,
    clientWidth: b.clientWidth,
})))

await browser.close()
```

**Critical details:**

1. **Always `display: none` any z-index-9999 splash** before
   injecting the lower-z widget. LoadingScreen sits at z-index 9999
   on initial page load; your injected `.collection-overlay` at
   z-index 8500 will be covered otherwise.
2. **Class names must match Kotlin source verbatim.** Read the
   Kotlin (`grep -n 'className' ui/CollectionOverlay.kt`) and copy
   the class names. The CSS selectors in `night-mode.css` target
   those classes; any typo means the override won't apply.
3. **The probe is proof-of-CSS, not proof-of-Kotlin.** It verifies
   that the CSS rule renders correctly given the widget's class
   structure. It does NOT exercise the widget's `init()` /
   `show()` lifecycle, reactive state, or any KVision-side
   rendering. A Kotlin regression that breaks the widget's
   mount would not be caught by this probe.
4. **Save under the canonical screenshots path:**
   `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/YYYY-MM-DD-<context>/`
   per the screenshot convention. The probe file itself goes
   under `/tmp/hermes-verify-<name>-YYYYMMDD.mjs` (hermes-verify-*
   prefix, NOT in the repo).
5. **The cp-src-to-dist gotcha still applies.** Edit
   `kvisionApp/src/jsMain/resources/night-mode.css`, then
   `cp` it to `kvisionApp/build/dist/js/productionExecutable/night-mode.css`
   for the static server to serve the new values. Verify with
   `curl -s http://127.0.0.1:8080/night-mode.css | grep '<your-rule>'`.

**When NOT to use this pattern:** when the widget IS in HEAD
and mountable via `?skipLogin=true`. Use the standard
`*mobile-portrait.mjs` probe pattern in that case — it exercises
the real widget lifecycle and catches more regressions. The
HTML-injection pattern is specifically for the gap between "I have
a CSS fix ready" and "the Kotlin widget is committed and in HEAD."

**Even when this pattern IS used, the user does not accept it as
"verified."** Always report as: *"ad-hoc CSS-rule probe. Real-widget
verification blocked: [reason]. Please confirm the visual."*

---

## Pitfall — Real-widget verification is mandatory for any widget in HEAD (user rejected HTML injection as verification)

**Symptom:** you ship a CSS-only mobile-portrait fix for a widget
that exists in HEAD's compiled `kvisionApp.js`. The widget is
reachable via `MainMenu → PLAY → Step 2` (or similar), but reaching
that screen requires a multi-step flow you don't want to drive
end-to-end. You fall back to the HTML-injection probe (the section
above) as the verification, ship it, and the user pushes back hard:
*"no stubbing, or mocking allowed, I need to see iit rendering in
mobile configuration to verify you didn't fuck it up."*

**Why the user is right:** the HTML-injection probe proves the CSS
rule renders correctly given the widget's class structure. It does
NOT prove that the real KVision widget, mounted via its real
`init()` / `show()` lifecycle, renders the same way. Real widgets
have:
- Reactive state that re-renders subtrees asynchronously.
- `setAttribute("data-mobile-layout", ...)` from the matchMedia
  listener that fires AFTER CSS load and may interact with the
  override.
- KVision's `setStyle()` calls that inject inline styles AFTER CSS
  load (see "KVision setStyle() writes inline style=" pitfall above).
- A class structure that may differ subtly from what you hand-built
  in the probe HTML (e.g. an extra wrapping div, a missing parent
  class on an internal element).
- Kotlin-side layout decisions (e.g. `padding = CssSize(15, UNIT.px)`)
  that compose with the CSS rule in ways the probe HTML doesn't.

The user has been bitten by HTML-injection probes claiming
"verified" when the real widget rendered differently. They will
reject this as verification.

**The workflow for a CSS-only fix to an in-HEAD widget:**

1. **Drive the real widget through its real flow.** Boot all three
   services (`./debugger/scripts/start_servers.sh` per the boot
   sequence). For MainMenu → PLAY → Step 2 of the
   CommanderSelectionDialog, the canonical flow is:
   - `page.goto('http://127.0.0.1:8080/index.html')`
   - `await page.getByTestId('loading-screen-cta').click()` —
     loading screen dismisses (allow up to 30s for music asset 404
     timeout, see "Loading screen music 404 timeout" pitfall below)
   - `await page.getByTestId('login-as-guest').click()` — real
     AccelByte OAuth (allow up to 90s; OAuth + loadSavedCommanders
     can take a while)
   - `await page.waitForSelector('[data-testid="main-menu"]')` —
     MainMenu mounted
   - Dismiss any post-login MessageBox: poll
     `.autogenesis-message-box-overlay` for an "OK" button, click
     with `force: true` (the modal intercepts pointer events)
   - `await page.locator('[data-testid="main-menu"] .btn-play').first().click()` —
     Step 1 of the wizard
   - `await page.locator('.commander-selection-card').first().click()` —
     pick a commander
   - `await page.getByRole('button', { name: /^Next$/i }).first().click()` —
     Step 2 of the wizard (where the opponent cards live)
   - `await page.waitForSelector('.commander-selection-step-2')` —
     Step 2 content visible
   - `await page.screenshot({ path: '<canonical>/realwidget-390x844.png' })`
   - Vision review via `vision_analyze`.

2. **If the real flow is blocked by an environmental issue** (AccelByte
   unreachable, music asset 404, etc.), report the blocker honestly
   to the user and ASK whether to (a) proceed with HTML-injection as
   a fallback (clearly labeled), (b) ship the CSS fix unverified and
   have the user manually click through, or (c) defer until the
   blocker is resolved. Don't silently substitute HTML-injection for
   real-widget verification.

3. **NEVER claim "verified" on an HTML-injection probe for an in-HEAD
   widget.** Always: *"ad-hoc CSS-rule probe verified the rule
   renders correctly with the widget's class structure. Real-widget
   verification blocked: [reason]. Please visually confirm by clicking
   through MainMenu → PLAY → Step 2 at 390x844, or by reviewing the
   after-390x844.png screenshot from the HTML-injection probe with
   the caveat that the real widget's reactive lifecycle may differ."*

**When HTML-injection IS acceptable:** see the section above — only
when (a) the widget exists ONLY in uncommitted Kotlin, AND (b) no
flow can mount it on `:8080` today, AND (c) the fix is CSS-only and
the rendered DOM geometry is the load-bearing question. Even then,
report it as ad-hoc CSS verification, not as "verified."

**The CommanderSelectionDialog Step 2 specifically** (the wave-2
mobile-portrait widget with three opponent cards 2/3/4 Players):

- Kotlin source: `ui/CommanderSelectionDialog.kt:343` (the hPanel
  containing 3 OpponentCard children, no className)
- CSS rule that landed: `night-mode.css:3886-3908`
- data-testid: `commander-selection-root` (on the overlay root)
- Step 2 selector: `.commander-selection-step-2`
- Reaching Step 2 requires: MainMenu mounted → click PLAY → Step 1
  commander selected → click Next. The Next button is conditionally
  visible (only after a commander is picked), and Step 1 requires at
  least one commander in the list — which requires real OAuth, NOT
  skipLogin (skipLogin's synthetic `"guest-user"` string gets
  rejected by the server's VFS / CloudSave handlers).

---

## Pitfall — Loading screen music asset 404 takes 30s to dismiss on first CTA click

**Symptom:** you boot the game, navigate to `http://127.0.0.1:8080/`,
the LoadingScreen shows "CLICK TO ENTER", you click it, and the
status text changes to "Loading Main menu music... 10%" then hangs
for ~30 seconds before the screen dismisses. The CTA button's CSS
class transitions from `loading-screen-cta--idle` to
`loading-screen-cta--loading` to `loading-screen-cta--ready`. The
30s hang is the music asset 404 + `canplaythrough` timeout.

**Diagnostic to confirm:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 \
  "http://127.0.0.1:8080/audio/music/Xilaron%20and%20Eleuryiyidict%20wet%20final.mp3"
# Expect: 404 in this sandbox (asset dropped / not in dist)
```

Or watch the browser console: `[NETWORK]: Mp3AssetLoader:
canplaythrough timed out (>30s)`.

**Mitigation in probes:**

```javascript
// Don't wait for `data-mobile-layout` on the loading screen — it
// doesn't have it. Wait for the loading screen to FULLY DISMISS,
// then proceed.
await page.getByTestId('loading-screen-cta').click()
const start = Date.now()
while (Date.now() - start < 75000) {
    const gone = await page.evaluate(() => {
        const root = document.querySelector('.loading-screen-root')
        return !root || root.offsetWidth === 0 || getComputedStyle(root).display === 'none'
    })
    if (gone) break
    await page.waitForTimeout(2000)
}
console.log(`loading screen dismissed after ${Math.round((Date.now()-start)/1000)}s`)
// Now expect login-as-guest button to be visible within ~30s.
```

**Why this matters:** if your probe uses a hard `waitForSelector`
with timeout 30000, it will timeout at the 30s mark even though the
loading screen is ALMOST done dismissing. Use the polling loop
above with a 75s ceiling.

**Root cause (not your problem, but worth knowing):** the
`Mp3AssetLoader` for `main-menu-music` resolves
`audio/music/Xilaron and Eleuryiyidict wet final.mp3` from the
AudioResourceLoader manifest. The file isn't in the production
dist (likely dropped during a manual asset cleanup or not committed
to the dist copy step). The LoadingScreen waits for the asset to
either load or 30s to pass before dismissing.

---

## Pitfall — AccelByte OAuth backend unreachable from sandbox blocks real-widget verification (2026-07-15)

**⚠️ CORRECTED 2026-07-15 (v1.18.0):** the original curl recipe below
targeted the namespace ROOT URL, which legitimately returns 404 EVEN
WHEN OAUTH WORKS — the namespace root has no handler at `/`, only
at `/auth/oauth/token`. The 404 was a false signal. The correct test
is the OAuth endpoint itself.

**Symptom:** you drive the live app through the loading screen CTA,
the Login As Guest button appears, you click it, and the app shows
"Login Please Wait" with a spinner indefinitely. No progress after
30s, 60s, 90s. If real network/backend is the issue, the OAuth
round-trip to AccelByte never completes.

**Diagnostic to confirm (CORRECTED 2026-07-15):**

```bash
# CORRECT endpoint to test — this is what the SDK POSTs to:
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 \
  https://echoofmaridia-autogenesis.prod.gamingservices.accelbyte.io/auth/oauth/token
# Returns 200 even when OAuth works (the endpoint exists; valid POSTs
# with valid client credentials get a token, but the URL itself
# responds with 200 to any HTTP request — the namespace root 404s
# because no route is registered at /).
# In this sandbox (2026-07-15): returns 200, OAuth works. Verified
# real OAuth completes and the SDK returns
# accelbyteId=004c3eb02c0b4436b41b24d5d670b0e4.

# WRONG — do NOT use this. The namespace root 404s even when OAuth works:
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 \
  https://echoofmaridia-autogenesis.prod.gamingservices.accelbyte.io
# In this sandbox (2026-07-15): returns 404, but OAuth WORKS — this
# was the false-signal that v1.17.0's recipe gave, and the agent
# fabricated a "sandbox blocks OAuth" blocker narrative from it.
# The user corrected: "stop using the word sandbox as an excuse to do
# a bad job, not do your acutal research."
```

The OLD signal that gave a false positive (DO NOT TRUST):

**The AB tenant URLs are in** `kvisionApp/kvision-iam.local.properties`
(`kvision.baseUrl=https://echoofmaridia-autogenesis.prod.gamingservices.accelbyte.io`)
and `kvisionApp/kvision-global.local.properties`
(`kvision.baseUrl=https://autogenesis.prod.gamingservices.accelbyte.io`).
The OAuth flow in `LoginWidgets.kt:636-785` POSTs to these endpoints;
with the sandbox blocking DNS / returning 404, the round-trip never
resolves.

**What this blocks:** real-widget verification of any widget behind
the OAuth flow — which is most of them. Specifically:
- MainMenu is reachable only after OAuth (no skipLogin path)
- Step 2 of CommanderSelectionDialog requires OAuth (the skipLogin
  synthetic `"guest-user"` string gets rejected by the server's VFS
  / CloudSave handlers — see "Path A — `?skipLogin=true`" section in
  this file for the full reason)
- ResumeOrNewDialog requires OAuth (snapshot is per-account)
- All gameplay UI requires OAuth

**When this hits, the workflow:**

1. **Confirm the blocker** via the two `curl` commands above. Don't
   assume — the auth endpoints could be temporarily down on the
   tenant's side rather than blocked from the sandbox.
2. **Report honestly to the user**: *"Real-widget verification
   blocked: AccelByte OAuth backend unreachable from this sandbox
   (curl confirms DNS failure / 404). The CSS fix in
   night-mode.css is correct per the computed-style probe and the
   HTML-injection visual review, but the real KVision widget's
   reactive lifecycle hasn't been exercised. Options: (a) you click
   through manually at 390x844 and confirm, (b) we ship unverified
   with a regression-risk note, (c) we defer until the OAuth
   backend is reachable."*
3. **Do NOT silently substitute HTML-injection for real-widget
   verification.** The user has explicitly rejected this.
4. **The blocker is environmental, not code.** It's not a skill
   rule — different sessions on networks with AB backend reachability
   will NOT hit this. Document the diagnostic recipe (two curl
   commands) for the next session that hits it.

**Workarounds (none are user-acceptable per the 2026-07-15
directive, listed for completeness):**

- Set up a local AccelByte IAM mock server that accepts the OAuth
  round-trip. Significant engineering effort — not worth it for a
  one-off CSS fix.
- Rotate the test guest account's `GUEST_PASSWORD` to a value that
  bypasses the round-trip. Not actually possible — the OAuth
  round-trip is required to get a session token, regardless of
  credentials.
- Use `?skipLogin=true` and accept that Step 2 of the wizard is
  unreachable. Probes can verify MainMenu + Collection overlay +
  Commander Creation + Settings + Shop + Usage at the MainMenu
  level, but cannot reach Step 2 of the PLAY wizard.

The real-widget-verification-is-mandatory rule from the previous
section wins: when this blocker is active and the user wants
verification of a widget behind OAuth, ASK before falling back to
HTML-injection. The user may have access to the AB backend on a
different network, or may want to ship unverified with a known-risk
note, or may want to defer.

---

## Pitfall — Don't fabricate environment blocker narratives; do real research first (2026-07-15)

Symptom: you hit a real-world verification blocker (a flow fails,
a screen is wrong, an assertion doesn't pass). Instead of doing
archaeology to find the actual cause, you reach for the cheapest
explanation that lets you stop: the sandbox is blocking X, or
the network is unreliable, or the test environment is broken.
You report the blocker to the user without curl-testing the
endpoints, without reading the config files, and without checking
whether the blocker you're citing even applies to the current
failure mode. The user corrects you: stop using the word sandbox
as an excuse to do a bad job, not do your acutal research, and
not obey skills, memory, and instructions.

Why this is a skill-level trap: environment-blame is the cheapest
narrative available to a confused agent. It externalizes the problem
(out of your control), closes the investigation prematurely (no fix
needed from you), and saves cognitive effort. The cost is that you
miss the actual fixable cause and burn user trust.

The 2026-07-15 case study (verbatim from the conversation):

The OAuth flow hung at Login Please Wait indefinitely. The agent
jumped to: AccelByte backend unreachable from this sandbox and
quoted the v1.17.0 curl recipe — which tested the namespace ROOT
URL. That URL returns 404 EVEN WHEN OAUTH WORKS (no route registered
at /). The OAuth endpoint /auth/oauth/token was never curled.
Three minutes of probing later, the same agent curled the right
URL, got 200, and proceeded to a clean real-widget verification.
The blocker was fabricated from a false-signal diagnostic.

Working rule: before reporting any environment blocker, perform
the FULL diagnostic recipe from the relevant pitfall section. For
network connectivity, curl the actual endpoint the application
uses (not the namespace root, not a marketing page, not a global
host that the app doesn't use). For missing files, ls + find +
read the file in question — don't assume the file structure from
the class name. For OAuth timeouts, check the server log AND the
client console for the actual error message, not must be the
sandbox.

The 4-step diagnostic discipline:

1. Read the source. Open the actual file the user asked about.
   Check the file path is real (ls). Read it (cat/read_file).
2. Read the config. Open the actual .properties / .json / YAML
   that the system reads. Confirm the URL/key/path it expects.
3. Test the endpoint the app actually uses. Not a related URL,
   not a documentation page. The exact endpoint from step 2.
4. Read the runtime log. Server-side log for backend issues,
   browser console for client-side issues. The error message
   tells you what's actually wrong.

If after all four steps the blocker is real, report it with
the diagnostic transcript — the curls, the ls output, the log
lines — not a summary statement. The user can spot a fabricated
narrative from a transcript in seconds; they cannot from a
one-line summary.

Memory anti-pattern: don't save a session note like AccelByte
sandbox unreachable — that hardens into a self-imposed constraint
that bites you next session when the environment changes. Save the
DIAGNOSTIC RECIPE that proved it (the two curl commands, the file
paths to check), not the conclusion. Conclusions age; recipes
don't.

---

## Pitfall — Stale-bundle for .local.properties files (separate from CSS stale-bundle, 2026-07-15)

Symptom: the static server at :8080 returns 200 for
index.html and night-mode.css, the AccelByte OAuth endpoint
returns 200, but the OAuth round-trip still hangs at Login
Please Wait. Browser console shows:

```
[REQ] GET http://127.0.0.1:8080/kvision-iam.local.properties
[RES 404] http://127.0.0.1:8080/kvision-iam.local.properties
```

The AccelByte SDK can't find its config. Without it, OAuth
never initializes. Same shape as the CSS-stale-bundle pitfall
but a DIFFERENT file class — the missing files are
.local.properties (AccelByte SDK config), not CSS.

Files that bit on 2026-07-15:

```
kvisionApp/kvision-iam.local.properties       (AccelByte Iam SDK config)
kvisionApp/kvision-global.local.properties    (AccelByte Global SDK config)
```

Both get copied to kvisionApp/build/processedResources/js/main/
during the gradle build but NOT to build/dist/js/productionExecutable/
which is where the static server serves from. So the OAuth SDK
fetches /kvision-iam.local.properties (relative to the page),
gets 404, and OAuth initialization fails silently.

Fix:

```bash
cp kvisionApp/build/processedResources/js/main/kvision-iam.local.properties \
   kvisionApp/build/dist/js/productionExecutable/
cp kvisionApp/build/processedResources/js/main/kvision-global.local.properties \
   kvisionApp/build/dist/js/productionExecutable/
```

Or in one line for any *.local.properties in processedResources:

```bash
cp kvisionApp/build/processedResources/js/main/*.local.properties \
   kvisionApp/build/dist/js/productionExecutable/
```

Why this is the FOURTH stale-bundle class (worth knowing):

1. CSS stale-bundle: edit night-mode.css, copy to
   dist/.../night-mode.css. Documented in v1.11.0.
2. kvisionApp.js stale-bundle: edit Kotlin, run gradle, copy
   bundle to dist. Documented in v1.8.0 (jsBrowserProductionWebpack
   section).
3. processedResources audio/img stale-bundle: assets like
   Xilaron and Eleuryiyidict wet final.mp3 get dropped from
   dist during the webpack bundle step. Documented in the
   jsBrowserProductionWebpack section.
4. .local.properties stale-bundle: config files that the
   AccelByte SDK fetches at runtime are in
   processedResources but not in dist. (NEW in v1.18.0.)

Diagnostic recipe for any future "OAuth won't initialize" or
"Something is 404 in the browser console" issue:

```bash
diff kvisionApp/kvision-iam.local.properties \
     kvisionApp/build/dist/js/productionExecutable/kvision-iam.local.properties
diff kvisionApp/build/processedResources/js/main/kvision-iam.local.properties \
     kvisionApp/build/dist/js/productionExecutable/kvision-iam.local.properties
# The first diff should be empty (dist matches source).
# The second is informational — shows what step of the pipeline
# produced the dist version.
```

If any diff is non-empty, the dist file is stale. Apply the cp
fix above.

Why it happens: the gradle copy task
copyKvisionIamLocalProperties in kvisionApp/build.gradle.kts
copies the .local.properties files to build/processedResources/js/main/
for inclusion in the webpack bundle. But the webpack bundle doesn't
actually copy *.local.properties to the dist output (they're
treated as private config). The static server serves from dist,
which is missing them. Net result: source → processedResources
works, processedResources → dist breaks.

Long-term fix (not done in this session): patch the gradle
copyKvisionIamLocalProperties task (or add a new task) to also
copy *.local.properties to build/dist/js/productionExecutable/.
Until then, the manual cp is the workaround.

---

## Pattern — Desktop-viewport + resize-to-mobile for real-widget verification (2026-07-15)

The problem: every proven mobile-portrait Playwright probe in
this project (per kvisionApp-e2e/probes/guest-login.mjs,
commander-create-mr-tree.mjs, etc.) uses DESKTOP viewport
(width: 1280, height: 800 or width: 1280, height: 900).
This works because the proven desktop login flow lives at desktop
viewport, the OAuth flow takes time and is reliable at desktop,
and the existing probes never need mobile CSS to fire (they assert
desktop behavior).

When this bites: you need to verify a CSS fix that targets
mobile-portrait (@media max-width:600px). The widget is in HEAD
and requires real OAuth to reach. You need:
- Desktop viewport to drive the proven login flow reliably.
- Mobile viewport at the moment of screenshotting, so the @media
  CSS rules actually fire and the mobile layout renders.

The pattern (verified 2026-07-15, CommanderSelectionDialog Step 2):

1. Create the context at desktop viewport (the proven size for
   the proven login flow):

```javascript
const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' +
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    // ↑ desktop UA explicitly — without this, iPhone 12 UA on
    //   chromium-120 sends a mobile UA that some servers reject.
})
```

2. Drive the full flow at desktop viewport — LoadingScreen →
   Login As Guest → MainMenu → PLAY → Step 1 → pick commander →
   Next → Step 2. All at 1280x800.

3. Right before screenshotting, resize to mobile viewport:

```javascript
// Right before screenshotting, after Step 2 is mounted and visible.
await page.waitForSelector('.commander-selection-step-2', { timeout: 10000 })
await page.waitForTimeout(800)   // let layout settle

await page.setViewportSize({ width: 390, height: 844 })

// Wait for the matchMedia listener to fire on resize and update
// data-mobile-layout.
await page.waitForFunction(() => {
    const root = document.querySelector('[data-testid="commander-selection-root"]')
    return root?.getAttribute('data-mobile-layout') === 'portrait'
}, { timeout: 5000 }).catch(() => {})

await page.waitForTimeout(1000)   // let CSS transitions settle
```

4. Screenshot at mobile viewport:

```javascript
await page.screenshot({ path: '<canonical>/realwidget-viewport-390x844.png',
                       fullPage: false })
await page.screenshot({ path: '<canonical>/realwidget-fullpage-390x844.png',
                       fullPage: true })
```

The setViewportSize triggers the browser resize event, which
fires any active matchMedia listeners attached via
addEventListener(change, ...). The CommanderSelectionDialog
listener (and every other widget that uses the v1.17.0+ pattern)
sets data-mobile-layout="portrait" and the @media CSS rules
activate.

Why this works (vs always-mobile-viewport):

- iPhone 12 viewport at 390x844 with devices[iPhone 12] sends
  a mobile User-Agent. Some OAuth endpoints reject mobile UAs.
  Desktop viewport sidesteps this.
- The proven desktop login flow is well-tested at 1280x800.
  Reliably completes in ~30-60s. Don't fight it.
- The matchMedia listener pattern (set up in widget init for
  rotation handling) re-fires on viewport resize. No need to remount
  the widget.

When to use this vs always-mobile viewport:

| Use desktop-then-resize when...                | Use always-mobile when...                          |
|------------------------------------------------|----------------------------------------------------|
| The flow requires OAuth                         | The flow mounts via ?skipLogin=true                |
| The proven desktop probes work for the flow    | No proven mobile probe exists                        |
| The widget is mounted, only the CSS needs to fire | You want to verify the initial mobile mount too  |
| Multiple widgets need mobile verification in one session | One widget, one shot                              |

Probes that use this pattern:

- /tmp/hermes-verify-opponent-cards-reallive-20260715.mjs (this
  session's CommanderSelectionDialog Step 2 probe)

Real-widget verification pitfall extended: this pattern
unblocks real-widget verification for ANY widget whose flow
requires OAuth, when the AB backend IS reachable. The v1.17.0
Real-widget verification is mandatory section assumed you'd
drive the full flow at mobile viewport, which is brittle when
the OAuth step hangs or times out. Desktop-then-resize gives the
proven flow room to work, then snaps to mobile for the actual
verification step.
section wins:** when this blocker is active and the user wants
verification of a widget behind OAuth, ASK before falling back to
HTML-injection. The user may have access to the AB backend on a
different network, or may want to ship unverified with a known-risk
note, or may want to defer.
