# GameplayUI HUD/CSS Mobile Adaptation

## Scope difference from the mainmenu-round skill

The mainmenu-round skill covers MainMenu + 7 modal-class overlays (CollectionOverlay, ShopOverlay, UsageOverlay, SettingsWidget, CommanderCreation, CommanderSelection, MessageBox, ResumeOrNew, SurrenderConfirmDialog). This reference covers the **separate GameplayUI shell** — the in-game HUD, map, score bar, turn progression, command box, Game History panel, and the 12 modal-class widgets that share `.login-widget-window` (WorldStats, PlayerResources, etc.). All CSS overrides land in the same `night-mode.css` file but live in a different region of the design system and use different breakpoint values.

## Stitch project (the design source of truth)

| Field | Value |
|---|---|
| Project title | Autogenesis Mobile Adaptation — Concept Sketches |
| Project ID | `projects/10219611715979180962` |
| Device type | MOBILE (portrait primary) |
| Created | 2026-07-17 |
| Last updated | 2026-07-19 21:16 UTC |
| Design system | `Autogenesis Tactical Interface` (asset `623147e28a1f49b4b1671f0724b1f64d`) |

### Design system tokens

- **Colors**: cyan `#00f2ff` (friendly/active/score), violet `#bc13fe` (hostile/NPC), gold (CAPITAL markers), dark bg `#051424`
- **Fonts**: Space Grotesk headlines, Inter body, JetBrains Mono labels (0.1em tracking, uppercase)
- **Shape**: 0.25rem default radius, angular leaning, 45° corner clips optional on large panels
- **NO emoji** — crown glyph for capitals, `?` for NPCs, sword/handshake/flask/mountain for stat icons

### 9 screens in the project (use these IDs as Stitch regen targets)

| Title | Screen ID | Viewport | Status |
|---|---|---|---|
| Idle Map View (portrait) | `e39be246499540bb836ce4aa25b34b21` | 780×1768 | current |
| Territory Selected (portrait) | `49a5c3b0e4a3464b91fea22230b579d3` | 780×1768 | current |
| Command Sheet Expanded (portrait) | `0d154c827abc4673be789e5b57655a1d` | 780×1768 | current |
| Agent Work Stream (portrait) | `e1a449889b454eb982550e3afd986611` | 780×1768 | current |
| Tactical Command (portrait) | `fff6140d46424d39b366acc6743956ed` | 780×2318 | thumbnail reference |
| Landscape Idle Map View | `9fe2b886526d40e393b9d7c3e5f90c83` | 1840×1768 | **regenerated 2026-07-19** (replaces broken `26f51b918ca5470388657694d9c37122`) |
| Landscape Command | `8a0d12157f7a428fbb81a24510afd6a7` | 1840×1768 | current |
| Landscape Command Expanded | `da45e7919e664a999d67c4270569d579` | 780×1768 | current |

## The Game History docking rule (operator-confirmed, highest-priority)

**Game History panel ALWAYS docks on the LEFT across ALL viewports** (portrait AND landscape). This rule was operator-confirmed 2026-07-19 after Stitch generated a landscape variant that put Game History on the top as a horizontal drawer — wrong. The regenerated landscape screen (`9fe2b886…`) corrects it: 240px left rail with map + control surface splitting the right.

The opposite assumption — "in landscape, flip Game History to the right to give map space" — is wrong. Do not regenerate Stitch designs against that assumption; the operator has overridden it.

### Source-of-truth hierarchy when the operator overrides a derived artifact

1. **Operator confirmation** — highest priority, overrides everything below
2. **Plan file** (`~/.hermes/plans/mobile-adaptation/plan.md`) — must be updated to reflect the new rule
3. **CSS** (`kvisionApp/src/jsMain/resources/night-mode.css`) — patched next, including any prior wrong-direction rules
4. **Stitch project screenshots** — regenerated LAST so the visual artifact matches the canonical source

When the rule is patched: also check any landscape CSS that was set to `right: 0` from the previous assumption. The 2026-07-19 patch changed landscape Game History from `right: 0` to `left: 0, right: auto` after the operator ruling.

## Breakpoint specs (different from the mainmenu-round 600px)

| Layout | Media query |
|---|---|
| Portrait | `@media (max-width: 767px)` |
| Landscape | `@media (max-width: 920px) and (max-height: 500px)` |
| Modal-class (the 12 widgets sharing `.login-widget-window`) | `@media (max-width: 1024px)` |

The mainmenu-round uses a single `(max-width: 600px), (max-height: 600px) and (orientation: portrait)` block. The GameplayUI round uses three separate blocks keyed to viewport aspect, not just width.

## Component spec table (what CSS has to produce)

| Component | Desktop | Portrait | Landscape |
|---|---|---|---|
| Score bar height | 100px | 64px | 40px |
| Map width | inherits from centerStackPanel | 100% width with HUD overlay | 50% width, control surface splits right |
| Game History panel width | 400px (left rail) | 240px left-edge drawer handle | 240px left rail |
| HUD quicks grid (RESOURCES/STATS/WORLD/SETTINGS) | single row | 2×2 grid | 2×2 grid |
| Turn progression 8 chips | single row | single row | 2×4 grid |
| Active phase glow | n/a | cyan 10px outer shadow | cyan 10px outer shadow |
| HUD bar background | solid surface-container-high | glass surface-container-high + 12px backdrop blur + 1px cyan border at 20% opacity | same as portrait |
| Command box | full-width row with SEND | full-width row, compressed SEND button | horizontal command box, compressed SEND button |

## Source constraints from the Kotlin code (do not refactor, only adapt CSS)

- `GameplayUI.kt:202-205` — left dockPanel `width=400px, minWidth=400px`. Forces centerStackPanel to negative/zero width on viewports < 400px. CSS alone cannot override this — a data-testid hook (`score-bar`, `main-score-label`, `command-box`) is the only reliable selector target.
- `GameplayUI.kt:214` — score bar `paddingLeft=400.px` pushes score widgets off-screen. Same constraint.
- `centerStackPanel.activeIndex` is server-driven via `ui.forceShowTurnResolution`. No user toggle. Mobile portrait always displays whichever modal is currently active (default boot: TurnResolutionWidget at index 1).
- Map ↔ TurnResolutionWidget flip is server-driven; default Map active after TurnResolutionWidget step 7. UpdateWorldPage forces switch via `syncMapForWorldUpdate`.

## Commits that landed the mobile-branch work (in chronological order)

Repo: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis`. Branch: `Autogenesis-Mobile` (ahead of `main`).

- `8febe1c59` — header-stretch + wordmark-pan fix (mainmenu)
- `0924cc9cc` — header shrink to fit 320px + wordmark pan to 55% (mainmenu)
- `6a919f1c7` — hide credits-pill on mobile portrait (mainmenu)
- `154920b99` — widen gear to 44px + pin action buttons to right edge (mainmenu)
- `d54f8d898` — align PLAY button right edge with COLLECTION/NEW COMMANDER (mainmenu)
- `4d7344bc4` — fix(mobile-portrait) stack Shop BUY CREDITS cards into a column (mainmenu)
- `4c4fe4531` — feat(mobile) pan/zoom + centerOnTerritory for MapViewer; portrait+landscape CSS (**GameplayUI round**)
- `c4aec1e78` — fix(e2e) expose `firstTerritoryName` as a live getter in Main.kt + GameplayUI.kt test-mode branches (GameplayUI test hook)
- `d627f253d` — "Unlock and pray" (WIP sitting on top, uncommitted)

## Open blockers (2026-07-19 status)

1. **12 modal-class widgets** (WorldStats, PlayerResources, etc., all sharing `.login-widget-window`) remain broken at 390px viewport width after the 2026-07-18 capture session verification. The 2026-07-19 CSS patch only fixed Game History positioning; the modal widgets still need a CSS pass against the new Stitch landscape composition.
2. **Plan file** `~/.hermes/plans/mobile-adaptation/plan.md` needs to reflect the corrected Game History docking rule before the CSS work references it.
3. **Production bundle minifies widget field names** — `window.gameplayUI.worldStatsWidget` is undefined, so modal widgets can't be probed at runtime. Either expose test-mode handles or capture via Stitch-only workflow.
4. **TurnResolutionWidget state-flow captures** — the 12-state machine (per `GAMEPLAYUI_WIDGET_INVENTORY.md` lines 100-113) has zero visual documentation. The capture-script pattern in `references/capture-and-boot-2026-07-14.md` is the recipe; needs to be applied across the 12 states.

## Verification probe (GameplayUI-specific)

The HTML-injection harness at `/tmp/hermes-harness-gameplay-mobile-20260716.mjs` (from plan `~/.hermes/plans/2026-07-16-gameplay-mobile-harness.md`) is the canonical GameplayUI shell composite probe. It boots MapViewer via `?testMode=true`, loads `kvisionApp-e2e/tests/fixtures/tiny-map.map` (2566 bytes), then HTML-injects the rest of the gameplay widgets using their real class names so existing CSS rules fire unchanged. Output goes to `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-16-gameplay-mobile/`.

For the 12 modal-class widgets that minify to undefined handles, the Stitch-only workflow is the only verification path until test-mode handles are exposed.
