# PumpStation Doc Set — Worked Example

Reference recipe for "writing brand-new docs for a complex TPipe subsystem." Captures the workflow, the file shapes, the things to verify, and the bumps hit during the PumpStation doc-set session. Use this as the template when the next TPipe subsystem needs the same treatment.

## Session context

- Subsystem: `PumpStation` — the judge/dispatch/path-loop agentic harness.
- Branch: `PumpStation` (active development; 14 files modified vs `origin/PumpStation`).
- Source layout: main class is 4,041 lines, plus 5 sibling files (models, DSL, helpers, v3 models, path-object extensions) and a TPipe-Defaults factory.
- Design doc: `docs/superpowers/specs/2026-06-10-pumpstation-execution-loop-design.md` — 649 lines, approved sections 1-5.
- Pre-existing docs: NONE. Cross-references existed for Manifold, Junction, DistributionGrid, but PumpStation was un-documented in `docs/containers/` and `docs/api/`.

## File shapes produced

Two valid shapes, depending on whether the models section is large enough to warrant its own file.

### Shape A: 3-file (models folded into API reference)

| File | Lines | Purpose |
|------|-------|---------|
| `docs/containers/pumpstation.md` | ~810 | Main reference. Architecture, loop, exit mechanisms, paths, memory, concurrency, DITL hooks, magic contracts, pause/resume/snapshot, kill switch, tracing, full DSL surface, factory, vs Manifold/Junction, common failures, best practices. |
| `docs/containers/pumpstation-how-to.md` | ~680 | Magic contracts and how-to. Required setup checklist, the six magic contracts (judge JSON, dispatch JSON, execution function signature, flags, PCP binding, FlagTriggered loop control), 10 build recipes, custom agents, anti-patterns. |
| `docs/api/pumpstation.md` | ~1,140 | Exhaustive API reference. Every public method on `PumpStation` and `PathObject` with signatures and defaults, all 14 enums, all data classes, the v3 compaction models, the 39 sealed `PumpStationEvent` types, all 9 DSL blocks, the TPipe-Defaults factory. |

### Shape B: 4-file (models split out — used when the sealed-event / enum taxonomy is large)

| File | Lines | Purpose |
|------|-------|---------|
| `docs/containers/pumpstation.md` | ~1,460 | Main reference. Architecture, two-scope loop, agent contracts (one section per contract), PathObject, DSL builder, DSL block reference, execution flow, phase reference, memory management, concurrency modes, DITL hooks, path risk levels, loop guards, reserve paths, stash/snapshots/pause-resume, tracing, kill switch, P2P integration, common startup failures, best practices. |
| `docs/core-concepts/pumpstation-magic-contracts.md` | ~590 | Magic contracts reference. Default prompt text, required JSON shape, data class signature with `path:line`, parser function name with `path:line`, strictness policy, fallback behavior, repair loop, testing the contracts. |
| `docs/api/pumpstation.md` | ~295 | API reference. Public properties, public functions, PathObject class, TurnResult, PumpStationBuilder, enums reference. |
| `docs/api/pumpstation-models.md` | ~590 | Models API reference. Every enum, every V3 compaction model, path description models, memory/action models, health models, failure policy/snapshot models, task state and sealed events, loop control models, source file locations. |

Plus updates to:
- `docs/containers/container-overview.md` — add to orchestration container list, implementation status table
- `docs/containers/cross-cutting-topics.md` — add to tracing table, kill switch table, implementation status table
- `docs/api/tpipe-defaults-package.md` — add `PumpStationDefaults` section
- `README.md` — add to container architecture section

**Total:** Shape A: 2,627 new doc lines. Shape B: 2,931 new doc lines. Either is acceptable; pick based on whether the models taxonomy is dense enough to warrant its own file.

The magic-contracts file lives in `docs/containers/pumpstation-how-to.md` (Shape A) or `docs/core-concepts/pumpstation-magic-contracts.md` (Shape B). Both locations are valid; the difference is whether you treat the contracts as a container-specific how-to or as a cross-cutting concept. Shape B was used in the 2026-06-15 session because the contracts are referenced by every container doc and the user wanted them discoverable from the core-concepts nav.

## Workflow that worked

### 1. Load the domain skill first

`skill_view(name='pump-station')` returned:
- The 4+1/4/3 architecture breakdown (4 core agents, the loop, the path sub-system, memory management).
- The PathObject schema contract (lightweight PCP-inspired, NOT full P2P, NOT full PCP).
- The pump-station-vs-Manifold comparison table.
- The two critical pitfalls (P2PInterface new members need default bodies; PathObject.init() validation).

That last point — "P2PInterface new members need default bodies" — saved a multi-file audit later.

### 2. Read the spec before reading the code

`docs/superpowers/specs/2026-06-10-pumpstation-execution-loop-design.md` fixed the vocabulary:
- Phase names: `PreInit`, `HealthCheck`, `Judge`, `Dispatch`, `PathSafety`, `PathExecution`, `PathValidation`, `Intervention`, `ForegroundAgents`, `MemoryUpdate`, `Compaction`, `GoalValidation`, `Exit` (13 phases).
- 11 pause phases.
- 13 DITL hooks.
- The 3-tier error model.
- The 6-section design philosophy ("quick and dirty — auto-inject what the developer doesn't supply").

Without the spec, you ship docs that name phases `BeforeJudge` instead of the correct `BeforeJudge` (would have been fine), or worse, mis-spell the v3 compaction result types (the `HandedOff` vs `HandedOffToTruncation` trap I almost hit).

### 3. Batch-read source files

In one turn, issue `read_file` calls for:
- `PumpStation.kt` (4041 lines, paginated 3×)
- `PumpStationModels.kt` (1070 lines, paginated 2×)
- `PumpStationV3Models.kt` (179 lines)
- `PumpStationDsl.kt` (1684 lines, paginated 2×)
- `PumpStationHelpers.kt` (816 lines, paginated 2×)
- `PumpStationDefaults.kt` (154 lines)
- `PumpStationPathObjectExtensions.kt` (59 lines)
- `TPipe-Defaults/.../PumpStationDefaults.kt` (150 lines)
- `TPipe-Defaults/.../examples/pumpstation/PumpStationOpenRouterExample.kt` (152 lines)
- A short browse of the rest (test files, AGENTS.md, sibling docs)

This is the right shape: paginate, batch, do not react between pages.

### 4. Read sibling docs for format

`docs/containers/manifold.md` and `docs/containers/junction.md` (842 and 386 lines) set the format:
- `> 💡 **Tip:**` callout immediately after the title.
- `## Table of Contents` with anchor links.
- `## Section → ### Subsection` hierarchy.
- Inline `path:line` references.
- "See Also" footer at the end.
- Comparison tables for "what X provides to Y" / "what Y must provide back" contracts.

`docs/api/lorebook.md` and `docs/api/pipe.md` set the API doc density (one function per `####` heading, behavior in `**Behavior:**` bold).

### 5. Read tests for magic contracts

`src/test/kotlin/Pipeline/` contains the magic contracts:
- `PumpStationTestFixtures.kt` — `judgeScriptedResponse`, `dispatchScriptedResponse`, `testPath`. The exact JSON shape the agents must produce.
- `PumpStationSetGetTest.kt` — proves the fluent setters return `this` for chaining, the alias relationship between `setMaxHarnessTurns` and `setMaxTurns`.
- `PumpStationDslParityTest.kt` — exhaustive tour of every DSL var; copying its structure gives you the complete DSL surface in one place.
- `KillSwitchPumpStationTest.kt` — the propagation rules, the trip semantics, the limit semantics.
- `PumpStationPauseResumeTest.kt` — the `Channel<Unit>` rendezvous pattern.
- `PumpStationNewFieldsTest.kt` — confirms default values for every new config field.

These are the most valuable sources for the how-to doc's "Required Setup Checklist" and the magic-contracts section.

### 6. Verify every enum / method / event name

Caught my own bug here. I wrote `PUMP_STATION_COMPACTION_HANDED_OFF_TO TRUNCATION` in the cross-cutting-topics update. The actual enum value is `PUMP_STATION_COMPACTION_HANDED_OFF`. I also initially wrote `PUMP_STATION_COMPACTION_ATTEMPT_COMPLETED` which doesn't exist at all.

Verification command (run after writing any table that lists these):
```bash
grep -n "PUMP_STATION_" src/main/kotlin/Debug/TraceEventType.kt
```

Lesson: never trust your own recall of an enum list. The single most common error in fresh-from-code docs is "looks right but is wrong" on enum values, event types, or method names. Diff against source before committing.

## Magic contracts: first-class coverage requirement

The user explicitly demanded that all magic contracts (LLM-facing JSON payloads the model must emit) be "fully covered and clear in the docs, as well as where said data classes are and how to get at them." PumpStation has **eight** magic contracts — Judge, Dispatch, Path, Goal, Path-Safety, Health, Lorebook, Summary — plus an inbound path-descriptor protocol and an outbound flag-based control surface. Each contract must be documented with:

1. The default prompt text in full (so the reader sees what the LLM is asked to produce)
2. The required JSON shape
3. The data class name with `path:line` location
4. The parser function name with `path:line` location
5. Strictness policy (lenient vs strict) and the fallback behavior on parse failure
6. Whether a repair loop exists

The strictness is **by design** and must be documented:
- Judge and Health are lenient (fall back to defaults, continue the loop)
- Dispatch is strict (returns null → repair loop)
- Path-Safety is the strictest (`safe` must be a JSON boolean literal; string `"true"` is rejected)

The user specifically called out that PumpStation's contract surface is "a lot smarter" than Manifold's — meaning the docs need to be correspondingly more thorough. The bare "we have a judge, it returns JSON" treatment that suffices for Manifold is not acceptable for PumpStation. Every contract needs its own section with full coverage of the points above.

## Style: no LLM 4th wall breaks

The user explicitly required: *"this has to be written like a professional software docs so don't do classic llm 4th wall breaks here."* This is a strong, persistent style preference for TPipe source documentation. When writing any TPipe doc, the output must:

- **No** AI-style preambles ("In this document we will explore...", "Let's dive in...", "I hope this helps")
- **No** first-person voice unless quoting a developer-facing API
- **No** "as an AI" or "as a language model" framing
- **No** "of course!" or "happy to help!" interjections
- **No** hedging like "it's worth noting that..." when a direct statement is appropriate

Match the existing `manifold.md` / `junction.md` / `distributiongrid.md` style. Their openings are:
- A `> 💡 **Tip:**` callout
- A direct definition in the first paragraph
- An immediate `## Table of Contents`

Their section bodies are:
- Tables with concrete columns
- Code blocks with realistic calls
- `path:line` references
- "See Also" footers
- Direct prose, no conversational asides

The user is paying for engineering rigor, not conversation. Match the existing siblings.

## Things to verify checklist

For a TPipe subsystem doc set, before committing:

- [ ] Every enum value listed in the doc appears in the source (grep the enum name).
- [ ] Every event / phase / status type listed in the doc appears in the source.
- [ ] Every public method signature in the API doc matches the source (parameters, defaults, return type).
- [ ] Every `path:line` reference in the doc points to existing code at that line.
- [ ] Cross-references in updated existing docs (overview, cross-cutting-topics, README) point to the new files.
- [ ] The cross-cutting-topics tracing table row matches the new tracing method.
- [ ] The cross-cutting-topics kill switch row matches the new kill switch behavior.
- [ ] The README TOC has a link to the new doc.
- [ ] Any examples in the doc actually compile (best-effort: check the function names and types against source).
- [ ] Every magic contract has its data class and parser function cited with `path:line`.
- [ ] Strictness policy is documented per contract (not a footnote, alongside the data class).
- [ ] No "as an AI", no conversational preambles, no "let's dive in" — match the existing sibling style.

## How to apply this to the next subsystem

For the next TPipe subsystem needing the same treatment (likely candidates: any of the P2P sub-systems, the ContextBank, the LoreBook, the DistributionGrid remote handoff protocol, or any new container):

1. Check if a domain skill exists under `software-development/`. If yes, `skill_view` it first.
2. Check if a design doc exists at `docs/superpowers/specs/`. If yes, read end-to-end first.
3. Read sibling docs in the same category (other containers / other API docs) to lock the format.
4. Find the relevant test fixtures — they encode the magic contracts.
5. Choose Shape A (3 files) or Shape B (4 files) based on whether the sealed-event / enum taxonomy is large. Shape B is preferred when the magic-contract count exceeds 4.
6. Write the docs in dependency order: main reference first, then magic-contracts (or how-to), then API reference, then models (if separate).
7. Update cross-references in the same commit.
8. Grep-verify every enum, event type, and method name.
9. Commit all changes in one commit so the docs land atomically with the code they describe.

## File paths produced (for cross-referencing in future work)

- `docs/containers/pumpstation.md` — canonical reference
- `docs/containers/pumpstation-how-to.md` — magic contracts and recipes (Shape A)
- `docs/core-concepts/pumpstation-magic-contracts.md` — magic contracts reference (Shape B)
- `docs/api/pumpstation.md` — full API index
- `docs/api/pumpstation-models.md` — sealed events / enums / data classes (Shape B)
- Source: `src/main/kotlin/Pipeline/PumpStation.kt` and siblings
- Spec: `docs/superpowers/specs/2026-06-10-pumpstation-execution-loop-design.md`
- Example: `TPipe-Defaults/src/main/kotlin/examples/pumpstation/PumpStationOpenRouterExample.kt`
- Domain skill: `pump-station` (under `software-development/`)
