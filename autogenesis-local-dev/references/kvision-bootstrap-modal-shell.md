# KVision `Modal` shell collapse when Bootstrap CSS is not loaded

## Symptom

A `<div class="modal-header">Some Title</div>` text shows up at x≈1880
on a 1920px viewport, clipped by the right edge — only "Some Ti..." is
visible. The user perceives this as "the modal is trapped on the right
side of the screen" or "the dialog doesn't render correctly at all."

The full title is rendered, but it has overflowed the viewport to the
right and been clipped by `overflow: hidden` on a parent (or the viewport
itself).

## Which widgets trigger it

Any KVision class that extends `io.kvision.modal.Modal`:

```bash
grep -rn "Modal(" kvisionApp/src/jsMain/kotlin --include="*.kt"
```

In this codebase today (2026-06-24), only one: `SurrenderConfirmDialog`
in `kvisionApp/src/jsMain/kotlin/ui/gameplay/SurrenderConfirmDialog.kt`.
When that dialog opens (e.g. user clicks SURRENDER in the Settings modal),
its header "Surrender Match" gets clipped at x≈1880 on a 1920px viewport.

Future KVision Modal subclasses (any confirm dialog, info dialog,
wizard step dialog) will hit the same bug if Bootstrap CSS isn't loaded.

## Root cause

Same root cause as the broader Bootstrap-mismatch problem (see
`kvision-modal-layout.md` Pitfall 1: "Bootstrap CSS load breaks the
entire night-mode theme"), but a different symptom:

1. KVision's `Modal` class renders as a Bootstrap modal shell:
   ```html
   <div class="modal fade show" style="width: 420px; display: block;">
     <div class="modal-dialog modal-sm modal-dialog-centered">
       <div class="modal-content">
         <div class="modal-header">
           <h5 class="modal-title">Surrender Match</h5>
           <button class="btn-close"></button>
         </div>
         <div class="modal-body">…</div>
       </div>
     </div>
   </div>
   ```
2. Bootstrap CSS is intentionally NOT loaded (the `<link>` in
   `index.html` has a stale SRI hash; see Pitfall 1).
3. Without Bootstrap's `.modal { position: fixed; inset: 0; ... }`
   rules, the outer `<div class="modal">` collapses to `position: static`
   and lays out in document flow at wherever its KVision parent
   positioned it.
4. In this codebase, the parent is the `GameplayUI` which puts everything
   left-aligned; the modal's natural document-flow position ends up at
   the right edge of the GameplayUI's content area, which happens to be
   at x≈1880 on a 1920px viewport. The text gets clipped.

So the modal isn't "trapped on the right side" — it's been knocked out
of its centered fixed-positioned layout by missing CSS and is now just a
normal-flow block, which happens to render near the right edge.

## Preferred fix — refactor to `SimplePanel(className = "login-widget-window")`

**Use this approach when the dialog doesn't need Bootstrap's modal
features** (backdrop click-to-close, ESC key handler, X close button).
For a YES/NO confirm, info popup, or wizard step dialog, none of those
features justify the trouble of KVision `Modal` in this codebase.

**Pattern:** convert the KVision `Modal` subclass to a
`SimplePanel(className = "login-widget-window")` mirroring the proven
in-app recipe used by `SettingsWidget` and `DelegateWidget`. The
resulting dialog:

- Joins the existing `login-widget-window` glassmorphic chrome family
  that 9+ other popup widgets already use successfully
  (`PlayerResourcesWidget`, `WorldStatsWidget`, `GameHistoryWindow`,
  `TurnResolutionWidget`, etc.)
- Renders correctly without ANY `.modal { ... }` CSS — pure CSS,
  no Bootstrap modal JS lifecycle, no `Modal.show()` reparenting to
  a modal root
- Lets the dialog live as a normal child of its parent (e.g. a child
  of `SettingsWidget`), so its zIndex, position, and clip behavior
  are predictable and match the surrounding modals
- Avoids the entire `Modal.width` → `.modal-content` width mismatch
  that the CSS-shell fix can't fully solve (see "Known caveat" below)

**Refactor template — `SurrenderConfirmDialog` (concrete example):**

```kotlin
// Before — KVision Modal subclass (the broken pattern in this codebase)
class SurrenderConfirmDialog(
    private val onConfirm: () -> Unit
) : Modal(
    caption = "Surrender Match",
    closeButton = true,
    size = ModalSize.SMALL,
    animation = true,
    centered = true,
    scrollable = false,
    escape = true,
    className = "surrender-confirm-dialog"
) { ... }

// After — SimplePanel mirroring DelegateWidget/SettingsWidget
class SurrenderConfirmDialog(
    private val onConfirm: () -> Unit
) : SimplePanel(className = "login-widget-window")
{
    init {
        // Chrome — copy verbatim from DelegateWidget.kt:62-87
        width = CssSize(600, UNIT.px)            // outer fixed width
        height = CssSize(100, UNIT.perc)
        position = Position.FIXED
        top = 120.px
        bottom = 220.px
        setStyle("left", "calc(50% - 300px)")
        setStyle("max-width", "calc(100vw - 40px)")
        setStyle("max-height", "calc(100vh - 340px)")
        zIndex = 201                              // one above SettingsWidget (200)
        padding = 30.px
        setStyle("box-sizing", "border-box")
        overflow = Overflow.HIDDEN
        display = Display.NONE                     // hidden by default
        flexDirection = FlexDirection.COLUMN
        alignItems = AlignItems.CENTER
        justifyContent = JustifyContent.FLEXSTART
        setStyle("animation", "dialogFadeIn 0.3s ease-out")

        // Inner content vPanel — THIS is where the 420px "narrow confirm
        // dialog" width goes. The outer SimplePanel is 600px to match
        // the family; the inner vPanel is the visible dialog body.
        vPanel(spacing = 16, alignItems = AlignItems.CENTER) {
            width = CssSize(420, UNIT.px)          // ← was Modal.width = 420.px
            // ... existing content (p, hPanel of NO/YES buttons) ...
        }
    }

    fun show() { display = Display.FLEX; visible = true }
    fun hide() { display = Display.NONE; visible = false }
}
```

**Tradeoffs vs the CSS-shell fix:**

| Aspect | CSS-shell fix | SimplePanel refactor |
|---|---|---|
| Files touched | night-mode.css (~110 lines) | SurrenderConfirmDialog.kt (~30 lines) |
| Bootstrap modal JS dependency | Yes (show/hide lifecycle) | None |
| Per-instance width honored | No (~868px vs declared 420px) | Yes (inner vPanel is exactly 420px) |
| Matches the rest of the codebase | No (only KVision Modal subclass in app) | Yes (9+ widgets use this pattern) |
| Backdrop click-to-close | Yes (Bootstrap) | No — wire manually if needed |
| ESC key handler | Yes (`escape = true`) | No — wire `Window.addEventListener` if needed |
| X close button | Yes (`closeButton = true`) | No — add a button to the header if needed |

**Decision rule:**

- New dialog that needs Bootstrap features (backdrop, ESC, X) → CSS-shell fix
- New dialog that doesn't → SimplePanel refactor
- Refactoring an existing broken `Modal` subclass → SimplePanel refactor (always)

## Fallback fix — CSS shell (applied 2026-06-24, keep if you can't refactor)

If for some reason the dialog must remain a KVision `Modal` subclass
(e.g. it genuinely needs Bootstrap's backdrop click-to-close for a
wizard flow), the workaround is a `.modal { ... }` block in
`night-mode.css`. Documented here for reference; the SimplePanel
refactor above is the preferred approach.

Add a generic `.modal:not(.billing-modal-window-host) { ... }` block in
`night-mode.css` that reproduces the bits of Bootstrap's `.modal` rules
the bare KVision Modal needs to render correctly. The block is ~110
lines and lives around line 2585 of `night-mode.css` (right after the
existing `.modal.billing-modal-window-host { ... }` block).

What it covers:

- `.modal` outer shell: `position: fixed; top/left/right/bottom: 0;
  min-width: 100vw; min-height: 100vh; display: flex;
  align-items: center; justify-content: center; padding: 1rem;
  overflow-y: auto; background-color: rgba(2, 4, 12, 0.78); z-index: 1010`
- `.modal-dialog`: `display: block; position: relative; max-width:
  calc(100vw - 2rem); flex: 0 0 auto; pointer-events: auto; margin: 0`
- `.modal-content`: glassmorphic background gradient, dark blue border,
  14px radius, flex column, `max-height: calc(100vh - 2rem);
  overflow: hidden; max-width: calc(100vw - 2rem)`
- `.modal-header`: dark backdrop, bottom border, padding 16 24, flex row
  with space-between (so the title sits on the left and the close button
  on the right)
- `.modal-body`: padding 20 24, `flex: 1 1 auto; overflow-y: auto`
- `.modal-footer`: top border, padding 12 24, flex row flex-end, gap 8

The selector uses `:not(.billing-modal-window-host)` so the existing
`BillingOverlayWindow` (which has its own dedicated `.modal.billing-modal-window-host { ... }` block in `night-mode.css` and explicitly sets `z-index: 10000`) isn't touched.

The big comment block above the rule group in `night-mode.css` explains
the why in detail — search for `Generic KVision Modal chrome` to find it.

## Known caveat — dialog width is wider than design intent

After the fix, `SurrenderConfirmDialog` renders centered and visible, but
the inner `.modal-content` is ~868px wide on a 1280px viewport instead of
the 420px the KVision code declares.

**Why:** KVision's `Modal.width` getter is inherited from
`StyledComponent.width` which calls `setStyleProperty("width", value)` on
the outer `<div class="modal">` element — NOT on `.modal-content`. The
`SurrenderConfirmDialog.kt:53` declares `width = 420.px`, which ends up
as the inline style `width: 420px; display: block;` on the modal shell.
The `min-width: 100vw !important` in the generic rule forces the shell to
≥ viewport width so flex centering has room to work, but the inner
`.modal-content` then sizes to its natural content width (the `<p>` text
wraps based on container width — the content's natural width when given
the full viewport to lay out is ~868px).

**Fix:** move the `width = 420.px` from the outer `Modal` to the inner
content via `getContent().setStyle("width", "420px")` (or apply it to
`getDialog()` in KVision Bootstrap). CSS-only clamping (e.g.
`width: min(420px, 100vw - 2rem)` on `.modal-content`) hardcodes the
per-instance width into the CSS, which defeats KVision's per-instance
override pattern — don't do that. If the inner-content width really
matters for UX, do it in Kotlin.

## Verification

After applying the CSS fix and restarting `:kvisionApp:jsBrowserDevelopmentRun`:

```bash
# Boot all three servers
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./debugger/scripts/start_servers.sh

# In the browser, navigate to a game, open Settings, click SURRENDER
# SurrenderConfirmDialog should be centered, with title "Surrender Match"
# fully visible and NO/YES buttons inside the dialog.
```

Quick data-only verification (paste into browser console while the
SurrenderConfirmDialog is open):

```javascript
var dialog = Array.from(document.querySelectorAll('.modal'))
  .find(m => m.className.includes('surrender-confirm-dialog'));
var inner = dialog.querySelector('.modal-dialog');
var title = dialog.querySelector('.modal-title');
var dr = dialog.getBoundingClientRect();
var ir = inner.getBoundingClientRect();
var tr = title.getBoundingClientRect();
console.log({
  modal: { w: dr.width, x: dr.x },
  dialog: { w: ir.width, x: ir.x, centerX: ir.x + ir.width / 2 },
  title: { x: tr.x, y: tr.y, text: title.textContent },
  viewport: window.innerWidth
});
```

Expected after fix (1280×633 viewport):
- `modal.w` = 1280 (full viewport, the shell)
- `dialog.w` ≈ 868 (content-shrunk, not the 420 design width — see caveat)
- `dialog.centerX` ≈ 640 (centered, not clamped to viewport)
- `title.x` > 200 and `title.x + title.w` < viewport (title is inside the
  dialog, not clipped)

If `dialog.centerX` is not ≈ viewport/2 or the title is clipped at the
viewport edge, the CSS rule didn't take effect — webpack-dev-server has
cached the old CSS (see `kvision-modal-layout.md` Pitfall 5 for the cache
flush dance: copy source files to `processedResources/js/main/` and
restart the kvision dev server).