# Settings Modal Fit Guarantee (Batch 5, 2026-07-14)

Session-specific detail for the SettingsWidget cascade-conflict root cause and fix. Complements the SKILL.md "Override a dialog that uses fixed desktop positioning" recipe and the new "Cascade conflict: width: 100vw !important" pitfall.

## What the user reported

User provided a screenshot showing the Settings modal (opened from Main Menu gear) anchored to the RIGHT edge of the device viewport, with a massive empty band on the left. Modal's right edge was clipped past the viewport. The modal had `width: 600px` (Kotlin hardcoded) and `left: calc(50% - 300px)` (Kotlin hardcoded) — at 390px viewport, this puts the modal at x=-105 with the right edge at x=495 (105px past viewport).

## The non-obvious root cause — cascade conflict, not missing CSS

Initial probe at 390x844 showed the modal correctly positioned at x=12, w=366 (12px margin on both sides). But the user kept reporting the issue was visible. Disagreement between probe result and user's screenshot.

Root cause found by listing ALL matching CSSStyleSheet rules: there were TWO `@media` blocks containing `.login-widget-window { width: ... }` rules:

1. **Line 3620** (older, `@media (max-width: 600px)`): `width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px) !important`
2. **Line 4514** (later in source, `@media (max-width: 600px), (max-height: 600px) and (orientation: portrait)`): `width: 100vw !important; max-width: 100vw !important`

Both rules matched the 390x844 viewport (both arms of the @media trigger). Both had `!important`. Same selector specificity. With same specificity, the rule appearing LATER in source wins (cascade order, not selector specificity).

**The line 4514 rule was the more recent of the two** (added later in the Settings mobile-portrait polish) and was overriding the line 3620 rule. So the modal was being constrained to `100vw` (= 390) instead of `calc(100vw - 24px)` (= 366).

## The fix

Two changes:

1. **Added a new `@media (max-width: 1024px), (max-height: 600px) and (orientation: portrait)` block** at line 3654 with `.login-widget-window { width: calc(100vw - 24px) !important; max-width: calc(100vw - 24px) !important; left: 12px; right: 12px; top: 12px; bottom: auto; transform: none }`. The `@media (max-width: 1024px)` arm covers landscape phones (812px wide) and small tablets where the 600px modal would also overflow.

2. **Removed the conflicting `width: 100vw !important; max-width: 100vw !important` from the existing Settings block at line 4514**, kept the `margin-left: 0; margin-right: 0` rules. The new (later) batch-5 rule at line 3654 now wins the cascade.

After fix: modal at x=12, w=366, right=378 (12px right margin), all content visible (Music Volume 50%, SFX Volume 75%, Show Tooltips, Fullscreen Mode, CLOSE button full-width).

## Why the cascade-conflict detector matters for future modal work

The Settings modal is just one of several `.login-widget-window` modal widgets in the codebase (also: SurrenderConfirmDialog, ResumeOrNewDialog, CollectionOverlay sub-windows). They share the className so they all compete in the same CSS cascade. Whenever you add a new modal override, ALWAYS check what other `@media` blocks already contain `.login-widget-window { ... }` rules.

The full cascade-detection recipe is in the SKILL.md "Cascade conflict: width: 100vw !important later in the source wins over earlier calc(100vw - 24px) !important" pitfall.

## Probe pattern for modal-fit verification

The probe at `/tmp/hermes-verify-settings-fit-20260714/verify.mjs` (hermes-prefixed, exits 0, fresh output at `/tmp/hermes-verify-settings-fit-20260714/run-2.json`) asserts:

```javascript
const probe = await page.evaluate(() => {
  const m = document.querySelector('.login-widget-window');
  if (!m) return { error: "no modal" };
  const r = m.getBoundingClientRect();
  const cs = getComputedStyle(m);
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    modal: {
      x: Math.round(r.left), y: Math.round(r.top),
      w: Math.round(r.width), right: Math.round(r.right),
      h: Math.round(r.height), bottom: Math.round(r.bottom),
    },
    cs: { width: cs.width, maxWidth: cs.maxWidth, left: cs.left, right: cs.right, top: cs.top, height: cs.height },
  };
});

// Assertions
const vpW = probe.viewport.w;
const fits = probe.modal.x >= 0
  && probe.modal.right <= vpW
  && probe.modal.y >= 0
  && probe.modal.bottom <= probe.viewport.h
  && probe.modal.w <= vpW;
const expectedW = vpW - 24; // 100vw - 24px
const widthClamped = probe.modal.w === expectedW;
```

The width-clamp assertion (`probe.modal.w === vpW - 24`) is what catches the cascade-conflict bug. The earlier probe reported `w = 390` (full viewport, NO margin) when the modal was overflowing. After fix: `w = 366` (= vpW - 24). The probe has to assert on the EXACT computed width, not just "fits inside viewport," because "fits" doesn't catch the 12px-margin regression.

## The KVision hPanel nesting that makes SettingsWidget harder than other modals

`SettingsWidget.kt:55-67` hardcodes `width=600.px; position=fixed; top=120px; bottom=220px; left=calc(50% - 300px)` AND sets `transform: dialogFadeIn` animation. The animation's `from`/`to` keyframes touch `transform`, so `translateX(-50%)` for centering is clobbered by the animation during fade-in. The codebase chose `left: calc(50% - 300px)` as a workaround. This means the modal is positioned via `left: Xpx` not `left: 50%; transform: translateX(-50%)`. Mobile overrides must reset BOTH `left` AND `transform`, not just one.

The SettingsWidget-specific overrides added in batch 5:
```css
@media (max-width: 1024px), (max-height: 600px) and (orientation: portrait) {
  .login-widget-window {
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px) !important;
    height: auto !important;
    max-height: calc(100vh - 48px) !important;
    left: 12px !important;
    right: 12px !important;
    top: 12px !important;
    bottom: auto !important;
    transform: none !important;
    margin: 0 !important;
  }
  .login-widget-window h4 {
    text-align: center !important;
    margin-top: 0 !important;
    font-size: 26px !important;
  }
  .login-widget-window input[type="range"] {
    width: 100% !important;
    max-width: 100% !important;
  }
  .login-widget-window .btn.btn-primary:last-of-type {
    width: 100% !important;
    min-height: 48px !important;
    margin-top: 16px !important;
  }
}
```

`bottom: auto` (instead of `bottom: 12px`) lets the modal auto-size to its content instead of stretching to viewport bottom — keeps it compact when content is short (e.g. 4 sliders + 2 checkboxes + 1 button).

## Screenshot evidence

- Pre-fix baseline: `/home/cage/.hermes/images/clip_20260714_174835_1.png` (user's report)
- Pre-fix probe capture: `screenshots/2026-07-14-mainmenu-mobile/12-settings-current.png`
- Post-fix first attempt (still showing 12px past viewport due to cascade conflict): `screenshots/2026-07-14-mainmenu-mobile/13-settings-detail.png`
- Post-fix final: `screenshots/2026-07-14-mainmenu-mobile/15-settings-final-fix.png` (modal at x=12, w=366, right=378, all content fits cleanly)

URL: http://127.0.0.1:8080/preview/2026-07-14-mainmenu-mobile/15-settings-final-fix.png

## Status (2026-07-14)

CSS change is uncommitted at HEAD `4d7344bc4` on branch `Autogenesis-Mobile`. Awaiting user visual confirmation before committing.