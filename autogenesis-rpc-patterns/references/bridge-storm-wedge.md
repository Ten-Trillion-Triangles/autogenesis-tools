# Bridge-storm wedge (RestRpcBridgeJs.connect) and the UI e2e harness that caught it

Added 2026-08-12. Companion to `rpc-auto-registration-verification.md` — that file proves the auto-registration chain fires; this file proves the BRIDGE STATE is healthy after a 4-5-call connect storm. The two failure classes are different.

## The wedge symptom

A `Map.Upload.Success` notification never lands on the kvisionApp. Console shows:

```
[info] MapUploadModal: state VALIDATED -> PUBLISHING file=tiny-map.map size=2566
[warning] MapUploadModal: ServerExtendBridge.rpcInvoker is null (disconnected); aborting publish
```

`ServerExtendBridge.rpcInvoker` returns null 8-11 seconds after page load — too late for the publish click to see a live client. The `Map.Upload.Success` channel is irrelevant because no RPC is even being attempted.

## Root cause

SKIP-LOGIN (`?skipLogin=true`) boot fires 4-5 `ServerExtendBridge.connect()` callbacks within 9ms during the post-loading-screen rebind. Each call uses `generatePlayerId()`, so the dedup at the old `RestRpcBridgeJs.connect` form `currentPlayerId == playerId && currentAccelbyteId == accelbyteId && isConnected` fails (different random playerId each time, but same `accelbyteId='guest-user'`). Each call tears down the previously-installed `RestRpcClient`. 8-11 seconds later, the surviving client's SSE channel is silently torn down by an orphaned auto-reconnect coroutine (the old client's auto-reconnect schedule fires after its `internalScope` is canceled — race window).

Six call sites funnel into this storm:
- `Main.kt:252` — `RestRpcBridge.connect(accelbyteId = globals.AccelByteEnv.userId)` after loading-screen-await
- `Main.kt:682` — `ServerExtendBridge.connect()` (no args, default `accelbyteId=null`)
- `LoginWidgets.kt:719` — `RestRpcBridge.connect(accelbyteId = userInfo.userId)` in the Login As Guest path
- `ServerExtendBridge.kt:101` — `SharedRestRpcBridge.connect(...)` called transitively by the above
- `RestRpcBridge.kt:78` — `SharedRestRpcBridge.connect(...)` wrapper called by `Main.kt:252`
- A fifth call path that comes from the `suspend fun onconnected { ... }` listeners firing

`generatePlayerId()` is a fresh `Random.nextInt().absoluteValue` per call — every connect() has a unique `playerId`, defeating the old dedup.

## The fix (verified 2026-08-12)

`sharedModel/src/jsMain/.../network/RestRpcBridgeJs.kt` and JVM sibling `sharedModel/src/jvmMain/.../network/RestRpcBridgeJvm.kt`. Replace the old dedup with a `client?.let { existing -> ... }` block that keys on `accelbyteId` only:

```kotlin
client?.let { existing ->
    val boundAccelbyteId = currentAccelbyteId
    if (boundAccelbyteId != null &&
        accelbyteId != null &&
        boundAccelbyteId == accelbyteId &&
        existing.isConnected()) {
        console.info("RestRpcBridge: skip rebind — already bound to accelbyteId=$accelbyteId (was playerId=$currentPlayerId, incoming playerId=$playerId)")
        Logger.info(
            LogCategory.NETWORK,
            "RestRpcBridgeJs.connect: skipping rebind — same accelbyteId=$accelbyteId, current playerId=$currentPlayerId is connected (incoming playerId=$playerId rejected to defuse the boot reconnect storm)"
        )
        return
    }
}
```

Before tearing down the previous client, clear `client = null` first — this prevents re-entrant calls from racing. The order of operations matters:

1. `old = client` (snapshot the existing reference)
2. `client = null` (vacant before teardown begins)
3. `old?.let { it.disconnect(); try { it.close() } catch (...) { ... } }` (tear down the old one)

The structured form (`client?.let { existing -> ... }`) is required, not stylistic — see the Kotlin/JS precedence hazard below.

## Kotlin/JS precedence hazard

`x != null && y != null` in Kotlin source compiles to JS as `!(x == null) && !(y == null)`. JS operator precedence (`==` > `!`) means this is parsed as `(!x) == null && (!y) == null`, where `(!x) == null` is always `false` because `(true|false) == null` is never `true`. **The Kotlin/JS compiler emits the parens as `!(x == null)` (correct null-check) — works fine.** But the shape is fragile: any future change to how Kotlin/JS emits this (or a hand-rewrite of the bytecode) can break the chain. Use `client?.let { x -> ... }` (safe-call) which compiles to `tmp0_safe_receiver !== null` (receiver safe-call) — no chained-`!=` to reason about. Always prefer the structured form in sharedModel code that runs on both JVM and JS.

## The verification probe

`kvisionApp-e2e/probes/map-upload-e2e.mjs` — 22-check Playwright probe driving the full map upload flow end-to-end. The probe catches the bridge-storm wedge as Phase 6's failure mode (publish button never transitions to `data-state=publishing` because the early-exit at `MapUploadModal.kt:364` fires when `ServerRpcBridge.rpcInvoker` returns null). The probe is at the live, working state as of 2026-08-12.

The probe phases:

1. Navigate `?skipLogin=true` and wait for `[data-testid="main-menu"]`.
2. Open Collection overlay, click MAPS tab.
3. Click `[data-testid="maps-upload-button"]`, wait for modal.
4. Click `[data-testid="map-upload-file-input"]` with `setInputFiles(tests/fixtures/tiny-map.map)`, assert drop-zone `data-state=validated`, name pre-filled.
5. **Bridge-stabilize reload** — `page.reload()`, repeat phases 2-4. This is a belt-and-suspenders step that gives the bridge a clean single-connect cycle.
6. Click `[data-testid="map-upload-publish"]`, assert `data-state=publishing`, text `"Publishing…"`, cancel+close disabled.
7. Wait for either "Map uploaded" MessageBox (success) or "Upload failed:" MessageBox (error).
8. Capture every `console.log/info/warn/error` to `artifacts-map-upload-e2e/all-console.txt`.

## Build/restart cycle for the kvision dev server

When iterating on sharedModel changes, the dev cycle traps people. The minimal sequence that actually deploys a JS-side change to the running browser:

```bash
# 1. Edit sharedModel/src/jsMain/kotlin/.../RestRpcBridgeJs.kt
# 2. Recompile sharedModel JS
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :sharedModel:compileKotlinJs --no-daemon

# 3. Rebundle kvisionApp (sharedModel.js is a separate AMD chunk)
./gradlew :kvisionApp:assemble --rerun-tasks --no-daemon

# 4. Restart webpack-dev-server (it serves build/js/packages/Autogenesis-kvisionApp/kotlin/Autogenesis-kvisionApp.js)
#    runKvisionNoHotReload is a ROOT project task, NOT :kvisionApp:
./gradlew runKvisionNoHotReload > /tmp/autogenesis-proxy/kv-restart.log 2>&1 &
ss -tlnp 2>/dev/null | grep :8080   # confirm listening

# 5. Re-run probe
cd kvisionApp-e2e
node probes/map-upload-e2e.mjs 2>&1 | tail -50
```

**`runKvisionNoHotReload` is a ROOT project task** (not `:kvisionApp:`). Trying `:kvisionApp:runKvisionNoHotReload` errors with "task not found in project :kvisionApp". The ROOT task wraps `:kvisionApp:jsBrowserDevelopmentRun` with `KVISION_DISABLE_HOT_RELOAD=true`.

**Bundle layout** — webpack creates TWO AMD chunks:
- `build/js/packages/Autogenesis-kvisionApp/kotlin/Autogenesis-kvisionApp.js` — kvisionApp wrapper code
- `build/js/packages/Autogenesis-kvisionApp/kotlin/Autogenesis-sharedModel.js` — sharedModel impl (where `RestRpcBridgeJs` lives)

kvisionApp loads sharedModel via AMD `define(['exports', './Autogenesis-sharedModel.js', ...], factory)`. If sharedModel is updated, you must rebuild the kvisionApp bundle too — otherwise kvisionApp serves the OLD in-memory reference while sharedModel.js on disk is new, and the fix won't take effect. Symptoms: console shows your new `Logger.info(...)` log lines (from sharedModel.js running), but the behavior is unchanged (from kvisionApp.js's cached view of the old sharedModel API). To verify the fix is in the served bundle:

```bash
# On-disk bundle (what should match the source)
grep -c 'skipping rebind' /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/packages/Autogenesis-kvisionApp/kotlin/Autogenesis-sharedModel.js

# Served bundle (what the browser actually loads)
curl -s 'http://localhost:8080/Autogenesis-sharedModel.js' | grep -c 'skipping rebind'
```

Both should match. If on-disk has the fix but served doesn't, webpack-dev-server is serving a stale in-memory version — kill and restart `runKvisionNoHotReload`.

## Console capture pattern

`page.on('console', msg => captured.push(\`[${msg.type()}] ${msg.text()}\`))` is the only sink that captures all entries in this build. AGENTS.md:72's claim about `localStorage['autogenesis_logs']` persistence is stale — `sharedModel/.../LogWriter.js.kt:34-43` says "localStorage persistence removed for performance." The JS log writer writes to `console.log`/`info`/`warn`/`error` and (in DEBUG mode) POSTs to `http://127.0.0.1:9080/api/browser-log` every 3s. Without console capture, you can't see what the bridge was doing 8 seconds before a publish click — the log lines from the failed `rpcInvoker is null` early-exit are the smoking gun.

## The 14 data-testids for the upload UI surface

| testid | widget |
|---|---|
| `data-testid="main-menu"` | MainMenu root |
| `data-testid="collection-overlay"` | CollectionOverlay root |
| `data-testid="maps-upload-button"` | "UPLOAD MAP" gold-gradient button |
| `data-testid="map-upload-modal"` | MapUploadModal root |
| `data-testid="map-upload-drop-zone"` | drop zone, `data-state="idle"\|"validated"` |
| `data-testid="map-upload-browse-link"` | "browse from your computer" link |
| `data-testid="map-upload-file-input"` | hidden `<input type=file accept=".map">` |
| `data-testid="map-upload-name-input"` | name input, pre-filled from filename |
| `data-testid="map-upload-description-input"` | description textarea |
| `data-testid="map-upload-info-text"` | "Maps enter a brief review queue..." text |
| `data-testid="map-upload-cancel"` | Cancel button |
| `data-testid="map-upload-publish"` | Publish button, text "Publish to review" / "Publishing…" |
| `data-testid="map-upload-close"` | X close button |
| `data-testid="loading-screen-cta"` | Loading screen CTA (dismiss) |

## Two failure modes the probe catches

1. **Bridge-storm wedge** (this file) — fix at `RestRpcBridgeJs.connect` dedup. Phase 6 fails because the publish button never enters `data-state=publishing` — the early-exit at `MapUploadModal.kt:364` fires when `ServerExtendBridge.rpcInvoker` returns null.
2. **RPC Fail to fetch** — post-fix surface. The RPC fires (button transitions to `data-state=publishing`, "Publishing…" text shows) but `RestRpcClient.send: Failed to send to http://127.0.0.1:7070/rpc?... - Fail to fetch` fires before reaching the server. Phase 8 (error path) PASSES — "Upload failed: Network error" MessageBox renders correctly. Likely CORS preflight or cookie/credential issue on the POST path; SSE channel works fine via direct curl. As of 2026-08-12 root cause not nailed down.

The probe is at `kvisionApp-e2e/probes/map-upload-e2e.mjs`. Bridge-state diagnostic (faster, ~5s) at `kvisionApp-e2e/probes/bridge-state-probe.mjs`.
