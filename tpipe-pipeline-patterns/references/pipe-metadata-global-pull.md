# Per-Class Page-Key Pull from `MetadataBank`

The complementary pattern to the construction-time manual-bind in `references/pipe-metadata-payload-binding.md`. Where the manual-bind pattern is "destructure at construction, hand fragments to each pipe," this **page-key pull pattern** is "stash state in a globally-addressable scratchpad, pull what you need when you need it."

## The seam: `MetadataBank` + a per-class pull method

`MetadataBank` is a process-singleton, page-keyed, in-memory-only `Map<Any, Any>` registry, shipped in `src/main/kotlin/Context/MetadataBank.kt` (TPipe 1.0.15+). Every public method comes as a blocking + `suspend` pair. Four classes with a metadata bag now expose a glued-page-key pull primitive:

| Class | Field | Setter | Pull method |
|-------|-------|--------|-------------|
| `Pipe` | `pipeMetadata: MutableMap<Any, Any>` | `setMetaPageKeys(glued: String): Pipe` | `pullMetaPageKeysIntoPipeMetadata()` |
| `MultimodalContent` | `metadata: MutableMap<Any, Any>` | `setMetaPageKeys(glued: String): MultimodalContent` | `pullMetaPageKeysIntoMetaData()` |
| `ContextWindow` | `metaData: MutableMap<Any, Any>` | `setMetaPageKeys(glued: String): ContextWindow` | `pullMetaPageKeysIntoWindowMetaData()` |
| `PumpStation` | `metadata: MutableMap<Any?, Any?>` | `setMetaPageKeys(glued: String): PumpStation` | `pullMetaPageKeysIntoPumpStationMetadata()` |

The setter records the glued string verbatim. The pull method calls `MetadataBank.pullMetaPageKeysIntoSuspend(target, glued)` — parsing happens in the bank itself (split on `", "`, trim, drop empty). Empty glued string is a no-op; missing keys silently skipped; last-write-wins on collision. Lazy by design — no execute-hook is touched.

## The contract

```kotlin
// At setup time — any code path, anywhere in the JVM:
MetadataBank.setMeta("apex.flow_state", mapOf("rounds" to 3, "focus" to "epic"))
MetadataBank.setMeta("apex.reasoning_config", mapOf("method" to "react"))
MetadataBank.setMeta("workflow.global_state", mapOf("step" to 5))

// At consumption time — pulls everything found at those keys, last-write-wins:
pipe.setMetaPageKeys("apex.flow_state, apex.reasoning_config, workflow.global_state")
pipe.pullMetaPageKeysIntoPipeMetadata()

// Now pipe.pipeMetadata carries every entry from all three pages, last-write-wins per collision.
```

## Why a parallel surface to `Pipe.setPageKey(...)`?

`Pipe.setPageKey(glued)` at `Pipe.kt:4201` already exists for the **LLM ContextWindow** path — it splits the glued string into `pageKeyList`, and the runtime pull reads `ContextWindow`s from `ContextBank` for LLM context injection. That's a different concern:

| Surface | Glue string | Pull target | What gets pulled |
|--------|-------------|-------------|------------------|
| `Pipe.setPageKey(...)` + auto-pull at execute | `"a, b, c"` | `ContextWindow` | LLM context (`ContextWindow`s from `ContextBank`) |
| `Pipe.setMetaPageKeys(...)` + explicit pull | `"a, b, c"` | `pipeMetadata: MutableMap<Any, Any>` | Metadata bag (`Map<Any, Any>` values from `MetadataBank`) |

The two surfaces use the same convention because the same dev mental model — "give me everything at these page keys" — applies to both. **The bank is different** (`MetadataBank` for metadata, `ContextBank` for LLM context).

## The `Any?`-keyed bridge on `PumpStation`

Three of the four classes have `MutableMap<Any, Any>` metadata fields, so the bank primitive fits directly. `PumpStation.metadata` is `MutableMap<Any?, Any?>` — `Any?` keys, not `Any`. The pull method uses a transient `MutableMap<Any, Any>` view, populated by the bank, then written back into the `Any?` bag:

```kotlin
fun pullMetaPageKeysIntoPumpStationMetadata() {
    if(metaPageKeys.isBlank()) return
    val view = mutableMapOf<Any, Any>()
    MetadataBank.pullMetaPageKeysInto(view, this.metaPageKeys)
    for((k, v) in view) {
        this.metadata[k] = v
    }
}
```

The bank never produces `null` keys in practice (devs pass strings, ints, structured keys), so the bridge is safe — but documented: only `Any`-keyed values from the bank land in the `Any?` bag; a `null` key in the bank would fail the `view[k] = v` assignment.

## When to use this pattern vs. the manual-bind pattern

| Scenario | Use |
|----------|-----|
| Single-pipe agent, wrapper known at construction | Manual bind (`pipeMetadata["x"] = ...` in `.apply { }`) |
| Multi-component setup where ANY class with a metadata bag needs cross-component state | Page-key pull via `MetadataBank` |
| Apex-agent features, workflow bundles, anything "global for the JVM" | Page-key pull |
| State that should persist across many `execute()` calls | Page-key pull |
| State scoped to a single construction → single `execute()` lifecycle | Manual bind |
| LLM context (ContextWindow payload, not metadata) | `Pipe.setPageKey(...)` (different surface, same convention) |

## Anti-patterns

### Don't auto-pull on every execute

The setter is lazy: the bank is only consulted when dev calls the explicit pull method. Auto-pulling at execute-time would couple every pipe to bank state and hide the "metadata bag" semantics behind silent I/O. If you want auto-pull, do it in the consuming code (one call site, well-named), not in the pipe's execute hook.

### Don't use empty-glued-string as a sentinel for "remove my metadata"

`setMetaPageKeys("")` followed by `pullMetaPageKeysInto*()` is a documented no-op — the bank is not consulted and the metadata bag is untouched. To clear the bag, use whatever clear primitive your class already exposes (`metadata.clear()`, `pipeMetadata.clear()`, `clearMetaData()` if it exists).

### Don't reach for the bank when a local write would do

If the state is scoped to one class for one execution, the manual-bind pattern is cheaper and more readable. The bank is for cross-component state — anything else is overhead.

## Cross-references

- `references/pipe-metadata-payload-binding.md` — the manual-bind pattern (destructure + bind at construction). This document is the page-key-pull companion.
- `tpipe-pipeline-patterns` SKILL.md section "Per-Class Page-Key Pull from `MetadataBank`" — quick-reference table and the lazy-vs-auto trade-off.
- `src/main/kotlin/Context/MetadataBank.kt` — the bank primitive itself. Both the blocking `pullMetaPageKeysInto` and the coroutine `pullMetaPageKeysIntoSuspend` are documented at the file's top-level KDoc.