# Live Test Infrastructure — generating fresh trace artifacts

The parser is verified against on-disk traces. When you need **fresh** traces (new event types, new container variants, regression testing), you have to run a live test yourself. This reference documents the env-var gates, credential sources, and output paths for every live test that produces trace artifacts.

## Two parallel gating systems

TPipe has two independent families of live tests, each with its own gating:

### MiniMax tests (PumpStation) — `TPIPE_LIVE_LLM_TEST=true`

Tests gated on `TPIPE_LIVE_LLM_TEST` env var + `MINIMAX_API_KEY` from `~/.bashrc`:

```bash
export TPIPE_LIVE_LLM_TEST="true"
export MINIMAX_API_KEY="$(grep '^export MINIMAX_API_KEY' ~/.bashrc | sed -E 's/^export MINIMAX_API_KEY="(.+)"$/\1/')"
export MINIMAX_BASE_URL="https://api.minimax.io/v1"
export tpipe_allowInsecureBaseUrl="true"
./gradlew :test --tests "com.TTT.Pipeline.PumpStationSteeringInterruptLiveTest" --rerun-tasks
./gradlew :test --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest" --rerun-tasks
./gradlew :test --tests "com.TTT.Pipeline.PumpStationGapCoverageLiveTest" --rerun-tasks
```

These tests cover: PumpStation steering, PumpStation interrupt, PumpStation gap coverage, multi-path, safe-prune, post-goal, give-up escape hatch, TPipeConfig trace.

**Output paths** (under `~/.tpipe/debug/trace/`):
- `tpipe-config-steering-live/pumpstation-ps-NNNNNN.html` + `agent-*.html`
- `tpipe-config-interrupt-live/pumpstation-ps-NNNNNN.html` + `agent-*.html`

### Bedrock tests (Manifold, Junction, Splitter, DistributionGrid) — `AllowTest=true`

Bedrock tests under `TPipe-Bedrock/src/test/kotlin/bedrockPipe/` use a different gating. They need both AWS credentials AND `AllowTest=true`:

```bash
export AWS_ACCESS_KEY_ID="<from ~/.aws/credentials [default]>"
export AWS_SECRET_ACCESS_KEY="<from ~/.aws/credentials [default]>"
export AWS_REGION="us-west-2"  # qwenInferenceConfig uses us-west-2 for nvidia.nemotron-nano-3-30b
export AllowTest="true"
./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.JunctionLiveBedrockIntegrationTest" --rerun-tasks --no-daemon
./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.DistributionGridLiveBedrockIntegrationTest" --rerun-tasks --no-daemon
./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.DistributionGridTransportLiveBedrockIntegrationTest" --rerun-tasks --no-daemon
./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.ManifoldLoopLimitLiveBedrockIntegrationTest" --rerun-tasks --no-daemon
./gradlew :TPipe-Bedrock:test --tests "bedrockPipe.NestedReasoningConverseHistoryBugTest" --rerun-tasks --no-daemon
```

The `AllowTest=true` env var is read by `TestCredentialUtils.kt:requireAwsCredentials()` — without it, JUnit's `assumeTrue` aborts the test before any credential resolution. The Bedrock-side enforcement is to prevent accidental CI runs from spending real money.

**AWS credentials auto-resolve** from `~/.aws/credentials` even without explicit env vars, but the test still requires `AllowTest=true` to opt in. The nested-reasoning bug test is enabled regardless of `AllowTest` (no `assumeTrue` gating).

**Output paths** (under `~/.tpipe/debug/trace/Library/`):
- `junction-live-bedrock/<discussion|workflow>-<variant>/junction.html` + `<role>.html`
- `distribution-grid-live-bedrock/<scenario>/<sender|remote>-<role>.html`
- `nested-reasoning-bug/<model>/manifold-execution.html` + `manifold-execution.json`

## Common build issues

The Kotlin compiler daemon has known intermittent failures on multi-module builds. When `./gradlew :test` fails with `Internal compiler error. See log for more details` or `Daemon compilation failed: null`:

1. **Retry without `--no-daemon` first** — the daemon issue is unidirectional (always works without daemon, occasionally fails with).
2. **If still failing**: kill all `kotlin-compile-embeddable` and `gradle` JVMs, then `./gradlew --stop` and retry.
3. **Test filter format**: JUnit 5 syntax requires fully qualified names — `com.TTT.Pipeline.PumpStationSteeringInterruptLiveTest`, not bare `Debug.PumpStationSampleReportTest`.

## Trace path ephemerality

Every test run overwrites `pumpstation-ps-NNNNNN.html` with a new millisecond-precision runId. Verification cases pinned to exact paths will go stale after every test run. Use `expect_event_count_gt` and `expect_token_totals_gt` (lower-bounds) instead of exact values, and update the path with `verify_extraction.py --add <name> <path>` after each run.

## Capturing new artifact → automatic verification

After running a live test, capture the new trace as a pinned case:

```bash
python3 scripts/verify_extraction.py --add my-new-case /path/to/new-trace.html
```

This prints a JSON snippet — paste it into the `CASES` dict in `verify_extraction.py`. The new case runs every time `--strict` is invoked, catching future regressions.
