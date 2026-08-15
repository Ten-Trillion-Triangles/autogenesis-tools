# Container Embedding and the DummyPipe Shim System

The canonical way to put a higher-level TPipe container (Manifold, Splitter, Junction, DistributionGrid, nested PumpStation) inside a slot that only accepts a Pipe or only accepts a Pipeline.

## The Three Layers

### Layer 1 — DummyPipe

**File:** `src/main/kotlin/Pipe/DummyPipe.kt` (19 lines)

```kotlin
package com.TTT.Pipe

@kotlinx.serialization.Serializable
class DummyPipe : Pipe()
{
    override fun truncateModuleContext(): Pipe = this
    override suspend fun generateText(promptInjector: String): String = promptInjector
}
```

Identity pass-through pipe. Does nothing on its own. The redirect happens at Layer 2.

KDoc from the file (verbatim):
> A no-op pipe that delegates entirely to a `containerPtr`. Used as a developer-friendly placeholder in pipelines when the intent is to embed a container (Manifold, Splitter, etc.) without any additional pipe-level logic. The pipe functions as a pure redirect — it defers all execution to the contained object via `P2PInterface.executeLocal`.

### Layer 2 — Pipe.setContainerPtr

**File:** `src/main/kotlin/Pipe/Pipe.kt`

| What | Line | Notes |
|------|------|-------|
| `containerPtr: P2PInterface?` declaration | 1570 | The slot that gets installed |
| Execute-path redirect | 5737-5741 | The actual swap to `containerPtr.executeLocal(inputContent)` |
| `setContainerPtr(ptr: P2PInterface): Pipe` | 4907-4911 | The setter that wires the redirect |
| Token-budget recursion forwarding | 7774-7784 | When `containerPtr != null`, budget recursion calls `containerPtr.setTokenBudgetRecursive(budget)` instead of pipe-level `setTokenBudget` |
| Pipe-settings recursion forwarding | 7786-7796 | Same pattern for `applyPipeSettings` |

**The execute-path swap (Pipe.kt:5737-5741, the load-bearing code):**

```kotlin
if(containerPtr != null)
{
    val result = containerPtr!!.executeLocal(inputContent)
    return@coroutineScope if(wrapContentWithConverseHistory)
        embedContentIntoInternalConverse(result)
    else result
}
```

KDoc from Pipe.kt:4904-4906:
> You can place a manifold or splitter inside a pipeline. Instead of executing this pipe the container pointer will be redirected to and ran instead.

**Implication:** any class installed as `containerPtr` MUST have a working `executeLocal(MultimodalContent): MultimodalContent` override. Manifold, Junction, Pipeline, Splitter, Connector, MultiConnector, DistributionGrid, and PumpStation all provide this. A custom class without `executeLocal` will silently pass through unchanged or throw at runtime — see the pitfall below.

**Why every named container satisfies this:** all of them implement `P2PInterface` directly (Pipeline.kt:43, Pipe.kt:753, Manifold.kt:66, DistributionGrid.kt:97, P2PHostedRegistryClient:469). A Pipeline plugs into a `P2PInterface?` slot because Pipeline : P2PInterface. See `references/p2p-interface-type-hierarchy.md` for the full class hierarchy and the slot-by-slot comparison table for Manifold / PumpStation / Junction / DistributionGrid.

### Layer 3 — Factory Functions

**File:** `src/main/kotlin/Util/Util.kt`

```kotlin
// Line 1599-1605
fun createContainerPtr(ptr: P2PInterface, pipeNameRef: String = "") : DummyPipe
{
    return DummyPipe().apply {
        setContainerPtr(ptr)
        setPipeName(pipeNameRef.ifEmpty { "ContainerPtr" })
    }
}

// Line 1615-1624
fun createContainerPtrAsPipeline(
    ptr: P2PInterface,
    dummyPipe: DummyPipe? = null,
    pipelineName: String = ""
) : Pipeline
{
    return Pipeline().apply {
        setPipelineName(pipelineName.ifEmpty { "ContainerPtrPipeline" })

        val internalPipe = dummyPipe ?: createContainerPtr(ptr, "$pipelineName-dummy-pipe")
        add(internalPipe)
    }
}
```

KDoc from `createContainerPtr` (Util.kt:1590-1597):
> Convince function to allow the automation of creating a dummy pipe to hold a container pointer. Useful for adding to a pipeline as a one off when you want to route to a complex container.

KDoc from `createContainerPtrAsPipeline` (Util.kt:1607-1614):
> Convince function that creates a dummy pipeline that houses a container ptr inside of it. Useful for handling cases like [Connector] and [Splitter] which only accept pipelines.

## Decision Matrix

| Slot accepts | Use | Returns |
|--------------|-----|---------|
| `Pipe` | `createContainerPtr(ptr, name)` | `DummyPipe` |
| `Pipeline` (Connector.add, Splitter) | `createContainerPtrAsPipeline(ptr, pipelineName = ...)` | `Pipeline` (one internal DummyPipe) |
| You already built a DummyPipe and want to reuse it inside a wrapper | `createContainerPtrAsPipeline(ptr, dummyPipe = preBuilt)` | `Pipeline` |

## Worked Recipes

### Embed a Manifold inside a Connector branch

```kotlin
val wrappedManifold: Pipeline = createContainerPtrAsPipeline(
    ptr = myBuiltManifold,
    pipelineName = "manifold-as-connector-branch"
)
connector.add("branch-a", wrappedManifold)
```

### Embed a Junction as a single redirect pipe

```kotlin
val junctionPtr: DummyPipe = createContainerPtr(myJunction, "junction-dummy")
pipeline.add(junctionPtr)
```

### Reuse a manually-built DummyPipe

```kotlin
val dummy = DummyPipe().apply {
    setContainerPtr(myContainer)
    setPipeName("container-redirect")
}
val wrapped = createContainerPtrAsPipeline(myContainer, dummyPipe = dummy)
splitter.add(wrapped)
```

## Where Lambda Adapters Actually Exist

`Pipeline.kt` and `Util.kt` are the wrong files to look in for `addLambda` / `from` / `wrap` / `as` style adapters. Those don't exist for Pipeline/Manifold/Junction/Connector/Splitter. Their `add*` and `insert` methods all take real instances:

| Method | Signature | File:Line |
|--------|-----------|-----------|
| `Pipeline.add` | `fun add(pipe: Pipe): Pipeline` | `Pipeline.kt:691` |
| `Pipeline.insert` | `fun insert(pipe: Pipe, index: Int): Pipeline` | `Pipeline.kt:708` |
| `Manifold.addWorkerPipeline` | `fun addWorkerPipeline(pipeline: Pipeline, descriptor, requirements)` | `Manifold.kt:873` |
| `Connector.add` | `fun add(key: Any, pipeline: Pipeline): Connector` | `Connector.kt:240` |
| `Junction.addParticipant` | `fun addParticipant(roleName: String, component: P2PInterface, ...): Junction` | `Junction.kt:402` |

**The ONE place TPipe has lambda → P2PInterface adapters is the PumpStation DSL** (`Pipeline/PumpStationDsl.kt`). See the matrix below.

## PumpStation DSL Builder-Function Matrix

The seven core station agent slots each have a parallel pair — a direct instance field AND a builder-function field that returns a fresh instance per harness invocation.

| Slot | Direct instance | Builder function | Return type |
|------|-----------------|------------------|-------------|
| Judge | `var judgeAgent: P2PInterface?` | `var judgeAgentBuilderFunction: (suspend (PumpStation) -> Pipeline)?` | Pipeline |
| Dispatch | `var dispatchAgent: P2PInterface?` | `var dispatchAgentBuilderFunction: (suspend (PumpStation) -> Pipeline)?` | Pipeline |
| Intervention | `var interventionAgent: P2PInterface?` | `var interventionAgentBuilderFunction: (suspend (PumpStation) -> P2PInterface)?` | P2PInterface |
| Lorebook | `var lorebookAgent: P2PInterface?` | `var lorebookAgentBuilderFunction: (suspend (PumpStation) -> P2PInterface)?` | P2PInterface |
| Summary | `var summaryAgent: P2PInterface?` | `var summaryAgentBuilderFunction: (suspend (PumpStation) -> P2PInterface)?` | P2PInterface |
| Goal | `var goalAgent: P2PInterface?` | `var goalAgentBuilderFunction: (suspend (PumpStation) -> P2PInterface)?` | P2PInterface |
| Health | `var healthAgent: P2PInterface?` | `var healthAgentBuilderFunction: (suspend (PumpStation) -> P2PInterface)?` | P2PInterface |

**File:** `src/main/kotlin/Pipeline/PumpStationDsl.kt` lines 80-162 (field declarations)

For additional harness agents beyond the seven core slots, two public DSL functions exist:

```kotlin
// Direct instance — concurrency defaults to Blocking
fun harnessAgent(
    agent: P2PInterface,
    concurrency: PumpStationConcurrencyMode = PumpStationConcurrencyMode.Blocking,
    block: (HarnessAgentSlotDsl.() -> Unit) = {}
): PumpStationBuilder<S>
// PumpStationDsl.kt:815-828

// Lambda → fresh P2PInterface per slot invocation — concurrency defaults to Async
fun harnessAgentBuilder(
    fn: suspend (PumpStation) -> P2PInterface,
    concurrency: PumpStationConcurrencyMode = PumpStationConcurrencyMode.Async,
    block: (HarnessAgentSlotDsl.() -> Unit) = {}
): PumpStationBuilder<S>
// PumpStationDsl.kt:833-845
```

The slot data class `HarnessAgentSlot` lives at `PumpStationModels.kt:1013-1018`:

```kotlin
data class HarnessAgentSlot(
    val agent: P2PInterface?,
    val concurrency: PumpStationConcurrencyMode,
    val builderFunction: (suspend (harness: PumpStation) -> P2PInterface)? = null,
    val appendsToTurnHistory: Boolean = false
)
```

The lambda receives the live `PumpStation` instance, so you can read turn state, minibank, etc. before building the agent.

## Pitfalls

### P1 — Inventing fake lambda adapters (anti-pattern, 2026-07-09)

The instinct when wiring non-Pipe objects into TPipe is to look for `addLambda` / `asPipeline` / `from` / `wrap` style adapters. These do NOT exist for Pipeline/Manifold/Junction/Connector/Splitter. Their `add*`/`insert` methods take real instances only.

**Verified:** a session hallucinated three fake adapter paths (wrap into Pipeline + setP2pDescription + register) before the operator prompted for the actual shim system. Always check `PumpStationDsl.kt` for the builder-function matrix if you need lambda adapters. Otherwise, build a real Pipeline wrapper and use the shim system.

### P2 — containerPtr requires a working executeLocal (anti-pattern, 2026-07-09)

The redirect at Pipe.kt:5739 calls `containerPtr!!.executeLocal(inputContent)`. Manifold, Junction, Pipeline, Splitter, Connector, MultiConnector, DistributionGrid, and PumpStation all override `executeLocal`. If you point `containerPtr` at a custom class without a working `executeLocal(MultimodalContent): MultimodalContent`, the shim silently fails — the pipe either passes through unchanged or throws. **Verify the embedded class has `executeLocal` before installing the redirect.**

### P3 — PumpStation DSL uses PROPERTY assignment, not method calls (2026-07-09)

The PumpStation core-agent slots are DSL-bound `var` properties, NOT DSL methods:

```kotlin
// RIGHT — property assignment inside the DSL block
pumpStation {
    dispatchAgent = myPipeline
    judgeAgentBuilderFunction = { ps -> buildJudge(ps) }
}

// WRONG — these don't exist as DSL methods
pumpStation {
    judgeAgent(myPipeline)              // doesn't compile
    dispatchAgentBuilderFunction { ... } // doesn't compile
}
```

For additional harness agents, the DSL method form IS used:

```kotlin
pumpStation {
    harnessAgent(myContainer, concurrency = PumpStationConcurrencyMode.Async)
    harnessAgentBuilder({ ps -> buildMyAgent(ps) })
}
```

When reading example code, look for `=` signs (property assignment) for the seven core slots and `functionName(...)` (method call) for `harnessAgent` / `harnessAgentBuilder`.

## Where to Look in the Codebase

| What you want | Read |
|---------------|------|
| The DummyPipe class itself | `src/main/kotlin/Pipe/DummyPipe.kt` (19 lines, read in full) |
| The redirect mechanism | `src/main/kotlin/Pipe/Pipe.kt:5737-5741` (the if-block), `:4907-4911` (setter), `:7774-7796` (recursion forwarding) |
| The two factory functions | `src/main/kotlin/Util/Util.kt:1599-1605` and `:1615-1624` |
| PumpStation DSL builder-function fields | `src/main/kotlin/Pipeline/PumpStationDsl.kt:80-162` |
| PumpStation DSL `harnessAgent` / `harnessAgentBuilder` | `src/main/kotlin/Pipeline/PumpStationDsl.kt:815-845` |
| `HarnessAgentSlot` data class | `src/main/kotlin/Pipeline/PumpStationModels.kt:1013-1018` |
| The seven core station agent magic contracts | `pump-station` skill, "Magic Contracts" section |