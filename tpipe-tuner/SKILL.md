---
name: tpipe-tuner
description: "Run TPipe Tuner for a model. Print the default string."
version: 1.0.0
author: Shitty Bob (TTT)
created: 2026-07-29
tags: [tpipe, tuner, truncation, token-counting, tokenizer, llm]
trigger: "When asked to tune TPipe for a model, run the tuner, find optimal truncation settings, calibrate token counting, or print the default tuner string."
---

# TPipe Tuner

TPipe uses an internal `Dictionary` and `TruncationSettings` system to estimate token counts. Since LLM providers use different tokenization algorithms, TPipe provides tunable parameters to match the real token count. The tuner automates finding the optimal combination.

## Quick start

```bash
# Print the built-in default stress-test string (no --expected-tokens needed)
./TPipe-Tuner/tuner.sh --print-default-string

# Tune against a known token count
./TPipe-Tuner/tuner.sh --test-string "your string here" --expected-tokens 1234

# For large/multi-line strings or JSON, use command substitution
./TPipe-Tuner/tuner.sh --test-string "$(cat file.json)" --expected-tokens 1305
```

## The tuner.sh wrapper

The script at `TPipe-Tuner/tuner.sh` is a thin wrapper that:
1. Writes args to a temp file (handles spaces, newlines, quotes, special chars)
2. Calls `gradle :TPipe-Tuner:run -DtunerArgsFile=<tempfile>`
3. Cleans up the temp file

**Gradle must be on PATH.** If `gradle: command not found`, use the full path:
```bash
/home/cage/.sdkman/candidates/gradle/9.0.0/bin/gradle :TPipe-Tuner:run ...
```
Or add it to PATH: `export PATH="/home/cage/.sdkman/candidates/gradle/9.0.0/bin:$PATH"`

## Output format

The optimal configuration is emitted as a JSON block:
```json
============ OPTIMAL CONFIGURATION ===============
{
    "multiplyWindowSizeBy": 0,
    "countSubWordsInFirstWord": true,
    "favorWholeWords": true,
    "countOnlyFirstWordFound": false,
    "splitForNonWordChar": true,
    "alwaysSplitIfWholeWordExists": false,
    "countSubWordsIfSplit": false,
    "nonWordSplitCount": 4,
    "tokenCountingBias": 0.05,
    "fillMode": false,
    "fillAndSplitMode": false,
    "multiPageBudgetStrategy": null,
    "pageWeights": null
}
==================================================
```

## Applying the settings

Take the JSON values and map them into `TruncationSettings` in the appropriate provider class (e.g., `TPipe-Ollama/src/main/kotlin/com/TTT/OllamaPipe.kt`).

## Common failures

- **"Failed to find any viable combinations"** — verify the expected token count is correct for the test string size
- **`gradle: command not found`** — gradle not in PATH; use full path to gradle executable
- **Build fails on unknown option** — the `--print-default-string` flag is read by TunerApp, not Gradle; ensure the arg file is passed correctly via `-DtunerArgsFile`

## Reference

- `references/default-string.md` — the full default stress-test string used by `--print-default-string`
