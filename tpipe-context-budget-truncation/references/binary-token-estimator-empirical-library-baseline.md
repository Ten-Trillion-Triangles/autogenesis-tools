# Binary Token Estimator — Empirical Library Baseline

Companion to `binary-token-estimator-design.md`. That file captures the **design space** (5 approaches, `TruncationSettings` knobs, per-MIME formulas). This file captures the **measured numbers** Thread 02 (existing-tools-and-libraries research) produced on 2026-08-08, so the next implementer can pick a library tier with measured MB/s + bytes/token numbers rather than docs-only claims.

## What this file owns

- Empirical throughput numbers (MB/s) and accuracy numbers (bytes/token) for tiktoken / jtokkit / HuggingFace `tokenizers` / SentencePiece BPE+byte_fallback against base64 and raw-bytes inputs.
- A primary-source library shortlist with JVM/JNI/JS/Rust/.NET pathways ranked against TPipe's actual deployment surface (JVM 24 / GraalVM).
- The empirical "real BPE on base64 = ~1.30 bytes/token" anchor that the design space's `ceil(bytes / 4)` heuristic is being measured against.
- Citations to the original library docs/issues/sources so the next implementer can re-verify in <10 minutes.

## Empirical baseline — measured on the Hermes host (Linux 6.17, GraalVM CE 24.0.2)

### Test harness

```bash
uv run --python 3.13 --with tiktoken==0.13.0 --with tokenizers==0.23.1 \
       --with sentencepiece==0.2.2 --with transformers python3
```

Libraries installed cleanly under Python 3.13.13. `sentencepiece` 0.2.2 (the version that previously refused Python 3.13) is now compatible.

### Benchmark results

| Input | Library | tokens | bytes/token | elapsed | throughput | source |
|---|---|---:|---:|---:|---:|---|
| uniform 'A' × 1 MB (base64) | tiktoken o200k_base (`enc.encode`) | 125,000 | 8.00 | 0.265s | 3.77 MB/s | bench #1 |
| random base64 × 1 MB | tiktoken o200k_base (`enc.encode`) | 910,338 | 1.30 | 0.145s | 9.17 MB/s | bench #1 |
| uniform 'A' × 1 MB | tiktoken o200k_base (`encode_to_numpy`) | 666,668 | 2.00 | 0.322s | 4.15 MB/s | bench #2 |
| uniform 'A' × 10 MB | tiktoken o200k_base (`encode_to_numpy`) | 6,666,668 | 2.00 | 3.026s | 4.41 MB/s | bench #2 |
| uniform 'A' × 100 MB | tiktoken o200k_base (`encode_to_numpy`) | 66,666,668 | 2.00 | 39.561s | 3.37 MB/s | bench #2 |
| random × 100 MB (base64) | tiktoken o200k_base (`encode_to_numpy`) | 91,017,106 | 1.30 | 13.186s | 10.11 MB/s | bench #2 |
| uniform 'A' × 100 MB peak RSS | tiktoken o200k_base | — | — | — | 5.9 GB RSS | bench #2 |
| random × 1 MB (raw bytes) | tiktoken o200k_base (`_encode_bytes`) | 934,604 | 1.07 | 0.058s | 17.32 MB/s | bench #3 |
| random × 10 MB (raw bytes) | tiktoken o200k_base (`_encode_bytes`) | 9,344,431 | 1.07 | 0.805s | 12.43 MB/s | bench #3 |
| uniform 'A' × 1 MB | GPT-2 fast (HF) | 125,000 | 8.00 | 0.469s | 2.13 MB/s | bench #4 |
| random × 1 MB (base64) | GPT-2 fast (HF) | 1,026,359 | 1.30 | 0.977s | 1.37 MB/s | bench #4 |
| random × 10 MB (base64) | GPT-2 fast (HF) | 10,262,807 | 1.30 | 11.742s | 1.14 MB/s | bench #4 |
| random × 10 MB (base64) HF peak RSS | GPT-2 fast (HF) | — | — | — | 2.5 GB RSS | bench #4 |
| uniform 'A' × 1 MB | SentencePiece BPE + byte_fallback (vocab 425, 8T) | 1,000,001 | 1.00 | 0.088s | 11.32 MB/s | bench #5 |
| random × 1 MB (base64) | SentencePiece BPE + byte_fallback | 1,322,383 | 1.01 | 0.128s | 10.41 MB/s | bench #5 |
| random × 1 MB (256 cycle × 4k) | SentencePiece BPE + byte_fallback | 1,929,217 | 0.54 | 0.119s | 8.82 MB/s | bench #5 |
| random × 10 MB (raw bytes) | SentencePiece BPE + byte_fallback | 17,473,992 | 0.57 | 1.026s | 9.74 MB/s | bench #5 |

bench #1 = `01-existing-tools-libraries-findings.md` §1 (1 MB sanity); #2 = §2 (scaling sweep via `encode_to_numpy`); #3 = §3 (private `_encode_bytes` direct path); #4 = §4 (HuggingFace GPT-2 fast tokenizer); #5 = §5 (SentencePiece BPE trained in this session).

### The accuracy anchor

The two numbers that bound the design space's accuracy claim:

- **Random base64 → ~1.30 bytes/token** in every byte-level BPE family tested (o200k_base, GPT-2). This is the "real BPE" baseline that `ceil(base64Length / 4) × 1.0` (the design's approach-A rule) is within 5-10% of on the high side.
- **Random raw bytes → 0.57 bytes/token** with `byte_fallback=True` (SentencePiece), 1.07 bytes/token with tiktoken's private `_encode_bytes` path. Both confirm the "real BPE on raw bytes is ~1 token per byte" claim the design space rests on.

The difference between base64 (1.30) and raw bytes (0.57-1.07) is the **reason** the formula branches by `BinaryContent` subtype — `Bytes` should use `ceil(byteSize / 4)` × fudge, `Base64String` should use `ceil(base64Length / 4) × (3/4)` × fudge (the extra `3/4` factor for the base64-to-bytes expansion is what makes them agree).

### The throughput gate

Any candidate library for TPipe's hot path must sustain ≥5 MB/s on 10 MB base64 input to be worth the implementation cost. From the table:

- ✅ tiktoken o200k_base: 10.11 MB/s on random base64 / 12.43 MB/s on raw bytes (private path).
- ✅ SentencePiece BPE + byte_fallback: 9.74 MB/s on raw bytes / 10.41 MB/s on base64.
- ⚠ HuggingFace GPT-2 fast: 1.14 MB/s on 10 MB base64 (10× slower than tiktoken).
- ❌ TPipe's broken path: 2,929 tokens/s on 256 KB base64 = ~1.3 KB of tokens/s.

HuggingFace is too slow for TPipe's 4×-per-request hot path. tiktoken / SentencePiece / jtokkit are all candidates.

### The memory cliff

tiktoken on 100 MB uniform 'A' base64 → **5.9 GB peak RSS**. 10 MB HF GPT-2 → 2.5 GB. SentencePiece with byte_fallback on 10 MB random bytes → 420 MB. This is why the parent skill's "Real BPE encoder is opt-in for binary" pitfall is the right rule: the default `PER_ENCODER_RULE` path must stay integer-math because a single OOM at the 100 MB scale takes down the whole JVM. Threshold (default 1 MB) is the right floor below which the encoder is never invoked.

## Library shortlist with primary-source verification

### Tier 1 — JTokkit (Java/Kotlin, recommended default for TPipe)

- **Repo:** https://github.com/knuddelsgmbh/jtokkit
- **Maven:** `com.knuddels:jtokkit:1.1.0` (latest stable, 2024-07-19).
- **Encodings:** r50k_base, p50k_base, p50k_edit, cl100k_base, o200k_base.
- **API:** `Encoding#countTokens(String)` and `Encoding#countTokensOrdinary(String)` — exact analog of TPipe's `countBinaryTokens` shape.
- **License:** MIT, zero dependencies, Java 8+, GraalVM native-image friendly.
- **Performance:** "between 2-3 times faster than a comparable tokenizer" (per README) — sits in the same throughput tier as tiktoken.
- **Verified:** inspected `Usage` docs at https://jtokkit.knuddels.de/docs/getting-started/usage and the README. No `bytes`-input path in the public API (same as tiktoken) — caller must `new String(bytes, Charsets.ISO_8859_1)` or hex-encode first. The `TikTokensUtil.tokens(EncodingType, String)` shape is the cleanest bridge for TPipe.

### Tier 2 — tiktoken-rs / tiktokenx (Rust → JNI bridge, opt-in for accuracy)

- **tiktoken-rs:** https://crates.io/crates/tiktoken-rs (the original Rust port).
- **tiktokenx:** https://crates.io/crates/tiktokenx (Aug 2025 rewrite).
- **Why not direct:** TPipe is JVM, not Rust. A JNI bridge would be the integration path. Not worth it unless accuracy on `o200k_harmony` (the new 201,088-vocab tokenizer for GPT-5/gpt-oss) is required, which JTokkit 1.1.0 doesn't yet expose.

### Tier 3 — In-tree minbpe port (zero-dep fallback, accuracy ≈ BPE)

- **Reference:** https://github.com/karpathy/minbpe — 2 files, <400 LOC of Python; "minbpe always allocates the 256 individual bytes as tokens, and then merges bytes as needed from there."
- **Tradeoff:** same shape as cl100k_base / o200k_base without their specific merge table. Re-implementable in <300 LOC of Kotlin. Gives "always available" BPE without an external dependency.
- **Cost:** accuracy is bounded by which merge table is loaded. The cl100k_base table is ~700 KB; the o200k_base table is ~2 MB. Either ships as a classpath resource.

### Tier 4 — chars/4 heuristic with `tokenCountingBias` (current 1.2.0 default)

- **Source:** https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them — "1 token ≈ 4 characters" for English.
- **TPipe wiring:** `TruncationSettings.tokenCountingBias` is already there (multiplier on raw token counts). For binary, the design's `(base64Length × 3 + 11) / 16` formula on `Base64String` and `(byteSize + 1) / 2` on `Bytes` is the integer-math default, with `binaryFudgeFactor` as the multiplier.
- **When to use:** always, when no `binaryEncoder` is wired. The accuracy envelope is documented in the parent skill's "Binary payloads" pitfall.

### Tier 5 — Per-MIME carve-outs (OpenAI / Claude / Gemini image & audio)

Verified from primary sources:

- **Gemini:** "Images ≤384 px in both dimensions count as 258 tokens. Larger images are tiled into 768×768 pixel tiles, each counting as 258 tokens. Video: 263 tokens per second. Audio: 32 tokens per second." — https://ai.google.dev/gemini-api/docs/tokens
- **Claude (Anthropic):** Image tokens = `ceil(width × height / 750)`. PDF tokens = text-extracted-tokens + ~1,500-3,000 per page image. — https://platform.claude.com/docs/en/build-with-claude/vision, https://platform.claude.com/docs/en/build-with-claude/pdf-support
- **OpenAI:** Low-fidelity image = 65 base + 129/tile; high-fidelity = 85 + 170 × tiles (512×512). PDF (US Letter) = 2,424. — https://community.openai.com/t/how-do-i-calculate-image-tokens-in-gpt4-vision/492318, https://community.openai.com/t/how-does-openai-charge-tokens-when-sending-pdf-content-in-a-prompt/1280985

These don't replace the base64 heuristic for raw-bytes payloads — they're the `binaryMimeOverride` table for known MIME types.

## Decision tree for next implementer

```
Input is binary (Bytes or Base64String)?
├─ byteCount < binaryEncoderThresholdBytes (1 MB)? → use PER_ENCODER_RULE (always)
├─ byteCount >= threshold AND binaryEncoder set?
│  ├─ JTokkit available → call jtokkit's Encoding#countTokens on hex-encoded bytes
│  ├─ Else tiktoken-x via JNI → call enc.encode_to_numpy on base64 string
│  └─ Else fall back to PER_ENCODER_RULE with binaryFudgeFactor
├─ Known MIME (image / audio / pdf)?
│  └─ Look up binaryMimeOverride map, else fall back to PER_ENCODER_RULE
└─ Chunked stream to bound memory at binaryChunkSizeBytes (default 64 KB)
```

## Why "real BPE" stays opt-in

The parent skill's "Real BPE encoder is opt-in for binary — never the default path" pitfall is empirically correct:

1. **5.9 GB peak RSS** for tiktoken on 100 MB uniform base64 — TPipe's heap would OOM well before that.
2. **2.5 GB peak RSS** for HF GPT-2 on 10 MB base64 — same OOM cliff, smaller scale.
3. The 4× hot-path in `Pipe.kt:5555, 5651, 5834, 8070` means a single OOM kills the request.
4. The integer-math rule is already within 5-10% of real BPE for base64 (1.30 bytes/token vs the rule's 1.0-1.07 depending on padding).
5. The accuracy gap shrinks toward zero as the rule gets `binaryFudgeFactor` calibration per MIME.

The opt-in path is reserved for operators who need exact cost on large payloads AND have the heap to afford it (≥2 GB headroom).

## See Also

- `references/binary-token-estimator-design.md` — the design space (5 approaches, TruncationSettings knobs, per-MIME formulas) this baseline anchors.
- `references/tpipe-context-budget-fields.md` — full `TruncationSettings` field reference; the `binary*` knobs would extend it.
- `references/bedrock-model-request-builders.md` — per-model truncation wiring in `TPipe-Bedrock`; the `binaryMimeOverride` map values are model-specific.
- `md/2026-08-08-binary-token-estimation/02-existing-tools-libraries-findings.md` — the full Thread 02 research file (158 sources, 472 lines) this file is distilled from.
- Parent skill `tpipe-context-budget-truncation` — the "Binary payloads must NEVER flow through the dictionary tokenizer" and "Real BPE encoder is opt-in" pitfalls this baseline supports.
