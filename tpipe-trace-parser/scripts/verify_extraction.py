#!/usr/bin/env python3
"""
verify_extraction.py — Self-test the trace parsers against known ground truth.

This script captures EXPECTED values from REAL trace artifacts, runs the parsers,
and compares the output. Run after every change to parse_html_trace.py or
parse_json_trace.py to verify nothing regressed.

Ground truth is computed by reading the raw HTML/JSON directly via regex, so this
verification doesn't trust either parser to validate itself.

Usage:
    python3 verify_extraction.py                          # auto-discover traces under ~/.tpipe/debug/trace
    python3 verify_extraction.py --strict                # exit nonzero on any drift
    python3 verify_extraction.py --case NAME              # run just one named case
    python3 verify_extraction.py --add NAME PATH          # capture new ground-truth case from a trace
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from html import unescape


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Ground-truth extraction (independent of the parser under test)
# ---------------------------------------------------------------------------

def gt_event_count(html_path):
    """Count event blocks by directly inspecting the HTML format."""
    h = open(html_path).read()
    if 'ps-detail-label' in h:  # pumpstation
        return len(re.findall(r"<div class=['\"]ps-detail-label['\"]>", h))
    return len(re.findall(r"<tr[^>]*class=['\"]trace-item['\"]", h))


def gt_event_types(html_path):
    """Return ordered list of event-type strings."""
    h = open(html_path).read()
    if 'ps-detail-label' in h:
        # In pumpstation, event type is inside parens in label: <div class='ps-detail-label'>LABEL<span class='ps-detail-type'>(TYPE)</span></div>
        # TYPE is like "PUMP_STATION_STARTED"
        return re.findall(r"\((PUMP_STATION_[A-Z_]+)\)", h)
    # standard pipeline: extract from <td>...</td> at index 2 (event type cell)
    types = []
    for row in re.finditer(r'<tr[^>]*class=["\']trace-item["\'][^>]*>(.*?)</tr>', h, re.DOTALL):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.DOTALL)
        if len(cells) >= 3:
            types.append(_strip(cells[2]))
    return types

def gt_token_totals(html_path):
    """Sum TOKEN counts directly from HTML (independent of any parser)."""
    h = open(html_path).read()
    totals = OrderedDict((k, 0) for k in (
        "inputTokens", "outputTokens", "totalTokens",
        "actualInputTokens", "reasoningTokens",
        "totalInputTokens", "totalOutputTokens",
    ))
    counts = OrderedDict((k, 0) for k in totals)
    # Pattern A: standard_pipeline <strong>key:</strong> <span...>N</span>
    for m in re.finditer(r"<strong>([a-zA-Z]+):</strong>\s*<span[^>]*>(\d+)</span>", h):
        k, v = m.group(1), int(m.group(2))
        if k in totals:
            totals[k] += v
            counts[k] += 1
    # Pattern B: pumpstation <span class='ps-meta-key'>key:</span><span class='ps-meta-val'>N</span>
    for m in re.finditer(r"<span class=['\"]ps-meta-key['\"]>([a-zA-Z]+):?</span><span class=['\"]ps-meta-val['\"]>(\d+)</span>", h):
        k, v = m.group(1), int(m.group(2))
        if k in totals:
            totals[k] += v
            counts[k] += 1
    return {k: {"total": totals[k], "count": counts[k]} for k in totals if counts[k] > 0}


def gt_length_totals(html_path):
    """Sum LENGTH counts (character lengths, NOT tokens) directly from HTML."""
    h = open(html_path).read()
    totals = OrderedDict((k, 0) for k in (
        "responseLength", "reasoningLength",
        "promptLength", "resultLength", "resultTextLength",
    ))
    counts = OrderedDict((k, 0) for k in totals)
    for m in re.finditer(r"<strong>([a-zA-Z]+):</strong>\s*<span[^>]*>(\d+)</span>", h):
        k, v = m.group(1), int(m.group(2))
        if k in totals:
            totals[k] += v
            counts[k] += 1
    for m in re.finditer(r"<span class=['\"]ps-meta-key['\"]>([a-zA-Z]+):?</span><span class=['\"]ps-meta-val['\"]>(\d+)</span>", h):
        k, v = m.group(1), int(m.group(2))
        if k in totals:
            totals[k] += v
            counts[k] += 1
    return {k: {"total": totals[k], "count": counts[k]} for k in totals if counts[k] > 0}


def gt_run_id(html_path):
    h = open(html_path).read()
    m = re.search(r"<span class=['\"]ps-run-id['\"]>(ps-[\w\-]+)</span>", h)
    if m:
        return m.group(1)
    m = re.search(r"<title>[^<]*?(ps-[\w\-]+)</title>", h)
    return m.group(1) if m else None


def gt_run_status(html_path):
    h = open(html_path).read()
    m = re.search(r"class=['\"]ps-status\s+ps-status-(\w+)['\"]", h)
    return m.group(1) if m else None


def _strip(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def gt_json_event_count(json_path):
    d = json.load(open(json_path))
    if isinstance(d, list):
        return len(d)
    if isinstance(d, dict) and "events" in d:
        return len(d["events"])
    raise ValueError(f"unexpected root: {type(d)}")


def gt_json_token_totals(json_path):
    """Sum TOKEN fields (NOT lengths) by key across all events in a JSON trace."""
    d = json.load(open(json_path))
    if isinstance(d, dict) and "events" in d:
        events = d["events"]
    elif isinstance(d, list):
        events = d
    else:
        raise ValueError(f"unexpected root: {type(d)}")
    totals = OrderedDict()
    for ev in events:
        meta = ev.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        for k in ("inputTokens", "outputTokens", "totalTokens",
                  "actualInputTokens", "reasoningTokens",
                  "totalInputTokens", "totalOutputTokens"):
            if k in meta:
                v = meta[k]
                if isinstance(v, bool): continue
                try:
                    iv = int(v)
                except (ValueError, TypeError):
                    continue
                totals.setdefault(k, {"total": 0, "count": 0})
                totals[k]["total"] += iv
                totals[k]["count"] += 1
    return totals


def gt_json_length_totals(json_path):
    """Sum LENGTH fields (NOT tokens) by key across all events in a JSON trace."""
    d = json.load(open(json_path))
    if isinstance(d, dict) and "events" in d:
        events = d["events"]
    elif isinstance(d, list):
        events = d
    else:
        raise ValueError(f"unexpected root: {type(d)}")
    totals = OrderedDict()
    for ev in events:
        meta = ev.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        for k in ("responseLength", "reasoningLength",
                  "promptLength", "resultLength", "resultTextLength"):
            if k in meta:
                v = meta[k]
                if isinstance(v, bool): continue
                try:
                    iv = int(v)
                except (ValueError, TypeError):
                    continue
                totals.setdefault(k, {"total": 0, "count": 0})
                totals[k]["total"] += iv
                totals[k]["count"] += 1
    return totals

# ---------------------------------------------------------------------------
# Case definitions (the source of truth for verification)
# ---------------------------------------------------------------------------

CASES = OrderedDict([
    ("pumpstation-interrupt", {
        "path": "/home/cage/.tpipe/debug/trace/tpipe-config-interrupt-live/pumpstation-ps-178493467.html",
        "kind": "html",
        "expect_format": "pumpstation",
        "expect_event_count": 23,
        "expect_run_id": "ps-1784934679811-8579",
        "expect_run_status": "completed",
        "expect_token_totals_gt": {
            "inputTokens": 100,
            "outputTokens": 50,
        },
        "expect_event_types_subset": [
            "PUMP_STATION_INTERRUPT_FIRED",
            "PUMP_STATION_STARTED",
            "PUMP_STATION_COMPLETED",
            "PUMP_STATION_JUDGE_COMPLETED",
        ],
    }),
    ("pumpstation-steering", {
        "path": "/home/cage/.tpipe/debug/trace/tpipe-config-steering-live/pumpstation-ps-178493471.html",
        "kind": "html",
        "expect_format": "pumpstation",
        "expect_event_count": 14,
        "expect_run_id": "ps-1784934713652-1452",
        "expect_run_status": "completed",
        "expect_token_totals_gt": {
            "inputTokens": 100,
            "outputTokens": 50,
        },
        "expect_event_types_subset": [
            "PUMP_STATION_STEERING_INJECTED",
            "PUMP_STATION_STARTED",
            "PUMP_STATION_COMPLETED",
            "PUMP_STATION_JUDGE_COMPLETED",
        ],
    }),
    ("junction-conversational", {
        "path": "/home/cage/.tpipe/debug/trace/Library/junction-live-bedrock/discussion-conversational/junction.html",
        "kind": "html",
        "expect_format": "junction",
        "expect_event_count": 13,
    }),
    ("junction-vote-plan-output-exit", {
        "path": "/home/cage/.tpipe/debug/trace/Library/junction-live-bedrock/workflow-vote_plan_output_exit/junction.html",
        "kind": "html",
        "expect_format": "junction",
        "expect_event_count": 18,
    }),
    ("distribution-grid-strict-execution", {
        "path": "/home/cage/.tpipe/debug/trace/Library/distribution-grid-live-bedrock/manual-core-qwen-two-node/strict-execution/sender-grid.html",
        "kind": "html",
        "expect_format": "distribution_grid",
        "expect_event_count": 18,
    }),
    ("distribution-grid-policy-visible", {
        "path": "/home/cage/.tpipe/debug/trace/Library/distribution-grid-live-bedrock/manual-core-qwen-two-node/trace-policy-visible/sender-grid.html",
        "kind": "html",
        "expect_format": "distribution_grid",
        "expect_event_count": 18,
    }),
    ("agent-judge-interrupt", {
        "path": "/home/cage/.tpipe/debug/trace/tpipe-config-interrupt-live/agent-judge.html",
        "kind": "html",
        "expect_format": "standard_pipeline",
        "expect_token_totals_gt": {
            "inputTokens": 100,
            "outputTokens": 50,
        },
    }),
    ("manifold-nested-reasoning-bug", {
        "path": "/home/cage/.tpipe/debug/trace/Library/nested-reasoning-bug/llama4-maverick/manifold-execution.html",
        "kind": "html",
        "expect_format": "manifold",
        "expect_event_count": 45,
        "expect_event_types_subset": [
            "MANIFOLD_START", "MANIFOLD_END", "MANIFOLD_FAILURE",
            "MANAGER_DECISION", "AGENT_REQUEST_VALIDATION",
            "P2P_REQUEST_FAILURE", "API_CALL_SUCCESS",
        ],
    }),
    ("manifold-nested-reasoning-bug-json", {
        "path": "/home/cage/.tpipe/debug/trace/Library/nested-reasoning-bug/llama4-maverick/manifold-execution.json",
        "kind": "json",
        "expect_event_count": 45,
        "expect_token_totals_gt": {
            "actualInputTokens": 1000,
            "totalOutputTokens": 100,
        },
        "expect_length_totals": {
            "responseLength": {"total": 4868, "count": 2},
            "resultTextLength": {"total": 6540, "count": 3},
        },
    }),
    ("reversal-agent-json", {
        "path": "/home/cage/.tpipe/autogenesis-trace/Round_1_Turn_2_Narjan_Goren/ReversalAgent/trace.json",
        "kind": "json",
        "expect_event_count": 54,
        "expect_token_totals": {
            "inputTokens": {"total": 4601, "count": 2},
            "outputTokens": {"total": 4668, "count": 6},
            "totalTokens": {"total": 6759, "count": 2},
            "actualInputTokens": {"total": 8090, "count": 4},
            "totalInputTokens": {"total": 11935, "count": 4},
            "totalOutputTokens": {"total": 4025, "count": 4},
        },
        "expect_length_totals": {
            "responseLength": {"total": 11059, "count": 2},
            "reasoningLength": {"total": 5103, "count": 1},
        },
    }),
])


# ---------------------------------------------------------------------------
# Run parser, compare to ground truth
# ---------------------------------------------------------------------------

def run_parser_html(path):
    r = subprocess.run(
        ["python3", os.path.join(SCRIPT_DIR, "parse_html_trace.py"),
         "--input", path, "--format", "full", "--quiet"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"parser failed: {r.stderr}")
    return json.loads(r.stdout)


def run_parser_json(path):
    r = subprocess.run(
        ["python3", os.path.join(SCRIPT_DIR, "parse_json_trace.py"),
         "--input", path, "--format", "full", "--quiet"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"parser failed: {r.stderr}")
    return json.loads(r.stdout)


def _diff(expected, actual, *, path=""):
    """Return list of (path, expected, actual) for any mismatches."""
    out = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out.append((path, expected, actual))
            return out
        for k in expected:
            sub = f"{path}.{k}" if path else k
            if k not in actual:
                out.append((sub, expected[k], "<missing>"))
            else:
                out.extend(_diff(expected[k], actual[k], path=sub))
        # extras are OK
    else:
        if expected != actual:
            out.append((path, expected, actual))
    return out


def run_case(name, spec):
    path = spec["path"]
    if not os.path.exists(path):
        return [(f"{name}:path", path, "<missing file>")]

    if spec["kind"] == "html":
        gt_event_count_val = gt_event_count(path)
        gt_token_totals_val = gt_token_totals(path)
        gt_run_id_val = gt_run_id(path)
        gt_run_status_val = gt_run_status(path)
        gt_event_types_val = gt_event_types(path)

        parsed = run_parser_html(path)
        out = []

        # event count
        if "expect_event_count" in spec and parsed["event_count"] != spec["expect_event_count"]:
            out.append((f"{name}.event_count", spec["expect_event_count"], parsed["event_count"]))
        if "expect_event_count_gt" in spec and parsed["event_count"] <= spec["expect_event_count_gt"]:
            out.append((f"{name}.event_count_gt", f"> {spec['expect_event_count_gt']}", parsed["event_count"]))
        # format
        if "expect_format" in spec and parsed["format"] != spec["expect_format"]:
            out.append((f"{name}.format", spec["expect_format"], parsed["format"]))
        # run_id / run_status (only meaningful for pumpstation)
        if "expect_run_id" in spec and parsed["run_id"] != spec["expect_run_id"]:
            out.append((f"{name}.run_id", spec["expect_run_id"], parsed["run_id"]))
        elif gt_run_id_val and parsed["run_id"] != gt_run_id_val:
            out.append((f"{name}.run_id(gt)", gt_run_id_val, parsed["run_id"]))
        if "expect_run_status" in spec and parsed["run_status"] != spec["expect_run_status"]:
            out.append((f"{name}.run_status", spec["expect_run_status"], parsed["run_status"]))
        elif gt_run_status_val and parsed["run_status"] != gt_run_status_val:
            out.append((f"{name}.run_status(gt)", gt_run_status_val, parsed["run_status"]))
        # token totals
        out.extend(_diff(gt_token_totals_val, parsed["token_totals"], path=f"{name}.token_totals"))
        # length totals (separate dict)
        if "expect_length_totals" in spec:
            out.extend(_diff(spec["expect_length_totals"], parsed.get("length_totals", {}),
                             path=f"{name}.length_totals"))
        # lower-bound token totals
        if "expect_token_totals_gt" in spec:
            for tk, threshold in spec["expect_token_totals_gt"].items():
                actual = parsed.get("token_totals", {}).get(tk, {}).get("total", 0)
                if actual < threshold:
                    out.append((f"{name}.token_totals_gt[{tk}]", f">= {threshold}", actual))
        # event types order
        parsed_types = [e["eventType"] for e in parsed["events"]]
        if parsed_types != gt_event_types_val:
            # Compare just the prefix; expected is identical length
            for i, (g, p) in enumerate(zip(gt_event_types_val, parsed_types)):
                if g != p:
                    out.append((f"{name}.eventType[{i}]", g, p))
        # event types subset (presence check, not ordering)
        if "expect_event_types_subset" in spec:
            parsed_set = set(parsed_types)
            for required in spec["expect_event_types_subset"]:
                if required not in parsed_set:
                    out.append((f"{name}.eventType_missing", required, parsed_set))
        return out

    elif spec["kind"] == "json":
        gt_count = gt_json_event_count(path)
        gt_tokens = gt_json_token_totals(path)
        parsed = run_parser_json(path)
        out = []
        if parsed["event_count"] != gt_count:
            out.append((f"{name}.event_count", gt_count, parsed["event_count"]))
        out.extend(_diff(gt_tokens, parsed["token_totals"], path=f"{name}.token_totals"))
        if "expect_length_totals" in spec:
            out.extend(_diff(spec["expect_length_totals"], parsed.get("length_totals", {}),
                             path=f"{name}.length_totals"))
        return out
    else:
        return [(f"{name}.kind", spec["kind"], "<unsupported>")]


# ---------------------------------------------------------------------------
# Auto-discover mode
# ---------------------------------------------------------------------------

def autodiscover(roots=("/home/cage/.tpipe/debug/trace",)):
    """Scan roots for *.html and *.json files. Print summary but don't add as cases."""
    found = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for root, _, files in os.walk(r):
            for fn in files:
                if fn.endswith(".html") or fn.endswith(".json"):
                    found.append(os.path.join(root, fn))
    return found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="Exit with nonzero status if any case fails")
    ap.add_argument("--case", help="Run only one named case")
    ap.add_argument("--add", nargs=2, metavar=("NAME", "PATH"),
                    help="Capture a new ground-truth case (prints the JSON to add to CASES)")
    ap.add_argument("--autodiscover", action="store_true",
                    help="List all trace files under default roots")
    args = ap.parse_args()

    if args.autodiscover:
        files = autodiscover()
        print(f"Discovered {len(files)} trace files:")
        for f in sorted(files):
            print(f"  {f}")
        return 0

    if args.add:
        name, path = args.add
        kind = "json" if path.endswith(".json") else "html"
        spec = {"path": path, "kind": kind}
        if kind == "html":
            spec["expect_event_count"] = gt_event_count(path)
            spec["expect_format"] = "pumpstation" if 'ps-detail-label' in open(path).read(5000) else "standard_pipeline"
            spec["expect_token_totals"] = gt_token_totals(path)
            rid = gt_run_id(path)
            if rid: spec["expect_run_id"] = rid
            st = gt_run_status(path)
            if st: spec["expect_run_status"] = st
            spec["expect_event_types"] = gt_event_types(path)
        else:
            spec["expect_event_count"] = gt_json_event_count(path)
            spec["expect_token_totals"] = gt_json_token_totals(path)
        print(json.dumps({name: spec}, indent=2))
        print(f"\n# Add the above to CASES in {__file__}", file=sys.stderr)
        return 0

    cases_to_run = OrderedDict()
    if args.case:
        if args.case not in CASES:
            print(f"unknown case: {args.case}", file=sys.stderr)
            print(f"available: {list(CASES.keys())}", file=sys.stderr)
            return 2
        cases_to_run[args.case] = CASES[args.case]
    else:
        cases_to_run = CASES

    total = 0
    failures = []
    print(f"{'CASE':40s} {'EVENTS':>7} {'FORMAT':20s} {'STATUS'}")
    print("-" * 90)
    for name, spec in cases_to_run.items():
        if not os.path.exists(spec["path"]):
            print(f"{name:40s} {'<missing>':>7}")
            failures.append((name, "<missing path>", spec["path"]))
            continue
        diffs = run_case(name, spec)
        total += 1
        if diffs:
            status = f"FAIL ({len(diffs)} diffs)"
            print(f"{name:40s} {spec.get('expect_event_count', '?'):>7} {spec.get('expect_format', '?'):20s} {status}")
            for d in diffs:
                print(f"    DIFF  {d[0]}: expected={d[1]!r}  actual={d[2]!r}")
            failures.extend(diffs)
        else:
            print(f"{name:40s} {spec.get('expect_event_count', '?'):>7} {spec.get('expect_format', '?'):20s} PASS")
    print("-" * 90)
    print(f"\nRan {total} case(s); {len(failures)} failure(s)")
    if failures:
        print("\nFAILURES:")
        for d in failures:
            print(f"  {d[0]}: expected={d[1]!r}  actual={d[2]!r}")
    return 1 if (args.strict and failures) else 0


if __name__ == "__main__":
    sys.exit(main())