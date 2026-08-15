# Session 2026-05-09 — Bug Fix Session: Session Mismatch + UI Signals

## What Was Fixed

### Fix #1: BUG #2 — Session Mismatch (10,014 session-not-found warnings)

**Root cause:** `UiSignalRpcHandlers` used `findSession(connectionId)` for broadcasts — single-session lookup. In dual-control mode, both browser and Python controller hold sessions for the same player. Game state was being sent to ONE session only, causing "session not found" warnings for the other.

**Fix:** Changed 5 methods in `UiSignalRpcHandlers.kt` from `findSession()` → `findAllSessions()` + `sessions.forEach { it.sendRpcMessage }`:
- `broadcastPromptStatus` (line ~26)
- `sendInitialSync` (line ~51) — also changed `session.sendRpcMessage(...)` → `sessions.forEach { it.sendRpcMessage(...) }`
- `sendCommandClassification` (line ~230)
- `sendAgentStreamPayload` (line ~246)
- `sendAgentWorkStream` (line ~273)

**File:** `server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt`

### Fix #2: BUG #8 — Defeated NPCs in Turn Order

**Root cause:** TurnHarness line 1530 used `world.npc.filter { it.type != NpcType.Passive }` without `!it.isDefeated`. Defeated NPCs appeared in turn order. The interference rolling at line 1792 correctly had `!it.isDefeated`.

**Fix:** Added `!it.isDefeated` to line 1530:
```kotlin
val eligibleNpcs = world.npc.filter { !it.isDefeated && it.type != NpcType.Passive }
```

**File:** `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt`

### BUG #3 — REVISED (No actual bug)

The initial bug analysis claimed "thinking capture looks at author pipe instead of reasoning pipe." **Hostile review found no bug exists.** The thinking capture code in `BedrockConfig.kt:592-629` correctly targets the reasoning pipe. The session's traces showed thinking was generated and the capture mechanism works as intended. No code change needed.

### New UI Signal Infrastructure

Added 5 new Python→browser debug signals via `DebugSignalBridge.kt` → `DebugConsole.kt`:
- `OPEN_WIDGET:widgetName` — opens widget overlays (worldStats, playerResources, stats, playerTerritories, playerInfo, settings, history)
- `CLOSE_WIDGET` — closes all open widgets
- `EXECUTE_COMMAND:text` — sets command text AND submits atomically
- `SHOW_TURN_RESOLUTION` — forces turn resolution panel to show
- `CAPTURE_SCREENSHOT` — placeholder (Playwright CDP is used for screenshots)

New Kotlin files modified:
- `DebugSignalBridge.kt` — 5 new dispatch cases
- `DebugConsole.kt` — 5 new trigger methods + `KEnv.currentGameplayUI` registration on GameplayUI creation
- `KEnv.kt` — added `currentGameplayUI: GameplayUI?` global reference
- `CommandBox.kt` — added `setAndSubmit(text: String)` public method for atomic command execution
- `controller.py` — added 5 new `send_*` methods to `GameController`

### Compilation Pitfalls Encountered

**Kotlin/JS `split(String, Int)` does not exist:**
```kotlin
// BROKEN on Kotlin/JS — split(String, Int) not available
val parts = signal.split(":", 2)

// FIXED — use substringAfter which is available on all platforms
val commandText = signal.substringAfter("EXECUTE_COMMAND:", "")
```

**Kotlin/JS compile task is `compileKotlinJs`, not `compileKotlin`:**
```bash
# WRONG — ambiguous task name
./gradlew :kvisionApp:compileKotlin

# CORRECT
./gradlew :kvisionApp:compileKotlinJs
```

**Gradle task name expansion:** Full task name is `compileKotlinJs`. Run `./gradlew :project:tasks --group build` to find exact task names for multiplatform projects.

## Architecture After Fixes

```
Browser (KVision) + Python Controller (dual-control, same player slot)
  ↓ WS registration via playerAlias matching
Game Server (9080)
  ↓ findAllSessions() broadcast — ALL sessions receive game state
Both browser and Python receive: turn updates, thinking, narrative, turn resolution
```

Python uses `send_open_widget()`, `send_execute_command()` etc. to drive browser UI. Browser captures screenshots via Playwright CDP. Python also talks directly to game server via WS for turn submission.

## Session Status

- All servers confirmed stopped post-session
- Compile check: `server:compileKotlin` ✓ `kvisionApp:compileKotlinJs` ✓
- Ports 7070/7075/9080/8080 confirmed free
- Skill updated with post-session log/trace analysis section