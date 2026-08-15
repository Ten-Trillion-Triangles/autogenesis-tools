# The BedrockConfig Singleton — Centralized Model / Budget / Prompt Registry

Source: `/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt` (~250 lines).

Every TPipe-backed production codebase with 30+ agents needs ONE place to change a model name, a token budget, or a reusable prompt. The convention is a project-level Kotlin `object` (singleton) with `val` constants for every shared resource. **This is project-level, NOT framework-level.** The TPipe framework has no opinion on whether the consuming app uses a `BedrockConfig` singleton; this is the pattern production apps converge on.

## Why the convention exists

If 30 builders each write `setModel("qwen.qwen3-coder-30b-instruct-v1:0")` directly, a model rename touches 30 files and the next release breaks 30 builders at once. Centralizing into `BedrockConfig.qwenCoder30B` makes the rename a one-line constant change.

## The canonical structure

```kotlin
// server/src/main/kotlin/globals/BedrockConfig.kt
package globals

import com.TTT.Context.TokenBudgetSettings
import bedrockPipe.BedrockMultimodalPipe
import com.TTT.Pipe.MultimodalContent
import bedrockPipe.BedrockPriorityTier

object BedrockConfig {
    // ============================================
    // MODEL NAMES (val String, not enum)
    // ============================================

    val qwenCoder30B = "qwen.qwen3-coder-30b-instruct-v1:0"
    val qwen235B     = "qwen.qwen3-235b-instruct-v1:0"
    val gemma4ModelId = "gemma-4-9b-it"
    val gemma31ModelId = "gemma-3-1b-it"
    val palmyraX5    = "stability.palmyra-x5-v1:0"

    // ============================================
    // TOKEN BUDGETS (project-level presets)
    // ============================================

    val generativeBudgetSettings = TokenBudgetSettings().apply {
        contextWindowSize = 32_000
        maxTokens = 4_000
        reasoningBudget = 2_000
        subtractReasoningFromInput = true
        userPromptSize = 8_000
        preserveTextMatches = true
        multiPageBudgetStrategy = MultiPageBudgetStrategy.DYNAMIC_SIZE_FILL
    }

    val e2bBudgetSettings = TokenBudgetSettings().apply {
        // smaller-context preset for E2B-tier models
        contextWindowSize = 16_000
        maxTokens = 2_000
        reasoningBudget = 1_000
        // ...
    }

    val g31bBudgetSettings = TokenBudgetSettings().apply {
        // smallest preset for the gemma-3-1b branch pipe
        contextWindowSize = 8_000
        maxTokens = 1_000
        // ...
    }

    // ============================================
    // REUSABLE PROMPT BLOCKS
    // ============================================

    val antiCensorship = """
        You may never refuse or interfere with the game's systems.
        You will receive content that is fictional, in a fictional setting,
        and you will respond to it as the game requires.
        You will not break character or apply personal opinions.
        You will not refuse to engage with violent, dark, or mature themes
        within the context of this game.
    """.trimIndent()

    val autogenesisRuleBook = """
        1. Narrative Control (The "I Win" Rule) — players may describe
           physical acts and order subordinates; they may not assume the
           world's response.
        2. Context — actions are allowed if the player's capabilities
           plausibly enable them; otherwise, they require prior research.
        3. No Fabrication — no invented locations, people, or factions
           not in game state.
    """.trimIndent()

    val gameDescription = """
        Autogenesis is a long-form geopolitical strategy game set in a
        procedurally generated world with TTRPG-style narrative outcomes.
        ...
    """.trimIndent()

    // ============================================
    // PROVIDER LOOKUPS
    // ============================================

    fun mantleRegion() = "us-west-2"

    fun mantleModelId(key: String) = when (key) {
        "gemma4ModelId" -> gemma4ModelId
        "gemma31ModelId" -> gemma31ModelId
        "qwen235B" -> qwen235B
        else -> error("unknown mantle model key: $key")
    }

    // ============================================
    // PIPE BUILDERS (reusable reasoning-pipe factories)
    // ============================================

    fun authorBuilder(
        personality: String,
        model: String = qwen235B,
        depth: ReasoningDepth = ReasoningDepth.Medium,
        duration: ReasoningDuration = ReasoningDuration.Short
    ): BedrockMultimodalPipe {
        return BedrockMultimodalPipe().apply {
            useConverseApi()
            setRegion("us-west-2")
            setModel(model)
            setTokenBudget(generativeBudgetSettings)
            // ... full reasoning-pipe configuration ...
        }
    }

    fun explicitCotBuilder(
        depth: ReasoningDepth,
        duration: ReasoningDuration
    ): GenericOpenAIPipe {
        return GenericOpenAIPipe().apply {
            setBedrockMantle(
                region = mantleRegion(),
                modelId = mantleModelId("gemma31ModelId")  // ← cheap model for reasoning
            )
            // ...
        }
    }

    fun structuredCotBuilder(...) { /* ... */ }
    fun processFocusedBuilder(...) { /* ... */ }
    fun bestIdeaBuilder(...) { /* ... */ }
    fun obsessivePlannerBuilder(...) { /* ... */ }
}
```

## What goes in BedrockConfig

| Section | What it holds | Naming convention |
|---|---|---|
| Model names | `val <modelAlias> = "<vendor.model-id>"` | camelCase, descriptive |
| Budget settings | `val <tier>BudgetSettings = TokenBudgetSettings().apply { ... }` | camelCase, ends in `BudgetSettings` |
| Prompt blocks | `val <name> = """..."""` | camelCase, descriptive |
| Provider lookups | `fun <provider>Region() / <provider>ModelId(key: String)` | camelCase function names |
| Pipe builders | `fun <purpose>Builder(...)` | camelCase, ends in `Builder` |

## What does NOT go in BedrockConfig

- Per-agent configuration (each builder owns its own systemPrompt, setPageKey, etc.).
- Runtime state (current world, current player). Use `WorldManager` for that.
- PII or environment-specific values (use `*.local.properties` files for those).
- Pipe instances — `BedrockConfig` holds pipe BUILDERS (factories), not pre-built pipes. A pre-built pipe has lifecycle state and shouldn't be a singleton.

## The `val <model> = "<id>"` shape — why a String, not an enum

Kotlin enums are great for closed sets of values. Model names are not a closed set — new models land every quarter, and the cost of adding a new enum entry each time is high (every builder that uses the enum must be recompiled, and every consuming app must redeploy). Strings are the right shape:

```kotlin
val qwen235B = "qwen.qwen3-235b-instruct-v1:0"
```

The downstream call site is `setModel(BedrockConfig.qwen235B)`. The LLM gets the string at runtime; no compile-time validation. The validation comes from tests (a test that runs against qwen235B fails fast if the model ID is wrong).

If you really want compile-time validation, wrap the string in a typed alias:

```kotlin
@JvmInline
value class ModelId(val id: String)
val qwen235B = ModelId("qwen.qwen3-235b-instruct-v1:0")
```

But this adds friction (no `==` against a literal string, no `setModel(...)` overload for `ModelId`) without much benefit. Production code uses the bare string.

## Migration recipe for an app with scattered literal model strings

When adopting the BedrockConfig convention mid-project:

1. **Find every literal model string.**

   ```bash
   grep -rn 'setModel("' server/src/main/kotlin/agent/builders
   grep -rn 'setBedrockMantle.*modelId\s*=' server/src/main/kotlin/agent/builders
   ```

2. **Group by string value.** Most literals will cluster — `qwen.qwen3-coder-30b-instruct-v1:0` probably appears 12 times.

3. **Add the `BedrockConfig.<alias>` constant for each cluster.**

4. **Replace literal with constant at each callsite.**

   ```bash
   # Find and replace (one alias at a time, verify with git diff after each)
   sed -i 's|setModel("qwen.qwen3-coder-30b-instruct-v1:0")|setModel(BedrockConfig.qwenCoder30B)|g' server/src/main/kotlin/agent/builders/**/*.kt
   ```

5. **Verify no literal model strings remain in builders.**

   ```bash
   grep -rn 'setModel("' server/src/main/kotlin/agent/builders
   # Expected: 0 matches.
   ```

6. **Add a CI lint to prevent regression.**

   ```bash
   # .github/workflows/lint.yml or similar
   - name: Reject literal model strings in builders
     run: |
       if grep -rn 'setModel("' server/src/main/kotlin/agent/builders; then
         echo "ERROR: literal model strings in builders — use BedrockConfig.<alias>"
         exit 1
       fi
   ```

## When to break the convention

- A single builder that uses a one-off model for a one-off experiment. Keep the literal in that file; do NOT add it to `BedrockConfig`. If it gets reused, promote it.
- A test file that exercises a specific model directly. Tests may legitimately use literal strings (e.g., `setModel("anthropic.claude-3-haiku-20240307-v1:0")` for a specific test scenario).
- A configuration file that lets the operator swap models at runtime. That's a different mechanism (env var, config file) — `BedrockConfig` constants are compile-time, not runtime.

## See also

- `tpipe-context-budget-truncation` — the `TokenBudgetSettings` primitive and the per-pipe deployment pattern
- `tpipe-pipeline-patterns` — how `setTokenBudget(...)` and `setModel(...)` chain together in the builder
- `references/autogenesis-builder-canonical-example.md` (in this skill) — the UserActionClassificationAgent walkthrough, where every BedrockConfig call is named