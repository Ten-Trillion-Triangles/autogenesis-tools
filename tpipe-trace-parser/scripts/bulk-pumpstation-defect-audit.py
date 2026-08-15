#!/usr/bin/env python3
"""
Bulk-parse all PumpStation live-test trace folders to verify which defects
from a catalog are still observable in the traces.

Pattern proven 2026-07-10 against the 13-defect batch:
- 13 trace folders at ~/.tpipe/debug/trace/PumpStation/01-always-on-judge, 02-..., stub-01-...
- Each folder has agent-{role}.html + pumpstation-ps-{runId}.html
- Map each catalog defect to one or more signature regexes
- For each trace, count hits and report the files that contain them
- Aggregate to a "defect present in trace" matrix

This is a one-shot, deterministic probe — no LLM calls. Run after a catalog
update to confirm which defects are still observable in the canonical traces.
"""
import re
import os
import sys
from collections import defaultdict
from pathlib import Path

TRACE_ROOT = Path.home() / ".tpipe/debug/trace/PumpStation"

# Per-defect signature map. Add new entries when a new defect is identified.
# Each entry: defect_id -> compiled regex (the symptom you want to detect)
SIGNATURES = {
    "D1_judge_hallucinated_complete": re.compile(
        r"PUMP_STATION_JUDGE_COMPLETED[^<]*?isComplete[^<]{0,20}?true",
        re.IGNORECASE
    ),
    "D3_NoExitSignal_warning": re.compile(
        r"PUMP_STATION_HARNESS_WARNING[^<]*NoExitSignalConfigured",
        re.IGNORECASE
    ),
    "D5_pathSafety_exercised": re.compile(
        r"PUMP_STATION_PATH_SAFETY_(STARTED|COMPLETED)",
        re.IGNORECASE
    ),
    "D8_dispatch_no_path_injection": re.compile(
        r"Available paths will be auto-injected",
        re.IGNORECASE
    ),
    "D8_dispatch_no_PathDescriptionList": re.compile(
        r"PathDescriptionList",
        re.IGNORECASE
    ),
    "D9_rationale_nudge_count": re.compile(
        r"\[Harness Notice\] Your dispatch output was a valid PathRequest JSON but the pathSelectionRationale",
        re.IGNORECASE
    ),
    "D11_loopGuard_before_pathSafety": re.compile(
        r"PUMP_STATION_LOOP_GUARD_TRIPPED",
        re.IGNORECASE
    ),
    "D14_judge_accepted_path_failure": re.compile(
        r"I don't have enough information",
        re.IGNORECASE
    ),
    "D15_turnSummary_corrupts_judge": re.compile(
        r"## Summary:",
        re.IGNORECASE
    ),
    "D17_empty_pathName_hint": re.compile(
        r"\[Harness Notice\] Your dispatch output was a valid PathRequest JSON but the pathName field was empty",
        re.IGNORECASE
    ),
    "D20_HarnessStarted_drop_originalInput": re.compile(
        r"PUMP_STATION_STARTED",
        re.IGNORECASE
    ),
    "D22_JudgeStarted_empty_metadata": re.compile(
        r"PUMP_STATION_JUDGE_STARTED",
        re.IGNORECASE
    ),
    "D23_killSwitch_kill_site_disambig": re.compile(
        r"KillSwitchTripped",
        re.IGNORECASE
    ),
    "D26_analyze_echo_path_name": re.compile(
        r"Analyzed themes[^<]*source finding[^<]*analyze",
        re.IGNORECASE
    ),
    "F3_pathSafety_hint_in_history": re.compile(
        r"\[Path Safety\] Path '[^']+' was rejected by the path-safety gate",
        re.IGNORECASE
    ),
    "PIPE_EOFDuringTeardown": re.compile(
        r"EOFException.*server prematurely closed",
        re.IGNORECASE
    ),
}

# Per-test metadata. Optional — extend when adding new test fixtures.
TEST_META = {
    "01-always-on-judge":       {"kind": "live", "expected_judge_mode": "Always"},
    "02-flag-triggered-judge":  {"kind": "live", "expected_judge_mode": "FlagTriggered"},
    "03-compaction-memory":     {"kind": "live", "expected_compaction": True},
    "04-kill-switch-trip":      {"kind": "live", "expected_killswitch": True},
    "05-single-path-pass-pipeline": {"kind": "live", "expected_pass": True},
    "06-multi-path-risk-levels":   {"kind": "live", "expected_risk": True},
    "stub-01-always-on-judge":  {"kind": "stub"},
    "stub-02-flag-triggered-judge": {"kind": "stub"},
    "stub-03-compaction-memory":    {"kind": "stub"},
    "stub-04-kill-switch-trip":     {"kind": "stub", "killed": True},
    "stub-05-single-path-pass-pipeline": {"kind": "stub"},
    "stub-06-multi-path-risk-levels":   {"kind": "stub"},
    "stub-07-path-safety-rejection":    {"kind": "stub", "expected_rejection": True},
}


def parse_pumpstation_html(path):
    """Pull key facts from a pumpstation-ps-*.html file."""
    text = path.read_text(errors="replace")
    out = {}
    for ev_type in [
        "HARNESS_STARTED", "HARNESS_WARNING", "HARNESS_COMPLETED",
        "JUDGE_STARTED", "JUDGE_SKIPPED", "JUDGE_COMPLETED",
        "DISPATCH_STARTED", "DISPATCH_COMPLETED",
        "PATH_SAFETY_STARTED", "PATH_SAFETY_COMPLETED",
        "PATH_STARTED", "PATH_COMPLETED", "PATH_FAILED",
        "LOOP_GUARD_TRIPPED", "INTERVENTION_STARTED", "INTERVENTION_COMPLETED",
        "GOAL_VALIDATION_STARTED", "GOAL_VALIDATION_COMPLETED",
    ]:
        out[f"count_{ev_type}"] = text.count(f"PUMP_STATION_{ev_type}")
    m = re.search(r"PUMP_STATION_COMPLETED[^<]*?exitReason[^<]{0,200}?([A-Z][a-zA-Z]+)", text)
    if m:
        out["completed_exitReason"] = m.group(1)
    out["judge_complete_count"] = text.count("PUMP_STATION_JUDGE_COMPLETED")
    out["judge_isComplete_true"] = len(re.findall(
        r"PUMP_STATION_JUDGE_COMPLETED[^<]*?isComplete[^<]{0,20}?true", text, re.IGNORECASE
    ))
    out["dispatch_complete_count"] = text.count("PUMP_STATION_DISPATCH_COMPLETED")
    out["selected_path_sequence"] = re.findall(
        r"PUMP_STATION_DISPATCH_COMPLETED[^<]*?selectedPathName[^<]{0,50}?[\"']([^\"']{0,40})[\"']",
        text, re.IGNORECASE
    )
    out["turn_count_max"] = len(re.findall(r"JUDGE_(STARTED|SKIPPED)", text))
    return out


def main():
    trace_root = TRACE_ROOT
    if not trace_root.exists():
        print(f"FAIL: trace root {trace_root} does not exist", file=sys.stderr)
        sys.exit(1)

    rows = []
    for test_dir in sorted(trace_root.iterdir()):
        if not test_dir.is_dir():
            continue
        test_name = test_dir.name
        meta = TEST_META.get(test_name, {})
        ps_htmls = list(test_dir.glob("pumpstation-ps-*.html"))
        if not ps_htmls:
            rows.append({"test": test_name, "status": "MISSING_PS_HTML"})
            continue
        ps_html = ps_htmls[0]
        ps_data = parse_pumpstation_html(ps_html)
        sig_hits = defaultdict(int)
        sig_files = defaultdict(list)
        for html in test_dir.glob("*.html"):
            text = html.read_text(errors="replace")
            for sig_name, sig_re in SIGNATURES.items():
                hits = len(sig_re.findall(text))
                if hits > 0:
                    sig_hits[sig_name] += hits
                    sig_files[sig_name].append(html.name)
        rows.append({
            "test": test_name,
            "kind": meta.get("kind", "?"),
            "ps_data": ps_data,
            "sig_hits": dict(sig_hits),
            "sig_files": dict(sig_files),
        })

    print("=" * 100)
    print(f"PumpStation Trace Audit — {len(rows)} tests")
    print("=" * 100)
    for row in rows:
        print(f"\n--- {row['test']} [{row['kind']}] ---")
        if "status" in row and row["status"] == "MISSING_PS_HTML":
            print("  MISSING pumpstation-ps-*.html")
            continue
        ps = row["ps_data"]
        print(f"  judge_completed={ps.get('judge_complete_count', 0)} "
              f"judge_isComplete_true={ps.get('judge_isComplete_true', 0)} "
              f"dispatch_completed={ps.get('dispatch_complete_count', 0)} "
              f"turns={ps.get('turn_count_max', 0)}")
        print(f"  exit: completed={ps.get('completed_exitReason', '?')}")
        print(f"  path_sequence: {ps.get('selected_path_sequence', [])[:10]}")
        sigs = row["sig_hits"]
        if sigs:
            print(f"  SIGNALS:")
            for sig, count in sorted(sigs.items()):
                files = ",".join(set(row["sig_files"][sig]))
                print(f"    {sig}: {count} hit(s) in [{files}]")


if __name__ == "__main__":
    main()
