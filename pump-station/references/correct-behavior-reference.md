---
name: pumpstation-correct-behavior-reference
title: PumpStation Correct-Behavior Reference (triage ground truth)
description: Pointer to the canonical PumpStation behavior spec at /home/cage/.hermes/plans/pumpstation-correct-behavior.md (84 KB, 823 lines). Use as ground truth when triaging "is this a real bug or expected behavior?" reports, when the user references bug F1–F9, when a stub/live test fails and you need to know what the harness should have done at each phase, or when the third-pass triage workflow starts. Documents the file structure, how to read it, the third-pass triage workflow, and the four-bucket classification of bug claims.
---

# PumpStation Correct-Behavior Reference (triage ground truth)

## Why this file exists

The user maintains a hand-authored spec at `/home/cage/.hermes/plans/pumpstation-correct-behavior.md` (84,033 bytes, 823 lines, created 2026-07-07 17:32) that captures how PumpStation's harness is *supposed* to work — file map, `executeLocal` entry sequence, full `runTurn` per-turn phase order, `runJudgePhase`, `runDispatchPhase`, `runPathFlow`, `invokePath` funnel, `runMemoryUpdatePhase`, `runCompactionPhase`, SafePrune, foreground/background agents, exit flow, kill switch, pause guards, context blowout handling, dispatch JSON repair, and the full magic-contract enumeration.

**This file is the source of truth for triage.** When a bug report says "the harness did X wrong", consult this spec to determine whether X is a real bug or correct behavior. The 2026-07-07 catalog (Defects 1–26) was produced by exactly this kind of cross-reference.

## File structure

| Section | Lines | What it covers |
|---|---|---|
| Header | 1–11 | Why the doc exists, when to read it |
| File map | 12–24 | LOC + role per production file under `src/main/kotlin/Pipeline/` |
| Top-Level Entry: `executeLocal` | 25–37 | The canonical sequence for any config |
| The Harness Loop | 38–94 | `runHarnessLoop` + `runTurn` with strict turn-index semantics |
| `runJudgePhase` | 96–115 | 14-step order, FlagTriggered + Always-mode + skip-on-first-turn |
| `runDispatchPhase` | 117–138 | 8-step order including the JSON repair loop |
| `runPathFlow` | 140–146 | Path resolution + async vs foreground branching |
| `invokePath` (the funnel) | 148–174 | 13-step foreground path funnel: loop guards, risk check, kill switch, path validation |
| `runMemoryUpdatePhase` | 176–188 | Lorebook + summary async agents, pressure-gated join |
| `runCompactionPhase` (v3) | 190+ | Multi-attempt, pre-attempt gates, six `compactXxx` strategies, backup ring |

(Read the file for the full 823-line coverage — it includes SafePrune, foreground/background agents, exit flow, kill switch, pause guards, and the complete magic-contract enumeration.)

## The third-pass triage workflow

The user said: *"It's useful context, because you will be forced to do the triage for a third time."* The third-pass triage pattern:

1. **Load the spec first.** Open the doc and read at least the sections relevant to the bug claims. The user's bug reports reference symptoms that map to specific phase methods — match the symptom to the phase, read that section, then judge.

2. **Classify each claim into one of four buckets:**
   - **Real bug** — the spec says one thing, the code does another. Add to `references/harness-defect-catalog.md` with full symptom/root-cause/fix-sketch, link the bug-report file.
   - **Expected behavior** — the spec confirms the harness is supposed to do this. Explain to the user with a `path:line` citation from the spec. **Do not patch.**
   - **Test bug, not harness bug** — the test fixture is wrong (queue undersized, role misclassified, mock server teardown race). Fix the test, not the harness.
   - **Ambiguous** — the spec is silent or the symptom has multiple plausible causes. Print-instrument the boundary (see "Three debugging techniques" in the main SKILL.md) before classifying.

3. **Capture every bucket-1 finding in the catalog.** Use the format in `harness-defect-catalog.md`: status icon, severity, symptom, root-cause with `path:line`, fix sketch, verification. Link to the bug-report file if one exists.

4. **TDD before fix.** Every defect must have a failing test before the production fix. The catalog pattern is RED captured with timestamp + XML excerpt, GREEN captured with timestamp + `BUILD SUCCESSFUL` line.

5. **Cross-class verification sweep.** A fix in one phase often regresses another. After every defect fix, run the full sibling test sweep (the catalog's "verification grep" recipe) before claiming done.

## How to read the spec efficiently

The spec is long (823 lines). For a triage session with N bug claims:

1. Read the **File map** (lines 12–24) and **executeLocal** (lines 25–37) — that's the overall harness shape.
2. For each bug claim, jump to the relevant phase section. The section headers (`##`, `###`) are well-named.
3. Cross-reference the bug-report file under `/home/cage/.hermes/bug-reports/` (named `YYYY-MM-DD-bug-<short-name>.md`) — these are short, point-form summaries the user wrote to frame each bug.
4. If the spec's section is silent on a detail, the next step is `search_files` on the production source at `src/main/kotlin/Pipeline/PumpStationLoop.kt` and `:PumpStation.kt` for the method in question.

## Where this file came from

This skill reference was authored on 2026-07-07 during a third-pass triage session after the user said: *"Somewhere in .hermes, or /tmp you created this file. It's useful context, because you will be forced to do the triage for a third time."* The prior 2026-07-07 catalog (Defects 1–26) was the second pass; the user's framing implies a third pass is expected and this doc + this skill reference are the durable handoff so the next session starts already knowing what the spec is and where to find it.

## Anti-pattern: do NOT skip the spec

When a bug report sounds obvious ("the harness should fire X here, not Y there"), resist the urge to patch from intuition alone. The harness has 18 DITL hooks, 8 magic contracts, and a strict two-scope loop — what looks like a bug from outside is often a documented intentional choice in the spec. The five-minute spec read is faster than the hour of fix-and-revert cycles you'd otherwise burn on a wrong diagnosis.

**Rule of thumb**: every triage session opens with `read_file` on this spec (or the targeted section), not with `search_files` on the production code. The spec is the answer to "what should this have done?" — without it, you're guessing.