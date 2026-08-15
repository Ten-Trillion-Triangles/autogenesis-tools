# Phase 1 / Phase 2 split in resume-game e2e probes

When `resume-preserves-round.mjs` (or any multi-phase resume probe) fails,
diagnose the failure **per phase** before changing code. The probe
silently produces different failure modes depending on which phase breaks,
and conflating them leads to multi-hour debug spirals.

## Phase 1 failure mode (snapshot never saved)

**Symptom:** probe exits with `FATAL: dialog never appeared`, but the
Phase 1 capture log line is present:
```
[01:09:00.151] [phase1] gameplay=true round=1 leaderboardEntries=N turnOrder=true
```

**Root cause:** the probe's Phase 1 disconnected before the human's first
turn started. The server-side gate `shouldPersistOnDisconnect`
(`Server.kt:1037`) requires `humanPlayerHasJoinedOnce=true`, which is
set only in `TurnHarness.awaitPlayerAction` when the human player
reaches a turn-timer-driven action point. Default turn timer is
`TURN_TIMEOUT_MS=302000ms` (5 min 2 s). A 12-second probe window
isn't long enough.

**Server-side tell:** grep `srv.log` for `Persisted running-game` between
the Phase 1 capture timestamp and the Phase 2 start timestamp. Zero hits
= Phase 1 didn't save. Multiple hits after the Phase 2 start = the
probe's Phase 1 actually saved AFTER Phase 2 already started (probe is
racing its own timer).

**Fix (verified 2026-06-27):** set
`AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000` on the `:server:run` JVM
start. With that, the human's turn starts in ~5s instead of 5 min, and
the AI takeover fires immediately. The Phase 1 disconnect then
saves a real snapshot.

## Phase 2 failure mode (push never reaches the client)

**Symptom:** probe exits with `FATAL: dialog never appeared`, Phase 1
saved a snapshot, BUT the JS console never logs
`ResumeAvailabilityListener: notification received for userId=...`.
Server-extend's `ResumeAvailabilityPushService.pushToMainServer` shows
`pushed resumeAvailable for user=... round=1 hasAi=true` (the RPC
returned successfully), but main server's
`UiSignalRpcHandlers.notifyResumeAvailable` shows either:
- `pushed to userId=... sessions=1` — push succeeded, problem is downstream
- (no entry) — the push RPC call itself never reached main server

**Two distinct Phase 2 problems were observed 2026-06-27:**

1. **Snapshot push succeeds, main server pushes to no sessions.**
   `connectionManager.findAllSessionsByAccelbyteId(userId)` returns
   empty because Phase 2's browser never opened a WebSocket to main
   server. The JS console shows `RpcRegistry: Registering handler for
   client.resumeAvailable` (local handler registration) but no
   `WebSocketRpcBridge: successfully connected` log line. Main server
   `srv.log` has zero activity during the Phase 2 window.

2. **Snapshot push reaches main server, push is dropped.** Main
   server's `notifyResumeAvailable` log line never appears. Indicates
   a routing/auth issue between server-extend and main server.

**Both of these are independent of the Phase 1 fix.** A "snapshot
saves correctly" message from the agent is NOT proof the resume
flow works end-to-end. The user's contract requires the dialog to
appear, which requires the Phase 2 push to reach the browser, which
requires the Phase 2 WS to be open, which requires the Phase 2
browser's `RestRpcBridge.connect(accelbyteId=userInfo.userId)` to
fire.

**Diagnostic order:**
1. check `se.log` for the `ResumeAvailabilityPushService: pushed
   resumeAvailable` line in the Phase 2 window — if missing,
   server-extend never pushed
2. If present, check `srv.log` for the `notifyResumeAvailable:
   pushed to userId=... sessions=N` line — if N=0, the push hit a
   WS that doesn't exist
3. If N>0, check JS console for `ResumeAvailabilityListener:
   notification received` — if missing, the push reached the WS but
   the listener didn't fire (race or registration order bug)

## Probe timing rules that make Phase 2 hang silently

- **20-second wait after Resume click.** The GameplayUI mounts at
  `ui.setLocalPlayer`, but the leaderboard widget isn't populated
  until `loadMapPack` (~8MB / ~282 chunks) and `updateWorld` (~110KB
  / ~4 chunks) finish assembling. Probe must wait 20s after the
  Resume click before capturing state. See
  `autogenesis-local-dev` skill "Do not treat 'GameplayUI mounted'
  as proof" pitfall.

- **20-second wait after Phase 1 close before Phase 2 opens.** The
  server-side `shouldPersistOnDisconnect` runs on a coroutine
  triggered by WS close, then writes to VFS. 20s is a safe
  lower bound; less risks racing the write.

- **Dismiss `Match Resumed` OK button before taking post-Resume
  screenshots.** Otherwise the screenshot is a modal overlay
  on a blurred game UI.

## Quick diagnostic recipe

```bash
# 1. Are all three servers up?
ss -tlnp 2>/dev/null | grep -E ':(7070|8080|9080)\b' || echo STACK DOWN

# 2. Did Phase 1 save a snapshot?
grep "Persisted running-game" /tmp/autogenesis-proxy/srv.log | tail -5

# 3. Did Phase 2's SSE connect to server-extend?
grep "SSE /events request" /tmp/autogenesis-proxy/se.log | tail -5

# 4. Did server-extend push?
grep "ResumeAvailabilityPushService.*pushed\|pushed resumeAvailable" /tmp/autogenesis-proxy/se.log | tail -5

# 5. Did main server receive the push?
grep "notifyResumeAvailable" /tmp/autogenesis-proxy/srv.log | tail -5

# 6. Did the JS console see the push?
# (probe console.log filter captures: "ResumeAvailability", "client.resume", "mountResumeDialog")
# If step 5 shows push but step 6 doesn't, the listener didn't fire
# (likely a WS registration order race or main server session table miss)
```

## Why both phases need to be debugged separately

A "Phase 1 works" message and a "Phase 2 works" message are
independent. Conflating them leads to the agent celebrating a Phase
1 fix while Phase 2 still fails — exactly the failure mode that
caused the 2026-06-27 user loss of trust ("I don't trust you to be
frank"). The e2e bar is the FULL FLOW: Phase 1 saves → Phase 2 sees
dialog → click → resumed game. Anything less is incomplete proof.
