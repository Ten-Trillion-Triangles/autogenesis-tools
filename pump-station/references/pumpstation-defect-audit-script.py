#!/usr/bin/env python3
"""
Bulk-parse all 13 PumpStation live-test traces to verify which defects from the
catalog are still true in current source.

The script parses each pumpstation-ps-*.html for: PUMP_STATION_* event counts,
isComplete/shouldTerminate triggers, pathSafety verdicts, HarnessWarning
events, HarnessCompleted exitReason, and specific markers for the catalog
defects (missing path-injection, unbounded rationale nudges, pathSchema-as-
user-prompt, path-safety rejection hint presence).

Run from anywhere. Writes a per-test summary to stdout. Designed for the third-
pass triage pattern documented in `pump-station` SKILL.md.

Usage:
    python3 pumpstation-defect-audit-script.py

Output sections per test:
  - judge_completed, judge_isComplete_true, dispatch_completed, turns
  - exit: completed/failed reason
  - path_sequence: selectedPathName values per dispatch
  - SIGNALS: defect-pattern hits with source files
  - per-agent role diagnostics: prompts, judge_verdicts, dispatch_decisions,
    path_safety, rationale, input_tokens

Cross-reference each SIGNAL with current source state. The script does NOT
report a defect as fixed — it only reports the trace symptom. A defect is
"fixed" only when the production source has the corresponding code change AND
the trace artifacts no longer exhibit the symptom.

This pairs with the source-verification protocol in the pump-station SKILL.md
"Catalog staleness" pitfall: trace-evidence + source-grep together, not either
alone. Trace evidence is necessary-but-not-sufficient because:
  1. Traces are stale the moment they're written (subsequent fixes don't
     propagate back).
  2. Catalog text can be wrong (Defect 18 originally claimed the funnel at
     Helpers.kt:117 dropped exitReason, but current source at :132-137
     clearly extracts both fields — catalog diagnosis was incorrect).
  3. New defects can emerge (F3 path-safety hint at PumpStation.kt:2907-2915
     is a clone of the pre-fix Defect 9 unbounded-duplicate anti-pattern).
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

TRACE_ROOT = Path.home() / ".tpipe/debug/trace/PumpStation"

# Per-test metadata table (extensible — add new tests here)
TEST_META = {
    "01-always-on-judge":       {"kind": "live", "killed": False},
    "02-flag-triggered-judge":  {"kind": "live", "killed": False},
    "03-compaction-memory":     {"kind": "live", "killed": False},
    "04-kill-switch-trip":      {"kind": "live", "killed": True},
    "05-single-path-pass-pipeline": {"kind": "live", "killed": False},
    "06-multi-path-risk-levels":   {"kind": "live", "killed": False},
    "stub-01-always-on-judge":  {"kind": "stub", "killed": False},
    "stub-02-flag-triggered-judge": {"kind": "stub", "killed": False},
    "stub-03-compaction-memory":    {"kind": "stub", "killed": False},
    "stub-04-kill-switch-trip":     {"kind": "stub", "killed": True},
    "stub-05-single-path-pass-pipeline": {"kind": "stub", "killed": False},
    "stub-06-multi-path-risk-levels":   {"kind": "stub", "killed": False},
    "stub-07-path-safety-rejection":    {"kind": "stub", "killed": False},
}

# Catalog-defect → trace-pattern mapping. Each entry is a regex searched
# across every .html file in the test directory.
SIGNATURES = {
    "D3_NoExitSignal_warning": re.compile(
        r"PUMP_STATION_HARNESS_WARNING[^<]*NoExitSignalConfigured", re.IGNORECASE),
    "D5_pathSafety_exercised": re.compile(
        r"PUMP_STATION_PATH_SAFETY_(STARTED|COMPLETED)", re.IGNORECASE),
    "D8_dispatch_no_path_injection": re.compile(
        r"PathDescriptionList|Available paths will be auto-injected|hasExecutionFunction",
        re.IGNORECASE),
    "D9_rationale_nudge_text": re.compile(
        r"\[Harness Notice\] Your dispatch output was a valid PathRequest JSON but the pathSelectionRationale",
        re.IGNORECASE),
    "D11_loopGuard_before_pathSafety": re.compile(
        r"PUMP_STATION_LOOP_GUARD_TRIPPED", re.IGNORECASE),
    "D14_judge_accepted_path_failure": re.compile(
        r"I don't have enough information", re.IGNORECASE),
    "D15_turnSummary_corrupts_judge": re.compile(
        r"## Summary:", re.IGNORECASE),
    "D16_pathSafety_decisions": re.compile(
        r"\"safe\":\s*(true|false)", re.IGNORECASE),
    "D17_empty_pathName_hint": re.compile(
        r"\[Harness Notice\] Your dispatch output was a valid PathRequest JSON but the pathName field was empty",
        re.IGNORECASE),
    "F3_pathSafety_hint_in_history": re.compile(
        r"\[Path Safety\] Path '[^']+' was rejected by the path-safety gate", re.IGNORECASE),
    "F3_clone_unbounded_duplicate": re.compile(
        r"\[Path Safety\] Path '[^']+' was rejected by the path-safety gate", re.IGNORECASE),
}


def parse_pumpstation_html(path):
    text = path.read_text(errors="replace")
    out = {}
    # Event counts for the harness funnel
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
    m = re.search(
        r"PUMP_STATION_FAILED[^<]*?error[^<]{0,500}?([A-Z][A-Z_]+)[^<]{0,500}?exitReason[^<]{0,200}?([A-Z][a-zA-Z]+)",
        text)
    if m:
        out["failed_error"] = m.group(1)
        out["failed_exitReason"] = m.group(2)
    out["judge_complete_count"] = text.count("PUMP_STATION_JUDGE_COMPLETED")
    out["judge_isComplete_true"] = len(re.findall(
        r"PUMP_STATION_JUDGE_COMPLETED[^<]*?isComplete[^<]{0,20}?true", text, re.IGNORECASE))
    out["dispatch_complete_count"] = text.count("PUMP_STATION_DISPATCH_COMPLETED")
    out["selected_path_sequence"] = re.findall(
        r"PUMP_STATION_DISPATCH_COMPLETED[^<]*?selectedPathName[^<]{0,50}?[\"']([^\"']{0,40})[\"']",
        text, re.IGNORECASE)
    m = re.search(
        r"PUMP_STATION_COMPLETED[^<]*?finalOutput[^<]{0,400}?text=([^<\n]{0,80})", text)
    if m:
        out["final_output_preview"] = m.group(1)[:80]
    out["turn_count_max"] = len(re.findall(r"JUDGE_(STARTED|SKIPPED)", text))
    return out


def parse_agent_html(path):
    text = path.read_text(errors="replace")
    out = {}
    out["input_token_counts"] = re.findall(r"inputTokens[\"']?\s*[:=]\s*([\-\d]+)", text)
    out["output_token_counts"] = re.findall(r"outputTokens[\"']?\s*[:=]\s*([\-\d]+)", text)
    out["judge_verdicts"] = re.findall(r"\"isComplete\":\s*(true|false)", text)
    out["dispatch_decisions"] = re.findall(r"\"pathName\":\s*\"([^\"]+)\"", text)
    out["path_safety_decisions"] = re.findall(r"\"safe\":\s*(true|false)", text)
    out["rationale_field"] = re.findall(r"\"pathSelectionRationale\":\s*(\"[^\"]*\"|null)", text)
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
        ps_data = parse_pumpstation_html(ps_htmls[0])

        sig_hits = defaultdict(int)
        sig_files = defaultdict(list)
        for html in test_dir.glob("*.html"):
            text = html.read_text(errors="replace")
            for sig_name, sig_re in SIGNATURES.items():
                hits = len(sig_re.findall(text))
                if hits > 0:
                    sig_hits[sig_name] += hits
                    sig_files[sig_name].append(html.name)

        agent_facts = {}
        for role in ["judge", "dispatch", "gather", "analyze", "report", "path-safety"]:
            role_html = test_dir / f"agent-{role}.html"
            if role_html.exists():
                agent_facts[role] = parse_agent_html(role_html)

        rows.append({
            "test": test_name, "kind": meta.get("kind", "?"),
            "ps_data": ps_data, "sig_hits": dict(sig_hits),
            "sig_files": dict(sig_files), "agent_facts": agent_facts,
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
        print(f"  exit: completed={ps.get('completed_exitReason', '?')} "
              f"failed={ps.get('failed_error', '?')}/{ps.get('failed_exitReason', '?')}")
        print(f"  path_sequence: {ps.get('selected_path_sequence', [])[:10]}")
        if ps.get("final_output_preview"):
            print(f"  final_output_preview: {ps['final_output_preview']}")
        sigs = row["sig_hits"]
        if sigs:
            print(f"  SIGNALS:")
            for sig, count in sorted(sigs.items()):
                files = ",".join(set(row["sig_files"][sig]))
                print(f"    {sig}: {count} hit(s) in [{files}]")
        for role, facts in row["agent_facts"].items():
            print(f"  agent-{role}: prompts={facts.get('prompt_count', 0)} "
                  f"judge_verdicts={facts.get('judge_verdicts', [])[:8]} "
                  f"dispatch_decisions={facts.get('dispatch_decisions', [])[:8]} "
                  f"path_safety={facts.get('path_safety_decisions', [])[:8]} "
                  f"rationale={facts.get('rationale_field', [])[:5]}")


if __name__ == "__main__":
    main()
