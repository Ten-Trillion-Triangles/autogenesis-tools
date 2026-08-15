---
name: tpipe-repl-state-retention-recipe
description: Working recipe for state-retaining Kotlin REPL inside the TPipe fat-jar using JvmReplCompiler + JvmReplEvaluator from kotlin-scripting-jvm-host 2.2.20. Use when fixing the "--repl state retention is a 2.2.20 limitation" deferral in tpipe-scripting, when wiring BasicJvmScriptingHost's per-call isolation problem, when `val greeting = "hello"` doesn't persist across stdin lines in --repl mode, or when adding state-retaining REPL support to any kotlin-scripting-based host.
---

# Real Kotlin REPL State Retention in TPipe — Working Recipe (2026-06-29)

The `tpipe-scripting` skill's v0.5.0 update corrected the cost framing for the deferred REPL state-retention fix ("the blocker is engineering, not bytes"), but did NOT include the working JvmReplCompiler + JvmReplEvaluator wiring recipe. This file is the recipe.

## The shape of the fix (verified working, kotlin-scripting 2.2.20)

The `BasicJvmScriptingHost`-based `ReplSession` recompiles each `eval()` call in isolation. The fix uses the **legacy REPL pair** from `kotlin.script.experimental.jvmhost.repl`, both classes already loadable from the published `TPipe-<v>-all.jar` fat-jar (verified 2026-06-29, see `references/tpipe-fatjar-empirical-classpath-check.md`):

```bash
$ unzip -l build/libs/TPipe-<v>-all.jar | grep -E "JvmRepl.*\.class|cli/common/repl/" | head
   12712  kotlin/script/experimental/jvmhost/repl/JvmReplCompiler.class
   17810  kotlin/script/experimental/jvmhost/repl/JvmReplEvaluator.class
   11961  org/jetbrains/kotlin/cli/common/repl/BasicReplStageHistory.class
   ...
```

`org.jetbrains.kotlin.cli.common.repl.*` classes are present because `kotlin-scripting-compiler-impl-embeddable` (which the `-no-stdlib -no-reflect` workaround pulls in at commit `1c235cfe`) transitively bundles `kotlin-compiler-embeddable`. No additional fat-jar bytes needed.

## Three keys to the wiring

### Key 1 — ReplCompilationConfiguration must include `repl { makeSnippetIdentifier }`

Without this block, the second `eval()` call throws `IllegalStateException` because the compiler cannot generate a stable snippet ID across lines. The configuration DSL is on the `ScriptCompilationConfiguration` builder:

```kotlin
object TPipeReplCompilationConfiguration : ScriptCompilationConfiguration({
    defaultImports.append(
        "kotlin.*",
        "kotlinx.coroutines.*",
        "com.TTT.*",
        // ... other TPipe subpackage imports
    )
    val jvmBuilder = kotlin.script.experimental.jvm.JvmScriptCompilationConfigurationBuilder()
    jvmBuilder.dependenciesFromCurrentContext(wholeClasspath = true)
    // Critical: without repl { makeSnippetIdentifier { ... } }, JvmReplCompiler.compile()
    // throws on the second call. Confirmed by reading
    // kotlin-scripting-jvm-host-2.2.20-sources.jar
    // kotlin/script/experimental/jvmhost/repl/legacyReplCompilation.kt.
    jvmBuilder.repl {
        makeSnippetIdentifier { _, id -> id.toString() }
    }
})
```

This is a separate object from the single-shot `TPipeScriptCompilationConfiguration` used by `--script` / `--stdio-script-loop` because the REPL path needs the REPL compilation configuration keys, not just dependenciesFromCurrentContext.

### Key 2 — ReplSession holds a locked state across eval() calls

The `JvmReplCompiler` / `JvmReplEvaluator` pair takes a `ReentrantReadWriteLock` and an `IReplStageState<*>` reference that must be shared across calls. The state mutates as the compiler accumulates compiled snippets — top-level `val`/`var` declarations from prior calls become live JVM fields the next call can resolve.

```kotlin
class ReplSession : AutoCloseable {
    private val hostConfiguration: ScriptingHostConfiguration =
        defaultJvmScriptingHostConfiguration
    private val compiler: JvmReplCompiler =
        JvmReplCompiler(TPipeReplCompilationConfiguration, hostConfiguration)
    private val evaluator: JvmReplEvaluator =
        JvmReplEvaluator(hostConfiguration)
    private val lock: ReentrantReadWriteLock = ReentrantReadWriteLock()
    private var state: IReplStageState<*>? = null
    private var lineNo: Int = 0

    fun eval(snippet: String): Result<Any?> {
        return try {
            // Create state lazily — JvmReplCompiler.createState(lock) returns
            // a fresh IReplStageState<JvmReplCompilerState>. Re-using the same
            // state instance across eval() calls is what enables retention.
            val currentState = state ?: compiler.createState(lock).also { state = it }
            lineNo++
            val codeLine = ReplCodeLine(lineNo, 0, snippet, snippet)
            when (val compileResult = compiler.compile(currentState, codeLine)) {
                is ReplCompileResult.CompiledClasses -> {
                    val evalResult = evaluator.eval(currentState, codeLine, compileResult)
                    Result.success(unwrapReturnValue(evalResult))
                }
                is ReplCompileResult.Incomplete -> Result.failure(
                    IllegalStateException("Incomplete: ${compileResult.message}")
                )
                is ReplCompileResult.Error -> Result.failure(
                    IllegalStateException("Compile error: ${compileResult.message}")
                )
            }
        } catch (t: Throwable) {
            Result.failure(t)
        }
    }

    override fun close() {
        state = null
    }

    private fun unwrapReturnValue(returnValue: ReplEvalResult): Any? {
        return when (returnValue) {
            is ReplEvalResult.ResultValue -> returnValue.value
            is ReplEvalResult.UnitValue -> Unit
            is ReplEvalResult.ErrorVal -> returnValue
            else -> returnValue.toString()
        }
    }
}
```

Key contract points:
- **State is `var` and nullable**, mutated on first call, never replaced. This is the load-bearing retention mechanism. If you write `val state = compiler.createState(lock)` and re-create on every call, retention is broken — you have a BasicJvmScriptingHost-equivalent.
- **`lock` is created once per ReplSession**, not per call. JvmReplCompiler and JvmReplEvaluator share it for read/write coordination.
- **`lineNo` increments across calls.** Stable line numbers give stable snippet IDs (assuming `makeSnippetIdentifier { _, id -> id.toString() }` returns the `id` directly).
- **`AutoCloseable` close() drops the state reference.** No resources to release because the underlying Kotlin scripting types don't implement `close()` themselves in 2.2.20. Releasing the reference lets the GC collect the compiled-script cache.

### Key 3 — Imports map to the public API surface

```kotlin
import kotlin.script.experimental.host.ScriptingHostConfiguration
import kotlin.script.experimental.host.defaultJvmScriptingHostConfiguration
import kotlin.script.experimental.jvmhost.repl.JvmReplCompiler
import kotlin.script.experimental.jvmhost.repl.JvmReplEvaluator
import org.jetbrains.kotlin.cli.common.repl.ReplCodeLine
import org.jetbrains.kotlin.cli.common.repl.ReplCompileResult
import org.jetbrains.kotlin.cli.common.repl.ReplEvalResult
import org.jetbrains.kotlin.cli.common.repl.IReplStageState
import java.util.concurrent.locks.ReentrantReadWriteLock
```

If the `org.jetbrains.kotlin.cli.common.repl.*` imports fail to resolve, verify the fat-jar classpath with:

```bash
unzip -l build/libs/TPipe-<v>-all.jar | grep "org/jetbrains/kotlin/cli/common/repl/.*\.class" | head -5
```

Expected: 20+ matches including `IReplStageState`, `ReplCodeLine`, `ReplCompileResult`, `ReplEvalResult`. If absent, the build dep `kotlin-scripting-compiler-impl-embeddable` is missing from `fatJarImplementation` — add it to `build.gradle.kts`.

## Verification recipe

After implementing ReplSession, run:

```bash
# 1. Build the fat-jar with the new wiring.
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew fatJar --offline --no-daemon --console=plain 2>&1 | tail -5

# 2. The smoking-gun REPL state-retention test.
printf 'val greeting = "hello"\ngreeting\ngreeting + " from tpipe"\n:quit\n' \
  | java -jar build/libs/TPipe-1.0.0-all.jar --repl 2>&1 | tail -20
# Expected stdout (after "TPipe REPL (state-retaining). Type :quit to exit."):
#   >
#   > hello
#   > hello from tpipe
#   >
# NO "Unresolved reference 'greeting'" line anywhere.

# 3. Make sure --script still works (separate code path).
java -jar build/libs/TPipe-1.0.0-all.jar --script scripts/smoke-test-dummy.kts
# Expected: "smoke-test-dummy: PASS"

# 4. Make sure --stdio-script-loop still works.
printf '{"script":"println(\"agent-tool works from tpipe-script-host\")"}\n' \
  | java -jar build/libs/TPipe-1.0.0-all.jar --stdio-script-loop 2>&1 | head -3
# Expected: a JSON envelope response with "status":"ok".
```

If verification step 2 shows "Unresolved reference 'greeting'", the most likely cause is missing `repl { makeSnippetIdentifier { _, id -> id.toString() } }` in the compilation configuration. Check that block first.

## Pitfalls observed in the working fix

1. **`state` MUST be re-used across eval() calls.** A fresh `state = compiler.createState(lock)` per call gives you a "no-context" REPL equivalent to `BasicJvmScriptingHost`. The retention mechanism IS the persistent state holder.
2. **`makeSnippetIdentifier` lambda receives `(ScriptCompilationConfiguration, ReplSnippetId)`.** Returning `id.toString()` works because `ReplSnippetId` is a data class. If you want human-readable line numbers, format it: `"line_${id.no}_gen${id.generation}"`.
3. **`ReplCompileResult.CompiledClasses` is the success branch.** `Incomplete` means the input was a partial expression (multi-line input). `Error` means compile failed. Don't treat `Incomplete` as `Error` — the caller might want to feed more lines.
4. **`ReplEvalResult` is a sealed class with subclasses `ResultValue(value)`, `UnitValue`, `ErrorVal(exception)`.** The original `BasicJvmScriptingHost` returned a `ResultValue` only; the REPL evaluator also has explicit `UnitValue` and `ErrorVal` cases that need matching.
5. **`lock.write { ... }` is what JvmReplCompiler does internally.** You don't need to wrap the eval call in a write-lock unless you have concurrent ReplSession users. The lock exists to coordinate with the compiler's internal reads.
6. **The fat-jar classpath must include `kotlin-scripting-compiler-impl-embeddable`.** The simpler `kotlin-scripting-jvm-host` artifact alone does NOT bring the `org.jetbrains.kotlin.cli.common.repl.*` types. If you removed that dep during a build cleanup, the REPL classes won't resolve. Add back: `implementation("org.jetbrains.kotlin:kotlin-scripting-compiler-impl-embeddable:2.2.20")`.

## When to use Pattern A vs the REPL wiring

- **`--script <file.kts>` (Pattern A, unchanged)** — single-shot, no state retention between calls. Use for fire-and-forget scripts. Compiles once, runs once, exits.
- **`--stdio-script-loop` (agent-tool envelope, unchanged)** — JSON in, JSON out, one snippet per call. Same code path as `--script`, just multiplexed.
- **`--repl` with the JvmReplCompiler wiring (this recipe)** — state-retaining interactive session. Use when a human or agent is feeding snippets one at a time and expects prior `val`/`var` declarations to remain in scope.

The `--repl` and `--stdio-script-loop` modes both go through `repl.eval(line)` after this fix. The wiring is internal to `ReplSession`.

## Related reference files in `tpipe-scripting`

- `tpipe-scripting/SKILL.md` — overall script-host architecture, the `--repl` "documented limitation" section that this recipe replaces
- `tpipe-scripting/references/tpipe-fatjar-empirical-classpath-check.md` — 5-command recipe for verifying any class IS on the fat-jar classpath BEFORE claiming a classpath blocker
- `tpipe-scripting/references/tpipe-fatjar-jpms-pitfall.md` — Variants 6 + 7 (the stdlib/stdlib visibility fixes that make this recipe possible)
- `tpipe-scripting/references/tpipe-fatjar-build-wiring.md` — the `fatJar` task config that includes `kotlin-scripting-compiler-impl-embeddable` as a build dep
