#!/usr/bin/env node
// hermes-verify-adhoc-positional.mjs (template — copy and customize per round)
//
// AD-HOC VERIFIER TEMPLATE for mobile-portrait positional fix commits.
// Distinct from the canonical suite probes that also run:
//
//   - mainmenu-mobile-multi-viewport.mjs: covers 5 viewports, 8-9 generic
//     assertions, exercises every CSS class in night-mode.css. A "fix"
//     commit adds 1-3 assertions to this probe, but the bulk of the
//     evidence comes from this script.
//
//   - mainmenu-mobile-portrait.mjs: 9 single-viewport (390x844) asserts,
//     covers the canonical reference device.
//
// Use this template when committing a CSS fix that targets a specific
// element's position (left, right, width, alignment). The template
// captures ONLY the behavior delta between the prior commit and the
// new commit — no generic regress-of-existing-asserts noise.
//
// EXAMPLES (real, 2026-07-12):
//   /tmp/hermes-verify-gear-right-pin-20260712.mjs    (commit 154920b99)
//   /tmp/hermes-verify-play-alignment-20260712.mjs   (commit d54f8d898)
//
// PATTERN:
//   1. Set up Chrome headless via @playwright/test's chromium
//   2. Visit http://127.0.0.1:8080/index.html?skipLogin=true
//   3. Click LoadingScreen CTA, wait for [data-testid="main-menu"]
//   4. page.evaluate() to grab getBoundingClientRect + computed style of
//      the targeted element AND its expected peer elements
//   5. Assert the deltas match the design intent
//
// USAGE:
//   1. Copy to /tmp/hermes-verify-<feature>-YYYYMMDD.mjs
//   2. Replace TARGET_QUERY, PEER_QUERY, EXPECTED_* constants
//   3. Run against a live static-server-8080.mjs on :8080
//
// REQUIRES:
//   - kvisionApp-e2e/static-server-8080.mjs running on :8080
//   - kvisionApp-e2e/node_modules/playwright installed

import { chromium } from '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/playwright/index.mjs'

const FAILURES = []
function check(name, condition, detail = '') {
    if (condition) console.log(`PASS: ${name}`)
    else { console.log(`FAIL: ${name} ${detail}`); FAILURES.push(name) }
}

const browser = await chromium.launch()
const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
})
const page = await ctx.newPage()
await page.goto('http://127.0.0.1:8080/index.html?skipLogin=true', { waitUntil: 'domcontentloaded' })
await page.waitForSelector('[data-testid="loading-screen-cta"]', { timeout: 15000 })
await page.click('[data-testid="loading-screen-cta"]')
await page.waitForSelector('[data-testid="main-menu"]', { timeout: 30000 })
await new Promise(r => setTimeout(r, 1500))

// --- BEGIN: PER-COMMIT CUSTOMIZE BLOCK ---
//
// Replace TARGET_QUERY with the element your commit fixed.
// Replace PEER_QUERY with the sibling/anchor that defines correct position.
// EXPECTED_* constants encode the design intent.
//
const TARGET_QUERY = '.btn-play'                            // <-- fixed element
const PEER_QUERY = '.main-menu-bottom .btn-secondary-action' // <-- anchor sibling

const m = await page.evaluate(({ tq, pq }) => {
    const grab = (sel) => {
        const el = document.querySelector(sel)
        if (!el) return null
        const r = el.getBoundingClientRect()
        return { left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height) }
    }
    return {
        viewport: { w: window.innerWidth },
        target: grab(tq),
        peer: grab(pq),
    }
}, { tq: TARGET_QUERY, pq: PEER_QUERY })

console.log(`target ${TARGET_QUERY}: left=${m.target.left} right=${m.target.right} w=${m.target.w}`)
console.log(`peer   ${PEER_QUERY}: left=${m.peer.left} right=${m.peer.right} w=${m.peer.w}`)
console.log(`delta.left  = ${m.target.left - m.peer.left}`)
console.log(`delta.right = ${m.target.right - m.peer.right}`)
console.log()

// Example assertions — replace with the actual intent for your commit.
// The 154920b99 round used: |gear.right - (viewport.w - 43)| <= 8
// The d54f8d898 round used: |play.left - collection.left| <= 2 AND play.w === 360
check('(A) example assertion: target.left aligned with peer.left (within 2px)',
      Math.abs(m.target.left - m.peer.left) <= 2,
      `delta=${m.target.left - m.peer.left}`)
check('(B) example assertion: target.right aligned with peer.right (within 2px)',
      Math.abs(m.target.right - m.peer.right) <= 2,
      `delta=${m.target.right - m.peer.right}`)

await browser.close()

// --- END: PER-COMMIT CUSTOMIZE BLOCK ---

console.log()
if (FAILURES.length === 0) {
    console.log(`ALL CHECKS PASSED`)
    process.exit(0)
} else {
    console.log(`${FAILURES.length} CHECK(S) FAILED:`)
    FAILURES.forEach(f => console.log(`  - ${f}`))
    process.exit(1)
}
