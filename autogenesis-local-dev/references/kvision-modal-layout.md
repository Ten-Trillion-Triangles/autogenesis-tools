# KVision Modal Layout Pitfalls — Autogenesis

The settings modal (Game Settings) and delegate modal (Delegate Instructions)
are both `position: fixed` panels with `display: flex; flex-direction: column`,
600px wide by default, centered via `left: calc(50% - 300px)` and `top: 120px`.

These are the layout pitfalls future debugging sessions will hit again.

---

## Pitfall 1 — Bootstrap CSS load breaks the entire night-mode theme

**Symptom:** Login page form inputs render with wrong typography/padding,
modal stretches vertically, button rows misalign. Everything looks "all
fucked up".

**Root cause:** `index.html` ships a `<link>` to Bootstrap 5.3.2 from
jsdelivr. The integrity hash in the HTML is STALE — the file jsdelivr
actually serves has a different SHA-384. If the hash is ever updated to
the real value (so Bootstrap actually loads), Bootstrap's defaults
overwrite night-mode.css:

- `.form-control { font-size: 1rem; line-height: 1.5; padding: .375rem .75rem; min-height: calc(1.5em + .75rem + 2px); }`
- `.modal-header`, `.modal-body`, `.modal-footer` add their own padding/margins
- `.btn` resets the button styling

The login page was designed against night-mode.css WITHOUT Bootstrap. The
theme rebuilds Bootstrap's defaults from scratch via `.login-widget-input`,
`.login-widget-button`, `.login-widget-window`, etc. Bootstrap loading on
top of that is double-styling.

**Decision rule:** the broken SRI hash is INTENTIONAL. Don't "fix" it to
the real Bootstrap SHA-384 unless you also audit every `.form-control`,
`.form-group`, `.btn`, `.modal-header`, `.modal-body` rule in
night-mode.css and add `!important` where needed.

If you DO want real Bootstrap utilities, replace the hash with the real
one AND switch the night-mode.css rules for affected selectors to use
`!important` or higher-specificity selectors.

---

## Pitfall 2 — KVision TextArea width does not propagate to inner <textarea>

**Symptom:** Textarea inside DelegateWidget renders at its `cols` attribute
default width (~60 chars ≈ 561px) and overflows the form-group wrapper,
making the modal's content area wider than the modal itself and breaking
the centered layout.

**Root cause:** KVision's `width = 100.perc` on a `textArea { ... }` block
is applied to the FORM-GROUP wrapper (the outer div with class
`form-group kv-mb-3`), not the inner `<textarea>` element. The inner
textarea has no inline width and only the HTML `cols="60"` attribute, so
the browser gives it its default char-width.

Bootstrap's `.form-control { width: 100% }` was the only thing cascading
that 100% width down to the inner textarea. With Bootstrap not loaded (see
Pitfall 1), the textarea was always wrong, but only noticeable in tight
modal containers.

**Fix (the right way):** Apply styles directly to the `input` property of
the `TextArea` widget. KVision exposes the inner `TextAreaInput` as a
public `val input: TextAreaInput` (NOT `getInput()` — that name does not
exist as a Kotlin method, only as the mangled JS getter).

```kotlin
textArea {
    width = 100.perc          // wrapper
    height = 180.px           // wrapper
    setStyle("padding", "12px")
    // ...
    // B1e fix: also propagate to the inner <textarea>
    input.setStyle("width", "100%")
    input.setStyle("height", "100%")
    input.setStyle("box-sizing", "border-box")
}
```

This was previously the workaround documented in
`DelegateWidget.kt` for `padding` (see the comment block above the
`textArea` block in that file: "KVision's `padding` property does not
propagate to <textarea> elements"). The same pattern applies to width
and height.

**Convention for sizing textareas in this codebase:**
`CommandBox.kt` and `CommanderCreationDialog.kt` both use the `cols` /
`rows` attributes as the primary size control, NOT `width = 100.perc`,
because they accept that KVision can't reliably resize textareas via
`width`. See `CommandBox.kt:160` for the per-browser `cols = when(getBrowserEnvironment())`
hack and its "Stupid hack needed because KVision does not allow size
control except through rows and cols" comment.

---

## Pitfall 3 — Modal vPanel overflow when `flexGrow` and `max-height` are missing

**Symptom:** A button (e.g. SURRENDER in SettingsWidget) renders OUTSIDE
the modal frame, visible 60+px below the modal's `overflow: hidden`
boundary on a 1080p viewport.

**Root cause:** The modal is `display: flex; flex-direction: column`,
fixed height (capped by `max-height: calc(100vh - 340px)` = 740px on
1080p). Its inner content vPanel needs to:

- `flex-grow: 1` (so it absorbs the free vertical space inside the
  modal)
- `min-height: 0` (so the flex item is allowed to shrink below its
  natural content size — without this, flex items default to
  `min-height: auto` which is the content height, defeating the cap)
- `overflow: auto` (so anything overflowing the resolved height scrolls
  instead of spilling out of the modal)
- `max-height: 100%` (caps the vPanel at the modal's content area — pairs
  with `max-height` on the modal so the scrollbar engages on short
  viewports)

Removing any of these causes the modal's overflow:hidden boundary to
NOT clip the content — the inner buttons render at their natural y
position regardless of the modal's max-height. This is what the
"void-free" refactor of SettingsWidget accidentally did.

**Fix template (SettingsWidget vPanel):**

```kotlin
vPanel(spacing = 16, alignItems = AlignItems.STRETCH) {
    width = 90.perc
    flexGrow = 1
    overflow = Overflow.AUTO
    setStyle("min-height", "0")
    setStyle("max-height", "100%")
    // ...
}
```

---

## Pitfall 4 — Modal zIndex vs Game History sidebar stacking

**Symptom:** Modal's left edge appears to be painted over by the Game
History sidebar (the 400px-wide panel with Story/Details/Geopolitics
tabs on the left of the GameplayUI). SURRENDER button looks "cut off" on
its left side in the modal.

**Root cause:** `historyWindow` in GameplayUI has `zIndex = 1000`. The
modal widgets (SettingsWidget, DelegateWidget) were originally at
`zIndex = 200`. The sidebar paints on top of the modal's left edge.

**Fix:** bump modal `zIndex = 1010`. Sits above historyWindow (1000) but
BELOW KVision Modal defaults (~1055 from Bootstrap) so the
SurrenderConfirmDialog can still stack on top when the user clicks
SURRENDER.

If you also use KVision Modal (not just the login-widget-window pattern),
verify it lands above 1010. If not, raise the modal zIndex higher (but
watch out for the SurrenderConfirmDialog stacking).

---

## Pitfall 5 — KVision `Modal` (Bootstrap modal subclass) renders with `.modal-header` clipped at the right viewport edge when Bootstrap CSS is not loaded

**Symptom:** A `<div class="modal-header">Some Title</div>` text shows up at x≈1880 on a 1920px viewport, clipped by the right edge — only "Some Ti..." is visible. The user thinks the modal is "trapped on the right side of the screen" or "doesn't render correctly at all."

**Root cause:** Any KVision class that extends `io.kvision.modal.Modal` (e.g. `SurrenderConfirmDialog` in `kvisionApp/src/jsMain/kotlin/ui/gameplay/SurrenderConfirmDialog.kt`) renders as a Bootstrap modal shell: `<div class="modal fade show">` → `<div class="modal-dialog">` → `<div class="modal-content">` → `<div class="modal-header"><h5 class="modal-title">Surrender Match</h5></div>`. **Bootstrap CSS is intentionally NOT loaded** (see Pitfall 1). Without Bootstrap's `.modal { position: fixed; inset: 0; ... }` rules, the `<div class="modal">` shell collapses to `position: static` and lays out in document flow. The inner header is no longer inside a fixed full-viewport backdrop, so it floats to wherever the dialog's parent happens to be — in this codebase, the right edge of the GameplayUI, clipped by the viewport.

This is the **same root cause as Pitfall 1**, but a different symptom: Pitfall 1 is the login page losing its theme; this is any KVision Modal subclass (SurrenderConfirmDialog is the only one in the app today, but future confirm dialogs would hit the same issue) losing its positioning entirely.

**Fix (preferred):** refactor the KVision `Modal` subclass to a
`SimplePanel(className = "login-widget-window")` mirroring
`SettingsWidget` / `DelegateWidget`. This is the architectural fix —
it eliminates the entire Bootstrap dependency for that dialog, makes it
match the 9+ other popup widgets in this codebase that already use the
pattern, and avoids the `Modal.width` → `.modal-content` width
mismatch that no CSS-only fix can solve cleanly. Full template and
tradeoffs: see `references/kvision-bootstrap-modal-shell.md` "Preferred
fix" section.

**Fix (fallback, applied 2026-06-24):** if the dialog MUST remain a
KVision `Modal` (e.g. needs Bootstrap's backdrop click-to-close for a
wizard flow), add a generic `.modal:not(.billing-modal-window-host) { ... }` block in `night-mode.css` that reproduces the bits of Bootstrap's `.modal` rules the bare KVision Modal needs to render correctly. The block is already present in `night-mode.css` (added 2026-06-24, see the big comment block above the rule group) — it's ~110 lines covering:

- `position: fixed; top/left/right/bottom: 0; min-width: 100vw; min-height: 100vh` — full-viewport shell
- `display: flex; align-items: center; justify-content: center` — centers the inner dialog
- `padding: 1rem; overflow-y: auto` — handles viewports shorter than the dialog
- `background-color: rgba(2, 4, 12, 0.78)` — backdrop tint
- Matching `.modal-dialog { display: block; position: relative; max-width: calc(100vw - 2rem); flex: 0 0 auto; pointer-events: auto }`, `.modal-content { background: glassmorphic gradient; border; box-shadow; flex column; max-height: calc(100vh - 2rem); overflow: hidden }`, `.modal-header { backdrop dark background; bottom border; padding 16 24; flex row; space-between }`, `.modal-body { padding 20 24; flex 1 1 auto; overflow-y: auto }`, `.modal-footer { top border; padding 12 24; flex row; flex-end; gap 8 }`

The selector uses `:not(.billing-modal-window-host)` because the existing `BillingOverlayWindow` already has its own dedicated `.modal.billing-modal-window-host { ... }` block in `night-mode.css` (around line 2526) and shouldn't be touched.

**Known caveat — dialog width is wider than design intent:** KVision's `Modal.width` getter (inherited from `StyledComponent` via `setStyleProperty`) puts a per-instance width on the OUTER `<div class="modal">` as an inline style — NOT on `.modal-content`. `SurrenderConfirmDialog.kt:53` declares `width = 420.px`, so the inline style is `width: 420px; display: block;` on the shell. The `min-width: 100vw !important` in the generic rule forces the shell to ≥ viewport width so flex centering has room to work, but the inner `.modal-content` then sizes to its natural content width (the `<p>` text wraps based on container width), which comes out around 868px on a 1280px viewport. The dialog is centered and visible, but wider than the 420px the KVision code declares.

The clean fix is a Kotlin-side one-liner: move the `width = 420.px` from the outer `Modal` to the inner content via `getContent().setStyle("width", "420px")` (or apply it to `getDialog()` in KVision Bootstrap). The CSS-only fix that exactly honors the KVision width is awkward — you'd need to use `width: min(420px, 100vw - 2rem)` on `.modal-content` to clamp it, but that hardcodes the per-instance width into the CSS, defeating KVision's per-instance override pattern. Don't bother trying to fix it from CSS alone; if the inner-content width really matters, do it in Kotlin.

Full reference doc with the live verification snippet: `references/kvision-bootstrap-modal-shell.md`.

---

## Pitfall 7 — KVision `Window` (NOT Modal) renders title as `<h5 class="modal-title">`, not `.kv-window-caption`; the Kotlin 64px fontSize on the Window inflates the header to 250px

**Symptom:** A KVision `Window` subclass (e.g. `LoginPage` at `kvisionApp/src/jsMain/kotlin/ui/LoginWidgets.kt:100`) renders with the title FLUSH-LEFT (not centered in the header bar), and the header itself is ~250px tall instead of ~56px. Modal extends past the viewport on screens shorter than ~1100px — the centered `transform: translate(-50%, -50%)` positioning pushes the top half above `y=0`, hiding the title entirely. Inner inputs (Email, Password) render at the designed 72px height with no obvious defect, but checkboxes inside `.form-check` containers are ~96px tall (white square instead of small native input).

**Root cause:** Two compounding problems:

1. **Dead CSS selector.** The `night-mode.css:855` rule targets `.login-widget-window .kv-window-header .kv-window-caption` — but KVision's `Window` (different from `Modal`) renders the title inside `<div class="modal-header"><h5 class="modal-title">Title</h5></div>` (verified via `outerHTML` probe on a live `LoginPage`). The `.kv-window-caption` class never appears in KVision's Window output. This selector has been dead since some prior KVision version upgrade — every CSS rule targeting it is a no-op.

2. **Kotlin-side `fontSize = 64` on the Window.** `LoginPage.kt:143` declares `fontSize = CssSize(64, UNIT.px)` on the entire Window. The h5 inside `.modal-header` inherits 64px and gets Bootstrap's `.modal-title { font-size: 1.25rem }` override (which loses to the inline `font-size: 64px` because the inline style is on the parent, not the h5). But more importantly, `1em` inside the inherited context = 64px, so the h5's `margin: 1em 0` (Bootstrap default for h5) becomes `64px 0` — that's `128px` of vertical margin ON TOP OF the h5's own line-height (~53px at 0.83em). Total header height = ~250px. The `.form-check { min-height: 1.5em }` rule inside `.modal-header` also scales to 96px, ballooning the Remember-me checkbox.

**Fix (applied 2026-07-18 to `night-mode.css:841-871`):**

```css
.login-widget-window {
    /* ... existing background / border / radius / shadow / backdrop-filter ... */
    /* Reset the Kotlin Window's `fontSize = 64.px` so Bootstrap-derived children
       don't inflate to 64em-derived sizes. */
    font-size: 16px !important;
    /* Cap the modal so it stays inside the viewport on shorter screens;
       without this the centered transform pushes the top half above y=0. */
    max-height: calc(100vh - 32px) !important;
}

.login-widget-window .modal-header {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 14px 20px !important;
    min-height: 56px !important;
}

.login-widget-window .modal-title {
    flex: 1 1 auto !important;
    text-align: center !important;
    font-size: 26px !important;
    font-weight: 700 !important;
    line-height: 1.2 !important;
    letter-spacing: 1px !important;
    margin: 0 !important;
    color: #f4f6fb !important;
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.7) !important;
}

.login-widget-window .kv-window-icons-container {
    flex: 0 0 auto !important;
}
```

**Verification recipe (Browser dev-tools console probe on the live modal):**

```javascript
const modal = document.querySelector('.login-widget-window');
const r = modal.getBoundingClientRect();
const h5 = modal.querySelector('.modal-title');
const h5r = h5.getBoundingClientRect();
const h5cs = getComputedStyle(h5);
JSON.stringify({
    modal: { w: r.width, h: r.height, top: r.top, fontSize: getComputedStyle(modal).fontSize },
    h5: { fontSize: h5cs.fontSize, margin: h5cs.margin, textAlign: h5cs.textAlign, text: h5.textContent },
    viewport: { w: window.innerWidth, h: window.innerHeight }
})
// Expected AFTER fix: modal.h <= viewport.h - 32, h5.fontSize="26px", h5.margin="0px", h5.textAlign="center"
```

**General rule for any KVision `Window` (not `Modal`) subclass:** always probe `getComputedStyle(modal.querySelector('.modal-title')).fontSize` and `.margin` before assuming the CSS is reaching the title. The KVision class-name difference (`.modal-title` for `Window`, `.modal-title` for `Modal` too — they're the same!) means you can reuse the existing `.modal-title` rule from Pitfall 5, but the Kotlin-side 64px fontSize reset is unique to `Window` subclasses where the user passes `fontSize = CssSize(64, UNIT.px)` to the constructor.

**Companion to Pitfall 5**: both Window and Modal use `.modal-title` for the title element, but the **Kotlin-side fontSize on Window vs Bootstrap's modal flex centering on Modal** make the failure modes distinct. A LoginPage (Window) needs the fontSize reset; a SurrenderConfirmDialog (Modal) needs the Bootstrap-shell fallback from Pitfall 5.

## Pitfall 6 — Bootstrap SRI mismatch + webpack-dev-server caching

When webpack-dev-server starts up, it caches `index.html` and
`night-mode.css` from `kvisionApp/build/processedResources/js/main/`.
Touching the source files does NOT trigger a re-read. To pick up
night-mode.css or index.html changes:

```bash
# After editing night-mode.css or index.html:
cp kvisionApp/src/jsMain/resources/night-mode.css \
   kvisionApp/build/processedResources/js/main/night-mode.css
cp kvisionApp/src/jsMain/resources/index.html \
   kvisionApp/build/processedResources/js/main/index.html
# Then hard-reload the browser tab
```

For Kotlin/JS source changes, webpack hot-reloads automatically — but the
Kotlin/JS compile is incremental. If you only see old behavior after a
Kotlin edit, kill the gradle process and restart `:kvisionApp:jsBrowserDevelopmentRun`.
The compileSync file at
`kvisionApp/build/compileSync/js/main/developmentExecutable/kotlin/Autogenesis-kvisionApp.js`
is what webpack watches; if its mtime is older than your Kotlin source,
you must rebuild.

---

## What the user expects when you fix a modal

When the user asks for a layout fix on a modal in this codebase:

1. Boot all three services (`debugger/scripts/start_servers.sh` is the
   documented sequence — see the main SKILL.md).
2. Navigate to a game (use the "Empire: Exists In Mailman Land Idk..."
   existing commander from the list — don't try to create a new
   commander, the save fails silently because the guest account isn't
   authenticated with AccelByte).
3. Open the broken modal, screenshot the bug, fix it.
4. Rebuild (kill + restart `:kvisionApp:jsBrowserDevelopmentRun`).
5. Hot-reload, screenshot the fixed modal.
6. Shut down all servers (see `kill_pattern.sh` in the references or the
   SKILL.md `shutdown_all_servers` snippet).

The user explicitly does NOT want the dev servers left running between
turns — they will ask "did you shut the servers down?" if you don't.