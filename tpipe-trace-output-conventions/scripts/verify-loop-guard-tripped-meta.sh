#!/usr/bin/env bash
# Ad-hoc verification probe for the LoopGuardTripped event meta.
#
# Reads the most recent pumpstation HTML under
# $HOME/.tpipe/debug/trace/loop-guard-meta-keys/ (the canonical resolver output
# from TPipeConfig.getTraceDir() + "/loop-guard-meta-keys") and asserts the
# three new meta keys (metric, observed, limit) are present in the
# PUMP_STATION_LOOP_GUARD_TRIPPED event block, alongside the legacy packed
# `detail` string for back-compat.
#
# This is a probe, NOT a test-suite replacement. Pass criteria:
#
#   - metric:<value>      present (the new field name)
#   - observed:<int>      present (numeric value)
#   - limit:<int>         present (numeric value)
#   - detail:<packed>     still present (legacy back-compat)
#   - guard / pathName    preserved (existing keys)
#
# Usage: bash verify-loop-guard-tripped-meta.sh
# Exit:  0 if all keys present, 1 if any key missing, 2 if no HTML found.
#
# The PumpStationGapCoverageLiveTest.stubLoopGuard_emitsSeparateMetricAndLimitMetaKeys
# test (in the TPipe test suite) produces the trace this probe reads. Run
# that test first to populate the trace artifact. Per the test-hygiene rule
# in the parent skill, this script also asserts the trace landed at the
# canonical resolver output, not at a legacy `~/.TPipe-Debug/` path.

set -euo pipefail
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

TRACE_DIR="$HOME/.tpipe/debug/trace/loop-guard-meta-keys"

if [[ ! -d "$TRACE_DIR" ]]; then
  fail "trace dir $TRACE_DIR does not exist; run PumpStationGapCoverageLiveTest first"
fi

# Pick the most recent HTML. TraceVisualizer writes per-runId, so sort-by-name
# is timestamp-ordered and `ls -t` picks the newest.
HTML=$(ls -t "$TRACE_DIR"/pumpstation-ps-*.html 2>/dev/null | head -1)
if [[ -z "$HTML" ]]; then
  fail "no pumpstation HTML files in $TRACE_DIR; run stubLoopGuard test first"
fi

# Locate the line containing PUMP_STATION_LOOP_GUARD_TRIPPED. The
# TraceVisualizer renders each event on a single line, so this gives us the
# full event block in one awk/sed step.
line=$(grep -nE "PUMP_STATION_LOOP_GUARD_TRIPPED" "$HTML" | head -1 | cut -d: -f1)
if [[ -z "$line" ]]; then
  fail "no PUMP_STATION_LOOP_GUARD_TRIPPED event found in $HTML"
fi

# Extract the LoopGuardTripped meta block from that single line.
# Each meta key renders as
#   <span class='ps-meta-key'>KEY:</span><span class='ps-meta-val'>VAL</span>
#
# NOTE: use the negated char class [^"] to avoid catastrophic backtracking
# on long HTML lines. Naive `.` (greedy dot) in `.{0,N}` triggers regex
# backtracking hangs when the input line is 1500-1600 chars and N >= 500.
# This was the dominant debugging trap on 2026-07-10. See the matching
# pitfall in the parent SKILL.md.
block=$(sed -n "${line}p" "$HTML" | grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED[^\"]{0,900}")
if [[ -z "$block" ]]; then
  fail "could not extract LoopGuardTripped block from line $line of $HTML"
fi

# Verify the three new keys are present with their values.
for key in metric observed limit; do
  if echo "$block" | grep -qE "ps-meta-key'>${key}:</span><span class='ps-meta-val'>[^<]+"; then
    val=$(echo "$block" | grep -oE "ps-meta-key'>${key}:</span><span class='ps-meta-val'>[^<]+" \
            | head -1 | sed -E "s/.*ps-meta-val'>([^<]+)/\1/")
    pass "key '${key}' present (value: ${val})"
  else
    fail "key '${key}' missing from PUMP_STATION_LOOP_GUARD_TRIPPED meta block"
  fi
done

# Backward-compat: legacy packed detail string still emitted.
if echo "$block" | grep -qE "ps-meta-key'>detail:</span>"; then
  pass "legacy 'detail' key still emitted (back-compat)"
else
  echo "WARN: legacy 'detail' key absent (may be expected if removed)" >&2
fi

# Sanity: existing keys still emitted.
for key in guard pathName; do
  if ! echo "$block" | grep -qE "ps-meta-key'>${key}:</span>"; then
    fail "existing key '${key}' missing"
  fi
done
pass "existing keys (guard, pathName) preserved"

echo
echo "Verified HTML: $HTML"
echo "Verified line: $line"
echo "Verification complete."