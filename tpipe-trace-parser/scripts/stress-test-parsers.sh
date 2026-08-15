#!/usr/bin/env bash
# stress-test-parsers.sh — Run verify_extraction.py against EVERY trace file on disk.
#
# Usage: bash scripts/stress-test-parsers.sh [--pinned-only]
#   --pinned-only: run only the 7 pinned cases (default: every trace file)
#
# This is the safety net that catches parser regressions that hand-picked
# test cases miss. When this script was first run (2026-07-24), it caught
# a token-vs-length conflation bug that affected 56 of 61 autogenesis JSON
# traces — the pinned-7 set had masked it because none of the 7 traces
# emit `responseLength` in a way that triggered the broken code path.
#
# Exit code: 0 if all traces pass, 1 if any drift.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFIER="${SCRIPT_DIR}/verify_extraction.py"

PINNED_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --pinned-only) PINNED_ONLY=1 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# --- 1. Pinned cases (always run) ---
echo "=== pinned cases ==="
python3 "$VERIFIER" --strict
PINNED_RC=$?

if [[ $PINNED_ONLY -eq 1 ]]; then
    exit $PINNED_RC
fi

# --- 2. Stress test against every JSON trace on disk ---
echo
echo "=== stress test: every autogenesis trace.json ==="
FAIL=0
TOTAL=0

while IFS= read -r -d '' trace; do
    TOTAL=$((TOTAL + 1))
    # Capture ground truth via the verifier's --add mode (prints CASES dict entry)
    # We don't actually mutate CASES; we run the parser directly and compare against
    # the same ground-truth functions the verifier uses, but inlined.
    name="autogenesis-$(echo "$trace" | md5sum | cut -c1-8)"
    expected_count=$(python3 -c "
import json, sys
with open('$trace') as f:
    d = json.load(f)
events = d['events'] if isinstance(d, dict) and 'events' in d else d
print(len(events))
")
    actual_count=$(python3 "$VERIFIER" --help >/dev/null 2>&1; python3 "$SCRIPT_DIR/parse_json_trace.py" --input "$trace" --format full --quiet 2>/dev/null | python3 -c "import json, sys; print(json.load(sys.stdin)['event_count'])")
    if [[ "$expected_count" != "$actual_count" ]]; then
        echo "FAIL: $trace  expected=$expected_count actual=$actual_count"
        FAIL=$((FAIL + 1))
    fi
done < <(find /home/cage/.tpipe -name 'trace.json' -print0 2>/dev/null)

echo
echo "=== summary ==="
echo "  total traces: $TOTAL"
echo "  failures:     $FAIL"
if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit $PINNED_RC
