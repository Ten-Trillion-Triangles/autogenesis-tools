---
name: autogenesis-mobile-ui-support
description: "Add mobile-portrait rendering support to Autogenesis KVision UI widgets (MainMenu, CollectionOverlay, ShopOverlay, UsageOverlay, SettingsWidget, CommanderCreation, CommanderSelection + its Step 3 SimulationSettingsPage, MessageBox, ResumeOrNew, SurrenderConfirmDialog). When the user reports a widget broken or clipped on a phone (iPhone 12 / 390x844 viewport), when asked to add responsive CSS overrides, or when extending the @media (max-width: 600px) blocks in night-mode.css — start here. CRITICAL: every new wizard step / dialog content panel added to a host that already has mobile rules must ship its OWN @media block or it ships broken on phones (see simulation-settings-mobile-gap.md)."
metadata:
  hermes:
    tags: [autogenesis, mobile, kvision, css, responsive, portrait, iphone, e2e, playwright]
    related_skills: [autogenesis-local-dev, autogenesis-prompt-debugging, autogenesis-rpc-patterns, apex-coder]
---

# Autogenesis Mobile UI Support

Add portrait-phone rendering to Autogenesis widgets via CSS @media overrides. Desktop layout must stay byte-identical. All fixes live inside existing `@media (max-width: 600px), (max-height: 600px) and (orientation: portrait)` blocks in `kvisionApp/src/jsMain/resources/night-mode.css`. No Kotlin changes required for responsive work — only CSS overrides.

## Trigger Conditions

Load this skill when any of these appear:

- User reports a widget clipped, overflowing, or visually broken on a phone
- User asks to "make this work on mobile" or "responsive" for any KVision widget
- A Playwright probe at 390x844 viewport fails an assertion about button size, horizontal overflow, or visible elements
- Extending or adding to the existing `@media` blocks in night-mode.css
- Reviewing mobile screenshots in `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/`
- Working on the **GameplayUI shell** (HUD, score bar, map, Game History, turn progression, command box, or the 12 modal-class widgets sharing `.login-widget-window`). This is a separate round of work from the MainMenu + 7 modal-class overlays covered above. Stitch project, breakpoints, source constraints, and component specs are in `references/gameplay-ui-mobile-adaptation.md` — load it when the task is GameplayUI, not when it's MainMenu.
- Asked to regenerate a Stitch screen for Autogenesis. The Stitch project IDs, design system tokens, and the Game History docking rule (always LEFT across all viewports) are in `references/gameplay-ui-mobile-adaptation.md`.

## The Autogenesis Mobile Context

**Breakpoint**: 600px width. The matchMedia listener in each widget sets `data-mobile-layout="portrait"` (or `"desktop"`) on the root, fired live on rotation via `addEventListener("change", ...)`. All CSS mobile rules must live inside `@media (max-width: 600px), (max-height: 600px) and (orientation: portrait)` blocks. Landscape phones above 600px-wide get the desktop layout via the existing `(min-width: 600px)` fallback semantics.

**The skipLogin path**: `?skipLogin=true` in the URL bypasses the real AccelByte login flow with a guest-user placeholder. It does NOT bypass LoadingScreen — LoadingScreen still mounts first and its CTA must be clicked before MainMenu mounts. All e2e probes must include this CTA click step before waiting for MainMenu or any later widget.

**KVision DOM quirks**: KVision renders `hPanel(...)` as a className-less `<div>` with inline `display: flex; align-items: ...`. The inner action panel inside `.main-menu-bottom` has no className, no id, no data-testid — it's a bare `<div>` styled only by inline attributes. Targeting it via CSS requires either `:has(.btn-play)` (works) or `> div` (stripped by webpack). See the webpack pitfall below.

## File Locations

- Source CSS: `kvisionApp/src/jsMain/resources/night-mode.css` (4323 lines after 2026-07-12 polish; 9 `@media` blocks)
- Built CSS (processedResources): `kvisionApp/build/processedResources/js/main/night-mode.css`
- Built CSS (dist, what static server serves): `kvisionApp/build/dist/js/productionExecutable/night-mode.css`
- Dev server: `kvisionApp-e2e/static-server-8080.mjs` serves `dist/js/productionExecutable/` at `http://127.0.0.1:8080` (NOT `:3000` — that's the webpack-dev-server default in upstream KVision tutorials; the autogenesis scripts override to 8080)
- Probes directory: `kvisionApp-e2e/probes/` — pattern `<feature>-mobile-portrait.mjs` for portrait, `-landscape.mjs` for desktop-fallback verification
- Plan files: `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md` (kebab-case slug, e.g. `loading-screen-mobile-support`, `mobile-ui-rendering-fix`)
- Captured screenshots: `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/YYYY-MM-DD-<slug>/`

## How to Add a New Mobile Override

1. **Diagnose the defect first** — write a probe at iPhone 12 viewport (390x844) that captures DOM measurements + screenshot. Use `kvisionApp-e2e/probes/diagnose-all-mobile.mjs` as the template. The probe dumps bounding rect, computed style, and scroll dimensions for each widget.
2. **Locate the offending selector** — use `chrome devtools`-equivalent probes via `page.evaluate(() => { const el = document.querySelector(...); ... })`. Inline-styled elements need their computed style, not their attribute.

3. **Write the CSS rule inside an existing `@media` block** — append to the appropriate block (MainMenu at line 3278, CollectionOverlay at line 3369, SettingsWidget at line 3388 (delegated to CollectionOverlay's block since they share `.login-widget-window`), Billing Modal at line 3398, ResumeOrNew at line 3500, CommanderSelection at line 3520, CommanderCreation at line 3533). Prefer extending existing blocks over creating new ones.

4. **Verify three checkpoints before claiming the fix works**:
   a. Source: `grep -c '<selector>' kvisionApp/src/jsMain/resources/night-mode.css` >= 1
   b. Built processedResources: `grep -c '<selector>' kvisionApp/build/processedResources/js/main/night-mode.css` >= 1
   c. Dist (what server serves): `grep -c '<selector>' kvisionApp/build/dist/js/productionExecutable/night-mode.css` >= 1

5. **Verify desktop byte-identity at 1440x900** — headerHeight=80px, flexWrap=nowrap, playWidth=200px, playHeight=100px must all be unchanged. Use the `check-desktop-byte-identity.mjs` probe pattern (start a static server, query the same selectors, assert against pre-fix values).

6. **Run the live probe** — `cd kvisionApp-e2e && node probes/<feature>-mobile-portrait.mjs` against a running static server. Expect 8/8 PASS for the mainmenu probe.

7. **Re-run `diagnose-all-mobile.mjs`** to confirm the fix didn't regress other widgets — the probe captures all 10 widgets and dumps measurements.

8. **Commit on `Autogenesis-Mobile` branch** with the pattern `fix(mobile): <what broke> <what now works>`. Single commit per plan; the loading-screen precedent uses 3 commits (CSS + matchMedia listener + probes) but a single-fix plan ships as one commit.

## Multi-Viewport Coverage (REQUIRED for any header/row layout fix)

A defect that passes the iPhone 12 (390×844) probe may still clip on smaller devices (iPhone SE 1st gen 320×568) or smaller-width iPhone SE 3rd gen (375×667). The MainMenu header-row defect (gear clipped at 320×568) shipped first as a "PASS at 390×844" verification and the user caught it on a narrower phone. **For any fix that touches the header row, the right-side action cluster, or the bottom action row, capture and assert at all 5 of these viewports:**

```javascript
const VIEWPORTS = [
    { name: '320x568-iphone-se-1st',     w: 320, h: 568 },
    { name: '375x667-iphone-se-3rd',     w: 375, h: 667 },
    { name: '390x664-iphone-12-mini',    w: 390, h: 664 },
    { name: '390x844-iphone-12',         w: 390, h: 844 },
    { name: '430x932-iphone-14-pro-max', w: 430, h: 932 },
]
```

Per viewport, assert:
- `scrollW <= viewport.w + 1` (no horizontal overflow)
- For the gear/rightmost header element: `element.right <= viewport.w + 1` (not clipped)
- Header secondary buttons are within the compact-band range set by the fix

A reusable probe template is at `scripts/hermes-verify-multi-viewport.mjs` of this skill. Drop it into `kvisionApp-e2e/probes/<feature>-multi-viewport.mjs` for any new fix that touches header/row layout. See `references/multi-viewport-coverage.md` for the canonical example (`mainmenu-mobile-multi-viewport.mjs`).

## Verified Defect Catalog (June 2026 → July 2026)

Each entry shows the diagnostic measurement (before → after fix).

| Widget | Defect | Before | After |
|---|---|---|---|
| MainMenu | PLAY button squished (inner hPanel row layout) | w=18px | w=360px |
| MainMenu | AUTOGENESIS wordmark clipped | scrollW=430 | scrollW=390 |
| MainMenu | Header row stretched (Shop/Usage ~125px tall, credits-pill ~95px tall, gear oversized) | row h=~210px | row h=~64px → ~56px |
| MainMenu | AUTOGENESIS wordmark hidden behind giant buttons | top 40% only visible | fully visible, centered mid-screen |
| MainMenu | Wordmark sits too HIGH (upper-third with dead band below) | top y≈60-180 (close to header) | center y≈400-500 (`background-position: center 55%`) |
| MainMenu | Gear (⚙) clipped off right edge at 320×568 (iPhone SE 1st gen) | gear.right=363, viewport=320 | gear.right=277, clearance=43px (visible) |
| MainMenu | Gear tap target too small (28×28 below iOS HIG 44px) | gear 28x28 | gear 44×44 (auto-passed single-viewport `btn-options >= 44x44` assert as side benefit) |
| MainMenu | Action cluster not pinned to right — leaves 100+px empty space | gear.right=265 (viewport=390) | gear.right=347 (= viewport.w − 43, flush to header padding edge) |
| MainMenu | PLAY button shifted ~9px LEFT of COLLECTION/NEW COMMANDER siblings | play.left=5, collection.left=14 (delta=9) | play.left=14, collection.left=14 (delta=0) |
| SettingsWidget | 600px dialog off-screen left | x=-210 | x=12, w=366 |
| CollectionOverlay | Close (X) stretched to full-width banner | full-width | 44x44 corner icon |
| CollectionOverlay | Tabs icon-only, no labels | 48x48 squares | 90x58 with COMMANDERS/STORIES text |
| ShopOverlay | Modal 13px horizontal overflow | scrollW=403 | scrollW=391 |
| ShopOverlay | GO MONTHLY footer overlap | 3 elements crammed in row | stacked column |
| UsageOverlay | ALL TIME tab wrapped to 2 lines | text wrap | nowrap, 2-row wrap |
| CommanderCreation | Placeholder text clipped mid-word | "Enter your commander's nam" | ellipsis |

The 2026-07-12 followup fix (header shrink to fit 320px + wordmark pan to 55%) is committed as `0924cc9cc` on `Autogenesis-Mobile`. Companion commit to `8febe1c59` from earlier the same day. Multi-viewport verification at commit time: 25/25 PASS at 320, 375, 390×664, 390×844, 430. Single-viewport: 7/9 PASS (2 pre-existing out-of-scope FAILs). See the `multi-viewport-coverage.md` reference for the 5-viewport canonical probe and pitfalls.

Later the same day, three more rounds shipped on `Autogenesis-Mobile`:

- **`6a919f1c7` — hide credits-pill on mobile portrait.** Credits-pill (gem + count + plus button) was eating ~75–118px of horizontal space at 320–430px viewports. Hidden via `@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) { .credits-container { display: none !important } }`. Multi-viewport: 30/30 PASS including a new `credits-pill is hidden (display:none)` assertion. The `BillingState.addListener + refreshCreditPill()` Kotlin wiring stays intact, so the pill reappears with up-to-date text when the viewport widens past 600px.

- **`154920b99` — widen gear to 44px + pin action buttons to right edge.** Gear widened from 28×28 to 44×44 (iOS HIG tap target floor). Right-cluster hPanel pinned to right via two combined CSS rules: `justify-content: flex-end` (pack buttons against each other at right of inner panel) + `margin-left: auto` (shove the entire hPanel against the parent's right padding). Multi-viewport: 40/40 PASS with two new assertions (`gear widened to >= 44px`, `gear pinned to right side of header panel`). Single-viewport: 8/9 (the pre-existing PLAY 360px vs 90vw=351 FAIL is the only one remaining — widening the gear incidentally fixed the prior `btn-options >= 44x44` failure). Probe assertion was wrong on first try (guessed 16px padding instead of the actual 43px); a DOM-tree dump revealed the real number. See the new Pitfall below.

Screenshot at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-12-mainmenu-mobile-fix/mainmenu-390x844-iphone-12.png` is the canonical post-`154920b99` capture. Ad-hoc verifier at `/tmp/hermes-verify-gear-right-pin-20260712.mjs` (4 behavior-focused asserts, all PASS); live multi-viewport + single-viewport suite also green per the rounds above.

- **`d54f8d898` — align PLAY button with COLLECTION/NEW COMMANDER siblings.** PLAY was rendered 9px LEFT of its sibling bottom-row buttons. Root cause: a stale `align-self: center !important` on `.btn-play` inside the mobile @media block was centering the button horizontally inside its parent 362px hPanel, overriding the parent's `align-items: FLEXEND` that COLLECTION and NEW COMMANDER inherited. Removing the `align-self` line lets PLAY inherit FLEXEND and align to the same right edge as its siblings. Multi-viewport: 45/45 PASS with new `PLAY left-aligned with bottom-row siblings (|play.left - sibling.left| <= 2)` assertion. Single-viewport: 8/9 (only the pre-existing PLAY vs 90vw intentional FAIL). Ad-hoc verifier at `/tmp/hermes-verify-play-alignment-20260712.mjs` (3 asserts, all PASS, delta.left=0).

The 2026-07-12 header-stretch + wordmark-pan fix is committed as `8febe1c59` on `Autogenesis-Mobile`. Screenshot at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-12-mainmenu-mobile-fix/mainmenu-390x844-after-fix.png`. Diagnosis + ad-hoc verifier at `/tmp/hermes-verify-mainmenu-mobile-fix-20260712.mjs` (20 assertions, all PASS).
| (Billing modal title) | USAGE & PLAN clipped | "PLAN" cut off | font-size 18px |
| UsageOverlay | ALL TIME button text bleeds past right edge (visual) | `scrollWidth=80, clientWidth=70`, text bleeds 9px past inner content | text bleeds -3px (3px margin) — see batch 3 follow-up below |
| UsageOverlay | Calendar icon overlaps progress bar | cal.x=330, bar.right=342, same y range | cal moved to y=520, below bar with separator |
| UsageOverlay | Right zone (Today UNTIL RESET) takes 99px | `right.h = 99` | `right.h = 29` |
| UsageOverlay | KPI tiles unequal (80/78/80/69) | sub-pixel rounding on inline `width: 25%` | all 68px via `flex: 1 1 0` |
| UsageOverlay | MANAGE button overflows ACTIVE PLAN card left | MANAGE.x=34, planStrip.x=42 (8px overflow) | MANAGE.x=55, full-width inside actions |
| UsageOverlay | No scroll affordance — bottom cut off | contentRoot scrollH=1148, no mask | mask-image linear-gradient on contentRoot |
| CommanderSelectionDialog | NEXT button smaller than CANCEL | inline `width: 180px` both, computed 75px vs 55px (flex-shrink) | both 147px via `flex: 1 1 0` |

**Batch 3 follow-up (2026-07-12):** the batch-2 fix to ALL TIME button shrank padding+font-size, which moved `scrollWidth` from 80 to 70 (= `clientWidth`, so "overflowBy: 0"). But visually the "E" of "TIME" still extended past the button. Root cause: `overflow: visible` lets the browser render text outside the element's box even when no scroll is needed. Real fix: `padding: 8px 6px; font-size: 11px; letter-spacing: 0.03em; overflow: hidden` — verified with `Range.getBoundingClientRect()` comparing textRect to inner content boundary (was +9px bleed, now -3px). See `references/usage-modal-batch-2-batch-3.md` for the full measurement trace and "scrollWidth === clientWidth does NOT mean text fits" pitfall below.

## Key CSS Recipes

### Target a className-less inner panel
The inner hPanel inside `.main-menu-bottom` has no className, no id, no data-testid. The only way to target it via CSS:
```css
.main-menu-bottom > div:has(.btn-play) {
    flex-direction: column !important;
    align-items: stretch !important;
}
```
The `> div` selector ALONE is stripped by webpack's CSS pipeline. Use `:has()` (Chrome 105+, Safari 15.4+, iPhone 12 = Safari 15.4+).

### Show text label from a title attribute
For icon-only buttons that have `title="..."` set in Kotlin:
```css
.collection-tab-button {
    flex-direction: column !important;
    gap: 4px !important;
}
.collection-tab-button::after {
    content: attr(title) !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
}
```

### Override a dialog that uses fixed desktop positioning
SettingsWidget.kt:55-60 sets `width=600px; position=fixed; top=120px; bottom=220px; left=calc(50% - 300px)`. On 390px viewport this puts the dialog at x=-210. Override ALL positioning, not just width:
```css
.login-widget-window {
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px) !important;
    max-height: calc(100vh - 48px) !important;
    left: 12px !important;
    right: 12px !important;
    top: 12px !important;
    bottom: 12px !important;
    height: auto !important;
    transform: none !important;
}
```

### Background-image on root that needs to fit viewport
The AUTOGENESIS wordmark is set via `KEnv.setBackgroundImage("img/AutogenesisTitle.png")` on `mainRoot`, NOT on `.main-menu-center`. Target the root:
```css
#kvapp {
    background-size: contain !important;
    background-position: center top !important;
    background-repeat: no-repeat !important;
}
```

### Flex-wrap tab strip
For 4 tabs that don't fit on one row at 390px, force 2-per-row:
```css
.billing-tabs {
    flex-wrap: wrap !important;
    gap: 8px !important;
}
.billing-tab {
    flex: 1 1 calc(50% - 8px) !important;
    min-width: 0 !important;
    white-space: nowrap !important;
}
```

### Pin a KVision hPanel cluster to the right edge of its parent header
KVision's `hPanel(alignItems = CENTER)` only sets the cross-axis (vertical in a row). It leaves `justify-content` at the default `flex-start`, so children render at the LEFT of the inner panel — leaving the parent's `justify-content: space-between` no room to push the cluster right when a sibling hPanel (e.g. "Guest Commander + v1.0.0") is wide enough to leave the right-cluster overlapping it visually. Symptom: the action cluster appears in the middle of the header band, with 100+px of empty space to the viewport's right edge.

Two CSS properties together pin the cluster right:

```css
/* 1. Pack the buttons against each other at the right of the hPanel */
.main-menu-header > div:last-child {
    justify-content: flex-end !important;
}
/* 2. Push the entire hPanel itself against the parent's right padding.
   `margin-left: auto` is the flex idiom for "consume all free space on
   my left side" — the parent stops trying to use the cluster as the
   right-anchor of `space-between` and just lets auto-margin shove it. */
.main-menu-header > div:last-child {
    margin-left: auto !important;
}
```

Both rules together produce the right-aligned action row the desktop layout has. Either rule alone is insufficient: `flex-end` only re-packs the cluster's children, and `margin-left: auto` only shoves the cluster right without packing its children (they still fan out from the cluster's left).

Verified measurement at 390x844 after applying both rules: right-cluster shifts from `left=14, right=280` (overlapping left cluster) to `left=96, right=362` (flush to the 28px header padding-right edge). Gear.right=347, viewport.w=390 → 43px clearance (28px header padding-right + ~15px internal cluster padding).

**Critical companion rule:** verify the cluster's right edge by computing the EXPECTED gear.right from a DOM tree dump of computed styles + rects, NOT from guessed padding values. See Pitfall "Dump DOM tree before writing positional probe assertions" below.

### KVision hPanel `spacing` overflow at narrow viewports (header row clipping fix)
KVision's `hPanel(spacing = N)` renders as a flex container with `gap: Npx` and children at their intrinsic sizes. When the parent flex row compresses (e.g. header on a 320px phone), the hPanel's children don't shrink by default — they overflow the parent and get clipped by the parent's `overflow: hidden`. To make the row fit at 320px without breaking the gear's tap target:

```css
/* Compress the right-side cluster hPanel — credits-pill + Shop + Usage + gear */
.main-menu-header > div:last-child {
    gap: 6px !important;       /* override KVision's spacing=15 (MainMenu.kt:169) */
}
.main-menu-header > div:last-child > * {
    flex-shrink: 1 !important;
    min-width: 0 !important;   /* allow credits-pill + buttons to compress */
}
/* Keep the gear at its tap-target floor even when the row shrinks */
.main-menu-header > div:last-child > .btn-options {
    min-width: 28px !important; /* higher specificity wins over `> *` */
}
```

The three rules together: shrink the gap, allow every child to compress, then re-pin the one element that must NOT compress (the gear, because it's the only tap target for Settings). At 320×568 the gear.right=277 (43px clearance); at 375 and up it stays at its 28px size with comfortable margins. The credits-pill itself is the element that absorbs the compression (119px → 75px wide).

## Pitfalls (verified — these bit us)

### Dump the DOM tree with computed styles + rects BEFORE writing positional probe assertions
Symptom (real example, 2026-07-12 round 154920b99): you write a probe that asserts `gear.right ≈ viewport.w - 16` based on a guessed header padding of 16px. The probe fails at all 5 viewports; you wonder if your CSS is wrong; you iterate on the CSS again. The actual pin location was `viewport.w - 43` (28px header padding-right + ~15px internal cluster padding) — the probe assertion was wrong, not the CSS.

The fix: BEFORE shipping a probe that asserts any edge pinned to viewport.{left,right,top,bottom}, write a 30-line ad-hoc script that walks the relevant DOM subtree and dumps each element's `display`, `flex-direction`, `justify-content`, `align-items`, `width`, computed `paddingLeft/Right`, and `getBoundingClientRect()`. Run it, read the actual numbers, THEN write the assertions against the ground truth. The script is reusable for the next probe in the same plan and can be deleted (or `/tmp/hermes-verify-*` named and left for diagnostic).

Skeleton:

```javascript
const tree = await page.evaluate(() => {
    function dump(el, depth = 0) {
        const r = el.getBoundingClientRect()
        const cs = window.getComputedStyle(el)
        return `${'  '.repeat(depth)}${el.tagName}.${el.className || '(no-class)'} ` +
               `display=${cs.display} pos=${cs.position} justify=${cs.justifyContent} ` +
               `${Math.round(r.left)},${Math.round(r.top)} ${Math.round(r.width)}x${Math.round(r.height)}\n`
    }
    const root = document.querySelector('.main-menu-header')
    // ... walk children, include paddingRight/paddingLeft for the targeted hPanel
})
console.log(tree)
```

This is especially critical when KVision's `hPanel(spacing = N)` is involved, because KVision renders an extra unstyled wrapper `<div>` per `hPanel()` call that the CSS selector `> div:last-child` does reach but whose own `padding-right` is non-obvious from reading the Kotlin source alone.

### Stale `align-self: center` on one bottom-row button overrides parent's FLEXEND
Symptom (real example, 2026-07-12 round d54f8d898): three buttons stacked in a KVision `hPanel(alignItems = FLEXEND, spacing = 20)` — COLLECTION, NEW COMMANDER, PLAY — but PLAY renders ~9px LEFT of its siblings. The CSS file contains:
```css
.btn-play {
    width: 100% !important;
    max-width: 360px !important;
    align-self: center !important;   /* <— STALE: this is the bug */
}
```
The `align-self: center` overrides the parent's `align-items: FLEXEND` for PLAY only. In a row flex container, `align-self: center` horizontally centers the item within its parent hPanel. Since PLAY has `max-width: 360px` inside a 362px-wide hPanel, the centering pushes it 1px right but the actual cause of the 9px shift is something more subtle (likely the same centering math interacting with KVision's intrinsic-size wrapping).

**Fix**: Delete the `align-self: center !important` line entirely. Let the button inherit FLEXEND from its parent hPanel so it sits at the parent's right edge, lining up with COLLECTION and NEW COMMANDER.

**Detection probe**: write a probe that captures `play.left` and `collection.left` (or any sibling) and asserts `|play.left - sibling.left| <= 2`. If deltas appear consistently across viewports, a stale `align-self` override is the first thing to suspect.

**General rule**: `align-self` on a single child is rarely correct when the parent already has `alignItems` set in the KVision DSL — it always overrides the parent for that one child and breaks visual consistency with the siblings.

###
Symptom: rule like `.main-menu-bottom > div { ... }` doesn't fire in the served bundle, only the source CSS. webpack emits rules as flat selectors — `.main-menu-bottom > div` shows up as just `"main-menu-bottom"` in the JS bundle. Always use `:has(...)` to anchor to a known inner element. **Detection**: `grep -oE '"\.selector[^"]*"' kvisionApp.js | head -5` — if your `> div` selector doesn't appear, webpack stripped it.

### night-mode.css is emitted as a separate file, NOT inlined in JS
webpack outputs `kvisionApp/build/dist/js/productionExecutable/night-mode.css` as a sidecar file, referenced via `<link rel="stylesheet">` in `index.html`. The `:kvisionApp:jsBrowserProductionWebpack` task regenerates the JS bundle but does NOT re-copy `processedResources/night-mode.css` to `dist/`. After every CSS edit, you must manually:
```bash
cd kvisionApp
./gradlew :kvisionApp:jsProcessResources -Pkvision.liveMode=true
cp build/processedResources/js/main/night-mode.css build/dist/js/productionExecutable/night-mode.css
```
The actual `cp` step lives in `amplify.yml` postBuild phase (lines 144-156), not in `build.gradle.kts`. Until Amplify deploys, local dev needs the manual `cp` to see CSS changes. **Detection**: if `grep '<selector>' processedResources/night-mode.css` returns 1 hit but `grep '<selector>' dist/night-mode.css` returns 0, the dist file is stale.

### Playwright probe LoadingScreen CTA click is mandatory even with skipLogin
Probes that wait for `[data-testid="main-menu"]` will time out at 15s if they don't click the LoadingScreen CTA first. LoadingScreen mounts unconditionally on every page load; `?skipLogin=true` only bypasses the AccelByte login flow, not LoadingScreen. Required probe prefix:
```javascript
await page.waitForSelector('[data-testid="loading-screen-cta"]', { timeout: 15000 })
await page.click('[data-testid="loading-screen-cta"]')
await page.waitForSelector('[data-testid="main-menu"]', { timeout: 20000 })
```

### `window.innerWidth` at probe top-level crashes with "window is not defined"
Playwright probes run in Node.js scope. `window` is undefined at the top level. Always read viewport metrics inside `page.evaluate`:
```javascript
// BAD — throws ReferenceError: window is not defined
playBox.width <= window.innerWidth * 0.9

// GOOD — read inside evaluate
const playBox = await page.evaluate(() => {
    const r = document.querySelector('.btn-play').getBoundingClientRect()
    return { width: r.width, height: r.height, vw: window.innerWidth }
})
playBox.width <= playBox.vw * 0.9
```

### Force-click on header buttons is unreliable after layout shifts
Playwright's `click({ force: true })` skips intercept-checks but still computes the click coordinates from the current bounding rect. After mobile CSS makes the header collapse vertically, the header may end up under another element via stacking context. Direct JS click is more reliable:
```javascript
await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('.main-menu-header button'))
        .find(b => b.textContent.trim().includes('Shop'))
    btn?.click()
})
await page.waitForSelector('.billing-modal-window-host', { timeout: 5000 })
```

### z-index hack to expose bottom-row clicks
In the diagnostic probe (not the production CSS), to prevent the bottom-row buttons from intercepting clicks meant for the header, inject a runtime style:
```javascript
await page.addStyleTag({ content: '.main-menu-header { z-index: -1 !important; }' })
```
**Do NOT use `pointer-events: none`** — that makes the Shop/Usage/Options buttons in the header non-clickable, breaking the rest of the diagnostic flow. Use only `z-index: -1`. Even better: remove the hack entirely once the CSS fix collapses the inner panel (the original problem goes away).

### Static server's stale bundle after CSS edit
`static-server-8080.mjs` serves whatever's on disk in `dist/js/productionExecutable/`. If you edit `night-mode.css` and rebuild but skip the `cp` step, the server keeps serving the OLD CSS and your changes appear to have no effect. Symptom: `grep` confirms the selector is in source + processedResources, but the served page (or probe assertions) behave as if it isn't there. **Always run the `cp` step before re-probing.**

For a CSS-only edit where `processedResources/night-mode.css` is already in sync (the common case for this work), the dist cp alone is sufficient:

```bash
cp kvisionApp/src/jsMain/resources/night-mode.css \
   kvisionApp/build/dist/js/productionExecutable/night-mode.css
```

Only run the full `:kvisionApp:jsProcessResources + cp` chain when the src and processedResources diverge (e.g. resource additions). The CSS ship-as-sidecar file pattern makes the local dev loop trivially fast.

### `text-overflow: ellipsis` needs `box-sizing: border-box` to work
If the input has `width: 100%` and no `box-sizing: border-box`, the padding extends past the width and the ellipsis renders on an over-padded element. Always pair them:
```css
.commander-creation-dialog input[type="text"] {
    width: 100% !important;
    box-sizing: border-box !important;
    text-overflow: ellipsis !important;
}
```

### Full webpack rebuild OOM-kills on this sandbox — skip it for CSS-only work
`:kvisionApp:jsBrowserProductionWebpack` exits with SIGKILL (137) at ~40s into webpack compile on this sandbox. The Gradle config + Kotlin/JS plugin tasks complete fine; the actual webpack bundle step blows the heap. Don't waste tool budget retrying it for a 5-line CSS tweak. The CSS ships as a separate file (see the `cp` recipe above), so the webpack rebuild is not needed for CSS verification. Only invoke the rebuild when a `.kt` file changed in the same plan, and even then, consider whether the change can ship without a rebuild.

### Do NOT set `CODEARTIFACT_AUTH_TOKEN` for Autogenesis work
`~/.gradle/init.d/chronotrace.gradle.kts` (and any sibling TPipe/ChronoTrace init script) sets `RepositoriesMode.PREFER_SETTINGS` and wires the CodeArtifact Maven mirror. Autogenesis does NOT use CodeArtifact; only TPipe/ChronoTrace do. If your kvisionApp build dies with `Could not find org.nodejs:node:22.0.0`, the chronotrace init script is blocking the node-gradle plugin's project-level `https://nodejs.org/dist/` repo. Don't try to "fix" this by setting the token — that's bleed from a different workspace. Either:
1. Temporarily rename the init script (`mv ~/.gradle/init.d/chronotrace.gradle.kts ~/.gradle/init.d/chronotrace.gradle.kts.disabled`), build, then rename back. NEVER delete — it belongs to a different workspace.
2. Skip the webpack rebuild entirely (see above) and use the cp recipe. This is the right default for CSS-only mobile work.

### E2E probes have pre-existing FAILs — parse `PASS:`/`FAIL:` markers, don't trust exit code
Several kvisionApp e2e probes have FAILs that predate the current commit work. Example: `mainmenu-mobile-portrait.mjs` as of 2026-07-12 has two FAILs that are pre-existing (PLAY button width > 90vw due to `max-width: 360px`, btn-options 28x44 from an earlier polish pass). When you modify a probe and it exits non-zero:
1. **Don't panic**, don't claim regression unless you can SHOW the test was green before your change.
2. Parse the probe output for `PASS:` and `FAIL:` markers. If the failing checks predate the current commit, that's expected — the probe was already broken.
3. The honest summary is "N new checks added, all PASS; the M FAILs that remain are pre-existing." That's better evidence than a zero-exit happy-path that's just because you removed the test.

For a reusable verifier pattern that handles this correctly, see the new `scripts/hermes-verify-mobile-ui-node.mjs` (the Node.js sibling of `scripts/hermes-verify-mobile-ui.sh`) which asserts on PASS/FAIL markers and explicitly carves out pre-existing FAILs as expected.

### Dev port is :8080, not :3000
KVision's docs and most KVision tutorials default `webpack-dev-server` to `:3000`. Autogenesis overrides to `:8080` via `kvisionApp-e2e/static-server-8080.mjs`. If you copy a "standard KVision probe" into the repo, change `BASE_URL` to `http://127.0.0.1:8080` and ensure `node kvisionApp-e2e/static-server-8080.mjs &` is running first. Symptom of the wrong port: probe connects (gets HTML), but the JS bundle 404s, and every `data-testid` selector times out — the serving layer is fine, but it's serving from the wrong upstream.

### Billing modal scroll-container chain — only the innermost contentRoot actually scrolls
Symptom (real example, 2026-07-12 Usage modal diagnosis): you probe `.modal.billing-modal-window-host`, see `overflowY: auto`, see `scrollH: 842, clientH: 842` (no overflow), and assume the modal doesn't scroll. You ask "does this scroll?" and the user says "no" — but it DOES scroll, just not on the host. The BillingOverlayWindow modal renders as a 5-layer flex chain:

```
.modal.billing-modal-window-host     overflowY: auto,  scrollH=842 clientH=842  → no overflow
  > .modal-dialog                    overflowY: visible, scrollH=782 clientH=782 → not scrollable
    > .modal-content                 overflowY: hidden,   scrollH=780 clientH=780 → not scrollable
      > .modal-body.billing-modal-body  overflowY: auto, scrollH=707 clientH=707 → scrollH==clientH, no overflow
        > .billing-modal-content-root   overflowY: auto, scrollH=1148 clientH=675 → REAL scroll container
```

**Always walk the entire scroll chain before claiming "modal doesn't scroll."** Measure scrollH vs clientH on every layer. The layer where scrollH > clientH is the actual scroll surface. On the Usage modal at 390×844, it's `.billing-modal-content-root` with 473px of hidden content (DAILY TOKEN BURN mid-card, KPI tiles, ACTIVE PLAN, MANAGE/UPGRADE, RECENT DEDUCTIONS — all reachable via scroll).

**Probe recipe** for any future modal-scroll diagnosis:
```javascript
const layers = ['.modal.billing-modal-window-host', '.modal-dialog', '.modal-content', '.modal-body.billing-modal-body', '.billing-modal-content-root'];
const data = await page.evaluate((sels) => sels.map(s => {
  const el = document.querySelector(s);
  if (!el) return { selector: s, missing: true };
  const cs = getComputedStyle(el);
  return { selector: s, overflowY: cs.overflowY, scrollH: el.scrollHeight, clientH: el.clientHeight, isScrollable: (cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight };
}, layers), data);
const scrollable = data.filter(d => d.isScrollable);
console.log('Scrollable layers:', scrollable.map(d => d.selector));
// Always assert: scrollable.length === 1 (modal has exactly ONE scroll container)
```

If `scrollable.length > 1` the modal has competing scroll surfaces (usually a bug). If `scrollable.length === 0` the modal truly doesn't scroll and content is clipped.

### Playwright `page.mouse.wheel()` does NOT scroll KVision modals — use CDP touch dispatch
Symptom (real example, 2026-07-12 Usage modal verification): you `await page.mouse.wheel(0, 500)` and `scrollTop` stays 0. You conclude "modal doesn't scroll on this device." But it DOES scroll — just not via wheel. Two reasons:

1. `page.mouse.wheel()` is a mouse-input API. On a context with `isMobile: true, hasTouch: true`, the wheel event has no implicit focus on the scrollable element — the event fires but the browser routes it based on `document.elementFromPoint(...)`, which on mobile emulation may route to the backdrop, not the contentRoot.
2. Real mobile devices scroll via touch (finger drag), not wheel. Mouse wheel events on real mobile Safari/Chrome are not native — they're synthesized by desktop browser devtools.

**Fix**: use CDP's `Input.dispatchTouchEvent` sequence to simulate a real touch swipe:
```javascript
const client = await ctx.newCDPSession(page);
await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: 195, y: 600 }] });
for (let i = 0; i < 20; i++) {
  await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: 195, y: 600 - i * 20 }] });
  await page.waitForTimeout(20);
}
await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
const afterScroll = await page.evaluate(() => document.querySelector(".billing-modal-content-root").scrollTop);
```

A 400px swipe on a Usage modal with 473px max scroll typically produces `afterScroll ≈ 430-470` (most of the max). If `afterTouch` is non-zero, real touch scroll works — the modal IS scrollable on mobile devices, even if `mouse.wheel` reports zero.

**General rule for mobile-scroll verification**: programmatic `element.scrollTop = N` is the cheapest proof that the chain is scrollable; CDP touch dispatch is the proof that real user gestures will scroll it; mouse wheel is unreliable and should not be the basis of a "doesn't scroll" verdict.

### `hPanel(spacing=N)` injects inline `margin-right: Npx` on every child — flex math must account for it
Symptom (real example, 2026-07-12 Usage tab strip diagnosis): 4 buttons inside `hPanel(spacing = 8)` should each be `(stripInnerWidth - 3×8) / 4 = 76.25px` wide when given `flex: 1 1 0`. They're only 72px each. You wonder if `flex-grow: 1` is broken — it's not. KVision's `hPanel(spacing = N)` injects `style="margin-right: Npx;"` on every child, including the last one. So the flex math is: `4 × button-width + 4 × 8px margin = stripInnerWidth`. With 369px strip − 48px padding (24px each side) = 321px inner. Each button gets `(321 - 32) / 4 = 72.25px` — which matches the measured 72.125px.

**Implication for text overflow inside buttons**: with 14px×2 padding = 28px and 8 chars × ~6.5px = ~52px text, the button needs at least 80px content area. A 72px button has only 70px content area (72 − 2 padding) — **10px short**. The text "ALL TIME" overflows the button by 10px even though the button itself fits the strip.

**Diagnostic probe** to confirm text-overflow-inside-button:
```javascript
const tabs = Array.from(document.querySelectorAll('.usage-tab-strip .billing-tab'));
const tabData = tabs.map(t => {
  const r = t.getBoundingClientRect();
  return { label: t.textContent.trim(), w: r.width, clientW: t.clientWidth, scrollW: t.scrollWidth };
});
// Assert: scrollW > clientW → text overflows the button's content area
const overflowing = tabData.filter(t => t.scrollW > t.clientW);
```

**Fix options** (in order of preference):
1. Shrink `padding` from `14px` to `10px` (saves 8px per side = 16px total — enough for the 10px overflow).
2. Shrink `font-size` from `13px` to `12px` (saves ~8% text width).
3. Allow `white-space: normal` and let the button grow taller (2 lines) — but this breaks the "compact pill" design intent.
4. Use `text-overflow: ellipsis` + `overflow: hidden` + `white-space: nowrap` — clip the visible text with "…" (worst UX for a 4-tab strip where each label is meaningful).

Default: option 1 or 2. Verify with the `scrollW > clientW` probe that `scrollW == clientW` after the fix.

### `scrollWidth > clientWidth` is the universal "content overflows its container" probe
When ANY element clips its content (button text, input placeholder, card label), measure `scrollWidth` vs `clientWidth`:
- `scrollWidth === clientWidth` → content fits exactly
- `scrollWidth > clientWidth` → content overflows (clip, scroll, or visually broken)
- `scrollWidth < clientWidth` → unused space

This is the cheap, universal probe for "is anything being clipped here?" It works for buttons, inputs, cards, badges, anything with intrinsic content. Pair it with `getBoundingClientRect()` to get the visible position.

Worked example (Usage tab strip, 2026-07-12):
| button | w | clientW | scrollW | verdict |
|---|---|---|---|---|
| WEEK | 72 | 70 | 70 | fits exactly |
| MONTH | 72 | 70 | 70 | fits exactly |
| YEAR | 72 | 70 | 70 | fits exactly |
| ALL TIME | 72 | 70 | **80** | **10px overflow** (text "ALL TIME" clips) |

The 10px overflow on ALL TIME only — the other 3 buttons fit because their labels are shorter (4-5 chars vs 8). A multi-label button row where labels have different lengths needs padding/font-size tuned for the LONGEST label, not the median.

### `scrollWidth === clientWidth` does NOT mean text fits in its button
Symptom (real example, 2026-07-12 ALL TIME bleed): the batch-2 fix shrank padding+font-size, probe reported `scrollWidth=80, clientWidth=70, overflowBy=10px` — that's the BEFORE state. After the same fix landed, probe reported `scrollWidth=70, clientWidth=70, overflowBy=0` — "no overflow." But the user's screenshot STILL showed "E" extending past the button right edge. The fix shipped as PASS but visually didn't.

**The gotcha:** `scrollWidth === clientWidth` is the universal "content fits inside the element's clip rectangle" probe, but it does NOT account for `overflow: visible` — the default for buttons. With `overflow: visible`, the browser is allowed to render the text outside the element's box even when no scroll is needed (because no scroll is needed — the text "fits" in the document's view, just not in the box).

**Right measurement:** use `Range.getBoundingClientRect()` to get the actual rendered text geometry, then compare to the element's inner content boundary (rect minus padding minus border):
```javascript
const range = document.createRange()
range.selectNodeContents(btn)
const textRect = range.getBoundingClientRect()
const r = btn.getBoundingClientRect()
const cs = getComputedStyle(btn)
const innerContentRight = r.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth || 0)
const textBleedsRightBy = textRect.right - innerContentRight
// textBleedsRightBy > 0 → text extends past the inner content boundary
// textBleedsRightBy <= 0 → text fits inside
```

**Fix pattern when text bleeds:** add `overflow: hidden` as belt-and-suspenders, AND shrink the text by enough to fit. Padding+font-size alone is not enough if `overflow: visible` is set — the text will still render past the box. The combination `padding: 8px 6px; font-size: 11px; letter-spacing: 0.03em; overflow: hidden` was needed for "ALL TIME" (8 chars at 11px with 6px horizontal padding fits inside 50px inner content).

**General rule:** for "is this text actually contained in its container?" claims, the answer is `Range.getBoundingClientRect()` compared to the inner content boundary, NEVER trust `scrollWidth` alone. See `references/usage-modal-batch-2-batch-3.md` for the full before/after measurement trace.

### Same inline `width` on two siblings renders at different sizes — flex shrink with non-uniform basis
Symptom (real example, 2026-07-12 CommanderSelectionDialog): two buttons (CANCEL and NEXT) both with inline `width: 180px` in Kotlin, both in the same hPanel parent, render at 75px and 55px respectively. The user sees "NEXT is much smaller than CANCEL."

**Root cause:** the parent hPanel has `display: flex; flex-direction: row` (KVision's `hPanel(spacing=N)`). The buttons are flex children with default `flex: 0 1 auto` (Bootstrap button style). When the parent's available width is less than the sum of children's requested widths, flex-shrink kicks in — and **`flex-shrink: 1` shrinks children NON-UNIFORMLY by content-size basis**. The button with more text characters shrinks MORE. CANCEL has 6 chars, NEXT has 4 chars — wait, no, NEXT has 4 chars, CANCEL has 6 chars. So CANCEL shrinks more. But the measurement showed the OPPOSITE: CANCEL=75, NEXT=55. Why?

Re-checking: in this case, the inline `margin-right: 16px` from `hPanel(spacing=16)` was also flex-basis'd into the shrink calculation. KVision's `hPanel(spacing=N)` injects `margin-right: Npx` on every child INCLUDING THE LAST ONE — so the flex math is `4 × button-width + 4 × 16px margin = available`. Both buttons had the same `margin-right: 16px`, so they should shrink equally... but NEXT happened to have `text-align: center` in the `.btn-secondary-action` style which interacts with the flex shrinking. The exact reason doesn't matter — the **fix** is to override the entire flex chain:

```css
/* Force equal-width distribution + pin min-width + override inline width */
.parent-hpanel > button {
    flex: 1 1 0 !important;       /* equal share, not content-sized */
    min-width: 100px !important;  /* floor under which neither can collapse */
    width: auto !important;       /* override the inline width: 180px from Kotlin */
    margin-right: 0 !important;   /* override KVision's hPanel spacing */
}
```

**Probe to confirm the diagnosis:**
```javascript
const buttons = Array.from(document.querySelectorAll('.parent-hpanel > button'))
buttons.map(b => {
    const r = b.getBoundingClientRect()
    const cs = getComputedStyle(b)
    return {
        text: b.textContent.trim(),
        inlineW: b.getAttribute('style')?.match(/width:\s*(\d+)px/)?.[1],  // extract inline width
        computedW: cs.width,
        computedFlex: cs.flex,
        clientW: b.clientWidth,
        rectW: Math.round(r.width),
    }
})
// If inlineW is consistent (both 180) but rectW differs (75 vs 55), flex shrink is the cause
```

**General rule:** "buttons render at different sizes despite same inline width" is almost always flex shrink, not the inline style being wrong. The fix is the flex chain override, not the inline width.

### Stale verifier cache holds deleted file paths
Symptom (real example, 2026-07-12 ALL TIME bleed follow-up): after deleting `/tmp/hermes-verify-usage-scroll-20260712.mjs` (it failed because /tmp has no node_modules), the system verifier cache still showed it as "last command" with the failure output. Subsequent re-runs of the same-named verifier (or any other probe) returned `stale` because the cache held the old path.

**Fix:** run the verifier and capture output to a NEW hermes-prefixed file path so the system sees fresh evidence:
```bash
mkdir -p /tmp/hermes-verify-<topic>-YYYYMMDD
ln -sfn /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules /tmp/hermes-verify-<topic>-YYYYMMDD/node_modules
cp kvisionApp-e2e/probes/<verifier>.mjs /tmp/hermes-verify-<topic>-YYYYMMDD/verify.mjs
cd /tmp/hermes-verify-<topic>-YYYYMMDD && node verify.mjs > /tmp/hermes-verify-<topic>-YYYYMMDD/output.json 2>&1
```

The captured output file at `/tmp/hermes-verify-<topic>-YYYYMMDD/output.json` is what the verifier cache will see as fresh evidence. Re-running the same-named verifier doesn't always invalidate the cache — capture to a new file path.

**General rule:** for ad-hoc verification in a session that already has a stale cache entry, always create a new hermes-prefixed directory and capture to a new file. The cache key is the file path, not the script content.

### Never capture pre-edit screenshots when the user asks for "the fix"
The user asked "run the game and capture a screenshot, lets see how close we got to fixing the layout" — and got back screenshots identical to the previous run, because I had been waiting for an explicit go-ahead to apply the CSS but never applied it. Result: one wasted round-trip plus a "the image looks EXACTLY the same" frustration signal.

**The right read**: "run the game and capture a screenshot" after a stated intent to fix something implies "show me the fix in place." If you have a CSS patch drafted but uncommitted, **apply it first** (sync to dist, run probe, capture), THEN ask "want me to commit?" — that's the screenshot after the fix. Capturing pre-edit state and calling it "the fix" is a Class-7 narration-over-execution error.

Exception: if the user explicitly said "show me the current state first," then capture pre-edit. Otherwise, default to "apply + capture after."

### New wizard step / dialog content panel without matching `@media` block ships broken on phones
Symptom (real example, 2026-08-10 SimulationSettingsPage audit): the CommanderSelectionDialog wizard grew from 2 steps (Step 1 commander picker, Step 2 game-type + opponents) to 3 steps — Step 3 is the new SimulationSettingsPage (roster + slot count + map picker) introduced by the `Core ui fixes and changes for simulation mode` commit (`c6c9f2ca2`). The dialog host (`.commander-selection-window`) has comprehensive mobile rules at `night-mode.css:4028-4135` — overlay/window width:100vw, padding 12px, gap 8px, footer buttons flex 1 1 0, opponent cards stacked, active-card glow shrunk. **None of those rules apply to Step 3's new classes:** `.simulation-settings-body`, `.commander-mini-card`, `.simulation-map-card`, `.simulation-map-card-active`, `.commander-mini-card.commander-selection-card-active`. All five selectors live at `night-mode.css:5123-5218` with desktop styling only. The 50px gold box-shadow + 25px inset glow + 60px cyan halo on active cards bleeds well past the 358px modal width on portrait.

**Detection recipe** — when a new KVision widget or wizard step lands:

```bash
# 1. Find the new selectors in the desktop CSS block
grep -nE '^\.(simulation-settings|commander-mini|simulation-map)' kvisionApp/src/jsMain/resources/night-mode.css

# 2. Check whether those selectors appear INSIDE any @media block
awk '/^@media \(max-width: 600px\)/,/^}$/' kvisionApp/src/jsMain/resources/night-mode.css \
  | grep -nE '^\.(simulation-settings|commander-mini|simulation-map)'
# If (1) returns matches and (2) returns nothing, the new selectors are desktop-only.
```

**Fix template** — append a new `@media` block (or extend the closest existing one). The six rules the SimulationSettingsPage fix needs:

```css
@media (max-width: 600px), (max-height: 600px) and (orientation: portrait) {
  /* 1. Tighten the scroll body gap to match dialog compaction (line 4056) */
  .simulation-settings-body { gap: 8px !important; }

  /* 2. Mini-card active-state glow — shrink + clip, mirror line 4077-4084 */
  .commander-mini-card.commander-selection-card-active {
    box-shadow: 0 0 18px rgba(255, 215, 0, 0.55),
                inset 0 0 12px rgba(255, 215, 0, 0.3) !important;
    overflow: hidden !important;
  }
  .commander-mini-card.commander-selection-card-active::after { display: none !important; }

  /* 3. Map-card active-state glow — same shrink + clip pattern */
  .simulation-map-card-active {
    box-shadow: 0 0 18px rgba(255, 215, 0, 0.55),
                inset 0 0 12px rgba(255, 215, 0, 0.3) !important;
    overflow: hidden !important;
  }
  .simulation-map-card-active::after { display: none !important; }

  /* 4. Long commander / map names — prevent card width blow-out */
  .commander-mini-card > div,
  .simulation-map-card > div { min-width: 0 !important; width: 100% !important; }
  .commander-mini-card span,
  .simulation-map-card span { overflow-wrap: anywhere !important; word-break: break-word !important; }
}
```

**General rule**: when adding a new KVision widget, dialog step, or modal sub-section to a host that already has mobile-portrait rules, the new content is NOT covered by the host's `@media` block — host rules apply to the host's own selectors only. Each new content class must add its own `@media` block, or the existing block must be extended to include it. Treat the mobile-CSS-coverage audit as part of the merge gate for any UI-affecting PR.

**Companion rule for KVision code shape**: when a wizard host already exposes a `data-mobile-layout="portrait"` attribute via its matchMedia listener (e.g. `CommanderSelectionDialog.kt:319-338`), the new step inherits the breakpoint signal but NOT the CSS rules. Don't rely on the host's data attribute as proof of mobile coverage — verify the selectors.

### Game History docks LEFT across ALL viewports (operator-confirmed 2026-07-19)
Symptom: regenerating a Stitch landscape screen for Autogenesis GameplayUI, you assume "in landscape, flip Game History to the right so the map has more space." You ship `26f51b918ca5470388657694d9c37122` with Game History on top as a horizontal drawer. Operator overrides: Game History MUST stay on the LEFT rail across portrait AND landscape, even when the map needs the right side.

**Rule**: When generating or patching any Stitch screen, CSS rule, or probe for Autogenesis GameplayUI's Game History panel, dock it LEFT (`left: 0`, `right: auto`). Never `right: 0` for landscape.

**Background**: the 2026-07-19 correction changed landscape Game History CSS from `right: 0` to `left: 0, right: auto`. The CSS was wrong, then patched; the Stitch screen was regenerated (`26f51b91…` → `9fe2b886…`). Don't reintroduce the right-dock variant.

**Source-of-truth hierarchy when patching this rule**: (1) operator confirmation wins, (2) then the plan file at `~/.hermes/plans/mobile-adaptation/plan.md` must be updated, (3) then CSS, (4) then Stitch regen LAST so the visual matches the canonical source. If you patch one tier without the others, drift recurs.

**Verification before claiming "Game History is left-docked":**
- CSS: `grep -n "game-history\|gameHistory\|game-history-panel" kvisionApp/src/jsMain/resources/night-mode.css | grep -E "left|right"` — confirm a `left:` declaration appears in the landscape media query block, NOT a `right:`.
- Stitch: the regenerated landscape screen ID is `9fe2b886526d40e393b9d7c3e5f90c83`. Old broken ID is `26f51b918ca5470388657694d9c37122` (do not reuse).
- Live DOM at 920×420 (landscape): `document.querySelector('[class*="game-history"]').getBoundingClientRect().left` should be `0` or within the left padding margin (~12px).


## Verification Recipe (ad-hoc, idempotent)

A reusable recipe for verifying mobile-CSS changes is at `/tmp/hermes-verify-mobile-ui-fix.sh` (template in `scripts/hermes-verify-mobile-ui.sh` of this skill). The script checks:

1. Source CSS contains the new selectors (10 selectors from the defect catalog)
2. Desktop-layout safety: 0 top-level (non-indented) CSS property additions — every change lives inside a `@media` block
3. `processedResources` CSS contains the selectors (webpack emitted them)
4. `dist` CSS contains the selectors (what the server actually serves)
5. Both probe files pass `node --check` syntax validation
6. mainmenu probe has the LoadingScreen CTA click step
7. mainmenu probe has no bare `window.innerWidth` outside `page.evaluate` (awk-line-tracked)
8. Commit `ec9be11b3` (or whichever) is in Autogenesis-Mobile history

Run after every CSS change. Result pattern: ~26 PASS / 0 FAIL for the mobile-ui-render-fix plan.

### Per-commit ad-hoc verifier (positional fixes)

When a CSS commit targets the **position** of a single element (left, right, width, alignment, pin-to-edge), the canonical multi-viewport + single-viewport suite probes may pass without ever showing the behavior delta because they assert general invariants. For those commits, also ship a focused ad-hoc verifier under `/tmp/hermes-verify-<feature>-YYYYMMDD.mjs` that:

1. Captures `getBoundingClientRect()` of the targeted element AND its expected peer (sibling or anchor)
2. Asserts the deltas match the design intent directly
3. Prints the raw numbers on success AND failure so future debugging has ground truth

Template at `scripts/hermes-verify-adhoc-positional.mjs` of this skill. Two real examples from 2026-07-12:

- `/tmp/hermes-verify-gear-right-pin-20260712.mjs` (commit 154920b99) — 4 asserts: gear width, gear position relative to "v1.0.0" text, gear right edge ≈ viewport.w − 43, no horizontal overflow
- `/tmp/hermes-verify-play-alignment-20260712.mjs` (commit d54f8d898) — 3 asserts: PLAY.left == COLLECTION.left, PLAY.right == COLLECTION.right (within 2px), PLAY.width unchanged at 360px (max-width regression guard)

These verifiers are NOT part of the suite (they live in `/tmp`, not `kvisionApp-e2e/probes/`) and are NOT meant to be run repeatedly. Their purpose is to give the operator a clean "before / after this commit" evidence trail that doesn't get drowned in the other 40+ suite assertions. Reuse the template for any future positional fix.

### Modal-scroll ad-hoc verifier (recipe for "does this modal scroll?")

For commits that change a modal's scroll behavior (fix scroll-container chain, make modal-body overflow-y:auto, fix a clipped history list), the canonical positional verifier template isn't enough — you also need to prove that the scroll surface is reachable end-to-end. The recipe:

1. **Walk the scroll chain** (per the "Billing modal scroll-container chain" pitfall below) — measure scrollH vs clientH on every layer between `.modal.billing-modal-window-host` and the innermost contentRoot. Confirm exactly ONE layer is the real scroll surface.
2. **Programmatic scroll** — set `element.scrollTop = 9999`, verify it advances to the max scroll value (= `scrollH - clientH`).
3. **Real-touch scroll** — use CDP `Input.dispatchTouchEvent` (touchStart/touchMove/touchEnd sequence), verify `afterScroll > 0`. Mouse wheel is unreliable on mobile-emulated contexts (see "Playwright mouse.wheel does NOT scroll KVision modals" pitfall below).
4. **Visual destination check** — screenshot at `scrollTop = (scrollH - clientH)` and confirm the content you expected to reach is visible (e.g., RECENT DEDUCTIONS, footer buttons, plan strip).
5. **Text-overflow probe** — for any buttons/badges inside the modal, compare `scrollWidth` vs `clientWidth`. Anything where `scrollWidth > clientWidth` is clipping text inside its container.

## Browser Viewport Reference

iPhone 12 (the standard portrait target):
- Viewport: 390x844 (logical), DPR=3
- matchMedia `(max-width: 600px)`: true → portrait
- matchMedia `(max-height: 600px) and (orientation: portrait)`: true (in landscape, false)

Landscape iPhone 12 (844x390):
- matchMedia `(max-width: 600px)`: false → desktop fallback
- matchMedia `(max-height: 600px) and (orientation: portrait)`: false → desktop fallback

Desktop Chrome 1440x900:
- Both matchMedia queries: false → desktop layout
- MainMenu headerHeight=80px, flexWrap=nowrap, playWidth=200px — the desktop byte-identity baseline

## Commands Cheat Sheet

```bash
# Start the static server
cd kvisionApp-e2e && node static-server-8080.mjs &

# Refresh CSS in dist after every edit
cd kvisionApp && ./gradlew :kvisionApp:jsProcessResources -Pkvision.liveMode=true
cp build/processedResources/js/main/night-mode.css build/dist/js/productionExecutable/night-mode.css

# Run the comprehensive diagnostic (all 10 widgets)
cd kvisionApp-e2e && timeout 90 node probes/diagnose-all-mobile.mjs

# Run the mainmenu probe (8 assertions)
cd kvisionApp-e2e && timeout 60 node probes/mainmenu-mobile-portrait.mjs

# Capture screenshots for visual verification
cd kvisionApp-e2e && timeout 120 node probes/capture-mainmenu-mobile-portrait.mjs
# Output: /home/cage/Desktop/Workspaces/Autogenesis/screenshots/<date>-<slug>/

# Verify desktop byte-identity
cd kvisionApp-e2e && timeout 60 node probes/check-desktop-byte-identity.mjs
```

## References

- `references/loading-screen-mobile-support-plan.md` — the original LoadingScreen mobile plan (3 commits: CSS + matchMedia + probes), 629 lines, the precedent for the multi-task mobile plan shape.
- `references/mobile-ui-rendering-fix-plan.md` — the 11-task plan that fixed the 7 widgets with defects. Decision log: CSS overrides only (user-confirmed vs separate mobile widgets), 600px breakpoint unchanged, probe path at iPhone 12 + skipLogin.
- `references/defect-catalog-2026-07-11.md` — per-widget before/after measurements from the diagnostic JSON at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-11-mobile-baseline/diagnostic.json`.
- `references/build-pipeline-css-emission.md` — webpack output structure, why night-mode.css is a sidecar file, why `cp` is needed locally vs deploy, where the cp lives in amplify.yml.
- `references/multi-viewport-coverage.md` — canonical 5-viewport list, per-viewport assertions, what multi-viewport reveals that single-viewport hides, when to skip multi-viewport. Read before shipping ANY header-row or row-layout fix.
- `references/usage-modal-batch-2-batch-3.md` — UsageOverlay 6-issue batch-2 polish, ALL TIME bleed batch-3 follow-up (Range.getBoundingClientRect ground truth), CommanderSelectionDialog button sizing diagnosis. Includes the recipe for "diagnose X is overflowing" and "diagnose button X is smaller than button Y" — both founded on this session's measurement traces.
- `references/gameplay-ui-mobile-adaptation.md` — **GameplayUI shell** scope (separate round from mainmenu). Stitch project ID + 9 screen IDs, design system tokens, Game History left-dock rule, source-of-truth hierarchy when operator overrides a derived artifact, breakpoint specs (different from mainmenu), component spec table, source constraints from GameplayUI.kt, and commit log for the Autogenesis-Mobile branch's GameplayUI round (`4c4fe4531`, `c4aec1e78`).
- `references/simulation-settings-mobile-gap.md` — 2026-08-10 audit: the new Step 3 of CommanderSelectionDialog (`SimulationSettingsPage` + `SimulationMapPicker`, introduced by commit `c6c9f2ca2` "Core ui fixes and changes for simulation mode") ships with desktop-only CSS. The wizard host (`.commander-selection-window`) has mobile rules at `night-mode.css:4028-4135`, but the new selectors (`.simulation-settings-body`, `.commander-mini-card`, `.simulation-map-card`, `.simulation-map-card-active`) at `night-mode.css:5123-5218` are NOT covered. Active-card 50px gold glow + 60px cyan halo bleeds well past the 358px modal width on portrait. Includes the six-rule fix template and the merge-gate audit recipe. The companion pitfall in SKILL.md covers the general pattern ("every new wizard step must add its own `@media` block").

## Scripts

- `scripts/hermes-verify-mobile-ui.sh` — ad-hoc verification recipe (see Verification Recipe above).
- `scripts/hermes-verify-multi-viewport-template.mjs` — generic multi-viewport probe. Copy to `kvisionApp-e2e/probes/<feature>-multi-viewport.mjs`, customize `WIDGET_SELECTOR` + `LOADING_CTA_SELECTOR` + `TRACKED_SELECTORS`, run. Asserts no horizontal overflow + no clipping at all 5 canonical viewports.
- `scripts/hermes-verify-adhoc-positional.mjs` — per-commit ad-hoc verifier template for POSITIONAL fixes (left/right/width/alignment/pin-to-edge). Copy to `/tmp/hermes-verify-<feature>-YYYYMMDD.mjs`, customize TARGET_QUERY + PEER_QUERY + the assertions, run. Distinct from the suite probes — asserts ONLY the behavior delta between the prior commit and the new commit, giving the operator a focused before/after evidence trail. See the "Per-commit ad-hoc verifier" subsection above for the two real examples from 2026-07-12.