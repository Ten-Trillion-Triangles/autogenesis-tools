#!/usr/bin/env bash
# Run a single JUnit class, capture exit code, parse the JUnit XML, and log a one-liner.
# Source of truth for per-class pass/fail during a TPipe upgrade triage sweep.
#
# Usage:
#   ./run-class.sh <gradle-module> <fully.qualified.ClassName>
# Examples:
#   ./run-class.sh :test com.TTT.Pipeline.JunctionTest
#   ./run-class.sh :TPipe-Bedrock:test bedrockPipe.ConstructPipeTest
#   ./run-class.sh :TPipe-Bedrock:test ComprehensiveBuilderTest    # default-package
#
# Required env gates (set them BEFORE invoking):
#   MINIMAX_API_KEY=sk-stub          # force live tests to skip (liveGateOrSkip returns null)
#   TPIPE_LIVE_LLM_TEST=false        # close the live-test gate explicitly
#   AllowTest=true                   # enable TPipe-Bedrock *LiveTest.kt classes (otherwise silent skip)
#   TPIPE_ALLOW_INSECURE_BASEURL=true  # bypass HTTPS check for tests that boot local HTTP servers
#                                       # (PumpStationF1PathInjectionTest, RunJudgePhaseTest, etc.)
#
# Output:
#   - One line per class appended to per-class.log (path: tests/skipped/failures/errors)
#   - If failures>0 or errors>0, the <testcase>/<failure>/<error> lines from the XML are dumped
#   - If no XML is produced (quarantined test, no-source filter match, etc.), the tail of
#     gradle-raw.log is dumped instead
#
# Pitfall:
#   `./gradlew ... | tail` masks gradle's exit code as $?. Use a single assignment (no pipe)
#   OR use ${PIPESTATUS[0]} if you must pipe. Anything else reports exit=0 for failures.
set -u
MODULE="$1"
FQCN="$2"
SESSION_DIR="${SESSION_DIR:-.hermes/test-results/per-class-sweep}"
LOG="$SESSION_DIR/per-class.log"
GRADLE_LOG="$SESSION_DIR/gradle-raw.log"
mkdir -p "$SESSION_DIR"

case "$MODULE" in
  ":test") XML="build/test-results/test/TEST-${FQCN}.xml" ;;
  *)
    MOD_DIR="${MODULE#:}"; MOD_DIR="${MOD_DIR%:test}"
    XML="${MOD_DIR}/build/test-results/test/TEST-${FQCN}.xml"
    ;;
esac

START=$(date +%s)
./gradlew "${MODULE}" --tests "${FQCN}" --no-daemon --console=plain > "${GRADLE_LOG}" 2>&1
EXIT=$?
END=$(date +%s)
ELAPSED=$((END - START))

if [ ! -f "$XML" ]; then
  echo "${FQCN} | module=${MODULE} | NO_XML | exit=${EXIT} | ${ELAPSED}s" >> "$LOG"
  echo "  --- gradle tail ---" >> "$LOG"
  tail -10 "${GRADLE_LOG}" >> "$LOG" 2>/dev/null
  echo "" >> "$LOG"
  exit 0
fi

SUMMARY=$(head -2 "$XML" | grep -oE 'tests="[0-9]+" skipped="[0-9]+" failures="[0-9]+" errors="[0-9]+"' | head -1)
echo "${FQCN} | module=${MODULE} | ${SUMMARY} | exit=${EXIT} | ${ELAPSED}s" >> "$LOG"

if echo "$SUMMARY" | grep -qE 'failures="[1-9]|errors="[1-9]'; then
  echo "  --- failure detail ---" >> "$LOG"
  grep -E '(<testcase|<failure|<error)' "$XML" | head -60 >> "$LOG"
  echo "" >> "$LOG"
fi