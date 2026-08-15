---
name: pumpstation-test-design-vs-code-fix
title: Test-Design vs Code-Fix Classification (PumpStation audit pattern)
description: Five-step protocol for classifying trace-surfaced defects as REAL BUG (patch) vs TEST DESIGN (redesign) before proposing a fix. Captured 2026-07-10 from a 13-defect audit session where 4 of the 13 "real bugs" turned out to be test-design failures. Load when triaging a defect audit, when a live test surfaces a "bug" that smells like the harness needs a defensive layer, or when running a PumpStation triage pass.
---

# Test-Design vs Code-Fix Classification (PumpStation audit pattern)

## The wrong default

When a "defect" surfaces from a live test failure, the wrong default is:

> "The test surfaced it, so the harness needs a defensive layer / fix to be made defensible."

The right default is:

> "The harness has the feature already; use it correctly in the test."

The PumpStation harness has 18 DITL hooks and 8 magic contracts. A live test that surfaces a "defect" often does so because the test didn't wire the existing feature surface correctly — not because the harness needs a defensive layer.

## Real instance: Defect 14 (2026-07-10)

Defect 14 surfaced from a live test that ran judge-LLM-only with no DITL hooks, no goal agent, no path-level failure signal. The path returned "I don't have enough information," the judge trusted structural completion, the harness exited with `JudgeComplete` carrying the failure text as the deliverable. The proposed "fix" was a defensive layer that filtered judge output.

**The right fix was redesigning the test** to use:

- `pathValidationFunction` (catches failure phrases in path output before judge gets to vote)
- Path self-correction (`terminatePipeline=true` on admission-of-failure)
- `goalAgent` (second-opinion verification before finalization)

The user-verbatim direction: *"The harness needs to use DITL hooks, goal agent, etc. — defensively papering over gaps is the wrong default. The agent is the issue, not the harness."*

## 5-step protocol before proposing any patch

1. **List every PumpStation feature the test design COULD have used but DIDN'T:** DITL hooks (`pathValidationFunction`, `postGenerateFunction`, `preInvokeFunction`), goal agent, intervention agent, path self-correction (`terminatePipeline=true`), health agent, lorebook agent, summary agent, `setJudgeRunMode(FlagTriggered)`, `setSkipJudgeOnFirstTurn`, reserve paths + `revealWhen`, `setPauseAt`, `setMaxHarnessTurns`, `setFailurePolicy.maxDispatchRepairAttempts`.

2. **For each "defect", ask: "if the test had wired feature X correctly, would this still be a bug?"** This is the load-bearing question.

3. **If yes — real bug, patch. If no — test design issue, redesign without patching.** Default to "test design" if uncertain; the operator can re-classify up.

4. **Cross-cutting rule for trace-surfaced defects:** every defect entry gets one of three labels:
   - `REAL BUG (patch)` — the harness has a real bug, ship a fix
   - `TEST DESIGN (redesign)` — the test mis-routed, redesign without patching
   - `BOTH (patch + redesign)` — both layers need attention

5. **Pair with the existing Pitfall #N+4 (LLM MISBEHAVIOR is verdict of LAST RESORT).** That rule says "verify the prevention mechanism exists and is wired before classifying as LLM fault." This rule says "verify the test used the harness's existing mechanism before classifying as harness bug." Both push back on the agent's "ship a defensive layer" default.

## Applies across all TPipe work

Manifold, Junction, Connector, Splitter, MultiConnector, DistributionGrid all have analogous surface areas (DITL hooks, kill switch, goal/verification layer, exit signals). When a "defect" surfaces from a live integration test, the test design audit is the load-bearing step — even when the surface area isn't PumpStation.

## Companion observation: user confirm-by-restatement

The user sometimes responds to clarify-gate text by echoing my framing back rather than clicking a row. That's a confirm-by-restatement signal — interpret as agreement when the echoed text is a clean restatement of the proposed option, but re-issue the gate explicitly with clearer option labels per the gate-response pitfall if the response is ambiguous.

## Canonical PumpStation verifiable-completion test pattern (the right way)

```kotlin
val station = pumpStation("research-X") {
    setJudgeAgent(realLLMJudge)        // first-opinion verifier
    setDispatchAgent(realLLMDispatch)
    setGoalAgent(realLLMGoal)            // second-opinion verifier

    path("research") {
        riskLevel = PathRiskLevel.Medium
        pathValidationFunction = { path, input, station ->
            // Catches path-level failure phrases before judge votes.
            result.text.contains("I don't have enough information").not()
        }
        setInternalAgent(researchAgent)  // path can return terminatePipeline=true on failure
    }
}

station.executeLocal(MultimodalContent(text = "research X"))
// Acceptable exit reasons:
//   - JudgeComplete (judge verified completion AND goal agent verified too)
//   - TerminateSignal (path self-corrected with terminatePipeline=true)
//   - GoalValidationFailed (goal rejected the work)
// NEVER:
//   - JudgeComplete with finalOutput containing admission-of-failure text
//     (this is the Defect 14 anti-pattern)
```

## Where to look in the existing skill

- `references/correct-behavior-reference.md` — documents the four-bucket classification (Real bug / Expected behavior / Test bug / Ambiguous). This file expands the "Test bug" bucket with the 5-step protocol.
- Pitfall #N+4 (LLM MISBEHAVIOR is verdict of LAST RESORT) in the main SKILL.md — companion rule for LLM-fault-vs-harness-fault.
- `references/harness-defect-catalog.md` — concrete examples of REAL BUG entries with file:line evidence.
