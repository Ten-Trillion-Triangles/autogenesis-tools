# Autogenesis 5-Named-Budget Pattern — Annotated Walkthrough

Captured 2026-06-26 from `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/`. This is the reference architecture the user keeps pointing at when talking about TPipe token budgeting.

## The pattern in one paragraph

Autogenesis defines five named `TokenBudgetSettings` instances on a single companion object (`BedrockConfig`), sized for different model families. Every pipe-construction builder in the codebase picks one of these by name when calling `.setTokenBudget(...)`. On model retry, the budget travels with the model — model swap implies budget swap. There is NO explicit summarization or trimming code; the lorebook is the user-side compensation for budget truncation, with writer-agent prompts explicitly acknowledging truncation.

## The 5 budgets — `BedrockConfig.kt:477-505`

```kotlin
// BedrockConfig.kt:477-478
val workerBudgetSettings = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 32000,
)

// BedrockConfig.kt:483-484
val generativeBudgetSettings = TokenBudgetSettings(
    maxTokens = 12000,
    contextWindowSize = 230000,
)

// BedrockConfig.kt:489-490
val novaBudgetSettings = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 990000,
)

// BedrockConfig.kt:495-496
val novaProBudgetSettings = TokenBudgetSettings(
    maxTokens = 5000,
    contextWindowSize = 285000,
)

// BedrockConfig.kt:501-502
val palmyraBudgetSettings = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 980000
)
```

## The helper — `BedrockConfig.kt:510-517`

```kotlin
private fun Pipe.applyModelBudget(modelName: String) {
    when (modelName) {
        PalmyraX5 -> setTokenBudget(palmyraBudgetSettings)
        novaModelName -> setTokenBudget(novaBudgetSettings)
        novaProModelName -> setTokenBudget(novaProBudgetSettings)
        else -> setTokenBudget(generativeBudgetSettings)
    }
}
```

This is a `Pipe` extension function on the base Pipe class — provider-agnostic. Same pattern would work for GenericOpenAIPipe targeting MiniMax.

## Per-pipe budget calls — the actual usage map

Every builder in `agent/builders/*.kt` calls `.setTokenBudget(...)` on the pipes it constructs. Selected representative examples (NOT exhaustive — see the full table in the session report at `/home/cage/Desktop/Workspaces/TPipeWriter/.hermes/plans/token-budgeting-context-gathering.md`):

| File | Line | Pipe | Budget |
|---|---|---|---|
| `writerAgent.kt` | 199 | guide pipe | `generativeBudgetSettings` |
| `writerAgent.kt` | 388 | guide branch fail | `palmyraBudgetSettings` |
| `writerAgent.kt` | 439 | selection pipe | `generativeBudgetSettings` |
| `writerAgent.kt` | 521 | selection branch | `palmyraBudgetSettings` |
| `writerAgent.kt` | 584 | writing pipe | `palmyraBudgetSettings` |
| `lorebookAgent.kt` | 89 | lorebook extraction | `generativeBudgetSettings` |
| `lorebookAgent.kt` | 145 | lorebook branch | `palmyraBudgetSettings` |
| `nemesisCreationBuilder.kt` | 139 | reasoning pipe | `novaBudgetSettings` |
| `nemesisCreationBuilder.kt` | 154 | data collection | `palmyraBudgetSettings` |
| `nemesisCreationBuilder.kt` | 265 | story analysis | `generativeBudgetSettings` |
| `commanderCreationBuilder.kt` | 48-53 | `PipeSettings` inline | `contextWindowSize=320000, maxTokens=4000` |

Pattern: **generation pipes get the big budget; fallback pipes get Palmyra; worker pipes get the small budget; reasoning pipes get Nova's huge context.**

## Budget swap on model retry — `gameplayOrchestrator.kt:2748-2763`

```kotlin
fun swapPipelineModels(pipeline: Pipeline) {
    pipeline.getPipes().forEach { pipe ->
        val modelName = pipe.getModelName()
        if (modelName == BedrockConfig.novaModelName) {
            pipe.setModel(BedrockConfig.PalmyraX5)
            pipe.setTokenBudget(BedrockConfig.palmyraBudgetSettings)
            pipe.disableReasoning()
        }
        else if(...) {
            pipe.setModel(BedrockConfig.qwen235B)
            pipe.setTokenBudget(BedrockConfig.generativeBudgetSettings)
            pipe.disableReasoning()
        }
    }
}
```

The lesson: when retrying with a different model, **always swap the budget**. Wrong budget + wrong model wastes tokens.

## Lorebook as overflow absorption

There is **no** explicit summarization/trimming code in Autogenesis. The compensation mechanism is user-side: writer-agent prompts at `writerAgent.kt:219-225`, `:531-537`, `:647-651` explicitly tell the model:

> "There is also a lorebook which contains summarized data on a keyed basis about all of the characters, places, things, and events in the story... Use any visible lorebook keys to infer about any aspect of the story that was truncated"

> "Any [chapter] that exceeds may overflow and become truncated. The story also has an internal lorebook, which holds summarized data about things which might have [been lost]"

When the budget truncates oldest chapters, the lorebook still has entity summaries. The model reconstructs from the lorebook.

## Adapting to TPipeWriter's PlusWriterPipeline

PlusWriterPipeline is much smaller than Autogenesis — it has one main writer pipe, plus lorebook and summary pipes. Suggested mapping:

| PlusWriterPipeline pipe | Suggested budget | Rationale |
|---|---|---|
| Main writer | `generativeBudgetSettings` (12K/230K) — but consider scaling down to 8K/32K | Autogenesis pattern, but PlusWriterPipeline's stories are single-chapter-per-call |
| Branch-fallback writer | `palmyraBudgetSettings` (8K/980K) | Retry fallback |
| Lorebook extraction | `workerBudgetSettings` (8K/32K) | Smaller scope — just key extraction |
| Summary | `workerBudgetSettings` (8K/32K) | Compact output |

If MiniMax-M2.7 is the only model, you can collapse to a single budget. The pattern still scales — keep one `BedrockConfig`-equivalent object (`GenericOpenAIConfig`?) in TPipeWriter that holds MiniMax-specific budgets.

## What Autogenesis DOES NOT do (so you don't accidentally copy these anti-patterns)

1. **No custom `Pipe` subclass.** Every pipe is `BedrockMultimodalPipe()` directly instantiated. The TPipe framework handles provider differentiation.
2. **No `multiPageBudgetStrategy` override.** Left at default `DYNAMIC_SIZE_FILL`.
3. **No custom `truncationMethod`.** Left at default `TruncateTop`.
4. **No token-counting in builder code.** Budgets are set, not measured. Measurement happens via `getTokenUsage()` only when needed for debugging.
5. **No per-call budget overrides.** The budget is set at construction and stays put until `swapPipelineModels()` swaps it on retry.
</content>
</invoke>