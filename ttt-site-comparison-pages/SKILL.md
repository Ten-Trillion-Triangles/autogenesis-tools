---
name: ttt-site-comparison-pages
description: "Rewrite or ADD competitor/comparison marketing copy on ttt-site (TPipe vs LangChain, LangGraph, CrewAI, Google ADK, AutoGen, A2A, Koog, future competitors) for strength-first positioning. Verifies claims against TPipe source + competitor docs, removes defensive hedging and copula avoidance, and rewrites page-by-page with the dev server running for visual review. Use this skill for any single-page edit, full audit-and-rewrite, or adding a new comparison target to the site."
version: 1.5.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [marketing, comparison, ttt-site, tpipe, voice, content-rewrite]
    related_skills: [ttt-site-blog, ttt-site-pricing, humanizer, plan]
---

# TPipe Comparison Pages: Rewrite for Strength-First Positioning

Use this skill when rewriting the TPipe vs [competitor] comparison pages at `src/pages/comparison/` on the ttt-site. The goal is marketing copy that positions TPipe as the production agent infrastructure answer, with verified claims and zero defensive hedging.

The trigger fires for: any edit pass on a single comparison page, a full audit-and-rewrite of all 6 pages + hub, or a new competitor being added. The voice rules and workflow below apply to all of these.

## Core voice rules

These are non-negotiable. Apply to every comparison page on the site.

### Lead with what TPipe IS, never what it isn't

- "TPipe is the agent operating substrate" — yes
- "TPipe is not a graph orchestration library" — no
- "Not a feature comparison — a fundamental architectural distinction" — no, reframe as "Two architectures. TPipe is X. [Competitor] is Y."
- Replace copula avoidance ("not X, but Y", "instead of X, Y") with positive-first framing

### Make the minimum correction, not the maximum rewrite

When the user says "fix X" or "make sure X is accurate," fix X in place. Do not rewrite surrounding prose, restructure adjacent paragraphs, or add explanatory framing the user did not ask for. The instinct to "while I'm in here, also explain why" is the failure mode. The user reviews every rewrite; an unsolicited rewrite is more surface area for them to reject.

Operational test: if a single fact needs correction, the change should be a single fact-level edit. If a paragraph needs to be replaced to land one fact, the paragraph change is appropriate. If two or more paragraphs need to be replaced, the user probably asked for a rewrite, not a correction.

Failure mode observed (June 13, 2026, tpipe-vs-maf session): the user asked to "make sure you don't say graalvm is the only runtime but that jvm and graalvm are supported runtimes." The correct response was a single-sentence acknowledgement at the affected claim sites — e.g., "JVM bytecode (default) or GraalVM Native compilation target" appended to a runtime description. Instead, the rewrite replaced the entire "Why This Comparison Matters" intro paragraph, every "JVM-first" feature cell, the "Deployment Surface" cell, the pricing cell, the "When to Choose TPipe" bullet, and the FAQ — six distinct edits, all elaborately explaining the "both runtimes supported" framing in long prose. User correction: "vomit a bunch of it's not x it's Y crap when I told to just make sure you don't say grallvm is the teh only runtime but that jvm and graalvm are supported runtimes."

The right response, applied retroactively to the same call: six single-line edits, one at each location where the old framing was wrong, each acknowledging both runtimes. No paragraph rewrites, no explanatory framing, no KMP-project side commentary the user did not request. The "TPipe's answer to not being a KMP project" framing is good copy and is preserved in the skill's runtime-narrative section for when the user does ask for a longer treatment, but it is not the default response to a "fix this one fact" request.

**How to recognize you've over-corrected:** the change you're about to apply touches more than the minimum surface required to land the fact. If you're rewriting a paragraph to add a phrase that could have been a parenthetical, the parenthetical is right. If you're adding a sub-paragraph where one sentence would do, the sentence is right. If you're explaining the "why" when the user only asked for the "what," drop the why.

**Where this rule applies:** voice rules, factual corrections, dated content refreshes, runtime-narrative fixes, and JSON-LD date bumps. Everywhere a "while I'm here" rewrite would feel like an overreach.

### Never punt to the competitor

- "If LangGraph's graph model fits your problem, use LangGraph" — no
- "If you're not hitting those limits, stay with LangGraph" — no
- "You wouldn't switch for familiarity" — no
- "The honest assessment: X is excellent for what it is" — no
- Reframe "When to choose [competitor]" as a 2-paragraph fallback: "If you're already locked into this ecosystem and need to ship a chatbot in hours, here's what you get. Beyond that, the ceiling shows."
- The reader should walk away thinking "TPipe is the answer" — the competitor section is SEO scaffolding, not a real recommendation

### Migration sections use "Adopt Y for X" not "Replace X with Y"

- "Replace ConversationMemory with ContextBank" → "Adopt ContextBank for persistent distributed state"
- "Replace LangGraph with Manifold" → "Adopt Manifold for state-machine manager-worker coordination"
- "Replace LangSmith with TraceServer" → "Adopt TraceServer for self-hosted observability"
- Lead with the value gained, not the thing given up
- Rename section heading from "Migrating from X to TPipe" → "Adopting TPipe for [capability]"

### Blacklist — these phrases are out

Grep target. If any of these appear in a comparison page, rewrite or delete:

- "honest assessment"
- "reasonable choice"
- "excellent for what it is"
- "well-suited"
- "well-architected framework"
- "vibrant community"
- "extensive documentation"
- "architectural ceiling" (use "where X stops delivering" or "what TPipe provides beyond X")
- "rapid prototyping is the priority"
- "if X fits your [requirements|problem|use case], use X"
- "if you have a fixed number of states, explicit transitions"
- "you wouldn't switch for familiarity"
- "An architectural ceiling" / "Not a feature gap. An architectural ceiling"

### Never score an IDE/editor integration dimension — TPipe is headless-first

TPipe is intentionally headless-first: server and container deployment are the target surface, IDE/editor integration is not a competitive category TPipe operates in. When a competitor (Koog via ACP, Cursor, etc.) ships a documented IDE win, **omit the dimension from the matrix entirely** rather than scoring it as a competitor win. The reader walks away with no impression that TPipe has a gap — because there is no gap, by design.

Concretely:

- Do not add an "Ecosystem" / "IDE Integration" / "Editor Support" row to a comparison matrix to "be thorough." A 1-2 dimensional edge the other side doesn't contest is not a competitive fact; it's noise.
- If the dimension has already been published on a prior version, retract it on the next refresh. (The Koog v3, June 12, 2026, initially scored this dimension; per operator directive the dimension was removed in the corrected v3 — see Koog v3 in `md/FINAL-report-tpipe-vs-koog-v3.md` for the editorial note.)
- Don't write the supporting copy as "TPipe is headless-first, so this is by design, not a gap." The reader doesn't need the explanation. The dimension is just not in the matrix.
- Apply the same rule to any other category TPipe intentionally doesn't operate in: IDE plugins, language-server integrations, in-editor chat surfaces, dev-tooling-on-the-side. The substrate paradigm targets server-side autonomous systems, not developer ergonomics on the desktop.

This rule is broader than the other voice rules: it's a content-scope decision, not a phrasing decision. The other voice rules govern how to write; this one governs what to include.

**Where it goes in the workflow:** When adding a new comparison target (Step 0a-0e), audit each potential dimension against this rule before scoring. A dimension only enters the matrix if TPipe's position is meaningful in a competitive sense — that is, the user might choose the competitor for this dimension.

**Residual mentions in supporting copy still score the dimension by association.** Omitting the IDE/editor row from the matrix is necessary but not sufficient. Strip every reference to the category from the page:

- "When to Choose [competitor]" — do not say "IDE-adjacent workflows", "IDE-first positioning", or "JetBrains' IDE integration". These framings re-score the dimension by giving the reader the impression that TPipe has considered and rejected the category.
- FAQ items — do not include a question like "What about [competitor]'s ACP integration with IDEs?" The question itself is a points-by-association for the competitor.
- "Why this comparison matters" lead question — do not contrast TPipe's deployment target against the competitor's "IDE-adjacent workflows" framing. Frame the contrast around what TPipe IS, not what the competitor is not.
- Subtitle / quick-verdict labels — "JVM Graph Framework" with no IDE association is fine; "IDE-first Graph Framework" re-scores the dimension.

Empirically observed (June 13, 2026, tpipe-vs-koog): the page initially had "IDE-adjacent workflows" in "When to Choose Koog", "IDE-first (Koog's design center)" in the closer, and an "ACP integration with IDEs" FAQ item. All three re-scored the dimension despite it being absent from the matrix. Stripped on user directive. Lesson: omit from the matrix AND omit from the prose, or the matrix omission is hollow.

### Exclude work-in-progress features from comparison pages

This is a TTT-specific rule that overrides the usual "be comprehensive" instinct. TPipe's roadmap contains features in active development (the Harness class, the GraalVM Native ABI for mobile, etc.) that are **not yet shipped** and should not appear in comparison pages.

**Operator directive (June 12, 2026)**: "TPipe's new harness class (work in progress) should not be counted against TPipe in the comparison."

Translation for the page author:

- **Do not mention the feature at all** in the page body. Not as "coming soon," not as "in progress," not as a hedge that softens the comparison.
- **Do not score against TPipe** for lacking the feature. If Koog has X and TPipe's WIP feature would address the same problem, the page does not flag X as a TPipe gap.
- **Do not score in TPipe's favor** either. The WIP feature is not yet a TPipe capability; you can't claim it wins a dimension.
- **If a `FINAL-report` references a WIP feature as a forward-looking note**, ignore that note in the page. The page reflects the shipped product, not the roadmap.

This rule is a content-scope decision, not a phrasing decision. Same as the IDE-omission rule above: the dimension (or the WIP-feature mention) is just not in the page. The reader walks away with no impression that TPipe has a gap, because by the rule of the moment there is no gap to call out.

The current shipping TPipe surface is the source of truth for "what TPipe provides." Cross-check `src/content/docs/` for what's documented as production-ready. Anything in design docs, blog posts marked "in progress," or PR descriptions is WIP and excluded.

### Sections that are usually filler, cut them

- Closing "honest assessment" paragraph at the end of every page — delete
- "The ceiling becomes a problem only when..." minimization — reframe as what TPipe provides
- Both-sides framing in FAQ answers — make the answer direct ("No. Don't compose them. Here's why.")
- The "What X Actually Is" intro sections that dismiss TPipe as "not a Y" — flip order, lead with TPipe
- Subtitle hedging — "Different categories. Not a feature comparison." → "Two architectures. TPipe is X. [Competitor] is Y."

### TPipe's runtime narrative — JVM is the default, GraalVM Native is an optional AOT target

When a comparison page describes TPipe's deployment surface or runtime, the correct framing is non-negotiable. TPipe **runs on the JVM by default** (Java 24+). **GraalVM Native is an optional AOT compilation target** that produces a native shared library (`.so`/`.dylib`) for deployment targets where the JVM cannot run — iOS, Android, embedded systems, edge devices, native applications. GraalVM Native is **not a requirement**, and the FAQ should not ask "Why does TPipe require GraalVM Native Image for production?" because the answer is "It doesn't."

**Apply the minimum-correction principle when fixing runtime-narrative claims.** When the user says "make sure you don't say GraalVM is the only runtime" or similar, the change is a single-sentence acknowledgement at the affected site. The default runtime-narrative line to drop in is one of:

- "JVM bytecode (default) or GraalVM Native — both runtimes supported."
- "TPipe runs on JVM bytecode (default) or compiles to a GraalVM Native shared library for iOS, Android, embedded, and edge targets — both runtimes supported."
- "Default: JVM bytecode (Java 24+). Optional: GraalVM Native Image for iOS/Android/embedded/edge."

That is the entire fix. Do not rewrite the surrounding paragraph. Do not add a sub-paragraph explaining "the JVM is the design center, not a target among many." Do not add a "TPipe's answer to not being a KMP project" framing unless the user asks for it. The KMP-project framing is preserved below as available copy for when the user does want the longer treatment, but it is not the default response to a correction request.

The longer architectural framing is also correct copy — use it when the user asks for a rewrite of a section, or when writing a new page from scratch where the prose is not yet locked:

> "This is TPipe's answer to not being a KMP project. Instead of cross-compiling common code to many targets (the KMP path Koog takes, fragmenting the codebase into `commonMain`/`jvmMain`/`iosMain`), TPipe AOT-compiles JVM bytecode to a single native binary when the deployment target requires it."

The rule: short single-sentence acknowledgments for corrections, longer architectural framing for rewrites. Match the response to the request.

- "GraalVM Native — 50MB binary, no JVM at runtime" as the *only* runtime description. Wrong: undersells JVM. Correct: "JVM (default) or GraalVM Native — runtime choice" or "JVM bytecode (default) + GraalVM Native Image (optional AOT compilation target)."
- "TPipe requires GraalVM Native Image for production" — wrong premise. TPipe's default is the JVM. GraalVM Native is for cases where the JVM cannot run (mobile, embedded, edge, native applications).
- "GraalVM Native versus JVM" as a dichotomy — there is no dichotomy. They are two deployment targets from the same TPipe source. JVM bytecode is the default; GraalVM Native Image is the optional AOT target.
- "TPipe deploys to iOS/Android via GraalVM Native" presented as the primary deployment story — it's one option for the cases where the JVM cannot run, not the headline.

Where the correction applies (each site is a single-line edit, not a paragraph rewrite — see the minimum-correction principle above):
- The "Runtime" or "Deployment Surface" row in the feature table
- The "When to Choose TPipe — Headless operation" bullet
- The Pricing cell ("Manifold includes... GraalVM Native" should be "JVM bytecode + GraalVM Native compilation target — all included")
- The FAQ — the question "Why does TPipe require GraalVM Native Image for production?" must become "Does TPipe require GraalVM Native Image for production?" with the answer being "No, here's why and when you'd use the optional native target."

Empirically observed (June 13, 2026, tpipe-vs-maf session): the initial MAF page and the existing Koog + AutoGen pages all had the GraalVM-Native-only framing, including the "Why does TPipe require GraalVM Native Image for production?" FAQ. User explicit correction: "It explained that you can run on jvm or graalvm. It's not only graalvm at runtime graalvm is an option for a runntime target. You can compile to jvm or a native shared library for embedding into native targets, embedded systems and other cases where the jvm can't be used. It's TPipe's answer to not being able to be a KMP project." All four pages (MAF, Koog, AutoGen, index) were patched in one pass — first with a paragraph-rewrite overcorrection (six verbose edits, each with a KMP-project framing), then after user pushback, dialed back to single-sentence acknowledgments at each site. The second pass is the right one; the first pass was the failure mode the minimum-correction principle exists to prevent.

## Workflow

### Step 0: Adding a new comparison target (skip for edits to existing pages)

When the user wants to add a new competitor (e.g., TPipe vs Koog, TPipe vs Smolagents, TPipe vs Microsoft Semantic Kernel), the workflow is distinct from rewriting existing pages. Existing Steps 1-7 assume the 6 competitors are already on the site — adding a 7th has setup work none of those steps cover.

**Step 0a: Check for prior research first.** Before starting ANY new competitor research, scan for existing reports:
- `md/FINAL-report-tpipe-vs-<competitor>-vN.md` — versioned research outputs (the project uses a v1 → v2 → v3 cadence as new competitor releases ship)
- `md/0N-<competitor>-*-findings.md` — thread-level findings files
- `references/competitor-verification-checklist.md` — see if the competitor is already tracked

If a `FINAL-report` exists, the research is already done. Read it cold, do NOT re-research from scratch. Update with a "what's new since vN" delta check on the competitor's most recent release (target: 30-day window unless the user specifies otherwise). The prior report's citation table is your source list — extend, don't replace.

**Step 0b: If no prior research, dispatch deep-research with the 3-step methodology.** Load `deep-research` skill. Critical pitfall to enforce (from the skill's pitfalls section): internal products (TPipe) have NO public web presence. The 3-step methodology is:
1. Read all existing thread findings files in `md/`
2. Check `src/content/docs/` for internal product capabilities
3. Only then search the web for external competitor information

If you skip step 1, the comparison thread will conclude TPipe "doesn't exist" (empirically observed: `md/05-tpipe-vs-koog-findings.md` from May 12, 2026 has this exact failure). See `references/competitor-add-workflow.md` for the Koog case study and the versioned-report pattern.

**Step 0c: Wire the new page into the site hub.** Creating the new `.astro` file is not enough. The new comparison must be discoverable:
- Add a card to `src/pages/comparison/index.astro` `comparison-grid` section. Match the existing card structure (header, card-badge, card-status, card-title, card-subtitle, card-verdict, card-highlights, card-footer with CTA). Read 2-3 existing cards first to match the convention, don't invent a new card shape.
- Update the comparison count meta item on the hub ("6 Comparisons" → "7 Comparisons").
- Update the hub's "Updated [Month Year]" date display.
- If the hub has a `meta-sep` count or "Last updated" string, refresh it.
- Check the homepage comparison table at `src/components/comparison/ComparisonTable.astro` — if it lists competitors, add a row/column for the new one (same link-target audit rule from Pitfalls).

**Step 0d: JSON-LD on the new page.** Set `datePublished` to today (the date the new card ships), `dateModified` to today. Don't inherit from a competitor page's existing dates — the new page has no history.

**Step 0e: Don't fabricate missing TPipe-side details.** If the FINAL report doesn't have a specific number for a TPipe feature, look it up in `src/content/docs/` before writing the claim. The "VERIFIED / MARKETING-AS-OF / STALE" matrix from Step 2 still applies. Default for new pages: only include claims with `src/content/docs/` paths as evidence. MARKETING-AS-OF claims need the user's sign-off before shipping.

### Step 1: Survey the page set

Read all 6 comparison pages + the hub (`src/pages/comparison/index.astro`). Note:
- Which numbers are repeated across pages (8 reasoning methods, 5 injectors, 18 hooks, DistributionGrid LOC, 120+ turn, etc.)
- Which competitor claims appear in multiple pages (A2A 150+ orgs, AutoGen 0.4, etc.)
- Which style issues are systemic (every page has the same closing "honest assessment" paragraph)

**Also audit the homepage comparison table** at `src/components/comparison/ComparisonTable.astro`. It renders on the `/` page and uses the same data shape (feature / TPipe / competitor) as the dedicated comparison pages, so the same voice rules and accuracy rules apply. It's a separate Astro component, not under `src/pages/comparison/`, so it gets missed if you only walk the page directory. Same competitor claims, same audit checklist. Bug classes observed: misrouted links (a "CrewAI" header cell pointing at `/comparison/tpipe-vs-langchain`) and stale "Python only" claims that contradict the verified LangChain v1 / Google ADK multi-language state.

**Also cross-check the hub card for the page.** `src/pages/comparison/index.astro` has a card for each comparison target, and the card's verdict text (the `verdict-tpipe` / `verdict-vs` / `verdict-koog` span trio) is independent prose from the article's verdict block. When the article's count changes (e.g., "10 of 11 dimensions" → "10 of 12 dimensions"), the card must be re-read for matching, otherwise the hub and the deep-dive will contradict each other. The card's verdict framing — "TPipe wins N of M dimensions" vs "X wins on Y and Z" — is the high-risk string. Empirically observed (June 13, 2026, tpipe-vs-koog): the article narrative said "Eight of eleven… Three are Draws" but the hub card said "TPipe wins 10 of 11 dimensions" with the Koog span saying "Koog wins on accessibility and operational maturity" — two different matrix shapes coexisting on the same site. See `references/verdict-count-audit.md` for the full sweep checklist.

### Step 2: Build the claims matrix

For each TPipe-specific number that appears in the pages, mark it:
- **VERIFIED** — found in TPipe source, include path
- **MARKETING-AS-OF** — claimed in marketing, source unclear, OK to keep with owner sign-off
- **STALE** — needs update or removal

For each competitor claim, mark:
- **CURRENT** — verified against competitor docs as of [date]
- **STALE** — competitor has shipped, needs update
- **WRONG** — competitor never had this or has it differently

Decide with the user which to keep, soften, or drop before rewriting. Default: user owns the call on what stays. The user may explicitly say "keep all numbers as-is" if they've already signed off.

### Step 3: Start the dev server FIRST

Before any rewrite, start `npm run dev` in the ttt-site directory. The user reviews each page by browsing. This is not optional — diff-based review of marketing copy is unreliable. Visual review in the actual site is the only signal that matters.

Use `terminal(background=true)` to start. The server runs on port 4321. After starting, curl the page to confirm HTTP 200 before telling the user it's ready.

The server is hot-reloading, so each page change is instantly visible.

### Step 4: Rewrite one page at a time, pause for review

For each comparison page:
1. Apply the voice rules
2. Replace "Replace X with Y" with "Adopt Y for X" in migration sections
3. Cut the closing "honest assessment" paragraph
4. Shrink "When to choose [competitor]" to 2 short paragraphs (or a 2-3 item list max)
5. Reframe FAQ answers to be direct (no diplomatic both-sides)
6. Update JSON-LD `dateModified` to today; keep `datePublished` unchanged
7. Remove unused imports (check for `import BlogPost` and similar)
8. Run `npm run build` to confirm no Astro errors
9. Curl the page to confirm HTTP 200
10. Grep the page for the blacklist phrases — must be 0 matches
11. Tell the user the URL, summarize the changes, pause for their next-step signal

Do not start the next page until the user says so. The user reviews visually between pages.

### Step 5: Hub page last

The hub (`index.astro`) gets rewritten after all 6 competitor pages. Lead with TPipe, not the competitor count. Refresh the "Updated [Month Year]" display.

### Step 6: Final audit

After all pages rewritten:
1. Grep all comparison pages for the blacklist phrases — final pass, 0 matches. **Run the script AFTER all rewrites complete, not just per-page.** Your own rewrite can re-introduce a hedge phrase the per-page check missed (observed: "vibrant community" slipped into an AutoGen rewrite and was only caught at the final-pass audit). Grep both `src/pages/comparison/` and `src/components/comparison/ComparisonTable.astro`.
2. `npm run build` for the full site
3. Spot-check each page renders correctly via curl
4. Update `AGENTS.md` with the voice rules so future agents don't reintroduce hedging

### Step 7: Layout polish — center single CTAs

After pruning dead links, a `.migration-cta` flex container is often left with only the "View Documentation" button. Without justification, it floats hard left and looks unbalanced inside the panel. Add `justify-content: center` to the `.migration-cta` rule to center the remaining button. One-line CSS fix, applies to all 5 pages with migration sections (langchain, langgraph, crewai, google-adk, autogen). a2a-protocol has no migration section, skip it.

## Pitfalls

- **Don't drop specific numbers without owner sign-off.** "120+ turn tasks", "DistributionGrid 8,773 LOC", "GraalVM 50MB binary" are marketing claims the user has likely already approved. The user may want to defend them. Default is keep, not drop. Build the claims matrix and ask.
- **Don't fabricate destinations for dead links.** If a CTA button or see-also card links to a blog post, migration guide, or FAQ answer that doesn't exist, **remove the link, don't fix the destination by writing bad filler content.** A user who hits a "Migration Guide →" 404 will distrust the whole page; a user who hits a thinly-veiled hallucinated guide will distrust the company. The user can write the missing piece themselves when they're ready. Exception: fix obvious URL typos (e.g., ttt-site blog posts live at `/blog/YYYY-MM-DD-slug/` — see `references/ttt-site-blog-urls.md` — so a slug-only URL is a typo, not a missing post).
- **Don't dispatch N parallel research subagents** when other agents or rate-limited contexts are running. The `delegate_task` API itself can fail under load (observed: HTTP 404 on parallel fan-out with 6 tasks in one call). The user may not have API request budget for 6 parallel web-search agents, and may not have noticed they're running concurrently. Do the research inline with `mcp_MiniMax_web_search` or in 2-3 sequential batches. Verify the dispatch works with a small test before fanning out.
- **Don't claim "Python only" for LangChain.** LangChain v1 (alpha Sept 2025) ships in both Python and JavaScript/TypeScript. LangGraph.js is GA for JS. Any "Python only" or "Python framework you call" claim will read as out-of-date on contact. Wording: "Python and JavaScript (LangChain.js / LangGraph.js) — v1.0 alpha in both runtimes."
- **Don't claim "Python-based" for Google ADK.** ADK is multi-language: Python, TypeScript, Go, Java, Kotlin. ADK Python 2.0 GA is live. See verification checklist.
- **Don't claim "No native hooks" for CrewAI.** CrewAI has `step_callback`, `task_callback`, `before_kickoff_callback`, `after_kickoff_callback` at agent and crew level. The original homepage table said "No native support" and was wrong. CrewAI's callback system is shallower than TPipe's 18-hook DITL — say that, don't say it's absent.
- **Don't localize TPipe's architecture to a single container when framing the comparison.** TPipe's design lives at the P2PInterface level. When the comparison copy describes a TPipe mechanism (kill switch, error propagation, context flow, agent communication), the framing must be interface-level, not "TPipe's Splitter does X" or "TPipe's Pipe does Y." The mechanism runs in every container that implements `P2PInterface` — Pipeline, Manifold, Junction, Splitter, MultiConnector, DistributionGrid. The Splitter or any other specific container is one concrete example, never the actor. Correct: "A kill switch is a property of the P2PInterface. Every container that implements it runs a check as it executes. The Splitter is one example: it runs branches in parallel and accumulates tokens across them." Wrong: "The Splitter enforces the kill switch." The first framing positions TPipe's architecture as designed; the second undersells it as one container's feature. The user has caught this multiple times on the corresponding blog post — apply the same rule to comparison copy.
- **Don't cite zuplo.com or third-party blogs for the A2A "150+ organizations" claim.** Use the Linux Foundation press release dated April 9, 2026. The LF announcement is the authoritative source; the third-party blog is downstream of it and may be inaccurate.
- **Don't merge CSS classes across pages.** Each comparison page has its own style block. If you find a page missing CSS for `.migration-section` (LangGraph was missing it in the original), add it — but don't refactor all pages to share a stylesheet. Out of scope.
- **Don't add a new comparison target without checking prior research.** A new "TPipe vs X" page is a different workflow from rewriting existing pages. If the user says "add a comparison for X," Step 0 above applies. If `md/FINAL-report-tpipe-vs-X-vN.md` exists, the research is done — read it, verify the delta, write the page. Re-dispatching deep-research when prior work exists wastes an hour and risks contradicting a verified source list.
- **JSON-LD `dateModified` must be refreshed.** `datePublished` stays the same; `dateModified` becomes the date of the rewrite.

- **Before claiming "X is missing" on a comparison page, verify the class names that page actually uses, and audit visible markup vs structured data as separate layers.** The failure mode: a grep for `class="faq-question"` returns 0, the agent concludes "FAQ is missing" and recommends adding it. The FAQ is rendered with `<div class="faq-item">` inside `<div class="faq-grid">` inside `<section class="faq-section">` — same content, different class name. Landing pages use `<details class="faq-item">` with `<summary class="faq-question">`; comparison pages use a div-based grid. Same trap with feature tables: HTML `<table>` is what gets grepped, but the comparison pages use `<div class="feature-table">` with `<div class="feature-row">` divs. Grep returns 0, the tables are there. Operational rule: before claiming X is missing on a comparison page, do a content-shape grep (broader pattern, e.g. `grep -iE "FAQ|frequently|questions?"` or `grep -iE "feature|table|row"`) and read 1-2 representative blocks via `read_file`. TTT-specific class-name cross-walk: FAQ section = `<div class="faq-item">` in `<div class="faq-grid">` (comparison) vs `<details class="faq-item">` with `<summary class="faq-question">` (landing); feature tables = `<div class="feature-table">` (comparison) vs HTML `<table>` (everywhere else); quick verdict = `<div class="quick-verdict">` (comparison only). **Visible markup and structured data are independent layers.** A page can have a fully-rendered FAQ section but no `<script type="application/ld+json">` FAQPage wrapper — the visible markup is what the reader sees, the JSON-LD is what LLMs and search engines parse for citation. Both layers are needed. Audit pattern: `grep -c '"@type": "FAQPage"' src/pages/comparison/*.astro` per page; ship the wrapper script tag if the count is 0. The wrapper data parses from the visible `<h3>`/`<p>` pairs in the existing `faq-item` divs, HTML-stripped, JSON-serialized with the same `set:html={JSON.stringify(...)}` Astro pattern used for the Article + BreadcrumbList scripts on the same page. Empirically observed (June 14, 2026, ttt-site AEO audit): an audit pass claimed both "comparison tables are missing" and "FAQ is missing on comparison pages" — both were already present in the comparison-page conventions, only the FAQPage JSON-LD wrapper was actually absent. The fix was one script tag per page (~30 min total, 6-7 questions per page parsed from existing markup), not a structural rewrite. The user explicitly directed: "verify before suggesting duplicate work" — when an audit conclusion would result in rewriting visible content, read the file at the section first, and audit the visible-markup layer and the JSON-LD layer separately.
- **The hedge audit is the gate, not the afterthought.** "Architectural ceiling" is the single most-likely hedge slip — the phrase is in the skill's blacklist, the audit script catches it correctly, but the failure mode is the *timing* of when the audit runs. If the agent writes the page, builds, and then runs the audit, the audit can return a hit and force a patch — but the hedge was already shipped once. The fix is positional: run the audit script **before** declaring the page complete and before the build. The audit is a pre-declare-complete gate, not a post-write review. Same principle as running tests before merging, not after. Failure observed (June 13, 2026, Koog page): wrote "...the architectural ceiling is the same as every graph-based framework" in the "When to Choose Koog" fallback paragraph, then ran the audit post-build, then had to patch the paragraph. The fix: write the page, run the audit, then declare complete. If the audit fails, you patch and re-run, but you never "ship" a hedge phrase to a build artifact.
- **Homepage comparison table link targets are a separate audit class.** `src/components/comparison/ComparisonTable.astro` has header cells and Category cells that are `<a href="/comparison/...">` — every one of them must point at the correct page. Bug observed: the CrewAI header cell was pointing at `/comparison/tpipe-vs-langchain` (wrong target — should have been `/comparison/tpipe-vs-crewai`), and the same wrong target appeared in the Category row. The per-page voice/accuracy audit won't catch this — the table's correctness is purely about link targets. After rewriting the table, verify every `<a href>` resolves to the right page: a one-liner like `grep -oE 'href="/comparison/[^"]+"' src/components/comparison/ComparisonTable.astro | sort | uniq -c` shows the link distribution. Two pages with one URL, or one page referenced from a header that doesn't match, = bug.
- **Unused imports break linting in some setups.** Check the frontmatter for imports the page doesn't actually use. The original ttt-site had `import BlogPost from '../../components/blog/BlogPost.astro';` in 3 of 6 comparison pages but never rendered it.
- **Migration sections need CSS.** The original LangGraph page referenced `.migration-section` / `.step-number` / `.cta-button` but had no styles for them, so the migration section rendered unstyled. If a page has the HTML but unstyled rendering, add the missing CSS block.
- **Visual card density must match — verify the new card's boundingBox against row-mates before declaring complete.** A new comparison card with a longer verdict line or more text in the highlights will render taller than its row-mates, breaking the visual grid. The grid auto-stretches all cards in a row to the tallest, so the visual gap can be 80+px and look like a styling bug. Verified workflow (observed June 13, 2026, tpipe-vs-microsoft-agent-framework session):
  1. Screenshot the new card via Playwright: `await page.locator('a.comparison-card').nth(N).screenshot({ path: '/tmp/card.png' })`.
  2. Get all card boundingBoxes: `const box = await cards[i].boundingBox();` and log them.
  3. If the new card is >30px taller than the row's other cards, trim the verdict line (other cards' verdict lines are short — one phrase, ~30-50 chars each side) and tighten the highlights list (other cards' highlights are short — ~50-80 chars each).
  4. Re-screenshot and confirm the card is now within 10-15px of row-mates.

  The MAF card was 613px vs the Koog row-mate at 530px (83px taller) when first drafted. After trimming the verdict to "Draws on paradigm, language, multi-agent breadth" and shortening the 5 highlights, it landed at 597px — only 10px taller than the row. Same fonts, same colors, same padding, just shorter text content.
- **Astro interprets `{...}` as a template expression even inside `<p>` content.** When writing a page that needs literal curly braces in prose (e.g., describing a REST endpoint like `/api/traces/{id}` or a JSON path like `${variable}`), Astro tries to compile `{id}` or `${variable}` as a JS expression and the build throws `ReferenceError: id is not defined`. Escape curly braces with HTML entities: `{` becomes `&#123;` and `}` becomes `&#125;`. Same fix for angle brackets in code blocks where you need literal `<` or `>` — use `&lt;` and `&gt;`. The escapes render as the literal characters in the served HTML. Observed: the MAF page TraceServer description contained `GET /api/traces/{id}` and Astro threw a 500 until the braces were escaped.
- **When browser_vision fails, fall back to Playwright screenshots — don't try to guess visual state from box dimensions alone.** When the vision tool returns a 404 (or any upstream error), capture the rendered page directly via Playwright and read the box dimensions, screenshot the specific element, or just diff numeric output. The workflow:
  ```js
  import { chromium } from '/home/cage/Desktop/Workspaces/ttt-site/node_modules/playwright/index.mjs';
  // (use the project's own node_modules — no global install needed)
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 2200 } });
  await page.goto('http://127.0.0.1:4321/comparison', { waitUntil: 'networkidle' });
  const cards = await page.locator('a.comparison-card').all();
  for (let i = 0; i < cards.length; i++) {
    const box = await cards[i].boundingBox();
    console.log(JSON.stringify(box));
    // Optional: await cards[i].screenshot({ path: `/tmp/card-${i}.png` });
  }
  await browser.close();
  ```
  Use the project's `node_modules/playwright` directly — no `npx`, no global install. `boundingBox()` is enough to detect "this card is 80px taller than its row-mates"; `screenshot()` is enough to compare against a previously-captured image. If you also need pixel-level diff, save the screenshot and read it back. Empirically observed (June 13, 2026): browser_vision returned a 404 for the rendered card; Playwright `boundingBox()` revealed the MAF card was 83px taller than the row-mate, which led to the visual-density fix.

- **When verifying visual fixes, actually look at the screenshot — don't trust box dimensions alone.** Box height/width is a numeric proxy for visual state, not a substitute for it. A card with `.verdict-maf { color: #5c2d91 }` (dark muted purple) and a card with `.verdict-maf { color: #e879f9 }` (vivid magenta) can have identical boundingBox dimensions, but the dark-purple version is hard to read on the dark background — the visual issue is invisible to box-dimension inspection. The verification workflow is:
  1. Screenshot the specific element via Playwright: `await page.locator('a.comparison-card[href*="..."]').screenshot({ path: '/tmp/card.png' })`.
  2. Run `mcp_MiniMax_understand_image` on the screenshot with a question that asks specifically about the visual property in question (color, layout, alignment, contrast).
  3. Confirm the vision tool's answer matches your claim about the fix. If the vision tool says "the color is dark and hard to read," the fix did not land, regardless of what `boundingBox()` says.
  4. If the vision tool returns 404 or upstream error, retry once. If it still fails, capture a fresh screenshot and read the actual pixel data via Playwright (e.g., compute the dominant color of the verdict text region with `sharp` or compare two screenshots for pixel diff). The point: do not declare a visual fix complete based on box dimensions alone.

  Empirically observed (June 13, 2026, tpipe-vs-maf session): the MAF card's verdict color was changed from `#5c2d91` to `#a855f7` to `#e879f9` over three iterations. The first change was claimed fixed; user reported "it has not changed at all." On inspection: the dev server's CSS cache was serving the old color, AND the color contrast was still wrong even after the second iteration. The vision tool (when it worked) caught the contrast issue that box dimensions could not. Final state: bright vivid magenta (#e879f9) verified by vision tool as "stands out sharply against the dark background, matching the intensity of the green text above it." Lesson: visual verification requires actually looking at the image. Numeric proxies fail on color, contrast, alignment, and font-rendering issues — the exact classes of issues that affect "does this card look like the others."

- **Verdict span colors must have visible contrast on the dark theme — pick vivid, not muted.** Each comparison card's second-line verdict span (`verdict-tpipe` is always green; the competitor-side span uses a per-competitor color) needs to be bright enough to read on the dark page background. Existing colors: TPipe green `#4ede9e`, LangChain yellow `#ffc107`, LangGraph purple `#9c27b0`, CrewAI orange `#ff5722`, AutoGen blue `#0078d4`, A2A cyan `#00bcd4`, Koog red/pink `#fe315d`. When adding a new card's verdict color, pick a color with similar brightness and saturation — not a dark muted shade (e.g., `#5c2d91` dark purple) that disappears into the background. Test the color with the vision tool workflow above before declaring complete. Empirically observed (June 13, 2026, tpipe-vs-maf): the initial MAF color `#5c2d91` (a Microsoft brand purple) was too dark to read on the dark background; the vision tool flagged it as "low contrast, the letters feel fuzzy or bleeding into the gray." Final color `#e879f7` (bright vivid magenta) was confirmed by vision tool as "stands out sharply against the dark background, matching the intensity of the green text above it." Same brightness tier as the other cards' verdict colors.

- **The Astro/Vite dev server can serve stale CSS after edits — restart it before declaring a visual fix complete.** The Astro dev server's Vite HMR does not always pick up changes to `<style>` blocks inside `.astro` files. Symptom: you edit a CSS rule, the file on disk has the new value, the page renders HTML referring to the rule — but the rendered CSS still has the old value. The Vite client reloaded, the file changed, but the HMR endpoint kept serving the cached version. The fix: kill the dev server (process.kill or `pkill -f "astro dev"`) and restart it (`terminal(background=true)` with `npm run dev`). Verify the new CSS is actually in the served HTML before declaring the fix complete. The Playwright screenshot after restart will show the new color/layout; the screenshot before restart will show the stale state, regardless of how many HMR cycles the dev server has been through. Empirically observed (June 13, 2026, tpipe-vs-maf): the `.verdict-maf` color change from `#5c2d91` to `#a855f7` did not appear in the served HTML after multiple HMR cycles; required dev server restart to take effect. The playwright screenshot taken before restart still showed the old color even though `grep` against the file on disk returned the new value.
- **Don't trigger the plan skill and stop.** The plan skill's "for this turn, you are planning only" restriction is per-turn. After writing the plan and getting user approval (via `clarify` calls), proceed to execute. The user expects plan + execute as one workflow, not two separate sessions.
- **Read the full file before overwriting.** `read_file` with `offset`/`limit` only loads a window. The `write_file` tool warns about this. Always re-read the whole file (or load the rest with a second `read_file` call) before `write_file` on a multi-page document.

- **Kotlin Multiplatform competitor (Koog and any other KMP framework) — verify KMP-first architecture before scoring Language/Runtime as a Draw.** KMP `commonMain` must compile to every target (JVM, Android, iOS, JS, WasmJS). JVM-specific features — `ClassLoader`, full `java.lang.reflect`, JVMTI, `java.lang.invoke Method Handles`, `StackWalker`, JDK Flight Recorder, JNI, GraalVM Native Image, HotSpot intrinsics — cannot be exposed in the cross-platform API surface. They would only work in `jvmMain`, fragmenting the codebase per target. A competitor marketed as "JVM" with KMP-first architecture has a binding constraint on JVM-specific substrate power. When comparing TPipe against any KMP competitor, Language/Runtime is a **TPipe win** on the JVM target specifically: TPipe's JVM-first substrate has direct access to features KMP common code cannot expose. Empirically observed (June 13, 2026, tpipe-vs-koog): the v3 TPipe vs Koog report initially framed Language/Runtime as "Draw (three paths to mobile)" because the analyst noted KMP gives Koog iOS/JS/WasmJS targets. User corrected: Koog is KMP-first, JVM-second, and the cross-platform API surface excludes the JVM-specific substrate features TPipe uses. The 1.0 release advertises JVM as a target because demand is pointing at JVM, but architecturally the framework is KMP-first. The marketing posture (advertised as "JVM") and the architectural reality (KMP-first) are different. Don't reintroduce the "Draw" framing on refresh — Language/Runtime stays a TPipe win. The final matrix is 10-of-11 TPipe wins, 1 draw (Multiplatform Mobile, where KMP's iOS/JS/WasmJS target surface is a real and legitimate Koog advantage), 0 Koog wins.

- **Verdict counts drift across the page set — sweep ALL of them, not just the one the user pointed at.** A comparison page's verdict (e.g., "10 of 11 dimensions") typically appears in at least four locations on the page itself — the quick-verdict block, the narrative intro paragraph, the meta description in the frontmatter, and the JSON-LD `description` field — plus the corresponding hub card on `src/pages/comparison/index.astro`. These strings are written independently across the file's lifetime and can drift out of sync without breaking the build. When a user reports a stale count, audit every location. The GEO/AEO reason this matters: bot crawlers re-encountering inconsistent counts (e.g., "8 of 11" in the narrative and "10 of 11" in the verdict block) will repeat both numbers across the LLM citation layer. A wrong recipe name in one comparison page = thousands of citation-context reproductions citing it. Accuracy is a citation asset, not just a build-quality asset. See the stale-claim-audit pitfall below for the new-page audit pattern.

  ```
  grep -nE "(\d+ of \d+|\d+-of-\d+|outright wins|are Draws|is a Draw|is a draw|wins on|wins \d+ of)" \
    src/pages/comparison/<page>.astro src/pages/comparison/index.astro
  ```

  Do not stop at the line the user cited. Cross-check the page's own verdict block, the narrative paragraph, the meta description, the JSON-LD, and the matching hub card. Empirically observed (June 13, 2026, tpipe-vs-koog): the article narrative said "Eight of eleven… Three are Draws" but the quick-verdict block said "10 of 11 dimensions" and "1 draw, 0 outright wins", the meta description said "10-of-11 in TPipe's favor", the JSON-LD said "10-of-11 in TP's favor", and the hub card said "TPipe wins 10 of 11 dimensions" with the Koog span saying "Koog wins on accessibility and operational maturity" — five distinct verdict shapes for the same page. The article's feature table is the source of truth: count the rows, count the winners per row, derive the matrix, then update every count string to match. Hub card and meta description often need a separate edit because they're not in the article's `astro` file. See `references/verdict-count-audit.md` for the full sweep procedure.

- **When writing a new comparison page, audit the existing pages for stale claims about the same TPipe features.** Empirically observed (June 13, 2026): the TPipe vs MAF research pass uncovered that `tpipe-vs-koog.astro` and `tpipe-vs-autogen.astro` both list invented Junction recipes (`UNANIMOUS_VOTE`, `WEIGHTED_VOTE_ACT`, `PLURALITY_VOTE_ACT_VERIFY`, `CONSENSUS_BREAKER_VOTE_ACT`) that don't exist in `Junction.kt`. The first two real recipes were renamed. The same kind of invented-feature drift is plausible elsewhere. When drafting a new comparison, do a parallel audit: `grep -nE "Junction|DistributionGrid|KillSwitch|ChainOfDraft|ContextBank|TraceServer|LoreBook|Manifold" src/pages/comparison/*.astro` and verify each claim against `references/tpipe-systems-ground-truth.md` (in the `product-claims-audit` skill) before drafting. The corrected Junction recipes are: `VOTE_PLAN_OUTPUT_EXIT`, `PLAN_VOTE_ADJUST_OUTPUT_EXIT`, `VOTE_ACT_VERIFY_REPEAT`, `ACT_VOTE_VERIFY_REPEAT`, plus DSL shortcuts `VOTE_PLAN_ACT_VERIFY_REPEAT` and `PLAN_VOTE_ACT_VERIFY_REPEAT`. Flag the stale claims in a separate "stale-claim audit" section at the end of the research file, not in the page itself — the new page is about the new competitor, not about fixing the old pages. The user has flagged this directly: "we're still fighting to own all those SEO keywords (and winning) so make sure you don't drop a detail because you were too lazy to dig into tpipe far enough directly read the code and our web page and docs."

- **Don't undersell TPipe features in the comparison matrix.** Real categories where the existing pages undercount TPipe: 8 reasoning methods (not just Chain-of-Draft — `StructuredCot`, `ExplicitCot`, `processFocusedCot`, `BestIdea`, `ComprehensivePlan`, `RolePlay`, `ChainOfDraft`, `SemanticDecompression`); 4 memory tiers (not 3 — `ContextWindow`, `LoreBook`, `ContextBank`, `MiniBank` plus `Dictionary`); 7 Junction binding kinds (not just "moderator + participants" — `MODERATOR`, `PARTICIPANT`, `PLANNER`, `ACTOR`, `VERIFIER`, `ADJUSTER`, `OUTPUT`); 4 DistributionGrid routing directives (not just "P2P mesh" — `RUN_LOCAL_WORKER`, `HAND_OFF_TO_PEER`, `RETURN_TO_SENDER`, `TERMINATE`); 6 active PCP transports (not just "Kotlin + JS + Python" — `Stdio`, `Tpipe`, `Http`, `Python`, `Kotlin`, `JavaScript`). The undersell usually comes from an analyst working from AGENTS.md and second-hand descriptions rather than from source. Full source-verified inventory is in `references/tpipe-systems-ground-truth.md` in the `product-claims-audit` skill. When the page says "Chain-of-Draft" or "3-tier memory" without the surrounding context, the LLM citation layer will pick up the narrow framing. Either use the precise count or scope the claim correctly (e.g., "Chain-of-Draft, the only production-validated reasoning optimization in the survey" rather than implying it's the only reasoning method TPipe ships).

- **TPipe source code is co-located locally — go to it directly, don't reason from AGENTS.md.** `/home/cage/Desktop/Workspaces/TPipe/TPipe/` is the canonical source. The local docs at `ttt-site/src/content/docs/` are synced from a separate repo and can drift from the source. The marketing site pages can drift from the docs. For any TPipe feature claim — recipes, transport lists, memory fields, hooks, exception types, line counts — open the file in the source tree and confirm.

  **Path trap:** the workspace root `/home/cage/Desktop/Workspaces/TPipe/` contains model-name analysis scripts (`analyze_har.py`, `foundation_models.json`) that look like TPipe code but aren't. Always `cd TPipe/` before any grep. Reinforced June 25, 2026 when a BedrockPipe snippet accuracy audit started at the workspace root and returned no matches; the actual source is one level deeper. The same nested-path mistake applies to any code-snippet accuracy audit on landing pages — see `ttt-site-code-snippets` for the full workflow. The user has been explicit: "dig through TPipe on this system, or use our website to examine the docs and github... directly read the code and our web page and docs." The verification grep that covers most subsystems:

  ```
  cd /home/cage/Desktop/Workspaces/TPipe/TPipe/ && \
    find . -type f -name "*.kt" -not -path "*/.claude/*" -not -path "*/build/*" | \
    xargs grep -l "<FeatureName>" 2>/dev/null
  ```

  If a feature the page claims TPipe has doesn't appear in source, it's invented. The full source-verified feature inventory (Junction recipes, KillSwitch trip reasons, ContextBank mutex layout, LoreBook fields, Memory tiers, Manifold contract, DistributionGrid directives, TraceServer specifics, PCP transports) is in `references/tpipe-systems-ground-truth.md` in the `product-claims-audit` skill. Use that file as the canonical lookup, but always re-verify the specific line before citing in a fresh page. Empirically observed: ContextBank, LoreBook, KillSwitch, TraceServer, ChainOfDraft, DistributionGrid, Manifold, Junction all have hits across `src/test/kotlin/`, `TPipe-Defaults/src/main/kotlin/`, and `TPipe-TraceServer/src/main/kotlin/`. A feature that the article claims TPipe has but that does not appear in source is a STALE or WRONG claim per the Step 2 VERIFIED/MARKETING-AS-OF/STALE matrix. Competitor features cannot be verified this way — Koog, LangGraph, etc. live on GitHub, not locally; for those use the `deep-research` skill and the `references/competitor-verification-checklist.md`.

- **Do not include work-in-progress TPipe features in competitor comparisons.** If a TPipe capability is not yet shipped, it does not belong in a comparison page — not as a forward-looking note, not as an "in progress" annotation, not as a "5 days to ship" timeline. Including it implicitly scores against TPipe (the competitor is "already there") or sets an expectation the next release has to meet. The v3 TPipe vs Koog report mentions the "Harness class (~5 days to ship as of v2)" in a forward-looking closer — the tpipe-vs-koog page omits it entirely, per user directive. The next refresh should keep it omitted until the Harness class ships. If a WIP feature must be referenced for some reason, the user's explicit sign-off is required before it appears on the page.

### When a page is missing CSS rules (copy-paste error in the original), wholesale-replace the entire CSS block from a reference page — don't try to merge incremental fixes

When writing a new comparison page from scratch, the per-element styles (`.foo h3`, `.foo p`) tend to get copied from an existing page, but the **base/parent rules** (`.foo { ... }` itself) get missed. The result: a page where every child element has styling, but the parent has no background, border, padding, or border-radius — so the parent renders as raw text on the page background. The page looks structurally different from its row-mates.

**Observed (June 13, 2026, tpipe-vs-microsoft-agent-framework.astro):** the MAF page was missing the `.faq-item { background-color; border-radius; padding; border; }` base rule that every other comparison page has. The child rules (`.faq-item h3`, `.faq-item p`) were present, so individual text rendered, but the FAQ items had no card background and no border — the page looked structurally broken next to the others. The migration steps had similar but different styling (48px step numbers vs 32px elsewhere, gap 2rem vs 1.5rem elsewhere, bigger font-sizes) because the per-element rules were written by hand from a different mental model rather than copied from the reference.

**Wrong approach:** try to fix each missing rule incrementally. You will miss rules, the page will still look different from the reference, and you'll iterate forever.

**Right approach:** locate the equivalent CSS block in a reference page (typically the most recently updated page — `tpipe-vs-koog.astro` is the canonical reference as of June 2026), and **wholesale-replace the entire CSS block from the relevant section marker through the end of that section or the next section marker**. For the MAF fix, this meant replacing from `.migration-steps {` through the closing `</style>` with the Koog reference, with only the class-name differences (`.feature-maf` vs `.feature-koog`) preserved. One patch, not ten.

Operational test: after the patch, run `grep -A4 "^\s*\.faq-item\s*{" src/pages/comparison/<page>.astro` and confirm the base rule is present. Repeat for every base rule the reference page has (`.migration-step`, `.step-number`, `.step-content`, `.faq-item`, `.faq-item h3`, `.faq-item p`, `.see-also-card`, `.card-label`, `.card-title`, `.card-desc`, `.see-also-links`, `.cta-button`, `.cta-button.primary`, `.cta-button.secondary`). A blank grep result for a base rule that the reference has = the page is missing that rule = visual inconsistency.

Verification: after the wholesale-replace, screenshot the page via Playwright and run the vision tool on the FAQ section. The vision tool should confirm "each Q&A pair is contained within its own individual card with a thin border" — the canonical visual outcome. If the vision tool says "no card styling" or "text directly on background," the fix didn't land.

The wholesale-replace preserves the user's class-name variations (`.feature-maf` instead of `.feature-koog` in the mobile media query, etc.) by preserving the differences from the reference in the `new_string` of the patch. Don't wholesale-replace so aggressively that you rename the user's class names — only the CSS values change.

### Runtime-narrative facts need the same sweep-all-pages treatment as verdict counts

When a TPipe feature fact (runtime narrative, Junction recipe names, KillSwitch trip reasons, DistributionGrid routing directives, any shared truth) gets re-stated across multiple pages, the user-issued correction applies to ALL the pages, not just the one the user is viewing at the moment. The pattern is identical to the verdict-count drift pitfall: a single fact lives in N independent prose blocks across N files, and a fix at one site doesn't propagate.

**Workflow:** when the user says "fix the runtime narrative" or "make sure claim X is accurate" or "audit the X claim" and the fact is repeated across pages, sweep every comparison page (and the homepage table at `src/components/comparison/ComparisonTable.astro` if it lists competitors) before declaring complete. The minimum-correction principle still applies per-site — single-sentence acknowledgment, no paragraph rewrite — but the sweep must be total.

**Empirically observed (June 13, 2026):** the user's correction "make sure you don't say GraalVM is the only runtime" applied to all 8 comparison pages (MAF, Koog, AutoGen, LangChain, LangGraph, Google ADK, CrewAI, A2A Protocol) plus the index.astro hub card. The first pass fixed 3 of 8. The follow-up sweep (after the user invoked the mcsmarm cleanup persona) added the same single-sentence acknowledgment to the remaining 5 plus the index card highlights. The single-sentence rule is correct; the missing step was the sweep across the page set, not the prose shape at each site.

**The audit grep:**

```bash
# Find every site that needs the runtime-narrative acknowledgment
grep -nlE "(GraalVM Native|graalvm)" src/pages/comparison/*.astro src/components/comparison/*.astro 2>/dev/null
```

For each match, apply the canonical-runtime-narrative line at the affected site. Don't rewrite the surrounding paragraph. Don't add the KMP-project framing unless the user asks.

**Generalization:** any time the user issues a fact-level correction about TPipe, audit the page set for the same fact at every site. Verdict counts, runtime framing, recipe names, feature lists, JSON-LD strings — all are independent prose blocks across the page set and all drift independently. The user reviewing one page is not the same as the user reviewing the whole site; treat the correction as site-wide by default.

### When writing a new comparison page, copy the CSS structure of the canonical reference page wholesale — don't invent your own styling

The canonical reference page (currently `tpipe-vs-koog.astro` as of June 2026) defines the visual baseline: migration steps with 32px step numbers at 1.5rem gap, 1rem h3 font-size, 0.875rem p font-size; FAQ items with the `.faq-item { background-color: var(--color-surface-container-low); border-radius: var(--radius-xl); padding: 1.5rem; border: 1px solid var(--color-outline-variant) }` base rule; See Also cards at the same border-radius / padding / background-color pattern; CTA buttons with primary + secondary states; FAQ-grid using `display: grid; gap: 1.5rem`; etc.

**Prevention:** at page-write time, copy the entire CSS block from the reference and only adjust the class-name variations (`.feature-maf` instead of `.feature-koog` in the mobile media query, etc.). Do NOT hand-write the CSS from a different mental model. The result of hand-writing is a page that's structurally broken next to the others (different step-number sizes, missing FAQ card background, wrong border-radius values, wrong grid/flex choice on `.faq-grid`).

**Empirically observed (June 13, 2026, tpipe-vs-microsoft-agent-framework.astro):** the MAF page was hand-written with 48px step numbers, 2rem gap, 1.25rem font-sizes, and missing the `.faq-item` base rule. The result rendered with oversized step circles, FAQ items as raw text on the page background, and See Also cards at a different border-radius than the rest of the site. The remediation was a wholesale CSS replacement from the Koog reference — but the prevention is to copy the reference structure at write time, not invent your own and hope.

The wholesale-replace pitfall below covers remediation. This pitfall is the prevention.

### Patching with `old_string` that doesn't capture the full line leaves orphan text fragments

When the text you want to replace ends mid-line (e.g., "GraalVM Native Image ships as a 50MB binary — no Python int" — the `int` is the start of a word, not the end), using `old_string="...no Python int"` and replacing it with new content causes the rest of the word (e.g., "erpreter, no JVM at runtime.") to remain as orphan text on the next line. The build succeeds, the page renders, and a vision tool may or may not flag the orphan text — but the page is broken.

**Wrong approach:** patch with a partial string and hope the orphan doesn't matter. The build will pass, the user will notice, and you'll patch again.

**Right approach:** before patching, `read_file` the surrounding lines to see exactly where the line ends. If the line ends at `</p>`, capture the full content up to `</p>`. If the line is a paragraph that flows across sentence boundaries, capture from a unique starting point to a unique ending point (a period, a `</p>`, a section marker). The patch should always restore the file to a clean state.

**Workaround if you forget:** if a patch leaves orphan text, follow it immediately with a second patch that captures the orphan + the next clean boundary, and removes the orphan. The vision tool workflow (screenshot the page, run `mcp_MiniMax_understand_image`) will catch orphan text, but the Playwright `boundingBox()` inspection will not — orphan text adds height to the page but doesn't change card dimensions measurably.

**Observed (June 13, 2026, tpipe-vs-langchain and tpipe-vs-google-adk):** the langchain page's intro paragraph had the runtime-narrative text ending at "no Python int" (the `int` is the start of "interpreter" — the line continues to "erpreter, no JVM at runtime."). The patch replaced up to "no Python int" with new text, leaving "erpreter, no JVM at runtime.</p>" as orphan text on the next line. The same pattern recurred on the google-adk page. Both required a follow-up patch to clean the orphan. The fix: read the file's surrounding context before patching, capture the full sentence.

- **Persona invocation: when user names a different persona for cleanup, switch fully to that persona's voice**

The user has multiple personas registered (BigWang, Apex, mcswarm, etc.) and may invoke one explicitly mid-session ("mcsmarm I'm calling on you to clean up bigwang being bigwang"). The invocation is a directive to switch voice, not a topic change. The cleanup persona's voice is the opposite of the producing persona's voice — BigWang is verbose and confident, so mcswarm-style cleanup is brief, focused, and aimed at the specific mess left by BigWang. Don't keep producing BigWang-style content after the user has invoked a different persona; the new persona's voice is the new operating mode until the user says otherwise.

**Personas seen in the comparison-page workflow:**

- **BigWang** — the producer. Verbose, confident, smug-startup-CEO voice, brief/direct. Generates long rewrites, explanations, and big rewrites. Default persona for comparison page work. Risky for fix-passes because the voice pushes toward "while I'm in here, also explain why" rewrites.
- **mcswarm** (cleanup) — the opposite of BigWang. Brief, surgical, focused. "Yeah I'm on it" acknowledgment, focused execution, clean summary at the end. Invoked by the user when BigWang has over-rewritten and the user wants the mess cleaned up. The mental model: BigWang produces the draft, mcswarm produces the diff. Switch into mcswarm voice the moment the user invokes the name, don't keep BigWang's voice running.
- **Apex** — TTT's senior coding AI. Architecture-obsessed, file:line references, no hedging. Use for audit/review work on the comparison pages, not for marketing copy generation.

**Observed (June 13, 2026):** the user invoked "mcsmarm" (likely the same as mcswarm — the user typed it slightly differently) explicitly after a series of BigWang-style over-rewrites that the user had been correcting ("vomit a bunch of it's not x it's Y crap"). The expected response: switch to brief, focused, surgical cleanup. Don't continue the verbose BigWang pattern. The persona switch is a one-line acknowledgment ("Yeah I'm on it, let me sweep") and a focused execution.

When the cleanup is done, give a clean summary of what changed and the verification (HTTP status, hedge-phrase audit, vision tool confirmation of visual consistency). Don't add new prose or new section intros — the user is reviewing the cleanup, not asking for more.

The cleanup-mode voice rule: brief, focused, surgical. No meta-commentary about "what I should have done" or "lesson learned" — those go in the skill, not the response. The user is the operator; they want results, not the cleanup agent's autobiography.

## What this skill is NOT

- Not a layout/CSS redesign — only copy
- Not a SEO audit — though competitor name in title/URL is preserved for SEO
- Not adding new comparison targets (out of scope)
- Not updating the docs site at `src/content/docs/` (synced from TPipe repo at build time per `amplify.yml`)
- Not writing the marketing voice for blog posts or pricing pages (those are different skills with different rules)
- Not verifying competitor claims as a hard gate — the user owns the call on what stays; verification is a tool, not a blocker

## See also

- `references/competitor-verification-checklist.md` — what to verify for each major framework (LangChain, LangGraph, CrewAI, Google ADK, AutoGen, A2A, Koog) before rewriting
- `references/competitor-add-workflow.md` — the Step 0 research half of adding a new comparison target: pre-flight scan, versioned-report pattern, hub wiring notes, JSON-LD. **Use when the user asks to add a new competitor card to the site (not rewrite an existing one).**
- `references/competitor-page-build-checklist.md` — the page-build half of adding a new comparison target: the 7 touchpoints in `index.astro`, the CSS class rename, the verdict-color hex discipline, the link-target audit, the JSON-LD dateModified discipline. **Read this alongside `competitor-add-workflow.md` when shipping a new card.**
- `references/verdict-count-audit.md` — the verdict-count sweep pattern: where the count string appears (5 locations including the hub card), the audit grep, the source-of-truth order (table first), and the failure modes observed on the Koog page June 13, 2026. **Run before declaring any comparison page complete, or any time the user reports a stale count.**
- `references/css-uniformity-audit.md` — the CSS uniformity audit + wholesale-replace remediation pattern. Use when a page looks visually different from its row-mates — missing base rules in the `<style>` block, wrong step-number sizes, FAQ items without cards, See Also cards without borders. Includes the audit grep, the wholesale-replace procedure, and the operational test for completeness.
- `references/ttt-site-blog-urls.md` — ttt-site quirk: blog post URLs include the date prefix (`/blog/YYYY-MM-DD-slug/`)
- `references/readme-as-product-mechanism.md` — how open source projects like oh-my-pi drive GitHub traction: the README-as-landing-page pattern, badge walls, vague benchmark claims with citation targets, fork momentum, personal brand infrastructure, and the specific gap between TPipe's current README and the pattern. **Use when the user asks about competitor traction mechanisms or how to drive GitHub stars.**
- `scripts/hedge-phrase-audit.sh` — verification script for the blacklist-phrase audit, exit non-zero on any match
- `ttt-site-code-snippets` — TPipe API accuracy verification and Shiki syntax highlighting for code samples on Astro pages. **Use this skill when the user reports a code sample "isn't accurate" or asks for syntax highlighting on a `<pre>` block.** Includes a verified BedrockPipe + Chain-of-Draft template and a sweep script that catches invented APIs across all pages.
- Related skills: `ttt-site-blog` (different voice rules), `ttt-site-pricing`, `ttt-site-code-snippets`, `humanizer`, `plan`
