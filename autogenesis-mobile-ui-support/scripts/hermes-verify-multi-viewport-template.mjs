#!/usr/bin/env node
// scripts/hermes-verify-multi-viewport-template.mjs
//
// TEMPLATE (not run as-is). Copy to kvisionApp-e2e/probes/<feature>-multi-viewport.mjs
// and adapt the TRACKED_SELECTORS block + WIDGET_SELECTOR + LOADING_CTA_SELECTOR
// at the top.
//
// Captures a widget at 5 standard portrait viewports (320, 375, 390x664, 390x844, 430)
// and asserts:
//   - no horizontal overflow at any viewport
//   - no element right edge past viewport width (no clipping)
//   - element-specific assertions (heights, widths within expected bands)
//
// Run after CSS-only fixes. Pre-req: node kvisionApp-e2e/static-server-8080.mjs &
// (the CSS must already be synced to dist).

import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8080'
const SKIPLOGIN = '/index.html?skipLogin=true'
const OUT_DIR = process.env.OUT_DIR
    || join(process.env.HOME, 'Desktop/Workspaces/Autogenesis/screenshots')

// === Customize for each widget ===
const WIDGET_SELECTOR = '[data-testid="main-menu"]'
const LOADING_CTA_SELECTOR = '[data-testid="loading-screen-cta"]'

// For each tracked selector: 'noClip' (right edge past viewport width?)
// and 'heightBand' ([lo, hi] pixel range).
const TRACKED_SELECTORS = [
    { selector: '.btn-options',                        noClip: true, heightBand: [40, 50] },
    { selector: '.main-menu-header .btn-secondary-action', noClip: true, heightBand: [32, 44] },
]

const VIEWPORTS = [
    { name: '320x568-iphone-se-1st',     w: 320, h: 568 },
    { name: '375x667-iphone-se-3rd',     w: 375, h: 667 },
    { name: '390x664-iphone-12-mini',    w: 390, h: 664 },
    { name: '390x844-iphone-12',         w: 390, h: 844 },
    { name: '430x932-iphone-14-pro-max', w: 430, h: 932 },
]
// === End customization ===

const FAILURES = []
function check(name, condition, detail = '')
{
    if (condition) console.log(`PASS: ${name}`)
    else { console.log(`FAIL: ${name} ${detail}`); FAILURES.push(name) }
}

await mkdir(OUT_DIR, { recursive: true })

const browser = await chromium.launch()

for (const v of VIEWPORTS) {
    const context = await browser.newContext({
        viewport: { width: v.w, height: v.h },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
    })
    const page = await context.newPage()
    try {
        await page.goto(BASE_URL + SKIPLOGIN, { waitUntil: 'domcontentloaded' })
        await page.waitForSelector(LOADING_CTA_SELECTOR, { timeout: 15000 })
        await page.click(LOADING_CTA_SELECTOR)
        await page.waitForSelector(WIDGET_SELECTOR, { timeout: 30000 })
        await page.waitForFunction(
            (sel) => document.querySelector(sel)?.getAttribute('data-mobile-layout') !== null,
            WIDGET_SELECTOR,
            { timeout: 5000 },
        )
        await new Promise(r => setTimeout(r, 800))

        const m = await page.evaluate((sels) => {
            const grab = (sel) => {
                const el = document.querySelector(sel)
                if (!el) return null
                const r = el.getBoundingClientRect()
                return { w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left), right: Math.round(r.right) }
            }
            const viewportW = window.innerWidth
            const scrollW = document.documentElement.scrollWidth
            return {
                viewport: { w: viewportW, h: window.innerHeight },
                scrollW,
                measurements: sels.map(s => ({ name: s.selector, ...grab(s.selector) })),
            }
        }, TRACKED_SELECTORS)

        console.log(`\n[${v.name} ${v.w}x${v.h}] scrollW=${m.scrollW}`)
        for (const tm of m.measurements) {
            console.log(`  ${tm.name}: right=${tm.right} w=${tm.w} h=${tm.h}`)
        }

        check(`[${v.name}] no horizontal overflow`,
              m.scrollW <= m.viewport.w + 1,
              `(scrollW=${m.scrollW}, viewportW=${m.viewport.w})`)

        for (const t of TRACKED_SELECTORS) {
            const tm = m.measurements.find(x => x.name === t.selector)
            if (!tm) {
                check(`[${v.name}] ${t.selector} exists`, false, 'no bounding rect')
                continue
            }
            if (t.noClip) {
                check(`[${v.name}] ${t.selector} visible (right <= viewport)`,
                      tm.right <= m.viewport.w + 1,
                      `(right=${tm.right}, viewportW=${m.viewport.w})`)
            }
            if (t.heightBand) {
                const [lo, hi] = t.heightBand
                check(`[${v.name}] ${t.selector} height in [${lo},${hi}]`,
                      tm.h >= lo && tm.h <= hi,
                      `(got: ${tm.h}px)`)
            }
        }

        const probeName = new URL(import.meta.url).pathname.split('/').pop().replace('.mjs', '')
        await page.screenshot({
            path: join(OUT_DIR, `${probeName}_${v.name}.png`),
            fullPage: false,
        })
    } catch (err) {
        console.error(`[${v.name}] CRASHED: ${err.message}`)
        FAILURES.push(`[${v.name}] crashed: ${err.message}`)
    } finally {
        await context.close()
    }
}

await browser.close()
if (FAILURES.length > 0) {
    console.error(`\n${FAILURES.length} failure(s):`)
    FAILURES.forEach(f => console.error(`  - ${f}`))
    process.exit(1)
}
console.log('\nAll multi-viewport checks passed.')
