---
name: tpipe-pipeline-patterns
description: "TPipe pipeline configuration patterns — the builder pattern (.apply { } or chained setX() calls) and the scope/DSL pattern (manifold { }, junction { }, distributionGrid { }). Load when configuring any TPipe pipe or container, choosing between builder and DSL styles, debugging configuration order, composing multi-pipe architectures, embedding higher-level containers inside lower-level ones (DummyPipe + setContainerPtr + createContainerPtr* factory shim system), when binding fragments of a composite payload onto individual pipes via pipeMetadata (top-of-function destructure + per-pipe bind idiom), OR when subclassing com.TTT.Pipe.Pipe directly to write a custom Pipe (the four required overrides, the setIP/setPort return-type gotcha, the OllamaPipe.generateText wire-format bug workaround). Use when working with BedrockMultimodalPipe, Pipeline, Connector, Splitter, Manifold, Junction, DistributionGrid, any container's init() and configuration flow, or any custom Pipe subclass."
version: 1.3.0
author: Hermes Agent + Apex
license: MIT
metadata:
  tpipe:
    tags: [tpipe, pipeline, builder-pattern, dsl, kotlin, configuration, manifold, junction, distributiongrid]
    homepage: https://github.com/ten-trillion-triangles/TPipe
---

# TPipe Pipeline Patterns

TPipe offers two patterns for configuring components. The **builder pattern** (chained `setX()` calls or `.apply { }` blocks) and the **scope/DSL pattern** (typed receiver blocks like `manifold { worker { pipeline { add(p) } } }`). Both ship in production. The choice between them is structural, not stylistic.

## The Rule

**Builder for pipes. Scope for containers.**

- Pipes (BedrockMultimodalPipe, OpenRouterPipe, BedrockPipe, GenericOpenAIPipe) → builder only
- Pipeline, Connector, Splitter, MultiConnector, PumpStation → builder only
- Manifold, Junction, DistributionGrid → both patterns (builder classes + scope DSLs)

When in doubt: build pipes with the builder, hand them to a scope-configured container. The patterns compose at the boundary.

## Pattern 1: The Builder

Instantiate a class, chain configuration calls, call `init()`.

### Chained calls (short configuration)

```kotlin
val pipe = BedrockMultimodalPipe()
    .setRegion("us-west-2")
    .setModel("anthropic.claude-3-haiku-20240307-v1:0")
    .setTemperature(0.7)
    .setSystemPrompt("You are a helpful assistant.")
    .init()
```

### `.apply { }` block (long or conditional configuration)

```kotlin
val guidePipe = BedrockMultimodalPipe().apply {
    useConverseApi()
    setRegion("us-west-2")
    setModel(BedrockConfig.qwen235B)  // val property on BedrockConfig singleton — returns a String, NOT a Kotlin enum
    setTemperature(1.0)
    setTopP(.9)
    requireJsonPromptInjection()
    setJsonInput(PlayerStoryInput::class)
    setJsonOutput(GuideData::class)
    setTokenBudget(TokenBudgetSettings().apply {
        contextWindowSize = 32_000
        maxTokens = 4_000
        reasoningBudget = 2_000
        subtractReasoningFromInput = true
        userPromptSize = 8_000
        preserveTextMatches = true
        multiPageBudgetStrategy = MultiPageBudgetStrategy.DYNAMIC_SIZE_FILL
    })
    setReasoningPipe(BedrockConfig.authorBuilder(...))
    setPipeName("guide pipe")
    enableLoreBookFillAndSplitMode()
    setSystemPrompt(systemPrompt)
    setMiddlePrompt(middlePrompt)
    autoInjectContext(context)
}
```

The `.apply` block is a style choice. Both forms are the builder pattern. The block groups configuration visually and allows conditional `if` statements.

### Required: `init()`

After configuration, call `init()` before any `execute()`. For Bedrock pipes, `init()` does four things: (1) calls `super.init()` to propagate timeout settings and initialize child pipes, (2) loads inference profile mappings from `~/.aws/inference.txt` via `bedrockEnv.loadInferenceConfig()`, (3) resolves the model ID to an inference profile ARN, (4) initializes the `BedrockRuntimeClient` with region, credentials, and HTTP timeouts. Without `init()`, `bedrockClient` is never created and the first `execute()` throws because the provider backend is missing.

> **Note:** With the scope DSL, init is handled internally. With the builder, you must call it explicitly.

## Pattern 2: The Scope (DSL)

A Kotlin DSL with a typed receiver. The compiler enforces what you can call at each stage. Lifecycle is handled internally — you cannot get a reference to the finished object until configuration is complete.

### Manifold DSL

```kotlin
val builtManifold = manifold {
    defaults {
        bedrock(BedrockConfiguration(
            region = "us-east-1",
            model = "anthropic.claude-3-haiku-20240307-v1:0"
        ))
    }

    worker("research-worker") {
        description("Researches and summarizes requested information.")
        skill("research", "Investigates the user's request.")
        pipeline {
            pipelineName = "research-worker-pipeline"
            add(researchWorker)
        }
    }
}
```

### Junction DSL — with state machine

Junction's DSL enforces a four-stage state machine at compile time:

| Stage | Required calls | Available methods |
|-------|---------------|-------------------|
| `Initial` | (none) | `moderator(...)` only |
| `HasModerator` | `moderator { }` | `moderator`, `participant` |
| `HasParticipants` | `moderator` + at least one `participant` | `moderator`, `participant`, all builder methods |
| `Ready` | All required configuration | `build()` returns `Junction` |

```kotlin
val junction = junction {
    participant("worker", workerPipeline)  // Does NOT compile — Initial has no participant
}
```

The compiler rejects misuse at the type-system level. The receiver type at any point is `JunctionBuilder<Stage>`, and only stages that have passed the required calls have the method you want.

### DistributionGrid DSL

The deepest DSL — has P2P, routing, memory, hooks, tracing, and concurrency blocks.

```kotlin
val grid = distributionGrid {
    p2p {
        agentName("my-grid-node")
        transportAddress("my-grid-node")
        transportMethod(Transport.Tpipe)
    }
    router(routerPipeline)
    worker(workerPipeline)
    routing {
        allowRetrySamePeer(true)
        maxRetryCount(1)
        maxHopCount(8)
    }
    memory {
        outboundTokenBudget(4096)
        summaryBudget(512)
    }
    tracing { enabled() }
    hooks {
        beforeRoute { envelope -> envelope }
        afterLocalWorker { envelope -> envelope }
    }
    concurrencyMode(P2PConcurrencyMode.ISOLATED)
    killSwitch(inputTokenLimit = 100000, outputTokenLimit = 10000)
}
```

## State Machine Validation (The Scope Pattern's Payoff)

The scope pattern's defining feature is compile-time enforcement of configuration order. The `junction { }` DSL is the cleanest example:

```kotlin
val junction = junction {
    moderator("mod", modPipeline)
    // No participants — block compiles, but inferred type is
    // JunctionBuilder<HasModerator>, not Junction. Cannot call .execute().
}
```

This is impossible to express as a runtime check without ceremony. With the scope pattern, the type system does it for free.

## Mixing the Patterns

The patterns compose at the boundary. A Pipeline built with the builder can be passed to a Manifold worker via the scope DSL:

```kotlin
// Builder: build the pipeline
val classifier = BedrockMultimodalPipe().apply { /* ... */ }.init()
val agentPipeline = Pipeline().add(classifier).add(router).init()

// Scope: hand the pipeline to a manifold worker
val builtManifold = manifold {
    defaults { bedrock(BedrockConfiguration(...)) }
    worker("sentiment-agent") {
        description("Classifies sentiment.")
        skill("sentiment", "Sentiment classifier.")
        pipeline(agentPipeline)  // ← builder-built pipeline handed to scope DSL
    }
}
```

This is the recommended pattern. Builder for pipes, scope for the containers that compose them.

## When to Use Which

| Scenario | Pattern |
|----------|---------|
| Configuring a single pipe | Builder (no DSL exists) |
| Long pipe configuration with conditional logic | Builder with `.apply { }` |
| Composing multiple pipes into a Pipeline | Builder |
| Building a Manifold, Junction, or DistributionGrid | Scope DSL (preferred) |
| Building a Manifold, Junction, or DistributionGrid with dynamic/conditional config | Builder class version (`ManifoldBuilder<Stage>().worker().build()`) |
| Library code that wraps TPipe | Scope DSL (state machine catches caller misuse) |

## Anti-Patterns

### Don't nest scope blocks five levels deep

```kotlin
// BAD
val builtManifold = manifold {
    worker("name") {
        pipeline {
            reasoning { ... }   // hard to read, hard to refactor
        }
    }
}
```

If nesting gets deep, hoist the inner blocks into variables built with the builder pattern. The scope is for top-level structure. The builder is for explicit configuration.

### Don't mix container concerns into pipe-focused articles

When writing a blog post about pipes and pipelines, keep scope DSL content to the minimum: the composition boundary only (how a builder-built Pipeline gets handed to a Manifold worker). Container deep-dives (Manifold defaults/worker/pipeline blocks, Junction state machine stages, "why the DSL exists" rationales) belong in a separate containers article — not in a pipeline tutorial. Apex corrected this mid-session: the scope DSL is the thin boundary layer, not the subject. If the article's subject is "how to build a pipeline," container-level DSL blocks are out of scope.

## Container Embedding and the DummyPipe Shim System

When you have a higher-level container (Manifold, Splitter, Junction, DistributionGrid, even a nested PumpStation) and you need to place it somewhere that only accepts a Pipe or only accepts a Pipeline, TPipe has a three-layer shim system. This is the canonical way to embed higher-level containers inside lower-level ones — the comment at Pipe.kt:4904-4906 is explicit: "You can place a manifold or splitter inside a pipeline. Instead of executing this pipe the container pointer will be redirected to and ran instead."

### Layer 1 — DummyPipe (Pipe/DummyPipe.kt:14)

A no-op `Pipe` subclass with two overrides:
- `generateText(promptInjector: String): String = promptInjector` (identity pass-through)
- `truncateModuleContext(): Pipe = this`

Serializable. Does nothing on its own — the redirect happens at Layer 2.

### Layer 2 — Pipe.setContainerPtr (Pipe.kt:4907)

The redirect mechanism. When a Pipe's `containerPtr: P2PInterface?` (declared Pipe.kt:1570) is non-null, the pipe's execute path at Pipe.kt:5737-5741 calls `containerPtr.executeLocal(inputContent)` instead of running the LLM logic. So `setContainerPtr` is the act of installing the redirect — the Pipe itself becomes a pure pass-through to whatever P2PInterface you point at.

Token-budget recursion and pipe-settings recursion are containerPtr-aware at Pipe.kt:7774-7796 — when set, they forward to the container instead of applying at pipe level. So the shim is transparent to budget and settings propagation.

### Layer 3 — Two public factory functions (Util/Util.kt:1599 and 1615)

```
fun createContainerPtr(
    ptr: P2PInterface,
    pipeNameRef: String = ""
): DummyPipe
// Returns a DummyPipe with setContainerPtr(ptr) already called.
// pipeNameRef defaults to "ContainerPtr".

fun createContainerPtrAsPipeline(
    ptr: P2PInterface,
    dummyPipe: DummyPipe? = null,
    pipelineName: String = ""
): Pipeline
// Builds a Pipeline containing exactly one Pipe — the DummyPipe — set up
// as a containerPtr redirect to ptr. Defaults to "ContainerPtrPipeline".
// The KDoc is explicit: "Useful for handling cases like Connector and
// Splitter which only accept pipelines."
```

### When to use which

| Situation | Use |
|-----------|-----|
| Slot accepts `Pipe` | `createContainerPtr(myContainer, "name")` |
| Slot accepts `Pipeline` (Connector.add, Splitter) | `createContainerPtrAsPipeline(myContainer, pipelineName = "...")` |
| You already built the DummyPipe and want to reuse it | `createContainerPtrAsPipeline(container, dummyPipe = preBuilt)` |

### Worked example

```kotlin
// Embed a Manifold inside a Connector branch
val wrappedManifold: Pipeline = createContainerPtrAsPipeline(
    ptr = myBuiltManifold,
    pipelineName = "manifold-as-connector-branch"
)
connector.add("branch-a", wrappedManifold)

// Embed a Junction inside a Pipeline as a redirect pipe
val junctionPtr: DummyPipe = createContainerPtr(myJunction, "junction-dummy")
pipeline.add(junctionPtr)
```

### Pitfall: containerPtr requires a working executeLocal

The redirect at Pipe.kt:5739 calls `containerPtr!!.executeLocal(inputContent)`. Manifold and Junction override `executeLocal`; Pipeline does too. If you point `containerPtr` at a custom class that doesn't implement `P2PInterface.executeLocal(MultimodalContent): MultimodalContent` correctly, the shim silently fails at runtime — the pipe passes through unchanged or throws. Verify the embedded class has a working `executeLocal` before installing the redirect.

### The anti-pattern: inventing lambda adapters that don't exist

A common search instinct when wiring non-Pipe objects into TPipe is to look for `addLambda` / `asPipeline` / `from` / `wrap` style adapters. **TPipe does not have these** for Pipeline/Manifold/Junction/Connector/Splitter — their `add*` and `insert` methods take real instances only:

- `Pipeline.add(pipe: Pipe): Pipeline` (Pipeline.kt:691) — Pipe only
- `Pipeline.insert(pipe: Pipe, index: Int): Pipeline` (Pipeline.kt:708) — Pipe only
- `Manifold.addWorkerPipeline(pipeline: Pipeline, ...)` (Manifold.kt:873) — Pipeline only; no `addManifold`/`addJunction` overload
- `Connector.add(key: Any, pipeline: Pipeline)` (Connector.kt:240) — Pipeline only
- `Junction.addParticipant(roleName, component: P2PInterface, ...)` (Junction.kt:402) — any P2PInterface, but instance-only

**The ONE place TPipe has lambda → P2PInterface adapters is the PumpStation DSL** (`Pipeline/PumpStationDsl.kt`). Each of the seven core station agent slots has a parallel pair: a direct instance field (`judgeAgent: P2PInterface?`) AND a builder-function field (`judgeAgentBuilderFunction: (suspend (PumpStation) -> Pipeline)?` or `-> P2PInterface` for the five that don't require Pipeline). The builder-function form creates a fresh instance per harness invocation. Plus `harnessAgent(agent: P2PInterface, ...)` and `harnessAgentBuilder(fn: suspend (PumpStation) -> P2PInterface, ...)` for arbitrary additional agents. See the pump-station skill's "Magic Contracts" section for the full slot list.

Outside PumpStation: build a real Pipeline wrapper, then use the shim system. **Do not invent `addLambda(myContainer)` adapters — they don't exist** (verified 2026-07-09 after a session hallucinated three fake paths before the user prompted for the actual wrappers).

## P2P Scoping: Local vs Global Agents in Container `init()`

Every container that builds an agent list to hand to its manager/moderator pipe (Manifold, Junction, DistributionGrid) has to choose which agents to advertise. TPipe's `P2PRegistry` exposes two listers with different scoping rules:

| Function (P2PRegistry) | Returns | Filter |
|---|---|---|
| `listLocalAgents(container: Any)` | Agents whose `container` object-identity matches the passed container | Excludes agents with `requirements.allowExternalConnections = true` |
| `listGlobalAgents()` | Every agent in the registry | Excludes agents with `requirements.allowExternalConnections = false` (so you get the externally-reachable set) |

`isLocal` is a JVM `==` check on the `container` field of the registered `P2PAgentListing`. Two different Manifold instances on the same JVM are NOT local to each other. A remote agent (registered by another JVM via `P2PHostedRegistry`) is also not local to your container.

### Manifold's historical local-only restriction is a vestige

`Manifold.init()` historically called only `listLocalAgents(this)`. The inline comment explained this was for "memory safety and race condition concerns" — those concerns are now covered by `P2PRegistry`'s agent-duplication (`P2PConcurrencyMode.ISOLATED` + factory) and the per-dispatch `Transport.Tpipe` agent-name lookup at `P2PRegistry.kt:1037-1058`. The restriction is obsolete. The right call now is:

```kotlin
val visibleAgents = mutableListOf<P2PDescriptor>()
visibleAgents.addAll(P2PRegistry.listLocalAgents(this))
visibleAgents.addAll(P2PRegistry.listGlobalAgents())
visibleAgents.removeAll { it.agentName == managerDescriptor.agentName }
```

The dispatch path itself was never local-only. `Manifold.execute()` calls `P2PRegistry.sendP2pRequest(agentRequest, ...)` which routes through `clientAgentList[request.agentName]` (remote) or the in-JVM `Agents` map filtered by `Transport.Tpipe` (local-by-name). The local-only listing was the only thing hiding remote workers from the manager's prompt.

### Pitfall: local-only worker listings silently disable remote dispatch

If a Manifold, Junction, or DistributionGrid only feeds `listLocalAgents(container)` into its manager pipe, the manager LLM will NEVER see remote agents in its prompt. Even if the manager somehow emits an `AgentRequest` for a remote name (e.g., from prompt engineering or a bug), the dispatch path will still route correctly through `P2PRegistry`, but the manager's `setP2PAgentList` call won't have included the descriptor so the LLM has no reason to choose it. Result: the remote agent sits unused.

When auditing or extending any higher-level container, check the listing site. If you see only `listLocalAgents(this)`, that's the local-only vestige — widen it.

### Three-tier worker resolution for the `agent` argument

When the user-supplied validator / failure / transformation function gets the dispatched worker, the container's code typically does:

```kotlin
val workerPipeline = workerPipelinesByAgentName[agentRequest.agentName] ?: workerPipelines.find { ... }
if(workerPipeline != null) { ... validator.invoke(..., workerPipeline, ...) }
```

The `workerPipeline != null` guard silently skips the function for any worker that isn't in the local map — which is EVERY remote worker. To fix this:

1. Widen the function signature from `agent: Pipeline` to `agent: P2PInterface`. Pipeline implements P2PInterface, so existing callers passing a Pipeline keep compiling.
2. Resolve the worker as a `P2PInterface?` via three tiers, in order: local map → local list `find` → `P2PRegistry.findAgentByName(agentName)`.
3. The `findAgentByName` helper is O(N) over the registered-agent count — small in practice. Add a secondary index only if profiling flags it.

```kotlin
fun P2PRegistry.findAgentByName(agentName: String): P2PInterface? {
    for(entry in Agents) {
        if(entry.value.descriptor.agentName == agentName) return entry.value.agent
    }
    return null
}
```

The `killSwitch` token accounting at the worker-dispatch site can keep its existing local-only lookup — remote workers contribute to the budget via the registry's own token totals, and the per-call local accumulation is just bookkeeping. Don't widen the kill-switch guard.

## Pipeline Content Flow Control

Pipelines aren't simple chains. Every pipe receives a `MultimodalContent` object and can set control flags on it to redirect execution at runtime. See `references/multimodal-content-flow.md` for the full detail — the short version:

- `terminatePipeline` — halt cleanly, not an error
- `repeatPipe` — re-call this pipe until flag is cleared
- `passPipeline` — exit early, not an error
- `jumpToPipe` — jump to named pipe (forward or backward)
- `interuptPipeline` — interrupt signal for PumpStation harness
- `skipReasoningPipe` — skip reasoning sub-pipe this turn
- `metadata["connectorPath"]` — routing key for Connector; set by any pipe, read by Connector

The pipeline evaluates these flags after every pipe execution. The Connector reads `metadata["connectorPath"]` to route to the matching branch. `terminatePipeline` is a boolean flag, not an exception — do not use try/catch.

## See Also

- `tpipe-token-budgeting` — TPipe's `TokenBudgetSettings` primitive (fields, math, Autogenesis pattern, per-pipe deployment recipe)
- `tpipewriter-feature-delivery` — TPipeWriter-specific class-level umbrella for shipping features into the writing app (4-surface rule, /help discipline, runtime-overridable variable audit)
- `pump-station` — the ONE TPipe container with lambda → P2PInterface adapters (judgeAgentBuilderFunction, harnessAgentBuilder); full slot list in its Magic Contracts section
- `references/container-embedding-and-shims.md` — DummyPipe + setContainerPtr + createContainerPtr* factory reference with file:line citations and the seven-slot builder-function matrix for PumpStation
- `references/autogenesis-pipeline-examples.md` — real production code from the Autogenesis WriterAgent
- `references/multimodal-content-flow.md` — MultimodalContent control flags, Connector routing mechanism, convenience methods
- `references/json-prompt-injection-encoding.md` — `setJsonInput/Output` prompt-injection behavior, `serialize(obj)` `encodeDefaults` default, and the dead `senddefaults` parameter
- `references/pipe-metadata-global-pull.md` — per-class `MetadataBank` page-key pull via `setMetaPageKeys` + `pullMetaPageKeysInto<…>MetaData`; the bank primitive's lazy pull surface
- `references/pipe-metadata-global-pull.md` — the page-key pull pattern via `MetadataBank` — companion to `references/pipe-metadata-payload-binding.md`. Use when wiring cross-component metadata state through `MetadataBank` instead of manual-bind-at-construction.
- `references/custom-pipe-hello-world.md` — verified recipe for writing your own Pipe subclass (the four overrides, the four gotchas, a working Ollama subclass)
- `references/live-test-patterns.md` — env-gate silent-skip pattern, helper-factory, 4-test container harness, trace output convention, Hermes verification-evidence workflow, `runBlocking<Unit>` syntax gotcha — use when writing a live integration test for any container × provider combination

## Production Examples

- **Autogenesis WriterAgent** uses the builder pattern (`.apply { }` blocks) for all three pipes — guide, selection, writing. The pipes are composed into a Pipeline that is handed to a Manifold configured with the scope DSL. See `references/autogenesis-pipeline-examples.md`.
- **TStep debugger** uses pipelines composed with the scope pattern, with workers that share context through the Manifold's shared history.
- **Production convention:** builder for pipes, scope for the container that composes them.

## Key Files

| File | Role |
|------|------|
| `TPipe/src/main/kotlin/Pipe/Pipe.kt` | Base pipe class with all setX() methods |
| `TPipe/src/main/kotlin/Pipeline/Pipeline.kt` | Pipeline container (builder only) |
| `TPipe/src/main/kotlin/Pipeline/Connector.kt` | Routing container (builder only) |
| `TPipe/src/main/kotlin/Pipeline/Splitter.kt` | Fan-out container (builder only) |
| `TPipe/src/main/kotlin/Pipeline/ManifoldBuilder.kt` | Manifold scope DSL entry point |
| `TPipe/src/main/kotlin/Pipeline/JunctionBuilder.kt` | Junction scope DSL with state machine |
| `TPipe/src/main/kotlin/Pipeline/DistributionGridBuilder.kt` | DistributionGrid scope DSL |
| `Autogenesis/server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt` | Production builder-pattern example (lines 239-560) |

## See Also

- `references/autogenesis-pipeline-examples.md` — real production code from the Autogenesis WriterAgent, showing the builder pattern in a system that handles 100+ turn sessions.
- `templates/scope-dsl-manifold.kt` — copy-and-modify starter for a multi-worker Manifold using the scope DSL with three Bedrock-backed workers.

Custom Pipe Subclass (verified hello-world recipe)

When the built-in pipes (`BedrockPipe`, `OllamaPipe`, `GenericOpenAIPipe`) don't fit — when you need a stateless processor, a custom HTTP backend, or a pipe that doesn't rely on a chat-style LLM — you subclass `com.TTT.Pipe.Pipe` directly. The minimum viable subclass implements three abstract methods (`generateText`, `generateContent`, `truncateModuleContext`); `init()` is open and only needs override when you have setup work.

See `references/custom-pipe-hello-world.md` for the full recipe including:
- The 4-step verified lifecycle (`runBlocking { construct → configure → init → execute }`)
- A 10-line minimum custom Pipe subclass
- A working Ollama-backed Pipe (verified end-to-end against a live local Ollama)
- Five gotchas that bite first-time subclass authors (including why `OllamaPipe.generateText` is currently broken and how to sidestep it)
- The difference between `execute(String)` and `execute(MultimodalContent)` and why the latter is preferred

Starter templates:
- `templates/hello-pipe.kt` — stateless echo pipe (no LLM backend)
- `templates/hello-ollama-pipe.kt` — working Ollama-backed Pipe with verified end-to-end run

## Per-Class Page-Key Pull from `MetadataBank`

The complementary pattern to the construction-time bind in `references/pipe-metadata-payload-binding.md`. Where the manual-bind pattern is "destructure at construction, hand fragments to each pipe," the **page-key pull pattern** is "stash state in a globally-addressable scratchpad, pull what you need when you need it."

`MetadataBank` is a process-singleton, page-keyed, in-memory-only `Map<Any, Any>` registry (see `src/main/kotlin/Context/MetadataBank.kt`, shipped 1.0.15). The contract:

```kotlin
// At setup time — any code path, anywhere in the JVM:
MetadataBank.setMeta("apex.flow_state", mapOf("rounds" to 3, "focus" to "epic"))
MetadataBank.setMeta("apex.reasoning_config", mapOf("method" to "react"))
MetadataBank.setMeta("workflow.global_state", mapOf("step" to 5))
```

```kotlin
// At consumption time — Pipe.pipeMetadata, ContextWindow.metaData,
// MultimodalContent.metadata, PumpStation.metadata all support it:
pipe.setMetaPageKeys("apex.flow_state, apex.reasoning_config, workflow.global_state")
pipe.pullMetaPageKeysIntoPipeMetadata()
```

The class-typed methods that ship today (TPipe 1.0.15+):

| Class | Setter | Pull method | Target bag |
|-------|--------|-------------|------------|
| `Pipe` | `setMetaPageKeys(glued)` | `pullMetaPageKeysIntoPipeMetadata()` | `pipeMetadata` |
| `MultimodalContent` | `setMetaPageKeys(glued)` | `pullMetaPageKeysIntoMetaData()` | `metadata` |
| `ContextWindow` | `setMetaPageKeys(glued)` | `pullMetaPageKeysIntoWindowMetaData()` | `metaData` |
| `PumpStation` | `setMetaPageKeys(glued)` | `pullMetaPageKeysIntoPumpStationMetadata()` | `metadata` (uses `Any?`-keyed bridge) |

The glued string is parsed by `MetadataBank.pullMetaPageKeysIntoSuspend(target, glued)` itself — split on `", "`, trim, drop empty, last-write-wins on collision. Empty glued string is a no-op. Missing keys are silently skipped. See `references/pipe-metadata-global-pull.md` for the full contract including the `Any?`-keyed bridge that `PumpStation.metadata` uses (its bag is `MutableMap<Any?, Any?>`, not `MutableMap<Any, Any>`).

### When to use which pattern

| Scenario | Use |
|----------|-----|
| Single-pipe agent, wrapper known at construction | Manual bind (`pipeMetadata["x"] = ...` in `.apply { }`) |
| Multi-component setup where ANY class with a metadata bag needs cross-component state | Page-key pull via `MetadataBank` |
| Apex-agent features, workflow bundles, anything "global for the JVM" | Page-key pull |
| State that should persist across many `execute()` calls | Page-key pull |
| State scoped to a single construction → single `execute()` lifecycle | Manual bind |

### Pitfall: per-page-key mutex is for `emplaceSuspend`, not for `setMetaSuspend`

Both `MetadataBank.setMetaSuspend(key, value)` and `MetadataBank.deleteSuspend(key)` MUST take the per-page `getMetaMutex(key).withLock { ... }` bracket — not just `emplaceSuspend`. Without this, an `emplaceSuspend` mid-R-M-W can have its merged map clobbered by a racing `setMetaSuspend` on the same key, or resurrected by a racing `deleteSuspend`. Audit 2026-08-12 found both races in v1 of the bank; the fix is mechanical and lives in `MetadataBank.kt`. Verify any per-class `pullMetaPageKeysInto<...>` you add inherits this — the lazy-pull methods above do, because they all route through `MetadataBank.pullMetaPageKeysIntoSuspend`, which is the read-side (no lock needed).

## Common Patterns

### Build a content-classification agent (builder + scope mix)

```kotlin
// Builder: pipes
val classifier = BedrockMultimodalPipe().apply {
    setRegion("us-west-2")
    setModel(BedrockConfig.qwen235B)
    setTemperature(0.0)
    setSystemPrompt("Classify the sentiment of the input text.")
    setJsonInput(TextInput::class)
    setJsonOutput(SentimentResult::class)
    requireJsonPromptInjection()
    setPipeName("sentiment classifier")
}.init()

// Builder: pipeline
val agentPipeline = pipeline {
    add(classifier)
    add(router)
}.init()

// Scope: manifold
val builtManifold = manifold {
    defaults { bedrock(BedrockConfiguration(region = "us-east-1", model = "anthropic.claude-3-haiku")) }
    worker("sentiment-agent") {
        description("Classifies sentiment and routes to specialized response generators.")
        skill("sentiment", "Classifies text sentiment and generates sentiment-aware responses.")
        pipeline(agentPipeline)
    }
}
```

### Configure a multi-round discussion (scope only)

```kotlin
val junction = junction {
    moderator("moderator", moderatorPipeline)
    participant("security", securityPipeline)
    participant("performance", performancePipeline)
    participant("ux", uxPipeline)
    workflowRecipe(JunctionWorkflowRecipe.VOTE_PLAN_OUTPUT_EXIT)
    concurrencyMode(P2PConcurrencyMode.ISOLATED)
    killSwitch(inputTokenLimit = 50000, outputTokenLimit = 5000)
    strategy(DiscussionStrategy.ROUND_ROBIN)
    rounds(4)
    threshold(0.75)
    intervention(true)
    tracing()
}
```
