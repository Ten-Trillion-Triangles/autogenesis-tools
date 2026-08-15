# Worked example: `calculateAvailableContext()` math

This file shows the arithmetic `TokenBudgetSettings.calculateAvailableContext()` actually performs, against three realistic MiniMax-M2.7 scenarios that PlusWriterPipeline's writer pipe would hit.

## Scenario 1: Default MiniMax-M2.7 writer, no reasoning budget

```kotlin
val budget = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 32_000,
)
budget.calculateAvailableContext()
```

Walk-through:

```
available = contextWindowSize - maxTokens
         = 32_000 - 8_000
         = 24_000
(subtractReasoningFromInput is false → skip reasoning subtraction)
available -= userPromptSize   // userPromptSize is null → no subtraction
available.coerceAtLeast(0)    // 24_000
```

**Result: 24,000 tokens available for lorebook + context elements.** With MiniMax-M2.7's `max_tokens=8000`, the writer has 24K of context for the story plus lorebook plus author/editor/treadwell prompts plus chapter history.

## Scenario 2: M2.7 reasoning model, reasoning carved from input

```kotlin
val budget = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 32_000,
    reasoningBudget = 4000,
    subtractReasoningFromInput = true,   // subtract reasoning from contextWindow, not from maxTokens
)
budget.calculateAvailableContext()
```

```
available = 32_000 - 8_000 = 24_000
available -= 4_000  (reasoning, because subtractReasoningFromInput = true)
available -= 0      (userPromptSize is null)
```

**Result: 20,000 tokens available.** Smaller because reasoning eats into input capacity. Use this when reasoning content is large and you need to budget for it explicitly.

## Scenario 3: M2.7 reasoning model, reasoning carved from maxTokens (default)

```kotlin
val budget = TokenBudgetSettings(
    maxTokens = 8000,
    contextWindowSize = 32_000,
    reasoningBudget = 4000,
    subtractReasoningFromInput = false,   // default — reasoning is part of the 8K output budget
)
budget.calculateAvailableContext()
```

```
available = 32_000 - 8_000 = 24_000
(subtractReasoningFromInput is false → skip reasoning subtraction)
available -= 0
```

**Result: 24,000 tokens available.** Same as Scenario 1 — reasoningBudget is ignored for input arithmetic; the framework assumes reasoning comes out of the maxTokens output budget. The total output is still `maxTokens = 8K`, but `reasoningBudget = 4K` of that is reserved for thinking.

## Which scenario for PlusWriterPipeline?

MiniMax-M2.7 emits `thinking_delta` blocks before `text_delta`. With `reasoningBudget = 4K` and `maxTokens = 8K`, the model has 4K for thinking + 4K for actual prose — typically enough for a 1500-2000 word chapter. If you want the model to think longer (better plot consistency, longer lorebook reasoning), bump `reasoningBudget` to 6K and `maxTokens` to 10K.

For PlusWriterPipeline with a single-chapter-per-call scope (not the multi-chapter agent loop Autogenesis runs), `Scenario 1` or `Scenario 3` (both yield 24K context) is the sweet spot. `Scenario 2` is right if your chapter is prompt-heavy (lots of lorebook + author + editor + chapter history) and reasoning-light.

## Sanity check at runtime

To verify the budget actually fires, instrument PlusWriterPipeline:

```kotlin
val writerPipe = GenericOpenAIPipe().apply {
    setApiKey(...)
    setBaseUrl("https://api.minimax.io/v1")
    setApiMode(ApiMode.OpenAI)
    setModel("MiniMax-M2.7")
    setMaxTokens(8000)
    setTemperature(0.9)
    setReasoning()  // base Pipe — flips useModelReasoning
    setReasoningConfig(ReasoningConfig(effort = "high", enabled = true))
    setTokenBudget(budget)
    // ...
}
pipeline.enableComprehensiveTokenTracking()  // CRITICAL — see skill pitfall
val result = pipeline.execute(userPrompt)
val usage = writerPipe.getTokenUsage()
println("input=${usage.inputTokens}, output=${usage.outputTokens}, total=${usage.totalInputTokens + usage.totalOutputTokens}")
// Assertion: total <= budget.contextWindowSize!! for context-bounded inputs
```

If `usage.inputTokens + usage.outputTokens` exceeds `budget.contextWindowSize`, the budget didn't fire. If both are zero, `comprehensiveTokenTracking` is missing.

## The math pitfalls

- **`reasoningBudget` is ignored when `subtractReasoningFromInput = false`.** Set it for observability only; it doesn't reduce input capacity.
- **`userPromptSize` is a hard reservation, not a soft target.** If set too low, prompts truncate. If set too high, lorebook gets squeezed.
- **`maxTokens` is BOTH the output cap AND the input reservation.** If you raise it for longer outputs, you shrink context for lorebook.
- **`reserveEmptyPageBudget = true` (default)** means MiniBank pages with no content still reserve budget. If you have a MiniBank with sparse pages, set this to `false` to reclaim the budget.
- **`truncateContextWindowAsString = true`** is fast but lossy. Default false is right for narrative content — structural preservation matters for lorebook metadata.
</content>
</invoke>