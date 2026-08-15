# Two-stage pre-write grounding template

The user runs a labeled two-stage pre-write process before any TPipe feature blog post. Each stage has a specific deliverable and trigger language. Skipping either stage produces a post that fails the audit.

## Stage 1 — End-to-end technical grounding

**Trigger language:** "Goto where X is on this system and learn all about Y end-to-end. This is required context before the next blog article I have you write for our site."

**Deliverable:** a working understanding of the class/feature, including:

- File locations and line counts (e.g. "PumpStation.kt: 4465 lines, 8 files total 10,950 lines")
- The class structure (constructor, public surface, key methods)
- The loop architecture (two-scope, inner cycle, transition phase — for harness features)
- The LLM-facing magic contracts (8 for PumpStation, varies by feature)
- The exit mechanisms and how they differ
- The memory/control modes and when each applies
- The DSL builder surface
- Real-world usage examples from the source repo

**Output format:** structured terminal-friendly report. Plain text. No markdown headers. Sectioned by class, loop, contracts, exit mechanisms, memory modes, DSL, public surface, defaults. Lead with the architectural argument, end with "ready for the next prompt."

**Common failure:** treating this as a one-sentence summary. The deliverable is the working document, not a confirmation that the system exists. The user has 11+ blog posts in flight; future TPipe feature blog posts will reuse this workflow.

## Stage 2 — Concept + competitive + TPipe-superpowers

**Trigger language:** "Break down the core concepts in X in greater detail, compare how it's different from agent harness loops of today, and breakdown all of the TPipe superpowers that X is also bringing to the table. This is the second stage of grounding to understand how to sell it as a concept, but also how to explain in tpipe terms."

**Three deliverables:**

### 2a. Core concepts in detail

Take the stage 1 working understanding and break it down further. For a harness like PumpStation, that means:

- The two-scope loop structure (outer runHarnessLoop, inner runTurn, transition runExitFlow) — the most-missed concept, lead with it
- The N magic contracts (8 for PumpStation: judge, dispatch, path, goal, path-safety, health, lorebook, summary) with their strictness, parsers, fallback behavior
- The path/atom object (PathObject for PumpStation) with its execution priority and init() validation
- The DITL hooks (the 18 hooks across the harness)
- The async substrate (asyncScope, historyMutex, asyncSeqCounter, pendingAsyncResults)
- The memory modes (3 for PumpStation: Compaction, Truncation, Hybrid)
- The v3 architecture (cursors, backups, CompactionResult sealed type) — if the feature has a v2/v3 split
- The loop guards and P2P integration
- The event taxonomy (39 sealed events for PumpStation)

### 2b. Competitive landscape

Compare against the current agent framework ecosystem. The standing list:

- **LangGraph** (LangChain) — graph-based state machine, nodes/edges, Pregel runtime, checkpointers
- **CrewAI** — crew of agents, role/goal/backstory, sequential or hierarchical processes, Crews + Flows
- **AutoGen / Microsoft Agent Framework** — conversation model, GroupChat, Magentic-One, GraphFlow
- **OpenAI Agents SDK** (formerly Swarm) — handoffs, guardrails, sessions, sandbox
- **Google ADK 1.0/2.0** — cross-language SDK, SequentialAgent/ParallelAgent/LoopAgent, A2A protocol
- **LlamaIndex Workflows** — event-driven abstraction, FunctionAgent, ReActAgent

The comparison axes (durable across years, re-verified per bigwang's verify-everything rule) live in `agent-harness-competitor-axes.md`. The output is a table with one row per framework and one column per axis. Each cell describes what that framework does (or doesn't do) on that axis. PumpStation's delta on each axis is the blog post's positioning argument.

### 2c. TPipe superpowers the feature composes

Every TPipe feature is positioned by which TPipe primitives it composes. The standing list:

- **KillSwitch** (`P2P/KillSwitch.kt`) — cost control. The hard ceiling on token spend per run.
- **ContextWindow + MiniBank + LoreBook** (`Context/*`) — memory substrate.
- **TokenBudget** — the runtime context algorithm. The activation switch (`setTokenBudget`) is distinct from the strategy switches (`enableLoreBookFillMode`, `enableLoreBookFillAndSplitMode`).
- **P2PInterface** (`P2P/P2PInterface.kt`) — the composability contract. The 8 containers all implement it.
- **PCP — PipeContextProtocol** (`PipeContextProtocol/*`) — typed tool calling. FunctionRegistry is the global singleton.
- **PipeTracer** (`Debug/PipeTracer.kt`) — observability.
- **FailureAnalysis** (`Debug/FailureAnalysis.kt`) — failure classification.
- **The 7 other containers** — Pipeline, Manifold, Junction, Splitter, Connector, MultiConnector, DistributionGrid. PumpStation is the only LLM-driven container; the others are deterministic.
- **DITL** — the first-class intervention surface (18 hooks across PumpStation + Pipe + Pipeline).
- **The branded bundle** — the default prompt set, the PumpStationDefaults factory, the OpenRouter example.

For each primitive, document: what the primitive is, where it lives (file:line), what the feature does with it, and what the alternative framework does (typically: nothing).

## Stage 3 (implicit) — Write the blog

Use the ttt-site-blog skill's existing voice, structure, and two-pass humanizer workflow. The two stages of grounding produce the working document; the blog draft draws from it.

## Why this workflow matters

- **Stage 1 prevents the cite-the-marketing-component pitfall** (bigwang pitfall #6). The blog post has file:line citations because the agent has read the source. A claim about the user's own product that cites `src/components/...` or `src/pages/...` is decoration, not fact.
- **Stage 2 prevents the copula-avoidance double-sentence** when positioning against competitors. The comparison produces a specific delta, not a "X is not Y. X is Y." dance. The first-class tell in any competitive blog post.
- **The two stages are about not skipping the work.** A blog post that ships from a single prompt without grounding ships wrong. The user has corrected this in past sessions (the open-source-lie pricing post needed multiple rounds of revision because the cost-table was wrong, the license claim was wrong, the billing flow was wrong).
