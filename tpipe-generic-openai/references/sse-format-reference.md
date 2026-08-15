# SSE Format Reference: OpenAI vs Anthropic

## OpenAI SSE Format

Used by: OpenAI, MiniMax at `api.minimax.io/v1`, any OpenAI-compatible provider.

**Lines sent by server:**
```
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Hello"}}]}
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":" world"}}]}
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"!"}}]}
data: [DONE]
```

**Key characteristics:**
- Lines start with `data: ` prefix (no `event:`)
- JSON objects with `choices[].delta.content` for incremental text
- `[DONE]` marker to signal end
- No event type field

**TPipe parser:** `SseParser.extractContentFromLine()` (line 110 of `SseParser.kt`)

## Anthropic SSE Format

Used by: Real Anthropic API at `api.anthropic.com`.

**Lines sent by server:**
```
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}

event: message_stop
data: {"type":"message_stop"}
```

**Key characteristics:**
- Two-line format: `event: <type>` followed by `data: <json>`
- JSON must contain `"type":"content_block_delta"` (checked by parser)
- Multiple event types: `content_block_delta`, `message_stop`, `ping`, etc.
- Text content in `delta.text` field

**TPipe parser:** `AnthropicSseParser.extractContentFromLine()` (line 298 of `SseParser.kt`)

## Why Mixing Them Fails

If you call MiniMax with `ApiMode.Anthropic`:
- TPipe sends request correctly
- MiniMax responds with OpenAI SSE format (`data: {...}`)
- `AnthropicSseParser.extractContentFromLine()` looks for `"type":"content_block_delta"` in each line
- OpenAI SSE lines don't have this field → 0 chunks extracted

If you call real Anthropic with `ApiMode.OpenAI`:
- TPipe sends request correctly
- Anthropic responds with Anthropic SSE format (`event: ...\ndata: ...`)
- `SseParser.extractContentFromLine()` looks for `data: ` prefix + JSON with `choices[].delta.content`
- Anthropic SSE lines start with `event: ` → 0 chunks extracted

## Quick Diagnosis

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| 0 chunks with OpenAI URL | Wrong ApiMode? | Check URL matches mode |
| 0 chunks with Anthropic URL | Wrong ApiMode? | Check URL matches mode |
| Some chunks but empty final | SSE parser mismatch | Confirm actual format vs mode |
| Works in browser/curl | TPipe SSE parsing issue | Compare TPipe output to curl output |
