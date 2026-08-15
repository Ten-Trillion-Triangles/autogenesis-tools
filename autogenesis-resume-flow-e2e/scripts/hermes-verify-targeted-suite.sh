#!/usr/bin/env bash
# Ad-hoc verification: run a single targeted test suite (or a small set
# of suites) without the full build-chain warmup. Receipts: grep the
# JUnit XML test counts for each suite; exit non-zero on any failure.
#
# Usage: hermes-verify-targeted-suite.sh SUITE1 [SUITE2 ...]
# Example: hermes-verify-targeted-suite.sh \
#     "MapUploadGatePackContentValidationTest" \
#     "MapUploadGateDownsamplePreFlightTest" \
#     "MapUploadGateTest"
#
# The script lives at /tmp/hermes-verify-targeted-suite.sh on the
# operator's machine; copy to a session-specific name when running
# (e.g. /tmp/hermes-verify-<feature>-<date>.sh) so the receipt trail
# is identifiable.
set -u

if [ $# -eq 0 ]; then
  echo "usage: $0 SUITE1 [SUITE2 ...]"
  exit 2
fi

cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis || exit 99

# Build the --tests args. Gradle expects --tests 'class.fqn' (a single
# fully-qualified class), so we construct one --tests per suite.
tests_args=()
for suite in "$@"; do
  tests_args+=(--tests "network.${suite}")
done

# Use --no-daemon for the foreground session; the gradle daemon would
# outlive the receipt printout and produce misleading "BUILD FAILED"
# tail-truncation artifacts in the agent's chat history.
gradle :server-extend:test "${tests_args[@]}" --no-daemon 2>&1 | tail -8

status=$?
echo "---"
echo "JUnit receipts:"
for suite in "$@"; do
  xml="/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/server-extend/build/test-results/test/TEST-network.${suite}.xml"
  if [ -f "$xml" ]; then
    grep -E 'tests=|failure message' "$xml" | head -2
    echo "  (file: $xml)"
  else
    echo "  $xml MISSING"
  fi
done

exit $status
