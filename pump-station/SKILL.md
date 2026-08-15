---
name: pump-station
description: Design, implement, and reason about TPipe PumpStation — a judge/dispatch/path-loop agentic harness with async memory management. Load when working on PumpStation architecture, PathObject schema design, dispatcher contract, memory management modes, or any of PumpStation's eight LLM magic contracts (judge, dispatch, path, goal, path-safety, health, lorebook, summary). Also load when wiring a goal-agent test that "passes" despite the agent supposedly failing (the harness checks `result.terminatePipeline`, never text content — Pitfall 9), when a live-mode test class needs the canonical 6-stub + 6-live architecture with trace capture at `TPipeConfig.getTraceDir()`, or when a `tracingConfiguration` setter doesn't take effect (DSL `copyFrom` snapshot ordering — Pitfall 8).
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
  builds silently defaulted this to 3` — before/after narration belongs in
  the commit body, not the KDoc.
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

## ConverseRole tier for harness-injected messages (added 2026-07-24)

When the harness injects a message into `turnHistory` (path-safety hint, empty-pathName hint, empty-rationale nudge, pathSchema-fallback hint, DITL steering entries), the role MUST be `ConverseRole.harness`, NOT `ConverseRole.user` or `ConverseRole.system`. The role-fraud bug is a class-level pattern that hit 5 sites across the codebase before being caught.

**Why each candidate role is wrong:**

- **`ConverseRole.user`** is the LLM provider's contract for human-user input. Tagging a harness-emitted message as `user` is role-fraud: the LLM may weight the message as authoritative user intent, downstream tools that distinguish user input from system instructions will misclassify the hint, and the prompt is now lying about the source of the message. The harness is not a user.
- **`ConverseRole.system`** is the LLM's system-prompt slot. The context-trimming rule at `PumpStationLoop.kt:1015` keeps only the most-recent `system` message (`.filter { turn.role != ConverseRole.system || i == lastSystemIndex }`). That behavior is correct for the system prompt but wrong for harness corrections, which must survive context pressure. Putting hints in `system` would silently prune all but the last one.
- **`ConverseRole.harness`** is a dedicated tier for harness-emitted messages. Distinct from `user` (no role fraud) and from `system` (the trimming rule does not touch `harness` entries, so all five hint kinds survive context pressure).

**The 5 production sites that must use `ConverseRole.harness`** (verified via `ConverseRoleHarnessHintTest` regression coverage):

| File:line | Hint kind | Hint marker |
|---|---|---|
| `Pipeline/PumpStation.kt:3067` | Path-safety rejection | `[Path Safety] Path '<X>' was rejected by the path-safety gate...` |
| `Pipeline/PumpStationLoop.kt:188` | DITL steering entries (DITL one-shot + persistent overlays) | varies — DITL author defines |
| `Pipeline/PumpStationLoop.kt:419` | Empty-pathName dispatch | `[Harness Notice] Your dispatch output was a valid PathRequest JSON but the pathName field was empty...` |
| `Pipeline/PumpStationLoop.kt:914` | pathSchema-fallback (non-JSON pathSchema) | `[Harness Notice] Your dispatch output's pathSchema did not deserialize as a valid PathRequest JSON object...` |
| `Pipeline/PumpStationLoop.kt:3274` | Empty-rationale nudge (gated on `failurePolicy.requirePathSelectionRationale`) | `[Harness Notice] Your dispatch output was a valid PathRequest JSON but the pathSelectionRationale field was empty...` |

**Test contract** to pin (so future hint sites don't regress to the wrong role): `ConverseRoleHarnessHintTest` (`src/test/kotlin/Pipeline/`) covers (a) the enum declares the `harness` tier, (b) the path-safety hint site stores `ConverseRole.harness`, (c) the DITL steering injection site stores `ConverseRole.harness`, (d) static-analysis guard: any future `ConverseRole.user` site in `Pipeline/PumpStation.kt` or `Pipeline/PumpStationLoop.kt` is a regression.

**When to add a new harness hint site**: always pair it with a test that asserts `ConverseRole.harness`. The role is not a "free pick" — it's part of the contract that the LLM prompt's message-source hierarchy depends on.

**Cross-reference**: `pump-station/SKILL.md` "harness-defect-catalog" Defect 27 covers the path-safety hint's dedup behavior; this section covers the orthogonal role-tier concern. Both are required for the hint system to work correctly.

## Path-name case-insensitive registry: map-key boundary contract (added 2026-07-24)

The path-name registry on `PumpStation` (`pathList: MutableMap<String, PathObject>` and `reservePaths: MutableMap<String, PathObject>` at `src/main/kotlin/Pipeline/PumpStation.kt:1181-1188`) is documented as case-insensitive in three places — the KDoc on `pathList` (`PumpStation.kt:1178-1180`), the KDoc on `resolvePath` (`PumpStationHelpers.kt:766-768`), and the build-time uniqueness check (`PumpStationDsl.kt:1099-1102`) — but the implementation was inconsistent: insert sites stored case-preserved (`pathList[path.pathName] = path`), while lookup sites lowercased the key (`pathList[lowerName]`). Any path name with non-lowercase characters (`path("giveUp")`, `path("MyPath")`, etc.) was unreachable at runtime despite being visible to the LLM in the dispatch prompt.

**The contract is `pathName` is a case-insensitive identifier.** The path's own `pathName` field preserves the original casing for display/event output, but every map insert and lookup routes through a single `pathKey(name): String = name.lowercase()` helper.

**The 6 sites that needed the fix in lockstep** (drift between any pair leaves the harness in a worse state than before):

1. `addPath` (`PumpStation.kt:2769-2774`) — store under `pathList[pathKey(path.pathName)]`
2. `addReservePath` (`PumpStation.kt:5156-5162`) — same pattern
3. `getPath` (`PumpStation.kt:2762`) — lookup via `pathKey(name)`
4. `removePath` (`PumpStation.kt:2779-2782`) — same
5. `movePathToReserve` (`PumpStation.kt:2788-2793`) — same
6. Two direct `pathList[name] ?: reservePaths[name]` lookups at `PumpStation.kt:4678` and `PumpStation.kt:4695` (the `mergeDrainedEntries` loop for async path completions) — same

Plus the secondary `revealedReservePaths` (`MutableSet<String>` at `PumpStation.kt:1854`) — its three call sites in `getVisiblePathDescriptorsInternal` (`PumpStation.kt:2210-2211, 2222`) needed `pathKey(...)` normalization on insert and lookup.

Plus `getVisiblePathNames` and `getReservePathNames` must return **original casing** for the LLM-facing menu. They read `pathList.values.map { it.pathName }` (not the lowercase map keys). Without this, the LLM prompt shows `giveup` while the user-registered path is `giveUp`, and the LLM's response (which echoes back the visible-path casing) would dispatch the wrong key.

**The single helper to centralize the rule**:

```kotlin
/**
 * Normalize a path-name key for the [PumpStation.pathList] and
 * [PumpStation.reservePaths] maps. Path lookup is case-insensitive
 * per the contract documented on [PumpStation.pathList].
 */
private fun pathKey(name: String): String = name.lowercase()
```

Add it file-local to `PumpStation.kt` adjacent to the `pathList` declaration. Every map insert and lookup routes through it. The single helper is the only place that knows the normalization rule.

**Test contract to pin** (so future changes to the registry can't silently re-break the case contract): see `references/case-insensitive-path-registry.md` for the 6-test `PumpStationPathCaseInsensitiveTest` that covers addPath/getPath/removePath case-insensitivity, original-casing visibility, end-to-end dispatch with mixed-case path, and reserve-reveal with mixed-case path.

**Symptom** (from the live-04 trace on 2026-07-24): the LLM genuinely saw `giveUp` in its dispatch prompt's visible-paths list (confirmed by `grep "available paths" agent-dispatch.html`), dispatched `giveUp` 19 times, every dispatch failed with `error: UnknownPath, errorMessage: "Path 'giveUp' not found"`, harness exited with `MaxTurnsHit` and `Failed`. The trace evidence is the disambiguator: the LLM is not at fault, the prompt is not at fault, the harness's registry is at fault. Without trace data the prior session had no way to land on this conclusion.

**Why this is a class-level lesson, not a one-off**: every container that has a name-keyed map (Manifold's worker registry, Junction's participant map, DistributionGrid's node table) likely has the same shape — case-preserved insert, case-insensitive lookup. The `pathKey` pattern applies to all of them. The fix is one-line per site; the testing pattern (case-lookup tests + original-casing visibility test) is reusable.

## Stub-server wire-shape fixtures for strict-mode parser tests (added 2026-07-23)

When a PumpStation live+stub test class sets `setApiMode(ApiMode.OpenAIResponses)` (or any wire format the parser enforces strictly), the test's `StubOpenAIServer` MUST wrap canned responses in the parser-accepted envelope shape. A raw JSON snippet like `{"path":"report"}` deserializes to `null` on the strict parser side and trips:

```
P2PException: Failed to deserialize OpenAI Responses body: {"path":"report"}
```

The strict parser (e.g. `OpenAIResponsesResponseParser` at `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/api/OpenAIResponsesResponseParser.kt:73`) requires the full wire shape: `id`, `object`, `created_at`, `status`, `model`, plus a polymorphic `output` list of typed items (`message` items with `output_text` content parts for assistant text, `reasoning` items for chain-of-thought). Any canned response from the stub must be wrapped before being returned.

**Recipe**: add a `stubResponsesJson(text: String): String` helper to the test class that wraps arbitrary text content in a minimal but valid envelope. Refactor every `loopEnqueue(role) { """{...}""" }` call site and the existing `stubJson(...)` helper to route through it. The envelope is:

```kotlin
"""{"id":"stub-resp","object":"response","created_at":0,"status":"completed","model":"stub","output":[{
    "type":"message",
    "role":"assistant",
    "content":[{"type":"output_text","text":"$escapedText"}]
}]}"""
```

with `$escapedText` being the canned content with `"` and `\` escaped. Both fields and the polymorphic `output` envelope are required by `OpenAIResponsesResponse` (`id: String`, `model: String`, `output: List<OpenAIResponsesOutputItem>` are all non-null in the data class at `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/OpenAIResponsesResponse.kt:17`).

**Symptom-to-fix lookup**:

- `P2PException: Failed to deserialize OpenAI Responses body: {...}` on the first LLM call in a stub test → the stub is returning a raw snippet; wrap with `stubResponsesJson`.
- Stub test that pre-enqueued `{"path":"report"}` works in chat-completions mode but fails after the pipe is switched to `ApiMode.OpenAIResponses` → parser is now strict about the wire shape.
- Distinct from a **dispatch contract** mismatch where the stub returns valid envelopes but the dispatch agent's prompt expects a different JSON field name (e.g. `pathName` vs `path` per the magic-contracts doc). That surfaces as a harness-event assertion failure (`PUMP_STATION_POST_GOAL_COMPLETED` never fires) AFTER deserialization succeeds. The fix is a test-data change, not a parser-format change.

**Why the prior-session chat-completions-mode helpers did not catch this**: the existing `stubJson(isComplete, passPipeline)` helper built `{"output":[{"type":"message",...}]}` without the required `id` and `model` fields. It worked when the test pipe was in chat-completions mode (the legacy `/v1/chat/completions` parser is more lenient). When a test sets `setApiMode(ApiMode.OpenAIResponses)`, the new parser's strict shape requirement rejects every payload that lacks `id`/`model`, even if the body has a valid `output` array. The wire-shape fix is unconditional once a test class runs in Responses-API mode.

**Captured from**: 2026-07-23 path-safety rejection triage session, fixing `stub_04_multiPathRiskLevels_postGoalFiresAfterFullLoop` in `src/test/kotlin/Pipeline/PumpStationPostGoalLiveTest.kt`. Commit `2eee334d test(pumpstation): wrap stub server payloads in valid OpenAI Responses envelopes` in TPipe.

The three-layer post-goal-hook failure pattern is documented in detail at `references/stub-test-three-layer-failure-pitfalls.md` — Layer 1 (wire shape, this section), Layer 2 (dispatch contract field name), Layer 3 (termination signal never fires). When a `PUMP_STATION_POST_GOAL_COMPLETED` assertion fails, check the trace HTML size first to disambiguate: < 100KB = Layer 1, 100-500KB = Layer 2 or 3, > 500KB = Layer 3 fixed.

## Multi-line comments in KDoc / block form for IDE link hints (added 2026-07-10)
strings* — for readability and so the IDE can resolve `[Symbol]` link hints
against declarations.

The rule has two distinct shapes:

1. **Comments attached to a declaration** (function, property, class, data
   class) → use KDoc `/** ... */`. This is the canonical Kotlin doc form and
   is the only form that `Dokka` and IDE quick-doc render as documentation.

2. **Block comments inside a function body or `when` branch** (explanations
   of local logic, multi-paragraph rationale, multi-line `[Foo]` references
   to types outside the surrounding declaration) → use `/* ... */` (with the
   `*`-aligned continuation indent that IDEs recognize). The `[Foo]`
   reference form works inside `/* */` in IntelliJ/Kotlin plugin the same way
   it does inside `/** */` — the difference is that `/** */` is the
   documentation surface and `/* */` is the body-explanation surface.

**Forbidden inside multi-line comments:**

- `// …` continued across more than one line. Two or more consecutive `//`
  lines become an unreadable wall of text the IDE doesn't recognize as a
  single unit. Convert to `/** */` (declaration) or `/* */` (body).
- `//` followed by `//` followed by `//` for paragraph breaks. The same.

**Allowed one-liners (do not convert):**

- `// surface truth` / `// re-emit` / `// F3 fix` style — single-line intent
  comments inside a function body are fine and stay `//`.
- The pre-existing section banners `//=====Group I accessors=====` and similar
  file-structure markers throughout `PumpStation.kt` — those are an
  established grep target in this codebase, not a comment to convert.
- Pre-existing pre-fix code is out of scope. Convert only the comments you
  authored this turn/session; do not rewrite comments on lines you did not
  touch.

**Conversion recipe** when refactoring an existing multi-line `//` block to
`/* */` or `/** */`:

```kotlin
// Surface the original input preview so the trace visualizer can
// show what the harness was tasked with, even after the input has
// been compacted out of turn history. Clipped at CONTENT_PREVIEW_MAX
// with the standard ellipsis suffix.

// ↓ convert to ↓

/*
 * Surface the original input preview so the trace visualizer can
 * show what the harness was tasked with, even after the input has
 * been compacted out of turn history. Clipped at [CONTENT_PREVIEW_MAX]
 * with the standard ellipsis suffix.
 */
```

The `*` continuation indent is the IDE's signal that the block is a
structured comment, not just a free-form block. Without the `*` indent the
block still parses but loses the visual alignment with `/** */`.

**Inside the rewritten block, replace bare identifiers with `[Identifier]`
references** where they point to a symbol in scope. Examples from the
2026-07-10 defect-batch work:

| Bare identifier | KDoc form |
|---|---|
| `CONTENT_PREVIEW_MAX` | `[CONTENT_PREVIEW_MAX]` (private const in same file) |
| `PumpStationLoopGuardSafetyOrderingTest` | `[com.TTT.Pipeline.PumpStationLoopGuardSafetyOrderingTest]` |
| `PumpStationHelpers.parseDispatchOutput` | `[com.TTT.Pipeline.PumpStationHelpers.parseDispatchOutput]` |
| `PathObject.pathSchema` | `[PathObject.pathSchema]` (in-scope import) |
| `Json.parseToJsonElement` | `[kotlinx.serialization.json.Json.parseToJsonElement]` |
| `[Path Safety]` (user-facing marker text) | stays as `[Path Safety]` — KDoc resolves this as a no-op link, but it visually marks the marker |

The fully-qualified form `com.TTT.Pipeline.X` works for IDE link resolution
when the unqualified `X` would be ambiguous. The unqualified form works when
`X` is in scope at the comment site.

**Verification after the conversion** (mandatory): the file must still
compile. Run `./gradlew :compileKotlin` (or the targeted class run via
`./gradlew :test --tests "com.TTT.Pipeline.PumpStation*"`) before considering
the conversion done. A misconverted `[Foo]` reference compiles fine (KDoc
references are unchecked) but fails to link — the IDE shows a red squiggle
that the developer must investigate.

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

## Live + stub test suite architecture (added 2026-07-10)

For any new PumpStation feature that needs integration coverage (new DSL field,
new agent slot, new event type, new exit reason, new trace visualization), the
canonical shape is `PumpStationMiniMaxLiveTest`'s 6 stub + 6 live configuration
matrix. The single-test shape (1 test, no trace capture, no stub-mode, no
multi-config) feels complete in a vacuum but is silently missing 11/12 of the
For any new PumpStation feature that needs integration coverage (new DSL field, new agent slot, new event type, new exit reason, new trace visualization), the canonical shape is `PumpStationMiniMaxLiveTest`'s 6 stub + 6 live configuration matrix. The single-test shape (1 test, no trace capture, no stub-mode, no multi-config) feels complete in a vacuum but is silently missing 11/12 of the matrix. See `references/live-test-suite-architecture.md` for:

Required reading before writing any new `MyFeatureLiveTest` class for the
next PumpStation feature. The pattern is reusable across new event types,
new agent slots, new exit reasons, and new magic-contract flags.

## TraceServer dispatch double-POST when stamping container-kind (added 2026-07-11)

Captured while planning a PumpStation-aware TraceServer integration
(plan `.hermes/plans/pumpstation-traceserver-component-aware/plan.md`,
Tasks 3 + 6). The architectural finding applies to **every container**
(PumpStation, Manifold, Junction, Splitter, DistributionGrid) that
wants to stamp its component-kind on the TraceServer dashboard.

**The wiring today**: `PumpStationLoop.kt:2993` calls
`PipeTracer.exportTrace(taskState.runId, TraceFormat.HTML)` after the
harness completes. Inside `PipeTracer.exportTrace` at
`Debug/PipeTracer.kt:128-138`:

```kotlin
fun exportTrace(pipelineId: String, format: TraceFormat): String {
    val exportedTrace = exportTraceInternal(pipelineId, format)
    if (RemoteTraceConfig.dispatchAutomatically) {
        RemoteTraceDispatcher.dispatchTrace(pipelineId)   // POST #1 (no kind)
    }
    return exportedTrace
}
```

**The trap when adding `kind="pumpstation"`**: the obvious patch is
to add an explicit call after the `exportTrace` line:

```kotlin
// WRONG: double-POST
PipeTracer.exportTrace(taskState.runId, TraceFormat.HTML)
RemoteTraceDispatcher.dispatchTrace(
    pipelineId = taskState.runId, ..., kind = "pumpstation"
)
```

This results in **two POSTs per harness run**. The first POST carries
`kind=null` (because `PipeTracer.exportTrace` calls `dispatchTrace`
without the kind arg). The second carries `kind="pumpstation"`. The
TraceServer's `_upsertSummary` upserts on `pipelineId`, so the second
wins and the dashboard correctly shows the badge.

**Why this is actually fine** (and is the intended path for this work):
the second POST is the desired live-update exercise. The dashboard's
WebSocket handler (`dashboard.js:455-489`) already handles the summary
broadcast and `_upsertSummary` is the existing live-render-update path.
The double-POST is a feature, not a bug — it's the cheapest way to
verify that the live-update path works without writing a separate
WebSocket subscriber test.

**The wrong alternative** (calling `exportTraceWithoutDispatch` to
avoid the first POST) requires exposing the no-dispatch variant to
the container code. `PipeTracer.exportTraceWithoutDispatch` is
`internal` (`Debug/PipeTracer.kt:140-145`) and not importable from
the `Pipeline` package. A `public` promotion is a bigger surface
change than the double-POST.

**The wrong alternative 2** (suppressing the first POST via a
`RemoteTraceConfig.dispatchAutomatically = false` flip before
`exportTrace` and `= true` after) is racy and breaks any other
container that fires through the same `PipeTracer.exportTrace` path
during the gap.

**Generalization for future container-kind work**: any container that
wants a custom `kind` field on its TraceServer dashboard badge should
follow the same double-POST pattern — `exportTrace` for the
v1-compatible payload, explicit `dispatchTrace(..., kind=X)` for the
v2-kind payload. The TraceServer's `_upsertSummary` contract guarantees
the second one wins. Document the pattern in the container's integration
site (e.g. `PumpStationLoop.kt:2986-2994` comment block,
`ManifoldLoop.kt` equivalent if/when Manifold gets the same treatment).

**Verification recipe**: in the live JUnit test, assert that
`GET /api/traces/{id}` returns the trace with `kind="pumpstation"`,
then assert the WebSocket subscriber received ≥2 summary frames (one
for each POST). The two-frame signal proves both the wire shape AND
the live-update path fire correctly. If you see only one summary
frame, the second POST didn't fire — check that the explicit
`dispatchTrace` call is AFTER `exportTrace` in the container's
completion block.

## Pre-seeded DSL is more reliable than background coroutines for live-test injection (added 2026-07-24)

When a live test needs the harness to receive a steering or interrupt payload during the loop, the **DSL pre-seed pattern** (`steeringPolicy { phaseBoundContent(...) }` and `interruptPolicy { initialQueue[...] = listOf(...) }`) is more reliable than a background coroutine that fires `station.steer(...)` or `station.interrupt(...)` while polling `taskState.turnIndex`.

**Why the background-coroutine approach fails**: the harness's judge agent may return `isComplete = true` on turn 0 if the judge LLM is lenient about the "is the task complete?" check. The harness then exits with `PumpStationExitReason.JudgeComplete` and `taskState.turnIndex` stays at 0 forever. The coroutine's `while (station.taskState.turnIndex < 1) { delay(100) }` polls forever and the steer/interrupt is never enqueued. The test fails with "steered text not in turnHistory" — but the root cause is the test design, not the feature.

**The pre-seeded DSL pattern** seeds the steering or interrupt service at construction time. The entry sits in the queue from `executeLocal` start, and the first `BeforeJudge` poll at the top of `runTurn` drains it regardless of how many turns the harness runs (including 1 turn):

```kotlin
val station = pumpStation("pumpstation-steering-live") {
    // ... judge + dispatch + paths ...

    // Steering: pre-seeded one-shot fires at the very first BeforeJudge
    steeringPolicy {
        phaseBoundContent(PumpStationPausePhase.BeforeJudge, steeredText)
    }
}

val result = station.executeLocal(MultimodalContent(text = "Research: ..."))
// turnHistory now contains the steered entry on the first turn's judge call
```

```kotlin
val station = pumpStation("pumpstation-interrupt-live") {
    // ... judge + dispatch + paths ...

    // Interrupt: pre-seeded one-shot fires at the very first BeforeJudge
    // (the interrupt rewinds the harness; on re-entry the judge sees the
    // interrupt message in turnHistory and decides what to do)
    interruptPolicy {
        initialQueue[PumpStationPausePhase.BeforeJudge] = listOf(
            MultimodalContent(text = interruptText)
        )
    }
}

val result = station.executeLocal(MultimodalContent(text = "Research: ..."))
// turnHistory contains the interrupt entry with the canonical envelope
```

**When to use the background-coroutine pattern instead**: when the test needs to fire the steer/interrupt at a SPECIFIC turn number (e.g. "interrupt must fire at turn >= 2, not at turn 0"). The pre-seed pattern always fires at the first poll. The background coroutine can wait for a specific turnIndex. The cost of the coroutine approach is the race condition above; mitigate by polling `taskState.turnIndex` AND `taskState.status` (don't fire if the harness has already exited).

**Acceptance shape for the pre-seed pattern**: assert on the live station's `turnHistory.history` directly (NOT on the rendered HTML — see "Visualizer doesn't surface the metadata map as labeled fields" below). The entry must be present in `turnHistory` with the canonical envelope (`metadata["steering"]` or `metadata["interrupt"]`) at the moment `executeLocal` returns.

## Visualizer doesn't surface the metadata map as labeled fields (added 2026-07-24)

The pump-station HTML visualizer renders a small, fixed set of fields per `ConverseData` event: `contentPreview`, `contentLength`, `pathName` (when set), `inputTokens`, `outputTokens`, `totalTokens`, plus the surrounding `phase` / `turnIndex` / `runId` / `timestamp` / `eventType` / `detailType` / `result` / `content` (the latter as a `<pre class='ps-event-text'>` dump of the JSON). It does **NOT** render arbitrary metadata fields as labeled rows.

**Symptom**: a test asserts `pumpContent.contains("\"phase\"")` looking for the steering envelope's `"phase"` key, but the visualizer doesn't put `"phase"` in the HTML. The test fails. The feature is fine; the assertion is wrong.

**Correct assertion target** is the live in-memory station, not the rendered HTML:

```kotlin
// WRONG: visualizer does not surface metadata as labeled fields
assert(pumpContent.contains("\"phase\""))   // the literal string "phase" with quotes
assert(pumpContent.contains("\"persistent\""))
assert(pumpContent.contains("\"injectionId\""))
assert(pumpContent.contains("\"timestamp\""))

// RIGHT: read the live station's turnHistory directly
val steeredEntry = station.turnHistory.history.firstOrNull {
    it.content.text == steeredText
}
assertNotNull(steeredEntry) {
    "steered text '$steeredText' not in station.turnHistory — turnHistory size: " +
        "${station.turnHistory.history.size}, turnIndex: ${station.taskState.turnIndex}, " +
        "exitReason: ${station.taskState.exitReason}"
}
@Suppress("UNCHECKED_CAST")
val envelope = steeredEntry!!.content.metadata["steering"] as? Map<String, Any>
assertNotNull(envelope)
assertEquals("BeforeJudge", envelope!!["phase"])
assertEquals(false, envelope["persistent"])
assertTrue((envelope["injectionId"] as? String)?.isNotBlank() == true)
assertTrue((envelope["timestamp"] as? Long) ?: 0L > 0L)
```

The same shape applies to `metadata["interrupt"]` envelopes. The visualizer-side `pumpContent.contains(...)` checks are useful only for: (a) `DISPATCH_COMPLETED` / `PATH_COMPLETED` event-name markers, (b) the JSON dump of `ConverseData` content (which contains the text but is HTML-escaped, so `&quot;` substitutes for `"`), and (c) other text the LLM emitted that was rendered in the `Result:` line.

**When the live station object is the right assertion target** vs. the HTML:
- Live station: metadata envelope shape, metadata key presence, turnHistory content, taskState fields, exit reason
- HTML: event-name markers (DISPATCH_COMPLETED, PATH_COMPLETED, etc.), LLM-generated text visible in the `Result:` line, HTML-escaped JSON dumps in the `<pre>` content blocks

**Diagnostic flow** when a live-test assertion fails:
1. Read the failure message. If the message says "X not in pumpContent", the assertion target is wrong — switch to the live station.
2. If the message says "X not in station.turnHistory", the production feature didn't fire. Check the production code: did the poll call site actually fire? Did the entry get added to `turnHistory`? Print `station.turnHistory.history.size` and `station.taskState.turnIndex` and `station.taskState.exitReason` to disambiguate "never fired" from "fired and got rewound out."

## Adding a new DSL block to `PumpStationBuilder` (recipe, added 2026-07-23)

Whenever the task is "expose an `xxx { }` block on `pumpStation { }` that threads a typed configuration object into the built station," the change spans exactly the same five anchors every time. The shape was first walked end-to-end for `steeringPolicy { }` and `PumpStationSteeringService` on 2026-07-23 (Tasks 3+4 of a steering-service plan) and will recur for every future DSL feature (a future `retryPolicy { }`, `personalityOverride { }`, or `phaseOverlay { }` block will follow the same recipe verbatim).

### The five anchors

```text
1. Field on PumpStationBuilder                  → PumpStationDsl.kt (≈line 80)
2. DSL entry-point function                    → PumpStationDsl.kt (≈line 851)
3. copyFrom preservation (Pitfall 8 again)     → PumpStationDsl.kt (≈line 982)
4. build() integration                        → PumpStationDsl.kt (≈line 1105)
5. Top-level <Policy>Builder class             → PumpStationDsl.kt (≈line 2127)

Plus the constructor injection:
   PumpStation(...) signature + backing field + public accessor
   → PumpStation.kt (≈line 761, 776, 804)
```

The existing `tracing { }`, `killSwitch { }`, and `compaction { }` blocks are the reference shapes — copy their structure exactly. The `SteeringPolicyBuilder` reference implementation is at `src/main/kotlin/Pipeline/PumpStationDsl.kt:2104-2179` and the `PumpStation`-side wiring is at `src/main/kotlin/Pipeline/PumpStation.kt:761-804`.

### Field declaration (anchor 1)

```kotlin
/** Optional xxx configuration ... */
var xxxConfiguration: XxxConfiguration? = null
```

Place it adjacent to the existing configuration fields (`tracingConfiguration`, `killSwitchConfiguration`, `compactionConfiguration`).

### Entry-point function (anchor 2)

```kotlin
fun xxx(block: XxxBuilder.() -> Unit): PumpStationBuilder<S> {
    val targetBuilder = resolveActiveBuilder()
    val builder = XxxBuilder()
    builder.block()
    targetBuilder.xxxConfiguration = builder.build()
    return this
}
```

`resolveActiveBuilder()` is load-bearing: without it, post-`path()` DSL calls silently land on the discarded initial builder (Pitfall 8).

### `copyFrom` preservation (anchor 3 — Pitfall 8)

```kotlin
internal fun copyFrom(source: PumpStationBuilder<*>): PumpStationBuilder<*> {
    tracingConfiguration = source.tracingConfiguration
    killSwitchConfiguration = source.killSwitchConfiguration
    compactionConfiguration = source.compactionConfiguration
    +xxxConfiguration = source.xxxConfiguration    // <-- ADD THIS LINE
    ...
}
```

Without this line, `pumpStation { xxx { ... }; path("name") { } }` silently drops `xxx` because `path()` promotes the initial builder and `copyFrom(this)` snapshots initial-stage state into the promoted Ready-stage builder. The harness's `build()` reads from the promoted builder, so the configuration is silently lost.

### `build()` integration (anchor 4)

```kotlin
val xxxService = xxxConfiguration?.let { XxxService(it) } ?: XxxService()
val station = PumpStation(xxxService = xxxService)
```

The `?: XxxService()` empty-default keeps behavior identical for PumpStations built without a `xxx { }` block.

### Top-level `<Policy>Builder` class (anchor 5)

- **Top-level, not nested.** `@DslMarker` allows nesting; convention is top-level. `SteeringPolicyBuilder`, `KillSwitchBlock`, `CompactionBlock`, `PumpStationTracingDsl` all follow this rule.
- **Two overloads per DSL method.** One for `MultimodalContent`, one for `String` (auto-constructs the content).
- **`build()` is `internal`.** Only `PumpStationBuilder.build()` consumes it.

### `PumpStation` constructor injection (the sixth anchor)

```kotlin
class PumpStation(
    killSwitch: KillSwitch? = null,
    xxxService: XxxService = XxxService()   // <-- ADD with DEFAULT
) : P2PInterface {
    private var _killSwitch: KillSwitch? = killSwitch
    private val _xxxService: XxxService = xxxService
    val xxxService: XxxService get() = _xxxService
    ...
}
```

**Three load-bearing rules:**

- **The new parameter MUST have a default value.** The TPipe test suite has ~80+ `PumpStation()` call sites across `src/test/kotlin/Pipeline/*.kt`. A required parameter silently breaks the entire test surface. The `= XxxService()` default preserves every pre-existing call site.
- **Backing field uses `val`, accessor exposes `val` getter.** No custom setter required.
- **The KDoc must describe the runtime guarantee**, not the history. Pattern: `"Always non-null — defaults to an empty [XxxService] when no xxx { } is configured."`

### Verification recipe (no canonical test exists yet)

`./gradlew compileKotlin -x test` confirms the entire test compilation graph (including the ~80 `PumpStation()` call sites) still compiles with the new default-valued constructor parameter — proof that the constructor-default rule is satisfied for the entire test surface in one shot. Until a `PumpStationXxxTest` lands, run an ad-hoc declaration-grep via a `hermes-verify-*.sh` script (see the `verifying-code-changes` skill) that asserts every anchor landed in the diff:

```bash
require_pattern() {
    local pattern=$1; local file=$2
    grep -Eq "$pattern" "$file" || { printf 'FAIL: %s in %s\n' "$pattern" "$file" >&2; exit 1; }
}
require_pattern 'var xxxConfiguration: XxxConfiguration\? = null' "$DSL"
require_pattern 'fun xxx\(block: XxxBuilder\.\(\) -> Unit\)' "$DSL"
require_pattern 'xxxConfiguration = source\.xxxConfiguration' "$DSL"
require_pattern 'class XxxBuilder' "$DSL"
require_pattern 'val xxxService = xxxConfiguration\?\.let \{ XxxService\(it\) \}' "$DSL"
require_pattern 'val station = PumpStation\(xxxService = xxxService\)' "$DSL"
require_pattern 'xxxService: XxxService = XxxService\(\)' "$STATION"
require_pattern 'private val _xxxService: XxxService = xxxService' "$STATION"
require_pattern 'val xxxService: XxxService get\(\) = _xxxService' "$STATION"
./gradlew compileKotlin -x test
git diff --check -- "$DSL" "$STATION"
```

This is **ad-hoc** verification, not "test suite green" — a real test for runtime behavior lands in a later task.

### The `MultimodalContent` constructor signature trap

A plan-supplied text-overload example may use `MultimodalContent().text(text)`. That fails to compile: `MultimodalContent` is a `data class` (`src/main/kotlin/Pipe/BinaryContent.kt:118`) whose primary constructor takes `text = ""` as a named, default-valued parameter — *not* a settable property. The right shape is the named-argument form:

```kotlin
MultimodalContent(text = text)
```

**Always re-read the actual constructor signature before patching from a plan's literal code snippet.** Same trap applies to every other `data class` in the codebase where parameter names in a plan snippet were approximations.

### The `MultimodalContent.metadata` body-level-var trap (added 2026-07-23; revised 2026-07-24)

`MultimodalContent.metadata` is **NOT a primary-constructor property** — it is declared as a body-level `var metadata = mutableMapOf<Any, Any>()` inside the class body (`src/main/kotlin/Pipe/BinaryContent.kt:180-181`). The data-class auto-generated `copy()` method has **no `metadata` parameter** and CANNOT be used to produce a clone with merged metadata. Two specific compile errors fire when you try:

1. `content.copy(metadata = mergedMap)` → `No parameter with name 'metadata' found.`
2. A naïve `mergedMap + ("steering" to env)` fails variance because `content.metadata: MutableMap<Any, Any>` is invariant on its value type — `Map<String, Any>` is NOT a subtype of `MutableMap<Any, Any>`.

**The deeper hazard — `copy()` also silently drops body-level `var` CURRENT values, not just metadata.** This was the lesson the 2026-07-24 deep-copy audit learned the hard way (operator verbatim: "deep copy is used because .copy is so shallow it's basically genuinely useless"). When you call `data class Foo(var x: Int = 0) { var body: MutableMap<Any, Any> = mutableMapOf("a" to 1, "b" to 2) }.copy()`, Kotlin's compiler-generated `copy()` invokes the primary constructor with the primary-ctor field values, then the class body re-runs — and body-level `var` initializers execute, producing a **fresh initializer-default value**, NOT the source's current value. Verified at runtime 2026-07-24:

```kotlin
val src = Test(1).also { it.body["c"] = 3 }      // body={a=1, b=2, c=3}
val cpy = src.copy()                            // body={a=1, b=2}   ← initializer defaults, not src.current
cpy.body.clear(); cpy.body["x"] = 99
// src.body unchanged (different identity), cpy.body={x=99}
```

**Concrete user-visible impact on `MultimodalContent`** (the same shape, six call sites in the TPipe codebase needed the fix): `.copy()` drops `passPipeline`, `currentPipe`, `modelReasoning`, `pipeError`, `repeatPipe`, `interuptPipeline`, `skipReasoningPipe`, `jumpToPipe`, and the current contents of `metadata`. A path that returned `passPipeline = true` and got rewritten by the pre-prune Rule 7 (whitespace normalization) lost its `passPipeline` on the rewritten turn — the harness's exit-via-passPipeline signal silently disappeared.

**Required pattern** when producing a clone with full state preservation:

```kotlin
// Use Util.deepCopy() (com.TTT.Util.deepCopy, inline reified extension at
// Util/Util.kt:528). It walks the primary-ctor fields AND the body-level
// KMutableProperty1 members via reflection, so body-level current values
// (metadata, passPipeline, currentPipe, etc.) are preserved.
val updated = content.deepCopy()
updated.metadata = merged   // mutate the body-level var in place after copy
```

**Why `data class.copy()` is broken for any class with body-level `var`s**: the contract users assume (`copy()` produces a clone with current values) is not what Kotlin delivers. The compiler-generated `copy()` is a primary-ctor convenience, not a semantic clone. For pure data classes with no body-level state, `.copy()` is fine. For `MultimodalContent` (and any `data class` with body-level `var`s), `.copy()` is a footgun — every field the user assumes is "current" is actually "default."

**Trap-recognition checklist** when reviewing existing code or planning new code:

- `data class Foo(var x: Int = 0)` body-level `var body: ... = default` → `.copy()` drops body's CURRENT value, returns initializer default. Use `Util.deepCopy()` instead.
- A code path does `c = something.copy(); c.field = newValue` where `field` is a body-level `var` → the source's `field` is NOT in `c.field`'s starting state. Look for this when auditing call sites.
- `content.copy(metadata = map)` compile error → metadata is body-level; use `content.deepCopy()` then mutate, or build a fresh `MutableMap<Any, Any>` and assign.

**Verification at audit time** (the repro that catches shallow-copy hazards):

```kotlin
val src = Test(/* populate EVERY field with non-default value */)
val cpy = src.copy()  // or src.deepCopy()
fields.forEach { field ->
    println("${field.name}: src=${field.get(src)} cpy=${field.get(cpy)} same=${field.get(src) == field.get(cpy)}")
}
```

Every field on adjacent lines. If a `cpy` value equals the field's initializer default, the source's value was dropped. The repro at `notes/repro.txt` from the 2026-07-24 audit (`src body={a,b,c}`, `cpy body={a,b}`, identity-hash-different, source-untouched) is the canonical example.

**Fix sites in the TPipe codebase** (all six `MultimodalContent.copy()` call sites swapped to `Util.deepCopy()` after the 2026-07-24 audit):

| File:line | Pre-fix code | Post-fix code |
|---|---|---|
| `Pipeline/PumpStation.kt:927` (steering envelope) | `val updated = content.copy(); updated.metadata = mergedMetadata` | `val updated = content.deepCopy(); updated.metadata = mergedMetadata` |
| `Pipeline/PumpStationLoop.kt:231` (interrupt envelope) | `val stamped = first.copy(); stamped.metadata = mergedMetadata` | `val stamped = first.deepCopy(); stamped.metadata = mergedMetadata` |
| `Pipeline/PumpStationLoop.kt:1144` (Rule 6 metadata filter) | `val c = turn.content.copy(); c.metadata.clear(); c.metadata.putAll(kept)` | `val c = turn.content.deepCopy(); c.metadata.clear(); c.metadata.putAll(kept)` |
| `Pipeline/PumpStationLoop.kt:1158` (Rule 7 whitespace) | `val c = turn.content.copy(); c.text = normalized` | `val c = turn.content.deepCopy(); c.text = normalized` |
| `Pipeline/PumpStationLoop.kt:1339` (Rule 8 summary dedup) | `val rewritten = turn.content.copy(); rewritten.text = "[See turnSummary]"` | `val rewritten = turn.content.deepCopy(); rewritten.text = "[See turnSummary]"` |
| `Pipeline/PumpStationLoop.kt:1490` (tool-call truncation) | `val rewritten = turn.content.copy(); rewritten.text = stub` | `val rewritten = turn.content.deepCopy(); rewritten.text = stub` |

**TDD pins** for the regression (in `src/test/kotlin/Pipeline/CompactionPruneTest.kt`):

- `testRule6DoesNotMutateSourceTurnMetadata` — pins that the source turn's metadata is unchanged after Rule 6's rewrite. (Passes under both `.copy()` and `.deepCopy()` because body-level `var` initializers re-run.)
- `testRule7PreservesPassPipelineAcrossRewrite` — pins that the REWRITTEN turn carries the source's `passPipeline = true`. **This is the actual bug pin** — under `.copy()` the source's `passPipeline` is dropped on the rewrite (body initializer re-runs with default `false`); under `.deepCopy()` it survives.

The Rule-7 pin is RED under `.copy()` and GREEN under `.deepCopy()`. The Rule-6 pin alone would have passed on buggy code — which is exactly the failure mode that taught us "tests that pass on the bug aren't pins."

**Runtime-repro misread pattern from this audit** — the audit's first repro showed `src body={a,b,c}` and `cpy body={a,b}` and the agent read "no aliasing — source untouched" but missed that the copy's body equals the initializer defaults (silent data drop). The user pushed back. **Three checks that catch this class of misread:**

1. **Diff every field, not just the one under investigation.** Compare identity hashes AND contents AND initializer-defaults for every field.
2. **Treat "copy value matches initializer default" as a finding, not a coincidence.** When a freshly-copied object's field equals the field's initializer default, the source's current value was dropped.
3. **When user pushes back with "you missed something," re-read the existing repro output with the new frame rather than generating a fresh hypothesis.** The repro output doesn't change when the user disagrees with you; only your interpretation of it does.

**Lesson also captured** in the user's working memory and in the systematic-debugging skill (proposed: "Don't dress up inferences as findings from your own repro output — read the actual values, not the shape").

### Interrupt runtime-API surface on PumpStation (added 2026-07-24)

The interrupt feature landed as the sibling of steering — opposite semantics. Where steering ADDS content to the running turn, an interrupt STOPS the active turn, rewinds the harness state to the BeforeJudge of the current turn, and re-enters `runTurn` from the top with the interrupt message injected into `turnHistory`. Equivalent of a hard interrupt in other LLM harnesses (OpenAI Agents SDK, Claude Code). The full user-facing surface lives at `Pipeline/PumpStation.kt:807-967` (suspend extensions + property); the harness-loop wiring lives at `PumpStationLoop.kt` (11 chokepoint poll calls + outer-snapshot catch in `runHarnessLoop` + inner-snapshot threading through `runTurn`). The full design (combination semantics, envelope shape, overflow forwarding, BeforeExit special case) is documented at `docs/containers/pumpstation.md` "Interrupt: Hard Rewind-and-Restart".

**Three load-bearing invariants** future tasks must NOT break:

1. **`taskState.turnIndex` is NOT advanced on rewind.** The catch handler in `runHarnessLoop` `continue`s the `while` loop with the same `turnIndex`. The interrupted turn slot is re-attempted. Advancing the index on rewind would silently consume max-turns budget per interrupt, defeating the watchdog use case.
2. **The exception carries a rewind snapshot, not the current state.** `PumpStationInterruptException(content, snapshot)` — `snapshot` is captured at the top of `runTurn` (BeforeJudge) and is the rewind target. Reading `taskState.latestContent` inside `injectInterruptForPhase` would NOT work — that field already reflects the in-flight turn's mutations. Always read from the captured `snapshot`, never the live state.
3. **First-only drain with steering overflow.** The first entry in `PumpStationInterruptService`'s per-phase queue becomes the active interrupt; the rest are forwarded to the steering service as one-shot instructions. If the steering service is not configured for the phase, the overflow is silently dropped AND a `InterruptOverflowDropped` event is emitted (operator-confirmed requirement 2026-07-24, see "InterruptOverflowDropped event" entry below). Do NOT change the drain to "drain all and pick the first one" — that breaks the overflow-forwarding semantics.

**Five load-bearing runtime invariants** future tasks must NOT break:

1. **Top-level suspend extensions are MEMBER functions of `PumpStation`, not extensions declared as `suspend fun PumpStation.interrupt(...)`.** Kotlin treats `suspend fun PumpStation.interrupt(...)` declared INSIDE the `PumpStation` class body as invalid syntax (extension-of-self inside a class); the parser accepts it as a member with the `PumpStation.` label, which doesn't resolve from outside the class. The declaration must be plain `suspend fun interrupt(...)` inside the class body — the receiver is implicit. Verified the hard way at `PumpStation.kt:955-967` on 2026-07-24: `station.interrupt(...)` from outside the class failed to resolve until the `PumpStation.` prefix was dropped. Same applies to `steer` / `steerPersistent` / `clearSteering` / `drainSteeringForPhase`.

2. **`injectInterruptForPhase` polls BEFORE `injectSteeringForPhase` at every chokepoint.** Interrupt is higher priority than steering because interrupt rewinds the turn (steering does not). Order matters: `injectInterruptForPhase(phase, turnSnapshot); injectSteeringForPhase(phase)`. Reordering changes behavior — if steering runs first and injects content into `turnHistory`, the interrupt's snapshot still points to the pre-rewind state, but the `turnHistory` rewind would clear the steering injection along with the in-flight work.

3. **Outer-snapshot in `runHarnessLoop` catches interrupts that arrive between turns.** The harness loop has a double-snapshot pattern: `turnSnapshot` is taken at the top of `runTurn` (inner, used by the in-flight catch) AND at the top of the `while` loop body in `runHarnessLoop` (outer, used for interrupts arriving during finalization or between turns). Do NOT remove the outer snapshot — late-arriving interrupts need a rewind target even if `runTurn` never entered. Verified at `PumpStationLoop.kt:2904-2920` (outer snapshot + catch) and `PumpStationLoop.kt:2967-2971` (inner snapshot).

4. **`runExitFlow` takes `turnSnapshot: PumpStationInterruptSnapshot` as a parameter.** Before the interrupt feature, `runExitFlow()` had no parameters. The signature change is required because the interrupt poll at `BeforeGoalValidation` needs the same `turnSnapshot` that `runTurn` captured. The two call sites in `runTurn` (lines 2998 and 3040) pass `turnSnapshot` through; the three test sites in `RunExitFlowTest.kt` pass `station.takeInterruptSnapshot()` directly. Do NOT add a member field to `PumpStation` to hold the snapshot — that creates a re-entrancy hazard if `runTurn` is called twice without going through `runHarnessLoop`.

5. **`runFinalizationPhase` has a special-case for `BeforeExit` interrupt poll.** Finalization runs AFTER `runHarnessLoop` returns. There is no `while` loop to `continue` into. The interrupt poll at `BeforeExit` rewinds the snapshot AND appends the message to `turnHistory`, then finalization proceeds. Do NOT throw an exception in finalization — there's no catch handler above it. The user-visible behavior is: an interrupt arriving during finalization shows up in `turnHistory` but does NOT trigger a re-entry into the harness loop (the harness has already exited). Document this clearly in the API surface.

**InterruptOverflowDropped event** (operator-confirmed requirement, 2026-07-24): when the interrupt service's first-only drain finds overflow entries that cannot be forwarded to the steering service (steering not configured for that phase), the harness must NOT silently drop them. Emit an `InterruptOverflowDropped` event with `boundaryPhase`, `droppedCount`, and `firstDroppedText` (truncated to 200 chars). Mirrors to `TraceEventType.PUMP_STATION_INTERRUPT_OVERFLOW_DROPPED` in `Debug/TraceEventType.kt`. Three load-bearing rules:

- The event is emitted from `injectInterruptForPhase` only when `droppedCount > 0`. No event when all overflow was successfully forwarded to steering.
- `firstDroppedText` is truncated to 200 chars (`extra.text.take(200)`) to keep the event payload bounded. Long-form text in the dropped payload stays in the dropped queue's debug surface, not in the trace stream.
- The event's `phase` field (the harness-phase slot on `PumpStationEvent`) defaults to `PumpStationPhase.Judge` because the overflow is most commonly observed at the BeforeJudge poll (interrupts queued between turns fire there). The boundary phase is in the `boundaryPhase` field. Do NOT conflate the two — they're orthogonal.

**The "wait, that flag is wrong" historical-note smell in `MultimodalContent.interuptPipeline`**: the magic-contracts doc at `docs/core-concepts/pumpstation-magic-contracts.md` line 10 references a `MultimodalContent.interuptPipeline` flag that triggers a path-intervention hook. This is a DIFFERENT surface from the new Interrupt feature — the flag is per-content and triggers a path hook, the harness Interrupt feature stops the in-flight turn and rewinds. When documenting or referencing "the interrupt feature," disambiguate. Captured 2026-07-24 after a session confusing the two surfaces.

## Feature delivery ends at docs, not delivery summary (added 2026-07-24)

Feature work on this umbrella conventionally ended at "delivery summary" — the operator reviews the diff and the working tree is the deliverable. The 2026-07-24 interrupt-feature session established a stricter pattern: code + tests + verification + docs is the full loop. The operator asked for doc updates AFTER the feature was fully verified, and the work split across three doc files (`docs/containers/pumpstation.md`, `docs/api/pumpstation.md`, `docs/api/pumpstation-models.md`).

**The doc-update recipe for any new PumpStation feature with user-visible surface:**

1. **Container doc (`docs/containers/pumpstation.md`)** gets a new top-level section sibling to the existing sibling-feature sections (Steering, Interrupt, Tracing, etc.). Use the same section structure as the existing sibling: `When to use <feature>` table, `Configuration Surface (DSL)` block, `Runtime API`, `<Behavior>` mechanics, `Phase Boundaries (N chokepoints)` table, `Combination Semantics` table, `Metadata Provenance` table, `How It Works` numbered list, `Reference Locations` table, two usage `Example` blocks. Match the section headers exactly — the operator greps for them.
2. **API doc (`docs/api/pumpstation.md`)** gets a new top-level `## <feature> Runtime API` section placed AFTER the Enums section and BEFORE the Cross-References section. The API doc does NOT have a Steering section; pair new features with steering-related siblings in a single combined `## Steering and <feature> Runtime API` section. Multi-feature pairing keeps the API doc's section count bounded as features accumulate.
3. **Models doc (`docs/api/pumpstation-models.md`)** gets a new `## <feature> Models` section placed AFTER the Failure Policy and Snapshot Models section and BEFORE the Task State and Sealed Events section. Each new data class gets a `### ClassName` subsection with file path, signature (the data-class declaration, not a paraphrase), and a brief description. Each new event type gets a row in the appropriate events table (e.g. `InterruptOverflowDropped` goes in the Harness Lifecycle Events table alongside `HarnessSuspended`, `HarnessResumed`, `HarnessWarning`).

**Three rules that recur every doc-update task:**

1. **Reproduce the source-file declarations verbatim in the doc.** Don't paraphrase class signatures; copy the actual `data class Foo(...)` block from the source. Doc-signature drift from source-signature is the #1 source of operator pushback on doc accuracy.
2. **Match the operator's table-density expectation.** The container doc's `Phase Boundaries (N chokepoints)` table has 11 rows for PumpStation. The API doc's `When to use which` table has 5 rows. The models doc's events tables have ~30 rows total. Adding a feature without filling these tables in the same density is "thin documentation" and gets pushback.
3. **Cross-link between the three docs.** Container doc has full design prose; API doc has runtime surface + cross-link to container; models doc has signatures + cross-link to API. The operator uses the container doc as the entry point and follows links to the other two. Adding a feature to one doc without linking from the others produces dead links and "where do I find X" questions.

## Steering runtime-API surface on PumpStation (added 2026-07-23, Tasks 5+6)

The runtime surface for external callers pushing instructions into the harness loop landed at `Pipeline/PumpStation.kt:807-920`. Every future steering-feature task must respect this contract verbatim:

| Member | Signature | Purpose |
|---|---|---|
| Producer — one-shot | `suspend fun steer(phase: PumpStationPausePhase, content: MultimodalContent)` | Fire at next phase, then auto-consumed |
| Producer — one-shot | `suspend fun steer(phase: PumpStationPausePhase, text: String)` | Convenience String overload (delegates to `MultimodalContent(text = text)`) |
| Producer — persistent | `suspend fun steerPersistent(phase, content: MultimodalContent)` | Fires on every phase match until replaced/cleared |
| Producer — persistent | `suspend fun steerPersistent(phase, text: String)` | String overload |
| Producer — clear | `suspend fun clearSteering(phase: PumpStationPausePhase)` | Removes the persistent overlay for `phase` |
| Consumer | `suspend fun drainSteeringForPhase(phase): List<MultimodalContent>` | Returns persistent overlay (index 0) then FIFO one-shots; each entry stamped with `metadata["steering"] = { phase, persistent, injectionId: UUID, timestamp }` |

**Three load-bearing invariants** future tasks must NOT break:

1. **Order at drain time is fixed**: persistent overlay first (index 0), one-shots in FIFO order. The combination/reordering logic lives in `drainSteeringForPhase`, NOT in the producer methods. Do NOT change the producer methods to consume their own entries on enqueue — that would break cross-call accumulation semantics.
2. **`persistent` flag per drained entry**: index 0 reports `persistent=true` ONLY IF `steeringService.hasPersistentOverlay(phase)` was true at drain time. All subsequent indexes report `false`. The check happens via the non-suspending `hasPersistentOverlay(phase)` (it's a `fun`, not `suspend`), so it can run inside the drain's mapIndexed without `await`.
3. **`injectionId` is a fresh UUID per drained entry.** Never persist a single ID across an overlay + one-shot pair. Each entry's `injectionId` is independently generated so trace log filtering can show a single injected entry end-to-end.

**The harness loop is the sole caller of `drainSteeringForPhase`.** Producers are `public suspend` so any external coroutine (governance agent, monitor, DITL hook, test) can call them concurrently with the running loop. `steeringService` itself uses `Mutex` + `Channel(UNLIMITED)` for thread safety; do NOT add a separate lock around the public surface — producers are already concurrent-safe at the service layer.

**Body-level metadata stamping pattern** (see "The `MultimodalContent.metadata` body-level-var trap" above) is the only way to stamp the envelope without breaking `copy()`. Do not refactor `drainSteeringForPhase` to use `content.copy(metadata = ...)` — that will fail to compile.

## Container-kind dispatcher-stamp call-site: senary TDD sibling case (added 2026-07-11)

When the current task is to make a SPECIFIC container call site
(`PumpStation.runFinalizationPhase` for PumpStation, `Manifold.runFinalizationPhase`
for Manifold, etc.) stamp the existing `kind` field on `TracePayload` —
and the `kind` field has ALREADY landed on the wire in a prior task —
the TDD recipe is **1 test, not the 3-test back-compat matrix**. The
back-compat matrix is already covered by the prior task's
`RemoteTraceDispatcherWireTest`. The current task's smoke test
(`PumpStationDispatchKindTest`) only verifies the call signature
compiles and doesn't throw a "no such parameter" error.

The shape:

- Production patch is the call site ONLY — no new wire field, no
  serializer change. See
  `references/wire-contract-field-backcompat-tdd.md` "Senary Sibling
  Case: Container-Kind Dispatcher-Stamp (TraceServer Task 3)" for the
  full call-site recipe, status-mapping invariant, and cross-class
  verification discipline (run the new smoke test + the prior
  back-compat test together with `--no-daemon`).

- Use fully-qualified names (`com.TTT.Debug.RemoteTraceDispatcher`,
  `com.TTT.Pipeline.PumpStationStatus`) to match the surrounding file
  style. Do NOT add imports.

- Status mapping invariant: `PumpStationStatus.Completed` → `"SUCCESS"`,
  else → `"FAILURE"`. The block runs AFTER the harness exits, so the
  `else` branch is reachable for `Failed` / `Terminated` / `Suspended`
  / `WaitingOnBackground` / `NotStarted` / `Running`.

Reference case: TraceServer Task 3 commit `39315bce` (2026-07-11),
test `src/test/kotlin/Debug/PumpStationDispatchKindTest.kt`, production
patch at `Pipeline/PumpStationLoop.kt:2986-2994`.