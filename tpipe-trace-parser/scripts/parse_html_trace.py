#!/usr/bin/env python3
"""
TPipe HTML Trace Parser — accurate, format-aware.

Handles every container HTML format emitted by TraceVisualizer.kt:

    STANDARD_PIPELINE_HTML  (Pipe/Pipeline trace, generateStandardHtmlReport)
        <table id="trace-details-table"> with rows
        <tr id="trace-event-N" class="trace-item" data-pipe="PIPE_NAME">
        Cells: time | pipe | eventType | phase | status | metadata
        Metadata cell uses <strong>key:</strong> <span style="color: ...">value</span><br>
        Content blocks (input/output/prompt) inside <details><summary>📥 Input Content (N chars)</summary><pre>...</pre></details>

    PUMP_STATION_HTML  (generatePumpStationHtmlReport)
        Per-turn accordion: <details class='ps-turn-card'>
        Per-event row inside: <div class='ps-detail-row'>
        Label + type:  <div class='ps-detail-label'>LABEL<span class='ps-detail-type'>(TYPE)</span></div>
        Meta pairs:    <div class='ps-meta-row'><span class='ps-meta-key'>KEY</span><span class='ps-meta-val'>VAL</span></div>
        Content blocks (contentPreview / ps-event-extras / ps-event-text)

Usage:
    python3 parse_html_trace.py --input trace.html --output parsed.json
    python3 parse_html_trace.py --input trace.html --format tokens          # token totals only
    python3 parse_html_trace.py --input trace.html --format timeline        # chronosorted events
    cat trace.html | python3 parse_html_trace.py --stdin --format summary --quiet

Output JSON shape:
    {
        "path": "...",
        "format": "standard_pipeline|pumpstation|manifold|junction|splitter|distribution_grid|unknown",
        "run_status": "completed|failed|...",
        "run_id": "...",
        "token_totals": {"inputTokens": N, "outputTokens": N, "totalTokens": N, ...},
        "events": [
            {"id", "timeMs", "pipeName", "eventType", "phase", "status",
             "metadata": {key: value, ...}, "content_blocks": [{label, text}, ...]}
        ],
        "event_count": N
    }
"""
import argparse
import json
import re
import sys
from collections import OrderedDict
from html import unescape


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(html):
    """Identify which TraceVisualizer generator produced this HTML."""
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
    # Last resort: event-card divs indicate Layout B (Junction/Manifold/DistributionGrid)
    if "event-header" in html and "event-badge" in html:
        # Heuristic: DistributionGrid uses registry nodes, Junction uses round/workflow
        if "registry" in html.lower() or "peer-handoff" in html.lower() or "DISTRIBUTION_GRID" in html:
            return "distribution_grid"
        if "round" in html.lower() or "JUNCTION" in html:
            return "junction"
        return "manifold"
    return "unknown"


# ---------------------------------------------------------------------------
# Standard pipeline / container HTML (rows in <table id="trace-details-table">)
# ---------------------------------------------------------------------------

_STD_ROW_RE = re.compile(
    r'<(?:tr|div|article)\s+id=["\']trace-event-(\d+)["\']\s+class=["\']trace-item(?:\s+event-card)?\s*[^"\']*["\']\s+data-pipe=["\']([^"\']+)["\']\s*>(.*?)</(?:tr|div|article)>',
    re.DOTALL,
)

_STD_CELL_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.DOTALL)

# Layout B (Junction/Manifold/DistributionGrid): <div|article|tr ...trace-item...>
# Uses <header><span class='event-time'>+Xms</span><span class='event-badge STATUS'>LABEL</span><span class='phase-pill'>PHASE</span><span class='node-tag'>PIPE</span></header>
# Metadata is in <section class='event-section'><h4>Metadata</h4><div class='metadata-grid'>...
_EVENT_TIME_RE = re.compile(r"<span class=['\"]event-time['\"]>([^<]+)</span>")
_EVENT_BADGE_RE = re.compile(r"<span class=['\"]event-badge\s+(\w+)['\"]>(?:<span[^>]*>[^<]*</span>)?([^<]+)</span>")
_PHASE_PILL_RE = re.compile(r"<span class=['\"]phase-pill['\"]>([^<]+)</span>")
_NODE_TAG_RE = re.compile(r"<span class=['\"]node-tag['\"]>([^<]+)</span>")

# Metadata item (Layout B): <div class="metadata-item"><strong>key</strong><span>value</span></div>
_B_META_ITEM_RE = re.compile(
    r"<div class=['\"]metadata-item['\"]>\s*<strong>([^<]+)</strong>\s*<span>([^<]*)</span>\s*</div>",
    re.DOTALL,
)
_B_METADATA_GRID_RE = re.compile(
    r"<div class=['\"]metadata-grid['\"]>(.*?)</div>\s*(?:</section>|<section|</article>)",
    re.DOTALL,
)

# Metadata pair (Layout A — standard pipeline rows): <strong>key:</strong> value<br>
_STD_META_PAIR_RE = re.compile(
    r"<strong>([^<]+):</strong>\s*(?:<span[^>]*>)?([^<]*)",
    re.DOTALL,
)

# Content block (Layout A): <details><summary>📥 Input Content</summary><pre>...</pre></details>
_STD_DETAILS_RE = re.compile(
    r"<details[^>]*>\s*<summary[^>]*>(.*?)</summary>\s*<pre[^>]*>(.*?)</pre>\s*</details>",
    re.DOTALL,
)


def _strip_to_text(s):
    """Strip remaining HTML tags + unescape entities + collapse whitespace."""
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _classify_status(class_attr):
    """'class=\"info\"' → 'INFO'; 'class=\"success\"' → 'SUCCESS'."""
    if not class_attr:
        return "UNKNOWN"
    if "success" in class_attr:
        return "SUCCESS"
    if "failure" in class_attr:
        return "FAILURE"
    if "info" in class_attr:
        return "INFO"
    if "warning" in class_attr:
        return "WARNING"
    return "UNKNOWN"


def _parse_status_from_text(text):
    """'✅ SUCCESS' → 'SUCCESS'."""
    text = text.strip()
    for label in ("SUCCESS", "FAILURE", "INFO", "WARNING"):
        if label in text:
            return label
    return "UNKNOWN"


def _parse_standard_metadata(cell_html):
    """Extract structured metadata from a standard-pipeline metadata cell.

    Returns (meta_dict, content_blocks).
    """
    meta = OrderedDict()
    # Split on <br> so each <strong>key:</strong> value captures its own value (not the next one's)
    segments = re.split(r"<br\s*/?>", cell_html)
    for seg in segments:
        m = _STD_META_PAIR_RE.search(seg)
        if not m:
            continue
        key = m.group(1).strip()
        val = _strip_to_text(m.group(2)).strip()
        if key and val and val != "-":
            meta[key] = val

    # Content blocks (📥 Input Content / 📤 Output Content / 📝 Full Prompt / ✨ Generated Content / 📦 Request Object / 🧠 reasoningContent)
    blocks = []
    for dm in _STD_DETAILS_RE.finditer(cell_html):
        summary = _strip_to_text(dm.group(1))
        text = _strip_to_text(dm.group(2))
        if text:
            blocks.append({"label": summary, "text": text})
    return meta, blocks


def _parse_layout_b(body):
    """Parse a Junction/Manifold/DistributionGrid container event (Layout B).

    Layout B uses:
        <header class="event-header">
            <span class="event-time">+0ms</span>
            <span class="event-badge info"><span class="badge-icon">ℹ️</span>label</span>
            <span class="phase-pill">Phase</span>
            <span class="node-tag">PipeName</span>
        </header>
        <div class="event-body">
            <section class="event-section"><h4>Metadata</h4>
                <div class="metadata-grid">
                    <div class="metadata-item"><strong>key</strong><span>val</span></div>
                    ...
                </div>
            </section>
            <section class="event-section"><h4>Content &amp; Context</h4>
                ...
            </section>
        </div>
    """
    # Time
    time_str = ""
    m = _EVENT_TIME_RE.search(body)
    if m:
        time_str = m.group(1).strip()
    time_match = re.search(r"(\d+)\s*ms", time_str)
    time_ms = int(time_match.group(1)) if time_match else 0

    # Status from event-badge class
    status = "UNKNOWN"
    label = ""
    m = _EVENT_BADGE_RE.search(body)
    if m:
        status = m.group(1).lower()
        if status == "info":
            status = "INFO"
        elif status == "success":
            status = "SUCCESS"
        elif status == "failure":
            status = "FAILURE"
        elif status == "warning":
            status = "WARNING"
        label = _strip_to_text(m.group(2)).strip()

    # Phase
    phase = ""
    m = _PHASE_PILL_RE.search(body)
    if m:
        phase = _strip_to_text(m.group(1)).strip()

    # Pipe name from node-tag (falls back to caller-provided data_pipe)
    pipe_name = ""
    m = _NODE_TAG_RE.search(body)
    if m:
        pipe_name = _strip_to_text(m.group(1)).strip()

    # Metadata from metadata-grid
    meta = OrderedDict()
    grid_m = _B_METADATA_GRID_RE.search(body)
    if grid_m:
        for km, vm in _B_META_ITEM_RE.findall(grid_m.group(1)):
            key = km.strip()
            val = _strip_to_text(vm).strip()
            if key and val:
                meta[key] = val

    # Content blocks: <pre>...</pre> inside event-body
    blocks = []
    for em in re.finditer(r"<pre[^>]*>(.*?)</pre>", body, re.DOTALL):
        text = _strip_to_text(em.group(1))
        if text:
            blocks.append({"label": "Content", "text": text})

    return {
        "timeMs": time_ms,
        "timeDisplay": time_str,
        "pipeName": pipe_name,
        "eventType": label.upper().replace(" ", "_") if label else "",
        "phase": phase,
        "status": status,
        "metadata": meta,
        "contentBlocks": blocks,
    }


def _parse_layout_a(body, data_pipe):
    """Parse a standard pipeline row (Layout A — <tr>...</tr> with <td> cells)."""
    cells = _STD_CELL_RE.findall(body)
    if len(cells) < 6:
        return None

    time_str = _strip_to_text(cells[0][1])
    time_match = re.search(r"(\d+)\s*ms", time_str)
    time_ms = int(time_match.group(1)) if time_match else 0

    pipe_name = _strip_to_text(cells[1][1])
    event_type = _strip_to_text(cells[2][1])
    phase = _strip_to_text(cells[3][1])
    status_class = cells[4][0]
    status_text = cells[4][1]
    status = _classify_status(status_class) if status_class else _parse_status_from_text(status_text)

    meta, blocks = _parse_standard_metadata(cells[5][1])

    return {
        "timeMs": time_ms,
        "timeDisplay": time_str,
        "pipeName": pipe_name or data_pipe,
        "eventType": event_type,
        "phase": phase,
        "status": status,
        "metadata": meta,
        "contentBlocks": blocks,
    }


def _parse_standard_row(row_html):
    """Parse one row, dispatching to Layout A (table) or Layout B (article/div with event-card)."""
    row_m = _STD_ROW_RE.match(row_html)
    if not row_m:
        return None
    event_id = "trace-event-" + row_m.group(1)
    data_pipe = row_m.group(2)
    body = row_m.group(3)

    # Layout B: <header class="event-header">...</header> or class contains 'event-card'
    is_layout_b = ("event-header" in body) or ("event-card" in row_html[:200])

    if is_layout_b:
        parsed = _parse_layout_b(body)
    else:
        parsed = _parse_layout_a(body, data_pipe)

    if not parsed:
        return None

    return {
        "id": event_id,
        **parsed,
    }


def _parse_standard_pipeline(html):
    """Extract all rows from a standard-pipeline HTML trace."""
    rows = _STD_ROW_RE.findall(html)
    events = []
    for _id, _pipe, body in rows:
        full_row = _STD_ROW_RE.pattern  # placeholder
    # Re-match by iterating with the same pattern as _parse_standard_row expects
    events = []
    for m in _STD_ROW_RE.finditer(html):
        full_row = m.group(0)
        ev = _parse_standard_row(full_row)
        if ev:
            events.append(ev)
    return events


# ---------------------------------------------------------------------------
# PumpStation HTML (turn-card accordions with ps-detail-label rows)
# ---------------------------------------------------------------------------

_PS_EVENT_RE = re.compile(
    r"<div class=['\"]ps-detail-label['\"]>([^<]+)<span class=['\"]ps-detail-type['\"]>\(([^)]+)\)</span></div>(.*?)(?=<div class=['\"]ps-detail-label['\"]|</body>)",
    re.DOTALL,
)

_PS_META_RE = re.compile(
    r"<span class=['\"]ps-meta-key['\"]>([^<]+)</span><span class=['\"]ps-meta-val['\"]>([^<]*)</span>",
    re.DOTALL,
)

# Envelope rows: nested-map children rendered by TraceVisualizer as
#   <div class='ps-meta-row ps-meta-row-envelope'>
#     <span class='ps-meta-key'>&nbsp;&nbsp;parent.child:</span><span class='ps-meta-val'>val</span>
#   </div>
# The parent renders as
#   <div class='ps-meta-row'>
#     <span class='ps-meta-key'>parent:</span><span class='ps-meta-val'>{envelope: N field(s)}</span>
#   </div>
# We must collect these and assemble a nested dict under parent.
_PS_ENVELOPE_ROW_RE = re.compile(
    r"<div class=['\"]ps-meta-row\s+ps-meta-row-envelope['\"]>\s*"
    r"<span class=['\"]ps-meta-key['\"]>(&nbsp;)*([^<]+)</span>\s*"
    r"<span class=['\"]ps-meta-val['\"]>([^<]*)</span>\s*</div>",
    re.DOTALL,
)
_PS_PARENT_PLACEHOLDER_RE = re.compile(
    r"<div class=['\"]ps-meta-row['\"]>\s*"
    r"<span class=['\"]ps-meta-key['\"]>([^<]+):</span>\s*"
    r"<span class=['\"]ps-meta-val['\"]>\{envelope:[^}]*\}</span>\s*</div>",
    re.DOTALL,
)

_PS_TEXT_RE = re.compile(
    r"<pre class=['\"]ps-event-text['\"]>(.*?)</pre>", re.DOTALL
)

_PS_EXTRAS_RE = re.compile(
    r"<details class=['\"]ps-event-extras['\"]>.*?<summary[^>]*>(.*?)</summary>(.*?)</details>",
    re.DOTALL,
)

_PS_RUN_ID_RE = re.compile(r"<span class=['\"]ps-run-id['\"]>(ps-[\w\-]+)</span>")
_PS_TITLE_RUN_ID_RE = re.compile(r"<title>[^<]*?(ps-[\w\-]+)</title>")
_PS_STATUS_RE = re.compile(r"class=['\"]ps-status\s+ps-status-(\w+)['\"]")
_PS_TURN_NUM_RE = re.compile(r"<span class=['\"]ps-turn-num['\"]>Turn\s+(\d+)</span>")


def _parse_pumpstation_meta(body, event_type=None):
    """Parse the metadata block of a PumpStation event.

    Handles two layouts:
      1. Flat rows: <div class='ps-meta-row'>
                      <span class='ps-meta-key'>key:</span><span class='ps-meta-val'>val</span>
                   </div>
      2. Envelope rows: <div class='ps-meta-row ps-meta-row-envelope'>
                         <span class='ps-meta-key'>&nbsp;&nbsp;parent.child:</span>
                         <span class='ps-meta-val'>val</span>
                      </div>
         The parent renders as <div class='ps-meta-row'> with a placeholder
         <span class='ps-meta-val'>{envelope: N field(s)}</span> which we drop —
         the actual data is in the envelope children.
    """
    meta = OrderedDict()

    # 1. Capture envelope children BEFORE stripping them (they hold the
    #    actual nested-map data). Strip the envelope parent placeholder
    #    rows first so they don't get re-captured by the flat-row regex.
    cleaned = _PS_PARENT_PLACEHOLDER_RE.sub("", body)

    # 2. Capture envelope children FIRST — they need parent-prefix awareness.
    #    Format: <div class='ps-meta-row ps-meta-row-envelope'>...<span>parent.child:</span>...val...</div>
    envelopes = OrderedDict()  # parent_name -> OrderedDict of children
    for m in _PS_ENVELOPE_ROW_RE.finditer(body):
        nbsp_prefix = m.group(1) or ""
        dotted_key = m.group(2).strip()
        val = _strip_to_text(m.group(3))
        if not nbsp_prefix or not dotted_key or not val:
            continue
        # dotted_key looks like "parent.child"; split on first dot only.
        if "." in dotted_key:
            parent, child = dotted_key.split(".", 1)
            parent = parent.rstrip(":").strip()
            child = child.rstrip(":").strip()
            envelopes.setdefault(parent, OrderedDict())[child] = val
        else:
            # Envelope child without dot prefix → treat as flat under envelope_root
            key = dotted_key.rstrip(":").strip()
            envelopes.setdefault("__envelope_root__", OrderedDict())[key] = val

    # 3. Capture flat rows from the cleaned body. The envelope parent
    #    placeholder rows have been stripped in step 1. The envelope
    #    children rows are also stripped here so the flat-row regex doesn't
    #    re-capture them as garbage &nbsp;&nbsp;-prefixed keys.
    cleaned = _PS_ENVELOPE_ROW_RE.sub("", cleaned)
    for m_meta in _PS_META_RE.finditer(cleaned):
        key = m_meta.group(1).rstrip(":").strip()
        val = _strip_to_text(m_meta.group(2))
        if key and val:
            # If a parent placeholder already accumulated children, merge them.
            if key in envelopes:
                envelopes[key]["_envelope_meta"] = val
                # If the placeholder carried a real value (not the {envelope: N} pattern),
                # the meta dict for this event already had it. Don't overwrite.
            else:
                meta[key] = val

    # 4. Splice envelope children into meta as nested dicts.
    for parent, children in envelopes.items():
        if parent == "__envelope_root__":
            # No parent key was found; fall back to flat dotted keys.
            for ck, cv in children.items():
                meta[ck] = cv
        else:
            nested = OrderedDict()
            for ck, cv in children.items():
                if ck == "_envelope_meta":
                    continue
                nested[ck] = cv
            # If the parent also has flat metadata under its key (rare), merge:
            if parent in meta:
                # The flat value was likely the envelope placeholder; nest the real children.
                nested_dict = OrderedDict()
                nested_dict.update(nested)
                meta[parent] = nested_dict
            else:
                meta[parent] = nested

    return meta


def _parse_pumpstation_events(html):
    """Extract every event row from a PumpStation HTML trace."""
    events = []
    for m in _PS_EVENT_RE.finditer(html):
        label = _strip_to_text(m.group(1))
        event_type = m.group(2).strip()
        body = m.group(3)

        meta = _parse_pumpstation_meta(body)

        blocks = []
        for em in _PS_EXTRAS_RE.finditer(body):
            summary = _strip_to_text(em.group(1))
            inner_body = em.group(2)
            text_matches = _PS_TEXT_RE.findall(inner_body)
            text = "\n---\n".join(_strip_to_text(t) for t in text_matches) if text_matches else _strip_to_text(inner_body)
            if text:
                blocks.append({"label": summary, "text": text})

        # turnIndex: read from <div class='ps-turn-num'>N</div> BEFORE this event block in the HTML
        # Heuristic: find the most recent ps-turn-num before this event's position
        preceding = html[: m.start()]
        tn_matches = _PS_TURN_NUM_RE.findall(preceding)
        turn_index = int(tn_matches[-1]) if tn_matches else None

        events.append({
            "id": None,
            "timeMs": None,
            "pipeName": "PumpStation",
            "eventType": event_type,
            "phase": meta.get("phase"),
            "status": _status_from_event_type(event_type),
            "turnIndex": turn_index,
            "metadata": meta,
            "contentBlocks": blocks,
            "label": label,
        })
    return events


def _status_from_event_type(event_type):
    if "FAILED" in event_type or "TRIPPED" in event_type or "BLOWOUT" in event_type:
        return "FAILURE"
    if "COMPLETED" in event_type or "STARTED" in event_type or "REVEALED" in event_type or "APPLIED" in event_type:
        return "SUCCESS"
    return "INFO"


# ---------------------------------------------------------------------------
# Token totals (works on BOTH formats)
# ---------------------------------------------------------------------------

_TOKEN_KEYS = (
    "inputTokens", "outputTokens", "totalTokens",
    "actualInputTokens", "reasoningTokens",
    "totalInputTokens", "totalOutputTokens",
)

_LENGTH_KEYS = (
    "responseLength", "reasoningLength",
    "promptLength", "resultLength", "resultTextLength",
)


def extract_token_totals(html):
    """Sum token counts by key across ALL events in an HTML trace.

    Pattern A (standard pipeline):
        <strong>inputTokens:</strong> <span style="color: ...">1705</span>
    Pattern B (pumpstation):
        <span class='ps-meta-key'>inputTokens</span><span class='ps-meta-val'>1928</span>
    """
    totals = OrderedDict((k, 0) for k in _TOKEN_KEYS)
    counts = OrderedDict((k, 0) for k in _TOKEN_KEYS)

    # Pattern A: bold-then-span (standard pipeline)
    for m in re.finditer(
        r"<strong>([a-zA-Z]+):</strong>\s*<span[^>]*>(\d+)</span>", html
    ):
        key = m.group(1)
        val = int(m.group(2))
        if key in totals:
            totals[key] += val
            counts[key] += 1

    # Pattern B: pumpstation meta-key/meta-val
    for m in re.finditer(
        r"<span class=['\"]ps-meta-key['\"]>([a-zA-Z]+):?</span><span class=['\"]ps-meta-val['\"]>(\d+)</span>",
        html,
    ):
        key = m.group(1)
        val = int(m.group(2))
        if key in totals:
            totals[key] += val
            counts[key] += 1

    # Drop zero/zero-count keys
    result = OrderedDict()
    for k in _TOKEN_KEYS:
        if counts[k] > 0:
            result[k] = {"total": totals[k], "count": counts[k]}
    return result


def extract_length_totals(html):
    """Sum character-length fields (NOT tokens) across ALL events."""
    totals = OrderedDict((k, 0) for k in _LENGTH_KEYS)
    counts = OrderedDict((k, 0) for k in _LENGTH_KEYS)

    for m in re.finditer(
        r"<strong>([a-zA-Z]+):</strong>\s*<span[^>]*>(\d+)</span>", html
    ):
        key = m.group(1)
        val = int(m.group(2))
        if key in totals:
            totals[key] += val
            counts[key] += 1

    for m in re.finditer(
        r"<span class=['\"]ps-meta-key['\"]>([a-zA-Z]+):?</span><span class=['\"]ps-meta-val['\"]>(\d+)</span>",
        html,
    ):
        key = m.group(1)
        val = int(m.group(2))
        if key in totals:
            totals[key] += val
            counts[key] += 1

    result = OrderedDict()
    for k in _LENGTH_KEYS:
        if counts[k] > 0:
            result[k] = {"total": totals[k], "count": counts[k]}
    return result


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

def parse_html(path):
    with open(path) as f:
        html = f.read()

    fmt = detect_format(html)
    run_id = None
    run_status = None

    if fmt == "pumpstation":
        events = _parse_pumpstation_events(html)
        rid_match = _PS_RUN_ID_RE.search(html) or _PS_TITLE_RUN_ID_RE.search(html)
        if rid_match:
            run_id = rid_match.group(1)
        st_match = _PS_STATUS_RE.search(html)
        if st_match:
            run_status = st_match.group(1)
    else:
        events = _parse_standard_pipeline(html)

    token_totals = extract_token_totals(html)
    length_totals = extract_length_totals(html)

    return {
        "path": str(path),
        "format": fmt,
        "run_status": run_status,
        "run_id": run_id,
        "token_totals": token_totals,
        "length_totals": length_totals,
        "events": events,
        "event_count": len(events),
    }


# ---------------------------------------------------------------------------
# Format-specific outputs (--format tokens / timeline / summary)
# ---------------------------------------------------------------------------

def render_tokens(parsed):
    out = OrderedDict()
    out["path"] = parsed["path"]
    out["format"] = parsed["format"]
    out["token_totals"] = parsed.get("token_totals", {})
    out["length_totals"] = parsed.get("length_totals", {})
    return out


def render_timeline(parsed):
    """Chronological events with key metadata fields surfaced."""
    out = []
    for e in parsed["events"]:
        rec = OrderedDict()
        rec["eventType"] = e["eventType"]
        rec["pipeName"] = e["pipeName"]
        if e.get("timeMs") is not None:
            rec["timeMs"] = e["timeMs"]
        if e.get("turnIndex") is not None:
            rec["turnIndex"] = e["turnIndex"]
        if e["status"] != "UNKNOWN":
            rec["status"] = e["status"]
        # Surface token fields (NOT lengths — they're character counts)
        for tk in ("inputTokens", "outputTokens", "totalTokens",
                   "actualInputTokens", "reasoningTokens"):
            if tk in e["metadata"]:
                rec[tk] = e["metadata"][tk]
        # Surface path-related fields
        for fk in ("selectedPathName", "pathName", "riskLevel",
                   "approved", "isComplete", "shouldTerminate",
                   "warningCode", "exitReason", "reason", "judgeRunMode"):
            if fk in e["metadata"]:
                rec[fk] = e["metadata"][fk]
        out.append(rec)
    return out


def render_summary(parsed):
    """One-line-per-event, condensed."""
    out = []
    for e in parsed["events"]:
        bits = [f"{e['eventType']:50s}", f"{e['pipeName']:20s}", f"{e['status']:8s}"]
        if e.get("timeMs") is not None:
            bits.append(f"+{e['timeMs']:>5}ms")
        if e.get("turnIndex") is not None:
            bits.append(f"turn={e['turnIndex']}")
        for k in ("inputTokens", "outputTokens", "totalTokens"):
            if k in e["metadata"]:
                bits.append(f"{k}={e['metadata'][k]}")
        for k in ("selectedPathName", "pathName", "riskLevel",
                  "isComplete", "shouldTerminate", "approved", "exitReason"):
            v = e["metadata"].get(k)
            if v is not None:
                bits.append(f"{k}={v}")
        out.append(" ".join(bits))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", help="Path to a *.html trace file")
    ap.add_argument("--stdin", action="store_true", help="Read HTML from stdin")
    ap.add_argument("--output", help="Write JSON to this path (default: stdout)")
    ap.add_argument("--format", choices=["full", "tokens", "timeline", "summary"],
                    default="full", help="Output shape (default: full)")
    ap.add_argument("--quiet", action="store_true", help="Suppress summary stderr")
    args = ap.parse_args()

    if args.stdin:
        import tempfile
        html = sys.stdin.read()
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            tmp = f.name
        parsed = parse_html(tmp)
        parsed["path"] = "<stdin>"
    elif args.input:
        parsed = parse_html(args.input)
    else:
        ap.error("either --input or --stdin required")

    if args.format == "tokens":
        out = render_tokens(parsed)
    elif args.format == "timeline":
        out = render_timeline(parsed)
    elif args.format == "summary":
        out = render_summary(parsed)
    else:
        out = parsed

    if args.output:
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2, default=str)
        if not args.quiet:
            print(f"Wrote {parsed['event_count']} events to {args.output}",
                  file=sys.stderr)
    else:
        if args.format == "summary":
            print(out)
        else:
            json.dump(out, sys.stdout, indent=2, default=str)
            print()


if __name__ == "__main__":
    main()