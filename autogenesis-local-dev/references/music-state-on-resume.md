# Music State on Resume — Architecture Note (2026-06-24)

When the user resumes a saved single-player game, music restoration works
through the existing `audio.syncState` broadcast — no custom
`musicState` field on `GameSnapshot` is needed. This reference pins
which path handles which case so future session work doesn't reinvent
the wheel.

## Where each music source lives

| Source | Stored where | Survives server restart? | Resume mechanism |
|---|---|---|---|
| Gameplay music (start/nemesis/end) | `AudioManager.playingObjects` (JVM singleton) | NO — fresh DS starts empty | `sendInitialSync` at `server/.../UiSignalRpcHandlers.kt:114-119` broadcasts `audio.syncState` containing `AudioManager.buildSyncState()`. Client picks up the currently-scheduled tracks. |
| Menu music (repeating ambient) | `MusicRunner.currentMusicIds` (JS singleton) | YES — browser-resident state | Restarts on every `MainMenu.init` via `MenuMusicPlayer.start()` at `kvisionApp/.../MainMenu.kt:96`. No server state involved. |
| Music volume / channel mute | `AudioManager.globalVolume` + `AudioManager.channels` | NO (for game) / persisted (for global) | `AudioManager.buildSyncState()` includes both; same `audio.syncState` broadcast covers it. |
| Music selector per-turn | `MusicSelector.selectForTurn()` called from `TurnHarness.executeSingleTurn` | YES across turns within a session; NO across server restarts | First turn after a fresh-DS resume calls `MusicSelector.selectForTurn` → `AudioManager.broadcastMusicSchedule`. Brief delay before first music fires. |

## Resume cases

1. **In-place reconnect** (same DS process, WS reconnect without server restart):
   - `sendInitialSync` runs from `GameRestoreRpcHandlers.applyRestoredWorldAndSync` at `server/.../GameRestoreRpcHandlers.kt:198-228` (after a Resume click) OR from `Server.kt:362-378` (on initial WS connect after auto-restore).
   - `audio.syncState` carries the current gameplay music tracks.
   - **Result: music resumes on the same tracks.**

2. **DS-respawn reconnect** (server shut down after DC, user logs in, gets fresh DS via `server.extend.requestResume`):
   - `AudioManager.playingObjects` is empty on the fresh DS (no music was scheduled there).
   - `sendInitialSync` still fires after `setGameMode(resumeFromVfs=true)` triggers `restoreRunningGameForUser`, but `audio.syncState` has empty `scheduledObjects`.
   - First `TurnHarness.executeSingleTurn` after resume calls `MusicSelector.selectForTurn` which broadcasts `audio.musicSchedule`.
   - **Result: brief delay before first music track; no persistent music gap.**

3. **Cancel the resume dialog** (returns to menu without resuming):
   - `MainMenu.init` re-runs `MenuMusicPlayer.start()`.
   - **Result: menu music starts fresh from beginning.**

4. **Reconnect into a fresh game (no snapshot)**:
   - Same as case 3 — menu music plays, no gameplay music.

## What NOT to add

- **Do NOT add a `musicState: MusicStateSnapshot?` field to `GameSnapshot`.** The existing `audio.syncState` covers everything that needs to persist. Adding a custom field would duplicate the data path and create two sources of truth for "what's playing."
- **Do NOT add a custom `client.musicState` RPC method.** The existing `audio.syncState` (sent from server to client) is the right transport. A new RPC would require the server to know about menu music (which it doesn't, because that's client-only state).

## Verification

The regression-pin test at
`server/src/test/kotlin/org/ttt/autogenesis/server/audio/AudioManagerSyncStateOnRestoreTest.kt`
verifies that `sendInitialSync` broadcasts `audio.syncState` with the
correct payload shape (track id + resourceName preserved through the
sync, empty scheduledObjects on fresh-DS resume).

If a future session proposes adding a `musicState` field to
`GameSnapshot` for "music restoration," point them at this reference
and the "What NOT to add" section above.