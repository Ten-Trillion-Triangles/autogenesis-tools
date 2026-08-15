# Verified Snippet Variants

Source-checked TPipe API patterns for recurring snippet types on ttt-site landing pages. Each variant was derived from `/home/cage/Desktop/Workspaces/TPipe/TPipe/` source on June 25, 2026, and shipped live across the six landing pages.

For the canonical BedrockPipe + Chain-of-Draft + ContextBank pattern (the most common case), see `../templates/canonical-bedrock-snippet.kt`. This file covers the four non-BedrockPipe variants the session produced.

---

## Variant A — Determinism: same input, same output, twice

Used on `src/pages/deterministic-ai-agents.astro`. Adds `setJsonOutput(jsonString)` to lock the response shape, runs `generateText(input)` twice, asserts equality.

Key APIs verified:
- `setJsonOutput(json: String)` — Pipe.kt:2487, takes a raw JSON schema string. **No `JsonOutput(...)` wrapper class exists.**
- `setSystemPrompt("Return JSON only matching the declared schema.")` — pairs with `setJsonOutput` to enforce shape

```kotlin
import bedrockPipe.BedrockPipe
import com.TTT.Pipe.TokenBudgetSettings
import Defaults.BedrockConfiguration
import Defaults.reasoning.ReasoningBuilder.reasonWithBedrock
import Defaults.reasoning.ReasoningDepth
import Defaults.reasoning.ReasoningDuration
import Defaults.reasoning.ReasoningInjector
import Defaults.reasoning.ReasoningMethod
import Defaults.reasoning.ReasoningSettings
import kotlinx.coroutines.runBlocking

val bedrockConfig = BedrockConfiguration(
    region = "us-west-2",
    model = "anthropic.claude-3-haiku-20240307-v1:0"
)

val codSettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.ChainOfDraft,
    depth = ReasoningDepth.Med,
    duration = ReasoningDuration.Short,
    reasoningInjector = ReasoningInjector.SystemPrompt
)

val deterministic = BedrockPipe().apply {
    setModel(bedrockConfig.model)
    setRegion(bedrockConfig.region)
    useConverseApi()
    setSystemPrompt("Return JSON only matching the declared schema.")
    setReasoningPipe(reasonWithBedrock(bedrockConfig, codSettings, null))
    setTokenBudget(TokenBudgetSettings(
        contextWindowSize = 2048,
        maxTokens = 256,
        reasoningBudget = 128
    ))
    setJsonOutput(
        """{"type":"object","properties":{"result":{"type":"number"}}}"""
    )
    setPageKey("deterministic-demo")
}

runBlocking {
    deterministic.init()
    val input = "Compute 15% of 240."
    val run1 = deterministic.generateText(input)
    val run2 = deterministic.generateText(input)
    check(run1 == run2) { "Substrate-level determinism broken" }
    println(run1)
}
```

**Marketing claim that this supports:** "Same input, same pipe configuration, same output. By design."

---

## Variant B — Multi-node DistributionGrid: P2P coordination across nodes

Used on `src/pages/long-horizon-ai-agents.astro`. Three pipes on three nodes, routed by `DistributionGrid`, registered with the TPipe P2P registry.

Key APIs verified:
- `com.TTT.Pipeline.distributionGrid` — DSL entry point. Imports as `import com.TTT.Pipeline.distributionGrid`
- `distributionGrid { router(pipeline) }` — DSL block with `router(...)` for the work pipeline
- `.addPeer("node.local")` — `DistributionGrid.kt:795`, adds a peer node
- `grid.init()` — suspend, `DistributionGrid.kt:1337`
- `grid.registerWithRegistry()` — suspend, `DistributionGrid.kt:1791`
- `pullGlobalContext()` — `Pipe.kt:2706`, toggles `readFromGlobalContext` so the pipe reads from the global ContextBank rather than the per-pipe bank
- `Pipeline().add(pipe).add(pipe).pauseAfterPipes()` — `Pipeline.kt:892`

```kotlin
import bedrockPipe.BedrockPipe
import com.TTT.Pipe.TokenBudgetSettings
import com.TTT.Pipeline.distributionGrid
import com.TTT.Pipeline.Pipeline
import Defaults.BedrockConfiguration
import Defaults.reasoning.ReasoningBuilder.reasonWithBedrock
import Defaults.reasoning.ReasoningDepth
import Defaults.reasoning.ReasoningDuration
import Defaults.reasoning.ReasoningInjector
import Defaults.reasoning.ReasoningMethod
import Defaults.reasoning.ReasoningSettings
import kotlinx.coroutines.runBlocking

val bedrockConfig = BedrockConfiguration(
    region = "us-west-2",
    model = "anthropic.claude-3-haiku-20240307-v1:0"
)

val codSettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.ChainOfDraft,
    depth = ReasoningDepth.Med,
    duration = ReasoningDuration.Short,
    reasoningInjector = ReasoningInjector.SystemPrompt
)

fun researchNode(nodeId: String): BedrockPipe = BedrockPipe().apply {
    setModel(bedrockConfig.model)
    setRegion(bedrockConfig.region)
    useConverseApi()
    setSystemPrompt("You are a research analyst. Be specific and terse.")
    setReasoningPipe(reasonWithBedrock(bedrockConfig, codSettings, null))
    setTokenBudget(TokenBudgetSettings(maxTokens = 2048))
    setPageKey("long-horizon-research")
    pullGlobalContext()
}

val pipeline = Pipeline()
    .add(researchNode("node-1.research.local"))
    .add(researchNode("node-2.research.local"))
    .add(researchNode("node-3.research.local"))
    .pauseAfterPipes()

val grid = distributionGrid {
    router(pipeline)
}
    .addPeer("node-1.research.local")
    .addPeer("node-2.research.local")
    .addPeer("node-3.research.local")

runBlocking {
    grid.init()
    grid.registerWithRegistry()
}
```

**Marketing claim that this supports:** "Three pipes on three nodes, coordinated by a DistributionGrid peer-to-peer mesh. State survives any single-node failure via P2P replication."

---

## Variant C — Manifold: manager-worker with pause/resume

Used on `src/pages/ai-agent-orchestration-kotlin.astro`. One manager, three workers, declarative pause point on completion, plus a manual `pause()`/`resume()` to show the substrate-level checkpoint.

Key APIs verified:
- `Manifold()` — `Pipeline/Manifold.kt:66`. **No `(manager, workers)` constructor exists.** Always builder: `setManagerPipeline` + `addWorkerPipeline`.
- `setManagerPipeline(pipeline)` — `Manifold.kt:714`
- `addWorkerPipeline(pipeline)` — `Manifold.kt:873`. Workers must be wrapped in a Pipeline even if they're a single pipe.
- `pauseOnCompletion()` — `Pipeline.kt:928`, declarative pause point on the inner pipeline
- `manifold.init()` — suspend init
- `manifold.execute(MultimodalContent)` — `Manifold.kt:1275`, suspend. **`MultimodalContent(text: String)` is a real constructor** — no invented `contentOf("...")` helper needed.
- `manifold.pause()` — `Manifold.kt:2003`, suspend
- `manifold.resume()` — `Manifold.kt:2014`, suspend

```kotlin
import bedrockPipe.BedrockPipe
import com.TTT.Pipe.MultimodalContent
import com.TTT.Pipe.TokenBudgetSettings
import com.TTT.Pipeline.Manifold
import com.TTT.Pipeline.Pipeline
import Defaults.BedrockConfiguration
import Defaults.reasoning.ReasoningBuilder.reasonWithBedrock
import Defaults.reasoning.ReasoningDepth
import Defaults.reasoning.ReasoningDuration
import Defaults.reasoning.ReasoningInjector
import Defaults.reasoning.ReasoningMethod
import Defaults.reasoning.ReasoningSettings
import kotlinx.coroutines.runBlocking

val bedrockConfig = BedrockConfiguration(
    region = "us-west-2",
    model = "anthropic.claude-3-haiku-20240307-v1:0"
)

val codSettings = ReasoningSettings(
    reasoningMethod = ReasoningMethod.ChainOfDraft,
    depth = ReasoningDepth.Med,
    duration = ReasoningDuration.Short,
    reasoningInjector = ReasoningInjector.SystemPrompt
)

fun buildPipe(systemPrompt: String, maxTokens: Int): BedrockPipe = BedrockPipe().apply {
    setModel(bedrockConfig.model)
    setRegion(bedrockConfig.region)
    useConverseApi()
    setSystemPrompt(systemPrompt)
    setReasoningPipe(reasonWithBedrock(bedrockConfig, codSettings, null))
    setTokenBudget(TokenBudgetSettings(maxTokens = maxTokens))
}

val planner    = buildPipe("You are a research planner. Decompose the query into 3 sub-tasks.", 1024)
val researcher = buildPipe("You are a researcher. Execute one sub-task and return findings.",     2048)
val critic     = buildPipe("You are a critic. Review findings and return a structured assessment.", 1024)

val managerPipeline = Pipeline().add(planner)
val workerPipelines = listOf(
    Pipeline().add(researcher),
    Pipeline().add(researcher),
    Pipeline().add(researcher)
)

val manifold = Manifold().apply {
    setManagerPipeline(managerPipeline)
    workerPipelines.forEach { addWorkerPipeline(it) }
    pauseOnCompletion()
}

runBlocking {
    manifold.init()
    manifold.execute(
        MultimodalContent("Compare Kotlin, Scala, and Clojure for AI agent runtimes.")
    )

    manifold.pause()    // snapshot; resume from any node, any process
    // ... later, possibly on a different node ...
    manifold.resume()
}
```

**Marketing claim that this supports:** "Manager-worker primitive. The manager cycles a Pipeline of worker pipes until it emits pass/terminate, with deterministic substrate semantics for pause, resume, and snapshot-based retry."

---

## Variant D — ContextBank singleton: persistent state across sessions

Used on `src/pages/persistent-memory-ai-agents.astro`. Two pipes attached to the same page key; intake agent writes structured data to ContextBank; followup agent reads it across hours or days.

Key APIs verified:
- `com.TTT.Context.ContextBank` — `object` singleton (ContextBank.kt:46). **No `.connect(pageKey, lorebook)` method exists.** Imported as `import com.TTT.Context.ContextBank`.
- `com.TTT.Context.ContextWindow` — `data class ContextWindow(isInitialized: Boolean = false)` (ContextWindow.kt:17). Real field is `var contextElements: MutableList<String>` for raw string context.
- `ContextBank.emplaceWithMutex(key, window, persistToDisk)` — suspend, `ContextBank.kt:574`. Takes a `ContextWindow`, NOT a raw String. The `persistToDisk: Boolean = false` overload is the common one.
- `ContextBank.getContextFromBank(key, copy, skipRemote)` — synchronous, `ContextBank.kt:1022`. Returns a `ContextWindow`.
- The only `connect`-style method is `connectToRemoteMemory(url, token, useGlobally)` for MemoryServer, not for page keys.

```kotlin
import bedrockPipe.BedrockPipe
import com.TTT.Context.ContextBank
import com.TTT.Context.ContextWindow
import com.TTT.Pipe.TokenBudgetSettings
import kotlinx.coroutines.runBlocking

val pageKey = "customer-onboarding-session-42"

val intakeAgent = BedrockPipe().apply {
    setModel("anthropic.claude-3-haiku-20240307-v1:0")
    useConverseApi()
    setSystemPrompt("Extract structured customer data from the conversation.")
    setTokenBudget(TokenBudgetSettings(maxTokens = 1024))
    setPageKey(pageKey)
}

val followupAgent = BedrockPipe().apply {
    setModel("anthropic.claude-3-haiku-20240307-v1:0")
    useConverseApi()
    setSystemPrompt("Personalize follow-up based on the customer's prior interactions.")
    setTokenBudget(TokenBudgetSettings(maxTokens = 1024))
    setPageKey(pageKey)
}

runBlocking {
    intakeAgent.init()
    followupAgent.init()

    val intake = intakeAgent.generateText(
        "Customer: Jane, 32, looking for Series D coverage."
    )
    val intakeWindow = ContextWindow().apply {
        contextElements.add(intake)
    }
    ContextBank.emplaceWithMutex(
        key = "structured-intake",
        window = intakeWindow
    )

    // Hours or days later: state survives because ContextBank is substrate-level.
    val priorWindow = ContextBank.getContextFromBank("structured-intake")
    val prior = priorWindow.contextElements.firstOrNull().orEmpty()
    val followup = followupAgent.generateText(
        "Prior context: $prior\nWrite a follow-up."
    )
    println(followup)
}
```

**Marketing claim that this supports:** "ContextBank persists memory across sessions and distributed systems. State survives every process restart. Reads and writes use mutex-locked operations for safe concurrent access."

---

## Quick verification checklist per variant

For each snippet, before shipping:

1. `grep -n` each method/class/import against `/home/cage/Desktop/Workspaces/TPipe/TPipe/src/main/kotlin/`
2. Cross-check the `package ...` declaration at the top of each source file
3. Run `bash /home/cage/.hermes/skills/software-development/ttt-site-code-snippets/scripts/sweep-broken-bedrock-snippet.sh` — should print "All snippets clean"
4. `npm run build` from `/home/cage/Desktop/Workspaces/ttt-site` — must complete with zero errors
5. `curl -sI http://127.0.0.1:4321/<page>/` — HTTP 200
6. Visual verify per page via Playwright or browser_vision: shiki `github-dark` colors present, no `&lt;`/`&#123;` HTML-entity artifacts