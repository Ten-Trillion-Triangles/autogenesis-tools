# Ad-Hoc Trace HTML Verification Recipe

How to write a `hermes-verify-*.sh` script that grep-parses a rendered TPipe trace HTML and reports PASS/FAIL on specific event-meta fields. This is the canonical pattern for "the user asks me to verify a fix landed in the trace, but a full `./gradlew :test` rerun is too expensive to do in-band."

## When to Use This

- The operator asks for evidence that a specific event block now carries a specific meta key.
- The relevant test class has already run and written a trace artifact under `${TPipeConfig.getTraceDir()}/<component>/<test-name>/`.
- A full `./gradlew :test --tests "..." --rerun-tasks` cycle is too expensive to run as part of the verification turn (live LLM tests take 1-3 minutes; full suite takes 20+).
- The verification needs to be auditable and reproduceable from a script path (the operator can re-run `bash /tmp/hermes-verify-bug14.sh` to confirm the same finding).

## The Recipe (4 steps)

### Step 1: Resolve the canonical trace path

```
TRACE_DIR="$HOME/.tpipe/debug/trace/<component>/<test-name>"
HTML=$(ls -t "$TRACE_DIR"/<prefix>-*.html 2>/dev/null | head -1)
```

The trace dir name MUST come from `TPipeConfig.getTraceDir()` resolved against the test's `exportPath`. Never `~/.TPipe-Debug/`. If the dir doesn't exist, fail loudly — the operator should run the relevant test first.

### Step 2: Locate the event by line number

```
line=$(grep -nE "PUMP_STATION_LOOP_GUARD_TRIPPED" "$HTML" | head -1 | cut -d: -f1)
```

`TraceVisualizer` renders each event as a single long line of HTML. `grep -n` gives the line number. The event-type span (`<span class='ps-detail-type'>(EVENT_TYPE)</span>`) is the anchor.

### Step 3: Extract the meta block with `sed -n "${line}p"` + NEGATED CHAR CLASS grep

```
block=$(sed -n "${line}p" "$HTML" | grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED[^\"]{0,900}")
```

**This is the load-bearing trick.** Naive `grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED.{0,900}"` triggers catastrophic backtracking hangs on long lines (HTML event lines are 1500-1600 chars; the meta block is ~700-900 chars embedded in the middle). See the pitfall section below for the full failure mode.

### Step 4: Assert on key presence

```
for key in metric observed limit; do
  if echo "$block" | grep -qE "ps-meta-key'>${key}:</span><span class='ps-meta-val'>[^<]+"; then
    val=$(echo "$block" | grep -oE "ps-meta-key'>${key}:</span><span class='ps-meta-val'>[^<]+" \
            | head -1 | sed -E "s/.*ps-meta-val'>([^<]+)/\1/")
    pass "key '${key}' present (value: ${val})"
  else
    fail "key '${key}' missing from PUMP_STATION_LOOP_GUARD_TRIPPED meta block"
  fi
done
```

The key+value rendered shape is deterministic across all `TraceVisualizer` containers (PumpStation, Manifold, Junction, Splitter, DistributionGrid): `<span class='ps-meta-key'>KEY:</span><span class='ps-meta-val'>VAL</span>`. Grep for both the key and its value in one regex.

## Worked Example: Bug 14 (LoopGuardTripped metric/observed/limit split)

The full script lives at `scripts/verify-loop-guard-tripped-meta.sh` in this skill. Source against an HTML produced by `PumpStationGapCoverageLiveTest.stubLoopGuard_emitsSeparateMetricAndLimitMetaKeys` at `${TPipeConfig.getTraceDir()}/loop-guard-meta-keys/pumpstation-ps-*.html`. Output:

```
PASS: key 'metric' present (value: consecutive)
PASS: key 'observed' present (value: 2)
PASS: key 'limit' present (value: 2)
PASS: legacy 'detail' key still emitted (back-compat)
PASS: existing keys (guard, pathName) preserved
```

The PumpStationGapCoverageLiveTest test class itself runs `grep -oE "ps-meta-row">...ps-meta-key...ps-meta-val..."` inline against the HTML and asserts the same shape — both the JUnit test and the ad-hoc probe read the same meta-block grammar.

## Pitfall: grep -oE "X.{0,N}" catastrophic backtracking on long single-line HTML

**Symptom**: ad-hoc verification script hangs for 15+ seconds; `grep` runs but produces no output before timing out.

**Root cause**: TraceVisualizer emits each event as ONE HTML line, 1500-1700 chars total. The event's meta block is embedded inline (`<div class='ps-meta-row'><span class='ps-meta-key'>KEY:</span>...</div>`). When a regex like `grep -oE "EVENT_TYPE.{0,N}"` runs against this line, the `.{0,N}` greedy-quantified alternation forces grep's regex engine to backtrack across all the `<` and `>` and quote characters trying to find a match — for N=500 the search is bounded but for N=1500 on a 1600-char line, the engine essentially tries every suffix and runs out of time.

**Fix**: use a NEGATED CHAR CLASS instead of `.`. Pick a character that does NOT appear in the meta block (single quote `"` works — all the meta keys/values use single-quote HTML attributes). The regex becomes `grep -oE "EVENT_TYPE[^\"]{0,N}"`. Same match result, no backtracking.

```bash
# HANGS for 15+ seconds on a 1600-char HTML line
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED.{0,900}" "$HTML"

# Returns in <100ms with identical match content
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED[^\"]{0,900}" "$HTML"
```

**Why single quote**: `TraceVisualizer` renders `<span class='ps-meta-key'>` with single quotes. Single quote never appears inside a meta value (the values are content text or numbers). Use double quote `[^"]` if your values might contain single quotes — but if they do, you're probably grepping the wrong text.

**Discovery**: this trap caught the first run of the bug14 verification script on 2026-07-10. The script was hung on `grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED.{0,3000}"` for 30+ seconds. The fix reduced runtime to <1 second with identical output. Captured as a hard pitfall in the parent SKILL.md.

## Companion: when the script SHOULD be a real test instead

If the assertion logic in the ad-hoc probe is reusable across multiple fix verifications (e.g., every time you add a new key to LoopGuardTripped meta, you'd re-verify it), promote the probe to a real JUnit test in the TPipe test suite. Use the ad-hoc script as a TEMPLATE — copy its grep patterns, paste them into a `@Test` method's assertion block, and add it to the existing `PumpStationGapCoverageLiveTest` class or a new gap-coverage class. The ad-hoc probe is for one-off verification; a real test is for every-fix verification.

If the assertion is single-use (the operator asked "did this specific change land in the trace?"), keep it as an ad-hoc `/tmp/hermes-verify-*.sh` and label the result explicitly as ad-hoc verification per the standing rule.

## Pattern: error path on missing trace

```
if [[ ! -d "$TRACE_DIR" ]]; then
  fail "trace dir $TRACE_DIR does not exist; run <test-class>.<test-method> first"
fi
```

Never silently treat a missing trace as "PASS." The whole point of these probes is to verify the test ran AND the artifact landed correctly. If the test didn't run, the operator needs to know that — saying "PASS: trace missing" is the same anti-pattern as the "green test" rule the parent skill already warns about.