# TPipe Trace Formats

TPipe supports 4 output formats for trace data, configured via `TraceFormat` enum.

## Format Overview

| Format | Description | File Extension | Use Case |
|--------|-------------|---------------|----------|
| `JSON` | Structured machine-readable | `.json` | Machine parsing, export/import |
| `HTML` | Visual with charts | `.html` | Human review, debugging UI |
| `MARKDOWN` | Text-based tables | `.md` | Documentation, text analysis |
| `CONSOLE` | Human-readable text | `.txt` | Terminal output, quick logs |

---

## JSON Format

### Structure

JSON traces are arrays of `TraceEvent` objects:

```json
[
  {
    "id": "trace-event-1",
    "timestamp": 1746284400000,
    "pipeId": "pipe-001",
    "pipeName": "BedrockPipe-Claude",
    "eventType": "PIPE_START",
    "phase": "INITIALIZATION",
    "content": null,
    "contextSnapshot": null,
    "metadata": {
      "model": "claude-3-sonnet",
      "provider": "bedrock"
    }
  }
]
```

### TraceEvent Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Auto-generated: `trace-event-${counter}` |
| `timestamp` | Long | Unix timestamp in milliseconds |
| `pipeId` | String | Pipeline identifier |
| `pipeName` | String | Human-readable name |
| `eventType` | String | TraceEventType enum name |
| `phase` | String | TracePhase enum name |
| `content` | MultimodalContent? | Optional input/output (null if stripped) |
| `contextSnapshot` | ContextWindow? | Optional memory state (null if stripped) |
| `metadata` | Map<String, Any> | Flexible key-value pairs |

### Parsing Notes

- Use `kotlinx.serialization.json.Json.decodeFromString<List<TraceEvent>>()` for parsing
- `MapAnySerializer` handles `Map<String, Any>` with nested Maps/Lists
- The `error` field is `@Transient` — not serialized
- Large files (>10MB) should be processed in chunks of 1000 events

---

## HTML Format

### Structure

HTML traces are self-contained web pages with:
- Embedded Mermaid flowchart for pipeline visualization
- Table with 6 columns: Time, Pipe, Event, Phase, Status, Metadata
- Collapsible `<details>` elements for content dumps
- JavaScript interactivity (click to highlight)

### Key HTML Elements

```html
<table id="trace-details-table">
  <tr>
    <th>Time</th>
    <th>Pipe</th>
    <th>Event</th>
    <th>Phase</th>
    <th>Status</th>
    <th>Metadata</th>
  </tr>
  <tr class="trace-item" data-pipe="BedrockPipe-Claude">
    <td>+0ms</td>
    <td>BedrockPipe-Claude</td>
    <td>PIPE_START</td>
    <td>INITIALIZATION</td>
    <td class="info">INFO</td>
    <td class="metadata">
      <details>
        <summary>Content</summary>
        <pre>actual data</pre>
      </details>
    </td>
  </tr>
</table>
```

### Parsing Notes

- Strip `<script>`, `<style>`, `<div>`, `<span>` tags
- Extract rows from `table#trace-details-table`
- Time values are relative: `+0ms`, `+200ms`
- Status classes: `success`, `failure`, `info`
- Details content has `<strong>` tags for key names

---

## MARKDOWN Format

### Structure

Markdown traces use table formatting:

```markdown
# TPipe Pipeline Execution Flow

## Execution Details

| Time | Pipe | Event | Phase | Status | Metadata |
|------|------|-------|-------|--------|----------|
| +0ms | BedrockPipe-Claude | PIPE_START | INITIALIZATION | INFO | model: claude-3-sonnet |
| +200ms | BedrockPipe-Claude | API_CALL_START | EXECUTION | INFO | endpoint: bedrock.invoke |
```

### Parsing Notes

- Table headers may include emoji: clock, wrench, note, etc.
- Separator rows: `|---|---|` are not data
- Content after tables may include code blocks
- Metadata is space-separated key: value pairs

---

## CONSOLE Format

### Structure

Console traces use emoji prefixes:

```
[INFO] [PIPE_START] BedrockPipe-Claude at +0ms (INITIALIZATION)
[INFO] [API_CALL_START] endpoint=bedrock.invoke at +200ms (EXECUTION)
[SUCCESS] [API_CALL_SUCCESS] responseTokens=300 at +1500ms (EXECUTION)
[SUCCESS] [PIPE_SUCCESS] success=true at +1700ms (CLEANUP)
```

### Emoji Meanings

| Prefix | Event Type |
|--------|------------|
| `[INFO]` | Info/Start |
| `[SUCCESS]` | Success |
| `[FAILURE]` | Failure |
| `[ERROR]` | Error |
| `[PHASE]` | Special/Phase |

### Parsing Notes

- Regex pattern: `\[(\w+)\]\s+\[(\w+)\]\s+(.+?)(?:\s+at\s+\+(\d+)ms)?`
- Strip ANSI color codes: `\x1b\[[0-9;]*m`
- Handle multi-line events (continuation lines start with spaces)

---

## Default Storage Location

TPipe stores traces at:
```
~/.tpipe/debug/
```

Configured via `TraceConfig`:
```kotlin
TraceConfig(
    autoExport = true,
    exportPath = "~/.tpipe/debug/"
)
```

---

## Large File Handling

For files >10MB:

1. **JSON**: Process in chunks of 1000 events
2. **HTML**: Extract table rows in batches
3. **MARKDOWN**: Process section by section
4. **CONSOLE**: Stream line-by-line

Python chunked processing example:
```python
CHUNK_SIZE = 1000
for i in range(0, len(events), CHUNK_SIZE):
    chunk = events[i:i + CHUNK_SIZE]
    process(chunk)
```

---

## See Also

- `references/event-types.md` — All TraceEventType values
- `references/console_trace.md` — CONSOLE format parsing guide