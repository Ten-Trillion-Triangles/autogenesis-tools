# Bug Hunt Session — 2026-05-10

11 bugs investigated during an active multi-round gameplay session using dual-control (Python controller + browser visual driver).

## Session Setup
- **Servers:** server-extend (7070), game server (9080), webpack (8080), Python controller (--no-ui), browser navigated to `http://127.0.0.1:8080/?skipLogin=true&playerId=lord-...`
- **Game:** Single-player with 3 AI opponents (Lord Maple Tree vs Officer, Narjan, Gl'kr'kr'kr'k)
- **Rounds completed:** 2 full rounds, karma reached 5

## Bug Status Table

| Bug | Status | Evidence |
|-----|--------|----------|
| #1 Server 15s shutdown | **FIXED** | SessionRole CONTROLLER fix verified; server stayed alive throughout |
| #2 AI thinking vanishes | **PARTIALLY FIXED** | `findAllSessions` fix in place; `SHOW_MAP` signal added for UI control |
| #3 NPC thinking not captured | **NOT A BUG** | Capture correctly targets reasoning pipe; hostile review confirmed architecture |
| #4 Writing UI stuck | **NOT OBSERVED** | "Result: (Planning...)" cleared between turns — no persistence bug found |
| #5 Reasoning [] in UI | **CANNOT PROVE** | Need mid-turn screenshot with reasoning panel visible |
| #6 Nemesis alert missing | **NOT TRIGGERED** | Karma=5, threshold=100 — needs aggressive action over many rounds |
| #7 Dark void / map display | **FIXED** | `SHOW_MAP` signal added; controller auto-calls on turn detection |
| #8 NPC flood with passives | **FIXED** | `!isDefeated` added at TurnHarness.kt:1530 |
| #9 Too many nemesis/elders | **NOT TRIGGERED** | Karma never reached 100 |
| #10 Counterplay cascade | **NOT OBSERVED** | No counterplay occurred this session |
| #11 Elder God generic | **NOT TRIGGERED** | No Elder God spawned |

## Key Finding — Dark Void Issue (BUG #7)

**Problem:** The center panel of GameplayUI defaults to `TurnResolutionWidget` (index 1), NOT the `MapViewer` (index 0). The map area appeared as a completely black/dark void even when the game was active and Lord Maple Tree's turn was in progress.

**Root Cause:** No signal existed to force the map view to display. `GameplayUI.showMap()` sets `centerStackPanel.activeIndex = 0` and hides `TurnResolutionWidget`, but there was no way for the Python controller to trigger this remotely.

**Fix Applied (2026-05-10):**
1. `DebugSignalBridge.kt` — added `Signals.SHOW_MAP = "SHOW_MAP"`
2. `DebugConsole.kt` — added `triggerShowMap()` calling `gameplayUI.showMap()`
3. `controller.py` — added `send_show_map()` method; called on both `ui.setResolutionStep: START` and `ui.activeTurn` turn detection events

**Verification:** Controller log shows `Sent SHOW_MAP signal to browser` immediately when Lord Maple Tree's turn was detected.

## Session Log

```
2026-05-10 11:59:16 | Controller started (playerId: lord-1778428756532-8374)
2026-05-10 11:59:17 | GAME_STARTED signal sent
2026-05-10 11:59:26 | Sent SHOW_MAP signal to browser (Lord Maple Tree's turn)
2026-05-10 11:59:27 | Action: "The dragon riders take to the skies for reconnaissance."
2026-05-10 12:01-12:36 | NPC turns executed (Officer, Narjan, Gl'kr'kr'kr'k)
2026-05-10 12:42 | Round 2 started with turn order [Lord Maple Tree, Officer, Narjan, Agent 9-Alpha, Gl'kr'kr'kr'k]
```

## Karma Progress
- Karma reached 5 (from Lord Maple Tree's successful action)
- Threshold for nemesis/elder god spawn: 100
- To trigger BUG #6 and #9: need aggressive hostile action across many rounds

## Unresolved — Need Screenshot Evidence
- **BUG #4**: Capture mid-turn transition screenshot to see if "Result: (Planning...)" persists
- **BUG #5**: Capture screenshot during player's turn while reasoning panel is visible
- **BUG #7**: After `SHOW_MAP` signal fires, verify map renders correctly (not dark void)