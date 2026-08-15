# The Seven Design Choices That Have No ReAct Equivalent

Each design choice is a structural answer to a ReAct failure mode. All seven compose into the system. Each is a TPipe native primitive, not a bolt-on.

## 1. Personality is a first-class, auto-injectable variable

The four-tier explicit priority is `personality > systemTask > userGuidelines > entryUserPrompt`. The fields are concatenated into the judge and dispatch system prompts at content-build time, in this order, before any other instruction. The personality forces the agent to take on the persona and prioritize it above every other instruction.

When a pipe is configured with `RolePlay` reasoning, the personality is automatically applied. Every pipe in the harness that uses RolePlay embodies the same persona. A small judge model on one provider and a frontier dispatch model on another share the same character. The persona is structural, not cosmetic.

- **Source:** `PumpStation.kt:988-1015` (the four fields), `PumpStationHelpers.kt:640-661` (buildJudgeSystemPrompt injects personality), `Structs/ModelReasoning.kt:657` (RolePlay reasoning type).
- **ReAct failure addressed:** Persona is a one-time system prompt overlay. It does not propagate to sub-agents, it does not survive LLM swaps, it does not enforce priority over system task / user guidelines / entry prompt. PumpStation's personality is a property of the harness, not a property of the LLM.

## 2. Paths compress the dispatch agent's input

A PumpStation path is a single named function. The dispatch agent sees N path names plus descriptions plus schemas, where each path abstracts an entire turn. The LLM picks one path by name. The path can call 100 tools internally, spawn 5 subagents, run async work, and return one `MultimodalContent`. The LLM never sees the internal complexity.

- **Source:** `PumpStation.kt:225-634` (PathObject class), `PumpStation.kt:198-216` (PathRequest data class), `PumpStation.kt:1739-1935` (getVisiblePathDescriptorsInternal).
- **ReAct failure addressed:** Flat tool list inflates the LLM's input as tools accumulate. Hermes ships 60+ tools. Claude Code ships 80+ commands plus skills plus plugins. Codex ships a 32KB AGENTS.md blob. A 10-turn task on Hermes burns roughly $0.50 in tool-definition overhead. The same task on PumpStation with 12 paths burns roughly $0.05 in path-descriptor overhead. Input saving 3-10x. Smaller models can dispatch effectively because the surface is smaller.

## 3. Paths curate the path's output

The path's execution function is a Kotlin function. The developer is in the path. The developer can filter, parse, summarize, transform, or stash the path's output before the LLM sees it. A shell call returns 5,000 tokens of directory listing. The path's execution function returns 200 tokens of curated output. "47 files, 3 modified in the last hour, 2 with errors." The LLM gets the signal, not the noise.

Three independent layers of output curation:
1. **Inside the path.** The developer's code shapes the result.
2. **`pathTransformationFunction` DITL hook.** Fires after path validation, transforms the result.
3. **`pathValidationFunction` DITL hook.** Returns false to reject the result; the original input flows through as the turn's result.

All three layers are in code. All three are deterministic. None of them require an LLM call.

- **Source:** `PumpStation.kt:573-630` (PathObject.execute priority chain), `PumpStationModels.kt:198-209` (path-safety / path-transformation hook signatures).
- **ReAct failure addressed:** Tool calls return raw output. The LLM sees 5K tokens of terminal noise and has to do the curation work. Cost scales linearly with output size. Smaller models are confused. PumpStation puts the curation in code, where it is verified and deterministic.

## 4. Eighteen DITL hooks at every phase boundary

`preInitFunction`, `preValidationJudgeFunction`, `preInvokeFunction`, `preValidationDispatchFunction`, `postGenerateFunction`, `pathValidationFunction`, `pathTransformationFunction`, `postMemoryFunction`, `preCompactionFunction`, `postCompactionFunction`, `onContextTruncated`, `pathSafetyFunction`, `pathLimitExceededFunction`, `compactionRolledBackFunction`, `externalContextProvider`, plus the agent-level interventions (interventionAgent, healthAgent, preInitAgent).

Every hook is a suspend function with the full harness state in scope. `preInvokeFunction` returning `false` aborts the run with `InterventionTerminated`. `pathValidationFunction` returning `false` rejects the path's result. `postGenerateFunction` returns a `P2PInterface` to chain another agent. `preCompactionFunction` modifies the input to the summary agent. `compactionRolledBackFunction` overrides the backup restore.

- **Source:** `PumpStation.kt:1578-1620` (DITL hook fields), `docs/containers/pumpstation.md` (DITL Hooks section with the full table).
- **ReAct failure addressed:** ReAct loops have one or two hooks at the LLM call boundary (Hermes `pre_tool_call` / `pre_llm_call`, Claude Code `PreToolUse` / `PostToolUse`). They can read state, log, and block a tool call. They cannot intervene mid-loop at every phase, mutate the MiniBank between judge and dispatch, chain a P2PInterface after dispatch, or override a backup restore. PumpStation's DITL surface is structural, not bolted-on.

## 5. Three-state history with pre-prune transformation

Three distinct history states. `turnSummary` is the string at the top of every prompt. `turnHistory` is the curated middle. `rawTurnHistory` is the full event log for DITL hooks and the goal agent.

The LLM sees `turnSummary` plus `turnHistory`, never `rawTurnHistory`. The default pre-prune transform drops blank turns, drops stash placeholders, collapses duplicate system messages, drops pure echoes, collapses tool-call and result pairs into one turn, strips excess metadata, normalizes whitespace, and drops turns already in the turnSummary. A custom pre-prune transform can be wired with `setPrePruneTransform` or `appendPrePruneTransform`.

- **Source:** `PumpStationLoop.kt:584-602` (default pre-prune rules), `PumpStation.kt:1264-1270` (prePruneTransform + extraPrePruneTransforms fields), `PumpStation.kt:1167-1175` (turnHistory + rawTurnHistory properties).
- **ReAct failure addressed:** The conversation grows with every turn. Tool calls and results pile up. Duplicate system messages echo. The LLM reasons over a wall of noise. PumpStation's curated stream keeps the LLM's input dense. No terminal vomit. No duplicate system messages. No tool-call sprawl.

## 6. Native memory, compaction optional

PumpStation ships with TPipe's memory substrate. `ContextWindow` plus `MiniBank` plus `LoreBook` plus `TokenBudget` plus `TruncationSettings`. The runtime context algorithm runs at every prompt build. Lorebook entries are selected by priority and weight. Multi-page MiniBank budget allocation is enforced. Token overflow triggers truncation, not compaction.

Three memory management modes:
- `Compaction` — traditional summary-based path
- `Truncation` — TPipe's `TokenBudget` plus lorebook selection plus MiniBank allocation with no summarization
- `Hybrid` — both, auto-promoted from `Compaction` if a lorebook or summary agent is configured

In `Truncation` mode, the developer does not bind a summary agent. The compaction phase returns `SkippedNoAgent` and does no work. The LLM never sees a compression step. Context management is deterministic.

- **Source:** `PumpStation.kt:84-89` (memory modes enum), `PumpStationLoop.kt:1153-1168` (compaction phase returns SkippedNoAgent when no summary agent), `PumpStationDefaults.kt:44-45` (recommended default is Truncation, not Compaction, for first live runs).
- **ReAct failure addressed:** Compression is a hand-rolled prompt-trimming hack or a multi-layer cascade (Codex and Claude Code each ship 5-layer compaction). PumpStation's memory is a designed substrate. Compaction is one option, not mandatory. Truncation mode means no LLM-driven compression at all.

## 7. Stash and retrieve for oversized outputs

When a path's output would exceed the context window, the harness stashes it. The full content moves to a stash map. A `StashEntry` is added to the manifest with `id`, `sourcePath`, `createdTurn`, `reason` (TokenOverflow, BinaryPayload, ErrorLog, UnsafeForPrompt, DeveloperRequested, BackgroundResult), `tokenEstimate`, `byteSize`, and `preview`. A `StashCreated` event is emitted. A placeholder goes into the turn history.

The LLM sees the reference. A path designed for stashed content can call `getStashContent(stashId, station)` to retrieve the full content. A follow-up path can parse the content, summarize it, write it to a file, or route it to a subagent. The multi-path pattern handles oversized outputs without inflating the conversation.

- **Source:** `PumpStationLoop.kt:1770-1819` (stash creation), `PumpStationPathObjectExtensions.kt:53-59` (getStashContent extension), `PumpStationModels.kt:113-129` (StashReason enum), `PumpStationModels.kt:952-966` (StashEntry data class).
- **ReAct failure addressed:** No ReAct loop has a stash. A 50K token tool result is a context blowout. The LLM has to handle the noise, the conversation inflates, the cost scales linearly with output size. PumpStation's stash is a first-class data structure with a manifest, an event, a retrieval API, and a multi-path pattern.

---

## Why these compose

Each design choice addresses a specific ReAct failure mode:

| ReAct failure mode | PumpStation design choice |
|---------------------|---------------------------|
| Persona is a one-time system prompt overlay | Personality is a harness property, auto-injected into RolePlay pipes |
| Tool list inflates the LLM's input | Paths compress the dispatch agent's input |
| Tool calls return raw noise | Paths curate the path's output |
| Hooks are at the LLM call boundary | DITL hooks are at every phase boundary |
| Conversation grows unbounded | Three-state history with pre-prune transformation |
| Compression is a hack | Native memory substrate, compaction optional |
| Oversized tool outputs blow context | Stash and retrieve pattern |

The combination is a system, not a feature. None of the seven choices alone is the differentiator. All seven together are.

## Cross-references

- **For the ReAct contrast:** see `SKILL.md` § "PumpStation vs a ReAct Loop" for the structural delta in three points
- **For the Manifold dichotomy:** see `SKILL.md` § "When to Reach for PumpStation vs Manifold" for the user-facing rule
- **For the magic contracts:** see `SKILL.md` § "Magic Contracts" for the eight LLM-facing JSON contracts
- **For the two-scope loop:** see `SKILL.md` § "Two-Scope Loop Structure" and `references/loop-execution-and-goal-validation.md`
- **For the PCP function binding:** see `references/pcp-data-classes-deep-dive.md`
