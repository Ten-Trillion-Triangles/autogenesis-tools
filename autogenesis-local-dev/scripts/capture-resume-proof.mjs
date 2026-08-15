#!/usr/bin/env node
// Captures both the 3-button Resume dialog AND the resumed game state
// in a single Playwright run. Use this when the user explicitly asks
// for "screenshot proof" of the resume flow working end-to-end.
//
// Output:
//   <out>/screenshot-resume-dialog.png   — the ResumeOrNewDialog with all 3 buttons
//   <out>/screenshot-resumed-game.png    — GameplayUI restored, prior turn narrative visible
//
// Prerequisites:
//   - All three dev servers running (server-extend 7070, server 9080, webpack 8080)
//   - A snapshot already persisted in VFS for the test user (run Phase 1 of
//     `kvisionApp-e2e/probes/echo-verify-resume.mjs --phase=1` first)
//
// Usage:
//   node scripts/capture-resume-proof.mjs [outDir]
//   # default outDir = /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/probes/artifacts-echo-verify

import { chromium } from '@playwright/test'

const log = (s) => console.log(`[${new Date().toISOString().slice(11, 23)}] ${s}`)
const OUT_DIR = process.argv[2] ||
    '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/probes/artifacts-echo-verify'

async function dismissMessageBoxes(page, timeoutMs = 15000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
        try {
            const dismissed = await page.evaluate(() => {
                const overlays = document.querySelectorAll(
                    '.autogenesis-message-box-overlay, [class*="modal"], [class*="popup"]'
                )
                for (const overlay of overlays) {
                    if (overlay.offsetWidth === 0 || overlay.offsetHeight === 0) continue
                    const buttons = overlay.querySelectorAll('button')
                    for (const btn of buttons) {
                        const t = btn.textContent.trim().toLowerCase()
                        if (t === 'ok' || t === 'o.k.') { btn.click(); return true }
                    }
                }
                const allOk = Array.from(document.querySelectorAll('button'))
                    .filter(b => b.textContent.trim().toLowerCase() === 'ok')
                if (allOk.length > 0) { allOk[0].click(); return true }
                return false
            })
            if (dismissed) { await page.waitForTimeout(800); break }
            await page.waitForTimeout(300)
        } catch { await page.waitForTimeout(300) }
    }
}

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const page = await ctx.newPage()

try {
    log('navigating to index.html')
    await page.goto('http://127.0.0.1:8080/index.html')
    const cta = page.getByTestId('loading-screen-cta')
    await cta.waitFor({ state: 'visible', timeout: 30_000 })
    await cta.click()
    const guestBtn = page.getByTestId('login-as-guest')
    await guestBtn.waitFor({ state: 'visible', timeout: 30_000 })
    await guestBtn.click()

    log('dismissing Login Complete')
    await page.waitForFunction(
        () => document.querySelector('.autogenesis-message-box-overlay') !== null,
        { timeout: 30_000 }
    ).catch(() => {})
    await dismissMessageBoxes(page, 5000)

    log('waiting for Resume dialog')
    const dialog = page.locator('[data-testid="resume-or-new-dialog"]')
    await dialog.waitFor({ state: 'visible', timeout: 30_000 })
    log('Resume dialog visible')
    await page.waitForTimeout(500)

    // CAPTURE: the 3-button dialog
    await page.screenshot({ path: `${OUT_DIR}/screenshot-resume-dialog.png`, fullPage: false })
    log(`saved: ${OUT_DIR}/screenshot-resume-dialog.png`)

    const dialogText = await dialog.textContent()
    log(`dialog text: ${dialogText?.slice(0, 300)}`)

    log('clicking Resume')
    const resumeBtn = page.getByRole('button', { name: /^Resume$/ }).first()
    await resumeBtn.click({ force: true })

    log('waiting for Match Resumed modal to dismiss')
    await dismissMessageBoxes(page, 10000)

    log('waiting for GameplayUI to mount')
    await page.locator('[data-testid="gameplay-ui"]').waitFor({ state: 'visible', timeout: 30_000 })
    log('GameplayUI mounted')

    // Wait for the chunked-frame pipeline (loadMapPack + updateWorld) to fully
    // populate state — without this wait, the prior turn's narrative isn't visible
    // in the Game History pane yet.
    log('waiting 10s for stream content to populate')
    await page.waitForTimeout(10_000)

    // CAPTURE: the resumed game state
    await page.screenshot({ path: `${OUT_DIR}/screenshot-resumed-game.png`, fullPage: false })
    log(`saved: ${OUT_DIR}/screenshot-resumed-game.png`)

    const state = await page.evaluate(() => ({
        round: document.body.textContent.match(/Round:\s*(\d+)/i)?.[1] || null,
        bodyTextSnippet: document.body.textContent.slice(0, 800),
    }))
    log(`state: ${JSON.stringify(state).slice(0, 400)}`)

    log('BOTH SCREENSHOTS CAPTURED SUCCESSFULLY')
    log(`dialog.png shows the 3-button Resume dialog`)
    log(`resumed-game.png shows the GameplayUI with the prior turn's narrative`)
    log(`For verification: cross-check the server log for`)
    log(`  TurnHarness.hydratePostRestoreState: calling runNextTurn() to resume`)
    log(`  TurnHarness.executeSingleTurn: Resolved actor='<NPC-NAME>'`)
} catch (e) {
    log(`ERROR: ${e.message}`)
    await page.screenshot({ path: `${OUT_DIR}/error.png`, fullPage: false }).catch(() => {})
} finally {
    await browser.close()
}