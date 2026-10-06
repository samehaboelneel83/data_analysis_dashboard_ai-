import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')

/**
 * Redesign 7d: reading a dashboard (view, widget toolbar, More menu, focus,
 * the AI panel's three tabs, offline), Present (controls, idle, Ask AI) and a
 * view-only reader, × light / dark / Arabic / Arabic dark at 1440 × 900.
 * Browser-only data: a "down" /llm/endpoints for offline, and a view-only
 * capability for the reader. The dev server rate-limits widget queries, so
 * screens are spaced out (PAUSE ms, default 4000).
 * Usage: node cap_step7d.mjs <outdir> [state] [reportId]; ONE=1 for light only.
 */

const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const RID = Number(process.argv[4] ?? 1)
const PAUSE = Number(process.env.PAUSE ?? 4000)
const VIEW = { width: 1440, height: 900 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(([s]) => !process.env.ONE || s === 'light')
const at = p => u => new URL(u).pathname === p
const sleep = ms => new Promise(r => setTimeout(r, ms))

const hoverWidget = async p => {
  const w = p.locator('[data-widget-id]').first(); const b = await w.boundingBox()
  await p.mouse.move(b.x + b.width / 2, b.y + 40); await sleep(300)
}
const openAi = async p => { await p.getByTestId('view-ai-open').click(); await sleep(900) }
const screens = [
  { name: 'view' },
  { name: 'widget-toolbar', act: hoverWidget },
  { name: 'more-menu', act: async p => { await p.locator('.dl-vw-more').click() } },
  { name: 'focus', act: async p => { await hoverWidget(p); await p.locator('.dl-vw-wt button').nth(1).click(); await sleep(1500) } },
  { name: 'ai-ask', act: async p => { await hoverWidget(p); await p.locator('.dl-vw-wt button').first().click(); await sleep(1200) } },
  { name: 'ai-insights', act: async p => { await openAi(p); await p.locator('.dl-vw-ai__tabs button').nth(1).click() } },
  { name: 'ai-suggest', act: async p => { await openAi(p); await p.locator('.dl-vw-ai__tabs button').nth(2).click(); await sleep(1500) } },
  { name: 'ai-offline', fake: 'offline', act: async p => { await sleep(4000); await openAi(p) } },
  { name: 'present', act: async p => { await p.locator('[data-testid=builder-header] button', { hasText: /Present|عرض/ }).click(); await sleep(1500); await p.mouse.move(700, 450) } },
  { name: 'present-idle', act: async p => { await p.locator('[data-testid=builder-header] button', { hasText: /Present|عرض/ }).click(); await sleep(3500) } },
  { name: 'present-ai', act: async p => { await p.locator('[data-testid=builder-header] button', { hasText: /Present|عرض/ }).click(); await sleep(800); await p.locator('.dl-pr-ctl .dl-pr-btn').nth(1).click(); await sleep(1000) } },
  { name: 'viewer', fake: 'viewer' },
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
  if (sc.fake === 'viewer') await page.route(at(`/api/v1/reports/${RID}`), async r => {
    if (r.request().method() !== 'GET') return r.continue()
    const res = await r.fetch(); const body = await res.json()
    await r.fulfill({ json: { ...body, my_capability: 'view', is_mine: false, created_by: 99 } })
  })
  await page.goto(`${BASE}/reports/${RID}`)
  await sleep(3500)
  // An editor lands in edit mode: switch to reading.
  const mode = page.getByTestId('mode-toggle')
  if (await mode.count() && (await mode.getAttribute('aria-label')) === 'View mode') { await mode.click(); await sleep(2000) }
  if (sc.act) { try { await sc.act(page) } catch (e) { errors.push('act: ' + String(e).slice(0, 120)) } }
  await sleep(700)
  await page.screenshot({ path: path.join(OUT, `view-${sc.name}-${suffix}.png`) })
  console.log(`view-${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.slice(0, 3).join(' | ') : 'clean')
  await ctx.close()
  await sleep(PAUSE)
}
await browser.close()
