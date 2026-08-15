# Push-Turn-Start E2E Probe Recipe

Operator playbook for running `kvisionApp-e2e/probes/push-turn-start.mjs` end-to-end. The probe verifies that the server's turn-loop push trigger actually delivers a POST to a local HTTP mock receiver when the player has no PRIMARY session.

## When to run

- Verifying any change to `TurnHarness.kt:1365-1399` push trigger.
- Verifying any change to `PushNotificationService.kt` (sender).
- After VAPID keypair regeneration.
- After store schema changes.
- Before claiming "push notifications work" for a release.

## What the probe proves

That:

1. The browser registers a `PushSubscription` (or that we synthesize one via `/debug/seed-push-subscription`).
2. The subscription is stored server-side in the VFS under `push-subscription`.
3. Closing the browser disconnects the WS.
4. The next turn-loop iteration where the human actor's turn starts fires `PushNotificationService.sendTurnStart(...)`.
5. The push arrives at the local mock receiver on port 9099 within the wait window.

It does NOT prove:

- That the OS actually displays a notification (browser environment, not native).
- That the `notificationclick` handler invokes the resume RPC (needs a real browser SW).
- That mobile browsers work (different platform).

## Pre-requisites

All three dev servers must be up on standard ports:

```bash
# 7070 = server-extend (REST + SSE)
# 9080 = main server (WebSocket)
# 8080 = client/dev server (KVision App)

ss -tlnp 2>/dev/null | grep -E ":(7070|9080|8080)\b"
# Expected: 3 lines
```

`Server.kt` boots with all three env vars set:

```bash
AUTOGENESIS_DEV_PUSH_MOCK_PORT=9099 \
AUTOGENESIS_SHUTDOWN_DELAY_MS=600000 \
AUTOGENESIS_PUSH_TEST_ENDPOINT=true \
./gradlew :server:run
```

VAPID keypair must exist:

```bash
test -f ~/.autogenesis/vapid_private.pem && echo "vapid ok" || \
  ./gradlew :kvisionApp:generateVapidKeys
```

## Step-by-step

### 1. Start the probe

```bash
cd kvisionApp-e2e
timeout 900 node probes/push-turn-start.mjs 2>&1 | tee /tmp/push-probe.log
```

The probe opens its own mock HTTP server on port 9099, then Playwright drives a real Chromium browser against the dev server at http://127.0.0.1:8080.

### 2. What the probe does internally

**Phase 1 — register:**
- Boot browser, AccelByte guest login, click PLAY.
- Extract `accelbyteId` from a MainMenu data-attribute.
- **Bypass**: headless Chromium rejects SW registration with "permission denied". The probe synthesizes a P-256 keypair via `webcrypto`, builds a `PushSubscriptionDto`, and POSTs it to `/debug/seed-push-subscription` on the main server (port 9080). The endpoint is rewritten to `http://127.0.0.1:9099/<original-path>`.
- Drive one turn so the world advances. Confirm via server log: `TurnHarness: persist running-game snapshot`.

**Phase 2 — push delivery:**
- Close the browser. WS disconnect handler arms the single-player shutdown countdown (10 min via `AUTOGENESIS_SHUTDOWN_DELAY_MS`).
- The TurnHarness loop is still alive (`loopJob.isActive` stays true across `defer-await`).
- When the loop next reaches the human actor's turn, `executeSingleTurn` broadcasts the turn start and `pushService.sendTurnStart(...)` fires.
- The probe's HTTP mock receives the POST within `PUSH_WAIT_MS` (default 360000 = 6 minutes).

### 3. Expected server log lines

In `/tmp/autogenesis-proxy/srv.log`:

```
UiSignalRpcHandlers.registerPushSubscription: stored subscription for user=<UUID> endpoint=http://127.0.0.1:9099/...
PushNotificationService: endpoint rewritten for dev override: ...
TurnHarness.executeSingleTurn: Resolved actor='<NAME>'
TurnHarness: push trigger fired for user=<UUID> round=2 ...
PushNotificationService: push sent for user=<UUID> status=201
```

In `/tmp/autogenesis-proxy/srv.log` you should NOT see:

```
PushNotificationService: VAPID not configured, skipping push
PushNotificationService: no subscription for user=<UUID>
```

These would mean a Phase 1 bypass failure (VAPID or store write).

### 4. Expected probe log output

```
[HH:MM:SS.mmm] [push-mock] POST /web-push/fcm/send/abc body=128B from=Java/17.x
[HH:MM:SS.mmm] [push-mock] headers: ttl=86400 content-encoding=aesgcm vapid=vapid.auth.token...
Push probe PASSED
```

If you see `Push probe FAILED: timeout` the issue is most likely:

1. VAPID not configured (server log shows "skipping push").
2. Subscription not stored (server log doesn't show `registerPushSubscription: stored subscription`).
3. The human actor's turn never reached the broadcast phase (TurnHarness log doesn't show `Resolved actor`).
4. The push did send but `AUTOGENESIS_DEV_PUSH_MOCK_PORT` env var doesn't match the probe's expectation (default 9099).

### 5. Cleanup

```bash
# Kill all three servers
for port in 7070 9080 8080; do fuser -k $port/tcp 2>/dev/null; done

# Probe artifacts
ls kvisionApp-e2e/probes/artifacts-push-turn-start/
# Expected: probe.log, screenshot-before-close.png (if --keep-running)
```

## Common probe failures

| Symptom | Cause | Fix |
|---|---|---|
| `Registration failed - permission denied` (in browser console) | Headless Chromium rejecting SW | Expected — the probe bypasses via `/debug/seed-push-subscription`. Not a failure. |
| `Push probe FAILED: timeout waiting for push` | Turn loop didn't reach human's turn | Check `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000` is set; check `WorldManager.world.roundNumber` advances between server restart and probe start. |
| `404 on /debug/seed-push-subscription` | `AUTOGENESIS_PUSH_TEST_ENDPOINT=true` not set | Restart server with the env var. |
| `push-subscription not found in VFS` | `/debug/fetch-snapshot` failed | The CloudSave proxy may be down. Check `:server-extend` log. |
| `status=201 in server log but probe sees no POST` | Different `AUTOGENESIS_DEV_PUSH_MOCK_PORT` than probe expected | Check `/tmp/autogenesis-proxy/srv.log` for `endpoint rewritten for dev override:` line; both sides must show the same port. |

## Headless Chromium permission gate

The standard headless Chromium rejects `navigator.serviceWorker.register()` and `Notification.requestPermission()` with `NotAllowedError`. The probe works around this by:

1. Detecting the failure in the page console
2. Switching to the `/debug/seed-push-subscription` HTTP path
3. Generating a synthetic P-256 keypair via `node:crypto.webcrypto.subtle.generateKey({name:'EC', namedCurve:'P-256'}, true, ['deriveBits'])`
4. Constructing a real `PushSubscription` shape and POSTing it

This is a deliberate probe design decision: the goal is to verify the **server pipeline** (subscription store + turn-loop trigger + VAPID-signed send), not the browser-side SW registration flow. The SW registration is verified by manual `npm run dev` + Chrome DevTools inspection.

## Why local mock endpoint instead of real FCM

Sending to real `https://fcm.googleapis.com/...` from the dev environment would require:

1. A real FCM project with valid auth tokens
2. Network egress from `127.0.0.1` to Google
3. A real device endpoint registered

The mock endpoint (port 9099) is owned by the probe process. The VAPID signature is real (server signs with the dev keypair, probe's mock doesn't verify but receives the encrypted payload). The probe confirms that the round-trip from `sendTurnStart` → VAPID-signed POST → receiver works; it doesn't confirm Google would accept the request.
