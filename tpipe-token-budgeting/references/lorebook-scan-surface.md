# Lorebook Scan Surface — `useEntireContextForLoreSelection()`

Reference extracted from `TPipe/docs/api/lorebook.md` (lines 87-169), `TPipe/docs/api/pipe.md` (lines 703-707), and `TPipe/src/main/kotlin/Context/ContextWindow.kt` (lines 2278-2312). Audited 2026-06-26.

## The problem it solves

The lorebook matcher decides which entries to inject by scanning text for substring matches against entry `key` (plus `aliasKeys`, gated by `requiredKeys`). Historically it scanned **only the user prompt** (`content.text`). That misses multi-turn context:

- Character names mentioned three turns ago.
- Locations established in `contextElements` (system-injected summaries).
- Prior assistant replies that name an entity.
- Multi-turn dialogue references.

If your lorebook key is `"Silverbrook"` and the user just types `"what was here?"`, the entry misses — even though the conversation is full of Silverbrook references.

## The flag — `useEntireContextForLoreSelection()`

```kotlin
val pipe = BedrockPipe()
    .setModel("anthropic.claude-3-sonnet-20240229-v1:0")
    .useEntireContextForLoreSelection()
```

Sets `useEntireContextForLoreSelection = true` on `PipeSettings` (`Structs/PipeSettings.kt:47`).

**Default is `false`** — historical "scan user prompt only" contract preserved.

## The helper — single source of truth

`Context/ContextWindow.kt:2278-2312`:

```kotlin
fun ContextWindow.buildLorebookScanText(
    userPrompt: String,
    useEntireContext: Boolean
): String
{
    if(!useEntireContext) return userPrompt      // legacy path, byte-exact

    return buildString {
        append(userPrompt)
        if(contextElements.isNotEmpty()) {
            append('\n')
            append(contextElements.joinToString("\n"))
        }
        if(converseHistory.history.isNotEmpty()) {
            append('\n')
            append(converseHistory.history.joinToString("\n") { it.content.text })
        }
    }
}
```

### Behavior contract
- **`useEntireContext = false`** → returns `userPrompt` verbatim. Zero behavior change for un-opted-in callers.
- **`useEntireContext = true`** → concatenates `userPrompt` + `contextElements` + `converseHistory.history[*].content.text`, each block newline-joined. Empty blocks skipped, no trailing newline.
- **Order is fixed**: `userPrompt` first, then `contextElements`, then `converseHistory`.

## The 5 call sites in Pipe.kt

The lorebook.md doc states there are **five lorebook selection/truncation call sites** in `Pipe.kt`. The `useEntireContextForLoreSelection` flag flips `useEntireContext = true` for **every one of them** in that pipe's execution path. That's the key design property — it's not a per-call opt-in, it's a pipe-wide policy.

When wiring this flag into a pipeline, expect it to affect:
1. Pre-truncation lorebook selection.
2. Post-truncation re-selection.
3. Any select-and-fill paths.
4. Any split-budget paths.
5. Any auxiliary selection paths used during context window construction.

(Exact call sites vary by TPipe version — search `Pipe.kt` for `buildLorebookScanText(` and `selectLoreBookContext(` / `selectAndTruncateContext(` for the current count.)

## MiniBank per-page isolation preserved

In multi-page contexts (`MiniBank`), each page's matcher uses:
- The **shared** `userPrompt`.
- **That page's own** `contextElements` and `converseHistory` — NOT the main window's.

Per-page isolation holds even with `useEntireContext = true`. The helper is called per-page against each page's `ContextWindow`, so each page's lorebook selection sees a scan surface scoped to its own context.

## Worked example — Silverbrook

```kotlin
import com.TTT.Context.ContextWindow
import com.TTT.Context.ConverseHistory
import com.TTT.Context.ConverseRole
import com.TTT.Pipe.MultimodalContent
import com.TTT.Context.buildLorebookScanText

val contextWindow = ContextWindow()
contextWindow.contextElements.add(
    "Lyra first visited the Silverbrook archives on the eve of the autumn equinox."
)
contextWindow.converseHistory.add(
    ConverseRole.user,
    MultimodalContent("Tell me about the last time you were in Silverbrook.")
)
contextWindow.converseHistory.add(
    ConverseRole.agent,
    MultimodalContent("I remember the archives well — the dust on the southern stacks was almost gold in the lamplight.")
)

val userPrompt = "What did Lyra find in the restricted wing?"
val scanText = contextWindow.buildLorebookScanText(userPrompt, true)
// scanText:
// "What did Lyra find in the restricted wing?
// Lyra first visited the Silverbrook archives on the eve of the autumn equinox.
// Tell me about the last time you were in Silverbrook.
// I remember the archives well — the dust on the southern stacks was almost gold in the lamplight."

// With useEntireContext = false, the same call returns userPrompt unchanged:
// "What did Lyra find in the restricted wing?"
```

## Enabling on a Pipe (DSL)

```kotlin
val pipe = BedrockPipe()
    .setModel("anthropic.claude-3-sonnet-20240229-v1:0")
    .useEntireContextForLoreSelection()
```

The flag is on `PipeSettings`, which means:
- It's persisted in the same JSON envelope as other Pipe settings.
- It's snapshotted by `PipeSettingsSnapshotTest`.
- It travels with the pipe across the composite build (`TPipe` + provider-specific subprojects).

## Relationship to the lorebook-as-overflow pattern (Autogenesis)

Autogenesis relies on lorebook entries holding entity summaries that survive budget truncation. The user prompt is sparse; entity mentions accumulate in `converseHistory` and `contextElements` over the conversation.

**For the lorebook-as-overflow-absorption design to actually fire**, the selection surface must see those mentions — otherwise the entries never match, never inject, and the overflow absorption loop is broken.

If you're porting the Autogenesis pattern and your lorebook keys reference multi-turn concepts, **enable `useEntireContextForLoreSelection()` on every pipe.** Otherwise:
- Entries with multi-turn-context keys never fire.
- The lorebook stays empty under load.
- Context truncation fires WITHOUT the compensating lorebook summaries.
- The writer agent loses entity memory across turns.

## Pitfalls

| Anti-pattern | Why it bites | Fix |
|---|---|---|
| Adding `useEntireContextForLoreSelection()` per-call instead of per-pipe | Bypasses the pipe-wide policy intent; future call sites won't be covered | Use the DSL flag on the pipe builder. |
| Calling `buildLorebookScanText(...)` directly with `useEntireContext = false` | Underscores the legacy contract; defeats the purpose | Set the flag on the pipe, let the call sites read it. |
| Enabling the flag when keys fire on user-prompt-only triggers (commands, single-turn lookups) | Wastes matcher cycles on irrelevant history; can cause false-positive alias hits | Leave off unless multi-turn context references are core to your key design. |
| Forgetting MiniBank per-page isolation assumption when designing scan-text expectations | Page-level lorebook misses won't surface in a single-window test | Run lorebook tests against MiniBank fixtures, not just plain `ContextWindow`. |
| Assuming `loreBookFillMode` / `loreBookFillAndSplitMode` enable the wider scan surface | Those flags control *budget allocation*, not *selection surface* | Use `useEntireContextForLoreSelection()` for the surface concern. |

## File locations (quick reference)

| File | Role |
|---|---|
| `TPipe/docs/api/lorebook.md` | Scan Surface section (lines 87-169) |
| `TPipe/docs/api/pipe.md` | `useEntireContextForLoreSelection()` Pipe DSL section (lines 703-707) |
| `TPipe/src/main/kotlin/Structs/PipeSettings.kt:47` | `useEntireContextForLoreSelection: Boolean?` field on `PipeSettings` |
| `TPipe/src/main/kotlin/Context/ContextWindow.kt:2278-2312` | `buildLorebookScanText(userPrompt, useEntireContext)` helper |
| `TPipe/src/main/kotlin/Pipe/Pipe.kt` | 5 lorebook selection/truncation call sites (grep for `buildLorebookScanText(` and `selectLoreBookContext(`) |

## Companion TPipe concerns

- **`tpipe-pipeline-patterns`** — the builder call patterns that wrap pipe DSL flags
- **`tpipe-json-serialization`** — how `PipeSettings.useEntireContextForLoreSelection` round-trips through JSON
- **Autogenesis per-pipe-budget pattern** — see `tpipe-token-budgeting/references/autogenesis-budget-pattern.md`