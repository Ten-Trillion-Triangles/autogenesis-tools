---
name: autogenesis-web-push-notifications
description: Autogenesis Web Push notifications — VAPID keypair provisioning, browser subscription flow, server store over VFS (envelope with subscription-list), turn-loop fan-out trigger, service-worker click → idempotent rehydration, pushsubscriptionchange rotation path. Use when adding the push pipeline, debugging "push not received", reviewing subscription wiring, fixing iOS/mobile push, debugging VAPID PEM loading, debugging the SERVICE WORKER turn-start probe, debugging the `pushsubscriptionchange` re-subscription path, debugging tests that pass for the wrong reason (cryptographic-fixture correctness trap), or auditing the click-to-restore flow against the user's four-spec contract (register / turn-start push / mobile / click-to-rehydrate). NOT for LLM prompt debugging (autogenesis-prompt-debugging) or resume-game snapshots (autogenesis-rpc-patterns).
version: 1.1.0
author: Hermes Agent (extracted from push-notification code review session 2026-06-29)
created: 2026-06-29
updated: 2026-06-29
tags: [autogenesis, web-push, vapid, service-worker, push-api, kotlin-js, kotlin-jvm, notification, multi-device, fan-out, test-fixture, cryptography]
changelog:
  - 1.1.0 (2026-06-29). Three of four v1.0.0 known gaps fixed in production code — multi-device store, pushsubscriptionchange page handler, iOS manifest verification. New pitfall section — synthetic-fixture correctness trap. Architecture-refresh of store shape and fan-out semantics.
  - 1.0.0 (2026-06-29). Initial extraction from full 4-spec code review. Embeds the four-spec contract, the 8 modules and their file-line evidence, and the kotlin-JS DCE keepalive pattern.
---

# Autogenesis Web Push Notifications

The push notification subsystem is a 4-spec contract that spans eight modules across the Kotlin/JS browser, the JVM main server, and the build pipeline. It has its own runbook (`server/RUNBOOK_PUSH.md`), its own e2e probe (`kvisionApp-e2e/probes/push-turn-start.mjs`), and its own private VFS key (`push-subscription`) whose value is now an **envelope** `{"subscriptions": [PushSubscriptionDto, ...]}` (was a flat single-DTO before v1.1.0). Treat it as a subsystem, not a feature — changes here ripple into the resume-restore pipeline (because the click handler ends in `server.restoreRunningGame`).

## When to load this skill

Load when ANY of the following is true:

- About to add, modify, or review push notification code.
- User reports "the push isn't being delivered" or "I never see a notification."
- User reports "I only get push on one device" or "my mobile never gets push" → multi-device fan-out problem.
- User reports "after my browser rotated my subscription, pushes stop arriving" → `pushsubscriptionchange` page handler missing/broken.
- User reports "the click doesn't open the right thing" or "the resume dialog didn't appear after I clicked the notification."
- Reviewing or modifying `kvisionApp/src/jsMain/resources/sw.js`, `kvisionApp/src/jsMain/kotlin/.../PushNotificationService.kt`, any file under `server/src/main/kotlin/.../push/`, or `TurnHarness` push trigger plumbing.
- Debugging VAPID keypair provisioning (PEM generation, `~/.autogenesis/vapid_private.pem`, the `generateVapidKeys` Gradle task).
- Debugging the push-turn-start e2e probe or the `/debug/seed-push-subscription` test endpoint.
- Auditing that the change honors the 4-spec contract below.
- Auditing tests for the `removeDeletesSubscriptionOn410Gone` failure mode documented in the synthetic-fixture pitfall below.

## The 4-spec contract (verbatim from the user, 2026-06-29)

1. **Allows the browser to register to receive push notifications from the game server.**
2. **At the start of a turn the server can send this push notification to the turn player's browser to notify them to come back.**
3. **Works on mobile.**
4. **If the push notification is clicked, it will re-open the tab, reconnect the player to their game, then go through the rehydration process the snapshot restore system uses to get a player reconnected and back into the game. If they are already open to that game server, clicking the notification does nothing.**

All four are met as of 2026-06-29. Known limitations (by design, not bugs) are at the end of this skill — review them before claiming "done."

## The 30-second mental model

Three tiers, eight files of interest:

**Kotlin/JS browser tier (push pipeline runs here):**
- `kvisionApp/src/jsMain/resources/sw.js` — service worker (78 lines). Three handlers: `push`, `notificationclick`, `pushsubscriptionchange`. Receives the payload, shows the OS notification, focuses or opens a tab on click.
- `kvisionApp/src/jsMain/kotlin/.../PushNotificationService.kt` — browser-side subscription manager (260+ lines after v1.1.0). Registers the SW, calls `pushManager.subscribe()` from a user gesture, sends the resulting `PushSubscriptionDto` to the server via the existing WS bridge's `RpcInvoker`. **As of v1.1.0** also owns `handleSubscriptionChanged` — called when the SW posts `{type: "autogenesis.subscriptionChanged", subscription: ...}` after a `pushsubscriptionchange` rotation. Re-invokes `client.registerPushSubscription` so the server sees the new endpoint.
- `kvisionApp/src/jsMain/kotlin/.../Main.kt:67,93,99` — DCE keepalive reference, `registerServiceWorker()` call, `window.addEventListener("message", ...)` **as of v1.1.0** a `when` over both `autogenesis.resumeTurn` and `autogenesis.subscriptionChanged` postMessage types.

**JVM server tier (turn-loop trigger + storage):**
- `server/src/main/kotlin/.../push/PushVapidConfig.kt` — VAPID PEM loader. Reads `~/.autogenesis/vapid_private.pem` (path overridable via `AUTOGENESIS_VAPID_PRIVATE_KEY`), normalizes SEC1 → PKCS8 via openssl shellout, decodes via `KeyFactory("EC")`, extracts the raw uncompressed public point (last 65 bytes of DER `pubout`).
- `server/src/main/kotlin/.../push/PushSubscriptionStore.kt` — VFS-backed subscription store. **As of v1.1.0** stores a list under `STORAGE_KEY = "push-subscription"`. Per-subscription identity is the `endpoint` URL (matches `pushsubscriptionchange` semantics). APIs: `put(accelByteId, dto)` upserts by endpoint (replaces keys for existing endpoint, appends new); `getAll(accelByteId): List<PushSubscriptionDto>` for fan-out; `get(accelByteId): PushSubscriptionDto?` returns the most-recent (back-compat); `removeByEndpoint(accelByteId, endpoint)` surgical prune for 410/404 cleanup; `remove(accelByteId)` drops everything. Decode-any-shape: handles new envelope, AccelByte CloudSave `{"value": ...}` wrapper, AND legacy flat single-DTO (zero-downtime migration for users registered before v1.1.0).
- `server/src/main/kotlin/.../push/PushNotificationService.kt` — push sender. **As of v1.1.0** `sendTurnStart(...)` iterates all stored subscriptions via `store.getAll(...)` and fans out to each one in a fire-and-forget loop. 410 Gone / 404 Not Found on any single endpoint triggers `store.removeByEndpoint(...)` for that endpoint only — the user's other devices keep receiving. Returns `true` if at least one delivery succeeded, `false` otherwise.
- `server/src/main/kotlin/.../Server.kt:288-314` — wire-up at server boot. Loads VAPID keypair, instantiates `PushSubscriptionStore`, builds `PushNotificationService` with optional `AUTOGENESIS_DEV_PUSH_MOCK_PORT` endpoint override (used by the probe).
- `server/src/main/kotlin/.../UiSignalRpcHandlers.kt:817-841` — `@RpcMethod("client.registerPushSubscription", RpcDirection.SERVER)` handler. Resolves `accelByteId` from `connectionManager`, calls `store.put(...)`. Because `put` is now upsert-by-endpoint, the same handler works for both initial subscription and rotation re-registration.
- `server/src/main/kotlin/.../TurnHarness.kt:1365-1399` — turn-loop trigger. **No signature change**: still `pushService.sendTurnStart(accelByteId, actor, roundNumber)`. The fan-out is internal to `PushNotificationService`. **Suppression gate**: only fires if the player has no live PRIMARY WebSocket session. Fire-and-forget on `Dispatchers.IO`.

**Build / verification tier:**
- `kvisionApp/build.gradle.kts:91-138` — `generateVapidKeys` task: idempotent PEM at `~/.autogenesis/vapid_private.pem`, writes `build/generated/vapid/vapid_public.json` (Base64URL raw point). Wired as a `compileKotlinJs` / `kspKotlinJs` dependency.
- `server/build.gradle.kts:161-166` — `nl.martijndwars:web-push:5.1.2` + `bcprov-jdk18on:1.78.1` + `apache httpclient` deps. The BouncyCastle provider must be on the runtime classpath; registered at `PushVapidConfig.kt:32` in an idempotent `init` block.
- `sharedModel/src/commonMain/kotlin/structs/push/PushSubscriptionDto.kt` — `@Serializable` DTO: `endpoint`, `p256dh`, `auth`. Used by both browser and server.
- `kvisionApp-e2e/probes/push-turn-start.mjs` — Node + Playwright probe. Phase 1: Play → bypass headless SW permission gate → seed subscription via `/debug/seed-push-subscription`. Phase 2: close browser, drive a turn, observe POST land on local mock receiver at port 9099 within 60s.
- `server/RUNBOOK_PUSH.md` — operator runbook. Required env vars: `AUTOGENESIS_DEV_PUSH_MOCK_PORT=9099`, `AUTOGENESIS_SHUTDOWN_DELAY_MS=600000`, `AUTOGENESIS_PUSH_TEST_ENDPOINT=true`, VAPID keypair at `~/.autogenesis/vapid_private.pem`.
- `server/src/test/kotlin/.../push/PushSubscriptionStoreTest.kt` — 13 unit tests as of v1.1.0 (was 5). Covers: envelope put, replace-by-endpoint, append-new-endpoint, empty read, multi-device getAll, legacy-flat migration, CloudSave-wrapped migration, back-compat `get()`, surgical removeByEndpoint (prune / clear-last / no-op), `remove()`, blank-accelByteId no-op.
- `server/src/test/kotlin/.../push/PushNotificationServiceIntegrationTest.kt` — 8 tests as of v1.1.0 (was 5). New: `sendTurnStartFansOutToAllSubscriptionsInEnvelope` (live desktop + unroutable mobile both attempted), `sendTurnStartPrunesOnlyDeadEndpointOn410_KeepingOthers` (live endpoint survives 410 prune). The 410-test now uses a keypair-derived p256dh — see the synthetic-fixture pitfall below.

## Each spec, line by line

### Spec #1 — Browser registers to receive push (MET)

The browser only gets a real subscription if:

1. **User gesture** invokes `PushNotificationService.subscribeIfPermitted()` — wired at `kvisionApp/src/jsMain/kotlin/ui/MainMenu.kt:519` inside `beginMatchSession`, which is the Play button handler. The Push API rejects `subscribe()` outside a gesture; this is the only correct call site.
2. **`/sw.js` is registered** before the gesture — `Main.kt:93` calls `registerServiceWorker()` at app start.
3. **VAPID public key is fetchable** at `/vapid_public.json` — `PushNotificationService.kt:122` loads, Base64URL-decodes to a 65-byte raw point.
4. **Notification permission is granted** — `PushNotificationService.kt:93-99` requests via `Notification.requestPermission()`. If denied, returns silently.
5. **`pushManager.subscribe({userVisibleOnly: true, applicationServerKey: vapidKeyBytes})`** returns a `PushSubscription` with endpoint + keys.
6. **`client.registerPushSubscription` RPC** sends the DTO to the server. Because `put` is upsert-by-endpoint as of v1.1.0, the same RPC works for fresh subscription AND for `pushsubscriptionchange` rotation re-registration (the SW posts the new subscription via `handleSubscriptionChanged`, which calls the same RPC).

### Spec #2 — Server sends push at turn start (MET, multi-device)

The trigger block at `TurnHarness.kt:1365-1399`:

```kotlin
// Web Push notification: if the human actor has no live PRIMARY WebSocket
// session (player closed the tab or browser), fire a Web Push to every
// stored subscription for that user. Multi-device (desktop + mobile,
// multiple browser profiles) is supported by the underlying
// PushSubscriptionStore, which holds a list of subscriptions per
// accelByteId — the service fans out to each one and surgically prunes
// dead endpoints (404/410) without disturbing the user's other live
// devices. ...
val pushService = UiSignalRpcHandlers.pushNotificationService
val pushStore = UiSignalRpcHandlers.pushSubscriptionStore
val pushHumanAccelByteId = WorldManager.playerStats
    .firstOrNull { it.playerData?.name?.equals(actor, ignoreCase = true) == true }
    ?.accelByteUserId
    .orEmpty()
if (pushService != null && pushStore != null && pushHumanAccelByteId.isNotBlank())
{
    val connectionManager = UiSignalRpcHandlers.connectionManager
    val hasPrimarySession = connectionManager
        ?.findAllSessionsByAccelbyteId(pushHumanAccelByteId)
        ?.any { it.role == SessionRole.PRIMARY }
        ?: false
    if (!hasPrimarySession)
    {
        kotlinx.coroutines.GlobalScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            try
            {
                pushService.sendTurnStart(pushHumanAccelByteId, actor, WorldManager.world.roundNumber)
            }
            catch (e: Throwable) { /* swallowed */ }
        }
    }
}
```

Three load-bearing decisions (unchanged from v1.0.0):

- **Suppression by PRIMARY session** (line 1384). The push is sent only when the user has no live WS. If they're playing, no push, no click ambiguity.
- **Human-vs-AI actor lookup** (line 1377). Uses `WorldManager.playerStats` rather than the local `val player` so the block stays adjacent to the broadcast site.
- **`GlobalScope.launch(Dispatchers.IO)`** (line 1390). The turn loop MUST NOT block on the push round-trip.

Two semantic changes since v1.0.0:

- **Fan-out is internal.** `sendTurnStart(...)` iterates `store.getAll(...)` and dispatches each via a private `sendOne(...)`. The trigger signature is unchanged. Failures on one endpoint don't abort the fan-out — the user's other devices still receive.
- **410/404 surgically prune.** `sendOne` catches 410/404 and calls `store.removeByEndpoint(accelByteId, endpoint)`. Only the dead endpoint is removed; the others remain. If the last subscription is removed, `removeByEndpoint` calls `vfs.deleteUserRecord(...)` to clean up the VFS record entirely.

Payload shape (unchanged from v1.0.0, set in `PushNotificationService.kt`):
```json
{"title":"Your turn","body":"Round $roundNumber — $actorName, ready when you are","tag":"turn-$roundNumber","url":"/"}
```

The SW at `sw.js:16-19` reads these and renders with `requireInteraction: true`, the `Resume turn` action button, and `tag` for coalescing.

### Spec #3 — Works on mobile (MET, verified 2026-06-29)

No mobile-specific code is required because the W3C Push API + Service Worker stack is the cross-platform abstraction:

- iOS 16.4+ Safari supports Web Push for **installed PWAs only** (the site must be added to the home screen). The browser-tab path does NOT support push on iOS.
- Android Chrome (browser and installed PWA) supports Push API.
- Desktop Chrome / Firefox / Edge all support it.

The 2 platform requirements that production must satisfy (not code, but operators must provide):

1. HTTPS in live mode (Push API rejects `http://`, exempts `localhost` and `127.0.0.1`).
2. **Web App Manifest with `display: standalone`** — verified at `kvisionApp/src/jsMain/resources/manifest.webmanifest`. The manifest contains `name: "Autogenesis"`, `start_url: "/"`, `display: "standalone"`, `theme_color: "#1a1f2e"`, `background_color: "#0a0e1a"`, and a single 512x512 PNG icon at `/img/AutogenesisTitle.png`. `index.html` loads `kvisionApp.js` from the same origin and SW is registered at `/sw.js` from the page root — reachable from `start_url`. **iOS support is correctly met.**

### Spec #4 — Click re-opens tab and rehydrates (MET)

The flow has 4 hand-offs:

1. **SW `notificationclick` handler** (`sw.js:35-60`): calls `self.clients.matchAll({ type: 'window', includeUncontrolled: true })`. If a focused tab at the SW's scope exists, `client.focus().then(() => client.postMessage({type:'autogenesis.resumeTurn'}))`. Otherwise, `clients.openWindow(targetUrl)`.
2. **Page-side `message` listener** (`Main.kt:99-104`): as of v1.1.0 this is a `when` over both message types — `autogenesis.resumeTurn` → `handleResumeTurnMessage()`; `autogenesis.subscriptionChanged` → `handleSubscriptionChanged(data.subscription)`.
3. **Page-side resume trigger** (`PushNotificationService.kt:193-212`): invokes `server.restoreRunningGame` on the existing `WebSocketRpcBridge.rpcInvoker`. Same path the Resume dialog uses.
4. **Server-side restore** (`GameRestoreRpcHandlers.kt:146-251`): idempotent. If the auto-restore on connect already applied the snapshot, the `isWorldAlreadyRestoredForUser(userId)` predicate at line 177 returns true and `applyRestoredWorldAndSync(..., "race-recovered")` re-syncs the world to the current WS without re-applying. Otherwise, fresh-restore path.

**"If already on game server, click does nothing" is satisfied by defense in depth:**

- Layer 1 (server, primary): `TurnHarness` doesn't even send the push when a PRIMARY session exists. No notification → no click.
- Layer 2 (server, idempotent): if the push DOES get sent (race window between turn-loop push and WS connect), `restoreRunningGame` is idempotent and the second call returns success without side effects.

This is stronger than the spec asked for, and the redundancy is the right posture given how rare the user clicks are.

## The Kotlin/JS DCE keepalive pattern (class-level pitfall, 2026-06-29)

**The pattern.** When a Kotlin/JS singleton is invoked via a stored lambda (e.g. `onClick { ... }`, `addEventListener("message", { ... })`, `setOnXxxCallback { ... }`), Kotlin/JS dead-code-eliminates it from the webpack bundle because the linker can't trace reflective call sites through the lambda capture. The bundle ships without the singleton's methods, and a runtime call hangs or no-ops.

**The fix.** Store a reference somewhere reachable from `Application.start()` (the function KSP / webpack keeps):

```kotlin
// In Main.kt onStart()
val pushServiceKeepalive: Any = PushNotificationService
Logger.debug(LogCategory.SYSTEM, "Main: PushNotificationService keepalive bound (ref=$pushServiceKeepalive)")
```

**When this matters.** Every Kotlin/JS singleton with a reflective invocation pathway. Real-world instances in this codebase:

- `PushNotificationService` — invoked through `onClick { ... }` in `MainMenu.kt:519`. Keepalive at `Main.kt:67`.
- Any singleton registered via `WebSocketRpcBridge.registerHandlers { ... }` whose KSP-generated provider class needs to be retained.
- Any `addEventListener` listener whose handler is an `object::method` reference.

**Anti-pattern (do not do this).** Hand-importing the singleton from a non-app-start site and hoping the linker keeps it. Webpack's tree-shaker is aggressive — only `Application.start()` and its transitive closure get guaranteed retention.

**Diagnostic when a singleton's methods are missing from the bundle.** Build the bundle and grep for a class-name fragment:

```bash
cd kvisionApp/build/development-webpack/
grep -c "PushNotificationService" *.js  # should be > 0
# If 0: add the keepalive reference and rebuild
```

## Synthetic-fixture correctness trap (CRITICAL pitfall, 2026-06-29)

**The bug shape.** When a test uses a synthetic fixture (a base64 string, a JSON literal, a synthetic key) that has *hidden structural or cryptographic invariants* the test author didn't verify, the test can pass via the **wrong code path entirely**. The test asserts a return value (or absence of a side effect) that the production code produces for an unrelated reason — not because the code path the test was meant to exercise actually ran.

**The Autogenesis incident.** The pre-v1.1.0 `PushNotificationServiceIntegrationTest.removeDeletesSubscriptionOn410Gone` test stored a synthetic 65-byte-as-64-char `BIPUL12_K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5` string as the subscription's `p256dh`. That string was valid Base64URL **but its decoded bytes were not a valid uncompressed P-256 curve point**. The `nl.martijndwars:web-push` library validates the curve point *before* sending the encrypted request, throws `Incorrect length for uncompressed encoding` synchronously, and the catch block in `sendOne` returns `false` without ever reaching the 410-handler. The test asserted `assertFalse(sent, ...)` and `coVerify { vfs.deleteUserRecord(...) }` — and **passed for the wrong reason**. Months went by assuming "the 410 prune path works" when in fact the test had never exercised that path.

**The diagnostic tell.** When a test fails with a different error mode than the test name suggests, the test is masking the bug. The classic signs:

1. **The library throws a different exception than what the test's behavior asserts.** "Incorrect length for uncompressed encoding" instead of "got HTTP 410." A test stub that produces the library's silent validation failure rather than the expected HTTP response means the test never reached the HTTP layer.
2. **The test's `assertFalse(sent, ...)` passes, but only because the production code's `catch (e: Throwable)` swallowed an exception thrown by a fixture-validation check.** Catch blocks are silent tests' hideout — the exception is logged, the test goes green, and no one notices the function-under-test never completed its primary work.
3. **Removing the fixture reveals the test is wired wrong.** If you replace the synthetic base64 with garbage that obviously wouldn't parse, the test now fails with a different error message than the test's `assertX` captures — that's the signature the test is actually exercising.

**The fix recipe for cryptographic / structural fixtures in tests:**

```kotlin
// BAD — synthetic 64-byte string, not a valid uncompressed P-256 point
val dto = PushSubscriptionDto(
    endpoint = "http://127.0.0.1:$port/push-gone",
    p256dh = "BIPUL12_K4Z1K9y5K4Z1K9y5..."  // wrong length AND invalid curve
    auth = "testauth1234567890"
)

// GOOD — derive from a real keypair so the curve point is guaranteed valid
val keyPair = KeyPairGenerator.getInstance("EC").apply { initialize(256) }.generateKeyPair()
val ecPublicKey = keyPair.public as java.security.interfaces.ECPublicKey
val w = ecPublicKey.w
val rawPoint = ByteArray(65).also {
    it[0] = 0x04
    // copy affineX / affineY into it[1..32] / it[33..64]
}
val p256dhB64 = java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(rawPoint)
```

The pattern generalizes: **when a test fixture has hidden invariants, derive the fixture from the same generator the library uses internally.** For a keypair that's `KeyPairGenerator("EC").initialize(256)`; for a JWT that's `Jwts.builder()...`; for a checksum that's `Mac.getInstance("HmacSHA256")...`; for a UUID that's `UUID.randomUUID()` (not `"test-uuid-string"`).

**Companion debugging recipe.** When a test in this project that involves push / crypto / parse / network fails differently than the test name implies, check the fixture first. The fix is not "make the test pass" — it's "make the test exercise the code path it claims to exercise."

**Reference case (full transcript in the integration test):** the v1.1.0 rewrite of `removeDeletesSubscriptionOn410Gone` swapped the synthetic base64 string for the keypair-derived `rawPoint`. With the new fixture, the library's encryption check passes, the request actually reaches the local HttpServer, the server returns 410, the catch-block for the 200-status path does NOT execute, the 404/410-handler branch DOES execute, and the test now genuinely exercises the surgical prune path.

**Adjacent trap — catch blocks hiding fixture failures.** The same `sendOne` has two distinct catch paths: a status-bucket that handles 404/410 by calling `removeByEndpoint`, and a generic catch that swallows library-thrown exceptions and returns `false`. Tests that exercise the generic-catch path will pass for any reason that triggers an exception. If the production code gains a third code path (e.g. a new status bucket for 429 rate-limit) that returns `false` *without* calling `removeByEndpoint`, a test that asserts `coVerify { vfs.removeByEndpoint }` will pass for the wrong reason again. Audit tests for catch-block coverage as carefully as for the happy path — the catch-block assertion is the one most likely to silently mask.

## The `pushsubscriptionchange` path (shipped v1.1.0, was gap)

**What runs.** SW `sw.js:65-78` listens for `pushsubscriptionchange` (RFC 8030 lifecycle event for when the browser rotates the subscription). It re-subscribes internally, then posts `{type:'autogenesis.subscriptionChanged', subscription: subscription.toJSON()}` to all open clients.

**Page-side handling (v1.1.0).** `Main.kt:99-104` now routes both message types:

```kotlin
window.addEventListener("message", { event ->
    val data: dynamic = event.asDynamic().data
    val type: String? = data?.type as? String
    when (type)
    {
        "autogenesis.resumeTurn" -> {
            PushNotificationService.handleResumeTurnMessage()
        }
        "autogenesis.subscriptionChanged" -> {
            PushNotificationService.handleSubscriptionChanged(data?.subscription)
        }
    }
})
```

`PushNotificationService.handleSubscriptionChanged(subscription)` (added in v1.1.0, ~50 lines) unwraps `PushSubscription.toJSON()` (`{endpoint, keys: {p256dh, auth}}`) into the flat `PushSubscriptionDto` and re-invokes `client.registerPushSubscription` via the same WS bridge. Null-safe: drops messages missing `endpoint` / `keys.p256dh` / `keys.auth`.

**Why this works seamlessly with v1.1.0 store semantics.** Because `store.put` is now upsert-by-endpoint, the same RPC that handles fresh subscription also handles rotation re-registration. When Firefox rotates a subscription, the new endpoint is the same as the old (rotation is key-rotation, endpoint-stable per RFC 8030 §4), so `put` replaces the keys for the existing endpoint without creating a duplicate. The user's other devices' subscriptions are untouched.

**Tests.** `PushSubscriptionStoreTest.putReplacesExistingSubscriptionByEndpoint` (unit) exercises the upsert semantics that the handler relies on. No dedicated page-handler test yet — add `PushSubscriptionChangePageHandlerTest.kt` if the rotation path becomes flaky in production.

## Known limitations by design (2026-06-29)

The v1.0.0 "four known gaps" section is now mostly resolved. What remains:

1. **VAPID PEM openssl shellout dependency** (`PushVapidConfig.kt:105,123` invokes `openssl pkcs8` and `openssl ec` as subprocesses). JVM depends on `openssl` on `$PATH` at runtime. KDoc acknowledges this. Fix: add `bcpkix` to the classpath and use `JcaPEMKeyConverter` from Bouncy Castle to do the SEC1→PKCS8 conversion in-process. **Not a blocker** — openssl is universally available on every supported deployment target, and the shellout runs once at server boot. The `bcpkix` swap would add ~4MB to the server runtime for zero behavioral gain. Decision: leave as-is unless a deployment target lacks openssl.

2. **`GlobalScope.launch(Dispatchers.IO)` in `TurnHarness.kt:1390`** — uses the delicate `kotlinx.coroutines.GlobalScope` reference; the file likely has `@file:OptIn(kotlinx.coroutines.DelicateCoroutinesApi::class)` somewhere. If you're touching `TurnHarness`, verify the opt-in is still present (or migrate to a `CoroutineScope` field on the harness if the existing opt-in is missing). Not a bug today; a future Kotlin upgrade could escalate it.

## Anti-patterns (do NOT do)

These are mistakes that would silently break the push pipeline:

1. **Calling `subscribeIfPermitted()` outside a user gesture.** The Push API rejects silently. Symptom: registration never completes, no push arrives.
2. **Re-registering the service worker on every page load with a different scope.** `navigator.serviceWorker.register(SW_PATH)` is idempotent but writing a new SW file with a different scope conflicts and the new SW never takes over. Always use the same scope.
3. **Calling `pushService.sendTurnStart(...)` from the turn-loop thread directly.** Never call from `Dispatchers.Default`. Always wrap in `withContext(Dispatchers.IO)` or fire-and-forget `GlobalScope.launch(Dispatchers.IO)`. The push round-trip to FCM can take seconds; the turn loop would block.
4. **Storing the subscription without `accelByteId` resolution.** The `@RpcMethod("client.registerPushSubscription")` handler must resolve the userId from `connectionManager.findSession(ctx.connectionId)`, not trust a payload field. Browsers can be shared across accounts; the WS connection is the source of truth.
5. **Running `:kvisionApp:compileKotlinJs` without the `:kvisionApp:generateVapidKeys` dep.** The webpack build will fail because `vapid_public.json` doesn't exist. The dependency is wired at `kvisionApp/build.gradle.kts:92` — keep it there.
6. **Removing the BouncyCastle provider registration in `PushVapidConfig.init`.** Without it, `Utils.loadPublicKey` throws `NoSuchProviderException` because the web-push library hard-codes the BC provider name.
7. **Sending the JSON `value` from CloudSave as if it were the raw DTO.** The AccelByte CloudSave wraps the stored value one level deep (`{"value": {...}}`). The `PushSubscriptionStore.decodeAny()` method handles envelope / wrapped / legacy-flat — preserve that handling if you refactor it.
8. **Storing the subscription in a globally-shared Singleton accessible by `server.registerPushSubscription` without an `accelByteId` check.** Server is multi-tenant; the handler must verify the WS connection's userId matches before storing.
9. **Treating the store as single-DTO after v1.1.0.** `PushSubscriptionStore.put` REPLACES by endpoint; `getAll` returns the list. Any code that reads the store as a single DTO (e.g. callers using `store.get(...)` assuming a single subscription) gets "most recent" — which may not be what multi-device callers want. Use `getAll` for fan-out.
10. **Returning a boolean per-endpoint from a fan-out.** `sendTurnStart` returns `true` if at least one delivery succeeded. Callers that want "all devices got the push" need to inspect a different signal. Not currently needed anywhere; document if it becomes needed.
11. **Using mockk `coEvery { vfs.fetchUserRecord(...) } returns Result.failure(...)` without also stubbing the same method for upsert paths.** When `put` is changed to read-before-write, existing tests that only stubbed `saveUserRecord` start blowing up with `ClassCastException` deep in the new code path (the relaxed mock returns Object, not the typed `PlayerRecordResponse`). **Stub every method the production code calls**, not just the method the test name says it tests. When refactoring production code to call new VFS methods, re-audit every test in the file.
12. **Trusting `Result.fold(onSuccess, onFailure)` with a relaxed-mocked `Result.success(PlayerRecordResponse(...))`.** If the mock isn't typed correctly, `fold` receives Object instead of PlayerRecordResponse and throws ClassCastException. Even when the test stub is "correct," if a previous path triggers an unstubbed call returning Object, the fold crash surfaces deep inside production code as a confusing error. Always assert with `coVerify` after every changed VFS method.

## Quick checklist for modifying the push pipeline

1. **Adding a new push type** (e.g. "GameOver" push): add a method to `PushNotificationService` that builds the payload and calls `pushService.send(buildWebPushNotification(sub, payload))`. Wire the trigger at the appropriate call site in `TurnHarness` or `WorldManager`. DO NOT bypass the suppression check on `connectionManager.findAllSessionsByAccelbyteId(...)`.
2. **Adding a new notification field** (e.g. action buttons, image, sound): update both the payload shape in `PushNotificationService.kt` AND the `sw.js` `push` handler at line 21-31. SW reads the payload JSON, server doesn't dictate shape directly.
3. **Changing the VAPID keypair path**: update `PushVapidConfig.resolvePrivateKeyPath()` (line 71) and document the new location in `RUNBOOK_PUSH.md`.
4. **Adding subscription validation** (e.g. reject if endpoint is not https): add the check in `server/UiSignalRpcHandlers.kt:registerPushSubscription` AFTER the `connectionManager` accelByteId resolution but BEFORE `store.put(...)`. Returning success-with-warning to the client preserves the gesture-driven contract.
5. **Adding a new device type** (e.g. iPad, Wear OS): no code change needed if it's a Web Push-capable browser with a Service Worker. Verify the new platform's push deliverability matrix (iOS requires PWA install; Wear OS requires app installation) but the existing wire-up handles all of them via the same envelope.
6. **Adding the migration test for any store-shape change**: write the test that exercises the legacy-shape read path BEFORE the migration ships. Otherwise existing users with the old shape silently lose their subscriptions on first read.

## Operators must provide (NOT code territory)

- VAPID keypair at `~/.autogenesis/vapid_private.pem` (or `$AUTOGENESIS_VAPID_PRIVATE_KEY` override). Provision via `:kvisionApp:generateVapidKeys` Gradle task.
- HTTPS in live mode (Push API rejects http).
- For iOS support: Web App Manifest with `display: standalone` + PWA-installable.
- For dev/test: `AUTOGENESIS_DEV_PUSH_MOCK_PORT=9099`, `AUTOGENESIS_SHUTDOWN_DELAY_MS=600000`, `AUTOGENESIS_PUSH_TEST_ENDPOINT=true` — all documented in `RUNBOOK_PUSH.md`.

## Reference Files

- `references/web-push-architecture.md` — six-module file:line map of the entire push pipeline with the cross-module data flow at each handshake point.
- `references/push-e2e-probe-recipe.md` — operator playbook for running `kvisionApp-e2e/probes/push-turn-start.mjs`, including the headless-Chromium permission bypass and the timing of "wait 60s for POST to land on the mock."
- `references/test-fixture-cryptographic-correctness.md` — class-level pattern for the synthetic-fixture correctness trap. Covers the discovery recipe (six diagnostic tells), the fix recipe (derive from the same primitive the library validates against), the adjacent catch-block-hides-failure trap, and a 6-item audit checklist.

## Where to find the framework code

- **`nl.martijndwars:web-push:5.1.2`** — Java Web Push library. The PushService class signs JWTs (VAPID) and posts to FCM / Mozilla Push / APNs.
- **W3C Push API** — the browser-side `PushManager`, `PushSubscription`, `PushSubscriptionOptionsInit`. Kotlin/JS DOM bindings don't ship these — the code uses `js()` and `unsafeCast` to bridge.
- **Service Worker API** — fully shipped in Kotlin/JS dom bindings (`navigator.serviceWorker`, `ServiceWorkerContainer`, etc.) — only the Push API subset needs the `js()` workaround.
