# Memory says fixed ≠ source code fixed — re-verify file:line citations

Captured from a 2026-07-10 PumpStation bug-verification session. The user invoked this skill with "based on how the pumpstation should behave in a bug free state, please go through each trace and verify all the issues in memory regarding bugs it had are not happenning now after we made the changes." Memory listed 17 prior bugs with status claims like "FIXED at PumpStationLoop.kt:2390-2402" and "FIXED at PumpStation.kt:880-886 using hasExecutionFunction gate." Several of those memory claims turned out to be wrong.

**Symptom**: Triaging against a memory-cited file:line produces a "FIXED" verdict even though the live code at that line shows the original buggy behavior, or shows an entirely different fix surface, or shows that the cited code path is never actually invoked. The "fix" claim was either never real, was reverted, or was applied to a different file than memory said.

## Real examples from the 2026-07-10 verification session

- Memory cited "Bug 4 intervention silent no-op — FIXED at PumpStation.kt:880-886 using hasExecutionFunction gate." Live code: the `interventionAgent` and `interventionAgentBuilderFunction` fields are declared at lines 891 / 897, the builder setter exists at 3219, but `InterventionStarted(...)` is **never constructed anywhere** in production source. The entire intervention invocation path is absent. Memory's claim referenced the hasExecutionFunction gate — but that gate was the Bug 3 fix (NoExitSignalConfigured false positive), not Bug 4. Two different bugs got conflated.
- Memory cited "Bug 14 LoopGuardTripped detail field packs consecutive+limit" as a known cosmetic issue. Live code at PumpStation.kt:2843 still emits `detail = "consecutive=$consecutivePathCount, limit=${maxConsecutiveSamePath!!}"` — packed string, no separate meta keys. The cosmetic fix never shipped.

## The rule

When memory or a prior session transcript says "Bug X is fixed at file:line Y", you MUST:

1. Open the file at the cited line range. Read the actual code there. If it doesn't match the claimed fix surface, the memory claim is wrong.
2. If the memory-cited line number is off by a few lines (renumbering, edits since), search for the function name and read the current implementation. Confirm the fix is in the *current* code, not in memory.
3. If the memory-cited fix surface refers to a function/feature that doesn't exist in the current source (e.g., the agent path it described was renamed or removed), the bug class may have shifted — re-classify.
4. When memory describes a fix at a location that doesn't actually fix the described bug (conflated with a different bug's fix), report the memory error explicitly in the verification report — don't silently "verify" by checking a different bug's evidence.

## Tri-state verdict vocabulary for verification reports

Replaces the binary FIXED/NOT FIXED with five categories:

- **FIXED** — both source-code grep confirms the fix AND trace observation shows the symptom is gone. Cite both file:line and trace counts.
- **STILL PRESENT** — source-code grep shows the fix never landed OR trace observation shows the symptom persists. Cite the evidence.
- **NOT EXERCISED** — bug class not triggered by any of the test runs; cannot verify by trace observation; source-code grep only. Use this when (a) the test corpus doesn't cover the bug's trigger condition, or (b) the cited code path is dead code (declared but never invoked). The absence of symptoms in trace observation does NOT count as "FIXED" for this category — only source-code evidence can upgrade it to FIXED.
- **NOT PRESENT IN THIS RUN** — symptom was observed in prior runs (memory cites trace evidence) but didn't manifest in this run. Usually LLM-stochastic; absence in one run is NOT proof of permanent fix.
- **MEMORY CLAIM WRONG** — memory said "FIXED at X" but X doesn't contain the claimed fix. Re-verify and report the discrepancy. This is a distinct category from STILL PRESENT — the bug isn't just unfixed, the memory record is incorrect.

## Workflow when a memory bug claim lands at verification time

1. Open file at cited file:line. Compare memory's "expected fix surface" with the actual code. If they match, upgrade to FIXED (after trace evidence confirms symptom gone).
2. If they don't match but the code at that line is doing the right thing for a DIFFERENT bug — call out the conflation.
3. If they don't match and the code at that line still has the bug — STILL PRESENT.
4. If memory cited a feature/function that doesn't exist in the live source — feature may be absent; re-classify as NOT EXERCISED with a note that the invocation path is absent.

## Failure modes this prevents

- Verifier says "Bug 4 FIXED" because memory said so, without checking that the intervention agent is actually invoked anywhere
- Verifier cites a fix at a file:line that contains a different bug's fix (Bug 4 vs Bug 3 conflation above)
- Verifier ignores a packed-string emission bug because no test scenario triggers it (Bug 14 cosmetic)
- Verifier reports "no symptoms in fresh traces = fixed" for a bug whose trigger condition is absent from the test corpus

## Pairs with

Pitfall v1.3 "Fix claims need source-code evidence, not trace observation." That pitfall forbids claiming a fix without source-code grep; this pitfall extends it to forbid MEMORY-CITED source-code grep without re-verification against the live source. Both apply during the same verification pass.

## Worked example from the 2026-07-10 session

Verification report `/tmp/pumpstation-bug-verification-report-2026-07-10.md` (17-row chart with file:line + trace evidence per row). Net result: 5 FIXED, 1 STILL PRESENT (LLM-stochastic), 2 NOT EXERCISED (one of which had a wrong memory claim), 1 NOT PRESENT IN THIS RUN (LLM-stochastic), 8 NOT INVESTIGATED (no file:line anchors in memory). The tri-state verdict categories made the LLM-stochastic vs code-bug distinction explicit and let the user see exactly which bugs needed follow-up vs which were already handled.