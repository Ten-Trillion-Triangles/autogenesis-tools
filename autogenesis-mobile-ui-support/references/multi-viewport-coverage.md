# Multi-Viewport Coverage for Mobile Polish

A defect that passes the iPhone 12 (390×844) probe may still clip on narrower phones. Captured 2026-07-12: MainMenu header-row defect shipped as "PASS at 390×844" — the user caught the gear clipping at 320×568 and 375×667 on their actual phone.

## Canonical 5-Viewport List

When verifying ANY header / row layout fix, assert at all 5 of these (logical CSS pixels):

| Device | Viewport | matchMedia `(max-width:600px)` | matchMedia `(max-height:600px) and (orientation:portrait)` |
|---|---|---|---|
| iPhone SE 1st gen | 320×568 | true | true |
| iPhone SE 3rd gen | 375×667 | true | false (only width-driven) |
| iPhone 12 mini | 390×664 | true | false |
| iPhone 12 | 390×844 | true | false |
| iPhone 14 Pro Max | 430×932 | true | false |

The 320×568 case is the **critical small-phone test**. Layouts that pass 390×844 commonly clip at 320×568 because the inner hPanel `spacing = 15` (KVision default) sums with intrinsic button widths and overflows.

## Per-Viewport Assertions

For a header-row fix, each viewport should report:

```
[viewport-name wxh]
  bg={computed background-position}  scrollW=N  gear.right=X
  credits=WxH  secondaries=N (each HxW)
PASS/FAIL: no horizontal overflow
PASS/FAIL: gear visible (not clipped)
PASS/FAIL: gear has positive width
PASS/FAIL: header-secondary #i compact (H_RANGE) tall
```

The critical assertions are:
1. `scrollW <= viewport.w + 1` — no horizontal overflow
2. `gear.right <= viewport.w + 1` — gear not clipped past the right edge
3. Header secondary buttons within the expected compact-height band

## Canonical Probe

`kvisionApp-e2e/probes/mainmenu-mobile-multi-viewport.mjs` is the reference implementation. It uses `getBoundingClientRect()` for each header child at each viewport, asserts no clip and compact sizing, and saves a per-viewport screenshot to `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-12-mainmenu-mobile-fix/mainmenu-{viewport}.png`.

Drop-in template for a new widget probe: copy the structure, change the selectors, change the per-widget assertion (e.g. for a footer row, assert the footer's bottom edge, not header).

## What Multi-Viewport Reveals That Single-Viewport Hides

- KVision `hPanel(spacing = 15)` doesn't compress at narrow widths (the children overflow the parent), so a row that fits at 375px can clip at 320px.
- `min-width: 28px !important` on the gear wins over a more-specific rule's `min-width: 0 !important` only when the gear rule's specificity is equal or higher. The parent `> *` rule and child `.btn-options` rule need to be ordered correctly (child wins by specificity, not source order in this case).
- Background-image wordmark positions that work at 390×844 (e.g. `center 30%`) leave a giant dead band at 390×664 (iPhone 12 mini is shorter by 180px). Pan values may need re-tuning per aspect ratio.

## When NOT to Use Multi-Viewport

- Modal/dialog fixes (dialogs are `position: fixed`, so the same logic applies at all viewports — single-viewport probe is enough)
- Single-button-size fixes where the button is centered and only its own size matters
- Typography fixes that affect every viewport identically

Use it for: header rows, bottom rows, fixed-position elements that depend on viewport width, anything involving `flex-wrap` or `min-width`.

## Related Commits

- `0924cc9cc` — Multi-viewport coverage added to existing MainMenu probe; 25/25 PASS
- `8febe1c59` — Earlier single-viewport probe shipped with the gear-clipping defect (rectified by `0924cc9cc`)
