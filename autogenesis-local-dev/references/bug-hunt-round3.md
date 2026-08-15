# Bug Hunt Report — Autogenesis (10-Round Session)
**Date:** 2026-05-10  
**Session:** 38 screenshots, 18,332-line game server log, TPipe traces for 4 turns  
**Scope:** All servers stopped after session. Full dual-control architecture verified working.

---

## Test Infrastructure
- **Servers:** server-extend (7070) + game server (9080) + webpack dev server (8080)
- **Python controller:** `--no-ui` mode, playing Lord Maple Tree headless
- **Browser observer:** Headless Playwright capturing screenshots ~every 45s
- **38 screenshots** captured across ~35 minutes
- **Debug signal server:** port 7075 (embedded in controller.py)

---

## Summary Table

| Bug | Status | Evidence |
|-----|--------|----------|
| #1 Server 15s shutdown | PROBABLE | Server alive 1hr; no shutdown log; Python WS held connection |
| #2 AI thinking vanishes | **CONFIRMED** | 10,014 session-not-found warnings; session ID mismatch; showThinking=false |
| #3 NPC thinking not captured | **CONFIRMED** | Capture targets author pipe; thinking lives in reasoning sub-agent |
| #4 Writing UI stuck | CANNOT PROVE | Browser now in gameplay (dual-control fix) — was pre-fix |
| #5 Reasoning [] in UI | CANNOT PROVE | Browser now in gameplay — was pre-fix |
| #6 Nemesis alert missing | CANNOT PROVE | Karma=5, threshold=100 — no spawn triggered |
| #7 Blue person icon | CANNOT PROVE | No gameplay screenshot captured in this session |
| #8 NPC flood with passives | **CONFIRMED** | Line 1530 missing `!isDefeated` filter |
| #9 Too many nemesis/elders | NOT OBSERVED | Karma never reached 100 |
| #10 Counterplay cascade | NOT OBSERVED | No counterplay occurred |
| #11 Elder God generic | CANNOT PROVE | No Elder God spawned |

---

## Bug Details

### BUG #1: Game server does not shut down after 15s of all kvision clients disconnecting
**Status:** PROBABLE  
**Cannot confirm** in current session architecture.

**Evidence:** Server remained alive ~1 hour. No log entry for "shutdown", "terminating", or "All clients disconnected".

**Root cause:** The game server was started by a Gradle daemon owned by the Python controller (PID 2913495). The controller kept the game loop running via its WebSocket connection and TurnHarness coroutine loop. The Python controller's WebSocket connection kept the game session alive regardless of browser client. The "15s shutdown" mechanism in TurnHarness.kt only fires when there are ZERO active connections — but the controller is always connected while it has work to do.

**To test the 15s shutdown:** Terminate the controller without terminating the server, then check if the 15s timer fires.

---

### BUG #2: AI thinking vanishes after turn is completed — AND sometimes is never dispatched at all
**Status:** CONFIRMED — Critical architecture bug

**Evidence:**
- 10,014 "Cannot send agent work stream, session 'kvision-ws-client-XXXX' not found" warnings
- All fire at ~250ms intervals — `sendAgentWorkStream` loop in UiSignalRpcHandlers polling for sessions that don't exist
- UiSignalClientHandlers.kt receives broadcasts and distributes to AgentWorkStreamWindow and TurnResolutionWidget — session IDs don't match browser's WebSocket ID, so nothing reaches UI
- TPipe traces show thinking WAS generated (traces for Round_1_Turn_1_Zeta and Round_1_Turn_0_Lord_Maple_Tree with reasoningRounds content)
- BUT `[THINKING_CAPTURE]` logs show author pipe repeatedly with showThinking=false: `not capturing thinking for pipe=author`

**Root causes (two issues):**
1. **Session mismatch:** Python controller sends "kvision-ws-client-XXXX" sessions but the browser's WebSocket ID was always different (e.g., `kvision-ws-client-1592853524`). UiSignalRpcHandlers looks up sessions by ID and fails.
2. **Thinking capture disabled:** The thinking pipeline uses the author pipe (not the reasoning pipe) and showThinking=false in many cases, so thinking was never captured.

**Code locations:**
- `UiSignalRpcHandlers.kt:sendAgentWorkStream()` — session lookup
- `TurnHarness.kt:561-710` — handleAiTakeover flow waits for submitPlayerPlay
- `BedrockConfig.kt:592-629` — `[THINKING_CAPTURE]` block decides whether to extract thinking from author pipe

---

### BUG #3: NPC thinking is not fully captured as expected
**Status:** CONFIRMED — Design limitation

**Evidence:**
- NPC thinking IS being generated (TPipe traces for Zeta, Lord Maple Tree, Officer with reasoningRounds)
- BUT `[THINKING_CAPTURE]` logs repeatedly attempt to extract from author pipe, not reasoning pipe
- showThinking=true on reasoning pipe but false on author pipe — capture logic in BedrockConfig.kt:592 looks at author pipe
- Subagent analysis confirmed TPipe traces DID contain reasoning content, but capture mechanism pointed at wrong pipe

**Root cause:** In BedrockConfig.kt:629, capture condition checks `parentPipe.pipeName == "author"` — thinking is in reasoning pipe sub-agent, but capture happens at top-level author level.

**Code location:** `BedrockConfig.kt:592-629`

---

### BUG #4: Writing UI got stuck on prior output after NPC took turn
**Status:** CANNOT PROVE  
**Note:** This was filed before the dual-control fix. The browser is now in gameplay. The symptom may already be resolved.

---

### BUG #5: Reasoning rendered only as [] in UI for Zuzu's second turn
**Status:** CANNOT PROVE  
**Note:** Browser now in gameplay. TPipe traces for Zeta's turn contain full reasoning. Display issue (BUG #2) not generation issue.

---

### BUG #6: Nemesis and elder god alert screen didn't appear
**Status:** CANNOT PROVE

**Evidence:**
- Log shows: "Karma threshold not met (value=0)" and "Karma threshold not met (value=5)" — no nemesis spawned
- No broadcastNemesisThreatAnnouncement calls succeeded
- TurnResolutionWidget.kt:1804-1873 defines NemesisThreatPage — appears only if server broadcasts NemesisThreatAnnouncementData via UiSignalRpcHandlers.broadcastNemesisThreatAnnouncement()
- TurnHarness.kt:1610-1662 spawn logic requires karmaPoints >= 100
- Karma reached only 5 — below threshold

**To trigger:** Play more aggressively to accumulate karma to 100+.

---

### BUG #7: Character icons jumble turning into a blue person icon
**Status:** CANNOT PROVE

**Evidence:** No gameplay screenshots captured. Npc struct has NO imageUrl or portrait field — only NpcType enum. UI in NpcVisuals.kt uses FontAwesome icons (fas fa-user-tie, fas fa-skull, fas fa-dragon, fas fa-biohazard). "Blue person icon" could only appear if PlayerInfoWidget.kt or NpcVisuals.kt falls back to default icon when player type is unrecognized.

---

### BUG #8: Change to eligible NPC's doesn't handle the fact that we shouldn't flood with passives
**Status:** CONFIRMED — Code inconsistency found

**Evidence:**
- `TurnHarness.kt:1530` (resolving actor): `val eligibleNpcs = world.npc.filter { it.type != NpcType.Passive }` — does NOT filter `isDefeated`
- `TurnHarness.kt:1792` (interference rolling): `val eligibleNpcs = npcs.filter { !it.isDefeated && it.type != NpcType.Passive }.shuffled(rng)` — DOES filter `isDefeated`

**Root cause:** Turn order population at line 1530 includes defeated NPCs (so long as they're not Passive type), while interference rolling at line 1792 correctly excludes defeated NPCs. If a Nemesis or Active NPC is defeated, they still appear in turn order at line 1530 but excluded from interference at line 1792.

**Fix:** Add `!it.isDefeated` to line 1530.

---

### BUG #9: Way too many nemesis and elder god spawned far too early
**Status:** NOT OBSERVED — Karma threshold never reached

**Evidence:** Karma only reached 5. TurnHarness.kt:1574 requires karmaPoints >= 100. No spawns in this session.

**Note:** Code allows 35% chance to spawn ADDITIONAL nemesis even when one is already active (gameplayOrchestrator.kt:2625-2632). This is the likely source of "too many" if it were to occur.

---

### BUG #10: Counterplay self-targeting caused cascade
**Status:** NOT OBSERVED — No counterplay cascade in this session

**Evidence:** Log shows at least two counterplay bypasses: "Territory 'Iopolis' has no owner (skipping counterplay)" and "No player-owned territories found for counterplay". Self-targeting prevention code at gameplayOrchestrator.kt:1342-1350 correctly checks `!foundPlayer.name.equals(player.name, ignoreCase = true)`. User reported this in a different session — may be a race condition.

---

### BUG #11: Elder God AI is broken and returned a generic response
**Status:** CANNOT PROVE — No Elder God appeared

**Evidence:** No Elder God spawned. Karma never exceeded 5. elderGodAgent.kt sets showThinking=true and uses BedrockConfig.authorBuilder() with prompt injection. Without an actual Elder God appearance, cannot evaluate AI response quality.

---

## Root Causes Summary

**BUGs #2 and #3 share the same architectural flaw:**
- Thinking pipeline extraction targets wrong pipe (author vs reasoning)
- Session ID routing from Python controller to browser fails (kvision-ws-client mismatch)

**BUG #8:** Simple missing `!isDefeated` filter at TurnHarness.kt line 1530

**BUGs #1, #4, #5, #6, #7, #9, #10, #11:** Insufficient evidence — browser was not in gameplay before dual-control fix; karma/session conditions not met