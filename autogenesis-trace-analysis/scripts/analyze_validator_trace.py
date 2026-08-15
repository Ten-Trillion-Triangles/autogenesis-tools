#!/usr/bin/env python3
"""
analyze_validator_trace.py — Print the chronology of a validator trace file,
highlighting the events that matter for "why did my play get changed" debugging.

Usage:
    python3 scripts/analyze_validator_trace.py <path-to-validator-trace.json>

Outputs:
  - Total events and duration
  - Distinct pipe runs (by pipeId UUID)
  - All top-level PIPE_START events
  - All TRANSFORMATION / BRANCH_PIPE_TRIGGERED events
  - The legality-rectifier skip detection (PIPE_START + 2 PRE_INVOKE + no PIPE_SUCCESS)
  - The style-reapply branch trigger detection

Designed for the autogenesis game trace format: JSON array of events with
{id, timestamp, pipeId, pipeName, eventType, phase, metadata}.
"""

import json
import sys
from collections import Counter, defaultdict


def analyze(path: str) -> None:
    with open(path) as f:
        events = json.load(f)

    print(f"=== {path} ===")
    print(f"Total events: {len(events)}")
    if events:
        dur = (events[-1]["timestamp"] - events[0]["timestamp"]) / 1000
        print(f"Duration: {dur:.2f}s")
    print()

    # Distinct pipe runs
    pipe_runs = defaultdict(list)
    for i, e in enumerate(events):
        pipe_runs[e["pipeId"]].append((i, e))

    print(f"--- Distinct pipe runs ({len(pipe_runs)}) ---")
    for pid, occurrences in sorted(pipe_runs.items(), key=lambda kv: kv[1][0][0]):
        names = set(e["pipeName"] for _, e in occurrences)
        first_event = occurrences[0][1]
        last_event = occurrences[-1][1]
        outcome = (
            "COMPLETED" if any(e["eventType"] == "PIPE_SUCCESS" for _, e in occurrences)
            else "SKIPPED / NO COMPLETION"
        )
        print(f"  {pid[:8]}: {len(occurrences)} events, {outcome}")
        print(f"     names: {names}")
        print(f"     first: {first_event['eventType']} in {first_event['pipeName']}")
        print(f"     last:  {last_event['eventType']} in {last_event['pipeName']}")
    print()

    # Top-level PIPE_STARTs (no "->" in pipeName)
    print("--- Top-level PIPE_STARTs (chronological) ---")
    for i, e in enumerate(events):
        if e["eventType"] == "PIPE_START" and "->" not in e["pipeName"]:
            ts = e["timestamp"] - events[0]["timestamp"]
            print(f"  [{i:3d}] t+{ts:>6}ms {e['pipeName']}")
    print()

    # Critical events: TRANSFORMATION_SUCCESS, BRANCH_PIPE_TRIGGERED
    print("--- Play-rewriting events ---")
    rewrites = 0
    for i, e in enumerate(events):
        if e["eventType"] in ("TRANSFORMATION_SUCCESS", "BRANCH_PIPE_TRIGGERED"):
            ts = e["timestamp"] - events[0]["timestamp"]
            print(f"  [{i:3d}] t+{ts:>6}ms {e['eventType']:<25} in {e['pipeName']}")
            if e["eventType"] == "TRANSFORMATION_SUCCESS":
                rewrites += 1
    print(f"\n  Total play rewrites (TRANSFORMATION_SUCCESS): {rewrites}")
    print()

    # Detect the "legality rectifier silent skip" pattern
    print("--- Legality rectifier check ---")
    rectifier_starts = [i for i, e in enumerate(events)
                        if e["eventType"] == "PIPE_START" and e["pipeName"] == "legality rectifier pipe"]
    if not rectifier_starts:
        print("  legality rectifier pipe did not run at all")
    else:
        for start_idx in rectifier_starts:
            # Find next PIPE_START (different pipe) or end
            rectifier_pid = events[start_idx]["pipeId"]
            subsequent = [e for e in events[start_idx + 1:] if e["pipeId"] != rectifier_pid]
            has_completion = any(
                e["eventType"] == "PIPE_SUCCESS" and e["pipeId"] == rectifier_pid
                for e in events
            )
            pre_invokes = sum(
                1 for e in events[start_idx:start_idx + 10]
                if e["eventType"] == "PRE_INVOKE" and e["pipeId"] == rectifier_pid
            )
            skipped = not has_completion
            print(f"  legality rectifier pipe at event {start_idx}:")
            print(f"     pre-invokes logged: {pre_invokes}")
            print(f"     pipe completed: {not skipped}")
            if skipped and pre_invokes >= 2:
                print(f"     → SILENT SKIP DETECTED (legality was likely true, pipe body never ran)")
    print()

    # Detect style reapply branch trigger
    print("--- Style reapply branch check ---")
    branch_triggers = [
        (i, e) for i, e in enumerate(events)
        if e["eventType"] == "BRANCH_PIPE_TRIGGERED" and e["pipeName"] == "style reapply pipe"
    ]
    if branch_triggers:
        for idx, e in branch_triggers:
            print(f"  ⚠ BRANCH TRIGGERED at event {idx}")
            print(f"     → Main Qwen Coder third-person conversion was REJECTED by the validator.")
            print(f"     → The branch pipe (Palmyra X5) re-generated the third-person version.")
            print(f"     → The branch's `newOutput` is what wrote the play. This is the 'nuke'.")
    else:
        print("  No style reapply branch trigger — main pipe output was accepted as-is.")
    print()

    # Author pipe LLM call summary
    print("--- Author pipe LLM calls (responseLength by call) ---")
    for i, e in enumerate(events):
        if e["pipeName"] == "author" and e["eventType"] == "API_CALL_SUCCESS":
            md = e.get("metadata", {})
            rl = md.get("responseLength", "?")
            mi = md.get("modelId", "?")
            short_model = mi.split("/")[-1] if "/" in mi else mi
            print(f"  [{i:3d}] responseLength={rl:<6} model={short_model}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-validator-trace.json>")
        sys.exit(1)
    analyze(sys.argv[1])
