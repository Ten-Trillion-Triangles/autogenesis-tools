# TPipe API accuracy — corrections from this session

This file captures TPipe API corrections that future blog posts must not repeat. Both errors in this section were caught by Apex (Richard Wang) during the 2026-06-06 blog post sessions, so the wrong descriptions are the kinds of plausible-sounding-but-wrong content an LLM produces when writing from memory instead of source.

**The general rule: any claim about a TPipe API must be sourced from the function definition in `TPipe/src/main/kotlin/`.** The 30 seconds it takes to read the function is the difference between a correct post and a rewrite.

---

## Correction 1: `setModel` takes ONLY a string. Never an enum.

### What was wrong (the LLM's mistake)

> "`setModel` accepts either a string ID or a typed enum from `BedrockConfig` (`BedrockConfig.qwen235B`, `BedrockConfig.PalmyraX5`, etc.). Use the enum. The string version compiles fine, runs fine, then returns 404 from Bedrock at runtime and you spend an hour wondering why."

### What is actually true

`setModel` always takes a `String`. Period. The string can be either a model ID (e.g. `anthropic.claude-3-haiku-20240307-v1:0`) or a full ARN (e.g. `arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.writer.palmyra-x5-v1:0`).

The constants like `BedrockConfig.qwen235B` are **val properties on a Kotlin `object`** (a singleton). They return strings. They are NOT Kotlin enums. This is what they actually look like in `Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt`:

```kotlin
object BedrockConfig
{
    val qwen235B = "qwen.qwen3-235b-a22b-a22b-2507-v1:0"
    val PalmyraX5 = "arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.writer.palmyra-x5-v1:0"
    // ...
    init
    {
        bedrockEnv.bindInferenceProfile(qwen235B, "arn:aws:bedrock:us-west-2::foundation-model/qwen.qwen3-235b-a22b-2507-v1:0")
        bedrockEnv.bindInferenceProfile(PalmyraX5, "arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.writer.palmyra-x5-v1:0")
    }
}
```

### The real value of the constants

1. **IDE autocomplete** — `BedrockConfig.qw` autocompletes, `"qwen-2-35b"` doesn't
2. **Single source of truth** — change the model once on the config object, not by grep-and-replace across the codebase
3. **ARN binding** — `bedrockEnv.bindInferenceProfile(modelId, arn)` is called once at startup, mapping the ID to its ARN

The win is NOT compile-time type checking. There's no enum to give you that. The win is the constants are easy to type and easy to find.

### For cross-region ARN models

Two options:
- Call `bedrockEnv.bindInferenceProfile(modelId, arn)` once at startup, then pass just the model ID to `setModel`
- Pass the ARN directly to `setModel`

Either works. The bind call is cleaner because the rest of the codebase can use the short ID.

### How to describe this in a blog post

> **`setRegion` / `setModel`** — Where the inference runs and which model you hit. `setModel` always takes a string — either a model ID like `anthropic.claude-3-haiku-20240307-v1:0` or a full ARN. Save the IDs you use to constants on a config object (like `BedrockConfig.qwen235B`) so you don't have to copy-paste them. For cross-region models, call `bedrockEnv.bindInferenceProfile(modelId, arn)` first to map the ID to the ARN, or pass the ARN directly.

### Source files for verification

- `Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt` — the canonical config object
- `Autogenesis/server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt` — the canonical usage in pipe construction
- `TPipe/src/main/kotlin/Pipe/Pipe.kt` — the `setModel` function definition on the Pipe class

---

## Correction 2: `setTokenBudget` is the memory management system. Not a cap.

### What was wrong (the LLM's mistake)

> "`setTokenBudget(...)` — Hard cap on input and output tokens. TPipe's KillSwitch infrastructure uses these budgets to enforce limits — if the pipe tries to exceed the budget, the pipeline halts cleanly. Put token budgets in your config object. You will want to tune them later and you don't want a recompile."

This describes a ceiling. What `setTokenBudget` actually does is far richer.

### What is actually true

`setTokenBudget(...)` is the **activation switch for TPipe's runtime context management algorithm**. The doc comment on the function in `TPipe/src/main/kotlin/Pipe/Pipe.kt:2680` reads:

> "External setter for the token budget. Allows an advanced token budget to be assigned that will account for the system prompt, user prompt, any binary content, reasoning budget, max token budget, and any remaining context to ensure it all fits inside the context window. If assigned, the internal version of this function will be called at runtime during the critical context truncation stage."

Two phases:

**At config time** (when you call `setTokenBudget(...)`):
- Tokenizes the system prompt, max output tokens, reasoning budget, and user prompt size
- Subtracts them from the context window
- Throws if the configuration itself would overflow

**At runtime** (around `Pipe.kt:5851`, before each LLM call):
- Runs the "critical context truncation stage"
- Calls `truncateModuleContextSuspend()` which performs:
  - **Lorebook selection** — by priority or weight, based on `enableLoreBookFillMode()` or `enableLoreBookFillAndSplitMode()`
  - **Multi-page budget allocation** — splits the budget across MiniBank pages using `MultiPageBudgetStrategy` (EQUAL_SPLIT, WEIGHTED_SPLIT, PRIORITY_FILL, DYNAMIC_FILL, DYNAMIC_SIZE_FILL)
  - **Text-matching preservation** — keeps content matching user-prompt keywords before truncating the rest
  - **Truncation or compression** of whatever overflows

### The relationship to other settings

- `setTokenBudget(...)` — activates the algorithm and configures the limits (the trigger)
- `autoTruncateContext()` / `enableLoreBookFillMode()` / `enableLoreBookFillAndSplitMode()` — choose the truncation strategy
- `KillSwitch` — the hard ceiling ABOVE this layer. Halts the pipeline if tokens truly run out (OOM-equivalent)
- LoreBook / MiniBank / ContextBank — the storage layers this algorithm manages

### Apex's framing

> "It's basically like if you could turn on garbage collection in a coding language on the fly."

The memory model:
- `setTokenBudget` = the GC (manages what's in/out of context, ensures important things survive, prevents overflow)
- `KillSwitch` = the OOM killer (hard ceiling, halts the agent)
- `LoreBook` = the heap (where memory lives)
- `ContextBank` = global mutable state shared across pipes (thread-safe with `emplaceWithMutex`)

### How to describe this in a blog post

> **`setTokenBudget(...)`** — This is the memory management system, not just a cap. Calling `setTokenBudget(...)` activates TPipe's runtime context algorithm. At config time, the pipe tokenizes the system prompt, max output, reasoning budget, and user prompt size, subtracts them from the context window, and throws if the configuration itself would overflow. At runtime, before each LLM call, the pipe runs the truncation stage: lorebook selection by priority or weight, multi-page budget allocation across MiniBank pages, text-matching preservation that keeps content matching user-prompt keywords, and either truncates or compresses whatever overflows. Working with KillSwitch (the hard ceiling that halts the pipeline if tokens truly run out), this is the layer that keeps the agent from forgetting important context, drifting under pressure, or drowning in oversized context.

### Source files for verification

- `TPipe/src/main/kotlin/Pipe/Pipe.kt:2692` — `fun setTokenBudget(budget: TokenBudgetSettings) : Pipe` (with the doc comment explaining the algorithm)
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:2834` — `private fun setTokenBudgetInternal(...)` (the config-time math)
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:5851` — runtime call to `truncateModuleContextSuspend()`
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:3453` — `autoTruncateContext()` (strategy switch)
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:3508` / `:3518` — `enableLoreBookFillMode()` / `enableLoreBookFillAndSplitMode()`
- `TPipe/src/main/kotlin/Context/ContextWindow.kt` — the actual truncation logic

---

## Correction 3: `init()` loads the provider backend, not just state wiring.

### What was wrong (the LLM's mistake)

> "`init()` — Wires up internal state, validates the required config, prepares the pipe for execution. Calling execute() on an uninitialized pipe throws UninitializedComponentException with a clear message."

This describes the general contract of `init()` correctly but misses what it actually DOES in provider-specific implementations. The `UninitializedComponentException` description is the general case, but for Bedrock specifically the failure mode is different.

### What is actually true

For Bedrock pipes specifically, `init()` does four things (from `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:787-854`):

```kotlin
override suspend fun init(): Pipe
{
    super.init()  // propagate timeout settings, initialize child pipes

    // 1. Load inference profile mappings from ~/.aws/inference.txt
    bedrockEnv.loadInferenceConfig()

    // 2. Track the requested model ID
    requestedModelId = model

    // 3. Resolve model ID to inference profile ARN if configured
    if(model.isNotEmpty())
    {
        val inferenceId = bedrockEnv.getInferenceProfileId(model)
        if(!inferenceId.isNullOrEmpty())
        {
            model = inferenceId  // switch to ARN
        }
    }

    // 4. Initialize the BedrockRuntimeClient with region, credentials, HTTP timeouts
    bedrockClient = BedrockRuntimeClient {
        region = this@BedrockPipe.region
        val (accessKey, secretKey) = bedrockEnv.getKeys()
        if(accessKey.isNotEmpty() && secretKey.isNotEmpty())
        {
            credentialsProvider = StaticCredentialsProvider(Credentials(accessKey, secretKey))
        }
        httpClient(OkHttpEngine) {
            socketReadTimeout = readTimeoutSeconds.seconds
            connectTimeout = 60.seconds
        }
    }

    return this
}
```

Without `init()`, `bedrockClient` is never created. The first `execute()` throws because the provider backend is missing — NOT `UninitializedComponentException`. That exception is for the general case of skipping `init()` on pipes that don't do provider-specific initialization. For Bedrock specifically, the failure is the client being null.

### How to describe this in a blog post

> **`init()`** — Loads the provider backend and gets the LLM ready to run. For Bedrock pipes, this means loading inference profile mappings from `~/.aws/inference.txt`, resolving the model ID to an inference profile ARN, and initializing the AWS Bedrock Runtime client with credentials and HTTP timeouts. Without this call, `bedrockClient` is never created and the first `execute()` throws a runtime exception because the provider backend is missing.

### Source files for verification

- `TPipe/src/main/kotlin/Pipe/Pipe.kt:4748` — the abstract `init()` declaration with its doc comment
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:4763-4784` — `super.init()` propagation logic
- `TPipe-Bedrock/src/main/kotlin/bedrockPipe/BedrockPipe.kt:787-854` — Bedrock's `init()` override (the actual implementation)

---

## Correction 4: `enableLoreBookFillAndSplitMode()` is a strategy switch, not an activation switch.

### What was wrong (the LLM's mistake)

> "`enableLoreBookFillAndSplitMode()` — Turns on LoreBook memory injection. When the LoreBook is populated with character/location/event entries, the pipe pulls relevant entries into the prompt based on keyword triggers. Split mode also handles context overflow by summarizing + keeping the most relevant recent content rather than truncating from the end."

This misattributes what activates the memory management system. `setTokenBudget(...)` is the activation switch. This method is only a knob that adjusts strategy once the algorithm is already running.

### What is actually true

`setTokenBudget(...)` activates the runtime context algorithm. Once called, the truncation stage runs at runtime (around `Pipe.kt:5851`). The lorebook fill modes are strategy switches that tell that already-running stage HOW to allocate budget between lorebook entries and other context:

- `pipe.autoTruncateContext()` — the runtime switch that gates whether the truncation stage fires at execution time
- `pipe.enableLoreBookFillMode()` — select-and-fill: top-weighted lorebook entries selected first, remaining budget to other context
- `pipe.enableLoreBookFillAndSplitMode()` — fill mode + reserves a split budget for the rest of the top-level context window

The mental model: `setTokenBudget` = power switch. `autoTruncateContext()` = run button. `enableLoreBookFillMode()` / `enableLoreBookFillAndSplitMode()` = knobs that adjust strategy when the machine is already running.

### How to describe this in a blog post

> **`enableLoreBookFillAndSplitMode()`** — Strategy switch for the lorebook portion of the truncation stage. The truncation stage is already running because you called `setTokenBudget(...)` above; this method tells that stage to use the select-and-fill strategy for lorebook entries and reserve a split budget for the rest of the top-level context.

### Source files for verification

- `TPipe/src/main/kotlin/Pipe/Pipe.kt:3447-3468` — `autoTruncateContext()` doc comment
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:3508-3523` — `enableLoreBookFillMode()` and `enableLoreBookFillAndSplitMode()` doc comments
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:5851` — runtime call to `truncateModuleContextSuspend()`

---

## Correction 5: `BedrockConfig.generativeBudgetSettings` is a project pattern, not a TPipe feature.

### What was wrong (the LLM's mistake)

> "`setTokenBudget(BedrockConfig.generativeBudgetSettings)` — reference a preset from your config like `BedrockConfig.generativeBudgetSettings` rather than a magic number. The BedrockConfig has preset budgets for different generation strategies."

This implies `BedrockConfig.generativeBudgetSettings` is a built-in TPipe feature. It's not. It's a project-level constant in Autogenesis (and similar TPipe-built projects), defined in `Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt`. It's not part of the TPipe framework.

### What is actually true

When writing about `setTokenBudget`, always show the actual `TokenBudgetSettings` data class inline. It's at `TPipe/src/main/kotlin/Pipe/Pipe.kt:141-165`:

```kotlin
data class TokenBudgetSettings(
    var userPromptSize: Int? = null,           // default ~12K tokens
    var maxTokens: Int? = null,                // default ~20K tokens
    var reasoningBudget: Int? = null,         // default ~8K tokens
    var subtractReasoningFromInput: Boolean = false,
    var contextWindowSize: Int? = null,         // default ~32K tokens
    var allowUserPromptTruncation: Boolean = false,
    var preserveJsonInUserPrompt: Boolean = true,
    var compressUserPrompt: Boolean = false,
    var truncateContextWindowAsString: Boolean = false,
    var preserveTextMatches: Boolean = false,
    var truncationMethod: ContextWindowSettings = ContextWindowSettings.TruncateTop,
    var multiPageBudgetStrategy: MultiPageBudgetStrategy = MultiPageBudgetStrategy.DYNAMIC_SIZE_FILL,
    var pageWeights: Map<String, Double>? = null,
    var reserveEmptyPageBudget: Boolean = true
)
```

### How to describe this in a blog post

Show the actual build pattern:

```kotlin
val budget = TokenBudgetSettings().apply {
    contextWindowSize = 32_000
    maxTokens = 4_000
    reasoningBudget = 2_000
    subtractReasoningFromInput = true
    userPromptSize = 8_000
    allowUserPromptTruncation = true
    preserveJsonInUserPrompt = true
    compressUserPrompt = false
    preserveTextMatches = true
    truncationMethod = ContextWindowSettings.TruncateMiddle
    multiPageBudgetStrategy = MultiPageBudgetStrategy.DYNAMIC_SIZE_FILL
    pageWeights = mapOf("story" to 2.0, "lorebook" to 1.0)
    reserveEmptyPageBudget = false
}
pipe.setTokenBudget(budget)
```

Never claim `BedrockConfig` has preset budgets. The `BedrockConfig` singleton is project-level, not framework-level.

### Source files for verification

- `TPipe/src/main/kotlin/Pipe/Pipe.kt:141-165` — the actual `TokenBudgetSettings` data class
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:276-282` — `MultiPageBudgetStrategy` enum (EQUAL_SPLIT, WEIGHTED_SPLIT, PRIORITY_FILL, DYNAMIC_FILL, DYNAMIC_SIZE_FILL)
- `TPipe/TPipe/src/main/kotlin/Enums/ContextWindowSettings.kt` — `ContextWindowSettings` enum (TruncateTop, TruncateBottom, TruncateMiddle)
- `Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt` — where `BedrockConfig` lives (project-level, not TPipe framework)

Before publishing any TPipe blog post that mentions a pipe setting, pipe method, container behavior, or API contract:

1. Open `TPipe/src/main/kotlin/Pipe/Pipe.kt` (or the relevant file) in your editor
2. Find the function you're writing about
3. Read its doc comment AND its body
4. Write the description based on what the code actually does
5. If the description sounds clean and obvious, that's a signal it might be wrong — terse-but-correct is OK, but if it sounds too clean, double-check

The session 2026-06-06 produced two rewrites from these rules. Both rewrites took less than 5 minutes because the source code was in the same workspace. Both would have shipped as wrong content otherwise.

---

## Correction 6: Reasoning pipes are NOT part of Developer-in-the-Loop. They are a separate subsystem.

### What was wrong (the LLM's mistake)

> "The reasoning pipes are one of seven Developer-in-the-Loop intervention points in TPipe."

A confidently-stated, plausibly-sounded, completely wrong claim. Reasoning pipes and Developer-in-the-Loop pipes are two different TPipe subsystems that happen to live in the same general "intervention points" category. They are not nested. They are not variants of each other. They are not the same thing under different names.

### What is actually true

- **Reasoning pipes** (`TPipe-Defaults/src/main/kotlin/Defaults/reasoning/`) — the structured-output reasoning system. Each reasoning method (StructuredCot, ExplicitCot, processFocusedCot, BestIdea, ComprehensivePlan, RolePlay, ChainOfDraft, SemanticDecompression) has its own response data class, and the field order in the class forces the LLM through a specific reasoning chain. See `tpipe-reasoning-pipes/SKILL.md` for the full architecture.
- **Developer-in-the-Loop (DITL) pipes** (`TPipe/src/main/kotlin/.../ditl/`) — the hook-point system for inserting custom logic at specific stages of pipe execution. The DITL hooks are: Pre-Init, Pre-Validation, Pre-Invoke, Post-Generate, Validator, Transformation, On-Failure. They are about *inserting behavior*, not about *structuring output*.

### How to describe this in a blog post

> "Reasoning pipes are one of TPipe's intervention mechanisms, sitting alongside Developer-in-the-Loop pipes as a separate subsystem."

Or just talk about reasoning pipes without mentioning DITL at all. There is no reason a reasoning-pipes post needs to position itself relative to DITL. The claim "X is one of Y intervention points" only matters if Y is well-defined and X is correctly a member of Y.

### How the user caught this

> "The reasoning pipes are one of seven Developer-in-the-Loop intervention points in TPipe. (This isn't true reasoning pipes are not part of DITL they're a seperate system)"

Notice the user's directness. They didn't say "I think you might be wrong about this" or "let me check." They said "this isn't true." The user will catch factual claims like this immediately. If you're uncertain whether claim A belongs inside category B, leave the category out. The cost of being wrong about the category is a rewrite. The cost of not naming a category is zero.

---

## Correction 7: Autogenesis token counts are "billions," not specific round numbers.

### What was wrong (the LLM's mistake)

> "The third covers the Autogenesis deployment — 300 million tokens, zero human intervention, a judge that cannot be jailbroken because the reasoning pipe structure prevents the failure modes other systems are vulnerable to."

A confidently-cited round number, with a specific unit. The unit is plausible-sounding but wrong. The user has explicitly flagged this in two prior sessions and called it out again in 2026-06-13.

### What is actually true

The user said directly in 2026-06-13:

> "The amount of tokens produced by TPipe is somewhere in the billions. Way more than 300 million to the point we've honestly lost count at TTT."

The user has now said this twice. The pattern is: when claiming a specific round number for production usage of Autogenesis, do not. The honest phrasing is "billions" or "we stopped counting" or "we've lost count at TTT."

The reason this matters: the user is going to be the one to fact-check the post. If the post says "300M tokens" and the actual number is "north of 4B and we don't track it anymore," the post reads as marketing. The user has explicitly chosen "billions" / "lost count" as the framing because it is the honest framing. A specific round number is not.

### How to describe this in a blog post

For Autogenesis production claims:
- ✅ "Billions of tokens, lost count at TTT"
- ✅ "We stopped tracking the total somewhere along the way"
- ✅ "Eighteen months of production, billions of tokens processed"
- ❌ "300 million tokens"
- ❌ "1 billion tokens"
- ❌ Any specific round number

For the production history framing:
- ✅ "18+ months in production as of June 2026"
- ✅ "Production since early 2025"
- ❌ Any specific month/year as a precise launch date (the user has not given one)

The general principle: when the user says "we don't track this anymore," do not invent a number. Use the user's exact framing.

---

## Correction 8: The KillSwitch is termination architecture, not a budget cap.

### What was wrong (the LLM's mistake)

> "The KillSwitch is a token budget cap. When the pipe tries to exceed the budget, the pipeline halts cleanly."

Describes a ceiling. The actual mechanism is far more specific. The KillSwitch throws an exception that bypasses retry policies and propagation is defended by a specific catch-and-rethrow carve-out in the Splitter.

### What is actually true

The KillSwitch is the runtime safety mechanism that:

1. Is a data class at `TPipe/src/main/kotlin/P2P/KillSwitch.kt` with `inputTokenLimit`, `outputTokenLimit`, and an `onTripped` callback typed `(KillSwitchContext) -> Nothing`
2. The `Nothing` return type is Kotlin's bottom type. The compiler rejects callbacks that do not throw.
3. The default callback is `{ ctx -> throw KillSwitchException(ctx) }`. The exception is a `RuntimeException`. It is uncaught by default. The runtime propagates it.
4. **The catch-and-rethrow carve-out at `Splitter.kt:778-782`:** the Splitter has a generic `catch(e: Exception)` block that turns exceptions into "Pipeline execution failed" content, allowing the next pipeline to run. A specific `catch(e: KillSwitchException)` block sits BEFORE the generic catch and re-throws. The comment says: "KillSwitchException must never be caught — it must propagate to terminate the agent."
5. The Splitter's accumulator at `Splitter.kt:732-737` enforces the budget at the root of the call chain with accumulated totals. The limit is the operator's limit, not the agent's limit.

The mechanism is termination. The agent does not get a chance to spend what it should not. The architecture explicitly defends the propagation.

### How to describe this in a blog post

> "The KillSwitch isn't a budget cap — it's termination architecture. The agent doesn't get a chance to spend what it shouldn't, because the runtime kills the call chain before the cost accrues."

Or, more directly: the KillSwitch is an exception the runtime is explicitly designed to propagate. A budget cap is a value the agent checks. The former terminates. The latter estimates.

### Source files for verification

- `TPipe/src/main/kotlin/P2P/KillSwitch.kt` — the 66-line file, the entire implementation
- `TPipe/src/main/kotlin/Pipeline/Splitter.kt:778-782` — the catch-and-rethrow carve-out
- `TPipe/src/main/kotlin/Pipeline/Splitter.kt:732-737` — the root-down accumulator
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:7615-7647` — the `checkKillSwitch` function
- `TPipe/src/main/kotlin/Pipe/Pipe.kt:6015-6021, 6153-6158` — the call sites in the pipe execution loop
- `TPipe/src/main/kotlin/Pipeline/ManifoldDsl.kt:154-162` — the DSL builder API

Full source points and the origin story for the KillSwitch feature: `references/killswitch-source-points.md`.
