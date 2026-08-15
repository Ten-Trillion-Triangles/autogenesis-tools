# Debug Signal Server — Signal Persistence Fix

## Root Cause

`debug_signal_server.py` line 96 called `self.signal.clear()` after returning the signal value via `GET /debug/signal`. This meant:

1. Python sends `POST /debug/signal` with `GAME_STARTED:Lord Maple Tree:3`
2. Browser polls `GET /debug/signal` → receives signal → **auto-clear fires**
3. Browser's `DebugSignalBridge.dispatch()` calls `triggerGameStarted()` → `GameplayUI` added
4. If browser navigates to the page AFTER step 2 (Python already started the game):
5. Browser polls `GET /debug/signal` → signal is empty (already cleared) → nothing happens
6. Browser stays on main menu

This is a race condition: the signal is consumed on the very first poll from ANY client. A browser that joins after the first poll gets nothing.

## The Fix

**Remove** `self.signal.clear()` from `GET /debug/signal` handler. The signal persists until Python explicitly overwrites it with a new signal.

Signal now only changes when:
- Python calls `set_signal("GAME_STARTED:...")` → new game started
- Python calls `set_signal("SHOW_MAP")` → turn map shown
- Python calls `clear_signal()` → explicit clear

## Why Persistence Is Architecturally Correct

In dual-control, the Python controller owns the game state. The browser joins as an observer/visual driver via `?playerId=`. It is expected that the browser may connect after the game has already started. The signal must survive across polls AND across late connections.

## Test Coverage

**File:** `controller/tests/test_debug_signal_server.py` (20 tests, all pass)

Key regression tests:
```
test_signal_persists_across_multiple_polls   — 5 consecutive GETs, all return same value
test_signal_persists_for_10_consecutive_polls — 10 polls, simulates real browser polling
test_new_signal_overwrites_old_signal        — explicit overwrite still works
test_concurrent_get_and_set                  — thread safety under concurrent load
```

Run: `cd controller && /tmp/autogenesis-dev/bin/python -m pytest tests/test_debug_signal_server.py -v`

## Affected File

`controller/debug_signal_server.py` — lines 92-106 (GET /debug/signal handler)