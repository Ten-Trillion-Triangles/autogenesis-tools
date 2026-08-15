# In-flight posts

Active article queue. When picking up an in-flight post, find the latest spec here. Check this file before starting any new post — the user may already have a draft in motion.

**Status (2026-06-21):** Posts 5, 6, 7, 8, and 9 are all shipped. The user's framing for Post 9 (2026-06-21) was a **code-tour across production projects** rather than the "build a pipeline from scratch" deep-dive that the original spec described. The post showcases the lorebook-update pattern as it actually lives in production at three real projects (Autogenesis, TPipeWriter, TStep) with file:line citations. If the user later wants the "build it from scratch" tutorial — WriterAgent stub + LorebookAgent stub + extraction schema + token budget + KillSwitch wiring, the spec below is still useful as a future post candidate. The active next post is the one the user picks next, per `hindsight_recall` ("blog post idea backlog").

---

## Post 9 (NEXT, original spec — repurposed as a candidate for a future post if requested): Memory Agents — Building a Pipeline That Keeps Its Own Lorebook in Real Time

**Status:** Spec preserved as a candidate. Post 9 was shipped 2026-06-21 as a code-tour variant (see SHIPPED POSTS). If the user wants the "build a pipeline from scratch" tutorial this spec described, it can be picked up as a future post.

**Original spec (preserved for reference):**

**Working title (confirm with user):** "Memory Agents: How TPipe Pipes Keep Their Own Lorebook in Real Time"
Or: "Build a Lorebook That Writes Itself: A TPipe Memory Agent Tutorial"

**Author:** Richard Wang

**Voice:** BigWang — definitive, code-first, the kind of post that ends with a working repo. The opener (Post 8) was lighter and more architectural; the code-tour (Post 9, shipped 2026-06-21) was heavier on production evidence but lighter on the build-it-yourself walkthrough. This "from-scratch" deep-dive would be heavier and more hands-on than either.

**Core angle (the spine of the post):**
- The opener showed that two Autogenesis agents — WriterAgent and LorebookAgent — read and write the same `ContextBank` key, with the WriterAgent appending raw text to `contextElements` and the LorebookAgent extracting structured entities and updating `loreBookKeys`. The deep-dive shows how to BUILD that two-agent pipeline from scratch, end to end, with your own extraction schema.
- The architectural argument: a memory agent is a Pipeline with an LLM call that runs after every generation, extracts structured data from the new context, and writes it back to the bank. The data structures (Post 8) are the foundation. The Pipeline is the mechanism. The extraction prompt is the policy.
- The contrast: most "memory agent" tutorials in other frameworks (LangChain, LangGraph, CrewAI, AutoGen) end at "write to a vector store after each turn." TPipe's lorebook approach is keyword-triggered, deterministic, and auditable. The post should make that contrast explicit without becoming a comparison page.
- Real production evidence: the Autogenesis LorebookAgent runs on every turn and has been in production long enough to be the canonical reference. The numbers (extraction categories, call frequency, latency impact) come from the user, not from LLM memory.

**Code samples to source (must read from real Autogenesis code):**
- `Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt:793-799` — the WriterAgent's write-back pattern (canonical, also used in Post 8)
- `Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/lorebook/lorebookAgent.kt:166-280` — the LorebookAgent's read-extract-write loop (canonical, this is the spine of the post)
- A minimal end-to-end pipeline (WriterAgent stub + LorebookAgent stub) that the reader can paste and run
- The extraction prompt structure: the JSON schema that defines the entities the agent will extract (characters, events, locations, items, factions, relationships)
- The `combineValue` merge pattern for updating existing lorebook entries without losing prior context
- The `enableLoreBookFillAndSplitMode` / token budget wiring that keeps the agent from drowning in its own lorebook as it grows

**Pairs with:** Post 8 (just shipped, the opener), Post 7 (the KillSwitch — token budget is the next bottleneck after the lorebook grows large enough that selection matters), and the shipped Post 9 code-tour (the production-evidence companion to this from-scratch tutorial).

**FAQ seeds:**
- What is a memory agent?
- How does TPipe keep a lorebook up to date in real time?
- What's the difference between a memory agent and a RAG pipeline?
- Can the extraction step run on every turn without blowing the token budget?
- What happens when two agents write to the same lorebook key concurrently?
- How do I prevent the lorebook from growing unboundedly?
- Can a memory agent run headless, without a human reviewing the writes?

**HowTo seeds:**
- Design the extraction schema (what entities, what fields, what weights)
- Build the WriterAgent stub (a pipe that takes a prompt, calls the LLM, writes the result to the bank)
- Build the LorebookAgent stub (a pipe that reads the bank, runs extraction, writes structured entries back)
- Wire them into a Pipeline
- Add the page key + token budget so selection stays bounded as the lorebook grows
- Add the KillSwitch so runaway extraction cost gets capped
- Test with a real workload (10 turns, 50 turns, 100 turns — does the lorebook stay coherent?)

---

## Post 10: Migrating From LangChain — A Practical Guide

**Status:** Spec needed. Pre-writing research has not started. The user is the canonical reference for what migration surface to cover.

**Working title:** "Migrating From LangChain: A Practical Guide"

**Author:** Richard Wang

**Voice:** BigWang — definitive, code-first, "we are the future" framing. This post is a conversion play targeting searches for "LangChain alternatives" and the engineers who have hit LangChain production failures. The thesis: "Type your way into determinism. Don't prompt your way into it."

**Core angle (to confirm with the user before drafting):**
- Most LangChain refugees are drowning in prompt-template spaghetti that the framework cannot enforce. The first 500 lines of any production LangChain agent are prompt engineering. The first 500 lines of a TPipe agent are types.
- The migration surface: `PromptTemplate` → typed data class + JSON schema injection, `Chain` → `Pipeline`, `AgentExecutor` → `Manifold` or `Junction`, `Retriever` → `LoreBook` priority/weight selection, `OutputParser` → `@Serializable` data class + `setJsonOutput()`.
- The architectural argument: LangChain's primitives are strings. TPipe's primitives are types. The cost of strings is the same cost the LLM pays — you cannot reason about correctness. The cost of types is the cost the compiler pays — refactor and the build breaks.
- Real production evidence: Autogenesis, billions of tokens, no drift failures. The judge is unjailbreakable.

**Code samples to source (must read from real TPipe/Autogenesis code):**
- A LangChain prompt template and the equivalent TPipe data class
- A LangChain chain and the equivalent TPipe Pipeline
- A LangChain AgentExecutor and the equivalent TPipe Manifold or Junction
- The `setJsonOutput` + `requireJsonPromptInjection` combo for typed LLM output

**Related skill content:**
- `tpipe-reasoning-pipes/SKILL.md` — covers the JSON schema injection that replaces LangChain's `OutputParser`
- `references/tpipe-api-accuracy.md` — read before writing about any TPipe API
- `references/voice-and-style.md` — the FIRST-CLASS tell ("X is not Y. X is Z.") is the most common LLM failure mode in posts like this

**FAQ seeds:**
- Why migrate from LangChain to TPipe?
- What's the equivalent of LangChain's PromptTemplate in TPipe?
- How do I replace LangChain's OutputParser with TPipe's typed output?
- Can I use TPipe's reasoning pipes with LangChain's existing chains?
- What about LangChain's vector store integrations?
- Does TPipe support LangChain's hub (prompt sharing)?

**HowTo seeds:**
- Inventory your current LangChain primitives
- Map each LangChain primitive to its TPipe equivalent
- Replace PromptTemplate with a typed data class
- Replace Chain with Pipeline
- Replace AgentExecutor with Manifold or Junction
- Set up typed JSON output for every LLM call
- Test the migration with a small agent first

---

## Post 9: The Token Budget Is Not a Suggestion

**Status:** Spec needed. Pre-writing research has not started.

**Working title:** "The Token Budget Is Not a Suggestion"

**Author:** TBD (could be Richard Wang or BigWang; depends on framing)

**Core thesis:** "The TokenBudgetSettings system is not a cap. It is the memory management system." The runtime context algorithm is the closest thing TPipe has to garbage collection — it runs at config time (tokenize, subtract, throw on overflow) and at runtime (lorebook selection by priority/weight, multi-page MiniBank allocation, text-matching preservation, overflow handling).

**Critical accuracy notes (read references/tpipe-api-accuracy.md first):**
- `setTokenBudget` is the ACTIVATION SWITCH. Calling it activates the runtime context algorithm.
- `enableLoreBookFillMode()` and `enableLoreBookFillAndSplitMode()` are STRATEGY SWITCHES. They adjust how the already-running algorithm allocates budget.
- `autoTruncateContext()` is the RUN BUTTON for the algorithm.
- `BedrockConfig.generativeBudgetSettings` is a project-level pattern in Autogenesis, NOT a TPipe framework feature. Do not describe it as part of the framework.
- The actual `TokenBudgetSettings` data class fields: `contextWindowSize`, `maxTokens`, `reasoningBudget`, `inputTokenReserve`, `outputTokenReserve`, `truncationStrategy`. Show them inline in the post.

**Pairs with:** The KillSwitch post (Post 7) — the TokenBudgetSettings works at config time, the KillSwitch enforces the hard ceiling at runtime. Together they are the two layers of cost control.

---

## SHIPPED POSTS (for reference)

### ✅ Post 9: How TPipe Agents Update Their Own Memory in Real Time (2026-06-21)

**Status:** Shipped. File: `ttt-site/src/content/blog/2026-06-21-contextbank-realtime-memory-updates.md`. Build clean. ~3,160 words, 8 sections, 7-item FAQ, 6-step HowTo. Featured: true. No hero image (omitted per bigwang pitfall #3; falls back to default card image).

**The variant:** Code-tour across production projects, not a "build a pipeline from scratch" tutorial. The post showcases the lorebook-update pattern as it actually lives in production at three real projects (Autogenesis, TPipeWriter, TStep) with file:line citations, then closes with cross-project patterns (aliasKeys, per-page mutexes, `StorageMode.DISK_ONLY`, no-pruning) and a third-person observation closer.

**Sections:**
1. The lorebook agent is a transformation function — the architectural claim and the `setTransformationFunction { ... }` hook
2. Autogenesis: the canonical example — `lorebookAgent.kt:166-283` with the six merge functions
3. Fire-and-forget means the player's turn does not wait — `gameplayOrchestrator.kt:1794-1821`
4. TPipeWriter: the honest version — `Env.kt:729-768` with the candid bug comments and the `cleanLorebook` workaround
5. TStep: when the writer is a code indexer — `LorebookPublisher.kt:7-56` (same shape, non-LLM motivation)
6. 120+ turns is what this buys you — `ActionHistoryRpcHandlers.kt:47-63` per-turn persistence
7. Patterns that emerged across all three projects — aliasKeys, per-page mutexes, `StorageMode.DISK_ONLY`, no lorebook pruning, two valid overflow answers
8. The architectural claim — "The LLM is the mouth. The substrate is the brain. The pipe is the loop."

**Closer:** Third-person observation, no 4th-wall break. "The agent's memory is the agent's. The pipe gives the hook. The bank is the persistence. What the writer does with the hook is up to the writer." Plus the Apache 2.0 closer pattern (recurring TTT voice move — same shape as the 2026-06-15 pricing post closer).

**The variant template (for future code-tour posts):** When the user's framing is "show me the real production pattern across the projects," not "build one from scratch," use this structure. Three real production projects with file:line code excerpts (5-8 excerpts per project maximum), one cross-project "patterns that emerged" section, and a third-person closer. NO stub code. NO "build it from scratch" walkthrough. The reader walks away having seen the actual production code at three different shops, not having built a toy pipeline. The opener (Post 8) sets up the data structures. The code-tour shows the real pattern. The from-scratch deep-dive (still queued as a future candidate if the user wants it) would show the reader how to build their own.

**Pairs with:** Post 8 (the opener — ContextWindow and ContextBank data structures). The opener's last paragraph explicitly teases this post: "The next post in this series covers the full memory agent pattern: a pipeline that runs after every generation, extracts structured entities from the new context, folds them into the lorebook, and persists the result — all automatically, all in real time, with no human in the loop touching the lorebook by hand." Post 9 delivered on that tease via the code-tour variant.

**Code references (all spot-checked at file:line during write):**
- Autogenesis `agent/builders/lorebook/lorebookAgent.kt:166-283` (transformation function with six merge functions)
- Autogenesis `agent/runners/gameplayOrchestrator.kt:1794-1821` (fire-and-forget invocation)
- TPipeWriter `src/main/kotlin/Globals/Env.kt:729-768` (`recordLoreBook` with candid bug comments)
- TStep `TStep/src/main/kotlin/com/tstep/code/index/LorebookPublisher.kt:7-56` (code-index-driven writer)
- Autogenesis `org/ttt/autogenesis/server/ActionHistoryRpcHandlers.kt:47-63` (per-turn persistence)
- tpipe-manifold-validation `orchestration/ManifoldOrchestrator.kt:81-88` (overflow safety net)

**Sub-agent contribution:** Delegate-task leaf scanned 35 source files across 4 TPipe-using projects (Autogenesis, TPipeWriter, TStep, tpipe-manifold-validation). Returned 6 quotable code snippets with file:line, cross-project patterns, and surprising non-obvious findings. All 6 file:line references were spot-checked against source — exact match. The subagent pattern for "scan all projects using X library, pull real code excerpts" works well for this post type. It keeps the main agent's context clean (the subagent's full tool output never enters this context; only its final summary does).

**Audit results:** 0 hedge phrases. 0 signposting. 0 copula avoidance ("X is not Y, X is Z"). 1 legitimate em dash in a "term — definition" bullet pair (Six entity types — characters, events, locations, items, factions, relationships). 6 "Ten Trillion Triangles TPipe" mentions (≥4 required). All fenced code blocks labeled kotlin. Build clean, 200 OK at `/blog/2026-06-21-contextbank-realtime-memory-updates/`.

### ✅ Post 7: The KillSwitch: Token Budgets That Actually Kill the Agent (2026-06-13)

**Status:** Shipped. File: `ttt-site/src/content/blog/2026-06-13-killswitch-explained-token-budgets-that-kill-the-agent.md`. Build clean. Hero image at `/assets/blog/killswitch-explained-hero.png`.

**The 66-line file. The `Nothing` type. The catch-and-rethrow carve-out. The root-down accumulator. The billion-token burn origin story.**

Full research: `references/killswitch-source-points.md` (this skill). Origin story details and the "do not name a specific competitor" pitfall are documented there.

### ✅ Post 6: Reasoning Pipes Explained: How TPipe Stops Prompting and Starts Programming (2026-06-12)

**Status:** Shipped. File: `ttt-site/src/content/blog/2026-06-12-reasoning-pipes-explained-stops-prompting-starts-programming.md`. Build clean. Hero image at `/assets/blog/reasoning-pipes-explained-hero.png` (alt text patched in `BlogPost.astro`).

**The JSON schema field-ordering pattern. The `doesLegendExist` boolean. Eight reasoning methods, all using the same railroad.**

Full research: `tpipe-reasoning-pipes/SKILL.md` and the schema definitions at `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:454-555`.

### ✅ Post 5: Why P2P Agent Communication Is Inevitable (2026-05-11)

**Status:** Shipped. File: `ttt-site/src/content/blog/2026-05-11-p2p-agent-communication-inevitable.md`.

**The five non-negotiables of true P2P. The centralized-vs-P2P failure mode. The DistributionGrid architecture.**

---

## Reasoning Pipes Explained (Post 6 — historical spec, now shipped)

The spec below is preserved for reference. For current state, see the SHIPPED POSTS section above.

**Title:** Reasoning Pipes Explained: How TPipe Stops Prompting and Starts Programming

**Author:** Richard Wang

**Word count target:** 3,200–3,500

**Voice:** "Big Wang" — definitive, code-first, "the LLM is a compiler" framing

**Core thesis (used as the lead):**

> **TPipe doesn't prompt. It programs.** Left-to-right token prediction is a compiler for sequential commitment. By designing JSON schemas where the FIRST fields are boolean/int commitments and the LATER fields are the hallucination-prone content, TPipe forces the LLM to lock in a position before it ever touches the rich output. The `doesLegendExist` field is the cleanest example: a single boolean, structurally positioned first, kills an entire class of hallucinations in smaller models. The same trick scales across every reasoning method. Once you see it, you can't unsee it — and you can't build a serious LLM application any other way.

**The worked example (kill shot for the post):**

Walk through `LegendAnalysis.doesLegendExist` in `ModelReasoning.kt:454-467`. Show before/after for the same empty compressed prompt:

- Model A (no boolean, lists first): `codesFound: ["AB", "AC", "BA"]`, `mappings: ["AB: foo", "AC: bar", "BA: baz"]` — fabricated
- Model B (boolean first): `doesLegendExist: false`, `codesFound: []`, `mappings: []` — correct

One boolean. One structural position. One class of bugs eliminated. Then pan out to the other response classes that use the same trick.

**Code samples (6–8 total, all from real TPipe source):**

1. `LegendAnalysis` data class — the boolean-first pattern, with the KDoc
2. `SemanticDecompressionResponse` — the content identification gate (legend → hypotheses → evidence → task)
3. `MethodActorResponse` — character profile first, problem view second, solution last
4. `MultiPhasePlan` — analysis first, limitations listed, then phases with risks
5. `ChainOfDraftResponse` — 5-word problem analysis first, 5-word draft steps
6. `Pipe.kt:1944-1962` — the JSON schema injection with default-value instructions
7. `ReasoningBuilder.kt:317-321` — the footer prompt enforcement
8. One `unravel()` method (e.g. `MultiPhasePlan.unravel()`) — showing the reverse path

**Hero image concept:** Split frame — top half: jumbled prompt + hallucinated JSON. Bottom half: same prompt + railroaded JSON with `doesLegendExist: false`. Caption: "Same prompt. Same model. Different schema. Different output."

**Schema markup:** BlogPosting + HowTo + SoftwareApplication (TPipe reasoning pipes feature)

**Sequenced after:** Post 5 (P2P — published 2026-05-08)

**Sets up:** Post 7 (Autogenesis: 300M tokens), Post 8 (Migrating from LangChain), Post 9 (Token Budget)

**Source code references (must-source, not from memory):**

- `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:454-555` (LegendAnalysis + SemanticDecompressionResponse)
- `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:357-390` (MethodActorResponse)
- `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:285-322` (MultiPhasePlan)
- `TPipe/src/main/kotlin/Structs/ModelReasoning.kt:392-448` (ChainOfDraftResponse)
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:1942-1962` (JSON schema injection)
- `TPipe-Defaults/src/main/kotlin/Defaults/reasoning/ReasoningBuilder.kt:240-274, 317-321` (jsonOutputObject assignment + footer prompt)
- `TPipe/src/main/kotlin/Util/Schema.kt:51-100` (JsonSchemaGenerator — the schema-from-classes pipeline)

**Related skill content:**

- `tpipe-reasoning-pipes/references/json-railroad-pattern.md` — the technical deep-dive, worked examples, the design pattern for new response classes, and the anti-patterns to avoid. The article thesis above is also in this file.

**FAQ items (6-7, asked-from-outside framing, not the article's voice):**

Drafting these is the last step before writing the body. Typical seeds:
- What is the JSON railroad pattern?
- Why does field order in a JSON schema matter for LLM output?
- How does TPipe force the LLM to acknowledge a legend?
- What's the difference between a reasoning pipe and a regular LLM call?
- Why does TPipe use Kotlin data classes for output schemas?
- Can I use this pattern with any LLM provider?
- How does this compare to OpenAI's structured outputs or function calling?

**HowTo steps (5-7, imperative):**

Drafting these is the last step before writing the body. Typical seeds:
- "Define a Kotlin data class with your output schema, ordered by commitment"
- "Annotate with @Serializable and add @kotlinx.serialization.Serializable"
- "Set the data class as the JSON output type on the pipe"
- "Call requireJsonPromptInjection() to force schema-based output"
- "Add a boolean to the top of the class to force a commitment"
- "Write an unravel() method that flattens the JSON back to prose"
