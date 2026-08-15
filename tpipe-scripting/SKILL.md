---
name: tpipe-scripting
description: "Authoring external scripts that consume TPipe — .kts scripts, REPL sessions, coding-agent runs — without rebuilding TPipe as a Gradle hard-dep. Load when wiring BasicJvmScriptingHost against the published TPipe jar, when adding a --script / --repl flag to com.TTT.Application, when exposing P2P/PCP/Pipeline/Pipe/MultimodalContent APIs to script authors, when wiring @file:DependsOn for CodeArtifact-published TPipe modules, or when verifying a script host can reach TPipe's public surface (Pipe is abstract — DummyPipe is the no-API smoke-test stand-in). NOT for consuming TPipe from inside a Kotlin/Gradle project (use tpipe-pipeline-patterns); NOT for TPipe publishing (use aws-codeartifact-publishing); NOT for executing scripts FROM TPipe via PCP (use tpipe-pcp-code-execution — opposite direction)."
version: 0.6.0
author: Hermes Agent + Apex
license: MIT
metadata:
  tpipe:
    tags: [tpipe, scripting, kotlin-scripting, jsr-223, repl, host, kotlin-main, coding-agent]
    homepage: https://github.com/ten-trillion-triangles/TPipe
trigger: "When adding or designing a script-host entry point for the published TPipe artifact (--script flag, REPL loop, script-coding-agent integration), OR when external code wants to consume TPipe APIs (.kts script, JVM REPL, embedded scripting) without rebuilding TPipe as a Gradle dependency."
changelog:
  - |
    0.6.0 (2026-06-29): Adds references/tpipe-repl-state-retention-recipe.md — the working JvmReplCompiler + JvmReplEvaluator wiring recipe for state-retaining REPL inside the TPipe fat-jar. v0.5.0 corrected the cost framing on REPL state retention ("the blocker is engineering, not bytes") but did not include the actual working code shape. The user pushed back when the deferred REPL surfaced as a user-flagged seriousness: "since that one sounds like a fairly serious issue. I need to understand what exactly the problem is with it." This update closes the gap the v0.5.0 cost-correction identified. Three load-bearing contract points documented: (1) `state` must be a `var` re-used across eval() calls (the retention mechanism IS the persistent state holder); (2) `ScriptCompilationConfiguration` needs a `repl { makeSnippetIdentifier { _, id -> id.toString() } }` block — without it the second eval() throws; (3) the fat-jar classpath must include `kotlin-scripting-compiler-impl-embeddable` (already transitively present, but the dep is load-bearing — if removed during cleanup the REPL classes stop resolving). Companion to tpipe-fatjar-empirical-classpath-check.md — both recipes must be applied together: the cost-framing check confirms reachability, this file shows the wiring.
  - |
    0.5.0 (2026-06-29): User-correction patch. The REPL state-retention deferral cost in v0.4.0 was overstated. Empirically verified: `JvmReplCompiler` + `JvmReplEvaluator` are already loadable from the fat-jar because `kotlin-scripting-compiler-impl-embeddable` brings `org.jetbrains.kotlin.cli.common.repl.*` in transitively as part of the Variant 7 workaround. Real blockers for switching are `org.jetbrains.kotlin.scripting.compiler.plugin.impl.*` namespace instability + `ScriptCompilationConfiguration.repl.makeSnippetIdentifier` configuration + `IReplStageState` lifetime management — engineering cost, not bytes. Adds a new pitfall: "Don't fudge commit/revert messages to justify deferring a workaround under feature-pressure" — when the empirical investigation contradicts a previous claim, correct the prior claim with evidence (in this same skill AND in the next commit message) before shipping the deferral. Adds a cheap empirical verification recipe (5 commands) for confirming whether any class is loadable from the fat-jar before claiming a classpath blocker.
  - |
    0.4.0 (2026-06-29): Major update to references/tpipe-fatjar-jpms-pitfall.md. The "next blocker" (stdlib/coroutines visibility) is now RESOLVED via Variant 7 (commit 1c235cfe on tpipe-scripting branch). Variant 7 sets `compilerOptions = [-no-stdlib, -no-reflect]` to disable the script compiler's bundled stdlib/script-runtime/reflect jars, then explicitly injects `kotlin-stdlib-2.2.20.jar` + `kotlinx-coroutines-core-jvm-*.jar` from the Gradle cache via `locateExtraScriptClasspathJars()`. Replaces the "Open verification checklist" with a "Resolved" section. Adds three new traps discovered this session: (1) the tmpfs `deleteOnExit()` inode-exhaustion trap — registering 45k+ files from an unpacked fat-jar with `deleteOnExit()` exhausts tmpfs inodes after ~10 script invocations and breaks subsequent runs with `FileSystemException: No space left on device`; do NOT register scratch directories or repackaged JARs with `deleteOnExit()`; (2) the `kotlin-logging 7.x` Automatic-Module-Name root-cause — kotlin-logging-jvm 7.x is the JAR whose module-info the compiler picks because its name sorts first/last; documented as Variant 6.1; (3) the `*/` KDoc terminator trap (already in v0.3.0 but reinforced). Also adds a new session-warning note: --repl state retention is a 2.2.20 limitation — `BasicJvmScriptingHost` recompiles each snippet in isolation, so top-level `val`s do NOT persist across stdin lines. True REPL state requires `JvmReplCompiler`+`JvmReplEvaluator` from `org.jetbrains.kotlin.cli.common.repl` in `kotlin-compiler-embeddable`, which is impractical to ship in a fat-jar for end users.
  - |
    0.3.0 (2026-06-29): Major update to references/tpipe-fatjar-jpms-pitfall.md. Adds Variant 6 (unpack + strip module-info + re-zip), the actual fix that landed in commit f2657eb3 on the tpipe-scripting branch. Marks Variants 1-5 with decompiled-API verification — Variant 1's `isOnClasspath` flag does NOT exist in Kotlin scripting 2.2.20, Variant 4's `getEnvironment().addClasspath` does NOT exist either. Adds three new sub-section traps: the directory-silently-dropped trap (`isValidClasspathFile` whitelist), the multi-release `META-INF/versions/N/module-info.class` strip requirement, and the `*/` KDoc comment termination trap. Adds the next-blocker diagnostic recipe and open verification checklist (stdlib/coroutines visibility was still unresolved at session end — Tasks 8-14 blocked on it). Companion to the existing `tpipe-fatjar-build-wiring.md` (BUILD side; this is RUNTIME side).
  - |
    0.2.0 (2026-06-29): Adds references/tpipe-fatjar-jpms-pitfall.md — the JPMS module-path failure mode that fires when BasicJvmScriptingHost compiles scripts from inside the `<v>-all.jar` ShadowJar artifact. Symptom: "Unresolved reference 'runBlocking'" + "Symbol is declared in module X which does not export package Y". Root cause: shadow plugin bundles 47k files including Automatic-Module-Name manifests; Kotlin scripting compiler treats them as a JPMS module path and misassigns packages. Five workaround variants enumerated (Variant 1 is the single-line `JvmDependency(isOnClasspath = true)` fix; cheapest first). Companion to the existing `tpipe-fatjar-build-wiring.md` (which covers the BUILD side; this covers the RUNTIME side).
  - |
    0.1.0 (2026-06-29): Initial extraction from the TPipe-script-access research session. Captures the surface inventory findings, the 4 runtime patterns (A/B/C/D), and the recommended Pattern A (embedded JSR-223 host via scripting-jsr223 + scripting-jvm-host, both already on the published classpath). References: references/tpipe-public-surface.md (the verified import graph and concrete Pipe subclass table).
---

# TPipe Scripting Access

TPipe the library is a Kotlin/JVM artifact published to CodeArtifact as `com.github.ten-trillion-triangles:TPipe:<v>`. Letting an external **script author** (a `.kts` file, a coding agent, a REPL session, a runtime-eval setup) consume TPipe without rebuilding it as a Gradle hard-dep is a separate problem from using TPipe from inside a Kotlin project. That separation is the gap this skill fills.

## The rule

**Concrete `Pipe` subclasses are non-core. Scripts default to `DummyPipe` for smoke tests and `@file:DependsOn` provider modules for real LLM work.**

## Verified status (2026-06-29, all blockers resolved)

| Claim | Evidence |
|---|---|
| The fat-jar is being treated as a JPMS module path | The "Loading modules: [...]" debug lines at the start of every compile output (Kotlin scripting compiler-internal log). |
| JARs with `Automatic-Module-Name` are the cause | The `kotlinlogging` misassignment error explicitly cites a module name from a manifest, not anything in the source. |
| Directories are rejected as classpath entries | `kotlin.script.experimental.jvm.util.isValidClasspathFile`'s `validClasspathFilesExtensions` whitelist is only `.jar` and `.zip`. No diagnostic; directories are silently dropped. |
| Variant 6 (re-zip) fixes the JPMS hijack | `java -jar build/libs/TPipe-1.0.0-all.jar --script scripts/smoke-test-dummy.kts` no longer produces "Symbol is declared in module X which does not export package Y" errors. `com.TTT.*` symbols resolve via `import com.TTT.Pipe.DummyPipe` etc. Verified at commit `f2657eb3`. |
| Variant 7 (-no-stdlib + explicit deps) fixes stdlib/coroutines visibility | `kotlin.io.println`, `kotlin.require`, `kotlinx.coroutines.runBlocking` all resolve. Smoke test prints `smoke-test-dummy: PASS`. Verified at commit `1c235cfe`. |
| The "No space left on device" error during re-zip is inode exhaustion, NOT disk space | `df -h /tmp` shows 23G free; `df -i /tmp` shows 100% inode usage. Recovery: `rm -rf /tmp/tpipe-scripting-*`. |
| The `KotlinJars` system-property override (`-Dkotlin.java.stdlib.jar=...`) does NOT win the resolution race | Verified in-session by passing the property at JVM startup; the script compiler still loads bundled `kotlin.stdlib` from its internal JAR. Variant 7's `compilerOptions = ["-no-stdlib"]` is the lever that actually works. |

## Diagnostic recipe (cheap → expensive) — for any FUTURE regression

When a `tpipe-<v>-all.jar --script foo.kts` invocation fails compilation, work through this list:

1. **Confirm shadow bundled everything you expect:**
   ```bash
   unzip -l build/libs/TPipe-<v>-all.jar | grep -E "kotlin-stdlib|kotlinx-coroutines|kotlinlogging|Pipe\\.class"
   ```
   All four should match. If `Pipe.class` doesn't, the ShadowJar config missed `sourceSets.main.get().output`.

2. **Confirm fat-jar isn't corrupt:**
   ```bash
   file build/libs/TPipe-<v>-all.jar
   unzip -t build/libs/TPipe-<v>-all.jar | tail -5
   ```
   `unzip -t` runs CRC checks on every entry. A prior interrupted build can leave a corrupt (truncated) jar that LOOKS valid but fails on first read. Confirmed in this session: a 14MB truncated "shadow jar" at `build/libs/TPipe-1.0.0-all.jar` had a missing End-of-central-directory record; `unzip` rejected it as "End-of-central-directory signature not found." A fresh `./gradlew fatJar` rebuild restored a valid 92MB jar.

3. **Check tmpfs inodes BEFORE assuming "disk full":**
   ```bash
   df -h /tmp    # if 0 available, disk IS full
   df -i /tmp    # if 100% used, tmpfs inode exhaustion — clean up /tmp/<your-temp-pattern>/*
   ```
   Critical when error text says "No space left on device" but `df -h` shows free space.

4. **Confirm the repackaged JAR is being indexed:**
   Add a temporary diagnostic line inside `repackageFatJarWithoutModuleInfo` early in the function:
   ```kotlin
   System.err.println("[Scripting] repackaged jar: ${repackaged.absolutePath} (${repackaged.length()} bytes)")
   ```
   Run the smoke test and confirm the line prints BEFORE the first `ERROR:` line. Without this, you're debugging blind — the failure manifests only as "ERROR:" lines that don't distinguish "JAR wasn't built" from "JAR was built but the compiler didn't pick it up."

5. **Run with a no-imports trivial script** to isolate the issue:
   ```kotlin
   println("hello from kts")
   ```
   If THIS fails with "Unresolved reference 'println'", you're in stdlib-visibility territory (Variant 7 territory). If it fails with "Symbol is declared in module X", you're in JPMS-hijack territory (Variant 6 territory). If it passes, the bug is in your specific imports, not the host.

6. **Inspect the classpath the JVM script compiler sees at compile time.** Look for `JVM_REPL_PROBE`-style hooks in `BasicJvmScriptingHostKt.createJvmCompilationConfigurationFromTemplate` if any; otherwise dump `System.getProperty("java.class.path")` from a temporary init block in the host.

7. **Try a different launch path:**
   ```bash
   unzip -q build/libs/TPipe-<v>-all.jar -d /tmp/tpipe-extract
   java -cp '/tmp/tpipe-extract:/tmp/tpipe-extract/classes' \
        -Dkotlin.script.classpath.use.classpath=true \
        com.TTT.ApplicationKt --script scripts/smoke-test-dummy.kts
   ```
   If this works, the issue is genuinely JPMS-from-jar; if it doesn't, the issue is unrelated.

## File paths referenced

- `src/main/kotlin/Config/Scripting.kt` — `TPipeScriptCompilationConfiguration` object, the `repackageFatJarWithoutModuleInfo()` helper, the `defaultImports.append(...)` block, the `compilerOptions.append("-no-stdlib", "-no-reflect")` line, the `locateExtraScriptClasspathJars()` helper.
- `build.gradle.kts` — `fatJar` ShadowJar task in root project
- `scripts/smoke-test-dummy.kts` — smoke test that now prints `smoke-test-dummy: PASS`

## Resolution log (chronological)

This file tracks the chain of fixes in the order they landed on the `tpipe-scripting` branch:

1. **2026-06-29 — Variant 6 lands (commit `f2657eb3`)**: unpack + strip + re-zip. Fixes the JPMS hijack; all `com.TTT.*` symbols become resolvable. Unblocks Tasks 1-7.
2. **2026-06-29 — `--no-stdlib` system-property attempt fails (no commit)**: passes `-Dkotlin.java.stdlib.jar` at JVM startup, observed the script compiler STILL loads bundled stdlib via `KotlinJars.getExplicitLib` returning the bundled JAR's classloader resource. Property override is not strong enough to redirect.
3. **2026-06-29 — Variant 7 lands (commit `1c235cfe`)**: `compilerOptions.append("-no-stdlib", "-no-reflect")` + `locateExtraScriptClasspathJars()` adds explicit `kotlin-stdlib-2.2.20.jar` + `kotlinx-coroutines-core-jvm-*.jar` from Gradle cache. Smoke test prints `smoke-test-dummy: PASS`. Unblocks Tasks 8-14 minus the live API call (Task 10).
4. **2026-06-29 — tmpfs inode trap discovery (commit `1c235cfe` same)**: removing `deleteOnExit()` calls from scratch dir and repackaged JAR restored stable operation across multiple script invocations.
5. **2026-06-29 — REPL state retention deferred (commit `a90fad0a`)**: `BasicJvmScriptingHost` does not retain top-level `val`s across `eval()` calls in 2.2.20. Documented as a limitation in KDoc; user-facing text in README reflects "use `--script <file>` for cross-line state."

The full chain (`release of Variants 6+7`) makes `--script` + `--repl` (single-line) + `--stdio-script-loop` all functional. Live LLM verification (Task 10) requires a `MINIMAX_API_KEY` env var and was not run end-to-end in this session.

## Anti-pattern observed in the search history

A previous version of this file (pre-Variant 6) listed Variant 1 as the recommended first attempt and did NOT include the decompiled-API verification ("does the flag actually exist?"). That was a documentation error, not just an outdated note: a future agent reading this file would have wasted a debugging cycle attempting `JvmDependency(classpath, isOnClasspath = true)` against 2.2.20. **The lesson — when documenting a workaround as "may work," verify the API exists by `javap` against the actual jar before publishing the note. Hypothesized is not verified; say which.**

The same anti-pattern applied to the `KotlinJars` system-property workaround (Documented in the "Open verification checklist" of v0.3.0 as a potential fix; verified in v0.4.0 as ineffective). Future agents: do NOT skip the verification step.
| `DummyPipe` | core (no LLM) | `com.github.ten-trillion-triangles:TPipe:<v>` |
| `BedrockPipe` | TPipe-Bedrock | `com.github.ten-trillion-triangles:TPipe-Bedrock:<v>` |
| `BedrockMultimodalPipe` | TPipe-Bedrock | same |
| `NovaPipe`, `NovaCanvasPipe` | TPipe-Bedrock | same |
| `OllamaPipe` | TPipe-Ollama | `com.github.ten-trillion-triangles:TPipe-Ollama:<v>` |

(See `references/tpipe-public-surface.md` for the full import-map and the builder-method surface.)

## What's already on the classpath (you don't need to add deps)

`build.gradle.kts:75-76` already declares:
```kotlin
implementation(kotlin("scripting-jsr223"))
implementation(kotlin("scripting-jvm-host"))
```
These ship **inside the published TPipe artifact**, not just inside the TPipe project. Pattern A below uses them as-is. Verify `kotlin-reflect` is transitively pulled before assuming it always will be — at the time of writing, `scripting-jvm-host` brings it in.

## Runtime patterns (ranked, with recommendation)

### Pattern A — embedded JSR-223 host with `kotlin-main` script type (RECOMMENDED)

Wire a `--script <file.kts>` flag into `com.TTT.Application` (alongside the existing `--http`, `--stdio-loop`, `--mcp-http`, etc. flags in `Application.kt`). The handler:

```kotlin
val engine = ScriptEngineManager().getEngineByExtension("kts")
val host   = BasicJvmScriptingHost()                       // fallback
val result = engine.eval(scriptSource, ScriptRequest(
    compilationClasspath = currentClasspath(),             // TPipe + provider jars
    defaultImports       = listOf(
        "com.TTT.Pipe.*",
        "com.TTT.Pipeline.*",
        "com.TTT.Context.*",
        "com.TTT.P2P.*",
        "com.TTT.PipeContextProtocol.*",
        "com.TTT.Enums.*",
        "com.TTT.Util.*"
    ),
    properties           = mapOf("tpipe.version" to TPipe_VERSION),
    hostConfiguration    = JvmScriptingHostConfiguration().jvm {
        extractFromClasspath = true                        // reflect on TPipe classes
    }
))
```

The script author writes something like:

```kotlin
import com.TTT.Pipe.DummyPipe
import com.TTT.Pipeline.manifold

val pipe = DummyPipe().setSystemPrompt("You are an analyst.")
println(runBlocking { pipe.execute("summarize: $args") })
```

Pros:
- Uses libraries already on the published classpath.
- `BasicJvmScriptingHost` handles incremental compile, class caching, dependency closure.
- Author experience is "write `.kts`, run it" — same model as the user's stated coding-agent use case.
- Trivially extendable to REPL (`--repl` mode) by mirroring `PcpStdioHost.runLoop()`.

Cons / work to add:
- A `@file:DependsOn` resolver wired to CodeArtifact so scripts can pull `TPipe-Bedrock` / `TPipe-Ollama` by Maven coord.
- Verify `kotlin-reflect` is on the runtime classpath (`./gradlew dependencies :script-runtime` smoke-test).
- A fat-jar shadow config so authors don't rebuild classpath themselves when running the published artifact (`alias(libs.plugins.shadow)` is already declared).

### Pattern B — standalone CLI wrapper `tpipe-script`

Thin shell launcher that resolves the published TPipe jar from CodeArtifact at install time and pipes `script.kts` into Pattern A's JSR-223 host. Zero core change.

Pros: clean separation.
Cons: two processes, harder to ship `--repl` from the same binary as the existing `Application.kt`.

### Pattern C — extend `PcpStdioHost.runLoop()` to accept inline-script RPC requests

Distributed agents on other TPipe nodes can ask *this* node to execute a script. Useful for the coding-agent-with-many-nodes case.

Pros: reuses existing stdio protocol.
Cons: trust model explodes — script-bearing remote requests are equivalent to `ssh + bash`. Needs per-message signing. Pattern A and C are probably best as siblings (A for `--script` CLI, C stays gated behind auth).

### Pattern D — compile-and-spawn child JVM

`kotlinc -script`, drop fat classpath, capture stdout/stderr.

Pros: works even if Pattern A hits a wall.
Cons: no incremental compile, no REPL, slow cold-start. Skip unless A is blocked.

## Recommended rollout

1. Pattern A as the canonical entry point. Touches: `build.gradle.kts` (fat-jar shadow config), `Application.kt` (dispatch), a new `ScriptHost.kt` (engine bootstrap), and an `@file:DependsOn` resolver. ~200 LOC + tests.
2. Default-import a curated TPipe prelude so authors don't import 30 names by hand (the list above).
3. Verify with `DummyPipe` end-to-end before any provider integration — proves the host works without external services.
4. Pattern C only if the coding agent genuinely needs cross-node script exec — otherwise defer.

## The `Application.kt` dispatch site to extend

Current shape (verified 2026-06-29 from `src/main/kotlin/com/TTT/Application.kt`):

```kotlin
fun main(args: Array<String>) {
    if(args.isEmpty() || args.contains("--http") || args.contains("--remote-memory")) {
        embeddedServer(Netty, port = 8080, host = "0.0.0.0", module = Application::module).start(wait = true)
    }
    else if(args.contains("--stdio-once"))  { P2PStdioHost.runOnce() }
    else if(args.contains("--stdio-loop"))  { P2PStdioHost.runLoop()  }
    // ... --pcp-stdio-*, --mcp-stdio-*, --mcp-http, --mcp-bridge-* ...
}
```

Add a new branch for `--script <file.kts>` and `--repl`. Mirror `PcpStdioHost.runLoop()` for the REPL (stdin line in → execute → stdout line out).

## Open questions to resolve before implementation

- Should scripts be able to access `BedrockPipe`/`OllamaPipe`, or only `DummyPipe` + user-supplied subclasses? Default-restrict to core; let scripts `@file:DependsOn` the provider jars they need.
- Should `tpipe-script` be the same binary as `tpipe-server` with subcommands, or separate? Same binary is simpler and matches `Application.kt`'s current dispatch style.
- Hot-reload: `BasicJvmScriptingHost` already caches compiled classes by content hash + classpath hash. Standard behavior, no extra work.
- Versioning: pin the TPipe version script authors see to the same version as the host jar; document escape hatch via `kotlinx-script-definitions`.

## Verification pre-implementation

Verify before implementation — these are the move-blocking gaps from the 2026-06-29 research session:

1. `BasicJvmScriptingHost` resolver API at Kotlin 2.2.20 — minor breaking changes across 2.x; check the API surface for the version TPipe compiles against.
2. Whether `kotlin-reflect` is transitively pulled at runtime. Run `./gradlew dependencies` on a `:script-runtime` smoke module.
3. End-to-end `DummyPipe.setMultimodalInput(MultimodalContent("hello")).execute(content)` round-trip without external services. The class is `Pipe() { override fun generateText(...) = promptInjector }` (`src/main/kotlin/Pipe/DummyPipe.kt:14`), so `generateText` is pure pass-through — but the harness calls other lifecycle methods (`truncateModuleContext` is also overridden to `this`) and the full path through `execute().await()` was not traced.
4. Provider-jar wiring for `BedrockPipe`/`OllamaPipe` from scripts — needs `@file:DependsOn` coordination through CodeArtifact credentials (`CODEARTIFACT_AUTH_TOKEN` env var at script runtime, matches the existing `publishing { ... }` block in `build.gradle.kts`).

## Anti-patterns

- **Don't ship `script-host` as a separate process.** `--script` belongs in `Application.kt` next to `--http` and `--mcp-http` so there's one binary per TPipe install.
- **Don't ship `--repl` without state carry-over between invocations.** Either persistent interpreter state (compile once, evaluate many times) or admit it's session-mode-only and document clearly.
- **Don't expose `Pipe` as directly constructible.** Scripts MUST use concrete subclasses (`DummyPipe` for smoke, provider subclasses for real). If `Pipe()` is needed, the right move is a constructor with sensible defaults (`BedrockPipe(...).init()` chain), not unabstracting the base class.
- **Don't run scripts through the agent dispatcher by accident.** Pattern C requires explicit opt-in (per-message signed envelope). Don't route `--script` traffic through `P2PStdioHost.runLoop()` — it's the wrong protocol and the wrong trust boundary.
- **Don't use default-imports in scripts.** The 2026-06-29 design session deliberately chose `import com.TTT.*` explicit imports over auto-importing 30 namespaces. See the "Import policy" pitfall below for the rationale.
- **Don't fudge commit/revert messages to justify deferring a workaround under feature-pressure.** When the empirical investigation contradicts a previous claim (cost framing, classpath availability, runtime behavior), the previous claim must be corrected with evidence — in the SAME skill, in the same branch, IN THE NEXT COMMIT MESSAGE. The 2026-06-29 REPL-deferral commit (`a90fad0a`) said `kotlin-compiler-embeddable` "isn't on the standard kotlin-scripting user classpath" — that was empirically wrong (it's transitively in the fat-jar via Variant 7's build dep), and the overstated cost framing stuck around until the user called it out. The user has direct visibility into why a workaround was deferred, and inflated cost framing makes the deferral look strategic when it was actually triage. **When deferring, write what is empirically true; the user will trust future deferrals more, not less.**
- **Don't claim a classpath blocker without a 5-command empirical check.** Before stating "class X isn't on the classpath" in a commit, PR, or skill, run: `unzip -l build/libs/TPipe-<v>-all.jar | grep "<class-or-package-substring>"`, then `unzip -p build/libs/TPipe-<v>-all.jar <path-to-class> | head -c 8 | xxd` (verify it's a valid `.class` and not a 14-byte truncated stub), then `find ~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<version>/ -name "*-sources.jar"` (the sources jar proves the class is reachable from a known-public API surface, not just bundled). If all three return matches, the class IS on the runtime classpath. If a fourth `javap -p` against the class shows the constructor signature you expect, the API is reachable. Five-command verification is cheaper than a wrong "can't reach it" deferral.

## Import policy: explicit `import com.TTT.*`, no default imports

The skill's Pattern A originally recommended `defaultImports = listOf("com.TTT.Pipe.*", "com.TTT.Pipeline.*", ...)`. The 2026-06-29 design session rejected that approach at the Phase 2 gate. Reasons:

1. **Diagnostic clarity.** When a script breaks at runtime with `Unresolved reference: DummyPipe`, an agent author immediately knows the import is missing. With default imports, that error mode becomes "where did `DummyPipe` come from?" — slower debugging.
2. **No surprise surface.** Default imports silently expose `com.TTT.Debug.*` and `com.TTT.Util.*` (operator-internal namespaces). Explicit imports force authors to learn the public API.
3. **Composable with authoring tools.** Coding agents that generate `.kts` files don't need to second-guess what's already in scope — they emit fully explicit code.

Do NOT change this back. If a future session argues for default imports, push back with the diagnostic-clarity case above and ask the user to re-decide.

## Build wiring: opt-in `fatJar` task with `fatJarImplementation` configuration

The cleanest way to expose the full TPipe surface to a Kotlin script host without contaminating the published `com.github.ten-trillion-triangles:TPipe:<v>` jar is an opt-in `fatJar` task using a dedicated configuration that extends `implementation`:

```kotlin
// build.gradle.kts (root project)
val fatJarImplementation: Configuration by configurations.getting {
    extendsFrom(configurations.getByName("implementation"))
    isCanBeConsumed = false
    isCanBeResolved = false
}

dependencies {
    fatJarImplementation(project(":TPipe-Bedrock"))
    fatJarImplementation(project(":TPipe-Ollama"))
    fatJarImplementation(project(":TPipe-OpenRouter"))
    fatJarImplementation(project(":TPipe-GenericOpenAI"))
    fatJarImplementation(project(":TPipe-Defaults"))
    fatJarImplementation(project(":TPipe-Tuner"))
    fatJarImplementation(project(":TPipe-TraceServer"))
    fatJarImplementation(project(":TPipe-MCP"))
}

tasks.register<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("fatJar") {
    group = "build"
    archiveClassifier.set("all")
    archiveBaseName.set("TPipe")
    archiveVersion.set(project.version.toString())
    mergeServiceFiles()
    manifest { attributes["Main-Class"] = "com.TTT.ApplicationKt" }
    from(sourceSets.main.get().output)
    from(configurations.getByName("fatJarImplementation"))
    configurations = listOf(
        configurations.getByName("runtimeClasspath"),
        configurations.getByName("fatJarImplementation")
    )
    exclude("META-INF/*.kotlin_module")
}
```

The key trick: `fatJarImplementation` extends `implementation` (so it picks up `com.TTT.*` core) but is NOT added to `runtimeClasspath` or `archives`. The provider submodules are `fatJarImplementation(project(":TPipe-..."))`, NOT `implementation(project(":TPipe-..."))` — so they ship only in the fat-jar, never in the published TPipe artifact.

**Verify with this exact command sequence after wiring:**

```bash
./gradlew fatJar --offline                                              # produces build/libs/TPipe-<v>-all.jar
unzip -l build/libs/TPipe-<v>-all.jar | grep -c GenericOpenAIPipe        # > 0 (provider classes present)
./gradlew jar --offline
unzip -l build/libs/TPipe-<v>.jar | grep -c GenericOpenAIPipe             # 0 (provider classes ABSENT from regular jar)
```

If the second count is NOT zero, the provider submodules leaked into the regular jar. Stop and fix the dependency declarations before continuing — do not paper over with `shadowJar { exclude(...) }` retroactive fixes.

## Pitfall — Kotlin script compiler + shadow fat-jar = JPMS module-path interference

A fat-jar built by ShadowJar bundles 47,000+ files including every transitive JAR's `META-INF/MANIFEST.MF`. When `BasicJvmScriptingHost` evaluates a script from inside that fat-jar, the Kotlin scripting compiler reads each embedded JAR's `Automatic-Module-Name` and constructs a JPMS module graph. The result is two simultaneous error categories at script compile time:

```text
ERROR: Unresolved reference 'runBlocking'.          # kotlinx-coroutines-core is right there
ERROR: Unresolved reference 'println'.             # kotlin-stdlib is right there
ERROR: Symbol is declared in module 'io.github.oshai.kotlinlogging'
       which does not export package 'com.TTT.Pipe'.   # kotlinlogging claims our package
```

Full reproducer, root-cause analysis, and six ranked fix variants (Variant 6 — unpack + strip module-info + re-zip — is the one that lands; Variant 1's `JvmDependency(isOnClasspath = true)` flag **does NOT exist** in 2.2.20 and is a documented trap, not a fix) are documented in `references/tpipe-fatjar-jpms-pitfall.md`. **Read that file before the first `java -jar tpipe-<v>-all.jar --script foo.kts` smoke test**, otherwise you'll waste hours watching the compiler claim it can't see the classpath it just printed the size of. Three things in particular to read up on in that file:

- **The directory trap** — `isValidClasspathFile` only accepts `.jar` and `.zip` extensions. Plain directories are silently dropped from the compiler's classpath with no diagnostic, which is the second-most-easy thing to discover because the symptom just shifts to "still no symbols."
- **The multi-release module-info trap** — `kotlinx-coroutines-core-jvm-1.8.x.jar` ships `META-INF/versions/9/module-info.class` naming itself `kotlinx.coroutines.core`. The variant that fixes the JPMS hijack MUST also strip this entry, not just the root-level one.
- **The `*/` KDoc trap** — referencing `META-INF/versions/*/module-info.class` inside a Kotlin `/** ... */` block silently terminates the comment. Compiler error is `Syntax error: Unclosed comment` at EOF, well past the offending line.

As of the 2026-06-29 session, Variant 6 fixed the JPMS hijack but the script compiler's stdlib/coroutines visibility remains unresolved (see the "Open verification checklist" at the bottom of the reference file). Tasks 8-14 of the implementation plan are blocked on that follow-on.

## REPL state retention: a 2.2.20 limitation, not a bug

`BasicJvmScriptingHost.evalWithTemplate<T>(source)` recompiles each snippet in isolation. The compiled-script cache the host maintains is keyed by `(source-hash, classpath-hash)`, NOT by session lineage — calling `eval(snippetA)` followed by `eval(snippetB)` where `B` references a top-level `val` declared in `A` will return `Unresolved reference: <valName>`.

True REPL state retention requires the legacy `kotlin.script.experimental.jvmhost.repl.JvmReplCompiler` + `JvmReplEvaluator` pair from `kotlin-scripting-jvm-host` 2.2.20 (see `references/tpipe-fatjar-jpms-pitfall.md` for source-dive links). These classes depend on `org.jetbrains.kotlin.cli.common.repl.{IReplStageState, ReplCompiler, ReplEvaluator, ReplCodeLine, ReplCompileResult, ReplEvalResult}` from `kotlin-compiler-embeddable` 2.2.20 — they are NOT shipped via `kotlin-scripting-jvm-host` alone.

**Verified empirical fact (post-Deferral review, 2026-06-29):** when the decision to defer the true REPL was made and the `a90fad0a` commit message claimed `kotlin-compiler-embeddable` wasn't on the classpath, that claim turned out to be overstated. The fat-jar built on the `tpipe-scripting` branch DOES contain `org/jetbrains/kotlin/cli/common/repl/*.class` because the `-no-stdlib -no-reflect` workaround (Variant 7) pulls in `kotlin-scripting-compiler-impl-embeddable` as a build dep, which transitively bundles the `kotlin-compiler-embeddable` Repl types. The real blockers for using them are:

1. **Namespace instability.** `KJvmReplCompilerBase` and `K2ReplCompiler` live in `org.jetbrains.kotlin.scripting.compiler.plugin.impl.*` — JetBrains' `impl` namespace. These have changed signatures across Kotlin minor versions before. Wiring against them commits the script-host feature to track every Kotlin compiler bump.
2. **Configuration surface.** `JvmReplCompiler` requires `ScriptCompilationConfiguration.repl { makeSnippetIdentifier { ... } }` to be configured for stable line IDs across calls. `BasicJvmScriptingHost` doesn't need this; switching means configuring it.
3. **Lifecycle code.** `IReplStageState<JvmReplCompilerState>` is the persistent state holder passed between calls. It must outlive `eval()` but be safe across `ReplSession.close()` — that's lifecycle code, not config.

The 2026-06-29 decision: defer the true REPL, document the limitation in `ReplSession`'s KDoc, and steer users toward `--script <file>` for any work that needs cross-line state. Concrete user-facing text:

> The host exposes the full TPipe classpath with no host-level script timeouts. The `--repl` mode is single-line — each stdin line compiles in isolation; top-level `val`/`var` declarations do NOT persist across lines. For interactive sessions that need cross-line state, paste all lines into a single `.kts` file and run with `--script`.

If a future session argues for fixing the REPL state-retention limitation, the work is (revised, post-deferral-cost-correction):
1. Rewrite `ReplSession` to construct `JvmReplCompiler(TPipeScriptCompilationConfiguration)` + `JvmReplEvaluator(...)` and feed snippets via `ReplCodeLine` objects rather than `BasicJvmScriptingHost.evalWithTemplate`.
2. Configure `TPipeScriptCompilationConfiguration` with `repl { makeSnippetIdentifier { ... } }` for stable line IDs.
3. Manage `IReplStageState<JvmReplCompilerState>` lifecycle in `ReplSession` so state outlives a single `eval()` call but is released cleanly on `close()`.
4. Write a `--repl` regression test: feed `printf` input, assert `greeting` resolves across lines.
5. Pin Kotlin compiler-embeddable version compatibility — track Kotlin compiler minor bumps for `impl` namespace breaks.

NO additional fat-jar bytes are required — `kotlin-scripting-compiler-impl-embeddable` is already a build dep and the `org.jetbrains.kotlin.cli.common.repl.*` classes are already on the fat-jar classpath (verify with `unzip -l build/libs/TPipe-<v>-all.jar | grep "cli/common/repl"`). The cost of fixing the REPL is ENGINEERING, not bytes.

Pitfall to surface before attempting: the `org.jetbrains.kotlin.scripting.compiler.plugin.impl.*` types are explicitly marked as not-public API and have changed signatures across minor versions before. Pin the Kotlin compiler version used to develop and test the REPL wiring; do NOT assume the same wiring works across a single Kotlin minor-version bump.

## Scripts that need a live LLM: gate on the API key env var

The 2026-06-29 design session validated live testing against MiniMax API via `GenericOpenAIPipe`. The smoke test pattern that works:

```kotlin
// scripts/smoke-test-minimax.kts
val apiKey = System.getenv("MINIMAX_API_KEY")
    ?: throw IllegalStateException("MINIMAX_API_KEY env var required for this script")
GenericOpenAIEnv.setApiKey(apiKey)

val pipe = GenericOpenAIPipe()
    .setApiKey(GenericOpenAIEnv.resolveApiKey())
    .setBaseUrl("https://api.minimax.io/v1")
    .setApiMode(ApiMode.OpenAI)
    .setModel("MiniMax-M2.7")
    .setMaxTokens(256)
    .setTemperature(0.0)

val pipeline = Pipeline()
pipeline.add(pipe)
pipeline.init(true)

val result = pipeline.execute("hello")
println(result)
```

Mirrors `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/MiniMaxApiTest.kt:65-82`. Constants worth pinning: `MINIMAX_BASE_URL = "https://api.minimax.io/v1"`, `MINIMAX_MODEL = "MiniMax-M2.7"`, gated on `@EnabledIfEnvironmentVariable(named = "MINIMAX_API_KEY", matches = ".+")`.

## `--stdio-script-loop` JSON envelope (agent-tool surface)

The agent-tool entry point. One JSON envelope per line on stdin, one JSON response per eval on stdout. Mirrors `PcpStdioHost.runLoop()`'s shape exactly — if the protocol drifts later, change them together.

Wire format (per line):
```json
{"script": "<kts source as a JSON string>"}
```

Response format (one per eval):
```json
{"status": "ok|error", "result": <serialized value or null>, "error": "<message>"}
```

Concrete dispatcher shape (sits inside Application.kt's main-mode dispatch):

```kotlin
else if(args.contains("--stdio-script-loop")) {
    ReplSession().use { repl ->
        while(true) {
            val line = readLine() ?: break
            if(line.isBlank()) continue
            try {
                val envelope = com.TTT.Util.deserialize<Map<String, kotlinx.serialization.json.JsonElement>>(line)
                val script = envelope["script"]?.let {
                    (it as kotlinx.serialization.json.JsonPrimitive).content
                } ?: throw IllegalArgumentException("Missing 'script' field in envelope")
                val result = repl.eval(script)
                val response = if(result.isSuccess) {
                    """{"status":"ok","result":${com.TTT.Util.serialize(result.getOrNull())}}"""
                } else {
                    """{"status":"error","error":"${result.exceptionOrNull()?.message?.replace("\"", "\\\"")}"}"""
                }
                println(response)
            } catch(t: Throwable) {
                println("""{"status":"error","error":"${t.message?.replace("\"", "\\\"")}"}""")
            }
        }
    }
}
```

Pitfall: the `script` field is a string field that itself contains Java/Kotlin code with embedded `\n` and `"` characters. JSON-encode carefully; do not paste a multi-line script raw into the envelope field.

## Reference files

- `references/tpipe-public-surface.md` — verified import graph and concrete Pipe subclass table.
- `references/tpipe-fatjar-build-wiring.md` — complete `build.gradle.kts` snippet with the shadow plugin config plus the exact `unzip -l` verification commands.
- `references/tpipe-fatjar-jpms-pitfall.md` — **read this BEFORE running the first `--script foo.kts`** if the build produces a shadow fat-jar. Documents the JPMS module-path failure mode (Kotlin scripting compiler treats embedded JARs with `Automatic-Module-Name` as JPMS modules and misassigns packages across unrelated modules), the exact error strings to grep for, and five ranked workaround variants (Variant 1 — `JvmDependency(isOnClasspath = true)` — is the single-line cheap fix; verify it first before extracting the fat-jar).
- `references/tpipe-fatjar-empirical-classpath-check.md` — 5-command recipe + cost-framing grid for verifying whether any class is reachable from the fat-jar BEFORE claiming a classpath blocker in a deferral commit message. Use when about to write "package X isn't on classpath" — the user has direct visibility into why work was deferred, and inflated cost framing makes deferrals look strategic when they're actually triage.
- `references/tpipe-repl-state-retention-recipe.md` — working JvmReplCompiler + JvmReplEvaluator wiring recipe (kotlin-scripting 2.2.20). Use when fixing the "--repl state retention is a 2.2.20 limitation" deferral in this skill, when `val greeting = "hello"` doesn't persist across stdin lines, or when adding state-retaining REPL support to any kotlin-scripting-based host. Companion to the `tpipe-fatjar-empirical-classpath-check.md` recipe — both need to be applied together: the cost-framing check confirms `kotlin-compiler-impl-embeddable` is reachable, this file shows the wiring recipe.

## Related skills

- `tpipe-pipeline-patterns` — same APIs but from inside a Kotlin project with TPipe as a Gradle dep. Loaded for builder/DSL config patterns.
- `tpipe-pcp-code-execution` — *opposite direction*: executing scripts *from* TPipe agents via PCP. NOT for *authoring* scripts against TPipe.
- `tpipe-editions` — license/branch facts if a script needs to pull a specific TPipe tier (Community vs Startup).
- `aws-codeartifact-publishing` — the publish workflow that produces the artifact scripts will resolve.
- `kotlin-jvm-tui-runtime` — the interactive-shell pattern (slash commands, subshells). `--repl` mode for the script host borrows the `runLoop()` shape from this skill's territory.
