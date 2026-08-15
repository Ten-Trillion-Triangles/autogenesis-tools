---
name: tpipe-lorebook-agent-authoring
description: "Authoring a TPipe pipe that uses an LLM to extract entities from narrative and merge them into ContextWindow.loreBookKeys via ContextBank. Companion to tpipe-lorebook-system (data plane). Covers the seven-component canonical pattern (typed JSON output, validator, branch pipe, on-failure safety, pre-invoke bank load, typed merge-by-name, emplaceWithMutex writeback) and seven failure modes that produce the broken TPipeWriter loreBookPipe (raw ContextWindow output, missing validator, missing bank load, missing alias population, _-band-aids, model-specific JSON repair, append-vs-stomp confusion). Use when writing a new lorebook-extraction pipe, when debugging empty/stomped/duplicate lorebook entries, when porting Autogenesis's lorebookAgent.kt pattern, or when refactoring a legacy lorebook pipe off a single bad-output model."
version: 1.0.0
author: Hermes Agent (TPipeWriter session, 2026-07-13)
license: MIT
metadata:
  hermes:
    tags: [tpipe, tpipewriter, lorebook, lorebook-agent, context-bank, extraction, merge-by-name, append-scheme, typed-json]
    related_skills: [tpipe-lorebook-system, plus-writer-pipeline, autogenesis-prompt-debugging]
---

# TPipe Lorebook-Agent Authoring

How to write a TPipe pipe that uses an LLM to extract story entities (characters, events, locations, items, factions, relationships) and merge them as typed entries into a `ContextWindow.loreBookKeys` map via `ContextBank`. Companion to `tpipe-lorebook-system`, which covers the data plane (data shape, selection algorithms, lock system) — this skill covers the **agent-authoring plane**.

## When to Use

- Writing a new TPipe pipe that extracts entities from narrative and writes them to a lorebook bank.
- Debugging an existing lorebook pipe that: produces empty entries, stomps existing entries, duplicates keys, throws on bad JSON, or never reaches `ContextBank`.
- Porting Autogenesis's `lorebookAgent.kt` pattern to a new TPipeWriter pipeline.
- Refactoring a legacy lorebook pipe that was built around a single bad-output model into a model-agnostic typed-schema pattern.

## The Canonical Pattern (7 Components)

Reference: `Autogenesis/server/src/main/kotlin/agent/builders/lorebook/lorebookAgent.kt`. Each component is required; missing any one produces a broken pipe.

### 1. Typed JSON output schema

Define a serializable schema that mirrors your entity model. The LLM must emit typed entries that the transformation function can deserialize back to typed structs — not raw `loreBookKeys` map shapes.

```kotlin
@Serializable
data class CharacterEntry(
    var name: String = "",
    var description: String = "",
    var aliases: List<String> = listOf(),
    // ...
)

@Serializable
data class LorebookExtraction(
    var characters: List<CharacterEntry> = listOf(),
    var events: List<EventEntry> = listOf(),
    // ...
)
```

Then on the pipe: `setJsonOutput(LorebookExtraction::class)`. **Do not** use an empty `ContextWindow` as the output type.

### 2. Validator function

```kotlin
setValidatorFunction {
    extractJson<LorebookExtraction>(it.text) != null
}
```

The pipe must reject any LLM output that doesn't parse to the typed schema. Without this, bad JSON silently propagates into the bank.

### 3. Branch pipe (retry)

A second pipe that retries with a different model when validation fails. The branch pipe's `setOnFailure` synthesizes an empty struct so the pipe never throws on bad JSON.

```kotlin
setOnFailure { _, processed ->
    processed.text = serialize(LorebookExtraction())
    processed
}
```

### 4. On-failure safety on the main pipe

Same pattern as Component 3 on the main pipe — never throw on bad JSON, even if the branch pipe also fails.

### 5. Existing-bank load via `preInvoke` (preferred) or transformation

The LLM cannot merge against the existing lorebook if it cannot see it.

**Pattern A — preInvoke (preferred):**

```kotlin
.setPreInvokeFunction { miniBank, _ ->
    miniBank.contextMap["story"] = ContextBank.getContextFromBank("story")
    miniBank
}
```

**Pattern B — in transformation (simpler but LLM is blind):** load inside the transformation function. Pattern A is safer.

### 6. Typed merge-by-name

```kotlin
for (char in extraction.characters) {
    val existing = storyContext.findLoreBookEntry(char.name)
    val merged = if (existing != null) {
        mergeCharacterEntry(deserialize<CharacterEntry>(existing.value), char)
    } else char
    storyContext.addLoreBookEntry(
        key = char.name,
        value = serialize(merged),
        aliasKeys = merged.aliases  // CRITICAL: rich alias list from extraction
    )
}
```

**Critical pattern details:**
- The lorebook key is the entity's canonical name (e.g. "Shepard"), not a synthetic id.
- The lorebook value is the *serialized typed struct* — round-trippable. Next extraction can `deserialize<CharacterEntry>(existing.value)`.
- `aliasKeys = merged.aliases` — every alias the LLM generated (titles, nicknames, role keywords) goes into the lorebook's `aliasKeys` set. This is what enables fuzzy matching downstream via `findMatchingLoreBookKeys`.
- Merge strategy: append description with newline separator, dedupe aliases/affiliations, fall back on blank fields (don't overwrite populated status with empty).

### 7. Persist via `emplaceWithMutex`

```kotlin
ContextBank.emplaceWithMutex("story", storyContext)
```

Per-page mutex, atomic write. Never the non-mutex variant on a shared bank.

## The Seven Failure Modes

These are the actual bugs in the TPipeWriter `loreBookPipe` (`src/main/kotlin/Globals/Env.kt:763` and `src/main/kotlin/Builders/PlusWriterPipeline.kt:1198-1218`). Each maps to a missing component above.

### FM-1. Raw ContextWindow as output schema

`setJsonOutput(blankLoreBookExample)` where `blankLoreBookExample = ContextWindow()`. LLM has to invent the full `loreBookKeys` map shape with no per-entity typing. Schema errors propagate directly.

**Fix:** Replace with typed `LorebookExtraction` schema (Component 1).

### FM-2. No validator function

No `setValidatorFunction` on the lorebook pipe. Bad JSON either silently propagates or `throw`s ("Cannot deserialize deepseek jank ass json") and aborts the pipeline.

**Fix:** Add validator + branch pipe + on-failure safety (Components 2, 3, 4).

### FM-3. No existing-bank load into pipe context

The `loreBookPipe` has no `setPageKey`, no `pullGlobalContext`, no `setPreInvokeFunction`. `autoInjectContext` text says "the context will be provided in the user's prompt" but nothing sources it.

**Symptom:** LLM writes lorebook updates blind. Cannot deduplicate, cannot understand existing arcs, re-emits same key as "new" every turn. With emplace mode = stomp. With append mode = duplicate the value field.

**Fix:** Add `setPreInvokeFunction` that loads the existing bank into the pipe's miniBank (Component 5, Pattern A).

### FM-4. Missing alias population

Transformation function calls `bankedContext.merge(newLoreBookEntries, emplace, append)` directly on LLM-emitted JSON. Does NOT call `addLoreBookEntry` per entity with `aliasKeys`.

**Symptom:** Empty `aliasKeys`. Downstream `findMatchingLoreBookKeys` gets only exact key hits, no fuzzy alias hits. Effectively zero lorebook injection at runtime.

**Fix:** Per-entity typed merge with `aliasKeys = merged.aliases` (Component 6).

### FM-5. Underscore-for-space band-aids

`newLoreBookEntries.cleanLorebook("_", " ")` — `cleanLorebook` is documented as recovering from LLM-introduced garbage, not as production parsing. The auto-populated `key.uppercase()/lowercase()` aliases only work if you go through `addLoreBookEntry`, not raw map insertion.

**Fix:** Don't band-aid. Typed-schema (Component 1) makes LLM emit `{"name": "Fireball", "aliases": [...]}` — no underscore key strings possible.

### FM-6. Model-specific JSON repair

`repairAndDeserialize<ContextWindow>(content.text)` — fallback that tries to repair malformed JSON. Baked into production code. Comment confirms it: "Cannot deserialize deepseek jank ass json."

**Fix:** Parse typed `LorebookExtraction`, not raw `ContextWindow`. If a model can't output typed JSON, pick a different model — don't patch the output.

### FM-7. Append-vs-stomp confusion

`enableAppendLoreBookScheme()` is wired correctly through `ContextWindow.merge` (`Pipe.kt:3762-3767`, `Pipe.kt:6039-6046`, `Pipe.kt:6567-6568`). But the transformation function does `bankedContext.merge(newLoreBookEntries, ...)` where `newLoreBookEntries` is fresh LLM-emitted JSON. Append merges at the **whole-entry level** — entire lorebook value gets concatenated, not field-by-field.

**Symptom:** Even with append-mode, lorebook values are incoherent concatenations of whole struct serializations, not merged fields.

**Fix:** Merge at the typed-struct level, before serialization (Component 6). Don't serialize-then-append — deserialize, merge field-by-field, re-serialize.

## Anti-Patterns

### AP-1. Using `ContextWindow.merge` directly on LLM-emitted JSON

`ContextWindow.merge` is for merging two well-formed `ContextWindow`s. It does not parse, validate, or dedupe entries. Using it as a transformation function's main operation is the #1 sign the pipe is broken.

### AP-2. Reading the bank without locking

`ContextBank.getContextFromBank("story")` without `WithMutex` is a race when multiple pipes write concurrently. Use `getContextFromBankWithMutex` or read inside `emplaceWithMutex`'s callback.

### AP-3. Setting `enableAppendLoreBookScheme()` as the primary merge strategy

Append-mode is appropriate for the `ContextWindow.merge` cascade via `updatePipelineContextOnExit`. It is NOT a substitute for typed per-entity merge in the transformation function. Append + raw ContextWindow JSON = concatenation hell (FM-7).

### AP-4. Documenting bugs as `// bug:` comments

TPipeWriter has `// bug: There's quite a few issues here:` in production. These are unfinished-code signals, not accepted-behavior documentation. Convert to `// TODO:` or fix them.

## Verification

After refactoring a lorebook pipe to the canonical pattern:

1. **Known-story smoke:** Feed 3-5 pages of narrative with 2-3 named characters. Inspect `ContextBank.getContextFromBank("story").loreBookKeys`. Each character should have `key`=canonical name, `value`=`serialize(CharacterEntry(...))`, `weight`>0, `aliasKeys` containing ≥3 aliases, `linkedKeys`/`requiredKeys` empty.

2. **Overlapping-story merge:** Feed a second batch mentioning the same characters in new contexts. Verify merged entries: descriptions appended with newlines, aliases unioned and deduped, status updated only if new value non-blank.

3. **Bad-JSON resilience:** Force the LLM to produce invalid JSON. Pipe must not throw. Validator rejects → branch retries → on-failure synthesizes empty `LorebookExtraction()` → bank unchanged.

4. **No-underscore regression:** Verify `_`-band-aid code paths are now dead (e.g., delete the `cleanLorebook("_", " ")` call and re-run known-story smoke — should still pass).

## See Also

- `tpipe-lorebook-system` — data plane (data shape, selection, lock system, persistence).
- `references/typed-schema-cookbook.md` — worked examples of typed `LorebookExtraction` schemas for different genres (sci-fi, fantasy, mystery).