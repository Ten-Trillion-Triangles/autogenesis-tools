# MiniMax Model Reference

Canonical model names, response shapes, and deprecated names to avoid.

## Canonical Model Names (use these)

| Model | Reasoning? | Notes |
|-------|------------|-------|
| `MiniMax-M3` | No | Newest. No `setCacheControl` support. Uses passive auto-cache on `/v1`. No Anthropic endpoint support. |
| `MiniMax-M2.7` | Yes | **Primary live-test target.** Emits `<think>` blocks and `reasoning_details[]` array. Supports explicit cache_control on `/anthropic/v1/messages` (TTL ignored, always 5min). |
| `MiniMax-M2.5` | Yes | Same as M2.7 behavior. |
| `MiniMax-M2.1` | Yes | Same as M2.7 behavior. |
| `MiniMax-M2` | Yes | Only one that requires `/anthropic/v1/messages` (no passive auto-cache on `/v1`). |

## Deprecated / Wrong Names (NEVER use)

| Name | Why it's wrong |
|------|----------------|
| `MiniMax-text-01` | Legacy Anthropic-era codename. The current canonical name is `MiniMax-M2`. The 2026-06 audit of `docs/generic-openai/getting-started.md` caught this — line 223 had `setModel("MiniMax-text-01")` which was incorrect. |
| `https://api.MiniMax.io/v1` | Wrong case. Correct is `https://api.minimax.io/v1` (all lowercase). The casing bug appeared in `docs/generic-openai/getting-started.md` line 115 and 222. |
| `MiniMax_API_KEY` | Wrong env var name. Correct is `MINIMAX_API_KEY` (all caps). Found in `docs/generic-openai/getting-started.md` line 221. |
| `/anthropic` (without `/v1/messages`) | Truncated path. Returns 400. Must be `/anthropic/v1/messages`. |

## Response Shape Quirks

### Thinking blocks on `/v1` (OpenAI mode)
MiniMax-M2.7 includes `<think>...</think>` blocks in the response text. The `reasoning_details[]` array is also returned in the chat completions response message object. Both forms need to be handled when parsing.

### Thinking blocks on `/anthropic/v1/messages` (Anthropic mode)
Anthropic-style content blocks with `type: "thinking"`. TPipe's `AnthropicResponseParser` handles these — see `api/AnthropicResponseParser.kt`.

### Reasoning on `/v1/responses` (OpenAI Responses mode)
Uses `OpenAIResponsesResponse` shape with `output` array containing typed items including `reasoning` items. TPipe's `OpenAIResponsesSseParser` extracts `response.reasoning_text.delta` events. See `env/OpenAIResponsesResponse.kt:55-110` for the schema.

### MiniMax hardwired-to-think behavior
**CRITICAL for testing reasoning toggle:** MiniMax-M2.7 emits reasoning content even when the wire `enabled=false` flag is set in `setReasoningConfig(enabled=false)`. This is a model behavior, not a TPipe bug. So when testing whether reasoning toggle works, **do not assert on `reasoningContent` presence/absence in the response**. Assert on the trace metadata's `reasoningEnabled=true|false` flag instead (which reflects the base `Pipe.useModelReasoning` field).

## Endpoint Selection Cheat-Sheet

| If you want... | Use |
|----------------|-----|
| OpenAI chat completions (default, simplest) | `ApiMode.OpenAI` + `https://api.minimax.io/v1` + `/chat/completions` |
| Anthropic messages format (for cache_control, M2.7 thinking blocks) | `ApiMode.Anthropic` + `https://api.minimax.io/anthropic` + `/v1/messages` |
| OpenAI Responses API (for `response.*` streaming, `instructions` top-level) | `ApiMode.OpenAIResponses` + `https://api.minimax.io/v1` + `/responses` |

The `apiMode` is LOCKED after the first API call. Set it up front before `init()` or `execute()`.

## Caching

| Endpoint | Cache mechanism | TTL |
|----------|----------------|-----|
| `/v1` (OpenAI) | Passive auto-cache (no markers needed) | Auto-managed by MiniMax |
| `/v1/responses` (OpenAI Responses) | Passive auto-cache | Auto-managed by MiniMax |
| `/anthropic/v1/messages` (Anthropic) | Explicit `cache_control: {type: "ephemeral"}` on last system block | Always 5min on MiniMax (TTL field IGNORED) |
| `/anthropic/v1/messages` on direct Anthropic | Same explicit form | "5m" or "1h" supported |

`setCacheControl()` on `GenericOpenAIPipe` is a no-op on `ApiMode.OpenAI` and `ApiMode.OpenAIResponses` — it only takes effect on `ApiMode.Anthropic`.

## Session context

Reference updated 2026-06-24 during a MiniMax support audit. The audit caught four doc/code mistakes in `docs/generic-openai/getting-started.md`:
- `https://api.MiniMax.io/v1` → `https://api.minimax.io/v1` (case)
- `System.getenv("MiniMax_API_KEY")` → `System.getenv("MINIMAX_API_KEY")` (case)
- `setModel("MiniMax-text-01")` → `setModel("MiniMax-M2")` (deprecated name)

Also added `MiniMaxReasoningToggleTest.kt` as a live test pattern for verifying the two-knob reasoning toggle architecture.
