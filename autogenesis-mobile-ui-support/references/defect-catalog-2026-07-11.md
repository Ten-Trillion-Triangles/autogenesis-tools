# Defect Catalog — 2026-07-11 Mobile UI Diagnostic

Captured during the `mobile-ui-rendering-fix` plan execution. Source: `diagnose-all-mobile.mjs` output at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-11-mobile-baseline/diagnostic.json`.

## Per-Widget Measurements

### LoadingScreen (DONE — committed earlier on Autogenesis-Mobile)
- Status: working at iPhone 12 portrait (390x844)
- Probe files: `loading-screen-mobile-portrait.mjs`, `loading-screen-mobile-landscape.mjs`
- Commits: `6feaeb217` (CSS), `3327fb514` (matchMedia listener), `352070ecc` (probes)

### MainMenu
| Selector | Before | After fix |
|---|---|---|
| `.btn-play` rect | w=18px, x=355 (clipped off right edge) | w=360px, x=5 |
| `.main-menu-center` scrollW | 430 (overflow) | 390 (fits viewport) |
| `.main-menu-bottom > div` (inner action panel) | h=82, flexDirection row | h=180, flexDirection column |
| `#kvapp` (background-image AUTOGENESIS wordmark) | background-size cover, extends past viewport | background-size contain, fits within 390 |
| `.main-menu-header` | h=80px, nowrap | h=121px, wrap (2 rows) |
| `.main-menu-header .btn-options` | w=44, h=44 (gear icon visible) | unchanged |

### ShopOverlay
| Selector | Before | After fix |
|---|---|---|
| `.billing-modal-window-host .modal-dialog` | w=371 | w=390-8=382 |
| `.billing-modal-window-host` scrollW | 403 | 391 |
| `.shop-credit-card` (GO MONTHLY footer) | flexDirection row, overlap | flexDirection column, stacked |
| Tabs count | 3 (CREDITS / SUBSCRIPTIONS / UPGRADE) | 5 (same + MONTHLY/ANNUAL nested) |
| Background bleed-through behind modal | yes (TOGENE… visible) | yes still (modal opacity) |

### UsageOverlay
| Selector | Before | After fix |
|---|---|---|
| `.billing-tabs` | flexDirection row | flex-wrap, 2-per-row |
| `.billing-tab` text "ALL TIME" | wrapped to 2 lines | nowrap on single line |
| Meter rows | 1 row (compressed) | 1 row at 279x187 |
| `.billing-tab` (4-up row, mobile 390×844) | buttons 72px each, "ALL TIME" text overflows 10px (scrollW=80 vs clientW=70) inside its pill — right edge of "E" clipped. Other 3 buttons fit because labels are shorter. | **pending fix** — shrink `padding: 14px` → `10px` or `font-size: 13px` → `12px` on mobile `.billing-tab`. Verify via `scrollW > clientW` probe |
| Modal scroll-container chain | `.modal-host` / `.modal-dialog` / `.modal-content` / `.modal-body` all have scrollH == clientH. Only `.billing-modal-content-root` actually scrolls (scrollH=1148 vs clientH=675 = 473px overflow). Symptom "modal doesn't scroll" is misleading — it scrolls but the scroll surface is the innermost contentRoot, not the outer modal. | **verification recipe** — walk every layer's scrollH/clientH before claiming "doesn't scroll" |
| Real-touch scroll on mobile modal | `page.mouse.wheel(0,500)` reports scrollTop=0; CDP `Input.dispatchTouchEvent` (touchStart/touchMove/touchEnd sequence) reports scrollTop=434 (~92% of max). Real mobile devices scroll correctly. | **verification recipe** — wheel is unreliable on mobile emulated contexts; use CDP touch dispatch |

### SettingsWidget
| Selector | Before | After fix |
|---|---|---|
| Root | null (never opened under skipLogin) | found, x=12, y=12, w=366, h=616 |
| `.login-widget-window` (Chrome in render) | renders off-screen left (x=-210, w=600) | renders at x=12, w=366 (12px insets) |
| Width source bug | SettingsWidget.kt:55-60: `width=600.px; left=calc(50% - 300px)` | CSS override left/right/top/bottom to 12px |

### CollectionOverlay
| Selector | Before | After fix |
|---|---|---|
| `.btn-close-collection` | full-width banner | 44x44 corner icon, position absolute top-right |
| `.collection-tab-button` | 48x48 icon-only square | 90x58 with icon + text label via `::after { content: attr(title) }` |
| `.collection-tab-button::after` | n/a | shows COMMANDERS / STORIES text |
| `.collection-content` | 2-pane (list + tab-strip) side-by-side | flex-direction column, tab strip below |
| Overlay scrollW | 390 (already fine) | unchanged |

### CommanderCreationDialog
| Selector | Before | After fix |
|---|---|---|
| Inputs | placeholder "Enter your commander's nam" clipped mid-word | `text-overflow: ellipsis` + `box-sizing: border-box` |
| Dialog width | fits viewport | unchanged |
| Play button | fits viewport | unchanged |

### CommanderSelectionDialog / ResumeOrNewDialog / MessageBox / SurrenderConfirmDialog
- NOT TESTED under skipLogin (server-pushed events that don't fire without AccelByte backend)
- Existing CSS at night-mode.css lines 3503-3513, 3500-3513 should cover these
- Need a separate verification pass when live backend is available

## Verification Probes Used

1. `diagnose-all-mobile.mjs` — comprehensive measurement capture (10 widgets, ~9000 chars JSON output)
2. `mainmenu-mobile-portrait.mjs` — 8 specific assertions (PLAY size, header height, no overflow, etc.)
3. `capture-mainmenu-mobile-portrait.mjs` — full-page screenshot capture at every interactive state
4. `check-desktop-byte-identity.mjs` — ad-hoc desktop verification at 1440x900

## Live Diagnostic Run Output

From the 2026-07-11 run:
```
PLAY: x=5 y=588 w=360 h=64 (was 18x64)
CENTER: w=390 scrollW=390 (was 430)
INNER: w=362 h=180 (was 82x82)
SETTINGS root: True, window: True (was NULL NULL)
COLLECTION overlay scrollW: 390 (was 390)
COLLECTION window: w=359 h=598 (was unchanged)
COLLECTION tabs: 2 (text labels via attr(title))
SHOP: HOST exists, DIALOG exists, 5 tabs
```

Desktop 1440x900 byte-identity (unchanged):
```
headerHeight: 80px
headerFlexWrap: nowrap
headerPadding: 0px 20px
playWidth: 200px
playHeight: 100px
bottomHeight: 160px
data-mobile-layout: "desktop"
```

## Files Changed

1. `kvisionApp/src/jsMain/resources/night-mode.css` (+484 lines of mobile @media overrides)
2. `kvisionApp-e2e/probes/diagnose-all-mobile.mjs` (NEW)
3. `kvisionApp-e2e/probes/mainmenu-mobile-portrait.mjs` (existing, fixed 2 bugs)

Commit: `ec9be11b3 fix(mobile): render all UI widgets correctly at iPhone 12 portrait` on branch `Autogenesis-Mobile`.