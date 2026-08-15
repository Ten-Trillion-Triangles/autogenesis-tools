# TPipe Trace Parse Playbook (v2.0)

The accurate, script-driven playbook for picking apart TPipe trace
files. Every recipe in this reference was captured against a real
trace file or against the actual rendering code in `src/main/kotlin/Debug/`.
Read this BEFORE running any trace analysis — the gotchas below are
the ones that turned "garbage results" into "real data" in the 2026-07-24
rebuild session.

## Where Traces Land On Disk

Canonical resolver chain (NEVER hard-code; always go through this):

```
TPipeConfig.configDir              (default ${user.home}/.tpipe)
TPipeConfig.getDebugDir()          ← ${configDir}/debug
TPipeConfig.getTraceDir()          ← ${getDebugDir()}/trace     *** USE THIS ***
TPipeConfig.getMemoryDir()         ← ${configDir}/memory
TPipeConfig.getTodoListDir()       ← ${getMemoryDir()}/todo
TPipeConfig.getLorebookDir()       ← ${getMemoryDir()}/lorebook (autogenesis)
```

For container live tests the convention is
`${getTraceDir()}/Library/<feature>/<test-name>/<test-name>.html`.

For PumpStation live tests the convention is
`${getTraceDir()}/Library/<feature>/<test-name>/pumpstation-<runId12>.html`.

For pipe-harness incremental traces the convention is
`${getTraceDir()}/<pipeline-component>/<ts>/<branch>/trace.json` (autogenesis-style).

## Five On-Disk Formats

The TPipe trace export is NOT a single format. There are five
distinct surfaces and they answer different questions:

| Format | Source | When to use | How to parse |
|---|---|---|---|
| **JSON** | `PipeTracer.exportAsJson` → `kotlinx.serialization.encodeToString(trace)` | Round-trippable, full schema, machine-readable | `json.loads()` directly — events are a flat array |
| **HTML** | `TraceVisualizer.generateHtmlReport(trace)` — five container-specific renderers | Human-readable report, has CSS class names per container | Line-oriented (one event per line, ~1500-1700 chars), regex with negated char class |
| **Markdown** | `TraceVisualizer.generateMarkdownOutput(trace)` | Lightweight postmortem, no JS dependency | Pipe-separated table rows |
| **Console** | `TraceVisualizer.generateConsoleOutput(trace)` | Streaming stdout | `[SUCCESS]/[FAILURE]/[INFO]` lines with metadata dump |
| **Lorebank `.bank`** | TPipe lorebook subsystem | In-character dialogue history for autogenesis/NPCs | `json.load()` then `converseHistory.history` array |

The JSON format is the canonical source. HTML is what humans open.
If you find yourself parsing HTML when you have a JSON equivalent,
stop — go back and find the JSON. The HTML class names change
between container renderers; the JSON field names do not.

## Five HTML Container Renderers — Class Namespace Cheat Sheet

`TraceVisualizer.generateHtmlReport` (TraceVisualizer.kt:333) sniffs
the first event prefix and routes to one of five sub-renderers.
Each has its own CSS class namespace. If you write a regex that
assumes the Standard namespace, you'll silently miss every PumpStation
event:

| Container | CSS class prefix | Event block selector | Token card selector |
|---|---|---|---|
| Standard | (default) | `.event-card` or `.trace-item` | n/a |
| Manifold | `.manifold-section` | `.event-card` | `.container > .summary-card:first-of-type` |
| Junction | `.junction-section` | `.event-card` | `.container > .summary-card:first-of-type` |
| Splitter | `.splitter-section` | `.event-card` | `.container > .summary-card:first-of-type` |
| DistributionGrid | `.grid-section` | `.event-card` | `.container > .summary-card:first-of-type` |
| PumpStation | `.ps-*` | `.ps-turn-card` | `.ps-ribbon-card` |

**Critical**: The PumpStation HTML uses `.ps-turn-card` (lower-cased
turn), not `.event-card`. The Standard/Manifold/Junction/Splitter/
DistributionGrid HTMLs all use `.event-card`. If you grep for
`.event-card` in a PumpStation trace, you'll find ZERO matches.

**Detection recipe** — sniff the HTML and pick the parser:

```python
def detect_container(html_path):
    html = open(html_path).read(200_000)  # 200KB is enough for detection
    if 'ps-turn-card' in html or 'PumpStation Trace' in html:
        return 'pumpstation'
    if 'splitter-section' in html or 'Splitter' in html[:5000]:
        return 'splitter'
    if 'manifold-section' in html or 'Manifold' in html[:5000]:
        return 'manifold'
    if 'junction-section' in html or 'Junction' in html[:5000]:
        return 'junction'
    if 'grid-section' in html or 'DistributionGrid' in html[:5000]:
        return 'distributiongrid'
    return 'standard'
```

## Single-Line HTML — The Catastrophic Backtracking Trap

**This is the single most common parsing failure.** TraceVisualizer
emits each event block as ONE HTML line, 1500-1700 chars typical.
A long PumpStation turn-card with 8 phases in it can be 6000+ chars
on one line.

```bash
# HANGS for 15-30 seconds — greedy `.` triggers catastrophic backtracking
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED.{0,900}" trace.html

# Returns in <100ms with identical match content
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED[^\"]{0,900}" trace.html
```

**Rule**: For ANY multi-line-extraction regex on TPipe HTML, use a
negated char class. Single quote `"` is safe — TraceVisualizer
renders HTML attributes with single quotes, and meta values never
contain single quotes in practice. Tested at N=900, runs in <100ms.

For N > 1500 you may need to bump the upper bound; for N < 50 this
is unneeded. The break-even where the negated class beats the
greedy `.` is right around N=200.

## Token Counts — The Source Taxonomy

This is the section that fixes the "garbage token totals" problem.

There are SEVEN distinct sources of token-like data in a TPipe trace
and they have different semantics. A "trace-wide token total" that
just sums everything is wrong.

| Source | Field | Where it appears | What it measures | When to use it |
|---|---|---|---|---|
| `metadata.inputTokens` | int | `API_CALL_SUCCESS`, `CONTEXT_PREPARED`, `PIPE_START` (with fullPrompt) | Tokens sent to the LLM for THIS call | **PRIMARY** — sum per-call for actual spend |
| `metadata.outputTokens` | int | `API_CALL_SUCCESS`, `PIPE_START` | Tokens received from the LLM | **PRIMARY** — sum with inputTokens |
| `metadata.totalTokens` | int | `API_CALL_SUCCESS` | input + output | Use when inputTokens absent |
| `metadata.actualInputTokens` | int | `CONTEXT_PREPARED` (autogenesis-style) | Real reported input tokens (not estimated) | **PRIMARY** if present — replaces inputTokens |
| `metadata.responseLength` | int | `API_CALL_SUCCESS` | **CHARACTER count, NOT tokens** | NEV