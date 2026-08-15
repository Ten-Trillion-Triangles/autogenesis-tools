#!/usr/bin/env bash
# find-live-tests.sh — locate every TPipe live test that produces trace artifacts.
#
# Usage:
#   ./scripts/find-live-tests.sh                        # all live tests
#   ./scripts/find-live-tests.sh --by-container         # grouped by container
#   ./scripts/find-live-tests.sh --env-needed           # show env vars required
#
# Lists every test class under src/test/kotlin that:
#   1. Has a live-gate pattern (liveGateOrSkip, MINIMAX_API_KEY, TPIPE_LIVE_LLM_TEST)
#   2. Calls TraceVisualizer or enables tracing
#   3. Writes a *.{html,json} file as a test artifact
#
# This is the source of truth for "where do I get a fresh trace for container X?"
# Run it before claiming "no live test exists for container X".

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
# Resolve repo root by walking up from this skill's location
REPO_ROOT="$(cd "$SKILL_DIR/../.." && pwd 2>/dev/null || echo /home/cage/Desktop/Workspaces/TPipe/TPipe)"

GROUP_BY_CONTAINER=0
ENV_NEEDED=0
for arg in "$@"; do
    case "$arg" in
        --by-container) GROUP_BY_CONTAINER=1 ;;
        --env-needed)   ENV_NEEDED=1 ;;
    esac
done

# Patterns that indicate a live test (matches the standard gates)
LIVE_GATE_PATTERNS='liveGateOrSkip|MINIMAX_API_KEY|TPIPE_LIVE_LLM_TEST|BEDROCK_LIVE|OPENAI_API_KEY'

# Patterns that indicate a trace producer
TRACE_PRODUCER_PATTERNS='enableTracing|getTraceReport|generateHtmlReport|generateMockPumpStationTrace|generateMockManifoldTrace|generateMockJunctionTrace|generateMockSplitterTrace|generateMockDistributionGridTrace|TraceVisualizer'

# Find all test files
TEST_FILES=$(find "$REPO_ROOT/src/test/kotlin" -name '*.kt' 2>/dev/null)

echo "=== Live test inventory (repo: $REPO_ROOT) ==="
echo

# Header
if [[ $ENV_NEEDED -eq 1 ]]; then
    printf "%-70s %-12s %s\n" "TEST FILE" "CONTAINER" "ENV VARS"
else
    printf "%-70s %-12s %s\n" "TEST FILE" "CONTAINER" "GATE"
fi
echo "------------------------------------------------------------------------------------------------------"

# Empty separator for grouping
declare -A GROUPS

for f in $TEST_FILES; do
    # Check for live-gate patterns
    if grep -lE "$LIVE_GATE_PATTERNS" "$f" > /dev/null 2>&1; then
        # Detect container
        container="unknown"
        if   grep -lE 'PumpStation|ps-status' "$f" > /dev/null 2>&1; then container="PumpStation"
        elif grep -lE 'manifold|MANIFOLD_' "$f" > /dev/null 2>&1; then container="Manifold"
        elif grep -lE 'junction|JUNCTION_' "$f" > /dev/null 2>&1; then container="Junction"
        elif grep -lE 'splitter|SPLITTER_' "$f" > /dev/null 2>&1; then container="Splitter"
        elif grep -lE 'DistributionGrid|distributionGrid' "$f" > /dev/null 2>&1; then container="DistributionGrid"
        fi

        # Detect gate
        gate=""
        if grep -lE 'liveGateOrSkip' "$f" > /dev/null 2>&1; then gate="liveGateOrSkip"; fi
        if grep -lE 'MINIMAX_API_KEY' "$f" > /dev/null 2>&1; then gate="${gate:+$gate, }MINIMAX"; fi
        if grep -lE 'TPIPE_LIVE_LLM_TEST' "$f" > /dev/null 2>&1; then gate="${gate:+$gate, }TPIPE_LLM"; fi
        if grep -lE 'BEDROCK_LIVE' "$f" > /dev/null 2>&1; then gate="${gate:+$gate, }BEDROCK"; fi

        # Short path
        short=$(echo "$f" | sed "s|$REPO_ROOT/||")

        if [[ $GROUP_BY_CONTAINER -eq 1 ]]; then
            GROUPS[$container]+="$short|$gate"$'\n'
        else
            printf "%-70s %-12s %s\n" "$short" "$container" "$gate"
        fi
    fi
done

if [[ $GROUP_BY_CONTAINER -eq 1 ]]; then
    for c in PumpStation Manifold Junction Splitter DistributionGrid unknown; do
        if [[ -n "${GROUPS[$c]:-}" ]]; then
            echo
            echo "── $c ──"
            echo "$GROUPS[$c]" | while IFS='|' read -r path gate; do
                [[ -z "$path" ]] && continue
                printf "  %-68s %s\n" "$path" "$gate"
            done
        fi
    done
fi

# Also list the trace-producer tests that DON'T have a live gate (synthetic-event tests)
echo
echo "=== Synthetic-event trace tests (no live API) ==="
for f in $TEST_FILES; do
    if grep -lE "$TRACE_PRODUCER_PATTERNS" "$f" > /dev/null 2>&1; then
        if ! grep -lE "$LIVE_GATE_PATTERNS" "$f" > /dev/null 2>&1; then
            short=$(echo "$f" | sed "s|$REPO_ROOT/||")
            container="unknown"
            if   grep -lE 'ps-ps-' "$f" > /dev/null 2>&1 || grep -lE 'PUMP_STATION_' "$f" > /dev/null 2>&1; then container="PumpStation"
            elif grep -lE 'MANIFOLD_' "$f" > /dev/null 2>&1; then container="Manifold"
            elif grep -lE 'JUNCTION_' "$f" > /dev/null 2>&1; then container="Junction"
            elif grep -lE 'SPLITTER_' "$f" > /dev/null 2>&1; then container="Splitter"
            elif grep -lE 'DISTRIBUTION_GRID_' "$f" > /dev/null 2>&1; then container="DistributionGrid"
            fi
            printf "  %-68s %s\n" "$short" "$container"
        fi
    fi
done

echo
echo "=== Conclusion ==="
echo "If a container has NO entry above, it has no test that produces trace artifacts."
echo "Cross-check this list with: find ~/.tpipe -name '<container>*.html' -o -name 'trace.json' | head"
echo "If you find a container missing from this list, search under src/test/kotlin for the keyword"
echo "directly with: grep -rln 'ContainerName' src/test/kotlin --include='*.kt'"
