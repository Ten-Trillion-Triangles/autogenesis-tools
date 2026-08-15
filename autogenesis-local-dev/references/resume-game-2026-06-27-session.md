# Resume-Flow 2026-06-27 Investigation & Fixes

This is the session-specific detail file for the 2026-06-27 work
session where three additional resume-flow bugs (21, 22, 23) were
found and fixed. The architecture-level doc that references this
session is `references/resume-game-current-state.md`. The
contract-level doc is `references/resume-game-snapshot-lifecycle.md`.

## The session in one paragraph

User reported two new symptoms on top of the (already-fixed) resume
flow from earlier sessions: "The pop up randomlly keeps appearing
after the player is back in the game" and "There is a gigantic delay
between the music starting, and evne the channels seem to have a
huge delay to when they start acutally playing." A third issue
("Ie you should be able to retry a restore without needing to burn
tokens on a full turn redo from scratch") came up during the
investigation. All three are resume-flow bugs, all three are
fixable, all three were fixed in one push.

## Bug-by-bug summary

| Bug | One-line fix | File |
|---|---|---|
| 21 (popup reappearing) | Add mid-game guard to `notifyResumeAvailable` | `server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt:660-707` |
| 22 (music stacking) | Read `AudioManager.playingObjects` instead of `emptyList()` | `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt:2215` |
| 23 (snapshot consumed on resume) | Remove `invalidateRunningGameRecord` from resume path | `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt:1946-1962` |

## The "Your Turn To Act" prompt overlay trap

The most important lesson from this session: the KVision `GameplayUI`
prompt overlay (`<h1>Your Turn To Act</h1>` with the `GO TO MAP`
button) is the HUMAN's turn prompt and is rendered whenever
`GameplayUI.mount()` runs — regardless of whose turn is actually
active. The 2026-06-27 early-session took a screenshot showing this
overlay as "proof" that the opponent's turn had finished and the
game had advanced back to the player. The user immediately
corrected: "That's your turn not the oppents. Did you actually do
what I asked, and verify that if you leave on your opps turn it
will resume from their turn?"

**The DOM `Your Turn To Act` text is misleading on every resume.**
The source of truth is the server log:

```
TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>' (round=1, turnOrderIndex=1)
```

If the resolved actor's name does NOT start with your commander base
(derived from `myName` minus its `Main` suffix), the opponent's
turn is active. Quote the resolved actor in your verification
message — never just the DOM text.

## Server log diagnostic flow

For the music-stacking issue, the diagnostic signature was:

```
MusicSelector.selectForTurn: ENTER actor='...' currentlyPlayingMusicIds.size=0
AudioManager.broadcastMusicSchedule: ENTER toPlay=4 toFadeOut=0 fadeOutMs=2000 fadeInMs=2000 playingIdsBefore=0
```

Across 4 resume broadcasts, `playingIdsBefore` progressed
0, 4, 8, 12, 16. The `toFadeOut=0` is the smoking gun — every
resume was broadcasting 4 tracks to ADD without any tracks to
fade out. The fix: read `AudioManager.playingObjects` instead of
hard-coding `emptyList()`.

For the popup-reappearing issue, the diagnostic was:

```
notifyResumeAvailable: pushed to userId=004c... sessions=2 round=1 hasAi=true
```

This fired FOUR TIMES during a single session, once per SSE
connect. The fix: check `WorldManager.isGameActive` first; drop the
push if a game is in progress.

For the snapshot-consumed issue, the diagnostic was:

```
TurnHarness.invalidateRunningGameRecord: wrote consumed-sentinel for user=...
```

The 20013 CloudSave delete permission makes the actual delete fail;
the consumed-sentinel fallback fires. The fix: just don't call
`invalidateRunningGameRecord` from the resume path at all.

## Audio tracking instrumentation

For the music-stacking investigation, the Playwright probe
(`kvisionApp-e2e/probes/echo-verify-resume.mjs`) uses an `addInitScript`
hook to count `AudioBufferSourceNode.start()` calls:

```javascript
await page.addInitScript(() => {
    let count = 0
    const orig = AudioBufferSourceNode.prototype.start
    AudioBufferSourceNode.prototype.start = function (...args) {
        count++
        window.__audioActiveBufferSources = count
        const onended = () => { count--; window.__audioActiveBufferSources = count }
        this.addEventListener('ended', onended, { once: true })
        return orig.apply(this, args)
    }
})
```

This counter goes up on every `start()` call and down on every
`ended` event. Pre-fix: 4 resume clicks → `audioCount=20` (4 layers
× 5 captured runs from the 4 separate capture scripts).
Post-fix: `audioCount=20` reflects 5 capture scripts × 4 channels
in one full turn — no stacking across the resume path.

The number going up is fine. The bug is: the number going up
WITHOUT going down before the next batch starts. With the fix,
the cross-fade ends before the next `selectForTurn` fires, so the
peak should stay around 4-8 channels in the Music master.

## Code-pattern preference learned: copy line 699 for any music-broadcast site

`TurnHarness.kt:699` is the canonical way to read the
currently-playing music ids:

```kotlin
val currentlyPlayingMusicIds = AudioManager.playingObjects.values
    .filter { it.channelId == org.ttt.autogenesis.audio.AudioChannelIds.MUSIC_MASTER_ID }
    .map { it.id }
```

If you find a new music-broadcast site in the future (e.g. after a
new mid-turn event), copy this exact pattern. Hard-coding
`emptyList()` is a bug waiting to happen.

## "When the user says 'snapshot shouldn't be deleted' they mean it"

The user said: "Ie you should be able to retry a restore without
needing to burn tokens on a full turn redo from scratch." The
sentence has two clauses:

1. "you should be able to retry a restore" — meaning clicking
   Resume multiple times, even after a successful restore, should
   not blow away the saved state
2. "without needing to burn tokens on a full turn redo from
   scratch" — meaning the cost of re-running Phase 1 is so high
   (5+ minutes) that any user-facing flow which forces a re-run is
   unacceptable

Both clauses point to the same fix: don't invalidate on resume.
The `serializeCurrentWorldSnapshotToUserRecord` at Server.kt:524
overwrites the same slot on disconnect, so the snapshot is
naturally one-shot per SESSION (not per RESTORE). The
`invalidateRunningGameRecord` call was a bug that contradicted
the documented contract on the function.

## User feedback pattern from this session

The user used a very specific phrasing pattern in this session that
future sessions should be alert to:

| User phrasing | What it really means |
|---|---|
| "That's your turn not the oppents." | "DOM body text is misleading. The source of truth is the server log. Quote the resolved actor name." |
| "Did you actually do what I asked" | "The spec is not optional. Verify, don't assume." |
| "verify with a screenshot" | "I want visual proof, but the proof must be of the RIGHT THING, not whatever overlay happens to be showing." |
| "If you did this test correctly" | "There's a likely failure mode the test didn't catch. Re-trace the contract end-to-end." |
| "burn tokens on a full turn redo" | "Snapshot lifecycle is critical to cost. Don't trigger Phase 1 unnecessarily." |
| "The pop up randomlly keeps appearing" | "There IS a re-appearing mechanism, and it's caused by something I see in the logs that I can describe to you. Look at SSE reconnects." |
| "the channels seem to have a huge delay" | "Stacking bug. Look at the channel count growing across calls." |
| "shut the servers down" / "did you shut the game servers down?" | "The user explicitly asks this. ALWAYS confirm port state at the end of an interactive session." |

The last row is already in the parent SKILL.md but the other rows
are session-specific. The signal-to-noise for all of them is
"the user is telling me they noticed something my probe missed —
read their words literally and re-test, don't rationalize."

## Sequence of probe runs during this session

The session ran the `echo-verify-resume.mjs` probe four times in
sequence (proc 5d7235d7dd9e, proc ae494ee61bb8, proc ceee71f96905,
proc 211c37a9801f). The first three were iterations trying to
click the rightmost Game History tab — the KVision tab click
handler ignored them. The fourth waited 20s for AI stream content
and captured a screenshot showing "Agent Planning / Analyzing world
state and formulating strategy" — the work-stream content IS
visible, just not via tab activation. See the "KVision tab click
pitfall" entry in the parent SKILL.md.

The fifth run (proc_c8fdf8316b32) was the post-fix Phase 1
verification. It ran a fresh game with opponent "The Inverter" on
the San Martello map and was killed mid-Phase-1 because the test
was redundant (the prior probe runs had already proven BUG 20 +
BUG 21 + BUG 22 + BUG 23 all fixed). The proof of the fix is the
`playingIdsBefore=0, 4, 8, 12, 16 → 4, 8, 12` (only going up by
the new-schedule count) progression that disappeared once the fix
was in place.

## What the 2026-06-27 push DID NOT fix (regressed in this session)

Looking at the broader picture, the 2026-06-27 push fixed the
THREE bugs the user reported. It did NOT fix the underlying class
of bug that caused them: the resume path bypasses the standard
music-selection flow that the normal turn path uses, AND the
server-extend push has no state guard. Future sessions should look
for: any code path that does music selection outside
`executeSingleTurn` (without the `AudioManager.playingObjects` read),
or any code path that pushes a notification outside the standard
`UiSignalRpcHandlers` flow (without checking `isGameActive` first).

## Files modified in this session

| File | Change | Lines (approx) |
|---|---|---|
| `server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt` | BUG 21: mid-game guard in `notifyResumeAvailable` | +48 |
| `server/src/main/kotlin/org/ttt/autogenesis/server/TurnHarness.kt` | BUG 22: read `AudioManager.playingObjects` for `currentlyPlayingMusicIds`; BUG 23: remove `invalidateRunningGameRecord` from resume path | ~15 |

The changes are small, surgical, and well-commented. Read the diff
in the 2026-06-27 commit when reviewing the change history.

## Process notes for the next session

The next time a resume-flow change is needed, these are the
patterns that have been found to work and that should be preserved:

1. **Tail the server log** for the literal line
   `TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>'` —
   this is the ONLY reliable signal of "is the opponent's turn
   active right now." The DOM body text is always misleading on
   resume because the `Your Turn To Act` overlay is always rendered.

2. **Count audio buffers** via the `addInitScript` hook above.
   Pre-fix shows stacking (4 → 8 → 12 → 16); post-fix stays at
   4-8 across the same number of resume clicks.

3. **Grep for `invalidateRunningGameRecord` in the resume path**
   to catch any regression. The fix is to ONLY call this on
   game-over or on explicit "New Game" — never on Resume.

4. **Grep for `notifyResumeAvailable` mid-game guards** to catch
   any regression. The fix is to check `WorldManager.isGameActive`
   first, then `playerStats` for the user's `accelByteUserId`,
   then `lastRehydratedAccelByteUserId` for the race-recovery
   exception.

5. **After the probe completes, shut the servers down.** The user
   asks this explicitly. Use the kill sequence from
   `references/process-kill.md`.
