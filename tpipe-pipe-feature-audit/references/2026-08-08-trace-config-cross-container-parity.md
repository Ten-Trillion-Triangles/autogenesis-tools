# TraceConfig feature parity across TPipe orchestration containers (2026-08-08)

## What this captures

The companion session-applied reference to the cross-container parity section in `tpipe-pipe-feature-audit`. The cross-provider audit (1.8.0) asks "does feature X behave consistently across all LLM provider modules (TPipe-Bedrock / TPipe-GenericOpenAI / TPipe-Ollama / TPipe-OpenRouter)?" This reference captures the orthogonal question for TPipe's orchestration containers: "does `TraceConfig` feature X behave consistently across all 6 container types?"

Same shape (4×N scorecard of features × containers), different layer (containers within the SDK, not SDK modules).

## The 6 containers in scope

| Container | getTraceReport location | autoExport honored? |
|---|---|---|
| `Pipeline` | `Pipeline.kt:860-879` | ✅ Yes |
| `PumpStation` | `PumpStation.kt:2815-2838` | ✅ Yes |
| `Manifold` | `Manifold.kt:2482-2485` | ❌ No |
| `Splitter` | `Splitter.kt:568-571` | ❌ No |
| `Junction` | `Junction.kt:1558-1561` | ❌ No |
| `DistributionGrid` | `DistributionGrid.kt:1208-1211` | ❌ No |

## The 2026-08-08 audit findings

The operator opened the session with "identify dead vars and params, `autoExport` is one example." That framing led to a wider sweep. The headline finding is that `TraceConfig.autoExport` and `TraceConfig.exportPath` — declared in `Debug/TraceConfig.kt:19-20` — are honored by 2 of 6 containers and silently ignored by 4. Users wiring `manifold { tracing { autoExport(true) } }` get nothing.

The full dead-code sweep captured alongside this finding:

1. **5 dead private fields** with no setter and no read:
   - `PumpStation.kt:306 maxConcurrentAgents = 3`
   - `PumpStation.kt:328 parentTokenBudgetSettings: TokenBudgetSettings? = null`
   - `PumpStation.kt:407 truncationSettings: TruncationSettings? = null` (a shadow of the per-pipe field elsewhere)
   - `Splitter.kt:292 isExecuting = false`
   - `HttpSecurityManager.kt:123 privateNetworkRanges` (list of 8 CIDRs; `isPrivateNetwork()` uses inline `when` instead)

2. **11 interface no-op stubs in `P2P/P2PInterface.kt`** (L30, 36, 42, 57, 76, 96, 109, 137, 158, 164, 179). Empty-body interface defaults that silently no-op when a concrete class forgets to override. **Fix:** make the interface abstract so the compiler forces every implementer to wire these.

3. **13 emitted-but-unconsumed trace events** in `Debug/TraceEventType.kt` — emitted into the store, dropped at render time. Highest priority: `KILLSWITCH_TRIPPED` (operators need to see killswitch trips).

4. **2 declared-but-unemitted trace events**: `PAUSE_POINT_CHECK`, `PIPE_TIMEOUT`.

5. **~10 dead function parameters** (e.g. `setJsonInput(json, senddefaults)` at `Pipe.kt:2941` ignores both args; `setValidatorPipe(saveSnapshotAsPageKey)` at `Pipe.kt:4859` ignores the boolean).

## Verification recipe (the cross-container parity cells)

```bash
# For each container, locate the autoExport-branch in getTraceReport
for f in Pipeline PumpStation Manifold Splitter Junction DistributionGrid; do
  echo "=== $f ==="
  grep -nE 'autoExport|exportPath|writeStringToFile' \
    "/home/cage/Desktop/Workspaces/TPipe/TPipe/src/main/kotlin/Pipeline/$f.kt" 2>/dev/null \
    || grep -rnE "$f.kt.*autoExport" \
      /home/cage/Desktop/Workspaces/TPipe/TPipe/src/main/kotlin/Pipeline
done
# Expected: Pipeline + PumpStation show 2-3 hits; Manifold/Splitter/Junction/DistributionGrid show 0.
```

## Fix shape for the autoExport parity defect

Apply the same `if(traceConfig.autoExport) { ... }` block across all 4 missing containers:

```kotlin
fun getTraceReport(format: TraceFormat = traceConfig.outputFormat): String
{
    val report = PipeTracer.exportTrace(<containerId>, format)
    if(traceConfig.autoExport)
    {
        val extension = when(format) {
            TraceFormat.HTML -> "html"
            TraceFormat.JSON -> "json"
            TraceFormat.MARKDOWN -> "md"
            TraceFormat.CONSOLE -> "txt"
        }
        val filename = "<container-prefix>-${<containerId>.take(<N>)}.$extension"
        val exportPath = traceConfig.exportPath.trimEnd('/') + "/" + filename
        writeStringToFile(exportPath, report)
    }
    return report
}
```

`<containerId>` and `<container-prefix>` vary per container:
- Manifold: `manifoldId`, prefix `manifold`
- Splitter: `splitterId`, prefix `splitter`
- Junction: `junctionId`, prefix `junction`
- DistributionGrid: `gridId`, prefix `grid`

The Pipeline.kt:873 version has a malformed filename — `"trace-${pipelineId.take(8)}-$extension.${extension}"` produces `trace-abc12345-html.html`. Fix to `"trace-${pipelineId.take(8)}.$extension"`. Cosmetic, but a clear sign the code path was never run end-to-end.

## Why this is a class-level pattern, not a one-off

The cross-container audit is structurally identical to the cross-provider audit (1.8.0):

- Both ask "does feature X behave consistently across N implementations?"
- Both produce an N-row scorecard
- Both fail in the same shape: 2 of N implemented, N-2 silently ignored
- Both require a verification recipe that explicitly enumerates each row

The reason the patterns were not caught earlier is that **no compiler or test signal flags "container N ignored the contract"**. The contract is documented in `TraceConfig.kt` and a builder/DSL method exists on `PumpStationTracingDsl` / `TracingBuilder`, but the contract is silent about which containers must honor it. A future auditor scanning for "how many containers implement autoExport?" would catch it; nobody asks that question because the contract looks complete.

**Lesson for future contract audits:** when a feature has both a configuration site (the field on `TraceConfig`) and a builder site (`tracing { autoExport() }`), also enumerate the *consumer* sites — every class that reads the field. The number of consumer sites IS the parity scorecard.

## Related

- `tpipe-pipe-feature-audit` § "Cross-provider feature parity audit" — the provider-modules equivalent, captured 2026-08-02.
- `references/2026-08-02-provider-feature-parity-breakdown.md` — the provider-modules scorecard.
