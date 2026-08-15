---
name: tpipe-lorebook-system
description: "TPipe lorebook subsystem — keyword-triggered weighted context injection across 5 files (LoreBook.kt, ContextWindow.kt selection pipeline, MiniBank.kt multi-page merge, ContextBank.kt disk persistence, ContextLock.kt KeyBundle veto). Use when working with selectLoreBookContext / selectAndFillLoreBookContext and their _Suspend / _WithSettings variants, when implementing addLoreBookEntry, when debugging lorebook matching or lock suppression, when configuring ContextLock global/per-page locks or passthroughFunction bypass, when persisting lorebooks to disk via ContextBank, when writing a setPreValidationMiniBankFunction that mutates contextMap['main'] (it is lorebook-only after copyLorebookFromMain — text-truncation is a no-op, see pitfall #14), or when auditing a deleted utility that called selectAndTruncateContext on contextMap['main']. Not for the PumpStation lorebookAgent magic contract (consumes this — see pump-station contract 7), not for truncateContextElements or truncateConverseHistory."
version: 1.1.0
metadata:
  hermes:
    tags: [tpipe, lorebook, context, context-window, context-bank, context-lock, mini-bank, weighted-injection, novelai-compatible, pre-validation-hook, silent-no-op]
    changelog:
      - "1.1.0 (2026-08-09): Added pitfall #14 — contextMap['main'] in the mini bank is a lorebook-only window after copyLorebookFromMain; text-truncation functions are no-ops on it. Captured from the ChapterRewrite util-truncation audit (d79ec35). Trigger widened to surface this gotcha when writing pre-validation hooks or auditing deleted helpers."
author: Shitty Bob (TTT)
created: 2026-07-03
updated: 2026-07-03
tags: [tpipe, lorebook, context, context-window, context-bank, context-lock, mini-bank, weighted-injection, novelai-compatible]
trigger: When asked about TPipe lorebook design or selection algorithm, when implementing lorebook-aware logic in a Pipe or container, when debugging lorebook key matching or lock suppression, when configuring ContextLock global/per-page locks or passthrough functions, when persisting lorebooks to disk via ContextBank, when working with MiniBank multi-page composition, when writing a `setPreValidationMiniBankFunction` hook that mutates `contextMap["main"]` (the window is lorebook-only — text-truncation is a no-op), when auditing a deleted helper that called `selectAndTruncateContext` on `contextMap["main"]` (verify it was actually doing anything), or when the operator asks for the lorebook system to be explained end-to-end.
---

# TPipe Lorebook System

Keyword-triggered, weight-prioritized context injection. Compatible in shape with NovelAI's lorebook model - every entry has a `key`, a `value`, a `weight`, and optional `linkedKeys` / `aliasKeys` / `requiredKeys`. When the scan text contains a key (or any of its aliases), the entry's value is packed into the prompt budget ahead of lower-weight entries.

The system spans **five files** in `src/main/kotlin/Context/`:

| File | LOC | Owns |
|------|----:|------|
| `LoreBook.kt` | 85 | The data class itself. |
| `ContextWindow.kt` | 2,312 | Selection algorithm + lock integration + merge + mutators + rendering. |
| `MiniBank.kt` | 57 | Multi-page `MutableMap<String, ContextWindow>` composition. |
| `ContextBank.kt` | 1,737 | Global singleton, disk persistence under `${TPipeConfig.getLorebookDir()}/${key}.bank`. |
| `ContextLock.kt` | 534 | `KeyBundle`-based veto layer for lorebook and page keys. |

The single most important architectural fact: **lorebooks live inside `ContextWindow.loreBookKeys: MutableMap<String, LoreBook>`**. Everything else is plumbing. Selection happens on the `ContextWindow`, persistence is per-page-key (pages, not lorebook entries, are what's stored in `ContextBank`), and locks are process-wide via a separate `ContextLock` singleton.

---

## When to Reach for Lorebook vs the Alternatives

TPipe has three context-injection mechanisms. Pick by triggering pattern.

| Need | Mechanism | Where |
|------|-----------|-------|
| **Keyword-triggered weighted injection** ("inject the spellbook lore when 'fireball' is mentioned") | **Lorebook** | `ContextWindow.loreBookKeys` + `selectLoreBookContext` |
| **Unconditional raw text appended to context** (system notes, persistent instructions) | `ContextWindow.contextElements: MutableList<String>` + `truncateContextElements` | `ContextWindow.kt` `truncateContextElements` |
| **Structured message-by-message conversation history** (multi-turn dialog) | `ContextWindow.converseHistory: ConverseHistory` + `selectConverseHistoryLoreBookContext` / `truncateConverseHistory` | `ContextWindow.kt` |

The lorebook is the only mechanism that does **keyword-gated, weighted, budget-allocated** injection. Raw contextElements always land in the prompt. ConverseHistory is round-trip structured. Lorebooks fire conditionally on the scan text and compete for budget.

---

## The Five-Layer Architecture

```
+------------------------------------------------------------------+
| ContextLock (object)        | process-wide veto layer           |
| ConcurrentHashMap<String,   | - isKeyLocked / canSelectLoreBook |
|   KeyBundle>                | - passthrough per-call bypass     |
+-------------^---------------+----------------------------------+
              | gates every match + every candidate
              v
+------------------------------------------------------------------+
| ContextWindow.loreBookKeys : MutableMap<String, LoreBook>        |
|                                                                  |
|  findMatching -> expandLinks -> checkDeps -> weight/hit sort ->  |
|  token-pack (Dictionary.countTokens) -> fill (optional)          |
+-------------^----------------------------------------------------+
              | owns the algorithm (see references/selection-algorithm.md)
              v
+------------------------------------------------------------------+
| MiniBank : MutableMap<String, ContextWindow>                     |
| MiniBank.merge -> ContextWindow.merge (per-page composition)     |
+-------------^----------------------------------------------------+
              | wraps multiple pages
              v
+------------------------------------------------------------------+
| ContextBank (object) - global singleton                          |
| bank: ConcurrentHashMap<String, ContextWindow> + disk persistence|
| ${getLorebookDir()}/${key}.bank - atomic .bank file per page key |
+------------------------------------------------------------------+
```

---

## LoreBook.kt - the data shape (85 LOC)

```kotlin
@Serializable data class LoreBook(@Transient val cinit: Boolean = false) {
    var key: String = ""
    var value: String = ""
    @Serializable(with = IntCoercionSerializer::class) var weight: Int = 0
    var linkedKeys = mutableListOf<String>()   // co-trigger cascade
    var aliasKeys  = mutableListOf<String>()   // bidirectional trigger aliases
    var requiredKeys = mutableListOf<String>() // all-must-be-present gate
}
```

Two methods: `combineValue(other)` (append value string, dedupe-merge requiredKeys) and `toMap(): Map<String, LoreBook>` (single-entry map wrapper).

### The three "relationship" fields and their semantics

| Field | Direction | Resolved at |
|-------|-----------|-------------|
| `linkedKeys` | **Outgoing** - when THIS entry fires, also try these other keys. | BFS expansion stage. |
| `aliasKeys` | **Bidirectional** for matching AND dependency resolution. | `findMatchingLoreBookKeys` + `checkKeyDependencies`. |
| `requiredKeys` | **Incoming** - these keys (or their aliases) must all be present in the matched set for THIS entry to fire. | `checkKeyDependencies` after expansion. |

Alias resolution works in **both directions** when checking dependencies: `requiredKey` is satisfied either by being in the matched set directly, or by any matched key whose `aliasKeys` contains `requiredKey`, or by `requiredKey.aliasKeys` containing some matched key. See `references/selection-algorithm.md` step 5 for the exact bidirectional logic.

---

## ContextWindow - the selection algorithm

The algorithm runs identically in a sync version and a `_Suspend` version (same math, different lock-check method). The full pipeline is 9 stages. For the per-stage walkthrough with code locations, fall-through order, and edge cases, see `references/selection-algorithm.md`.

Quick reference of the public surface on `ContextWindow`:

| Category | Functions |
|----------|-----------|
| **Matching** | `findMatchingLoreBookKeys(text)`, `...Suspend(text)` |
| **Selection** | `selectLoreBookContext(text, maxTokens, ...9 tokenization knobs...)`, `selectLoreBookContextSuspend(...)` |
| **Selection with opportunistic fill** | `selectAndFillLoreBookContext(...)`, `...Suspend(...)` |
| **Converse-history-driven selection** | `selectConverseHistoryLoreBookContext(maxTokens, ...)` - uses `extractConverseHistoryText()` as scan text |
| **Settings-wrappers** | `selectLoreBookContextWithSettings(settings, text, maxTokens)`, `...Suspend`, plus `*AndFill*WithSettings` variants |
| **Mutators** | `addLoreBookEntry(key, value, weight=0, linkedKeys, aliasKeys, requiredKeys)`, `addLoreBookEntryWithObject(lorebook)`, `findLoreBookEntry(key)`, `cleanLorebook(bannedChars, replaceBannedCharWith)` |
| **Lock integration** | `isContextLocked()`, `canSelectLoreBookKey(key)`, `...Suspend`, `getLockedKeys()` |
| **Merge** | `merge(other, emplaceLoreBookKeys=true, appendKeys=false, emplaceConverseHistory=false, onlyEmplaceIfNull=false)` |
| **Scan surface** | `buildLorebookScanText(userPrompt, useEntireContext): String` extension function |

### The strict-priority vs select-and-fill choice

- **`selectLoreBookContext`** runs the 9-stage pipeline once. Sort by `(weight desc, hitCount desc)`, then greedily pack values into the budget. **Entries that overflow are dropped** - no partial-include of a value. Use when the priority order must be enforced strictly and overflow is acceptable as dropped knowledge.
- **`selectAndFillLoreBookContext`** runs the strict pass first, then takes leftover budget and fills with weight-sorted non-priority keys (re-checking `checkKeyDependencies` per fill iteration). Use when the budget should be saturated even at lower priorities, but you still want the priority set preserved.

Both have `_Suspend` and `_WithSettings` variants for a total of **8 public selection entry points**.

### Auto-populated aliases - a non-obvious property of `addLoreBookEntry`

```kotlin
fun addLoreBookEntry(key: String, value: String, ...) {
    loreBookKeys[key] = LoreBook().apply {
        ...
        this.aliasKeys.addAll(aliasKeys)
        this.aliasKeys.add(key.uppercase())   // <- implicit
        this.aliasKeys.add(key.lowercase())   // <- implicit
        ...
    }
}
```

When you add a lorebook entry, the `key.uppercase()` and `key.lowercase()` variants are **automatically appended** to `aliasKeys`. This makes case-insensitive matching implicit - `findLoreBookEntry` is case-insensitive without callers doing anything. **`addLoreBookEntryWithObject` does NOT do this re-population** because it round-trips through `addLoreBookEntry`, but it relies on the entry still having the case-variants in its alias list. If a caller has stripped the auto-aliases before passing to `addLoreBookEntryWithObject`, they will be re-added on the round-trip. Don't rely on this - the only safe assumption is that entries added through `addLoreBookEntry` are case-insensitive.

### `findLoreBookEntry` case-resolution order

```kotlin
fun findLoreBookEntry(key: String): LoreBook? {
    if(loreBookKeys.containsKey(key.uppercase())) return loreBookKeys[key.uppercase()]
    if(loreBookKeys.containsKey(key.lowercase())) return loreBookKeys[key.lowercase()]
    if(loreBookKeys.containsKey(key))            return loreBookKeys[key]
    // fallback: scan every entry's aliasKeys
    for((_, loreBookEntry) in loreBookKeys) {
        if(loreBookEntry.aliasKeys.contains(key.uppercase())) return loreBookEntry
        if(loreBookEntry.aliasKeys.contains(key.lowercase())) return loreBookEntry
        if(loreBookEntry.aliasKeys.contains(key))            return loreBookEntry
    }
    return null
}
```

Probes `uppercase` -> `lowercase` -> as-is -> alias scan. Always returns the first hit; later duplicates are masked. If you need to look up entries added with mixed case (e.g. one entry keyed `"Fireball"` and another keyed `"fireball"`), you'll get the uppercase one first - be careful with case in identifier author-side.

---

## ContextLock - the gating layer

`object ContextLock` with `ConcurrentHashMap<String, KeyBundle>` storage and a `Mutex` for lifecycle safety.

### KeyBundle

```kotlin
data class KeyBundle(
    var keys: MutableList<String> = mutableListOf(),
    var pages: MutableList<String> = mutableListOf(),
    var isGlobal: Boolean = false,
    var isLocked: Boolean = false,
    var isPageKey: Boolean = false,
    var passthroughFunction: (() -> Boolean)? = null   // sync callback - return true to BYPASS
)
```

The `passthroughFunction` is the **adjudication point**. A locked entry can be admitted via passthrough. The function is sync, takes no arguments, and may throw - exceptions fall through to `!bundle.isLocked` (i.e. honor the lock).

### The trio pattern: sync / `_Suspend` / `_WithMutex`

Every public API has **three variants**:

- `<name>(args, skipRemote=false)` - blocks via `runBlocking { ...Suspend }`. Compatibility surface.
- `<name>Suspend(args, skipRemote=false)` - coroutine-native. May consult remote state via `MemoryClient`.
- `<name>WithMutex(args, skipRemote=false)` - coroutine-native AND holds `lockMutex` for the full lifecycle.

The trio covers (lock, add-lock, remove-lock, key-bundle lock/unlock, key-lock check, page-lock check).

`skipRemote=true` bypasses `MemoryClient` delegation even when remote is configured globally - used by internal recursive calls and by tests.

### When a key hits a lock

1. `findMatchingLoreBookKeys` calls `canSelectLoreBookKey(key)` for every substring hit.
2. `selectLoreBookContext` calls `canSelectLoreBookKey(key)` again after dependency check, before adding to the candidate triple list.
3. `selectAndFillLoreBookContext` calls `canSelectLoreBookKey(key)` yet again during the fill pass for each candidate.

**Three choke points.** If the key is locked at any point, it's filtered out. If the bundle has `passthroughFunction`, the function's boolean decides - true means admit, false means deny (or throw -> honor `isLocked`).

### Add-lock lifecycle

`addLockSuspend` resolution order:
1. If not `skipRemote` and remote enabled -> POST to `MemoryClient.addLock(LockRequest)`.
2. Determine affected pages: empty `pageKeys` arg means global -> call `ContextBank.getPageKeysSuspend(skipRemote = true)`. Otherwise parse `pageKeys` (comma-separated, trimmed, blanks filtered).
3. For each affected page: set `metaData["isLocked"] = lockState` via `ContextBank.withContextWindowReferenceSuspend`, then find the lorebook entry to record the key.
4. If `isPageKey` (lock targets a page, not a lorebook entry) -> skip the lorebook entry discovery, just record the page list.
5. Store the `KeyBundle` under `locks[normalizeKey(key)]` (lowercased).

`removeLockSuspend` reverses the metadata writes for each affected page before dropping the bundle. `lockKeyBundleSuspend` / `unlockKeyBundleSuspend` flip `bundle.isLocked` and re-persist metadata. Three-state lock lifecycle: `addLock` -> `lockKeyBundle`/`unlockKeyBundle` (toggles) -> `removeLock` (removes).

---

## Multi-page composition

### MiniBank

```kotlin
@Serializable data class MiniBank(
    var contextMap: MutableMap<String, ContextWindow> = mutableMapOf()
)
```

`merge(other, emplaceLorebookKeys=true, appendKeys=false, emplaceConverseHistory=false, onlyEmplaceIfNull=false)` - for each `(key, contextWindow)`:
- If `this.contextMap` has the key -> delegate to `ContextWindow.merge(contextWindow, emplaceLorebookKeys, appendKeys, emplaceConverseHistory, onlyEmplaceIfNull)`.
- Else -> `contextMap[key] = contextWindow` (reference assignment - no deep copy).

`isEmpty()` / `clear()` thin wrappers over the underlying map.

### ContextWindow.merge semantics

`emplaceLoreBookKeys` is the LLM-mutator default (true). When true and a key exists on both sides, the `other` entry replaces `this`. The relationship fields (`linkedKeys`, `aliasKeys`, `requiredKeys`) are **always combined** via `Util.combine(...)` regardless of the emplacement flag - only the `value` respects the policy.

`appendKeys=true` overrides emplacement: `value = "${existing.value} ${other.value}"` instead of replacing. This is the "scanner agent only appends, never stomps" mode.

### ContextBank persistence

`object ContextBank` owns:
- `bank: ConcurrentHashMap<String, ContextWindow>` - in-memory page cache.
- `getPageMutex(key).withLock { ... }` - serializes concurrent writes per page.
- Storage modes (`StorageMode.kt`): `MEMORY_ONLY` / `MEMORY_AND_DISK` / `DISK_ONLY` / `DISK_WITH_CACHE` / `REMOTE`.

Disk layout: `${TPipeConfig.getLorebookDir()}/${key}.bank`. **One file per page key, containing the entire `ContextWindow` (including its `loreBookKeys` map), serialized as JSON via `serialize(...)` / `deserialize(...)`.** Lorebook entries do not have their own files - they're embedded in the parent page.

`loadContextWindowForKeyLocked(key, mode)` - reads from `bank`, falls back to disk `${key}.bank`, populates cache if appropriate to the mode. Atomic writes via `MemoryPersistence.writeMemoryFile`.

---

## End-to-end flow (the operator's mental model)

When a Pipe is lorebook-aware:

1. **Load / assemble.** Pipe pulls a `ContextWindow` from `ContextBank` for its page key. Optionally composes multiple pages via `MiniBank.merge`.
2. **Build scan text.** Pipe calls `window.buildLorebookScanText(userPrompt, useEntireContext)` to get the text to scan for keyword matches. With `useEntireContext=true`, this folds in `contextElements` and `converseHistory.history[]` - substantial behavior change.
3. **Select.** Pipe calls `selectAndFillLoreBookContextWithSettings(settings, scanText, lorebookBudget)` (or the strict-priority variant).
4. **Inside selection.** `findMatchingLoreBookKeys` does case-insensitive substring matching across every entry's `key` + every alias on each entry. Locked entries are filtered. Matching set is expanded via `linkedKeys` BFS (with cycle guard via `expandedKeys.contains`). Dependencies are then evaluated (`requiredKeys` satisfied?). Eligible candidates are sorted by `(weight desc, hitCount desc)`. Token-budget packing uses `Dictionary.countTokens(value, 9 knobs...)`.
5. **Render.** Selected lorebook entries' values are folded into the LLM's prompt context. Some Pipe implementations run `cleanLorebook(bannedChars, replaceBannedCharWith)` first to strip LLM-introduced garbage like `_` for spaces.

---

## Threading contract (must-know)

- Concurrent-safe: `ConcurrentHashMap` access in `ContextLock.locks`.
- Concurrent-safe: `ContextLock.lockMutex` serializes all lock lifecycle mutations.
- Concurrent-safe: `ContextBank.getPageMutex(key).withLock { ... }` serializes per-page writes.
- NOT thread-safe: `MiniBank.merge` - mutates local maps without locking.
- NOT thread-safe: `ContextWindow.merge` - same.
- Concurrent-reads-OK with mutex-needed-for-writes: `selectLoreBookContext` reads `ConcurrentHashMap` directly (sync variant) - fine in concurrent reads, but the caller must hold the page mutex if there's a concurrent writer.

The safe pattern for live editing: hold `ContextBank.getPageMutex(key)` across any read-modify-write that touches `loreBookKeys`. Update via `withContextWindowReferenceSuspend`.

---

## Pitfalls

### 1. `MiniBank.merge` does NOT deep-copy on first insertion

When `other.contextMap` has a key not yet in `this.contextMap`, the assignment is reference-assignment: `contextMap[key] = contextWindow`. If the caller then mutates that window through either reference, both see the change. Callers wanting isolation must `deepCopy()` first.

### 2. `addLoreBookEntryWithObject` re-runs `addLoreBookEntry` (and re-adds auto-aliases)

`addLoreBookEntryWithObject(lorebook)` -> `addLoreBookEntry(lorebook.key, lorebook.value, lorebook.weight, lorebook.linkedKeys, lorebook.aliasKeys, lorebook.requiredKeys)`. The auto-aliases (`key.uppercase()`, `key.lowercase()`) get RE-ADDED on every round-trip. If the input `lorebook.aliasKeys` already contained the case-variants, you'll get duplicates - harmless for matching, ugly for serialization.

### 3. Linked-key cycles are bounded but not detected

BFS uses an `expandedKeys.contains` check to prevent re-enqueueing, which handles cycles (A->B->A) correctly. But the check is `Set.contains` - if you have 10,000 entries and deep linked chains, the cost adds up. The algorithm is O(edges), not O(vertices). Don't build webs of arbitrary complexity.

### 4. The sort is unstable across equal (weight, hitCount) pairs

`compareByDescending(weight).thenByDescending(hitCount)` has no tertiary sort key. Two entries with weight=10 and hitCount=2 will land in iteration order, which is the underlying `LinkedHashMap` order, which is insertion order. If you need deterministic order across `selectLoreBookContext` calls, add a stable tiebreaker field.

### 5. The `useEntireContext=true` scan-surface change is dramatic

With `useEntireContext=true`, the scan text is `userPrompt + "\n" + contextElements.joinToString("\n") + "\n" + converseHistory.joinToString("\n") { it.content.text }`. A 5,000-token prior chapter in `converseHistory.history[].content.text` will multiply your lorebook matches. Test with `useEntireContext=false` first and switch only when you have a clear reason.

### 6. `selectAndFillLoreBookContext`'s dependency re-check

During the fill pass, `checkKeyDependencies(selectedSet)` is re-evaluated per candidate iteration. This means a fill-eligible key whose `requiredKeys` are NOT all in the (priority + fill-so-far) set will be skipped, even if its weight would have won under unsorted fill. This is intentional - fills must respect dependency semantics - but it can be surprising.

### 7. Lock add is fire-and-forget on remote

`addLockSuspend` calls `MemoryClient.addLock(...)` first and throws via `requireSuccess("add remote lock '$key'")` if it fails. But on `removeLockSuspend`, a `notFound` remote response is **silently tolerated** because remove-on-missing is a no-op. Don't rely on the same tolerance for `addLock` - a missing page on remote WILL throw.

### 8. `cleanLorebook` re-canonicalizes but doesn't fix the source

When you run `cleanLorebook(",", " ")` to replace commas in keys, the deep-copy + clear + re-add pattern produces a new lorebook map with the bans replaced, but the old `loreBookKeys` map is now a fresh `MutableMap`. **You're using this to recover from LLM-introduced garbage**. Calling it inside a hot selection loop is expensive - pre-clean once, then cache.

### 9. Token-counting is greedy-fail, not partial-pack

`selectLoreBookContext` drops entries that overflow the budget. There's no way to fit a partial entry's value into the remaining budget. If you have a 100-token value and 50 tokens left, the entire value is dropped. Workaround: split large values into multiple smaller entries.

### 10. Lock add expects `pageKeys` to be comma-separated, not a list

`ContextLock.addLock(key, pageKeys: String, ...)` parses `pageKeys` as a CSV. If you pass `pageKeys = listOf("foo", "bar").joinToString(",")`, do it manually. There's no helper overload that takes `List<String>` - the existence of the CSV form is historical. Don't accidentally pass `"foo, bar"` (with a space) - `parsePageKeys` does trim but the blank filter will reject empty segments.

### 11. Building a lorebook-write agent? Use a typed extraction schema, not raw `ContextWindow`

The legacy pattern is `setJsonOutput(ContextWindow())` and have the LLM emit a full `{loreBookKeys: {key: {key, value, weight, linkedKeys, aliasKeys, requiredKeys}}, contextElements, converseHistory, metaData}` shape. This is fragile: the LLM has to invent field names that match TPipe's serialization exactly, frequently mistypes `_` for spaces in `key`/`value`, mismatches casing, or dumps output into `contextElements` instead of `loreBookKeys`. The downstream code ends up running `cleanLorebook("_", " ")` and a manual `newContext.contextElements?.clear()` band-aid, neither of which fixes the underlying contract.

The modern shape is a typed per-entity schema (see Autogenesis's `LorebookExtraction` with `CharacterEntry` / `EventEntry` / `LocationEntry` / etc.). Define a typed `@Serializable` data class, set it via `setJsonOutput(TypedExtraction())`, and let kotlinx-serialization generate the schema in the prompt. Apply the trio: `setValidatorFunction { extractJson<T>(it.text) != null }` + a branch-pipe retry + `setOnFailure { synthesize empty typed struct }`. **Never `throw` from a transformation function on bad JSON** — the pipe's validator is the right place, and even the validator should be backed by `setOnFailure` so a malformed run degrades to "no updates" rather than aborting the pipeline.

The merge on the transformation side becomes: `ContextBank.getContextFromBank("main")` → for each typed entity, `findLoreBookEntry(entity.name)` → deserialize `existing.value` as the typed struct → run a typed `mergeXxxEntry(existing, new)` with real domain semantics → re-`addLoreBookEntry(key, value = serialize(merged), aliasKeys = merged.aliases)`. Append-vs-stomp is now a per-merge-function decision, not a `ContextWindow.merge` flag.

Reference: `references/agent-patterns.md` has the full TPipeWriter-vs-Autogenesis comparison with code-shape diffs and the migration checklist.

### 12. Don't make the LLM write lorebook updates blind against the existing lorebook

A lorebook-write pipe that has neither `pullGlobalContext()` nor `setPageKey("main")` nor a `setPreInvokeFunction` that loads the current bank will produce updates with no awareness of what's already in the lorebook. The LLM re-emits the same key without seeing the existing value; the merge either stomps (emplace) or produces a duplicate append. The agent looks "active" but it's corrupting state silently.

Correct shape: the transformation function (or `setPreInvokeFunction`) loads `ContextBank.getContextFromBank(<page key>)`, exposes the current `loreBookKeys` map to the LLM through the prompt, and the merge function uses `findLoreBookEntry(name)` per entity. The pipe must see what exists in order to decide whether to add, append, or skip. See `references/agent-patterns.md`.

### 13. `cleanLorebook` is a band-aid, not a fix

Calling `cleanLorebook(bannedChars, replaceBannedCharWith)` in a transformation function (especially with hardcoded `"_", " "`) means the upstream JSON contract is wrong. The clean function does a deep-copy + clear + re-add to normalize keys, but the LLM will emit garbage in the same shape next time. The fix is a typed output schema (pitfall #11), not more cleaning. Reserve `cleanLorebook` for legitimate cases — a known-bad legacy lorebook imported from another format (SillyTavern/NAI JSON via `LoreBookData` / `LoreBookConverter`), where the source format is the actual problem.

### 14. `contextMap["main"]` in the mini bank is a lorebook-only window — text-truncation on it is a no-op

`copyLorebookFromMain(bank, content)` (PlusWriterUtil.kt:135-145) is the canonical pre-validation hook that puts `ContextBank["main"]` into the mini bank's `contextMap["main"]` slot. The resulting window has:
- `loreBookKeys: MutableMap<String, LoreBook>` populated with the page's lorebook
- `contextElements: MutableList<String>` EMPTY (the underlying text is NOT copied)

This is intentional — the pipe is meant to see lorebook entries (key→value map), not the full main prose (which lives in `contentElements` of the upstream page, not the mini bank).

**The pitfall:** if your `setPreValidationMiniBankFunction` calls a text-truncation function on `context.contextMap["main"]`, you're truncating `contextElements`, which is empty. The call is a no-op.

```kotlin
// Example of the silent no-op pattern (DON'T do this):
fun styleSuggestPreValidate(context: MiniBank, content: MultimodalContent? = null): MiniBank {
    val mainContext = context.contextMap["main"] ?: ContextWindow()
    // ← mainContext.contextElements is EMPTY because copyLorebookFromMain
    //   replaced it with a lorebook-only window. This call does nothing:
    mainContext.selectAndTruncateContext("", 8000, TruncateTop, truncationSettings)
    context.contextMap["main"] = mainContext
    return context
}
```

`selectAndTruncateContext` operates on `contextElements`. When `contextElements` is empty (always, after `copyLorebookFromMain`), the function returns the window unchanged. The 8K-truncation claim in the function name is a lie — the lorebook map is in `loreBookKeys`, not `contextElements`, so it doesn't even get touched.

**The diagnostic that catches this:** before relying on a pre-validation hook that mutates `contextMap`, dump `context.contextMap["main"]?.contextElements?.size` to a file or assertion. If it's 0, any `selectAndTruncateContext` / `combineAndTruncateAsString` / `setMaxTokens` on it is dead code.

**The fix when you actually want to truncate the lorebook:** if you genuinely need to drop lorebook entries (not text), iterate `mainContext.loreBookKeys` and call `mainContext.loreBookKeys.remove(key)` directly. That's not a built-in — it's a manual key-removal loop.

**The fix when you actually want the page's full text:** read from `ContextBank.getContextFromBank("main")` (NOT the mini bank), which has `contextElements` populated. The mini bank's `contextMap["main"]` is the lorebook-isolated copy, not the full context.

**Reference case:** captured 2026-08-09 during the ChapterRewrite util truncation audit (`d79ec35`). The deleted `styleSuggestPreValidate` function in `ChapterRewriteUtil.kt` had this exact pattern — it called `mainContext.selectAndTruncateContext("", 8000, TruncateTop, settings)` on a lorebook-only window. The function was a no-op for years; the audit found it because `copyLorebookFromMain` had been added long after the function was written, replacing the text-context semantics with lorebook semantics. Same pattern can silently reappear in any new `setPreValidationMiniBankFunction` that treats `contextMap["main"]` as text.

### 15. `gpt-oss-20b` artifacts in code are dead weight now

TPipeWriter's pre-2026 lorebook-write path was tuned for `openai.gpt-oss-20b-1:0` and `deepseek.v3-v1:0` — both produced output that needed refusal-string lists (`gptOssRefusals`), underscore-to-space cleaning, deepseek-specific `contextElements.clear()` band-aids, and "cannot deserialize deepseek jank ass json" `throw` sites. The pipe has since moved to `ModelConfig.primaryModelName`. The refusal lists, the model-name constants, and the band-aids are all dead code that confuses future readers. When fixing the lorebook-write path, rip them out rather than preserving them as "the safe path" — they were only safe relative to models that no longer run there.

---

## See Also

- **`references/agent-patterns.md`** - lorebook-write agent patterns: the Autogenesis typed-extraction reference shape vs the legacy TPipeWriter raw-`ContextWindow` shape, migration checklist, the validator/branch/on-failure trio, append-vs-emplace at the merge-function level.
- **`references/selection-algorithm.md`** - the 9-stage algorithm with code locations and per-stage edge cases.
- **`references/lock-lifecycle.md`** - KeyBundle state machine, the trio pattern, passthrough function semantics, remote vs local resolution.
- **`references/persistence-and-storage.md`** - Storage modes, `.bank` file format, mutex semantics, REMOTE mode coupling to MemoryServer.
- **`pump-station/SKILL.md`** contract #7 - the `lorebookAgent` magic contract that WRITES lorebook entries as LLM output, and uses `applyTypedLorebookUpdates` (`PumpStationLoop.kt:1416`) to apply them to the running `ContextWindow`.
- **`tpipe-json-serialization/SKILL.md`** - `@EncodeDefault` and the AI-malformed-JSON repair used by `serialize()` / `deserialize()` for the lorebook->wire and wire->lorebook round-trips on P2P/DistributionGrid.
