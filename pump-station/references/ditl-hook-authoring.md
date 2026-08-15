# DITL Hook Authoring on PathObject (and the TPipe Class-Ownership Trap)

Source: 2026-07-22 TPipe session. Scope: adding `outputCaptureFunction` DITL hook to
`com.TTT.Pipeline.PathObject` and the standalone `pathObject { }` DSL.

## The Hook Shape (verified pattern)

A DITL hook on a TPipe container is a nullable `var`, `suspend (T) -> Unit`, marked
`@kotlinx.serialization.Transient`. The setter returns `this` for chaining. The
invocation site is `?.invoke(...)` immediately before the `return` statement on
every success path. Every TPipe class that implements hooks follows this shape
(see `Pipe.finalCaptureFunction` for the canonical example).

```kotlin
// In the class body
@kotlinx.serialization.Transient
var outputCaptureFunction: (suspend (content: MultimodalContent) -> Unit)? = null

// Builder setter
fun setOutputCaptureFunction(func: suspend (content: MultimodalContent) -> Unit): PathObject
{
    outputCaptureFunction = func
    return this
}

// Invocation — IMMEDIATELY before each `return <var>` statement, NOT
// inside the expression. If the return is `return expr.foo()`, you need
// to wrap: `val captured = expr.foo(); capture?.invoke(captured); return captured`.
captureFunction?.invoke(capturedResult)
return capturedResult
```

The existing DITL hooks on `Pipe` are the canonical reference: `Pipe.kt:1503`
(`postGenerateFunction`), `:1510` (`validatorFunction`), `:1524`
(`transformationFunction`), `:1531` (`onFailure`). `Pipe.finalCaptureFunction`
was added in the same session, at `Pipe.kt:1537`, with invocations at the
six `return@coroutineScope` sites in `executeMultimodal` (lines 6619-6892).
`PathObject.outputCaptureFunction` mirrors this exactly.

## The Trap: which `executeLocal` are you patching?

This is the load-bearing lesson of the 2026-07-22 session. **`PathObject` has
only `execute()`, not `executeLocal()`.** `PumpStation` has `executeLocal()`. Both
classes are in `Pipeline/PumpStation.kt`. When you `grep` for "executeLocal"
you find exactly one match — and it is `PumpStation.executeLocal()` at line 2129
(file:line citations verified at session time).

The temptation is to assume "PathObject inherits `executeLocal` from
`P2PInterface`, so it must have one" and patch the line you find. The
compiler will catch this as `Unresolved reference 'outputCaptureFunction'`
because `outputCaptureFunction` is a field on `PathObject`, not `PumpStation`.

### Verification recipe (mandatory before patching)

Before wiring a DITL hook on any TPipe class, run the 3-call probe:

```bash
# 1. Locate the class
grep -n "class <Name>" src/main/kotlin/Pipeline/PumpStation.kt

# 2. Find the brace boundary of the class (Python helper)
python3 -c "
src = open('src/main/kotlin/Pipeline/PumpStation.kt').read()
lines = src.split('\n')
depth = 0
in_class = False
for i, line in enumerate(lines, 1):
    if f'class <Name>(' in line:
        in_class = True
        print(f'line {i}: <Name> opens')
    if in_class:
        for c in line:
            if c == '{': depth += 1
            elif c == '}': depth -= 1
        if depth == 0 and in_class and i > <start_line>:
            print(f'line {i}: <Name> closes')
            break
"

# 3. Within that brace scope, enumerate the methods you intend to patch
grep -nE "override suspend fun (execute|executeLocal|executeP2PRequest)" \
  src/main/kotlin/Pipeline/PumpStation.kt
# CONFIRM each match falls inside the class brace scope from step 2
```

If a method you'd expect to find is missing, the class probably inherits it
from its interface and does NOT override. Don't patch the inherited
override site — there isn't one. Patch the override that DOES exist (or
add the override if you genuinely need a hook on the inherited path).

### What `PathObject` actually has

```kotlin
class PathObject(...) : P2PInterface {
    // Direct override — real method on the class, brace scope covers it
    internal suspend fun execute(
        content: MultimodalContent,
        station: PumpStation,
        turnHistory: ConverseHistory?,
        turnSummary: String
    ): MultimodalContent   // ← 4-priority dispatch lives here

    // NO override of executeLocal — inherits P2PInterface default, which
    // is never actually called by the harness loop. The harness calls
    // PathObject.execute(...) directly via PathObject.invokePath(...).
}
```

The four-priority dispatch in `execute()` (PCP, executionFunction, internalAgent,
agentBuilderFunction) is the actual surface that fires when the harness invokes
a path. `executeLocal` is the inherited P2PInterface default, which is never
called from production paths. **Any DITL hook on a path's outgoing content must
fire from inside `execute()`, not `executeLocal()`.**

### Other class-ownership traps in the same file

`PumpStation.kt` contains BOTH `PathObject` and `PumpStation` (plus a few nested
helpers). The `executeLocal` at line 2129 is `PumpStation.executeLocal`, NOT
`PathObject.executeLocal`. The `outputCaptureFunction` field is on `PathObject`,
NOT `PumpStation`. Always verify which class owns the method you're patching by
running the 3-call probe above.

There is also an `executeP2PRequest` override on `PumpStation` (around line
2113) which delegates to `executeLocal`. It is part of `PumpStation`, not
`PathObject`. Same trap class.

## The TDD Discipline That Catches This

The third-party-class-API-paraphrasing pitfall from `interactive-plan` SKILL
warns about this pattern. The fix discipline that actually catches it in
practice is TDD with a real Gradle compile:

1. Write the test FIRST. Tests that exercise the DSL surface (entry-point
   invocation, setter delegation, end-to-end execute on the new path) will
   compile-fail with `Unresolved reference 'outputCaptureFunction'` if the
   field is patched in the wrong class.
2. Run `./gradlew :test --tests "<your new test class>"`. The compile
   error tells you immediately which class scope the field belongs in.
3. Fix the patch (revert the wrong-class insertion, find the right class).
4. Re-run. Green.

The TDD loop catches the bug in 2 minutes. The plan-time 3-call probe
prevents it. Do both — the probe prevents the bug, the TDD catches any
class-ownership mistake the probe missed.

## The Standalone `pathObject { }` DSL Pattern (verified 2026-07-22)

PathObject now has its own standalone DSL, mirroring the dual
`pumpStation(name, block)` / `pumpStationBuilder(name)` entry-point pattern.

### Class shape

`PathBuilder` is a `@PumpStationDslMarker`-annotated class with the same setters
as the nested `PathBlock`. The `build()` method returns the constructed
`PathObject`. There is no parent-builder reference — the standalone DSL is
fully decoupled from `PumpStationBuilder`.

### Entry points

```kotlin
// Single-call: build and return the PathObject
fun pathObject(pathName: String, block: PathBuilder.() -> Unit): PathObject

// Factory: staged construction (set properties, then call build())
fun pathObjectBuilder(pathName: String): PathBuilder
```

`pathObjectBuilder` does NOT accept a block. Use property assignment on
the returned builder, then `.build()`. This is different from
`pumpStationBuilder` which does accept a block — test files that assumed
both factories were block-style will fail to compile.

### Test fixture recipe (verified)

The new test file at `src/test/kotlin/Pipeline/PathObjectStandaloneDslTest.kt`
demonstrates the full test pattern for the standalone DSL. The 18 tests
cover:

- Group A (3): `pathObject()` entry — name round-trip, attachable to a
  `PumpStation` via `addPath()`, default state with empty block
- Group B (3): `pathObjectBuilder()` factory — name round-trip, configuration
  round-trip, idempotent `build()` returns same `PathObject` instance
- Group C (6): setter delegation — description, risk, runsInBackground,
  suppressHistoryEmit, schema, pathMetadata
- Group D (2): setInternalAgent + setExecutionFunction delegation
- Group E (3): setOutputCaptureFunction — both on standalone builder and
  on nested `PathBlock`, plus independence check
- Group F (1): end-to-end execute — `PathObject.execute(input, station, null, "")`
  runs the configured `executionFunction` and returns the result

### Required precondition for `pumpStation("...") { path("...") { ... } }`

`PumpStationBuilder.build()` at `PumpStationDsl.kt:1072` requires
`dispatchAgent` to be set AND be a `Pipeline`. Any test using the nested
DSL must include `dispatchAgent = Pipeline()` inside the `pumpStation { }`
block. Without it, `require(dispatchAgent != null) { "dispatchAgent is required" }`
throws `IllegalArgumentException`. The existing pattern is documented in
`PumpStationDslParityTest.kt` and `references/container-embedding-and-shims.md`
section "Where Lambda Adapters Actually Exist".

## File:Line Citations (verified at 2026-07-22 session time)

- `PathObject` class declaration: `Pipeline/PumpStation.kt:246`
- `outputCaptureFunction` field: `Pipeline/PumpStation.kt:339`
- `setOutputCaptureFunction` builder setter: `Pipeline/PumpStation.kt:578`
- 4 invocation sites in `PathObject.execute()`: `Pipeline/PumpStation.kt:635,
  651, 660, 671`
- `PathObject.execute()` 4-priority dispatch: `Pipeline/PumpStation.kt:616-672`
- `PumpStation.executeLocal()` (NOT a PathObject site): `Pipeline/PumpStation.kt:2129`
- `PathBuilder` class: `Pipeline/PumpStationDsl.kt:1462`
- `pathObject()` entry point: `Pipeline/PumpStationDsl.kt:1952`
- `pathObjectBuilder()` factory: `Pipeline/PumpStationDsl.kt:1969`
- `PathBlock.setOutputCaptureFunction` helper: `Pipeline/PumpStationDsl.kt:1582`
- `PumpStationBuilder.build()` dispatchAgent require: `Pipeline/PumpStationDsl.kt:1072`
- New test class: `src/test/kotlin/Pipeline/PathObjectStandaloneDslTest.kt` (18 tests)

## Run Recipe for DITL Hook Test Sweeps

```bash
# Focused subset (the new test class + adjacent PumpStationPath* baseline)
./gradlew :test \
  --tests "com.TTT.Pipeline.PathObjectStandaloneDslTest" \
  --tests "com.TTT.Pipeline.PumpStationPath*" \
  2>&1 | tee /tmp/hermes-verify-<feature>-<date>.txt

# Parse the JUnit XML reports for per-class summary
python3 -c "
import os, re
d = 'build/test-results/test/'
total_t = total_f = total_e = 0
for f in sorted(os.listdir(d)):
    if any(p in f for p in ['PathObjectStandaloneDslTest', 'PumpStationPath']):
        x = open(f'{d}{f}').read()
        t = int(re.search(r'tests=\"(\d+)\"', x).group(1))
        fl = int(re.search(r'failures=\"(\d+)\"', x).group(1))
        er = int(re.search(r'errors=\"(\d+)\"', x).group(1))
        print(f'{f.split(chr(0x54)+chr(0x45)+chr(0x53)+chr(0x54)+\"-\")[1].split(\".xml\")[0]:65s} tests={t} fail={fl} err={er}')
        total_t += t; total_f += fl; total_e += er
print(f'TOTAL tests={total_t} fail={total_f} err={total_e}')
"
```

The `:test UP-TO-DATE` cache is valid signal — if Gradle says UP-TO-DATE,
the test JVM was reused from a prior green run. The XML reports under
`build/test-results/test/` are the authoritative pass/fail counts.

## Generalization Beyond PathObject

Same recipe applies to any future DITL hook on:

- `Pipe` — `executeMultimodal` has 6 `return@coroutineScope` sites
  (see `Pipe.finalCaptureFunction` for the canonical pattern)
- `Manifold`, `Junction`, `DistributionGrid` — `executeLocal` is
  inherited from `P2PInterface` and IS overridden on each. Verify
  with the 3-call probe before patching.
- `Pipeline` — `executeLocal` IS overridden (it's the no-op default
  for a Pipeline that just runs its pipes in order). Hook fires here.

The trap is most acute when the file contains MULTIPLE classes that
implement the same interface (`Pipeline/PumpStation.kt` has 4 such
classes: `PathObject`, `PumpStation`, plus some nested helpers). The
3-call probe + TDD discipline is the only reliable defense.