#!/usr/bin/env python3
"""
extract_pipeline.py — End-to-end trace triage tool.

Walks a directory of trace artifacts (*.html and/or *.json), parses every file,
and produces a single structured report covering:
  - Per-file event counts and formats detected
  - Aggregate token totals across ALL files (the single number operators care about)
  - Per-pipe aggregates (event count + tokens) when pipeName is meaningful
  - Per-event-type aggregates
  - Run status summary (for PumpStation)
  - JSON dump of every event with relevant metadata fields

Designed for "the operator ran 13 tests, 9 passed, what tokens actually spent?"
triage. Sub-200ms on the typical 20-file live-test run.

Usage:
    python3 extract_pipeline.py --dir ~/.tpipe/debug/trace/some-test
    python3 extract_pipeline.py --dir ... --output report.json
    python3 extract_pipeline.py --dir ... --quiet            # summary only to stderr
    python3 extract_pipeline.py --dir ... --filter pumpstation   # only pumpstation files
    python3 extract_pipeline.py --dir ... --tokens-only          # token totals only

Output (JSON):
    {
        "dir": "...",
        "files_scanned": N,
        "files_parsed": N,
        "files_failed": [{"path": "...", "error": "..."}],
        "format_breakdown": {"pumpstation": N, "standard_pipeline": N, "json": N, "unknown": N},
        "aggregate_token_totals": {"inputTokens": {"total": N, "count": N}, ...},
        "run_statuses": {"completed": N, "failed": N, ...},
        "per_file": [
            {"path": "...", "format": "...", "event_count": N,
             "run_id": "...", "run_status": "...",
             "token_totals": {...}, "events": [...]},
            ...
        ],
        "per_event_type": {...},
        "per_pipe": {...}
    }
"""
import argparse
import json
import os
import sys
from collections import OrderedDict, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Import the parsers as modules
import importlib.util

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_html_mod = _load_module("parse_html_trace", os.path.join(SCRIPT_DIR, "parse_html_trace.py"))
_json_mod = _load_module("parse_json_trace", os.path.join(SCRIPT_DIR, "parse_json_trace.py"))

parse_html = _html_mod.parse_html
parse_json = _json_mod.parse_json


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_traces(root, *, only=None):
    """Walk `root` recursively, return list of (path, kind) tuples.

    kind is 'html' or 'json' based on filename extension.
    only: optional filter ('pumpstation' | 'json' | 'standard_pipeline' | 'all')
    """
    found = []
    for parent, _, files in os.walk(root):
        for fn in sorted(files):
            full = os.path.join(parent, fn)
            if fn.endswith(".html"):
                # Quick format sniff on first 8KB
                try:
                    head = open(full).read(8000)
                except Exception:
                    continue
                fmt = "unknown"
                if 'ps-status' in head or 'ps-detail-label' in head:
                    fmt = "pumpstation"
                elif 'trace-details-table' in head:
                    fmt = "standard_pipeline"
                if only == "json":
                    continue
                if only and only != "all" and only != fmt:
                    continue
                found.append((full, "html", fmt))
            elif fn.endswith(".json"):
                if only and only not in ("json", "all"):
                    continue
                found.append((full, "json", "json"))
    return found


# ---------------------------------------------------------------------------
# Per-file parse with error capture
# ---------------------------------------------------------------------------

def parse_one(path, kind):
    if kind == "html":
        return parse_html(path)
    else:
        return parse_json(path)


def parse_many(files):
    """Parse every file. Return (parsed_list, failed_list)."""
    parsed = []
    failed = []
    for path, kind, _fmt_hint in files:
        try:
            p = parse_one(path, kind)
            p["_kind"] = kind
            parsed.append(p)
        except Exception as e:
            failed.append({"path": path, "kind": kind, "error": f"{type(e).__name__}: {e}"})
    return parsed, failed


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------

def _merge_token_totals(target, source):
    for k, v in source.items():
        if k not in target:
            target[k] = {"total": 0, "count": 0}
        target[k]["total"] += v["total"]
        target[k]["count"] += v["count"]


def aggregate_token_totals(parsed_list):
    out = OrderedDict()
    for p in parsed_list:
        _merge_token_totals(out, p.get("token_totals", {}))
    return out


def aggregate_per_pipe(parsed_list):
    """Merge per-pipe aggregates across all parsed files."""
    out = defaultdict(lambda: {"event_count": 0, "event_types": set(), "tokens": defaultdict(int)})
    for p in parsed_list:
        # Both HTML and JSON events have pipeName
        for e in p.get("events", []):
            pipe = e.get("pipeName", "<unknown>")
            b = out[pipe]
            b["event_count"] += 1
            et = e.get("eventType", "")
            if et:
                b["event_types"].add(et)
            # Token fields may live in metadata (HTML & JSON)
            meta = e.get("metadata") or {}
            for k in ("inputTokens", "outputTokens", "totalTokens",
                      "actualInputTokens", "reasoningTokens",
                      "totalInputTokens", "totalOutputTokens"):
                if k in meta:
                    try:
                        iv = int(meta[k])
                    except (ValueError, TypeError):
                        continue
                    b["tokens"][k] += iv
    # Convert
    res = OrderedDict()
    for pipe, b in sorted(out.items()):
        res[pipe] = {
            "event_count": b["event_count"],
            "event_types": sorted(b["event_types"]),
            "tokens": dict(b["tokens"]),
        }
    return res


def aggregate_per_event_type(parsed_list):
    out = defaultdict(lambda: {"count": 0, "pipes": set(), "tokens": defaultdict(int)})
    for p in parsed_list:
        for e in p.get("events", []):
            et = e.get("eventType", "<unknown>")
            b = out[et]
            b["count"] += 1
            b["pipes"].add(e.get("pipeName", ""))
            for k, v in (e.get("metadata") or {}).items():
                if k in ("inputTokens", "outputTokens", "totalTokens",
                         "actualInputTokens", "reasoningTokens",
                         "totalInputTokens", "totalOutputTokens"):
                    try:
                        iv = int(v)
                    except (ValueError, TypeError):
                        continue
                    b["tokens"][k] += iv
    res = OrderedDict()
    for et, b in sorted(out.items()):
        res[et] = {
            "count": b["count"],
            "pipes": sorted(b["pipes"]),
            "tokens": dict(b["tokens"]),
        }
    return res


def run_statuses(parsed_list):
    """Count run_status values (pumpstation only)."""
    out = defaultdict(int)
    for p in parsed_list:
        rs = p.get("run_status")
        if rs:
            out[rs] += 1
    return dict(out)


def format_breakdown(parsed_list):
    out = defaultdict(int)
    for p in parsed_list:
        out[p.get("format", "unknown")] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def build_report(root, parsed_list, failed_list):
    return OrderedDict([
        ("dir", str(root)),
        ("files_scanned", len(parsed_list) + len(failed_list)),
        ("files_parsed", len(parsed_list)),
        ("files_failed", failed_list),
        ("format_breakdown", format_breakdown(parsed_list)),
        ("run_statuses", run_statuses(parsed_list)),
        ("aggregate_token_totals", aggregate_token_totals(parsed_list)),
        ("per_event_type", aggregate_per_event_type(parsed_list)),
        ("per_pipe", aggregate_per_pipe(parsed_list)),
        ("per_file", [
            OrderedDict([
                ("path", p["path"]),
                ("format", p["format"]),
                ("event_count", p["event_count"]),
                ("run_id", p.get("run_id")),
                ("run_status", p.get("run_status")),
                ("token_totals", p.get("token_totals", {})),
                ("events", p["events"]),
            ])
            for p in parsed_list
        ]),
    ])


# ---------------------------------------------------------------------------
# Compact summary printer (for stderr)
# ---------------------------------------------------------------------------

def print_summary(report, stream=sys.stderr):
    dir_ = report["dir"]
    n = report["files_parsed"]
    print(f"=== extract_pipeline: {dir_} ===", file=stream)
    print(f"  files: scanned={report['files_scanned']} parsed={n} failed={len(report['files_failed'])}", file=stream)
    print(f"  formats: {report['format_breakdown']}", file=stream)
    if report["run_statuses"]:
        print(f"  run_statuses: {report['run_statuses']}", file=stream)
    tt = report["aggregate_token_totals"]
    if tt:
        print(f"  tokens (across all files):", file=stream)
        for k in ("inputTokens", "outputTokens", "totalTokens",
                  "actualInputTokens", "reasoningTokens"):
            if k in tt:
                v = tt[k]
                print(f"    {k:25s} total={v['total']:>7} count={v['count']}", file=stream)
    if report["files_failed"]:
        print(f"  failed files:", file=stream)
        for f in report["files_failed"]:
            print(f"    {f['path']}: {f['error']}", file=stream)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="Root directory to walk")
    ap.add_argument("--output", help="Write JSON report to this path (default: stdout)")
    ap.add_argument("--quiet", action="store_true", help="Suppress summary stderr")
    ap.add_argument("--tokens-only", action="store_true",
                    help="Output only aggregate_token_totals + summary")
    ap.add_argument("--filter", choices=["all", "pumpstation", "standard_pipeline", "json"],
                    default="all", help="Restrict to specific formats (default: all)")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print(f"ERROR: not a directory: {args.dir}", file=sys.stderr)
        return 1

    files = discover_traces(args.dir, only=args.filter)
    parsed, failed = parse_many(files)
    report = build_report(args.dir, parsed, failed)

    if args.tokens_only:
        report = OrderedDict([
            ("dir", report["dir"]),
            ("files_scanned", report["files_scanned"]),
            ("files_parsed", report["files_parsed"]),
            ("files_failed", report["files_failed"]),
            ("format_breakdown", report["format_breakdown"]),
            ("run_statuses", report["run_statuses"]),
            ("aggregate_token_totals", report["aggregate_token_totals"]),
        ])

    if not args.quiet:
        print_summary(report)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
    else:
        json.dump(report, sys.stdout, indent=2, default=str)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())