#!/usr/bin/env node
// probe-computed-styles.mjs
//
// Re-runnable Playwright probe for CSS-only changes that grep cannot verify.
//
// Why this exists: when a CSS rule has its `!important` override silently
// defeated by a higher-specificity base rule, `grep -c` on the dist CSS
// still matches (the rule is in the file) but the rendered DOM never
// applies it. Static grep is necessary but not sufficient for CSS
// fixes; the only thing that proves a rule is actually applied is a
// computed-style read from a real browser at the target viewport.
//
// This probe accepts a JSON config describing the viewport, the
// selectors, and the expected computed styles. It launches headless
// Chromium, drives the page through the widget mount, opens any
// overlays specified in the config, and reads each selector's
// computed style. Exits non-zero on any mismatch.
//
// Usage:
//   node probe-computed-styles.mjs <config.json>
//
// Where config.json looks like:
//   {
//     "baseUrl": "http://127.0.0.1:8080/index.html?skipLogin=true",
//     "viewport": "iPhone 12",
//     "waitForSelector": "[data-testid=\"main-menu\"]",
//     "waitForDataAttr": "data-mobile-layout",
//     "probes": [
//       {
//         "label": "shop-modal-opacity",
//         "openSelector": "button:has-text(\"Shop\")",
//         "selectors": [
//           {
//             "selector": ".modal.billing-modal-window-host",
//             "property": "backgroundColor",
//             "expected": "rgba(2, 4, 12, 0.97)"
//           },
//           ...
//         ]
//       }
//     ]
//   }
//
// Exit codes:
//   0 — all probes passed
//   1 — config error, server unreachable, or any probe failed

import { chromium, devices } from '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e/node_modules/@playwright/test/index.mjs'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const args = process.argv.slice(2)
if (args.length !== 1) {
    console.error('usage: node probe-computed-styles.mjs <config.json>')
    process.exit(1)
}

const configPath = resolve(args[0])
const config = JSON.parse(await readFile(configPath, 'utf8'))

if (!config.baseUrl) {
    console.error('config.baseUrl is required')
    process.exit(1)
}
if (!config.viewport) {
    console.error('config.viewport is required (e.g. "iPhone 12")')
    process.exit(1)
}
if (!config.probes || !Array.isArray(config.probes)) {
    console.error('config.probes must be an array')
    process.exit(1)
}

// Resolve viewport — supports both Playwright device names and raw shapes.
function resolveViewport(name) {
    if (devices[name]) return devices[name]
    if (typeof name === 'object') return name
    throw new Error(`unknown viewport: ${name}`)
}

// Server reachable? Surface early so the user sees the actual problem.
const probe0 = await fetch(config.baseUrl).then(r => r.status).catch(e => `ERR ${e.message}`)
if (probe0 !== 200) {
    console.error(`server not reachable: ${config.baseUrl} returned ${probe0}`)
    process.exit(1)
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ ...resolveViewport(config.viewport) })
const page = await ctx.newPage()

let allPass = true
const results = { timestamp: new Date().toISOString(), config, probes: [] }

try {
    await page.goto(config.baseUrl, { waitUntil: 'domcontentloaded' })

    // Wait for the root widget before opening overlays. Most KVision widgets
    // set data-mobile-layout once their matchMedia listener attaches; if the
    // config asks for that, gate on it.
    if (config.waitForSelector) {
        await page.waitForSelector(config.waitForSelector, { timeout: 15000 })
    }
    if (config.waitForDataAttr) {
        await page.waitForFunction(
            (sel, attr) => document.querySelector(sel)?.hasAttribute(attr),
            { timeout: 5000 },
            config.waitForSelector, config.waitForDataAttr
        )
    }
    // Settle layout before measuring.
    await new Promise(r => setTimeout(r, 800))

    for (const probe of config.probes) {
        const probeResult = { label: probe.label, checks: [] }

        // Open the overlay if specified.
        if (probe.openSelector) {
            try {
                await page.click(probe.openSelector)
            } catch (e) {
                probeResult.error = `openSelector click failed: ${e.message}`
                results.probes.push(probeResult)
                allPass = false
                continue
            }
            // Let the overlay mount + KVision layout settle.
            await new Promise(r => setTimeout(r, 1500))
        }

        // Read all selectors + properties.
        for (const sel of probe.selectors || []) {
            const actual = await page.evaluate((selector, property) => {
                const el = document.querySelector(selector)
                if (!el) return null
                const cs = getComputedStyle(el)
                return cs[property]
            }, sel.selector, sel.property)
            const pass = actual === sel.expected
            probeResult.checks.push({
                selector: sel.selector,
                property: sel.property,
                expected: sel.expected,
                actual,
                pass,
            })
            if (!pass) allPass = false
        }

        // Close the overlay (best effort) before opening the next one.
        if (probe.openSelector) {
            await page.keyboard.press('Escape').catch(() => {})
            await new Promise(r => setTimeout(r, 600))
        }

        results.probes.push(probeResult)
    }
} finally {
    await browser.close()
}

console.log(JSON.stringify(results, null, 2))
process.exit(allPass ? 0 : 1)
