# Adding a New Comparison Page — Site Wiring Checklist

The research half of "add a TPipe vs [competitor] page" is covered in `competitor-add-workflow.md`. This reference covers the page-build half: every touchpoint in `src/pages/comparison/index.astro` and the new `.astro` file itself that must be updated for the new card to be live, linkable, and discoverable. Re-deriving this from scratch each time wastes 15-20 minutes of patch iteration.

Worked example: TPipe vs JetBrains Koog, June 13, 2026. The 7th comparison target. All patches below were applied in that session.

## 1. Create the new page file

`src/pages/comparison/tpipe-vs-<slug>.astro`

Follow the structure of the existing `tpipe-vs-langchain.astro` (the "primary" template). Required sections in order:

1. Frontmatter (canonicalURL, imports)
2. `<BaseLayout>` with title, description, canonicalURL, page="comparison"
3. `<main class="comparison-page">` with `<header>` containing breadcrumb, comparison-badge ("Head-to-Head"), h1, subtitle, `<div class="quick-verdict">` (5-6 verdict items)
4. "Why This Comparison Matters" section — 3-5 paragraphs, lead with the deployment-target question
5. "Architecture Comparison" section with `<div class="feature-table">` and 9-12 feature-rows (header + rows)
6. "When to Choose TPipe" + "When to Choose [Competitor]" section — TPipe is 5-8 bullets; competitor is 2 short paragraphs max, framed as locked-in fallback
7. "Adopting TPipe for [Production/Capability]" section with 4-6 numbered `migration-step` divs
8. "Frequently Asked Questions" section with 5-7 `faq-item` divs
9. "See Also" section with 2-3 `see-also-card` divs
10. Two JSON-LD `<script>` blocks (Article + BreadcrumbList)
11. CSS — copy from `tpipe-vs-langchain.astro` lines 408-874 verbatim, then rename `.feature-langchain` → `.feature-<slug>` and `.verdict-value.langchain` → `.verdict-value.<slug>` and `.badge-framework` color to the vendor's brand

Title format: `"TPipe vs [Competitor] — [TPipe category] vs [Competitor category]"`

## 2. The competitor CSS class rename

The langchain template hardcodes `.feature-langchain` and `.verdict-value.langchain` in the CSS. When you copy the styles to the new page, rename them. The new page is fully self-contained (per the "Don't merge CSS classes across pages" pitfall), so the rename is local to the new file.

For the **index.astro verdict color**, the existing pattern is one CSS class per vendor:

| Vendor | Color (hex) | CSS class |
|---|---|---|
| LangChain | #ffc107 (yellow) | `.verdict-langchain` |
| LangGraph | #9c27b0 (purple) | `.verdict-langgraph` |
| CrewAI | #ff5722 (deep orange) | `.verdict-crewai` |
| Google ADK | #4285f4 (Google blue) | `.verdict-adk` |
| AutoGen | #0078d4 (Microsoft blue) | `.verdict-autogen` |
| A2A Protocol | #00bcd4 (cyan) | `.verdict-a2a` |
| Koog (added June 13, 2026) | #fe315d (JetBrains red) | `.verdict-koog` |
| Microsoft Agent Framework (added June 13, 2026) | #5c2d91 (Microsoft purple) | `.verdict-maf` |

Pick a brand-recognizable color for the new vendor. If the vendor has a documented brand color (JetBrains red, Google blue, etc.), use that. If not, use a hue that doesn't collide with the existing palette.

## 3. The index.astro patches (7 touchpoints)

When a new card goes up, the hub needs 7 surgical patches. Read the existing index.astro end-to-end first, then apply each:

1. **`<BaseLayout description=...>`** — add the new vendor to the comma-separated list (current example: "TPipe vs LangChain, LangGraph, CrewAI, Google ADK, AutoGen, Koog, and A2A Protocol")
2. **`<div class="index-meta">`** — bump "6 Comparisons" → "7 Comparisons" and "Updated June 8, 2026" → "Updated June 13, 2026" (or current date)
3. **Add the new `<a href="/comparison/tpipe-vs-..." class="comparison-card">` block** — insert in the position that fits the visual priority. Convention: vendor cards in roughly alphabetical order by vendor name, with the "Highest Traffic" LangChain card first as `class="comparison-card primary"`. Protocol cards (like A2A) come last.
4. **Add a new verdict-color CSS class** in the `<style>` block (`.verdict-<slug> { color: #...; font-weight: 600; }`)
5. **JSON-LD `description`** in the CollectionPage script block — add the new vendor to the comma-separated list
6. **JSON-LD `dateModified`** in the CollectionPage script block — refresh to today. `datePublished` stays the same.
7. **Bottom "architectural line" section** — add a sentence linking to the new card as a related comparison, framed positively (e.g., "Evaluating the JVM-native landscape? [TPipe vs Koog] covers the headless-first versus IDE-first split..."). Don't make this section longer than 3-4 sentences total — the existing copy already covers the hub's positioning.

## 4. JSON-LD dateModified discipline

Two JSON-LD dateModified fields refresh on a new card:

- **New page** (`tpipe-vs-<slug>.astro`): `datePublished` AND `dateModified` both = today's date. The new page has no history, so both are today.
- **Index.astro**: `dateModified` refreshes to today. `datePublished` stays the same (the hub was first published earlier).

If you only update one, the schema validator will flag it. The audit pattern: `grep -E "datePublished|dateModified" src/pages/comparison/tpipe-vs-<slug>.astro src/pages/comparison/index.astro`.

## 5. The link-target audit (separate from hedge audit)

The skill's hedge audit catches phrasing mistakes. A separate audit catches broken links. Per the homepage table pitfall, link targets in the new card must resolve to existing pages. One-liner:

```bash
grep -oE 'href="/comparison/[^"]+"' src/pages/comparison/tpipe-vs-<slug>.astro src/pages/comparison/index.astro | sort | uniq -c
```

Every URL the page links to should exist in `src/pages/comparison/`. If you linked to `/comparison/tpipe-vs-something-not-yet-built`, the audit will surface it. Don't ship a card that links to a 404.

## 6. The vendor color hex discipline

The verdict-color CSS in `index.astro` and the `.badge-framework` color in the new page should be **consistent**. If the index card says Koog wins in JetBrains red, the page's "When to Choose Koog" verdict value should also be JetBrains red. Two visual systems pointing at the same vendor with different colors is a brand inconsistency that bots and humans both catch.

The convention: pick the hex once, use it in both files. Document it in the table above (or in a follow-on reference when the count grows past 10).

## 7. When to choose [Competitor] — the 2-paragraph rule

The "When to choose [competitor]" section is the most-likely voice-rule-violation site. Per the skill's main rules:

- Maximum 2 short paragraphs
- Lead with the locked-in framing: "If you're already locked into [ecosystem]..."
- The fallback paragraph reframes the gap as the deployment-target distinction, not a TPipe win
- No "honest assessment" / "reasonable choice" / "well-suited" / "architectural ceiling" closings

Failure observed (June 13, 2026, Koog page): first draft wrote "the architectural ceiling is the same as every graph-based framework" in the fallback paragraph. The audit caught it; the patch was "the structural limits show." Lesson encoded in the SKILL.md pitfalls section — the audit is the gate, not the afterthought.

## 8. Don't merge CSS, but do inherit structure

The new page's `<style>` block should be a near-verbatim copy of the langchain template's styles. Don't refactor to share a stylesheet — out of scope per the existing pitfall. Do rename the two CSS classes that contain the vendor name (`.feature-langchain` → `.feature-<slug>`, `.verdict-value.langchain` → `.verdict-value.<slug>`). Leave the rest of the CSS as-is.

## Quick verification commands

After the page is written and the index is patched, run all four:

```bash
# 1. Build
npm run build

# 2. Hedge audit (the gate — see pitfalls)
./scripts/hedge-phrase-audit.sh

# 3. Link target audit
grep -oE 'href="/comparison/[^"]+"' src/pages/comparison/tpipe-vs-<slug>.astro src/pages/comparison/index.astro | sort | uniq -c

# 4. JSON-LD dateModified check
grep -E "datePublished|dateModified" src/pages/comparison/tpipe-vs-<slug>.astro src/pages/comparison/index.astro
```

If all four pass, the new card is live, linkable, hedge-free, and dated correctly. The dev server (started with `npm run dev`) will hot-reload — curl `http://localhost:4321/comparison/tpipe-vs-<slug>` for HTTP 200 to confirm.
