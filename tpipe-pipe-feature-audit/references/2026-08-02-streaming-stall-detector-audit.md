# Streaming Stall Detector — Pipe-Level Feature Audit

The TPipe stall detector (commits 9999ce0a → d76a7a69, landed 2026-08-02 on
TPipe main) is the canonical worked example of a **streaming-observer feature**
— a pipe-level cross-cutting concern that fires not on a wire signal but on
the *statistics of the wire signal*. Use this reference when auditing or
wiring any feature that observes the streaming chunk stream and reacts to
properties of that stream.

## What it does

Detects when an LLM has stalled mid-stream (silently died without throwing).
Tracks inter-token interval timestamps via a rolling 50-interval ring buffer +
running sum/sum-of-squares (O(1) population mean and variance). After a
`warmupTokenCount` (default 20) warm-up, each new arrival tests:

```
silence > max(mean + stddevMultiplier × stddev, stallMinSilenceMs)
```

The conjunctive trigger (statistical bar AND absolute floor) is the key
design choice — see "Pitfalls" below. Fires a `StallCallback` for
notification and trips a retry through `PipeTimeoutManager.handleStallSignal`,
mirroring the existing `handleTimeoutSignal` path with a separate retry
counter.

## The audit recipe — six wire paths to verify

The existing five-path recipe (`tpipe-pipe-feature-audit/SKILL.md` § "The five
wire paths a pipe-level feature travels") enumerates main pipe, reasoning
pipe, `PipeSettings`, `ProviderConfiguration`, runtime overrides. The stall
detector adds a sixth path that future streaming-observer audits must check:

| Path | Stall detector surface | Verify |
|---|---|---|
| 1. Main pipe | `Pipe.enableStallDetector: Boolean` (Pipe.kt:941), `Pipe.stallDetectorConfig: StreamingStallConfig` (947), `Pipe.stallCallback: StallCallback?` (955, Transient) | `grep -nE 'enableStallDetector\|stallDetectorConfig\|stallCallback' src/main/kotlin/Pipe/Pipe.kt` |
| 2. Reasoning pipe | Independent. `setReasoningPipe(reasoningPipe)` does NOT carry stall settings. Reasoning pipes that stream need their own `enableStallDetector()` call. | `grep -rnE 'setReasoningPipe.*enableStallDetector\|reasoningPipe\.enableStallDetector' .` |
| 3. `PipeSettings` | NOT serializable. `stallCallback` is `@Transient` and the config is not on `PipeSettings` — feature cannot survive `toPipeSettings()` / `applyPipeSettings()` round-trips. | `grep -nE 'stall' src/main/kotlin/Structs/PipeSettings.kt` (expect zero hits) |
| 4. `ProviderConfiguration` | Not on any provider config dataclass. There is no `BedrockConfiguration(stallDetectorConfig = ...)` opt-in. Caller must use `pipe.enableStallDetector(...)` after factory construction. | `grep -nE 'stall' TPipe-Defaults/src/main/kotlin/ProviderConfiguration.kt` (expect zero hits) |
| 5. Runtime overrides | If a retry-swap calls `pipe.setModel(newModel)` etc. but NOT `pipe.enableStallDetector(...)`, the new pipe has stall detection off by default. Each pipe instance owns its own `enableStallDetector` flag. | `grep -nE 'setModel\|setStallCallback\|enableStallDetector' src/main/kotlin/orchestrator/...` |
| **6. Streaming callback manager** (NEW) | The detector subscribes per-chunk via `obtainStreamingCallbackManager().addCallback { chunk → detector.onTokenReceived(chunk, now) }`. Without the streaming callback manager being populated (i.e. without `setStreamingEnabled(true)` on the pipe), the detector never observes anything and is silent. | `grep -nE 'obtainStreamingCallbackManager\|streamingCallbackManager' src/main/kotlin/Pipe/Pipe.kt` |

The sixth path is the new shape that any *streaming-observer feature* must
satisfy. If the feature observes the chunk stream, its presence in paths
1-5 is insufficient — it must also be reachable from the streaming
callback chain.

## Pitfalls

### Streaming-observer features are silent when `streamingEnabled = false`

The detector is created inside `Pipe.executeMultimodal()` (Pipe.kt:6189)
gated on `enableStallDetector && streamingEnabled`. If a caller sets
`enableStallDetector()` on the pipe but never calls `enableStreaming(...)`
(or the provider transport's equivalent), the detector object exists but
never receives chunks. Same shape as the documented "streaming without a
callback is silent" pitfall in `tpipe-pipe-internals/references/streaming-transport-mechanics.md`
— but here the *observer* is silent, not the user-supplied callback.

Verification recipe: in the audit, check whether `enableStreaming(...)` and
`enableStallDetector(...)` are both called on the same pipe. A grep that
finds one without the other is a silent-no-op signature.

### The conjunctive trigger (μ + kσ) AND absolute floor

The detector uses `max(mean + stddevMultiplier * stddev, stallMinSilenceMs)`
NOT `mean + stddevMultiplier * stddev + stallMinSilenceMs`. Either condition
is sufficient — a slow model that pauses 11s fires on the floor alone even
when its mean+3σ says 8s; a fast model with occasional jitter fires on
statistics alone when the silence is 500ms but the floor is 10s. Both paths
to stall detection exist intentionally:

- **Floor path** (`stallMinSilenceMs`): catches "model died" regardless of
  normal throughput. Slow models need a high floor; fast models can use a
  low floor.
- **Statistical path** (`mean + kσ`): catches "model slowed dramatically but
  hasn't gone fully silent." A fast model emitting at 10ms intervals with a
  100ms gap fires because 100 > 10 + 3×0 = 10, even though 100ms is below
  any reasonable absolute floor.

Removing the floor produces false positives on slow-but-alive models (the
StreamingStallDetectorBehaviorTest "slow but alive model — 3s gap with 10s
floor does not fire" test pins this). Removing the statistical path
produces false negatives on jittery models that are functionally dead but
still producing occasional chunks. Both paths must remain.

### Population variance, not sample variance

The variance formula is `(sumSquares / N) - mean²` — divides by N (the
buffer count), NOT by N-1. This is population variance, and it is the
deliberate choice: the detector is observing the running stream, not
estimating a population parameter from a sample. The
`StreamingStallDetectorMathTest.variance formula is population variance, not
sample variance` test pins this contract (asserts `stddev ≈ sqrt(125.0)` not
`sqrt(500/3)` for `[10,20,30,40]`). Do NOT switch to sample variance
"for statistical correctness" — the detector is not a statistical estimator,
it is a streaming classifier.

### First token does not contribute an interval

`StreamingStallDetector.onTokenReceived` (StreamingStallDetector.kt:152)
early-returns on the first token (`lastTokenTimestamp < 0L`), recording
the timestamp but not computing or testing an interval. Without this guard,
the first inter-token interval is `currentTimestamp - 0` = `currentTimestamp`,
producing a spurious ~16M-ms interval on a Jan 1, 1970 epoch that would
fire a stall on the very first chunk.

The `first token does not contribute interval` test in MathTest pins this.
A future "fix" that removes the early-return to "simplify" will regress
the first-chunk behavior.

### `StallCallback` is suspend, fires via GlobalScope, failures are swallowed

The callback is `typealias StallCallback = suspend (StallEvent) -> Unit`
(StreamingStallDetector.kt:71). The detector fires it via `GlobalScope.launch
+ SupervisorJob + CoroutineExceptionHandler` (line 216) and catches any
exception from the body. Three implications:

1. **Callback failures must not crash the streaming loop.** The detector
   catches and discards, so a buggy callback never propagates back into the
   chunk delivery path. This is deliberate — the streaming pipe must keep
   flowing even if observability code throws.
2. **The callback is fire-and-forget on Default dispatcher.** Callers
   cannot rely on synchronous notification ordering; the stall event may
   fire AFTER subsequent chunks have already been emitted.
3. **The callback cannot return a retry decision.** The retry path is
   independent — it goes through `PipeTimeoutManager.handleStallSignal` in
   the `onStall` lambda at Pipe.kt:6194-6203. The callback is for
   notification only.

### Retry path mirrors `handleTimeoutSignal` but uses a separate counter

`PipeTimeoutManager.handleStallSignal` (Pipe.kt:590-635) is structurally
identical to `handleTimeoutSignal` but reads `pipe.stallDetectorConfig.maxStallRetries`
(default 3) instead of `pipe.maxRetryAttempts` (default 5) and writes to
`stallRetryAttempts: ConcurrentHashMap<Pipe, Int>` (line 454) instead of
`retryAttempts`. The two counters are independent — a pipe can exhaust its
stall retries (3) without exhausting its timeout retries (5), or vice versa.

The retry path sets `snapshot.repeatPipe = true` and the streaming
pipe's `abort()` is called (Pipe.kt:6202) to cancel the in-flight stream
so the outer `execute()` loop's `repeatPipe` check fires immediately
rather than waiting for the transport to finish. The abort calls
`activeStallDetector = null` (line 6135) to clear detector state between
executions.

Audit shape: when investigating "feature X retries into the running
pipe," verify that the new feature has its own counter (`stallRetryAttempts`,
not `retryAttempts`) and its own `handleStallSignal` entry point (not a
piggyback on `handleTimeoutSignal`). Sharing a counter conflates two
independently-tunable budgets and prevents per-feature retry tuning.

### `activeStallDetector` lifecycle: cleared on abort, cleared in `finally`

`Pipe.activeStallDetector` is cleared at Pipe.kt:6135 in `abort()` and at
Pipe.kt:6720 in the inner-job `finally` block. The cleanup pattern matches
`activeJob: Job?` (line 880-881) — both fields are `@Transient` and both
must be cleared to avoid state leak between executions.

Audit shape: any new pipe-level feature that creates per-execution state
needs the same "set on enter, clear on abort, clear in finally" triple
otherwise the second execution sees leftover state from the first.

### Pipeline-level propagation is config-only, not state

`Pipeline.enableStallDetector(config, callback)` (Pipeline.kt:724) sets
`enablePipelineStallDetector = true` and propagates the config + callback
to every child at pipe-attachment time (Pipeline.kt:1221-1226). Each
child pipe calls `pipe.enableStallDetector(pipelineStallDetectorConfig)`
and `pipe.setStallCallback(stallCallback)` — each pipe receives its OWN
`StreamingStallDetector` instance with its own rolling stats.

The comment at Pipeline.kt:1217-1220 is load-bearing: "stall detection does
NOT recursively cascade by default — each pipe owns its own
StreamingStallDetector since per-pipe stats need per-pipe state." This is
a deliberate departure from `enablePipeTimeout` / `applyTimeoutRecursively`
which DO recursively cascade (Pipe.kt:933). Future sessions extending
stall detection to "share rolling stats across pipes" must consciously
break this default and document why.

## Verification recipe for the stall detector specifically

When auditing "did stall detection actually get wired on pipe Y?":

```bash
# 1. Is the per-pipe flag set on the pipe you think?
grep -nE 'enableStallDetector\(\)|enableStallDetector\s*=' \
  src/main/kotlin/Pipe/Pipe.kt

# 2. Is streaming actually enabled on the same pipe? (silent-no-op otherwise)
grep -nE 'setStreamingEnabled\(true\)|enableStreaming\(' \
  src/main/kotlin/Pipe/Pipe.kt

# 3. Does the active detector get cleaned up between executions?
grep -nE 'activeStallDetector\s*=\s*null' \
  src/main/kotlin/Pipe/Pipe.kt
# Expected hits: 2 — one in abort() at line 6135, one in the inner-job
# finally block at line 6720. A count of < 2 means cleanup is incomplete.

# 4. Does the retry path actually mirror handleTimeoutSignal?
sed -n '590,635p' src/main/kotlin/Pipe/Pipe.kt
# Verify: separate stallRetryAttempts counter, separate
# maxStallRetries ceiling, separate trace event metadata keys
# (stallElapsedMs, stallTokensSeen, stallSilenceMs,
# stallExpectedIntervalMs, stallActualIntervalMs).

# 5. Does the population-variance contract survive?
grep -nE 'sumSquares.*\/.*n.*-.*mean.*\*.*mean' \
  src/main/kotlin/Pipe/StreamingStallDetector.kt
# Expected hit: at least one match in checkForStall (line 196).

# 6. Does the conjunctive trigger survive?
grep -nE 'maxOf.*stddevMultiplier.*stallMinSilenceMs' \
  src/main/kotlin/Pipe/StreamingStallDetector.kt
# Expected hit: line 198. A version that adds (not maxOf) the two is a regression.
```

A pipe that passes checks 1-3 but fails 4 has its detector firing but
silently dropping retry decisions. A pipe that passes 1-3 but fails 5 has
its detector firing but with wrong threshold math (false positives or
negatives). A pipe that passes 1-3 but fails 6 has its detector firing
on the wrong trigger shape.

## Why this is in `tpipe-pipe-feature-audit`

The stall detector is the canonical worked example for an audit methodology
extension: when the feature observes the streaming chunk stream, paths
1-5 are insufficient — the sixth path (streaming callback manager) is the
new shape to add to the recipe. The `references/streaming-transport-mechanics.md`
in `tpipe-pipe-internals` covers the per-chunk mechanics; this reference
covers the inter-chunk statistics layer where the detector lives.

The pitfall pattern is the same shape as the existing `tpipe-pipe-feature-audit`
entries (silent no-op, documented-contract-without-enforcement, broken
boundary). What is new is the LAYER the pitfall lives at: the chunk-stream
boundary, not the wire boundary. Future streaming-observer features
(throttlers, throughput governors, cost-per-stream guards, rate limiters
that watch token rate, etc.) all need this same audit shape.

## TPipe multi-project Gradle — the `:test` not `:TPipe:test` gotcha

When running the verification recipe above (or the one in `.hermes/plans/streaming-stall-detector.md`
Task 8), the gradle path matters. The TPipe repo is a multi-project
Gradle build where:

- The **root project** holds the stall-detector source: `Pipe.kt`,
  `StreamingStallDetector.kt`, `Pipeline.kt`, and `src/test/kotlin/com/TTT/Pipe/*` +
  `src/test/kotlin/com/TTT/Pipeline/*`.
- The **subprojects** are `TPipe-Bedrock`, `TPipe-Defaults`,
  `TPipe-GenericOpenAI`, `TPipe-MCP`, `TPipe-Ollama`, `TPipe-OpenRouter`,
  `TPipe-TraceServer`, `TPipe-Tuner`. None of these hold the stall-detector
  code, and the test filter has no matches in them.

The plan file at `.hermes/plans/streaming-stall-detector.md` (Task 1 Step 2,
Task 2 Step 2/4, Task 3 Step 3/5, Task 4 Step 4, Task 7 Step 2, Task 8) says
`./gradlew :TPipe:test` — this is wrong. Gradle reports:

```
Project 'TPipe' is ambiguous in root project 'TPipe'.
Candidates are: 'TPipe-Bedrock', 'TPipe-Defaults', 'TPipe-GenericOpenAI',
                'TPipe-MCP', 'TPipe-Ollama', 'TPipe-OpenRouter',
                'TPipe-TraceServer', 'TPipe-Tuner'.
```

The right invocations:

```bash
# SCOPED — root project only. Matches the stall-detector tests; subprojects
# are skipped.
./gradlew :test --tests "com.TTT.Pipe.StreamingStallDetector*Test" \
                --tests "com.TTT.Pipe.PipeStallDetectorDslTest" \
                --tests "com.TTT.Pipe.PipeTimeoutManagerStallTest" \
                --tests "com.TTT.Pipeline.PipelineStallDetectorDslTest"

# UNSCOPED — runs the test task in every subproject too. Works but
# TPipe-Tuner has no matching tests and fails with
# "No tests found for given includes" — the test task itself fails even
# though every other subproject passes.
./gradlew test --tests "..."
```

**Symptom of the wrong path**: "Cannot locate tasks that match ':TPipe:test'
as project 'TPipe' is ambiguous" — instant failure, no work done. Every
existing invocation in the plan file needs to be rewritten from `:TPipe:test`
to `:test` before the plan can be re-executed or audited.

**Authoritative pass-count signal — JUnit XML, not gradle stdout**. When
running the scoped `:test` command, gradle stdout drops `PASSED` markers
when tests produce substantial stdout (the Mantle Round 3 case in 1.5.0
changelog documents this; it applies here too — `StreamingStallDetectorBehaviorTest`
includes `delay(1)` calls that produce coroutine noise). Parse the XML
reports directly:

```bash
find build/test-results -name "*Stall*.xml" \
                       -o -name "*PipeStall*.xml" \
                       -o -name "*PipelineStall*.xml" 2>/dev/null \
  | xargs grep -hoE 'tests="[0-9]+" skipped="[0-9]+" failures="[0-9]+" errors="[0-9]+"' \
  | awk -F'"' 'BEGIN{t=0;s=0;f=0;e=0}
               {t+=$2; s+=$4; f+=$6; e+=$8}
               END{printf "tests=%d skipped=%d failures=%d errors=%d\n", t, s, f, e}'
# On stall-detector HEAD (verified 2026-08-02):
#   tests=39 skipped=0 failures=0 errors=0
# Spread across 7 classes:
#   PipeTimeoutManagerStallTest                  4 tests
#   StreamingStallDetectorTest                   3 tests
#   StreamingStallDetectorBehaviorTest           7 tests
#   StreamingStallDetectorMathTest              12 tests
#   StreamingStallDetectorIntegrationTest        5 tests
#   PipeStallDetectorDslTest                     5 tests
#   PipelineStallDetectorDslTest                 3 tests
```

A "tests=N skipped=0 failures=0 errors=0" line where N matches the
expected class sum is the green receipt. Any non-zero failures or errors
means a real regression — gradle's green BUILD SUCCESSFUL output alone is
not enough (build can succeed with test failures if the test task is not
a dependency of `build`).

## Cross-references

- `tpipe-pipe-internals/references/streaming-transport-mechanics.md` —
  per-chunk mechanics across providers (HttpURLConnection vs Ktor, SSE
  parsing, `emitStreamingChunk` override). Sibling reference: per-chunk
  delivery is here, inter-chunk statistics is here.
- `tpipe-pipe-feature-audit/SKILL.md` § "The five wire paths a pipe-level
  feature travels" — extend to six paths when the feature observes the
  streaming chunk stream.
- `tpipe-pipe-feature-audit/SKILL.md` § "Reasoning pipes have independent
  state" — the same lesson applies: a reasoning pipe that streams needs
  its own `enableStallDetector()` call; the main pipe's flag does not
  propagate via `setReasoningPipe()`.
- `.hermes/plans/streaming-stall-detector.md` (TPipe repo) — the
  implementation plan with the 8-task TDD recipe that produced this
  feature. Useful when re-implementing or extending the detector.
- `src/main/kotlin/Pipe/StreamingStallDetector.kt` — the implementation.
  Algorithm is fully documented in the class KDoc (lines 84-100).