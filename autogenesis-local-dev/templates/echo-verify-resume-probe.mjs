#!/usr/bin/env node
// kvisionApp-e2e/probes/echo-verify-resume.mjs
//
// Two-phase resume-flow verification probe for the Autogenesis KMP game.
// Pattern derived from the 2026-06-27 session: tests the full flow
// "play one turn → opponent's turn → close → restart → log in → Resume → verify".
//
// Usage:
//   cd kvisionApp-e2e
//   node probes/echo-verify-resume.mjs --phase=1    # play + close during opponent's turn
//   # ... kill all servers, restart, then:
//
//   node probes/echo-verify-resume.mjs --phase=2    # log in + click Resume + verify
//
// Critical pattern: phase 1 MUST wait for the server log
//   "Marked '<opponentName>-<round>-<oppIdx>' as processed"
// before closing the browser, NOT just the DOM `Active actor:` text.
// See references/resume-game-opponent-turn-detection.md for why.

import { chromium } from '@playwright/test'
import { writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BASE_URL = 'http://127.0.0.1:8080'
const ARTIFACT_DIR = join(__dirname, 'artifacts-echo-verify')
const SERVER_LOG = '/tmp/autogenesis-proxy/srv.log'

const PHASE_ARG = process.argv.find(a => a.startsWith('--phase='))
const PHASE = PHASE_ARG ? parseInt(PHASE_ARG.substring('--phase='.length), 10) : 1

const log = (s) => console.log(`[${new Date().toISOString().slice(11, 23)}] ${s}`)

async function dumpDomSnapshot(page, name) {
    try {
        const html = await page.content()
        const safeName = name.replace(/[^a-z0-9.-]+/gi, '_')
        const out = join(ARTIFACT_DIR, `${safeName}.html`)
        await writeFile(out, html, 'utf8')
        log(`  DOM snapshot: ${out} (${html.length} bytes)`)
    } catch (e) { log(`  failed DOM snapshot: ${e.message}`) }
}

async function dismissMessageBoxes(page, timeoutMs = 30000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
        const okByText = page.getByRole('button', { name: /^OK$/ })
        if (await okByText.count() > 0 && await okByText.first().isVisible()) {
            try { await okByText.first().click({ timeout: 2_000, force: true }) } catch (_) {}
        }
        await page.waitForTimeout(500)
    }
}

async function dismissResumeDialogs(page) {
    for (let i = 0; i < 5; i++) {
        const dialog = page.locator('[data-testid="resume-or-new-dialog"]')
        if (await dialog.count() > 0 && await dialog.first().isVisible()) {
            try {
                await page.locator('[data-testid="resume-or-new-dialog"] button:has-text("New Game")').first().click({ timeout: 2_000, force: true })
                await page.waitForTimeout(500)
            } catch (_) {}
        }
        await page.waitForTimeout(200)
    }
}

async function loginAsGuest(page, dismissPriorResume = true) {
    log('  navigating to index.html')
    await page.goto(`${BASE_URL}/index.html`)
    log('  waiting for loading-screen CTA')
    const cta = page.getByTestId('loading-screen-cta')
    await cta.waitFor({ state: 'visible', timeout: 30_000 })
    await cta.click()
    log('  waiting for LoginPage')
    await page.locator('.login-widget-window').waitFor({ state: 'visible', timeout: 30_000 })
    log('  clicking Login As Guest (real AccelByte OAuth flow)')
    const guestButton = page.getByTestId('login-as-guest')
        .or(page.getByRole('button', { name: 'Login As Guest' }))
    await guestButton.first().click()
    log('  dismissing post-login messageBox')
    await dismissMessageBoxes(page, 15000)
    log('  waiting for MainMenu')
    await page.locator('[data-testid="main-menu"]').waitFor({ state: 'visible', timeout: 30_000 })
    if (dismissPriorResume) {
        await dismissResumeDialogs(page)
    }
}

async function enterSinglePlayerGame(page) {
    log('  clicking PLAY')
    await page.locator('.btn.btn-play').waitFor({ state: 'visible', timeout: 30_000 })
    await page.locator('.btn.btn-play').click({ force: true, timeout: 10_000 })
    await dismissResumeDialogs(page)

    log('  waiting for commander selection dialog or direct GameplayUI')
    await page.waitForFunction(() => {
        const gp = document.querySelector('[data-testid="gameplay-ui"]')
        const cs = document.querySelector('.commander-selection-window')
        const cs2 = document.querySelector('[data-testid="commander-selection-dialog"]')
        const failedModal = document.body.textContent.includes('Matchmaking Failed')
        return !!gp || !!cs || !!cs2 || failedModal
    }, { timeout: 30_000 }).catch(e => log(`  waitForCommanderDialog: ${e.message}`))

    await dumpDomSnapshot(page, 'p1-commander-selection')

    log('  clicking existing commander AUongfa834nfa')
    const commanderRow = page.locator('text=/AUongfa834nfa/').first()
    if (await commanderRow.count() > 0 && await commanderRow.isVisible()) {
        await commanderRow.click({ timeout: 5_000, force: true })
        await page.waitForTimeout(300)
    } else {
        log('  WARNING: existing commander AUongfa834nfa not found in DOM')
    }

    log('  clicking Next (commander dialog step 1 -> 2)')
    const nextButton = page.getByRole('button', { name: /^Next$/ })
    if (await nextButton.count() > 0 && await nextButton.first().isVisible()) {
        try { await nextButton.first().click({ timeout: 5_000 }) } catch (e) { log(`  Next click failed: ${e.message}`) }
        await page.waitForTimeout(500)
    }

    log('  Step 2 is Single Player + 1 vs 1 Duel by default; clicking Play')
    const playButton = page.getByRole('button', { name: /^Play$/ })
    if (await playButton.count() > 0 && await playButton.first().isVisible()) {
        try { await playButton.first().click({ timeout: 5_000 }) } catch (e) { log(`  Play click failed: ${e.message}`) }
        await page.waitForTimeout(500)
    }
    await dumpDomSnapshot(page, 'p1-after-play-click')

    log('  waiting for matchmaking messageBox')
    await dismissMessageBoxes(page, 60000)
    log('  waiting for GameplayUI to mount')
    await page.waitForFunction(() => !!document.querySelector('[data-testid="gameplay-ui"]'), { timeout: 60_000 }).catch(e => log(`  waitForGameplay: ${e.message}`))
    if (await page.locator('[data-testid="gameplay-ui"]').count() === 0) {
        await dumpDomSnapshot(page, 'p1-no-gameplay')
        throw new Error('GameplayUI never mounted')
    }
}

// Capture audio + work stream + actor state. The "Your Turn To Act" prompt
// only matches the HUMAN's prompt (NOT the AI's turn), and the body text
// contains stale narrative from the prior turn. So this detection is
// a SOFT signal — the authoritative signal is the server log.
async function captureGameState(page, label) {
    const state = await page.evaluate(() => {
        const roundMatch = document.body.textContent.match(/Round:\s*(\d+)/)
        // "Your Turn To Act" only matches the PROMPT screen, not stale narrative text
        const yourTurnPrompt = /Your Turn To Act\s*Review the map/i.test(document.body.textContent)
        const opponentTurn = /Opponent's Turn|AI's Turn|AI is thinking|Opponent.*?turn|now playing|their turn/i.test(document.body.textContent)
        const m = document.body.textContent.match(/Active actor:\s*([A-Za-z0-9_]+)/)
        const activeActor = m ? m[1] : null
        const workStreamGlow = !!document.querySelector('.gh-tab-glow')
        const workStreamVisible = (() => {
            const ws = document.querySelector('[data-testid="agent-work-stream"], .agent-work-stream, [class*="work-stream"]')
            return ws && ws.offsetWidth > 0
        })()
        const audioCount = (window.__audioActiveBufferSources || 0)
        const audioContextState = (window.__audioContext && window.__audioContext.state) || 'unknown'
        const bodyTextSnippet = document.body.textContent.slice(0, 800)
        return {
            round: roundMatch ? parseInt(roundMatch[1], 10) : null,
            yourTurn: yourTurnPrompt,
            opponentTurn, activeActor, workStreamGlow, workStreamVisible,
            audioCount, audioContextState,
            bodyTextSnippet,
        }
    })
    log(`  state[${label}]: round=${state.round} yourTurn=${state.yourTurn} oppTurn=${state.opponentTurn} actor=${state.activeActor} wsGlow=${state.workStreamGlow} audio=${state.audioCount} ctxState=${state.audioContextState}`)
    return state
}

async function getMyCommanderName(page) {
    return await page.evaluate(() => {
        const m = document.body.textContent.match(/Active actor:\s*([A-Za-z0-9_]+)/)
        return m ? m[1] : null
    })
}

async function playFirstTurnAndWaitForOpponent(page) {
    log('  Step P1.6: wait 8s for game to settle')
    await page.waitForTimeout(8000)
    const myName = await getMyCommanderName(page)
    log(`  my commander name = ${myName}`)

    log('  Step P1.7: detect "Your Turn To Act" prompt')
    let found = false
    for (let i = 0; i < 60; i++) {
        const inputCount = await page.locator('textarea#kv_form_text_1').count()
        const bodyText = await page.evaluate(() => document.body.textContent)
        if (inputCount > 0 && /Your Turn To Act/i.test(bodyText)) {
            found = true
            log(`  Your Turn To Act at iteration ${i}`)
            break
        }
        await page.waitForTimeout(1000)
    }
    if (!found) throw new Error('Your Turn To Act never appeared')

    log('  Step P1.8: type a command and click Send')
    const cmdText = 'I move forward cautiously and scout the area.'
    const input = page.locator('textarea#kv_form_text_1').first()
    await input.click({ timeout: 5_000 })
    await input.fill(cmdText)
    await page.waitForTimeout(300)
    const sendBtn = page.getByRole('button', { name: /^Send$/ }).first()
    await sendBtn.click({ timeout: 3_000, force: true })
    log(`  clicked Send: "${cmdText}"`)

    log('  Step P1.9: wait for opponent turn (server log for opponent actor "as processed")')
    let oppTurnFound = false
    let turnIndexAdvanced = false
    const startWait = Date.now()
    let logOffset = 0
    const { statSync: stat, openSync: openF, readSync: readF, closeSync: closeF } = await import('fs')
    stat(SERVER_LOG).size
    for (let i = 0; i < 720; i++) {  // up to 12 minutes
        if (!turnIndexAdvanced) {
            try {
                const currentLogSize = stat(SERVER_LOG).size
                if (currentLogSize > logOffset) {
                    const fd = openF(SERVER_LOG, 'r')
                    const buf = Buffer.alloc(currentLogSize - logOffset)
                    readF(fd, buf, 0, buf.length, logOffset)
                    closeF(fd)
                    logOffset = currentLogSize
                    const newContent = buf.toString('utf8')
                    const processedMatches = newContent.match(/Marked '([^']+)' as processed/g) || []
                    for (const m of processedMatches) {
                        const turnKeyMatch = m.match(/Marked '([^']+)'/)
                        if (turnKeyMatch) {
                            const turnKey = turnKeyMatch[1]
                            const myCommanderBase = myName.endsWith('Main') ? myName.slice(0, -4) : myName
                            if (!turnKey.startsWith(myCommanderBase + '-')) {
                                turnIndexAdvanced = true
                                log(`  >>> server log: opponent turn ${turnKey} processed at ${(Date.now() - startWait) / 1000}s`)
                                break
                            }
                        }
                    }
                }
            } catch (_) {}
        }
        const state = await captureGameState(page, `wait-opp-${i}`)
        if (state.activeActor && myName && state.activeActor !== myName && turnIndexAdvanced) {
            oppTurnFound = true
            log(`  opponent turn detected at iter ${i} (${(Date.now() - startWait) / 1000}s elapsed): actor=${state.activeActor}`)
            break
        }
        if (i % 30 === 0 && i > 0) log(`  iter ${i} (${(Date.now() - startWait) / 1000}s): still waiting; turnIdxAdvanced=${turnIndexAdvanced}; current: ${JSON.stringify(state).slice(0, 200)}`)
        await page.waitForTimeout(1000)
    }
    if (!oppTurnFound) {
        log('  WARNING: opponent turn not detected in 12 minutes')
        log('  proceeding anyway — snapshot may be mid-turn')
        await dumpDomSnapshot(page, 'p1-no-opponent-turn')
    }

    log('  Step P1.10: verify music is playing (audioCount > 0)')
    const stateBeforeClose = await captureGameState(page, 'p1-end-before-close')
    if (stateBeforeClose.audioCount === 0) {
        log('  WARNING: audioCount is 0 — music may not be audibly playing')
    }
    return { state: stateBeforeClose, myName }
}

async function main() {
    if (PHASE === 1) {
        await runPhase1()
    } else if (PHASE === 2) {
        await runPhase2()
    } else {
        throw new Error(`Unknown phase ${PHASE}`)
    }
}

async function runPhase1() {
    log('==== PHASE 1: first session ====')
    const browser = await chromium.launch({ headless: true })
    const ctx1 = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    const page1 = await ctx1.newPage()
    page1.on('console', m => { if (m.type() === 'error') log(`  [console error] ${m.text().slice(0, 200)}`) })
    page1.on('pageerror', e => log(`  [pageerror] ${e.message.slice(0, 200)}`))

    // Hook AudioContext + AudioBufferSourceNode to track active music sources.
    await page1.addInitScript(() => {
        window.__audioActiveBufferSources = 0
        const OrigAudioContext = window.AudioContext || window.webkitAudioContext
        if (OrigAudioContext) {
            window.__audioContext = new OrigAudioContext()
            const proto = OrigAudioContext.prototype
            const origCreateBufferSource = proto.createBufferSource
            proto.createBufferSource = function () {
                const src = origCreateBufferSource.apply(this, arguments)
                window.__audioActiveBufferSources++
                src.addEventListener('ended', () => { window.__audioActiveBufferSources = Math.max(0, window.__audioActiveBufferSources - 1) }, { once: true })
                return src
            }
        }
    })

    await loginAsGuest(page1)
    const id1 = await page1.locator('[data-testid="main-menu"]').first().getAttribute('data-accelbyte-user-id')
    log(`  accelbyteId = ${id1}`)
    if (!id1 || id1 === 'guest-user') {
        await dumpDomSnapshot(page1, 'fatal-no-accelbyteId')
        await browser.close()
        throw new Error('No real accelbyteId after guest login')
    }

    await enterSinglePlayerGame(page1)
    const { state: phase1End, myName } = await playFirstTurnAndWaitForOpponent(page1)
    await dumpDomSnapshot(page1, 'p1-final')

    log('  Step P1.11: close browser to trigger disconnect + snapshot persist')
    await page1.close()
    await ctx1.close()

    log('==== PHASE 1 result ====')
    log(`  accelbyteId=${id1}`)
    log(`  myName=${myName}`)
    log(`  round=${phase1End.round}`)
    log(`  yourTurn=${phase1End.yourTurn}`)
    log(`  activeActor=${phase1End.activeActor}`)
    log(`  workStreamGlow=${phase1End.workStreamGlow}`)
    log(`  audioCount=${phase1End.audioCount}`)

    await writeFile('/tmp/echo-phase1.json', JSON.stringify({
        accelbyteId: id1,
        myName,
        round: phase1End.round,
        yourTurn: phase1End.yourTurn,
        activeActor: phase1End.activeActor,
        workStreamGlow: phase1End.workStreamGlow,
        audioCount: phase1End.audioCount,
    }, null, 2))

    await browser.close()
    log('==== PHASE 1 COMPLETE; user must kill+restart servers then re-run with --phase=2 ====')
}

async function runPhase2() {
    log('==== PHASE 2: second session after server restart ====')
    const browser = await chromium.launch({ headless: true })
    const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 800 } })
    const page2 = await ctx2.newPage()
    page2.on('console', m => { if (m.type() === 'error') log(`  [console error] ${m.text().slice(0, 200)}`) })
    page2.on('pageerror', e => log(`  [pageerror] ${e.message.slice(0, 200)}`))

    await page2.addInitScript(() => {
        window.__audioActiveBufferSources = 0
        const OrigAudioContext = window.AudioContext || window.webkitAudioContext
        if (OrigAudioContext) {
            window.__audioContext = new OrigAudioContext()
            const proto = OrigAudioContext.prototype
            const origCreateBufferSource = proto.createBufferSource
            proto.createBufferSource = function () {
                const src = origCreateBufferSource.apply(this, arguments)
                window.__audioActiveBufferSources++
                src.addEventListener('ended', () => { window.__audioActiveBufferSources = Math.max(0, window.__audioActiveBufferSources - 1) }, { once: true })
                return src
            }
        }
    })

    await loginAsGuest(page2, false)  // DO NOT dismiss the Resume dialog in Phase 2
    const id2 = await page2.locator('[data-testid="main-menu"]').first().getAttribute('data-accelbyte-user-id')
    log(`  accelbyteId = ${id2}`)

    log('  Step P2.1: wait up to 60s for ResumeOrNewDialog')
    let dialogAppeared = null
    for (let i = 0; i < 60; i++) {
        const result = await page2.evaluate(() => {
            const byTestId = document.querySelector('[data-testid="resume-or-new-dialog"]')
            if (byTestId) return { found: 'testid', text: byTestId.textContent.slice(0, 300) }
            return null
        })
        if (result) {
            dialogAppeared = result
            log(`  dialog appeared at iteration ${i}: ${JSON.stringify(result)}`)
            break
        }
        await page2.waitForTimeout(1000)
    }
    if (!dialogAppeared) {
        await dumpDomSnapshot(page2, 'p2-no-dialog')
        throw new Error('ResumeOrNewDialog did not appear')
    }

    log('  Step P2.2: click Resume button in the dialog')
    const resumeButton = page2.getByRole('button', { name: /^Resume$/ })
    await resumeButton.first().click({ timeout: 10_000, force: true })

    log('  Step P2.3: dismiss Match Resumed modal (if present), wait for GameplayUI')
    for (let i = 0; i < 60; i++) {
        const okByText = page2.getByRole('button', { name: /^OK$/ })
        if (await okByText.count() > 0 && await okByText.first().isVisible()) {
            try { await okByText.first().click({ timeout: 2_000, force: true }) } catch (_) {}
        }
        const gp = await page2.locator('[data-testid="gameplay-ui"]').count()
        if (gp > 0) break
        await page2.waitForTimeout(500)
    }
    await page2.waitForFunction(() => !!document.querySelector('[data-testid="gameplay-ui"]'), { timeout: 30_000 }).catch(e => log(`  waitForGameplayAfterResume: ${e.message}`))

    log('  Step P2.4: wait 25s for chunked ui.loadMapPack + ui.updateWorld')
    await page2.waitForTimeout(25_000)

    log('  Step P2.5: capture state after resume (gameplay mounted, music, work stream)')
    await dumpDomSnapshot(page2, 'p2-after-resume')
    const phase2State = await captureGameState(page2, 'p2-end')
    log(`  PHASE 2 STATE: ${JSON.stringify(phase2State, null, 2)}`)

    // CRITICAL: click OK on the Match Resumed modal BEFORE taking the screenshot
    log('  Step P2.5b: click OK on Match Resumed modal if present')
    for (let i = 0; i < 10; i++) {
        const okByText = page2.getByRole('button', { name: /^OK$/ })
        if (await okByText.count() > 0 && await okByText.first().isVisible()) {
            try { await okByText.first().click({ timeout: 2_000, force: true }) } catch (_) {}
            log('  clicked OK')
            break
        }
        await page2.waitForTimeout(500)
    }
    await page2.waitForTimeout(3_000)  // let game UI render after dismiss

    log('  Step P2.6: take screenshot proof of resumed game UI')
    const shotPath = join(ARTIFACT_DIR, 'screenshot.png')
    await page2.screenshot({ path: shotPath, fullPage: false })
    log(`  screenshot: ${shotPath}`)

    await writeFile('/tmp/echo-phase2.json', JSON.stringify({
        accelbyteId: id2,
        round: phase2State.round,
        yourTurn: phase2State.yourTurn,
        activeActor: phase2State.activeActor,
        workStreamGlow: phase2State.workStreamGlow,
        audioCount: phase2State.audioCount,
    }, null, 2))

    await page2.waitForTimeout(5_000)
    const phase2StateFinal = await captureGameState(page2, 'p2-after-5s')
    log(`  PHASE 2 STATE after 5s: ${JSON.stringify(phase2StateFinal, null, 2)}`)

    await browser.close()
    log('==== PHASE 2 COMPLETE ====')
    // Exit code reflects the user's contract: game resumed, music playing, work stream moving
    const ok = phase2State.round != null
        && phase2State.workStreamGlow
        && phase2State.audioCount > 0
    log(`==== PHASE 2 RESULT: ${ok ? 'PASS' : 'FAIL'} ====`)
    process.exit(ok ? 0 : 1)
}

await mkdir(ARTIFACT_DIR, { recursive: true })
main().catch(e => {
    console.error('FATAL:', e)
    process.exit(2)
})
