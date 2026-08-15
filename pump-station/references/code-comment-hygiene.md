---
name: pump-station
description: Design, implement, and reason about TPipe PumpStation — a judge/dispatch/path-loop agentic harness with async memory management. Load when working on PumpStation architecture, PathObject schema design, dispatcher contract, memory management modes, or any of PumpStation's eight LLM magic contracts (judge, dispatch, path, goal, path-safety, health, lorebook, summary).
---

# PumpStation

(...existing body kept verbatim — see git history of this skill for the canonical content. This reference file is the new addition, not a replacement.)

## Code-comment hygiene (added 2026-07-10)

When adding new KDoc, inline `//`, or block comments to PumpStation source files
(`src/main/kotlin/Pipeline/PumpStation*.kt`, `PumpStationHelpers.kt`,
`PumpStationLoop.kt`, `PumpStationDsl.kt`, `PumpStationModels.kt`,
`PumpStationEventMetadataTest.kt`, `PumpStationPath*.kt`, etc.), the comment must
describe the *current code*, not the *history of how the code came to be*.

**Forbidden patterns inside comments:**

- `Defect N (YYYY-MM-DD):` — change-log label, belongs in a commit message.
- `F3 fix (YYYY-MM-DD):` / `F3-clone fix (YYYY-MM-DD):` — same.
- `now HALT` / `used to drop` / `previous toString() dump` / `Historical DSL
  builds silently defaulted this to 3` — before/after narration belongs in the
  commit body, not the KDoc.
- `Task N / F3-clone:` / `Case 1 (post-YYYY-MM-DD):` in test-class KDocs — the
  audit/triage history belongs in the plan file.
- `The audit flagged that...`, `The user-corrected answer is...`,
  `Previously this test asserted X` — re-litigation of the design decision.
- Verdict/wrap-up phrasing in test KDocs: `should pass against the existing
  harness without any production patch unless a layer is broken`,
  `These tests document the three-layer pattern`, `It would be theater — ...`.
- `per skill Pitfall #N+6` / `Per OOB cross-cutting rule from cage` — references
  to meta-process belong in the plan file, not the test KDoc.

**Required pattern:** the comment names the contract or behavior of the code
adjacent to it. Reference symbols by `[Brackets]` (KotlinDoc convention),
point at the test class by name (without audit history), and keep dates out of
the source. If the code's contract is "the loop guard halts the harness",
write that — don't write "loop guard now halts the harness (Defect 19)".

**Audit pass recipe** when the user pushes back on code comments:

```bash
git diff -- src/main/kotlin/Pipeline/ src/test/kotlin/Pipeline/ \
  | grep -nE 'Defect [0-9]+ \(|F3[- ]?clone? fix|YYYY-MM-DD|used to|Historical|previously|previously this test|The audit|user-corrected|now HALT|now halts'
```

Every match is a candidate for rewriting into a contract statement. The
exception is references to **stable identifiers** like `[Pipe.getNearestPumpStationParent]`,
`Pipe.kt:2319-2341`, or test-class names — those are pointers, not narration,
and stay.

## Sandbox-tuned TDD recipe (added 2026-07-10)

Direct `kotlinc` compilation of the TPipe test tree does NOT have the
`kotlinx-serialization` compiler plugin wired in, so any test that exercises
`P2PInit → applySystemPrompt → refreshPipelinesPrompts → examplePromptFor(...)`
throws `SerializationException`. Affected tests: every `executeLocal`-driven
PumpStation test that constructs an agent pipeline.

**Approved pivot:** drive the patched helper **directly** as a unit test. The
internal seam is `-Xfriend-paths` (already wired in the Gradle test config)
plus calls like:

- `station.buildPathInput(path, request)` — pump-station-loop.kt:611+
- `station.invokePathInternal(path, input)` — pump-station.kt:2713+
- `station.checkPathSafety(path, input)` — pump-station.kt:2697+
- `station.buildUserMessageForTurn()` — pump-station-helpers.kt:807+
- `station.tracePumpStationEvent(event)` + `PipeTracer.getAllTraces()[runId]` — pump-station-helpers.kt:78+

Pre-existing tests that took the `executeLocal` route and worked under Gradle
(`PathSafetyDispatchFeedbackTest`, `PumpStationDispatchDefaultsTest`, etc.) can
also be exercised; the broken-under-direct-kotlinc claim is specific to
`examplePromptFor` driving through `applySystemPrompt`.