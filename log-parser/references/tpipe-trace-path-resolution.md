# TPipe Trace Path Resolution

## Log Entry to File Mapping

```
Log entry:  .../{turnFolder}/{agentType}/{connectionId}/{baseFileName}.*
Actual dir: ~/.tpipe/debug/trace/{turnFolder}/{agentType}/{connectionId}/
Actual files: {baseFileName}.json, {baseFileName}.html
```

Example:

```
Log entry:  .../Round_1_Turn_0_Lord_Maple_Tree/PromptClassification/kvision-ws-client-869291157/_1777760961878.*
Actual:     ~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/PromptClassification/kvision-ws-client-869291157/_1777760961878.json
Actual:     ~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/PromptClassification/kvision-ws-client-869291157/_1777760961878.html
```

## Known Agent Types

These agents produce trace files via `saveAgentTrace()` or equivalent:

- `PromptClassification`
- `Judge`
- `ChatAgent`
- `AnswerAgent`
- `OpenAgent`
- `ValidationSplitter`
- `TurnResolutionSplitter`
- `AnalysisSplitter`
- `MaintenanceSplitter`
- `NeoWritingAgent`
- `TargetDetectors`
- `LorebookUpdate`

## Why Trace Files May Not Exist

### 1. Exception Before Save Call

The `saveAgentTrace()` call must be reached before any exception propagates. Typical failure:

```kotlin
// PromptManager.kt ~line 99
saveAgentTrace(agentType, connectionId, pipe)
return extractJson<SomeResult>(result.text)  // throws if JSON invalid
```

If `extractJson` throws, `saveAgentTrace` was already called (files exist).  
If exception occurs BEFORE `saveAgentTrace`, the log may still reference a save from a prior successful run.

### 2. Trace Directory Cleanup

The `~/.tpipe/debug/trace/` directory is periodically cleaned. Old turn folders disappear. Always check:

```bash
ls -lt ~/.tpipe/debug/trace/ | head -20   # most recent turn folders
ls ~/.tpipe/debug/trace/{turnFolder}/    # check agent types exist
```

## Timeout/Retry Mechanism (TPipe Pipe.kt)

### How Retry Works

TPipe pipes can be configured with `enablePipeTimeout()`:

```kotlin
enablePipeTimeout(
    applyRecursively = true,
    duration = 180000,        // 3 minutes
    autoRetry = true,         // enable Retry strategy
    retryLimit = 5
)
```

**Timeout trigger** (`Pipe.kt:5111`): `PipeTimeoutManager.startTracking()` fires a timer. On expiry, calls `pipe.abort()` causing `CancellationException`.

**Retry logic** (`Pipe.kt:5611-5625`):
1. Catch `CancellationException` when `PipeTimeoutManager.isTimeout(this@Pipe)` is true
2. Call `PipeTimeoutManager.handleTimeoutSignal(this@Pipe, inputContent)`
3. If `retryAttempts < maxRetryAttempts && timeoutStrategy == Retry`: increment counter, set `snapshot.repeatPipe = true`, re-execute

**Trace events**: `TraceEventType.PIPE_RETRY` logged with attempt number.

### Distinguishing Timeout-Driven vs Callback-Driven Restart

| Signal | Timeout-Driven | Callback-Driven |
|--------|---------------|----------------|
| Timing | Exactly 3 minutes after pipe start | 1-2 seconds after railroad completes |
| Log entry | `PIPE_RETRY` trace event | `AgentWorkStreamStreaming: Pipeline 'railroad' completed` followed by new pipe start |
| Log entry | `handleTimeoutSignal` | `buildBranchPipeFromTemplate` in branch construction |
| Gap | Fixed duration | Variable, suggests async callback |

### Validator Restart Pattern (Autogenesis Specific)

Observed in game logs:

```
23:49:00.408  legality checker pipe → Started (VALIDATOR_TRUTH)
23:49:07.105  validator pipe → Started (nested, VALIDATOR_TRUTH)
23:49:08.075  AgentWorkStreamStreaming: Pipeline 'railroad' completed
23:49:09.467  legality checker pipe → Started AGAIN (1.3 sec after railroad)
```

**NOT a timeout issue** — 1.3 second gap is far shorter than the 3-minute timeout. Caused by `buildBranchPipeFromTemplate` with `copyFunctions=true` copying the `preInitFunction` hook, which re-triggers validation when the branch pipe executes.

## Useful Grep Patterns

```bash
# Find all trace saves for a specific agent type
grep "Saved agent traces.*PromptClassification" ~/.autogenesis/logs/*.log

# Find validator restart patterns
grep -E "(railroad completed|legality checker.*Started|buildBranchPipeFromTemplate)" ~/.autogenesis/logs/*.log

# Find timeout/retry events
grep -E "(PIPE_RETRY|handleTimeoutSignal|repeatPipe)" ~/.autogenesis/logs/*.log

# Check if trace directory still exists for a turn
ls ~/.tpipe/debug/trace/Round_*_Turn_*_Lord_Maple_Tree/ 2>/dev/null
```