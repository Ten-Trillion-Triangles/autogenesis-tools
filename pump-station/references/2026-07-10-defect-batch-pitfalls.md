# PumpStation Defect Batch 2026-07-10 — captured pitfalls

Authoritative re-entry for the 2026-07-10 defect batch. Each entry is one pitfall the
audit surfaced, with the canonical file:line, the fix shape, and the regression test that
pins the contract. Sessions working on PumpStation.kt in this region should grep these
symbols before patching so they don't re-fix or re-break any of them.

## Defect 8 — dispatch-pipe parent wiring (HIGH)

- File: `Pipeline/PumpStationLoop.kt` (`runAgent` body)
- Symptom: dispatch LLM system prompt never carries the `PathDescriptionList` /
  `Available paths` block from `Pipe.kt:2319-2341` because `getNearestPumpStationParent()`
  walks up a null parent chain and `autoInjectPathDataFromPumpStation` silently no-ops.
- Fix shape: when the agent pipeline has no existing parent, `agent.setParentInterface(this)`
  on the harness before invoking. Conditional — does NOT stomp a developer-supplied parent.
- Regression test: `src/test/kotlin/Pipeline/PumpStationDispatchPathInjectionTest.kt`
  (helper pipe `com.TTT.testing.TestCapturingPipe.kt` captures the composed prompt).

## Defect 10 — non-JSON pathSchema fallback (HIGH)

- File: `Pipeline/PumpStationLoop.kt::buildPathInput` + `Pipeline/PumpStationHelpers.kt::buildPathSchemaFallbackMessage`
- Symptom: when the dispatch LLM returns a non-JSON string for `pathSchema`, the harness
  concatenates the literal text into the path LLM's user prompt. The path LLM then
  obediently researches the schema text instead of the user's topic.
- Fix shape: parse the dispatch-emitted schema via `kotlinx.serialization.json.Json.parseToJsonElement`
  and require a `JsonObject`. On failure, append a `[Harness Notice]` hint to `turnHistory`
  AND fall back to the path's canonical `path.pathSchema`. Warn-and-continue, not halt.
- Regression test: `src/test/kotlin/Pipeline/PumpStationPathSchemaValidationTest.kt`
  (3 cases: malformed JSON fallback, valid JSON pass-through, blank dispatch schema).

## Defect 11 — path-safety must run before loop-guard (HIGH)

- File: `Pipeline/PumpStation.kt::invokePath` (high in the function)
- Symptom: loop-guard counters incremented for paths that path-safety gate would have
  rejected and returned early on. With `maxConsecutiveSamePath=2`, dispatching the same
  safety-rejected path three times trips the guard.
- Fix shape: risk check + path-safety gate must run BEFORE the consecutive-counter and
  per-path call counter updates. Confirmed live in current code: risk → safety → only
  on approval → loop guard counters → path execution.
- Regression test: `src/test/kotlin/Pipeline/PumpStationLoopGuardSafetyOrderingTest.kt`
  — three tests pinned:
  - safety rejection never trips loop guard
  - loop guard still fires when safety approves
  - `[Path Safety]` hint still appended on rejection after the reorder

## Defect 16 — risk-aware path-safety fallback (MEDIUM)

- File: `Pipeline/PumpStation.kt::checkPathSafety`
- Symptom: parsed verdict was the only condition for Medium/High risk; an unparseable
  path-safety agent output silently approved any path including High risk.
- Fix shape: re-order the fallback. `parsed?.approved ?: (pathSafetyExpectsJsonContract ->
  path.riskLevel == PathRiskLevel.Low) : !(result.terminatePipeline || result.passPipeline)`.
  Low still approves on parse failure (it's the no-op gate). Medium and High deny.
- Regression test: `src/test/kotlin/Pipeline/PumpStationPathSafetyFallbackTest.kt`

## Defect 12 — DSL default `maxConsecutiveSamePath=null` (LOW)

- File: `Pipeline/PumpStationDsl.kt` var declaration
- Symptom: DSL silently defaulted to `Int = 3`, surfacing a hidden loop-guard inside
  every DSL-built station.
- Fix shape: `var maxConsecutiveSamePath: Int? = null`. Pure opt-in.
- Regression test: `src/test/kotlin/Pipeline/PumpStationDslDefaultTest.kt`

## Defect 15 — `[TURN SUMMARY]` demarcation (MEDIUM)

- File: `Pipeline/PumpStationHelpers.kt::buildUserMessageForTurn`
- Symptom: `turnSummary` text concatenated raw, judge LLM could mistake it for the
  question.
- Fix shape: wrap summary in `[TURN SUMMARY] ... [/TURN SUMMARY]` markers, mirroring the
  existing `[CONVERSATION HISTORY]` block style. Skip block entirely when summary is blank.
- Regression test: `src/test/kotlin/Pipeline/PumpStationTurnSummaryDemarcationTest.kt`

## Defect 19 — loop guard HALTS (was: invoke + continue)

- File: `Pipeline/PumpStation.kt` (loop-guard block) + `PumpStationModels.kt::PumpStationExitReason`
  (new enum value `LoopGuardTripped`).
- Policy change: loop-guard trips now HALT with `PumpStationExitReason.LoopGuardTripped`,
  `lastError = PumpStationError.LoopGuardTriggered`, `latestContent.terminatePipeline = true`.
  The intervention agent is no longer invoked — prior policy was theater.
- Regression test: `src/test/kotlin/Pipeline/PumpStationLoopGuardHaltTest.kt`
- Side effect: `PumpStationInterventionAgentTest` was rewritten to assert the new halt
  contract. Three test methods: `loopGuardHalt_skipsInterventionAgentWhenBuilderSet`,
  `loopGuardHalt_skipsInterventionAgentWhenBothSet`, `loopGuardHalt_emitsLoopGuardTrippedWhenNoAgentConfigured`.

## Defects 20/22/24/25 — trace-event funnel metadata completeness

- File: `Pipeline/PumpStationHelpers.kt::convertPumpStationEvent`
- Defect 20: HarnessStarted now emits `originalInputPreview` (clipped to
  `CONTENT_PREVIEW_MAX`, ellipsis suffix).
- Defect 22: JudgeStarted now emits `judgeRunMode` (from `judgeRunModeInternal`).
- Defect 24: DispatchCompleted now emits `pathRequest` as JSON via
  `com.TTT.Util.serialize(it)` instead of `pathRequest.toString()` Kotlin dump.
- Defect 25: PathSafetyCompleted now emits `approvedAsInt` (Int 1/0) alongside the
  Boolean `approved`. Stable JSON representation for downstream consumers.
- Regression test: `src/test/kotlin/Pipeline/PumpStationEventMetadataTest.kt` (5 cases).
- Read trace funnel via `tracePumpStationEvent` extension + `PipeTracer.getAllTraces()` —
  enable tracing with `station.enableTracing()` first.

## F3-clone — path-safety hint dedup

- File: `Pipeline/PumpStation.kt::invokePath` (the `[Path Safety] Path '$pathName'`
  append site).
- Symptom: every safety rejection for a path appended a fresh hint, ballooning
  `turnHistory` over many turns of repeated rejections.
- Fix shape: dedup by pathName via `turnHistory.history.any { it.content.text?.contains("[Path Safety] Path '$pathName'") == true }`.
- Regression test: `src/test/kotlin/Pipeline/PumpStationPathSafetyHintDedupTest.kt`

## Defect 14 — test-redesign (no production patch)

- Three-layer "path admits failure" pattern documented in
  `src/test/kotlin/Pipeline/PumpStationPathFailureExitsProperlyTest.kt`. Layers:
  - Layer 1: `pathValidationFunction` DITL hook rejects path outputs that contain
    failure phrases before the judge votes.
  - Layer 2: path returning `terminatePipeline=true` exits via `PumpStationExitReason.TerminateSignal`.
  - Layer 3: path returning `passPipeline=false` continues the harness loop (does NOT exit).
- No production patch needed — the audit's proposed "defensive verification layer" was
  the wrong default. The right answer is using PumpStation's existing features correctly.

## Conventions captured for future work

- TDD-first: failing test first (RED), patch (GREEN), rerun (BREATHING). The seven
  production-patch tasks above each have a pinned regression test file at
  `src/test/kotlin/Pipeline/Pump*Test.kt` named for the defect they pin.
- Hazard: BuildVerification under sandbox needs the no-daemon + offline recipe:
  `JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" ./gradlew :test --tests "com.TTT.Pipeline.<TestClass>" --no-daemon --offline`.
- Hazard: a freshly-broken session falls back to `mavis@127.0.0.1:5432` (PostgreSQL)
  from the `hindsight_api` daemon. If `hindsight_recall` fails with connection error, restart
  via `systemctl --user restart hindsight` (or `daemon start`) before retrying — see
  `hermes-memory-local-embedded` skill.