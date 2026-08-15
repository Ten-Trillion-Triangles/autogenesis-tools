# Opponent Turn Detection in Resume-Flow Probes

**Problem:** The Autogenesis resume-flow test (per the user's 2026-06-25
contract) requires closing the browser during the *opponent's* turn so
the persisted snapshot's `turnIndex` reflects the opponent's turn
position. The probe then restarts servers + re-logs in, the user clicks
Resume, and the server rehydrates the game at the opponent's turn
position — proving the snapshot captured the correct mid-game state.

**Why DOM detection is unreliable:** A probe that watches for the
opponent's turn via the body text (looking for `Active actor:` name or
`Opponent's Turn` / `Your Turn To Act` / `AI is thinking`) will close
the browser at the wrong moment because:

1. The body text contains **stale narrative from the prior turn**
   ("AUongfa834nfa steps into the Communal Shower Rooms..." — this is
   the writing-agent's narrative, still in the DOM after the page
   re-renders during the opponent's turn).
2. The `Active actor:` text **persists across turns** because the body
   is re-rendered with chunked frames, not atomically — the `Active actor:`
   field shows the previous turn's actor for several seconds after the
   opponent's turn index advances.
3. `Your Turn To Act` is the **HUMAN's prompt**, not the AI's turn.
   Seeing it in the body during a probe means the game is asking the
   human to act, not that the opponent is processing.
4. The chunked-frame pipeline (loadMapPack ~8MB / 282 chunks, updateWorld
   ~110KB / 4 chunks) re-renders state asynchronously, so any DOM
   signal lags the server by 5-30 seconds.

**The reliable signal: server log `markTurnAsProcessed`.** When the
turn harness advances the turn index and starts the next player, it
emits a log line at `INFO` level:

```
TurnHarness.markTurnAsProcessed: Marked '<commanderName>-<round>-<turnIndex>' as processed (total processed: N)
```

`turnIndex` is `0` for the first player in turn order, `1` for the
second, etc. The `<commanderName>` is the in-game commander name (NOT
the WS playerId). For AUongfa834nfa vs Pissy Will, you would see:
- `Marked 'AUongfa834nfa-1-0' as processed` — MY turn was completed
- `Marked 'Pissy Will-1-1' as processed` — OPPONENT's turn was started

**Detection pattern (ESM-compatible):**

```javascript
// Derive your commander base from the probe's myName (which has 'Main' suffix
// like 'AUongfa834nfaMain'). The turnKey format is '<commanderName>-<round>-<turnIdx>'.
const myCommanderBase = myName.endsWith('Main') ? myName.slice(0, -4) : myName

// ESM-friendly fs import (require() doesn't work in .mjs)
const { statSync: stat, openSync: openF, readSync: readF, closeSync: closeF } = await import('fs')

let logOffset = 0  // track position across iterations
for (let i = 0; i < 720; i++) {
    if (!turnIndexAdvanced) {
        try {
            const currentLogSize = stat('/tmp/autogenesis-proxy/srv.log').size
            if (currentLogSize > logOffset) {
                const fd = openF('/tmp/autogenesis-proxy/srv.log', 'r')
                const buf = Buffer.alloc(currentLogSize - logOffset)
                readF(fd, buf, 0, buf.length, logOffset)
                closeF(fd)
                logOffset = currentLogSize
                const newContent = buf.toString('utf8')
                const processedMatches = newContent.match(/Marked '([^']+)' as processed/g) || []
                for (const m of processedMatches) {
                    const turnKey = m.match(/Marked '([^']+)'/)[1]
                    if (!turnKey.startsWith(myCommanderBase + '-')) {
                        // Found a NON-mine turn processed = opponent's turn started
                        turnIndexAdvanced = true
                        break
                    }
                }
            }
        } catch (_) {}
    }
    if (turnIndexAdvanced) {
        // Now safe to close browser; snapshot will capture the opponent's turn state
        break
    }
    await page.waitForTimeout(1000)
}
```

**Worked example (2026-06-27 session):**

The first probe attempt used `state.activeActor !== myName` to detect the
opponent's turn, where `state.activeActor` was extracted from the
`Active actor:` regex match in the DOM. The probe closed the browser at
iter 665 (11:05 elapsed) when it saw `actor=InvisMain` in the body text,
BUT the actual server log shows the snapshot was persisted at
13:50:10 — DURING my turn's Phase 13 End of Turn Maintenance, before
the `Marked 'Invis-1-1' as processed` log line at 13:50:42 (32 seconds
later). On Phase 2, the server rehydrated with `turnIndex=0` (my turn)
and the UI showed "Your Turn To Act" — making the probe's
`yourTurn=true` check fail the test.

After fixing the probe to tail the server log, the second attempt waited
for `Marked 'Pissy Will-1-1' as processed (total processed: 2)` before
closing the browser at iter 487 (8:08 elapsed). The server snapshot
persisted captured the state AT the moment after the opponent's turn
index advanced. On Phase 2, the server rehydrated with
`turnIndex=1, historyEntries=1` — the opponent's turn position, which
the resume correctly rehydrated to.

**Pitfalls to avoid:**

1. **Don't use the simple `as processed (total processed: N)` substring
   match** — this matches BOTH your turn and the opponent's turn being
   processed. You need the commander name prefix check.
2. **Don't use `page.evaluate(() => document.body.textContent)` regex
   on `Active actor:` text** — the body re-renders asynchronously, the
   text persists across turns, and the narrative chunks include the
   character name.
3. **Don't rely on a single iteration** — the `markTurnAsProcessed`
   log line may take 5-15 minutes to appear (it's emitted at the end
   of the action pipeline after Phase 6 narrative + Phase 11 judgement
   + Phase 13 maintenance). The probe loop should run up to 720
   iterations (12 min) with 1-second sleep.
4. **Don't forget to track `logOffset` between iterations** — reading
   the full file every iteration is O(n) and will throttle your probe.
   The chunked-read pattern (`openSync` + `readSync` from offset +
   `logOffset += readSize`) keeps detection O(delta).
5. **Don't use `require('fs')`** — Node ESM modules don't expose
   `require()`. Use `await import('fs')` and destructure the methods
   you need. This bit the 2026-06-27 probe mid-test with
   `ReferenceError: require is not defined` and crashed the test.
6. **Don't use `myName` as the literal check** — `myName` has a
   `Main` suffix (e.g. `AUongfa834nfaMain`) that's not in the turn
   key. Strip the suffix to get the commander base, then check the
   turn key's prefix against `<commanderBase>-`.

**When to apply this pattern:**

- Any probe that needs to wait for a specific turn state
- Any probe that needs to close the browser mid-game and persist a
  snapshot at a precise turn boundary
- Any probe that needs to verify turn progression for a multi-player
  or single-player-vs-AI scenario
- Any test of the `markTurnAsProcessed` race-recovery logic in
  `TurnHarness.handlePostTurn`

**Related references:**

- `references/resume-game-snapshot-lifecycle.md` — the four trigger
  paths for snapshot save/invalidate
- `references/resume-game-current-state.md` — current state of the
  resume system
- `references/resume-game-e2e-flow.md` — the user's intended flow
  contract and all 7 race conditions found
- `references/probe-patterns.md` — reusable Playwright patterns for
  the kvisionApp-e2e probes
- `references/server-architecture.md` — full RPC layer detail
