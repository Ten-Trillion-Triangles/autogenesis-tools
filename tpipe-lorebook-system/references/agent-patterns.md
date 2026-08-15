# Lorebook-Write Agent Patterns

How to build a TPipe pipe that extracts entities from prose and writes them back into a lorebook bank entry. This is the write-side companion to the consumer-side selection algorithm in `selection-algorithm.md`.

## Reference shape vs legacy shape

The reference is `Autogenesis/server/src/main/kotlin/agent/builders/lorebook/lorebookAgent.kt` (293 LOC). The legacy shape lives in `TPipeWriter/src/main/kotlin/Globals/Env.kt::recordLoreBook` and `TPipeWriter/src/main/kotlin/Builders/PlusWriterPipeline.kt::loreBookPipe` (around lines 1464–1514).

| Concern | Reference (Autogenesis) | Legacy (TPipeWriter) | Modern fix |
|---|---|---|---|
| **Output schema** | `setJsonOutput(LorebookExtraction::class)` — typed `characters: List<CharacterEntry>`, `events`, `locations`, `items`, `factions`, `relationships` | `setJsonOutput(ContextWindow())` — LLM guesses `loreBookKeys`/`contextElements`/`converseHistory`/`metaData` field names | Define a typed `@Serializable` extraction data class. Let kotlinx-serialization generate the schema in the prompt. |
| **Validator** | `setValidatorFunction { extractJson<LorebookExtraction>(it.text) != null }` | None — `recordLoreBook` `throw`s on bad JSON | `setValidatorFunction { extractJson<T>(it.text) != null }` + branch-pipe retry. |
| **On-failure** | `setOnFailure { processed.text = serialize(LorebookExtraction()); processed }` — synthesize empty struct | None — pipe aborts | `setOnFailure { processed.text = serialize(T()); processed }`. Never throw from a transformation function on bad JSON. |
| **Existing lorebook into prompt** | `setTransformationFunction` calls `ContextBank.getContextFromBank("story")` and merges explicitly per-entity | Not loaded — LLM writes blind | Load via `setPreInvokeFunction` or `pullGlobalContext()` + `setPageKey(<page key>)`. The pipe must see what exists. |
| **Per-entity merge** | `mergeCharacterEntry(existing, new)` / `mergeEventEntry` / etc. — typed field combination, alias dedupe, blank-fallback semantics | `bankedContext.merge(newLoreBookEntries, ...)` — generic map merge, no domain semantics | One `mergeXxxEntry` function per entity type, calling `deserialize<T>(existing.value)` then re-`addLoreBookEntry(key, value = serialize(merged), aliasKeys = merged.aliases)`. |
| **Append-vs-stomp** | Per-merge-function decision (`description = "${existing.description}\n${new.description}"`) | `enableAppendLoreBookScheme()` flag passed into `ContextWindow.merge(..., emplace, append)` | Drop the flag. Let merge functions decide per-field. |
| **Alias population** | `aliasKeys = merged.aliases` — typed list from extraction | Whatever the LLM puts in `aliasKeys` raw — case bugs common | Use the typed list from extraction. Case-insensitivity is already automatic via `addLoreBookEntry` (it appends uppercase/lowercase variants). |
| **Bank write** | `ContextBank.emplaceWithMutex("story", storyContext)` at end of transformation | `ContextBank.emplaceWithMutex("main", content.context)` + `updatePipelineContextOnExit()` (dual write) | Pick one path. With typed schema the pipe's `contextWindow` is the wrong container; the transformation function owns the bank write. |

## The validator / branch / on-failure trio

This is the modern TPipe pattern for any pipe whose output must match a typed schema. All three should be present:

```kotlin
val extractionPipe = GenericOpenAIPipe()
    .setJsonOutput(LorebookExtraction::class)              // 1. typed output
    .setValidatorFunction {                                // 2. hard gate
        extractJson<LorebookExtraction>(it.text) != null
    }
    .setOnFailure { _, processed ->                        // 3. safe degradation
        processed.text = serialize(LorebookExtraction())
        processed
    }

// Optional: branch pipe as a retry path
val branchPipe = GenericOpenAIPipe()
    .pullParentPipeContext()
    .setJsonOutput(LorebookExtraction::class)
    .setPreInitFunction {
        it.text = it.getSnapshot()?.text.toString()
    }
    .setValidatorFunction { extractJson<LorebookExtraction>(it.text) != null }
    .setOnFailure { _, processed ->
        processed.text = serialize(LorebookExtraction())
        processed
    }

extractionPipe.setBranchPipe(branchPipe)
```

The transformation function can then assume `extractJson<T>(it.text)` succeeds (or returns the empty fallback) and never throws on bad JSON.

## Per-entity merge recipe

```kotlin
fun mergeCharacterEntry(existing: CharacterEntry?, new: CharacterEntry): CharacterEntry {
    if (existing == null) return new
    return CharacterEntry(
        name = existing.name,
        description = if (new.description.isNotBlank())
            "${existing.description}\n${new.description}"
        else existing.description,
        aliases = (existing.aliases + new.aliases).distinct(),
        affiliations = (existing.affiliations + new.affiliations).distinct(),
        status = new.status.ifBlank { existing.status },
        lastSeen = new.lastSeen.ifBlank { existing.lastSeen }
    )
}

// Inside the transformation function:
val storyContext = ContextBank.getContextFromBank("main")

for (char in extraction.characters) {
    val existing = storyContext.findLoreBookEntry(char.name)
    val merged = if (existing != null) {
        mergeCharacterEntry(deserialize<CharacterEntry>(existing.value), char)
    } else {
        char
    }
    storyContext.addLoreBookEntry(
        key = char.name,
        value = serialize(merged),
        aliasKeys = merged.aliases
    )
}

ContextBank.emplaceWithMutex("main", storyContext)
```

Three properties this gives you:

1. **Append-by-default** — `description` concatenates rather than replaces. Per-field `ifBlank` falls back to existing rather than stomping.
2. **Alias dedupe** — `.distinct()` on the combined list. No more case-bug aliases from the LLM.
3. **Type-safe round-trip** — `existing.value` is a serialized `CharacterEntry`, not an opaque string. Adding a field to `CharacterEntry` is a single compile-time change.

## Wiring the existing lorebook into the pipe's input

Two options. Pick by how much of the bank the LLM needs to see:

**Whole-bank read** (Lorebook is the full context surface):

```kotlin
val pipe = GenericOpenAIPipe()
    .pullGlobalContext()                          // pull from bank
    .setPageKey("main")                           // map "main" -> page key
    .setPreInvokeFunction { content ->            // before LLM call: serialize current lorebook into prompt
        val lorebook = ContextBank.getContextFromBank("main")
        val lorebookJson = lorebook.loreBookKeys.entries.joinToString("\n") { (key, entry) ->
            "$key: ${entry.value}"
        }
        content.text = "$lorebookJson\n\n${content.text}"
        content
    }
```

**Just-the-existing-keys read** (Lorebook is supplementary; main text is the page being read):

```kotlin
.setPreInvokeFunction { content ->
    val lorebook = ContextBank.getContextFromBank("main")
    val lorebookSummary = lorebook.loreBookKeys.entries.take(50).joinToString("\n") { (key, entry) ->
        "$key: ${entry.value.take(200)}"
    }
    content.text = "Existing lorebook (do not duplicate these keys unless the new entity is genuinely new):\n$lorebookSummary\n\n${content.text}"
    content
}
```

Without one of these, the LLM has no signal that "Commander Shepard" already exists and will re-emit it as a fresh entry — see pitfall #12.

## JSON extraction utilities in TPipe

Two helpers in `com.TTT.Util`:

- `inline fun <reified T> extractJson(input: String): T?` (in `Util/JsonExtractor.kt`) — boundary-tracks `{...}` and `[...]`, repairs, tries a fallback extraction, returns the first JSON element that deserializes to `T`. Use this in validators and transformations as the first attempt.
- `inline fun <reified T> repairAndDeserialize(malformedJson: String): T?` (in `Util/Util.kt`) — the older one-shot repair path. Use as a fallback when `extractJson<T>` returns null and you want to retry with one more repair pass.

Plus `fun cleanJsonString(input: String): String` in `Util/JsonCleaner.kt` for stripping LLM-introduced markdown fences / prose wrapper around the JSON.

The legacy `recordLoreBook` does `extractJson<T>(...) ?: repairAndDeserialize<T>(...) ?: throw Exception(...)`. The modern shape is `extractJson<T>(...) ?: repairAndDeserialize<T>(...) ?: return synthesizedEmpty`. Throwing here is what kills the pipe — move that fallback into `setOnFailure` instead.

## Migration checklist for the TPipeWriter loreBookPipe

1. Define a `LorebookExtraction` typed schema suited to TPipeWriter's domain (chapters, characters, plot threads, locations — whatever the pipe is meant to track). Mirror Autogenesis's per-entity pattern.
2. Replace `setJsonOutput(blankLoreBookExample)` (a `ContextWindow()`) with `setJsonOutput(LorebookExtraction())`.
3. Add `setValidatorFunction { extractJson<LorebookExtraction>(it.text) != null }`.
4. Add `setOnFailure { _, processed -> processed.text = serialize(LorebookExtraction()); processed }`.
5. Optionally add a branch pipe retry path (mirror Autogenesis's branch setup).
6. Add `setPreInvokeFunction` (or `pullGlobalContext()` + `setPageKey("main")`) so the pipe sees the existing lorebook.
7. Rewrite `recordLoreBook` to: extract typed struct → for each entity, `findLoreBookEntry(name)` + `mergeXxxEntry(deserialize<T>(existing.value), entity)` + `addLoreBookEntry(...)` → `emplaceWithMutex("main", ...)`. Drop the `throw Exception("Cannot deserialize deepseek jank ass json")` path.
8. Drop `enableAppendLoreBookScheme()` from this pipe — the merge functions own append-vs-stomp now.
9. Remove dead code: `gptOssRefusals` list, `isValidGptOssResponse`, `gptOssModelName`/`gptOss120bModelName` constants, `recordLoreBookPlus` if superseded.
10. Remove the `contextElements.clear()` band-aid (no longer needed when the LLM can't write to a field that doesn't exist in the typed schema).
11. Decide on write path: keep either `updatePipelineContextOnExit()` OR the direct `ContextBank.emplaceWithMutex` call, not both — the dual write is a latent bug.

## Anti-patterns not to bring back

- **`setJsonOutput(ContextWindow())` for any LLM output that isn't a fully-formed context window.** The LLM will guess fields. The downstream code will need cleaning band-aids. Both are solved by a typed schema.
- **Throwing from a transformation function on bad JSON.** Use the validator/on-failure trio. Throwing aborts the pipeline.
- **`cleanLorebook` in the transformation function.** Reserve it for legitimate import-path cleanup.
- **Hardcoded refusal-string lists in `Env`.** They were model-specific. The model moved on.
- **Dual write paths (`emplaceWithMutex` + `updatePipelineContextOnExit`).** Pick one.