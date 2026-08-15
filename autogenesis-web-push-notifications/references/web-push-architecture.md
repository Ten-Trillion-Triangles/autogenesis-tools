# Web Push Architecture — File:Line Map

Cross-module data flow for the push pipeline. Every handshake point with its module boundary, file:line, payload shape, and the load-bearing decision at each boundary.

## The 8 files, ranked by criticality

1. **`server/src/main/kotlin/.../TurnHarness.kt:1365-1399`** — trigger block. The suppression check at line 1384 (`!hasPrimarySession`) is what makes spec #2's "only send if the user is away" semantics correct.
2. **`kvisionApp/src/jsMain/resources/sw.js`** — three event handlers (`push`, `notificationclick`, `pushsubscriptionchange`). 78 lines total. Pure ES5 JavaScript by design (Kotlin/JS minification is unpredictable; the SW must be readable and stable).
3. **`kvisionApp/src/jsMain/kotlin/.../PushNotificationService.kt`** — Kotlin/JS subscription manager. The user-gesture contract (lines 18-34) and the DCE keepalive comment (Main.kt:60-68, but this file is the one that's protected).
4. **`server/src/main/kotlin/.../push/PushNotificationService.kt`** — JVM sender. Handles 410/404 lifecycle (lines 105-108) for subscription cleanup.
5. **`server/src/main/kotlin/.../push/PushVapidConfig.kt`** — PEM loader with SEC1 → PKCS8 normalization (line 105-114) via openssl subprocess.
6. **`server/src/main/kotlin/.../push/PushSubscriptionStore.kt`** — VFS store with CloudSave wrapper detection (lines 75-86).
7. **`server/src/main/kotlin/.../UiSignalRpcHandlers.kt:817-841`** — `@RpcMethod("client.registerPushSubscription")` handler. Resolves accelByteId from WS session — NOT from payload.
8. **`server/src/main/kotlin/.../Server.kt:288-314`** — boot-time wiring. Decides null vs instantiated `PushNotificationService` based on VAPID availability.

## The data flow at each handshake

### H1: SW registration (browser boot)

`Main.kt:93` → `PushNotificationService.registerServiceWorker()` (line 46-70) → `navigator.serviceWorker.register("/sw.js")`. Idempotent. Result is not awaited beyond the `Logger.info`. The `(line 60-68) keepalive` is the critical companion.

### H2: Play button click (user gesture)

`MainMenu.kt:519` → `PushNotificationService.subscribeIfPermitted()` (line 76-115) → `Notification.requestPermission()` → `loadVapidPublicKey()` (line 122) → `pushManager.subscribe({userVisibleOnly: true, applicationServerKey})` → `sendSubscriptionToServer(sub)` (line 159) → `client.registerPushSubscription` RPC.

### H3: Register RPC (browser → server)

`PushNotificationService.kt:177` → `WebSocketRpcBridge.rpcInvoker.invoke("client.registerPushSubscription", payload)` → `UiSignalRpcHandlers.registerPushSubscription` (line 817) → resolve `accelByteId` from `connectionManager.findAllSessions(ctx.connectionId)` → `store.put(accelByteId, dto)` → `vfs.saveUserRecord(accelByteId, "push-subscription", payload)`.

### H4: Server boot (one-time wiring)

`Server.kt:288` → `PushVapidConfig.loadKeypair()` (line 86) → returns `VapidKeypair?` → instantiate `PushNotificationService` if non-null → wire to `UiSignalRpcHandlers.pushNotificationService` (line 306). If `AUTOGENESIS_DEV_PUSH_MOCK_PORT` is set, the third constructor arg rewrites endpoints to localhost.

### H5: Turn start (recurring trigger)

`TurnHarness.executeSingleTurn` (line ~1362) → broadcast turn start → push trigger block (line 1365-1399) → `connectionManager.findAllSessionsByAccelbyteId(accelByteId).any { it.role == SessionRole.PRIMARY }` → if false, `pushService.sendTurnStart(accelByteId, actor, world.roundNumber)` on `Dispatchers.IO`.

### H6: Web push delivery (browser / OS)

OS / FCM / Mozilla Push → SW `push` event handler (`sw.js:7-33`) → `event.data.json()` → `self.registration.showNotification(title, options)` with `tag` for coalescing.

### H7: Notification click

`sw.js:35-60` → `self.clients.matchAll({ type: 'window', includeUncontrolled: true })` → focus existing tab OR open new window → `client.postMessage({type: 'autogenesis.resumeTurn'})`.

### H8: Resume trigger (browser)

`Main.kt:99-104` → `window.addEventListener("message", ...)` → `PushNotificationService.handleResumeTurnMessage()` (line 193) → `WebSocketRpcBridge.rpcInvoker.invoke("server.restoreRunningGame", null)`.

### H9: Server-side restore (idempotent)

`GameRestoreRpcHandlers.restoreRunningGame` (line 146-191) → resolve userId → `restoreWorldFromUserRecord` → if world already restored (race-recovered), call `applyRestoredWorldAndSync(..., "race-recovered")` (line 184) → `UiSignalRpcHandlers.sendInitialSync(connectionId=ctx.connectionId, ...)` (line 226). Critical: sync goes to `ctx.connectionId`, NOT the saved `stats.playerID` (lines 198-206 KDoc).

## The three load-bearing decisions, with WHY

### Decision 1: Suppress push if PRIMARY session exists (`TurnHarness.kt:1384`)

**What:** `connectionManager.findAllSessionsByAccelbyteId(accelByteId).any { it.role == SessionRole.PRIMARY }` gates the push.

**Why:** Spec #4 says "if they are already open to that game server, clicking the notification does nothing." Sending the push only when no PRIMARY session exists means no notification → no click → no side-effect. This is the primary implementation of the spec; the SW-side `notificationclick` is the secondary (idempotent) implementation.

**What if it's wrong:** User receives push while playing, clicks it, gets redirected mid-turn. Worst case the resume RPC races with their in-flight RPC and corrupts state. The idempotency at `GameRestoreRpcHandlers.kt:177` (`isWorldAlreadyRestoredForUser`) is the safety net.

### Decision 2: Sync to `ctx.connectionId`, NOT `stats.playerID` (`GameRestoreRpcHandlers.kt:226`)

**What:** After restore, the world state is dispatched via `UiSignalRpcHandlers.sendInitialSync(connectionId = ctx.connectionId, ...)`.

**Why:** The snapshot's `playerStats[*].playerID` is the WS playerId that was alive at capture time. After the user logs back in, the new browser's WS has a NEW playerId. Sending to the saved playerId would dispatch the sync to a stale (likely disconnected) session. The new browser would mount an empty GameplayUI.

**What if it's wrong:** "Turn resumed" is false (world data never arrives), GameplayUI shows blank map. Symptom: user clicks notification, briefly sees the resume dialog, then sees nothing.

### Decision 3: VAPID PEM normalized via openssl shellout (`PushVapidConfig.kt:105-117`)

**What:** Subprocess `openssl pkcs8 -topk8 -nocrypt -in <pem>` to convert SEC1 → PKCS8 because `KeyFactory("EC")` rejects SEC1 `PrivateKey`.

**Why:** The Gradle task generates an SEC1 PEM (default `openssl ecparam -name prime256v1 -genkey -noout` output). Java's standard `KeyFactory.getInstance("EC").generatePrivate(PKCS8EncodedKeySpec)` requires PKCS8. Doing the conversion in-process would require `bcpkix` (`JcaPEMKeyConverter`), which is not currently a dependency.

**What if it's wrong:** `KeyFactory.generatePrivate` throws `InvalidKeySpecException`. Caught by the outer try (line 133), logged at ERROR. `loadKeypair` returns null → `Server.kt:312` logs "push notifications disabled" → no push ever fires.

## Local vs CloudSave storage shape

The `PushSubscriptionStore.get()` method has two decode paths because AccelByte CloudSave wraps the stored value:

```
Flat VFS:           {"endpoint": "...", "p256dh": "...", "auth": "..."}
CloudSave wrapped:  {"value": {"endpoint": "...", "p256dh": "...", "auth": "..."}}
```

The decode at line 70-86 tries `direct.decode(...)` first; on null result, checks `element is JsonObject && element["value"] is JsonObject` and unwraps. Both paths feed the same `PushSubscriptionDto.serializer()`. If you change the store schema, update both decode paths or migrate the wrapping decision to the producer side.

## The VAPID public key wire format

The browser's `applicationServerKey` argument to `pushManager.subscribe()` is the **raw uncompressed P-256 point (65 bytes)** encoded as **Base64URL without padding**:

- `0x04 || X (32 bytes) || Y (32 bytes)` = 65 bytes total
- Base64URL-encoded: 87 characters (no padding)

This matches what `nl.martijndwars:web-push:5.1.2` expects via `Utils.loadPublicKey` (line 67 in `PushVapidConfig.kt`). It does NOT match the standard `SubjectPublicKeyInfo` DER encoding (which has a 26-byte ASN.1 header). The Gradle task at line 129 strips the last 65 bytes of the DER `pubout` output to get the raw point.

If you regenerate keys manually with `openssl ec -in <pem> -pubout -outform DER`, you must strip the last 65 bytes — DER output is `26 + 65 = 91` bytes total.

## Lifecycle corners

### PushSubscription rotation (the `pushsubscriptionchange` gap)

Firefox rotates the subscription periodically. The SW handler at line 65-78 re-subscribes and posts the new endpoint to all clients. The page-side `autogenesis.subscriptionChanged` handler is **MISSING** as of 2026-06-29 — see the umbrella skill's "Critical gap" section for the fix shape.

### Subscriptions that 410 Gone or 404

`PushNotificationService.kt:105-108` recognizes the standard "browser killed the endpoint" signal and calls `store.remove(accelByteId)`. The next turn-loop push will not find a subscription and silently skip. **The store does not preserve the userId of the removed subscription** — if the user re-subscribes later, they have to click Play again and pay the gesture cost.

### Server restart with no VAPID keypair

`Server.kt:312` logs "VAPID keypair not loaded — push notifications disabled." The turn loop keeps running. No crash, no degraded gameplay. The store still writes subscriptions (line 39-41), they just never get sent.
