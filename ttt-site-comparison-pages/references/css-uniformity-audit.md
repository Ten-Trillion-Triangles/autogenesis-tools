# CSS Uniformity Audit for Comparison Pages

When a comparison page looks visually different from its row-mates, the cause is almost always missing or wrong CSS rules in the page's `<style>` block. This is a checklist + remediation pattern for bringing a page into visual uniformity with the rest of the comparison set.

## When to run this audit

- After writing a new comparison page from scratch
- After a user reports a page "looks broken" or "doesn't match the others"
- When `boundingBox()` shows the page is structurally different (taller, wider, or the FAQ section has no card styling)
- When vision tool on a screenshot says "no card styling" / "text directly on background" / "uneven spacing"

## The audit grep

Run this to compare the page's CSS block against the canonical reference (`tpipe-vs-koog.astro` as of June 2026):

```bash
# Check for the base rules the reference has — blank grep result = missing rule
for selector in \
  ".faq-item {" \
  ".migration-step {" \
  ".step-number {" \
  ".step-content h3 {" \
  ".step-content p {" \
  ".faq-item h3 {" \
  ".faq-item p {" \
  ".faq-grid {" \
  ".migration-cta {" \
  ".see-also-links {" \
  ".see-also-card {" \
  ".card-label {" \
  ".card-title {" \
  ".card-desc {" \
  ".cta-button {" \
  ".cta-button.primary {" \
; do
  echo "=== $selector ==="
  grep -c "^\\s*${selector}" src/pages/comparison/<page>.astro
done
```

If any selector returns 0, the page is missing that rule. The reference page should return 1+ for every selector.

## Common omission patterns

When writing a new page from scratch, the per-element styles (`.faq-item h3`, `.faq-item p`, `.see-also-card`) get copied from an existing page, but the **base/parent rules** (`.faq-item { ... }`, `.see-also-card { ... }`) get missed. The page renders individual text correctly, but the parent has no card background, no border, no padding — the structural framing is missing.

**Concrete examples observed (June 13, 2026):**

| Page | Missing base rule | Visual symptom |
|---|---|---|
| tpipe-vs-microsoft-agent-framework.astro | `.faq-item { ... }` | FAQ items rendered as raw text on the dark background, no card border |
| Same page | `.migration-step { ... }` proper sizing | Step numbers were 48px circles, gap 2rem — out of scale with the 32px / 1.5rem pattern elsewhere |
| Same page | `.cta-button.secondary { ... }` | Only `.cta-button.primary` was styled, missing the secondary state |
| Same page | `.faq-section h2 { ... }` margin | FAQ section heading had no bottom margin, ran into the first Q&A card |

## The remediation pattern — wholesale replace, not incremental merge

When a page is missing CSS rules, do not patch each missing rule incrementally. The result will still look different from the reference and you'll iterate forever. Instead, locate the reference block and wholesale-replace.

**Step 1: Identify the reference page.** The most recently updated comparison page is the canonical reference. As of June 2026, `tpipe-vs-koog.astro` is the reference (it was the last page edited before the MAF page was written, so its CSS represents the current "good" state).

**Step 2: Identify the section boundaries.** Find the start of the relevant CSS section (e.g., `.migration-steps {`) and the end (the closing `</style>` or the next `@media` block / unrelated section).

**Step 3: Wholesale-replace.** In one `patch` call, replace the entire CSS block from the reference. Preserve the page's class-name variations (e.g., `.feature-maf` instead of `.feature-koog` in the mobile media query) — only the CSS values change, not the class names.

**Step 4: Verify with vision tool.** Screenshot the page via Playwright, run the vision tool on the relevant section. The vision tool's answer should match the canonical visual outcome described in the SKILL.md pitfalls section.

**Step 5: Run the hedge-phrase audit script.** Wholesale replaces can introduce new hedge phrases if the reference page has them. Run `scripts/hedge-phrase-audit.sh` and confirm 0 matches.

## Operational test for completeness

After the wholesale replace, the page should:

1. Pass the audit grep above with all selectors returning 1+ (modulo class-name variations).
2. Render with FAQ cards that have `background-color: var(--color-surface-container-low)`, `border: 1px solid var(--color-outline-variant)`, `border-radius: var(--radius-xl)`, `padding: 1.5rem`.
3. Render migration steps with `width: 32px; height: 32px` step numbers, `gap: 1.5rem` between steps, `1rem` h3 font-size, `0.875rem` p font-size.
4. Render See Also cards with `border-radius: var(--radius-xl)`, `padding: 1.5rem`, `background-color: var(--color-surface-container-low)`.
5. Have 0 hedge phrase matches per the audit script.
6. Have 0 missing 200s on the dev server.
7. Look visually consistent in a side-by-side screenshot comparison with the other pages.

If any of these fail, repeat the wholesale-replace, this time including more of the page's CSS in the patch. The "more inclusive" direction is always safe; the "less inclusive" direction is where you miss rules.
