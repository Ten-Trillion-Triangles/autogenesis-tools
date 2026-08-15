# Case-Insensitive Path Registry (worked example)

**Captured:** 2026-07-24 from the PumpStation path-safety rejection triage session.

## The Bug

PumpStation's `pathList` map was documented as case-insensitive (the KDoc on `pathList` at `PumpStation.kt:1178-1180` says "Names are normalized to be case-insensitive, and all path calls will normalize to lowercase when calling a path") but the implementation was inconsistent:

- `addPath` at `PumpStation.kt:2773` stored `pathList[path.pathName]` (case-preserved)
- `resolvePath` at `PumpStationHelpers.kt:773` looked up `pathList[lowerName]` (lowercased)
- `parseDispatchOutput` is the LLM-side counterparty, and `PathRequest` is the schema the LLM is asked to return

Any path with a non-lowercase character (e.g. `path("giveUp")`) was registered under key `"giveUp"` but looked up under key `"giveup"`, returning `null` → `UnknownPath` at `PumpStationLoop.kt:711`.

## The Trace Evidence

`~/.tpipe/debug/trace/PumpStation/live-04-multi-path-risk-levels/pumpstation-ps-178484965.html` showed:

```
19× PUMP_STATION_PATH_FAILED with pathName='giveUp', error=UnknownPath, errorMessage="Path 'giveUp' not found"
1× taskState.exitReason = "MaxTurnsHit"
1× harness status: ps-status-failed
```

The same trace's `agent-dispatch.html` (per-agent trace dump) showed the LLM's dispatch prompt contained the visible-paths list with `giveUp` listed as a registered path. The LLM genuinely saw the path in its menu, picked it, and the harness rejected it. **The bug was the registry, not the LLM, not the prompt.**

## The Fix (6 sites, 1 helper)

File-local helper at `PumpStation.kt:1188-1195`:

```kotlin
private fun pathKey(name: String): String = name.lowercase()
```

Six insert/lookup sites routed through it:

| Site | Before | After |
|------|--------|-------|
| `addPath` (L2773) | `pathList[path.pathName] = path` | `pathList[pathKey(path.pathName)] = path` |
| `addReservePath` (L5160) | `reservePaths[path.pathName] = path` | `reservePaths[pathKey(path.pathName)] = path` |
| `getPath` (L2762) | `pathList[name] ?: reservePaths[name]` | `pathList[pathKey(name)] ?: reservePaths[pathKey(name)]` |
| `removePath` (L2781) | `pathList.remove(name)` | `pathList.remove(pathKey(name))` |
| `movePathToReserve` (L2790-2792) | `pathList.remove(name)`, `reservePaths[name]` | both `pathKey(name)` |
| Two direct lookups in `mergeDrainedEntries` (L4678, L4695) | `pathList[name] ?: reservePaths[name]` | `pathList[pathKey(name)] ?: reservePaths[pathKey(name)]` |

Plus `revealedReservePaths` (a `MutableSet<String>` at L1854) — three sites in `getVisiblePathDescriptorsInternal` (L2210-2211, L2222) needed `pathKey(...)` normalization on insert and lookup.

`getVisiblePathNames` (L2806) and `getReservePathNames` (L2815) were also changed to read `pathList.values.map { it.pathName }` (original casing) instead of `pathList.keys` (lowercased). This keeps the LLM-facing menu showing the registered casing (`giveUp`) rather than the map-key casing (`giveup`).

## The Tests

`src/test/kotlin/Pipeline/PumpStationPathCaseInsensitiveTest.kt` (6 tests, all green):

1. `addPath with mixed case is reachable via getPath with any case` — covers `addPath` + `getPath` (4-case lookup: exact, lower, upper, title)
2. `getVisiblePathNames preserves original casing` — covers the `values.map { it.pathName }` change
3. `removePath with any case removes the path` — covers `removePath`
4. `resolvePath returns the same instance for any case` — covers `resolvePath` lookup (via `getPath` since they're the same map)
5. `dispatching a mixed-case path name reaches the registered path` — end-to-end via the dispatch contract
6. `revealing a reserve path with mixed case populates the visible list with original casing` — covers `reservePath` registration + `revealedReservePaths` set membership

## Why Every Other Container Has the Same Bug

The pattern: "name-keyed map with documented case-insensitive contract, but case-preserved insert" is a class of bug that recurs across every PumpStation-shaped container:

- **Manifold's worker registry** — `worker("Foo")` + dispatch by `workerName` would hit the same key-normalization mismatch.
- **Junction's participant map** — `participant("Alice")` + lookup by `Alice` vs `alice` is the same shape.
- **DistributionGrid's node table** — `registerNode("Grid-1")` + route by name is the same shape.
- **PipeSettings'** named-pipe map (if any) — same shape.

The `pathKey(name): String = name.lowercase()` pattern is the canonical fix for any name-keyed map. The test matrix (case-lookup + original-casing visibility + end-to-end dispatch) is reusable for any of these.

## Verification

```bash
./gradlew :test --tests "com.TTT.Pipeline.PumpStationPathCaseInsensitiveTest" --rerun-tasks
# → BUILD SUCCESSFUL, 6 tests pass
```

`./gradlew :test --tests "com.TTT.Pipeline.PumpStation*" --rerun-tasks` (the broader non-live subset) stays green — no regressions in the 13 test classes that exercise addPath/getPath/removePath on the registry.

## Commits (this fix)

- `bf3c07ce test(pumpstation): pin case-insensitive path lookup contract (RED)`
- `730ef6d4 fix(pumpstation): lowercase path map keys for case-insensitive lookup`
- `b8fdc4f0 fix(pumpstation): getVisiblePathNames/getReservePathNames return original path-name casing`
- `b1439363 fix(pumpstation): revealedReservePaths uses case-insensitive membership`

Plan file: `.hermes/plans/2026-07-24_003213-pumpstation-path-case-insensitive-lookup.md`.
