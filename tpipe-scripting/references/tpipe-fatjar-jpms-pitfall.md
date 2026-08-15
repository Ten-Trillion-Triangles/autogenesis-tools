---
name: tpipe-fatjar-jpms-pitfall
description: Runtime failure mode when running `BasicJvmScriptingHost` against the `tpipe-<v>-all.jar` fat-jar — Kotlin scripting compiler treats embedded JARs' Automatic-Module-Name entries as a JPMS module path, leading to "Symbol is declared in module X which does not export package Y" errors and unresolved stdlib/`kotlinx-coroutines` references. Captured 2026-06-29 mid-investigation; Variants 6 + 7 confirm the full chain can be fixed in-script.
---

# Fat-jar + `BasicJvmScriptingHost` → JPMS module-path interference

The `tpipe-<v>-all.jar` ShadowJar task (see `tpipe-fatjar-build-wiring.md`) bundles 47,000+ files including every transitive JAR. When `BasicJvmScriptingHost` evaluates a script from inside the fat-jar via `--script foo.kts`, the Kotlin scripting compiler treats each embedded JAR as a Java module (reading `Automatic-Module-Name` from `META-INF/MANIFEST.MF`, or `module-info.class` if present) and constructs a **synthetic module graph**. That graph misassigns packages between unrelated modules and breaks stdlib resolution at the same time.

## Reproducer

```bash
# Pre-conditions:
# - branch tpipe-scripting checked out
# - fatJar built via: ./gradlew fatJar --offline (produces build/libs/TPipe-<v>-all.jar)
# - scripts/smoke-test-dummy.kts exists (DummyPipe + Pipeline + runBlocking)

java -jar build/libs/TPipe-<v>-all.jar --script scripts/smoke-test-dummy.kts
```

## Observed errors (verbatim, 2026-06-29)

Two distinct error categories fire simultaneously at first:

**Category 1 — stdlib symbols unresolved despite being on the fat-jar classpath:**

```
ERROR: Unresolved reference 'runBlocking'.
ERROR: Unresolved reference 'println'.
ERROR: Unresolved reference 'require'.
```

`runBlocking` lives in `kotlinx-coroutines-core` — present in the fat-jar. `println` and `require` are `kotlin.*` stdlib — also present. The compiler is reporting them as if the classpath were empty.

**Category 2 — inter-package JPMS rejection error:**

```
ERROR: Symbol is declared in module 'io.github.oshai.kotlinlogging' which does not
       export package 'com.TTT.Pipe'.
ERROR: Symbol is declared in module 'io.github.oshai.kotlinlogging' which does not
       export package 'com.TTT.Pipeline'.
```

The `kotlinlogging` JAR's `Automatic-Module-Name` (or `module-info.class` it embeds) claims modules whose `com.TTT.*` packages it does NOT actually contain — the compiler is mis-attributing `com.TTT.Pipe` and `com.TTT.Pipeline` to whichever JAR came first alphabetically, or to whichever JAR was loaded as the synthetic-module root.

The script-host wrapper then prints its own pre-amble at the top of every compile:

```
DEBUG: Using JDK home inferred from java.home: /home/cage/.sdkman/candidates/java/24.0.2-graalce
DEBUG: Loading modules: [java.se, jdk.attach, ..., kotlin.stdlib, kotlin.script.runtime,
                         kotlin.reflect, ...]
DEBUG: Loading modules: [java.se, jdk.attach, ..., kotlin.stdlib, ...]   # printed TWICE
```

The "Loading modules" duplication is `BasicJvmScriptingHost.evalWithTemplate<T>` doing TWO compile passes — one for the `@KotlinScript`-annotated template class, one for the actual script. Both fail the same way.

## Root cause

`BasicJvmScriptingHost` builds the script compiler invocation with BOTH the classpath AND the module path populated from the same source — `scriptCompilationClasspathFromContext(wholeClasspath = true)` returns every classpath entry as a JAR, and the compiler then ALSO reads each JAR's module manifest. When the JAR graph is a fat-jar:

1. Many embedded JARs have `Automatic-Module-Name` (e.g. `io.github.oshai:kotlinlogging-jvm:7.0.0` registers itself as module `io.github.oshai.kotlinlogging`).
2. The compiler assigns packages by JAR appearance order, not by actual class location.
3. `com.TTT.Pipe.*` classes are physically inside the fat-jar (Shadowed IN), but the compiler "claims" them for whichever module's auto-name is alphabetically nearby in the manifest list.
4. Once a package is claimed by a module, that module's `exports` clause must include it. Most JARs do not export `com.TTT.*`, so the compiler rejects usage.
5. Stdlib jars (kotlin-stdlib, kotlinx-coroutines-core-jvm) get the same treatment — they DO have `Automatic-Module-Name` set to `kotlin.stdlib` / `kotlinx.coroutines.core`, but the classpath-vs-modulepath resolution order means they're interpreted as "module" rather than "classpath", and `runBlocking` becomes cross-module inaccessible.

This is NOT specific to fat-jars containing TPipe — it's a property of shadow-plugin fat-jars containing JARs with `Automatic-Module-Name` entries. A `gradle shadowJar` artifact that bundles 50+ libs (which shadow-built TPipe does — Ktor, kotlinx-coroutines, kotlin-logging, log4j-slf4j-impl, jackson, etc.) will hit it.

**Specifically TPipe-relevant root-cause note:** `io.github.oshai:kotlin-logging-jvm:7.x` is the JAR whose `module-info` the compiler picks as the "module root" because its name sorts first alphabetically and it ships a complete `module-info.class`. Older (pre-7.x) kotlin-logging versions used Automatic-Module-Name only and were less aggressive at hijacking. **Downgrading kotlin-logging-jvm to 6.x is a real Variant 6.1 mitigation if Variants 6+7 are too invasive for your codebase** — the rest of the script-host wiring doesn't care.

## Workaround status — seven variants investigated, Variant 7 fixes the stdlib/coroutines blocker

### Variant 1 — `JvmDependency(classpath, isOnClasspath = true)` flag
The `JvmDependency` class has an `isOnClasspath: Boolean = false` flag that explicitly tells the compiler "this dependency belongs to the classpath, NOT the module path." If set, the compiler skips JPMS resolution for that entry.

```kotlin
dependencies.append(JvmDependency(classpath, isOnClasspath = true))
```

**Status: INVALID for Kotlin scripting 2.2.20.** Decompiled `JvmDependency.class` shows only `(List<File>)` and `(File...)` constructors — no boolean flag exists. The flag was removed (or only exists in older versions). Verify on `javap -p JvmDependency.class` against your actual `kotlin-scripting-jvm-2.x.jar`; do NOT trust docs alone.

### Variant 2 — extract fat-jar to a directory; use the directory as classpath
Workaround: at startup, extract the fat-jar into a temp directory and pass that as the classpath.

**Status: DOES NOT FIX THE SYMPTOM.** `kotlin.script.experimental.jvm.util.isValidClasspathFile`'s `validClasspathFilesExtensions` whitelist is `.jar` and `.zip` only. Plain directories are silently dropped from the compiler's classpath, even if every `.class` is there. No diagnostic; the symptom is just "symbols unresolved" with no pointer to the root cause. Most expensive variant to debug because of the silent drop. Required precursor step to Variant 6 (you re-zip the directory back into a JAR).

### Variant 3 — explicit `@KotlinScript` template WITHOUT fat-jar contents
If the `@KotlinScript`-annotated template class is on the regular classpath (not in the fat-jar), and the template declares only `dependenciesFromCurrentContext` (no synthetic module graph), this may bypass the issue.

**Status: HIGH ARCHITECTURAL COST. Likely unneeded if Variant 6 works.**

### Variant 4 — `BasicJvmScriptingHost.getEnvironment().addClasspath(...)` instead of `dependencies`
Some Kotlin scripting versions support an out-of-band API to add to the host's CLASSPATH environment variable directly.

**Status: METHOD DOES NOT EXIST on `BasicJvmScriptingHost` in 2.2.20.** Verify via `javap -p BasicJvmScriptingHost.class`; only `evalWithTemplate` and the JvmScriptCompiler-private accessor exist. Not usable.

### Variant 5 — disable `--add-modules ALL-MODULE-PATH` JVM flag
The Kotlin scripting compiler reads `--add-modules` from the JVM args.

**Status: NOT THE RIGHT LEVER.** `java -jar foo.jar` does NOT pass `--add-modules` by default. The compiler is constructing the module path from classpath entries it discovers, not from JVM args. Disabling the flag doesn't change that.

### Variant 6 — UNPACK + STRIP MODULE-INFO + RE-ZIP INTO A FRESH JAR (fixes the JPMS hijack)

One-time setup at object initialization, costs ~1-2s on cold start for a 92MB fat-jar. Sidesteps the JPMS hijack by producing a `.jar` file (whitelist-acceptable) that contains NO `module-info.class` (no JPMS module graph constructed).

```kotlin
object TPipeScriptCompilationConfiguration : ScriptCompilationConfiguration({
    defaultImports.append(
        "kotlin.*",
        "kotlinx.coroutines.*",
        "com.TTT.*",
        // ... other TPipe subpackage imports ...
    )
    val repackagedJar = repackageFatJarWithoutModuleInfo()
    dependencies.append(JvmDependency(listOf(repackagedJar)))
})

// Top-level helpers — companion objects aren't reachable from the
// static-initializer lambda of an `object : ScriptCompilationConfiguration(...)` parent.
private fun repackageFatJarWithoutModuleInfo(): java.io.File {
    val klass = TPipeScriptCompilationConfiguration::class.java
    val selfJar = java.io.File(klass.protectionDomain.codeSource.location.toURI())
    val tmpRoot = java.io.File(System.getProperty("java.io.tmpdir")).toPath()
    val scratch = java.nio.file.Files.createTempDirectory(tmpRoot, "tpipe-scripting-").toFile()
    // DO NOT call scratch.deleteOnExit() — see "tmpfs inode trap" below
    unpackZip(selfJar, scratch)
    scratch.walkTopDown().filter { it.isFile && it.name.endsWith(".jar") }.forEach { nested ->
        unpackZip(nested, scratch)
        nested.delete()
    }
    val repackaged = java.io.File(tmpRoot.toFile(), "tpipe-scripting-classpath-${ProcessHandle.current().pid()}.jar")
    // DO NOT call repackaged.deleteOnExit() — see "tmpfs inode trap" below
    java.util.zip.ZipOutputStream(repackaged.outputStream().buffered()).use { zout ->
        scratch.walkTopDown().filter { it.isFile }.forEach { file ->
            val relPath = file.relativeTo(scratch).invariantSeparatorsPath
            zout.putNextEntry(java.util.zip.ZipEntry(relPath))
            file.inputStream().use { it.copyTo(zout) }
            zout.closeEntry()
        }
    }
    return repackaged
}

private fun unpackZip(zip: java.io.File, dest: java.io.File) {
    val moduleInfoRegex = Regex("META-INF/versions/\\\\d+/module-info\\\\.class")
    java.util.zip.ZipInputStream(zip.inputStream().buffered()).use { zin ->
        var entry = zin.nextEntry
        while (entry != null) {
            val name = entry.name
            val isModuleInfo = name == "module-info.class" || moduleInfoRegex.matches(name)
            // The load-bearing skip: no module-info means no JPMS hijack.
            if (!entry.isDirectory && !isModuleInfo) {
                val outFile = java.io.File(dest, name)
                outFile.parentFile.mkdirs()
                if (outFile.exists()) outFile.delete()
                outFile.outputStream().use { zin.copyTo(it) }
            }
            entry = zin.nextEntry
        }
    }
}
```

**Why it works:**

1. **Strips every `module-info.class`** — root entry plus multi-release variants under `META-INF/versions/N/`. Without ANY `module-info.class` on the classpath, the K2 compiler cannot construct a synthetic module graph and falls back to flat-classpath mode.
2. **Re-zips as `.jar`** — `isValidClasspathFile` is whitelist-only on `.jar` and `.zip`; directories are silently dropped even if every `.class` is there.
3. **Single classpath entry** — the repackaged JAR is one file in the dependency list, so the compiler doesn't have to walk module manifests for nested jars.

**Subordinate pieces that matter:**

- **Stripping multi-release module-info is required, not optional.** `kotlinx-coroutines-core-jvm-1.8.x.jar` ships `META-INF/versions/9/module-info.class` naming itself `kotlinx.coroutines.core`. Leave that in, the compiler constructs a module graph and tries to enforce its `exports` clause, which still rejects `com.TTT.*`.
- **`defaultImports.append(...)` BEFORE `dependencies.append(JvmDependency(...))` is required.** Both go into the same builder; the second must NOT clobber the first.
- **`companion object` is invalid inside a top-level Kotlin `object` parent.** If helpers live in `companion object { fun repackage...() }`, the parent object's static-init lambda cannot reach them. Top-level `private fun`s in the same file work.

**KDoc trap that costs a rebuild:** A `*/` inside a Kotlin `/** ... */` KDoc comment terminates the comment prematurely. Mentions like `META-INF/versions/*/module-info.class` MUST avoid the literal `*/` sequence. The Kotlin compiler error is `Syntax error: Unclosed comment` at the END of the file (well after the offending line) — the comment terminator it sees is well above the EOF it's complaining about, so the wrong line gets blamed. Workarounds:

- Rephrase as `META-INF/versions/N/module-info.class` (digit placeholder).
- Put the literal in a code block or string literal so the lexer reads it as content.

### Variant 7 — DISABLE BUNDLED STDLIB + ADD EXPLICIT DEPS (fixes the stdlib/coroutines blocker)

After Variant 6, the script compiler successfully indexes the repackaged fat-jar's contents for `com.TTT.*` symbols but still reports `kotlin.io.println`, `kotlin.require`, `kotlinx.coroutines.runBlocking` as "Unresolved reference." That's because the script-compiler bundle (`kotlin-scripting-jvm-host` 2.2.20) ships its OWN bundled `kotlin-stdlib`, `kotlin-script-runtime`, `kotlin-reflect` JARs (resolved via `kotlin.script.experimental.jvm.util.KotlinJars.stdlib` etc.), loads them as JPMS modules, and routes symbol resolution through them. The user-classpath JARs are searched only after the bundled modulepath fails — and the bundled modulepath fails because the script declares no `kotlin.io.println` usage pattern that matches the bundled `ConsoleKt`'s `internal` accessibility.

**Fix in three lines** — disable the bundled auto-load and inject matching JARs from the Gradle cache as explicit `JvmDependency` classpath entries. The script compiler then has no implicit stdlib and uses user-supplied dependencies only.

```kotlin
object TPipeScriptCompilationConfiguration : ScriptCompilationConfiguration({
    defaultImports.append(
        "kotlin.*",
        "kotlinx.coroutines.*",
        "com.TTT.*",
        // ... other TPipe subpackage imports ...
    )
    // Disable the script compiler's bundled stdlib/script-runtime/reflect.
    // Without this, symbols like kotlin.io.println resolve only against the
    // bundled module (java.base path) and bypass user classpath entirely.
    compilerOptions.append("-no-stdlib", "-no-reflect")
    val repackagedJar = repackageFatJarWithoutModuleInfo()
    val extraJars = locateExtraScriptClasspathJars()
    dependencies.append(JvmDependency(listOf(repackagedJar) + extraJars))
})

/**
 * Locate the kotlin-stdlib and kotlinx-coroutines-core-jvm JARs in the
 * Gradle cache (~/.gradle/caches/modules-2/files-2.1/). These are added
 * to the script compiler's classpath as EXTRA JvmDependency entries —
 * the repackaged fat-jar already contains every class, but the script
 * compiler's symbol resolution prefers explicit classpath entries over
 * the bundled modulepath jars (see Variant 7 description above).
 *
 * The Graceful-Degradation contract: if any lookup fails, return empty
 * list. The repackaged JAR is still on the classpath so call sites
 * that already worked (DummyPipe + Pipeline round-trip, Pipe access)
 * continue to work; only stdlib/coroutines symbol resolution
 * degrades.
 */
private fun locateExtraScriptClasspathJars(): List<java.io.File> {
    val candidates = mutableListOf<java.io.File>()
    val gradleCache = java.io.File(
        System.getProperty("user.home"),
        ".gradle/caches/modules-2/files-2.1"
    )
    val stdlib = java.io.File(gradleCache, "org.jetbrains.kotlin/kotlin-stdlib/2.2.20")
        .walkTopDown()
        .firstOrNull { it.isFile && it.name == "kotlin-stdlib-2.2.20.jar" }
    if (stdlib != null) candidates.add(stdlib)

    val coroutines = java.io.File(gradleCache, "org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm")
        .walkTopDown()
        .firstOrNull { it.isFile && it.name.endsWith(".jar") && !it.name.contains("sources") }
    if (coroutines != null) candidates.add(coroutines)
    return candidates
}
```

**Why it works in detail:**

The Kotlin scripting compiler's `compilationContext.kt:296-305` constructs the script classpath with this shape:

```kotlin
scriptCompilationConfiguration[ScriptCompilationConfiguration.dependencies]?.let { dependencies ->
    addJvmClasspathRoots(
        dependencies.flatMap {
            (it as? JvmDependency)?.classpath ?: emptyList()
        }
    )
}
// ... later, unconditionally:
if (!baseArguments.noStdlib) {
    addModularRootIfNotNull(isModularJava, "kotlin.stdlib", KotlinJars.stdlib)
    addModularRootIfNotNull(isModularJava, "kotlin.script.runtime", KotlinJars.scriptRuntimeOrNull)
}
if (!baseArguments.noReflect && !baseArguments.noStdlib) {
    addModularRootIfNotNull(isModularJava, "kotlin.reflect", KotlinJars.reflectOrNull)
}
```

The compiler **separates** the classpath (user deps) from the module-path (bundled stdlib/reflect/script-runtime). Symbols on the modulepath take priority because the `KotlinJars`-bundled JARs are loaded as actual JPMS modules — `kotlin.io.ConsoleKt` IS in `kotlin.stdlib` module, so the symbol IS visible to the compiler at resolve time, but the compiler's symbol table for `kotlin.io.println` points to the bundled module's view of the package, NOT the user classpath's. The user's classpath gets `ConsoleKt` indexed but the compiled-script target sees only the bundled one.

By passing `compilerOptions = ["-no-stdlib", "-no-reflect"]`, the bundle is disabled and the compiler has no implicit stdlib. Adding the same stdlib JAR explicitly via `JvmDependency(classpath)` puts it on the classpath, and the script compiler resolves symbols through the classpath-first path: `addJvmClasspathRoots(listOf(repackagedJar, stdlibJar, coroutinesJar))`.

**Where `KotlinJars.stdlib` comes from (verified by `javap` on `kotlin-scripting-jvm-2.2.20.jar`):**

```java
public final class kotlin.script.experimental.jvm.util.KotlinJars {
    public final java.io.File getStdlib();
    public final java.io.File getReflectOrNull();
    public final java.io.File getScriptRuntimeOrNull();
    // ... delegates cached lazily on first read
}
```

The class lazy-resolves from the surrounding classloader's `getResource()` calls — that's why `System.setProperty("kotlin.java.stdlib.jar", somePath)` is a partial workaround (forces eager resolution) but does NOT actually win the resolution race in 2.2.20; the bundled JARs are pinned by the compiler bundle itself.

**Verified after Variant 7 (2026-06-29):**

```bash
java -jar build/libs/TPipe-1.0.0-all.jar --script scripts/smoke-test-dummy.kts
# OUTPUT:
# RESULT: hello from tpipe-script-host
# smoke-test-dummy: PASS
# Unit
```

The script compiler now resolves `kotlin.io.println`, `kotlin.require`, `kotlin.String.isNotEmpty`, `kotlinx.coroutines.runBlocking` correctly. The fat-jar + `BasicJvmScriptingHost` combination works end-to-end. Tasks 8-14 of the implementation plan are unblocked.

## tmpfs inode-exhaustion trap (`deleteOnExit()` on large file trees)

`java.io.File.deleteOnExit()` registers the file to be deleted on normal JVM termination. The hook list is maintained in memory during the JVM's lifetime, but on tmpfs filesystems (the default for `/tmp` on most Linux containers including this sandbox), the registration also adds to the filesystem's in-memory inode tracking. After several script invocations, the kernel's tmpfs inode table fills up.

**Symptom:** A script invocation that was working fine starts failing with `java.nio.file.FileSystemException: /tmp/tpipe-scripting-XXXXXXXXX: No space left on device` — even though `df -h /tmp` shows 23G free. The real failure is `df -i /tmp` showing 100% inode usage with thousands of leftover `tpipe-scripting-*` scratch directories.

**Why it bites in this script-host context specifically:** `repackageFatJarWithoutModuleInfo` writes ~45,000 files into the scratch temp directory (each unpacked class plus each unpacked nested-jar entry). Calling `scratch.deleteOnExit()` on the parent AND `repackaged.deleteOnExit()` on the zip adds each subdirectory and each file to the delete hook. Across multiple script invocations, the in-memory list survives until JVM exit — but on tmpfs, the FS-level "should I remove this on shutdown?" tracking also accumulates.

**Fix:** Do NOT call `deleteOnExit()` on either the scratch directory or the repackaged JAR. Let them persist on disk; the JVM is short-lived (single-shot script run, exit) and OS temp-rotation cleans up old `/tmp/tpipe-scripting-*` directories eventually. Concretely:

```kotlin
val scratch = java.nio.file.Files.createTempDirectory(tmpRoot, "tpipe-scripting-").toFile()
// NO scratch.deleteOnExit() — see "tmpfs inode trap"
val repackaged = java.io.File(tmpRoot.toFile(), "tpipe-scripting-classpath-${pid}.jar")
// NO repackaged.deleteOnExit() — see "tmpfs inode trap"
```

If you do hit the inode-exhaustion state in a sandbox, recovery is one command: `rm -rf /tmp/tpipe-scripting-*`. Verify with `df -i /tmp` before declaring the build broken — the `No space left on device` error is misleading because tmpfs is fs-type-dependent for that check.

## Verified status (2026-06-29, all blockers resolved)

| Claim | Evidence |
|---|---|