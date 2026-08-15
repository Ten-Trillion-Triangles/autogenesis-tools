# Loop Execution and Goal Validation

Detailed state machine and code references for the PumpStation execution loop. Companion to the SKILL.md's "Two-Scope Loop Structure" section.

## Why This Reference Exists

The single most common documentation error for PumpStation is treating the judge's `isComplete: true` as a terminal signal. It is not — it's a **transition** into goal validation (`runExitFlow`). This reference captures the exact state transitions, the four exit signal sources, and the caller-visible return value so a future session doesn't re-derive them from code.

## The Two Scopes

| Scope | Function | What it does |
|-------|----------|--------------|
| **Outer** | `runHarnessLoop` (`PumpStationLoop.kt:1858-1888`) | Drives turns via `while (turnIndex < maxTurns && status == Running)`. Each iteration calls `runTurn()`. After the while loop, calls `runFinalizationPhase()` once. |
| **Inner** | `runTurn` (`PumpStationLoop.kt:1898-1969`) | Runs the per-turn phase methods (judge, dispatch, path, agents, memory, compaction). Returns `TurnResult.Continue` to re-enter the outer loop, or `TurnResult.Halt(reason)` to exit. |
| **Transition** | `runExitFlow` (`PumpStationLoop.kt:1712-1754`) | Goal-validation phase. Lives inside the outer loop but outside the inner cycle. Called when the judge says `isComplete: true` OR a path's `passPipeline` flows through. |
| **Once** | `runFinalizationPhase` (`PumpStationLoop.kt:2078-2085`) | Emits `HarnessCompleted` or `HarnessFailed`. Returns the harness's content object to the caller. |

## The State Machine

```
NotStarted
    ↓ P2PInitInternal()
Running + PreInit (runPreInitPhase)
    ↓
Running + Judge
    ↓ runTurn() — inner cycle
    │
    ├── judge.shouldTerminate
    │     ↓
    │   Halt(TerminateSignal)              [direct halt, NO goal gate]
    │
    ├── judge.isComplete
    │     ↓
    │   runExitFlow
    │     ├── goalAgent == null       → Halt(JudgeComplete)
    │     ├── goal agent passes       → Halt(JudgeComplete)
    │     ├── goal agent fails        → Continue  (re-loop with critique, ++goalFailCount)
    │     └── goal fails > maxGoalFailAttempts
    │                                 → Halt(GoalValidationFailed)
    │
    ├── judge.!isComplete (judge skipped in FlagTriggered)
    │     ↓
    │   runDispatchPhase → runPathFlow
    │     ├── passPipeline && goalAgent       → runExitFlow
    │     ├── passPipeline && !goalAgent      → Halt(PassSignal)
    │     ├── terminatePipeline               → Halt(TerminateSignal)  [direct halt, NO goal gate]
    │     └── (normal path execution)
    │           ↓
    │         runForegroundAgentsPhase
    │           ↓
    │         runBackgroundAgentsPhase
    │           ↓
    │         runMemoryUpdatePhase
    │           ↓
    │         runCompactionPhase
    │           ↓
    │         Continue
    │
    └── judge exception / unparseable JSON
          ↓
        treated as isComplete=false → Continue

Outer loop exit conditions:
- TurnResult.Halt (any of the above)
- turnIndex >= maxTurns → Halt(MaxTurnsHit) + lastError = MaxTurnsExceeded
- taskState.exitReason set (kill switch, forceHalt, etc.)
- taskState.status != Running
```

## Four Exit Signal Sources

Per the `ExitMechanism` enum (`PumpStationModels.kt:1033-1046`):

| Source | Triggered by | Goal gate? | Reason on halt |
|--------|--------------|------------|----------------|
| `JudgeAlways` | Judge returns `isComplete: true` | Yes (via `runExitFlow`) | `JudgeComplete` |
| `JudgeFlagTriggered` | Same as Always, but judge only fires when `requestJudgeNextTurn()` was called | Yes (via `runExitFlow`) | `JudgeComplete` |
| `PathPassPipeline` | Path returns `passPipeline: true` | Yes if `goalAgent` configured; else direct | `JudgeComplete` (with goal) or `PassSignal` (without) |
| `PathTerminatePipeline` | Path returns `terminatePipeline: true` | No (direct halt) | `TerminateSignal` |

Plus independent halts:

| Halt | When | Reason |
|------|------|--------|
| `Judge.shouldTerminate: true` | Judge returns `shouldTerminate: true` | `TerminateSignal` (no goal gate) |
| Kill switch | Token usage exceeds `KillSwitch.inputTokenLimit` or `outputTokenLimit` at any phase boundary | `KillSwitchTripped` |
| Max turns | `turnIndex >= maxTurns` after a turn completes | `MaxTurnsHit` + `lastError = MaxTurnsExceeded` |
| Goal validation exhausted | Goal agent failed more than `maxGoalFailAttempts` times | `GoalValidationFailed` |
| Force halt | External call to `forceHalt(reason)` | Caller-supplied reason |
| `preInvokeFunction` returns false | DITL abort gate before judge | `InterventionTerminated` |

## The Pre-Init Advisory

`runPreInitPhase` (`PumpStationLoop.kt:1771-1835`) emits a `HarnessWarning` event with `code = NoExitSignalConfigured` when **all** of these are true:
- `judgeAgent == null` AND `judgeAgentBuilderFunction == null`
- `judgeRunModeInternal != PumpStationJudgeRunMode.FlagTriggered`
- `maxTurnsInternal > 1`

The `mechanisms` field lists the four legitimate `ExitMechanism` values. The advisory is non-blocking — the harness continues, but the trace flags it.

## What the Caller Receives

`runFinalizationPhase` returns the harness's deliverable (`PumpStationLoop.kt:2078-2085`):

```kotlin
return taskState.lastPathResult ?: (taskState.latestContent ?: MultimodalContent())
```

So the caller sees:
- The last path's actual output if a path ran (the "deliverable" the harness produced)
- Otherwise `latestContent` (judge's verdict, path's output, original input, etc.)
- Empty `MultimodalContent()` as a last resort

This is what `executeLocal(content)` returns. It is the content object the harness passes forward, **not** the judge's verdict and **not** the dispatcher's path request.

## Critical Pitfall: Don't Treat the Judge as a Terminal Signal

When a future session asks "what happens when the judge says isComplete?", the answer is:

> The judge transitioning to `isComplete: true` calls `runExitFlow` (the goal-validation phase). Without a goal agent, the harness exits with `JudgeComplete` and returns the content object. With a goal agent, the goal validates — pass means deliver, fail means re-loop with the goal's critique appended to history (up to `maxGoalFailAttempts`).

**Wrong answer to flag:** "The harness exits when the judge says the task is done." This misses the goal agent entirely.

## Critical Pitfall: Path `passPipeline` Routes Through Goal Too

`PumpStationLoop.kt:1940-1953` — a path returning `passPipeline: true` does NOT directly exit. It calls `runExitFlow` if a goal agent is configured, falling through to `Halt(PassSignal)` only when no goal agent exists. With a goal agent, the goal is the gate. This is a frequent miss because the "no judge" case feels like it should bypass goal validation — it doesn't, if a goal agent is wired.

## Critical Pitfall: `terminatePipeline` Skips the Goal

`PumpStationLoop.kt:1954-1957` — a path returning `terminatePipeline: true` halts directly with `TerminateSignal`. There is no goal gate on `terminatePipeline`. The harness trusts the path's failure signal.

## Cross-References

- `src/main/kotlin/Pipeline/PumpStationLoop.kt:1712-1754` — `runExitFlow`
- `src/main/kotlin/Pipeline/PumpStationLoop.kt:1858-1888` — `runHarnessLoop`
- `src/main/kotlin/Pipeline/PumpStationLoop.kt:1898-1969` — `runTurn`
- `src/main/kotlin/Pipeline/PumpStationLoop.kt:1771-1835` — `runPreInitPhase` (with `HarnessWarning` advisory)
- `src/main/kotlin/Pipeline/PumpStationLoop.kt:2078-2085` — `runFinalizationPhase` (return value contract)
- `src/main/kotlin/Pipeline/PumpStationModels.kt:1010-1025` — `WarningCode.NoExitSignalConfigured`
- `src/main/kotlin/Pipeline/PumpStationModels.kt:1033-1046` — `ExitMechanism` enum
- `src/main/kotlin/Pipeline/PumpStationModels.kt:298-309` — `JudgeVerdict` data class
- `docs/superpowers/specs/2026-06-10-pumpstation-execution-loop-design.md` — full implementation spec

## Why This Was Added

Session 2026-06-14: A documentation request asked for full PumpStation docs. The initial version treated the judge as a terminal signal — wrong. The user corrected: "If the judge decides the task is done the harness exits to the outer loop where the goal agent can verify the work, or we exit and pass the content object forward." The correction exposed that the original `pump-station` skill's "Core Loop" section was missing the goal-validation transition entirely. This reference was added to capture the precise state transitions and prevent re-deriving them.
