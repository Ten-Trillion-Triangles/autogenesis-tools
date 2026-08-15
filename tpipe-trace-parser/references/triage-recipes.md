# Trace triage recipes — concrete commands for common failure modes

Each recipe is a single command block that solves one specific "the test passed but..." complaint. Recipes are ordered roughly by what an operator asks first.

## Recipe 1: "Tests passed but tokens burned the budget"

**Symptom**: 13 tests green, but the bill is 4x what you'd expect. PumpStation ran 3 turns instead of 1, or the judge kept looping.

**Command**:
```bash
python3 scripts/extract_pipeline.py --dir ~/.tpipe/debug/trace/<test-name>/ --tokens-only
```

**Expected output**:
```json
{
  "inputTokens": {"total": 25513, "count": 17},
  "outputTokens": {"total": 7093, "count": 25},
  "totalTokens": {"total": 31097, "count": 17}
}
```

**Interpretation**:
- `count` is the number of events that emitted that key. A 3-turn PumpStation emits 9 JudgeCompleted events → `totalTokens.count == 9`.
- `total` is the sum across all events. That's your actual spend.
- If `inputTokens` is 5x the expected, the judge path is looping — check `metadata.fullPrompt` on the path's `PIPE_START` event to see what's being re-fed.

**Next command** (drill into per-pipe):
```bash
python3 scripts/extract_pipeline.py --dir ~/.tpipe/debug/trace/<test-name>/ --output full.json
jq '.per_file[0].events[] | select(.eventType=="API_CALL_SUCCESS") | {pipeName, "in": .metadata.inputTokens, "out": .metadata.outputTokens}' full.json
```

## Recipe 2: "Judge always says isComplete=true"

**Symptom**: PumpStation runs 1 turn, judge declines, dispatch picks the same path, repeat. Total iterations exceed expected.

**Command**:
```bash
python3 scripts/parse_html_trace.py --input ~/.tpipe/debug/trace/<test>/pumpstation-ps-*.html --format summary | grep -i judge
```

**Expected output** (one line per judge event):
```
PUMP_STATION_JUDGE_STARTED              turn=  1 status=SUCCESS  judgeRunMode=Always
PUMP_STATION_JUDGE_COMPLETED            turn=  1 status=SUCCESS  inputTokens=1175 outputTokens=137 totalTokens=1312 isComplete=false shouldTerminate=false
PUMP_STATION_JUDGE_STARTED              turn=  2 status=SUCCESS  judgeRunMode=Always
PUMP_STATION_JUDGE_COMPLETED            turn=  2 status=SUCCESS  inputTokens=2235 outputTokens=155 totalTokens=2390 isComplete=false shouldTerminate=false
```

**Interpretation**:
- `isComplete=false` everywhere → judge is correctly declining.
- `judgeRunMode=Always` → the judge runs every turn (vs `FlagTriggered` which only runs when a flag is set).
- If `isComplete=true` is appearing where it shouldn't, look at the `contentPreview` JSON in the `JUDGE_COMPLETED` event's metadata — the verdict structure is there.

**Next command** (extract the verdict for the failing turn):
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --output full.json
jq '.events[] | select(.eventType=="PUMP_STATION_JUDGE_COMPLETED" and .turnIndex==2) | .metadata.contentPreview' full.json
```

The `contentPreview` is a JSON-encoded verdict with fields like `isComplete`, `shouldTerminate`, `reasoning`. Use this to see WHY the judge said what it said.

## Recipe 3: "Loop guard tripped"

**Symptom**: PumpStation ran for 90 seconds, then `PUMP_STATION_LOOP_GUARD_TRIPPED` appeared. The trace shows the same path executing repeatedly.

**Command**:
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --format summary | grep -E "PATH_(STARTED|FAILED|COMPLETED)"
```

**Expected output**:
```
PUMP_STATION_PATH_SELECTED    turn=  1 status=INFO     pathName=gather riskLevel=Low
PUMP_STATION_PATH_STARTED     turn=  1 status=SUCCESS  pathName=gather riskLevel=Low
PUMP_STATION_PATH_COMPLETED   turn=  1 status=SUCCESS  inputTokens=46 outputTokens=292 totalTokens=338 pathName=gather riskLevel=Low
PUMP_STATION_PATH_STARTED     turn=  1 status=SUCCESS  pathName=dispatch riskLevel=Low
PUMP_STATION_PATH_STARTED     turn=  1 status=SUCCESS  pathName=dispatch riskLevel=Low
PUMP_STATION_PATH_STARTED     turn=  1 status=SUCCESS  pathName=dispatch riskLevel=Low
PUMP_STATION_LOOP_GUARD_TRIPPED  turn=  1 status=FAILURE
```

**Interpretation**:
- Multiple `PATH_STARTED` events with the same `pathName` (e.g. `dispatch`) inside a single turn = the path is being re-invoked within a turn.
- The `PUMP_STATION_LOOP_GUARD_TRIPPED` event has metadata fields `metric`, `observed`, `limit` (after the v1.7 fix) or `detail` (legacy).

**Next command** (extract the loop guard details):
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --output full.json
jq '.events[] | select(.eventType=="PUMP_STATION_LOOP_GUARD_TRIPPED") | .metadata' full.json
```

## Recipe 4: "What did the model actually see on this prompt?"

**Symptom**: Operator wants to know the full prompt sent to the LLM for a specific call.

**Command** (JSON trace with fullPrompt):
```bash
python3 scripts/parse_json_trace.py --input path/to/trace.json --format events | jq '.[] | select(.eventType=="PIPE_START") | {pipeName, fullPromptLen: (.metadata.fullPrompt | length // 0)}'
```

**Command** (HTML trace with input content):
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --output full.json
jq '.events[] | select(.eventType=="PIPE_START") | {pipeName, inputLen: (.contentBlocks[] | select(.label | contains("Input")) | .text | length)}' full.json
```

**Pitfall**: `inputText` (on `API_CALL_START`) covers only 0-14% of the prompt for most pipes. `fullPrompt` (on `PIPE_START`) covers the full prompt. Use `fullPrompt` whenever available. See `references/autogenesis-inputtext-coverage-pitfalls.md`.

## Recipe 5: "Per-pipe token breakdown"

**Symptom**: Operator wants to know which pipe (judge, dispatch, gather, etc.) consumed the most tokens.

**Command**:
```bash
python3 scripts/parse_json_trace.py --input path/to/trace.json --format per_pipe
```

**Expected output**:
```json
{
  "judge":             {"event_count": 18, "event_types": [...], "tokens": {"inputTokens": 4031, "outputTokens": 917, "totalTokens": 4703}},
  "dispatch":          {"event_count": 18, "event_types": [...], "tokens": {"inputTokens": 5610, "outputTokens": 1233, "totalTokens": 6626}},
  "gather":            {"event_count": 18, "event_types": [...], "tokens": {"inputTokens": 102, "outputTokens": 1613, "totalTokens": 1161}},
  "report":            {"event_count": 18, "event_types": [...], "tokens": {"inputTokens": 132, "outputTokens": 1785, "totalTokens": 1424}}
}
```

**Cross-validation invariant**: sum of per-pipe tokens = aggregate token totals. The parser prints this in `--tokens-only` mode.

## Recipe 6: "Cross-pipe runtime safety events"

**Symptom**: Operator wants to know if the trace captured `KILLSWITCH_CHECK` (token budget enforcement) or `PUMP_STATION_CONTEXT_BLOWOUT_DETECTED`.

**Command**:
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --output full.json
jq '[.events[] | select(.eventType | IN("KILLSWITCH_CHECK", "KILLSWITCH_TRIPPED", "PUMP_STATION_CONTEXT_BLOWOUT_DETECTED", "PUMP_STATION_INTERRUPT_OVERFLOW_DROPPED", "PUMP_STATION_HARNESS_WARNING"))] | length' full.json
```

**Note**: `KILLSWITCH_CHECK` is excluded from the TOKEN TOTALS card in the visualizer because it reports cumulative-AT-check-time, not actual spend. The actual token spend is in `JUDGE_COMPLETED` / `DISPATCH_COMPLETED` / `PATH_COMPLETED` events.

## Recipe 7: "Run status summary for a live test"

**Symptom**: 20 test files in a directory, want one-line-per-file status.

**Command**:
```bash
python3 scripts/extract_pipeline.py --dir ~/.tpipe/debug/trace/<test-name>/ --quiet 2>&1 | head -20
```

**Expected output**:
```
=== extract_pipeline: /home/cage/.tpipe/debug/trace/foo ===
  files: scanned=5 parsed=5 failed=0
  formats: {'standard_pipeline': 4, 'pumpstation': 1}
  run_statuses: {'completed': 1}
  tokens (across all files):
    inputTokens               total=  25513 count=17
    outputTokens              total=   7093 count=25
    totalTokens               total=  31097 count=17
```

If `failed > 0`, the per-file error message will tell you which trace failed to parse and why.

## Recipe 8: "Capture a new ground-truth case"

**Symptom**: A new trace format variant appears (e.g. a new container added a new event type), and we want to pin it so future regressions are caught.

**Command**:
```bash
python3 scripts/verify_extraction.py --add my-new-case /path/to/new-trace.html
```

This prints a JSON snippet like:
```json
{
  "my-new-case": {
    "path": "/path/to/new-trace.html",
    "kind": "html",
    "expect_event_count": 42,
    "expect_format": "pumpstation",
    "expect_token_totals": {...},
    "expect_run_id": "ps-...",
    "expect_run_status": "...",
    "expect_event_types": [...]
  }
}
```

Paste this into the `CASES` dict in `scripts/verify_extraction.py`. From now on, every `--strict` run verifies this case.

## Recipe 9: "Validate before deploying a parser change"

**Symptom**: Operator edits `parse_html_trace.py` or `parse_json_trace.py`. Need to verify nothing regressed.

**Command**:
```bash
python3 scripts/verify_extraction.py --strict
```

**Expected output**:
```
Ran 7 case(s); 0 failure(s)
exit: 0
```

**Stress-test (covers all 61 autogenesis traces)**:
```bash
bash scripts/stress-test-parsers.sh
```

If pinned-7 passes but stress-test fails, the stress test surfaced a bug class that pinned-7 doesn't cover. Add the failing trace as a new pinned case via `--add`.

## Recipe 10: "Why is the trace file empty?"

**Symptom**: `extract_pipeline.py` reports `files: scanned=N parsed=N` but the events array is empty.

**Command**:
```bash
python3 scripts/parse_html_trace.py --input path/to/trace.html --format summary | head -10
```

If the output is `=== TPipe Execution Trace ===` followed by nothing, the trace file was written but no events were emitted. Common causes:
- `PipeTracer.enable()` was never called (TraceConfig.enabled was false)
- `PipeTracer.startTrace(pipelineId)` was never called
- The pipeline crashed before any events fired

Check the producer side (`tpipe-trace-output-conventions`) for the setup.
