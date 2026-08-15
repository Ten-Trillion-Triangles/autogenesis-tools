#!/usr/bin/env python3
"""
TPipe JSON Trace Parser — accurate, type-preserving.

Trace JSON files are List[TraceEvent] serialized via kotlinx-serialization with the
MapAnySerializer custom serializer. Each event has:

    {
        "id": "trace-event-NNN",
        "timestamp": 1784845644440,
        "pipeId": "uuid",
        "pipeName": "judge",
        "eventType": "PUMP_STATION_JUDGE_COMPLETED",
        "phase": "EXECUTION",
        "content": { "text": "...", "binaryContent": [], ... } | null,
        "contextSnapshot": {...} | null,
        "metadata": {"key": value, ...}    // NOTE: MapAnySerializer deserializes
                                            //       nested maps/lists as objects/arrays
                                            //       but FLATTENS scalars to their type
        "error": "<Throwable.message>"      // @Transient — never serialized
    }

The metadata map may contain nested structures (Map<String, Any>). All token fields
appear as plain integers; complex fields like `pipelineDetails` are nested dicts.

Usage:
    python3 parse_json_trace.py --input trace.json --output parsed.json
    python3 parse_json_trace.py --input trace.json --format tokens       # token totals only
    python3 parse_json_trace.py --input trace.json --format per_pipe     # per-pipe aggregates
    python3 parse_json_trace.py --input trace.json --format events       # simplified events
"""
import argparse
import json
import os
import sys
from collections import OrderedDict, defaultdict


# ---------------------------------------------------------------------------
# Token-aware parsing
# ---------------------------------------------------------------------------

# TOKEN keys (counted as token spend; semantically equivalent to LLM tokens)
_TOKEN_KEYS = (
    "inputTokens", "outputTokens", "totalTokens",
    "actualInputTokens", "reasoningTokens",
    "totalInputTokens", "totalOutputTokens",
)

# LENGTH keys (character lengths of prompts/responses; NOT tokens)
# Reported separately so callers don't conflate them with token spend.
_LENGTH_KEYS = (
    "responseLength", "reasoningLength",
    "promptLength", "resultLength", "resultTextLength",
)


def _coerce_int(v):
    """Coerce a value to int when possible. Returns None otherwise."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except (ValueError, TypeError):
            return None
    return None


def _to_str(v):
    """Stringify non-trivial values; pass through primitives."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return json.dumps(v, default=str)


def extract_tokens_from_event(event):
    """Pull token + length counts out of one event's metadata."""
    meta = event.get("metadata") or {}
    out = OrderedDict()
    for k in _TOKEN_KEYS:
        if k in meta:
            v = _coerce_int(meta[k])
            if v is not None:
                out[k] = v
    return out


def extract_lengths_from_event(event):
    """Pull character-length fields out of one event's metadata (NOT tokens)."""
    meta = event.get("metadata") or {}
    out = OrderedDict()
    for k in _LENGTH_KEYS:
        if k in meta:
            v = _coerce_int(meta[k])
            if v is not None:
                out[k] = v
    return out


def aggregate_tokens(events):
    """Sum token counts by key across all events.

    Returns OrderedDict[tokenKey → {"total": N, "count": N}].
    """
    totals = OrderedDict((k, {"total": 0, "count": 0}) for k in _TOKEN_KEYS)
    for ev in events:
        per_event = extract_tokens_from_event(ev)
        for k, v in per_event.items():
            totals[k]["total"] += v
            totals[k]["count"] += 1
    return {k: v for k, v in totals.items() if v["count"] > 0}


def aggregate_lengths(events):
    """Sum character-length counts by key across all events.

    Returns OrderedDict[lengthKey → {"total": N, "count": N}].
    """
    totals = OrderedDict((k, {"total": 0, "count": 0}) for k in _LENGTH_KEYS)
    for ev in events:
        per_event = extract_lengths_from_event(ev)
        for k, v in per_event.items():
            totals[k]["total"] += v
            totals[k]["count"] += 1
    return {k: v for k, v in totals.items() if v["count"] > 0}


def aggregate_per_pipe(events):
    """Aggregate event count + tokens per pipeName."""
    buckets = defaultdict(lambda: {
        "event_count": 0,
        "event_types": set(),
        "tokens": defaultdict(int),
    })
    for ev in events:
        pipe = ev.get("pipeName", "<unknown>")
        b = buckets[pipe]
        b["event_count"] += 1
        b["event_types"].add(ev.get("eventType", ""))
        for k, v in extract_tokens_from_event(ev).items():
            b["tokens"][k] += v
    out = OrderedDict()
    for pipe, b in sorted(buckets.items()):
        out[pipe] = {
            "event_count": b["event_count"],
            "event_types": sorted(b["event_types"]),
            "tokens": dict(b["tokens"]),
        }
    return out


def aggregate_per_event_type(events):
    """Aggregate per eventType."""
    buckets = defaultdict(lambda: {
        "count": 0,
        "pipes": set(),
        "tokens": defaultdict(int),
    })
    for ev in events:
        et = ev.get("eventType", "<unknown>")
        b = buckets[et]
        b["count"] += 1
        b["pipes"].add(ev.get("pipeName", ""))
        for k, v in extract_tokens_from_event(ev).items():
            b["tokens"][k] += v
    out = OrderedDict()
    for et, b in sorted(buckets.items()):
        out[et] = {
            "count": b["count"],
            "pipes": sorted(b["pipes"]),
            "tokens": dict(b["tokens"]),
        }
    return out


# ---------------------------------------------------------------------------
# Simplified event view (for downstream consumers that don't need raw content)
# ---------------------------------------------------------------------------

def simplify_event(event, *, max_metadata_str=200, max_content_str=200):
    """Compact event shape preserving token-relevant fields without verbose content."""
    out = OrderedDict()
    for k in ("id", "timestamp", "pipeId", "pipeName", "eventType", "phase"):
        out[k] = event.get(k)

    meta = event.get("metadata") or {}
    if isinstance(meta, dict):
        out["metadata"] = {
            k: (v if not isinstance(v, str) or len(v) <= max_metadata_str
                else v[:max_metadata_str] + "...")
            for k, v in meta.items()
        }

    content = event.get("content")
    if isinstance(content, dict):
        # Only preserve text/reasoning previews; drop binaryContent
        compact = {}
        for k, v in content.items():
            if k in ("binaryContent", "miniBankContext", "tools"):
                compact[k] = f"<{type(v).__name__} omitted>"
            elif isinstance(v, str) and len(v) > max_content_str:
                compact[k] = v[:max_content_str] + "..."
            else:
                compact[k] = v
        out["content"] = compact
    elif content is not None:
        out["content"] = content

    if event.get("error"):
        out["error"] = event["error"]
    return out


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

def parse_json(path):
    with open(path) as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "events" in raw:
        events = raw["events"]
        metadata = {k: v for k, v in raw.items() if k != "events"}
    elif isinstance(raw, list):
        events = raw
        metadata = {}
    else:
        raise ValueError(f"unexpected JSON root type: {type(raw).__name__}")

    return {
        "path": str(path),
        "format": "json",
        "wrapper_metadata": metadata,
        "events": events,
        "event_count": len(events),
        "token_totals": aggregate_tokens(events),
        "length_totals": aggregate_lengths(events),
        "per_pipe": aggregate_per_pipe(events),
        "per_event_type": aggregate_per_event_type(events),
    }


# ---------------------------------------------------------------------------
# Format-specific outputs
# ---------------------------------------------------------------------------

def render_tokens(parsed):
    out = OrderedDict()
    out["path"] = parsed["path"]
    out["event_count"] = parsed["event_count"]
    out["token_totals"] = parsed["token_totals"]
    return out


def render_per_pipe(parsed):
    return parsed["per_pipe"]


def render_per_event_type(parsed):
    return parsed["per_event_type"]


def render_events(parsed, *, max_metadata_str=200, max_content_str=200):
    return [simplify_event(e,
                           max_metadata_str=max_metadata_str,
                           max_content_str=max_content_str)
            for e in parsed["events"]]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="Path to *.json trace file")
    ap.add_argument("--output", help="Write JSON to this path (default: stdout)")
    ap.add_argument("--format", choices=["full", "tokens", "tokens_and_lengths", "per_pipe", "per_event_type", "events"],
                    default="full", help="Output shape (default: full)")
    ap.add_argument("--max-metadata-str", type=int, default=200,
                    help="Truncate long metadata string values (default: 200)")
    ap.add_argument("--max-content-str", type=int, default=200,
                    help="Truncate long content string values (default: 200)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    parsed = parse_json(args.input)

    if args.format == "tokens":
        out = render_tokens(parsed)
    elif args.format == "tokens_and_lengths":
        out = OrderedDict([
            ("path", parsed["path"]),
            ("event_count", parsed["event_count"]),
            ("token_totals", parsed["token_totals"]),
            ("length_totals", parsed["length_totals"]),
        ])
    elif args.format == "per_pipe":
        out = render_per_pipe(parsed)
    elif args.format == "per_event_type":
        out = render_per_event_type(parsed)
    elif args.format == "events":
        out = render_events(parsed,
                            max_metadata_str=args.max_metadata_str,
                            max_content_str=args.max_content_str)
    else:
        out = parsed

    if args.output:
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2, default=str)
        if not args.quiet:
            print(f"Wrote {parsed['event_count']} events to {args.output}",
                  file=sys.stderr)
    else:
        json.dump(out, sys.stdout, indent=2, default=str)
        print()


if __name__ == "__main__":
    main()