# Autogenesis Pipeline Examples — Real Production Code

> **Important:** `BedrockConfig` is an **Autogenesis project-level** singleton object, NOT a TPipe framework feature. The `val` constants on it (`qwen235B`, `PalmyraX5`, etc.) return strings. `BedrockConfig.generativeBudgetSettings` is similarly a project-level constant, not a built-in TPipe preset. When writing tutorials, show the inline `TokenBudgetSettings` construction, not the `BedrockConfig` reference.

Extracted from `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt`. These are real configurations in a system that runs 100+ turn TTRPG sessions in production.

## Pattern in Use

The Autogenesis WriterAgent uses **builder pattern with `.apply { }` blocks** for all three of its pipes (guide, selection, writing). The pipes are then composed into a Pipeline which is handed to a Manifold configured with the scope DSL. This is the canonical "builder for pipes, scope for containers" pattern.

## Example 1: Guide Pipe (Builder with `.apply { }`)

The guide pipe generates structured narrative guidance for the writing pipe. Full configuration:

```kotlin
val guidePipe = BedrockMultimodalPipe().apply {
    useConverseApi()
    setRegion("us-west-2")
    setModel(BedrockConfig.qwen235B)  // val — returns String, NOT enum
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
    setReasoningPipe(BedrockConfig.authorBuilder(
        effectiveAuthorPersonality,
        depth = ReasoningDepth.High,
        duration = ReasoningDuration.Short
    ))
    setPipeName("guide pipe")
    enableLoreBookFillAndSplitMode()

    val systemPrompt = """You are a guide generation agent...""".trimMargin()
    val middlePrompt = """Your user prompt will contain...""".trimMargin()
    val context = """You have been provided with as much...""".trimMargin()

    setSystemPrompt(systemPrompt)
    setMiddlePrompt(middlePrompt)
    autoInjectContext(context)
}
```

### What This Tells You About the Builder Pattern

1. **Long configuration is normal.** Real pipes have 20+ configuration calls. The `.apply { }` block is the right shape.
2. **Configuration is conditional.** The prompts are built from variables (`systemPrompt`, `middlePrompt`, `context`) and may differ per session. The block allows local variable declarations alongside the configuration calls.
3. **JSON contract is central.** `setJsonInput`, `setJsonOutput`, and `requireJsonPromptInjection` are the type-system binding to the LLM. The Kotlin types are the contract.
4. **Memory and reasoning are first-class.** `setReasoningPipe` and `enableLoreBookFillAndSplitMode` show that pipes compose other pipes and memory systems, not just configure themselves.
5. **Naming matters.** `setPipeName("guide pipe")` — names appear in traces, logs, KillSwitch reports. The name is a sentence fragment, not an identifier.

## Example 2: Selection Pipe (Builder with branch logic)

The selection pipe is where the agent makes routing decisions. It uses the same pattern:

```kotlin
val selectionPipe = BedrockMultimodalPipe().apply {
    setRegion("us-west-2")
    setModel(BedrockConfig.qwen235B)
    setTemperature(1.0)
    setTopP(.8)
    setTokenBudget(TokenBudgetSettings().apply {
        contextWindowSize = 32_000
        maxTokens = 4_000
        reasoningBudget = 2_000
        subtractReasoningFromInput = true
    })
    setJsonInput(PlayerStoryInput::class)
    setJsonOutput(SelectionResult::class)
    setPipeName("selection pipe")
    enableLoreBookFillAndSplitMode()
    setSystemPrompt(buildSelectionSystemPrompt(stepTwo))
    // ...
}
```

## Example 3: Composition (Builder → Scope handoff)

The pipes are composed into a Pipeline:

```kotlin
val agentPipeline = Pipeline()
    .add(guidePipe)
    .add(selectionPipe)
    .add(writingPipe)
    .init()
```

The Pipeline is then handed to a Manifold (scope DSL, hypothetical — actual code may differ):

```kotlin
val builtManifold = manifold {
    defaults {
        bedrock(BedrockConfiguration(
            region = "us-east-1",
            model = "anthropic.claude-3-haiku-20240307-v1:0"
        ))
    }

    worker("writer-agent") {
        description("Composes narrative for 100+ turn TTRPG sessions.")
        skill("creative-writing", "Generates long-form narrative from player actions.")
        pipeline(agentPipeline)  // ← builder-built pipeline handed to scope DSL
    }
}
```

## Patterns That Show Up in the Wild

### Sub-pipes inside `.apply { }` blocks

```kotlin
val guidePipe = BedrockMultimodalPipe().apply {
    // ...
    setBranchPipe(BedrockMultimodalPipe().apply {
        setRegion("us-west-2")
        setModel(BedrockConfig.PalmyraX5)
        setTemperature(1.0)
        setTopP(1.0)
        // ... branch-specific config
    })
}
```

This is a common pattern: a main pipe with a specialized branch pipe. Both built with `.apply { }`, both configured in the same place.

### DITL hooks inside `.apply { }` blocks

```kotlin
val guidePipe = BedrockMultimodalPipe().apply {
    // ...
    setPreInitFunction { content ->
        Logger.debug(LogCategory.SYSTEM, "guide pipe: preInit entry")
        // pre-init work
        content
    }
    setValidatorFunction { result ->
        // validate the LLM output before passing downstream
        result.text.isNotBlank() && !result.terminatePipeline
    }
}
```

DITL hooks are configured at the pipe level. They take lambdas. They appear in the `.apply { }` block alongside the model and prompt configuration.

## Key Files to Read

- `writerAgent.kt` lines 239-560 — three pipes built with `.apply { }` blocks
- `playerAgent.kt` — the player-facing agent (similar pattern)
- `judge.kt` — the judge pipe for outcome validation
- `geoPoliticsAssessmentAgent.kt` — specialized assessment pipe

## What This Code Doesn't Show

- No scope DSL for containers in this codebase — Autogenesis uses the builder for container construction too
- No `.also { }` or `.run { }` scope functions — pure `.apply { }` throughout
- No pipe DSL — Autogenesis doesn't use `pipe { }` (which doesn't exist anyway)

## See Also

- `references/tpipe-api-accuracy.md` in the `ttt-site-blog` skill — for corrections about `setModel` (string-only), `setTokenBudget` (memory management system, not a cap), `init()` (provider backend loading), and `BedrockConfig` (project-level, not framework)