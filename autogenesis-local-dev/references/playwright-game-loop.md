# Playwright Probe Recipes — Autogenesis Game-Loop Automation

This reference covers driving the full game loop (login → commander
selection → wizard → multi-turn gameplay) from Playwright. It is a
companion to the SKILL.md `autogenesis-local-dev` entry that introduced
the four class-level lessons summarized here.

## When to use these recipes

Use the patterns below whenever you need to script end-to-end behavior
in the game UI beyond simple element screenshots — i.e. anything that
involves driving the game state forward, sending commands, or waiting
for AI response cycles.

For pure visual capture (screenshots of stable UI states), use
`references/screenshot-capture.md` instead — it has the simpler
"navigate + screenshot" pattern.

## Selector map (verified 2026-07-14)

| Element | Selector | Notes |
|---|---|---|
| LoadingScreen CTA | `data-testid="loading-screen-cta"` | Click to advance past loading |
| Login As Guest button | `data-testid="login-as-guest"` | Real AccelByte OAuth — not synthetic skipLogin |
| MainMenu root | `data-testid="main-menu"` | Has `data-accelbyte-user-id`, `data-accelbyte-display-name` |
| MainMenu PLAY button | `.btn.btn-play` | Inside MainMenu root |
| MessageBox overlay | `.autogenesis-message-box-overlay` | Class-based, NOT a KVision `Modal` |
| MessageBox OK button | `.autogenesis-message-box-overlay button.btn-secondary-action:has-text("OK")` | Force-clickable through the overlay |
| ResumeOrNewDialog root | `data-testid="resume-or-new-dialog"` | Matches commander-selection-overlay + dialog class |
| ResumeOrNewDialog "New Game" | `button:has-text("New Game")` | NOT generic OK |
| ResumeOrNewDialog "Resume" | `button:has-text("Resume")` | |
| CommanderSelectionDialog root | `data-testid="commander-selection-root"` | |
| Commander card | `.commander-selection-card:has-text("Lord Maple Tree")` | Substring match on commander name |
| Next button (wizard step 1) | `.commander-selection-window button:has-text("Next")` | Disabled until commander selected |
| Game type card (Single Player) | `.commander-selection-card:has-text("Single Player")` | Default selected |
| Opponent card "1 vs 1: Duel" | `.commander-selection-card:has-text("1 vs 1: Duel")` | 2 players (1 human + 1 AI) |
| Play button (wizard step 2) | `.commander-selection-window button:has-text("Play")` | Replaces Next after step 2 |
| gameplay-ui root | `data-testid="gameplay-ui"` | Mounted after Play clicked |
| CommandBox textarea | `textarea[placeholder*="action you want"]` | 500-char limit |
| CommandBox Send button | `button.btn-play:has-text("Send")` | Title-case `Send`, NOT `SEND` |
| Your Turn To Act text | `'Your Turn To Act'` text in gameplay-ui innerText | Polled for AI cycle completion |

## Lesson 1 — Overlay-race dismissal

The "Match Ready" message box (`.autogenesis-message-box-overlay`) is
mounted AFTER `[data-testid="gameplay-ui"]` becomes visible. A
single-shot `dismissMessageBox()` after the `gameplay-ui` wait is racy
and will often let the probe click through the textarea only to find
the overlay still intercepting pointer events.

**Wrong pattern** (race-condition):

```javascript
await page.locator('[data-testid="gameplay-ui"]').waitFor({ state: 'visible' })
await dismissMessageBox()  // count()==0 here, breaks early
await page.waitForTimeout(3000)
// later: <div class="autogenesis-message-box-overlay"> intercepts pointer events
```

**Right pattern** (polling loop):

```javascript
async function dismissAllOverlays(timeoutMs = 60_000) {
    const deadline = Date.now() + timeoutMs
    let dismissed = 0
    while (Date.now() < deadline) {
        const overlays = page.locator('.autogenesis-message-box-overlay')
        const count = await overlays.count()
        if (count === 0) return dismissed
        for (let i = 0; i < count; i++) {
            const ok = overlays.nth(i)
                .locator('button.btn-secondary-action:has-text("OK")').first()
            if (await ok.count() > 0) {
                try { await ok.click({ force: true, timeout: 2_000 }); dismissed++ } catch {}
            }
        }
        await page.waitForTimeout(500)
    }
    return dismissed
}

// After gameplay-ui mounts:
const d = await dismissAllOverlays(60_000)
// d tells you how many "Match Ready" / similar dialogs were dismissed
```

`force: true` is critical — the overlay sits above the textarea, so a
non-forced click on the OK button can be intercepted by intermediate
siblings. The polling loop catches dialogs that mount late.

## Lesson 2 — Multi-action turns ("N rounds" ≠ N cycles)

The Autogenesis orchestrator at `server/src/main/kotlin/agent/`
processes ONE player action per turn, then the AI player responds,
then Turn 2 opens. When you send multiple player commands back-to-back,
they all get consolidated into Turn 1 (the orchestrator uses the most
recent command for that turn).

User vocabulary mapping:

| User says | Means | Implementation |
|---|---|---|
| "Play N rounds" | Send N commands | Send commands with short pauses between; same turn resolves |
| "Play N full cycles" | Send command → wait AI → send next → wait AI … | Use the AI polling loop below |
| "Play through N turns" | Same as "full cycles" | |
| "Play until turn X" | Wait for "Turn X for Lord Maple Tree" sidebar entry | Poll DOM text |

**Default interpretation**: when the user says "N rounds", assume
N commands. If they explicitly say "cycles" or "wait for AI between",
use the polling pattern.

When in doubt: ask one focused clarification. Most users mean commands
when they say "rounds" in this game's vocabulary.

## Lesson 3 — AI turn polling

Each AI turn runs Phase 1-12 of the orchestrator. Observed timings
from the 2026-07-14 Lord Maple Tree campaign:

- Phase 1-3 (intent + validation + targeting): 10-30s
- Phase 4-5 (counter-play + simulation): 30-60s
- Phase 6 (Writing — `WriterAgent`): 60-120s, generates 5000+ chars
- Phase 7 (Outcome Analysis — `ResourceUsageDetector` + `PassFail`): 30-60s
- Phase 8 (NPCs + World Updates — `identifyNewNPCPipe`): 30-60s
- Phase 9 (Lorebook extraction): 10-20s
- Phase 10-12 (Counter / Judgement / Commit): 60-180s
- AI PlayerAgent then takes its OWN turn: 60-180s

**Total AI cycle: 3-10 minutes per player action**. First cycle is often
slowest (cold LLM context). Use `AUTOGENESIS_SHUTDOWN_DELAY_MS=1800000`
(30 min) on `:server:run` for any probe with 2+ cycles.

**Right pattern** (poll for "Your Turn To Act"):

```javascript
async function waitForYourTurn(maxMs = 360_000) {
    const deadline = Date.now() + maxMs
    while (Date.now() < deadline) {
        const txt = await page.evaluate(() =>
            document.querySelector('[data-testid="gameplay-ui"]')?.innerText || '')
        if (txt.includes('Your Turn To Act')) return true
        await dismissAllOverlays(2_000)
        await page.waitForTimeout(5_000)
    }
    return false
}
```

`waitForYourTurn(360_000)` gives 6 minutes per cycle, which covers most
cases. Increase to `600_000` (10 min) for the first cycle of a session.

## Lesson 4 — Reuse existing probes

Two battle-tested probes already exist:

- **`kvisionApp-e2e/probes/guest-login.mjs`** — drives Path B
  (Login As Guest → real AccelByte OAuth → MainMenu) and asserts the
  real accelbyteId (`004c3eb02c0b4436b41b24d5d670b0e4` for
  KingCandy13) is bound, not the synthetic `guest-user` placeholder.

- **`kvisionApp-e2e/probes/commander-create-mr-tree.mjs`** — creates
  the Lord Maple Tree commander with full 4-paragraph syrup manifesto,
  verifies it's listed in the Collection overlay.

For new game-loop probes, copy/paste the selector + login bootstrap
from `guest-login.mjs` and the commander-creation step only if your
selected commander isn't already in the KingCandy13 account.

## Lord Maple Tree persona probe pattern (worked example)

Verbatim from the 2026-07-14 campaign — see
`kvisionApp-e2e/probes/lord-maple-final2.mjs` for the full
implementation. The skeleton:

```javascript
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const ARTIFACT_DIR = join(__dirname, 'artifacts-lord-maple-...')
await mkdir(ARTIFACT_DIR, { recursive: true })

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await context.newPage()

// 1. Login (delegate to guest-login.mjs's selectors)
await page.goto('http://127.0.0.1:8080/index.html')
await page.getByTestId('loading-screen-cta').click()
await page.getByRole('button', { name: /^OK$/ }).catch(() => {}) // first messageBox
await page.getByTestId('login-as-guest').click()

// 2. Wait for MainMenu
const playButton = page.locator('.btn.btn-play')
while (Date.now() < Date.now() + 60_000) {
    if (await playButton.count() > 0) break
    await dismissAllOverlays(2_000)
    await page.waitForTimeout(300)
}
await playButton.first().click()

// 3. Handle resume dialog OR commander selection
const resumeDialog = page.locator('[data-testid="resume-or-new-dialog"]')
if (await resumeDialog.count() > 0) {
    await page.locator('button:has-text("Resume")').first().click()
} else {
    await page.locator('.commander-selection-card:has-text("Lord Maple Tree")').first().click()
    await page.waitForTimeout(300)
    await page.locator('.commander-selection-window button:has-text("Next")').first().click()
    await page.waitForTimeout(500)
    await page.locator('.commander-selection-card:has-text("1 vs 1: Duel")').first().click()
    await page.waitForTimeout(300)
    await page.locator('.commander-selection-window button:has-text("Play")').first().click()
}

// 4. Wait for gameplay-ui + dismiss ALL dialogs (overlay-race pattern)
await page.locator('[data-testid="gameplay-ui"]').waitFor({ state: 'visible' })
await dismissAllOverlays(60_000)

// 5. Per-round: send command, wait for AI, screenshot
const commands = ['Lord Maple Tree, Emperor of All Canada, declares...', ...]
for (let round = 1; round <= 3; round++) {
    const ta = page.locator('textarea[placeholder*="action you want"]').first()
    await ta.click({ force: true })
    await ta.fill(commands[round - 1])
    const sendBtn = page.locator('button.btn-play:has-text("Send")').first()
    await sendBtn.click({ force: true })

    const resolved = await waitForYourTurn(360_000)
    if (resolved) {
        // Capture Details tab for narrative
        await page.locator('button:has-text("Details")').first().click()
        await page.waitForTimeout(2000)
        await writeFile(join(ARTIFACT_DIR, `R${round}-details.png`),
            await page.screenshot({ fullPage: true }))
    }
}
```

## Cross-environment gotcha — /tmp probe scripts

When writing ad-hoc verification scripts under `/tmp/` (per the
`hermes-verify-YYYYMMDD.mjs` convention), the script's location has no
`package.json`, so ESM bare-specifier imports like
`import { chromium } from '@playwright/test'` fail with
`ERR_MODULE_NOT_FOUND`. Use absolute file-URL import instead:

```javascript
// In /tmp/hermes-verify-*.mjs
const PW_PATH = '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/@playwright/test/index.mjs'
const { chromium } = await import(PW_PATH)
```

The same pattern works for any package the probe needs — just point
to the absolute path under
`<project>/kvisionApp-e2e/node_modules/<pkg>/index.mjs`. ESM module
resolution treats file URLs as valid import targets.

A simpler-looking-but-broken alternative is `cd` + `node /tmp/foo.mjs`:
that works only if the user's shell happens to launch with cwd inside
the project's `node_modules` resolution path. Brittle — always use the
absolute import for `hermes-verify-*` scripts.

## Sub-pitfalls captured during the 2026-07-14 session

### Trailing single-quote after closing `).` — syntax error

A single-quoted JS string literal followed by `).` is easy to mis-key
when porting probe code from one context to another. Writing:

```javascript
console.log('  the gameplay session produced real artifacts (see screenshots').')
```

…makes the line end with `').` — a stray single quote AFTER the close
paren + period. Node reports `Invalid or unexpected token` and points
at the trailing `)`. The fix is either:
- Drop the trailing quote (string ends before `.`, period is statement
  punctuation outside the string), or
- Move the period INSIDE the quote (`'artifacts (see screenshots).'`)

The first form is what shows in this file's section above. Mistake
happened once in this session's `hermes-verify-lord-maple-probes-20260714.mjs`
(initial draft) and was caught on `node --check` immediately.

### Stale `notify_on_complete=true` notifications

When you launch a probe via:

```bash
node /home/cage/Desktop/.../lord-maple-final2.mjs 2>&1 | tee /tmp/log/gameplay/09-final2.log
```

…the `terminal(background=true, notify_on_complete=true)` call fires
when the **parent pipeline** (node + tee) exits. The notification
arrives sometimes minutes or hours after the actual node process has
already finished doing useful work. Don't treat the exit notification
as a "real-time" signal — verify process liveness via:

```bash
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080|9091|9092)" | sort -k4
ps -p <PIDs> -o pid,etime,comm
```

…before assuming the runtime is still alive. Multiple completion
notifications during a single gameplay session (one per backgrounded
probe) all arrive as "completed normally (exit code 0)" regardless of
whether the underlying JVMs are still serving. Always cross-check
ports/PIDs.

### 2026-07-14 `start_servers.sh` permission gotcha

The launcher script at `debugger/scripts/start_servers.sh` arrived
without executable bit (fresh checkout state); running it directly
prints `bash: ...start_servers.sh: Permission denied` and exits code 0
without launching anything. Bake `chmod +x` into the launch wrapper:

```bash
chmod +x /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh \
  && AUTOGENESIS_SHUTDOWN_DELAY_MS=1800000 \
     /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh \
     2>&1 | tee /tmp/log/boot.log
```

Quick pre-flight:

```bash
test -x /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh \
  || echo "need chmod +x on start_servers.sh"
```

## Receipts

- 2026-07-14 Lord Maple Tree campaign probes:
  `kvisionApp-e2e/probes/lord-maple-{3rounds,3rounds-v2,game,watch,deep-dive,final2}.mjs`
- Artifact directories:
  `kvisionApp-e2e/probes/artifacts-lord-maple-{3rounds-v2,watch,final2}/`
- Server-side narrative trace:
  `/home/cage/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/`

## Related references

- `references/screenshot-capture.md` — pure-visual capture recipe
- `references/process-kill.md` — graceful shutdown sequence
- `references/server-architecture.md` — RPC layer detail
