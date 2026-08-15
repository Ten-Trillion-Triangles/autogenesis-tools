---
name: tpipe-fatjar-build-wiring
description: Exact Gradle build configuration for the opt-in tpipe script-host fat-jar. Covers the dedicated `fatJarImplementation` configuration extending `implementation` (load-bearing trick), the ShadowJar task with manifest entry, and the verification recipe that proves provider classes are absent from the regular jar.
---

# tpipe-fatjar-build-wiring

The load-bearing trick for `java -jar tpipe-<v>-all.jar --script foo.kts` to expose provider classes (`BedrockPipe`, `OllamaPipe`, `GenericOpenAIPipe`) to script authors WITHOUT contaminating the published `com.github.ten-trillion-triangles:TPipe:<v>` artifact is a dedicated Gradle configuration.

## Why a dedicated configuration

Gradle's regular `implementation(project(":TPipe-Bedrock"))` puts the submodule into `runtimeClasspath`, which feeds BOTH the published jar AND the shadow fat-jar. The 2026-06-29 design session needed them to diverge:

- Published TPipe jar (`com.github.ten-trillion-triangles:TPipe:<v>`): **core only** — Agent OS, no provider implementations.
- Fat-jar (`TPipe-<v>-all.jar`): **everything** — core + all provider submodules, ready for `java -jar`.

Solution: a `fatJarImplementation` configuration that extends `implementation` (so it inherits `com.TTT.*` core) but does NOT participate in the regular `runtimeClasspath` or `archives` (so it doesn't leak into publishing).

## Full `build.gradle.kts` snippet (root project only)

```kotlin
// Add to existing imports at the top of build.gradle.kts
import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar

// Insert into the dependencies { } block (alongside existing testImplementation etc.)
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

// Append after the publishing { } block
tasks.register<ShadowJar>("fatJar") {
    group = "build"
    description = "Bundles core + provider submodules into TPipe-<v>-all.jar for script-host mode."
    archiveClassifier.set("all")
    archiveBaseName.set("TPipe")
    archiveVersion.set(project.version.toString())
    mergeServiceFiles()
    manifest {
        attributes["Main-Class"] = "com.TTT.ApplicationKt"
    }
    from(sourceSets.main.get().output)
    from(configurations.getByName("fatJarImplementation"))
    configurations = listOf(
        configurations.getByName("runtimeClasspath"),
        configurations.getByName("fatJarImplementation")
    )
    exclude("META-INF/*.kotlin_module")
}
```

## Why each piece matters

| Configuration knob | Purpose |
|---|---|
| `extendsFrom(configurations.getByName("implementation"))` | `fatJarImplementation` inherits core `com.TTT.*` deps so the JVM script host can resolve `Pipe`, `Pipeline`, etc. |
| `isCanBeConsumed = false` | Submodule `runtimeElements` won't expose the configuration to consumers (we don't need the fat-jar pulled downstream as a dep). |
| `isCanBeResolved = false` | It's a one-way declare-only configuration; resolution will fail if anyone tries `configurations.fatJarImplementation.resolve()`. |
| `mergeServiceFiles()` | Combines `META-INF/services/*` across all bundled jars into one — required for SPI-based libs (SLF4J providers, etc.). |
| `exclude("META-INF/*.kotlin_module")` | Stops `kotlin_module` duplicates from clashing on the fat-jar classpath. Without this, kotlin-reflect on the script classpath picks one and errors on the rest. |
| `Main-Class: com.TTT.ApplicationKt` | `java -jar TPipe-<v>-all.jar --script foo.kts` works without `-cp` gymnastics because the main-class pointer is preserved. |

Provider submodules go in `fatJarImplementation`, NOT `implementation`. Verify this — accidentally adding `implementation(project(":TPipe-Bedrock"))` will leak Bedrock into the published TPipe core jar.

## Verification recipe (run in this exact order)

```bash
# 1. Build the fat-jar — id of a normal build cycle
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew fatJar --offline 2>&1 | tail -5
# Expected: BUILD SUCCESSFUL
# Output:    build/libs/TPipe-<v>-all.jar

# 2. Verify fat-jar CONTAINS provider classes
ls -lh build/libs/TPipe-<v>-all.jar
unzip -l build/libs/TPipe-<v>-all.jar | grep -E "GenericOpenAIPipe|BedrockPipe|OllamaPipe"
# Expected: matches found

# 3. Build the regular jar (idempotent if cached)
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew jar --offline 2>&1 | tail -5
unzip -l build/libs/TPipe-<v>.jar | grep -cE "GenericOpenAIPipe|BedrockPipe"
# Expected: 0 — provider classes must NOT appear in the regular jar

# 4. Regression: existing tests still pass
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew test --offline 2>&1 | tail -20
# Expected: all previous tests still pass; CoercionTest.kt + JsonRepairTest.kt remain excluded per the quarantine in build.gradle.kts
```

If step 3 shows ANY provider-class count > 0, the dependencies leaked. Diagnose by running:

```bash
./gradlew :dependencies --configuration runtimeClasspath --offline 2>&1 | grep -E "TPipe-(Bedrock|Ollama|OpenRouter|GenericOpenAI)"
```

Any matches here mean the submodule is in `runtimeClasspath`, which means it's in the regular jar. Remove the `fatJarImplementation` declarations and move them to `fatJarImplementation` explicitly. (The recipe above already uses `fatJarImplementation`; this is a check to confirm.)

## Sandbox-specific build flags

If `./gradlew` fails with `Gradle build daemon has been stopped: stop command received` (sandbox cgroup killing the daemon):

```bash
JAVA_OPTS="-Xmx2g -XX:MaxMetaspaceSize=512m" \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1" \
./gradlew fatJar --offline
```

Add `--offline` if the daemon hangs on network requests the sandbox kills mid-flight. First compile takes 2-4 min; the sandbox must allow that wall-clock.

## Production-size expectations

A TPipe fat-jar typically lands at 60-100MB. The big contributors are `ktor-server-netty`, the bundled Ktor/Netty transitive deps, and MCP server libs. If the jar exceeds 200MB:

1. Audit `merging` in the ShadowJar config — service file merged blocks can bloat.
2. Consider explicitly `exclude`ing optional integrations not needed for the script host (e.g. `tpipemcp-package` server if no `--mcp-*` mode is reached from scripts).
3. Do NOT exclude `kotlin-reflect` — the script host needs it for `@KotlinScript` annotation processing.

## Files referenced by this document

- `build.gradle.kts` (root project, ~160 lines today)
- `settings.gradle.kts` (the module list — `TPipe-Ollama`, `TPipe-OpenRouter`, `TPipe-Bedrock`, `TPipe-MCP`, `TPipe-Defaults`, `TPipe-Tuner`, `TPipe-TraceServer`, `TPipe-GenericOpenAI`)
