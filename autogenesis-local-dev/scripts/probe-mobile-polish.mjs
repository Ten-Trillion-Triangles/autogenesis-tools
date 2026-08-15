#!/usr/bin/env node
// Re-runnable verification probe for Autogenesis mobile-portrait CSS polish.
//
// Launches a fresh Playwright Chromium per modal at iPhone 12 portrait dimensions
// (avoids click-flow state corruption between modals), then greps CSS source + dist
// for the portrait rules. Designed for the autogenesis-local-dev skill's
// `scripts/probe-computed-styles.mjs` slot.
//
// Usage:
//   1. Start the static server: cd kvisionApp-e2e && node static-server-8080.mjs
//   2. node probe-mobile-polish.mjs
//   3. Expect exit code 0 with all 35 rules + all modal checks green
//
// Ad-hoc verification, not suite green. The sandbox's
// `:kvisionApp:jsBrowserProductionWebpack` build is broken (cannot resolve
// org.nodejs:node:22.0.0 from the configured repos); this probe reads
// `build/dist/js/productionExecutable/night-mode.css` directly.

import { chromium, devices } from '../kvisionApp-e2e/node_modules/@playwright/test/index.mjs'
import { readFile } from 'node:fs/promises'

const BASE_URL = 'http://127.0.0.1:8080/index.html?skipLogin=true'

const css = await readFile('../kvisionApp/src/jsMain/resources/night-mode.css', 'utf8')
const cssDist = await readFile('../kvisionApp/build/dist/js/productionExecutable/night-mode.css', 'utf8')

const rules = [
    ['mm-flex-start',         /\.main-menu \{[^}]*justify-content: flex-start/],
    ['mm-center-margin-auto', /\.main-menu-center \{[^}]*margin-top: auto/],
    ['mm-friends-hidden',     /\.main-menu-bottom \.btn-friends \{[^}]*display: none/],
    ['mm-corner-stripped',     /\.main-menu-bottom > div \{[^}]*border-right: 0/],
    ['mm-credits-pill',        /\.credits-container \{[^}]*border-radius: 22px/],
    ['mm-gear-28',             /\.btn-options \{[^}]*width: 28px/],
    ['mm-ghost-secondary',     /\.btn-secondary-action\.btn-secondary-action \{[^}]*background: transparent/],
    ['mm-username-weight',     /\.display-name,?\s*\.version-text \{[^}]*font-weight: 600/],
    ['shop-modal-padding',     /\.modal\.billing-modal-window-host \.modal-body\.billing-modal-body \{[^}]*padding-bottom: 24px/],
    ['shop-cards-equal',       /\.shop-credit-card \{[^}]*min-height: 320px/],
    ['shop-bonus-inset',       /\.shop-credit-card-bonus-badge \{[^}]*right: 12px/],
    ['shop-tab-flex-1',        /\.billing-tab \{[^}]*flex: 1 1 0/],
    ['shop-section-border',    /\.billing-modal-section \{[^}]*border-radius: 12px/],
    ['shop-tab-glow',          /\.billing-tab\.active \{[^}]*box-shadow: 0 0 12px/],
    ['usage-mask-bottom',      /\.modal\.billing-modal-window-host \.modal-body\.billing-modal-body \{[^}]*mask-image: linear-gradient/],
    ['usage-intro-margin',     /\.billing-modal-intro,\s*\.usage-modal-intro \{[^}]*margin-bottom: 24px/],
    ['usage-tabs-nowrap',      /\.billing-tabs \{[^}]*flex-wrap: nowrap/],
    ['usage-card-max-h',       /\.billing-modal-credits-card \{[^}]*max-height: 280px/],
    ['usage-summary-flex',     /\.billing-modal-credits-summary \{[^}]*display: flex/],
    ['usage-section-mt',       /\.billing-modal-section-header \{[^}]*margin-top: 24px/],
    ['usage-cal-icon-36',      /\.billing-modal-credits-card \.fa-calendar[^}]*font-size: 36px/],
    ['settings-full-width',    /\.login-widget-window \{[^}]*width: 100vw/],
    ['settings-max-h',         /\.login-widget-window \{[^}]*max-height: 85vh/],
    ['settings-slider-track',  /input\[type="range"\]\.form-range[^}]*background: rgba\(255, 255, 255, 0\.18\)/],
    ['settings-checkbox-bd',   /input\[type="checkbox"\]\.form-check-input \{[^}]*border: 1\.5px solid/],
    ['collection-overlay',     /\.collection-overlay \{[^}]*background-color: rgba\(2, 4, 12, 0\.97\)/],
    ['collection-window-bg',   /\.collection-window \{[^}]*background: rgba\(10, 14, 26, 0\.99\)/],
    ['collection-window-mh',   /\.collection-window \{[^}]*max-height: 80vh/],
    ['collection-search',      /\.collection-search-input[^}]*width: calc\(100% - 24px\)/],
    ['collection-title-c',     /\.collection-window \.billing-modal-title \{[^}]*text-align: center/],
    ['cc-h3-28px',            /\.commander-creation-dialog > h3 \{[^}]*font-size: 28px/],
    ['cc-textarea-120',       /textarea\[placeholder\*="Describe your commander"\] \{[^}]*height: 120px/],
    ['cc-button-flex',        /\.commander-creation-button-row \{[^}]*display: flex/],
    ['cc-create-wider',       /\.commander-creation-button-row > button:last-child \{[^}]*flex: 1\.4/],
    ['cc-input-radius',        /\.commander-creation-overlay input[^}]*border-radius: 12px/],
]

const cssStatic = rules.map(([id, re]) => ({ id, src: re.test(css), dist: re.test(cssDist) }))

const browser = await chromium.launch()
const runtime = {}

async function freshMenu() {
    const ctx = await browser.newContext({ ...devices['iPhone 12'] })
    const page = await ctx.newPage()
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('[data-testid="loading-screen-cta"]', { timeout: 15000 })
    await page.click('[data-testid="loading-screen-cta"]')
    await page.waitForSelector('[data-testid="main-menu"]', { timeout: 30000 })
    await page.waitForFunction(
        () => document.querySelector('[data-testid="main-menu"]')?.hasAttribute('data-mobile-layout'),
        { timeout: 5000 }
    )
    await new Promise(r => setTimeout(r, 800))
    return { ctx, page }
}

{
    const { ctx, page } = await freshMenu()
    runtime.mainMenu = await page.evaluate(() => {
        const grab = (sel) => {
            const el = document.querySelector(sel)
            if (!el) return null
            const r = el.getBoundingClientRect()
            return { y: Math.round(r.y), h: Math.round(r.height), w: Math.round(r.width) }
        }
        return {
            header: grab('.main-menu-header'),
            center: grab('.main-menu-center'),
            bottom: grab('.main-menu-bottom'),
            scrollW: document.documentElement.scrollWidth,
            viewportH: window.innerHeight,
            noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerHeight + 10,
            friendsHidden: getComputedStyle(document.querySelector('.main-menu-bottom .btn-friends')).display === 'none',
            mmJustify: getComputedStyle(document.querySelector('.main-menu')).justifyContent,
            mmCenterMarginTop: getComputedStyle(document.querySelector('.main-menu-center')).marginTop,
            cornerAccent: (() => {
                const inner = document.querySelector('.main-menu-bottom > div')
                if (!inner) return null
                const cs = getComputedStyle(inner)
                return { borderRight: cs.borderRightWidth, boxShadow: cs.boxShadow }
            })(),
            creditsPill: (() => {
                const c = document.querySelector('.credits-container')
                if (!c) return null
                const cs = getComputedStyle(c)
                return { borderRadius: cs.borderRadius, borderColor: cs.borderColor }
            })(),
            gearRect: grab('.btn-options'),
            ghostShop: (() => {
                const b = document.querySelector('.main-menu-header .btn-secondary-action')
                if (!b) return null
                return { background: getComputedStyle(b).backgroundColor }
            })(),
        }
    })
    await ctx.close()
}

{
    const { ctx, page } = await freshMenu()
    await page.click('button:has-text("Shop")')
    await new Promise(r => setTimeout(r, 1500))
    runtime.shop = await page.evaluate(() => {
        const cardHeightsAll = Array.from(document.querySelectorAll('.shop-credit-card')).map(c => Math.round(c.getBoundingClientRect().height))
        const tabs = Array.from(document.querySelectorAll('.billing-tab')).filter(t => t.textContent.trim().length > 0 && t.getBoundingClientRect().width > 0).map(t => ({ text: t.textContent.trim(), w: Math.round(t.getBoundingClientRect().width) }))
        const purchaseBtns = Array.from(document.querySelectorAll('.modal.billing-modal-window-host button')).filter(b => b.textContent.includes('PURCHASE')).map(b => Math.round(b.getBoundingClientRect().width))
        const modalBody = document.querySelector('.modal.billing-modal-window-host .modal-body.billing-modal-body')
        const host = document.querySelector('.modal.billing-modal-window-host')
        return {
            cardHeightsAll,
            tabs,
            purchaseBtnWidths: purchaseBtns,
            modalBodyPaddingBottom: modalBody ? getComputedStyle(modalBody).paddingBottom : null,
            hostBg: host ? getComputedStyle(host).backgroundColor : null,
        }
    })
    await ctx.close()
}

{
    const { ctx, page } = await freshMenu()
    await page.click('button:has-text("Usage")')
    await new Promise(r => setTimeout(r, 1500))
    runtime.usage = await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('.billing-tab')).filter(t => t.textContent.trim().length > 0 && t.getBoundingClientRect().width > 0).map(t => t.textContent.trim())
        const body = document.querySelector('.modal.billing-modal-window-host .modal-body.billing-modal-body')
        return {
            tabLabels: tabs,
            bodyMaskImage: body ? (getComputedStyle(body).maskImage || getComputedStyle(body).webkitMaskImage) : null,
        }
    })
    await ctx.close()
}

{
    const { ctx, page } = await freshMenu()
    await page.click('.btn-options')
    await new Promise(r => setTimeout(r, 1500))
    runtime.settings = await page.evaluate(() => {
        const panel = document.querySelector('.login-widget-window')
        const slider = document.querySelector('input[type="range"].form-range')
        const checkbox = document.querySelector('input[type="checkbox"].form-check-input')
        return {
            panelWidth: panel ? Math.round(panel.getBoundingClientRect().width) : null,
            sliderTrackBg: slider ? getComputedStyle(slider).backgroundColor : null,
            checkboxBorder: checkbox ? getComputedStyle(checkbox).border : null,
        }
    })
    await ctx.close()
}

{
    const { ctx, page } = await freshMenu()
    await page.click('button:has-text("Collection")')
    await new Promise(r => setTimeout(r, 1500))
    runtime.collection = await page.evaluate(() => {
        const overlay = document.querySelector('.collection-overlay')
        const win = document.querySelector('.collection-window')
        return {
            overlayBg: overlay ? getComputedStyle(overlay).backgroundColor : null,
            winBg: win ? getComputedStyle(win).backgroundColor : null,
            winHeight: win ? Math.round(win.getBoundingClientRect().height) : null,
        }
    })
    await ctx.close()
}

{
    const { ctx, page } = await freshMenu()
    await page.click('button:has-text("New Commander +")')
    await new Promise(r => setTimeout(r, 1500))
    runtime.commanderCreation = await page.evaluate(() => {
        const title = document.querySelector('.commander-creation-dialog > h3')
        const textarea = document.querySelector('textarea[placeholder*="Describe your commander"]')
        return {
            titleFontSize: title ? getComputedStyle(title).fontSize : null,
            textareaHeight: textarea ? getComputedStyle(textarea).height : null,
        }
    })
    await ctx.close()
}

await browser.close()

const cssStaticPass = cssStatic.every(r => r.src && r.dist)

const verdict = {
    timestamp: new Date().toISOString(),
    css_static: { pass: cssStaticPass, total: cssStatic.length, ok: cssStatic.filter(r => r.src && r.dist).length },
    runtime,
}

console.log(JSON.stringify(verdict, null, 2))
process.exit(cssStaticPass ? 0 : 1)
