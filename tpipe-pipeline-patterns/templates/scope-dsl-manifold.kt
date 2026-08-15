// TPipe Manifold Scope DSL — Starter Template
// Copy this and modify for your multi-agent orchestrator.
// Pattern: builder for individual pipes, scope DSL for the Manifold container.

import com.TTT.Pipeline.manifold
import com.TTT.Pipeline.Pipeline
import bedrockPipe.BedrockMultimodalPipe
import bedrockPipe.BedrockConfiguration

// === BUILD YOUR PIPES WITH THE BUILDER PATTERN ===

val researchPipe = Pipeline().add(
    BedrockMultimodalPipe().apply {
        setRegion("us-east-1")
        setModel("anthropic.claude-3-haiku-20240307-v1:0")
        setTemperature(0.7)
        setSystemPrompt("You are a research agent.")
        setPipeName("research worker")
    }
).init()

val analysisPipe = Pipeline().add(
    BedrockMultimodalPipe().apply {
        setRegion("us-east-1")
        setModel("anthropic.claude-3-haiku-20240307-v1:0")
        setTemperature(0.3)
        setSystemPrompt("You are an analysis agent.")
        setPipeName("analysis worker")
    }
).init()

val writerPipe = Pipeline().add(
    BedrockMultimodalPipe().apply {
        setRegion("us-east-1")
        setModel("anthropic.claude-3-haiku-20240307-v1:0")
        setTemperature(0.9)
        setSystemPrompt("You are a writer agent.")
        setPipeName("writer worker")
    }
).init()

// === COMPOSE WITH THE SCOPE DSL ===

val builtManifold = manifold {
    // Manager pipeline: uses TPipe-Defaults to build a Bedrock-backed manager
    defaults {
        bedrock(BedrockConfiguration(
            region = "us-east-1",
            model = "anthropic.claude-3-haiku-20240307-v1:0"
        ))
    }

    // Workers: each one is a discoverable agent
    worker("research-agent") {
        description("Researches topics on demand.")
        skill("research", "Investigates the user's request.")
        pipeline(researchPipe)
    }

    worker("analysis-agent") {
        description("Analyzes data and surfaces insights.")
        skill("analysis", "Breaks down complex data.")
        pipeline(analysisPipe)
    }

    worker("writer-agent") {
        description("Composes long-form content.")
        skill("writing", "Generates narratives and reports.")
        pipeline(writerPipe)
    }

    // Optional: token budget enforcement
    killSwitch(inputTokenLimit = 100_000, outputTokenLimit = 50_000)

    // Optional: max loop iterations (default 100)
    maxIterations(50)

    // Optional: tracing for the manifold and child pipelines
    tracing { enabled() }
}

// === EXECUTE ===

suspend fun run(input: String) {
    val result = builtManifold.execute(input)
    println(result.text)
}
