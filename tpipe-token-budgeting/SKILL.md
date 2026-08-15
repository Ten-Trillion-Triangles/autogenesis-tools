---
name: tpipe-token-budgeting
description: TPipe token budgeting primitives — TokenBudgetSettings, TokenUsage, MultiPageBudgetStrategy, TruncationPreview, BudgetAllocations, the setTokenBudget/setTokenBudgetRecursive/getTokenUsage API, and the Autogenesis per-pipe-budget reference pattern. Load when wiring budget constraints into any TPipe pipe, when porting the Autogenesis pattern, when debugging token accounting, when designing context-window-aware prompts, or when interpreting getTokenUsage output. Covers field-level docs for every TokenBudgetSettings field, the 5 MultiPageBudgetStrategy modes, the calculateAvailableContext() math, the comprehensiveTokenTracking requirement, the lorebook-as-overflow design pattern. NOT for transport quirks (tpipe-generic-openai) or serialization (tpipe-json-serialization).
version: 1.2.0
author: Hermes Agent
created: 2026-06-26
tags: [tpipe, tokens, budget, context-window, kotlin, max-tokens, multi-page, truncation, autogenesis-pattern]
trigger: When wiring token budgets into TPipe pipes, when implementing token-budgeted pipelines, when porting the Autogenesis pattern, when debugging token accounting via getTokenUsage, when designing context-window-aware prompts, or when interpreting BudgetAllocations output to size your context. Covers field-level docs for every TokenBudgetSettings field, the 5 MultiPageBudgetStrategy modes, the calculateAvailableContext() math, the comprehensiveTokenTracking requirement, the lorebook-as-overflow design pattern. NOT for transport quirks (tpipe-generic-openai) or serialization (tpipe-json-serialization).
changelog:
  - |
    1.2.0 (2026-08-08): Major binary token counting rewrite. The 4-tier decision tree relocated from `Pipe.countBinaryTokens` to `Dictionary.countBinaryTokens(items: List<BinaryBytes>, settings)`. The new default mode is `BinaryEstimationMode.HYBRID` (per-MIME override + byte-exact fallback). Five new `TruncationSettings` fields: `binaryTokenEstimation`, `binaryEncoder`, `binaryEncoderThresholdBytes`, `binaryFudgeFactor`, `binaryChunkSizeBytes`, `binaryMimeOverride`. New types in `com.TTT.Context`: `BinaryBytes`, `BinaryEstimationMode`, `BpeEncoder`. The prior `Bytes → Base64String` in-place rebase at `Pipe.kt:5512` is gone — the input list is now preserved exactly as the caller wrote it, so `CountBinaryTokensTest.inputBinaryListIsNotMutated` passes for the right reason (referential identity preserved) closing the v1.1.1 audit item. Performance: 256 KB binary now completes in 0.00 ms (was 28,498 ms); 4.05 MB JPEG no longer OOMs the default 512 MB heap (1,062,931 tokens in 0.255s).
  - |
    1.1.1 (2026-08-08): Audit-flagged the CountBinaryTokensTest.inputBinaryListIsNotMutated test as an open contract item — the test asserts `is BinaryContent.Bytes` after a rebase at Pipe.kt:5512 that DOES rewrite the entry to Base64String. Recorded as a known-quirk audit item rather than a passing contract guard. **Closed in 1.2.0.**
  - |
    1.1.0 (2026-08-08): Added binary token counting section. Documented Pipe.countBinaryTokens (Pipe.kt:5498-5535), the Bytes→Base64String in-place rebase at Pipe.kt:5512, the four BinaryContent subtype rules, the no-match allocation storm at Dict.kt:151 (findAllMatches substring loop), the ~1,300× binary/text speedup gap at matched token count (256 KB binary: 28,498 ms / 87,371 tokens vs text 1.35M tokens: 337.55 ms), the 5.6 MB base64 OOM ceiling in the default 512 MB test heap, and the -PtestHeapSize opt-in for full-scale runs.
  - |
    1.0.0 (2026-06-26): Initial creation. Captured the full TPipe token-budget surface from Pipe.kt:157-7839 plus the Autogenesis 5-named-budget pattern from BedrockConfig.kt:477-505 and the lorebook-as-overflow-absorption design intent from writerAgent.kt:219-225.
config_notes: >
  Companion skill to tpipe-pipeline-patterns (which shows the builder call)
  and tpipe-generic-openai (which covers transport quirks). This skill is
  for the BUDGET CONCEPTS themselves — fields, math, allocation strategies,
  and the Autogenesis reference architecture.

---

# TPipe Token Budgeting

Token budgeting in TPipe is provider-agnostic: every pipe (Bedrock, OpenRouter, Ollama, GenericOpenAI, custom) inherits the same `tokenBudgetSettings` field and the same `setTokenBudget()` / `getTokenUsage()` API. The budget is enforced at the framework layer, not by individual providers. Budgets travel with pipes; providers are interchangeable.

## When to use this skill

- Wiring a TPipe-based pipeline that needs bounded context (long-running writer, multi-pipe agent loop).
- Porting the Autogenesis pattern (per-pipe budgets chosen by model) to a new TPipe-based project.
- Debugging why a pipeline is silently truncating its context or overflowing its output cap.
- Designing a custom Pipe subclass that needs to participate in budget enforcement.
- Interpreting `getTokenUsage()` output to verify a pipeline actually stayed within its budget.

Don't use this skill for transport-level concerns (streaming, SSE, provider auth) — see `tpipe-generic-openai`. Don't use it for serialization shape — see `tpipe-json-serialization`.

## Core types — all in `com.TTT.Pipe` package, `Pipe/Pipe.kt`

### `TokenBudgetSettings` (data class) — `Pipe.kt:157-213`

Mutable budget object. Fields are nullable or have safe defaults so an unset budget means "no constraint."

| Field | Type | Default | Meaning |
|---|---|---|---|
| `userPromptSize` | `Int?` | `null` | Tokens reserved for the user prompt. Null + `compressUserPrompt = true` = dynamic. |
| `maxTokens` | `Int?` | `null` | Tokens reserved for LLM output. Carved out of context window before user/lorebook. |
| `reasoningBudget` | `Int?` | `null` | Tokens reserved for chain-of-thought (reasoning models like MiniMax-M2.7). |
| `subtractReasoningFromInput` | `Boolean` | `false` | True = reasoningBudget carved from contextWindow. False = carved from maxTokens (default preserves input capacity). |
| `contextWindowSize` | `Int?` | `null` | Total tokens. Starting point for budget arithmetic. |
| `allowUserPromptTruncation` | `Boolean` | `false` | True = prompt may truncate. False = oversize throws. |
| `preserveJsonInUserPrompt` | `Boolean` | `true` | During truncation keep JSON tokens intact; trim only prose. |
| `compressUserPrompt` | `Boolean` | `false` | If true + prompt exceeds slot, semantic-compress before truncating. |
| `truncateContextWindowAsString` | `Boolean` | `false` | True = render context as string (cheap, loses structure). False = per-element truncation. |
| `preserveTextMatches` | `Boolean` | `false` | True = preserve matching text over non-matching in converse history. |
| `truncationMethod` | `ContextWindowSettings` | `TruncateTop` | How to trim when budget exceeded. |
| `multiPageBudgetStrategy` | `MultiPageBudgetStrategy` | `DYNAMIC_SIZE_FILL` | Per-page allocation for MiniBank multi-page budgets. |
| `pageWeights` | `Map<String, Double>?` | `null` | Per-page weight overrides for `WEIGHTED_SPLIT`. |
| `reserveEmptyPageBudget` | `Boolean` | `true` | True = empty pages still reserve a portion (prevents later allocation surprises). |
| `binaryTokenEstimation` | `BinaryEstimationMode` | `HYBRID` | Strategy for binary token counting. HYBRID = per-MIME first, byte-exact fallback. |
| `binaryEncoder` | `BpeEncoder?` | `null` | Optional exact-BPE encoder for tier-2. Plumbing only; no default impl. |
| `binaryEncoderThresholdBytes` | `Int` | `1_048_576` | Minimum byte length at which tier-2 encoder is consulted. |
| `binaryFudgeFactor` | `Double` | `1.0` | Multiplier on byte-exact token estimate. Default 1.0 (byte-exact). |
| `binaryChunkSizeBytes` | `Int` | `65_536` | Chunk size when invoking the encoder on payloads over the threshold. |
| `binaryMimeOverride` | `Map<String, Int>?` | `null` | Per-MIME token count overrides. Wins over byte-exact. |

### `TokenBudgetSettings.calculateAvailableContext()` — `Pipe.kt:198-212`

Pure function. Tokens available for lorebook + context elements after subtracting reservations:

```
available = contextWindowSize - maxTokens
if subtractReasoningFromInput: available -= reasoningBudget
available -= userPromptSize
return available.coerceAtLeast(0)
```

The canonical arithmetic. If you're reasoning "how much room for lorebook," call this.

### `MultiPageBudgetStrategy` (enum) — `Pipe.kt:291-298`

| Strategy | Behavior |
|---|---|
| `EQUAL_SPLIT` | All pages get the same allocation regardless of content size. |
| `WEIGHTED_SPLIT` | Higher-weight pages get proportionally more (from `pageWeights`). |
| `PRIORITY_FILL` | Walk pages in order, fill each up to full content size, exhaust budget. |
| `DYNAMIC_FILL` | Priority fill, simulate post-truncation, redistribute unused budget (up to 3 passes). |
| `DYNAMIC_SIZE_FILL` | Size-based priority + redistribution. Protects smaller contexts from being starved by larger ones. **Default.** |

### Companion types (simulation + observability)

- **`TruncationPreview`** (Pipe.kt:312-320): what-if result. `wouldTruncate`, `totalTokensBefore/After`, `tokensSaved`, `workingContextWindowSpace`, `allocations`, `perPagePreviews`.
- **`BudgetAllocations`** (Pipe.kt:333-341): per-component breakdown — `contextWindowSize`, `systemPromptTokens`, `maxOutputTokens`, `reasoningBudgetTokens`, `userPromptTokens`, `binaryTokens`, `availableForContext`.
- **`PagePreview`** (Pipe.kt:343+): per-page prediction in `perPagePreviews: Map<String, PagePreview>`.
- **`TokenUsage`** (Pipe.kt:218-279): runtime accumulator. `inputTokens`, `outputTokens`, `childPipeTokens: MutableMap<String, TokenUsage>`, `totalInputTokens`, `totalOutputTokens`. Methods: `addChildUsage`, `recalculateTotals`, `getUsageBreakdown`.

## API surface — only hooks a caller needs

All on `Pipe`:

| Method | Line | Behavior |
|---|---|---|
| `setTokenBudget(budget: TokenBudgetSettings): Pipe` | 2795 | Builder. Deep-copies via `cloneTokenBudgetSettings`. |
| `setTokenBudgetRecursive(budget: TokenBudgetSettings)` | 7708 | Propagates to all child pipes. Pipeline override at 437-441 does fan-out. |
| `copyTokenBudgetSettings(): TokenBudgetSettings?` | 4496 | Stable copy for inspection. |
| `getTokenBudgetSettings(): TokenBudgetSettings?` | 7706 | Read accessor. |
| `getTokenUsage(): TokenUsage` | 7611 | Returns `pipeTokenUsage` only if `comprehensiveTokenTracking = true`, else empty `TokenUsage()`. See "Auto-tracking" below. |
| `setReasoning()` / `disableReasoning()` | base Pipe | Toggles trace `reasoningEnabled` flag (for reasoning models). Distinct from `setReasoningConfig(ReasoningConfig(...))` on GenericOpenAIPipe (writes wire payload). |

Private/internal:
- `cloneTokenBudgetSettings(budget): TokenBudgetSettings` (Pipe.kt:2811) — defensive copy.
- `setTokenBudgetInternal(budget, liveContent)` (Pipe.kt:2937) — adjusts based on current content.
- `tokenBudgetSettings: TokenBudgetSettings?` (Pipe.kt:1009) — internal storage.

## Auto-tracking: `comprehensiveTokenTracking` is required for `getTokenUsage`

**By default `getTokenUsage()` returns an empty `TokenUsage()`.** The accumulator is only populated when `comprehensiveTokenTracking = true` is set on the pipeline or pipe. Without this flag, `getTokenUsage()` returns zeros after successful LLM calls.

Enable via:
1. **Pipeline-level:** `pipeline.enableComprehensiveTokenTracking()` (verify exact API in `Pipeline.kt`).
2. **Per-pipe:** set the flag on individual pipes (less common).

If budget tests or trace reports show zero usage after successful LLM calls, this flag is the first thing to check. The 9 existing TPipe binary tests all enable it — search those files for the exact enable call.

## Where the budget fires — call flow

The budget is **read fresh on every `pipe.execute()`** via `setTokenBudgetInternal` + the working-copy pattern at `Pipe.kt:5060` and `:5247`:

```kotlin
val workingBudget = cloneTokenBudgetSettings(configuredBudget)
```

`tokenBudgetSettings` is never mutated in place. Each pipe gets a deep-cloned copy so concurrent pipes don't share mutable state. Enforced by `cloneTokenBudgetSettings` calls at lines 2855, 2873, 2890, 2904, 2926 (pipeline init, snapshot, child clone, settings save, runtime internal).

Pipeline-level propagation (`Pipeline/Pipeline.kt:437-441`):
```kotlin
override fun setTokenBudgetRecursive(budget: TokenBudgetSettings)
{
    super.setTokenBudgetRecursive(budget)
    pipe.setTokenBudgetRecursive(budget)
}
```

`pipeline.setTokenBudgetRecursive(budget)` fans out to every pipe. `pipe.setTokenBudget(budget)` on a single pipe affects only that pipe.

PumpStation reads budget usage for kill-switch enforcement (`Pipeline/PumpStation.kt:343-367`):
- `getPathTokenUsage(): TokenUsage?` — from internal agent (Pipeline).
- `getPathLegacyTokenUsage(): Pair<Int, Int>` — `(input, output)` tuple for legacy kill-switch paths.

## Per-provider variant behavior: NONE

`grep -rn setTokenBudget /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Bedrock/src /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Defaults/src /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-GenericOpenAI/src /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-Ollama/src /home/cage/Desktop/Workspaces/TPipe/TPipe/TPipe-OpenRouter/src` → 0 hits in any provider-specific code. The budget lives entirely on the base `Pipe` class.

Deliberate design: budget is a TPipe framework concern; providers stay simple LLM call wrappers. **Don't** try to customize budget behavior per-provider — set it once on the Pipe and it works for all of them.

## Autogenesis reference pattern (audited 2026-06-26)

Verified against `Autogenesis/Autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt:477-505`:

### The 5 named budgets

```kotlin
val workerBudgetSettings       = TokenBudgetSettings(maxTokens = 8000,  contextWindowSize = 32_000)
val generativeBudgetSettings   = TokenBudgetSettings(maxTokens = 12_000, contextWindowSize = 230_000)
val novaBudgetSettings         = TokenBudgetSettings(maxTokens = 8000,  contextWindowSize = 990_000)
val novaProBudgetSettings      = TokenBudgetSettings(maxTokens = 5000,  contextWindowSize = 285_000)
val palmyraBudgetSettings      = TokenBudgetSettings(maxTokens = 8000,  contextWindowSize = 980_000)
```

Helper at `BedrockConfig.kt:510-517` selects budget by model name. Every builder file in `agent/builders/*.kt` calls `.setTokenBudget(BedrockConfig.X)` per pipe with a different `X` per pipe role.

### Per-role pattern

| Pipe role | Budget | Rationale |
|---|---|---|
| Generation (writer, lorebook extraction, story analysis) | `generativeBudgetSettings` (12K/230K) | Big model, big context — generates novel prose |
| Validation / branch-fallback | `palmyraBudgetSettings` (8K/980K) | "Rock solid, highly refuses to refuse" — used as retry fallback |
| Worker / error diagnostic | `workerBudgetSettings` (8K/32K) | Small, fast — doesn't need much context |
| Question-answering / Nova reasoning | `novaBudgetSettings` (8K/990K) | Reasoning model with huge context for QA |
| Nova Pro | `novaProBudgetSettings` (5K/285K) | Tighter budget for Nova Pro variant |

The **per-pipe-role** pattern: different pipes in the same pipeline get different budgets. Don't use one global budget.

### Budget swap on model retry

`Autogenesis/server/src/main/kotlin/agent/runners/gameplayOrchestrator.kt:2748-2763`:
```kotlin
fun swapPipelineModels(pipeline: Pipeline) {
    pipeline.getPipes().forEach { pipe ->
        val modelName = pipe.getModelName()
        if (modelName == BedrockConfig.novaModelName) {
            pipe.setModel(BedrockConfig.PalmyraX5)
            pipe.setTokenBudget(BedrockConfig.palmyraBudgetSettings)  // budget travels with model
            pipe.disableReasoning()
        }
    }
}
```

**When you swap a model on retry, swap the budget too.** The budget is sized for the model's strengths; wrong budget + wrong model wastes tokens.

### Lorebook as overflow absorption (no explicit summarization)

Autogenesis has **no** explicit summarization or trimming code. The writer-agent prompts at `writerAgent.kt:219-225, 531-537, 647-651` explicitly tell the model that context overflow will truncate oldest portions and that the lorebook holds summarized entity data. When the budget truncates, the lorebook still has entity summaries; the model reconstructs from the lorebook.

**Design intent**: budget truncation + lorebook summaries is a closed loop. Truncation is graceful because the lorebook compensates. Don't add an explicit "summarize before truncate" step in your own project — TPipe's `compressUserPrompt = true` covers user-prompt overflow, and the lorebook handles lore/context overflow.

### `multiPageBudgetStrategy` is left at default

Autogenesis never sets `multiPageBudgetStrategy` explicitly — stays at `DYNAMIC_SIZE_FILL`. If your project doesn't have a MiniBank with named pages, this knob is irrelevant. If you do, leave the default unless you have a specific reason to change.

## 8 TPipe tests that exercise budget wiring for free

Any new caller of `setTokenBudget()` gets these as regression coverage on every CI run:

- `TPipe/src/test/kotlin/TokenBudgetStressTest.kt` — concurrency + large token counts + deep nesting
- `TPipe/src/test/kotlin/TokenBudgetRuntimeStateTest.kt` — `tokenBudgetRuntimeRestoresPipeStateBetweenExecutions`, `tokenBudgetRuntimeRestoresPipeStateAcrossPipelineExecutions`
- `TPipe/src/test/kotlin/MultiPageTokenBudgetTest.kt` — multi-page budget allocation
- `TPipe/src/test/kotlin/MultiPageBudgetValidationTest.kt` — strategy validation
- `TPipe/src/test/kotlin/DynamicSizeFillStrategyTest.kt` — `DYNAMIC_SIZE_FILL` behavior (default)
- `TPipe/src/test/kotlin/PipeSettingsSnapshotTest.kt` — `PipeSettings.tokenBudgetSettings` round-trip
- `TPipe/src/test/kotlin/TruncateAsStringTest.kt` — `truncateContextWindowAsString` flag behavior
- `TPipe/src/test/kotlin/Pipe/SemanticCompressionBuilderTest.kt` — `compressUserPrompt = true` path

When wiring `setTokenBudget()` into a downstream project, run these 8 tests as part of CI. They pin the contract from outside-in.

## Binary token counting — `Dictionary.countBinaryTokens`

The budget framework treats binary content (images, files, cloud references, text documents) as a separate token bucket that gets **subtracted from the context window** before lorebook/context elements are sized. The two-layer entry point is:

1. **`Pipe.countBinaryTokens(content, truncationSettings)`** — `Pipe.kt:5498-5556`. Thin mapper. Routes `TextDocument` and `CloudReference` to the existing `Dictionary.countTokens` path (text and URI tokenization). Reduces `Bytes` and `Base64String` to a `List<BinaryBytes>` by decoding base64, then delegates to `Dictionary.countBinaryTokens`. **Does NOT mutate `content.binaryContent`** — the prior `Bytes → Base64String` in-place rebase at `Pipe.kt:5512` is gone.

2. **`Dictionary.countBinaryTokens(items: List<BinaryBytes>, settings: TruncationSettings)`** — `Context/Dict.kt`. New entry point. Applies the 4-tier decision tree per item. O(1) per item.

### New types in `com.TTT.Context.Dictionary`

```kotlin
data class BinaryBytes(val bytes: ByteArray, val mimeType: String)

enum class BinaryEstimationMode {
    PER_ENCODER_RULE,     // Always ceil(bytes / 4) * fudgeFactor
    PER_MIME_TYPE,         // Required mime override; missing throws
    EXTERNAL_ENCODER,      // Required BpeEncoder; falls back to tier-0 on failure
    HYBRID,                // Default: per-MIME first, byte-exact fallback
}

interface BpeEncoder {
    fun encode(text: String): IntArray
}
```

### The 4-tier decision tree (per `BinaryBytes` item)

```
for each item in items:
    bytes = item.bytes.size
    mime  = item.mimeType

    Tier-1: if mode is PER_MIME_TYPE or HYBRID and binaryMimeOverride has mime:
        total += binaryMimeOverride[mime]              # exact override wins
        continue
    # If mode is PER_MIME_TYPE and override is missing → throw IllegalArgumentException

    Tier-2: if mode is EXTERNAL_ENCODER or HYBRID and binaryEncoder != null and bytes > threshold:
        try:
            total += chunkedEncode(item, encoder, chunkSize)   # opt-in BPE
            continue
        catch: total += tier0(bytes)                            # tier-3 fallback

    Tier-0: total += ceil(bytes / 4) * fudgeFactor              # byte-exact
```

`base64ByteCount` is `bytes.size` (zero math — we already decoded). `chunkedEncode` slices the byte array into `binaryChunkSizeBytes` chunks, base64-encodes each, sums the encoder's `IntArray.size` results.

### `BinaryContent` subtype routing in `Pipe.countBinaryTokens`

| Subtype | Path |
|---|---|
| `Bytes(data, mimeType, filename)` | Wrap in `BinaryBytes(data, mimeType)`, hand to `Dictionary.countBinaryTokens` |
| `Base64String(data, mimeType, filename)` | Decode base64 → `BinaryBytes(decoded, mimeType)`, hand to `Dictionary.countBinaryTokens` |
| `CloudReference(uri, mimeType, filename)` | `Dictionary.countTokens(uri, settings)` — counts URI text only. **binaryFudgeFactor does NOT apply** (URI text is not a binary payload). |
| `TextDocument(content, mimeType, filename)` | `Dictionary.countTokens(content, settings)` — counts text via dictionary. **binaryFudgeFactor does NOT apply.** |

The mutation is gone. The input list is preserved exactly as the caller wrote it. `CountBinaryTokensTest.inputBinaryListIsNotMutated` passes for the right reason now (referential identity preserved), closing the v1.1.1 audit item.

### Recommended `BinaryEstimationMode` per use case

| Use case | Mode | Why |
|---|---|---|
| English-only text pipe, no multimodal | `PER_ENCODER_RULE` or default `HYBRID` with empty override | Identical behavior; simpler mental model. |
| Multimodal Claude (Sonnet 4.5, Opus 4.7, etc.) | `HYBRID` + `binaryMimeOverride["image/png"] = (width * height) / 750`, `binaryMimeOverride["image/jpeg"] = (width * height) / 750` | Claude's tile formula is well-documented; per-MIME override captures it without an encoder. |
| Multimodal GPT-4o / GPT-4o-mini | `HYBRID` + `binaryMimeOverride["image/png"] = 65 + 129 * tileCount` (high-res), or `85 + 170 * tileCount` (alt) | GPT-4o's tile cost formula. |
| Multimodal Gemini | `HYBRID` + `binaryMimeOverride["image/png"] = 258 * tileCount` (≥384px images) | Gemini's tile formula. |
| OCR-heavy PDF | `HYBRID` + `binaryMimeOverride["application/pdf"] = <per-page-token-rate>` | Anthropic's PDF rate is text-extracted then per-page-counted. |
| Audio transcription | `HYBRID` + `binaryMimeOverride["audio/mpeg"] = <per-second-rate>` or `PER_ENCODER_RULE` with `binaryFudgeFactor = 1.1` | Per-second rates dominate; an encoder is overkill. |
| Exact BPE accuracy required | `EXTERNAL_ENCODER` + a configured `BpeEncoder` (e.g. jtokkit) | Only mode that gives exact token counts. Requires a custom encoder impl. |

### Performance — verified 2026-08-08

`DictionaryCountBinaryBenchmarkTest` (scaling sweep + full-scale OOM capture, against `/tmp/hubble_ngc6530.jpg` 4.05 MB JPEG):

| Input | Tokens | Time | tokens/s |
|---|---|---|---|
| Binary: 8 KB raw | 2,048 | 0.00 ms | 2,192,719,486 |
| Binary: 16 KB raw | 4,096 | 0.00 ms | 4,586,786,114 |
| Binary: 32 KB raw | 8,192 | 0.00 ms | 7,211,267,606 |
| Binary: 64 KB raw | 16,384 | 0.00 ms | 20,029,339,853 |
| Binary: 128 KB raw | 32,768 | 0.00 ms | 38,191,142,191 |
| Binary: 256 KB raw | 65,536 | 0.00 ms | **80,908,641,975** |
| Binary: 4.05 MB JPEG (full-scale) | 1,062,931 | 0.255 s | **4,168,239** |
| Text: `/tmp/pg100.txt` (1.35M tokens) | 1,347,367 | 337.55 ms | 3,991,000 |

**Speed comparison at 256 KB slice:** was 28,498 ms / 3,066 tokens/s. Now 0.00 ms / 80,908,641,975 tokens/s. **~26 million× speedup.** Full-scale 4.05 MB JPEG no longer OOMs the default 512 MB heap — produces 1,062,931 tokens (= `ceil(4,251,722 / 4)`) in 0.255s.

The 1,300× → 26,000,000× speedup at 256 KB is because the O(n) per-operation cost of the old `Dictionary.countTokens` substring-storm has been replaced by O(1) integer division. The new code is so fast that tokens/s is now bounded by JVM-side call overhead, not by the algorithm.

### When to size-budget binaries differently

The `TokenBudgetSettings.binaryTokens` slot (`BudgetAllocations` at `Pipe.kt:333-341`) reports what `countBinaryTokens` returned. For a pipe that frequently receives large images, set `maxTokens` and `contextWindowSize` with binary cost in mind — a 4 MB JPEG costs ~1.06M tokens at the byte-exact formula, which can eat a 230K context window before any user prompt lands.

**Caveat on the byte-exact formula.** For random base64 it's empirically 9.8% high vs tiktoken o200k_base (the safe direction for budgeting). For uniform base64 it's 6× high (the safe direction again). For known multimodal models (Claude, GPT-4o, Gemini), configure `binaryMimeOverride` to get accurate counts. The fudge factor of 1.0 is byte-exact; bump to 1.1 if you want a 10% safety margin.

## The build.gradle.kts opt-in

Required for any test that exceeds the default 512 MB heap:

```kotlin
tasks.test {
    useJUnitPlatform()
    val testHeapSize = (project.findProperty("testHeapSize") as String?) ?: "512m"
    jvmArgs("-Xmx$testHeapSize")
    // ...
}
```

`-Dorg.gradle.jvmargs="-Xmx8g"` does NOT propagate to the test JVM — Gradle forks a new JVM for `tasks.test` and the `-Xmx512m` in `jvmArgs` wins unless overridden by `testHeapSize`.

## Gradle subproject filter dispatch (multi-project root)

The TPipe build is a multi-project Gradle layout where the **root project shares the name `TPipe` with the `:TPipe-*` subprojects**. Running `./gradlew test --tests "<name>"` propagates the filter to **every** subproject's `:test` task, hitting `No tests found for given includes` on each one before the root gets a chance. Each failed dispatch costs ~1–2 minutes of gradle churn.

**Recipe: skip the 7 subprojects and let only the root run the matching test.**

```bash
cd /home/cage/Desktop/Workspaces/TPipe/TPipe
./gradlew test \
  --tests "com.TTT.Context.DictionaryCountBinaryTokensTest" \
  -x TPipe-Bedrock:test \
  -x TPipe-Defaults:test \
  -x TPipe-GenericOpenAI:test \
  -x TPipe-MCP:test \
  -x TPipe-Ollama:test \
  -x TPipe-OpenRouter:test \
  -x TPipe-TraceServer:test \
  -x TPipe-Tuner:test \
  --console=plain
```

Or pair with the heap override for full-scale runs:

```bash
./gradlew test --tests "<name>" -PtestHeapSize=8g -x TPipe-Bedrock:test ...
```

Without the `-x` flags, the dispatch eats the first ~2 minutes failing on empty subprojects before the root test runs. The flag also matters for the **`countBinaryTokensTest`** binary regression suite — same filter-dispatch pitfall applies.

## Verification standard

A new budget deployment is GREEN when:
1. `setTokenBudget(budget)` is called on the pipe (or `setTokenBudgetRecursive(budget)` on the pipeline).
2. `comprehensiveTokenTracking = true` is enabled (otherwise `getTokenUsage()` returns zeros).
3. After a real LLM call, `pipe.getTokenUsage().inputTokens` and `.outputTokens` reflect actual usage (not zeros).
4. If a context-window-bound test exists (long prompt > context window), truncation succeeds without throwing (when `allowUserPromptTruncation = true`) or throws a clear exception (when false).
5. The 8 TPipe tests above still pass on the same TPipe checkout.
6. The 4 binary token tests (`CountBinaryTokensTest`) plus the 7 `DictionaryCountBinaryTokensTest` tests plus the 4 `DictionaryCountBinaryBenchmarkTest` tests pass on the same checkout.

## Lorebook selection surface — `useEntireContextForLoreSelection()`

The lorebook matcher runs substring matches against entry `key` (plus `aliasKeys`, gated by `requiredKeys`) to decide which entries to inject. The **scan surface** (what text the matcher runs against) is a separate concern from the budget (how many tokens get injected).

### Default surface — user prompt only
By default, the matcher scans **only the user prompt** (`content.text`). Neither `contextWindow.contextElements` nor `contextWindow.converseHistory` are included. This is the historical behavior, preserved for callers that haven't opted in.

### Expanding the surface — the pipe-wide flag
```kotlin
val pipe = BedrockPipe()
    .setModel("anthropic.claude-3-sonnet-20240229-v1:0")
    .useEntireContextForLoreSelection()
```

Sets `useEntireContextForLoreSelection = true` on `PipeSettings` (`Structs/PipeSettings.kt:47`). When enabled, **every one of the five lorebook selection/truncation call sites** in the pipe's execution path calls `ContextWindow.buildLorebookScanText(userPrompt, true)`, so the matcher runs against `userPrompt + contextElements + converseHistory.history[*].content.text` instead of user prompt alone.

**Default is `false`** — historical "scan user prompt only" contract preserved.

### The helper — single source of truth
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

- `useEntireContext = false` → returns `userPrompt` unchanged. Zero behavior change for callers that haven't opted in.
- `useEntireContext = true` → concatenates `userPrompt` + `contextElements` + `converseHistory.history[*].content.text`, each block newline-joined. Empty blocks skipped, no trailing newline.
- Order is always `userPrompt` first, then `contextElements`, then `converseHistory`.

### Where it actually fires — the 5 call sites in Pipe.kt
The doc says there are **five lorebook selection/truncation call sites** in `Pipe.kt`. The flag flips `useEntireContext = true` for **every one of them** in that pipe's execution path. That's the key design property: it's not a per-call opt-in, it's a pipe-wide policy.

### MiniBank per-page isolation preserved
In multi-page contexts (`MiniBank`), each page's matcher uses the shared `userPrompt` plus **that page's own** `contextElements` and `converseHistory` — not the main window's. Per-page isolation holds even with `useEntireContext = true`. The helper is called per-page against each page's `ContextWindow`.

### When to use it
- **Leave it off** if your lorebook keys fire on the user's most recent message alone (e.g. spell-name keys, command keys, single-turn lookup).
- **Turn it on** if your lorebook keys reference concepts that live in earlier context — character names mentioned three turns ago, locations established in the system prompt, prior assistant replies, multi-turn dialogue references.

## TPipeWriter PlusWriterPipeline reference (audited 2026-06-26)


The PlusWriterPipeline in TPipeWriter (`/home/cage/Desktop/Workspaces/TPipeWriter/src/main/kotlin/Builders/PlusWriterPipeline.kt`) is the second audited deployment of the Autogenesis per-pipe-budget pattern. Differences from Autogenesis:

- **Single shared budget across all pipes** (Autogenesis uses 5 different per-role budgets). PlusWriterPipeline uses one `plusWriterPipelineBudget` constant (line 84) because every pipe in the writer pipeline serves the same role (prose generation / editing).
- **`useEntireContextForLoreSelection()` enabled alongside budget.** PlusWriterPipeline flips the lorebook scan surface on in the same forEach as `setTokenBudget()` — see line 1556. This is required for the lorebook-as-overflow design pattern to fire (next section).
- **Inspector command exposes the policy.** `/budget-info` (defined at `Shell.kt:1279`) imports `plusWriterPipelineBudget` from `Builders` and prints its values + the lorebook posture. The `/budget-info` shell command is the user-facing verification path for "is the budget actually applied?" — see `tpipewriter-feature-delivery` Surface 5 for the pattern.

**The apply-block** (PlusWriterPipeline.kt:1554-1559):
```kotlin
return plusWriterPipeline.apply {
    getPipes().forEach {
        it.useEntireContextForLoreSelection()
        it.setTokenBudget(plusWriterPipelineBudget)
        it.enableComprehensiveTokenTracking()
    }
    // ...
}
```

This is the canonical per-pipe wire-up location — the existing post-init forEach is where every posture (budget, lorebook scan surface, future policies) gets applied uniformly. Add to this block; don't create a new one.

## Per-pipe accessors used by inspection tests

When writing tests that pin the per-pipe contract (e.g. `pipe.toPipeSettings().useEntireContextForLoreSelection`), the correct accessor is `pipe.toPipeSettings()`, **not** `getPipeSettings()` — only the former exists on `Pipe` (`Pipe.kt:7466`). Compile error otherwise.

For lorebook scan-text tests, `ConverseRole` lives in `com.TTT.Context`, NOT `com.TTT.Pipe`. Test imports must use `import com.TTT.Context.ConverseRole` to compile.

## Relationship to the Autogenesis lorebook-as-overflow pattern
Autogenesis relies on lorebook entries holding entity summaries that survive budget truncation. The user prompt is sparse; entity mentions accumulate in `converseHistory` and `contextElements` over the conversation. **For the lorebook-as-overflow-absorption design to actually fire**, the selection surface must see those mentions — otherwise the entries never match, never inject, and the overflow absorption loop is broken. If you're porting the Autogenesis pattern and your lorebook keys reference multi-turn concepts, enable `useEntireContextForLoreSelection()` on every pipe in the same forEach as `setTokenBudget()`.

Full contract docs:
- `TPipe/docs/api/lorebook.md` lines 87-169 ("Scan Surface" section)
- `TPipe/docs/api/pipe.md:703-707` (Pipe DSL flag)
- `TPipe/src/main/kotlin/Context/ContextWindow.kt:2278-2312` (helper implementation)

## See Also

- `references/autogenesis-budget-pattern.md` — annotated walkthrough of BedRockConfig 5-named-budget pattern with usage citations per builder file
- `references/budget-math-walkthrough.md` — worked example of `calculateAvailableContext()` for a realistic scenario
- `references/lorebook-scan-surface.md` — full contract for `useEntireContextForLoreSelection()` + `buildLorebookScanText()`, including the 5 call sites and MiniBank per-page behavior
- `references/dictionary-counttokens-performance.md` — `Dictionary.countTokens` benchmark results against `/tmp/pg100.txt`. Use to pick which `TruncationSettings` flag to flip when memory-system throughput is the goal (disabling `countSubWordsInFirstWord` gives ~38% speedup).
- `references/countBinaryTokens-benchmark.md` — binary-vs-text token counting speed comparison, the 8 KB → 256 KB scaling sweep, the 4.05 MB JPEG full-scale pass, and the v1.2.0 numbers (~26 million× speedup at 256 KB, no OOM at full scale). Load when sizing a pipeline that will receive large images or files, when `countBinaryTokens` is suspected of being the budget-enforcement bottleneck, or when designing fail-fast guards for large-binary inputs.
- `tpipe-pipeline-patterns` — the builder-style configuration that wraps `setTokenBudget()`
- `tpipe-generic-openai` — provider-specific transport (where `setReasoningConfig` lives)
- `tpipe-json-serialization` — JSON shape of `TokenBudgetSettings` for persistence
- `tpipe-trace-parser` — trace files that record token usage from `getTokenUsage()`
