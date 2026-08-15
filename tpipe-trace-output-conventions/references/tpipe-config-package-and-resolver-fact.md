# TPipeConfig: package, resolver chain, and test-isolation recipe

Quick reference for the package location of `TPipeConfig`, its resolver chain, and the safe per-test pattern for setting `configDir`. Captures facts that have caused import errors in sessions on 2026-07-06 and earlier.

## Package (the non-obvious one)

`TPipeConfig` lives in `com.TTT.Config.TPipeConfig`, NOT `com.TTT.Pipe.TPipeConfig`.

```
import com.TTT.Config.TPipeConfig
```

Confirmed against:
- `src/main/kotlin/Application.kt:9` — `import com.TTT.Config.TPipeConfig`
- `src/main/kotlin/Context/ContextBank.kt:3` — same
- `src/test/kotlin/Debug/JunctionTraceVisualizationTest.kt` — uses `TPipeConfig.getTraceDir()` directly with no import (same package)
- `src/main/kotlin/Config/TPipeConfig.kt` — the file itself

This trips up new task briefs because TPipe's overall package hierarchy is rooted at `com.TTT.*` with subpackages like `Pipe`, `Pipeline`, `MCP`, `Pcp`, `OpenRouter`, `Bedrock`. `Pipe` and `Pipeline` are different packages. `Config` is yet another.

## Resolver chain

```
TPipeConfig.configDir             — module-level mutable String (default: "${getHomeFolder()}/.tpipe")
TPipeConfig.getDebugDir()         — "${configDir}/debug"
TPipeConfig.getTraceDir()         — "${getDebugDir()}/trace"
TPipeConfig.getMemoryDir()        — "${configDir}/memory"
TPipeConfig.getTodoListDir()      — "${getMemoryDir()}/todo"
TPipeConfig.getLorebookDir()      — "${configDir}/lorebook"
```

`getTraceDir()` at `src/main/kotlin/Config/TPipeConfig.kt:52` is the canonical entry point for all trace HTML / JSON / debug output.

## Per-test isolation pattern

When a test needs to write traces into an isolated directory (not the user-default), save-and-restore `TPipeConfig.configDir` in a `try/finally`:

```kotlin
import com.TTT.Config.TPipeConfig

@Test
fun somethingThatWritesATrace()
{
    val testDir = createTempDirectory(prefix = "test-").toFile()
    val originalConfigDir = TPipeConfig.configDir
    try
    {
        TPipeConfig.configDir = testDir.absolutePath
        val traceDir = File(TPipeConfig.getTraceDir(), "PumpStation/run-1")
        traceDir.mkdirs()
        // ... test code, all TPipeConfig.getTraceDir() calls now resolve under testDir ...
    }
    finally
    {
        TPipeConfig.configDir = originalConfigDir
    }
}
```

Reference implementations in the codebase:
- `Context/ContextWindowRemoteLockTest.kt`
- `Context/RemoteMemoryTest.kt`
- `TPipe-Bedrock/.../QwenSemanticCompressionRoundTripTest.kt`

The save-and-restore MUST be inside the `try/finally`, not before-the-try or after-the-finally — module-level mutable state can be touched by parallel tests, and the only way to guarantee a clean restore on both success and exception paths is the `finally` block.

## The "is the trace dir writable under the test runner" guard

For unit-only tests that touch any policy or config class but don't yet write traces, add this guard at the end of the test to pin that `TPipeConfig.getTraceDir()` resolves to a non-blank string:

```kotlin
val traceDir = TPipeConfig.getTraceDir()
assertTrue(traceDir.isNotBlank(),
    "TPipeConfig.getTraceDir() must return a non-blank trace dir so subsequent tests can write traces.")
```

If the guard ever fails (returns blank or null), the test is running outside the canonical `TPipeConfig` initialization path. The fix is to wrap the test in the per-test isolation pattern above, or to add a `TPipeConfig.configDir = "/tmp/test-default"` call in a `@BeforeTest` setup method.

This guard is what Task 1.2 of the `pathSelectionRationale` plan added to its 4th test (`failurePolicyDefaultsRationaleRequirementToTrue`) and it's why `build/test-results/test/TEST-com.TTT.Pipeline.PathRequestRationaleTest.xml` shows the test passing in 0.085s with the assertion succeeding.
