# MiniMax API Quirks

## Overview

MiniMax is a Chinese LLM provider with non-standard API behavior compared to OpenAI and Anthropic.

## General Behavior

- Response includes `<think>...</think>` thinking blocks at the start of the response
- Non-streaming: full response includes `<think>...\n</think>` blocks
- Streaming: chunks arrive as thinking + content mixed
- Temperature 0.0 recommended to reduce non-determinism in tests

## API Endpoints

| Endpoint | Mode | Format | Notes |
|----------|------|--------|-------|
| `https://api.minimax.io/v1` | OpenAI | OpenAI SSE | Works with `ApiMode.OpenAI` |
| `https://api.minimax.io/anthropic/v1/messages` | Anthropic | Anthropic JSON or SSE | Works with `ApiMode.Anthropic` — use FULL path including `/v1` |
| `https://api.minimax.io/anthropic` | Anthropic | — | **DOES NOT WORK** — missing `/v1/messages` segment → 400 error |

## CRITICAL: Use Full Endpoint Path for Anthropic Mode

MiniMax's Anthropic endpoint requires the **complete path** `https://api.minimax.io/anthropic/v1/messages`.

- `/anthropic` alone → 400 "invalid params, invalid role: (2013)"
- `/anthropic/v1/messages` → 200 OK with correct response

This differs from OpenAI mode which only needs `/v1`.

## Streaming

MiniMax's streaming at `/v1` uses OpenAI SSE format (`data: {...}` lines). At `/anthropic/v1/messages` with `stream: true`, it emits true Anthropic SSE format (`event: content_block_delta\ndata: {...}`).

**Test evidence:**
```
ApiMode.OpenAI + api.minimax.io/v1 → chunks received (PASS)
ApiMode.Anthropic + api.minimax.io/anthropic/v1/messages → chunks received (PASS) — streaming works with full path
```

Both SSE formats work on MiniMax — the key is using the correct endpoint path.

### Passive Auto-Cache — `/v1` (OpenAI wire)
- **Endpoint:** `https://api.minimax.io/v1`
- **Mode:** `ApiMode.OpenAI`
- **How it works:** MiniMax automatically identifies repeated context for requests with 512+ input tokens. No `cache_control` markers needed.
- **Cache write cost:** Free
- **Cache hit billing:** Discounted price
- **Expiration:** Auto-adjusted by MiniMax based on system load
- **Supported models:** M3, M2.7 series, M2.5 series, M2.1 series
- **What gets cached:** Prefix matching in order `tool list` → `system prompts` → `user messages`
- **This is the RECOMMENDED mode** — system prompt is large and static, catches automatically
- **Docs:** https://platform.minimax.io/docs/api-reference/text-prompt-caching

### Explicit Cache-Control — `/anthropic/v1/messages` (Anthropic wire)
- **Endpoint:** `https://api.minimax.io/anthropic/v1/messages`
- **Mode:** `ApiMode.Anthropic`
- **How it works:** `pipe.setCacheControl(type="ephemeral", ttl=null)` on `GenericOpenAIPipe` adds `cache_control: {type: "ephemeral"}` to the LAST system block. The `AnthropicRequestSerializer.buildSystemContent()` handles block placement per spec.
- **TTL on MiniMax:** IGNORED — always 5min, auto-refreshes on hit at no extra cost
- **TTL on direct Anthropic:** "5m" (default) or "1h" supported
- **Supported models:** M2.7, M2.5, M2.1, M2 (NOT M3 — use passive auto-cache on `/v1` instead)
- **Cache write cost:** Extra charge on first write
- **Cache hit billing:** Discounted price
- **Verified by:** `AnthropicApiModeTest.testAnthropicRequestSerializerWithCacheControlEmitsSystemBlocks` and `testAnthropicRequestSerializerCacheControlWithTTL` in `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/AnthropicApiModeTest.kt` (line 475+). The "TPipe cannot currently emit explicit cache markers" claim in older revisions of this file is OUTDATED — `setCacheControl` was wired in.

### Default Recommendation

| Model | Endpoint | Mode | Why |
|-------|----------|------|-----|
| M3, M2.7, M2.5, M2.1 | `https://api.minimax.io/v1` | `ApiMode.OpenAI` | Passive auto-cache works, no markers needed |
| M2 | `https://api.minimax.io/anthropic/v1/messages` | `ApiMode.Anthropic` | M2 has no passive cache support |

## Reasoning Toggle — Two Knobs (Critical)

TPipe has TWO reasoning knobs that work together — confusing them produces a non-functional toggle:

1. **Base `Pipe.setReasoning()` / `disableReasoning()`** — flips `useModelReasoning: Boolean` in base `com.TTT.Pipe.Pipe` class. This is what propagates to trace metadata as `reasoningEnabled=true|false`. See `Pipe.kt:1119, 3930-3967` and the trace emit at `Pipe.kt:4723`.

2. **`GenericOpenAIPipe.setReasoningConfig(config)`** — writes the `reasoning` block to the wire body (`{effort, max_tokens, enabled, exclude}`). Has NO effect on the trace `reasoningEnabled` flag.

For a working toggle, use BOTH:
```kotlin
pipe.setReasoning()                            // flips trace flag
pipe.setReasoningConfig(                       // writes wire payload
    ReasoningConfig(effort = "high", enabled = true)
)
```

**DEAD CODE WARNING:** `GenericOpenAIPipe.kt:157` declares `private var reasoningEnabled: Boolean? = null` — this field is never read or written by any code path. The trace `reasoningEnabled` metadata comes from base `Pipe.useModelReasoning`, not from this field. Don't try to set it. (Future cleanup target.)

**MiniMax-M2.7 hardwired to think:** the model emits reasoning content even when wire `enabled=false` is set. So toggle verification CANNOT use response `reasoningContent` presence — use trace metadata `reasoningEnabled=true|false` instead.

Canonical 3-test pattern: `MiniMaxReasoningToggleTest.kt` in `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/`:
- `testReasoningOnEmitsReasoningTokens` — `setReasoning()` + `setReasoningConfig(enabled=true)`, saves trace
- `testReasoningOffSuppressesReasoningTokens` — `disableReasoning()` + `setReasoningConfig(enabled=false)`, saves trace
- `testReasoningToggleComparison` — reads both trace files, asserts `reasoningEnabled=true` in ON file and `reasoningEnabled=false` in OFF file

Activation: `@EnabledIfEnvironmentVariable(named = "MINIMAX_API_KEY", matches = ".+")`. Trace files saved to `TPipe-GenericOpenAI/build/traces/MiniMax-reasoning-{ON,OFF}.json` (or `TRACES_DIR` env var if set).

## Live Tests

Tests live at `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/`:

- `MiniMaxLiveTest.kt` — non-streaming live test
- `AnthropicStreamingLiveTest.kt` — streaming test with `ApiMode.Anthropic` + `/anthropic/v1/messages`
- `OpenAIResponsesLiveTest.kt` — 5 tests against `/v1/responses` (non-streaming, streaming, system prompt, JSON object format, reasoning capture)
- `MiniMaxReasoningToggleTest.kt` — 3 tests verifying the two-knob reasoning toggle (ON, OFF, comparison)

To run:
```bash
cd /home/cage/Desktop/Workspaces/TPipe/TPipe
MINIMAX_API_KEY="sk-cp-..." ./gradlew :TPipe-GenericOpenAI:test --tests "*.MiniMaxReasoningToggleTest"
```

## Key Finding: The 400 "invalid role" Error

**Symptom:** `400 Bad Request` with error `"invalid params, invalid role: (2013)"` — empty role value.

**Root cause:** Two possible issues:
1. Wrong endpoint path — using `/anthropic` instead of `/anthropic/v1/messages`
2. `generateText()` path using wrong serialization — see `tpipe-generic-openai` SKILL.md "Critical Pitfall" section

**Fix steps:**
1. Verify endpoint is `/anthropic/v1/messages` (full path)
2. Verify JSON has correct field names for the mode (`role` for OpenAI, `type` for Anthropic)
3. Add debug print: `System.err.println("DEBUG_JSON_REQ: $jsonRequest")` before HTTP POST
4. Compare debug output against a known-working curl request

## Working Curl for Anthropic Mode

```bash
curl -X POST 'https://api.minimax.io/anthropic/v1/messages' \
  -H 'Authorization: Bearer sk-cp-...' \
  -H 'Content-Type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{
    "model": "MiniMax-M2.7",
    "messages": [{"type": "user", "content": [{"type": "text", "text": "Say hello in 5 words."}]}],
    "max_tokens": 256,
    "stream": false
  }'
```

Note: MiniMax accepts both `type` and `role` fields in the message object when using the Anthropic endpoint.

## Canonical Model Names (avoid deprecated)

**USE:** `MiniMax-M3`, `MiniMax-M2.7`, `MiniMax-M2.5`, `MiniMax-M2.1`, `MiniMax-M2`

**NEVER USE:** `MiniMax-text-01` (legacy Anthropic-era codename). The 2026-06 audit caught this name in `docs/generic-openai/getting-started.md` line 223 — should be `MiniMax-M2`.

**NEVER USE (case-sensitive):** `https://api.MiniMax.io/v1` (correct: `https://api.minimax.io/v1`), `MiniMax_API_KEY` env var (correct: `MINIMAX_API_KEY`).
