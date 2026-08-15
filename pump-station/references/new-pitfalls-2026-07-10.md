# PumpStation Pitfalls — added 2026-07-10 from the 13-defect batch session

This file documents three new pitfalls that emerged from the 2026-07-10 trace audit + TDD fix session. The original `pump-station/SKILL.md` was approaching its character cap, so these pitfalls are captured here as a reference. When the SKILL.md is next refactored, merge these into the main pitfalls section.

---

## Pitfall #N+5 — Audit-class=patch vs Test-class=redesign (the OOB correction)

**Symptom:** The trace audit produces a "defect" entry; the agent immediately drafts a production patch (new defensive layer, new verification gate, new rejection fallback) without first asking whether the defect is in the harness code or in the test that surfaced it.

**Real instance (2026-07-10):** During the 13-defect batch, the agent proposed a defensive verification layer for Defect 14 (judge accepts `isComplete=true` from a path that admitted failure). The operator's OOB correction: *"#14 is a you problem. The othere are bugs. I stated clearly #14 was the you problem. And I stated clearly you need to across the board improve test deesign and makee better use of the pumpstation harness and tools to avoid your bad decision making annnd designs being flagged a bug."*

The defensive layer was the wrong move. The actual fix was to redesign the test to use `pathValidationFunction` DITL hook + `goal` agent + path self-correction (`terminatePipeline: true` on failure) — three PumpStation features that were already in the design but not wired in the test. Patching the harness to add a fourth layer of defense would have been layering over a test-design failure.

**The rule:** For each defect in an audit catalog, classify it as one of:

- **A. Real harness bug (PATCH)** — the spec is clear, the surface is in the harness code, the trace shows a genuine failure mode that no test-design change could avoid. **One production patch, TDD-RED-GREEN.**
- **B. Test-only bug (REDESIGN THE TEST)** — the trace shows a test that doesn't use PumpStation's existing features correctly. The fix is in the test, not the harness. No production patch. Document the canonical test pattern that should have been used.
- **C. LLM misbehavior (PROMPT + DEFENSE)** — the harness is doing the right thing, but the LLM consistently misbehaves. Add minimal defense (F3 hint-injection, F4 prompt constraint, F5 prescriptive termination) but no big architectural change.
- **D. Expected behavior (DOCUMENT)** — the spec is silent or the symptom is the documented behavior. Document, do not patch.

**The test:** before patching, ask "Could a redesign of the live test that surfaced this defect have caught it without the harness change?" If yes → class B. If no → class A.

**Anti-pattern:** defaulting to "add a defensive layer" because that feels safer. PumpStation ships with eight LLM magic contracts, six DITL hooks, three memory management modes, and a path safety system — there is no scenario where "just add a defensive layer" is the right answer if those features are wired correctly.

---

## Pitfall #N+6 — Read existing test fixtures BEFORE writing a new test

**Symptom:** Agent writes a new test file referencing symbols, classes, or patterns that don't exist in the project. The test compiles in isolation only if the agent happened to guess right; otherwise it fails to compile with errors that name symbols the agent invented.

**Real instance (2026-07-10 T1):** Wrote `PumpStationDispatchPathInjectionTest.kt` referencing:
- `com.TTT.testing.MockPipe` (doesn't exist — actual fixture is `ScriptedTestPipe` in `PumpStationTestFixtures.kt`)
- `pipe.onApplySystemPromptComplete = { ... }` callback (no such setter — `Pipe` exposes `getSystemPromptForTest()` for read-only capture)
- `Pipeline().getEntryPipe()` (no such method — use `Pipeline().getPipes()` and iterate)
- `com.TTT.Pipe.Pipe` direct import with custom class extension (works but bypasses the canonical fixture)

Fix: read `src/test/kotlin/Pipeline/PumpStationTestFixtures.kt` BEFORE writing the test. It has 4 reusable helpers: `buildTestStation(maxHarnessTurns)`, `testPath(name, returnText)`, `ScriptedTestPipe(name, response)`, `MockP2PAgent(script)`. The canonical pattern for capturing composed prompts is to subclass `Pipe` and read `systemPrompt` via `getSystemPromptForTest()` after `applySystemPrompt()` runs (override `onApplySystemPromptComplete` to copy the field).

**The rule:** before writing a test in a TPipe project, read in this order:
1. `src/test/kotlin/Pipeline/PumpStationTestFixtures.kt` — the canonical fixtures
2. The existing test file most similar to your defect (e.g. `PumpStationDispatchDefaultsTest.kt` for dispatch-related defects, `PumpStationLoopGuardResetTest.kt` for loop-guard defects)
3. The matching test pattern is in 90% of cases. Don't reinvent the wheel.

**The cost of skipping:** 30 minutes of compile errors, three iterations of the test, and a test that doesn't match the project's idiomatic style. The cost of reading: 3-5 minutes.

---

## Pitfall #N+7 — JUnit 5 `org.junit.jupiter.api.Test` not `org.junit.Test`

**Symptom:** Test compiles successfully but the JUnit Platform discoverer finds 0 tests at runtime. The summary report shows "1 containers found, 2 tests found, 0 tests started" — the class is discovered, the methods are scanned, but none of them are treated as runnable tests.

**Real instance (2026-07-10 T1):** Wrote the test file with `import org.junit.Test` (a JUnit 4 annotation). The kotlinc compiler happily resolved it via the JUnit 4 jar in the classpath. The compiled bytecode had `@Lorg/junit/Test;` annotations on the methods. But the JUnit Platform launcher was using the JUnit 5 Jupiter engine SPI (`META-INF/services/org.junit.platform.engine.TestEngine`), which only recognizes `@Lorg/junit/jupiter/api/Test;`. Result: 0 tests discovered.

**The rule:** for any TPipe test (and any modern Kotlin/JVM project on Gradle with `testImplementation` set to JUnit 5), use `import org.junit.jupiter.api.Test`. The JUnit 4 annotation is a footgun.

**The diagnostic:** if `RunOneTest.kt` shows "0 tests found" after a clean compile, the first thing to check is `javap -p -v TestClass.class | grep -E "Lorg/junit/Test|Lorg/junit/jupiter/api/Test"`. If you see `Lorg/junit/Test;` only (no `Lorg/junit/jupiter/api/Test;`), that's the bug.

**The cost of this bug:** 5-10 minutes of confusion per occurrence, because the compiler doesn't catch it and the test runtime gives a confusing "0 tests" message instead of a clear annotation error. The fix is a one-line import change.

---

## Companion reference (added T3 Defect 11 session, 2026-07-10)

**`references/defect-batch-sandbox-discipline.md`** — Pitfall #N+8 (sibling subagent `pumpstation_run_test.sh` contention produces empty log files; fix is per-defect runner with unique launcher class name like `RunOneTest_T11Kt`), Pitfall #N+9 (pre-applied fix detection — when the working tree already has the fix as an unstaged diff from a concurrent sibling; revert-to-HEAD-to-capture-true-RED pattern), Pitfall #N+10 (RED-only diagnostic purity depends on which file your defect lives in). Also documents the operator-fires-twice dedup pattern with `Long` timestamp (not `toInt()`).

## When to merge these into the main SKILL.md

When the next PumpStation audit cycle happens, the operator should consider:

1. Bumping `pump-station/SKILL.md` version to 1.17.0
2. Adding a "Pitfalls" section that includes the three new entries (currently the SKILL.md is at 100,957/100,000 char limit)
3. Either: (a) refactor the existing pitfalls section to be more compact and squeeze in the new ones, or (b) split the SKILL.md into SKILL.md + `pitfalls.md` reference

The current state — pitfalls in a separate reference file — works but is below the skill-library quality bar of "pitfalls in the SKILL.md body, not buried in references."
