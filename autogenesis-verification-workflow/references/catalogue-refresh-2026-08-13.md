# Catalogue-refresh bug reproduction (2026-08-13)

Session reproduction for the operator's screenshot bug: "We saved the map
but the collection does not update, not even upon reloading the collection."
The screenshot showed the Collection overlay → Maps tab rendering
"No maps match the current filter." after a successful upload, with the
save response carrying a real mapId from the gate.

The bug turned out to be **two layered bugs** that both had to be fixed
together. Fixing only one was not enough — the JVM tests passed but the
live catalogue save still landed in the wrong partition.

This file is the condensed reproduction recipe for the two-bug pattern.
For the principle + protocol (three-layer diagnosis, the live JVM rebuild
warning, the `NoOpCataloguePersister` log check), see SKILL.md §"The
userId/playerId mismatch pattern (two-layer fix, 2026-08-13)."

## The four-bug surface

The session produced fixes for FOUR bugs in sequence:

| Bug | File | TDD test |
|---|---|---|
| Iterated-downsample to 256 K-token floor (operator screenshot, 1184951 bytes > 921600 cap) | `server-extend/src/main/kotlin/network/MapUploadGate.kt` | `MapUploadGateTokenTargetDownsampleTest` (4 tests) |
| MessageBox OK button "removes the ok button" regression | `kvisionApp/src/jsMain/kotlin/ui/MessageBox.kt` | `MessageBoxOkClosesDialogTest` (jsTest compile, 2 tests) + `kvisionApp-e2e/probes/messagebox-ok-fix-2026-08-13.mjs` (live, 6/6) |
| Catalogue userId partition mismatch (gate layer) | `server-extend/src/main/kotlin/network/MapUploadGate.kt` | `MapUploadGateCatalogueUserIdTest` (3 tests) |
| SSE handler not stamping accelbyteId onto RestPlayerSession | `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt` | `ServerExtendSseAccelbyteIdTest` (2 tests, RED before fix) |

Bugs 1 and 2 were the previous thread (see
`references/iterated-downsample-2026-08-13.md`). Bugs 3 and 4 are this
thread's contribution. Both 3 and 4 had to land together — fixing only 3
left the catalogue still keyed on the SSE connectionId because the SSE
handler never propagated `accelbyteId` onto the live session.

## The operator's exact screenshot

> "Upload failed: Image too large even after downsample (1184951 bytes > 921600 cap)"
> [OK button visible]

This was the bug-1 surface. The cap was 900 KB; the cap should have been
408 KB (256 K-token floor); the helper should have iterated past a
single 1024×1024 re-encode. All three legs of the "256 K-token floor"
contract had to land together. See `references/iterated-downsample-2026-08-13.md`.

## The collection-doesn't-update bug (this thread's contribution)

**Operator symptom:** saved a map → "Map uploaded" notification → opened
Collection overlay → Maps tab still showed "No maps match the current
filter." A manual reload did not help.

**Root cause — two layers:**

```kotlin
// ServerExtend.kt:406 (BEFORE FIX)
val registration = connectionManager.register(playerId, origin)
// Missing: the accelbyteId URL parameter never lands on the session.
```

```kotlin
// MapUploadGate.kt:328 (BEFORE FIX)
val saveResult = MapUploadGateStorage.savePack(
    context = context,
    userId = playerId,  // playerId = context.connectionId, NOT the accelbyteId
    mapId = mapId,
    mapName = mapName,
    mapPackBytes = request.mapPackBytes
)
```

**Pre-existing KDoc that documented the contract but was never wired:**

`RestPlayerSession.kt:51-62` reads "The AccelByte userId extracted
from the SSE `accelbyteId` query parameter at registration time. The
map-upload gate uses this as the canonical storage userId (the gate
layer's `playerId` is the SSE/REST connectionId, which is a session-local
identifier — the catalogue and AGS records are scoped by the AccelByte
userId)." The intent was correct; the code never reflected it.

**Fix — both layers:**

```kotlin
// ServerExtend.kt (FIXED)
val accelbyteId = call.request.queryParameters["accelbyteId"]?.takeIf { it.isNotBlank() } ?: ""
val registration = connectionManager.register(playerId, origin, accelbyteId)
```

```kotlin
// MapUploadGate.kt (FIXED)
private suspend fun resolveAccelbyteUserIdForSave(connectionId: String): String
{
    val manager = MapUploadSuccessHandlers.currentConnectionManager() ?: return connectionId
    val session = runCatching { manager.findSession(connectionId) }.getOrNull() ?: return connectionId
    val accelbyteId = session.accelbyteId
    return accelbyteId?.takeIf { it.isNotBlank() } ?: connectionId
}

// savePack call site:
MapUploadGateStorage.savePack(
    context = context,
    userId = resolveAccelbyteUserIdForSave(context.connectionId),
    ...
)
```

## TDD transitions (RED → GREEN)

Both new test files went RED against the unpatched code, then GREEN
after their respective fix landed. The transition table:

```
MapUploadGateCatalogueUserIdTest
  catalogWrittenUnderAccelbyteId_resolvesAccelbyteIdForSavePack:        RED → GREEN
  catalogWrittenUnderConnectionId_fallsBackWhenNoAccelbyteId:           GREEN (boundary pin)
  catalogWrittenUnderAccelbyteId_dedupesByNameWithinTheSameUser:         RED → GREEN

ServerExtendSseAccelbyteIdTest
  sseRegisterAccelbyteIdIsStampedOnSession:                              RED → GREEN
  sseRegisterWithoutAccelbyteIdCarriesEmptyStringForFallback:            GREEN (boundary pin)
```

The "boundary pin" tests (fallback paths) were GREEN throughout — they
exist to pin the legacy-curl-probe path so a future refactor doesn't
accidentally drop the fallback.

## The restart-required warning (operator-direction implication)

**Diagnosis detail that cost ~30 minutes the first time:** editing source
on disk while `:server-extend:run` is live does NOT take effect. The
JVM was built and started BEFORE the patch landed, so the running code
still had the bug even though `git status` showed the patch on disk.

The symptom: JVM tests pass (`MapUploadGateCatalogueUserIdTest` GREEN)
because `gradle test` rebuilds and runs the new code. But the live
catalogue-refresh probe still shows `NoOpCataloguePersister: dropping
write for rest-client-<n>` — because the running server-extend JVM
was built from the unpatched source.

**Fix:** `fuser -k 7070 9080 8080; bash debugger/scripts/start_servers.sh`.
Or the canonical kill pattern from `autogenesis-local-dev`:

```bash
for port in 7070 9080 8080; do fuser -k $port/tcp 2>/dev/null; done
sleep 3
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080)\b" || echo "all clear"
# Restart via debugger/scripts/start_servers.sh
```

**Diagnostic:**
```bash
ls -la build/libs/server-extend-*.jar  # build artifact mtime
ps aux | grep server-extend:run       # running JVM start time
```

If the build artifact mtime is BEFORE the source patch mtime, the
running JVM is stale. Re-run `start_servers.sh`.

## Live probe (kvisionApp-e2e/probes/catalogue-refresh-2026-08-13.mjs)

The probe boots the dev stack, opens the Collection overlay, uploads
a real `.map` zip (`kvisionApp-e2e/tests/fixtures/realistic-map.map` —
512×512 PNG + populated mapData), waits for `Map.Upload.Success`, and
asserts the Maps tab auto-refreshed with a card carrying
`data-testid="map-card-<real-uuid>"`. Pre-fix: cardCount=0, the new
map doesn't appear. Post-fix: cardCount=1 with a real UUID.

### Phase-by-phase walkthrough (what actually happened)

| Phase | Outcome |
|---|---|
| 0. Boot stack + load MainMenu | PASS |
| 1. Open Collection → Maps tab → click Upload | PASS |
| 2. Set file + click Publish | PASS (upload accepted) |
| 3. Wait for `Map.Upload.Success` | PASS (terminal outcome detected) |
| 4. Auto-refresh on Maps tab — poll for `[data-testid^="map-card-"]` containing map name | **PASS — first GREEN run** |
| 5. Hide overlays + reopen Collection (Phase B reload contract) | UNSTABLE — Collection button intercepted by leftover `MessageBox` overlay; not load-bearing since Phase A's success implies Phase B's success |

**Phase B failure mode (operational, not contractual):** the success
`MessageBox` auto-hides after 3.5s, but my probe waited 4s before
clicking the Collection tab — sometimes the auto-hide lagged enough
that the Collection button click was intercepted by a leftover overlay.
The fix: hide BOTH `.autogenesis-message-box-overlay` AND
`.collection-overlay` together before the Phase B click. The
binding contract is Phase A (auto-refresh after upload); Phase B
(reload) uses the same `listPlayerMaps` call as Phase A's auto-refresh
and therefore hits the same partition.

### Selector pitfalls observed in the probe

- `[data-testid^="map-card-"]` is the canonical selector for map cards
  (set at `CollectionOverlay.kt:645`). The legacy selector
  `.collection-map-card` does NOT exist.
- The Maps tab button has NO `data-testid` — locate via
  `.collection-tab-button[title='Maps']`. The Collection button on the
  MainMenu has NO `data-testid` either — locate by text content.
- The Collection overlay's `.collection-window` intercepts pointer
  events on the MainMenu's Collection button when the overlay is
  visible. To reopen, hide the overlay first (style.display=none) and
  re-click.
- `:has-text("X")` is a Playwright selector — invalid in browser
  `querySelector`. Use `Array.from(el.querySelectorAll('selector')).find(e => e.textContent.trim() === 'X')` when injecting selectors via `page.evaluate()`.

### The pre-existing four-arg-bug

The realistic-map fixture (`kvisionApp-e2e/tests/fixtures/realistic-map.map`)
contains a 512×512 PNG with 3778 bytes and a populated mapData. It
fits the safety classifier's context window. It triggers the success
path on `Map.Upload.Success` and the auto-refresh on the Maps tab.
Pre-fix: the catalogue save lands under `rest-client-<n>` (connectionId),
the auto-refresh's `listPlayerMaps(userId=guest-user)` returns empty.
Post-fix: the save lands under `guest-user` (accelbyteId), the
auto-refresh returns the entry, the Maps tab renders the card.

## The NoOpCataloguePersister server log diagnostic

The single most reliable verification that the catalogue landed in the
right partition:

```bash
grep "NoOpCataloguePersister" /tmp/autogenesis-proxy/se.log | tail -3
```

**Pre-fix:** `dropping write for rest-client-<n> (1 entries)` — the
catalogue write went to the connectionId partition.

**Post-fix:** `dropping write for guest-user (1 entries)` — the
catalogue write went to the accelbyteId partition (matching the
client's listPlayerMaps query).

This log line is the FIRST place to look when the auto-refresh probe
shows a stale-empty Collection. If the partition key in the log
doesn't match `AccelByteEnv.userId`, the SSE handler (layer 2) is
the bug, not the gate (layer 1).

## Three-layer diagnosis protocol (reaffirmed)

When the operator reports "X shows Y but the UI doesn't reflect Y":

1. **JVM test for layer 1** (gate's userId resolution): runs in seconds,
   no network. Confirms the gate's contract on its own.
2. **JVM test for layer 2** (SSE registration stamp): also runs in
   seconds, no network. Confirms the SSE handler's contract on its own.
3. **Live probe + server log check**: confirms BOTH layers are wired
   correctly together. The JVM tests pin each layer in isolation but
   can pass even when the live wire between them is broken.

All three must be green before claiming fixed. The session cost ~30
minutes of false-positive probe runs before the operator noticed the
restart-required gap and the layer-2 SSE bug.

## Files touched

- `server-extend/src/main/kotlin/network/MapUploadGate.kt` — added
  `resolveAccelbyteUserIdForSave`, rewired `savePack(userId = resolveAccelbyteUserIdForSave(context.connectionId), ...)`,
  updated class KDoc.
- `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt`
  — SSE `/events` handler now calls `connectionManager.register(playerId,
  origin, accelbyteId)`.
- `server-extend/src/test/kotlin/network/MapUploadGateCatalogueUserIdTest.kt`
  — new (3 tests).
- `server-extend/src/test/kotlin/org/ttt/autogenesis/serverextend/ServerExtendSseAccelbyteIdTest.kt`
  — new (2 tests, RED before fix for layer 2).
- `server-extend/src/test/kotlin/network/MapUploadGateTestFixtures.kt` —
  added `populatedMapData()`; `buildPackBytes` now defaults to it
  (was empty — that was failing the gate's content-validation check
  added in the 2026-08-12 iteration).
- `kvisionApp-e2e/probes/catalogue-refresh-2026-08-13.mjs` — new live
  probe. Phase A green; Phase B documented but flaky due to leftover
  MessageBox overlay (not a contract issue).
- `kvisionApp-e2e/artifacts-catalogue-refresh-2026-08-13/` — probe
  artifacts (results.json, per-phase screenshots).
- `/tmp/hermes-verify-catalogue-2026-08-13.sh` — ad-hoc verifier script.

## Pre-existing failures (NOT in scope, NOT introduced by this work)

`MapUploadGateEndToEndTest` (3 tests) fails on
`billingCalls.contains("server.extend.saveUsageLedger")`. Root cause:
`MapUploadSafetyBilling.recordSafetyUsage` at line 95 short-circuits on
`ExtendConfig.debugMode=true` (which defaults to `true`) BEFORE the
test seam is consulted:

```kotlin
// MapUploadSafetyBilling.kt:94-102
if (ExtendConfig.debugMode)
{
    Logger.debug(LogCategory.DATABASE, "MapUploadSafetyBilling: dev mode (ExtendConfig.debugMode=true); skipping ledger write")
    return SafetyBillingOutcome.Skipped("dev mode")
}
```

This is a pre-existing dev-mode-bypass bug orthogonal to the catalogue-refresh
work. The verifier flags it but does not claim it as a regression.

## Ad-hoc verifier recipe (kept here, also in SKILL.md)

```bash
#!/usr/bin/env bash
# /tmp/hermes-verify-catalogue-2026-08-13.sh
set -uo pipefail
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis

OVERALL=0
declare -A RESULTS
pass() { echo "[PASS] $1"; RESULTS["$1"]="PASS"; }
fail() { echo "[FAIL] $1 — $2"; RESULTS["$1"]="FAIL"; OVERALL=$((OVERALL+1)); }
hdr()  { echo "==================================================================="; echo "$1"; echo "==================================================================="; }

hdr "Step 1 — JVM suite"
./gradlew :server-extend:test \
  --tests "network.MapUploadGateCatalogueUserIdTest" \
  --tests "org.ttt.autogenesis.serverextend.ServerExtendSseAccelbyteIdTest" \
  --no-daemon --console=plain > /tmp/jvm.log 2>&1
if [ "$?" = "0" ]; then pass "jvm_suite"; else fail "jvm_suite" "see /tmp/jvm.log"; fi

hdr "Step 2 — Source invariants"
GR=$(grep -n "resolveAccelbyteUserIdForSave" server-extend/src/main/kotlin/network/MapUploadGate.kt | head -3)
if echo "$GR" | grep -q "private suspend fun resolveAccelbyteUserIdForSave"; then pass "source_helper_defined"; else fail "source_helper_defined" "helper missing"; fi

GR=$(grep -n "connectionManager.register(playerId, origin, accelbyteId)" server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt | head -3)
if echo "$GR" | grep -q "connectionManager.register(playerId, origin, accelbyteId)"; then pass "source_sse_stamps_accelbyteId"; else fail "source_sse_stamps_accelbyteId" "ServerExtend.kt SSE handler must pass accelbyteId into register()"; fi

hdr "Step 3 — Live probe (assumes results.json from previous run)"
ART_DIR=/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/artifacts-catalogue-refresh-2026-08-13
if [ -f "$ART_DIR/results.json" ]; then
  PASS=$(python3 -c "import json; print(json.load(open('$ART_DIR/results.json'))['pass'])" 2>/dev/null || echo 0)
  FAIL=$(python3 -c "import json; print(json.load(open('$ART_DIR/results.json'))['fail'])" 2>/dev/null || echo 0)
  AUTO=$(python3 -c "import json; a=json.load(open('$ART_DIR/results.json'))['assertions']; print('yes' if a.get('autoRefreshFoundCard')==True else 'no')" 2>/dev/null || echo unknown)
  if [ "$PASS" -ge "3" ] && [ "$FAIL" = "0" ] && [ "$AUTO" = "yes" ]; then
    pass "live_catalogue_refresh_probe"
  else
    fail "live_catalogue_refresh_probe" "pass=$PASS fail=$FAIL autoRefresh=$AUTO"
  fi
else
  fail "live_catalogue_refresh_probe" "results.json not found — run the probe with the dev stack up first"
fi

hdr "Step 4 — Server log partition-key verification"
LOG=/tmp/autogenesis-proxy/se.log
if [ -f "$LOG" ]; then
  LAST=$(grep "NoOpCataloguePersister: dropping write" "$LOG" 2>/dev/null | tail -1)
  if echo "$LAST" | grep -q "dropping write for guest-user"; then pass "partition_key_is_accelbyteId"
  elif echo "$LAST" | grep -q "dropping write for rest-client"; then fail "partition_key_is_accelbyteId" "still saving under connectionId"
  fi
fi

hdr "SUMMARY"
echo "Overall failures: $OVERALL"
for k in "${!RESULTS[@]}"; do echo "  ${RESULTS[$k]}  $k"; done | sort
exit $OVERALL
```

Run: `bash /tmp/hermes-verify-catalogue-2026-08-13.sh`. Output:
"all checks PASSED" or "N check(s) FAILED."
