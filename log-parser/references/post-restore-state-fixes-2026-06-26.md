# Post-Restore State Hydration — BUG 22/23/24 (2026-06-26 22:12 session)

This is a companion to `autogenesis-bug-investigation.md` covering the third
regression family found on the same `applyGameSnapshot` restore path that
shipped BUG 15/19/20/21 in earlier rounds. The pattern is:

> `applyGameSnapshot` is a state-RESTORE funnel, not a state-INITIALIZE funnel.
> Anything that lives inside `executeSingleTurn` / `awaitPlayerAction` and
> establishes transient runtime state (music, timer, AI/human identity for
> the live session, etc.) is missed on restore.

## Bug inventory additions

| BUG | Title | Status | Plan | Probe |
|---|---|---|---|---|
| 22 | Music silent on restore until first action | FIXED 2026-06-26 | `.hermes/plans/reload-post-restore-state-2026-06-26.md` | `kvisionApp-e2e/probes/music-timer-restore.mjs` Phase A |
| 23 | Human treated as AI-controlled NPC on restore | FIXED 2026-06-26 | `.hermes/plans/reload-post-restore-state-2026-06-26.md` | `kvisionApp-e2e/probes/music-timer-restore.mjs` Phase C |
| 24 | Turn timer not armed on restore | FIXED 2026-06-26 | `.hermes/plans/reload-post-restore-state-2026-06-26.md` | `kvisionApp-e2e/probes/music-timer-restore.mjs` Phase B |

## Diagnostic patterns (copy-paste grep recipes)

```bash
# BUG 22 — music missing on restore (look for gap between rehydrate and first music broadcast)
LOG=~/.autogenesis/logs/autogenesis-$(date +%Y-%m-%d)-*.log
grep -n "Rehydrated running-game snapshot\|MusicSelector.selectForTurn: rule .* fired\|Music schedule broadcast" "$LOG" | head -10

# BUG 23 — user marked as NPC post-rehydrate
grep -n "Identified connection .* (isNpc=true)" "$LOG" | grep -A0 -B0 "Rehydrated" || \
  grep -n "Rehydrated running-game\|Identified connection .* (isNpc" "$LOG" | head -10

# BUG 24 — turn start broadcast without timer arm
grep -n "Rehydrated running-game\|broadcasting active turn actor\|Starting turn timer" "$LOG" | head -10
```

## Why these three are a single class

All three are symptoms of the same architectural gap: `TurnHarness.applyGameSnapshot`
restores durable state, but the runtime side-effects that `executeSingleTurn`
would normally trigger are not invoked. The fix shape for the entire family is
"re-run per-turn setup using the snapshot's frozen turn state as the input"
instead of the live state.

| Symptom | Per-turn setup call that was missed | Same call works for restore? |
|---|---|---|
| Music silent | `TurnHarness.selectAndBroadcastMusicForTurn(actor)` (TurnHarness.kt:662) | YES — pass the snapshot's frozen actor + isFirstTurn |
| Human treated as AI | `applyGameSnapshot` remap loop writes playerID/isConnected | PARTIAL — needs to also write `isControlledByNpc=false` on the remap target |
| Timer not armed | `WorldManager.startTurnTimer` (TurnHarness.kt:610) | YES — but only if the snapshot's `turnOrder[turnOrderIndex]` is the human; otherwise the saved NPC turn is up and the timer should not arm |

## Files touched in the fix

| File | Change |
|---|---|
| `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt` | `applyGameSnapshot` flips `isControlledByNpc=false` on remap target. `restoreWorldFromUserRecord` arms timer when human was active + calls new `rehydrateMusicForSnapshot` after apply. |
| `server/src/test/kotlin/.../TurnHarnessRunningGameTest.kt` | New tests: `applyGameSnapshot flips isControlledByNpc to false on the human remap target`, `restoreWorldFromUserRecord arms turn timer when human was active`, `restoreWorldFromUserRecord schedules initialConditions music on round-1 restore`, etc. |
| `kvisionApp-e2e/probes/music-timer-restore.mjs` (new) | Phase A (music mount), Phase B (timer visible), Phase C (no AI takeover), Phase D (action routes to executePlayerTurn not AI) |

## Out of scope (deliberately deferred)

- Capturing MusicDecision in `GameSnapshot` — the user (this session)
  chose to re-run `MusicSelector.selectForTurn` with `isFirstTurn=true` for
  round-1 restores because the snapshot doesn't capture music and replaying
  the rule-1 bucket is correct UX for any round-1 reload. Faithful replay
  for round > 1 would need the snapshot schema extension; that was discussed
  and deferred because the rule-1 fallback is the most common case and the
  schema change is invasive.
- Refactoring all per-turn setup into a single `rehydratePostRestoreState`
  funnel — this would be cleaner than scattering setup calls across
  `restoreWorldFromUserRecord`, but the user accepted the immediate-scatter
  fix in this session because the call sites are small (one timer arm, one
  music broadcast, one isControlledByNpc flip) and auditing them is easy.
  If a BUG 25 surfaces in this area, the right move is to consolidate.

  **Update 2026-06-27:** BUG 25 was discovered — but it's NOT in the restore
  path. BUG 25 is the **save-side** complement: `Server.kt:558` persists
  on disconnect when `isGameActive=true`, which is true the moment GameInit
  finishes. The save captures an empty fresh-init world because the human
  WS hasn't connected yet (only the `server-extend-client` CONTROLLER
  bridge disconnected). So even after BUG 22/23/24 fire perfectly, the
  state being rehydrated can still be empty — because the state that was
  saved was empty.

  Full BUG 25 write-up: `autogenesis-bug-investigation.md` § BUG 25. The
  companion lesson is: when fixing "the world looks wrong on restore,"
  check both the **restore gate** (does the rehydrate path re-establish
  transient state?) and the **save gate** (was what got saved actually
  interesting?). Fixing only one side leaves the other bug masking
  improvements.

  Recommended consolidation if the team chooses to ship both fixes: extract
  a `WorldManager.hasHumanPlayerPlayedAtLeastOneTurn: Boolean` (set inside
  `executeSingleTurn` after the first player action commits), gate
  `Server.kt:558` on it, and route BUG 22/23/24 fixes through a single
  `TurnHarness.rehydratePostRestoreState(snapshot, accelByteUserId)` funnel
  called from `restoreWorldFromUserRecord`. The "interesting-state" semantic
  lives in one place (`WorldManager`); the "post-restore setup" semantic
  lives in another (`TurnHarness`). Both should be reviewed together when
  either changes.

## Related

- BUG 15: server-side auto-restore vs Resume click race (FIXED 2026-06-22)
- BUG 19: `applyGameSnapshot` playerID remap missing (FIXED 2026-06-26)
- BUG 20: auto-restore IO-launch race, initial sync never sent (FIXED 2026-06-26)
- BUG 21: round-1 race-recovery short-circuit (FIXED 2026-06-26)

All five fixes (15/19/20/21/22/23/24) live on the same `applyGameSnapshot`
restore path. The pattern is now well-mapped: any future post-restore UX
regression should be investigated by asking "what setup call inside
`executeSingleTurn` was not re-invoked?"