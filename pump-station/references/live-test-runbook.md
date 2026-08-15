# PumpStation Live Test Runbook

Session-derived recipes for running `PumpStationMiniMaxLiveTest` and its siblings against real LLM endpoints. Captures the env-var wiring, the trace layout, the two-failure-bucket triage, the JUnit-XML-as-authoritative-verdict discipline, and the token-card verification recipe.

## Run command (canonical)

```bash
eval "$(grep '^export MINIMAX_API_KEY=' ~/.bashrc)"
export TPIPE_LIVE_LLM_TEST=true
cd TPipe
./gradlew :test --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest" --rerun-tasks -i 2>&1 | tee /tmp/pumpstation-live-run.log
```

Per-class reruns (recommended — combined 3-class live suite takes 20-40 min and re-exposes every stochastic failure mode on every run):

```bash
eval "$(grep '^export MINIMAX_API_KEY=' ~/.bashrc)"
export TPIPE_LIVE_LLM_TEST=true
./gradlew :test --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest" --rerun-tasks -i
./gradlew :test --tests "com.TTT.Pipeline.PumpStationSafePruneLiveTest" --rerun-tasks -i
./gradlew :test --tests "com.TTT.Pipeline.PumpStationTPipeConfigTraceLiveTest" --rerun-tasks -i
```

Wall time per class: 2-13 min depending on number of LLM calls and whether the LLM hits stochastic failure modes. The `-i` flag is required to get per-test stdout in the console log, which is where transport