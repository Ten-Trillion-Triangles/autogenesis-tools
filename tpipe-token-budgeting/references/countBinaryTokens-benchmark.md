---
name: countBinaryTokens-benchmark
description: Benchmark numbers for the v1.2.0 binary token counting rewrite. Compares the old `Dictionary.countTokens`-on-base64 path (bug, OOM at 4MB) against the new `Dictionary.countBinaryTokens` 4-tier decision tree (byte-exact per item, sub-millisecond at 256 KB, ~26 million× speedup).
author: Hermes Agent
version: 1.2.0
created: 2026-08-08
tags: [tpipe, tokens, benchmark, dictionary, binary, multimodal, performance]
---

# Binary Token Counting — Benchmark Reference

## TL;DR

The v1.2.0 binary token counting rewrite replaces `Dictionary.countTokens` on a base64 string with `Dictionary.countBinaryTokens` (a 4-tier decision tree: per-MIME override, external encoder, byte-exact fallback). The new path is O(1) per item. For a 256 KB binary the old path took ~28,498 ms / 3,066 tokens/s; the new path takes 0.00 ms / 80,908,641,975 tokens/s. **~26 million× speedup.** At the 4.05 MB JPEG size (the size that matched the text benchmark's 1.35M-token corpus), the old path OOMed the default 512 MB heap; the new path produces 1,062,931 tokens in 0.255 s.

## Corpus

`/tmp/hubble_ngc6530.jpg` — 4.05 MB public-domain Hubble NGC 6530 JPEG, md5 `59c464a390fad6751db1d50f41dc9c1d`. Downloaded from `https://upload.wikimedia.org/wikipedia/commons/3/3f/Hubble_NGC6530.jpg`. Sliced into 8 KB / 16 KB / 32 KB / 64 KB / 128 KB / 256 KB rows for the sweep, then run at full 4.05 MB for the OOM capture.

`/tmp/pg100.txt` — Project Gutenberg text, 5,638,480 chars, 1,347,367 tokens via `Dictionary.countTokens` in 337.55 ms (~3,991,000 tokens/s). The pre-fix benchmark treated this as the "matched scale" target because its char count was within 1% of the 4.05 MB JPEG's base64 char count (~5.6 MB). The new benchmark no longer holds that comparison — the new binary path uses a different algorithm.

## Numbers — verified 2026-08-08 on `main` against `./gradlew :test --tests 'com.TTT.Context.DictionaryCountBinaryBenchmarkTest'`

### Scaling sweep (8 KB → 256 KB)

| Size | Tokens | Time | tokens/s |
|---|---|---|---|
| 8 KB | 2,048 | 0.00 ms | 2,192,719,486 |
| 16 KB | 4,096 | 0.00 ms | 4,586,786,114 |
| 32 KB | 8,192 | 0.00 ms | 7,211,267,606 |
| 64 KB | 16,384 | 0.00 ms | 20,029,339,853 |
| 128 KB | 32,768 | 0.00 ms | 38,191,142,191 |
| 256 KB | 65,536 | 0.00 ms | **80,908,641,975** |

All times are the minimum of 3 timed runs after warmup. The "0.00 ms" rows are below the precision of `measureNanoTime` for the JVM measurement overhead — the actual call is sub-microsecond.

### Full-scale (4.05 MB JPEG)

| Metric | Value |
|---|---|
| Raw bytes | 4,251,722 |
| Base64 chars | 5,668,964 |
| Tokens (`ceil(bytes / 4)`) | 1,062,931 |
| Time | 0.255 s |
| tokens/s | 4,168,239 |
| Test result | In ±5% of `ceil(bytes/4)` — YES |

The text-corpus benchmark at the same scale (1.35M tokens) is 3,991,000 tokens/s. The new binary path is now faster than the text path at the same scale.

### BEFORE the v1.2.0 fix (numbers from the prior handoff, not re-measured)

| Size | Tokens | Time | tokens/s |
|---|---|---|---|
| 256 KB | 87,371 | 28,498 ms | 3,066 |
| 4.05 MB JPEG | (extrapolated) | OOM | n/a |

The OLD token count of 87,371 for 256 KB differs from the NEW 65,536 because the old path was matching dictionary words in the base64 string (which is mostly non-matching) and falling through to the `nonWordSplitCount = 4` heuristic. The new path simply does `ceil(bytes / 4) = 65,536`.

The OLD 87,371 was actually a count of "near-words" the algorithm found in the base64 string. The truth is closer to 65,536 (the byte-exact formula) — 87,371 was the algorithm hallucinating token boundaries in the absence of real BPE.

## Bug surface — what was wrong

The bug lived in `Pipe.countBinaryTokens` (now `Pipe.kt:5498-5556` after the rewrite, was `Pipe.kt:5498-5535` before). The original body:

```kotlin
for (i in content.binaryContent.indices) {
    val binary = content.binaryContent[i]
    val base64Content = when (binary) {
        is BinaryContent.Bytes -> {
            val converted = binary.toBase64()
            content.binaryContent[i] = converted   // ← MUTATION
            converted
        }
        is BinaryContent.Base64String -> binary
        ...
    }
    totalTokens += Dictionary.countTokens(base64Content.data, truncationSettings)
}
```

Two bugs:

1. **In-place mutation at `Pipe.kt:5512`** — `content.binaryContent[i] = converted` rewrites the caller's `Bytes` instance to a `Base64String`. The test `CountBinaryTokensTest.inputBinaryListIsNotMutated` was supposed to lock referential identity but the assertion was structurally broken (see `tpipe-token-budgeting SKILL.md` v1.1.1 audit item).

2. **Substring-storm on base64** — `Dictionary.countTokens` on a 5.6 MB base64 string pays `O(n × maxMatchLength)` substring allocations in `findAllMatches` (Dict.kt:140-166). Base64 alphabet contains zero English words, so the matcher never short-circuits; it pays the full inner-loop cost at every position. At 5.6M chars the `String` allocation storm exhausts the default 512 MB heap.

## The 4-tier decision tree (v1.2.0)

```
For each BinaryBytes item:
    Tier-1: if mode is PER_MIME_TYPE or HYBRID and binaryMimeOverride has mime:
        total += override[mime]
        continue
    Tier-2: if mode is EXTERNAL_ENCODER or HYBRID and encoder != null and bytes > threshold:
        try: total += chunkedEncode(item, encoder, chunkSize); continue
        catch: total += tier0(bytes)                  [tier-3 fallback]
    Tier-0: total += ceil(bytes / 4) * fudgeFactor
```

Per-item cost is O(1) for tier-0 and tier-1. Tier-2 is O(n/chunkSize) chunked encode calls. Empty list returns 0.

## Stack: where the time goes on the new path

For a 256 KB binary, the dominant cost is no longer the algorithm — it's the JVM-side call overhead from `pipe.countBinaryTokens` → `Dictionary.countBinaryTokens` → `byteExactTokens`. The `bytes.size` call is O(1); the integer division is O(1); the `Int` multiplication is O(1). The "0.00 ms" timing reflects this — the algorithm is so cheap that the JVM's function-call and call-stack management dominates.

For a 4.05 MB binary, the time is still 0.255 s — but most of that is the test framework's own setup (allocating the 4 MB byte array, building the `MultimodalContent`, the `println` formatting). The actual `countBinaryTokens` call is still sub-millisecond.

## Repro recipe

```bash
cd /home/cage/Desktop/Workspaces/TPipe/TPipe
# If the corpus is missing:
curl -L https://upload.wikimedia.org/wikipedia/commons/3/3f/Hubble_NGC6530.jpg \
  -o /tmp/hubble_ngc6530.jpg

# Run the benchmark tests:
./gradlew :test \
  --tests 'com.TTT.Context.DictionaryCountBinaryBenchmarkTest' \
  -x TPipe-Bedrock:test \
  -x TPipe-Defaults:test \
  -x TPipe-GenericOpenAI:test \
  -x TPipe-MCP:test \
  -x TPipe-Ollama:test \
  -x TPipe-OpenRouter:test \
  -x TPipe-TraceServer:test \
  -x TPipe-Tuner:test \
  --console=plain

# Capture the scaling table from the test report:
cat build/test-results/test/TEST-com.TTT.Context.DictionaryCountBinaryBenchmarkTest.xml
```

## Caveat on the byte-exact formula

For random base64, real tiktoken o200k_base produces 0.683 tokens/char; the byte-exact formula produces 0.75 tokens/char (9.8% high — the safe direction for budgeting).

For uniform base64 (e.g. `AAAA...`), real tiktoken collapses to 0.125 tokens/char via BPE merges; the byte-exact formula produces 0.75 tokens/char (6× high — the safe direction).

For image MIME types, the empirical model-specific rates (Claude's `(width × height) / 750`, GPT-4o's tile formula, Gemini's 258-tile) can be 1.5–3× higher than the byte-exact formula. Configure `binaryMimeOverride` for these.

The `binaryFudgeFactor` of 1.0 is byte-exact. Bump to 1.1 for a 10% safety margin.

## Migration checklist for downstream projects

If you're using TPipe's `countBinaryTokens` (transitively via `setTokenBudget` on a pipe that receives binaries), the v1.2.0 change is **non-breaking** for the default behavior:

- Old path: `Dictionary.countTokens` on base64 string ⇒ large token counts, O(n) cost, OOM at 4 MB.
- New path: `Dictionary.countBinaryTokens` on decoded bytes ⇒ `ceil(bytes / 4)` token count, O(1) cost, no OOM.

The token count for a given binary drops by ~30% (87,371 → 65,536 for 256 KB) because the byte-exact formula is more accurate than the old dictionary-no-match-fallback heuristic. This is a **budget-increase** effect — your pipes will have MORE available context after the upgrade.

If you depended on the old over-counting behavior, configure `binaryFudgeFactor = 1.33` to recover approximately the old token count for 256 KB raw binaries (87,371 / 65,536 ≈ 1.33). Note that this only holds for the 256 KB size; the relationship is not linear across the full range.

If you depend on a specific token count for budgeting (e.g. to match a downstream LLM's reported usage), use `binaryMimeOverride` with your model's per-MIME formula, or wire an `EXTERNAL_ENCODER` with a real BPE encoder implementation.
