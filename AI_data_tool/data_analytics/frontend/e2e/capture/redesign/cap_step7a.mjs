import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')

/**
 * Redesign 7a: Home in each state × light / dark / Arabic / Arabic dark, full
 * page at 1440 wide (the prototype's desktop frame). States other than `full`
 * use browser-only data (page.route): the dev database has no refresh runs and
 * only a few audit rows. Usage: node cap_step7a.mjs <outdir> [state]; ONE=1 for
 * light only.
 */

const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
// Tall enough for the whole page: the app scrolls inside its main column, so a
// full-page screenshot of a 900px window would stop at the fold.
const VIEW = { width: 1440, height: 2000 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(([s]) => !process.env.ONE || s === 'light')
const at = p => u => new URL(u).pathname === p
const ago = m => new Date(Date.now() - m * 60000).toISOString()

const ACTIVITY = [
  { id: 905, user_email: 'sara@example.com', action: 'report.publish', entity: 'report', entity_id: 1, detail: null, created_at: ago(12) },
  { id: 904, user_email: 'omar@example.com', action: 'report.share', entity: 'report', entity_id: 2, detail: 'finance@example.com', created_at: ago(40) },
  { id: 903, user_email: 'admin@datalytics.local', action: 'dataset.upload', entity: 'dataset', entity_id: 1, detail: 'sales.csv -> 2,000 rows, 13 columns', created_at: ago(180) },
  { id: 902, user_email: 'sara@example.com', action: 'report.create', entity: 'report', entity_id: 3, detail: 'Regional review', created_at: ago(300) },
]
const RUNS = [
  { id: 3, kind: 'dataset', item_id: 6, name: 'Demo — Live Orders', trigger: 'schedule', status: 'failed', started_at: ago(12), finished_at: ago(11), rows: null, duration_ms: 30000, error: 'connection timed out', error_code: 'timeout' },
  { id: 2, kind: 'dataflow', item_id: 1, name: 'Nightly sales', trigger: 'schedule', status: 'running', started_at: ago(3), finished_at: null, rows: null, duration_ms: null, error: null, error_code: null },
  ...Array.from({ length: 14 }, (_, i) => ({ id: 10 + i, kind: 'dataset', item_id: 1, name: 'Demo — Sales', trigger: 'schedule', status: 'ok', started_at: ago(60 + i * 60), finished_at: ago(59 + i * 60), rows: 2000, duration_ms: 900, error: null, error_code: null })),
]

const screens = [
  { name: 'full' },
  { name: 'sample', fake: 'admin' },
  { name: 'firstrun', fake: 'empty' },
  { name: 'loading', fake: 'loading' },
  { name: 'error', fake: 'error' },
  { name: 'offline', fake: 'offline' },
  { name: 'member', fake: 'member' },
  { name: 'section-errors', fake: 'sections' },
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
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => errors.push(String(e).slice(0, 140)))
  if (sc.fake === 'admin') {
    await page.route(at('/api/v1/admin/audit-log'), r => r.fulfill({ json: ACTIVITY }))
    await page.route(at('/api/v1/admin/monitoring/refresh-runs'), r => r.fulfill({ json: RUNS }))
  }
  if (sc.fake === 'empty') {
    for (const p of ['/api/v1/reports', '/api/v1/datasets', '/api/v1/data-sources', '/api/v1/reports/recent',
      '/api/v1/admin/audit-log', '/api/v1/admin/monitoring/refresh-runs', '/api/v1/agent/conversations'])
      await page.route(at(p), r => r.request().method() === 'GET' ? r.fulfill({ json: [] }) : r.continue())
  }
  if (sc.fake === 'loading') await page.route(at('/api/v1/reports'), () => { /* never answers */ })
  if (sc.fake === 'error') await page.route(at('/api/v1/reports'), r => r.fulfill({ status: 500, json: { detail: 'Database unavailable' } }))
  if (sc.fake === 'sections') {
    for (const p of ['/api/v1/reports/recent', '/api/v1/admin/audit-log', '/api/v1/admin/monitoring/refresh-runs', '/api/v1/datasets/lineage/graph'])
      await page.route(at(p), r => r.fulfill({ status: 500, json: { detail: 'boom' } }))
  }
  if (sc.fake === 'offline') await page.route(at('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.auto_pick = null
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: false, error: 'connection refused' } }))
    await r.fulfill({ json: body })
  })
  if (sc.fake === 'member') await page.route(at('/api/v1/auth/me'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.role = { ...body.role, name: 'Analyst', is_org_admin: false }; body.is_super_admin = false
    await r.fulfill({ json: body })
  })
  await page.goto(BASE + '/')
  await page.waitForTimeout(sc.fake === 'offline' ? 6000 : 3500)
  await page.screenshot({ path: path.join(OUT, `home-${sc.name}-${suffix}.png`) })
  console.log(`home-${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
