# TPipe Context Budget — Field-by-Field Reference

Captured 2026-07-24 by CFR-decompiling `TPipe-1.0.0.jar` from `server/build/server-runtime/server-linux-x64/lib/`. All values are documented defaults from the JAR bytecode.

## TokenBudgetSettings fields (in declaration order)

From `com.TTT.Pipe.TokenBudgetSettings`:

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `userPromptSize` | `Integer?` | null | yes | Max size of the user prompt in tokens. If null, no user-prompt reservation. |
| `maxTokens` | `Integer?` | null | yes | Output budget (model's max generation). If null, no output reservation. **Subtracted from `contextWindowSize` in `calculateAvailableContext()`.** |
| `reasoningBudget` | `Integer?` | null | yes | Budget for reasoning-pipe output. If `subtractReasoningFromInput=true`, also subtracted from `contextWindowSize`. |
| `subtractReasoningFromInput` | `boolean` | false | no | If true, `reasoningBudget` is subtracted from input budget too. |
| `contextWindowSize` | `Integer?` | null | yes | The TOTAL context window in tokens. If null, `calculateAvailableContext()` returns 0. **This is the field that must match the model's actual context window.** |
| `allowUserPromptTruncation` | `boolean` | false | no | If true, the user prompt itself may be truncated to fit. Default is `false` (user prompt is sacred). |
| `preserveJsonInUserPrompt` | `boolean` | true | no | If true, JSON content in the user prompt is preserved through truncation. |
| `compressUserPrompt` | `boolean` | false | no | If true, the user prompt is compressed before being added to context. |
| `truncateContextWindowAsString` | `boolean` | false | no | If true, the entire context window is serialized to a string before truncation (rather than per-element). |
| `preserveTextMatches` | `boolean` | false | no | If true, the truncation algorithm preserves text segments that match the scan text. |
| `truncationMethod` | `ContextWindowSettings` | `TruncateTop` | no | The truncation strategy. `TruncateTop` = drop oldest first. |
| `multiPageBudgetStrategy` | `MultiPageBudgetStrategy` | `DYNAMIC_SIZE_FILL` | no | How the budget is distributed across lorebook pages. |
| `pageWeights` | `Map<String, Double>?` | null | yes | Per-page budget weights. Only used if `multiPageBudgetStrategy` is per-page. |
| `reserveEmptyPageBudget` | `boolean` | true | no | If true, leaves budget room for an empty page. |

## The `calculateAvailableContext()` math (read once)

```kotlin
fun calculateAvailableContext(): Int {
    if (contextWindowSize == null) return 0
    val totalWindow = contextWindowSize
    val available = totalWindow - (maxTokens ?: 0)
    if (subtractReasoningFromInput) {
        available - (reasoningBudget ?: 0)
    }
    available - (userPromptSize ?: 0)
    return available.coerceAtLeast(0)
}
```

**The formula, in order:**
1. Start with `contextWindowSize`
2. Subtract `maxTokens` (if non-null)
3. Subtract `reasoningBudget` (if `subtractReasoningFromInput=true` AND `reasoningBudget` non-null)
4. Subtract `userPromptSize` (if non-null)
5. Clamp to zero minimum

**Footgun:** if you construct a TokenBudgetSettings with only `contextWindowSize` (all other fields null), the formula returns `contextWindowSize` (the full window is treated as input budget). The `maxTokens` field is what reserves the output side; if it's null, the framework assumes the model can output unlimited tokens, which would fail at the provider.

## TruncationSettings fields

From `com.TTT.Pipe.TruncationSettings` (all knobs for token counting + context fitting):

| Field | Type | Default | Effect |
|-------|------|---------|--------|
| `countSubWordsInFirstWord` | `boolean` | false | Count sub-words in first word of the match. |
| `favorWholeWords` | `boolean` | false | Prefer whole-word matches over partial. |
| `countOnlyFirstWordFound` | `boolean` | false | Only count the first word of a match. |
| `splitForNonWordChar` | `boolean` | false | Split at non-word characters. |
| `alwaysSplitIfWholeWordExists` | `boolean` | false | If whole word exists, always split. |
| `countSubWordsIfSplit` | `boolean` | false | Count sub-words only if split. |
| `nonWordSplitCount` | `int` | 0 | Number of non-word splits. |
| `tokenCountingBias` | `double` | 1.0 | Bias factor for token counting (1.0 = no bias). |

## ContextWindowSettings enum

```java
public enum ContextWindowSettings {
    TruncateTop,    // drops OLDEST context elements first
    TruncateBottom  // drops NEWEST context elements first
}
```

**Autogenesis default is TruncateTop** (no explicit override in `BedrockConfig.kt`).

## MultiPageBudgetStrategy enum

```java
public enum MultiPageBudgetStrategy {
    DYNAMIC_SIZE_FILL  // default — fill pages up to available budget
}
```

**Autogenesis default is DYNAMIC_SIZE_FILL.** Pages are sized dynamically to fill the available budget. The lorebook system's `ContextWindow` and `MiniBank` pages share the budget dynamically.

## Autogenesis hardcoded budget values

From `server/src/main/kotlin/globals/BedrockConfig.kt:478-506`:

| Constant | maxTokens | contextWindowSize | Available | Used by |
|----------|----------:|------------------:|----------:|---------|
| `workerBudgetSettings` | 8,000 | 32,000 | 24,000 | worker / branch pipes (validator, judge, NPC) |
| `generativeBudgetSettings` | 12,000 | 230,000 | 218,000 | narrative + author pipes (writer, refinement) |
| `palmyraBudgetSettings` | 8,000 | 980,000 | 972,000 | palmyra fallback |
| `novaBudgetSettings` | 8,000 | 990,000 | 982,000 | nova 2 chat pipes |
| `novaProBudgetSettings` | 5,000 | 285,000 | 280,000 | nova Pro 300K limit with 15K slack |

## CFR decompilation recipe (the working commands)

```bash
# 1. Find the JAR
find /home/cage -name "TPipe-*.jar" 2>/dev/null | head -5
# Common location: /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/build/server-runtime/server-linux-x64/lib/TPipe-1.0.0.jar

# 2. Extract the relevant classes
JAR="/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server/build/server-runtime/server-linux-x64/lib/TPipe-1.0.0.jar"
mkdir -p /tmp/tpipe_extract
unzip -o -j "$JAR" \
  com/TTT/Pipe/TokenBudgetSettings.class \
  com/TTT/Context/ContextWindow.class \
  com/TTT/Context/ContextWindowSettings.class \
  com/TTT/Context/ContextBank.class \
  com/TTT/Context/MiniBank.class \
  com/TTT/Context/LoreBook.class \
  com/TTT/Enums/ContextWindowSettings.class \
  com/TTT/Enums/MultiPageBudgetStrategy.class \
  com/TTT/Pipe/TruncationSettings.class \
  com/TTT/Pipe/MultiPageBudgetStrategy.class \
  com/TTT/Pipe/MultiPageBudgetStrategy\$Companion.class \
  -d /tmp/tpipe_extract/

# 3. Get CFR
curl -L https://www.benf.org/other/cfr/cfr-0.152.jar -o /tmp/cfr.jar

# 4. Decompile
java -jar /tmp/cfr.jar /tmp/tpipe_extract/TokenBudgetSettings.class --outputdir /tmp/decompiled
java -jar /tmp/cfr.jar /tmp/tpipe_extract/ContextWindow.class --outputdir /tmp/decompiled

# 5. Read the decompiled Java
ls /tmp/decompiled/com/TTT/Pipe/
ls /tmp/decompiled/com/TTT/Context/
```

## What gets truncated at each context window — empirical table

Assumes avg context injection of ~106K tokens (sum of: previous turn 30K, world info 15K, player data 5K, world context 20K, local adjacency 3K, NPC data 15K, other players 5K, user prompt 3K, system prompt 10K, lorebook 3K).

| Context window | `availableContext` | Verdict |
|----------------|-------------------:|---------|
| 32K (workerBudgetSettings) | 24K | OVERFLOWS immediately at 106K injection. TruncateTop drops everything older than R5 of game history. Critical game data lost. |
| 128K (Gemma 4 4B at FLEX) | 116K | Marginal — ~10K headroom. TruncateTop drops context from previous turns when history grows past 116K (R10+). |
| 230K (generativeBudgetSettings) | 218K | ~110K headroom. Comfortable through R20+ games. |
| 980K (palmyraBudgetSettings) | 972K | Massive headroom. No realistic truncation. |

## What survives TruncateTop (in priority order)

When truncation kicks in, the LOST items are (in order of being dropped first):

1. Oldest `previous turn` history (grows with rounds)
2. Oldest `contextElements` (any non-lorebook data)
3. Oldest `world_context` (full world JSON — duplicated from world info)
4. Oldest `npc_data` (per-NPC data dumps)
5. Oldest `other_players` (per-player data dumps)
6. Oldest `local_adjacency` (graph neighbors)
7. Oldest `player_data` (active player state)

What is SHIELDED from TruncateTop:

- `loreBookKeys` entries (added via `addLoreBookEntry`) — filled first by `selectAndFillLoreBookContext`
- System prompt (filled first in prompt assembly)
- User prompt (protected by `preserveJsonInUserPrompt=true` default)
- Recent `previous turn` (last N rounds)

## The lorebook shield order

```
loresbook entries  →  system prompt  →  user prompt  →  context elements
[selectAndFill...   [pre-assembled  [preserved by   [subject to
 is called BEFORE   into the       preserveJson-   TruncateTop
 contextElement     system block]  InUserPrompt]   based on
 truncation]                                     maxTokens/available
```

So a lorebook entry with a key like "actorStats" or "worldRules" is filled in first, occupying the first portion of the available budget. The remaining budget is then used for context elements, which are subject to TruncateTop.

## The CFR companion-class issue

CFR can only decompile classes that are in its classpath. By default, it decompiles the public API surface and marks non-public methods as "Unable to fully structure code" with a null body. To get full decompilation, pass `--classpath` with the relevant JARs:

```bash
java -jar /tmp/cfr.jar \
  /tmp/tpipe_extract/ContextWindow.class \
  --classpath /home/cage/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/1.9.24/4c8613592c2c25d63cd4e1558222b5f009b1bc80f/kotlin-stdlib-1.9.24.jar
```

The companion classes for ContextWindow are deep (LoreBook, MiniBank, ConverseHistory, ContextLock, etc.) — none of which are in the standard kotlin-stdlib. The classpath approach hits diminishing returns for deep context classes. **Stick to the public API surface** (fields + simple no-dependency methods like `calculateAvailableContext`).

## Symptom-to-diagnosis table

| Symptom in production | Likely cause | Fix |
|------------------------|--------------|-----|
| LLM output missing a context detail from a few turns ago | `previous turn` truncated by TruncateTop | Move the detail into a lorebook entry |
| LLM output missing a context detail that IS lorebook-shielded | lorebook key not in scan text | Update `aliasKeys` or pick a key that appears in LLM prose |
| Pipe throws "context window exceeded" error | `contextWindowSize` is smaller than the model's actual window capacity | Update `contextWindowSize` to match the model |
| Output stops mid-sentence | `maxTokens` too low | Increase `maxTokens` (the output budget, not the input budget) |
| Output is suspiciously short or hallucinates truncated content | `userPromptSize` reservation is too high — the user prompt gets truncated | Reduce `userPromptSize` or set `allowUserPromptTruncation=true` (with caution) |
| Different pipes have wildly different context payloads | Hardcoded `contextWindowSize` in BedrockConfig.kt is being shared | Per-pipe `TokenBudgetSettings(...)` literal instead of the shared constant |
