# Usage Modal Polish — Batch 2 + Batch 3 Follow-up (2026-07-12)

Session-specific detail for two rounds of fixes to the USAGE & PLAN modal at 390x844 portrait. Complements `references/defect-catalog-2026-07-11.md`.

## Round 1 (batch 2): Six real defects diagnosed and fixed

The user's "Look at the three files, there are tons wrong with it. Identify everything that's not rendering correctly" prompt produced 21 candidate issues from visual inspection, but only 6 were REAL after DOM measurement. Lesson: **always probe before fixing** — visual misinterpretation is easy, and many "obvious" issues are measurement artifacts.

### Issue 1: ALL TIME text overflow (initially mis-diagnosed)
- **Visual:** "ALL TIME" button text appears clipped at right edge
- **Wrong diagnosis:** shrink padding/font-size — fix #1 from initial attempt
- **Right measurement:** `Range.getBoundingClientRect()` showed text bleeds 9px past the button inner content boundary because `overflow: visible` lets text render outside the box even when `scrollWidth === clientWidth`
- **Real fix:** `padding: 8px 6px; font-size: 11px; letter-spacing: 0.03em; overflow: hidden` (overflow:hidden is belt-and-suspenders)
- **Verify with:** `Range.getBoundingClientRect()` comparing textRect.right vs `innerContentRight` (text vs button inner content area)

### Issue 4: Calendar icon overlaps progress bar
- **Visual:** calendar icon at right edge of progress bar, both at same x
- **Probe result:** cal.x=330, bar.right=342, cal.y=500, bar.y=441 (different y, same x)
- **Real fix:** `.usage-meter-right { flex-direction: row; ... padding-top: 8px; border-top: 1px solid ...; margin-top: 8px }`

### Issue 5: Right zone 99px tall
- **Visual:** huge dead space in credits-remaining card
- **Probe result:** `right.h = 99` taking the full bottom of the card
- **Real fix:** same fix as #4 — now `right.h = 29`

### Issue 8: KPI tiles unequal width
- **Visual:** AVG/TURN tile squashed to 69px vs 80/78/80 for others
- **Probe result:** widths = [80, 78, 80, 69] due to inline `width: 25%` from Kotlin (`UsageOverlay.kt:512`) + box-sizing: border-box sub-pixel rounding
- **Real fix:** `.usage-kpi-tile { flex: 1 1 0 !important; width: auto !important; min-width: 0 !important }` — all 4 tiles now 68px each

### Issue 12: MANAGE button overflows plan-strip left edge
- **Visual:** MANAGE button hangs off the left side of the ACTIVE PLAN card
- **Probe result:** MANAGE.x=34, planStrip.x=42 — **8px overflows left**
- **Real fix:** `.usage-plan-strip > .usage-plan-actions { flex-direction: column !important; width: 100% !important }`
- **UPGRADE TO ELITE was NOT actually overflowing** — visual confusion from MANAGE's overflow

### Issue 17: Scroll affordance missing
- **Visual:** modal cuts off at the bottom, no hint that more content scrolls below
- **Probe result:** contentRoot has 473px of overflow content, but no visual mask
- **Real fix:** `.billing-modal-content-root { mask-image: linear-gradient(180deg, black 0%, black calc(100% - 32px), rgba(0, 0, 0, 0.55) 100%) !important }`

### Phantom issues (NOT real bugs)
- **#2** KPI tiles cut off at bottom — modal scrolls, just no visual hint (#17 = real)
- **#3** USED label clipped — measured OK
- **#6** Empty card dead space — was #5
- **#7** Meter card 3-column broken — measured OK
- **#9-11** KPI tile content alignment — fixed by #8
- **#13-14** UPGRADE TO ELITE overflows — measured OK
- **#15** ACTIVE PLAN contrast — visual only
- **#16** RECENT DEDUCTIONS padding — not broken
- **#18-21** modal header border, ghost border — measured OK

## Round 2 (batch 3 follow-up): ALL TIME bleed re-emerged

User reported "The text for all time is bleeding out of the button." Initial measurement showed `scrollWidth=80, clientWidth=70, overflowBy=10px`. So batch-2's first fix did land — but the user was looking at a screenshot from before the fix.

A SECOND round was needed because the batch-2 fix only shrank the text to `scrollWidth=80, clientWidth=70` — but `overflow: visible` still let the rendered text render past the box. The REAL measure is `Range.getBoundingClientRect()` vs the button's inner content boundary:

```
textBleedsRightBy = textRect.right - innerContentRight
```

Before batch-3 follow-up: `+9px` (text extends 9px past button inner content)
After batch-3 follow-up: `-3px` (text ends 3px short of inner content — fits cleanly)

Full fix:
```css
.billing-tab {
    padding: 8px 6px !important;
    font-size: 11px !important;
    letter-spacing: 0.03em !important;
    overflow: hidden !important;
}
```

## Round 3: CommanderSelectionDialog button sizing

User: "The Next button is oddly small vs the cancel button and looks weird."

Visual: CANCEL was 75px wide, NEXT was 55px wide. Both 60px tall, both with same inline `width: 180px`. **Why do identical-width buttons render at different sizes?**

**Root cause:** the footer hPanel at `CommanderSelectionDialog.kt:198` uses KVision's `hPanel(spacing = 16)` rendering as `display: flex; flex-direction: row`. Buttons are children with `flex: 0 1 auto` (Bootstrap default — `flex-shrink: 1`). Total content width = 2×180 + 16px gap = 376px. Available = modal 358 - 2×24 padding = 310px. With `flex-shrink: 1`, flex shrinks children NON-UNIFORMLY by content-size basis. CANCEL has fewer characters, NEXT has more — NEXT shrinks more.

**Probe evidence:**
```
Cancel: inline width=180px, computed width=75px, computed flex="0 1 auto"
Next:   inline width=180px, computed width=55px, computed flex="0 1 auto"
```

**Fix:** force equal-width distribution + pin min-width:
```css
.commander-selection-window > div:last-child > button {
    flex: 1 1 0 !important;
    min-width: 100px !important;
    width: auto !important;
    height: 56px !important;
    margin-right: 0 !important;
    padding: 12px 16px !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
}
```

Post-fix: both buttons 147px wide, 56px tall, flex=1 1 0.

## Recipe: Diagnose "X is overflowing" claims

When a user says "X is overflowing Y" or "X is bleeding out":

1. **Measure three things**:
   - `element.getBoundingClientRect()` — the visible box
   - `element.clientWidth / clientHeight` — content area (excludes scrollbar but not border/padding)
   - `element.scrollWidth / scrollHeight` — full content (visible + clipped)
2. **If `scrollWidth > clientWidth`** — content IS clipped by the element's own box. Use `overflow: hidden` or shrink the content.
3. **If `scrollWidth === clientWidth`** — element thinks it fits, but rendered text might still extend past the box if `overflow: visible`. **The gotcha.** Use `Range.getBoundingClientRect()` on the actual text node to measure rendered text geometry.
4. **Compare text geometry to inner content boundary**:
   - `textRect.right - (elementRect.right - paddingRight - borderRightWidth) > 0` → text bleeds right
   - `textRect.left - (elementRect.left + paddingLeft + borderLeftWidth) < 0` → text bleeds left

**Why this matters:** `scrollWidth === clientWidth` is the universal "content fits" probe for the document's clip, but it doesn't account for `overflow: visible` which lets the browser render text outside the element's box. For visual rendering issues, the geometry check via `Range.getBoundingClientRect()` is ground truth.

## Recipe: Diagnose "button X is smaller than button Y" claims

When two buttons in the same hPanel render at different widths:

1. Measure each button's `getBoundingClientRect().width` AND the inline `width` style
2. Measure the parent hPanel's `getBoundingClientRect().width` and `padding`
3. Compute available space: `parentWidth - parentPaddingLeft - parentPaddingRight - sum(childMarginRight × numChildren)` = free space
4. Compare free space to total requested child width: if `freeSpace < totalRequested`, flex shrink is happening
5. Read the children's `flex-shrink` value — default is 1 (shrink), which shrinks children NON-UNIFORMLY by content-size basis. To force equal distribution: `flex: 1 1 0` on all siblings.

**KVision's `hPanel(spacing = N)` injects inline `margin-right: Npx` on every child including the last one.** When computing free space, subtract ALL child margins (not just N-1).

## Ad-hoc verifiers from this session

- `/tmp/hermes-verify-usage-batch2-20260712/verify.mjs` — usage-modal issues 1-21 diagnostic. Used the `Range.getBoundingClientRect()` pattern to distinguish real overflow from visual perception.
- `/tmp/hermes-verify-cmdsel-batch3-20260712/verify.mjs` — commander selection button sizing. Measures each button's inline width vs computed width vs parent panel width.
- `/tmp/hermes-verify-cmdsel-batch3-20260712/usage-bounds.mjs` — bounds probe for ALL TIME bleed. Computes `textBleedsRightBy` from textRect vs inner content boundary.

All three live in `/tmp/hermes-verify-*` hermes-prefixed directories with `node_modules` symlinked to `kvisionApp-e2e/node_modules`.
