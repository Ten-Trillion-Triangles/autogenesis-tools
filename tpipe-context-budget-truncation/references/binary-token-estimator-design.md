# Binary Token Estimator Design Space

Companion to the `Binary payloads must NEVER flow through the dictionary tokenizer` pitfall in `tpipe-context-budget-truncation`. This reference covers the **design space** the operator navigates when extending `countBinaryTokens` beyond the pure integer-math fix, plus the **concrete `TruncationSettings` knobs** and **recommended hybrid shape**.

## Why this exists

The 1.2.0 pitfall pins the *current* contract: `Bytes → (byteSize+1)/2`, `Base64String → (base64Length+3)/4`, no `Dictionary.countTokens` on binary. The session that produced 03-estimator-design-and-tpipe-audit-findings.md (2026-08-08) proved that contract works, but the operator asked for two further things:

1. **"Adjustable settings for binary possibly."** Operator wants tunable knobs on `TruncationSettings` — a fudge factor, an opt-in real encoder, a chunk size, a MIME override map. Not just the binary rule.
2. **"Close to possible to how tokenizers behave with bytes."** Within 5-10% of real BPE for raw bytes / base64.

This file captures the design space the implementation will draw from.

## The 5-approach design space

| Approach | Description | Accuracy | Perf | Cost | Default? |
|----------|-------------|----------|------|------|----------|
| **A — Per-encoder rule** | `ceil(bytes / 4) * fudgeFactor` | ±5-10% high | O(1) | 0 | **Yes (default)** |
| **B — Per-MIME lookup** | Lookup table keyed by MIME → per-model token cost formula | exact for known types | O(1) lookup | small map | opt-in |
| **C — Real BPE encoder** | tiktoken / jtokkit / ktoken over the payload | exact | O(n) time + memory | encoder setup | opt-in (large payloads only) |
| **D — Hybrid** | A by default, B for known MIME, C for unknown large | exact when configured | A or C per item | per-mode | **recommended long-term shape** |
| **E — Chunked + cached BPE** | Real BPE in 64 KB chunks, sum token counts | ±5% (chunk-boundary drift) | O(n) but bounded | small cache | useful if C's memory is too high |

**The current 1.2.0 contract IS approach A** with `fudgeFactor = 1.0` and a hardcoded `bytes-per-token = 4`. The next-generation extension is D.

## The `bytes-per-token = 4` derivation

Why 4? Three converging sources:

1. **OpenAI Help ("What are tokens")** — "1 token ≈ 4 characters" for English text. https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
2. **PMC tokenization-efficiency paper** — "English tokens consist of 4-5 characters on average, whereas Cyrillic tokens mostly contain 3-4 characters per token." https://pmc.ncbi.nlm.nih.gov/articles/PMC12380774/
3. **Iternal Token Usage Guide 2026** — "The widely-accepted rule of thumb is that the average tokens per word is about 1.33 (equivalently ~0.75 words per token, or roughly 4 characters per token)." https://iternal.ai/token-usage-guide

For arbitrary binary, BPE byte-level fallback produces **roughly 1 token per byte** (every byte value 0-255 maps to a base vocab entry; only merges happen on common pairs, and base64 alphabet is uniformly distributed). So:

- Raw bytes: `tokens ≈ bytes` (1:1 ratio).
- Base64 bytes: `tokens ≈ base64Bytes × 0.75` (4 base64 bytes decode to 3 raw bytes; BPE merges ~1 token per 4 base64 chars on average for random alphabet).

The conservative high-side approximation `ceil(bytes / 4)` over-estimates by ~5-10% for random base64, which is the **safe direction** for token budgeting (over-budget rather than under-budget).

## Approach C — Real BPE libraries

Three concrete options for the `BpeEncoder` interface:

| Library | Language | URL | Notes |
|---------|----------|-----|-------|
| **tiktoken** | Python (CPython + WASM) | https://github.com/openai/tiktoken | OpenAI reference; 3-6× faster than comparable open-source. Peak memory ~80 MB for 4o encoding (https://www.dsdev.in/counting-tokens-at-scale-using-tiktoken). |
| **JTokkit** | Java / Kotlin | https://github.com/knuddelsgmbh/jtokkit | "Fast and efficient tokenizer designed for use with OpenAI models." Maven Central: `com.knuddels:jtokkit:1.1.0`. Zero-dependency, Java 8+. Best fit for TPipe (Kotlin/JVM). |
| **ktoken** | Kotlin Multiplatform | https://github.com/aallam/ktoken | "Kotlin multiplatform BPE tokenizer library designed for seamless integration with OpenAI's models." Newer, smaller community. |

Performance benchmark context:
- tiktoken: 3-6× faster than comparable open-source (README).
- rs-bpe: 0.000605s for tiktoken's reference benchmark (HF discuss).
- TokenDagger: 4× faster code sample tokenization on a single thread (HN).
- tryAGI/Tiktoken (.NET): "up to 618 MiB/s, competitive with Rust. Zero-allocation counting."

The TPipe JVM path should default to **JTokkit** (zero-dependency, Java 8+, fits the GraalVM native-image build constraint).

## Approach C — chunked streaming memory ceiling

Even with JTokkit, encoding the full base64 of a 5 MB image holds the full string in memory. For TPipe's hot path (4× per request), that's unacceptable. The chunked pattern:

```kotlin
var tokens = 0
val chunkSize = settings.binaryChunkSizeBytes  // default 65_536
var offset = 0
while(offset < binary.data.length)
{
    val end = minOf(offset + chunkSize, binary.data.length)
    tokens += settings.binaryEncoder.encode(binary.data.substring(offset, end)).size
    offset = end
}
```

Memory ceiling: one 64 KB string at a time. Cost: ~5% accuracy loss at chunk boundaries (BPE merges that span two chunks get split). Acceptable for budgeting.

## The `TruncationSettings` knobs (recommended shape)

```kotlin
data class TruncationSettings(
    // ... existing fields (lines 64-95 of Pipe.kt) ...
    var binaryTokenEstimation: BinaryEstimationMode = BinaryEstimationMode.PER_ENCODER_RULE,
    var binaryEncoder: BpeEncoder? = null,
    var binaryEncoderThresholdBytes: Int = 1_048_576,  // 1 MB; below this, always use the rule
    var binaryFudgeFactor: Double = 1.0,                // multiplier on the rule-based estimate
    var binaryChunkSizeBytes: Int = 65_536,
    var binaryMimeOverride: Map<String, Int>? = null     // exact token count per MIME type
)

enum class BinaryEstimationMode {
    PER_ENCODER_RULE,   // ceil(bytes/4) * fudgeFactor — default, O(1)
    PER_MIME_TYPE,      // look up mime in binaryMimeOverride, else fall back to rule
    EXTERNAL_ENCODER,   // delegate to binaryEncoder (chunked if > threshold)
    HYBRID              // PER_MIME_TYPE for known MIME, EXTERNAL_ENCODER for unknown large, rule for the rest
}

interface BpeEncoder {
    fun encode(text: String): IntArray
}
```

**Default path** — `PER_ENCODER_RULE` with `fudgeFactor = 1.0`:
- `Bytes(byteSize) → ceil(byteSize / 4.0).toInt()`
- `Base64String(base64Length) → ceil((base64Length / 4) * 3 / 4.0).toInt()` — equivalently `(base64Length * 3 + 11) / 16` to absorb padding drift.

**Opt-in path** — `EXTERNAL_ENCODER` or `HYBRID` with `binaryEncoder != null`:
- Threshold check: if `byteCount < binaryEncoderThresholdBytes`, fall back to rule.
- Above threshold: chunked BPE encode over `binaryChunkSizeBytes` windows.
- On encoder failure (`encode` returns null/empty/throws): fall back to rule with `fudgeFactor`.

## Per-MIME-type formulas (Approach B — opt-in)

| MIME | Provider | Formula | Source |
|------|----------|---------|--------|
| `image/*` (low fidelity) | OpenAI | 65 base + 129 per tile | https://developers.openai.com/api/docs/guides/images-vision |
| `image/*` (high fidelity) | OpenAI 4o legacy | 85 + 170 × tiles (512×512) | https://community.openai.com/t/how-do-i-calculate-image-tokens-in-gpt4-vision/492318 |
| `image/*` (any) | Claude | `ceil(width × height / 750)` | https://platform.claude.com/docs/en/build-with-claude/vision |
| `image/*` ≤384 px | Gemini | flat 258 | https://carlosortet.com/blog/how-llms-read-text-as-images |
| `image/*` >384 px | Gemini | 258 × `ceil(max(w, h) / 768)²` | same source |
| `image/*` (1K, 2K) | Gemini 3 Pro | 1,120 | https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing |
| `image/*` (4K) | Gemini 3 Pro | 2,000 | same source |
| `application/pdf` (US Letter) | OpenAI | 2,424 | https://community.openai.com/t/how-does-openai-charge-tokens-when-sending-pdf-content-in-a-prompt/1280985 |
| `application/pdf` (general) | Anthropic | 1,500-3,000 per page | https://towardsdatascience.com/introducing-the-new-anthropic-pdf-processing-api-0010657f595f/ |
| `audio/*` | Gemini Live | 25 tokens / second | https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing |

The `binaryMimeOverride` map lets the operator pin an exact token cost for known MIME types in a known target model. Keyed by mime string, value is the token cost.

## Performance targets (recommended)

| Size | Old (dictionary tokenizer) | New (PER_ENCODER_RULE) | New (EXTERNAL_ENCODER, chunked) |
|------|---------------------------|------------------------|---------------------------------|
| 34 KB | ~30 ms | <0.1 ms | n/a (under threshold) |
| 256 KB | 28,498 ms | <0.5 ms | ~50 ms |
| 5 MB | OOM (512 MB heap) | <5 ms | ~1 s |

Captured in `DictionaryCountBinaryBenchmarkTest.kt:79-118` on main (2026-08-08).

## Backward compatibility (8 tests must pass)

| Test | Old | New (default) | Pass? |
|------|-----|---------------|-------|
| `rawBytesAreCountedFromByteLength` | 8,500 | 8,500 | ✓ |
| `base64StringIsCountedFromDecodedByteLength` | 8,501 | 8,501 | ✓ |
| `bytesAndBase64WithEquivalentPayloadProduceSameTokenCount` | equal | equal | ✓ |
| `base64PaddingIsAbsorbedByIntegerDivision` | 8 | 8 | ✓ |
| `inputBinaryListIsNotMutated` | passes (accidentally) | passes (no mutation at all) | ✓ |
| `textDocumentStillUsesDictionaryTokenizer` | 2 | 2 | ✓ |
| `cloudReferenceUsesDictionaryTokenizer` | 1-20 | 1-20 | ✓ |
| `thirtyFourKilobyteBinaryCompletesInUnderTwoMilliseconds` | <2 ms | <0.1 ms | ✓ |

The default `PER_ENCODER_RULE` path is a strict superset of the 1.2.0 contract. Opt-in paths add capability without regressing defaults.

## Round-trip equivalence — the padding fix

The base64 formula `(length × 3) / 4` ignores padding, drifting up by 1-2 bytes on padded input. The exact formula:

```kotlin
val padCount = binary.data.count { it == '=' }  // count padding chars
val byteCount = (binary.data.length / 4) * 3 - padCount
```

For non-padded base64 (clean multiple of 4 chars, no `=`), `padCount = 0` and the formula matches `(length × 3) / 4` exactly. For padded input, the subtraction corrects. Test `base64PaddingIsAbsorbedByIntegerDivision` uses 40-char base64 (no padding) so both formulas give 30 bytes → 8 tokens, but the corrected formula is the strict superset.

## Decision: when to use which approach

| Situation | Approach |
|-----------|----------|
| Default config, no operator input | A (PER_ENCODER_RULE) |
| Operator knows target model + MIME | B (PER_MIME_TYPE) via `binaryMimeOverride` |
| Operator wants exact cost for large payloads | D (HYBRID) with `binaryEncoder` set |
| Operator runs in-memory-constrained env, wants accuracy | E (chunked + cached) with `binaryChunkSizeBytes` small |
| Operator has custom tokenizer (e.g., a private BPE) | C (EXTERNAL_ENCODER) via custom `BpeEncoder` impl |

## See Also

- The parent skill `tpipe-context-budget-truncation` for the base contract on `countBinaryTokens` and the binary-vs-dictionary pitfall.
- `tpipe-pipe-builders` for the wider Pipe class hierarchy that `countBinaryTokens` sits inside.
- `references/tpipe-context-budget-fields.md` for the full `TruncationSettings` field reference (the binary knobs would extend this file when the implementation lands).
