# PlusWriterPipeline per-pipe wire-up recipe

Concrete recipe for adding a new posture surface (token budget, lorebook scan surface, future policies) to every pipe in the PlusWriterPipeline. Captured from the 2026-06-26 token-budgeting + 2026-06-26 lorebook-scan-surface deployments — both followed this exact 4-step pattern.

## The 4 steps

### Step 1: Define the posture as a top-level `val` in `Builders/PlusWriterPipeline.kt`

If the posture is a complex object (e.g. `TokenBudgetSettings`), make it a top-level `val` so it can be imported by the inspector command (`/budget-info`). If it's a single method call (e.g. `useEntireContextForLoreSelection()`), skip this step — no constant needed.

```kotlin
val plusWriterPipelineBudget: TokenBudgetSettings = TokenBudgetSettings(
    contextWindowSize = 512_000,
    maxTokens = 12_000,
    // ... full Phase 2 decisions
)
```

### Step 2: Apply to every pipe in the existing forEach

Add a new line to the existing `getPipes().forEach { ... }` block at PlusWriterPipeline.kt:1554-1559. **Do not create a new apply-block.** Wire the policy before `enableComprehensiveTokenTracking()` so tracking observes it.

```kotlin
return plusWriterPipeline.apply {
    getPipes().forEach {
        it.useEntireContextForLoreSelection()    // <-- posture #1 (added 2026-06-26)
        it.setTokenBudget(plusWriterPipelineBudget)  // <-- posture #2 (added 2026-06-26)
        it.enableComprehensiveTokenTracking()
    }
    // ...
}
```

**Order rationale**: lorebook scan surface affects every call site (cheap to flip), budget depends on context window size, tracking observes everything. Earliest in the forEach = wires the policy before the executor reads it.

### Step 3: Write the failing test FIRST (RED)

Pattern: call `buildPlusWriterPipeline()`, walk every pipe via `pipe.toPipeSettings()` (NOT `getPipeSettings()` — doesn't exist), assert the new posture is set. Pair with helper-level tests that pin the underlying framework contract independently.

```kotlin
@Test
fun everyPipeHasUseEntireContextForLoreSelectionEnabled() {
    val pipeline = buildPlusWriterPipeline()
    val pipes = pipeline.getPipes()
    assertTrue(pipes.isNotEmpty())
    pipes.forEach { pipe ->
        val settings = pipe.toPipeSettings()
        assertNotNull(settings.useEntireContextForLoreSelection,
            "Pipe '${pipe.pipeName}' has no useEntireContextForLoreSelection setting")
        assertTrue(settings.useEntireContextForLoreSelection!!,
            "Pipe '${pipe.pipeName}' must have useEntireContextForLoreSelection = true")
    }
}
```

For tests that need to populate `ContextWindow.converseHistory`, the `ConverseRole` enum is in `com.TTT.Context` (not `com.TTT.Pipe`). Use:
```kotlin
import com.TTT.Context.ConverseRole
```

For tests that instantiate the pipeline, the GenericOpenAI API key requirement applies — call `GenericOpenAIEnv.setApiKey("sk-test-fake-...")` in `@BeforeAll` (companion object, `@JvmStatic`). See `tpipewriter-feature-delivery` SKILL.md anti-patterns table for the rationale.

### Step 4: Extend the inspector command to surface the new posture

If the pipeline already has an inspector command (e.g. `/budget-info`), **extend its print block** — don't spawn `/lore-scan-info`. See Surface 5 in SKILL.md for the rationale.

```kotlin
fun printBudgetInfo() {
    val b = plusWriterPipelineBudget
    println(
        """
            |PlusWriterPipeline token budget (applied to every pipe):
            |  contextWindowSize:  ${b.contextWindowSize} tokens
            |  ... (existing budget fields) ...
            |Lorebook scan surface (applied to every pipe):
            |  useEntireContextForLoreSelection: true
            |    Scans userPrompt + contextElements + converseHistory.text
            |    (helper: ContextWindow.buildLorebookScanText(userPrompt, true))
        """.trimMargin()
    )
}
```

Add new sections to the same triple-quoted string. Keep the function single-purpose: "print the full posture report for this pipeline."

## Pitfalls (verified 2026-06-26)

| Pitfall | Symptom | Fix |
|---|---|---|
| `pipe.getPipeSettings()` in test | Compile error: `Unresolved reference 'getPipeSettings'` | Use `pipe.toPipeSettings()` (the only existing accessor) |
| `import com.TTT.Pipe.ConverseRole` in test | Compile error: `Unresolved reference 'ConverseRole'` | Use `import com.TTT.Context.ConverseRole` |
| `System.setProperty("MINIMAX_API_KEY", ...)` in test | `IllegalStateException: GenericOpenAI API key is required` from `buildPlusWriterPipeline()` | Call `GenericOpenAIEnv.setApiKey("sk-test-...")` in `@BeforeAll` companion object, package `genericOpenAIPipe.env.GenericOpenAIEnv` |
| Creating a new apply-block instead of extending the existing forEach | Drift: future postures don't get applied uniformly; some pipes get the budget but not the lorebook flag | Always add to the existing `getPipes().forEach { ... }` block at PlusWriterPipeline.kt:1554 |
| Spawning `/lore-scan-info` instead of extending `/budget-info` | `/help` grows; user has multiple commands to remember for the same posture report | Extend the existing inspector command's print block |
| Forgetting the `--rerun-tasks` flag | New test class appears compiled but doesn't run | Run `./gradlew test --rerun-tasks` (unfiltered) after adding a test class |
| Reading from a running pipeline instead of importing the constant | Inspector command requires the pipeline to be built (slow, may not exist) | Import the source-of-truth `val` from `Builders/` and print it verbatim |

## Files touched by this pattern (audit checklist)

When verifying a per-pipe posture deployment, check all of:

- [ ] `src/main/kotlin/Builders/PlusWriterPipeline.kt` — top-level `val` defined (if complex posture), line added to `getPipes().forEach` block
- [ ] `src/test/kotlin/Builders/<Posture>Test.kt` — RED-then-GREEN per-pipe test using `pipe.toPipeSettings()`
- [ ] `src/main/kotlin/Shell/Shell.kt` — inspector command (`/budget-info` or new) prints the new posture; `/help` line updated if a new command was added
- [ ] `src/test/kotlin/Shell/<Command>HelpTest.kt` — `/help` mention test if a new command was added
- [ ] `docs/maestro/transcripts/<feature-slug>/` — tmux smoke test transcript captured
- [ ] Commit message includes `feat(plus-writer):` or `test(plus-writer):` prefix on the `TPipeWriter-MiniMax` branch

## Reference commits

- `beb0bcb` — `feat(plus-writer): apply 512K/12K TokenBudgetSettings to every pipe` (token budget posture)
- `0e12afd` — `feat(plus-writer): apply useEntireContextForLoreSelection to every pipe` (lorebook scan posture)
- `5ad5e97` — `feat(shell): surface lorebook scan surface in /budget-info + smoke` (inspector command extended)