# PumpStation Defect Batch Subagent Dispatch Template

This is a context template for dispatching a single subagent to fix ONE PumpStation defect. Use when the operator wants the "subagents in sequence, verify between, intervene as needed" pattern across a multi-defect batch.

Proven pattern from 2026-07-10: 2 of 13 defects cleared with verified ad-hoc scripts in ~30 minutes. Each subagent gets a self-contained context that lets it work without round-trips back to the parent.

## When to use this template

- A multi-defect batch has been identified (typically from a trace audit or catalog review)
- Each defect has a clear surface (file:line + symptom + recommended fix approach)
- The operator wants sequential subagent dispatch with verification between
- The subagent will be a `leaf` role — no further sub-dispatch expected

## When NOT to use this template

- The defect has cross-cutting impact (touches >3 files) — use a different approach
- The fix isn't clear and needs investigation first — use `systematic-debugging` first, then dispatch
- The user wants the agent to dispatch a planning session before fixes — use `lead-architect` instead

## Template

```markdown
TPipe PumpStation defect batch (YYYY-MM-DD). T<N> of <TOTAL> tasks. Defect <M>: <SHORT TITLE>. Working tree: /home/cage/Desktop/Workspaces/TPipe/TPipe on main branch (base fcffc32f "Manifold Refactor"). Prior tasks already completed in this session: <T1, T2, ...> with patches at <file:line> — DO NOT TOUCH them.

AUDITED SURFACE (verify before patching):
- <file>:<line> — <what the code does wrong>
- <file>:<line> — <related call site>
- Evidence: <trace/audit/observation> shows the symptom.

USER-APPROVED FIX APPROACH (<option>, selected via clarify gate):
<a) Production patch at <file>:<line> — what to add/change
b) Production patch at <file>:<line> — what to add/change
c) RED test at <test file path> — what to assert>

KEY SOURCE FILES TO READ FIRST (before writing the test or patch):
1. <file>:<line range> — <what to look for>
2. <file>:<line range> — <what to look for>
3. src/test/kotlin/Pipeline/PumpStationTestFixtures.kt — buildTestStation(), testPath(), ScriptedTestPipe (canonical fixtures)
4. src/test/kotlin/Pipeline/PumpStation<Existing>Test.kt — pattern for the right kind of test (find the closest existing test to your defect's surface)
5. /home/cage/.hermes/skills/software-development/pump-station/references/sandbox-test-recipe.md — the sandbox build/test recipe (this template's companion)
6. /home/cage/.hermes/skills/software-development/pump-station/references/defect-batch-sandbox-discipline.md — Pitfall #N+8 (sibling runner contention), #N+9 (pre-applied fix detection), #N+10 (RED diagnostic purity); create your own per-defect runner per #N+8
7. /home/cage/.hermes/skills/software-development/pump-station/scripts/verify-pumpstation-defect-fix.sh — the ad-hoc verification pattern (10 checks)

CRITICAL RULES:
- Read existing test fixtures and test files BEFORE writing the new test. Use the established patterns.
- Imports use `org.junit.jupiter.api.Test` (JUnit 5), NOT `org.junit.Test` (JUnit 4 — wrong jar).
- Do NOT speculatively edit any other file beyond what's required for Defect <M>.
- Do NOT add new dependencies to build.gradle.kts.
- <T1 patch line ranges> MUST stay in place. Touch only your defect's surface.
- If the test fails with `kotlinx.serialization.SerializationException: Serializer for class 'PathRequest' is not found`, that's the kotlinx-serialization compiler plugin issue documented in references/sandbox-test-recipe.md. For this defect, design the assertions to avoid the serialization trigger — verify preconditions (parent wire reaches the pipe) or downstream effects (turnHistory content, return values) rather than PathRequest's serialized form.

SELF-REPORT BACK TO ME (deliverables):
1. Path to the new RED test file written.
2. Exact line numbers of the production patches.
3. RED output captured (snippet from the test runner showing the failure).
4. GREEN output captured OR explicit explanation if GREEN can't be reached in the sandbox. Tell me WHERE the GREEN signal lives.
5. Final git diff stat.
6. Your ad-hoc verification script path + PASS/FAIL counts.
7. Any support files added (test fixtures, etc.).

If you hit a blocker outside this defect's surface, write it up explicitly and return — don't expand scope. The orchestrator (cage) will intervene. <N+1>-<TOTAL> are queued after you.

Working tree base: `/home/cage/Desktop/Workspaces/TPipe/TPipe`. Compile from there. Read, patch, test, report. Use plain text in your final summary.
```

## What makes this template work

1. **Surface is verified before dispatch** — the parent (you) has already grep'd the source, read the trace artifacts, and identified the file:line. The subagent just verifies the surface hasn't moved and starts patching.
2. **Prior task patches are explicitly named** — the subagent knows which lines it must not touch, preventing accidental revert.
3. **The verification recipe is the canonical one** — `references/sandbox-test-recipe.md` is named so the subagent reads it, not re-derives it.
4. **Self-report is structured** — the 7-point deliverable list is what the parent needs to verify the work and to chain the next subagent. Without it, you get subagent prose that misses critical evidence.
5. **GREEN signal location is asked explicitly** — when the test can't run to GREEN in the sandbox, the subagent must say WHERE it would run green (under `./gradlew test`? under a different assertion design?). This prevents the parent from claiming "GREEN" without evidence.

## Verification pattern after subagent returns

1. Read the subagent's self-report (7 deliverables).
2. Read the full subagent output if available (subagent tool usually saves a summary file).
3. Run `/tmp/hermes-verify-t<N>-defect<M>.sh` (the script the subagent wrote).
4. Inspect the bytecode of the patched file via `javap -p -c -classpath build/classes/kotlin/main-recompile` to confirm the patch is live.
5. Check that the working tree diff doesn't have scope creep (e.g. 5+ files modified when only 1 was expected).
6. Mark T<N> complete in the goal marker, dispatch T<N+1>.

## Discovered failure modes

- **Subagent can't find `pathSafetyFunction` / `setXxxAgent` setter** — the skill body may reference symbols by old names. Mitigate by asking the subagent to grep before writing the test.
- **Subagent's `patch` tool fails on whitespace/indentation mismatch** — the pump-station code uses newline-brace style. Mitigate by passing the full line range in the dispatch context, not just line numbers.
- **Subagent self-flag "1 file NOT modified" warning at the end** — this is a common false alarm when the patcher hits one chunk fail but succeeds on a different chunk. Always verify the working tree diff, not the subagent's self-flag.
- **GREEN signal lives only under `./gradlew test`** — when the test relies on the kotlinx-serialization plugin (e.g. asserting `PathDescriptionList` injection), the sandbox can't run it. Document this clearly in the verify script's "NOT a suite-green verdict" footer so the operator knows what to expect.
