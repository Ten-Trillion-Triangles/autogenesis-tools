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

## Reference files

- `references/code-comment-hygiene.md` — what NOT to write in KDoc/inline
  comments on PumpStation source (plan-narration, before/after framing,
  audit-history references). Use the included grep audit pass to clean up.
- `references/sandbox-tdd-recipe.md` — this file.