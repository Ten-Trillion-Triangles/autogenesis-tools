# TPipe Trace Output Inventory — 2026-07-06

Concrete inventory of every TPipe file that writes persistent side-effect artifacts to disk, and the directory each one currently targets. Inventory is divided into **compliant** (uses `TPipeConfig.getTraceDir()` or equivalent typed resolver) and **violating** (hard-coded `~/.TPipe-Debug/...` literal or stale default value).

## Compliant (resolved via TPipeConfig)

| File | Resolver used | Subdir pattern | Notes |
|------|---------------|----------------|-------|
| `src/main/kotlin/Config/TPipeConfig.kt` | defines the resolver | n/a (this is the resolver itself) | `getDebugDir()`, `getTraceDir()` at lines 47-54 |
| `src/test/kotlin/Pipeline/PumpStationTPipeConfigTraceLiveTest.kt` | `TPipeConfig.getTraceDir()` | `<test-name>/` | Canonical pattern — both tests call `File(TPipeConfig.getTraceDir(), testName)` |
| `src/test/kotlin/Pipeline/PumpStationMiniMaxLiveTest.kt` (post-2026-07-06 fix) | `TPipeConfig.getTraceDir()` | `PumpStation/<testName>/` | Patched this session — old `TRACE_DIR` const removed |

## Violating (hard-coded literals)

| File | Line | Current literal | Should be |
|------|------|----------------|-----------|
| `src/main/kotlin/Pipeline/PumpStationDsl.kt` | (search source) | `~/.TPipe-Debug/...` | `${TPipeConfig.getTraceDir()}/...` |
| `src/main/kotlin/Util/Util.kt` | (search source) | `~/.TPipe-Debug/...` | `${TPipeConfig.getTraceDir()}/...` |
| `src/main/kotlin/Debug/TracingBuilder.kt` | (search source) | `~/.TPipe-Debug/...` | `${TPipeConfig.getTraceDir()}/<component>/` |
| `src/main/kotlin/Debug/TraceConfig.kt` | (verify exact line) | `val exportPath: String = "~/.TPipe-Debug/traces/"` | Should compute from `TPipeConfig.getTraceDir()` |

## How to Re-Run the Inventory

```bash
cd /home/cage/Desktop/Workspaces/TPipe/TPipe
grep -rn '~/\.TPipe-Debug' src/main src/test
grep -rn '\.TPipe-Debug' TPipe-*/src
```

Expected result post-cleanup: zero hits across all three greps. The only acceptable matches would be:

1. This inventory reference file (which documents the literals, not the code's own).
2. The deprecated-path explanatory docstring in `PumpStationMiniMaxLiveTest.kt` (kept as a signpost that the legacy path is no longer the canonical one — 2026-07-06 fix).

## Why Not Just Replace and Move On

These 4 files have not been patched in 2026-07-06's session because the user asked specifically for the test-only fix. Future sessions should:

1. Patch each file's literal to call `TPipeConfig.getTraceDir()`.
2. Verify the `TraceConfig.exportPath` default is moved to a `getDefaultExportPath()` companion function or similar lazy resolver — not a hard-coded string.
3. Re-run the inventory grep until empty.
4. Add integration tests that assert on a `TraceConfig`'s resolved `exportPath` matching the canonical resolver.

A dedicated plan file at `.hermes/plans/tpipe-trace-default-cleanup.md` would track the full cleanup.
