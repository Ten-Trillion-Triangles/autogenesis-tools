// canonical-bedrock-snippet.kt
//
// Verified working BedrockPipe + Chain-of-Draft + ContextBank pattern for ttt-site
// marketing pages. Source-verified against
// /home/cage/Desktop/Workspaces/TPipe/TPipe/ on 2026-06-25.
//
// Drop this in place of any prior BedrockPipe snippet on landing pages or
// comparison pages. Pair with shiki syntax highlighting via
// `codeToHtml(source, { lang: 'kotlin', theme: 'github-dark' })`.

import bedrockPipe.BedrockPipe
import com.TTT.Pipe.TokenBudgetSettings
import com.TTT.Structs.PipeSettings
import Defaults.BedrockConfiguration
import Defaults.reasoning.ReasoningBuilder.reasonWithBedrock
import Defaults.reasoning.ReasoningDepth
import Defaults.reasoning.ReasoningDuration
import Defaults.reasoning.ReasoningInjector
import Defaults.reasoning.ReasoningMethod
import Defaults.reasoning.ReasoningSettings
import kotlinx.coroutines.runBlocking

fun buildKotlinReviewer(): BedrockPipe {
    val bedrockConfig = BedrockConfiguration(
        region = "us-west-2",
        model = "anthropic.claude-3-haiku-20240307-v1:0"
    )

    val pipeSettings = PipeSettings(
        temperature = 0.2,
        topP = 0.9,
        maxTokens = 1024
    )

    val reasoningPipe = reasonWithBedrock(
        bedrockConfig,
        ReasoningSettings(
            reasoningMethod = ReasoningMethod.ChainOfDraft,
            depth = ReasoningDepth.Med,
            duration = ReasoningDuration.Short,
            reasoningInjector = ReasoningInjector.SystemPrompt
        ),
        pipeSettings
    ) as BedrockPipe

    return BedrockPipe().apply {
        setModel(bedrockConfig.model)
        setRegion(bedrockConfig.region)
        useConverseApi()
        setSystemPrompt("You are a Kotlin code reviewer. Be terse, specific.")
        setReasoningPipe(reasoningPipe)
        setTokenBudget(TokenBudgetSettings(
            contextWindowSize = 4096,
            maxTokens = 1024,
            reasoningBudget = 256
        ))
        setPageKey("kotlin-review-queue")
    }
}

fun main() = runBlocking {
    val analyzer = buildKotlinReviewer().also { it.init() }
    val code = """
        fun process(items: List<String>) = items
            .filter { it.isNotBlank() }
            .map { it.trim() }
            .distinct()
    """.trimIndent()
    val result = analyzer.generateText("Review:\n$code")
    println(result)
}