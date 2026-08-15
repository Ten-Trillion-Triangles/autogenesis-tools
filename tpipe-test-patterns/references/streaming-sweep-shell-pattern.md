# Streaming-Callback Test Sweep Shell Pattern

Created: 2026-07-30
Session: streaming-callbacks scaffolding

## Overview

Two-shell pattern for live-test scaffolding + end-to-end gradle sweep.

## Shell 1: Credential Gate

```bash
#!/usr/bin/env bash
# /tmp/hermes-verify-streaming-credentials.sh
SUMMARY=/tmp/hermes-verify-streaming-credentials.txt
echo "[$(date +%FT%TZ)] credential gate" > "$SUMMARY"

if [ -n "${MINIMAX_API_KEY:-}" ]; then
    echo "PASS: MINIMAX_API_KEY exported (len=${#MINIMAX_API_KEY})" >> "$SUMMARY"
else
    echo "FAIL: MINIMAX_API_KEY unset — Mantle live tests will skip." >> "$SUMMARY"
fi

if [ -f "$HOME/.aws/credentials" ]; then
    echo "PASS: ~/.aws/credentials present" >> "$SUMMARY"
else
    echo "FAIL: ~/.aws/credentials missing — Bedrock live tests will skip." >> "$SUMMARY"
fi

cat "$SUMMARY"
```

## Shell 2: Full Sweep

```bash
#!/usr/bin/env bash
# /tmp/hermes-verify-streaming-sweep.sh
export GENERIC_OPENAI_LIVE_TEST=true
export AllowTest=true

# Mantle unit tests (GenericOpenAIPipeTest covers core, StreamingCallbacksLiveTest covers streaming)
./gradlew :TPipe-GenericOpenAI:test \
  --tests "genericOpenAIPipe.GenericOpenAIPipeTest" \
  --tests "genericOpenAIPipe.GenericOpenAIPipeStreamingCallbacksLiveTest" \
  > "$WORK/gradle-mantle.out" 2>&1

# Bedrock unit tests (StreamingCallbackTest = 13 tests, BedrockPipeStreamingCallbacksLiveTest = 3 live)
./gradlew :TPipe-Bedrock:test \
  --tests "bedrockPipe.StreamingCallbackTest" \
  --tests "bedrockPipe.BedrockPipeStreamingCallbacksLiveTest" \
  > "$WORK/gradle-bedrock.out" 2>&1

# Reasoning regression sweep
./gradlew :TPipe-Bedrock:test \
  --tests "bedrockPipe.QwenReasoningTest" \
  --tests "bedrockPipe.DeepSeekReasoningTest" \
  --tests "bedrockPipe.QwenNextReasoningTest" \
  --tests "bedrockPipe.MiniMaxReasoningTest" \
  --tests "bedrockPipe.KimiReasoningTest" \
  --tests "bedrockPipe.GlmReasoningTest" \
  --tests "bedrockPipe.StreamingReasoningTest" \
  > "$WORK/gradle-reasoning.out" 2>&1
```

## Key Env Vars

| Var | Module | Effect |
|-----|--------|--------|
| `GENERIC_OPENAI_LIVE_TEST=true` | TPipe-GenericOpenAI | Gates Mantle live tests; `assumeTrue(getApiKey().isNotBlank() && ...)` |
| `AllowTest=true` | TPipe-Bedrock | Gates Bedrock live tests via `TestCredentialUtils.requireAwsCredentials()` |
| `MINIMAX_API_KEY=sk-stub` | Both | Forces live tests to skip — prevents accidental real API calls in CI |

## Expected Results (credential-gated environment)

| Test class | Expected | Reason |
|------------|----------|--------|
| `GenericOpenAIPipeTest` | 50 pass, 0 fail | Unit tests, no gate |
| `GenericOpenAIPipeStreamingCallbacksLiveTest` | 3 skipped | No MINIMAX_API_KEY |
| `StreamingCallbackTest` | 13 pass, 0 fail | Unit tests, no gate |
| `BedrockPipeStreamingCallbacksLiveTest` | 3 fail (Legacy model) | `anthropic.claude-3-haiku-20240307-v1:0` deprecated in this AWS account; fix: replace with `sonnet-4` or `nova-pro` |

## Critical Fixes Discovered

1. **`@BeforeTest` → `@BeforeAll`** — JUnit 5 annotation; wrong annotation blocks ALL test compilation in the module
2. **`setStreamingCallback` overload ambiguity** — bare lambda `{ chunk -> list.add(chunk) }` returns Boolean → ambiguity between `suspend (String) -> Unit` and `(String) -> Unit`. Fix: explicit type on val or parameter
3. **`GenericOpenAIPipe` now has `streamingCallbacks { add }` DSL** — both GenericOpenAIPipe and BedrockPipe expose identical surfaces: `streamingCallbacks { add(cb); concurrent() }` and `enableStreaming(callback?)`. The Mantle implementation (added 2026-07-30) registers via `obtainStreamingCallbackManager().addCallback` + `propagateStreamingCallback` per callback, matching Bedrock's pattern. Lambda disambiguation requires explicit `suspend { }` wrapper or pre-typed val.
4. **`testStreamingCallbacksConcurrentModeFansOutInParallel` deadlock** — `CompletableDeferred` gate deadlocks when `emitToAll` in concurrent mode runs all callbacks in a single coroutine: `gate.await()` suspends that coroutine, `gate.complete()` is never reached. Fix: use `java.util.concurrent.CountDownLatch` instead — it blocks threads without suspending coroutines.
