# Dictionary.countTokens performance characteristics

Benchmarked against the Project Gutenberg Shakespeare file (`/tmp/pg100.txt`, 5,575,099 chars, ~1.35M tokens) on the TPipe root project, JVM warmup applied. Full sweep harness at `src/test/kotlin/Context/DictionaryCountBenchmarkTest.kt`.

> **Different problem space:** this reference covers the text-path throughput (1.35M tokens / 337 ms, ~4M tokens/s). The binary path (`countBinaryTokens` over `BinaryContent.Bytes` rebased to base64) is a separate regime — see `references/countBinaryTokens-benchmark.md` for the ~1,300× slower, OOM-at-5.6 MB finding.

## Results table (default English wordlist, 466K entries)

| Configuration | Time | Tokens | chars/sec |
|---|---|---|---|
| default (subword-first, favor-whole-words) | 285 ms | 1,347,367 | 19.5M |
| favorWholeWords=false | 269 ms | 1,352,082 | 20.7M |
| countSubWordsInFirstWord=false | **178 ms** | 1,347,367 | **31.3M** |
| splitForNonWordChar=false | 249 ms | 1,322,842 | 22.4M |
| alwaysSplitIfWholeWordExists=true | 227 ms | 1,347,367 | 24.5M |
| countSubWordsIfSplit=true | 266 ms | 1,322,842 | 20.9M |
| countOnlyFirstWordFound=true | 227 ms | 839,394 | 24.5M |
| nonWordSplitCount=2 | 190 ms | 1,641,202 | 29.4M |
| nonWordSplitCount=8 | 173 ms | 1,223,388 | 32.2M |
| tokenCountingBias=0.10 | 151 ms | 1,482,104 | 37.0M |

## Where the cost lives

- `findAllMatches` (the first-word subword scan at `Dict.kt:140`) is the single biggest cost driver. `countSubWordsInFirstWord=false` gives ~38% speedup because it skips `findAllMatches` entirely on the first word and falls through to `findLongestMatch`.
- `findLongestMatch` (`Dict.kt:115`) walks lengths 50..1 with a `HashSet.contains` per probe. `HashSet.contains` on the 466K-entry default wordlist is fast (~80-150ns) but is called millions of times on a 1M-token corpus.
- `nonWordSplitCount` shifts the work between dictionary lookups and char-based fallback counting without changing the wall-time floor by much.
- `tokenCountingBias` only multiplies the final number, it does not change loop work — apparent speedup is a measurement artifact, not a real gain.

## Operational guidance

- If the memory system needs throughput, set `countSubWordsInFirstWord=false` on the `TruncationSettings` used for budget calculation. Keep it on for the per-token precision path if needed.
- `countOnlyFirstWordFound=true` produces wildly different counts (839K vs 1.35M on this corpus) — a one-token-per-word floor dominates on large inputs. Do not use it for budget calculations expecting whole-corpus accuracy.
- `Dictionary.truncate` calls `countTokens` once for the full text and then re-counts per word for the chosen truncation strategy. Truncating a 1M-token corpus is roughly 2-3x the cost of counting it.
- `resolveDictionary` is cached in a `ConcurrentHashMap` keyed by `locale:{tag}` / `path:{absolutePath}`, so the locale-vs-path resolution cost is paid at most once per settings instance.