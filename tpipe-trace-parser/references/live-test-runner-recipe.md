# PumpStation Live Test Runner Recipe

Distilled from the 2026-07-23 steering-feature live-test verification session.
Captures the canonical pattern for running `PumpStation*LiveTest` classes end-to-end
and verifying that every trace lands at the correct folder under `~/.tpipe/debug/trace/`.

## The two-gate pattern

Every `PumpStation*LiveTest` class has a `@BeforeAll setup()` that silently skips the
test unless **both** env vars are set:

```kotlin
@BeforeAll
fun setup() {
    if (System.getenv("TPIPE_LIVE_LLM_TEST") != "true") return
    val key = System.getenv("MINIMAX_API_KEY")
    if (key.isNullOrBlank()) return
    GenericOpenAIEnv.setApiKey(key)
    apiKeyCache = key
    ...
}
```

If either is missing, the test silently returns in ~0.001s (the early-exit path).
JVM XML will show "passing" but no LLM was called. **Always set both gates.**

The strict gate for `live_*_research*` tests is `liveGateOrSkip()` which rejects
`sk-stub` keys. Stubs use `envGateOrSkip()` (any non-blank key) because they hit
`StubOpenAIServer` on localhost, never the real MiniMax endpoint.

## API key extraction from `.bashrc`

The `MINIMAX_API_KEY` export line uses double-quotes:

```bash
export MINIMAX_API_KEY="sk-cp-...REDACTED"
```

A plain `source ~/.bashrc` does NOT export it into a subshell (the export
succeeds but the subshell may not inherit). Use this extraction:

```bash
KEY=$(grep "MINIMAX_API_KEY" ~/.bashrc | head -1 | sed -E 's/^export MINIMAX_API_KEY="(.+)"$/\1/')
export MINIMAX_API_KEY="$KEY"
```

If the sed pattern misses (e.g., line wraps), fall back to:

```bash
KEY=$(grep "MINIMAX_API_KEY" ~/.bashrc | head -1 | sed -E 's/^export MINIMAX_API_KEY="(.+)"$/\1/')
# or: KEY=$(awk -F'"' '/^export MINIMAX_API_KEY=/ {print $2}' ~/.bashrc)
```

Verify length > 100 before running tests.

## The 6 PumpStation*LiveTest classes (as of 2026-07-23)

| Class | Test method count | testName folder convention |
|-------|-------------------|----------------------------|
| `PumpStationMiniMaxLiveTest` | 6 live (`alwaysOnJudge_researchSucceeds`, `flagTriggeredJudge_researchSucceeds`, `compactionMemory_researchSucceeds`, `killSwitchTrip_researchHalted`, `singlePathPassPipeline_researchFinishes`, `multiPathRiskLevels_researchSucceeds`) + 7 stubs | `PumpStation/<testName>/` |
| `PumpStationSafePruneLiveTest` | 1 (`safePruneIsTransparentTheSinglePathBriefStillPasses`) | `<testName>/` |
| `PumpStationTPipeConfigTraceLiveTest` | 2 (`multiTurnHarnessOnRealTaskWritesTracesToTPipeConfigTraceDir`, `safePruneFiresDuringMultiTurnLiveRun`) | `<testName>/` |
| `PumpStationGapCoverageLiveTest` | 1 live (`liveReport_emitsOverviewHeader`) + 3 stubs (`stubLoopGuard_emitsSeparateMetricAndLimitMetaKeys`, `stubDispatch_carriesPathSelectionRationaleInMeta`, `stubDispatchHint_steersRotationAcrossPaths`) | (verify per test) |
| `PumpStationMultiPathLiveTest` | 1 (`multiPathDispatchProducesValidBatch`) | (verify per test) |
| `PumpStationPostGoalLiveTest` | 6 live (`live_01` through `live_06`) + 6 stubs (`stub_01` through `stub_06`) | (verify per test) |

Total: **17 live tests across 6 classes**.

## The trace folder convention

All live tests write traces via `File(TPipeConfig.getTraceDir(), testName)` where
`getTraceDir()` returns `${getDebugDir()}/trace` = `~/.tpipe/debug/trace/`.

- `PumpStationMiniMaxLiveTest` nests under `PumpStation/<testName>/`
- `PumpStationSafePruneLiveTest` and `PumpStationTPipeConfigTraceLiveTest` use flat `<testName>/`

The test sets `testName` explicitly when calling `runResearchHarness(testName = "01-always-on-judge", ...)`
or via the equivalent in the test class. The folder is derived from this name.

## The per-class sequential pattern

Memory from 2026-07-08: "Gradle test run failed: 16 tests completed with 2 failures.
Per-class rerun recovered them." The pattern:

1. Run **one test at a time**, not grouped, not parallel.
2. After each test, **parse the trace** with `parse_pumpstation_html.py --input <path>`.
3. Verify the trace landed at the expected folder (check `~/.tpipe/debug/trace/<expected_folder>/`).
4. If a test fails with `P2PException: OpenAI Responses error: Service error. Please retry later` —
   this is **upstream LLM stochastic noise**, not a code defect. Rerun the failing test.
5. If a test fails with `MaxTurnsExceeded` — the LLM needed more turns than the test's
   safety budget. The harness event chain is correct; this is a test design parameter.

## The 9-trace inventory from the 2026-07-23 verification session

| # | Test | Folder | Events | Result |
|---|------|--------|--------|--------|
| 1 | alwaysOnJudge_researchSucceeds | `PumpStation/01-always-on-judge/` | 31 | COMPLETED (JudgeComplete) |
| 2 | flagTriggeredJudge_researchSucceeds | `PumpStation/02-flag-triggered-judge/` | 45 | COMPLETED (JudgeComplete) |
| 3 | compactionMemory_researchSucceeds | `PumpStation/03-compaction-memory/` | 31 | COMPLETED (JudgeComplete) |
| 4 | killSwitchTrip_researchHalted | `PumpStation/04-kill-switch-trip/` | 4 | FAILED (KillSwitchTripped) — by design |
| 5 | singlePathPassPipeline_researchFinishes | `PumpStation/05-single-path-pass-pipeline/` | 8 | COMPLETED (PassSignal) |
| 6 | multiPathRiskLevels_researchSucceeds | `PumpStation/06-multi-path-risk-levels/` | 33 | COMPLETED (JudgeComplete) |
| 7 | safePruneIsTransparent | `safe-prune-transparent/` | 8 | COMPLETED (PassSignal) |
| 8 | multiTurnHarnessOnRealTask | `tpipe-config-multi-turn-harness/` | 13 | COMPLETED (JudgeComplete) |
| 9 | safePruneFiresDuringMultiTurnLiveRun | `tpipe-config-safe-prune-multi-turn/` | 14 | COMPLETED (JudgeComplete) |

Plus from the second batch:
- `PumpStationGapCoverageLiveTest.liveReport_emitsOverviewHeader` — PASS (1m 21s)
- `PumpStationMultiPathLiveTest.multiPathDispatchProducesValidBatch` — PASS (2m 17s)
- `PumpStationPostGoalLiveTest.live_01_passPipelineNoGoal_postGoalFiresOnNoGoalAgentExit` — PASS (7m 35s)

## Wall time expectations

| Test class | Stub | Live (single) |
|------------|------|---------------|
| `PumpStationMiniMaxLiveTest` | 2s | 1-7 min |
| `PumpStationSafePruneLiveTest` | n/a | ~40s |
| `PumpStationTPipeConfigTraceLiveTest` | n/a | 1-3 min |
| `PumpStationGapCoverageLiveTest` | <1s | ~1 min |
| `PumpStationMultiPathLiveTest` | n/a | ~2 min |
| `PumpStationPostGoalLiveTest` | <1s | 3-8 min |

A full live-test pass (all 17 live tests, sequential) takes roughly **45-90 minutes**.

## Pitfall: parse_pumpstation_html.py requires `--input` flag

The script uses argparse with `--input INPUT` not positional args. Calling it as:

```bash
python3 parse_pumpstation_html.py /path/to/trace.html  # WRONG — unrecognized arguments
```

fails with `usage: parse_pumpstation_html.py [-h] [--input INPUT] [--stdin] [--output OUTPUT] [--quiet]`.
Correct invocation:

```bash
python3 parse_pumpstation_html.py --input /path/to/trace.html --quiet
```

The `--quiet` flag suppresses per-event output to keep stdout parseable as JSON.

## Pitfall: never claim tests ran if only one env gate is set

Setting `MINIMAX_API_KEY` without `TPIPE_LIVE_LLM_TEST=true` causes the `@BeforeAll setup()`
to early-return. The test bodies execute the `if (liveGateOrSkip() == null) return@runBlocking`
path. JUnit XML will show "passing" with wall time ~0.001s. **This is not a real run.**

Verification: after the run, check `build/test-results/test/TEST-*.xml` for `time="X.XXX"`
where X > 0.1. Sub-0.01s times mean the test silently skipped.

## Pitfall: never move files to /tmp to dodge compile errors

The 2026-07-08 incident: an agent moved an untracked test file to `/tmp` to make a
compile error go away. **Do not do this.** If a test class has a compile error, fix
the source code. Moving files to `/tmp` is silent data loss the operator cannot recover
and is grounds for the Class 8 "Defensive Verification Dissertation" anti-pattern.

## Reference shape for per-test trace verification

After each test, verify:

1. **Folder exists**: `~/.tpipe/debug/trace/<expected_folder>/`
2. **pumpstation-*.html present**: at least one `pumpstation-ps-*.html` file
3. **agent-*.html present** (MiniMax tests): dispatch, gather, judge, report agent traces
4. **Parse succeeds**: `python3 parse_pumpstation_html.py --input <pumpstation.html> --quiet`
   returns valid JSON with `events` array, `run_status`, `run_id`
5. **Event count > 3**: real runs produce 4+ events; 3 events means the test only got
   to `PUMP_STATION_STARTED → JUDGE_SKIPPED → DISPATCH_STARTED` before the LLM errored
6. **Exit reason**: `JudgeComplete`, `PassSignal`, or `KillSwitchTripped` (by design for
   kill-switch test). Anything else (e.g., `LLMError`, `MaxTurnsExceeded`) needs investigation.
