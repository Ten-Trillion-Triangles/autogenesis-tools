---
name: pump-station-catalog-staleness
title: Pitfall #N+5 — Catalog staleness and the trace-evidence + source-grep protocol
description: Pitfall capturing the 2026-07-10 audit lesson: defect catalogs become stale. Trace evidence (what the artifacts show) AND source-grep (what the current code does) are BOTH required to verify a defect is present. The catalog is a snapshot, not ground truth. Captures the F3-clone anti-pattern (a fix that creates a new clone of a prior bug class by missing the symmetric dedup step). Load when triaging any "is defect X still present?" question, before writing a plan that targets PumpStation, or when adding a new hint-append site.
---

# Pitfall #N+5 — Catalog staleness

**Symptom:** Treating the harness defect catalog (Defects 1–26 in `harness-defect-catalog.md`) as authoritative ground truth about what is broken right now. The catalog is a **snapshot of when it was written**; it can be wrong about the symptom location, the fix state, and even the defect's existence.

**Why this exists:** The 2026-07-10 audit pass re-verified the catalog and found:
- **Defect 18 was a catalog misdiagnosis** — the catalog claimed the `HarnessCompleted` funnel at `PumpStationHelpers.kt:117` dropped `exitReason` and `finalOutput`. The current source at `:132-137` clearly extracts both. The 2026-07-06 author must have read an earlier revision before the metadata extraction was added.
- **Defect 9 was already fixed** — the catalog claimed `applyRationaleNudgeIfNeeded` was unbounded. Current source at `PumpStationLoop.kt:2830-2858` has the `alreadyNudged` dedup check at `:2841-2844`. The fix landed but the catalog wasn't updated.
- **Defect 9 has a NEW clone** — the F3 path-safety hint at `PumpStation.kt:2907-2915` has the **same unbounded-duplicate anti-pattern** that pre-fix Defect 9 had. The fix for Defect 9 deduped the rationale nudge but the same dedup wasn't applied to the path-safety hint. A new defect, born from the original fix's blind spot.
- **Defect 8 is the most-acute outstanding issue** — path descriptors never injected into the dispatch pipe in any of 13 traces. The catalog diagnosis was correct, but the source has not been patched. The fix is small (wire `setParentInterface(station)` on the dispatch pipe) but undone.

## The 2-step verification protocol (mandatory before triaging any catalog defect)

1. **Trace evidence (necessary but not sufficient):** run the bulk-audit script `references/pumpstation-defect-audit-script.py` against `~/.tpipe/debug/trace/PumpStation/*/` to surface defect-pattern hits. Count signals per test. If a defect's signal is present in trace evidence, the symptom is reproducible in the artifact set.
2. **Source evidence (sufficient but doesn't prove trace-level symptom):** `git log -1 --oneline` to get the current HEAD. For each defect, grep the current source for the catalog's claimed source line + read the surrounding context. Confirm: (a) the line numbers haven't drifted, (b) the code is still in the state the catalog claims, (c) no fix has been applied since the catalog was written.

A defect is **"STILL TRUE"** only when BOTH conditions hold: trace evidence shows the symptom AND source evidence shows the buggy code. A defect is **"FIXED"** when EITHER the trace no longer shows the symptom OR the source has the corresponding fix. A defect is **"CATALOG MISDIAGNOSIS"** when trace evidence is absent and source evidence shows the catalog text was wrong.

## The F3-clone pitfall (most insidious)

When adding a new hint-append site (path-safety, JSON-repair, empty pathName, empty rationale, etc.), the **symmetric-hint-set pattern at Pitfall #N+4** requires the new hint to ALSO have an `alreadyNudged`-style dedup. Missing the dedup creates a clone of Defect 9 that doesn't appear in the original catalog because the catalog is keyed to the FIRST appearance of each defect, not subsequent clones.

Always check: **does the new hint site scan prior history before appending?** If not, the fix is incomplete. The four-symmetric-set table (see Pitfall #N+4 in the main SKILL.md) is the canonical checklist:

| Failure mode | Hint location | Dedup check? |
|---|---|---|
| Empty `pathName` from dispatch | `PumpStationLoop.kt:378-389` | No dedup (the dispatch failure is terminal each turn — not unbounded) |
| Empty `rationale` from dispatch | `PumpStationLoop.kt:2848-2854` | `alreadyNudged` check at `:2841-2844` ✅ |
| `DispatchJsonRepairFailed` (parse failure) | `PumpStationLoop.kt:359-398` | n/a (terminal after max attempts) |
| **Path-safety rejection** | `PumpStation.kt:2907-2915` | **NO DEDUP — F3-clone anti-pattern** ⚠️ |

The F3 path-safety hint is the only one in the set that has been added without a dedup. Future hint sites added to the set MUST include the dedup — even if the failure mode "shouldn't repeat", defensive dedup costs ~3 lines and prevents the unbounded-history growth that Defect 9 documented.

## When to apply this protocol

- Before triaging any "is defect X still present?" question
- After any fix is shipped — re-verify the catalog's status icon matches reality
- After any trace artifact is added — the new trace may be the FIRST evidence of a new defect
- Before writing a plan that targets PumpStation — the catalog's priority list may be stale
- After adding a new hint-append site — verify the symmetric dedup is wired

## Companion references

- `references/harness-defect-catalog.md` — the catalog itself; its "2026-07-10 audit pass" section is the most recent full re-verification
- `references/pumpstation-defect-audit-script.py` — bulk-parse tool for trace evidence
- `pump-station` main SKILL.md — the four-symmetric-hint-set table is at Pitfall #N+4

## Catalog re-verification protocol (concrete steps)

When re-verifying the catalog (next audit pass):

1. `cd /home/cage/Desktop/Workspaces/TPipe/TPipe && git log -1 --oneline` to get HEAD
2. For each Defect N, run the bulk-audit script and grep the trace for the defect's signal
3. For each Defect N, `grep -n "<defect's claimed source location>" src/main/kotlin/Pipeline/PumpStation*.kt` and read 20 lines of context
4. Build a status table: `(defect, trace_signal_present, source_fix_present, current_status, current_source_location_if_drifted)`
5. For each "current_status = STILL TRUE" defect, capture the path:`line` and a one-sentence fix shape
6. For each "current_status = FIXED" defect, capture the fix commit SHA or uncommitted-on-branch note
7. For each "current_status = CATALOG MISDIAGNOSIS" defect, write a "what the catalog said vs. what's actually in source" section so the next catalog author doesn't repeat the mistake
8. Update the catalog's "2026-XX-XX audit pass" section with the new findings; do NOT delete the prior audit pass sections (regression detection — if a fix re-introduces a defect, the section history shows the round-trip)
