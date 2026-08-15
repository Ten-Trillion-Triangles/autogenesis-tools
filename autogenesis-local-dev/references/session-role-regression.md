# SessionRole Regression (2026-05-10)

## Root Cause

Commit `9f8ca9b05` ("python controller progress", 2026-05-09 19:30) introduced `SessionRole` (PRIMARY vs CONTROLLER) to PlayerConnectionManager.kt. The architecture:

- **PRIMARY**: Browser client — game terminates if all PRIMARY sessions disconnect
- **CONTROLLER**: Python/AI debugger — game survives without PRIMARY connections

**The bug**: Python controller never updated to pass `role=CONTROLLER` in WebSocket URL.

```kotlin
// Server.kt:292-296 — defaults to PRIMARY
val sessionRole = when (roleParam) {
    "CONTROLLER" -> SessionRole.CONTROLLER
    else -> SessionRole.PRIMARY  // ← Python sends nothing, gets PRIMARY
}
```

Python's `_build_url` at `controller.py:465`:
```python
# BEFORE (broken):
return f"{self.url}?playerId={player_id}&guestMode=true"

# AFTER (fix):
return f"{self.url}?playerId={player_id}&guestMode=true&role=CONTROLLER"
```

## Why Server Dies

```
Python controller connects → role=PRIMARY (no role param) → registered as PRIMARY
Browser connects → role=PRIMARY → registered as PRIMARY

Browser disconnects → hasAnyPrimarySession() = TRUE (Python is PRIMARY!) → timer NOT started
Python disconnects → hasAnyPrimarySession() = FALSE → 15s timer fires → exitProcess(0)
```

## Secondary Bug: onConnected/onReconnected Cancel for ALL Roles

```kotlin
// Server.kt:185-190 — cancels shutdown on ANY connection
if(gameState.WorldManager.isSinglePlayer)
{
    shutdownJob?.cancel()  // ← no role check! cancels even for CONTROLLER
    ...
}
```

Fix:
```kotlin
if(gameState.WorldManager.isSinglePlayer && session.role == SessionRole.PRIMARY)
{
    shutdownJob?.cancel()
    ...
}
```

Same fix needed at lines 240-245 (`onReconnected` handler).

## Evidence

All recent sessions (2026-05-10) show Gradle processes dying with exit -15 (SIGTERM):
- server-extend: registered RPC handlers, died 1.4s after startup
- game server: broadcast to 7 sessions, died mid-Round 1
- webpack: compiled successfully, died before serving

The pattern matches `exitProcess(0)` in the 15s timer, except Gradle itself receives SIGTERM. Possible Gradle parent process also getting SIGTERM'd, or external cleanup script.

## Files to Fix

1. `controller/controller.py:465` — add `&role=CONTROLLER` to `_build_url`
2. `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:185-190` — add `session.role == SessionRole.PRIMARY` check
3. `server/src/main/kotlin/org/ttt/autogenesis/server/Server.kt:240-245` — same check in `onReconnected`