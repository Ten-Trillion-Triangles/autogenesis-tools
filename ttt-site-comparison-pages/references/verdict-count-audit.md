# Verdict Count Audit — Sweep Pattern

A comparison page's verdict ("TPipe wins N of M dimensions") is repeated across at least five locations in the ttt-site codebase. These strings are written independently and **drift out of sync without breaking the build**. This file is the sweep procedure to use whenever a verdict number changes or is reported as stale.

## Where the verdict appears

For a page like `tpipe-vs-koog.astro`, the same logical verdict ("10 of 11 dimensions" or "8 of 11 dimensions") is rendered in:

1. **Quick-verdict block** (in the header, `<div class="quick-verdict">` → `<span class="verdict-value tpipe">` and `<span class="verdict-value koog">`). Two spans: TPipe count + Koog count. Example: "10 of 11 dimensions" vs "1 draw, 0 outright wins".
2. **Narrative intro paragraph** (the lead-in to the feature table, typically right before the `<section class="comparison-section">` for the architecture comparison). Prose form: "Ten of eleven dimensions go to TPipe. One is a Draw — … Koog wins zero outright."
3. **Meta description in frontmatter** (line 8-9 of the `.astro` file, `description="…"`). Compact form: "10-of-11 in TPipe's favor" or similar.
4. **JSON-LD `description` field** (the schema.org Article script tag at the bottom of the file). Often a near-duplicate of the meta description.
5. **Hub card on `src/pages/comparison/index.astro`** (the `<a class="comparison-card">` block for that target, lines ~35-220). Independent prose in three spans: `verdict-tpipe` + `verdict-vs` + `verdict-koog`.

That's five locations for the same fact, written by different parts of the file's lifetime, with no compile-time check that they agree.

## Sweep procedure

When the user reports a stale count on a comparison page, or when you are about to ship a count change, run this exact sweep. Do not skip the hub card — the hub is a separate file, separate write history, separate drift surface.

```bash
# Step 1: locate every verdict-shape string on the page itself.
grep -nE "(\d+ of \d+|\d+-of-\d+|outright wins|are Draws|is a Draw|is a draw|wins on|wins \d+ of)" \
  src/pages/comparison/<page>.astro

# Step 2: locate the matching card on the hub.
grep -nA2 "tpipe-vs-<competitor>" src/pages/comparison/index.astro

# Step 3: verify the JSON-LD description matches the meta description.
grep -nE "(10-of-11|8 of 11|\d+ of \d+ dimensions)" src/pages/comparison/<page>.astro
```

Expected output of Step 1: at minimum 4 hits (quick-verdict block tpipe span, quick-verdict block koog span, narrative paragraph, meta description). Step 3: 2 hits (meta + JSON-LD).

If you find fewer, one of the locations is missing the count string and the page is partially-stale. If you find 5+ on the page (e.g., the narrative has the count twice, or the verdict block has a third span), there's duplicate prose — likely from a prior rewrite that didn't dedupe.

## Source-of-truth order

When the counts disagree, derive the matrix from the **feature table itself**, not from any single count string. The table is the only place where each dimension's winner is explicit.

For `tpipe-vs-koog.astro` the 11 dimensions are: Paradigm, Memory Model, Reasoning Optimization, P2P Architecture, Multi-Agent, Safety/Governance, Tool Calling, Observability, Language/Runtime, Multiplatform Mobile, Pricing/TCO.

The verdicts in the article (as of June 13, 2026):

| Dimension | Verdict | Reasoning |
|---|---|---|
| Paradigm | **Draw** | Substrate vs graph framework — article explicitly frames as "different design centers" |
| Memory Model | TPipe win | LoreBook deterministic vs RAG probabilistic |
| Reasoning Optimization | TPipe win | Chain-of-Draft vs transport-only caching |
| P2P Architecture | TPipe win | Mesh vs hub-and-spoke |
| Multi-Agent | TPipe win | Junction's 6 voting recipes, no JVM equivalent |
| Safety/Governance | TPipe win | KillSwitch + open bug #1944 in Koog |
| Tool Calling | TPipe win | PCP in-process sandbox vs MCP external |
| Observability | TPipe win | TraceServer self-hosted $0 vs Langfuse SaaS |
| Language/Runtime | TPipe win | JVM-first substrate vs KMP common code |
| Multiplatform Mobile | TPipe win | GraalVM native binary vs KMP bytecode |
| Pricing/TCO | TPipe win | Manifold $7,500 all-inclusive vs Langfuse stacks up |

**10 TPipe wins, 1 draw (Paradigm), 0 Koog wins.**

Note: the KMP pitfall in the parent SKILL.md states the 1 draw is "Multiplatform Mobile, where KMP's iOS/JS/WasmJS target surface is a real and legitimate Koog advantage." This was the v3 report framing. The shipped article on the ttt-site (as of June 13, 2026) frames Paradigm as the 1 draw. Both are defensible; the next refresh should reconcile which dimension is the 1 draw and update the page, the hub card, and the skill's pitfall to the same answer. Until reconciled, prefer the article's current state as the source of truth (it is what the public sees).

## Failure modes observed

- **Narrative drift**: A paragraph says "Eight of eleven" but the verdict block above it says "10 of 11". This happened on the ttt-site Koog page June 13, 2026. Fix: derive from the table, sweep all five locations.
- **Hub card drift**: The article and the hub card each have a verdict, but the framing is different (article says "X wins", card says "Y wins on Z"). Most common. Fix: align the card's verdict span with the article's verdict block. If the matrix is 10/1/0 and the card says "Y wins on Z", the card is over-scoring — the dimension is either a draw or framed from the wrong angle.
- **JSON-LD drift**: A page ships with `datePublished: 2026-05-12, dateModified: 2026-05-12` but is rewritten 30 days later. The meta description is updated, the narrative is updated, but the JSON-LD is not. Grep `dateModified` separately from the verdict count. The skill's JSON-LD pitfall already covers this for the dates; the verdict strings inside JSON-LD are a separate audit.
- **Card "X wins on Y and Z" with no count**: The card uses prose framing without a number ("Koog wins on accessibility and operational maturity"). If the article says "0 Koog wins", the card is contradicting the article. Either the article's count is wrong (re-derive from table) or the card is over-claiming (reframe as a draw or remove).

## When to run this audit

- After the user reports a stale verdict count on any comparison page.
- After rewriting any comparison page's verdict (Step 4 of the parent SKILL.md). The verdict-block update is one part of the rewrite; the hub card is a separate edit.
- Before declaring a page complete. Same principle as the hedge-phrase audit: this is a pre-declare-complete gate, not a post-write review.
- When a FINAL-report version bumps (v2 → v3, etc.) — version bumps are when verdict counts change. Sweep the page and the hub card before shipping the new version.
