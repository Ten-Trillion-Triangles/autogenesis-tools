# ttt-site Docs Sync Reference

Created: 2026-06-07
Updated: 2026-06-16 (PumpStation sync + new `superpowers/` section; prevDoc/nextDoc format fix; audit false-positive lesson; null rule + deterministic chaining; YAML escape gotcha)
Updated: 2026-07-13 (Pre-sync audit normalization upgrade — frontmatter-only awk undercounts inline drift; cross-ref mr-manual-craft drift-audit methodology)
Context: TPipe docs are mirrored to the ttt-site marketing/docs Astro project. The canonical script is `scripts/sync-tpipe-docs.cjs`; a legacy `sync_tpipe_docs.py` exists at the repo root but is superseded. This reference captures the gotchas hit in that workflow.

## Paths

| Role | Path |
|------|------|
| TPipe source (canonical) | `/home/cage/Desktop/Workspaces/TPipe/TPipe/docs/` |
| ttt-site destination | `/home/cage/Desktop/Workspaces/ttt-site/src/content/docs/` |
| **Sync script (canonical)** | `/home/cage/Desktop/Workspaces/ttt-site/scripts/sync-tpipe-docs.cjs` |
| **Sync script (deterministic, no-null-in-middle)** | See `templates/sync-tpipe-docs-deterministic.py` |
| Sync script (legacy, superseded) | `/home/cage/Desktop/Workspaces/ttt-site/sync_tpipe_docs.py` |
| ttt-site dev server | `npm run dev` from `ttt-site/` -> `http://localhost:4321` |
| Doc route | `src/pages/docs/[...slug].astro` (dynamic from content collection) |
| Doc section hub | `src/pages/docs/[section].astro` (auto-routes per top-level dir) |
| Doc hub index | `src/pages/docs/index.astro` (HARDCODED section cards — see gotcha #6) |
| Doc sidebar | `src/components/docs/DocSidebar.astro` (HARDCODED `sectionMeta` — see gotcha #6) |
| Content schema | `src/content.config.ts` (glob `**/*.{md,mdx}` from `src/content/docs`) |
| Doc CSS (global) | `src/styles/docs.css` — **loaded as a side-effect import, NOT scoped** |
| Doc layout (scoped) | `src/layouts/DocsLayout.astro` — uses scoped `<style>` |

## Sync Script Behavior (`scripts/sync-tpipe-docs.cjs`)

**This is a full-replace, not incremental.** On every run, the script `rm -rf`s the entire `src/content/docs/` directory and regenerates it from the TPipe source tree. The output is fully derived — never hand-edit the files in `src/content/docs/`, your changes will be wiped on the next sync. To make site-specific changes, edit the sync script or the Astro UI (index.astro, DocSidebar.astro).

For each TPipe doc, the script:
1. Wipes OUTPUT_DIR
2. Walks the TPipe docs tree recursively (skips `maestro/`)
3. For each `.md`:
   - Extracts title from first H1, falls back to H2, then H3, then basename
   - Extracts description from the first paragraph after the first heading
   - Looks up `prevDoc`/`nextDoc` by parsing the **"## Next Steps"** section of every TPipe doc and walking the chain
   - Classifies `docType` by title keywords ("api"/"reference"/"package"/"interface" -> reference; "getting started"/"setup" -> how-to; etc.)
   - Estimates `readingTime` from word count (~200 wpm)
   - Generates the full YAML frontmatter block from scratch
   - Rewrites relative `.md` links to absolute `/docs/...` paths (via a global `basename -> astroPath` lookup built at startup)
   - Writes the combined frontmatter + body to the output path

**Overridable source path:** As of 2026-06-16, the script reads `process.env.TPIPE_DOCS` with the hardcoded `/home/cage/Desktop/Workspaces/TPipe/TPipe/docs` as fallback. To sync from a sparse clone (faster, branch-pinned, doesn't disturb the working TPipe repo):

```bash
cd /tmp && rm -rf tpipe-remote
git clone --depth 1 --filter=blob:none --sparse https://github.com/Ten-Trillion-Triangles/TPipe.git tpipe-remote
cd tpipe-remote && git sparse-checkout set docs
cd /home/cage/Desktop/Workspaces/ttt-site
TPIPE_DOCS=/tmp/tpipe-remote/docs node scripts/sync-tpipe-docs.cjs
```

## Sync Script Quirks and Patches

**Patched 2026-06-07** to handle `.md#anchor` links — original regex `[^)]+\.md` missed anchors. New regex `[^)]+\.md(#[^)]*)?` captures the fragment; resolution logic splits link and anchor, joins after stripping `.md`. See commit changes to `scripts/sync-tpipe-docs.cjs`.

**Patched 2026-06-16 (this session):**
- `SECTION_MAP` and `SECTION_ORDER` gained `comparison` and `superpowers` entries
- Subdirectory handling extended: `superpowers/specs/` is treated like `advanced-concepts/p2p/` (files in the subdir get the parent section, the slug retains the subdir prefix)
- Title extraction falls back H1 -> H2 -> H3 -> basename (3 PumpStation files in TPipe have no H1; fallback is required to give them any title)
- Description extraction now scans only AFTER the first heading, so frontmatter-free files don't pick up table captions as their description
- `TPIPE_DOCS` env var override (above) for syncing from a sparse clone without disturbing the working TPipe repo
- **prevDoc/nextDoc now written in HYPHENATED form** (e.g. `core-concepts-pipe-class`, not `core-concepts/pipe-class`) — see gotcha #10 below
- `buildNextStepsLookup` rewritten to recursively walk the docs tree and store `fullSlug -> fullSlug` (was: basename -> next-slug, which broke when basenames collided across sections and made prev/next values unprefixed)
- `resolveTarget` prefers same-section basename resolution before falling back to the global basename map (a `pipe-class` link from `core-concepts/pipe.md` resolves to `core-concepts/pipe-class`, not `api/pipe`)

**Known script footgun — basename collision in link rewriter:** The `GLOBAL_LOOKUP` map is keyed by basename only. If two files have the same basename across sections (e.g. `advanced-concepts/pipe-context-protocol.md` and `api/pipe-context-protocol.md`), the lookup is last-write-wins — whichever file processes last alphabetically wins. As of 2026-06-16, `api/pipe-context-protocol.md` processes last (sort order: `advanced-concepts/...` < `api/...`), so all basename-only links like `[pipe-context-protocol.md](...)` resolve to `/docs/api/pipe-context-protocol` rather than the conceptual `advanced-concepts/` page. This is a pre-existing bug, not a sync regression — flag in a TPipe PR rather than try to special-case it locally.

**Why the deterministic Python version exists (gotcha #13):** the .cjs script's "## Next Steps" lookup produces orphan docs (no inbound + no outbound link) with `prevDoc: null, nextDoc: null`. The user has been explicit: *"null is not an ok value for anywhere other than the very first doc or the very last one."* The Python script in `templates/` does alphabetical chaining per section, guaranteeing zero in-the-middle nulls. See gotcha #13 below.

## Site Frontmatter Pattern (required for sidebar visibility)

When adding a NEW doc file in `ttt-site/src/content/docs/`, it needs Astro frontmatter — TPipe source has none. Match an existing `api/*.md` for shape:

```yaml
---
title: "GenericOpenAI Pipe Class API"
description: "Short description; strip leading '> 💡 Tip:' if present"
section: "api"
sectionTitle: "API Reference"
docType: "reference"        # or "how-to", "concept"
order: 12                    # numeric — lower = earlier in section
readingTime: "~14 min"
prevDoc: null                # hyphenated slug or null
nextDoc: null                # hyphenated slug or null
hasHowTo: true
hasFAQPage: false
---
```

`order` is unused by the sidebar (which sorts by `nextDoc` chain) but conventional.

## URL Slug Normalization (Astro gotcha)

Astro content collections lowercase the slug in the URL. The file `comparison/TPipe-vs-Apache-Camel-Comparison.md` is served at `/docs/comparison/tpipe-vs-apache-camel-comparison`, **not** the case-preserved form. The sidebar generates lowercase URLs so the visible link works. When smoke-testing URLs, lowercase them.

## TPipe -> ttt-site Audit Workflow

1. **Diff directories**: `ls` both trees. Look for files present in TPipe but missing from ttt-site (e.g. new modules) and files present in ttt-site but no longer in TPipe.
2. **Copy missing files** (preserving TPipe source body — no site frontmatter yet).
3. **Add site frontmatter** to new files using a sibling file as template.
4. **Run sync script**: `python3 sync_tpipe_docs.py` from `ttt-site/`. Re-runs are idempotent.
5. **Boot dev server**: `npm run dev` in `ttt-site/` (background; tail `/tmp/astro-dev.log`).
6. **Smoke-test all URLs**: curl every `/docs/...` page, expect 200. Lowercase the slug.
7. **Audit in-content links**: extract `<a href>` from `<article>` blocks; verify each target returns 200 and (if anchored) the `#id` exists on the target page.
8. **Visual walk**: navigate each page in browser, check sidebar, TOC, prev/next, code blocks, mermaid renders.
9. **Mobile audit** with Playwright at iPhone 12 (390) and Android (360) viewports — see CSS pitfall below.

## Broken Link Found and Fixed (2026-06-07)

`TPipe/TPipe/docs/core-concepts/merged-pcp-json-output.md` line 295 had a sibling-link `[Pipe Context Protocol Overview](pipe-context-protocol.md)` pointing to a non-existent file. Rerouted to `/docs/advanced-concepts/pipe-context-protocol` in BOTH the TPipe source and the ttt-site file (the sync would re-break the ttt-site fix otherwise). Real-world "broken since origin" link — the sync script faithfully copied the bug.

## Home Page Dead Anchor

Nav and footer at `ttt-site/src/components/layout/{Navigation,Footer}.astro` link to `/#features`. The home page section `<section class="features">` in `src/components/features/Features.astro` had no `id` — anchor was dead. Fixed by adding `id="features"`.

## Mobile Responsive Pitfalls in `src/styles/docs.css`

The CSS file is loaded via `import '../../styles/docs.css'` in `[...slug].astro` as a side-effect import — meaning **NO Astro scoping**. The file's selectors must be plain CSS. If you find yourself writing `:global(table)` here, stop — it becomes a literal `:global(table)` selector and matches nothing.

After a 154-check mobile audit, the following CSS was needed and applied (see `src/styles/docs.css` for current state):

| Selector | Why |
|----------|-----|
| `h2, h3, h4, h5, h6` | Long unbreakable method names in h4 (`hasContextOverflowProtectionConfigured(): Boolean`) overflow at 390px |
| `p, li` | URLs and code identifiers in body text can overflow |
| `a` | Same — long anchor text in body |
| `th, td` | Long method-name cells in tables (Junction DSL tables) |
| `table` | `display: block; overflow-x: auto;` so the table itself scrolls horizontally instead of widening its parent |
| `.doc-title` | The 2.5rem page title can overflow on long single-word titles (e.g. "MultimodalContent Class API") |
| `.doc-content, .doc-body` | `min-width: 0` for flex safety in the docs layout |

Also: `min-width: 0` on `.doc-content` and `.doc-body` in `DocsLayout.astro`'s scoped style — the dynamic route's `main.docs-content` is `display: flex; min-width: 0;` but the inner doc-content and doc-body need it too or tables can still push past.

## Reusable Audit Script Skeleton

The Playwright mobile audit pattern is worth keeping. Drop a `.mjs` next to `package.json` (then delete) with:

```js
import { chromium } from "playwright";
const viewports = [
  { name: "iPhone 12", width: 390, height: 844 },
  { name: "Android",   width: 360, height: 800 },
];
const docs = [...]; // build with glob or pass array
const browser = await chromium.launch();
const problems = [];
for (const vp of viewports) {
  const ctx = await browser.newContext({ viewport: vp });
  const page = await ctx.newPage();
  for (const path of docs) {
    await page.goto("http://localhost:4321" + path, { waitUntil: "networkidle", timeout: 15000 });
    const m = await page.evaluate(() => ({
      body: document.body.scrollWidth,
      html: document.documentElement.scrollWidth,
    }));
    if (m.html > vp.width + 2) problems.push({ vp: vp.name, path, w: m.html });
  }
  await ctx.close();
}
await browser.close();
```

To inspect a specific element causing overflow: `await page.evaluate(() => { ...})` returning `{offsetW, scrollW, right}` for each element past the viewport right edge. A `<pre>` with `overflow-x: auto` properly clips — its `offsetW` should equal parent width, its `scrollW` can be larger. If `pre.scrollW > pre.offsetW` and `right` of children past viewport, the scroll container is working. The body being wider than viewport means a non-pre element is overflowing.

## Sidebar Order Gotcha

The sidebar (`DocSidebar.astro`) sorts docs by following the `nextDoc` chain from chain-starts (docs with no inbound `nextDoc` pointer). Two distinct chains may exist in one section. For new standalone entry points (no prev/next), use `order: <low number>` to keep them at top of section, but the actual sidebar sort is chain-based — `order` is mostly cosmetic.

## Verification Checklist (per audit session)

- [ ] 77 pages return 200
- [ ] Zero raw `.md` left in ttt-site body (all converted to `/docs/...`)
- [ ] Every in-content link target returns 200; every `#anchor` matches an `id` on the target page
- [ ] Mermaid diagrams render to SVG (count `document.querySelectorAll('svg.mermaid, .mermaid svg').length`)
- [ ] Prev/next chain flows correctly through each section
- [ ] TOC links resolve
- [ ] Home `/#features` anchor lands on the Features section
- [ ] 154 mobile checks (77 pages × 2 viewports) show zero horizontal overflow
- [ ] CamelCase comparison file URL is the lowercase form

## Pre-Sync Content Drift Audit (2026-06-16)

Before running `sync_tpipe_docs.py`, do a fast content-drift sweep so you know what you're shipping. The script will happily overwrite everything; the user wants to know the magnitude of the change first.

### 1. Shallow sparse clone (fast remote mirror)

Cloning the whole TPipe repo is slow. Sparse-checkout `docs/` only:

```bash
cd /tmp && rm -rf tpipe-remote
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/Ten-Trillion-Triangles/TPipe.git tpipe-remote
cd tpipe-remote && git sparse-checkout set docs
```

This pulls only the `docs/` tree in seconds. Use it as the comparison baseline for the steps below.

### 2. File-list diff (find missing + stale)

```bash
find /home/cage/Desktop/Workspaces/ttt-site/src/content/docs -name "*.md" \
  | sed 's|/home/cage/Desktop/Workspaces/ttt-site/src/content/docs/||' | sort > /tmp/local-files.txt
find /tmp/tpipe-remote/docs -name "*.md" \
  | sed 's|/tmp/tpipe-remote/docs/||' | sort > /tmp/remote-files.txt
comm -23 /tmp/remote-files.txt /tmp/local-files.txt   # MISSING locally
comm -13 /tmp/remote-files.txt /tmp/local-files.txt   # STALE (extra locally)
```

The "missing" set is the new-content list. The "stale" set is usually empty (the sync script doesn't leave orphans by design) but check anyway.

### 3. Content drift detection (frontmatter + link-rewrite normalized)

The ttt-site copies have two layers of post-processing that TPipe source doesn't:

1. A 13-line YAML frontmatter block at the top of every file
2. All relative `.md` link references rewritten to absolute `/docs/<slug>` paths by the build

A naive `diff` will report every file as different because of these two layers alone. The awk-only approach below handles layer 1 but misses layer 2 — and as a result, undercounts inline content drift between existing headings (real-world case from 2026-07-13: `core-concepts/killswitch.md` had a +293 char delta with matching H2/H3 heading sets on both sides; the awk-only diff would have flagged it as "sync noise" and missed the inline magic-contract paragraphs the upstream added). Use the Python normalization below instead:

```python
import re
def strip_frontmatter(text):
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            return text[end+4:].lstrip('\n')
    return text

def normalize(text):
    text = strip_frontmatter(text)
    text = re.sub(r'\[([^\]]+)\]\(/docs/([^)]+)\)', r'[\1](../\2)', text)
    text = re.sub(r'\[([^\]]+)\]\(/docs/([^)]+)/\)', r'[\1](../\2)', text)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

Apply `normalize()` to BOTH sides (site copy and remote TPipe copy), then compare. After normalization, files with truly trivial 18-30 line diffs are usually just whitespace drift; files with hundreds of difflines have real upstream changes.

**Heading-set diff as a fast Tier-1 pre-filter** (catches ~85% of content gaps in O(N) time without full-line diff):

```python
def h2_h3(text):
    return sorted(set(re.findall(r'^#{2,3}\s+(.+)$', text, re.MULTILINE)))
```

New H2/H3 headings in the upstream that aren't on the site = new sections to sync. Identical heading sets with non-trivial size delta = inline additions (these need full-line diff to catch — see the 2026-07-13 `killswitch.md` case).

**Tier rules (2026-07-13 calibration, after re-verification):**

| Normalized delta | Classification | Action |
|------------------|---------------|--------|
| < 100 chars | Sync noise (whitespace, comments) | Skip |
| 100 - 1000 chars | Possible inline drift | Sample-dump first 30 lines |
| > 1000 chars | Real content gap | Full diff |
| Identical heading sets but non-zero delta | Inline addition (hidden) | Always sample-dump |

The 200-450 b "sync noise" band that the original awk-only audit used is too coarse — see the canonical drift-audit methodology at `~/.hermes/skills/mr-manual-craft/references/doc-source-drift-audit.md` Pitfall #1 for the worked example.

**Awk-only fallback (if Python isn't available, less accurate):**

```bash
awk 'BEGIN{skip=1} /^---$/{c++; if(c==2){skip=0; next}} !skip{print}' local.md
```

This handles frontmatter stripping but NOT link-rewriting. The diff output will include every shared file's link-rewrites as "changes" — inflate your Tier 3 count and make the report noisier. Use the Python normalization when you can.

A 2026-06-16 sweep found real content drift in every one of the 77 shared files; the standout was `core-concepts/json-and-system-prompts.md` where the remote added an entire **Helper Categories** table breakdown that the local copy didn't have. A 2026-07-13 re-verification (using the Python normalization) found 7 Tier-1 files totaling ~26.6 KB — the same 6 large gaps plus a previously-missed inline addition in `killswitch.md`. Catch these before the sync and you can flag the substantive changes to the user.

### 4. Orphan inbound-link check (for new files)

For each new file in the remote set, check whether any existing remote doc already links to it. New files with zero inbound links are suspect — they may be:

- Design specs that shouldn't be published as routable docs (e.g. the `docs/superpowers/specs/*.md` pattern — internal specs, not user-facing)
- Staged features whose docs were merged before the code
- Genuinely new top-level content the user hasn't seen yet

Resolve every `(.md)` link from every remote doc against its source directory, then check which resolved targets are in the "missing locally" set. A 2026-06-16 audit found that 4 new PumpStation files formed a dense interlink web (16 cross-links between them) and 7 existing files (e.g. `containers/container-overview.md`, `api/tpipe-defaults-package.md`) already pointed at them — so the local site was already half-broken. The 5th new file (`superpowers/specs/2026-06-10-pumpstation-execution-loop-design.md`) was an orphan, which suggested it was an internal design spec that should NOT be published as a routable doc page.

### 5. New top-level section gotcha (the `superpowers/` pattern)

If the new files include a brand-new top-level directory in `TPipe/docs/` that the site has never seen, three Astro files need updates — `src/content.config.ts` is **not** one of them (the glob is recursive and auto-picks up any new subdir), but three hardcoded metadata lists are:

| File | What to add | Why |
|------|-------------|-----|
| `scripts/sync-tpipe-docs.cjs` | New `sectionId: 'Display Name'` to `SECTION_MAP` and `SECTION_ORDER`; subdir handling block in `processFile` (mirror the existing `advanced-concepts/p2p` block) | Without `SECTION_MAP`, the section title in frontmatter becomes the raw slug; without subdir handling, the `mdFiles` list used for `order` numbering is empty and every doc in the subdir gets `order: 1` |
| `src/pages/docs/index.astro` | New `{ sectionId, title, docCount, description, href, icon }` object in the hardcoded `sections` array | The docs hub index is hand-rolled; new sections don't appear in the grid without this |
| `src/components/docs/DocSidebar.astro` | New `'<sectionId>': { title: 'Display Name' }` entry in `sectionMeta` | The sidebar filters via `.filter(s => sectionMeta[s.id])` — sections not in the map are silently dropped from the sidebar |

The dynamic page at `src/pages/docs/[section].astro` auto-generates a per-section index page from the content collection, so the section hub at `/docs/<sectionId>/` works without any route work. **The build will succeed even if you skip the three hardcoded updates** — the doc will be routable, just invisible from the hub and sidebar. Always smoke-test by visiting `/docs/<newSectionId>/` after a sync.

A 2026-06-16 sync added the `superpowers/` section this way (4 entries: 2 in code, 1 in UI). The `superpowers/specs/` subdir follows the same pattern as `advanced-concepts/p2p/`. The previous reference text speculated that `superpowers/specs/*.md` "should NOT be published as a routable doc" — that was wrong for this case. The user wants the PumpStation design spec reachable, so the section is in fact published.

**Stale-branch footgun:** The local TPipe clone at `/home/cage/Desktop/Workspaces/TPipe/TPipe/` may be checked out to a feature branch (e.g. `ABI`) that's behind `main`. As of 2026-06-16, the local was on `ABI` (118 docs after filtering `maestro/`) while GitHub `main` was ahead with the PumpStation merge (82 docs in `main`'s `docs/` tree). If you sync against the local clone's branch, you get the stale state. Two fixes:

1. Use the env var override with a fresh sparse clone of `main` (preferred — doesn't touch the working TPipe repo)
2. Or `cd` into the local TPipe repo and `git fetch origin main && git checkout main` first, then re-run the default-path sync

Either works. The env var override is preferred when you don't want to disturb the user's in-progress TPipe work.

### 6. Link target resolution (the `.md` rewrite trap)

The build's link rewriter uses the regex `[^)]+\.md(#[^)]*)?` to find link targets. The new file may be linked from a doc at a different directory depth, and the rewriter needs to know which subdirectory the file lives in. If the link target is wrong, the rewriter will silently produce a broken `/docs/...` URL.

Always grep for `.md` link references to the new file across the entire `TPipe/docs/` tree before adding it to ttt-site:

```bash
grep -rn "filename.md" /tmp/tpipe-remote/docs/
```

A 2026-06-16 audit caught two upstream bugs in TPipe's own docs this way:
- `core-concepts/merged-pcp-json-output.md` linked to `(/docs/advanced-concepts/pipe-context-protocol)` — absolute URL, no `.md`, never resolved
- `containers/pumpstation.md` linked to `(pipe-context-protocol.md)` — wrong directory, real file is at `advanced-concepts/pipe-context-protocol.md`

Both bugs would have faithfully propagated to ttt-site on sync.

### 7. Local-only content drift (sanity check)

The reverse direction also matters: a local file may have content the remote doesn't. Example: `comparison/TPipe-vs-Apache-Camel-Comparison.md` had a site-specific intro block (Generated date, repo paths, Executive Summary table) on the local copy that was absent in the remote. Deciding whether to keep that on sync (site-specific content worth preserving) or drop it (going with the upstream canonical) is a user decision, not a script decision.

A 22-line size delta with no frontmatter change is the typical signature of a local-only site-specific addition.

**Verification gotcha:** A 2026-06-16 audit flagged this as a real divergence (local had an intro the remote didn't), but on actual re-read of the remote file the intro WAS present — the awk-based frontmatter stripper had a quirk with the `---` horizontal rule that follows the metadata block (different from the YAML frontmatter delimiter), causing the audit diff to look misleading. **Always re-verify the divergence by `head -25` of both files before deciding to keep or drop local-only content.** The 22-line delta is a heuristic, not a proof.

### 8. Missing H1 in TPipe source (title fallback pitfall)

TPipe source `.md` files are not required to have an H1. As of 2026-06-16, the new PumpStation files `api/pumpstation.md`, `api/pumpstation-models.md`, and `core-concepts/pumpstation-magic-contracts.md` all start with H2 or H3 — no `# Title` at the top. The sync script now falls back through H1 -> H2 -> H3 -> basename, so the page will get a title, but the title is a mid-page section name ("PathObject Class", "Path Description Models", "Path Execution Contract") rather than a proper page title.

If the title matters, the right fix is upstream: add a proper `# H1` at the top of the file in TPipe, then re-run the sync. Trying to override locally doesn't survive the next sync.

### 9. Section title display string

`SECTION_MAP` in the script maps `sectionId -> sectionTitle` (e.g. `'superpowers': 'Superpowers'`). The `sectionTitle` is what shows in:
- The YAML frontmatter of every doc in that section
- The docs hub cards (`src/pages/docs/index.astro`)
- The sidebar entries (`src/components/docs/DocSidebar.astro`)
- The per-section page header (via `docs[0]?.data.sectionTitle`)

So getting the `SECTION_MAP` entry right before running the sync avoids a round-trip to fix sectionTitle everywhere. The hardcoded UI arrays can then copy the same display string.

### 10. prevDoc/nextDoc format — HYPHENATED, not path (silent killer)

**The most important post-sync gotcha.** A 2026-06-16 sync shipped 77 files with `prevDoc: "core-concepts/why-tpipe"` (path format) and the site silently rendered **no prev/next nav on any page** because the site code's lookup couldn't find matches. The user noticed: *"I see already a lot of null where there wasn't null before and am very very sus you just introduced a ton of dead links."*

The invariant in the site code (`src/pages/docs/[...slug].astro` and `[section].astro`):

```js
const normalizeDocId = (id: string) => id.replace('.md', '').replace(/\//g, '-');
// doc.id in Astro = "getting-started/installation-and-setup.md"
// normalizeDocId(doc.id) = "getting-started-installation-and-setup"
// So frontmatter must store HYPHENATED slugs to match.
const prevDoc = prevDocId ? allDocs.find(d =>
  normalizeDocId(d.id) === prevDocId || d.id === prevDocId
) : null;
```

The script writes frontmatter as `prevDoc: "core-concepts-why-tpipe"` (hyphenated), via the `hyphenate` helper at the end of `processFile` (`s.replace(/\//g, '-')` on the full slug). If you change or remove that helper, this breaks for the whole site.

**The previous committed local had the same path-format bug** — meaning the prev/next nav was never actually working. The user just never had a reason to click the prev/next links. Any audit that touches this format must rebuild the site and verify the nav actually renders, not just that the frontmatter fields exist.

The same applies to the `superpowers/specs/*.md` file — its `doc.id` is `superpowers/specs/2026-06-10-pumpstation-execution-loop-design`, hyphenated to `superpowers-specs-2026-06-10-pumpstation-execution-loop-design`. The script's recursive walk and full-slug-based lookup handle this correctly when wired right.

**Verification command (run after every sync, never trust "looks fine" otherwise):**
```bash
# After npm run build, grep the rendered HTML to confirm nav actually rendered:
grep -A 1 "doc-nav-link" dist/client/docs/<section>/<doc>/index.html | head -10
# Should show <a href="..." class="doc-nav-link doc-nav-prev"> ... <span class="doc-nav-title">Title</span>
# If the <nav class="doc-nav"> contains <div></div> placeholders, the lookup failed and the values are null.
```

### 11. Dev server caches route data — restart after content config changes

After a sync that adds a brand-new section (e.g. `superpowers/`) and the corresponding entries in `src/pages/docs/index.astro` and `src/components/docs/DocSidebar.astro`, the dev server returns 200 for `/docs/` and `/` but **404 for any new doc page** until you kill and restart it. The content glob loader reloads the new `.md` files automatically, but the `getStaticPaths()` route table does not.

Symptoms in the dev log:
```
[WARN] [router] A `getStaticPaths()` route pattern was matched,
but no matching static path was found for requested path `/docs/superpowers/specs/...`.
```

Fix:
```bash
pkill -f "astro dev"
npm run dev &
# wait for "ready in", then smoke-test
```

Even if the user has a dev server running from before the sync, restart it after every sync that adds a new section. The sync also writes to the same dir the dev server watches, so file-content reloads are fine — but the route table won't regenerate.

### 12. Audit false positives from missing basename resolution

A 2026-06-16 first-pass audit reported **196 "dead inline links"** in the synced content. The reality: **zero dead links**. The audit script had been written naively:

```python
# WRONG: this produces false positives on every basename-style /docs/... link
if path_part.startswith('/docs/'):
    resolved = path_part[6:]   # "tpipe-mcp-package"
    if resolved not in all_full_slugs:   # missing section prefix -> flags as dead
        dead.append(...)
```

The link rewriter in the script produces `/docs/<basename>` (resolved via the global basename map), so the audit must do the same resolution: if the literal path doesn't exist, try the basename via the same `basename -> fullSlug` lookup the rewriter uses. The corrected audit (script at `/tmp/audit_links_v2.py`) found 0 dead links.

**Lesson:** when auditing link-rewriter output, mirror the rewriter's resolution exactly. A naive `path_part in all_paths` check is wrong because the rewriter does basename-to-fullSlug mapping that the audit must also do. If the user is going to see "196 dead links" in a report, the count must be real.

### 13. "No null in the middle" — user's hard rule, deterministic chaining required

The user has been explicit: *"null is not an ok value for anywhere other than the very first doc or the very last one."* This means a chain is allowed to have at most one null on each end — every doc in the middle must have BOTH prevDoc and nextDoc set.

The `scripts/sync-tpipe-docs.cjs` "## Next Steps" lookup does NOT enforce this. A TPipe source doc that has no `## Next Steps` section in its own body, AND no other doc links to it via Next Steps, becomes an isolated doc with `prevDoc: null, nextDoc: null`. Real-world examples after a PumpStation merge: `api/pumpstation.md`, `api/pumpstation-models.md`, `api/ollama-pipe.md`, `api/generic-openai-pipe.md`, `api/openrouter-pipe.md`, `api/tpipe-defaults-package.md`, `core-concepts/killswitch.md`, `core-concepts/merged-pcp-json-output.md`, `core-concepts/timeout-and-retry.md`, `core-concepts/pumpstation-magic-contracts.md`, `case-studies/grounded-case-studies.md`, `containers/pumpstation.md`. The script's "preserve the TPipe curated order" approach leaks orphans into the site.

When the user pushes back on nulls, the fix is **not** to patch the `## Next Steps` parser — it's to switch to deterministic alphabetical chaining per section (and per subdir). Every section's docs are sorted alphabetically and chained: first has prevDoc=null, last has nextDoc=null, everyone in the middle has both. This guarantees zero in-the-middle nulls by construction.

A working implementation lives at `templates/sync-tpipe-docs-deterministic.py` in this skill. It is a drop-in Python replacement for `scripts/sync-tpipe-docs.cjs` that:
- Alphabetically chains per section and per subdir (handles `p2p/`, `specs/`)
- Writes hyphenated slugs (gotcha #10)
- Escapes YAML in titles/descriptions (gotcha #14)
- Rewrites `.md` links to `/docs/<full-slug>` via a basename -> fullSlug map

Trade-off: deterministic chaining does NOT preserve TPipe's curated ordering. If the user wants curated order, fix the upstream TPipe docs (add `## Next Steps` sections) — but verify by also checking that every TPipe doc has at least one inbound or outbound link, otherwise it'll still orphan on sync.

When the user reverts the working tree and the .cjs script, the deterministic version at `templates/sync-tpipe-docs-deterministic.py` is the recovery path. Copy it to `scripts/`, point `REMOTE` and `SITE` at the right paths, run it.

### 14. YAML description with embedded quotes — escape or the build dies

The sync script writes the description string as a YAML double-quoted scalar. If the description contains a literal `"` (e.g. a quoted phrase like `"thinking"` or a code-quoted identifier), the YAML parser chokes:

```
bad indentation of a mapping entry
  Location: /home/cage/Desktop/Workspaces/ttt-site/src/content/docs/core-concepts/reasoning-pipes.md:2:99
```

Real-world case: `reasoning-pipes.md` description begins `"> 💡 Tip: Reasoning Pipes ... isolate the LLM's "thinking" ...`. The unescaped `"` terminates the YAML string early and the rest of the frontmatter is misinterpreted as nested mapping entries.

Fix: in the sync script, escape `\` and `"` before writing the title/description. Helper:

```python
def yaml_escape(s):
    if s is None:
        return None
    return s.replace("\\", "\\\\").replace('"', '\\"')
```

The .cjs script in the repo writes the raw title/description without escaping. The deterministic Python script in `templates/` escapes correctly. After every sync, scan the generated frontmatter for any unescaped quote inside a value:

```bash
grep -nE 'description: "[^"]*"[^,}\]]' src/content/docs/**/*.md
# or more simply: try `npm run build` -- it dies immediately on a broken file
```

The `npm run build` failure mode is informative: it stops at the FIRST file with bad YAML and prints `Location: <path>:<line>:<col>`. Fix that one, re-run, repeat until clean.

## Reference Files

- [GenericOpenAI Pipe Audit](references/generic-openai-pipe.md) — session audit findings: what was added, what gaps were found, audit command used
- [PumpStation Doc Set](references/pumpstation-doc-set.md) — full recipe, the things to verify, and the file shapes
- `templates/sync-tpipe-docs-deterministic.py` — drop-in Python replacement for the .cjs sync that guarantees zero in-the-middle null prev/next (see gotcha #13)
