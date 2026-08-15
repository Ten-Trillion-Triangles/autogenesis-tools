# PumpStation Defect Batch — Sandbox Discipline for Parallel Subagents

Companion to `templates/pumpstation-defect-dispatch-context.md` and `references/sandbox-test-recipe.md`. Captures the operational discipline a subagent must follow when working on **T<N>** of a parallel fan-out batch (T1, T2, T3+ all touching the same TPipe working tree from independent sessions simultaneously).

Source: 2026-07-10 T3 (Defect 11) session — confirmed necessary by direct observation (empty log files, pre-applied patches, sibling-runner collisions).

---

## Pitfall #N+8 — Sibling subagent `pumpstation_run_test.sh` contention produces empty log files

**Symptom:** Background `bash pumpstation_run_test.sh <T> > /tmp/red_run.log 2>&1` exits with `exit_code=1` and `wc -l /tmp/red_run.log` returns `0`. No stdout, no stderr. Process appears to run for 60+ seconds then exit silently. Repeated runs produce the same empty file.

**Real instance (2026-07-10 T3):** Three subagents (T1/T2/T3 fan-out) all launched `bash /tmp/pumpstation_run_test.sh com.TTT.Pipeline.<TheirTest> --rebuild-main` within ~90 seconds of each other. The shared runner:
- Writes the launcher source to `/tmp/RunOneTest.kt` (overwritten by every sibling)
- Compiles launcher + tests into the shared `build/test-classes-direct/` directory (race-condition overwrites)
- The `--rebuild-main` flag recompiles all Pipeline files (kotlinc is CPU/memory heavy; three parallel compiles kill each other or one of them gets a partial overwrite)

The T1 and T2 subagents had already left their own per-defect runners (`pumpstation_run_test_t10.sh`) using `RunOneTest_T10Kt` and similar. T3 inherited the shared script and collided.

**The rule:** when working on T<N> of a fan-out batch where siblings T1..T<N-1> are likely live or recently-live, **always create your own per-defect runner** by copying T10's pattern:

```bash
cp /tmp/pumpstation_run_test_t10.sh /tmp/pumpstation_run_test_t<N>.sh
sed -i 's/_T10/_T<N>/g; s/T2 (Defect 10)/T<N> (Defect <M>)/g; s/RunOneTest_T10Kt/RunOneTest_T<N>Kt/g' /tmp/pumpstation_run_test_t<N>.sh
chmod +x /tmp/pumpstation_run_test_t<N>.sh
```

This gives you:
- A unique launcher class name (`RunOneTest_T<N>Kt`) so your compiled launcher can't be clobbered by a sibling recompile.
- Your own copy of the recipe (you can change `--rebuild-main` defaults, fix bugs, etc.) without affecting T1/T2.
- A `.sh` file in `/tmp/` named after your defect, which makes `ps -ef | grep pumpstation_run_test_t<N>` trivial when debugging.

**The diagnostic for empty log files:**
```bash
ps -ef | grep -E "(kotlinc|pumpstation_run)" | grep -v grep
```
If you see another subagent's `pumpstation_run_test_t10.sh` (or any sibling) running, **wait for it to finish** (or kill it if you outrank them) before launching yours. Better: create your own and don't share `/tmp/RunOneTest.kt`.

**Cost of this bug:** 15-20 minutes of confusion per occurrence. The fix is a 30-second `cp` + `sed`.

---

## Pitfall #N+9 — Pre-applied fix detection (concurrent subagent raced ahead)

**Symptom:** You start T<N>, read the source, and discover the source tree already contains the fix as an unstaged diff against `HEAD`. The `invokePath` body has been reordered (or whatever your defect calls for) before you even started patching.

**Real instance (2026-07-10 T3, Defect 11):** Working tree showed `git status` with `M src/main/kotlin/Pipeline/PumpStation.kt` — the `invokePath` body had the risk-check block already moved before the loop-guard block (the exact fix the dispatch template prescribed). A sibling subagent (or an earlier T3 attempt that didn't complete) had already applied the patch.

If you naively run the test against the current source, your RED test PASSES (no bug to find). You waste time believing the test is broken.

**The rule — verify RED first, fix second:**

1. `cp src/main/kotlin/Pipeline/PumpStation.kt /tmp/PumpStation.kt.GREEN-patched` — preserve the current (possibly-fixed) state.
2. `git checkout HEAD -- src/main/kotlin/Pipeline/PumpStation.kt` — revert to the unfixed HEAD.
3. Run your RED test. It MUST fail with the documented symptom (e.g. `LoopGuardTripped` fired on safety-rejected path).
4. `cp /tmp/PumpStation.kt.GREEN-patched src/main/kotlin/Pipeline/PumpStation.kt` — re-apply the fix.
5. Run your GREEN test. It MUST pass.
6. `git diff HEAD -- src/main/kotlin/Pipeline/PumpStation.kt` — confirm the diff matches the intended fix (and nothing else).

**Why this matters more than just "skip RED":**
- The verification script (`/tmp/hermes-verify-t<N>-defect<M>.sh`) typically has a "RED captured" check. Without a real RED, that check is hand-waving.
- If your patch is subtly different from the sibling's, you need the RED phase to catch that divergence.
- A test that passes against unfixed source is a TEST BUG, not a "fix already in place" finding.

**Diagnostic when you suspect this pitfall:**
```bash
git diff HEAD --stat src/main/
# If you see modifications on files in your defect's surface, the fix may already be applied.
git diff HEAD -- src/main/kotlin/Pipeline/<YourFile>.kt | head -20
# Read the actual diff to see what was changed.
```

**Cost of this bug:** a "PASSING" test run that you can't trust + 10-20 minutes of debugging "why is my test passing on unfixed code?". The fix is two `cp` commands and a `git checkout`.

---

## Pitfall #N+10 — RED-only diagnostics can deceive when prior unrelated work is still uncommitted

**Symptom:** When the working tree has uncommitted modifications from sibling subagents (T1's pumpstation-loop.kt patch, T2's pumpstation-helpers.kt patch, etc.), running a test on `HEAD`'s source after reverting your own file gives you a test outcome that mixes in **the siblings' uncommitted behavior**. Your RED assertion may not be exactly what would happen on a truly-clean `HEAD`.

**Real instance (2026-07-10 T3):** When reverting `PumpStation.kt` to `HEAD` for the RED capture, the `PumpStationLoop.kt` and `PumpStationHelpers.kt` still had T1+T2 unstaged patches that affected `runPathFlow`, `applyPromptsToPipeline`, etc. The T3 test only drives `invokePathInternal` directly so it doesn't depend on those siblings — but a T4+ subagent working on `runPathFlow` itself would have been confused by T1+T2's behavior bleeding into its RED capture.

**The rule:** if your defect lives in `PumpStation.kt`, your RED capture is robust to T1/T2 sibling patches in `PumpStationLoop.kt` / `PumpStationHelpers.kt` (no bleed). If your defect lives in `PumpStationLoop.kt`, you need to:
1. Save the current `PumpStationLoop.kt` (which has T1+T2 patches live).
2. Decide whether to revert the T1+T2 portions or work around them. Reverting breaks the siblings' work; working around may produce a misleading RED.

**The general principle:** the RED capture's purity depends on which file your defect is in. For T3 (`PumpStation.kt::invokePath`), the purity is fine. For T4+ in `PumpStationLoop.kt` or `PumpStationHelpers.kt`, the parent orchestrator should sequence: T3 (PumpStation.kt) first, then T4 (PumpStationLoop.kt, but only after T3 lands in a clean commit), then T5 (PumpStationHelpers.kt). Otherwise each subagent inherits sibling noise.

**Cost of this bug:** A test that passes on unfixed code because the unfixed code is no longer truly unfixed (the siblings' patches compensate for the bug). Worst case: a false GREEN that ships an unfixed bug to main.

---

## Operator-fires-twice pitfall — confirmed canonical pattern

The operator mentions an "Observer-fires-twice pitfall: dedup events by `(turnIndex, timestamp)` per the pump-station skill." This is **Pitfall #N+2** in `references/tdd-recipe-pitfalls.md`. The pattern is:

```kotlin
val seen = mutableSetOf<Pair<Int, Long>>()
station.setEventObserver { event ->
    if (event is LoopGuardTripped) {
        val key = event.turnIndex to event.timestamp
        if (seen.add(key)) loopGuardList.add(event)
    }
}
```

**Why `Pair<Int, Long>` not `Pair<Int, Int>`:** `event.timestamp.toInt()` truncates the millisecond timestamp to 32 bits and loses millisecond disambiguation. Two events fired in the same second will have the same `toInt()` value. Use `event.timestamp` directly as `Long`.

**Confirmed working in T3 Defect 11:** `safetyRejectedPathNeverTripsLoopGuard` uses `val key = "guard" to event.timestamp.toInt()` (with a `String` prefix to avoid cross-event-type collisions) and successfully dedups 1 event across 3 `invokePathInternal` calls. The pattern is solid.

For mixed event-type observers (e.g. both `PathSafetyCompleted` and `LoopGuardTripped`), include the event-type discriminator in the key:

```kotlin
val key = event::class.simpleName!! to event.timestamp
```

This avoids the rare case where a `PathSafetyCompleted` and a `LoopGuardTripped` fire in the same millisecond (turn boundary) and collide on `(turnIndex, timestamp)`.

---

## Cross-references

- `templates/pumpstation-defect-dispatch-context.md` — the dispatch template these pitfalls fill in
- `references/sandbox-test-recipe.md` — the per-defect runner recipe these pitfalls complement
- `references/tdd-recipe-pitfalls.md` — Pitfall #N+2 (observer-fires-twice), Pitfall #N+7 (`*Internal` direct-drive), Pitfall #N+3 (runId clobber)
- `references/new-pitfalls-2026-07-10.md` — Pitfall #N+5 (audit-vs-test-design classification), #N+6 (read existing fixtures first), #N+7 (JUnit 5 import)
- `/tmp/pumpstation_run_test_t*.sh` — the per-defect runner scripts (T10, T11, ...) that Pitfall #N+8 prescribes creating

## When to merge into the main SKILL.md

When the next pump-station skill refactor happens (SKILL.md is at character cap), these three pitfalls (#N+8/#N+9/#N+10) should be added to the main SKILL.md alongside #N+2 through #N+7. The "Operator-fires-twice" pattern note belongs at the top of #N+2.