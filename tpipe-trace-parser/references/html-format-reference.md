# HTML Trace Format Reference — byte-level

This is the canonical byte-level reference for every HTML format emitted by `TraceVisualizer.kt`. Every script in this skill targets these patterns.

## Format detection (one-pass sniff)

```python
def detect_format(html):
    if re.search(r"class=['\"]ps-(status|header|container|turn-card)['\"]", html):
        return "pumpstation"
    if "trace-details-table" in html:
        return "standard_pipeline"   # also covers Manifold/Junction/Splitter/DistributionGrid
    return "unknown"
```

PumpStation uses `ps-*` class names; every other container uses `trace-details-table`. Both can coexist if a container embeds child traces — the outer container's detector wins.

## Standard pipeline HTML (Pipe / Pipeline / Manifold / Junction / Splitter / DistributionGrid)

### Skeleton

```html
<table id="trace-details-table">
    <tr>
        <th>⏱️ Time</th><th>🔧 Pipe</th><th>📝 Event</th><th>🔄 Phase</th>
        <th>✅ Status</th><th>📊 Metadata</th>
    </tr>
    <tr id="trace-event-65" class="trace-item" data-pipe="judge">
        <td>+0ms</td>
        <td>judge</td>
        <td>PIPE_START</td>
        <td>INITIALIZATION</td>
        <td class="info">ℹ️ INFO</td>
        <td class="metadata">
            <strong>pipeClass:</strong> genericOpenAIPipe.GenericOpenAIPipe<br>
            <strong>model:</strong> MiniMax-M2.7<br>
            <strong>inputTokens:</strong> <span style="color: #28a745; font-weight: bold;">1705</span><br>
            <strong>outputTokens:</strong> <span style="color: #17a2b8; font-weight: bold;">311</span><br>
            <strong>totalTokens:</strong> <span style="color: #6f42c1; font-weight: bold;">2016</span><br>
            <details style="margin-top: 8px;">
                <summary style="cursor: pointer; color: #28a745; font-weight: bold;">
                    📥 Input Content (7170 chars)
                </summary>
                <pre style="background: #f8f9fa; padding: 10px; ...">
                    Research: Kotlin coroutines...
                </pre>
            </details>
        </td>
    </tr>
    ...
</table>
```

### Parser regexes (verified)

```python
# Row pattern (anchors the parse)
ROW = r'<tr\s+id=["\']trace-event-(\d+)["\']\s+class=["\']trace-item["\']\s+data-pipe=["\']([^"\']+)["\']\s*>(.*?)</tr>'

# Cell pattern (capture attrs + content)
CELL = r'<td([^>]*)>(.*?)</td>'

# Metadata pair (key terminates at <br> or <details>)
META_PAIR = r"<strong>([^<]+):</strong>\s*(?:<span[^>]*>)?([^<]*)"

# Content block (input/output/prompt previews)
DETAILS = r"<details[^>]*>\s*<summary[^>]*>(.*?)</summary>\s*<pre[^>]*>(.*?)</pre>\s*</details>"

# Status class → label (the CLASS ATTR is authoritative, not the text)
#   class="success" → "SUCCESS"     (or "✅ SUCCESS" inside)
#   class="failure" → "FAILURE"
#   class="info"    → "INFO"
```

### Critical parsing rules

1. **Status comes from `class="..."` attribute on cell 4**, not from the emoji text. The emoji can be `ℹ️ INFO` or `✅ SUCCESS` — both are display decoration.
2. **Metadata values split on `<br>`** — never grab up to next `<` greedily (concatenation bug).
3. **HTML entities unescape**: `&quot;` → `"`, `&#39;` → `'`, `&lt;` → `<`, `&gt;` → `>`, `&amp;` → `&`.
4. **Two API_CALL_SUCCESS events per Pipe**: first has `inputTokens/outputTokens/totalTokens`, second has `totalInputTokens/totalOutputTokens`. Both are valid; don't dedupe.

### Token field rendering (HTML)

```html
<inputTokens>  → <strong>inputTokens:</strong> <span style="color: #28a745;">N</span>
<outputTokens> → <strong>outputTokens:</strong> <span style="color: #17a2b8;">N</span>
<otherTokens>  → <strong>key:</strong> <span style="color: #6f42c1;">N</span>
```

Color is decoration; only the number matters. The reliable extraction regex is:

```python
r"<strong>([a-zA-Z]+):</strong>\s*<span[^>]*>(\d+)</span>"
```

## PumpStation HTML (generatePumpStationHtmlReport)

### Skeleton

```html
<!DOCTYPE html>
<html>
<head>
    <title>PumpStation Trace — ps-1784931031776-5154</title>
    <style>
        .ps-container { ... }
        .ps-header { ... }
        .ps-status-completed { background: rgba(220,252,231,0.9); color: #166534; }
        .ps-status-failed { background: rgba(254,226,226,0.9); color: #991b1b; }
        .ps-status-suspended { background: rgba(254,243,199,0.9); color: #92400e; }
        .ps-status-running { background: rgba(224,231,255,0.95); color: #3730a3; }
        .ps-run-id { font-family: 'JetBrains Mono', monospace; ... }
        .ps-turn-num { font-weight: 700; ... }
        .ps-detail-label { ... }
        .ps-detail-type { ... }
        .ps-meta-key { ... }
        .ps-meta-val { ... }
        .ps-event-text { ... }
        ...
    </style>
</head>
<body>
    <div class='ps-container'>
        <div class='ps-header'>
            <div class='ps-title'>🎯 TPipe PumpStation Trace</div>
            <div class='ps-status ps-status-completed'>COMPLETED</div>
            <span class='ps-run-id'>ps-1784931031776-5154</span>
            <span class='ps-duration'>⏱ 93845ms</span>
        </div>
        <div class='ps-ribbon'>...KPI cards...</div>
        <div class='ps-sparkline-section'>...per-turn chart...</div>
        <div class='ps-paths-section'>...active vs reserve paths...</div>
        <div class='ps-turns-section'>
            <details class='ps-turn-card' open>
                <summary class='ps-turn-summary'>
                    <span class="ps-turn-num">Turn 0</span>
                    <span class='ps-turn-phases'>
                        <span class='ps-phase-pill ps-phase-info'>Judge skipped</span>
                        ...
                    </span>
                </summary>
                <div class='ps-turn-body'>
                    <div class='ps-detail-row'>
                        <div class='ps-detail-label'>Started
                            <span class='ps-detail-type'>(PUMP_STATION_STARTED)</span>
                        </div>
                        <div class='ps-detail-meta'>
                            <div class='ps-meta-row'>
                                <span class='ps-meta-key'>originalInputPreview:</span>
                                <span class='ps-meta-val'>Research: Kotlin...</span>
                            </div>
                        </div>
                    </div>
                    <div class='ps-detail-row'>
                        <div class='ps-detail-label'>Dispatch completed
                            <span class='ps-detail-type'>(PUMP_STATION_DISPATCH_COMPLETED)</span>
                        </div>
                        <div class='ps-detail-meta'>
                            <div class='ps-meta-row'>
                                <span class='ps-meta-key'>selectedPathName:</span>
                                <span class='ps-meta-val'>gather</span>
                            </div>
                            <div class='ps-meta-row'>
                                <span class='ps-meta-key'>inputTokens:</span>
                                <span class='ps-meta-val'>1928</span>
                            </div>
                            <div class='ps-meta-row'>
                                <span class='ps-meta-key'>outputTokens:</span>
                                <span class='ps-meta-val'>81</span>
                            </div>
                            <div class='ps-meta-row'>
                                <span class='ps-meta-key'>totalTokens:</span>
                                <span class='ps-meta-val'>2009</span>
                            </div>
                            <details class='ps-event-extras'>
                                <summary>📝 contentPreview</summary>
                                <pre class='ps-event-text'>...JSON verdict...</pre>
                            </details>
                        </div>
                    </div>
                    ...
                </div>
            </details>
            ...
        </div>
        <div class='ps-outcome'>...final result panel...</div>
    </div>
</body>
</html>
```

### Parser regexes (verified)

```python
# Event block (label + type + body, terminates at next label or </body>)
EVENT = (
    r"<div class=['\"]ps-detail-label['\"]>([^<]+)<span class=['\"]ps-detail-type['\"]>"
    r"\(([^)]+)\)</span></div>"
    r"(.*?)(?=<div class=['\"]ps-detail-label['\"]|</body>)"
)

# Meta pair (note the trailing colon on key, which differs from standard pipeline)
META = r"<span class=['\"]ps-meta-key['\"]>([^<]+)</span><span class=['\"]ps-meta-val['\"]>([^<]*)</span>"

# Content block (pre wrapped in details)
TEXT = r"<pre class=['\"]ps-event-text['\"]>(.*?)</pre>"
EXTRAS = r"<details class=['\"]ps-event-extras['\"]>.*?<summary[^>]*>(.*?)</summary>(.*?)</details>"

# Run ID (TWO possible locations — try both)
RUN_ID = r"<span class=['\"]ps-run-id['\"]>(ps-[\w\-]+)</span>"
TITLE_RUN_ID = r"<title>[^<]*?(ps-[\w\-]+)</title>"

# Run status
STATUS = r"class=['\"]ps-status\s+ps-status-(\w+)['\"]"
# Captured group: completed | failed | suspended | running

# Turn index (NOTE: text is "Turn N", not just N)
TURN = r"<span class=['\"]ps-turn-num['\"]>Turn\s+(\d+)</span>"
```

### Critical parsing rules

1. **Quote style is INCONSISTENT** — PumpStation mixes single (`class='ps-detail-label'`) and double (`class="ps-run-id"`). Every regex must accept both: `class=['\"]...['\"]`.
2. **Turn number has "Turn " prefix** — `<span class="ps-turn-num">Turn 0</span>`, NOT `<span class="ps-turn-num">0</span>`.
3. **Meta key has trailing colon** — `<span class='ps-meta-key'>inputTokens:</span>`. Strip the colon before storing in dict.
4. **Status badge has TWO classes** — `class="ps-status ps-status-completed"`. The captured group is the second class.
5. **`<details>` is nested inside event blocks** — `ps-event-extras` is nested under `ps-detail-meta`. The text block regex must be DOTALL.
6. **`runId` in the `<title>` is the canonical source** when `<span class="ps-run-id">` is absent (older builds).

### Token field rendering (PumpStation)

```html
<inputTokens> → <span class='ps-meta-key'>inputTokens:</span><span class='ps-meta-val'>N</span>
```

No color coding (no `<span style="color:...">`). Reliable extraction regex:

```python
r"<span class=['\"]ps-meta-key['\"]>([a-zA-Z]+):?</span><span class=['\"]ps-meta-val['\"]>(\d+)</span>"
```

The `:?` on key handles both `inputTokens:` (with colon, current build) and `inputTokens` (without colon, future-proof).

## HTML entity escape table

When stripping HTML for text extraction, decode these entities:

| Entity | Decoded |
|--------|---------|
| `&quot;` | `"` |
| `&#39;` | `'` |
| `&lt;` | `<` |
| `&gt;` | `>` |
| `&amp;` | `&` |
| `&nbsp;` | (space) |
| `&#10;` | (newline) |

Use `html.unescape()` (Python stdlib) — it handles all named and numeric entities.

## Catastrophic-regex pitfall

```bash
# HANGS for 15-30 seconds on a 1700-char single-line trace HTML row
grep -oE "EVENT_TYPE.{0,900}" trace.html

# Returns in <100ms with identical match content
grep -oE "EVENT_TYPE[^\"]{0,900}" trace.html
```

The negated char class `[^\"]` avoids greedy backtracking. Same fix applies to any `.*` quantifier with N ≥ 500 against single-line HTML.