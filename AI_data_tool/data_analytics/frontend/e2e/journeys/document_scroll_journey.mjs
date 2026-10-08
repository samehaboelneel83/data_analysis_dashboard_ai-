// QA4 E0, against a RUNNING stack: the document never scrolls -- every page
// scrolls inside the app shell, never the window.
//
//   node frontend/e2e/journeys/document_scroll_journey.mjs [shotsDir]
//
// Environment: JOURNEY_BASE_URL (default http://localhost:3001),
// JOURNEY_EMAIL, JOURNEY_PASSWORD. Reads only. For Home, Dashboards, Datasets
// and the Builder, in English and Arabic, dark theme, a 1920×1080 window:
//   - document.scrollingElement.scrollHeight === innerHeight;
//   - after a long wheel over the page content and over the sidebar, the
//     window has not scrolled and the shell's top is still 0.
// On failure it lists absolutely positioned elements that escape the shell.
// Exit code 1 when a check fails.

import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')
const BASE = (process.env.JOURNEY_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const EMAIL = process.env.JOURNEY_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.JOURNEY_PASSWORD || 'demo-password'
const SHOTS = process.argv[2]
const sleep = ms => new Promise(r => setTimeout(r, ms))
const PAGES = [['home', '/'], ['dashboards', '/reports'], ['datasets', '/datasets'], ['builder', '/reports/1?edit=1']]

const browser = await chromium.launch()
let failed = 0
try {
  const login = await browser.newContext()
  const lp = await login.newPage()
  await lp.goto(BASE + '/login')
  await lp.getByLabel('Email', { exact: true }).fill(EMAIL)
  await lp.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
  await lp.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })
  const state = await login.storageState(); await login.close()

  for (const lang of ['en', 'ar']) for (const [name, url] of PAGES) {
    const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, storageState: state })
    await ctx.addInitScript(({ lang }) => {
      localStorage.setItem('theme', 'dark'); localStorage.setItem('datalytics.language', lang)
      localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    }, { lang })
    const p = await ctx.newPage(); await p.goto(BASE + url); await sleep(5000)
    const sh = await p.evaluate(() => document.scrollingElement.scrollHeight)
    await p.mouse.move(960, 600); await p.mouse.wheel(0, 3000); await sleep(500)
    const rail = await p.locator('[data-testid="app-rail"]').boundingBox().catch(() => null)
    if (rail) { await p.mouse.move(rail.x + rail.width / 2, rail.y + rail.height - 40); await p.mouse.wheel(0, 3000); await sleep(500) }
    const r = await p.evaluate(() => ({ ih: innerHeight, y: Math.round(document.scrollingElement.scrollTop),
      top: Math.round(document.querySelector('.dl-shell').getBoundingClientRect().top),
      escaping: [...document.querySelectorAll('body *')].filter(e => getComputedStyle(e).position === 'absolute' && e.getBoundingClientRect().bottom > innerHeight + 1
        && !e.closest('.dl-shell__content, .dl-shell')?.contains(e)).map(e => e.tagName + '.' + e.className).slice(0, 5) }))
    const ok = sh === r.ih && r.y === 0 && r.top === 0
    if (!ok) failed++
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${lang} ${name.padEnd(10)} scrollHeight ${sh} / innerHeight ${r.ih}; after wheel: window scrolled ${r.y}, shell top ${r.top}`)
    if (SHOTS) await p.screenshot({ path: path.join(SHOTS, `E0-${name}-${lang}-dark.png`) })
    await ctx.close()
  }
} finally { await browser.close() }
console.log(failed ? `${failed} check(s) failed` : 'all checks passed')
process.exit(failed ? 1 : 0)
