import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')

/**
 * Redesign 7b: the Dashboards list in each state × light / dark / Arabic /
 * Arabic dark at 1440 × 900 (the prototype's desktop frame). `firstrun`,
 * `fempty`, `loading`, `error` and `member` use browser-only data (page.route).
 * Usage: node cap_step7b.mjs <outdir> [state]; ONE=1 for light only.
 */

const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const VIEW = { width: 1440, height: 900 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(([s]) => !process.env.ONE || s === 'light')
const at = p => u => new URL(u).pathname === p

const screens = [
  { name: 'grid' },
  { name: 'hover', act: async p => { const c = p.locator('.dsh-card').first(); const b = await c.boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + 60); await p.waitForTimeout(300); const m = await c.locator('.dsh-ov button').last().boundingBox(); await p.mouse.click(m.x + m.width / 2, m.y + m.height / 2) } },
  { name: 'list', layout: 'list' },
  { name: 'folder', act: async p => { await p.locator('.dsh-tree [data-folder]').last().click() } },
  { name: 'bulk', act: async p => { const cs = p.locator('.dsh-card'); for (const i of [0, 1]) { await cs.nth(i).hover(); await cs.nth(i).locator('.dsh-ck').check() } } },
  { name: 'nomatch', act: async p => { await p.locator('.dsh-srch input').fill('zzzz') } },
  { name: 'new', act: async p => { await p.locator('.dsh-hd .btn-primary').click() } },
  { name: 'new-tpl', act: async p => { await p.locator('.dsh-hd .btn-primary').click(); await p.locator('.dsh-opt').nth(1).click() } },
  { name: 'newfolder', act: async p => { await p.locator('.dsh-hd .dsh-btn-line').click(); await p.locator('.dsh-nf input').fill('Board packs') } },
  { name: 'move', act: async p => { const c = p.locator('.dsh-card').first(); const b = await c.boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + 60); await p.waitForTimeout(300); const m = await c.locator('.dsh-ov button').last().boundingBox(); await p.mouse.click(m.x + m.width / 2, m.y + m.height / 2); await p.getByRole('menuitem', { name: /Move to folder|نقل إلى مجلد/ }).click() } },
  { name: 'firstrun', fake: 'empty' },
  { name: 'fempty', fake: 'fempty', act: async p => { await p.locator('.dsh-tree [data-folder="Board packs"]').click() } },
  { name: 'loading', fake: 'loading' },
  { name: 'error', fake: 'error' },
  { name: 'member', fake: 'member' },
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
  await ctx.addInitScript(({ theme, lang, layout }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    localStorage.setItem('datalytics:dashboards-layout', layout)
    localStorage.removeItem('dashboards.collapsed-sections')
  }, { theme, lang, layout: sc.layout ?? 'grid' })
  const page = await ctx.newPage()
  const errors = []
  page.on('console', m => { if (m.type() === 'error' && !/status of (500|401)/.test(m.text())) errors.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => errors.push(String(e).slice(0, 140)))
  if (sc.fake === 'empty') {
    await page.route(at('/api/v1/reports'), r => r.request().method() === 'GET' ? r.fulfill({ json: [] }) : r.continue())
    await page.route(at('/api/v1/workspace/tree'), r => r.fulfill({ json: { roots: [], unfiled: [] } }))
  }
  if (sc.fake === 'fempty') await page.route(at('/api/v1/workspace/tree'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.roots.push({ id: 9999, parent_id: null, node_type: 'folder', name: 'Board packs', report_id: null, position: 99,
      can_manage: true, is_mine: true, role_ids: [], pages: [], children: [] })
    await r.fulfill({ json: body })
  })
  if (sc.fake === 'loading') await page.route(at('/api/v1/reports'), () => { /* never answers */ })
  if (sc.fake === 'error') await page.route(at('/api/v1/reports'), r => r.fulfill({ status: 500, json: { detail: 'Database unavailable' } }))
  if (sc.fake === 'member') {
    await page.route(at('/api/v1/auth/me'), async r => {
      const res = await r.fetch(); const body = await res.json()
      body.role = { ...body.role, name: 'Analyst', is_org_admin: false }; body.is_super_admin = false
      await r.fulfill({ json: body })
    })
    // What a member is served: someone else's dashboards, view only.
    await page.route(at('/api/v1/reports'), async r => {
      if (r.request().method() !== 'GET') return r.continue()
      const res = await r.fetch(); const body = await res.json()
      await r.fulfill({ json: body.map((x, i) => i % 2 ? { ...x, my_capability: 'view', is_mine: false, created_by: 99 } : x) })
    })
  }
  await page.goto(BASE + '/reports')
  await page.waitForTimeout(3000)
  if (sc.act) { try { await sc.act(page) } catch (e) { errors.push('act: ' + String(e).slice(0, 100)) } await page.waitForTimeout(900) }
  await page.screenshot({ path: path.join(OUT, `dash-${sc.name}-${suffix}.png`) })
  console.log(`dash-${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
