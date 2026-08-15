# Agent harness comparison axes

Durable comparison axes for TPipe feature blog posts that position against the current agent framework ecosystem. The specific facts (CrewAI star counts, OpenAI pricing, ADK 1.0 release date) are time-bounded and re-verified per the verify-everything rule in bigwang. The axes themselves are durable: any agent framework that competes in this space has to make a choice on each one.

Use these axes to build the comparison table in stage 2b of the pre-write grounding workflow.

## The axes

### Routing model
How does the framework decide which step / agent / node to invoke next?
- Static graph (conditional edges at runtime)
- Hierarchical / manager agent
- Selector function over a group
- LLM-named dispatch (model emits a name, framework resolves to a callable)
- Event-driven (events trigger steps)
- Handoff (agent delegates to another agent)

### Completion check
Does the framework have a first-class mechanism for determining the task is done?
- Manual (developer wires a terminal node)
- LLM judge
- Stop message in the conversation
- No events emitted
- No completion check (relies on caller)

### Verifier
Does the framework have a separate LLM-driven verifier that re-checks the work before exit?
- None
- Yes — separate agent (Ralph-loop equivalent)

### Memory substrate
How does the framework manage the conversation history and any long-term memory?
- Typed state dict with reducers
- Per-agent memory (short-term, long-term, entity)
- Conversation log (raw)
- Service registry (swappable backends)
- Custom substrate (e.g. contextWindow + miniBank + lorebook + cursors + stash)

### Token cost cap
Does the framework enforce a hard ceiling on token spend per run?
- None
- Per-call ceiling (the framework's wrapper checks before each LLM call)
- Per-run ceiling (the framework checks the running total)

### Mid-loop intervention surface
Can a developer (or external system) intervene mid-loop, transform state, and steer execution?
- Conditional edges
- Middleware
- Guardrails (input/output only)
- Steps
- DITL hooks (full lifecycle)
- None

### Risk-aware routing
Does the framework classify steps/paths by risk and gate execution by risk level?
- None
- Path-level risk + path-safety gate
- Per-step safety check

### Stash for oversized outputs
Does the framework have a mechanism to put oversized step outputs on a shelf, referenced by ID, instead of inlining them in the next prompt?
- None
- Stash with manifest (id, reason, byte size, preview)

### Pre-emption on parallel writes
Does the framework detect that a concurrent compaction/memory write has already covered the work and discard the stale result without mutating state?
- None
- CAS-protected cursor (generation counter)
- Last-write-wins

### Inflated-result recovery
When a summarization or compaction returns a result larger than the input, does the framework roll back and retry with a smaller scope?
- None
- Backup ring buffer + retry-with-smaller-scope
- Hand off to a different strategy (e.g. truncation)

### P2P / cross-process nesting
Can a single harness be nested inside another, or is it always a leaf?
- No nesting (leaf only)
- P2P interface (nested harness)
- Cross-process protocol (A2A, gRPC)
- DistributionGrid-style swarm

### Runtime substrate
What is the harness implemented in?
- Python
- Kotlin / JVM
- Multi-language (Python + Go + Java + TypeScript)

### Native binary deploy
Can the harness run as a single binary (no JVM, no Python interpreter)?
- No (Python wheel or pip install)
- GraalVM native image (`.so` / `.dylib` / `.exe`)

## How to use this

When a TPipe feature blog post needs to position against the current agent framework ecosystem:

1. Build a 2D table: one row per framework, one column per axis.
2. For each cell, write what that framework does. Cite the source URL (current docs, not third-party blogs).
3. Mark TPipe's column last. The column IS the blog post's positioning argument.
4. Be specific. "Yes, with X" beats "yes." Cite the file:line for TPipe's behavior, the docs URL for the competitor.
5. Re-verify the specific facts per the verify-everything rule in bigwang before shipping. Frameworks ship major updates frequently.
