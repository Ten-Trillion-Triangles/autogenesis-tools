# Browser Stuck on Main Menu — Signal Race Condition

## Symptom

Browser navigated to `?skipLogin=true&playerId=lord-...` but stays on main menu. Game is running server-side (Python controller connected, turn timer ticking). `window.__triggerGameStartedCalled` is `false`.

## Root Cause — Signal Auto-Clear Race

`debug_signal_server.py` was auto-clearing the signal on every `GET /debug/signal`:

```python
# BEFORE (broken):
signal = self.signal.get()
self.signal.clear()  # ← consumed immediately after first poll
return signal
```

When the browser joined *after* Python had already sent `GAME_STARTED`:
1. Python sets signal → `GAME_STARTED:LordMapleTree:3`
2. Browser calls `GET /debug/signal?websocket_id=...`
3. Signal returned: `GAME_STARTED:LordMapleTree:3`
4. Handler clears signal: `self.signal.clear()`
5. Browser's JS dispatches and calls `triggerGameStarted()`
6. Works fine for the first browser

But if browser navigates *after* Python sends `GAME_STARTED`:
1. Python sends signal → signal is set
2. Python's *own* poll (or any other poll) consumes and clears the signal
3. Browser's first poll → signal already cleared → empty response
4. `triggerGameStarted()` never called → `GameplayUI` never added → stuck on main menu

## The Fix

**File:** `controller/debug_signal_server.py`, lines 92-100

Remove the auto-clear. Signals persist until explicitly overwritten:

```python
# AFTER (correct):
signal = self.signal.get()
# DO NOT clear — signal persists until overwritten by next game
return signal
```

Python sets signal → browser polls → signal returned → browser dispatches → `GameplayUI` shown. Signal stays set until the next game starts and Python sends a new signal (or no signal at all, which also works).

## Verification

After applying the fix, restart the Python controller process (signals are in-memory per-process).

```bash
# Verify fix is in place
grep -n "self.signal.clear" /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller/debug_signal_server.py
# Should return nothing (the clear() call was removed)

# Restart controller to pick up the fix
pkill -f "controller.py"
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/controller
stdbuf -oL -eL /tmp/autogenesis-dev/bin/python controller.py --no-ui
```

## Session Verification (2026-05-10)

- Python started, sent `GAME_STARTED:LordMapleTree:3` + `SHOW_MAP` signals
- Browser navigated to `?playerId=lord-1778450513376-305455`
- Browser polled and received `GAME_STARTED` + `SHOW_MAP` on first poll
- `window.__triggerGameStartedCalled = true` confirmed
- GameplayUI shown immediately with "Your Turn To Act", "GO TO MAP", turn history, resource bars
- No manual signal re-injection needed

## Do Not Navigate During Active Game

Even with the fix applied, navigating the browser URL (refresh, new URL) creates new WebSocket connections with new session IDs. The game session stays bound to the old connection IDs. Symptoms: "Your Turn To Act" shown but server already processing NPC turns, or browser shows stale turn state. Keep the browser URL stable throughout the session.