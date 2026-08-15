# DebugSignalBridge Signal Audit — 2026-05-10

Audit of `DebugSignalBridge.kt`, `DebugConsole.kt`, `GameplayUI.kt`, `controller.py`.

## Implemented Signals (ALL WORKING)

| Signal | Python Method | Browser Handler | Effect |
|---------|-------------|-----------------|--------|
| `GAME_STARTED:Name:Count` | `set_signal(...)` | `dispatchGameStarted()` | Sets `World.localPlayer`, adds GameplayUI |
| `OPEN_WIDGET:name` | `send_open_widget(name)` | `triggerOpenWidget()` | Opens HUD widget |
| `CLOSE_WIDGET` | `send_close_widget()` | `triggerCloseWidget()` | Hides all widgets |
| `EXECUTE_COMMAND:text` | `send_execute_command(text)` | `triggerExecuteCommand()` | `CommandBox.setAndSubmit()` |
| `SHOW_TURN_RESOLUTION` | `send_show_turn_resolution()` | `triggerShowTurnResolution()` | `centerStackPanel.activeIndex = 1` |
| `CLOSE_OVERLAY` | — | Escape key dispatch | Closes overlays |

## Missing — NOT YET IMPLEMENTED

| Signal | Intended Effect | Implementation Path |
|---------|-----------------|---------------------|
| `SHOW_MAP` | Call `GameplayUI.showMap()` — index 0 | Add `Signals.SHOW_MAP` → `dispatchShowMap()` → `triggerShowMap()` → `gameplayUI.showMap()` |
| `SWITCH_TAB:story\|territory` | Switch tab in TurnResolutionWidget | `TurnResolutionWidget.showStep(Int)` exists internally; expose via `triggerSwitchTab(tabName)` |
| `OPEN_MENU:collection\|matchmaking\|settings` | Open main menu overlays | Requires new page objects with `.show()` methods |

## Key Files

- Browser: `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/DebugSignalBridge.kt`
- Browser: `kvisionApp/src/jsMain/kotlin/ui/DebugConsole.kt`
- Browser: `kvisionApp/src/jsMain/kotlin/ui/gameplay/GameplayUI.kt` (`showMap()`, `showTurnResolution()`, `centerStackPanel`)
- Python: `controller/controller.py` (`DebugSignalServer`, signal methods at lines 1318–1436)