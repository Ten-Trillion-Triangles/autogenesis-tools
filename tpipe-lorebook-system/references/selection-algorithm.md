# Lorebook Selection Algorithm - The 9-Stage Pipeline

Source: `src/main/kotlin/Context/ContextWindow.kt`. Every stage runs in BOTH the sync `selectLoreBookContext`/`selectAndFillLoreBookContext` chain and the `_Suspend` chain. The only difference between chains is which lock-check is called (`canSelectLoreBookKey` vs `canSelectLoreBookKeySuspend`).

This document captures the actual flow with code-line references for each stage. Total algorithm lives at `ContextWindow.kt:64-642` (selection pair) plus `ContextWindow.kt:1940-1965` (converse-history variant) plus `ContextWindow.kt:2280-2312` (scan-text builder).

## Stage 1 - `findMatchingLoreBookKeys(text)`

**Sync:** `ContextWindow.kt:64-94` | **Suspend:** `ContextWindow.kt:103-129`

For each `(key, loreBook)` in `loreBookKeys`:
1. Lowercase both the input `text` once (line 66).
2. If `text.contains(key.lowercase())` -> check `canSelectLoreBookKey(key)` -> if true add to `matchingKeys` set.
3. Then for every `alias` in `loreBook.aliasKeys`: if `text.contains(alias.lowercase())` -> check the same lock gate -> if true add.

Returns `matchingKeys.toList()`. The set dedupes main-key vs alias-key double-adds.

**Edge case - alias miss for case:** Aliases compared lowercase-to-lowercase. If your `aliasKeys` contains `"SpellBook"` but no `key.lowercase() == "spellbook"`, calling `addLoreBookEntry("Spellbook", ...)` re-adds the lowercase variant implicitly. If `aliasKeys` is hand-crafted with mixed case, only `alias.lowercase()` is checked - so capitalization in the match text doesn't matter (the text is also lowercased).

## Stage 2 - BFS expansion of `linkedKeys`

`ContextWindow.kt:208-232` (sync) | `:336-356` (suspend)

Start: `toProcess = matchingKeys`, `expandedKeys = emptySet()`.

Loop:
- Pop next `currentKey` from `toProcess`.
- If not yet in `expandedKeys`:
  - Add to `expandedKeys`.
  - For each `linkedKey` in `loreBookKeys[currentKey]?.linkedKeys`:
    - If `loreBookKeys.containsKey(linkedKey)` AND not in `expandedKeys`: enqueue.

**Why a Set-based cycle guard:** the same `linkedKey` referenced from two different entries would otherwise double-process. The `expandedKeys.contains` early-returns both. **Cost is O(edges)** across the linked-key graph, NOT O(vertices). Deep chains (10 hops) are fine; star configurations (one entry linking to 100) cost 100 enqueues.

**No bound on links per entry:** if you build a key with `linkedKeys = ["a","b","c",..."z"*100]`, the cost is bound by your lorebook size, not by a per-entry cap.

## Stage 2.5 - Dependency satisfaction promotion

`ContextWindow.kt:235-258` (sync) | `:358-378` (suspend)

After BFS, for every entry NOT in `expandedKeys` that has non-empty `requiredKeys`:
- For each `requiredKey`, check whether ANY of these is satisfied:
  - `expandedKeys.contains(requiredKey)`, OR
  - any `expandedKeys` member has `aliasKeys.contains(requiredKey)` (any matched key's aliases list it), OR
  - `requiredKey`'s own `aliasKeys` contains any `expandedKey` (the required key's aliases match something we have).
- If ALL `requiredKeys` satisfied -> add the entry to `dependencyEligibleKeys`.

This is the inverse of `checkKeyDependencies`. This stage **promotes** entries whose deps are now fully covered; stage 3.5 **filters** them at the candidate step.

**Why two passes:** the promotion and filter logic look similar but answer different questions. Promotion says "do I now qualify?"; filter says "given the existing selection, do I qualify?". Different timing.

## Stage 3 - `countAndSortKeyHits(hitKeys)`

`ContextWindow.kt:136-138`

`hitKeys.groupingBy { it }.eachCount().toList().sortedByDescending { it.second }` -> `List<Pair<String, Int>>`.

This counts how many times each key appeared in the matched list. Used at stage 4 as the `hitCount` tiebreaker. If `"fireball"` matched as both a primary key AND an alias of another entry, it lands twice in `hitKeys` -> count 2.

## Stage 3.5 - `checkKeyDependencies(matchedKeys)`

`ContextWindow.kt:148-175` (private)

Returns `Map<String, Boolean>` where each key is a lorebook key and the value is whether its `requiredKeys` are satisfied by `matchedKeys`.

Empty `requiredKeys` -> always true.

Non-empty: each `requiredKey` is satisfied by ANY of:
- `matchedKeys.contains(requiredKey)`, OR
- some `matchedKey == requiredKey` (which is the same condition spelled differently - redundant with the above; an artifact), OR
- `loreBookKeys[matchedKey]?.aliasKeys?.contains(requiredKey) == true`, OR
- `loreBookKeys[requiredKey]?.aliasKeys?.contains(matchedKey) == true`.

**Bidirectional alias resolution.** If entry-A requires `"fireball"` and entry-B is matched (not entry-A's key, but entry-B has `aliasKeys.contains("fireball")`), that's sufficient. Conversely, if entry-A requires `"fireball"` and entry-A's own `requiredKeys` check looks at the matched set member `"Fireball"`, that member's `aliasKeys.contains("fireball")` may or may not be true (depends on if the entry added `"fireball"` as an alias). The dual checks catch both directions.

## Stage 4 - Build candidate triples

`ContextWindow.kt:269-280`

```kotlin
val candidates = loreBookKeys.filter { (key, _) -> key in eligibleKeys }
    .map { (key, loreBook) ->
        Triple(key, loreBook, keyHitCounts[key] ?: 0)
    }
    .filter { (key, _, _) -> canSelectLoreBookKey(key) }
    .sortedWith(compareByDescending<Triple<String, LoreBook, Int>> { it.second.weight }
        .thenByDescending { it.third })
```

**Three choke points for locks in this single stage:**
1. `key in eligibleKeys` - dependency check filter.
2. `.filter { (key, _, _) -> canSelectLoreBookKey(key) }` - lock check.
3. The sort happens AFTER the lock filter. A locked entry never makes it to the sort.

`eligibleKeys` = `dependencyEligibleKeys` filtered by `checkKeyDependencies(dependencyEligibleKeys)`.

## Stage 5 - Token-budget packing

`ContextWindow.kt:282-302`

```kotlin
for((key, loreBook, _) in candidates)
{
    val valueTokens = Dictionary.countTokens(
        loreBook.value, countSubWordsInFirstWord, favorWholeWords,
        countOnlyFirstWordFound, splitForNonWordChar, alwaysSplitIfWholeWordExists,
        countSubWordsIfSplit, nonWordSplitCount, tokenCountingBias
    )
    if(usedTokens + valueTokens <= maxTokens)
    {
        selected.add(key)
        usedTokens += valueTokens
    }
}
```

Returns `selected: List<String>` of lorebook keys in priority order, sorted by `(weight desc, hitCount desc)`.

**Greedy fail, not partial-pack:** an entry whose `valueTokens` doesn't fit is skipped entirely. No way to truncate `loreBook.value` mid-string to fit a tighter budget. See SKILL pitfall #9.

## Stage 6 - Converse-history-driven selection

`ContextWindow.kt:1940-1965`

```kotlin
fun selectConverseHistoryLoreBookContext(maxTokens: Int, ...): List<String>
{
    val conversationText = extractConverseHistoryText()
    return selectLoreBookContext(conversationText, maxTokens, ...)
}
```

`extractConverseHistoryText()` (search `ContextWindow.kt` for the function name) builds a single string from `converseHistory.history[].content.text`. Then delegates to the same 9-stage pipeline.

**Use case:** the user prompt alone doesn't reference any keys, but the conversation history does. This selector catches that case WITHOUT requiring `useEntireContext=true` on the main flow.

## Stage 6.5 - The opportunistic-fill variant

`ContextWindow.kt:446-533` (sync) | `:549-642` (suspend)

Two-pass:
1. Run `selectLoreBookContext` -> `priorityKeys`.
2. For each candidate key NOT in `priorityKeys`, sorted descending by weight (no hitCount tiebreaker in fill):
   - Re-evaluate `checkKeyDependencies(selectedSet)` with the SO-FAR selected set.
   - If dependencies satisfied AND tokens fit -> add.

The dependency re-check is per-iteration, meaning a fill candidate whose deps ARE satisfied by priority keys BUT NOT by other fills added so far might be skipped. The dependency state shrinks as fills accumulate.

**Why re-check:** fills may add new dependencies that were not in priority. The contract is "after each fill, the running set must still be self-consistent". This is the same model as a circuit breaker - it can reset as the system grows.

## Stage 7 - Settings wrappers (TruncationSettings)

`ContextWindow.kt:647-720`

Four variants - 1) `selectLoreBookContextWithSettings`, 2) `…Suspend`, 3) `selectAndFillLoreBookContextWithSettings`, 4) `…Suspend`.

These unpack `TruncationSettings` (defined in `src/main/kotlin/Pipe/TruncationSettings.kt`) and forward to the canonical functions. No new logic. Just a builder-friendly convenience.

The 9 knobs are:

| Knob | Effect |
|------|--------|
| `countSubWordsInFirstWord: Boolean = true` | Treat subword units as count-able in the first word. |
| `favorWholeWords: Boolean = true` | Prefer whole words over subwords when tokenizing. |
| `countOnlyFirstWordFound: Boolean = false` | Only count first occurrence of each word. |
| `splitForNonWordChar: Boolean = true` | Split on non-word chars. |
| `alwaysSplitIfWholeWordExists: Boolean = false` | Always split when whole word exists. |
| `countSubWordsIfSplit: Boolean = false` | Count subwords after splitting. |
| `nonWordSplitCount: Int = 4` | Chars per token for non-word splits. |
| `tokenCountingBias: Double = 0.0` | Multiplier on the count. |

These are for `Dictionary.countTokens` heuristic, NOT for any LLM-specific tokenizer. TPipe approximates OpenAI-style BPE with a tunable heuristic.

## Stage 8 - The scan-text builder (extension function)

`ContextWindow.kt:2278-2312`

```kotlin
fun ContextWindow.buildLorebookScanText(
    userPrompt: String,
    useEntireContext: Boolean
): String
```

When `useEntireContext=false`: returns `userPrompt` unchanged (legacy behavior).

When `useEntireContext=true`: returns `buildString { append(userPrompt); if(contextElements.isNotEmpty()) { append('\n'); append(contextElements.joinToString("\n")) }; if(converseHistory.history.isNotEmpty()) { append('\n'); append(converseHistory.history.joinToString("\n") { it.content.text }) } }`.

**The scan surface is what gets matched.** With `useEntireContext=true`, a 5,000-token chapter in `converseHistory.history` becomes part of the matched text. EVERY lorebook key whose `value` is shorter than the scan text AND references any word/phrase in the chapter will fire.

If you have any lorebook entries with intentionally broad keywords (like "the" or "and"), `useEntireContext=true` will activate them on every turn. Don't enable it without auditing your lorebook for keyword collisions.

## Stage 9 - LoreBook rendering (the consumer side)

`ContextWindow.kt:2169-2194` (and surroundings)

`cleanLorebook(bannedChars, replaceBannedCharWith)` is the LLM-output sanitizer. It:
1. Deep-copies `loreBookKeys`.
2. Clears the original.
3. For each entry, replaces banned chars (comma-space delimited list) in key.
4. Sets `loreBookValue.key = loreBookKey`.
5. Re-adds via `addLoreBookEntryWithObject`.

Some implementations call `cleanLorebook` BEFORE `addLoreBookEntry` returns control to the lorebook-aware flow (i.e. right after a lorebookAgent creates entries). Most don't - the `cleanLorebook` pattern is documented but not auto-invoked.

## Common LLM-output lorebook pitfalls

When an LLM emits lorebook entries (e.g. via PumpStation's `lorebookAgent` magic contract), watch for:
- **Trailing punctuation:** `"fireball,"` -> won't match `"fireball"` substring. `cleanLorebook(",", "")` fixes.
- **Plural/singular mismatch:** `"fireballs"` -> matches `"fireball"` (substring match, not word-bounded). The opposite case (`"fireball"` substring in `"fireballs"`) also matches - likely intentional but worth knowing.
- **Case drift:** `"Fireball"` vs `"fireball"`. Auto-resolved by `addLoreBookEntry` adding both as aliases.
- **Garbage chars in aliasKeys:** LLMs sometimes emit aliases with `"_"` instead of spaces. `cleanLorebook(",_", " ")` covers this.
- **Trailing whitespace:** trim the key string before passing to `addLoreBookEntry`. There's no auto-trim.
