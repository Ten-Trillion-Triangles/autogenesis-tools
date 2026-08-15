---
name: tpipe-context-budget-truncation
description: "TPipe context budgeting + truncation mechanics: TokenBudgetSettings.calculateAvailableContext() formula, TruncateTop default truncation method, the per-pipe context budget hardcoded in autogenesis BedrockConfig.kt (workerBudgetSettings, generativeBudgetSettings, palmyraBudgetSettings, novaBudgetSettings, novaProBudgetSettings), and the per-agent context injection pattern via setPreInitFunction and ContextBank.emplaceWithMutex. Covers the BudgetSettings fields, the calculateAvailableContext math, TruncateTop vs TruncateBottom, MultiPageBudgetStrategy.DYNAMIC_SIZE_FILL default, the truncation + lorebook shield order, and how to read the relevant bytecode when source is not available. NOT for lorebook selection, NOT for context-pull builders, NOT for the Pipe lifecycle."
version: 1.7.0
author: Shitty Bob (TTT)
created: 2026-07-24
tags: [tpipe, context, budget, truncation, calculate-available-context, token-budget-settings, truncate-top, autogenesis, gemma-4-4b, model-swap, genericopenai-billing-exception, binary-tokens, base64, d0a17e48, three-tier-fallback]
changelog:
  1.5.0: "Implementation shipped at commit d0a17e48 on TPipe main (2026-08-08): the 1.2.0 integer-math contract and 1.3.0 design knobs are now the canonical code path. New reference references/binary-token-counting-implementation.md documents the three-tier fallback (tier-1 per-MIME / tier-2 chunked external encoder / tier-0 byte-exact) as it actually exists in Dictionary.countBinaryTokens, the six new TruncationSettings fields with their exact defaults, the 12-field override guard at BedrockPipe.kt:1628 and :1874 that propagates them, the build.gradle.kts testHeapSize property escape hatch, and the live NovaMultimodalImageLiveTest that proves the path end-to-end on a real amazon.nova-2-lite-v1:0 multimodal call. The body pitfall 'Binary payloads must NEVER flow through the dictionary tokenizer' is updated to point to this reference. The 'BedrockPipe has two nearly identical truncation when blocks' pitfall is corrected — current line numbers are 1617 and 1862, not 1211 and 1446. Test surface grew from the 8-case backward-compat baseline in the design doc to 6 new test files / 1094 LOC."
  1.7.0: "Mistral vision/audio formulas documented as references/mistral-vision-audio-token-formula.md (2026-08-08 Thread 03-mistral). Two formulas: (a) all 5 Mistral vision models share Pixtral-ViT — `tokens = W_t × H_t + (H_t − 1)` where `W_t = ⌈W'/16⌉`, `H_t = ⌈H'/16⌉`, after downscaling so `max(W, H) ≤ 1024`; source is `mistral-common/src/mistral_common/tokens/tokenizers/image.py` (MultiModalVersion.m1 config); (b) both Voxtral models share an identical Whisper-large-v3 + 4× adapter front-end — `tokens = ⌈audio_seconds × 12.5⌉` (1 token = 80 ms = 12.5 Hz); 32K ctx ≈ 40 min understanding / 30 min transcription. New pitfall added to the body: 'When the vendor's docs are silent on token math, the vendor's open-source tokenizer SDK is the authoritative source.' The Mistral research had to read `mistral-common/image.py` because the Pixtral paper describes the encoder abstractly (16×16 patches, RoPE-2D) but never gives the explicit `(W-1)//16 + 1` formula or the max-edge-downscale step. New pattern codified: the same pitfall applies to any LLM provider whose multimodal token-count is image/duration-dependent — for Mistral, Claude, and likely Gemini, the only authoritative source is the tokenizer SDK, not the model card, blog, or arXiv paper. Cross-reference to the existing `binaryMimeOverride cannot hold the correct count for Claude vision images` pitfall — same trap, different vendor. The Mistral findings explicitly recommend `PER_ENCODER_RULE` + a custom `MistralPixtralVisionEncoder` / `VoxtralAudioEncoder` plug-in for all 7 serverless Mistral models on Bedrock, with `binaryFudgeFactor = 1.0` (exact) and `binaryEncoderThresholdBytes = 0` (always use the encoder). The two encoders are ~30 lines of Kotlin each, porting the math from the Python SDK. See the new reference for worked examples (1920×1080 → 2339 tokens, 1024×1024 → 4159 tokens, 5 min audio → 3750 tokens) and full Kotlin pseudocode."
  1.6.0: "Claude 3 image formula in the design reference corrected (2026-08-08 Thread 01-anthropic). The previously-cited 'ceil(width × height / 750)' rule for Claude vision images is stale; the current Anthropic Vision docs specify a patch-based formula (⌈W/28⌉ × ⌈H/28⌉ visual tokens) capped per tier — Standard (Claude 3 Haiku, Claude 3 Sonnet, and all pre-4.7 models) caps at 1568 px long edge and 1568 visual tokens; High-resolution (Claude 4.7+) caps at 2576 px and 4784 tokens. Worked example: 1024×1024 JPEG → 37×37 = 1369 tokens (not 1398 from the old formula). The Claude PDF row in the design's per-MIME table now distinguishes the two Bedrock Converse API modes — Converse Document Chat (text-only, ~1000 tokens/3 pages, automatic when citations are disabled) vs Claude PDF Chat (full visual, ~7000 tokens/3 pages, requires citations). New pitfall added: 'binaryMimeOverride cannot hold the correct count for Claude images' — the patch formula depends on dimensions, which are not recoverable from a constant per-MIME map. A fixed entry like {image/jpeg: 1369} would only be correct for one specific image size. The correct integration is approach C/D (custom BpeEncoder plug-in that decodes JPEG/PNG headers, rescales to ≤1568 px, and returns IntArray(min(((W+27)/28)*((H+27)/28), 1568))). Worked Python pseudocode + Kotlin skeleton documented in the new references/anthropic-claude-vision-token-formula.md. The empirical library baseline's Tier 5 Claude citation is patched to the same correction."
  1.4.0: "Empirical library baseline added as references/binary-token-estimator-empirical-library-baseline.md (2026-08-08 Thread 02). The 1.2.0 contract and 1.3.0 design space rest on the claim 'real BPE on random base64 is approximately 1 token per 4 base64 chars'; that claim is now measured. Measured throughput on this host: tiktoken o200k_base 9-12 MB/s on 1-10 MB inputs, HuggingFace GPT-2 fast 1-2 MB/s, SentencePiece BPE+byte_fallback 9-11 MB/s. Measured accuracy: random base64 = 1.30 bytes/token across o200k_base AND GPT-2; random raw bytes = 0.57 bytes/token (SentencePiece byte_fallback) or 1.07 bytes/token (tiktoken private _encode_bytes). Memory cliff confirmed: tiktoken on 100 MB uniform A = 5.9 GB peak RSS, HF GPT-2 on 10 MB = 2.5 GB — exactly the magnitude the 'opt-in only, gated by binaryEncoderThresholdBytes' rule (1.3.0) was protecting against. Tiered library shortlist added: Tier 1 = JTokkit (com.knuddels:jtokkit:1.1.0, Maven Central, zero-dep, Java 8+, the JVM fit); Tier 2 = tiktoken-rs/tiktokenx via JNI bridge (only if o200k_harmony coverage is needed); Tier 3 = in-tree Karpathy/minbpe port (<300 LOC Kotlin, zero external dep, accuracy bounded by which merge table is loaded); Tier 4 = chars/4 with TruncationSettings.tokenCountingBias (current default, ~5-10% high side); Tier 5 = per-MIME carve-outs for Gemini 258/image + 263 tok/s video + 32 tok/s audio, Claude width*height/750, OpenAI 65+129/tile (low-fi) / 85+170*tile (high-fi). Decision tree at the bottom of the new reference is the implementation recipe. The '5-10% accuracy envelope' claim in the binary-payloads pitfall is now empirically supported rather than asserted."
  1.2.0: "Two pitfalls added in the binary-token-counting territory (2026-08-08 TPipe main-branch session). 'Binary payloads (especially base64) must NEVER flow through the dictionary tokenizer' — the dictionary tokenizer is O(n * maxMatchLength) on input with no whitespace and no dictionary entries, which base64 satisfies by construction. The previous countBinaryTokens routed 45,336-char base64 strings through Dictionary.countTokens and burned tens of milliseconds on a 34KB payload. Contract pinned: Bytes -> (byteSize+1)/2, Base64String -> (base64Length+3)/4, both pure integer math; CloudReference.uri and TextDocument.content remain on the dictionary tokenizer. 'A counting function that mutates its input is a separate bug' — the same countBinaryTokens was reassigning content.binaryContent[i] to a base64-converted copy on every Bytes branch, breaking idempotency and silently rewriting the input. Contract pinned: count* / estimate* / simulate* functions in TPipe must be side-effect-free; the regression test CountBinaryTokensTest > inputBinaryListIsNotMutated() pins this. Cross-reference: the bug was diagnosed on TPipe main, not the mcp-server branch — auto-injected AGENTS.md 'Branch:' lines are stale repo metadata, not live state."
  1.3.0: "Design space captured as a separate reference (binary-token-estimator-design.md, 2026-08-08). The 1.2.0 contract pins the integer-math fix; the operator asked for two further things in the 03-estimator-design session — 'adjustable settings for binary possibly' and 'close to how tokenizers behave with bytes' — which the integer-math contract alone does not address. The 5-approach design space (PER_ENCODER_RULE / PER_MIME_TYPE / EXTERNAL_ENCODER / HYBRID / chunked+cached) plus the TruncationSettings knobs (binaryTokenEstimation enum, binaryEncoder: BpeEncoder?, binaryFudgeFactor, binaryChunkSizeBytes, binaryMimeOverride) plus the per-MIME token-cost formulas for OpenAI / Claude / Gemini are now indexed in the reference file. Pin: do NOT widen the countBinaryTokens pitfall into a generic 'use BPE for everything' rule — approach A is the right default for arbitrary binary; approach C (real BPE) is opt-in only, gated by binaryEncoderThresholdBytes to avoid the 80 MB peak-memory cliff that real encoders hit on large payloads (https://www.dsdev.in/counting-tokens-at-scale-using-tiktoken). The 8 CountBinaryTokensTest cases must pass without modification under approach A; see the reference's backward-compat table."
  1.1.0: "Pitfall added: 'The GenericOpenAIPipe billing blind spot — endpoint returns inputTokens: 0, use TPipe's local estimate' (2026-07-31 autogenesis 25-round projection session). Captures the empirical exception that GenericOpenAIPipe providers don't return an endpoint input_tokens block; canonical billing truth for that pipe class is actualInputTokens (from CONTEXT_PREPARED) plus the paired secondary success row's outputTokens. Detection rule pinned by pipeClass + zero-inputTokens + non-zero actualInputTokens. Confirmed failure: under-counting by hundreds of millions of tokens over a 25-round projection when treated as the normal inputTokens bucket."
  1.0.0: "Initial version. Covers TokenBudgetSettings.calculateAvailableContext() formula, TruncateTop default, per-pipe context budget constants in autogenesis BedrockConfig.kt (workerBudgetSettings, generativeBudgetSettings, palmyraBudgetSettings, novaBudgetSettings, novaProBudgetSettings), per-agent context injection pattern via setPreInitFunction and ContextBank.emplaceWithMutex, and CFR decompilation recipe for reading TPipe primitives from the JAR."
trigger: When asked about TPipe context budgeting, when sizing a model swap against an existing context window, when investigating what gets truncated at a given budget, when reading or editing autogenesis BedrockConfig.kt budget settings, when implementing or repairing budget-aware pipe wiring, or when the operator says what happens at X context window or what fits in Y budget. ALSO load when reading or editing BedrockPipe.kt truncation settings, when adding a new Bedrock model, when debugging why a per-model maxTokens or truncation setting is not reaching the wire, or when investigating which API path (Invoke vs Converse) a model is using. ALSO load when investigating slow token-counting or choking behavior on multimodal inputs, when debugging BinaryContent / base64 payload size in cost projections, when countBinaryTokens or countTokens returns suspiciously fast or slow on image / document / audio inputs, when refining the binary-token counting contract on Pipe.kt, or when extending the test surface (CountBinaryTokensTest) for new BinaryContent subclasses.
---

# TPipe Context Budgeting & Truncation

The mechanics of how much context a pipe can hold, how the budget is computed, and what gets dropped first when the budget is exceeded. Companion to `tpipe-lorebook-system` (which covers the **what** — which lorebook entries get filled) and `tpipe-pipe-internals` (which covers the **when** — hook lifecycle). This skill covers the **how much** and **what drops first**.

The system spans **four files** in `server/build/server-runtime/server-linux-x64/lib/TPipe-1.0.0.jar`:

| File | Owns |
|------|------|
| `com/TTT/Pipe/TokenBudgetSettings.class` | Budget fields + `calculateAvailableContext()` math |
| `com/TTT/Context/ContextWindowSettings` enum | `TruncateTop` / `TruncateBottom` truncation method |
| `com/TTT/Pipe/TruncationSettings.class` | Tokenization knobs (subword counting, favor-whole-word, etc.) |
| `com/TTT/Pipe/MultiPageBudgetStrategy` enum | `DYNAMIC_SIZE_FILL` default vs static-size pages |

These classes live in the TPipe JAR, not the autogenesis source tree. The autogenesis source tree uses them via `setTokenBudget(TokenBudgetSettings(...))` and the `BedrockConfig.kt` budget-setting constants.

## The `calculateAvailableContext()` formula

From CFR-decompiled `TokenBudgetSettings.java`:

```java
public final int calculateAvailableContext() {
    Integer n = this.contextWindowSize;
    if (n == null) return 0;
    int totalWindow = n;
    Integer n2 = this.maxTokens;
    int available = totalWindow - (n2 != null ? n2 : 0);
    if (this.subtractReasoningFromInput) {
        Integer n3 = this.reasoningBudget;
        available -= n3 != null ? n3 : 0;
    }
    Integer n4 = this.userPromptSize;
    return RangesKt.coerceAtLeast((int)(available -= n4 != null ? n4 : 0), (int)0);
}
```

**The formula (read once):**

```
availableContext = contextWindowSize
                 - maxTokens                (output budget)
                 - userPromptSize           (max size of user prompt)
                 - reasoningBudget          (if subtractReasoningFromInput)
```

`coerceAtLeast(..., 0)` clamps negative to zero. **If any of those fields is null, the subtraction is skipped** — a null `maxTokens` means there is no output budget reserved. This is a footgun: a TokenBudgetSettings object constructed with only `contextWindowSize` set has `availableContext = contextWindowSize` (the full window is treated as input budget).

**Mental model:** the budget is the total context window minus what the model needs to *generate* (max_tokens) and what the user prompt itself consumes (userPromptSize). The remainder is what the framework can fill with system prompt + context injections + lorebook + contextElements.

## The autogenesis hardcoded budget settings

From `server/src/main/kotlin/globals/BedrockConfig.kt:478-506`:

| Constant | `maxTokens` | `contextWindowSize` | Used by |
|----------|------------:|-------------------:|---------|
| `workerBudgetSettings` | 8,000 | 32,000 | worker / branch pipes |
| `generativeBudgetSettings` | 12,000 | 230,000 | narrative + author pipes |
| `palmyraBudgetSettings` | 8,000 | 980,000 | palmyra fallback |
| `novaBudgetSettings` | 8,000 | 990,000 | nova 2 chat pipes |
| `novaProBudgetSettings` | 5,000 | 285,000 | nova Pro 300K limit with 15K slack |

**Two facts that catch a model-swap assessment off-guard:**

1. **The `contextWindowSize` is hardcoded per model.** When the model actually has a smaller window (e.g. Gemma 4 4B at 128K vs the hardcoded 230K), the budget settings will exceed the model's actual context window. The pipe will pack context up to `contextWindowSize - maxTokens` and then either fail or silently truncate. **The budget settings are NOT auto-derived from the model — they are a hardcoded knob the operator must update when the model changes.**

2. **The current `workerBudgetSettings` (32K) is already too small for the actual context being injected.** An `elderGodAgent.kt` preInitFunction injects 80K+ tokens of "previous turn" history into a worker pipe that has only `32,000 - 8,000 = 24,000` available. The truncation logic kicks in at 24K — old conversation history gets dropped at the start of every worker pipe call. This is pre-existing debt; not new.

## The truncation algorithm (TruncateTop)

From CFR-decompiled `ContextWindowSettings` enum:

```java
public enum ContextWindowSettings {
    TruncateTop,    // drops OLDEST context elements first
    TruncateBottom  // drops NEWEST context elements first
}
```

The autogenesis pipe budget defaults are configured without explicit `truncationMethod` (it inherits the default — `TruncateTop`). This means: **the oldest content is dropped first when the budget is exceeded.**

**Practical consequence for autogenesis:** `previous turn` history (which grows with each round) is the largest and oldest context element. As the game progresses, the oldest turns get truncated out of the budget. If the game history contains a critical fact that appears only in the oldest turn, that fact will eventually fall out of context. **The truncation is content-length-blind — it is age-only, not importance-only.**

**However**, lorebook entries are filled BEFORE regular contextElements via `selectAndFillLoreBookContext`. This means lorebook entries are shielded from `TruncateTop` because they go in first; the truncation budget for contextElements is `availableContext - system_prompt_size - lorebook_size`.

## The MultiPageBudgetStrategy

```java
public enum MultiPageBudgetStrategy {
    DYNAMIC_SIZE_FILL  // default — fill pages up to available budget
}
```

Autogenesis uses `DYNAMIC_SIZE_FILL` — pages are sized dynamically to fill the available budget. The lorebook system stores multiple pages per context key, and the budget allocator decides how to distribute tokens across pages. This is NOT a fixed-size model.

## What gets injected into context — the autogenesis pattern

Every autogenesis pipe has a `setPreInitFunction { ... }` that injects data via `ContextBank.emplaceWithMutex("key", ContextWindow().apply { contextElements.add(jsonString) })`. The keys, sizes, and patterns from a sample read:

| File | Injection key | ~size | Notes |
|------|---------------|------:|-------|
| `worldupdates.kt:73-95` | `previous turn`, `world info` | 30K → 80K+ | full previous turn JSON + map tile metadata |
| `validator.kt:412-475` | `player_data`, `world_context`, `local_adjacency`, `npc_data`, `other_players`, `user prompt` | 2K-30K each | per-NPC / per-player data dumps |
| `identifyPlayAgent.kt:222-225` | `actorStats` (lorebook entry) | ~3K | shielded via `addLoreBookEntry` |
| `validator.kt:444-465` | (further per-NPC + per-player entries) | 5K-15K each | full state dumps |

**Lorebook entries** (added via `addLoreBookEntry`) are stored on `ContextWindow.loreBookKeys: MutableMap<String, LoreBook>` and filled first by `selectAndFillLoreBookContext` (keyword match + weight sort + budget packing). **They are shielded from TruncateTop because they are filled before the regular contextElements truncation runs.**

**Context elements** (added via `contextElements.add(...)`) are subject to `truncateContextElements(maxTokens, ...)` which uses `TruncateTop` — drops the oldest entries first.

## The cost-per-context-window analysis pattern

When the operator asks "what fits in a 128K context" or "what gets truncated at X budget", the analysis chain is:

1. Read the actual pipe budget settings: `grep -nE "setTokenBudget\(BedrockConfig\." server/src/main/kotlin/agent/builders/ -r | sort -u`
2. Read the actual context injection sizes: read each `setPreInitFunction { ... }` body and `ContextBank.emplaceWithMutex` calls, estimate token counts from the JSON shape.
3. Read the actual context window model cap (NOT the hardcoded `contextWindowSize` — the model's actual window): `grep -nE "contextWindowSize\s*=" server/src/main/kotlin/globals/BedrockConfig.kt`
4. Compare (1) + (2) + (3) — if estimated injection > available budget, truncation kicks in.
5. Identify which elements get truncated: `TruncateTop` drops oldest contextElements first. Lorebook is shielded. System prompt is shielded (filled first in prompt assembly).
6. Identify the order: lorebook → system prompt → user prompt → context elements (newest first, oldest drops first).

## When to load this skill

- Operator asks "what fits in a 128K context window" or "what gets truncated at X budget"
- Operator asks "can we swap model X for model Y" — must update budget settings
- Implementing or repairing budget-aware pipe wiring
- Tuning token budgets for a specific pipe that is overflowing
- Reading or editing `autogenesis/server/src/main/kotlin/globals/BedrockConfig.kt` budget constants
- Investigating why a pipe's output is missing a context element (most likely: it was truncated)
- Auditing "is the lorebook shield actually working" — the answer is yes, but only for entries added via `addLoreBookEntry`, not for raw `contextElements` data

## CFR decompilation recipe (when source is not available)

The TPipe context primitives are NOT in the autogenesis source tree. They live in `server/build/server-runtime/server-linux-x64/lib/TPipe-1.0.0.jar`. To read them:

```bash
# 1. Extract the class
unzip -o -j TPipe-1.0.0.jar com/TTT/Pipe/TokenBudgetSettings.class com/TTT/Context/ContextWindow.class com/TTT/Context/ContextWindowSettings.class com/TTT/Context/ContextBank.class com/TTT/Context/MiniBank.class com/TTT/Context/LoreBook.class com/TTT/Enums/ContextWindowSettings.class com/TTT/Enums/MultiPageBudgetStrategy.class com/TTT/Pipe/TruncationSettings.class com/TTT/Pipe/MultiPageBudgetStrategy.class "com/TTT/Pipe/MultiPageBudgetStrategy\$Companion.class" -d /tmp/tpipe_extract/

# 2. Download CFR (Java decompiler)
curl -L https://www.benf.org/other/cfr/cfr-0.152.jar -o /tmp/cfr.jar

# 3. Decompile
java -jar /tmp/cfr.jar /tmp/tpipe_extract/TokenBudgetSettings.class --outputdir /tmp/decompiled
java -jar /tmp/cfr.jar /tmp/tpipe_extract/ContextWindow.class --outputdir /tmp/decompiled

# 4. CFR cannot load companion classes that are not in the classpath, so some
#    methods are commented out as "Unable to fully structure code". The
#    field declarations and method signatures are still readable.
```

CFR will not load companion classes by default. To get fuller decompilation:

```bash
java -jar /tmp/cfr.jar \
  /tmp/tpipe_extract/ContextWindow.class \
  --classpath /home/cage/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/1.9.24/4c8613592c2c25d63cd4e1558222b5f009b1bc80f/kotlin-stdlib-1.9.24.jar
```

The `calculateAvailableContext()` math is in the public API and is always fully decompiled.

## Pitfalls

### The GenericOpenAIPipe billing blind spot — endpoint returns `inputTokens: 0`, use TPipe's local estimate

For most providers (`bedrockPipe.BedrockMultimodalPipe`, OpenRouterPipe, etc.), the canonical billing truth on `API_CALL_SUCCESS` is the endpoint-reported `inputTokens` field. **GenericOpenAIPipe is an exception**: its primary success row emits `inputTokens: 0` because the upstream endpoint does not return an `input_tokens` usage block. The trace artifact then carries:

- Primary `API_CALL_SUCCESS` row: `inputTokens: 0`, `outputTokens: 0`, plus a `responseLength` (chars, not tokens).
- Secondary `API_CALL_SUCCESS` row on the same `pipeId`: `outputTokens: <actual>`, plus `totalInputTokens` and `totalOutputTokens` (recursive rollup of self + children).
- Separate `CONTEXT_PREPARED` event on the same `pipeId`: `actualInputTokens: <TPipe local count>`.

For GenericOpenAIPipe pipes, the canonical billing truth is **`actualInputTokens` from `CONTEXT_PREPARED`** for input, and **the secondary success row's `outputTokens`** for output. Detect it by checking: `pipeClass` contains `genericOpenAIPipe.GenericOpenAIPipe` AND `inputTokens == 0` on the primary success row AND `actualInputTokens > 0` on the matching CONTEXT_PREPARED event.

Confirmed failure (2026-07-31 autogenesis 25-round projection session): using `inputTokens` (zero) for GenericOpenAIPipe calls under-counted by hundreds of millions of tokens over 25 rounds. The 4-human per-turn total would have read as ~150K tokens when it was actually ~1M.

**The rule.** Before publishing any trace-derived cost artifact:

1. Bucket calls by `pipeClass` on `PIPE_START`.
2. For `genericOpenAIPipe.*` calls, swap to `actualInputTokens` (from `CONTEXT_PREPARED`) + the paired secondary success row's `outputTokens`.
3. Pin the bucket choice in the artifact's verification table — never mix.

**Cross-reference.** The full token-field taxonomy is in `software-development/tpipe-trace-parser`. This pitfall is the consumer-side exception to that taxonomy's "inputTokens is canonical" rule.

### The `contextWindowSize` field is NOT auto-derived from the model

The BudgetSettings object accepts a `contextWindowSize` integer — but it does NOT know the model's actual context window. The operator must set this when a model is swapped. Common swap-pitfall: replacing qwenCoder30B (262K window) with Gemma 4 4B (128K window) without updating the hardcoded `generativeBudgetSettings.contextWindowSize = 230000` to 128000 (or smaller). **The pipe will pack context up to 218K tokens and either fail or silently truncate the model's actual response.**

When you do a model-swap audit, the verification ritual is:
1. Read `BedrockConfig.kt` to find the current `contextWindowSize` for the relevant budget.
2. Compare against the new model's actual context window.
3. If they differ, update the hardcoded value.
4. Re-render the budget chart in the report.

### BedrockPipe has two nearly identical truncation `when` blocks — always edit both

`BedrockPipe.kt` has two copies of the per-model truncation configuration: `truncateModuleContext()` at line 1211 and `truncateModuleContextSuspend()` at line 1446. Both contain `when` blocks setting `contextWindowSize`, `multiplyWindowSizeBy`, `contextWindowTruncation`, and counting flags. **Adding a model to one without the other is the most common Bedrock model-add bug.** The suspend version additionally passes `tokenCountingBias` through to `combineAndTruncateAsStringWithSettingsSuspend()`. When adding a new model, search both blocks and edit them together.
4. Re-render the budget chart in the report.

### The `maxTokens` field determines output budget, not input budget

A common misread: `maxTokens = 12000` means "the model can output up to 12K tokens." It does NOT mean "the model has 12K input tokens." The `maxTokens` is the **output** budget; it is subtracted from `contextWindowSize` to determine the input budget. A `maxTokens` value of 12K with a 128K context means 116K of input budget. The model can OUTPUT up to 12K of those 116K.

### The default `truncationMethod` is `TruncateTop`, not `TruncateBottom`

The `setTokenBudget(...)` calls in autogenesis do not pass `truncationMethod` explicitly. The default inherits `ContextWindowSettings.TruncateTop`. **Oldest context is dropped first** — meaning conversation history (the oldest context element that grows with each round) is the first thing to fall out of the budget. If a critical fact appears only in the oldest turn, that fact will eventually disappear from the model's view.

When you do a truncation risk assessment: identify which context elements are oldest (typically `previous turn`), and which contain critical data. If a critical fact lives in the oldest turn, it WILL get truncated eventually. The fix is to push that fact into a lorebook entry (shielded) or extract it from history into a separate contextBank entry.

### `TruncateTop` is content-length-blind, not importance-blind

The truncation drops entries by index order, not by `weight` or `priority`. A high-value lorebook entry injected in the same call as a low-value context element will NOT be protected unless it is stored in `loreBookKeys` (not `contextElements`). If you need importance-based truncation, you need to (a) move the high-value data into lorebook, or (b) implement a custom `truncationMethod` that weights entries.

### The hardcoded budget values are a maintenance hazard

`workerBudgetSettings` and `generativeBudgetSettings` are typed as `val` constants at the top of `BedrockConfig.kt`. They are shared across all pipes that call `setTokenBudget(BedrockConfig.workerBudgetSettings)` etc. **A single edit to those constants affects every pipe that uses them.** When tuning, prefer per-pipe `TokenBudgetSettings(...)` literals with the specific values that pipe needs — not the shared constants. The shared constants are for "sensible default" behavior, not "tuned for this agent."

### The lorebook shield is entry-by-key, not value-by-value

A lorebook entry's `key` is matched against the scan text. The entry is only selected if the key (or an alias) appears. **Adding to the lorebook does not guarantee injection — the LLM's prose has to mention the key or alias.** If a critical game fact is stored as lorebook entry but the user prompt does not reference its key, the entry will not be selected and will not be shielded. The fix is to (a) pick keys that naturally appear in the LLM's prose, (b) use `aliasKeys` to broaden the match, or (c) add a `linkedKeys` chain that triggers a known-key.

### The model swap audit must check budget settings AND model window

A model swap audit is incomplete if it only checks pricing. The context window is the second axis: `qwenCoder30B @ 230K` is more permissive than `Gemma 4 4B @ 128K` even if Gemma is cheaper. The per-game cost math treats tokens as fungible, but they are not — context elements get truncated at the model window boundary, and the truncation is at the OLDEST content, not the most expensive. A swap that saves $0.11/M but loses 100K of context could lose more in agent quality than it gains in cost.

### Binary payloads (especially base64) must NEVER flow through the dictionary tokenizer

`Pipe.countBinaryTokens(content, truncationSettings)` at `src/main/kotlin/Pipe/Pipe.kt:5498` is the canonical site that costs every binary input to the model's token budget. The previous implementation routed every binary payload through `Dictionary.countTokens` after locally rebasing it into base64. **This is the wrong primitive.** Base64 alphabet is `A-Za-z0-9+/=` with no whitespace, so a 34 KB binary file → 45 KB base64 string becomes a single "word" inside the tokenizer's `text.split(" ")` pass, and `findAllMatches` walks the entire 45,136-char string with up to 50 inner probe iterations per position. The result is O(n × maxMatchLength) substring allocations per call — for the 34 KB case, roughly 90,000 string allocations plus ~2.25M `HashSet.contains` probes, choking the system for tens of milliseconds when the right answer is sub-millisecond integer math.

The cost compounds because `countBinaryTokens` is invoked from `calculateTokensSpent` on every pipe call and from `simulateTokenBudgetTruncation` on every budget preflight. A pipeline that touches 5 multimodal pipes per turn burns 50-500 ms on what should be 5 integer operations.

**The contract for `countBinaryTokens`** (verified 2026-08-08):

- `BinaryContent.Bytes` → token cost ≈ `(byteSize + 1) / 2`. No base64 conversion, no dictionary scan. Pure integer math on `data.size`.
- `BinaryContent.Base64String` → token cost ≈ `(base64Length + 3) / 4`. Same shape as the byte formula after dividing out the 4/3 base64 expansion. No `Dictionary.countTokens` call.
- `BinaryContent.CloudReference` → still routes through `Dictionary.countTokens` on the URI (URI is short, natural-language-shaped, the tokenizer is the right tool).
- `BinaryContent.TextDocument` → still routes through `Dictionary.countTokens` on `content`. This is the only binary-shaped payload that is genuinely text.

**Verification recipe** before shipping any change to this path:

```bash
# 1. The function must NEVER allocate a String from BinaryContent.Bytes data —
#    no base64 conversion should appear in the Bytes branch.
grep -nE 'Base64\.getEncoder|encodeToString|toBase64' src/main/kotlin/Pipe/Pipe.kt
# Expected: 0 matches inside countBinaryTokens.

# 2. The function must NEVER call Dictionary.countTokens on Bytes.data or
#    Base64String.data — only on CloudReference.uri and TextDocument.content.
grep -nE 'Dictionary\.countTokens' src/main/kotlin/Pipe/Pipe.kt
# Expected: 2 matches inside countBinaryTokens — on uri and on content.
```

**Performance gate**: a 34 KB binary must complete `countBinaryTokens` in **under 2 ms** end-to-end. The regression test `src/test/kotlin/CountBinaryTokensTest.kt` pins this contract with `measureNanoTime`; the threshold is the operator's stated ceiling, not a soft target.

**The deeper lesson — tokenizer primitive selection**. Dictionary-based tokenizers are designed for natural language where short prefixes exist in the wordlist, word boundaries appear as whitespace, and the match-fallthrough-to-`pos++` path is bounded by the density of real words. Binary payloads violate all three assumptions: no whitespace, no dictionary entries, dense random byte distribution. Whenever you encounter a `countTokens` call in TPipe and the input is structurally a base64 / hex / raw-bytes string, treat the call as a code-smell and look for a length-based approximation. `Dictionary.countTokens` is the right primitive for prose, lorebook values, serialized JSON context, and converse history text. It is the wrong primitive for binary content of any encoding.

**The accuracy envelope — within 5-10% of real BPE, on the high side**. The rule `ceil(byteSize / 4)` is a conservative high-side approximation. Real BPE on random base64 produces ~1 token per 4 base64 chars (the alphabet `A-Za-z0-9+/=` shares essentially no entries with the natural-language vocabulary, so the encoder falls back to byte-level merges). For raw bytes, real BPE is ~1 token per byte — which makes `ceil(byteSize / 4)` 4× over-conservative for raw bytes but only ~1.3× over-conservative for base64 (since 4 base64 chars encode 3 raw bytes). The accuracy gap is bounded and on the safe side for budgeting. If the operator wants tighter accuracy, the opt-in path (real BPE encoder via `TruncationSettings.binaryEncoder`) is in `references/binary-token-estimator-design.md`.

### A counting function that mutates its input is a separate bug — kill the side effect

The previous `countBinaryTokens` (also at `Pipe.kt:5498`) had a second defect independent of the dictionary-routing bug: it mutated `content.binaryContent[i]` in place. Specifically, the `BinaryContent.Bytes` branch called `binary.toBase64()` and reassigned the list slot to the converted `Base64String`:

```kotlin
is BinaryContent.Bytes ->
{
    val converted = binary.toBase64()
    content.binaryContent[i] = converted   // ← the side effect
    converted
}
```

A counting function that mutates its input is broken on two axes: idempotency (the second call returns different results than the first, because the second iteration sees `Base64String` instead of `Bytes`), and consumer trust (a caller that passes a `MultimodalContent` and later inspects its own `binaryContent` finds the type has silently changed). `countBinaryTokens` is called from `calculateTokensSpent` (line 5555) and `simulateTokenBudgetTruncation` (line 5651) — both are pure observation paths; neither is allowed to mutate the content object.

**The contract for `countBinaryTokens`**: pure function. Read `content.binaryContent` for its size and shape, return an `Int`. Do not assign to any list slot, do not call `toBase64()`, do not build derived payloads.

**Verification recipe**:

```bash
# 1. The function must not contain any write to a list slot.
grep -nE 'content\.binaryContent\[' src/main/kotlin/Pipe/Pipe.kt
# Expected: 0 matches inside countBinaryTokens. All access must be read-only iteration.

# 2. The regression test pins input-untouched by holding the original reference.
#    CountBinaryTokensTest > inputBinaryListIsNotMutated() asserts the original
#    BinaryContent.Bytes instance is still present at the same list index after
#    countBinaryTokens returns.
```

**Generalization**: any function named `count*` / `estimate*` / `simulate*` in TPipe must be idempotent and side-effect-free. These names signal "read-only observation" to callers. A side effect inside one is a silent contract violation — the caller cannot tell from the signature that the function rewrites the input. When refactoring, audit any `count*` function for writes to its arguments.

### Real BPE encoder is opt-in for binary — never the default path

The 1.2.0 contract (`Bytes → (byteSize+1)/2`, `Base64String → (base64Length+3)/4`) pins the integer-math default. It is tempting to "upgrade" this to a real BPE encoder (tiktoken / jtokkit / ktoken) for accuracy, but the default path MUST stay integer-math for three converging reasons:

1. **Memory cliff.** Real BPE encoders hold the entire payload in memory while encoding. tiktoken on GPT-4o hits ~80 MB peak memory for moderately large inputs (https://www.dsdev.in/counting-tokens-at-scale-using-tiktoken); a 5 MB image base64-encoded is ~6.7 MB plus tokenizer working memory, easily 100+ MB. TPipe's hot path calls `countBinaryTokens` 4× per request from `Pipe.kt:5555, 5651, 5834, 8070`. Four real-encoder passes per request is a guaranteed OOM on a typical 512 MB heap.

2. **Setup cost.** Real encoders must be constructed once and reused, which means `TruncationSettings.binaryEncoder` is a shared mutable reference — exactly the kind of state TPipe's pure-function patterns try to avoid. Loading the encoder eagerly on `TruncationSettings()` construction would burn the 80 MB on every pipe regardless of whether binary content was ever sent.

3. **The integer-math rule is already within 5-10% of real BPE for binary.** Random base64 alphabet (`A-Za-z0-9+/=`) shares essentially no entries with the natural-language BPE vocabulary, so real BPE on base64 produces ~1 token per 4 base64 chars — which is exactly the rule. The accuracy gap is bounded by the noise floor of base64 entropy.

**The rule.** Real BPE encoding for binary is opt-in only. Gate it behind `TruncationSettings.binaryEncoder != null` AND `byteCount >= settings.binaryEncoderThresholdBytes` (default 1 MB). Below the threshold, always use the integer-math rule. Above the threshold, encode in `binaryChunkSizeBytes` chunks (default 64 KB) to bound memory. On encoder failure (returns null/empty/throws), fall back to the rule with `binaryFudgeFactor`.

**Cross-reference.** Full design space — the 5 approaches (PER_ENCODER_RULE / PER_MIME_TYPE / EXTERNAL_ENCODER / HYBRID / chunked+cached), per-MIME token-cost formulas for OpenAI / Claude / Gemini, the `BpeEncoder` interface shape, and the `TruncationSettings` knob design — is in `references/binary-token-estimator-design.md`.

### `binaryMimeOverride` cannot hold the correct token count for Claude vision images

When wiring `TruncationSettings.binaryMimeOverride: Map<String, Int>` for `anthropic.claude-3-haiku-20240307-v1:0` or `anthropic.claude-3-sonnet-20240229-v1:0` (or any pre-Claude-4.7 model), do NOT populate it with a fixed integer for `image/jpeg`, `image/png`, `image/gif`, or `image/webp`. The current Anthropic Vision spec uses a patch-based formula that depends on the image's pixel dimensions: `tokens = min(⌈W/28⌉ × ⌈H/28⌉, 1568)` after scaling so the long edge is ≤1568 px (Standard tier; Claude 4.7+ uses High-resolution tier with a 2576-px long-edge cap and a 4784-token cap). A fixed entry like `{"image/jpeg": 1369}` would only be correct for one specific size (1024 × 1024); the same map would over-count a 200 × 200 PNG by **21×** (1369 vs the real 64) and under-count anything above 1568 px on the long edge (real: 1568, override: 1369).

This is why approach B (per-MIME override) is the wrong primary strategy for vision workloads — the formula depends on `(W, H)`, which is not recoverable from a constant map. For multimodal content, approach C (custom `BpeEncoder` plug-in) or approach D (`HYBRID` with a plug-in registered as `binaryEncoder`) is the correct integration. The plug-in decodes the image bytes via `javax.imageio.ImageIO` (Kotlin) or `PIL.Image.open(BytesIO(b))` (Python), rescales to ≤1568 px on the long edge, and returns `IntArray(min(((W+27)/28)*((H+27)/28), 1568))`.

For PDFs on the Bedrock Converse API, the situation is the opposite trap: a fixed `application/pdf` override is dangerous because the **mode** is selected at request time. Converse with citations enabled → full visual (~7000 tokens / 3 pages); Converse without citations → text-only (~1000 tokens / 3 pages); InvokeModel / Messages API → always full visual. The token cost of an `application/pdf` payload depends on a runtime flag, not a model formula. If the operator must use approach B for PDFs, populate with an **average** value (~2300 tokens/page assuming standard density, ~1.5 pages of image + ~1500 text/page) and document it as approximate. Better: register a plug-in that knows the Converse mode and returns the appropriate cost.

**The rule**: `binaryMimeOverride` is correct for MIME types whose token cost is **constant** (e.g., a small fixed-icon library or a known logo set). For vision images and documents, it is the wrong abstraction — use a model-aware `BpeEncoder` plug-in instead.

**Verification recipe** for any pre-existing `binaryMimeOverride` map:

```bash
# 1. Confirm no image/* entries are pinned to a constant integer.
#    (image/jpeg, image/png, image/gif, image/webp are the four supported
#    Claude vision MIME types.)
grep -nE '"image/(jpeg|png|gif|webp)"' src/main/kotlin/**/*.kt
# Expected: 0 matches inside TruncationSettings literals. If any matches
# exist, they should be in a commented-out test or marked deprecated.

# 2. Confirm any application/pdf entry is annotated as mode-dependent
#    (or replaced with a plug-in).
grep -nE '"application/pdf"' src/main/kotlin/**/*.kt
# Expected: either no entries, or entries with a comment naming the
# Converse mode they assume.

# 3. Confirm the BpeEncoder interface has at least one implementation
#    registered when the workload is multimodal.
grep -rnE 'BpeEncoder|class .*Encoder.*: .*BpeEncoder|setBinaryEncoder' src/main/kotlin
```

**Cross-reference.** The exact formula, the Kotlin pseudocode for the plug-in, the Converse-vs-Messages-API distinction, and worked examples for 1024×1024 JPEG and a 3-page PDF are in `references/anthropic-claude-vision-token-formula.md`.

### When the vendor's docs are silent on token math, the vendor's open-source tokenizer SDK is the authoritative source

When a multimodal model card or blog post gives no explicit token formula (e.g. "tokens per image depends on the image" with no formula), the **most authoritative source is the vendor's open-source tokenizer / preprocessing SDK**, not the model card, the marketing blog, or even the arXiv paper. The Mistral investigation (Thread 03, 2026-08-08) is the canonical example:

- The Pixtral 12B paper (https://arxiv.org/html/2410.07073v2) describes the encoder at the architecture level — "400M parameter ViT, RoPE-2D, variable image sizes, [IMAGE BREAK] tokens between rows, [IMAGE END] at the end, max 1024 px long edge" — but never gives the exact patch-count formula `(W-1) // 16 + 1` or the downscale-then-tile math.
- Mistral's Vision docs (https://docs.mistral.ai/studio-api/conversations/vision) name the recommended models but list no token-count formula and no maximum-image-size numeric.
- The model cards on HuggingFace (Magistral-Small-2509, Ministral-3-3B-Instruct-2512, etc.) confirm "vision encoder" but do not publish the algorithm.

The formula was only available in `mistral-common/src/mistral_common/tokens/tokenizers/image.py`:

```python
def _image_to_num_tokens(self, img):
    w, h = img.size
    ratio = max(h / 1024, w / 1024)
    if ratio > 1:
        w, h = round(w / ratio), round(h / ratio)
    width_tokens  = (w - 1) // (16 * 1) + 1   # ceil(w / 16)
    height_tokens = (h - 1) // (16 * 1) + 1   # ceil(h / 16)
    return width_tokens, height_tokens
```

The general pattern is now codified as a rule:

> **When the vendor's marketing layer is silent on multimodal token math, go to the vendor's open-source tokenizer SDK. The SDK is unambiguous where the docs are vague.**

This generalizes the existing `binaryMimeOverride cannot hold the correct count for Claude vision images` pitfall to the cross-vendor level. It applies to:

- **Mistral** → `mistral-common` (`image.py` for vision, `audio.py` for Voxtral).
- **Anthropic** → no open-source SDK for the vision encoder; formula is in Anthropic's Vision docs only.
- **Google (Gemma 3)** → `google/gemma_pytorch` or `transformers` (model code). The SigLIP vision encoder is in `transformers.models.siglip`.
- **OpenAI (GPT-4o)** → `tiktoken` doesn't cover images; formula is in OpenAI's Vision docs only.
- **Voxtral specifically** → the paper §2.1–2.2 + §5.2 ablation table is the authoritative source, since `audio.py` in `mistral-common` is a thin wrapper around the 12.5 Hz adapter output.

**Verification recipe** for any new multimodal model:

```bash
# 1. Check the vendor docs first for an explicit formula.
mmx search query --q "<vendor> <model> token count image formula"

# 2. If docs are silent, find the vendor's open-source tokenizer SDK.
#    Common patterns:
#    - HuggingFace `transformers.models.<arch>` (model code)
#    - Vendor's standalone SDK repo (e.g. mistral-common)
#    - The model's own GitHub repo (if open-weight)

# 3. Read the source. Look for functions named *_tokenize, _image_to_num_tokens,
#    preprocess_image, encode_image, encode_audio, etc. The function that
#    produces the token sequence is the source of truth.

# 4. Cross-check at least TWO of {vendor docs, tokenizer SDK, arXiv paper,
#    HF model card, community reverse-engineering} before publishing a formula.
```

**Cross-reference.** The Mistral findings (Pixtral-ViT formula + Voxtral 12.5 Hz formula), with worked examples and Kotlin pseudocode, are in `references/mistral-vision-audio-token-formula.md`. Same trap as the Claude pitfall above; same fix (custom `BpeEncoder` plug-in registered as `binaryEncoder`).

### The CFR decompilation produces "Unable to fully structure code" comments

CFR cannot load companion classes not in the classpath. The result is Java code with method bodies marked "Unable to fully structure code" or replaced with null returns. **The field declarations and method signatures are still readable, and the public API surface is fully decompiled.** Read the fields, the public method signatures, and the simple no-dependency methods (like `calculateAvailableContext`). Skip the methods that need companion classes unless you provide the full classpath.

## See Also

- **`tpipe-lorebook-system`** — sibling skill. Covers how lorebook entries are filled and shielded, but explicitly excludes `truncateContextElements` and `truncateConverseHistory`. This skill covers those.
- **`tpipe-pipe-internals`** — sibling skill. Covers Pipe lifecycle, DITL hook ordering, and the 8 hook entry points. This skill references the hooks (especially `preInitFunction` and `setPreInitFunction`) but does not cover the budget math.
- **`tpipe-context-pull-builder-repair`** — sibling skill. Covers dead pull builders. Complementary to the truncation math: a pull builder imports context; the budget settings determine how much of that import fits.
- **`product-claims-audit`** — relevant when doing a model-swap audit. The audit verifies product claims (cost, performance) against source code. The context budget audit is the source-code-ground-truth side of a model-swap verification.
- **`autogenesis-prompt-debugging`** — sibling skill. Covers the prompt layer (defaults files, agent builder code). The budget settings affect how much prompt survives truncation, but the prompt layer itself is separate.
- `references/tpipe-context-budget-fields.md` — full field-by-reference for TokenBudgetSettings, TruncationSettings, ContextWindowSettings, MultiPageBudgetStrategy. Captures defaults, valid ranges, and the inter-field relationships.
- `references/autogenesis-budget-pressure-trajectory.md` — empirical per-pipe measurements at R1T0/R2T0, the measured 30-40% per-round payload growth rate, the 1.05×/turn story-key growth rate, and the round-by-round truncation probability projection for a 25-round game. Use when the operator asks "when will this truncate" or "how big will this get over N rounds".
- `references/bedrock-model-request-builders.md` — per-model truncation configuration and request-building architecture in TPipe-Bedrock. Covers the Layer 1 `truncateModuleContext()`/`truncateModuleContextSuspend()` duplication hazard (two nearly identical `when` blocks at lines 1223 and 1460 of BedrockPipe.kt), the Layer 2 Invoke/Converse API routing `when` blocks, the `maxTokens` field-name mapping per model, the `QWEN_TUNED_TOKEN_COUNTING_BIAS` constant, and the `shouldSkipNovaMaxTokens()` suppression logic. Use when adding a new Bedrock model or debugging why a per-model setting is not reaching the wire.
- `references/binary-token-estimator-design.md` — the 5-approach design space (PER_ENCODER_RULE / PER_MIME_TYPE / EXTERNAL_ENCODER / HYBRID / chunked+cached), the recommended `TruncationSettings` knobs (`binaryTokenEstimation`, `binaryEncoder`, `binaryFudgeFactor`, `binaryChunkSizeBytes`, `binaryMimeOverride`), the `BpeEncoder` interface shape, the per-MIME token-cost formulas for OpenAI / Claude / Gemini, the chunked streaming pattern, and the backward-compat analysis against the 8 CountBinaryTokensTest cases. Use when extending `countBinaryTokens` beyond the integer-math fix, when the operator asks for "adjustable settings for binary", or when wiring a real BPE encoder (tiktoken / jtokkit / ktoken) into TPipe.
- `references/binary-token-estimator-empirical-library-baseline.md` — measured numbers from the 2026-08-08 Thread 02 research session: tiktoken o200k_base / GPT-2 fast / SentencePiece BPE+byte_fallback throughput (1-17 MB/s on 1-100 MB inputs), accuracy anchor (random base64 = 1.30 bytes/token across all byte-level BPE families; random raw bytes = 0.57-1.07), memory cliff (tiktoken 100 MB uniform A = 5.9 GB peak RSS, HF GPT-2 10 MB = 2.5 GB), and a tiered library shortlist (JTokkit / tiktoken-rs JNI / in-tree minbpe port / chars/4 heuristic / per-MIME carve-outs) with primary-source citations for each. Use when picking the real-BPE library for approach C in `binary-token-estimator-design.md`, when defending the "5 MB OOM at default heap" gate against the "just call tiktoken" argument, or when calibrating `binaryFudgeFactor` per MIME.
- `references/anthropic-claude-vision-token-formula.md` — Claude 3 Haiku / Claude 3 Sonnet binary token formulas on Bedrock: the patch-based image formula (⌈W/28⌉ × ⌈H/28⌉ capped at 1568 tokens for Standard tier), the two-mode Bedrock Converse API PDF cost (visual ~7000 tokens/3 pages with citations; text-only ~1000 tokens/3 pages without), Anthropic's count_tokens API on Bedrock, and worked Kotlin pseudocode for a custom `ClaudeVisionBpeEncoder` that decodes image bytes and returns the correct token count. Use when wiring a multimodal model-aware `BpeEncoder` for `claude-3-haiku-20240307-v1:0` or `claude-3-sonnet-20240229-v1:0`, when the operator asks "why can't I just set binaryMimeOverride={image/jpeg: N}", or when the operator is choosing between approach B (per-MIME) and approach C/D (custom encoder) for a Claude-heavy workload.
- `references/mistral-vision-audio-token-formula.md` — Mistral vision + Voxtral audio binary token formulas on Bedrock: the Pixtral-ViT formula `tokens = W_t × H_t + (H_t − 1)` (where `W_t = ⌈W'/16⌉`, `H_t = ⌈H'/16⌉`, after downscaling so `max(W, H) ≤ 1024`) shared by all 5 Mistral vision models (`magistral-small-2509`, `ministral-3-{3b,8b,14b}-instruct`, `mistral-large-3-675b-instruct`), and the Voxtral audio formula `tokens = ⌈audio_seconds × 12.5⌉` (1 token = 80 ms = 12.5 Hz effective frame rate after 4× adapter downsampling of a 50 Hz Whisper-large-v3 encoder) shared by `voxtral-mini-3b-2507` and `voxtral-small-24b-2507`. Both encoder source codes (`mistral-common/src/mistral_common/tokens/tokenizers/image.py` and `audio.py`) cited with file:line citations, plus worked examples (1024×1024 → 4159 tokens, 1920×1080 → 2339 tokens, 5 min audio → 3750 tokens), Kotlin pseudocode for `MistralPixtralVisionEncoder` and `VoxtralAudioEncoder` plug-ins, and the recommended `TruncationSettings` (`PER_ENCODER_RULE` + custom plug-in + `binaryFudgeFactor = 1.0` + `binaryEncoderThresholdBytes = 0`). Use when wiring a Mistral vision/audio model on Bedrock, when the operator asks "how many tokens for a Mistral image at resolution X", or when validating that `binaryMimeOverride` is the wrong abstraction for these models (cost is function-of-dimensions, not constant per MIME — same trap as the Claude pitfall above).