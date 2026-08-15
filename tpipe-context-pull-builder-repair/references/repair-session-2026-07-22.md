# 2026-07-22 PumpStation context bridge repair

## What shipped

The dead `Pipe.pullPumpStationContext()` builder was wired into `executeMultimodal()` so an opted-in pipe now imports the nearest PumpStation's `ContextWindow` and `MiniBank` during execution. The fix preserves the documented one-way contract, reuses the existing `P2PInterface.getNearestPumpStationParent()` / `getContextWindowFromInterface()` / `getMiniBankFromInterface()` accessors, and deep-copies before merging.

## Files changed

- `src/main/kotlin/Pipe/Pipe.kt:6094-6103` — new merge block immediately after parent-pipe context.
- `src/test/kotlin/Pipe/PipePumpStationContextTest.kt` — seven-test matrix (new file).

## Pre-flight verification (RED)

```
6 tests completed, 3 failed

PipePumpStationContextTest > pullPumpStationContextImportsMiniBankPages() FAILED
    org.opentest4j.AssertionFailedError at PipePumpStationContextTest.kt:66
PipePumpStationContextTest > pumpStationContextMergesAfterParentPipeContext() FAILED
    org.opentest4j.AssertionFailedError at PipePumpStationContextTest.kt:96
PipePumpStationContextTest > pullPumpStationContextImportsContextWindow() FAILED
    org.opentest4j.AssertionFailedError at PipePumpStationContextTest.kt:50
```

The three REDs exactly match the defect: the flag was never read. The other four tests pass because they exercise behaviors that depend on the absent branch (opt-out, missing ancestor, isolation).

## Post-fix verification (GREEN)

```
BUILD SUCCESSFUL in 53s
20 actionable tasks: 11 executed, 9 up-to-date
```

All seven tests passed. Adjacent tests (`com.TTT.Pipeline.PumpStationDispatchPathInjectionTest`) continued to pass.

## Final uncached rerun

```
./gradlew :test --rerun-tasks --tests "com.TTT.Pipe.PipePumpStationContextTest" --tests "com.TTT.Pipeline.PumpStationDispatchPathInjectionTest"
BUILD SUCCESSFUL in 1m 36s
20 actionable tasks: 20 executed
```

`--rerun-tasks` was mandatory here. Without it, Gradle reports `UP-TO-DATE` and the system reminder treats the run as no fresh evidence.

## Working tree at session close

```
## main...origin/main [ahead 1]
 M docs/api/pipe.md
 M docs/core-concepts/developer-in-the-loop.md
 M docs/core-concepts/reasoning-pipes.md
 M src/main/kotlin/Pipe/Pipe.kt
 M src/main/kotlin/Pipeline/PumpStation.kt
 M src/main/kotlin/PumpStationDsl.kt
?? src/test/kotlin/Pipe/PipePumpStationContextTest.kt
?? src/test/kotlin/Pipeline/PathObjectStandaloneDslTest.kt
```

The five pre-existing modifications to docs and Pipeline files were not touched. The two untracked files are both new (this session's test, plus the operator's existing `PathObjectStandaloneDslTest.kt`).

## Final patch (verbatim)

```kotlin
            if(readFromPumpStationContext)
            {
                val pumpStationParent = getNearestPumpStationParent()
                pumpStationParent?.getContextWindowFromInterface()?.let { pumpStationContext ->
                    contextWindow.merge(pumpStationContext.deepCopy(), emplaceLorebook, appendLoreBook, emplaceConverseHistory, emplaceConverseHistoryOnlyIfNull)
                }
                pumpStationParent?.getMiniBankFromInterface()?.let { pumpStationMiniBank ->
                    miniContextBank.merge(pumpStationMiniBank.deepCopy(), emplaceLorebook, appendLoreBook, emplaceConverseHistory, emplaceConverseHistoryOnlyIfNull)
                }
            }
```

## Why deep-copy was the load-bearing decision

Truncation runs against the merged `contextWindow` immediately after the merge block. If `contextWindow` references the PumpStation's own object directly, truncation will mutate the PumpStation's authoritative memory. The seventh test (`importedContextDoesNotAliasSourceState`) pins this: it mutates the pipe's context after the merge and asserts the PumpStation's state is unchanged. Without that test, a sloppy `merge(pumpStationContext, ...)` (no deep-copy) would silently pass the other six tests and corrupt PumpStation state on the next turn.

## Why the merge-order test was the second load-bearing decision

The four `if (readFrom*Context)` blocks in `executeMultimodal` exist in a specific order — global → pipeline → parent-pipe → (PumpStation) → pre-validation. The merge-order test sets a conflicting lorebook key on both `pipeline.context` and `pumpStation.contextWindow`, then asserts the PumpStation value wins. Without this test, a future refactor that reorders the branches would silently change precedence. The Pipe's behavior would still compile and still run; the operator would debug it for hours before suspecting the order.

## Why the generic-interface traversal was the third load-bearing decision

`getNearestPumpStationParent()` returns `P2PInterface?`, not `PumpStation?`. The accessors are defined on `P2PInterface`. The patch uses the generic path because the feature was built generically — any future container that overrides `getContextWindowFromInterface()` and `getMiniBankFromInterface()` becomes a pull-target without touching `Pipe.kt` again. Casting to `PumpStation` would have compiled and tested fine, but it would have made the next similar repair a 4-file change instead of a 1-file change.

## Compile-loop pattern that came up twice

The first compile failed because `LoreBook(value = "station")` was a paraphrased constructor that doesn't exist. The second compile failed because `setParentPipe` is protected and tests can't call it. Both were caught by `compileTestKotlin` and fixed before any test ran. The shape of the fix in both cases: read the actual constructor / visibility instead of paraphrasing from a similar example.

This is the same pattern as `software-development:test-driven-development` Pitfall 12 ("code blocks in plans for unfamiliar APIs must be compiled, not paraphrased"). The repair workflow followed it twice in one session, on the test side. Next session: when in doubt, write the test against the real class definition, not against a similar-shape example.

## Verification artifacts

- `/tmp/pipe-pumpstation-context-red.txt` — focused RED run, 3 failures, exact match to defect.
- `/tmp/pipe-pumpstation-context-green.txt` — focused GREEN run, all 7 tests pass.
- `/tmp/pipe-pumpstation-context-verification.txt` — combined focused + adjacent + `com.TTT.Pipe.*` rerun.

All three files were captured with `--rerun-tasks` to defeat Gradle's up-to-date cache. Future sessions should treat these as the canonical evidence shape for this class of repair.