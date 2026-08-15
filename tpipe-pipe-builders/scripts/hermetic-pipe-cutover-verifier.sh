#!/usr/bin/env bash
# Hermetic ad-hoc verifier for post-edit pipe-family cutovers.
#
# Copy this script to /tmp/hermes-verify-<topic>.sh, edit the CHECK sections
# to anchor on the cutover's specific files/lines, and run. The script:
#   - Stages into a mktemp workspace (auto-cleaned on EXIT)
#   - Writes per-check trace to /tmp/hermes-verify-<topic>.log
#   - Writes human-readable summary to /tmp/hermes-verify-<topic>.summary.txt
#   - Authoritative verification source: JUnit XML at server/build/test-results/test/
#     (run targeted tests with `./gradlew :server:test --tests "<fqcn>"` first)
#   - PASS markers are timestamp-prefixed; FAIL exits non-zero on first failure
#
# Use this for any cross-file cutover where the existing test surface
# doesn't pin the surface you actually changed (e.g. parent/child pipe
# alignment where pipe *types* are tested but reasoning pipe *models*
# aren't).

set -u

TOPIC="${TOPIC:-cutover}"  # override at invocation: TOPIC=palmyrax5-cutover bash this-script.sh
WORK="$(mktemp -d -t hermes-verify-${TOPIC}.XXXXXX)"
SUMMARY="/tmp/hermes-verify-${TOPIC}.summary.txt"
LOG="/tmp/hermes-verify-${TOPIC}.log"
ROOT="${ROOT:-/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis}"

cleanup() {
    rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

pass() { printf '%s PASS: %s\n' "$(date +%H:%M:%S)" "$1" | tee -a "$LOG"; }
fail() { printf '%s FAIL: %s\n' "$(date +%H:%M:%S)" "$1" | tee -a "$LOG"; exit 1; }

: > "$LOG"
: > "$SUMMARY"

cd "$ROOT" || fail "could not cd to $ROOT"

#-------------------------------------------------------------------------------
# CHECK TEMPLATES — replace each with a real check for your cutover.
# Each check should be a single shell command + a PASS/FAIL branch.
# See references/parent-child-pipe-alignment.md for the 7-site example set
# the palmyrax5 cutover used.
#-------------------------------------------------------------------------------

# Example: detect misaligned reasoning-pipe sites in agent/builders.
# A site is misaligned when its inner authorBuilder(...) call has no
# model= kwarg AND no .apply { setModel(...) } block.
check_alignment() {
    local file="$1" line="$2" parent_model="$3" parent_budget="$4" name="$5"
    if sed -n "${line},$((line+12))p" "$file" \
        | grep -q "setModel(BedrockConfig.${parent_model})" \
       && sed -n "${line},$((line+12))p" "$file" \
        | grep -q "setTokenBudget(BedrockConfig.${parent_budget})"; then
        pass "  $name aligned at $file:$line"
    else
        fail "  $name NOT aligned at $file:$line — expected setModel(${parent_model}) + setTokenBudget(${parent_budget}) within 12 lines"
    fi
}

# Example site list — replace with sites from your cutover.
# check_alignment path/to/file.kt LINE parent-model parent-budget "name"
# check_alignment server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt 200 qwenCoder30B generativeBudgetSettings "writerAgent guidePipe"
# check_alignment server/src/main/kotlin/agent/builders/writingAgent/writerAgent.kt 445 qwenCoder30B generativeBudgetSettings "writerAgent selectionPipe"

#-------------------------------------------------------------------------------
# JUnit XML authoritative check — read the targeted test XML and assert
# tests=N failures=0 errors=0. Requires a `./gradlew :server:test` invocation
# to have produced the XML first.
#-------------------------------------------------------------------------------
junit_check() {
    local xml="$1" expected="$2"
    local summary_line="$(grep -oE 'tests="[0-9]+" skipped="[0-9]+" failures="[0-9]+" errors="[0-9]+"' "$xml" | head -1)"
    if [[ -z "$summary_line" ]]; then
        fail "JUnit XML not found or unreadable: $xml"
    fi
    local actual="$summary_line"
    if [[ "$actual" == "$expected" ]]; then
        pass "JUnit XML $xml: $actual"
    else
        echo "Expected: $expected" | tee -a "$LOG"
        echo "Got:      $actual"   | tee -a "$LOG"
        fail "JUnit XML assertion failed for $xml"
    fi
}

# Example invocation:
# junit_check server/build/test-results/test/TEST-agent.builders.PalmyraX5ToG31bMigrationTest.xml \
#             'tests="7" skipped="0" failures="0" errors="0"'

#-------------------------------------------------------------------------------
# Final: write summary with all pass markers.
#-------------------------------------------------------------------------------
{
    echo "Hermetic verification summary — topic: $TOPIC"
    echo "============================================================"
    echo "Root: $ROOT"
    echo "Run:  $(date -Iseconds)"
    echo
    echo "Per-check status:"
    grep -E '^[0-9:]+ PASS:|^[0-9:]+ FAIL:' "$LOG" | sed 's/^/  /'
} > "$SUMMARY"

cat "$SUMMARY"