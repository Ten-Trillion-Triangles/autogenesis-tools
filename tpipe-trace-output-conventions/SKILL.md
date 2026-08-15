---
name: tpipe-trace-output-conventions
description: TPipe trace output and side-effect-path conventions. Load before writing any code or test that creates a TraceConfig, debug artifact, log file, billing record, on-disk JSON, or any other persistent side-effect artifact in the TPipe codebase. Covers the canonical resolver `TPipeConfig.getTraceDir()`, the four production files that still violate the rule (PumpStationDsl.kt, Util.kt, TracingBuilder.kt, TraceConfig.kt itself), the audit checklist for "did this patch leak a hard-coded path," and the test-suite hygiene rule that "green test" is insufficient when the observable artifact landed in the wrong directory.
version: 1.3.0
author: Apex (TTT)
created: 2026-07-06
updated: 2026-07-11
tags: [tpipe, trace, trace-config, tpipe-config, getTraceDir, path-conventions, debug-artifacts, test-hygiene, wire-format, wire-bump, kotlinx-serialization, kotlinc-standalone, hermes-verify]
trigger: When writing TPipe production code or test code that touches TraceConfig, log files, billing reports, on-disk JSON, snapshots, or any path-bearing artifact; before adding a new TraceConfig() constructor call or `exportPath = "..."` assignment; when debugging "why is the test green but the artifact is in the wrong place"; when auditing an existing TPipe file for hard-coded `~/.TPipe-Debug/` literals; when designing test fixtures that need isolated trace directories; when writing a hermes-verify-* probe that grep-parses a rendered trace HTML or verifies a wire-format bump on a `@Serializable` data class; when bumping the wire format on a TPipe `TracePayload` / `TraceSummary` style data class and need v1 to v2 verification; when the Kotlin gradle daemon crashes with the "Daemon compilation failed" message.
---

# TPipe Trace Output Conventions

## Operator-Mandated Test Standard (2026-07-06)

Every new test class in TPipe MUST capture traces into the default trace dir resolved via `TPipeConfig.getTraceDir()`. Failure to write a trace artifact is itself a defect — "the unit assertion passed but the trace landed in the wrong place" is a false-positive test that the harness runtime treats as green.

This is the test-side mirror of the production rule below. Captured mid-Phase-3.5 of the `pathSelectionRationale` feature plan after the operator sent an out-of-band message during tracking-mode setup.

The full 5-step recipe for **PumpStation-class tests** (resolve → stamp runId → enableTracing → assert on wrapper existence → restore configDir) lives at `references/test-trace-capture-recipe.md` and is required reading before writing any new test fixture that instantiates `PumpStation()` or drives a harness event.

The full 7-step recipe for **container-class live tests** (Manifold, Junction, DistributionGrid, Splitter) lives at `references/container-live-test-trace-recipe.md` — the `tracing { config(...) }` DSL block, the `getTraceReport()` → string → `writeStringToFile` chain, and the per-test subdirectory pattern. Required reading before writing any new live test that drives a TPipe container. The Manifold case (`ManifoldMiniMaxLiveTest.kt`, 2026-07-09) is the canonical worked example.

When dispatching a subagent to write a TPipe test, copy the appropriate recipe into the subagent's `context` field. The subagent will not otherwise know the rule applies to test code (it's not in the production-code section below).

## The Rule

**Every persistent side-effect artifact in TPipe resolves its directory from `TPipeConfig.getTraceDir()` (or the equivalent typed accessor for non-trace outputs). No hard-coded `~/.TPipe-Debug/...` string literal anywhere in production or test code.**

The canonical resolver chain:

    TPipeConfig.configDir             — module-level mutable String (default: "${getHomeFolder()}/.tpipe")
    TPipeConfig.getDebugDir()         — "${configDir}/debug"
    TPipeConfig.getTraceDir()         — "${getDebugDir()}/trace"   ← USE THIS FOR TRACE FILES
    TPipeConfig.getMemoryDir()        — "${configDir}/memory"
    TPipeConfig.getTodoListDir()      — "${getMemoryDir()}/todo"

For trace files specifically, the convention is `${TPipeConfig.getTraceDir()}/Library/<feature>/<test-name>/`. The harness-level tests in `PumpStationTPipeConfigTraceLiveTest.kt` and the PumpStation live test (`PumpStationMiniMaxLiveTest.kt` post-2026-07-06 fix) both follow `<component>-<testName>` subdirs. The container live tests (`JunctionLiveBedrockIntegrationTest.kt`, `DistributionGridLiveBedrockIntegrationTest.kt`, `ManifoldLoopLimitLiveBedrockIntegrationTest.kt`, `ManifoldMiniMaxLiveTest.kt`) all follow `Library/<feature>/<test-name>/<test-name>.html`.

## Why This Exists

The legacy literal `~/.TPipe-Debug/` was the pre-TPipeConfig path. TPipeConfig was introduced as the unified config root, and the trace resolver chain was added to it (`getDebugDir` → `getTraceDir`) precisely so all path-bearing code goes through one typed accessor that respects `tpipe.dir.*` overrides via `TPipeConfig.configDir = ...`.

Bypassing the resolver — by hard-coding `~/.TPipe-Debug/traces/PumpStation/` in a string literal — silently routes the output to a directory that:

1. Won't pick up user-configured `tpipe.dir.*` overrides (CI, container mount points, custom storage roots).
2. Won't appear in `TPipeConfig`-based audits or directory inventory tools.
3. Creates two parallel artifact trees that diverge over time (one following config, one static).
4. Breaks the user-visible rule the operator has stated multiple times: "traces must be saved using TPipeConfig.getTraceDir() as the path."

This rule was violated by the production codebase in 4 locations as of 2026-07-06 — tracked in the audit references below. The PumpStation live test was patched that day. The 4 production files remain a debt.

## Where the Rule Currently Leaks (Audit Inventory, 2026-07-06)

The following files contain hard-coded `~/.TPipe-Debug/` or stale-path literals that bypass `TPipeConfig.getTraceDir()`. They work today only because `configDir` happens to default to a path where `~/.tpipe/debug/trace` and the legacy `~/.TPipe-Debug/traces` can both exist as separate trees. Any future change to `configDir` (CI, container, user override) will silently route these writes to a directory the user does not want.

| File | Line | Current literal | What it should be |
|------|------|-----------------|-------------------|
| `src/main/kotlin/Pipeline/PumpStationDsl.kt` | varies | `~/.TPipe-Debug/...` (verify exact line) | `${TPipeConfig.getTraceDir()}/...` |
| `src/main/kotlin/Util/Util.kt` | varies | `~/.TPipe-Debug/...` (verify exact line) | `${TPipeConfig.getTraceDir()}/...` |
| `src/main/kotlin/Debug/TracingBuilder.kt` | varies | `~/.TPipe-Debug/...` (verify exact line) | `${TPipeConfig.getTraceDir()}/<component>/` |
| `src/main/kotlin/Debug/TraceConfig.kt` | `val exportPath: String = "~/.TPipe-Debug/traces/"` | Default value of `TraceConfig.exportPath` | Should compute from `TPipeConfig.getTraceDir()` instead of hard-code |

To re-run the inventory fresh, grep the codebase:

    grep -rn '~/.TPipe-Debug' src/main src/test

Expected result post-cleanup: `Pipeline/PumpStationLiveLLMTest.kt` is fine because it explicitly passes `exportPath` (does not rely on the default); only the 4 production files leak. Any test that constructs `TraceConfig()` without an explicit `exportPath` argument picks up the legacy default and writes to the wrong location.

## Conventions (Detailed)

### Naming a Subdir

Pattern: `${TPipeConfig.getTraceDir()}/<system-name>/<run-or-test-name>/`. The system-name separates artifacts across top-level domains (PumpStation, Pipe, Manifold, Junction, DistributionGrid, …). The run-or-test-name separates executions.

For container live tests specifically, the convention is `Library/<feature>/<test-name>/<test-name>.html`:
- `Library/junction-live-bedrock/<caseName>/junction.html` (per `JunctionLiveBedrockIntegrationTest.kt:723`)
- `Library/distribution-grid-live-bedrock/<scenarioName>/sender-grid.html` (per `DistributionGridLiveBedrockIntegrationTest.kt:937`)
- `Library/manifold-loop-limit-live-bedrock/<testName>/<testName>.html` (per `ManifoldLoopLimitLiveBedrockIntegrationTest.kt:72`)
- `Library/manifold-minimax-live/<testName>/<testName>.html` (per `ManifoldMiniMaxLiveTest.kt`, 2026-07-09)

```kotlin
// CORRECT — runtime resolution, respects configDir override
val traceRoot = File(TPipeConfig.getTraceDir(), "PumpStation")
val runSubdir = File(traceRoot, runId.take(12))
runSubdir.mkdirs()

// CORRECT (container live test) — Library/<feature>/<test-name>
val traceBaseDir = File("${TPipeConfig.getTraceDir()}/$TRACE_SUBDIRECTORY/$TEST_SUBDIRECTORY")
traceBaseDir.mkdirs()

// WRONG — string literal; ignores configDir override
val traceRoot = File("~/.TPipe-Debug/traces/PumpStation/".replace("~", System.getProperty("user.home")))
```

### TraceConfig exportPath Always Set Explicitly

`TraceConfig.exportPath` defaults to the legacy `"~/.TPipe-Debug/traces/"` literal in `TraceConfig.kt`. Whenever a `TraceConfig()` instance is constructed for an artifact that should land in the canonical location, pass an explicit `exportPath`:

```kotlin
// CORRECT
TraceConfig(
    enabled = true,
    outputFormat = TraceFormat.HTML,
    detailLevel = TraceDetailLevel.DEBUG,
    autoExport = true,
    exportPath = File(TPipeConfig.getTraceDir(), "PumpStation/${runId.take(12)}").absolutePath,
)

// WRONG — uses legacy default
TraceConfig(
    enabled = true,
    outputFormat = TraceFormat.HTML,
    autoExport = true,
    // no exportPath → falls back to "~/.TPipe-Debug/traces/"
)
```

The only acceptable use of the default is in code that intentionally targets the legacy directory (nothing in the current codebase does this).

**Container exception**: when the test calls `container.getTraceReport(TraceFormat.HTML)` directly and writes the result via `writeStringToFile`, the `TraceConfig.exportPath` is irrelevant (the container does not honor it). The container recipe in `references/container-live-test-trace-recipe.md` covers this case.

### Per-Test Isolation

Tests that mutate `TPipeConfig.configDir` for isolation MUST save the original and restore it in a `try/finally`, regardless of whether the test passes or throws. The pattern is already used in `Context/ContextWindowRemoteLockTest.kt`, `Context/RemoteMemoryTest.kt`, and `TPipe-Bedrock/.../QwenSemanticCompressionRoundTripTest.kt` — copy that exact shape, don't invent a new one.

```kotlin
val originalConfigDir = TPipeConfig.configDir
try {
    TPipeConfig.configDir = testSpecificDir.absolutePath
    // ... test code, trace exports use TPipeConfig.getTraceDir() ...
}
finally {
    TPipeConfig.configDir = originalConfigDir
}
```

### HTML autoExport Files

When the autoExport filename is a `pumpstation-<runId12>.html` template, the file's directory is `exportPath` from the active `TraceConfig`. Verify the file lands in the right directory by checking the parent dir's path before and after the run, not just the file's existence.

### Container `getTraceReport()` → `writeStringToFile` Chain

Containers (Manifold, Junction, DistributionGrid, Splitter) expose `getTraceReport(format: TraceFormat): String` which returns the rendered report as a Kotlin string — NOT a write side-effect. To persist the trace to disk, the test MUST:

1. Call `manifold.getTraceReport(TraceFormat.HTML)` to obtain the HTML string.
2. Call `writeStringToFile("$TPipeConfig.getTraceDir()/Library/<feature>/<testName>/<testName>.html", htmlString)`.
3. Assert on the file's existence, size, and content anchors.

Without step 2 the rendered HTML only lives in the heap and is GC'd at test end. Without step 3 the test is a false positive. See `references/container-live-test-trace-recipe.md` for the full 7-step recipe.

### Token Totals Card (header KPI row)

Every container HTML report (PumpStation, Manifold, Junction, Splitter, DistributionGrid) renders a `TOKEN TOTALS` pill near the top of the page via `TraceVisualizer.buildContainerTokenCard(trace)`. The card aggregates `inputTokens` and `outputTokens` from every event in the trace that carries them in metadata, **skipping `KILLSWITCH_CHECK`** (which reports cumulative-AT-check-time, not actual spend — the underlying JUDGE_COMPLETED / DISPATCH_COMPLETED / PATH_COMPLETED events are the source of truth). Returns null when no event in the trace carries token metadata, so short traces don't show a misleading "0 tokens" card. Single source of truth shared across all 5 container HTML reports.

## Pitfall: grep -oE "EVENT.{0,N}" hangs on long single-line trace HTML

`TraceVisualizer` emits each event block as ONE HTML line (1500-1700 chars typical). When a hermes-verify-*.sh script tries to extract a sub-block via `grep -oE "EVENT_TYPE.{0,N}"` with N >= 500, the greedy `.` quantifier triggers catastrophic regex backtracking and the script hangs for 15-30 seconds before timing out. The probe eventually produces no output because grep runs out of time mid-backtrack.

**Fix**: replace `.{0,N}` with a NEGATED CHAR CLASS that does not appear in the meta block. Single quote `"` is a safe pick (TraceVisualizer renders HTML attributes with single quotes, and meta values never contain single quotes in practice). Same match content, no backtracking, runtime drops to <1 second.

```bash
# HANGS for 15-30 seconds on a 1600-char HTML line
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED.{0,900}" "$HTML"

# Returns in <100ms with identical match content
grep -oE "PUMP_STATION_LOOP_GUARD_TRIPPED[^\"]{0,900}" "$HTML"
```

Captured 2026-07-10 on the Bug 14 fix verification probe. Full worked example and the standard 4-step probe recipe in `references/ad-hoc-trace-html-verification-recipe.md`. The reusable probe at `scripts/verify-loop-guard-tripped-meta.sh` already uses this pattern.

## Pitfall: Kotlin gradle daemon crash — "Daemon compilation failed" with no source line

When `./gradlew :test ...` (or any TPipe gradle task spanning the multi-module build) intermittently fails with `e: Daemon compilation failed: null` and a `Compilation error. See log for details` cause, the Kotlin compiler daemon crashed mid-way through. **Do not panic — this is not a TPipe bug, this is a Kotlin 2.2.x/2.3.x intermittent daemon bug.**

Symptoms:
- No source line number, no file pointer, just `e: Daemon compilation failed: null` in stdout
- Build appears fundamentally broken — looks like a real compile error
- Same gradle invocation may succeed on retry

Workaround:

```bash
./gradlew :test --tests "..." --rerun-tasks --no-daemon
```

`--no-daemon` bypasses the failing daemon and uses a fresh JVM per build. Build time roughly doubles but reliability approaches 100%.

**Prefer the standalone `kotlinc` recipe in `references/kotlin-data-class-wire-bump-recipe.md`** when you hit this — the standalone compiler has no daemon to crash, and verifies wire-format properties in seconds rather than waiting on gradle. Captured 2026-07-11 during the `kind` discriminator bump on `RemoteTraceDispatcher.TracePayload`.

## Test Hygiene: "Green Test" is Not Enough

The PumpStation live test session (2026-07-06) demonstrated this clearly: 9 of 13 tests were GREEN, but every green test was silently writing its trace artifacts to the wrong directory because `PumpStationMiniMaxLiveTest.kt:140` had a hard-coded `TRACE_DIR = "~/.TPipe-Debug/traces/PumpStation/"` literal that no assertion checked against.

The Manifold live test session (2026-07-09) demonstrated a different but related failure: a test that calls `manifold.getTraceReport(TraceFormat.HTML)` and only asserts on the in-memory string length. The string is non-empty, the test passes, the trace evaporates the moment the JVM returns. The fix is to write the string to a file under `TPipeConfig.getTraceDir()` and assert on the file's path + size + content anchors.

### The Rule

If a test's primary observable output is a side-effect artifact (not a return value), the test must assert on:

1. The artifact's CONTENT (existing convention — file size, structure, expected substrings).
2. The artifact's LOCATION — the directory it landed in must match the expected canonical resolver.
3. The artifact's OWNERSHIP — the file was written by the test invocation under test, not a stale leftover from a prior run.

### Where This Matters

- Test fixtures that create `TraceConfig()` — assert the exportPath resolves to `${TPipeConfig.getTraceDir()}/<expected-subdir>`.
- Tests that write billing records, log files, JSON snapshots — assert the file path matches the canonical resolver.
- Integration tests that exercise end-to-end artifacts — assert on at least one full path traversal of the artifact's parent directory.

### Anti-Pattern: Asserting only "the file exists"

A test that asserts `assert(file.exists() && file.length() > 5000)` passes regardless of where the file is. If the test wrote the file to the wrong directory (because the writer used a hard-coded path), the assertion still passes. The test is a false positive.

### Anti-Pattern: Asserting only on the in-memory return value

A container test that asserts `assertTrue(manifold.getTraceReport(TraceFormat.HTML).isNotBlank())` passes when the trace string is non-empty in memory. But that string evaporates the moment the test method returns. The user can't open it, the postmortem can't read it, and the CI artifact collection step has nothing to upload. Always write the string to disk, then assert on the file.

### Companion pitfall

Don't ship a test that wires a hard-coded path even if the test passes. The "tests are green" report covers assertion correctness but not behavioral conformance to project conventions. If the project convention says "use `TPipeConfig.getTraceDir()`," a passing test that doesn't use it is a defect, not a feature.

## Workflow: Adding a Trace-Writing Feature in TPipe

1. Load this skill (you're here).
2. Identify the path you need. It will be `${TPipeConfig.getTraceDir()}/<your-component>/<your-instance-id>/`.
3. Resolve it via `File(TPipeConfig.getTraceDir(), "<your-component>/<your-instance-id>")`. Never inline the literal.
4. Create the directory with `mkdirs()` only if it doesn't already exist. Use the static factory pattern, not `if(!exists) mkdirs()` scattered across the call site — every callsite that does this is one more divergence point.
5. If the feature adds a new subdir under the trace tree, document it in `references/trace-output-inventory.md` so future audits know it's expected.
6. If the feature ships a `TraceConfig` constructor, it MUST pass `exportPath = <resolved-path>` explicitly. Never rely on the default.

## Workflow: Auditing an Existing TPipe File

1. `git grep -n '~/.TPipe-Debug' src/main src/test` — current leak inventory.
2. For each hit, replace the literal with a `TPipeConfig.getTraceDir()`-based resolver. Capture the resolved path into a local before using it twice.
3. Cross-check that the new resolver still passes any test that asserts on `exportPath` value, not just existence.
4. Re-run the inventory grep. Empty result post-cleanup.

## Workflow: Bumping the TPipe Wire Format (`TracePayload`, `TraceSummary`, etc.)

TPipe ships wire contracts across module boundaries (TPipe client ↔ TPipe-TraceServer, TPipe client ↔ Bedrock, etc.). When you add or rename a field on a `@Serializable` data class that crosses one of those boundaries, do this:

1. **Write the gradle JUnit test FIRST** — TDD-RED. Assert on v1-decode, v2 round-trip, default-null round-trip, and explicit-string round-trip. Reference test: `src/test/kotlin/Debug/RemoteTraceDispatcherWireTest.kt` (created 2026-07-11 for the `kind` discriminator bump).
2. **Run gradle** — `./gradlew :test --tests "<test-name>" --rerun-tasks --no-daemon` (always include `--no-daemon` if the build has been flaky; see the daemon pitfall above). Confirm it fails RED for the right reason.
3. **Make the production change** — add the `kind: String? = null` (or equivalent) field with `= null` default, keep the position at the END of the data class so JSON field order is preserved for any consumers that care.
4. **Re-run gradle** — confirm GREEN.
5. **Optionally run the standalone `kotlinc` wire verifier** at `references/kotlin-data-class-wire-bump-recipe.md` to verify wire bytes (omit-vs-explicit-null, byte-identical-with-v1 behavior, etc.) in seconds without the full gradle round-trip. Especially useful when the gradle build is slow or the daemon crashed.
6. **Regress the dispatch path** — run any existing test that exercises the modified call site end-to-end (e.g. `PipeTracerTest` exercises `dispatchTrace` over a fake HTTP server). Confirm no regressions.
7. **Commit** — single commit with both files (data class + test), single line of "feat(<area>): <bump-description>".

**Why add the field at the END of the data class**: kotlinx-serialization preserves source order in JSON output. Adding a field at the end minimizes the diff for any consumer that diffs JSON byte-by-byte. Adding it in the middle is allowed but creates noisy cosmetic diffs.

**Why default-null and not default-empty-string**: kotlinx-serialization treats a missing key on a nullable field as `null` (the type's default). The "omit key = default" trick ONLY works for nullable types — see the standalone recipe for the gotcha.

## Workflow: Writing a hermes-verify-* Probe (one-off fix verification)

When the operator asks "did this specific change land in the trace?" or "does this wire bump survive the v1 path?" and a full `./gradlew :test --rerun-tasks` cycle is too expensive to run in-band, write a `/tmp/hermes-verify-<feature>` probe. **Two flavors, pick by what you're verifying:**

### Flavor 1: `*.sh` probe (grep artifact for substring presence)

When verifying that an event-meta field, a HUD fragment, or a wire byte landed in a rendered artifact. Full recipe (4 steps + the catastrophic-backtracking pitfall on long single-line trace HTML — `grep -oE "EVENT.{0,900}"` hangs for 15-30s; use a negated char class `[^"]{0,900}` for sub-100ms) is in `references/ad-hoc-trace-html-verification-recipe.md`. Reusable probe for the Bug 14 LoopGuardTripped meta split at `scripts/verify-loop-guard-tripped-meta.sh`.

### Flavor 2: `main.kt` probe (compile + run a standalone Kotlin verifier with `kotlinc`)

When verifying a **wire-format bump** on a `@Serializable` data class (`TracePayload`, `TraceSummary`, etc.) that is faster than a full gradle test and proves v1 ↔ v2 wire-compat in isolation. Full recipe (5 steps + the empirically-verified kotlinx-serialization null omission behavior — `String? = null` causes the JSON key to be OMITTED, not written as `"key":null`) is in `references/kotlin-data-class-wire-bump-recipe.md`. Includes the kotlinc standalone recipe (`kotlinc -Xplugin=$SERIAL_PLUGIN_JAR -classpath $LIBS main.kt -include-runtime -d verifier.jar`) and the daemon-crash alternative.

**Both flavors use the `hermes-verify-` path prefix.** Pick by what you're checking: shell flavor for artifacts that landed on disk, Kotlin flavor for wire-format bytes that exist only in memory.

If the same assertion will be needed for every future fix in the same area, promote the probe to a real JUnit test in `PumpStationGapCoverageLiveTest` (or sibling gap-coverage class). The probe is for one-off verification; a real test is for every-fix verification.

## Companion Files

- `references/trace-output-inventory.md` — full inventory of which TPipe files currently write to disk, broken by directory. Update on every audit cycle.
- `references/test-hygiene-green-vs-correct.md` — the 9/13 green-vs-correct incident from 2026-07-06, with the exact assertion message that passed and the path it should have checked.
- `references/test-trace-capture-recipe.md` — the 5-step recipe (resolve → stamp runId → enableTracing → assert on wrapper existence → restore configDir) for **PumpStation**-class tests, where the harness emits events to `taskState.runId` and autoExport handles the file write.
- `references/pumpstation-live-test-trace-recipe.md` — the **PumpStation env-gated live test** recipe (added 2026-07-11): the THREE signals required to write `pumpstation-<traceId12>.html` to the canonical trace root — `tracingConfiguration = traceConfig` inside the DSL block, `pipeline.enableTracing(traceConfig)` on every agent pipeline BEFORE `pipeline.init(true)`, and explicit `station.getTraceReport(TraceFormat.HTML)` AFTER `runBlocking { executeLocal(...) }`. Missing any signal produces a green test that wrote no trace file. Includes the GenericOpenAIPipe wiring for MiniMax (`ApiMode.OpenAIResponses`, `https://api.minimax.io/v1`, `tpipe.allowInsecureBaseUrl=true` system property). Required reading before writing any `PumpStation*LiveTest.kt`.
- `references/container-live-test-trace-recipe.md` — the 7-step recipe (resolve → build TraceConfig → wire `tracing { config(...) }` → run container → `getTraceReport()` → `writeStringToFile` → assert on file) for **container-class** live tests (Manifold, Junction, DistributionGrid, Splitter), where the container returns the rendered HTML as a string and the test must persist it to disk manually. Required reading before writing any new live test that drives a TPipe container. The Manifold case (`ManifoldMiniMaxLiveTest.kt`, 2026-07-09) is the canonical worked example.
- `references/agent-result-visibility-pitfall.md` — the "icons show they ran, but no results of what they did" failure class. Three failure modes converge: capture-vs-rendering confusion (events ARE captured, the bug is presentation), all-in-one toggle anti-pattern (collapsibles are wrong for "at-a-glance scanning"), colorblindness / fatigue UX (teal-vs-amber beats red-vs-green for colorblindness safety). Captured 2026-07-08 from the trace-token-totals + agent-result-line session.
- `references/tpipe-config-package-and-resolver-fact.md` — `TPipeConfig` package location (`com.TTT.Config.TPipeConfig`, NOT `com.TTT.Pipe.TPipeConfig`), the resolver chain, the per-test save-and-restore pattern, and the trace-dir-writable guard recipe. Read this any time you import `TPipeConfig`, set `TPipeConfig.configDir` in a test, or add a getTraceDir()-non-blank assertion.
- `references/ad-hoc-trace-html-verification-recipe.md` — recipe for writing `hermes-verify-*.sh` probes that grep-parse a rendered trace HTML and assert on event-meta fields. Includes the `sed -n "${line}p" | grep -oE "EVENT_TYPE[^\"]{0,N}"` recipe, the catastrophic-backtracking pitfall on long single-line HTML (greedy `.` triggers 30+ second hangs; negated char class returns in <1s), and the worked example for the Bug 14 LoopGuardTripped meta split.
- `references/kotlin-data-class-wire-bump-recipe.md` — recipe for writing `hermes-verify-*/main.kt` probes that compile-and-run a standalone Kotlin verifier with `kotlinc -Xplugin=kotlinx-serialization-compiler-plugin.jar` and exercise a wire-format bump on a `@Serializable` data class. Verifies v1 decode, v2 round-trip, default-null behavior (kotlinx OMITTED the key, not `"key":null`), arbitrary-string round-trip. Companion pitfall: Kotlin gradle daemon crash `--no-daemon` workaround. Captured 2026-07-11 on the `kind` discriminator v1 to v2 bump on `RemoteTraceDispatcher.TracePayload`.
- `scripts/verify-loop-guard-tripped-meta.sh` — reusable probe asserting the `metric` / `observed` / `limit` keys are present in the `PUMP_STATION_LOOP_GUARD_TRIPPED` meta block, alongside the legacy `detail` packed string. Read the HTML produced by `PumpStationGapCoverageLiveTest.stubLoopGuard_emitsSeparateMetricAndLimitMetaKeys` from `${TPipeConfig.getTraceDir()}/loop-guard-meta-keys/pumpstation-ps-*.html`. Re-runnable from `/tmp/hermes-verify-bug14.sh` after copying.

## Why This Isn't a Skill for "TraceConfig" Specifically

This skill is broader than just `TraceConfig`. It applies to every TPipe component that writes persistent artifacts — trace files, billing reports, snapshot JSON, memory dumps, lorebook persistence, todo lists, debug logs. The shared property is "where on disk does the output go, and is that location project-config-respecting?" Any future addition to `TPipeConfig.getXxxDir()` (e.g. `getBillingsDir()`, `getSnapshotDir()`) would extend this skill, not require a new one.

The companion skills `pump-station` and `tpipe-trace-parser` cover the *behavior* of tracing — what to capture, how to parse it. This skill covers the *convention* of where to put it AND the verification recipes for both shell-based and Kotlin-based probes. Both classes of work require their respective skills loaded together.
