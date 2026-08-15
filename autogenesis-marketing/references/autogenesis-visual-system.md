# Autogenesis Landing Page — Canonical Visual System

This is the **visual system for the Autogenesis landing page**. Load this file when generating any new HTML mock for the Autogenesis landing page — either re-skinning an existing mock or producing a fresh one from a content brief. The system preserves the original deep-navy / electric-blue palette and the `Space Grotesk + Inter + JetBrains Mono` font stack. Do not introduce a new color, a new font, a new spacing scale, or a new grid without operator approval.

**The load-bearing rule:** when generating a mock, copy the existing `<style>` block verbatim from `ttt-site/autogenesis-landing-mock.html` (or any prior approved mock) into the new file. Then write body markup using ONLY the existing CSS classes. Add new classes only if the new mock requires layout not present in the original. If you find yourself writing `style="..."` more than twice in a single section, you are bypassing the CSS and breaking the visual system. The operator will catch it.

## Color variables

| Variable | Value | Use |
|---|---|---|
| `--bg` | `#070b16` | Page background (deep navy) |
| `--bg-2` | `#0c1224` | Card / frame background (slightly lighter navy) |
| `--bg-3` | `#131b32` | Inner card / stat-block background |
| `--border` | `#1c2542` | Subtle dividers, frame borders |
| `--border-bright` | `#2a3a64` | Frame borders, hero-frame chrome |
| `--text` | `#e6e8ef` | Primary text (off-white) |
| `--text-2` | `#9aa3b8` | Secondary text (muted blue-gray) |
| `--text-3` | `#5b6580` | Tertiary text (further muted) |
| `--accent` | `#3b82f6` | Electric blue (used SPARINGLY) |
| `--accent-2` | `#2563eb` | Accent hover state |
| `--accent-soft` | `rgba(59, 130, 246, 0.12)` | Accent tinted backgrounds |
| `--cyan` | `#22d3ee` | Decorative (rare) |
| `--green` | `#10b981` | Success states (e.g. "live" tag dot) |
| `--amber` | `#f59e0b` | Decorative (rare) |
| `--magenta` | `#d946ef` | Decorative (rare) |
| `--red` | `#ef4444` | Recording dot, alerts |
| `--orange` | `#f97316` | Decorative (rare) |
| `--studio` | `#f87171` | Brand-link accent (footer) |

**The accent rule:** the operator (2026-08-12) caught the v2 mock for overusing accent color. The pattern that works: `color: var(--accent)` is reserved for `<span class="accent">` words inside `<h1>`, `<h2>`, and `<h3>` headlines. NEVER on full `<p>` elements. NEVER on `<button>` text (the primary button is already accent-blue by class). The original mock's headline structure is:

```html
<h1>Your imagination is <br/>the action <span class="accent">menu.</span></h1>
```

The accent word is the LAST word in the headline. The break before it lets the accent read as the punchline. Use this pattern for any new headline.

## Font stack

| Variable | Stack | Use |
|---|---|---|
| `--font-display` | `'Space Grotesk', system-ui, sans-serif` | Headlines, display text (h1, h2, h3, .trust-name) |
| `--font-body` | `'Inter', system-ui, sans-serif` | Body copy, paragraphs, buttons |
| `--font-mono` | `'JetBrains Mono', ui-monospace, monospace` | Section eyebrows, tags, frame chrome text, "DRAFT" watermark |

Load all three via the Google Fonts link in `<head>`:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

## Hero structure

```html
<section class="hero">
  <div class="wrap">
    <div class="hero-grid">
      <div>
        <div class="tag"><span class="dot"></span>A four-player narrative board game</div>
        <h1>Your headline<br/>with <span class="accent">accent word.</span></h1>
        <p class="lede">First paragraph — intro to the product.</p>
        <p class="lede-final">Second paragraph — punch line or italic close.</p>
        <div class="hero-actions">
          <a href="#" class="btn btn-primary">Play in Browser</a>
          <a href="#turn" class="btn">Watch a Turn</a>
        </div>
      </div>
      <div class="hero-frame">
        <div class="frame-bar">
          <span class="rec"><span class="rec-dot"></span>LIVE · COMMANDER INPUT</span>
          <span>NORTHERN THEATER</span>
        </div>
        <video autoplay loop muted playsinline>
          <source src="./public/gifs-final/01-map-typing.webm" type="video/webm" />
          <source src="./public/gifs-final/01-map-typing.mp4" type="video/mp4" />
        </video>
      </div>
    </div>
  </div>
</section>
```

**The hero rhythm:** `tag → h1 (with accent) → lede (1 short paragraph) → lede-final (1 short paragraph) → hero-actions (2 buttons)`. The original mock kept this to 3 short paragraphs total. The v2 mock that broke was 5+ paragraphs. Do not exceed 3 short paragraphs in the hero. If you have more canonical copy, distribute it across body sections.

**The hero-grid layout:** 1.05fr / 1fr (left column copy slightly wider than right column video). The grid gap is 56px. The hero section padding is 96px top, 64px bottom. The `.wrap` max-width is 1240px with 32px horizontal padding.

## Section structure (the canonical body rhythm)

```html
<section id="<anchor>" class="<section-class>">
  <div class="wrap">
    <div class="section-head">
      <p class="section-eyebrow">Consequence</p>
      <h2>What you write comes back.</h2>
      <p class="section-body">Lead paragraph — the section's main idea, one continuous block.</p>
    </div>
    <p class="section-body">Supporting paragraph — one additional beat if needed.</p>
    <p class="section-body" style="margin-top: 18px;"><strong style="color: var(--text);">Bold close — the section's punchline or one-line summary.</strong></p>
  </div>
</section>
```

**The section rhythm:** `.section-head` (max-width 720px, margin-bottom 64px) contains the `.section-eyebrow` (mono font, blue accent, 11.5px), the `<h2>` (Space Grotesk 32-52px clamp), and one lead paragraph. Then 1-2 supporting paragraphs below, with `margin-top: 18px` between them. Bold close if applicable, using `<strong style="color: var(--text);">` to keep the white text but emphasize weight.

**The five-state turn section is special.** It uses a `.turn-row` grid (200px / 1.4fr / 1fr) with a `.turn-num` (mono font, large step number), a `.turn-clip` (video frame with chrome), and a `.turn-state` + `.turn-desc` block. The five rows are: DECLARE, PLAN, RESOLVE, NARRATE, UPDATE. Each row uses the same 1280×652 video from `public/gifs-final/`.

## Section ordering (canonical sequence)

The v10 canonical copy establishes this order:

1. **Hero** — premise + sub + closer + reel
2. **Consequence** (`id="consequence"`) — "What you write comes back" + king-of-England + prophet + ruler-returns
3. **The Living World** (`id="world"`) — operator-verbatim "they spring to life" + NPCs-take-their-own-turns + world-remembers + world-evolves
4. **A Turn** (`id="turn"`) — "A turn is what the world does" + five-state pipeline (Declare / Plan / Resolve / Narrate / Update) + verb catalogue + sometimes-the-fit-rewrites-the-rules close
5. **The Premise** (`id="premise"`) — "Anything you can imagine. The game builds around it." + cause-and-effect clause + "The action you write is the only limit. The game has none."
6. **Commander** (`id="commander"`) — "The game starts with a character sheet" + four-commanders mock (Lord Maple Tree, Officer Dave, Zuzusarogorata, Talya) on the right
7. **Studio** (`id="studio"`) — "A game by Ten Trillion Triangles" + "the game that ate their own benchmark"

The nav links match the section IDs: `Consequence`, `The World`, `A Turn`, `The Premise`, `Commander`. The nav also has a `Studio` ghost button (anchor `#studio`) and a `Play` primary button (anchor `#` or `/play`).

## Section class names

The CSS uses these class names for the section divider line that runs above each section. Use them verbatim:

| Class | Used on | Style |
|---|---|---|
| `.turn-section` | Consequence, A Turn, The Premise | 1px border-top with `--border` color |
| `.world-section` | The Living World | Same |
| `.commander-section` | Commander | Same |
| `.trust` | Studio | Different — gradient background from `--bg-2` to `--bg` |

The `.turn-section` / `.world-section` / `.commander-section` classes all share the same border-top treatment. The original had this visual rhythm: hero → bordered section → bordered section → bordered section → bordered section → bordered section → trust band. Reproduce that rhythm.

## Commander section (special layout)

```html
<section id="commander" class="commander-section">
  <div class="wrap">
    <div class="section-head">
      <p class="section-eyebrow">Commander</p>
      <h2>The game starts with a character sheet.</h2>
      <p class="section-body">The first move is to invent yourself.</p>
    </div>
    <div class="commander-grid">
      <div class="commander-text">
        <p>Body paragraphs about commander creation.</p>
      </div>
      <div class="sheet">
        <h3>Commander · Lord Maple Tree</h3>
        <div class="field">
          <label class="field-label">Powers &amp; Abilities</label>
          <textarea class="field-textarea" readonly>Powers text here</textarea>
        </div>
        <div class="field">
          <label class="field-label">Nation of Origin</label>
          <textarea class="field-textarea" readonly>Nation text here</textarea>
        </div>
        <div class="examples">
          <div class="examples-label">Other commanders from this match</div>
          <div class="example"><strong>Name</strong> — one-line description.</div>
        </div>
      </div>
    </div>
  </div>
</section>
```

The `.commander-grid` is 1fr / 1.05fr (text left, character sheet right). The `.sheet` is a navy box with a "DRAFT" watermark in the top-right corner (the original had this; it's a tactile detail).

**Remove the "DRAFT" watermark** — the operator flagged this as a leftover from when the mock was a draft, not a final. The character sheet is canon (Lord Maple Tree, Officer Dave, Zuzusarogorata, Talya are the operator's own commanders), not a draft.

## Studio section

```html
<section id="studio" class="trust">
  <div class="trust-inner">
    <p class="trust-by">A game by</p>
    <h3 class="trust-name"><a href="/company">Ten Trillion Triangles ↗</a></h3>
    <p class="trust-desc">Three developers. The people who published their AI benchmarks open-source so the rest of the field could finally see the real numbers. Autogenesis is the game that ate their own benchmark.</p>
  </div>
</section>
```

The `.trust` class applies a gradient background (`linear-gradient(180deg, var(--bg-2), var(--bg))`) and reduced padding (80px vertical). The text is centered. The studio brand link is `--studio` color (`#f87171`).

**Remove the corporate proof pills.** The original mock had `<span>AWS Premier Partner</span> <span>Co-sell · Clazar</span> <span>AI Whitepapers · Avahi</span> <span>Open-source Benchmarks</span>` as `.proofs` row. The operator removed these — they're corporate boilerplate that belongs on the company page, not the game landing. Replace with the single-line "Ten Trillion Triangles" + the "game that ate their own benchmark" copy.

## Footer

```html
<footer>
  <div class="footer-inner">
    <div>© 2026 Ten Trillion Triangles · Autogenesis</div>
    <div class="footer-links">
      <a href="/company">Studio</a>
      <a href="/case-studies/avahi">Case Study</a>
      <a href="/privacy">Privacy</a>
      <a href="/terms">Terms</a>
      <a href="https://github.com/ten-trillion-triangles">GitHub ↗</a>
    </div>
  </div>
</footer>
```

The `.footer-inner` is a flex row with `justify-content: space-between`. The footer is centered text on the deep-navy background with `--text-3` color. No section padding override needed.

## Asset references

All video assets live in `public/gifs-final/`. The canonical asset set is five files in three formats (gif / mp4 / webm):

| File | Beat | Used in |
|---|---|---|
| `01-map-typing.{gif,mp4,webm}` | Player types action | Hero frame |
| `02-agent-stream.{gif,mp4,webm}` | AI work stream scrolls | A Turn "RESOLVE" row (background b-roll) |
| `03-agent-planning.{gif,mp4,webm}` | Agent planning spinner | A Turn "PLAN" row |
| `04-narrative-reveal.{gif,mp4,webm}` | Generated prose fills | A Turn "NARRATE" row |
| `06-world-update.{gif,mp4,webm}` | World state updating | A Turn "UPDATE" row |

Use the `.webm` source first, `.mp4` as fallback, `.gif` as final fallback. The HTML pattern is:
```html
<video autoplay loop muted playsinline>
  <source src="./public/gifs-final/01-map-typing.webm" type="video/webm" />
  <source src="./public/gifs-final/01-map-typing.mp4" type="video/mp4" />
</video>
```

## What to REMOVE from a new mock (operator-confirmed removals)

These are leftover artifacts from earlier drafts that the operator explicitly rejected:

- **The "DRAFT" watermark on the character sheet mock** — character sheets are canon (Lord Maple Tree, Officer Dave, Zuzusarogorata, Talya are the operator's own commanders), not drafts.
- **The "AWS Premier Partner / Co-sell · Clazar / AI Whitepapers · Avahi / Open-source Benchmarks" trust pills** — corporate boilerplate that belongs on `/company`, not the game landing.
- **The "PvP board game with no menu of moves" hero framing** — the operator rejected this as the category-description opener. The hero leads with the operator's verbatim interview quote instead.
- **The 4-promise "no two games are ever the same" closer ("Four players. Twenty-five rounds. One shared world. No two games are ever the same.")** — three numbers and an abstraction. The operator rejected this. The hero closer is the imperative pair "You write the moves. The world writes the consequences. Every turn, the board records what happened. The next player has to deal with it."
- **The "One turn · five states" tagline as a section header** — the operator rejected this as too SaaS. The Section 4 header is now "A Turn" and the headline copy is "A turn is what the world does with what you wrote."
- **The "The rest is hidden" commander-section opener** — operator rejected as implying the game has secrets. The replacement is "the rest is assigned by the system."

## What to ADD when generating a new mock

If the new mock requires a layout not in the original, add new CSS classes to the `<style>` block. Common additions:

- A new section class (e.g. `.reviews-section` for a customer-quotes section) — follow the pattern of existing section classes (`<section class="X-section">` with 1px border-top).
- A new tag/badge style — follow the pattern of `.tag` (rounded, mono font, 11-12px, 16% letter-spacing).
- A new grid — use the existing 1.05fr / 1fr hero-grid pattern as a template, or 200px / 1.4fr / 1fr turn-row pattern.

DO NOT add:
- A new color (extend the variable system instead — if a new color is needed, propose it to the operator first)
- A new font (the Space Grotesk + Inter + JetBrains Mono stack is the brand)
- A new spacing scale (the 96px / 112px / 80px / 32px section padding system is the brand)

## Worked example: v2 mock fix

The v2 mock broke the visual system in three ways. The fix:

1. **Hero copy stuffed with 5 paragraphs → restored to 3.** The original mock's hero: tag + h1 (line break + accent word) + lede + lede-final + hero-actions. The v2 mock added: lede-final, lede (imperative), lede (closer), lede-final (closer). Five paragraphs stacked. The fix: keep 3 short paragraphs total. If the canonical copy is longer, push it to body sections.

2. **`color: var(--accent)` on whole paragraphs → restored to `<span class="accent">` on headline words only.** The v2 mock applied accent-blue to two full paragraphs: the imperative closer (`You write the moves...`) and the section 2 lead. The original uses accent-blue ONLY on the LAST word of the `<h1>` (and on `.section-eyebrow` text). The fix: remove inline `color: var(--accent)` from paragraphs. Use `<span class="accent">` inside `<h1>` / `<h2>` for the accent word.

3. **Inline styles bypassed the existing CSS rhythm → restored to existing CSS classes.** The v2 mock used `style="font-size: 19px; color: var(--text); font-weight: 500; margin-top: 32px;"` and similar inline overrides. The original uses `.lede`, `.lede-final`, `.section-body`, `.hero-actions` classes for all of this. The fix: when the existing CSS has a class for what you need, USE IT. Inline styles are for one-off tweaks, not for replacing the class system.

## Build verification

After generating a new mock, run the production build to confirm the file is well-formed:

```bash
cd /home/cage/Desktop/Workspaces/ttt-site
npm run build
```

Expect exit code 0, no errors in stderr. The mock is untracked (it doesn't get built into the site bundle unless explicitly added to a page route). The build only checks HTML validity indirectly.

For HTML validity check, verify:
- All `<head>`, `<body>`, `<html>` tags balance (1 open, 1 close each)
- All custom class names exist in the `<style>` block
- All asset paths resolve (`./public/gifs-final/01-map-typing.webm` must exist)
- All `<video>` elements have at least one `<source>` with valid src

## Asset update pattern (operator-supplied additions)

If the operator supplies new commander names, new proof-clip entries, or new turn examples during iteration, update the corresponding section in the mock using the existing class structure. Example workflow for adding a new commander:

1. Add a new `<div class="example">` inside the existing `<div class="examples">` block in the Commander section
2. Use the format: `<strong>Name</strong> — one-line description.`
3. Do not change the `.sheet` character card structure — only the "Other commanders from this match" list grows

If the operator supplies a new proof-clip turn, add it as a new numbered list item inside Section 3's proof-clips cascade, using the existing `<ol>` / `<li>` markup (or the v2-style three-clause paragraph if that's what the operator has been editing toward).

## When in doubt

Default to the original. The original `ttt-site/autogenesis-landing-mock.html` is the source of truth for the visual system. If the operator's request would break the rhythm, ask once before changing the rhythm. The rhythm is the brand.