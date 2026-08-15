#!/usr/bin/env node
// hermes-verify-adhoc-injected-html.mjs (template — copy and customize per round)
//
// AD-HOC VERIFIER TEMPLATE for mobile-portrait CSS-only fixes where the widget
// is deep in the navigation flow (3+ clicks past LoadingScreen). Distinct from
// the suite probes that boot the real widget lifecycle:
//
//   - mainmenu-mobile-multi-viewport.mjs: 5 viewports, full boot + click flow.
//     Use when the fix needs the real Kotlin event handlers to fire.
//   - mainmenu-mobile-portrait.mjs: 1 viewport (390x844), full boot.
//
// Use this template when:
//   - The defect is PURELY in the CSS rules (e.g. text overflow, sizing,
//     stacking, glow bleed)
//   - The widget is mounted only after a long navigation chain
//     (e.g. CollectionOverlay requires LoadingScreen → MainMenu → COLLECTION)
//   - You want a quick before/after visual proof without 30s+ cold-start
//   - The Kotlin state management is NOT part of the fix (no async data load)
//
// PATTERN:
//   1. Open http://127.0.0.1:8080/index.html at iPhone 12 viewport (390x844)
//   2. Wait for night-mode.css to load
//   3. Inject widget HTML using REAL class names from the Kotlin source
//      so the existing @media (max-width: 600px) overrides apply unchanged
//   4. Hide LoadingScreen (z-index 9999) or set injected widget z-index > 9999
//   5. Screenshot AFTER state (current CSS rules apply)
//   6. Optionally inject inline <style> that simulates the OLD behavior
//      (e.g. flex-direction: row !important) and screenshot BEFORE state
//   7. Diff the two PNGs visually — scrollWidth/getBoundingClientRect metrics
//      can lie for ::after pseudo overflow and inline-style override cases
//
// EXAMPLES (real, 2026-07-15):
//   /tmp/hermes-verify-collection-tab-bleed-20260715.mjs
//   /tmp/hermes-verify-opponent-cards-20260715.mjs
//
// USAGE:
//   1. Copy to /tmp/hermes-verify-<feature>-YYYYMMDD.mjs
//   2. Replace INJECTED_HTML constant with the widget markup matching the
//      Kotlin source's structure (use the real class names)
//   3. Replace BEFORE_SIMULATION_CSS with an inline <style> block that
//      defeats the new mobile rules to reproduce the broken state
//   4. Run against a live static-server-8080.mjs on :8080
//
// REQUIRES:
//   - kvisionApp-e2e/static-server-8080.mjs running on :8080
//   - kvisionApp-e2e/node_modules/@playwright/test installed

import { chromium, devices } from '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/@playwright/test/index.mjs'

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8080'
const OUT = process.env.OUT_DIR || `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/${new Date().toISOString().slice(0,10)}-injected-html`

await import('node:fs/promises').then(m => m.mkdir(OUT, { recursive: true }))

const browser = await chromium.launch()
const context = await browser.newContext({ ...devices['iPhone 12'] })
const page = await context.newPage()

await page.goto(BASE + '/index.html', { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(1500)  // let night-mode.css load + parse

// --- BEGIN: PER-COMMIT CUSTOMIZE BLOCK ---
//
// Replace INJECTED_HTML with the widget's actual markup. Use REAL class names
// from the Kotlin source (e.g. 'collection-overlay' from CollectionOverlay.kt:77)
// so existing @media rules apply unmodified. Inline styles in the HTML should
// only cover what the Kotlin widget sets programmatically (sizes, colors,
// borders) — don't try to replicate state or event handlers.
const INJECTED_HTML = `
<div class="collection-overlay" data-testid="collection-overlay" data-mobile-layout="portrait" style="z-index: 10000;">
    <div class="collection-window" style="width: 92%; height: 90%; ...">
        <!-- collection cards + tab strip matching CollectionOverlay.kt:172-244 -->
    </div>
</div>
`

// Optional: inline <style> that simulates the OLD behavior by defeating the
// new mobile rules. Use to capture a BEFORE screenshot for visual comparison.
// Set to empty string '' to skip the BEFORE capture.
const BEFORE_SIMULATION_CSS = `
.collection-overlay .collection-content {
    flex-direction: column !important;
}
.collection-overlay .collection-tab-strip {
    width: 90px !important;
}
.collection-overlay .collection-tab-button {
    width: 90px !important;
    padding: 12px 16px !important;
}
.collection-overlay .collection-tab-button::after {
    font-size: 11px !important;
    letter-spacing: 0.05em !important;
}
`

// --- END: PER-COMMIT CUSTOMIZE BLOCK ---

// 1. Hide LoadingScreen + inject widget HTML
await page.evaluate((html) => {
    const loadingRoot = document.querySelector('.loading-screen-root')
    if (loadingRoot) loadingRoot.style.display = 'none'
    const wrap = document.createElement('div')
    wrap.innerHTML = html.trim()
    document.body.appendChild(wrap.firstElementChild)
}, INJECTED_HTML)
await page.waitForTimeout(400)

// 2. AFTER screenshot — current CSS rules apply
await page.screenshot({ path: `${OUT}/after-390x844.png`, fullPage: false })
console.log(`AFTER: ${OUT}/after-390x844.png`)

const after = await page.evaluate(() => {
    const elements = Array.from(document.querySelectorAll('[class*="card"], [class*="button"]'))
    return elements.slice(0, 10).map(el => {
        const r = el.getBoundingClientRect()
        return {
            cls: el.className.split(' ').filter(c => c.includes('-')).join('.'),
            w: Math.round(r.width),
            h: Math.round(r.height),
        }
    })
})
console.log('AFTER sizes:', JSON.stringify(after, null, 2))

// 3. BEFORE screenshot — apply simulation CSS (if provided) to defeat new rules
if (BEFORE_SIMULATION_CSS.trim()) {
    await page.evaluate((css) => {
        const styleEl = document.createElement('style')
        styleEl.id = 'simulate-before'
        styleEl.textContent = css
        document.head.appendChild(styleEl)
    }, BEFORE_SIMULATION_CSS)
    await page.waitForTimeout(300)
    await page.screenshot({ path: `${OUT}/before-390x844.png`, fullPage: false })
    console.log(`BEFORE: ${OUT}/before-390x844.png`)

    const before = await page.evaluate(() => {
        const elements = Array.from(document.querySelectorAll('[class*="card"], [class*="button"]'))
        return elements.slice(0, 10).map(el => {
            const r = el.getBoundingClientRect()
            return {
                cls: el.className.split(' ').filter(c => c.includes('-')).join('.'),
                w: Math.round(r.width),
                h: Math.round(r.height),
            }
        })
    })
    console.log('BEFORE sizes:', JSON.stringify(before, null, 2))
}

await browser.close()
console.log()
console.log(`Screenshots written to: ${OUT}`)
console.log(`Visual diff: compare before-*.png vs after-*.png side by side.`)