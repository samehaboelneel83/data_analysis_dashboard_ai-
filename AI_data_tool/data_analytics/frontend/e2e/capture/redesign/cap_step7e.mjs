import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')

/**
 * Redesign 7e: the builder (header and toolbars, left panel tabs, right rail
 * and Properties, canvas overlays, shortcuts, copilot offline, loading, load
 * error, empty page) × light / dark / Arabic / Arabic dark at 1440 × 900.
 * Browser-only data: a report with an empty page, a slow and a failing report
 * load, a "down" /llm/endpoints. The dev server rate-limits widget queries,
 * so screens are spaced out (PAUSE ms, default 4000).
 * Usage: node cap_step7e.mjs <outdir> [screen] [reportId]; ONE=1 for light only.
 */

const BASE = process.env.BASE ?? 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const RID = Number(process.argv[4] ?? 1)
const PAUSE = Number(process.env.PAUSE ?? 4000)
const VIEW = { width: 1440, height: 900 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(([s]) => !process.env.ONE || s === 'light')
const at = p => u => new URL(u).pathname === p
const sleep = ms => new Promise(r => setTimeout(r, ms))
const rail = (p, name) => p.locator('nav.dl-bd-rail button').nth(name)
const tile = (p, i) => p.locator('[data-widget-id]').nth(i)
const leftTab = (p, i) => p.locator('.dl-bd-lh [role="tab"]').nth(i)

const screens = [
  { name: 'edit' },
  { name: 'selected', act: async p => { await tile(p, 8).click({ position: { x: 60, y: 60 } }); await sleep(800); await tile(p, 8).hover() } },
  { name: 'multi', act: async p => { for (const i of [0, 2, 3]) { await tile(p, i).click({ position: { x: 60, y: 60 }, modifiers: ['Shift'] }); await sleep(300) } } },
  { name: 'insert', act: async p => { await leftTab(p, 0).click(); await sleep(400); await p.locator('.dl-gallery__tile').nth(3).hover() } },
  { name: 'fields', act: async p => { await leftTab(p, 1).click(); await sleep(400); await p.locator('.dl-bd-f').nth(1).hover() } },
  { name: 'templates', act: async p => { await leftTab(p, 2).click(); await sleep(1500) } },
  { name: 'page-menu', act: async p => { await p.locator('.dl-bd-pg__m').first().click() } },
  { name: 'layout-menu', act: async p => { await p.locator('.dl-bd-bar .dl-bd-menuw > button').click() } },
  { name: 'outline', act: async p => { await rail(p, 1).click(); await sleep(800) } },
  { name: 'pinned', act: async p => { await tile(p, 8).click({ position: { x: 60, y: 60 } }); await sleep(700); await p.locator('.dl-bd-ph button[aria-pressed]').click(); await rail(p, 1).click(); await sleep(900) } },
  { name: 'ai', act: async p => { await p.locator('nav.dl-bd-rail button:has(.av)').click(); await sleep(1500) } },
  { name: 'shortcuts', act: async p => { await p.keyboard.press('?') } },
  { name: 'copilot-offline', fake: 'offline', act: async p => { await sleep(3000); await p.locator('button.dl-askai__btn').click({ force: true }); await sleep(800) } },
  { name: 'empty-page', fake: 'empty' },
  { name: 'loading', fake: 'slow', wait: 1200 },
  { name: 'load-error', fake: 'error' },
].filter(s => !only || s.name === only)

const browser = await chromium.launch()
const login = await browser.newContext({ viewport: VIEW })
const lp = await login.newPage()
await lp.goto(BASE + '/login')
await lp.getByLabel('Email', { exact: true }).fill('admin@datalytics.local')
await lp.getByLabel('Password', { exact: true }).fill('demo-password')
await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
await lp.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })
const state = await login.storageState()
await login.close()

for (const sc of screens) for (const [suffix, lang, theme] of themes) {
  const ctx = await browser.newContext({ viewport: VIEW, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('console', m => { if (m.type() === 'error' && !/status of (500|401|403)/.test(m.text())) errors.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => errors.push(String(e).slice(0, 140)))
  if (sc.fake === 'offline') await page.route(at('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.auto_pick = null
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: false, error: 'connection refused' } }))
    await r.fulfill({ json: body })
  })
  if (sc.fake === 'empty') await page.route(at(`/api/v1/reports/${RID}`), async r => {
    if (r.request().method() !== 'GET') return r.continue()
    const res = await r.fetch(); const body = await res.json()
    body.pages = [{ ...body.pages[0], widgets: [] }, ...body.pages.slice(1)]
    await r.fulfill({ json: body })
  })
  if (sc.fake === 'slow') await page.route(at(`/api/v1/reports/${RID}`), () => { /* never answers */ })
  if (sc.fake === 'error') await page.route(at(`/api/v1/reports/${RID}`), r => r.fulfill({ status: 500, json: { detail: 'The database did not answer in time.' } }))
  await page.goto(`${BASE}/reports/${RID}`)
  await sleep(sc.wait ?? 4000)
  if (sc.act) { try { await sc.act(page) } catch (e) { errors.push('act: ' + String(e).slice(0, 120)) } }
  await sleep(700)
  await page.screenshot({ path: path.join(OUT, `builder-${sc.name}-${suffix}.png`) })
  console.log(`builder-${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.slice(0, 3).join(' | ') : 'clean')
  await ctx.close()
  await sleep(PAUSE)
}
await browser.close()
