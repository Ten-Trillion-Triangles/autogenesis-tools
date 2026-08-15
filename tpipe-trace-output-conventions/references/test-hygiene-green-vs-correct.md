# Test Hygiene: "Green Test" is Not "Correct Test" — 2026-07-06 Incident

## The Session

The user asked to locate the live PumpStation tests, run them, and verify the LLM correctly understood its role. The session executed `./gradlew :test --tests "com.TTT.Pipeline.PumpStationMiniMaxLiveTest"` with `TPIPE_LIVE_LLM_TEST=true` and `MINIMAX_API_KEY` set. 9 of 13 tests passed, 4 failed.

The session reported the verdict truthfully: tests passed, LLM roles were correctly played, trace HTML files were written. Working tree state remained clean (no edits made).

## The Reveal

The user fired: "Where are the trace files for the live tests? WHY WEREN'T THEY SAVED!!! AND YOU BETT NOT HAVE CHANNGED IT TO SAVE TO .TPipe again. The rules are clear, theey must be saved using TPipeConfig.getTraceDir() as the path!!!!"

The truth, verified by `git blame -L 139,141`:

```
20f4b377e (EchoOfMaridia 2026-06-13 18:02:59 -0400 140)         private const val TRACE_DIR = "~/.TPipe-Debug/traces/PumpStation/"
```

The test had `TRACE_DIR = "~/.TPipe-Debug/traces/PumpStation/"` hard-coded since June 13. The first session's tests (and every prior run before that) had been writing trace artifacts to the legacy location, NOT the canonical `TPipeConfig.getTraceDir()` location.

The "9 of 13 PASS" verdict was correct against the test's assertions, which checked:

```kotlin
assert(pumpHtmls.isNotEmpty() && pumpHtmls.all { it.length() > 5000 }) {
    "$testName: pump station HTML trace not found for runId=$expectedRunIdPrefix in $subdir " +
        "(looked for pumpstation-*$expectedRunIdPrefix*.html with size > 5KB)"
}
```

The assertion checks that a file exists in `subdir = File(traceDir(), testName)`. But `traceDir()` returns the WRONG directory (the hard-coded legacy one), and `subdir = File(wrongDir, testName)` is therefore also wrong. The assertion `pumpHtmls.isNotEmpty()` passes because the file DID exist — at the wrong location.

## The Fix

Patched `PumpStationMiniMaxLiveTest.kt`:

1. Removed `private const val TRACE_DIR = "~/.TPipe-Debug/traces/PumpStation/"`.
2. Changed `traceDir()` from `File(TRACE_DIR.replace("~", ...))` to `File(TPipeConfig.getTraceDir(), "PumpStation")`.
3. Added `import com.TTT.Config.TPipeConfig`.
4. Updated 3 KDoc/comment references that still pointed at the deleted constant.

Compile: `BUILD SUCCESSFUL`. Re-run produced 13 trace subdirs at `~/.tpipe/debug/trace/PumpStation/` and zero new subdirs at the legacy `~/.TPipe-Debug/traces/PumpStation/`.

## The General Rule

If a test's primary observable output is a side-effect artifact (not a return value), the test must assert on:

1. **CONTENT** — what was written (existing convention: file size, JSON shape, expected substrings).
2. **LOCATION** — where it landed (often missing: the directory the artifact is in should also be asserted).
3. **OWNERSHIP** — that this specific test invocation produced it (not a stale leftover from a prior run; usually handled by runId-based filenames).

When location is missing from the assertion, a test that silently routes every artifact to a wrong directory can still pass — false positive.

## Quick Heuristic

If your test produces ANY of these side-effect artifacts:

- Trace HTML files
- Log files
- Billing reports (JSON or otherwise)
- Snapshot dumps
- Persisted state files (ContextBank snapshots, LoreBook entries)
- Debug-event JSON

Then your assertion block must include at least one directory-path check (NOT just filename existence). The minimum bar:

```kotlin
val expectedDir = File(TPipeConfig.getTraceDir(), "<your-component>")
val actualDir = file.parentFile
assert(actualDir?.canonicalPath?.startsWith(expectedDir.canonicalPath)) {
    "Artifact directory mismatch: expected under ${expectedDir.canonicalPath}, got ${actualDir?.canonicalPath}"
}
```

If the artifact resolver is wrong, this assertion fails. If the artifact doesn't exist, the prior assertion fires first.

## Where This is Documented

The apex-coder persona SKILL.md gained a pitfall called `"Test passed" != "test does the right thing"` capturing this incident. The new class-level skill `tpipe-trace-output-conventions` documents the full convention. Both reference this incident.
