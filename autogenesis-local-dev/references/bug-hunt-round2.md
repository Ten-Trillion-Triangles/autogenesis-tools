# Bug Hunt Report — Autogenesis Round 2 (2026-05-10)

All servers stopped. Complete findings below.

## What We Ran
- Server-extend (port 7070) + Game server (port 9080) + Webpack dev server (port 8080)
- Python controller in --no-ui mode, playing Lord Maple Tree headless
- Headless Playwright screenshot observer capturing every ~45s
- 38 screenshots captured across ~35 minutes
- 18,332-line game server log and TPipe traces for 4 turns
- 10,014 occurrences of the session-not-found warning

## BUG #1: Game server does not shut down after 15s of all kvision clients disconnecting
**STATUS: PROBABLE — Cannot confirm in current session architecture**

**Evidence:** The server remained alive for the entire session (~1 hour). There is no log entry for "shutdown", "terminating", or "All clients disconnected" in the log. No shutdown signal was ever emitted.

**Root Cause:** The game server was started by a Gradle daemon owned by the Python controller (PID 2913495). The controller kept the game loop running via its WebSocket connection and TurnHarness coroutine loop. Even though the browser (the only "kvision client") was never properly connected (see BUG #2), the Python controller's WebSocket connection kept the game session alive. The "15s shutdown" mechanism exists in TurnHarness.kt but is triggered by the absence of ALL connections. Since the Python controller never disconnects while it has work to do, the server stays up.

**To test the 15s shutdown:** Terminate the controller WITHOUT terminating the server, then check if the 15s timer fires.

## BUG #2: AI thinking vanishes after turn is completed — AND sometimes is never dispatched at all
**STATUS: CONFIRMED — Critical architecture bug**

**Evidence:**
- 10,014 "Cannot send agent work stream, session 'kvision-ws-client-XXXX' not found" warnings
- All fire at ~250ms intervals — this is the sendAgentWorkStream loop in UiSignalRpcHandlers polling for sessions that don't exist
- UiSignalClientHandlers.kt receives these broadcasts and distributes to AgentWorkStreamWindow and TurnResolutionWidget — but session IDs don't match the browser's WebSocket ID, so nothing reaches UI
- TPipe traces show thinking WAS generated (traces exist for Round_1_Turn_1_Zeta and Round_1_Turn_0_Lord_Maple_Tree with reasoningRounds content)
- BUT thinking capture logs show author pipe repeatedly with showThinking=false: "[THINKING_CAPTURE] showThinking=false - not capturing thinking for pipe=author"

**Root Cause (two issues):**
1. Session mismatch: Python controller sends "kvision-ws-client-XXXX" sessions but browser's WebSocket ID was always different (e.g., kvision-ws-client-1592853524). UiSignalRpcHandlers looks up sessions by ID and fails.
2. Thinking capture disabled: The thinking pipeline uses the author pipe (not the reasoning pipe) and showThinking=false in many cases, so thinking is never captured.

**Code locations:**
- UiSignalRpcHandlers.kt:sendAgentWorkStream() — session lookup
- TurnHarness.kt:561-710 — handleAiTakeover flow waits for submitPlayerPlay from Python controller
- BedrockConfig.kt:592-629 — [THINKING_CAPTURE] block decides whether to extract thinking from author pipe

## BUG #3: NPC thinking is not fully captured as expected
**STATUS: CONFIRMED — Design limitation**

**Evidence:**
- NPC thinking IS being generated (TPipe traces exist for Zeta, Lord Maple Tree, Officer with reasoningRounds)
- But [THINKING_CAPTURE] logs show it repeatedly attempts to extract thinking from the author pipe, not the reasoning pipe
- showThinking is set to true on the reasoning pipe but false on the author pipe — capture logic in BedrockConfig.kt:592 looks at the author pipe, so it captures nothing

**Root Cause:** In BedrockConfig.kt:629, the capture condition checks `parentPipe.pipeName == "author"` — the thinking is in the reasoning pipe sub-agent, but capture is at the top-level author level.

## BUG #4: Writing UI got stuck on prior output after an NPC took their turn
**STATUS: CANNOT PROVE — Browser never reached gameplay screen**

**Evidence:** All 38 screenshots show main menu (AUTOGENESIS title, PLAY button, COLLECTION, etc.). DebugSignalBridge poll never received "GAME_STARTED" signals (controller had died). Browser was never in gameplay state, so cannot observe whether writing UI got stuck.

## BUG #5: Reasoning failed to capture after NPC turn — rendered only as [] in the UI for Zuzu's second turn
**STATUS: CANNOT PROVE — Browser never reached gameplay screen**

**Evidence:** No browser gameplay was visible in any screenshot. The "[]" empty reasoning box is a UI-rendering issue, not a server-generation issue. TPipe traces for Zeta's turn (Round_1_Turn_1_Zeta) contain full reasoning content. Issue is display path (BUG #2), not generation path.

## BUG #6: Nemesis and elder god alert screen didn't appear
**STATUS: CANNOT PROVE — No nemesis or elder god spawned**

**Evidence:**
- Log shows: "Karma threshold not met (value=0)" and "Karma threshold not met (value=5)" — no nemesis spawned
- No broadcastNemesisThreatAnnouncement calls succeeded in our session
- TurnResolutionWidget.kt:1804-1873 defines NemesisThreatPage but only appears if server broadcasts NemesisThreatAnnouncementData via UiSignalRpcHandlers.broadcastNemesisThreatAnnouncement()
- TurnHarness.kt:1610-1662 spawn logic requires karmaPoints >= 100
- Karma only reached 5 in our session — far below 100 threshold

**To trigger:** Play more aggressively to accumulate karma.

## BUG #7: Character icons jumble turning into a blue person icon
**STATUS: CANNOT PROVE — Browser never reached gameplay screen**

**Evidence:** No gameplay screenshots exist. Npc struct has NO imageUrl or portrait field — only NpcType enum. UI in NpcVisuals.kt uses FontAwesome icons: Active→fas fa-user-tie, Hostile→fas fa-skull, Nemesis→fas fa-dragon, ElderGod→fas fa-biohazard. The "blue person icon" could only appear if PlayerInfoWidget.kt or NpcVisuals.kt falls back to a default icon when a player type is unrecognized. No evidence in current session.

## BUG #8: Change to eligible NPC's doesn't handle the fact that we shouldn't flood with passives
**STATUS: CONFIRMED — Code inconsistency found**

**Evidence:** Clear inconsistency:
- TurnHarness.kt:1530 (resolving actor): `val eligibleNpcs = world.npc.filter { it.type != NpcType.Passive }` — does NOT filter `isDefeated`
- TurnHarness.kt:1792 (interference rolling): `val eligibleNpcs = npcs.filter { !it.isDefeated && it.type != NpcType.Passive }.shuffled(rng)` — DOES filter `isDefeated`

**Root Cause:** Turn order population at line 1530 includes defeated NPCs (so long as not Passive type), while interference rolling at line 1792 correctly excludes defeated NPCs. **Fix:** Add `!it.isDefeated` to line 1530.

## BUG #9: Way too many nemesis and elder god spawned far too early in the game
**STATUS: NOT OBSERVED — Karma threshold never reached in this session**

**Evidence:** Log shows karma only reached 5. TurnHarness.kt:1574 requires karmaPoints >= 100 to spawn a nemesis. Nemesis protocol checked at round boundaries but always skipped. No excessive spawning observed.

**Note:** Code structure allows a 35% chance to spawn an ADDITIONAL nemesis even when one is already active (gameplayOrchestrator.kt:2625-2632). This is the likely source of "too many" if it were to occur — the 35% reinforcement chance compounds across rounds.

## BUG #10: Counterplay self-targeting caused cascade
**STATUS: NOT OBSERVED — No counterplay cascade occurred in this session**

**Evidence:** Log shows at least two counterplay bypasses: "Territory 'Iopolis' has no owner (skipping counterplay)" and "No player-owned territories found for counterplay". No cascade triggered. Self-targeting prevention code at gameplayOrchestrator.kt:1342-1350 correctly checks `!foundPlayer.name.equals(player.name, ignoreCase = true)` and skips self-targeting. May be a race condition or timing issue in a different session.

## BUG #11: Elder God AI is broken and returned a generic response
**STATUS: CANNOT PROVE — No Elder God appeared in this session**

**Evidence:** No Elder God spawned. Karma never exceeded 5. elderGodAgent.kt code exists and sets showThinking=true and uses BedrockConfig.authorBuilder() with appropriate prompt injection. TPipe trace analysis confirmed the elder god prompt DOES contain destruction priority instructions. Without an actual Elder God appearance, cannot evaluate whether AI returns "generic" responses. Code appears correctly structured but no runtime evidence.

## Summary Table

| Bug | Status | Evidence |
|-----|--------|---------|
| #1 Server shutdown (15s) | PROBABLE | Server stayed up 1hr despite no browser; no shutdown log found |
| #2 AI thinking vanishes | CONFIRMED | 10,014 session-not-found warnings; session ID mismatch; showThinking=false on wrong pipe |
| #3 NPC thinking not captured | CONFIRMED | Capture looks at author pipe, thinking is in reasoning pipe sub-agent |
| #4 Writing UI stuck | CANNOT PROVE | Browser never left main menu |
| #5 Reasoning [] in UI | CANNOT PROVE | Browser never in gameplay; generation worked (traces exist) |
| #6 Nemesis alert missing | CANNOT PROVE | No nemesis spawned (karma=5, threshold=100) |
| #7 Blue person icon | CANNOT PROVE | Browser never in gameplay |
| #8 Eligible NPC flood | CONFIRMED | Line 1530 missing !isDefeated filter (vs line 1792 which has it) |
| #9 Too many nemesis/elders | NOT OBSERVED | Karma never reached 100; no spawns in this session |
| #10 Counterplay cascade | NOT OBSERVED | No counterplay occurred in this session |
| #11 Elder God generic | CANNOT PROVE | No Elder God spawned in this session |

**Root causes:** BUG #2 and #3 share the same architectural flaw — the thinking pipeline extraction targets the wrong pipe (author vs reasoning) AND the session ID routing from Python controller to browser fails. BUG #8 is a simple missing filter check at line 1530 of TurnHarness.kt.

---

## Round 2 Debug Session — The RPC Chain Mystery

### What we tested
- Server-side fix: UiSignalClientHandlers.handleSetLocalPlayer now calls triggerGameStarted() if GameplayUI is null
- Browser-side fixes: PLAYER_ID URL param + window.PLAYER_ID reading in WebSocketRpcBridge
- New playerId: lmt-1778377674

### Result: Still BROKEN — browser stuck on main menu

### What works:
1. Python controller generates player_id=lmt-1778377674 and uses it in matchmaking
2. Browser navigates with ?playerId=lmt-1778377674 → window.PLAYER_ID gets set
3. Server correctly identifies the browser connection as LordMapleTree
4. Server DISPATCHES ui.setLocalPlayer to lmt-1778377674 (confirmed in server log)
5. Browser receives WebSocket payloads (seen in browser log)

### What doesn't work:
1. handleSetLocalPlayer is NEVER called in browser
2. triggerGameStarted is NEVER called in browser
3. GameplayUI is NEVER created

### Evidence:
- Server log: "UiSignalRpcHandlers: Dispatching 'ui.setLocalPlayer' to lmt-1778377674" at 01:48:37
- Browser log: NO "Received Set Local Player" entry, NO triggerGameStarted
- Browser log: "Received WebSocket payload (length=131/132/143)" messages received but not processed

### Timing:
- Controller sends GAME_STARTED: 01:47:54.246
- Browser first connects (kvision-ws-client-*): 01:47:54.602 (BEFORE game session created)
- Browser registers as lmt-1778377674: 01:47:54.774 (first time, immediately deregistered)
- Game session created by server-extend: 01:47:54.547-548
- Browser re-registers as lmt-1778377674: 01:48:37 (correct, second attempt)
- Browser navigates to game URL: 01:48:40 (40 seconds after game started)

### Key discovery
The WebSocketRpcClient receives payloads but handleSetLocalPlayer is never called. RPC dispatch is not working despite connection being active.

### Hypotheses:
1. WebSocket message IS received but RPC deserialization fails silently (method name mismatch)
2. Two connections for same playerId cause message routing confusion
3. Nginx proxy on port 8080 intercepting requests (HTTP 404 seen in some attempts)
4. RpcRegistry not matching the notification because registration happened twice (once at app init, once after WS connect)

### Code paths investigated:
- UiSignalClientHandlers.handleSetLocalPlayer: handler registered correctly
- WebSocketRpcClient: receives messages and tries to dispatch via rpcRegistry
- RpcRuntime.dispatchNotification: looks up handler by method name
- Browser has "Received WebSocket payload" but no handler trace

### Root cause still unknown but narrowed
The setLocalPlayer IS being dispatched by server (confirmed). The browser IS receiving the WebSocket payload (confirmed). But handleSetLocalPlayer handler is NEVER invoked. The RPC message reaches the browser but NOT the handler function.

This suggests either:
- RPC message format mismatch (notification method name not matching registered handler)
- RpcRegistry.dispatchNotification is failing to find the handler
- WebSocket message is being consumed by something other than the RPC handler

### All servers stopped. Awaiting direction.