# Stall fingerprint recipe — "user reports stalls" diagnostic for the dev client

When the operator/user reports "the page froze for N seconds/minutes", this is the
canonical first-pass to localize the cause. Verified 2026-08-03 against
`~/.autogenesis/logs/server-extend-2026-08-03-105036.log`.

## The fingerprint

In any `server-extend-YYYY-MM-DD-HHMMSS.log`, count lines matching
`RestPlayerConnectionManager reconnecting playerId=` over a window. The
stall signature is:

- **N reconnects within M minutes**, with gaps of seconds-to-minutes between
  each reconnect event
- Each reconnect is followed by `CloudVFS.fetchUserRecord ... key=running-game`
  → `ResumeAvailabilityPushService: user=... record not a parseable snapshot,
  skipping push`
- The browser is mid-game (logged-in player has been connected for >5 minutes
  before the cycle starts)

This is **NOT** a server-side stall. The server is responding in <1s for every
SSE handshake. The stall is **client-side** — the UI has no live event feed
while `MatchmakingClient.connectToGameServer` tears down the old WebSocket
and opens a new one, and the next snapshot poll keeps firing the resume
flow.

## Read-only diagnostic (no code changes)

Run from the most recent `server-extend-*.log` in `~/.autogenesis/logs/`:

```bash
LOG=~/.autogenesis/logs/server-extend-2026-08-03-105036.log
echo "=== Reconnect events ==="
grep -c "RestPlayerConnectionManager reconnecting" "$LOG"
echo "=== Snapshot-poll results ==="
grep -c "record not a parseable snapshot" "$LOG"
echo "=== Gap analysis (first 10) ==="
grep "SSE /events request" "$LOG" | head -20
echo "=== Last 5 events ==="
grep "SSE /events request\|replacing previous session" "$LOG" | tail -10
```

If reconnect-count > 3 in any 15-minute window AND snapshot-poll-count > 0,
the stall cycle is the diagnostic target.

## The paired client-side trigger code paths

Verified file:line evidence (2026-08-03 reads):

- **Server replace-and-close**:
  `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/RestPlayerConnectionManager.kt:246-256`
  — atomically `sessions.put(playerId, session)` then unconditionally
  `previous.close()`. Old SSE channel killed the moment a new one registers.
  No grace period, no "wait for new stream to be ready" before closing the old.
- **Client WS tear-down**:
  `kvisionApp/src/jsMain/kotlin/ui/MatchmakingClient.kt:380-420` —
  `connectToGameServer` calls `WebSocketRpcBridge.close()` then
  `WebSocketRpcBridge.connect(...)` with `waitForConnection()` in between.
  While that's happening the UI has zero event feed.
- **Trigger sources**:
  - `kvisionApp/src/jsMain/kotlin/ui/MainMenu.kt:466` — `beginResumeSession`
    calls `MatchmakingClient.connectToGameServer(liveTicket.serverUrl)`
  - `kvisionApp/src/jsMain/kotlin/ui/MainMenu.kt:601` — `MatchOutcome.Ready`
    branch also calls `connectToGameServer(outcome.serverUrl)`
- **Resume-snapshot poll loop**:
  `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ResumeAvailabilityPushService.kt`
  — fires on every SSE `/events` connect. If the `running-game` record is
  a `{consumed:true, consumedAt:...}` sentinel or any non-parseable shape,
  the push is skipped but the next SSE connect will trigger another poll.

## Why this looks like a stall

1. Browser opens SSE → registers → listens.
2. Some client code path triggers `connectToGameServer` (resume flow, login
   re-bind, page reload, network blip retry).
3. New SSE arrives → server atomically replaces session, calls `previous.close()`
   on the old SSE channel.
4. Old `EventSource` sees close → no new events streaming → eventually times
   out → reconnects.
5. Reconnect fires another `ResumeAvailabilityPushService.checkAndPush`,
   which either pushes (if parseable snapshot) or skips (sentinel/empty).
6. If the push was skipped and the user re-clicks something that re-triggers
   `beginResumeSession`, the cycle repeats.
7. Each cycle creates a visible freeze because the UI thread blocks during
   the WS teardown/setup window.

## First-pass fix shapes (no implementation here — diagnostic only)

When the fingerprint matches, the fixes worth considering in priority order:

1. **Client-side reconnect-throttle**: in `connectToGameServer`, track
   recent reconnect timestamps; if N reconnects within M seconds, give up
   and show a "Connection unstable — reload?" prompt instead of looping.
2. **Server-side grace period**: in `RestPlayerConnectionManager.register`,
   don't call `previous.close()` until the new session's first RPC call
   has been observed (i.e. the new stream is actually live).
3. **Push-source logging**: distinguish user-initiated reconnects (page
   reload, login re-bind) from poll-triggered ones. Currently the log shows
   the SSE handshake but not why the SSE was opened.
4. **Snapshot-poll backoff**: in `ResumeAvailabilityPushService`, if the
   previous poll returned a non-parseable sentinel, skip the next poll
   for K seconds. Prevents the poll from re-firing the resume flow on
   every SSE reconnect.

## Existing tests that touch this code path

| File | What it pins |
|------|--------------|
| `server-extend/src/test/kotlin/.../RestPlayerConnectionManagerAwaitSessionTest.kt` | POST/SSE race — the 1000ms `awaitSession` timeout |
| `server-extend/src/test/kotlin/.../ServerExtendHttpRaceTest.kt` | HTTP-level race recovery |
| `server-extend/src/test/kotlin/.../UrlHandoverRegistryTest.kt` | URL handover semantics |
| `server-extend/src/test/kotlin/.../UrlHandoverRegistryOnVanishTest.kt` | Vanish-state behavior |
| `server-extend/src/test/kotlin/.../RpcUsageTrackingIntegrationTest.kt` | Telemetry sink correctness |

None of these currently pin the reconnect-churn budget (N reconnects in M
minutes is the diagnostic threshold). Adding a test that fails when the
SSE handler replaces a session more than N times in a configured window
would close the diagnostic loop.

## Anti-patterns

- **Do not** treat this as a server-side stall by looking at server thread
  state, GC pauses, or coroutine cancellation. The server is healthy; the
  stall is the gap between close() and connect() on the client.
- **Do not** add a "stuck reconnect" timer on the server side that kills
  the previous session after a long timeout. The grace-period fix is the
  right shape; killing sessions adds a new failure mode.
- **Do not** add reconnect logic without a visible UI state during the
  reconnect window. The operator has to be able to see "Reconnecting..."
  in the dev client, not just a frozen screen.