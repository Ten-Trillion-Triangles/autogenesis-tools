# Competitor Feature Verification Checklist

When rewriting competitor comparison content, verify each framework's claims against current official docs before the rewrite. Don't trust existing copy as truth — competitors ship major updates frequently. This is a checklist, not a current-state document. The categories and what-to-verify are what matter; the specific 2026 state will go stale.

## LangChain

- Language support: **Python and JavaScript/TypeScript** (LangChain.js). v1.0 alpha shipped Sept 2025 in both runtimes. Don't claim "Python only" or "Python framework you call" — that's stale by ~9 months. Wording: "Python and JavaScript (LangChain.js / LangGraph.js) — v1.0 alpha in both runtimes."
- Memory model: `ConversationMemory` is per-run (`ConversationBufferMemory`, `ConversationSummaryMemory`). For cross-session memory, modern LangChain routes through `LangGraph` persistence.
- LangGraph Checkpointer backends: `MemorySaver` (default, in-memory), `PostgresSaver`, `SQLiteSaver`, `MongoDBSaver`, `MySQLSaver`.
- LangGraph long-term memory via `BaseStore` (launched October 2024).
- LangSmith current state (paid SaaS — confirm).
- LCEL vs legacy chain imports.

## LangGraph

- Checkpointer defaults: `MemorySaver` is in-memory; needs explicit `PostgresSaver` etc. for production.
- Multiple database backends: Postgres, SQLite, MongoDB, MySQL.
- LangGraph Studio (visual editor).
- LangGraph Platform "P2P" claim: actually means horizontal scaling (multiple replicas of the same graph). Not peer-to-peer agent discovery. Don't confuse the two.
- Current version, recent major changes.

## CrewAI

- Process types: `Sequential`, `Hierarchical`, `Consensual` (3, not 2). Don't claim just 2.
- CrewAI Flows (event-driven workflow orchestration, on top of crews).
- Multi-language support? (Was Python-only as of 2026 — verify if this has changed.)
- Memory model: **Unified `Memory` class**. Short-term uses ChromaDB (RAG) + SQLite (row tables). Long-term memory via external integrations (Mem0, LangMem). Do not invent a name like "LaterMemory" — the real feature is just "long-term memory" enabled via `memory=True` on Crew or external integration.
- **Callbacks (don't claim "no native support")**: `step_callback`, `task_callback`, `before_kickoff_callback`, `after_kickoff_callback` at agent and crew level. Shallow compared to TPipe's 18-hook DITL, but present. Wording: "step_callback / task_callback / before_kickoff_callback / after_kickoff_callback — agent and crew level."
- CrewAI Studio (cloud platform) vs self-hosted observability.

## Google ADK

- Language support: multi-language as of late 2025 — **Python, TypeScript, Go, Java, Kotlin**. Don't claim Python-only.
- ADK Python 2.0 GA features: graph workflows, collaborative agents.
- ADK Kotlin current state.
- Session backends: `InMemorySessionService` (default), `DatabaseSessionService` (SQLite, Cloud SQL).
- Long-term memory: **Vertex AI Memory Bank** (paid, GCP-managed).
- Supported models: Gemini, Claude, Gemma, Ollama, vLLM, LiteLLM, LiteRT-LM, Apigee AI Gateway.
- A2A protocol integration.
- Official URL: `https://adk.dev/`.

## Microsoft AutoGen

- Current stable version. As of January 14, 2025: **v0.4** (a complete redesign with event-driven actor model). Don't say "announced 2024" — the release date is January 2025.
- Architecture: actor model, asynchronous messaging, modular core.
- Relationship to **Microsoft Agent Framework** (AutoGen lives alongside Semantic Kernel under this umbrella).
- Patterns: `AgentChat` (two-agent conversation), `GroupChat` (n-agent with `GroupChatManager`), `Swarm` (dynamic topic handoff), `Teams` (graph-based workflows, post-v0.4).
- Memory: in-memory by default. External adapters (LangChain, SQLite) needed for persistence.
- Code execution model: in-process by default (no sandbox).

## A2A Protocol

- **Linux Foundation project** (donated by Google on June 23, 2025).
- Current spec version: v1.
- "150+ supporting organizations" claim: cite the **Linux Foundation press release dated April 9, 2026**, not third-party blogs. The LF release is the authoritative source.
- Founding members: AWS, Cisco, Google, Microsoft, Salesforce, SAP, ServiceNow.
- Agent Card at `/.well-known/agent.json`.
- Task model: submitted / working / completed / failed / input-required / canceled.
- Push notifications: webhook-based (deployment constraint, not a feature).
- Official URL: `a2a-protocol.org` (or `github.com/a2aproject/A2A`).

## Microsoft Agent Framework (MAF)

- **Public preview**: October 1, 2025. **Release Candidate**: February 19, 2026. **v1.0 GA**: April 3, 2026. Latest release as of audit: `dotnet-1.10.0` (June 10, 2026). Don't cite "preview" status — v1.0 ships with stable APIs and a long-term support commitment.
- **Repo stats (June 2026)**: 11.3k stars, 1.9k forks, 102 watchers, 2,290 commits, 94 releases. License: MIT. Language split: Python 50.9%, C# 45.9%, TypeScript 2.7%.
- **Official source URLs**: `learn.microsoft.com/en-us/agent-framework/`, `github.com/microsoft/agent-framework`, `devblogs.microsoft.com/agent-framework/`, `devblogs.microsoft.com/foundry/`, `azure.microsoft.com/en-us/pricing/details/foundry-agent-service/`.
- **Lineage**: "The direct successor to both Semantic Kernel and AutoGen, created by the same Microsoft teams." Microsoft Learn overview, 2026-04-06. "Doesn't replace Semantic Kernel and AutoGen — it builds on them." Microsoft Foundry Blog, 2025-10-02.
- **Language support**: **Python and .NET (C#)** — both first-class. Don't claim single-language. MAF's TS tooling is 2.7% of the repo (DevUI / samples), not a runtime.
- **Service connectors (first-party)**: Microsoft Foundry, Azure OpenAI, OpenAI, Anthropic Claude, Amazon Bedrock, Google Gemini, Ollama. Don't claim "Azure-only" or "OpenAI-only" — multi-provider is the design center.
- **Memory model**: **Pluggable Context Providers** — Foundry Agent Service, Mem0, Azure Managed Redis, Neo4j, or custom store. The Context Provider API gives deterministic hooks to assemble the prompt on every turn (read path) and update state on every turn (write path). RAG supported by adding a Context Provider. Memory types: conversational history, persistent key-value state, vector-based retrieval. Memory is probabilistic at retrieval time — vector similarity introduces a calibration step the operator must tune. NO substrate-enforced memory equivalent to TPipe's ContextBank.
- **Multi-agent orchestration (5 patterns)**: Sequential, Concurrent, Group Chat (manager-routed, inherited from AutoGen), Handoff (responsibility transfer as context evolves), Magentic (Magentic-One-derived manager-driven dynamic task ledger, planning-heavy for open-ended problems). Two workflow APIs: Functional (`@workflow`/`@step` decorators, native Python control flow) and Graph (`WorkflowBuilder`, `executors`, `edges`, superstep-based parallel execution). Both APIs fully supported, produce same observable results.
- **Magentic positioning** — designed for "scenarios where the solution path is not known in advance and might require multiple rounds of reasoning, research, and computation." Microsoft Learn caveat: "It is untested how well the Magentic orchestration will perform outside of the original Magentic-One design." Don't position Magentic as a Junction equivalent — different mechanism (manager-with-task-ledger vs role-based voting harness with moderator intervention).
- **Tool calling**: MCP (Model Context Protocol, external tool servers) + OpenAPI (any REST API with spec auto-imported as callable tool) + AIFunctions. All three paths are EXTERNAL — tools live outside the agent process, called over network or inter-process boundaries. Different problem axis from TPipe's PCP (in-process multi-language sandbox). Don't position MCP as equivalent to PCP.
- **Middleware**: Flexible system for request/response processing, exception handling, custom pipelines. Use cases: content safety filters, logging, compliance policies, custom logic. Operates "without needing to modify agent prompts." Catchable and configurable. NO equivalent to TPipe's uncatchable KillSwitch substrate primitive.
- **Observability**: Built-in OpenTelemetry integration. Automatic emission of traces, metrics, logs. Exportable to Azure Monitor / Application Insights, Aspire Dashboard, Jaeger, or any OTel-compatible backend. The "Agents (Preview)" view in Application Insights gives end-to-end cost/latency insights. NO self-hosted equivalent to TPipe's TraceServer — substrate is the trace emission, storage is the operator's problem.
- **Checkpointing** — workflows support "Save workflow states via checkpoints, enabling recovery and resumption of long-running processes." **Limitation surfaced by Diagrid (March 2026)**: "For multi-agent patterns (Graph, Swarm, Workflow), the orchestrator state is persisted after every node call via AfterNodeCallEvent hooks." A community discussion (github.com/microsoft/agent-framework/discussions/2305) notes checkpoint storage constraints for long-running HITL workflows. Do not claim "fully durable workflow state" — claim what the docs say, note the Diagrid analysis as a real critique.
- **Pricing (Foundry Agent Service)**: "No additional charge for creating or running Foundry-native agents using prompts and workflows." Charges for: model token consumption through Foundry Models, Foundry Tools and Foundry IQ connections, hosted agent compute per hour, built-in tools. Built-in tool rates: File Search Storage $0.11/GB-day (1 GB free), Code Interpreter $0.033/session, Web Search $14/1k transactions, Custom Search $14/1k transactions. Memory billed separately (long-term, short-term, retrieval — per-1k-items rates not all public). Hosted agents billed by container compute per hour. The "free framework" claim is true at the SDK level; the Foundry-managed runtime is consumption-based.
- **Foundry Hosted Agents** — deploy with 2 additional lines of code per GitHub README. Customer-dedicated containers managed by Foundry with built-in scaling, observability, security, governance. Billed by underlying container compute per hour.
- **Cloud-agnostic runtime**: containers, on-prem, multi-cloud. NO native mobile/edge story — managed runtimes do not compile to iOS/Android binaries.
- **Where MAF wins outright**: language reach (Python + .NET, the two largest enterprise developer bases); production stability commitment (full backward compatibility from v1.0); Microsoft distribution + Azure ecosystem (Foundry Agent Service, App Insights, Logic Apps, Fabric, SharePoint); open-standards interop as first-class (MCP, A2A, OpenAPI); Foundry Hosted Agents (2-line deploy); MIT licensing; 5 orchestration patterns covering more topology shapes than TPipe's 3.
- **Where TPipe wins outright**: substrate primitives (KillSwitch, Chain-of-Draft, ContextBank + LoreBook, DistributionGrid, GraalVM Native); deterministic memory with per-key concurrency and retrieval/write-back function bindings; self-hosted observability at $0 (TraceServer); in-process multi-language tool sandbox (PCP vs MAF's external MCP); uncatchable substrate-enforced termination; JVM-first substrate power (ClassLoader, JVMTI, JFR, GraalVM Native); 8 reasoning methods including the only production-validated reasoning optimization in the survey; mobile/edge via 50MB native binary; fixed all-inclusive pricing.
- **Magentic vs Junction — do not equate**: Magentic is broader (open-ended task ledger); Junction is deeper (role-based voting with moderator intervention). Different mechanisms, different coordination patterns. The MAF page should not present Magentic as a Junction equivalent.

## JetBrains Koog

- **Latest stable version**: 1.0.0 (released May 27, 2026 at KotlinConf '26). Prior 1.0.0-preview3 series introduced the stable/beta module split.
- **Stability commitment**: "no breaking changes for stable modules for at least one year." Real production-readiness signal — verify it's still in effect when auditing.
- **Language/runtime**: Kotlin/JVM (Java 17+) + Kotlin Multiplatform (JVM/Android/iOS/JS/WasmJS). Don't claim "Kotlin only" — Java API shipped March 2026 with idiomatic builder-style API and Spring Boot integration.
- **Three mobile paths** (worth being precise): (1) KMP for cross-platform code sharing, (2) GraalVM Native is NOT supported in Koog — that's TPipe's path, (3) **LiteRT on Android** for on-device model inference (new in 1.0). TPipe's mobile story is GraalVM Native → .so/.dylib; Koog's is KMP + LiteRT.
- **Paradigm**: Graph-based (basic, functional, graph, planner agents). NOT a substrate. Don't equate Koog's "graph" with TPipe's "substrate" — they're different generations of agent framework architecture.
- **Memory model**: Two-tier (Chat Memory + Long-Term Memory) plus `AgentMemory` (subjects and scopes, encrypted storage, memory sharing between agents, automatic fact detection) + RAG (vector store, probabilistic similarity) + history compression (5 strategies: NoCompression, WholeHistory, ChunkedHistoryCompression, etc.). No deterministic keyword-triggered memory equivalent to TPipe's LoreBook.
- **Multi-agent**: Subgraphs (composable architectures) + A2A protocol (cross-platform/cross-cloud HTTP/JSON, client-server hub-and-spoke) + Agent-as-tool (dynamic agent creation) + **Planner agents** (1.0, beta — iterative plan-execute-verify). NO equivalent to TPipe's Junction democratic voting (6 recipes, 3 discussion strategies, weighted threshold consensus).
- **Safety/Governance**: Checkpoint/restore (state machine save/restore) + Trust Layers (token authorization, encryption, human-in-the-loop) + Agent Events. **Known open bug**: `ctx.storage` state is NOT restored on checkpoint restore (GitHub issue #1944, opened May 2026, status unverified in 1.0 release notes). Do NOT claim "checkpoint/restore is reliable" without checking the issue's current state. Koog 1.0 release notes do not list this as fixed.
- **Tool calling**: Type-safe, serializable tools with auto-generated schemas + MCP (Model Context Protocol, external tool servers) + class-based tools + annotation-based tools. **Known issue**: annotation-based tools silently stop without error (GitHub issue #798). NO equivalent to TPipe's PCP multi-language internal sandbox.
- **Observability**: Multiplatform OpenTelemetry (1.0, PR #1942 — Langfuse/Weave/DataDog on every target via Ktor-based OTLP/JSON exporter, not just JVM) + Agent Events + Langfuse integration ($29–$2,499/mo SaaS) + W&B Weave ($2,100+/mo base) + DataDog. NO self-hosted equivalent to TPipe's TraceServer. Closing the multiplatform gap did NOT close the SaaS-subscription requirement.
- **Pricing/TCO**: Apache 2.0 framework is free. Production observability is NOT — Langfuse Enterprise ($2,499/mo = $29,988/yr) + Weave ($2,100+/mo) = $50,000+/yr at commercial scale. TPipe's $7,500/yr Manifold tier is all-inclusive (TraceServer, KillSwitch, PCP, containers). Koog 1.0's stability commitment does not change the SaaS cost.
- **ACP (Agent Client Protocol) — new in Koog 1.0**: LSP-style JSON-RPC standard for **editor-to-agent** (NOT agent-to-agent). Zed introduced Aug 2025, JetBrains joined shortly after. Current adoption: Zed, JetBrains IDEs (IntelliJ, PyCharm, WebStorm), Cursor (joined March 2026), Goose (Block open source), Kimi CLI (Moonshot AI), Auggie (Augment Code). **Do not confuse ACP with TPipe's P2P — ACP solves editor-IDE-to-agent, DistributionGrid solves agent-to-agent mesh. Different problems, different protocols.**
- **Where Koog wins outright**: Spring AI integration (April 2026, orchestration layer above Spring AI abstractions), ACP-native IDE reach, Kotlin Multiplatform breadth, JetBrains brand and distribution.
- **Where TPipe wins outright**: Paradigm (substrate vs graph), Chain-of-Draft (75% token reduction, Zoom AI paper 2502.18600), P2P DistributionGrid, LoreBook deterministic memory, KillSwitch propagation, TraceServer self-hosted observability, PCP multi-language sandbox, Junction democratic voting, GraalVM Native mobile ABI.

## Sources to prefer

- Official docs: `docs.langchain.com`, `langchain-ai.github.io/langgraph`, `docs.crewai.com`, `adk.dev`, `microsoft.github.io/autogen`, `a2a-protocol.org`
- Official press releases / Linux Foundation announcements
- Official GitHub releases / changelogs

## Sources to avoid

- Third-party comparison blogs (use only as starting points)
- Stack Overflow answers (likely stale)
- Reddit threads (anecdotal)
- Marketing pages from competitors (self-serving)

## Verification log template

When doing the research, keep a log so the user can see what changed and why.

```
| Claim | Current Text | Status | Truth | Source URL |
|-------|--------------|--------|-------|------------|
| "Python-based" | ADK is Python framework | INCORRECT | Multi-language: Python, TS, Go, Java, Kotlin | https://adk.dev/ |
| "MemorySaver by default" | LangGraph Checkpointer defaults | VERIFIED | In-memory MemorySaver is default | https://langchain-ai.github.io/langgraph/ |
| "AutoGen 0.4 announced 2024" | AutoGen history | INCORRECT | Released January 14, 2025 | https://microsoft.com/en-us/research/blog/autogen-v0-4-... |
```

Status values:
- **VERIFIED** — claim matches current state
- **INCORRECT** — claim is wrong; state the truth
- **STALE** — was true at some point, no longer; state the current state
- **MISSING** — important feature not mentioned in the page but should be
