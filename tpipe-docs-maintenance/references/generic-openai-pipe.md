# GenericOpenAI Pipe — Doc Audit Reference

Created: 2026-06-07
Commit: 2d055494 (mcp-server branch)
Reason: New TPipe-GenericOpenAI module with three ApiMode variants had no existing doc.

## What Was Added

`docs/api/generic-openai-pipe.md` — full API reference for `GenericOpenAIPipe`

**Covers:**
- `ApiMode.OpenAI` — `/v1/chat/completions`, Bearer token
- `ApiMode.Anthropic` — `/anthropic/v1/messages`, x-api-key header
- `ApiMode.OpenAIResponses` — `/v1/responses`, Bearer token
- `setApiKey()` / `setBaseUrl()` / `setApiMode()`
- Function calling (`setTools`, `setToolChoice`, `setParallelToolCalls`)
- Structured output (`setResponseFormat`, `setStructuredOutputs`)
- Streaming (`setStreamingEnabled`, `setStreamingCallback`)
- Reasoning (`setReasoningConfig`)
- Multimodal binary content → format mapping per mode

**Audit command used:**
```bash
git log --since="3 days ago" --oneline --name-only
# Filter to TPipe-GenericOpenAI/ changes
# Read GenericOpenAIPipe.kt and ApiMode.kt to verify behavior
# Create docs/api/generic-openai-pipe.md
```

## Other Gaps Found This Session

### 1. MultimodalContent missing items (docs/api/multimodal-content.md)
- `interuptPipeline` property — was missing
- `interupt()` method — was missing
- `terminateAndPassPipeline()` method — was missing
- `saveSnapshot()` / `deleteSnapshot()` — were missing
- `setDistributionGridDirective()` / `getDistributionGridDirective()` — were missing

### 2. ConverseRole supervisor (docs/api/converse-history.md)
- `supervisor` enum value — was missing from the enum listing

## Pattern for Future Audits

When auditing, run:
```bash
# Get recent changes
git log --since="3 days ago" --oneline --name-only

# For each new .kt file, check:
# 1. Does docs/api/<classname>.md exist?
# 2. Does the existing doc cover all public methods and properties?
# 3. Are new enum values listed in the doc?
```