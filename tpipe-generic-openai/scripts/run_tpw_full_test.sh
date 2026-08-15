#!/bin/bash
# Drive every /help command in a TPipeWriter-style TUI via tmux and check
# the resulting trace for failures. The pattern that ACTUALLY works for
# verification — spot-checking 4 of 24 commands misses real regressions.
#
# Usage: /tmp/run_tpw_full_test.sh
# Prerequisites: tmux, MINIMAX_API_KEY env var (or per-provider equivalent),
#                the TUI binary at build/libs/<app>-1.0.0-all.jar
#
# What it does:
#   1. Restarts the TUI fresh (kills any prior tmux session for this app)
#   2. Drives each command in /help sequentially via `tmux send-keys`
#   3. Waits N seconds per command (longer for LLM-driven ones)
#   4. Parses the trace file from ~/.TPipe-Debug/traces/*.html
#   5. Reports failures and per-test results
#
# Test it against TPipeWriter (GenericAI branch):
#   cd /home/cage/Desktop/Workspaces/TPipeWriter
#   MINIMAX_API_KEY="$AUXILIARY_VISION_API_KEY" \
#       ./gradlew shadowJar
#   MINIMAX_API_KEY="$AUXILIARY_VISION_API_KEY" \
#       /tmp/run_tpw_full_test.sh
#   python3 ~/.hermes/skills/software-development/tpipe-trace-parser/scripts/parse_html_trace.py \
#       --input ~/.TPipe-Debug/traces/$(ls -t ~/.TPipe-Debug/traces/ | head -1) \
#       --output /tmp/trace.json
#   python3 ~/.hermes/skills/software-development/tpipe-trace-parser/scripts/generate_report.py \
#       --input /tmp/trace.json --output /tmp/report.md

set -e

# Find the latest trace file (filename includes a per-process hash)
TRACE_DIR="$HOME/.TPipe-Debug/traces"
TRACE=$(ls -t "$TRACE_DIR"/trace-*.html 2>/dev/null | head -1)
[ -z "$TRACE" ] && { echo "No trace file found in $TRACE_DIR — is the TUI running?"; exit 1; }
TRACE_BASE=$(basename "$TRACE" .html)
echo "Trace file: $TRACE"

# Find tmux session
SESSION="tpipe"
tmux kill-session -t "$SESSION" 2>/dev/null || true
sleep 2
tmux new-session -d -s "$SESSION" -x 240 -y 60
sleep 1

# Launch the TUI (edit this line for your app)
tmux send-keys -t "$SESSION" 'cd /home/cage/Desktop/Workspaces/TPipeWriter && MINIMAX_API_KEY="$AUXILIARY_VISION_API_KEY" ./run.sh' Enter
sleep 12

# Wait for the prompt
PROMPT=$(tmux capture-pane -t "$SESSION" -p -S -50 | grep -c "\[Writer\]>")
if [ "$PROMPT" -eq 0 ]; then
    echo "TUI did not start cleanly. Capture:"
    tmux capture-pane -t "$SESSION" -p -S -100 | tail -20
    exit 1
fi

# Per-command tests
declare -a RESULTS

run_test() {
    local label="$1"
    local cmd="$2"
    local wait="${3:-30}"

    local before_size=$(stat -c%s "$TRACE" 2>/dev/null || echo 0)
    local before_fail=$(grep -cE 'PIPE_FAILURE|API_CALL_FAILURE|VALIDATION_FAILURE|EXCEPTION' "$TRACE" 2>/dev/null || echo 0)

    echo ""
    echo "================================================"
    echo "TEST: $label"
    echo "CMD:  $cmd"
    echo "WAIT: ${wait}s"
    echo "================================================"

    tmux send-keys -t "$SESSION" "$cmd" Enter
    sleep "$wait"

    local after_size=$(stat -c%s "$TRACE" 2>/dev/null || echo 0)
    local after_fail=$(grep -cE 'PIPE_FAILURE|API_CALL_FAILURE|VALIDATION_FAILURE|EXCEPTION' "$TRACE" 2>/dev/null || echo 0)

    local delta=$((after_size - before_size))
    local new_fails=$((after_fail - before_fail))

    echo "Trace grew by: ${delta} bytes | New failures: ${new_fails}"

    if [ "$new_fails" -gt 0 ]; then
        echo "*** FAILURE DETECTED ***"
        grep -B2 -A4 -E 'PIPE_FAILURE|API_CALL_FAILURE|VALIDATION_FAILURE' "$TRACE" | tail -30
    fi

    RESULTS+=("$label: new_fails=$new_fails trace_delta=$delta")
}

# /help shows the available commands — base for our enumeration
run_test "01 /help" "/help" 3

# Short commands
run_test "02 /style" "/style" 3
run_test "03 /settings menu" "/settings" 3
# Provide /settings values
tmux send-keys -t "$SESSION" 'existing test style' Enter; sleep 1
tmux send-keys -t "$SESSION" '3500' Enter; sleep 1
tmux send-keys -t "$SESSION" 'y' Enter; sleep 4

# /llm-settings sub-shell
run_test "04 /llm-settings" "/llm-settings" 4
run_test "04a llm status" "s" 2
run_test "04b llm back" "back" 2

# LLM-driven commands — give them time
run_test "05 /write prompt" "/write A quiet forest at dawn." 60
run_test "06 /idea prompt" "/idea mystery in space" 60
run_test "07 /chat prompt" "/chat Tell me about the setting." 60

# Sub-shells
run_test "08 /character sub-shell" "/character" 4
run_test "08a /character back" "/exit" 2
run_test "09 /lorebook sub-shell" "/lorebook" 4
run_test "09a /lorebook back" "/exit" 2
run_test "10 /summary sub-shell" "/summary" 4

# State management
run_test "11 /save" "/save" 5
run_test "12 /export" "/export" 5
tmux send-keys -t "$SESSION" "load" Enter  # filename for export
run_test "13 /load" "/load" 5
tmux send-keys -t "$SESSION" "load" Enter  # filename for load
run_test "14 /clear" "/clear" 5
run_test "15 /clear-chat" "/clear-chat" 3
run_test "16 /test" "/test" 10

# More sub-shells
run_test "17 /lore sub-shell" "/lore" 4
run_test "17a /lore back" "/exit" 2

# Long-running
run_test "22 /rewrite" "/rewrite" 60
run_test "23 /guide sub-shell" "/guide" 4
run_test "23a /guide back" "/exit" 2

# /import-lorebook and /import-nai require pre-existing JSON files — skip
# unless you have fixtures in /home/cage/TPipeWriter/

echo ""
echo "================================================"
echo "FINAL TRACE ANALYSIS"
echo "================================================"
TOTAL_FAILS=$(grep -cE 'PIPE_FAILURE|API_CALL_FAILURE|VALIDATION_FAILURE|EXCEPTION' "$TRACE" 2>/dev/null || echo 0)
TOTAL_EVENTS=$(grep -cE 'id="trace-event-' "$TRACE" 2>/dev/null || echo 0)
echo "Total events: $TOTAL_EVENTS"
echo "Total failures: $TOTAL_FAILS"
echo ""
echo "Per-test results:"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done

# Don't kill tmux — leave it running so the user can inspect
echo ""
echo "TUI session '$SESSION' left running for manual inspection."
echo "tmux attach -t $SESSION"
