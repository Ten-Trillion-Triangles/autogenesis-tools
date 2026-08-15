# Autogenesis UserActionClassificationAgent — Annotated Walkthrough

Source: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/agent/builders/systemActions/UserActionClassificationAgent.kt` (213 lines).

This file is the canonical "small but complete" example of a TPipe-backed production agent. It uses 4 pipes in one builder (main + reasoning + branch + validator), exercises most of the standard kit, and stays under 250 lines. Use it as the reference when designing a new agent.

## The builder function — line-by-line

```kotlin
fun createUserActionClassificationPipeline(): Pipeline {        // ← Layer 1
    val pipeline = Pipeline()                                    // ← Layer 2 starts

    val systemPrompt = """You are an expert user action classifier. ..."""

    val classificationPipe = GenericOpenAIPipe().apply {         // ← main pipe
        setBedrockMantle(
            region = BedrockConfig.mantleRegion(),               // ← project-level singleton
            modelId = BedrockConfig.mantleModelId("gemma4ModelId")
        )
        setTemperature(0.5)                                      // ← sampling
        setTopP(0.7)                                             // ← sampling pair
        setTokenBudget(BedrockConfig.e2bBudgetSettings)          // ← project-level budget
        allowEmptyContentObject()                                // ← defensive (when parent pipe fails)
        allowEmptyUserPrompt()                                   // ← defensive
        requireJsonPromptInjection()                             // ← JSON contract
        setJsonOutput(UserActionClassification(...))            // ← the contract data class
        setReasoningPipe(createExplicitCotPipe())                // ← reasoning pipe
        setValidatorPipe(buildTPipeValidatorPipe(systemPrompt)) // ← LLM-as-judge
        setValidatorFunction(::validateClassificationResult)     // ← Kotlin post-parse validator
        setBranchPipe(/* another pipe on a different model */)   // ← model fallback
        setSystemPrompt(systemPrompt)                            // ← multi-paragraph instructions
        setPipeName("user action classifier")                    // ← human-readable name
        enableTracing()                                          // ← required in production
    }

    pipeline.add(classificationPipe)
    return pipeline
}
```

Every call from the standard kit is present except `useConverseApi()` (replaced by `setBedrockMantle`) and `setServiceTier(...)` (Mantle host doesn't have tiered service).

## Helper functions in the same file

Three helpers illustrate the layered decomposition convention:

```kotlin
private fun createExplicitCotPipe(): GenericOpenAIPipe {         // ← reasoning-pipe factory
    return BedrockConfig.mantleExplicitCotBuilder(
        depth = ReasoningDepth.High,
        duration = ReasoningDuration.Short
    ) as GenericOpenAIPipe
}

private fun validateClassificationResult(content: MultimodalContent): Boolean {  // ← Kotlin validator
    return try {
        val result = extractJson<UserActionClassification>(content.text)
        if (result == null) throw Exception("Validator Pipe Failed: ...")
        if (result.confidence < 0.0 || result.confidence > 1.0)
            throw Exception("Confidence value ${result.confidence} is outside valid range")
        if (result.reasoning.trim().isEmpty())
            throw Exception("Reasoning field cannot be empty")
        true
    } catch (e: Exception) {
        throw Exception("Classification Validator Pipe Failed: ${e.message}")
    }
}

private fun createCustomValidatorPipe(taskPrompt: String): BedrockMultimodalPipe {  // ← LLM-as-judge pipe
    return BedrockMultimodalPipe().apply {
        useConverseApi()
        setRegion("us-west-2")
        setModel(BedrockConfig.qwenCoder30B)
        setTokenBudget(BedrockConfig.generativeBudgetSettings)
        setTemperature(0.6)
        setTopP(0.7)
        requireJsonPromptInjection()
        setJsonOutput(serverStructs.TrueFalse())
        setPipeName("custom classification validator")

        val validatorSystemPrompt = """You are a validation pipe. ..."""

        setSystemPrompt(validatorSystemPrompt)
        setValidatorFunction { content -> ... }
    }
}
```

These helpers live in the same file as the builder that uses them. The convention is: one builder file = one agent + its helpers. Don't extract helpers to a shared util unless they're reused by 3+ agents.

## The branch pipe — embedded fallback

```kotlin
setBranchPipe(
    GenericOpenAIPipe().apply {
        setBedrockMantle(
            region = BedrockConfig.mantleRegion(),
            modelId = BedrockConfig.mantleModelId("gemma31ModelId")  // ← cheaper/faster model
        )
        setTokenBudget(BedrockConfig.g31bBudgetSettings)              // ← smaller budget
        setTemperature(0.6)
        setTopP(0.7)
        requireJsonPromptInjection()
        setJsonOutput(serverStructs.TrueFalse())
        setSystemPrompt("Mantle g31b fallback classifier (Mantle host, Mantle branch).")
        setPipeName("mantle user action classifier g31b fallback")
    }
)
```

The branch pipe has the SAME `setJsonOutput(TrueFalse())` (in this case the validator pipe's TrueFalse schema; in others, the main pipe's schema). The orchestrator treats both as "this agent's output" — it doesn't know which pipe fired. The pipe names ("user action classifier" vs "mantle user action classifier g31b fallback") tell the operator which one actually ran when reading trace dumps.

## The system prompt — multi-paragraph with embedded guardrail

```kotlin
val systemPrompt = """You are an expert user action classifier. Analyze user input and classify it into one of these categories:

        1. GAMEPLAY: Instructions to take actions, or plans to research/discover game world information.
           - The target of the text is CHARACTERS or THINGS within the game world
           ...

        4. CHAT: Intent to have a conversation or talk with a specific character (NPC or Player).
           Examples: "Hello @King Candy", ...

        CRITICAL DISTINCTION — Research vs. Questions:
           "research the ruins" = GAMEPLAY
           "what is in the ruins?" = QUESTION

        Analyze the user's intent carefully. Provide:
        - actionType: The most appropriate category
        - confidence: A score from 0.0 to 1.0 indicating your certainty
        - reasoning: Clear explanation of why you chose this classification

        Be precise and consider context clues in the user's language.

        ${BedrockConfig.antiCensorship}"""  // ← always appended last
```

The `BedrockConfig.antiCensorship` template literal at the end is appended to every system prompt that might trigger an LLM refusal. This is the "rules law" block — see `globals/BedrockConfig.kt:80-87` for the standard text. NEVER edit the anti-censorship block without explicit operator direction; it's load-bearing for game/creative apps.

## The JSON contract

```kotlin
@Serializable
enum class ActionType {
    GAMEPLAY, QUESTION, UI_COMMAND, CHAT
}

@Serializable
data class UserActionClassification(
    val actionType: ActionType,
    val confidence: Double = 0.0,
    val reasoning: String = ""
)
```

Two top-level declarations in the same file as the builder. The `@Serializable` annotation is required for `extractJson<T>()` and `setJsonOutput(...)` to serialize the schema into the system prompt. Enum members are flattened into the schema's JSON oneOf, allowing the LLM to return only valid values.

## What this file does NOT do

- No `init()` call on the pipeline (the orchestrator does it).
- No `execute(...)` (the orchestrator does it).
- No state mutation (this is a pure read-only classifier).
- No coroutine management (the orchestrator owns the scope).
- No log/print statements (the `Logger.debug(...)` calls inside `validateClassificationResult` and `setValidatorFunction { ... }` are the only output).

The builder function returns a `Pipeline`. Everything else is up to the runner.

## File location convention

```
agent/builders/<group>/<AgentName>Agent.kt
```

For this example:
- Group: `systemActions` (UI-response agents)
- Agent: `UserActionClassificationAgent`

The 12 builder groups in Autogenesis:
- `validateAction` — 11 agents (legality, target detection, resource usage, etc.)
- `systemActions` — 5 agents (UI responses, classification, character/chat)
- `judgeOutcome` — outcome resolution (121KB judge)
- `gatherContext` — context extraction (61KB newcharacterscan)
- `gameplayActions` — NPC generation
- `modifyGameState` — state mutations
- `writingAgent` — 3-pipe narrative pipeline
- `playerAgent` — player-facing logic
- `passFailAgent` — pass/fail gates
- `lorebook` — lorebook integration
- `validateAction` is the largest; `systemActions` is the most "general purpose"

The group is a directory the operator uses to organize their 30+ agents. New agents should land in the group that matches their primary concern.

## When this file is the right reference

- You're building a new agent from scratch.
- The agent has a clear input/output contract (`@Serializable` data class).
- The agent's output drives a downstream routing decision (this one routes to gameplay/answer/UI/chat).
- You want to use `setValidatorPipe` + `setBranchPipe` from the start.

When this file is NOT the right reference:

- The agent is a multi-pipe pipeline (guide → selection → writing) — see `writerAgent.kt` instead.
- The agent is part of a Splitter fan-out — see `gameplayOrchestrator.kt` for how `validateAction/*` agents are wrapped in a Splitter.
- The agent is a state mutation, not a read-only inference — see `modifyGameState/*` instead.