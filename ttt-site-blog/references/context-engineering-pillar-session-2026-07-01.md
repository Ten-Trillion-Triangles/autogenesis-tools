# Context Engineering Pillar Session — 2026-07-01 Postmortem

Session that produced `src/content/blog/2026-07-01-context-engineering-vs-prompt-engineering.md`. The session went through three full drafts before the user accepted the post. This file captures the failure modes and the corrections that future sessions should not repeat.

## What was supposed to happen

The user asked for the "Context Engineering vs Prompt Engineering: The Substrate Shift Beyond Prompt Engineering" pillar post, picked from a priority queue of AEO gaps. The plan covered source verification (Anthropic + LangChain + LlamaIndex + CrewAI + OpenAI + Microsoft Agent Framework), source-code verification against TPipe HEAD, ten-task draft flow, audit gates. The session followed the plan to the letter. None of that was the problem.

## What went wrong: two specific failures

### Failure 1 — BigWang swagger over general architecture, no research underneath

The first draft was 1,929 words of swagger declarative sentences ("Context engineering is the substrate discipline... The prompt is one input. The context is the substrate's job. PumpStation curates it. ContextBank stores it. Reasoning pipes assemble it. Frameworks retrofit the pattern.") repeated across five H2 sections, with no citations to canonical sources. The body content was the same thesis restated in slightly different forms, not actual research.

The user's critique verbatim: *"This is like the worst blog post I've ever seen. It's just llm'isms doesn't really cover the concepts with solid research, has two seperate faq sections (for some reason).... I think Bigwang might have suffered from some kind brain injury... Because this is just awful."*

The diagnosis: BigWang voice lands swagger attached to specific facts. Without specific facts underneath, the swagger reads as compensation for absent specifics. The voice itself wasn't the problem — the absence of research was. The user followed up with: *"what we need bob, is to take his ceo ism's which are fine, and just write a more coherent article. To do whatever he was trying to do, before he had some kind of stroke, or got diabeetus or something..."* — meaning the swagger was fine, the substance was missing.

The fix that landed: rewrite from scratch with research-anchored claims. Each H2 section now opens with one claim from a verified source (Anthropic's "iterative curation at every call," LangChain's four strategies, LlamaIndex's window-filling framing, CrewAI's Memory class unification, OpenAI Agents SDK's Session, Microsoft Agent Framework's "context providers"), each with a verifiable specifics quote. The substrate proof section (where TPipe is named) earned the swagger through the source-code citations. The "what frameworks get right" section earned its softer voice because the research was about acknowledging what competitors got right.

### Failure 2 — Body FAQ section duplicated the frontmatter FAQ

The first draft had a body section titled "## Frequently asked questions about context engineering in practice" with 4 H3 question blocks, plus a separate body section "## Steps to apply context engineering in any stack" with 5 numbered bold steps. The frontmatter had 4 `faqItems` and 5 `howToSteps`.

The theme at `src/pages/blog/[slug].astro` renders both `faqItems` and `howToSteps` from frontmatter via `<BlogFAQ items={post.data.faqItems} />` and the HowTo equivalent. The body sections duplicated what the theme was already rendering. On the rendered page, the reader saw two FAQ regions: the body H3 questions with prose answers, and the theme-rendered accordion below them. Same content, two surfaces.

The user's reaction: *"WHY IS THIS PART OF THE TEXT AND NOT PART OF THE DAMN FAQ SECTION?????"*

The fix: drop the body FAQ section entirely. Drop the body HowTo section entirely. The frontmatter `faqItems` and `howToSteps` arrays render visibly via the theme components. Body becomes tight body prose — 5 H2 sections, no H3 questions, no numbered steps. The audit pattern that catches this: `grep -c '^### ' body.md` and `grep -c '^## ' body.md` against `len(faqItems)` and `len(howToSteps)` from frontmatter. If both are non-zero AND `hasFAQ: true` / `hasHowTo: true` are set in frontmatter, there's a duplicate.

## What the second draft fixed

The second draft (1,812 words) added the actual research: Anthropic's verbatim quote about iterative curation, LangChain's four-strategy framing with each strategy named, LlamaIndex's window-filling definition, CrewAI's Memory class unification as the admission-of-retrofit, OpenAI's Session-as-conversation-history framing, Microsoft Agent Framework's "context providers" as the explicit retrofit. The substrate proof section kept the BigWang swagger attached to source-code citations (PumpStation transformation hook at `Pipeline/PumpStation.kt:4294`, ContextBank `emplaceWithMutex` at `Context/ContextBank.kt:559`, mutex at `Context/ContextLock.kt:43`). The five H2 sections each lead with research, then land the substrate claim, not the other way around.

The body FAQ section and body HowTo section were dropped. The frontmatter FAQ items are 4 different questions than what the body covers — practical adoption questions ("Which of the three vendor definitions should I start from?", "Does context engineering replace prompt engineering?", "How is this different from RAG?", "What does the substrate framing give that the vendor framings don't?"). The theme renders them as 4 `<details>` accordions at the bottom of the post, with proper JSON-LD FAQPage schema.

## Em dash audit failure

The second draft shipped with 20 em dashes in body — the audit threshold is ≤3 with all in H2/H3 titles. The third rewrite pass was a bulk em-dash conversion via Python script that brought the count down to 7 (4 strategy bullets + 3 source-code line citations in code-block-adjacent prose). The fix was mechanical but the lesson is: when the BigWang pass re-introduces em dashes for cadence (and it will), the humanizer pass needs a separate em-dash audit that doesn't rely on the 29-pattern scan alone.

## Two corrections that were caught at verification, not at audit

Two of the source-code claims I drafted were caught by verifying the source against HEAD before shipping, not by the audit greps:

1. **"18 DITL hooks" claim.** The PumpStation Runtime Harness post (2026-06-16) shipped with "Eighteen DITL hooks at every phase boundary." Verification at HEAD found 14 function-typed setters in `Pipeline/PumpStation.kt` (and 22 total including agent-typed setters). The pillar rewrote to "fourteen phase-boundary hook functions" — verifiable count.

2. **"Weighted lorebook activation" claim.** The ContextBank vs Vector Databases post (2026-06-26) uses "weighted lorebook activation." The pillar initially echoed this but verification found the LoreBook algorithm is the LoreBook content surface, separate from ContextBank's typed-key API. Rewrote to "typed, page-key addressed store" — verifiable from `emplace(key: String, window: ContextWindow, mode: StorageMode, ...)` at line 414.

Both rewrites preserved the architectural argument. Both rewrites kept the post shippable. Without the source verification step, both claims would have shipped false.

## What the user explicitly wanted that wasn't in the plan

The user's mid-stream course-correction: *"what we need bob, is to take his ceo ism's which are fine, and just write a more coherent article."* The BigWang swagger is fine when attached to substance. The fix wasn't "less swagger." The fix was "swagger on top of research, not swagger on top of swagger." This is a class-level signal for any future ttt-site-blog work: the BigWang voice is the delivery mechanism, not the content. Research is the content. Without research, the voice is a parade of declarations with nothing underneath.

## Plan + verification artifacts

- Plan: `.hermes/plans/context-engineering-pillar/plan.md`
- Source verification log (6 sources, all PASS): `.hermes/plans/context-engineering-pillar/verification-log.md`
- Final post: `src/content/blog/2026-07-01-context-engineering-vs-prompt-engineering.md` (1,812 body words, 5 H2 sections, 0 H3 sections in body, 4 FAQ items in frontmatter rendered as theme accordions, 5 HowTo steps in frontmatter rendered as ordered list, build exit 0, dev server HTTP 200)

## Lessons for future sessions

1. BigWang swagger on no-research is decoration. BigWang swagger on research is conviction. The voice doesn't change; the substance underneath does.
2. Frontmatter FAQ items render via the BlogFAQ theme component. A body FAQ section creates visible duplication. Drop one or the other.
3. Source-code claims decay between sessions. The verification log is the only reliable ground. Run it before any post that cites line numbers, file paths, function signatures.
4. The 29-pattern humanizer scan catches vocabulary, not structure. Em dashes, FAQ redundancy, swagger cadence require separate audits.
5. When the user says "this is awful," the right move is to drop the swagger cadence and lead with research, not to ask permission. The critique is the instruction.