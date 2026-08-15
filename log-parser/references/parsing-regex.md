# Log Parsing Regex Reference

This file documents regex patterns and parsing approaches for different log formats.

## Standard Logging Format (Python stdlib with time)

Pattern: `2026-05-03 10:15:23,123 - LEVEL - message`

Regex:
```
^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+-\s+(\w+)\s+-\s+(.*)$
```

Groups: timestamp, level, message

Python parsing:
```python
import re
pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+-\s+(\w+)\s+-\s+(.*)$')

def parse_stdlib_log(line):
    match = pattern.match(line)
    if match:
        return {
            'timestamp': match.group(1),
            'level': match.group(2),
            'message': match.group(3)
        }
    return None
```

---

## Loguru Format

Pattern: `2026-05-03 10:15:23.123 | LEVEL | source:line - message`

Regex:
```
^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\|\s+(\w+)\s*\|\s+(.+):(\d+)\s+-\s+(.*)$
```

Groups: timestamp, level, source, line, message

Python parsing:
```python
import re
pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\|\s+(\w+)\s*\|\s+(.+):(\d+)\s+-\s+(.*)$')

def parse_loguru(line):
    match = pattern.match(line)
    if match:
        return {
            'timestamp': match.group(1),
            'level': match.group(2),
            'source': match.group(3),
            'line': match.group(4),
            'message': match.group(5)
        }
    return None
```

---

## JSON Lines Format

Each line is a valid JSON object.

Python parsing:
```python
import json

def parse_json_lines(line):
    try:
        obj = json.loads(line)
        entry = {}
        for key, value in obj.items():
            lower_key = key.lower()
            if lower_key in ('timestamp', 'time', 'ts', '@timestamp'):
                entry['timestamp'] = value
            elif lower_key in ('level', 'loglevel', 'severity', 'levelname'):
                entry['level'] = value
            elif lower_key in ('message', 'msg', 'text', 'body'):
                entry['message'] = value
            elif lower_key in ('source', 'logger', 'name', 'logger_name'):
                entry['source'] = value
            else:
                entry[key] = value
        return entry
    except json.JSONDecodeError:
        return None
```

Extract fields: timestamp, level, message (case-insensitive key matching)

---

## Kotlin Log Format (Autogenesis)

Pattern: `2026-05-09T11:17:33.780Z [WARN] [NETWORK]: UiSignalRpcHandlers: Cannot send...`

Regex:
```
^(\d{4}-\d{2}-\d{2}T[\d:\.]+Z)\s+\[(\w+)\]\s+\[(\w+)\]:\s+(.*)$
```

Groups: timestamp, level, category, message

Python parsing:
```python
import re
pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T[\d:\.]+Z)\s+\[(\w+)\]\s+\[(\w+)\]:\s+(.*)$')

def parse_kotlin_log(line):
    match = pattern.match(line.strip())
    if match:
        return {
            'timestamp': match.group(1),
            'level': match.group(2),
            'category': match.group(3),
            'message': match.group(4)
        }
    return None
```

---

## Filter Implementation Patterns

### Level Filter

```python
def filter_by_level(entries, target_level):
    return [e for e in entries if e.get('level', '').upper() == target_level.upper()]
```

### Time Range Filter

```python
from datetime import datetime

def filter_by_time_range(entries, start_time=None, end_time=None):
    def parse_timestamp(ts):
        for fmt in (
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S,%f',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
        ):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
        return None

    filtered = []
    for entry in entries:
        ts = parse_timestamp(entry.get('timestamp', ''))
        if ts is None:
            continue
        if start_time and ts < start_time:
            continue
        if end_time and ts > end_time:
            continue
        filtered.append(entry)
    return filtered
```

### Pattern Match Filter

```python
import re

def filter_by_pattern(entries, pattern):
    compiled = re.compile(pattern, re.IGNORECASE)
    return [e for e in entries if compiled.search(e.get('message', ''))]
```

---

## CLI Interface Design

```bash
python log_parser.py <log_file> [options]
```

| Option | Description |
|--------|-------------|
| `--level LEVEL` | Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `--start-time DATETIME` | Filter entries after this time (ISO format or 'YYYY-MM-DD HH:MM:SS') |
| `--end-time DATETIME` | Filter entries before this time |
| `--pattern PATTERN` | Search pattern in message (regex supported) |
| `--source SOURCE` | Filter by logger name/source |
| `--category CATEGORY` | Filter by category (Kotlin logs) |
| `--limit N` | Limit to N entries |
| `--show-errors` | Show lines that could not be parsed |

---

## Common Log Level Normalization

Log levels vary across formats. Normalize to uppercase:

```python
LEVEL_MAP = {
    'debug': 'DEBUG',
    'info': 'INFO',
    'information': 'INFO',
    'warn': 'WARNING',
    'warning': 'WARNING',
    'error': 'ERROR',
    'err': 'ERROR',
    'critical': 'CRITICAL',
    'fatal': 'CRITICAL',
    'fatality': 'CRITICAL',
}

def normalize_level(level):
    if level is None:
        return None
    upper = level.upper()
    return LEVEL_MAP.get(upper, upper)
```