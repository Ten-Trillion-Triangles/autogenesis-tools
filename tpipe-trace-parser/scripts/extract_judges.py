#!/usr/bin/env python3
"""
extract_judges.py — Triage-focused extractor for parsed PumpStation HTML JSONs.

Usage:
    python3 extract_judges.py /tmp/pstriage/canonical /tmp/pstriage/legacy

Reads every *.json file under the given root dir(s), which are the output of
parse_pumpstation_html.py. Each parsed file is a dict with keys
{path, run_status, run_id, events, event_count}. This script pulls the
meta keys + the first JSON snippet from the text body for the five events
that carry decisions in PumpStation triage:

    PUMP_STATION_JUDGE_COMPLETED
    PUMP_STATION_DISPATCH_COMPLETED
    PUMP_STATION_PATH_SAFETY_COMPLETED
    PUMP_STATION_PATH_FAILED
    PUMP_STATION_LOOP_GUARD_TRIPPED

Output (per trace, to stdout) is shaped like:
    --- test-name ---
      EVENT: meta.field=val | meta.other=val | text.json={ ... } | text=...

This is the third-pass Stage-4 helper referenced in the
"PumpStation Third-Pass Triage Protocol" section of SKILL.md.

NOT a general-purpose trace parser. Use parse_pumpstation_html.py for that.
"""
import json
import os
import sys
from glob import glob


DECISION_EVENTS = {
    "PUMP_STATION_JUDGE_COMPLETED",
    "PUMP_STATION_DISPATCH_COMPLETED",
    "PUMP_STATION_PATH_SAFETY_COMPLETED",
    "PUMP_STATION_PATH_FAILED",
    "PUMP_STATION_LOOP_GUARD_TRIPPED",
    "PUMP_STATION_FAILED",
    "PUMP_STATION_COMPLETED",
}

META_KEYS_OF_INTEREST = (
    "isComplete", "shouldTerminate", "selectedPathName", "approved",
    "pathName", "riskLevel", "error", "errorMessage", "exitReason",
    "reason", "reasonText", "outcome", "guard", "detail", "warningCode",
    "mechanisms", "nudges", "shouldContinue", "trigger",
)


def get_events(fp):
    """Read parsed JSON. Output is a top-level DICT with 'events' key.

    Returns (events, status). Events is a list; status is a string from
    the parser (e.g. 'completed', 'failed', 'running').
    """
    with open(fp) as f:
        d = json.load(f)
    if isinstance(d, dict):
        return d.get("events", []), d.get("run_status", "?")
    return d, "?"


def first_json_block(text):
    """Return the first balanced { ... } JSON snippet in text, truncated."""
    text = text or ""
    jstart = text.find("{")
    if jstart < 0:
        return ""
    depth = 0
    for i in range(jstart, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[jstart : i + 1][:200]
    return text[jstart : jstart + 200]


def fmt_meta(meta):
    parts = []
    for k in META_KEYS_OF_INTEREST:
        v = meta.get(k)
        if v is not None and str(v).strip():
            vstr = str(v).replace("\n", " ")[:80]
            parts.append(f"{k}={vstr}")
    return parts


def fmt_event(e):
    t = e.get("type", "?")
    meta = e.get("meta", {}) or {}
    bits = fmt_meta(meta)
    text = e.get("text", "") or ""
    if text.strip():
        jb = first_json_block(text)
        if jb:
            bits.append(f"text.json={jb[:120]}")
        else:
            bits.append(f"text={text[:80].strip()}")
    return f"{t}: {' | '.join(bits)}" if bits else t


def dump_root(root):
    files = sorted(glob(os.path.join(root, "*.json")))
    if not files:
        print(f"(no json files found under {root})", file=sys.stderr)
        return
    print(f"\n========== {root} ({len(files)} traces) ==========")
    for fp in files:
        events, status = get_events(fp)
        test = os.path.basename(fp).replace(".json", "")
        print(f"\n--- {test} ---")
        any_decision = False
        for e in events:
            if e.get("type") in DECISION_EVENTS:
                line = fmt_event(e)
                if line:
                    print(f"  {line}")
                    any_decision = True
        if not any_decision:
            print("  (no decision events)")


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    for root in argv[1:]:
        if not os.path.isdir(root):
            print(f"not a directory: {root}", file=sys.stderr)
            continue
        dump_root(root)


if __name__ == "__main__":
    main(sys.argv)