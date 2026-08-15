# 2026-07-15 mobile-portrait batch — CollectionOverlay tabs + CommanderSelectionDialog Step 2

Two CSS-only fixes shipped to `Autogenesis-Mobile` (still uncommitted as of this reference) during the 2026-07-15 session. Both bypassed Kotlin rebuilds by using CSS4 structural selectors. Both verified via the injected-HTML probe pattern (`scripts/hermes-verify-adhoc-injected-html.mjs`).

## Fix 1 — CollectionOverlay tab button "COMMANDERS" label overflow

**Defect**: `.collection-tab-button` was 90px wide with 16px horizontal padding = 58px content area. The `::after { content: attr(title); text-transform: uppercase; letter-spacing: 0.05em; font-size: 11px }` rendered "COMMANDERS" (10 chars) at ~80px wide, overflowing the right rounded edge. "ERS" pressed against the border.

**Why scrollWidth lied**: per the pitfall in SKILL.md ("`::after` pseudo-element content is invisible to scrollWidth"), pseudo-elements don't contribute to scrollWidth on flex children. Probe reported `scrollWidth === clientWidth === 88px` (overflowing:false) while visually overflowing. Only the screenshot proved the bug.

**Fix** (night-mode.css:3564-3589):
| Property            | Before     | After      | Rationale                                       |
|---------------------|------------|------------|-------------------------------------------------|
| width               | 90px       | 110px      | Fits 10-char labels at the new font sizing     |
| padding             | 12px 16px  | 12px 14px  | Tighter horizontal padding                      |
| overflow            | (none)     | hidden     | Safety net for future label changes             |
| ::after font-size   | 11px       | 10px       | Tighter label rendering                         |
| ::after letter-spacing | 0.05em  | 0.02em     | Less aggressive spacing                         |
| ::after white-space | (normal)   | nowrap     | Prevent wrap on long future labels              |

**Ad-hoc probe**: `/tmp/hermes-verify-collection-tab-bleed-20260715.mjs`. Screenshots at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-15-collection-tab-bleed/`. Computed-style proof (post-fix):
- `.collection-tab-button` width=110px (was 90px)
- padding "12px 14px" (was "12px 16px")
- `::after` font-size 10px, letter-spacing 0.2px

## Fix 2 — CommanderSelectionDialog Step 2: opponent cards stack + active glow tightened

**Defects** (two distinct issues, both at 390x844 modal):
1. **Three opponent cards (2/3/4 Players) at 145px each in a row** — "Players" wrapped syllable-by-syllable to "Pla/ye/rs" on each card, icon overlapped text
2. **Yellow active-card glow** (`box-shadow: 0 0 50px rgba(255,215,0,0.7)` + `::after` with 60px cyan halo) extended ~110px outside the card on a 145px-wide card — bled well past the modal's right edge

**Why a Kotlin change was avoided**: a className addition (`className = "commander-selection-opponent-row"` on the opponent hPanel at CommanderSelectionDialog.kt:343) would have required a full `:kvisionApp:jsBrowserProductionWebpack` rebuild (~7 minutes) that the user has been bitten by in past sessions. Used a CSS4 `:has()` + `:nth-of-type(3)` structural selector instead — opponent row has 3 cards, GameType row has 2.

**Fix** (night-mode.css:3886-3908):
```css
/* Stack opponent row to 1-col on portrait — opponent row has 3 cards,
   GameType row has 2, so :nth-of-type(3) only matches the opponent row. */
.commander-selection-step-2 div:has(> .commander-selection-card:nth-of-type(3)) {
  flex-direction: column !important;
  align-items: stretch !important;
  gap: 12px !important;
}

/* Tighten active card glow on portrait — full 50px+60px glow bleeds off
   the modal at narrow widths. */
.commander-selection-card-active {
  box-shadow: 0 0 18px rgba(255, 215, 0, 0.55),
              inset 0 0 12px rgba(255, 215, 0, 0.3) !important;
  overflow: hidden !important;
}
.commander-selection-card-active::after {
  display: none !important;
}
```

**Why `class-rule !important` beats KVision's inline style** (separate pitfall in SKILL.md): the active card's inline `box-shadow` from KVision's Kotlin is 50px, but the class-rule `@media .commander-selection-card-active { box-shadow: 0 0 18px !important }` overrides it via the CSS cascade rule that `!important` on a class rule beats non-`!important` on an inline style, regardless of selector specificity. The `getComputedStyle` confirms `18px + 12px inset` is the live value.

**Ad-hoc probe**: `/tmp/hermes-verify-opponent-cards-20260715.mjs`. Screenshots at `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/2026-07-15-opponent-cards/`. Computed-style proof (post-fix):
| Card | Before (simulated) | After |
|---|---|---|
| 2/3/4 Players width × height | 145 × 109 | 306 × 82 |
| Active box-shadow | 50px + 25px inset | 18px + 12px inset |
| Active overflow | visible (bleed allowed) | hidden (clipped) |

## Working tree state at end of session

The branch's working tree now has my +21 line CSS fix plus pre-existing uncommitted wave-2 work:
- `night-mode.css`: +264 lines (my +21 + pre-existing SettingsWidget `@media (max-width: 1024px)` block, ~+222)
- `CommanderSelectionDialog.kt`: +42 lines (pre-existing matchMedia listener block + comment, no net change from this session)

The user was offered three commit-scoping options (focused fix / combined batch / leave alone) and will likely commit separately or in batched waves.

## Recipes that earned their place in the skill

The three patterns that came up across both fixes this session and warranted new entries in SKILL.md:
1. **`scrollWidth` lies for `::after` pseudo overflow** — Range.getBoundingClientRect or visual diff required
2. **`:has()` + `:nth-of-type(N)` for child-count structural targeting** — avoids Kotlin rebuild
3. **Class-rule `!important` beats inline style without `!important`** — relevant to KVision's heavy inline styling

All three are now in the "Pitfalls" section of the main SKILL.md and the third is also surfaced as a "Key CSS Recipes" entry.