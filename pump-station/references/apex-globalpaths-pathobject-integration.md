# Apex Canvas: GlobalPaths, GlobalAgents, and Skill Loader Integration

Source: Apex `/home/cage/Desktop/Workspaces/Apex/` + TPipe `Pipeline/PumpStation.kt`
Context: 2026-07-16 session (initial) and 2026-07-16 follow-up session (GlobalAgents + SkillLoader).
Apex v0.1 scaffold, TPipe `PathObject` internals reviewed.

## Key Finding: PathObject is Final — User-Facing Surface is ApexPathLoader

**Critical ground-truth correction (2026-07-16):** TPipe's `com.TTT.Pipeline.PathObject` is declared
`class PathObject(...) : P2PInterface` — **NOT `open`**. External code cannot subclass it.
A naive plan that has user-dropped `.kt` files subclassing `PathObject` directly will fail with
"This type is final, so it cannot be extended" at compile time.

The user-facing open base class for path loading is `ApexPathLoader`, defined at
`apex-runtime/src/main/kotlin/apexCore/path/GlobalPaths.kt:18`:

```kotlin
open class ApexPathLoader {
    var storedPath: PathObject? = null

    open fun init(): PathObject? {
        return null
    }

    fun load() {
        val pathResult = init() ?: throw Exception("path result is null in ${this.javaClass.simpleName}")
        storedPath = pathResult
        push()
    }

    fun push() {
        GlobalPaths.register(storedPath!!)
    }
}
```

Users subclass `ApexPathLoader`, override `init()` to construct a `PathObject` (which IS still
final — but they can construct one without subclassing), and the loader calls `load()` to
push it into `GlobalPaths`. This indirection lets users drop plain `.kt` files without
needing to make TPipe changes.

## Key Finding: ApexAgent IS Open — Users Subclass It Directly

Unlike `PathObject`, `apexCore.agent.ApexAgent` is declared `open class ApexAgent(override var killSwitch: KillSwitch?) : P2PInterface`
(see `apex-runtime/src/main/kotlin/apexCore/agent/ApexAgent.kt:25`). Users subclass directly,
no wrapper class needed.

## Two Registries, One Pattern

Apex has two parallel registries, both living in `apex-runtime` and both following the
copy-on-write snapshot + `kotlinx.collections.immutable.PersistentMap` pattern:

### GlobalPaths (paths)
- File: `apex-runtime/src/main/kotlin/apexCore/path/GlobalPaths.kt`
- Open base for user extension: `ApexPathLoader` (same file, top of file)
- Public API: `register(PathObject)`, `unregister(pathName)`, `lookup(pathName)`, `fuzzySearch(query, limit)`
- Storage: `AtomicReference<Snapshot>` where `Snapshot(paths: PersistentMap<String, GlobalPathDefinition>)`
- Convert pathObject → GlobalPathDefinition internally; TPipe types stay inside `apex-runtime`
- Tests: 16 (`apex-runtime/src/test/kotlin/apexCore/path/GlobalPathsTest.kt`)

### GlobalAgents (agents)
- File: `apex-runtime/src/main/kotlin/apexCore/agent/GlobalAgents.kt`
- Open base for user extension: `ApexAgent` (same module, separate file)
- Public API: `register(ApexAgent, agentName)`, `unregister(agentName)`, `lookup(agentName)`,
  `lookupAll()`, `agentCount()`, `registerPath(PathObject)` (pass-through to GlobalPaths)
- Storage: same COW snapshot + PersistentMap pattern
- Convert ApexAgent → GlobalAgentDefinition internally
- Tests: 8 (`apex-runtime/src/test/kotlin/apexCore/agent/GlobalAgentsTest.kt`)

## User Drop Zone — apex-skills Module

End-user dropped `.kt` files live in a dedicated Gradle module:

```
Apex/
├── apex-runtime/             ← registry owners (GlobalPaths, GlobalAgents)
└── apex-skills/              ← user drop zone
    ├── build.gradle.kts      ← depends on apex-shared (NOT apex-runtime, see circular-dep pitfall below)
    └── src/main/kotlin/apexSkills/
        ├── SkillLoader.kt     ← reflection-based scanner
        └── SmokeFixtures.kt   ← runtime-discoverable fixtures (apexCore.agent.*)
```

`apex-skills/build.gradle.kts` declares:
```kotlin
implementation(project(":apex-shared"))
implementation(kotlin("reflect"))           // for KClass.createInstance / superclasses
testImplementation(project(":apex-runtime"))  // tests can call into registries directly
```

The runtime dependency `apex-runtime → apex-skills` is one-way only (see circular-dep pitfall below).

## SkillLoader.loadAll() — Reflection Scanner

File: `apex-skills/src/main/kotlin/apexSkills/SkillLoader.kt`

```kotlin
object SkillLoader {
    data class LoadResult(val agentCount: Int, val pathCount: Int, val loadedAt: Long)
    fun loadAll(): LoadResult
}
```

Algorithm:
1. Resolve base classes via reflection (NOT direct import): `apexCore.agent.ApexAgent` and
   `apexCore.path.ApexPathLoader`.
2. Walk the three target package prefixes: `apexCore`, `apexSkills`, `userAgents`.
3. For each `.class` resource: load via `Class.forName`, check if non-abstract subclass of
   a target base, check no-arg constructor, collect.
4. For each `ApexAgent` subclass found: `kClass.createInstance()`, call
   `GlobalAgents.register(instance, agentName = simpleName)` reflectively.
5. For each `ApexPathLoader` subclass found: `kClass.createInstance()`, call
   `instance.load()` (which calls `init()` to produce the PathObject and pushes to GlobalPaths).
6. Return `LoadResult(agentCount, pathCount, System.currentTimeMillis())`.

Scoped to three package prefixes (not full classpath) to keep scanner cost bounded and to
prevent accidentally picking up classes from unrelated modules. Add new prefixes here when
introducing new drop-zone modules.

## Critical Pitfall: Circular Module Dependency

**Symptom:** `Circular dependency between the following tasks: :apex-runtime:classes / :apex-runtime:compileKotlin / :apex-skills:jar / :apex-skills:classes / :apex-skills:compileJava / :apex-runtime:jar`

**Root cause:** If `apex-runtime → apex-skills` AND `apex-skills → apex-runtime` both exist,
Gradle cannot resolve the build order. `apex-runtime/main()` needs `SkillLoader.loadAll()`,
but `SkillLoader` needs `GlobalAgents` / `GlobalPaths` from `apex-runtime`.

**Fix (verified pattern):** Break the cycle by removing `apex-skills → apex-runtime` from
PRODUCTION dependencies. Move the call into `SkillLoader` via reflection:

```kotlin
// apex-skills main source uses reflection, NOT direct imports:
val globalAgents = Class.forName("apexCore.agent.GlobalAgents", false, classLoader).kotlin
val globalAgentsInstance = globalAgents.objectInstance
val registerFn = globalAgents.memberFunctions.first { it.name == "register" && it.parameters.size == 3 }
registerFn.call(globalAgentsInstance, instance, simpleName)
```

For Kotlin `object` declarations, the KFunction takes the singleton as its receiver parameter,
so `parameters.size == 3` (receiver + 2 args) and `call(globalAgentsInstance, ...)` is required.
Plain Java reflection via `kFunction.javaMethod!!.invoke(null, instance, name)` works too because
Kotlin objects expose their members as static JVM methods.

Keep `testImplementation(project(":apex-runtime"))` on `apex-skills` so unit tests can use direct
imports (`apexCore.agent.GlobalAgents.unregisterAll()` etc.) without reflection.

## Wiring loadAll() into Runtime Startup

`apex-runtime/src/main/kotlin/com/TTT/apex/runtime/ApexRuntime.kt:36-37`:

```kotlin
val loadResult = apexSkills.SkillLoader.loadAll()
println("Apex runtime loaded ${loadResult.agentCount} agents and ${loadResult.pathCount} paths")
```

Run via `./gradlew :apex-runtime:run`. Smoke output for a registry with smoke fixtures:
`Apex runtime stub OK (TPipe classpath: loaded)` then `Apex runtime loaded 1 agents and 1 paths`.

## Pre-Existing TTT Style Violations (DEFERRED 2026-07-16)

`apex-runtime/src/main/kotlin/apexCore/agent/ApexAgent.kt:121` has `try {` (same-line brace,
should be next-line) and line 130 has `catch (exception: Exception) {` (same-line brace + space
after `catch`). These violate the TTT style rules now mandated by `AGENTS.md`. They pre-date
the GlobalAgents work and remain unfixed. Drive-by cleanup pass should:

1. Fix `try {` → `try\n{` on line 121.
2. Fix `catch (exception: Exception) {` → `catch(exception: Exception)\n{` on line 130.
3. Run `./gradlew :apex-runtime:test` to confirm no regression.

Don't fix as part of feature work — flag separately so the user's commit history shows the
style cleanup as its own atomic change.

## TDD Phase Notes

The full Apex GlobalPaths + GlobalAgents + SkillLoader rollout shipped 38 tests across 6 suites:

| Module | Suite | Tests |
|---|---|---|
| `apex-shared` | `WorkflowSerializationTest` | 5 |
| `apex-shared` | `AgentSerializationTest` | 3 (new — GlobalAgentDefinition round-trip) |
| `apex-runtime` | `GlobalPathsTest` | 16 |
| `apex-runtime` | `GlobalAgentsTest` | 8 (new) |
| `apex-runtime` | `TPipeClasspathProbeTest` | 2 (pre-existing) |
| `apex-skills` | `SkillLoaderTest` | 4 (new — `FixtureAgent` + `FixturePath`) |

`FixturePath` in `apex-skills/src/test/kotlin/apexSkills/SkillLoaderTest.kt` is a test fixture
that extends `ApexPathLoader` and overrides `init()` to produce a `PathObject` named "FixturePath".
The `SkillLoaderTest` then verifies the loader discovers and registers it via
`apexCore.path.GlobalPaths.lookup("FixturePath")`. This pattern is the canonical recipe for
testing path loader discovery — use it when writing new path/agent discovery tests.