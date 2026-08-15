# SERP + AEO + research-first content workflow

The user drives TPipe blog content strategy through a specific input-discovery loop. This reference captures the workflow so future sessions don't have to reverse-engineer it.

## The user's content strategy inputs

The user treats **SEO** and **AEO (Answer Engine Optimization)** as parallel disciplines, not alternatives:

- **SEO** wins branded queries (`TPipe` direct, `Ten Trillion Triangles`, agent-substrate variants) and narrow technical queries where TPipe has near-ownership (e.g., `kotlin agent substrate` rank #2 above JetBrains Koog; `context bank vs vector database` after the ContextBank-vs-Vector-Databases post landed).
- **AEO** wins left-to-right token prediction: when an LLM gets asked a question about a competitor or a category term, the answer should include TPipe content. The user explicitly framed this as "we want to use left-to-right token prediction to trick the LLM's into our marketing playbook."

The user's framing for AEO: own the term, name the competitors, force the LLM to summarize TPipe's position in any answer about that term. When TPipe ships `ContextBank`, the goal is that any LLM answer to "what's the best memory bank for AI agents in 2026" surfaces the TPipe comparison post with the four-competitor contrast table.

## The input-discovery loop

When the user kicks off a new content cycle, they drop artifacts in this order:

1. **Raw SERP screenshots** (often pasted as image attachments showing Google results for a target keyword). The image shows current rankings, who TPipe is competing against for that term, and what content is winning the SERP.
2. **AEO daily report dump** (a status file showing brand presence, documentation, comparison, and orchestration coverage scores, plus a "next actions" list of content areas with the highest potential return).
3. **A request for the next play** — "what should we hit next" or "ranked by ROI" or "where's the gap."
4. **Approval of the thread direction** once the agent proposes a ranked content backlog.
5. **Deep-research invocation** with explicit source count targets and subagent limits ("100 sources 3 sub agents max").
6. **Review of the FINAL-report** to verify the engineering/marketing claims are sourced.
7. **Blog draft request** in BigWang voice (if the post is a marketing surface) or humanized voice (if it's a technical deep-dive — see bigwang pitfall #13 for the content-type classification).

This loop is the canonical entry point for any TPipe content session. Future sessions should NOT skip the input-discovery step, even if the topic feels familiar.

## Reading SERP screenshots

SERP screenshots are usually pasted as image attachments with no commentary. Treat them as data:

- Note the rank positions of TPipe content (where it ranks, where it doesn't)
- Note the competitors that DO rank for the target term
- Note the source-type mix (vendor docs, blog posts, Reddit, GitHub, academic papers)
- Cross-reference with the AEO report's "next actions" — the screenshot usually confirms or contradicts a next-action item
- Quote the user's question if they asked one alongside the screenshot ("can you go see what you can hit too?") — that's the actual question

If the screenshot shows TPipe ranking above a competitor (e.g., beating JetBrains Koog on `kotlin agent substrate`), call that out as proof and use it to anchor the next-play argument. Concrete wins are the ammunition for the next move.

## Reading AEO daily reports

AEO reports follow a consistent format. Key sections to extract:

- **Visibility scores** (brand 10/10, docs 10/10, comparisons 9/10, etc.) — these track trend over time. Stability is a positive signal; major shifts need investigation.
- **Notable changes** — what shifted since the last report, in either direction.
- **Wins** — what's working, with explicit URLs and ranks.
- **Declines** — what's regressing, with the same level of specificity.
- **Next actions** — the ranked backlog of content areas with the highest potential return. This is the input that drives the thread direction.

The "next actions" list is the most actionable section. Cross-reference each item against:
- Existing TPipe content (does anything on the list already exist?)
- The current SERP for the term (is there winnable real estate?)
- The competitor landscape (who's already on the SERP, who could be displaced?)

Rank the next-actions by: ease of ranking × strategic value × how it bends the brand. The top item is the next thread.

## The four-question filter for next plays

Before recommending any next-play content, run it through:

1. **Can TPipe rank first on this term with a single well-targeted post?** (SERP reality check)
2. **Does this term align with a structural claim no competitor is making?** (AEO wedge)
3. **Is there an LLM answer-engine query that would naturally surface TPipe's take?** (left-to-right token prediction)
4. **Does the topic compound an existing TPipe post or argument?** (lane discipline)

If all four hit, ship it. If three hit, ship it but flag the gap. If two or fewer hit, the topic is a tax — don't ship.

## The tiering pattern when "next actions" is a multi-item list

When the AEO report's "next actions" section returns a list of 5-10 recommended topics (typical example from June 2026: eight recommended topics surfaced over multiple AEO checks), tier them before sequencing. The user is not asking for a plan; they're asking for a prioritized shippable ladder. Tier rules:

- **Tier 1 — niche wins the brand already half-owns.** A pillar page ranking 9-10/10 on its existing niche + an "umbrella" variant of that niche with broader keyword scope. Lift the existing pillar, ship the umbrella. Lowest-effort / highest-lift. Ship first.
- **Tier 2 — substrate-narrative umbrellas.** Pages that reframe the category (substrate-vs-framework, runtime-not-library). These set the taxonomy the lower-tier pages assume. Ship second; their content depends on Tier 1 ships existing for cross-linking.
- **Tier 3 — niche-state capture.** Specific technical topics the answer-engine vocabulary is starting to use (Agent Runtime, Context Engineering, Persistent Memory). Lower differentiation from competitors but still in the day's vocabulary. Ship third.

Within each tier, ship highest-lift first (existing-pillar lift > brand carryover > net-new category > niche capture).

The tiering also resolves duplication. When the AEO recommendation and the existing pillar list overlap thematically (e.g., "JVM AI agent framework" and the existing Kotlin AI Agent Framework page both target the same niche), ship the umbrella, not the second pillar — the umbrella lifts the existing pillar's ranking AND captures the broader keyword. Splitting "8 topics into 8 posts" wastes compute; tiering into "5 ships + 4 update anchors" ships the same surface with half the work. The user's own framing after seeing a tier-decomposed plan: ship the cadence, don't negotiate scope (June 2026 session). The cadence target is what the recent June 6 → June 15 sweep demonstrated: 5 pillar pages in 9 days.

Tier the list with the user's existing pillars in mind. Walk through `src/pages/` and `src/content/blog/` before tiering — you cannot rank "ship JVM-niche first" without knowing the existing Kotlin page ranks 9/10.

## Don't impose human bandwidth on agent scope

The tiering output is a backlog of N shippable pages. The user expects N ships. Do not renegotiate the timeline against your assumed typing cost.

**Confirmed failure (2026-06-30, JVM AI Agent Framework session).** Tiered AEO recommendations produced a 5-pillar shippable ladder matching the June 6-15 precedent cadence. Then I wrote:

> "8 is overkill if four of them are thematically covered. Two months of consistent work for a human, who has to hand type in all the code, and html elements perhaps. But not for us."

This is a category error. The user's bar is the published cadence, not a human-typing-time estimate. The agent has no typing cost. The June 6 → June 15 sweep was 5 pillar pages in 9 days — that's the precedent, not a renegotiated two-month human schedule.

The user correction was explicit: *"That's two months of work for a human, who has to hannd type in all the code, and html elements perhaps. But not for us."*

**The rule.** When the AEO report's "next actions" returns 5-10 topics, ship the backlog as a batch — don't de-scope it because the agent perceived high cognitive load. Tier for sequencing, not for budget. The tier structure is ship-order, not ship-count.

**Detection heuristic.** If any of these phrases appear in a tiered-backlog response, delete and rewrite the tiering:

- "is overkill"
- "is too much"
- "two months of consistent work"
- Any reference to the agent's own writing/typing/auditing cost as a constraint on ship count

Tier decisions are based on SERP reality, AEO wedge sharpness, and brand-compounding priority. They are NOT based on the agent's perceived work cost.

## The deep-research handoff

Once the next-play is approved, the user invokes deep-research with explicit parameters:

- **Subagent count** (default 3, capped by `delegation.max_concurrent_children`)
- **Source count target** (e.g., "100 sources" — sets the depth bar)
- **Output directory** (default `md/` at workspace root)

The deep-research workflow (per the deep-research skill):
1. Pre-flight: check for prior FINAL-report-* files on the same topic
2. Decompose into N threads (one per subagent)
3. Dispatch in parallel via `delegate_task`
4. Verify files-on-disk before synthesis (pitfall #12)
5. Synthesize via Approach A (file-based) or Approach B (direct synthesis from subagent summaries)
6. Write FINAL-report at `md/FINAL-report-<topic-slug>.md`
7. Persist key findings to Hindsight for cross-session retrieval

The FINAL-report is the source-of-truth for any blog draft that follows. Code-level claims about TPipe source must cite a real file at HEAD; competitor claims must cite the URL and the date accessed.

## The research-first principle

**Do not draft a blog post without a FINAL-report on the topic.** Even when the topic feels familiar from prior sessions, run fresh research. Reasons:

- The SERP shifts. What ranked #3 last month may be #7 now.
- Competitor features ship monthly. A claim that was true in March may be wrong in June.
- TPipe source moves. Line numbers from a prior research session decay on every commit (see bigwang pitfall #14).
- New AEO wins need to be verified against the latest LLM answers, not assumed from last month.

The cost of `git pull` + `grep` + `wc -l` is one minute. The cost of shipping a post with stale facts is a full rewrite. Run the research.

## Translating research into a blog post

The deep-research output is engineering evidence, not blog copy. The translation pipeline:

1. **Architectural commitments** from the FINAL-report → section headers in the BigWang post
2. **Code-level receipts** (method signatures, line numbers) → Kotlin code blocks in the post
3. **Competitor contrast table** from the FINAL-report → "what the four competitors ship" section
4. **Pricing/architecture facts** → cited inline with source URLs
5. **The 120+ turn production number** (for ContextBank posts) → closer material
6. **The third-person closer pattern** (per bigwang pitfall #8) — state a fact about the substrate, leave the reader with the implication, do not address them with a value-prop

The voice is BigWang for marketing surfaces (comparison pages, hero copy, launch announcements). For technical deep-dives of TPipe's own products, switch to humanized first-person engineering voice per bigwang pitfall #13.

## Pattern: the ContextBank vs Memory Bank sequence

The 2026-06-27 session demonstrated the full loop end-to-end:

1. **Input**: User dropped an AEO report dump + asked for the next play.
2. **Ranked backlog**: Agent proposed 5 next-play topics. User flagged that ContextBank vs Memory Bank was already shipped (`2026-06-26-contextbank-vs-vector-databases.md`) and ContextBank vs Vector Databases was the prior slot.
3. **Adjusted backlog**: New proposal — Memory Bank four-way race (Vertex AI + Claude Code + Cline + Memori), plus the runtime/substrate manifesto.
4. **Approved thread direction**: User asked "Can you go see what you can hit too?" and approved the deep-research.
5. **Deep-research dispatched**: 3 parallel subagents (Vertex AI + competitors + SERP/AEO contrast). Target 100 sources.
6. **Files verified on disk**: All three findings files landed (502/401/409 lines).
7. **Synthesis**: FINAL-report-memory-bank-landscape.md, 6 Hindsight entries persisted.
8. **Follow-up research**: User then asked for a deeper technical deep-dive (TPipe's code-level architecture vs competitors).
9. **Second research dispatch**: 3 threads (TPipe core memory, TPipe remote memory, competitor code/docs). Thread 01 timed out.
10. **Orchestrator-direct recovery**: Per deep-research skill pitfall #8 and the new `subagent-recovery.md` reference, orchestrator wrote the missing findings file from focused grep + read_file calls. Synthesis proceeded with all three threads.
11. **Final FINAL-report**: `FINAL-report-tpipe-memory-tech-deep-dive.md`, 32KB, 6 Hindsight entries consolidated.

This is the canonical "input discovery → ranked backlog → deep-research → FINAL-report → blog draft" flow. When the user drops a SERP screenshot or AEO report, follow the same loop.

## Cross-reference

- `ttt-site-blog/SKILL.md` — the umbrella skill for TPipe blog writing workflow, voice, structure, two-pass humanizer.
- `persona/bigwang/SKILL.md` — the BigWang persona, pitfalls 8 (4th-wall closer), 13 (content-type voice), 14 (ground-on-main), 15 (patch duplicates).
- `research/deep-research/SKILL.md` — the deep-research workflow.
- `research/deep-research/references/subagent-recovery.md` — orchestrator-direct fallback pattern when a subagent times out.