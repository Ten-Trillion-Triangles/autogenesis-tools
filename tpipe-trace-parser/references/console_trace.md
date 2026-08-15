# Console Trace Format Parsing

TPipe's CONSOLE trace format is a human-readable text output that requires pattern matching rather than structured parsing. This guide documents how to parse console traces effectively.

## Format Overview

Console traces use text-based formatting with emoji symbols per event type:

```
[INFO] [PIPE_START] BedrockPipe-Claude at +0ms (INITIALIZATION)
[INFO] [API_CALL_START] endpoint=bedrock.invoke at +200ms (EXECUTION)
[SUCCESS] [API_CALL_SUCCESS] responseTokens=300 at +1500ms (EXECUTION)
[SUCCESS] [PIPE_SUCCESS] success=true at +1700ms (CLEANUP)
```

## Common Patterns

### Event Pattern
```
{emoji} [{event_type}] {pipe_name} at +{time}ms ({phase})
```

### Success/Failure Pattern
```
✅/❌ [{event_type}] {details} at +{time}ms ({phase})
```

### Key-Value Metadata Pattern
```
{key}={value} or {key}: {value}
```

## Regex Patterns

### Basic Event Extraction
```python
import re

# Event line pattern
event_pattern = r'\[(\w+)\]\s+\[([A-Z_]+)\]\s+(.+?)(?:\s+at\s+\+(\d+)ms)?\s*\(([A-Z_]+)\)'

# Extract all events
for match in re.finditer(event_pattern, console_text):
    status, event_type, details, time_ms, phase = match.groups()
```

### Time Extraction
```python
time_pattern = r'\+(\d+)ms'
```

### Status Extraction
```python
success_pattern = r'\[SUCCESS\]'
failure_pattern = r'\[FAILURE\]'
info_pattern = r'\[INFO\]'
```

### Metadata Key-Value
```python
kv_pattern = r'([a-zA-Z]+)[:=]\s*([^,\)]+)'
```

## Example Parser Snippet

```python
import re

def parse_console_trace(console_text: str) -> list:
    events = []

    # Split into lines and process each
    for line in console_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Match event line
        match = re.match(
            r'\[(\w+)\]\s+\[(\w+)\]\s+(.+?)(?:\s+at\s+\+(\d+)ms)?',
            line
        )
        if match:
            status, event_type, details, time_ms = match.groups()

            event = {
                'status': status,
                'event': event_type,
                'details': details.strip(),
                'timeDeltaMs': int(time_ms) if time_ms else 0,
            }

            # Extract metadata from details
            kv_matches = re.findall(r'(\w+)[:=]\s*([^,\)]+)', details)
            for key, value in kv_matches:
                event[key] = value.strip()

            events.append(event)

    return events
```

## Event Status Meanings

| Status | Meaning |
|--------|---------|
| `[INFO]` | Info/Start event |
| `[SUCCESS]` | Success event |
| `[FAILURE]` | Failure event |
| `[ERROR]` | Error event |
| `[PHASE]` | Special/Phase event |

## Common Metadata Fields

- `endpoint` - API endpoint called
- `model` - Model name used
- `provider` - Provider (bedrock, ollama, etc.)
- `tokenCount` - Token usage
- `responseTokens` - Response token count
- `latency` - Request latency
- `success` - Boolean success flag

## Multi-line Handling

Console traces may have multi-line output for complex events:

```
[INFO] [PIPE_START] BedrockPipe-Claude at +0ms (INITIALIZATION)
   model=claude-3-sonnet provider=bedrock
```

Handle by continuing to read lines that start with whitespace.

## Edge Cases

1. **Color codes in output**: ANSI color codes may appear — strip with regex `r'\x1b\[[0-9;]*m'`
2. **Progress bars**: May appear as `[====>----]` — skip these lines
3. **Mixed timestamps**: Some lines may have absolute timestamps instead of deltas
4. **Wrapped lines**: Long lines may wrap — reassemble based on indentation

## Validation

After parsing, verify events have:
- `event` field (required)
- Either `timeDeltaMs` or `timestamp` (required)
- `status` derived from status code (INFO/SUCCESS/FAILURE/ERROR)