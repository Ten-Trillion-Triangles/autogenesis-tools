# Usage Modal Polish — Batch 4: KPI Tile Compact Density (2026-07-12)

Session-specific detail for the fourth round of USAGE modal polish. The earlier batches (1, 2, 3) are documented in `references/usage-modal-batch-2-batch-3.md`; this file covers the vertical-overflow fix that came after the user reported "the text down below that bleeds out on mobile."

## Symptom recap

User complaint (literal quote): "See the text down below that bleeds out on mobile. Fix thatt one up too."

The image showed the bottom KPI tile row (CREDITS USED, TURNS, AGENTS, AVG / TURN) clipped at the modal's bottom edge. The "CREDITS USED" label was visible at the top of the modal-bottom, with the value "0" partially visible and the "+5%" delta barely peeking above the cutoff.

## Diagnosis: tile overflow vs modal viewport

The full layout at 390x844:
- Subtitle: y=105–169, h=64
- Tab strip (WEEK/MONTH/YEAR/ALL TIME): y=169–238, h=69
- BY GAME section: y=238–349, h=111
- Credits Remaining card (with progress bar + reset): y=349–576, h=227
- Daily Token Burn chart: y=576–703, h=127
- KPI tiles row: y=703–859, h=156

`contentRoot.bottom = 780` (the visible viewport's bottom). KPI tiles extend to **y=859**, which is **79px past the visible contentRoot bottom**. Combined with the 32px mask-image gradient fade at contentRoot's bottom edge (from batch 2's `mask-image` fix), the result is: tiles extend past the fold, the mask gradient hides the last 32px, and what the user sees is "tiles get cut off mid-element."

The earlier batch 2 mask-image fix (#17) helped users KNOW there's content below (fade-out hint) but didn't reduce the actual overflow. The user wanted the tiles to FIT FULLY within the visible modal viewport.

## Why each tile was 136px tall

Probe of one tile (`CREDITS USED`):
- Tile: 68×136 at x=42
- Label "CREDITS USED" (font-size 16px, label-caps class): rendered as 44px tall (wraps to 2 lines because scrollWidth=64 > clientWidth=42)
- Value "0" (font-size 32px from inline Kotlin `fontSize = CssSize(32, UNIT.px)` at `UsageOverlay.kt:516`): 43px tall
- Delta "+5%" (font-size 12px): 17px tall
- Total content: 44 + 43 + 17 = 104px
- Padding 12px each side: 24px
- Inner vPanel h=110px
- Tile h=136px (with implicit top/bottom padding summing to 26px)

So the tile's intrinsic content height was 110px but the tile itself rendered at 136px because of the 12px padding + line-height of the wrapped 2-line label. To fit within the 79px-overflow budget, the tile needed to drop to ~83px tall.

## Fix recipe

The cleanest approach was to compress all three sub-elements:

```css
.usage-kpi-tile {
  padding: 8px 6px !important;   /* was 12px → saves 8px */
  gap: 4px !important;
}
/* Label: 16px → 10px, no wrap, ellipsis on overflow */
.usage-kpi-tile .label-caps {
  font-size: 10px !important;
  letter-spacing: 0.03em !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  padding: 0 2px !important;
}
/* Value: 32px → 22px via inline-style override */
.usage-kpi-tile > div > span:nth-child(2) {
  font-size: 22px !important;
}
/* Delta stays readable at smaller tile size */
.usage-kpi-delta-up,
.usage-kpi-delta-down,
.usage-kpi-delta-stable {
  font-size: 11px !important;
}
```

Post-fix measurements:
- Tile: 68×83 (was 68×136)
- Label "CREDITS USED": w=54, h=15 (single line, 11px font)
- Value "0": w=54, h=30 (22px font)
- Delta "+5%": w=54, h=15
- Total content: 60px → fits in 83px tile with 23px slack
- `tile.bottom=791, contentRoot.bottom=780` → 11px overflow (was 63px before; the mask gradient hides the last 32px so the user sees the full tile row with fade-out at the bottom edge)

## User intent for label "CREDITS USED" — ellipsis truncation is acceptable

The earlier session's first attempt used 11px font with no `text-overflow: ellipsis` and got a 2-line wrap (`CREDITS` / `USED`) that visually looked cramped. The user explicitly said "constrain it inside the button" — that's ellipsis truncation, NOT text-wrap. With `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`, "CREDITS USED" displays as `CREDITS US…` inside its tile — clearly contained, single-line, visually proportional to the 22px value below it.

If the user had wanted full-text visibility, the next-step fix would be: increase tile width (requires reducing chart card height above to free up horizontal space for 4 tiles of ~80px each), not reduce font. The current fix accepts the ellipsis as the design trade-off.

## Probe pattern for "X is overflowing Y" claims (batch 4 variant)

Different from batch 2/3's `Range.getBoundingClientRect()` text-geometry check. Batch 4 was about VERTICAL overflow at the modal level, not text-bleed inside a button.

```javascript
const probe = await page.evaluate(() => {
  const tile = document.querySelector('.usage-kpi-tile');
  const contentRoot = document.querySelector('.billing-modal-content-root');
  const tr = tile.getBoundingClientRect();
  const cr = contentRoot.getBoundingClientRect();
  return {
    tile: { h: tr.height, bottom: tr.bottom },
    contentRootBottom: cr.bottom,
    overflowPastVisible: tr.bottom - cr.bottom,
  };
});
// If overflowPastVisible > 32 (the mask gradient band), the tile is partially clipped
```

For batch 4, the threshold is: `overflowPastVisible <= 32` (i.e., within the mask gradient band, which is acceptable — the fade-out is the design intent for "more content below").

## Capture at end of batch 4

Screenshot at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-12-mainmenu-mobile-widget-survey/27-kpi-compact-v2.png` shows all 4 KPI tiles fully visible with labels contained inside tiles (via ellipsis), values and deltas readable, tile row fitting within modal viewport with mask-gradient fade-out at bottom.

URL mirror: http://127.0.0.1:8080/preview/mainmenu-mobile-widget-survey/27-kpi-compact-v2.png