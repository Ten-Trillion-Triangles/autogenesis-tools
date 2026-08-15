---
name: ttt-site-hero-images
description: "Generate, audit, optimize, and wire a hero image into a ttt-site blog post end-to-end. Triggers on 'generate a hero image for the blog post', 'wire up the hero image', 'create hero for /blog/<slug>', 'the post needs a hero', 'make an image for the new blog', 'ship the hero for X'. Covers the mmx image generate invocation, the audit (does it match the existing visual family?), the PNG-to-WebP optimization step, the frontmatter image field patch, the public/assets/blog/ file placement, the alt-text wiring in BlogPost.astro, and the npm run build verification. NOT for hero prompts alone (use image-prompt-craft), NOT for blog writing itself (use ttt-site-blog), NOT for comparing visual alternatives (use vision_analyze directly)."
metadata:
  hermes:
    tags: [hero-image, image-generation, mmx, blog-post, ttt-site, webp-optimization, alt-text]
    category: software-development
---

# ttt-site hero images — generate, wire, ship

The complete workflow for getting a hero image from "I want one" to "shipped in production." The hero image is a class of artifact on ttt-site with its own conventions, files, and verification steps — most of which are scattered across `image-prompt-craft`, `ttt-site-blog`, and one buried pitfall in `ttt-site-blog`. This umbrella consolidates them.

## When to load this skill

- The user says "generate a hero image" + a blog post slug
- The user says "wire up the hero image" / "wire this post together" / "ship the hero"
- The user says "the post needs a hero" and you have to figure out what's missing
- A blog post frontmatter has an `image:` field but the file does not exist at `public/assets/blog/<slug>-hero.*`
- You need to audit a generated image against the existing hero family

## The full workflow (one shot, top to bottom)

### Step 1 — Identify the visual family before generating

The existing ttt-site heroes split into two distinct families. Match the family of the post you are wiring — do not introduce a third style.

**Pipe schematic family** (most heroes in `public/assets/blog/`):
- Deep matte navy background `#0B1A2A` with radial vignette
- Flat two-tone shaded cast-iron pipes (steel teal `#4A8AA0` lighter face, deep slate teal `#2E5A6E` underside)
- Pipes trace abstract letterforms / pictograms on close inspection
- Small white triangular arrowheads `#F2F5F7` thread through pipe interiors
- Tiny white and pale-gray circular nodes at junctions
- Generous top/bottom negative space
- No people, no circuit boards, no robots, no neon, no legible text labels
- Mood: calm, infrastructure-grade, "1932 water authority schematic that was never replaced"
- Examples: `tpipe-blog1-hero.png`, `pumpstation-runtime-harness-hero.png`, `killswitch-explained-hero.png`, `python-iceberg-hero.png`, `agent-substrate-hero.png`

**Comparison diagram family** (only for explicit comparison posts):
- Dark dot-grid background, near-black
- Hub-and-spoke / radial composition with protagonist at center
- Neon accent colors per competitor (orange, purple, pink, yellow)
- Haloed central card, hard-edged rectangular competitor frames
- Punchy declarative tagline at the bottom in white
- Examples: `2026-06-27-contextbank-vs-memory-bank-hero.png`, `2026-06-26-contextbank-vs-vector-databases-hero.webp`

Use vision_analyze on an existing shipped hero first to lock the family before prompting. Do not trust memory.

### Step 2 — Draft the prompt

Open `templates/hero-image-prompt.md` (or use the structural skeleton below). One paragraph. Paste-ready. No "What to avoid" section. No preamble. No postamble.

```
Wide horizontal 16:9 banner in the dark industrial style of a [SCHEMATIC TYPE]: [PALETTE: dark navy + steel teal + white], foreground composed entirely of [METAPHOR: cast-iron pipes / municipal gauges / industrial apparatus] tracing [FLOW DIRECTION] with [COMPOSITION DETAIL], [ACCENT: small white arrowheads / circular nodes / chrome dial], generous negative space top and bottom, no people, no circuit boards, no robots, no fantasy, no neon, no legible technical text, the mood [MOOD: calm and infrastructure-grade like a 1932 water authority schematic that was never replaced].
```

For pipe-family heroes specifically, the `image-prompt-craft` skill carries the full pitfall warning: **image models cannot reliably render legible text labels.** Do not depend on the image to display "VECTOR DB" or "JVM" — describe architectural elements (a tall brass instrument, a massive cast-iron reservoir) and let alt-text handle the verbal layer.

### Step 3 — Generate with mmx

```bash
# mmx binary location (linuxbrew); adjust if different on your machine
MMX=/home/linuxbrew/.linuxbrew/bin/mmx

# Verify auth and install first if needed
[ -x "$MMX" ] || npm install -g mmx-cli
"$MMX" auth status

# Generate — the 16:9 aspect ratio matches ttt-site's hero card width
"$MMX" image generate \
  --prompt "$PROMPT" \
  --aspect-ratio 16:9 \
  --n 1 \
  --prompt-optimizer \
  --out-dir /home/cage/Desktop/Workspaces/ttt-site/public/assets/blog \
  --out-prefix "$SLUG-hero"
```

**mmx-cli flag pitfalls** (verified 2026-07-01):

- `--yes` is documented as a boolean in the bundled `mmx-cli` skill but the binary rejects it as `Error: Flag --yes requires a value.` As of mmx-cli 1.0.16 there is no working `--yes` flag for non-interactive skipping — confirmation prompts gate on TTY detection, not on a flag. Workaround: ensure the call runs from a non-TTY context (Hermes `execute_code` sandbox is non-TTY by default) and let `--output json` capture whatever decision a prompt makes.
- The bundled `mmx-cli` skill (under `mmx-cli/`) is a thin duplicate of the unbundled `minimax-cli` skill. Prefer `minimax-cli` for detailed usage (it has `references/` and `scripts/`, including `cache_probe.py`). The bundled one ships in the default install.
- `--out-dir` + `--out-prefix` produces `<prefix>_001.jpg` files. Use a stable prefix matching the blog slug: `<slug>-hero` so file renames follow naming conventions.
- `--prompt-optimizer` rewrites the prompt before generation. Generally produces cleaner outputs; if you need exact prompt fidelity, drop it.

### Step 4 — Audit the generated image

Always vision_analyze the output before deciding to ship. The audit questions live in `references/audit-prompts.md`.

Five-question audit:

1. **Palette match** — does it match the target family (navy + steel teal + white for pipe family; dark dot-grid + neon accents for comparison family)?
2. **Composition** — 16:9 banner? Generous top/bottom negative space? Left-to-right flow if pipe family?
3. **No obvious flaws** — garbled labels, melted geometry, people, neon where it should not be, text rendered incorrectly?
4. **Specificity** — does the metaphor carry the architectural meaning, or is it generic ("industrial pipes" that could illustrate anything)? A "C+ usable" verdict per the `image-prompt-craft` skill means it matches the family but lacks post-specific signal.
5. **Crisp at small sizes** — the rendered hero card is typically 1200x630 (OG image) and 800x450 (in-post hero). Will the metaphor still read at thumbnail size?

Honest verdict on every audit. If the result is C+ generic but on-family, surface it to the user with a "ship it / regenerate with X hook / reuse existing hero" choice. Do not silently ship a mediocre image and do not pretend the audit was clean.

### Step 5 — Optimize PNG/JPG to WebP if the source is > 1MB

The `humanizer` skill's pre-launch checklist flags hero images > 1MB as needing WebP for mobile. The `ttt-site-blog` "Hero image wiring is incomplete" pitfall specifies the exact ffmpeg recipe:

```bash
# Skip this step if the generated source is already small (< 500KB); .jpg/.png both work
ffmpeg -y -i public/assets/blog/<slug>-hero_001.jpg \
  -c:v libwebp -q:v 82 -lossless 0 \
  public/assets/blog/<slug>-hero.webp
```

Typical savings: 8-12x reduction without visible loss. Ship the `.webp` as primary, keep the original as fallback.

### Step 6 — Place files and patch frontmatter

File naming convention (already established across the blog):
- `<slug>-hero.webp` (primary, ship this)
- `<slug>-hero.png` (fallback / source-of-truth, for browsers without WebP)

Frontmatter patch — example for a post that does not have an `image:` field yet:

```yaml
---
title: "..."
description: "..."
author: "Richard Wang"
publishDate: 2026-07-01
updatedDate: 2026-07-01
image: "/assets/blog/<slug>-hero.webp"   # <-- ADD THIS LINE
tags: [...]
---
```

Frontmatter schema (`src/content.config.ts`) accepts `image: z.string().optional()`. The Astro `BlogLayout.astro` passes `image` through to `BaseLayout.astro` which sets `og:image`, `og:image:width` (1200), `og:image:height` (630) for social card crawlers.

### Step 7 — Wire alt-text

The piece that gets skipped. Without this, the `<img>` element gets generic alt text and accessibility/SEO suffers.

Alt-text wiring lives in `src/components/blog/BlogPost.astro`. The current implementation has a ternary chain:

```typescript
const altText = image?.includes('memory-system-hero') ? '...'
  : image?.includes('reasoning-pipes-explained-hero') ? '...'
  : image?.includes('pumpstation-runtime-harness-hero') ? '...'
  : ... : 'TPipe blog post hero';
```

The check uses `image.includes('filename-prefix')` which matches both `.webp` and `.png` (they share the prefix) — so the alt-text wires up automatically when the frontmatter switches extensions.

Before adding the alt-text case, check whether the slug's hero-prefix already matches an existing case. If yes, you are done — the frontmatter switch is enough. If no, add a specific ternary case for the new prefix.

If the vision_analyze audit flagged the image as good (specific, on-family), write the alt-text from the vision audit's description. If the vision tool cannot read the image (oversized, 413 error, no vision budget), fall back to the prompt itself — write a faithful alt-text against the prompt's described content, not a generic placeholder.

### Step 8 — Build verify

```bash
cd /home/cage/Desktop/Workspaces/ttt-site
npm run build
```

Must exit 0. Common failure modes after a hero wire-up:
- YAML frontmatter indentation drift (any field under `faqItems[]` or `howToSteps[]` at the wrong indent → silent 404 on the post)
- Image path typo (`image: /assets/blog/<slug>-hero.webp` not `/.../<slug>-hero_001.webp`)
- WebP file not actually written (the ffmpeg recipe exits 0 but produces a 0-byte file if the source path is wrong)

Do not declare done until `npm run build` exits 0. The skill-rule "do not impose human bandwidth limits on agent output" cuts the other way here — shipping without a build verify is a launch blocker per the `humanizer` pre-launch checklist.

### Step 9 — Post-render checks (sitemap + llms.txt)

Not hero-specific but always runs after any post change:

```bash
# 1. Image serves correctly
curl -sS -o /dev/null -w "WebP HTTP %{http_code} size=%{size_download}\n" \
  http://127.0.0.1:4321/assets/blog/<slug>-hero.webp

# 2. Post page returns 200
curl -sS -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:4321/blog/<slug>/

# 3. Sitemap reflects the slug (auto-generated from getCollection('blog'))
curl -s http://localhost:4321/sitemap.xml | grep "<slug>"

# 4. llms.txt drift audit — every published post in src/content/blog/ must appear
#    in the ## Blog section in reverse-chronological order. The dev server hot-
#    reloads public/ so this is the only post-render file edit that may be needed.
#
#    Drift audit:
#      - Posts in src/content/blog/*.md  (the source of truth)
#      - Entries in public/llms.txt ## Blog section  (hand-maintained)
#    If a post is in src but not in llms.txt, add an entry in the file's existing
#    format: `- [Title](URL): DESCRIPTION.`  Description voice matches the file's
#    other entries. Order reverse-chronological.
#
#    Verified 2026-07-01: llms.txt was 4 posts behind src/content/blog/ (06-22,
#    06-26, 06-27, 06-30). The dev server serves the live file from public/, so
#    the post-edit /llms.txt grep confirms the drift is closed.
```

`public/robots.txt` blanket `Allow: /` means crawlers auto-see the new hero via the post URL — no robots.txt edit needed. `src/pages/sitemap.xml.ts` auto-generates from the blog collection — no sitemap edit needed. Only `public/llms.txt` is hand-maintained and drift-prone. See the `ttt-site-blog` "Publishing & crawler visibility" section for the full inventory (which files need touching on which events) and the "llms.txt drift correction is NOT a publish event" pitfall for what NOT to do during a drift correction (don't bump `updatedDate`, don't re-run the full publish checklist, don't touch `robots.txt` or `sitemap.xml` — those are auto-handled).

## Pitfalls

### "Hero image wiring is incomplete" — the full workflow trap

The pitfall in `ttt-site-blog/SKILL.md` lists 5 wire-up steps but treats them as one bullet. Most sessions skip step 7 (alt-text ternary case in BlogPost.astro) because the dev server returns 200 without it. The user has caught this and pushed back. The alt-text patch is required, not optional. Read the full step 7 above.

### Generated image is "C+ usable but generic"

mmx `image-01` produces a clean image matching the family, but lacks post-specific metaphor signal. The hero could headline water utilities, DevOps pipelines, or industrial IoT — anything. This is the common outcome when the prompt uses a generic metaphor ("pipes tracing through") without anchoring to a post-specific concept ("a brass pressure gauge in the upper-right foreground with a chrome needle pointing into the green band suggesting cold-start timing" — the latter ties the metaphor to the JVM-native-runtime post).

When this happens: surface the audit honestly, present 3 paths (ship / regenerate with specific hook / reuse existing hero), let the user pick. Do not silently ship C+. The `image-prompt-craft` skill's audit-and-iterate workflow covers this; the missing piece is the wire-up side.

### Source content is research notes, not a published draft

When the upstream blog content is a working notes file (verification tables, BLOCKER sections, "WAIT for user" closer), do not auto-humanize it before generating the hero. The research notes might flag that the published post has ground-truth drift (sub-100ms cold-start numbers claimed but unmeasured; mobile/embedded claim overstated; tier availability framing wrong). Generating a hero from the wrong architectural claim bakes the error into imagery.

Order of operations:

1. Read the research notes first (if they exist alongside the post in `blog-research/`).
2. Check for ground-truth drift against the post.
3. If drift exists, flag to user before generating the hero — the hero's metaphor will lock in whatever the post says, and the post might say the wrong thing.
4. Generate the hero only after ground-truth is verified.

This is the same insight as the `humanizer` skill's "Research notes are NOT blog drafts" patch (2026-07-01) — applied to hero work.

### Image models cannot render legible technical text labels

Verified 2026-06-26 on the ContextBank vs Vector Databases hero. The image model rendered garbled labels like "brzdelenski" instead of "VECTOR DB" on first render, dropped labels entirely on second. Do not depend on the image to display readable text labels for named components.

When prompting: describe architectural elements ("a tall brass precision instrument with chrome dials," "a massive cast-iron municipal reservoir with weighted glass bottles in amber fluid," "a red-painted gate-valve wheel"). Describe visual style ("industrial brutalism, machinist precision, emerald and signal red accents on black"). Do not depend on the model to render labels.

If the user asks for a labeled hero, surface this constraint before generating. The visual metaphor carries the architectural meaning; alt-text handles the verbal layer for screen readers and SEO.

### File extensions — `.webp` vs `.png` vs `.jpg`

mmx `--out-dir` produces `_001.jpg` by default. The ttt-site convention is `.webp` primary + `.png` fallback. After ffmpeg conversion:

- Verify both files exist: `ls -la public/assets/blog/<slug>-hero.*`
- Frontmatter `image:` field points at `.webp` (smaller, modern browsers)
- The `BlogPost.astro` ternary match uses `image.includes('<prefix>-hero')` which catches both extensions automatically

If you only ship `.jpg` (skipping the WebP step), the file will load fine but mobile users will pay the larger payload. The `humanizer` pre-launch checklist flags PNGs > 1MB as needing WebP — applied to JPGs the same threshold makes sense.

### Do not reuse an existing hero across multiple posts

Each post gets its own hero. Reusing `tpipe-blog1-hero.png` for a different post reads as "the marketing team forgot to ship the right image." The audit on the published post will catch this — Apex reads the OG image tag on social cards.

If the audit reveals the existing heroes do not fit the post topic (e.g., a "Reasoning Pipes" post landing before the pipe-family was established), generate a new one. The wire-up cost is ~3 minutes once you have the recipe.

## See also

- `image-prompt-craft` — the prompt structure + label limitation + dark-industrial aesthetic. Use this to draft the prompt; use this umbrella to wire it.
- `ttt-site-blog` — the blog-writing side. Has the buried "Hero image wiring is incomplete" pitfall (5 steps listed inline) — this umbrella extracts and details those steps.
- `humanizer` — pre-launch checklist flags hero images > 1MB as needing WebP; the audit-table family for visual review.
- `minimax-cli` (preferred over `mmx-cli` for detail) — the mmx CLI reference with `references/vision-vs-browser-vision.md` for when to prefer mmx vision describe over built-in vision_analyze on dense dark-theme screenshots.
- `references/audit-prompts.md` — the exact audit questions to ask vision_analyze on a generated hero.
- `templates/hero-image-prompt.md` — paste-ready structural skeleton for the prompt itself.
- `scripts/optimize-hero.sh` — one-shot PNG/JPG to WebP + verify recipe.