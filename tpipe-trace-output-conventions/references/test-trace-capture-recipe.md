# Test Trace Capture Recipe — Harness-Event Test Fixtures

Operator-mandated standard (2026-07-06, captured during the `pathSelectionRationale` feature
plan): every new test class that exercises a `PumpStation` harness event MUST capture
traces into the default trace dir resolved via `TPipeConfig.getTraceDir()`, matching
existing TPipe standards. This is not optional. The earlier convention captured in
`SKILL.md` (use `TPipeConfig.getTraceDir()` in production code) is the resolver half; this
file captures the test-side recipe that consumes it.

The earlier "Green Test is Not Enough" anti-pattern rule from the same skill applies here
verbatim. The point of this recipe is to make the standard concrete enough that any new
harness test can be written without re-deriving it.

## The Recipe (5 Steps)

### Step 1 — Resolve the trace dir via `TPipeConfig.getTraceDir()` at test setup

```kotlin
val traceRoot = File(TPipeConfig.getTraceDir(), "PumpStation")
val runSubdir = File(traceRoot, "${testName}-${System.currentTimeMillis()}")
runSubdir.mkdirs()
```

DO NOT inline a literal like `"~/.tpipe/debug/trace/PumpStation/${testName}"` — even in
test code. The earlier audit (PumpStation live test fix on 2026-07-06) caught exactly this
anti-pattern and replaced the literal with `TPipeConfig.getTraceDir()`. The test recipe
inherits that rule.

### Step 2 — Stamp a deterministic run id BEFORE exercising the harness

The harness event-emit path drops events whose `taskState.runId` is blank
(`tracePumpStationEvent` early-returns at `PumpStationHelpers.kt:80` on
`taskState.runId.takeIf { it.isNotBlank() } ?: return`). Tests that exercise the harness
MUST set `station.taskState.runId = "<runId>"` before invoking dispatch / judge / path
execution, or events land nowhere.

Pattern:

```kotlin
val runId = "test-${javaClass.simpleName}-${testName}-${System.currentTimeMillis()}"
station.taskState.runId = runId
```

The same `runId` value is used to derive the trace subdir in Step 1 so events written by
the harness land in the resolved `runSubdir`.

### Step 3 — Enable tracing via `enableTracing(config)` (NOT `setTracingEnabled`)

The PumpStation public tracing setter is `enableTracing(config)`. There is no
`setTracingEnabled` setter — that name surfaces in some older comments but does not
exist on the current class. The trap is real: searching for `setTracingEnabled` returns
hits in comments/docs that misled the prior live test fixture once.

```kotlin
station.enableTracing(
    TracingConfig(
        enabled = true,
        outputFormat = TraceFormat.HTML,
        detailLevel = TraceDetailLevel.DEBUG,
        autoExport = true,
        exportPath = runSubdir.absolutePath,
    )
)
```

The internal field name is `tracingEnabled` (no `set` prefix), and the setter takes a
config, not a boolean. Mirror the existing live test fixture exactly.

### Step 4 — Drive the harness, then list the resolved trace dir contents at teardown

After the test's primary assertions, but before teardown returns, list the runSubdir and
confirm at least one `pumpstation-<runId>.html` wrapper was written. If the wrapper is
missing, the test pin is broken even if all unit assertions passed.

```kotlin
val runDir = runSubdir
val pumpstationWrapper = runDir.resolve("pumpstation-${runId.take(12)}.html")
assertTrue(
    pumpstationWrapper.exists() || traceEventLogged,
    "<test> did not write a trace artifact to ${runDir} — fail closed"
)
```

Where `traceEventLogged` is any boolean assertion you've already made about an event
landing (e.g. `PipeTracer.getAllTraces().any { it.eventType == ... }`).

### Step 5 — Restore `TPipeConfig.configDir` in a try/finally if you mutated it

Per `SKILL.md` § Per-Test Isolation: if the test mutates `TPipeConfig.configDir`, save the
original and restore it in `finally`, regardless of pass/fail. The pattern is already
used in `Context/ContextWindowRemoteLockTest.kt` and `Context/RemoteMemoryTest.kt` —
copy that exact shape.

```kotlin
val originalConfigDir = TPipeConfig.configDir
try
{
    TPipeConfig.configDir = testSpecificDir.absolutePath
    // ... test code, including steps 1-4 above ...
}
finally
{
    TPipeConfig.configDir = originalConfigDir
}
```

If the test does NOT mutate `TPipeConfig.configDir` (the common case), no try/finally is
needed — `TPipeConfig.getTraceDir()` is computed at each call from the current
`configDir`, so subsequent tests inherit whatever the next test sets.

## Shared Fixture Helper (Recommended)

Across a single feature plan (e.g. the 5-test-class `pathSelectionRationale` rollout), a
single shared fixture helper at `src/test/kotlin/Pipeline/RationaleTestFixtures.kt`
exposes `buildScratchStationWithTracing(testName: String): Pair<PumpStation, File>`. The
helper performs Steps 1-3 and returns the configured station + the resolved `File` so
each test class can assert on the same dir:

```kotlin
// src/test/kotlin/Pipeline/RationaleTestFixtures.kt
package com.TTT.Pipeline

import com.TTT.Pipeline.PumpStation
import com.TTT.Util.TPipeConfig
import java.io.File

internal fun buildScratchStationWithTracing(testName: String): Pair<PumpStation, File>
{
    val traceRoot = File(TPipeConfig.getTraceDir(), "PumpStation/rationale-feature-tests")
    val runSubdir = File(traceRoot, "${testName}-${System.currentTimeMillis()}")
    runSubdir.mkdirs()

    val station = PumpStation()
    val runId = "test-${testName}-${System.currentTimeMillis()}"
    station.taskState.runId = runId
    station.enableTracing(
        TracingConfig(
            enabled = true,
            outputFormat = TraceFormat.HTML,
            detailLevel = TraceDetailLevel.DEBUG,
            autoExport = true,
            exportPath = runSubdir.absolutePath,
        )
    )
    return station to runSubdir
}
```

Each test class that imports this helper follows the recipe without re-deriving it.

## Failure Modes the Recipe Catches

| Failure | Symptom | What the recipe catches |
|---------|---------|------------------------|
| Hard-coded `~/.TPipe-Debug/` literal | Artifact lands outside `TPipeConfig.getTraceDir()` — survives CI override breakage silently | Step 1 + Step 4 path assertion |
| Forgot `taskState.runId` stamp | Events drop silently (`tracePumpStationEvent` early-return) | Step 4 wrapper-existence assertion |
| Used `setTracingEnabled` (does not exist) | Compile error or no-op depending on the model | Step 3 uses the real setter |
| `pumpstation-<runId>.html` never written | Test asserts pass but the trace side-effect was never observed | Step 4 final assertion |
| Mutated `TPipeConfig.configDir` and forgot restore | Subsequent tests pick up wrong dir, leak test artifacts into production paths | Step 5 try/finally restore |

## Why This Is a Recipe, Not a New Rule

`SKILL.md` already establishes (a) the resolver rule (use `TPipeConfig.getTraceDir()`),
(b) the per-test isolation rule (try/finally around `configDir`), and (c) the "Green
Test is Not Enough" rule (assert on location, not just existence). The recipe adds the
test-side specifics the earlier skill did not pin: the `taskState.runId` stamp, the
correct tracing setter name (`enableTracing`, not `setTracingEnabled`), and the shared
fixture helper pattern. These specifics are class-level recipe detail, not a new rule —
they live under the existing rule umbrella.