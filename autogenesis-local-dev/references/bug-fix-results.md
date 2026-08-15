# Bug Fix Reference — Round 1 (2026-05-09) Bug Hunt Session

## FIXED

### BUG #8 — Defeated NPCs in Turn Order (CONFIRMED FIX)
**File:** `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt` (line ~1530)

**Problem:** Inconsistent filtering of defeated NPCs between turn order population and interference rolling.

**Before:**
```kotlin
val eligibleNpcs = world.npc.filter { it.type != NpcType.Passive }
```

**After:**
```kotlin
val eligibleNpcs = world.npc.filter { !it.isDefeated && it.type != NpcType.Passive }
```

**Verification:** Compile check passed. Line 1792 already had `!it.isDefeated` — now line 1530 matches.

---

### BUG #2 — Session ID Mismatch (PARTIAL FIX)
**File:** `server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt`

**Problem:** 5 methods used `findSession(connectionId)` to route to a single session — if the session ID didn't match, events were silently dropped.

**Fixed methods:**
1. `broadcastPromptStatus` (line 26)
2. `sendInitialSync` (line 51) — also fixed all `session.sendRpcMessage` to `sessions.forEach { it.sendRpcMessage }`
3. `sendCommandClassification` (line 230)
4. `sendAgentStreamPayload` (line 246)
5. `sendAgentWorkStream` (line 273)

All changed from `findSession(connectionId)` → `findAllSessions()` so broadcasts reach ALL connected clients.

**Limitation:** Browser still can't display gameplay in `skipLogin=true` mode because `World.localPlayer` is never set. See `references/browser-main-menu-stuck.md`.

---

## REVISED (No Code Change)

### BUG #3 — NPC Thinking Not Captured
**Verdict:** NO BUG FOUND.

The hostile review found the capture logic correctly targets the reasoning pipe. The original bug hunt report's analysis was inaccurate. No code change needed.

---

## UNPROVEN (Needs Working Browser Gameplay)

All other bugs from the original list (#4, #5, #6, #7, #9, #10, #11) could not be confirmed or disproven because the browser never left the main menu. Need a working browser gameplay session to continue bug investigation.