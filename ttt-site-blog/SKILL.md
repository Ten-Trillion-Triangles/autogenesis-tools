---
name: ttt-site-blog
description: Write technical tutorial blog posts for the TenTrillionTriangles/TPipe marketing site in Apex's preferred style — BigWang directness with human-blog terseness, no LLM hedging, no copula avoidance, code-first structure. Use when asked to write or rewrite a TPipe blog post, when an existing draft reads as "too AI," or when a blog article has the "X, not Y" pattern creep. Triggers on "write a blog post for ttt-site," "draft a TPipe tutorial," "review the blog article voice," and any time a TPipe blog post is being authored, audited, or rewritten.
---

# Writing TPipe blog posts in Apex's preferred style

This skill captures the voice and structure conventions for blog posts on the ttt-site (the TPipe marketing site at tentrilliontriangles.com). Apex is the audience and the editor.

## When to use this skill

- Writing a new blog post for ttt-site
- Reviewing or rewriting an existing TPipe blog draft
- A draft reads as "too AI" or "too LLM"
- The framing is "framework comparison" rather than "tutorial"
- A blog article has the "X, not Y" pattern creep that Apex hates
- A draft has consecutive "X is not Y. X is Z." sentences (the FIRST-CLASS tell — see `references/voice-and-style.md`)
- A draft claims reasoning pipes are part of Developer-in-the-Loop (they are a separate subsystem) — see `references/tpipe-api-accuracy.md`
- A draft cites specific token counts or production numbers for TPipe/Autogenesis that haven't been verified against the user's current numbers
- A draft cites source code with absolute local paths (`/home/cage/Desktop/Workspaces/...`) instead of the canonical public repo URL. See "Local file paths in published content — link to the public repo instead" pitfall below.
- Apex says "this reads off" or "this is too verbose" or "more human"
- The user asks for a visible "humanizer pass" on a draft — the audit becomes a deliverable, not just an internal step. See "The visible humanizer audit" below.
- The user asks for a hero image prompt or the frontmatter declares an `image:` path with no file behind it. See `templates/hero-image-prompt.md` and the "Hero image wiring is incomplete" pitfall.

## The one rule

TPipe blog posts are tutorials first, manifestos never. They teach a reader how to do a specific thing with TPipe. They are not framework pitches, not vendor comparisons, and not "here's why TPipe is better" essays.

If you find yourself writing "in this article we will explore" or "this is the difference between X and Y" — stop. Rewrite as "here's how to do X. here's the code. here's what each line does."

## The voice

- BigWang confidence: declarative, no hedging, "I do X" not "you might consider X"
- Human-blog terseness: code first, description after, short paragraphs
- No manifesto opener. No "in this post we will explore" framing
- The "things that bit me" / "pitfalls" section is the most authentic voice
- Real code from production (Autogenesis WriterAgent is the canonical reference)
- Don't over-explain. If a setting name is self-descriptive, one sentence is enough
- Sentence fragments are fine. Em-dashes are fine. Contractions are fine.
- **Prefer specific named contemporary cultural references over generic abstract descriptions.** "Reddit mods marking tickets solved because they hit the lock button" lands harder than "forum neckbeards closing threads they can't answer." When BigWang voice paints a picture, name the thing — Reddit, ProductHunt launches, Stripe Atlas incorporation, the actual product names people recognize. Generic labels ("users," "community," "people") read as AI filler. Specific labels ("the volunteer brigade moderating tickets they can't answer — Reddit in a trench coat charging SaaS prices") are the voice. Same principle for the company page, see-also copy, and GitHub Discussions posts on the ttt-site repo.

## Patterns to avoid (the copula avoidance list)

These are the LLM tells Apex has specifically called out. Grep every draft for them before showing the user. Full inventory with rewrites in `references/voice-and-style.md`.

**The big offenders:**
- `X, not Y` framing: "X is not Y", "it's a style choice, not a different pattern"
- **`X is not Y. X is Y.` double-sentence** — the explicit "is not X / is Y" pair, which reads as a defensive hedge even when the two sentences are short. Apex calls this out as a first-class tell. The fix is always to lead with the positive, then drop the negative, then drop the second sentence if it just restates the first. Before: "The LLM is not a conversational partner. The LLM is a left-to-right token predictor." After: "The LLM is a left-to-right token predictor. There is no hidden planner." Same point, no pattern. The 2-post pair (Reasoning Pipes + KillSwitch) shipped in June 2026 had this pattern appear 6 times across both drafts and had to be re-cleaned in three humanizer passes.
- `Use A not B` directives: "Use the typed model enum, not the string"
- `Instead of X` / `Rather than X` constructions
- `Skip it for [cases]`
- `Without X, Y doesn't do much`
- `X is not optional` / `X is not required`
- `It shouldn't be X` / `It shouldn't have Y`
- `This is the X` topic introducers ("This is the boundary", "This is the bridge", "This is how")
- `This is the first/second/third benefit` counting
- `Let me walk you through` / `Let me show you`
- Overuse of `doesn't`, `won't`, `isn't`, `aren't`

**The fix is always the same:** say what to do (positive), not what not to do (negative). Show the right thing first, then show the consequence of the wrong thing as a separate beat if needed.

## The structure for a TPipe tutorial blog post

```
1. Lead with the rule in 2-3 sentences (no manifesto)
2. Show the simplest possible code
3. Walk through what each setting does (terse)
4. Real production example (Autogenesis is canonical)
5. Chaining pieces into a Pipeline (if relevant)
6. End with a concrete closer that names the pattern
```

No "When the builder wins / When the scope wins" sections. No FAQ-as-essay. No "decision framework" as a list. The structure is a tool, not a religion — skip sections that don't apply.

**Important: the scope DSL section was cut from the pipeline post mid-session.** The "Same pipeline, two ways" section introduced Manifold/worker/pipeline DSL content into a pipeline tutorial. Apex called it out: "no dsl is used or supposed to be used here." The scope DSL is ONLY relevant as the composition boundary — how a builder-built Pipeline gets handed to a Manifold worker. It is NOT a standalone section in a pipe/pipeline article. If you're writing about pipes, stay on pipes. If you're writing about containers, write about containers. Don't do both in one post unless that's genuinely the topic.

### Variant: code-heavy technical posts (Reasoning Pipes, KillSwitch)

For posts where the entire argument is "here's how the code does X architecturally," use the punchline-code structure. The code IS the thesis, not the illustration. The reader walks away having seen the actual implementation, not a paraphrase.

```
1. Origin story (1-2 paragraphs) — real stakes that motivated the feature, with specific numbers and consequences. The KillSwitch post's "billion-token burn" lead is the canonical example.
2. The contrast — what other frameworks get wrong, or what the problem actually is (often worse than expected)
3. THE CODE — the entire file or the punchline block, verbatim, with file:line citations. This is the load-bearing section. The reader needs to see the actual code first.
4. First architectural punchline — one structural element (a type, a field, a callback signature) that proves the thesis in isolation
5. Where the code calls the code — the check site, the propagation site, the catch site
6. Second architectural punchline — a defensive pattern (catch-and-rethrow, accumulator, type-level enforcement) that defends the first
7. The propagation story — how it scales through the container hierarchy
8. What it is and what it does better than the alternative — comparison framed positively, no "is not X is Y"
9. Practical setup — DSL builder or example wiring
10. The bigger picture — bridge to the next post in the series
```

The two post examples that match this variant:
- **Reasoning Pipes** (June 2026): origin story (token-prediction framing) → JSON field order pattern → `doesLegendExist` boolean punchline (`ModelReasoning.kt:454-467`) → `Pipe.kt:1944` injection text → other reasoning-method data classes (StructuredCot, MethodActorResponse, ChainOfDraft) → closer to next post.
- **KillSwitch** (June 2026): origin story (billion-token burn + AWS SDK silent timeout) → what frameworks get wrong (debt accumulation + crash billing) → 66 lines verbatim → `Nothing` type punchline → `checkKillSwitch` → catch-and-rethrow carve-out (`Splitter.kt:778-782`) → root-down accumulator → propagation → comparison to budget caps → setup → bridge to next post.

The signature move: find one specific comment, one specific boolean, one specific catch block that exemplifies the entire thesis, and put it in front of the reader before the architecture argument. For reasoning pipes it was the `doesLegendExist` field. For KillSwitch it was the 66-line file ending in `throw`. The reader's first reaction should be "oh, that one line does it" — the rest of the post is just unpacking why.

### Variant: opener posts (foundation, teases a deep-dive)

For posts that introduce a TPipe concept at the data-structure or mechanism level and explicitly set up a more in-depth follow-up, use the opener structure. The reader gets the foundation today. The follow-up post delivers the full pipeline / production build. The opener establishes the API surface, the data shapes, and the read/write contract; the deep-dive wires them into a working system.

The signature example: **ContextWindow and ContextBank** (Post 8, shipped 2026-06-14) was the opener for **Memory Agents** (Post 9, queued). The opener covered the data classes, the singleton, the mutex contract, the read/write API, and a real Autogenesis code excerpt showing the pattern in production. It did NOT build a full memory agent pipeline — that work belongs to Post 9.

```
1. Lead with the two-scope rule (the data class, the singleton, the seam between them)
2. Show the simplest possible code that exercises both — create, mutate, persist
3. Walk through what each slot / mutex / field actually does
4. Lift the curtain on the production pattern — one Autogenesis excerpt, file:line cited
5. State the decision rule for choosing scope (local vs banked)
6. Bridge to the next post with a concrete teaser, not a generic one
```

The opener structure is deliberately lean (1500-2000 words, not 3000+). The deep-dive is where the heavy lifting happens. The opener's job is to make the deep-dive's first paragraph land.

**When the user asks for an opener / "first in a series" / "foundation for a more in-depth tutorial later," this is the variant. Do not deliver the full pipeline in the opener.** The user said it themselves: "This will be an opener to a more in depth tutorial later on how to make memory agents that are able to automatically keep a lorebook and memory system up to date in real time." The phrase "more in depth tutorial later" is the signal — split the work across two posts.

**Bridge to next post — be concrete, not generic.** The opener's closer should name the deep-dive's topic specifically, describe what data structures / mechanisms from the opener it will build on, and give the reader a reason to come back. The working pattern from the ContextWindow/ContextBank opener: "This is the foundation. The next post in this series covers the full memory agent pattern: a pipeline that runs after every generation, extracts structured entities from the new context, folds them into the lorebook, and persists the result — all automatically, all in real time, with no human in the loop touching the lorebook by hand. The data structures are the same. The bank is the same. The lorebook slot is the same. The difference is a pipeline that turns generated text into structured, retrievable memory on every turn." That's concrete, names the data structures from the opener, and ends the article. Not a generic "the substrate has many components" line — that gets rejected as AI padding.

**Update the in-flight queue when you ship an opener.** The deep-dive is now the active next post. Add a spec to `references/in-flight-posts.md` for the deep-dive that builds on the opener's data structures, with the opener's file path and the bridge text as the source for the deep-dive's first paragraph.

## The schema requirements (from src/content.config.ts)

Every blog post needs:
- Frontmatter: `title`, `description`, `author` ("Richard Wang"), `publishDate`, `updatedDate`
- Optional: `tags`, `image`, `featured`, `wordCount`
- For tutorial posts: `hasFAQ: true`, `hasHowTo: true`, `schemaTypes: ["FAQ", "HowTo"]`
- `faqItems` array (6-7 items typical): `{question, answer}`
- `howToSteps` array (5-7 items typical): `{name, text}`
- Filename: `YYYY-MM-DD-slug.md` in `src/content/blog/`
- The Astro content collection schema is at `src/content.config.ts` — check it before writing

The FAQ is asked-from-outside framing, not the article's voice. Don't let FAQ patterns leak into the body. The howTo is imperative ("Do X. Y happens.") — also not the article's voice.

## The humanizer + BigWang two-pass workflow

The ttt-site-blog voice rules and the humanizer skill are applied in two passes, not one. Drafting with both simultaneously produces mush — the humanizer strips AI-isms and the BigWang re-adds the punch, but if you try to write both voices in the same pass, they conflict and the result reads as neither.

**Pass 1: Draft in BigWang voice.** Lead with the rule. Show the code. Walk through terse. The voice rules in the section above apply.

**Pass 2: Run the humanizer skill on the draft.** Strip the AI-isms. This is where the "X is not Y. X is Y." patterns, the "stands as a testament," the "serves as" get caught and rewritten.

**Pass 3: Re-BigWang the result.** The humanizer pass often softens the punch. Re-apply the BigWang voice: short punchy sentences, real stakes, direct claims, no hedging. The rule-of-three may sneak back in here. Watch for it.

**Pass 4: Re-run humanizer to catch any AI-isms the BigWang re-pass reintroduced.** This loop usually runs 2-3 times before the draft is clean. Trying to skip it produces a draft that reads as "AI wrote this."

The 2-post pair (Reasoning Pipes + KillSwitch) shipped in June 2026 was processed through this loop. Both posts went through three humanizer passes each. The catches: `X is not Y. X is Y.` pattern appeared 6 times across both posts and had to be re-cleaned each pass; the rule-of-three got re-added by the BigWang re-pass and had to be re-stripped; one `It is not a feature but a termination architecture` survived three passes before being caught and rewritten as `KillSwitch is termination architecture, not a feature`.

## The visible humanizer audit

When the user explicitly invokes the humanizer skill (or asks for "a humanizer pass," "make it sound more human," "de-AI this," "this reads like AI"), the humanizer pass is a deliverable, not an internal step. The user wants to see what you found and what you changed. The workflow is:

1. **Run the grep pass.** Search the draft for the TTT first-class tells (`is not`, `isn't`, `won't`, `doesn't`, `aren't`, `not on`, `not a`, `not the`, `not in`) and the manifesto phrases (`In this`, `Let's`, `paradigm`, `leverage`, `tapestry`, `landscape`, `seamless`, `cutting-edge`, `delve`, `robust`, `harness`, `underscore`, `elevate`, `empower`, `unleash`). The full list and the grep commands are in `references/voice-and-style.md`.
2. **Identify the rule-of-three fragments.** Look for three short declarative sentences in a row that name the same kind of thing ("The window is X. The bank is Y. The mutex is Z."). Combine or trim.
3. **Patch each occurrence with a targeted edit.** Use `patch` with `old_string`/`new_string`. The patch is more credible than a full rewrite because the diff is visible.
4. **Re-verify the dev server still returns 200.** `curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:4321/blog/<slug>/`. The YAML is the most fragile part; any whitespace drift in faqItems[] or howToSteps[] 404s the page silently.
5. **Show the user three things:**
   - **What you changed.** A diff or before/after per section. Group by category (TTT first-class tells / rule-of-three fragments / listicle bloat / etc.) so the user can see the class of fix, not just the surface edit.
   - **What's still arguably AI.** Honest answer. The em dashes that remain, the structure that still feels algorithmically clean, the closer that could use more punch. Don't claim the draft is clean if it isn't.
   - **A one-sentence summary of the remaining work.** "Want me to keep going, or do you want to read the post first and come back with more direction?"

The user is a sharp reader. The audit is credibility — they will grep the patches. Show your work.

## The BigWang closer needs an opinion, not a recap

The closer is the spot where AI drafts tip their hand the most. A clean description that ends with "That's the next post" reads as a re-teach, not a closer. The BigWang closer has three parts:

1. **A definitive opinion about why this matters.** Not "this is a useful feature." An actual claim. The working pattern from the ContextWindow/ContextBank opener: "Most production agents have no memory worth mentioning. They re-derive context from a vector store on every call, return the same three chunks for every query, and forget what happened in the last session the moment it ends." That sentence is an opinion, not a description.
2. **A specific failure mode.** "Return the same three chunks for every query" is concrete. "The system has limitations" is generic. Name the failure.
3. **A declarative statement of what the next post delivers.** "The memory agent pattern is the fix: a pipeline that writes its own lorebook every turn, automatically, so the next turn starts where the last one left off." The user knows what they're getting. The reader knows whether to come back.

The anti-pattern: "The data structures are the same. The bank is the same. The lorebook slot is the same. The difference is a pipeline that turns generated text into structured, retrievable memory on every turn. That's the next post." That was the first draft of the ContextWindow/ContextBank closer. It reads as a fragment list. The fix: replace the "X is the same" repetition with one declarative line, then add the opinion. The fragment list looked thorough but the opinion did the actual work.

## The two-stage pre-write grounding workflow

For TPipe feature blog posts (new container, new primitive, new wiring), the user runs a labeled two-stage pre-write process before any draft lands. The skill is named "grounding" because the deliverable is the working document that informs the blog, not the blog itself. Skipping either stage produces a post that fails the audit.

**Stage 1 — End-to-end technical grounding.** The agent reads the relevant TPipe source end-to-end and internalizes the class. Deliverable: a working understanding of the class, its loop structure, its LLM-facing magic contracts, its public surface, and its file:line locations. Trigger language is explicit: "Goto where X is on this system and learn all about Y end-to-end. This is required context before the next blog article I have you write for our site."

**Stage 2 — Concept + competitive + TPipe-superpowers.** The agent breaks down the core concepts in greater detail, compares how the feature is different from agent harness loops of today (LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Google ADK, LlamaIndex), and breakdowns the TPipe superpowers the feature composes. Trigger language is explicit: "This is the second stage of grounding to understand how to sell it as a concept, but also how to explain in tpipe terms."

**Stage 3 (implicit) — Write the blog.** Drafted in BigWang voice using the existing voice, structure, and two-pass humanizer workflow documented below.

The two stages are about not skipping the work. Stage 1 prevents the cite-the-marketing-component failure (bigwang pitfall #6). Stage 2 prevents the copula-avoidance double-sentence when positioning against competitors — the comparison produces a specific delta, not a "X is not Y. X is Y." dance. See `references/grounding-stages.md` for the full template and per-stage deliverable format. See `references/agent-harness-competitor-axes.md` for the standing comparison axes (durable; the specific facts about each framework are time-bounded and re-verified per the verify-everything rule in bigwang).

When a future session is asked to write a TPipe feature blog post and there is no fresh stage 1 or stage 2 grounding, run the relevant stage before drafting. Do not draft from stale memory.

## The workflow for writing a new TPipe blog post

1. **Confirm the two-stage grounding is fresh.** Stage 1 (end-to-end source read) and stage 2 (concept + competitive + TPipe-superpowers) must be on disk for the feature. If the user is starting a new post without prior grounding, run the relevant stage first. Do not draft from stale memory.
2. **Identify the topic** from the backlog (hindsight memory has the running list) or as requested
3. **Ground technical claims in the actual TPipe source.** Before writing about any TPipe API, find the function in `/home/cage/Desktop/Workspaces/TPipe/TPipe/src/main/kotlin/`, read it, and verify the description matches what the code actually does. Don't write from memory of the API — write from the function definition. If a claim can't be sourced, it doesn't ship. See `references/tpipe-api-accuracy.md` for the corrections from this session that future drafts must not repeat.
4. **Find real production code** in Autogenesis or TPipe source — this is the canonical reference, not invented code
5. **Look at competitor tutorials** (LangChain, LangGraph, CrewAI, AutoGen) for style reference if needed — see `references/competitor-style-reference.md`
6. **Draft the post** following the structure above
7. **Grep the draft for the bad patterns** (the `references/voice-and-style.md` has the exact grep commands)
8. **Add a `## Related posts` section at the end of the body.** Format: bolded title link + em-dash + one-sentence description per item. Four links: next in series (if the post exists), prior in series (if the post exists), and 2-3 related posts. In-body forward references ("The next post in this series covers X") should be updated to actual markdown links to the next post when it exists. Forward references to not-yet-written posts stay as plain text. Cross-link the post to the rest of the blog for SEO and reader continuity — every post in the series should link to the others, and every post should link to its conceptual foundation (substrate, P2P, headless, memory, pipeline, etc.).
9. **Patch each occurrence** using the rewrites table
10. **Verify the dev server serves the post** — Astro hot-reloads, so just curl `http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/`
11. **Show the user**

Step 3 is not optional. Apex has corrected technical descriptions of `setModel` and `setTokenBudget` in the same session the posts were drafted. Writing from memory produces plausible-sounding but wrong content. The source is in the same workspace, takes 30 seconds to read, and is the only ground truth.

Step 7 is not optional either. The grep-and-patch pass is what turns a draft from "AI wrote this" into "a human wrote this."

Step 12. **Update config files for crawler visibility** — see "Publishing & crawler visibility" below. The post-render step is small but specific: one file gets a manual entry, everything else is auto or blanket.

## Publishing & crawler visibility

The post-render step after a new blog post lands. The user has said "only if needed" — this is a tight, surgical step. Do not over-update. Do not add new config files. Do not pre-emptively bump `updatedDate`. Each change has a specific, verifiable reason; everything else is unchanged.

**Config file inventory (as of 2026-06-17):**

- **`public/robots.txt`** — LLM bot allowlist. Blanket `Allow: /` plus per-bot entries (OpenAI=GPTBot+OAI-SearchBot+ChatGPT-User, Anthropic=ClaudeBot+Claude-User+Claude-SearchBot, Perplexity=PerplexityBot+Perplexity-User, Google-Extended, Bytespider, CCBot, cohere-ai, cohere-training-data-crawler, Applebot-Extended, Amazonbot, DuckAssistBot, Meta-ExternalAgent+Meta-ExternalFetcher, Omgilibot+Omgili, YouBot). Plus `All-llms: https://tentrilliontriangles.com/llms.txt`, `Content-Signal: search=yes, ai-input=yes, ai-train=yes`, `Content-Usage: ai=y`. **Update needed: never.** New posts are auto-visible to every allowed crawler via the blanket `Allow: /`. The DisallowAITraining directive is intentionally omitted (absence = allow).
- **`public/llms.txt`** — LLM-readable site map. Hand-maintained list of blog posts, docs, comparisons, landing pages, canonical, owner. **Update needed: yes.** Add the new post at the top of the `## Blog` section in the existing entry format: `- [Title](URL): DESCRIPTION`. Description should match the frontmatter's announcement voice — short, declarative, name the structural deltas. The file lives in `/public/` so dev server reflects updates immediately. The Optional section already links to the sitemap and robots.txt; no change there.
- **`public/llms.txt` after-build drift (static-server mode).** When the dev server is unavailable and the site is being served from `dist/client/` via a static file server (see `references/astro-dev-server.md`), `dist/client/llms.txt` is a snapshot of `public/llms.txt` taken at the last `npm run build`. Edits to `public/llms.txt` made after the build are invisible on the static server until the next build. After every `llms.txt` edit in this mode, verify with `wc -c public/llms.txt dist/client/llms.txt` — if they differ, run `npm run build` before declaring the audit done.
- **`llms.txt` Blog section is strictly reverse-chronological.** When you add an entry via `patch`, the new entry must go at the top of the Blog section — NOT appended at the end. If you append at the end, reverse-chronology breaks. If you insert in the middle of an existing date cluster (e.g. mid-06-XX), the sort breaks. The reliable recipe:
  1. Pull all blog entries by extracting every line that starts with `- [` between the `## Blog` and `## Canonical` markers.
  2. Extract the `/blog/YYYY-MM-DD-…/` slug from each line via `re.findall(r"/blog/(\d{4}-\d{2}-\d{2})-", line)`.
  3. Sort the (date, line) pairs by date descending.
  4. Write back preserving all other sections unchanged.
  Doing it via `patch` with `old_string`/`new_string` is faster when you only add ONE entry to a known spot, but if two entries are missing (or the order has drifted from prior patches), use the deterministic re-sort pass — a `patch` insertion will silently produce an out-of-order file. After any `llms.txt` edit, verify the final order with: `re.findall(r"/blog/(\d{4}-\d{2}-\d{2})-", blog_section)` and assert it equals `sorted(dates, reverse=True)`. Example drift observed this session: a `patch` to insert the 07-01 post wedged it between 06-16 and 06-15, breaking reverse-chronology silently. The fix was a full re-sort pass after both insertions.
- **`public/_redirects`** — URL redirects. **Update needed: never** for new posts. Only edit if the new post has URL-migration concerns (rare; consult user).
- **`src/pages/sitemap.xml.ts`** — Astro endpoint that generates `/sitemap.xml` from `getCollection('docs')` + `getCollection('blog')`. The blog entries map to `https://tentrilliontriangles.com/blog/${post.id}/` with `priority: 0.7` and `lastmod` from `updatedDate ?? publishDate`. **Update needed: never.** Auto-generates on every build. Verify with `curl -s http://localhost:4321/sitemap.xml | grep <slug>` before claiming shipped — the dev endpoint reflects content collection changes immediately.
- **`astro.config.mjs`** — site URL + integrations. **Update needed: never** for blog posts. Only edit if adding a new integration.

**What to flag, not silently fix.** JSON-LD `dateModified` and the meta `dateModified` on the post are sourced from frontmatter `updatedDate`. The user's edit may or may not warrant bumping it. **Flag in the wound report, ask before changing.** Today's edit date is `2026-06-17`; bump `updatedDate: 2026-06-16` to `updatedDate: 2026-06-17` only on user confirmation. The untracked post has no committed history to anchor the date claim.

**The "only if needed" principle.** When the user says "make sure all config files are updated (only if needed)," they mean it. Run the audit. Touch only what needs touching. The wound report lists exactly what changed and why; everything else is unchanged. Resist the urge to be thorough by adding things — the user has been clear.

The inspection discipline. After every post edit, leave the dev server up. Verify 200 OK on the post URL. Do not preemptively kill the server "to clean up." The user wants to inspect at their own pace. The `persona/mcsmarm` skill's pitfall #13 captures this from the editor's side; the rule applies here too. If the server was killed, restart it via `terminal(background=true)` (NOT `nohup ... &` foreground — Hermes blocks shell-level background wrappers), wait for 200 OK, hand back the URL + PID + session ID.

**Audit pattern before claiming publishing is done.**

```bash
# All crawlers allow the new URL (blanket Allow)
curl -s http://localhost:4321/robots.txt | grep -E "^Allow: /" || echo "no blanket allow"

# Sitemap includes the new slug
curl -s http://localhost:4321/sitemap.xml | grep "<slug>"

# llms.txt includes the new slug at the top of Blog
curl -s http://localhost:4321/llms.txt | grep -B1 "<slug>"

# Post itself returns 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4321/blog/<slug>/
```

All four must hit. If llms.txt is missing the entry, patch it. If sitemap is missing the URL, check that the post file is in `src/content/blog/` (it should be — auto-generation is from the collection). If post returns non-200, kill the stale dev server and restart before diagnosing further (see `references/astro-dev-server.md`).

## Common mistakes

- Treating the post as a "framework comparison" or manifesto
- Letting the FAQ/HowTo voice leak into the body
- Inventing code instead of pulling from Autogenesis WriterAgent or TPipe source
- Over-explaining what the framework IS instead of showing how to USE it
- Marketing language like "paradigm shift," "next-generation," "leverage"
- Padded paragraphs where one sentence would do
- "The verdict" or "the rule, restated" sections that just repeat the lead
- **Section headers that sound like listicles.** "A few things that bit me," "The rule, restated," "What's next," "X things you need to know" — these are LinkedIn content patterns, not blog post structure. Apex rejected "A few things that bit me" mid-session: "This is nonsense." Use direct section titles that describe the topic: "init()", "Token budget", "Model IDs", "Pipe names". The content speaks for itself. No framing header needed.
- **Closing with re-taught content.** The article already covered everything in the body. A closing section that re-examines it just pads the length and signals AI wrote it. Apex rejected this twice: "This is just weird and doesn't make sense," "That's not a closer." End with a concrete summary that names the pattern, not a re-teaching pass. The working pattern: "That's the builder pattern for pipes and pipelines. Config the pipe, chain into a Pipeline, wire the control flags, call init(). The same pattern applies to every pipe in TPipe — the settings change, the structure doesn't." That's concrete, names the structure, ends the article.
- **"What's next" as a generic teaser.** "The substrate has many components. Each of those has its own deep dive." reads as AI padding. If there IS a next article, name it specifically with a real teaser. If there isn't, don't write it. Apex rejected this mid-session.
- **Stale FAQ/howToSteps after content cuts.** When content is removed from the article body, the corresponding FAQ items and howToSteps in the frontmatter become misleading — they reference DSL content that no longer exists in the body. Apex caught this: the "Same pipeline, two ways" section was cut, but the FAQ still asked "What's the difference between the builder pattern and the scope pattern?" and the howToSteps still said "Pick the pattern based on what you're configuring." Always audit FAQ/howToSteps after removing a section. Remove or rewrite the stale entries so the frontmatter matches the body.
- **Body FAQ section duplicates the frontmatter FAQ rendered by the theme.** The blog schema in `src/pages/blog/[slug].astro` renders `faqItems` and `howToSteps` from frontmatter via `<BlogFAQ items={post.data.faqItems} />` and the HowTo component. Adding a body section with H3 question-style headings (e.g. `### Which of the three vendor definitions should I start from?`) creates a visible duplicate FAQ region that the user sees twice on the same page. Confirmed failure mode (2026-07-01, context engineering pillar): body had 4 H3 question blocks plus a "## Frequently asked questions about context engineering in practice" header. Frontmatter had 4 `faqItems`. The user reaction: "WHY IS THIS PART OF THE TEXT AND NOT PART OF THE DAMN FAQ SECTION?????". The fix: do NOT add a body FAQ section when the frontmatter `faqItems` already renders via the theme. Either use frontmatter only (the theme renders it visibly) or, if you need a body FAQ region, do NOT set `hasFAQ: true` AND drop the `faqItems` array from frontmatter. Same logic applies to HowTo. Audit pattern: before claiming shipped, `grep -c '^### ' body` should equal `len(faqItems)` only when the body H3s are the same questions as the frontmatter items AND there's no visible duplicate. The structural fix: frontmatter renders FAQ via theme, body has prose, never both.
- **BigWang swagger cadence mars the post when there's no research underneath it.** The BigWang voice is high-conviction swagger. The swagger lands when there's a concrete fact to land on (source-code line, named competitor with a verifiable claim, named production system). When the draft opens with swagger and the body underneath is general architectural commentary, the swagger reads as compensation for absent specifics. Confirmed failure mode (2026-07-01, context engineering pillar first draft): the lead was seven swagger declarative sentences in a row ("Context engineering is the substrate discipline... The prompt is one input. The context is the substrate's job. PumpStation curates it..."), then the body was the same claims restated in different forms across five H2 sections, with no citations to canonical sources and no concrete production failures. The user's critique: "This is like the worst blog post I've ever seen. It's just llm'isms doesn't really cover the concepts with solid research... I think Bigwang might have suffered from some kind brain injury... Because this is just awful." The fix is not "less swagger" — it's "swagger attached to research, not swagger attached to swagger." A working pattern: lead each H2 section with one research-anchored claim (Anthropic's September 2025 post says X, LangChain's July 2025 framing says Y), then prove the claim with the source code or competitor docs you already verified, then let the swagger land on the verified ground. Without research, swagger is decoration. With research, swagger is conviction.
- **Mixing container-level DSL content into pipe/pipeline articles.** Scope DSL content (Manifold defaults/worker/pipeline blocks, Junction state machine stages, "why the DSL exists" rationales) belongs in a separate containers article. The scope DSL is only relevant as the composition boundary — how a builder-built Pipeline gets handed to a Manifold worker. Apex corrected this mid-session: the "Same pipeline, two ways" section was drafted, shown, and cut because it was out of scope for the pipeline tutorial. If you're writing about pipes, stay on pipes. If you're writing about containers, write about containers. Don't do both in one post unless that's genuinely the topic.
- **YAML frontmatter indentation.** Astro's content loader uses a strict YAML parser. All fields under list items in `faqItems[]` and `howToSteps[]` must be at exactly 4 spaces indentation. A 6-space `text:` field causes "bad indentation of a mapping entry" and the page returns 404. The dev server keeps running but the page is broken. Always verify with `curl` after frontmatter edits. See `references/astro-dev-server.md` for the full checklist.
- **Missing hero images.** Before publishing, verify the `image:` path in frontmatter resolves to an actual file in `public/assets/blog/`. The Astro page will render fine but the hero will be broken. Audit all posts after content changes. Known case from this session: `2026-06-06-how-to-build-a-tpipe-pipeline.md` declares `image: "/assets/blog/tpipe-pipeline-patterns-hero.png"` but that file did not exist — generate it and place it at `public/assets/blog/tpipe-pipeline-patterns-hero.png` before the post goes live.
- **Local file paths in published content — link to the public repo instead.** TTT blog posts are public marketing. They cite TPipe and Autogenesis source code as evidence. **Never ship absolute local paths** like `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/validateAction/validator.kt`. The reader doesn't have your drive. The reader has the open-source repo. The pitfall fires when the draft was written against a local clone: every `validator.kt:97`, `identifyPlayAgent.kt:128`, `globals/BedrockConfig.kt:436` ends up cited as a local absolute path in the markdown. User's correction (2026-07-10, orchestration-matters-more-than-model-intelligence post): *"Don't put a path on my drive in the blog article. Link to the open-autogenesis github repo we have instead."* The fix:
  1. **Identify the canonical public repo URL.** For Autogenesis source code, the canonical URL is `https://github.com/Ten-Trillion-Triangles/Open-Autogenesis`. For TPipe core, it's `https://github.com/Ten-Trillion-Triangles/TPipe`. **Don't guess.** If the repo URL isn't known, ask before shipping — a fabricated GitHub link to a non-existent repo is worse than a local path. The 2026-07-10 session had no git remote on the local Autogenesis checkout, so the canonical URL had to be confirmed via `clarify` before any conversion could ship.
  2. **Convert each `path/to/file.kt:LINE` to a markdown link.** Use the GitHub blob URL with a `#L<line>` anchor so the citation still deep-links to the exact line: `[\`validator.kt:97\`](https://github.com/Ten-Trillion-Triangles/Open-Autogenesis/blob/main/Autogenesis/server/src/main/kotlin/agent/builders/validateAction/validator.kt#L97)`. Preserve the `:NN` line number in the visible text — readers grep for the file path and line number, not for the GitHub URL.
  3. **For file-only references (no line number)** like "the legality checker is `validator.kt`", link to the file at the head: `[\`validator.kt\`](https://github.com/Ten-Trillion-Triangles/Open-Autogenesis/blob/main/Autogenesis/server/src/main/kotlin/agent/builders/validateAction/validator.kt)` — no fragment.
  4. **Audit the static build, not the dev server.** Dev-server HTML includes HMR/Vite asset paths that look like `/home/cage/...` URLs (the `?astro&type=style` style-loader URLs) but are dev-only instrumentation, not content. The audit must check the static build: `grep -c /home/cage dist/client/blog/<slug>/index.html` should return 0 for content, and `grep -c github.com/Ten-Trillion-Triangles/Open-Autogenesis` should match the number of citations in the markdown.
  5. **Mechanical conversion is a script.** The 2026-07-10 conversion rewrote 18 inline citations in one Python pass against the post markdown. The script at `scripts/local-paths-to-github-blobs.py` implements the conversion for the canonical repo. When the canonical repo URL is different (not Open-Autogenesis), pass `--repo <url>` and `--path-prefix <repo-relative-path-prefix>`. Run after the draft is otherwise final, before the humanizer pass — the humanizer pass counts em-dashes and brand density against the visible text, and a `\`validator.kt:97\`` with a 100-character GitHub URL inflates the line count without changing the voice.
- **Hero image wiring is incomplete.**
- **Contradicting yourself in the contrast section.** When a post contrasts TPipe's mechanism against what "other frameworks" do, every claim about the other framework must align with the prior framing of what the framework actually does. The KillSwitch blog post (June 2026 revision) shipped a line that read "A budget cap is a value the agent checks" — this contradicted the prior "per-call ceiling" framing AND was factually wrong. In every framework the user is aware of (LangChain, LangGraph, CrewAI, AutoGen, Google ADK), the LLM never sees the budget cap. The framework's call wrapper does the per-call check, and the wrapper is what decides the response (throw, return a default, log and continue, hand back to the caller). The LLM is a passive responder to whatever the wrapper returns. Two failure modes to avoid: (1) attributing per-call behavior to "the agent" when the framework's wrapper is the actual component, and (2) writing the contrast paragraph without re-reading the prior framing paragraph — the contrast should sharpen the prior claim, not contradict it. The audit: after writing the contrast paragraph, scroll up and check that every noun in the new paragraph matches the noun used in the prior framing. If the prior paragraph said "framework's call wrapper" and the new paragraph says "the agent," that's a contradiction even if both are technically defensible.
- **Localizing TPipe's design to a single container class.** TPipe's architecture lives at the P2PInterface level. The kill switch, the error propagation, the context flow, the agent communication — all of these are properties of `P2PInterface`, not Splitter-specific or Pipe-specific. The kill switch check is in EVERY container class that implements `P2PInterface` — Pipeline, Manifold, Junction, Splitter, MultiConnector, DistributionGrid. Each container runs its own check as it executes, captures the running token totals, and propagates the kill through the call chain. The Splitter is ONE concrete example of this pattern: it runs branches in parallel, accumulates tokens after each branch completes, and fires the check on the accumulated totals. The same pattern runs in every container. The user caught this on the KillSwitch blog post and pushed back three separate times in one session before the framing landed. The signal that you've localized: any sentence that names a specific container (especially the Splitter) as the actor when describing cross-cutting behavior. The fix: lift the framing to the P2PInterface level, then name the specific container as one example of the general pattern. Wrong: "The Splitter maintains a killSwitchInputAccumulator and fires checkKillSwitch on the accumulated totals." Right: "A kill switch is a property of the P2PInterface. Every container that implements it runs a check as it executes. The Splitter is one concrete example: it runs branches in parallel and accumulates tokens after each branch completes (Splitter.kt:732)." Use the same one-example-of-the-pattern framing for any cross-cutting TPipe mechanism.
- **Claiming a type or field exists without sourcing it.** Before writing "the callback is typed `-> Nothing`" or "the field is `killSwitchInputAccumulator`" or "the file is 66 lines," read the actual source and confirm. The user caught a self-contradictory FAQ claim in the KillSwitch post that said "The type system enforces the throw, but the developer enforces the throw" — redundant, wrong, and the second clause contradicted the Nothing type the article itself correctly identified. For Nothing: yes, it's real, it's Kotlin's bottom type, it's used in `KillSwitch.kt:29` as the `onTripped` callback signature. The fix when a type claim IS real: write a concrete example showing how the type-level guarantee works (e.g., "a callback that logs and returns is a compile error, not a misconfigured kill switch"). The fix when a type claim is NOT real: don't write the claim. Source-or-skip applies to: type signatures, field names, function names, file paths, line numbers, default values, and any other code-level fact the reader can grep for. If the user grep-validates the article and the claim doesn't match, the article is dead on arrival.
- **Hero image wiring is incomplete.** The full workflow when the user provides a generated image: (1) **optimize to WebP if the PNG is > 1MB** — `ffmpeg -y -i input.png -c:v libwebp -q:v 82 -lossless 0 output.webp` typically gets an 8-12x size reduction without visible loss, and the pre-launch checklist in `humanizer` flags hero images > 1MB as needing WebP for mobile; ship the .webp as primary and keep the .png as fallback, (2) copy the WebP to `public/assets/blog/<slug>-hero.webp` (and the PNG to `public/assets/blog/<slug>-hero.png`), (3) point frontmatter `image:` at the .webp, (4) add a specific ternary case to the `alt` text computation in `src/components/blog/BlogPost.astro` (the current implementation falls back to a generic alt text unless the filename matches a hardcoded set like `memory-system-hero` or `reasoning-pipes-explained-hero`), (5) verify with `curl -sS -o /dev/null -w "WebP HTTP %{http_code} size=%{size_download}\n" http://127.0.0.1:4321/assets/blog/<slug>-hero.webp` and the same for the .png. The "drop in the file" half of the workflow is not the workflow. The alt text patch is required for accessibility and SEO. If the vision tool can't read the image (oversized file, no vision budget, 413 error from the analyzer), ask the user for the prompt that was used and write a faithful alt text against the prompt's described content — not a generic placeholder. The alt text ternary match uses `image.includes('filename-prefix')` which matches both `.webp` and `.png` since they share the prefix — so the alt text wires up automatically when the frontmatter switches from one extension to the other.
- **Delivering the image prompt as a brief instead of a paste-ready block.** When the user asks for an image generation prompt, the deliverable is the prompt itself — paste-ready, as the headline, in the first message. No multi-section brief that contains the prompt as one section. No "what to avoid" preamble outside the prompt. No closing notes about file paths, alt-text handlers, or "want me to fire this into a generator" — those go in a follow-up message only if the user asks. First version of the ContextWindow/ContextBank hero prompt ran ~1.2K of meta-discussion around a ~600-word prompt. The user replied: "That's not really a proper image prompt. Can you try againn." Second version was the prompt plus a two-line aside. That was the right format. The template at `templates/hero-image-prompt.md` documents the prompt structure (Format, Style, Palette, Composition, Mood, What to avoid) — that structure is fine for the prompt content. The failure mode is wrapping the prompt in a brief and burying it as one section among many. The image prompt is the headline, not the appendix. Inline negatives inside the prompt itself ("no people, no fantasy, no neon") are fine and read naturally; the problem is a separate "What to avoid:" section that pads the deliverable. When the user asks for a prompt, they want the prompt.
- **Body contradicts FAQ in the same article.** A self-contradicting FAQ is the worst kind of error because the reader is most likely to grep the FAQ for the specific fact. The KillSwitch post (June 2026) shipped a FAQ entry that read "The type system enforces the throw, but the developer enforces the throw. A callback that prints and returns is a misconfigured kill switch, not a working one." The body of the same article correctly identified the `onTripped` callback as `(KillSwitchContext) -> Nothing` and noted the type-level enforcement. The FAQ contradicted the body in the same sentence, then lied about the runtime behavior (a `-> Nothing` callback that prints and returns is a compile error, not a "misconfigured kill switch"). Audit procedure: after writing FAQ entries, re-read the body paragraphs that make the same claim and check the FAQ doesn't say the opposite. The same audit applies to HowTo steps that reference claims made in the body — if the body got rewritten, the HowTo can drift. The check is mechanical: for each `faqItems[i].answer` and `howToSteps[j].text`, find the body sentence that makes the same claim, and confirm the FAQ/HowTo version is consistent (not just plausible-sounding). Self-contradiction in different sections of the same article is harder for the reader to catch than cross-article contradiction, and harder for the author to notice on re-read.
- **Visible humanizer audit that only lists "what was AI" without showing the patches.** When the user invokes the humanizer skill on a draft, the audit is the deliverable. A list of "patterns I found" without the before/after or the diff is not a humanizer pass — it's a self-assessment. The user wants to see what changed and why. Show the diff, group by class of fix (TTT first-class tells / rule-of-three fragments / listicle bloat / closer opinion), and be honest about what's still arguably AI. See "The visible humanizer audit" above.
- **BigWang closer that reads as a re-teach.** The first draft of the ContextWindow/ContextBank closer was: "The data structures are the same. The bank is the same. The lorebook slot is the same. The difference is a pipeline that turns generated text into structured, retrievable memory on every turn. That's the next post." That is a fragment list with a recap at the end. The fix: replace the "X is the same" repetition with one declarative line, then add a BigWang opinion (a specific failure mode the reader has likely seen) and a declarative statement of what the next post delivers. The opinion does the actual closing work; the fragment list looks thorough but signals AI. See "The BigWang closer needs an opinion, not a recap" above.
- **Stale dev server (two variants).** (a) **Stale cache**: the Astro dev server can serve cached content after running for days. If edits to a `.md` file don't appear on the live page despite file being saved, kill and restart: `kill $(lsof -t -i:4321 -s TCP:LISTEN)` then `npm run dev` again. (b) **Upstream-reaper SIGKILL**: a different failure mode where `npm run dev` exits with code 137 within 30-90s of startup, no crash log, plenty of free memory, reproduces every cycle. The fix is NOT another restart — pivot to a static file server against `dist/client/`. Both variants are documented in `references/astro-dev-server.md` (Stale server problem section for variant a, Upstream-reaper SIGKILL section for variant b).
- **Stale-cache trigger (variant a) is specifically edits to content collection files and the BlogPost component, NOT arbitrary page components.** Editing an arbitrary `.astro` page triggers HMR correctly and shows up immediately. Editing `src/content/blog/*.md` frontmatter OR editing `src/components/blog/BlogPost.astro` component code can desync the content cache — `curl` returns 200 and the post URL but the rendered HTML still shows the pre-edit content. **Symptom that you hit variant a**: the build passes (`npm run build` exit 0, schema valid), the file on disk has the new content (`grep` confirms it), but `curl http://localhost:4321/blog/<slug>/` returns the old HTML. The fix is always a dev-server restart via `terminal(background=true)`, NOT another build. Confirmed 2026-07-21 on the `the-cheapest-agent-is-the-one-that-thinks-like-you` post — both the Mermaid block edit and the `BlogPost.astro` alt-text branch addition required server restart before `curl` showed the new content. Recovery sequence: (1) `kill $(lsof -t -i:4321 -s TCP:LISTEN)`, (2) `npm run dev` via `terminal(background=true)` (NOT `nohup` foreground — Hermes blocks shell-level background wrappers), (3) wait for "astro v6 ready" in the log, (4) `curl` to verify the new content is now rendered.
- **In-article architectural diagrams (decision trees, system maps, ladder diagrams) belong inline as `<img src=".svg">`, NOT in the frontmatter `image:` field.** The `image:` field drives the BlogCard thumbnail on the `/blog/` index, which uses `object-fit: cover` at 180px tall × ~360px wide. A 1280×720 or 16:9 hero SVG gets cropped in the card thumbnail, and load-bearing visual content (often placed left-of-center per the SVG composition convention) gets sliced off. The fix: drop the `image:` field for pillar posts whose hero is an in-article architectural diagram, and place the SVG inline via markdown image syntax: `![alt text](/assets/blog/<slug>-diagram.svg)`. The SVG renders at full article-body width with no cropping. The BlogCard falls back to the default thumbnail. **Decision rule:** if the SVG is the visual proof the post argues through (decision tree, agent hierarchy, ladder), inline it; if the SVG is a top-of-article banner with the post title treatment, put it in the `image:` field. **Confirmed 2026-07-21** on the cheapest-agent-thinks-like-you post: the user landed "SVG looks good but it's cut off here, it might not work as the hero image in this particular case, Idk if we can place svg image directly insdie the article or not though where we have better control over the size" — the pivot was to inline `<img>` markdown with the SVG saved to `public/assets/blog/<slug>-diagram.svg`, no `image:` field, and the diagram renders at full article-body width.
- **Adding a new hero branch in `BlogPost.astro` means extending the conditional ternary chain by one nesting level.** The alt-text computation at `src/components/blog/BlogPost.astro:113-127` is a single nested ternary chain — each new hero slug adds one more level of indentation to every prior branch. As of 2026-07-21, the chain is 9 levels deep (8 hero slugs plus the final fallback). When adding a new branch: (a) put the new branch INSIDE the deepest existing branch as a new child, (b) verify every prior branch's closing paren / colon matches the new depth — the `patch` tool warns about indentation drift but only on the changed region, not the unchanged siblings, so re-grep the whole ternary after the patch, (c) re-curl 3 sibling posts (the new post + 2 older posts that hit different branches) to confirm the chain still resolves correctly. The regression check is mechanical and cheap: `curl -s http://localhost:4321/blog/<sibling>/ | grep -oE 'alt="[^"]+"' | head -1` should return the expected alt text for each sibling. Confirmed 2026-07-21 — adding `the-cheapest-agent-is-the-one-that-thinks-like-you-hero` branch required bumping every prior branch's indentation by 2 spaces and a 3-post regression check confirmed PumpStation, ContextWindow+ContextBank, and the oldest pre-hero post still hit their correct branches.
- **When the user invokes the humanizer skill after a prior humanizer pass in the same session, default to a scoped sweep over the named pattern, NOT a full 29-pattern re-pass.** If the user says "humanize this" first and then "now go back and clear out it's not X it's Y type ism's," they mean the second-class fix specifically — they are not asking for another broad AI-isms sweep that re-catches what the first pass already cleaned. **Symptom to detect:** the user's second humanizer invocation names a specific pattern (`it's not X it's Y`, `paradigm shift`, `leverage`, `tapestry`, etc.) rather than saying "humanize this" or "make it sound more human." The scope is the named pattern. Run the targeted grep + targeted patches for that pattern only. Re-running the full 29-pattern audit when the user has narrowed scope is over-engineering and dilutes the audit signal — the user sees "50 things changed" when they expected "4 targeted kills." Confirmed 2026-07-21 on the cheapest-agent-thinks-like-you post: the second humanizer invocation said "Run another pass through and clear out itt's not X it's Y by or It's Y not X type ism's by rewording into cleaner lannguage" — named the pattern explicitly. The right response was a targeted sweep against `is not \w+,? is`, `is not .* but`, `isn't .* but`, plus the broad period-separated `is not` / `does not` audit, with 4 kills. NOT a full 29-pattern re-pass.
- **Humanizing working-notes files strips the audit trail.** When the user invokes the humanizer skill on a research-notes / blocker-tracker / status-flag file (not a finished draft), the 29-pattern audit will rewrite the load-bearing structure. All-caps verification flags (`**YES**`, `**NO — HYPOTHETICAL**`, `**TO VERIFY**`), BLOCKER labels, and the "WAIT for user on X before drafting" closer are not prose to be humanized — they're the file's working state. The correct counter-pattern is a three-category pass: (a) humanize the prose-only sections (outline, narrative paragraph), (b) leave verification tables and status flags verbatim, (c) tighten the BLOCKER narrative while preserving the decisions. Always ask which category before touching — a full humanize pass on a research file produces nonsense and the user will reject it. The signal that triggered this from session 2026-07-01: the user said "humanize the blog idea" and the actual artifact was `blog-research/<pillar>-research.md` with status `Research phase, NO draft yet. Two blockers flagged below.`
- **llms.txt drift correction is NOT a publish event.** When the user asks for a crawl-files audit (`make sure robots.txt / llms.txt are current`), the scope is just `public/llms.txt` — adding missing posts in the existing entry format, reverse-chronological order, with descriptions in the file's voice. Do NOT bump `updatedDate` on the existing posts. Do NOT re-run the full Publishing & crawler visibility checklist. Do NOT touch `robots.txt` (already has blanket `Allow: /` + Content-Signal/Content-Usage; new posts are auto-visible). Do NOT touch `sitemap.xml` (auto-generated from the content collection). The audit the user wants here is "does llms.txt list every published post?" — if yes, done. If no, add the missing entries and stop. Re-running the full publish checklist on every drift correction is over-engineering and the user has been explicit about it: "only if needed."

## Where to find real production code

See `references/source-locations.md` for the canonical paths. The short version:
- Autogenesis WriterAgent at `Autogenesis/server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt` is the gold standard for pipe construction
- TPipe framework docs at `TPipe/TPipe/docs/` for DSL examples (manifold, junction, distributionGrid)
- Existing TPipe blog posts at `ttt-site/src/content/blog/` for style reference

## TPipe-specific technical content

This skill is voice-and-structure only. For the technical content, pull from these sources (see references/source-locations.md for paths):

- **Builder pattern**: Chained method calls or `.apply { }` block. Used for all pipes and most containers.
- **Scope DSL**: `manifold { }`, `junction { }`, `distributionGrid { }`. State-machine-enforced at compile time.
- **Pipeline**: Order-of-execution container. Builder pattern only.
- **Junction state machine**: `Initial → HasModerator → HasParticipants → Ready`. The type system enforces this.
- **The one rule**: Builder for pipes, scope DSL for containers. Mix freely.
- **Common pitfall**: `init()` is required. Forgetting it throws `UninitializedComponentException` on first `execute()`.
- **Type safety**: `setJsonInput` / `setJsonOutput` + `requireJsonPromptInjection()` is the standard combo for typed LLM output.

### TPipe API accuracy (must source from code, not memory)

Corrections from this session that future drafts MUST NOT repeat. Full detail in `references/tpipe-api-accuracy.md`:

- **`setModel` takes ONLY a string.** Never an enum. The string can be a model ID (`anthropic.claude-3-haiku-20240307-v1:0`) or a full ARN. Constants like `BedrockConfig.qwen235B` are `val` properties on a Kotlin `object` (the BedrockConfig singleton) that return strings — NOT Kotlin enums. The win of using the constant is IDE autocomplete + one place to change the ID. For cross-region ARN models, call `bedrockEnv.bindInferenceProfile(modelId, arn)` first or pass the ARN directly. Source: `Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt`.
- **`setTokenBudget` is the memory management system, not a cap.** It activates TPipe's runtime context algorithm. At config time it tokenizes system prompt, max output, reasoning budget, and user prompt size, subtracts them from the context window, and throws on overflow. At runtime (line ~5851 of `Pipe.kt`) the pipe runs the truncation stage: lorebook selection by priority/weight, multi-page MiniBank budget allocation, text-matching preservation, and overflow handling. Working with KillSwitch (the hard ceiling above), this is the layer that keeps the agent from forgetting, drifting, or drowning in oversized context. Apex's framing: "like if you could turn on garbage collection in a coding language on the fly." **A claim that is wrong and must not appear:** "If any pipe fails, the pipeline halts and the failure is reported through KillSwitch. As long as the pipes have setTokenBudget configured, KillSwitch is automatic." KillSwitch handles token exhaustion specifically, not arbitrary pipe failures. setTokenBudget does not make KillSwitch "automatic" — they are two distinct layers. Source: `TPipe/src/main/kotlin/Pipe/Pipe.kt:2692` (`setTokenBudget`) and `Pipe.kt:5851` (runtime truncation call).
- **`init()` loads the provider backend, not just state wiring.** For Bedrock pipes, `init()` specifically: (1) calls `super.init()` to propagate timeout settings and initialize child pipes, (2) calls `bedrockEnv.loadInferenceConfig()` to load inference profile mappings from `~/.aws/inference.txt`, (3) resolves model ID to inference profile ARN if configured, (4) initializes `BedrockRuntimeClient` with region, credentials, and HTTP timeouts. Without `init()`, `bedrockClient` is never created and the first `execute()` throws a runtime exception because the provider backend is missing — NOT `UninitializedComponentException` (that exception is for the general case of skipping `init()` on pipes that don't do provider-specific initialization; Bedrock specifically fails with the client missing). Source: `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:787-854`.
- **`setTokenBudget(...)` is the ACTIVATION SWITCH. `enableLoreBookFillAndSplitMode()` is a STRATEGY SWITCH.** This is a critical distinction. `setTokenBudget(...)` activates the runtime context algorithm (the GC). The lorebook modes (`enableLoreBookFillMode()`, `enableLoreBookFillAndSplitMode()`) are knobs that adjust how the already-running algorithm allocates budget between lorebook entries and other context. Do NOT describe `enableLoreBookFillAndSplitMode()` as "turning on memory management" or "turning on LoreBook." The truncation stage runs because `setTokenBudget` was called; these methods only pick the strategy. Mental model: `setTokenBudget` = power switch, `autoTruncateContext()` = run button, `enableLoreBookFillMode()`/`enableLoreBookFillAndSplitMode()` = knobs.
- **`BedrockConfig.generativeBudgetSettings` (and similar) are PROJECT-LEVEL PATTERNS, not TPipe framework features.** These appear in some TPipe-built projects (e.g. Autogenesis) but are NOT part of the TPipe framework itself. Do NOT write "BedrockConfig has preset budgets for different generation strategies" — that is incorrect. When `setTokenBudget` is described, show the actual `TokenBudgetSettings` data class fields inline: `TokenBudgetSettings().apply { contextWindowSize = 32_000; maxTokens = 4_000; reasoningBudget = 2_000; ... }`. The data class is at `TPipe/src/main/kotlin/Pipe/Pipe.kt:141-165`.

### MultimodalContent flow control

Pipelines aren't simple chains. The `MultimodalContent` object carries control flags that let any pipe redirect execution at runtime. See `references/multimodal-content-flow.md` for the full detail. The key flags:

- `jumpToPipe` — the redirection primitive. Empty string = sequential, `"skip-to-next-pipe"` = skip one, `"pipe-name"` = jump to named pipe (forward or backward).
- `terminatePipeline` / `passPipeline` / `repeatPipe` — early exit and loop control.
- `metadata["connectorPath"]` — how the Connector component finds its routing key.

**The primitive is `jumpToPipe`.** Any pipe can directly set `content.jumpToPipe = "some-pipe-name"` to redirect execution. The Connector is a convenience pattern for key-based dispatch; `jumpToPipe` is the direct control.

**General rule: any claim about a TPipe API must be sourced from the function definition in `TPipe/src/main/kotlin/`.** Memory and prior session knowledge are not authoritative. The 30 seconds it takes to read the function is the difference between a correct blog post and a rewrite.

## See also

- `ttt-site-pricing` - the pricing page specifically (different artifact, different voice: marketing/decision-guide)
- `humanizer` - general AI-isms removal (this skill is the TPipe-blog-specific application)
- `ttt-site-comparison-pages` — the companion skill for site pages (comparison pages, README-as-product mechanism). The voice rules here and the voice rules there are the same rules. Blog posts and GitHub marketing share the same BigWang directness standards. If you're writing a blog post AND the content touches competitive positioning, check `ttt-site-comparison-pages/references/readme-as-product-mechanism.md` — it has the framework for understanding how competitor projects drive traction, which informs how TPipe should compete on the same stage.
- `seo-expert/references/unbranded-landing-page-pattern.md` — the cluster-signal wiring pass (homepage → category pages, comparison pages → relevant category page, docs index → category pages) is a separate post-build task that must run AFTER the category pages exist and BEFORE blog posts compete for the same category terms. Read the "The cluster-signal wiring pass (after page creation)" section before shipping a blog post that targets a category keyword.

## Support files

- `references/grounding-stages.md` — the two-stage pre-write grounding template. Stage 1 (end-to-end source read) + stage 2 (concept + competitive + TPipe-superpowers) before any TPipe feature blog post. Read this before starting a new post on a TPipe feature.
- `references/agent-harness-competitor-axes.md` — durable comparison axes for the competitive landscape table in stage 2b. Specific facts are time-bounded and re-verified per the bigwang verify-everything rule; the axes themselves are stable.
- `references/context-engineering-pillar-session-2026-07-01.md` — session postmortem for the first pillar that shipped with body-FAQ duplication and swagger-without-research failure modes. Read this if writing a pillar (architecture / category-owning) post for the first time, or after any session where the user rejected a draft as "this is awful."
- `references/voice-and-style.md` — the full bad-patterns inventory with before/after rewrites and the grep commands
- `references/source-locations.md` — exact paths to Autogenesis and TPipe source for finding real code
- `references/competitor-style-reference.md` — how LangChain, LangGraph, CrewAI, and AutoGen structure their tutorials
- `references/tpipe-api-accuracy.md` — TPipe API corrections: `setModel` is string-only (not enum), `setTokenBudget` is the memory management system (not just a cap), `init()` loads the provider backend, `enableLoreBookFillAndSplitMode()` is a strategy switch not the activation switch. Read this before writing any post that touches these APIs.
- `references/multimodal-content-flow.md` — MultimodalContent control flags (`terminatePipeline`, `repeatPipe`, `passPipeline`, `jumpToPipe`, `interuptPipeline`, `skipReasoningPipe`, `metadata["connectorPath"]`), Connector routing mechanism, `getNextPipe()` jump logic, and priority order. Relevant for pipeline content flow articles.
- `references/astro-dev-server.md` — Astro dev server management: stale server restart, YAML frontmatter indentation rules (4-space strict), verification checklist. Read this after any frontmatter edit.
- `scripts/local-paths-to-github-blobs.py` — mechanical converter for backtick-wrapped `file.kt:NN` citations inside a markdown blog post. Replaces local absolute paths with GitHub blob URLs (with `#L<line>` anchors) for the canonical open-source repo. Use after the draft is final, before the humanizer pass. Default repo is `Ten-Trillion-Triangles/Open-Autogenesis`; override `--repo` and `--path-prefix` for other repos. Read this skill's "Local file paths in published content" pitfall before running.
- `templates/blog-post-template.md` — starter template with the structure filled in
- `templates/hero-image-prompt.md` — starter prompt template for the dark-industrial hero image family (format, palette, composition, what-to-avoid, reference images, alt-text wiring)
- `references/in-flight-posts.md` — active article queue with specs (title, code samples, hero image concept, source file references). Check this before starting a new post.

## In-flight posts

Active article queue lives in `references/in-flight-posts.md`. When the user asks for "the next post" or picks up a draft, check that file first. The canonical research for each post lives in the relevant TPipe skill's `references/` directory — point there when sourcing technical claims.

### The origin story workflow

When the user provides a real origin story or lived experience for a feature ("we built X because Y happened"), lead the post with it. This is the highest-converting opening for technical posts in this voice — it earns the BigWang confidence because the stakes are real, not theoretical. The KillSwitch post's "billion-token burn" lead is the canonical example: it explains WHY the feature exists, with specific numbers and specific consequences ("the kind of number that ends a three-person company"), before any code lands. The user provided that story unprompted — the workflow is: take the user's lived experience, put it first, use specific details (dollar amounts, dates, exception classes, error messages) wherever they were given. Generic "we hit a problem" openings get rejected.

### Current state of the Stage 2 queue

- ✅ **Post 5:** "Why P2P Agent Communication Is Inevitable" — shipped 2026-05-11
- ✅ **Post 6:** "Reasoning Pipes Explained: How TPipe Stops Prompting and Starts Programming" — shipped 2026-06-12. See `tpipe-reasoning-pipes/references/json-railroad-pattern.md` for the technical research.
- ✅ **Post 7:** "The KillSwitch: Token Budgets That Actually Kill the Agent" — shipped 2026-06-13. See `references/killswitch-source-points.md` for the implementation research and the origin story details.
- ✅ **Post 8:** "How TPipe Stores an Agent's Memory: ContextWindow and ContextBank" — shipped 2026-06-14. The opener for Post 9. Covers the data structures, the singleton, the mutex contract, and the Autogenesis read/write pattern. Full production build is in Post 9, not here.
- ✅ **Post 9:** "How TPipe Agents Update Their Own Memory in Real Time" — shipped 2026-06-21. The **code-tour across production projects** variant. Showcases the lorebook-update pattern at Autogenesis, TPipeWriter, and TStep with file:line citations. See `references/in-flight-posts.md` for the full spec + audit results. The user's framing was a code-tour rather than the originally-prescribed "build a pipeline from scratch" deep-dive.
- ✅ **Post 12:** "Orchestration Matters More Than Model Intelligence: How Ten Trillion Triangles TPipe Hits 99% on a 30B Model" — shipped 2026-07-10. Pillar format. Grounded in Autogenesis source (validator.kt, identifyPlayAgent.kt, BedrockConfig.kt:436) with all citations linked to the open-autogenesis GitHub repo. The full plan is at `~/.hermes/plans/bbb-blog-pillar-orchestration-over-intelligence.md`. The 30B-vs-Opus empirical ladder (60% → 99% with substrate, same 99% on Qwen 3 Coder 30B-A3B at 1/30th per-token cost) is the load-bearing claim. Cited sources of the source-citation pitfall: local paths in published content must point to the public repo.
- ⏳ **Post 9b (candidate, only if requested):** "Build a Lorebook That Writes Itself: A TPipe Memory Agent Tutorial" — the from-scratch deep-dive that the original Post 9 spec described. WriterAgent stub + LorebookAgent stub + extraction schema + token budget + KillSwitch wiring. Not the active next post; available if the user wants the hands-on tutorial after the code-tour.
- ⏳ **Post 10:** "Migrating From LangChain: A Practical Guide" — spec in `references/in-flight-posts.md`. Pushed from Post 8 to make room for the ContextWindow/ContextBank opener.
- ⏳ **Post 11:** "The Token Budget Is Not a Suggestion" — spec in `references/in-flight-posts.md`. Covers `TokenBudgetSettings` and the runtime context algorithm.

The full backlog of unstarted ideas (LoreBook deep dive, ContextBank, Junction voting, Chain-of-Draft, benchmarks page, CrewAI/DSPy/Semantic Kernel migration, hero image concept for "You Cannot Build an Agent Substrate in Python") is in hindsight memory — search "blog post idea backlog" to recall it.

### The code-tour across production projects variant (added 2026-06-21)

When the user's framing is "show me the real production pattern across the projects," not "build one from scratch," use this variant. Post 9 (memory agents, 2026-06-21) is the canonical example.

```
1. The architectural claim (the rule, stated in 1-2 sentences, no manifesto)
2. The canonical example (1 project, full code excerpt with file:line, walk through what each block does)
3. The invocation pattern (the call site, fire-and-forget or whatever, with code excerpt)
4. The honest second example (a second project, the same shape but with the production workarounds visible — including candid bug comments and "this is janky but it works" annotations)
5. The non-LLM variant (a third project, the same shape but with a different motivation — proves the pattern is general, not coupled to a specific writer)
6. The continuity payoff (the third project's per-turn persistence, shows what the pattern buys you at scale)
7. Cross-project patterns (the patterns that fell out across all 2-4 projects — aliasKeys, mutex contracts, storage modes, no-pruning policy, overflow answers, etc.)
8. The architectural claim, restated sharper (third-person observation, not value-prop summary; Apache 2.0 closer or equivalent third-person move)
```

The signature move: 2-4 real production projects, 5-8 file:line code excerpts per project, every claim grounded in actual source. NO stub code. NO "here's a toy pipeline you can build" walkthrough. The reader walks away having seen the actual production code at multiple shops, not having built a toy.

**The opener-of-a-series + code-tour pair is a recurring pattern.** Post 8 (opener, 1900 words) set up the data structures. Post 9 (code-tour, 3160 words) showed the real production pattern across three projects. If the user later wants the hands-on build, that's Post 9b (from-scratch deep-dive, the originally-prescribed Post 9 spec, still queued as a candidate).

**When to use this variant:** Trigger phrases include "show some actual examples," "what does this look like in production," "real-world patterns from the projects," "across the projects you can find on my system." When the user asks for production evidence and code excerpts at multiple shops, reach for this variant.

**The Apache 2.0 closer (recurring TTT voice move).** When the post is a flagship piece and the closer should leave the reader with a third-person observation about the ecosystem rather than a value-prop summary, consider the Apache 2.0 closer. The pattern: one or two sentences on the architectural truth, then the closer. Examples shipped:
- Pricing post (2026-06-15): "The Apache 2.0 license is a real gift to the ecosystem. The gift does not include the production platform."
- Memory agents post (2026-06-21): "The Apache 2.0 license is a real gift to the ecosystem. The gift does not include the lorebook writers."

The variant on the verb ("the production platform" vs "the lorebook writers") is what makes it land each time. The constant is the structure: a gift statement, then a "the gift does not include X" follow-up where X is the specific feature the post is about. Don't reuse the same X twice across posts.
