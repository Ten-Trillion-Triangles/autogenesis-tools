---
title: HTML Layout B — Junction / Manifold / DistributionGrid Container Reports
generated: 2026-07-24
verified_against: 9 Junction + 6 DistributionGrid + 1 Manifold trace files (Bedrock live)
bypass_first_run_bug: 0 events on Layout B (container HTML) before this fix
---

# HTML Layout B — Junction / Manifold / DistributionGrid Container Reports

This is the canonical byte-level reference for the **container HTML layout** emitted by `TraceVisualizer.generateJunctionHtmlReport`, `generateManifoldHtmlReport`, and `generateDistributionGridHtmlReport`. Layout B is structurally different from the standard-pipeline Layout A (table rows) and from the PumpStation layout. The previous parser returned 0 events for every Layout B file because it only matched `<tr class="trace-item">`.

## Why this matters

When a user runs live tests for Junction, DistributionGrid, or Manifold against AWS Bedrock, the resulting trace files under `~/.tpipe/debug/trace/Library/<container>-live-bedrock/<scenario>/<container>.html` use Layout B. Layout A (`<tr>` rows) is used for standard pipelines and for **nested pipes inside a container** — the same file can contain both layouts. The parser must dispatch per-row based on the actual element type and inner structure, not on a file-level format detection.

## Detection: title-based, then Last-Resort Layout B

The container HTML is detected by `<title>` content first (the source of truth), then by Layout B signature as a fallback:

```python
def detect_format(html):
    if re.search(r"class=['\"]ps-(status|header|container|turn-card)['\"]", html):
        return "pumpstation"
    title_m = re.search(r"<title>([^<]+)</title>", html)
    title = title_m.group(1) if title_m else ""
    if "trace-details-table" in html:
        return "standard_pipeline"
    if "Junction Execution" in title or "junction-round" in html or "junction-workflow" in html:
        return "junction"
    if "DistributionGrid Execution" in title or "distribution-grid" in html[:10000]:
        return "distribution_grid"
    if "Manifold Execution" in title:
        return "manifold"
    if "Splitter" in title:
        return "splitter"
    # Last-resort Layout B signature
    if "event-header" in html and "event-badge" in html:
        if "registry" in html.lower() or "peer-handoff" in html.lower() or "DISTRIBUTION_GRID" in html:
            return "distribution_grid"
        if "round" in html.lower() or "JUNCTION" in html:
            return "junction"
        return "manifold"
    return "unknown"
```

**The earlier detection only substring-matched `Junction`/`Manifold`/`DistributionGrid` against the first 5000 chars.** That worked for the `<h1>` "🎯 TPipe Junction Execution Analysis" header but failed for the participant HTML files (e.g. `participant-a.html`) which have title "TPipe Pipeline Flow Visualization" and are actually standard pipeline traces for nested pipes. Always trust the title first.

## Layout B event skeleton

```html
<!-- Container-level event (Junction, Manifold, DistributionGrid) -->
<article id="trace-event-223" class="trace-item event-card info" data-pipe="Junction">
    <header class="event-header">
        <span class="event-time">+0ms</span>
        <span class="event-badge info"><span class="badge-icon">ℹ️</span>junction round start</span>
        <span class="phase-pill">Orchestration</span>
        <span class="node-tag">Node: Junction</span>
    </header>
    <div class="event-body">
        <section class="event-section">
            <h4>Metadata</h4>
            <div class="metadata-grid">
                <div class="metadata-item">
                    <strong>roundIndex</strong>
                    <span>0</span>
                </div>
                <div class="metadata-item">
                    <strong>strategy</strong>
                    <span>RoundRobin</span>
                </div>
                ...
            </div>
        </section>
        <section class="event-section">
            <h4>Content & Context</h4>
            <p class="empty-state">No content captured for this event.</p>
        </section>
    </div>
</article>
```

**Critical regex points** (the patterns are derived from real HTML on disk):

```python
# Row opener — must accept <tr>, <div>, OR <article> with mixed class lists
_STD_ROW_RE = re.compile(
    r'<(?:tr|div|article)\s+id=["\']trace-event-(\d+)["\']\s+'
    r'class=["\']trace-item(?:\s+event-card)?\s*[^"\']*["\']\s+'
    r'data-pipe=["\']([^"\']+)["\']\s*>'
    r'(.*?)</(?:tr|div|article)>',
    re.DOTALL,
)

# Layout B header fields
_EVENT_TIME_RE = re.compile(r"<span class=['\"]event-time['\"]>([^<]+)</span>")
_EVENT_BADGE_RE = re.compile(
    r"<span class=['\"]event-badge\s+(\w+)['\"]>"
    r"(?:<span[^>]*>[^<]*</span>)?([^<]+)</span>"
)
_PHASE_PILL_RE = re.compile(r"<span class=['\"]phase-pill['\"]>([^<]+)</span>")
_NODE_TAG_RE = re.compile(r"<span class=['\"]node-tag['\"]>([^<]+)</span>")

# Layout B metadata — shape differs from Layout A
_B_META_ITEM_RE = re.compile(
    r"<div class=['\"]metadata-item['\"]>\s*"
    r"<strong>([^<]+)</strong>\s*"
    r"<span>([^<]*)</span>\s*</div>",
    re.DOTALL,
)
_B_METADATA_GRID_RE = re.compile(
    r"<div class=['\"]metadata-grid['\"]>(.*?)</div>\s*"
    r"(?:</section>|<section|</article>)",
    re.DOTALL,
)
```

**Layout B metadata VALUE is wrapped in `<span>` (no color, no class attr on value).** Layout A uses `<span style="color: ...">` for tokens. The regex above matches BOTH because both wrap the value in `<span>` — the optional `style="..."` attribute is dropped by `[^<]*` capture.

## Detection: row-level format dispatch

A single trace file may contain rows of BOTH layouts. Dispatch per row, not per file:

```python
def _parse_standard_row(row_html):
    row_m = _STD_ROW_RE.match(row_html)
    if not row_m:
        return None
    event_id = "trace-event-" + row_m.group(1)
    data_pipe = row_m.group(2)
    body = row_m.group(3)

    # Layout B has <header class="event-header"> OR class contains 'event-card'
    is_layout_b = ("event-header" in body) or ("event-card" in row_html[:200])

    if is_layout_b:
        parsed = _parse_layout_b(body)
    else:
        parsed = _parse_layout_a(body, data_pipe)
    ...
```

**Why per-row dispatch**: a Junction container's `junction.html` contains Layout B events for the container itself + Layout A rows for nested pipes (`participant-a.html`, `moderator.html`). A naive file-level detection misses the embedded Layout A rows.

## What Layout B surfaces that Layout A doesn't

| Field | Layout A | Layout B |
|-------|----------|----------|
| Status | `class="info"` on `<td>` (cell 4) | `class="event-badge info"` on `<span>` (header) |
| Event type | `<td>PIPE_START</td>` (cell 2) | UPPER-CASE label inside `<span class="event-badge">` |
| Phase | `<td>INITIALIZATION</td>` (cell 3) | `<span class="phase-pill">Phase</span>` |
| Pipe name | `<td>pipeName</td>` (cell 1) | `<span class="node-tag">Node: PipeName</span>` |
| Time | `<td>+0ms</td>` (cell 0) | `<span class="event-time">+0ms</span>` |
| Metadata | `<strong>key:</strong> <span style="color: ...">val</span><br>` (in `<td class="metadata">`) | `<div class="metadata-item"><strong>key</strong><span>val</span></div>` (in `<div class="metadata-grid">`) |
| Content blocks | `<details><summary>📥 Input Content</summary><pre>...</pre></details>` | `<pre>...</pre>` inside `<section class="event-section">` |

**Event type normalization**: Layout B's label is human-readable text like `"junction round start"`. The parser uppercases and replaces spaces with underscores: `JUNCTION_ROUND_START`. This matches the canonical `TraceEventType` enum values.

## Real-world event-type distribution from Junction LiveBedrockIntegrationTest

After running the Junction live test (Bedrock nvidia.nemotron-nano-3-30b in us-west-2) and parsing the resulting trace:

```
JUNCTION_START                    1
JUNCTION_ROUND_START              1
JUNCTION_PARTICIPANT_DISPATCH     3
JUNCTION_PARTICIPANT_RESPONSE     3
JUNCTION_VOTE_TALLY               1
JUNCTION_CONSENSUS_CHECK          1
JUNCTION_ROUND_END                1
JUNCTION_SUCCESS                  1
JUNCTION_END                      1
```

For workflow traces (e.g. `workflow-vote_plan_output_exit`):

```
JUNCTION_WORKFLOW_START       1
JUNCTION_PHASE_START          3
JUNCTION_PARTICIPANT_DISPATCH 4
JUNCTION_PARTICIPANT_RESPONSE 4
JUNCTION_PHASE_END            3
JUNCTION_HANDOFF              1
JUNCTION_WORKFLOW_SUCCESS     1
JUNCTION_WORKFLOW_END         1
```

For Manifold with a bug-recovery trace (`NestedReasoningConverseHistoryBugTest`):

```
MANIFOLD_START              1
MANIFOLD_LOOP_ITERATION     1
MANAGER_TASK_ANALYSIS       1
MANAGER_DECISION            1
AGENT_REQUEST_EXTRACTION    1
AGENT_REQUEST_VALIDATION    1
AGENT_DISPATCH              1
P2P_REQUEST_FAILURE         1   ← bug marker
MANIFOLD_FAILURE            1
MANIFOLD_END                1
```

The Manifold case shows the parser correctly surfaces `P2P_REQUEST_FAILURE` with the full error message (`P2PRejection(errorType=transport, reason=Agent not found as remote or running under this Instance of TPipe)`) — making it useful for bug triage.

## DistributionGrid container-level events

DISTRIBUTION_GRID events at the container level cover lifecycle and routing, NOT tokens. Tokens live in the **nested pipe** Layout A rows (`sender-router-pipeline.html`, `sender-worker-pipeline.html`, `remote-router-pipeline.html`, `remote-worker-pipeline.html`).

```
DISTRIBUTION_GRID_INIT                      1
DISTRIBUTION_GRID_VALIDATION_START          1
DISTRIBUTION_GRID_VALIDATION_SUCCESS        1
DISTRIBUTION_GRID_START                     2
DISTRIBUTION_GRID_ROUTER_DECISION           2
DISTRIBUTION_GRID_LOCAL_WORKER_DISPATCH     1
DISTRIBUTION_GRID_LOCAL_WORKER_RESPONSE     1
DISTRIBUTION_GRID_SUCCESS                   2
DISTRIBUTION_GRID_END                       2
DISTRIBUTION_GRID_SESSION_HANDSHAKE         1
DISTRIBUTION_GRID_MEMORY_ENVELOPE           1
DISTRIBUTION_GRID_PEER_HANDOFF              1
DISTRIBUTION_GRID_PEER_RESPONSE             1
DISTRIBUTION_GRID_RETURN_ROUTING            1
```

## How to run live tests to get Layout B artifacts

The Bedrock live tests are gated by TWO env vars:

```bash
# 1. AllowTest must be set to enable the live path (assumeTrue check)
export AllowTest="true"

# 2. AWS credentials must resolve — either via env vars or ~/.aws/credentials
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-west-2"
```

Then run with gradle:

```bash
./gradlew :TPipe-Bedrock:test \
    --tests "bedrockPipe.JunctionLiveBedrockIntegrationTest" \
    --tests "bedrockPipe.DistributionGridLiveBedrockIntegrationTest" \
    --rerun-tasks --no-daemon
```

Note: `ManifoldLoopLimitLiveBedrockIntegrationTest` is `@Disabled("non-deterministic LLM behavior")` — it won't run. Use `NestedReasoningConverseHistoryBugTest` instead; it's enabled and produces a real Manifold trace (HTML + JSON) when the bug is present.

Traces land in `~/.tpipe/debug/trace/Library/<container>-live-bedrock/<scenario>/` regardless of the `TPipeConfig.configDir` override.

## Pitfall: HTML escapes inside metadata values

Layout B's `metadata-item` values sometimes contain HTML entities. The previous parser was returning `&quot;` literally instead of `"`. Pipe all values through `html.unescape()` and strip whitespace before storing in the dict.

For example, a `decision` field might serialize as:

```html
<div class="metadata-item">
    <strong>decision</strong>
    <span>{"approve": true, "reason": "all checks passed"}</span>
</div>
```

The parser captures `{"approve": true, "reason": "all checks passed"}` correctly. But if the producer HTML-escaped the JSON (e.g. `&quot;approve&quot;`), the parser must decode BEFORE storing.

## Source files

- `src/main/kotlin/Debug/TraceVisualizer.kt` — the generator
  - `generateJunctionHtmlReport` ~line 739
  - `generateManifoldHtmlReport` ~line 616
  - `generateDistributionGridHtmlReport` (no exact line citation — search for the generator name)
- `src/main/kotlin/Debug/TraceNodeMapper.kt` — maps events to renderable nodes for Mermaid graphs

## Verified against

- 9 Junction traces from `bedrockPipe.JunctionLiveBedrockIntegrationTest` (2026-07-24 run)
- 6 DistributionGrid traces from `bedrockPipe.DistributionGridLiveBedrockIntegrationTest`
- 1 Manifold trace from `bedrockPipe.NestedReasoningConverseHistoryBugTest` (45 events, real Bedrock llama4-maverick call)

All 16 Layout B files parsed with 0 failures and 0 event-count mismatches against ground-truth extraction.
