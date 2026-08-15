---
name: autogenesis-resume-flow-e2e
description: End-to-end verification harness for the Autogenesis login + resume flow. Use when about to claim a fix for the login flow, ResumeOrNewDialog, snapshot persistence, resume restore, or popup-reappearing bug, when the user demands e2e proof of a fix, or when shipping changes to notifyResumeAvailable, shouldPersistOnDisconnect, restoreWorldFromUserRecord, or hydratePostRestoreState. The user has explicitly lost trust in unverified claims — running these probes IS the work, not an optional step. NOT for LLM prompt debugging (autogenesis-prompt-debugging), trace analysis (autogenesis-trace-analysis), or local-dev startup (autogenesis-local-dev).
version: 1.1.0
author: Hermes Agent (extracted from resume-flow sessions 2026-06-27)
created: 2026-06-27
updated: 2026-08-13
tags: [autogenesis, resume, login, e2e, verification, probe, trust, dialog]
changelog:
  - 1.1.0 (2026-08-13): Cost-control patterns for LLM-backed pipelines (cap calibration against Nova Lite empirical 0.627 tokens/byte; always-downsample pre-flight; empty-pack fail-fast; MapPackUnpackException typed-exception pattern). Two forbidden patterns -- env-gated bypass mechanisms and factory-pattern refactors of working production code without operator direction. TDD discipline rule -- sentinel tests must fail RED against the existing wrong code. Patch-tool retry-loop workaround (switch to terminal+python). Added scripts/hermes-verify-targeted-suite.sh.
  - 1.0.0 (2026-06-27): Initial extraction after 6 iterations of the login-flow-e2e probe + the consumed-sentinel, isGameActive-guard, and historySize-gate fixes. Encodes the user's explicit "I don't trust you" / "prove it" / "e2e test dammit" contract.
---

# Autogenesis Resume-Flow E2E Verification

Authoritative verification harness for the Autogenesis login + resume flow. Use this
skill **before reporting any fix to the user** that touches the login, snapshot,
resume, or dialog surface. The user has explicitly lost trust in unverified claims
and demands end-to-end proof — failing to run these probes is the same as not doing
the work.

## When to load

Load this skill when ANY of the following is true:

- About to claim a fix for the login flow, ResumeOrNewDialog, snapshot persistence,
  resume restore, or popup reappearing bug.
- The user says "I don't trust you", "prove it", "e2e test", "verify", or "dammit" in
  the context of the resume flow.
- About to ship a change to `Server.kt:resolveAutoRestoreUserId`,
  `UiSignalRpcHandlers.notifyResumeAvailable`, `shouldPersistOnDisconnect`,
  `restoreWorldFromUserRecord`, or `hydratePostRestoreState`.
- After any change to the consumed-sentinel, the `isGameActive` mid-game guard,
  or the `shouldPersistOnDisconnect` `historySize > 0` gate.

## The 5-test minimum bar (11 assertions)

## Phase 1 e2e requires the HUMAN's turn to actually start (CRITICAL — 2026-06-27 finding)

`shouldPersistOnDisconnect` at `Server.kt:1037` is the save-on-disconnect gate. It requires **`humanPlayerHasJoinedOnce=true`** for the snapshot write to fire on WS disconnect. The flag is set **only in `TurnHarness.awaitPlayerAction`** when the human player is reachable.

**Why Phase 1 probes fail without intervention:** the default human turn timer is `TURN_TIMEOUT_MS = 302_000ms` (5 min 2 s) at `gameState/WorldManager.kt:45`. If the probe disconnects within ~5 minutes of gameplay mount, the human's turn may not have started yet (the AI may have just finished its opening turn, or the round-1 is still in progress). When the probe closes the browser, `shouldPersistOnDisconnect` sees `humanPlayerHasJoinedOnce=false` and skips the save. No snapshot → no Phase 2 dialog → "dialog never appeared" FATAL.

**The fix is server-side and debug-only:** `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS` env var (added 2026-06-27) overrides the per-turn timer for e2e tests. The probe takes ~5 s per phase instead of 5+ minutes.

```bash
# Add to start_servers.sh or pass to the JVM directly:
AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000 \
  ./gradlew :server:run -Dorg.gradle.jvmargs="-DAUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000"
```

Verified log line on each human turn start:
```
TurnHarness.awaitPlayerAction: marked humanPlayerHasJoinedOnce=true for '<NAME>' (save-on-disconnect gate now permissive)
TurnHarness.awaitPlayerAction: DEBUG SHORT TURN TIMEOUT active: 5000ms (default 302000ms)
```

Then AI takeover fires ~5s later, the round advances, and on Phase 1 disconnect:
```
TurnHarness: Persisted running-game snapshot for user=<UUID> (round=1, turnIndex=0, historyEntries=N)
```

**Without this env var, probes are forced to wait 5+ minutes per Phase 1 run.** For CI / pre-merge runs, set the env var. For manual exploration, leave it default (5 min) so the human's actual turn timer is the one tested.

The full server-side implementation: `effectiveTurnTimeoutMs()` at `WorldManager.kt:51` reads `System.getProperty` then `System.getenv`, returns the env value if positive, else `TURN_TIMEOUT_MS`. `TurnHarness.kt:638` reads `effectiveTurnTimeoutMs()` and logs the override. Default behavior unchanged when env var absent.

---

Run `kvisionApp-e2e/probes/login-flow-e2e.mjs` and verify ALL 11 assertions pass:

See `references/phase1-vs-phase2-diagnostics.md` for the per-phase
diagnostic recipe (Phase 1 = save-on-disconnect; Phase 2 = push-to-WS
chain). The two phases have **independent failure modes** — fixing
one does not prove the other. A passing Phase 1 plus a broken
Phase 2 still produces "dialog never appeared" FATAL.

| Test | Catches regression |
|------|-------------------|
| 1. Login → main menu OR resume dialog, no "fail to fetch" | Login flow broken; bridge not connecting to server-extend |
| 1a. Resume dialog has Resume + New Game + Cancel | Dialog lost a button; text/button binding changed |
| 2. Cancel → main menu, no auto-restore, no dialog | Cancel re-routes wrong; cancel doesn't actually dismiss |
| 3. New Game → snapshot cleared (no dialog on re-login) | New Game doesn't delete; sentinel still written |
| 4. Cancel + disconnect cycle → next login clean | Disconnect path breaks login flow; consumed-sentinel left over |

Plus capture BOTH screenshots (dialog + resumed game) for the user:
- `kvisionApp-e2e/probes/artifacts-echo-verify/screenshot-resume-dialog.png`
- `kvisionApp-e2e/probes/artifacts-echo-verify/screenshot-resumed-game.png`

## How to run

```bash
# 1. Start all three servers (do NOT run JUST :server:run)
bash debugger/scripts/start_servers.sh
for i in $(seq 1 15); do
  if ss -tlnp 2>/dev/null | grep -E ":(7070|9080|8080)\b" | wc -l | grep -q 3; then
    echo "all up"; break
  fi
  sleep 5
done

# 2. Phase 1: seed snapshot
cd kvisionApp-e2e
timeout 900 node probes/echo-verify-resume.mjs --phase=1 2>&1 | tee /tmp/phase1.log

# 3. Restart all three servers
for port in 7070 9080 8080; do fuser -k $port/tcp 2>/dev/null; done
sleep 5
mkdir -p ~/Desktop/Workspaces/Autogenesis/Autogenesis/server/build/generated/ksp/main/kotlin/gameInit
bash debugger/scripts/start_servers.sh
for i in $(seq 1 15); do
  if ss -tlnp 2>/dev/null | grep -E ":(7070|9080|8080)\b" | wc -l | grep -q 3; then
    echo "all up"; break
  fi
  sleep 5
done

# 4. Phase 2: resume from snapshot, capture both screenshots
timeout 600 node probes/capture-resume-flow.mjs 2>&1 | tee /tmp/phase2.log

# 5. Login flow regression suite
timeout 240 node probes/login-flow-e2e.mjs 2>&1 | tee /tmp/login-flow-e2e.log
```

Expected output:
- `login-flow-e2e.mjs`: 11 passed, 0 failed
- `capture-resume-flow.mjs`: both screenshots saved

## The user's exact spec (2026-06-27)

1. **Login** → server-extend pushes `client.resumeAvailable` if a save exists
2. **ResumeOrNewDialog** appears with EXACTLY 3 buttons: Resume / New Game / Cancel
3. Each button behaves correctly:
   - Resume → restores game, opponent's turn continues if mid-turn
   - New Game → clears snapshot, lands on main menu
   - Cancel → closes dialog, lands on main menu, snapshot preserved
4. **Popup must NOT reappear** on mid-game reconnects (the `isGameActive` guard
   in `notifyResumeAvailable` enforces this)
5. **No "fail to fetch" errors** at any point in the flow

## Diagnostic order (the user's spec verbatim)

"When the user reports a behavioral bug, the diagnostic order is:
(1) verify the dev stack is fully up
(2) check the server log for the expected state-transition line
(3) only then look at code."

```bash
# Step 1: dev stack
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080)\b" || echo "STACK DOWN"

# Step 2: server logs
tail -50 /tmp/autogenesis-proxy/srv.log | grep -E "rehydr|rehydrate|started turn|executeSingleTurn|notifyResume|consumed|persist"
tail -50 /tmp/autogenesis-proxy/se.log | grep -E "pushed resume|ResumeAvailabilityPushService"

# Step 3: only then look at code
```

## Testid surface (do not remove)

These `data-testid` attributes are the contract for all e2e probes:

- `data-testid="loading-screen-cta"` — must be clicked to dismiss the loading screen
- `data-testid="login-as-guest"` — Login As Guest button (`ui/LoginWidgets.kt:269`)
- `data-testid="main-menu"` — MainMenu root VPanel (`ui/MainMenu.kt:60-65`)
- `data-testid="resume-or-new-dialog"` — ResumeOrNewDialog root (`ui/ResumeOrNewDialog.kt:57`)
- `data-testid="gameplay-ui"` — GameplayUI root (`ui/gameplay/GameplayUI.kt:74`)

**There is NO `data-testid="login-page"`.** Use `.login-widget-window` class instead.

## The user's stated loss of trust (verbatim)

> "Ok I dont trust you to be frank. So you are going to e2e test this and verify
> its working the way I stated it needs to."

> "Whats going on? Is the record being deleted after loading it or not? I need to know
> if its bugged or not."

> "Look for any bugs you find or any case where it doesn't work as expected and
> ensure the login flow works as it used to. And resume works to my specs this time
> dammit."

**Operating rule:** never report a fix without first running these probes end-to-end.
If a probe is not appropriate to the change, write a new probe that covers the
user's stated contract for that change. **The proof IS the fix.**

## Common probe bugs (from this session's iteration)

These bit the probe through 6 iterations before all 11 tests passed. They will
bite any future probe in this area:

1. `page.waitFor(async () => document.querySelector(...))` outside page context
   → `ReferenceError: document is not defined`. Use `page.waitForFunction(...)`.
2. `getByTestId('login-page')` doesn't exist. Use `getByTestId('login-as-guest')`.
3. OK button click is too early. The LoginPage message box starts with
   `ok=false, cancel=false`. Wait for OK to be appended by `setMessage("Loaded N")`.
4. `getByRole({ name: /^Cancel$/ })` may match the wrong button. Use
   `locator('[data-testid="resume-or-new-dialog"] button:has-text("Cancel")')`.
5. Resume dialog intercepts MainMenu clicks. Dismiss dialog first.
6. Server-extend port-7070 may be down. Always use
   `bash debugger/scripts/start_servers.sh`.
7. `build/generated/ksp/main/kotlin/gameInit` may not exist after `gradle clean`.
   `mkdir -p` it before starting servers.
8. The "Your Turn To Act" text is the HUMAN's prompt, NOT the AI's turn. Source
   of truth is server log `TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>'`.
9. `globals.World.worldData` defaults to a fresh world at page load — body text
   "Round: 1" appears even when no restore happened. Capture concrete state
   (round + leaderboard + turn order), not body text.
10. The 20013 CloudSave delete permission is documented in `docs/OPERATIONS.md` as
    a known issue with a working consumed-sentinel workaround — do NOT re-report
    as a P0 bug.

## SkipLogin boot-storm wedge (added 2026-08-12)

**Symptom:** when using `?skipLogin=true` + waiting 1-12s before firing any RPC
(e.g. uploadMapGate, refreshMapCatalogue), the JS LogWriter captures a WARN at
the call site:

```
[warn] MapUploadModal: ServerExtendBridge.rpcInvoker is null (disconnected); aborting publish
```

Same shape appears in `CollectionOverlay.refreshMapCatalogue()`.

**Root cause:** SKIP-LOGIN triggers 4-5 redundant `ServerExtendBridge.connect()`
calls during boot. `Main.kt:682` calls once with `accelbyteId=null`, then
`Main.kt:252` is called 4-5x in 9ms with `accelbyteId=guest-user`. Each call
uses `generatePlayerId()` so the dedup at `RestRpcBridgeJs.connect:58`
(`currentPlayerId == playerId && currentAccelbyteId == accelbyteId && isConnected`)
fails — every call tears down the previous client and opens a fresh SSE channel.
Orphaned clients' auto-reconnect (`keepReconnecting = true`) keeps running.
The active channel races the orphaned reconnect loops and dies within 8-11s.

**Confirmed receipt** (from `probes/map-upload-e2e.mjs` artifacts):

```
17:01:07.904 → RestRpcBridgeJs.connect playerId=rest-client-1159749095 accelbyteId=guest-user
17:01:07.906 → RestRpcBridgeJs.connect playerId=rest-client-1305013   accelbyteId=guest-user
17:01:07.907 → RestRpcBridgeJs.connect playerId=rest-client-1534629043 accelbyteId=guest-user
17:01:07.913 → RestRpcBridgeJs.connect playerId=rest-client-763909874  accelbyteId=guest-user
17:01:18.157 → MapUploadModal: ServerExtendBridge.rpcInvoker is null (disconnected); aborting publish
```

**Diagnostic recipe:** if a UI publish/subscribe/refresh probe fails with
"rpcInvoker is null" or "RPC error: client closed":

1. Grep the captured console for `ServerExtendBridge: connecting` and `RestRpcBridge: connected to` — count the connects. If more than 2 within the first 2s of page load, the storm is firing.
2. Confirm with `ss -tlnp | grep -E ':(7070|8080|9080)'` — server side is alive (the wedge is JS-side).
3. `curl -sN -H 'Accept: text/event-stream' 'http://127.0.0.1:7070/events?playerId=probe-123&guestMode=true' | head` — server returns session.ready + connection_state events. If yes, server is healthy, wedge is purely client-side.

**Workaround options:**

- **Path A (resume-flow probes use `?skipLogin=true`):** the resume probes wait
  for the ResumeOrNewDialog SSE push which is the very first push after
  reconnect, so the wedge doesn't bite. But ANY post-resume probe (e.g.
  pushing gameplay commands, refreshing billing) needs a fresh bridge —
  see option 2.

- **Path B (auth + bridge reset before RPC):** in skipLogin mode, after
  the loading-screen CTA click and MainMenu mount, wait **at least 12s**
  before firing ANY RPC. Then re-bind the bridge by triggering a benign
  RPC first (`server.extend.getUsageHistory` works) — it forces a fresh
  connect attempt and the race resolves.

- **Path C (real OAuth login):** use the `Login As Guest` button
  (`data-testid="login-as-guest"`, see `autogenesis-local-dev` Path B
  section). Real OAuth does NOT trigger the boot-storm because the bridge
  is already bound by the time MainMenu mounts. Probe artifacts at
  `kvisionApp-e2e/probes/guest-login.mjs` demonstrate the flow.

**Pre-ship gate for any new skipLogin UI probe:** add a wait-and-bind
probe that asserts `window.<bridgeRef>?.rpcInvoker` is non-null before
the main flow runs. If the assertion fails, surface the wedge as the
finding (not "the upload RPC is broken") — saving 30+ minutes of
misdiagnosis per future session.

## JS LogWriter sink correction (added 2026-08-12)

AGENTS.md documents `localStorage['autogenesis_logs']` as the browser
log sink. **This is stale.** `sharedModel/src/jsMain/kotlin/org/ttt/autogenesis/logging/LogWriter.js.kt`
line 30 explicitly says: `localStorage persistence removed for performance`.
The actual sinks are:

- `console.{log,info,warn,error}` based on `entry.priority` (DEBUG → log, INFO → info, WARN → warn, ERROR → error)
- `POST http://127.0.0.1:9080/api/browser-log` only when `minPriority == LogPriority.DEBUG` (batched every 3s via `flushIntervalId`)

**Operational rule for UI probes:** capture browser logs via Playwright
`page.on('console', msg => captured.push(...))`, NOT via
`localStorage.getItem('autogenesis_logs')`. The latter will always
return an empty string. Format on the wire is
`"${timestamp} [${priority}] [${category}]: ${message}"` with
priority being the enum name (uppercase, e.g. `[DEBUG]`).

Probes that historically relied on localStorage log capture:
none — but a future session might re-discover the AGENTS.md claim and
waste time on it.

## After tests pass

Send BOTH screenshots via Discord:
- `kvisionApp-e2e/probes/artifacts-echo-verify/screenshot-resume-dialog.png`
  — shows the 3-button Resume dialog (Cancel | New Game | Resume)
- `kvisionApp-e2e/probes/artifacts-echo-verify/screenshot-resumed-game.png`
  — shows the resumed game with prior-turn narrative + "Awaiting <NPC>"

Always shut down all 3 servers at the end:
```bash
for port in 7070 9080 8080; do fuser -k $port/tcp 2>/dev/null; done
```

The user explicitly asked: "Once you are done with your task: Shut every game server
and client down." Leaving servers running will trigger "did you shut the servers
down?" follow-ups.

## Cost control for LLM-backed pipelines (added 2026-08-13)

The map-upload safety gate runs Bedrock Nova Lite on every upload. Without
cost-control guards, malformed or empty packs still trigger a real LLM
call — burning tokens for zero value. The operator's standing rule: gate
work that touches a Bedrock invocation must prove the no-burn path is
wired.

### Three guards the safety gate must implement

1. **Cap calibration against the actual model context window.** The
   empirical ratio for Nova Lite's Converse API image input is
   `990_000 tokens / 1_579_421 bytes ≈ 0.627 tokens/byte` (derived from a
   live trace that failed with `Context window size: 990000 Binary size:
   1579421`). The gate's `MAX_SAFE_BINARY_BYTES` must be calibrated so
   the image alone stays under ~70% of the 990 K window. Current cap:
   `900 * 1024 = 921_600 bytes` (~564 K tokens for the image, leaving
   ~426 K tokens for prompt / footer / reasoning / output).
   Test seam: `MapUploadGate.maxSafeBinaryBytesForTest()`.

2. **Always-downsample pre-flight.** The operator's directive: "always
   downsample any images we send to the map safety agent to 256K tokens
   in size." The gate must route EVERY image through
   `downsampleImageBytes(...)` — not just images above the cap. The
   helper's existing no-op fast path (`if (longestEdge <=
   DOWNSAMPLE_MAX_DIMENSION) return bytes`) keeps the cost bounded for
   small images. Cap-based gating was a pre-fix regression — the
   `MapUploadGateTest::small image passes through downsample without
   rejection` test pins the new contract.
   Downsample target: 1024×1024 → ~300 KB PNG → ~188 K tokens.

3. **Empty-pack fail-fast before the safety pipeline.** A pack with
   empty `imageBytes` OR `mapData.pins.isEmpty() && mapData.connections.isEmpty()`
   has no safety signal. The gate must reject with a specific reason
   (`"Map pack is empty: image entry has zero bytes"` /
   `"Map pack is empty: no pins or connections in map data"`) BEFORE
   the downsample / safety pipeline runs. Test contract:
   `MapUploadGatePackContentValidationTest` (3 tests).

### Typed exceptions for data-load failures

The prior shape used `!!` in `MapPackManager.unpack` and let NPEs
propagate. The gate's generic `catch (e: Exception)` then surfaced
`"Unpack failed: null"` — useless to the user and operator.

**Pattern:** replace `!!` with named `MapPackUnpackException` throws
in BOTH the JVM and JS implementations. Wrap the kotlinx.serialization
`decodeFromString` call in a try/catch that re-throws as
`MapPackUnpackException("Map.json is not a valid MapPackData (${e.message})")`.
Surface the typed exception's message verbatim through the gate.

**Test contract:** `MapUploadGatePackContentValidationTest::mapPackUnpackExceptionMessageSurfacesVerbatim` asserts the
exact `Unpack failed: <typed message>` reason reaches the client.

## Forbidden patterns (added 2026-08-13)

The operator explicitly rejected two patterns the agent added during
the safety-pipeline verification work. These are off-limits unless the
operator introduces them:

1. **Do NOT add `bypassSafetyInDev` / `DEV_SAFETY_LIVE_TEST=1` style
   env-gated bypass mechanisms to the production code without operator
   direction.** The "verify live safety works" investigation was
   one-shot; adding the env gate as a permanent fixture, plus
   `MapUploadGateBypassSafetyTest`, plus a ServerExtend.kt env-var
   branch, is the wrong shape. The operator's reaction: "FYI I'm
   looking at hte git diff for the saftey agent builder. And idk wwtf
   you did or think you're doinng here. But you butchered it. You
   will restore it to it's intended design." Restore to HEAD and
   verify via trace.json inspection (`~/.tpipe/debug/trace/MapUploadGate/trace.json`)
   instead.

2. **Do NOT refactor `MapPackManager.unpack` / `MapUploadGate.uploadMapGate`
   to "the factory pattern"** when the existing shape is the
   intended design. The original `buildMapSafetyAgent` uses two pipes
   (`image pipe` + `text pipe`), each with its own per-pipe
   `setOnFailure` callback that parses `MapSafetyCheck` JSON via
   `extractJson<MapSafetyCheck>` and calls
   `MapUploadErrorHandlers.sendMapUploadError(id, failureReason)`.
   The `!!`-driven NPEs were a known bug, but the dual-pipe shape
   was the intended design. The TDD-driven "collapse to one pipe"
   refactor was rejected; the operator's exact words: "ensure the
   backrend functions understands to to interpret it's output." The
   backend = the two per-pipe `setOnFailure` callbacks that parse
   the JSON and dispatch the specific LLM reason.

## TDD discipline: tests must fail RED against the existing wrong code

The operator reads git diff. A TDD sentinel that asserts
"at least one pipe" + "first pipe has a non-blank name" passes
trivially against both the wrong shape (two hand-rolled pipes) and
the right shape (one factory pipe). That test is useless — it pins
nothing.

**Rule:** every TDD sentinel must fail RED against the existing
wrong code with a specific assertion failure that names the wrong
shape. The operator's exact words: "Wtf are you smoking? The safety
agent returns a pipeline that is setup with both pipes."

A useful assertion: `pipe.reasoningPipe != null` (catches the
no-reasoning-pipe shape), `pipeline.getPipes().size == 1` (catches
the two-pipe shape if the spec is one), or
`pipe.reasoningPipe is null` (catches a wrong-reasoning-pipe shape).
The assertion message should name the wrong shape in plain English.

## Patch tool: when `path` is dropped into a retry loop, switch to terminal-based Python text replacement

Repeated observation: the `patch` tool can drop the `path` parameter
on retries with `error: "path required"` while the `old_string` /
`new_string` are present. Three retries with the same arguments
fires the `same_tool_failure_warning` loop.

**Fix:** drop the `patch` retry loop. Switch to terminal-based
Python text replacement:

```python
path = '/abs/path/to/file.kt'
with open(path) as f: text = f.read()
old = '...unique anchor...'
new = '...'
if old not in text:
    print('OLD NOT FOUND')
else:
    text = text.replace(old, new, 1)
    with open(path, 'w') as f: f.write(text)
    print('REPLACED')
```

This works reliably for file contents <= 8K tokens. For larger
edits, break the diff into multiple smaller patches via `read_file`
+ targeted `write_file` (the entire-file write is reliable; the
targeted-diff `patch` is what loops).

## Support file: ad-hoc targeted-suite verification

`scripts/hermes-verify-targeted-suite.sh` runs a small set of test
suites (e.g. `MapUploadGateTest`, `MapUploadGateDownsamplePreFlightTest`,
`MapUploadGatePackContentValidationTest`) without the full
build-chain warmup. Greps the JUnit XML test counts and exits
non-zero on any failure. Copy to a session-specific path
(`/tmp/hermes-verify-<feature>-<date>.sh`) when running so the
receipt trail is identifiable.

## Where to find the harness

- `kvisionApp-e2e/probes/login-flow-e2e.mjs` — the 11-assertion suite
- `kvisionApp-e2e/probes/echo-verify-resume.mjs` — Phase 1 + Phase 2 snapshot+resume
- `kvisionApp-e2e/probes/capture-resume-flow.mjs` — captures both screenshots
- `kvisionApp-e2e/probes/capture-dialog.mjs` — quick capture of just the dialog
- `kvisionApp-e2e/probes/guest-login.mjs` — proves real AccelByte OAuth login
