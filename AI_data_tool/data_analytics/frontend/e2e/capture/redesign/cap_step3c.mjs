import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')
const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const VIEW = { width: 1440, height: 1000 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const CHECKS = [
  { id: 901, kind: 'rule', column: 'revenue', params: { expression: 'revenue >= 0' }, severity: 'warn', enabled: true, created_at: null },
  { id: 902, kind: 'rule', column: 'margin_pct', params: { expression: 'margin_pct <= 100' }, severity: 'warn', enabled: true, created_at: null },
  { id: 903, kind: 'not_null', column: 'date', params: {}, severity: 'block', enabled: true, created_at: null },
  { id: 904, kind: 'accepted_values', column: 'region', params: { values: ['Asia Pacific', 'Europe', 'Americas', 'Africa'] }, severity: 'block', enabled: true, created_at: null },
]
const AGGS = [
  { dataset: { id: 991, name: 'orders_by_region_day', row_count: 1460, refresh_interval_minutes: 60, last_refreshed_at: new Date().toISOString(),
      aggregate_spec: { grain: ['region', 'day(order_date)'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } }, last_error: null, attempts: 0 },
  { dataset: { id: 992, name: 'orders_by_product_month', row_count: 252, refresh_interval_minutes: 1440,
      aggregate_spec: { grain: ['region', 'product', 'month'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }, { column: 'qty', agg: 'sum', name: 'qty_sum' }] } },
    last_error: 'Not refreshed: the source query changed', attempts: 2 },
]
const screens = [
  { name: 'columns-full', id: 1, tab: 'columns' },
  { name: 'data-full', id: 1, tab: 'data' },
  { name: 'analysis-full', id: 1, tab: 'analysis' },
  { name: 'rules-full', id: 1, tab: 'rules', fake: 'checks' },
  { name: 'models-full', id: 1, tab: 'models' },
  { name: 'models-empty', id: 7, tab: 'models' },
  { name: 'aggregates-directquery', id: 6, tab: 'aggregates', fake: 'aggs' },
  { name: 'share-dialog', id: 1, tab: 'rules', fake: 'checks', share: true },
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
  if (sc.fake === 'checks') {
    await page.route(at(`/api/v1/datasets/${sc.id}/checks`), r => r.request().method() === 'GET'
      ? r.fulfill({ json: CHECKS }) : r.continue())
    await page.route(at(`/api/v1/datasets/${sc.id}/checks/try`), r => r.fulfill({ json: { rows: 2000, results: [
      { id: 901, kind: 'rule', column: 'revenue', severity: 'warn', passed: true, detail: null },
      { id: 902, kind: 'rule', column: 'margin_pct', severity: 'warn', passed: false, failing: 3, detail: '3 rows fail' },
      { id: 903, kind: 'not_null', column: 'date', severity: 'block', passed: true, detail: null },
      { id: 904, kind: 'accepted_values', column: 'region', severity: 'block', passed: true, detail: null }] } }))
  }
  if (sc.fake === 'aggs') await page.route(at(`/api/v1/datasets/${sc.id}/aggregates`), r => r.request().method() === 'GET' ? r.fulfill({ json: AGGS }) : r.continue())
  await page.goto(`${BASE}/datasets/${sc.id}?tab=${sc.tab}`)
  await page.locator('h1').first().waitFor({ timeout: 30000 })
  await page.waitForTimeout(2500)
  if (sc.tab === 'data') await page.locator('.dl-data3__main table').waitFor({ timeout: 90000 }).catch(() => {})
  if (sc.tab === 'rules' && !sc.share) {
    const run = page.locator('.dl-rules__actions button').first()
    if (await run.count()) { await run.click(); await page.waitForTimeout(800) }
  }
  if (sc.share) { await page.locator('.dl-dsd__actions button', { hasText: /Share|مشاركة/ }).first().click(); await page.waitForTimeout(1500) }
  await page.screenshot({ path: path.join(OUT, `${sc.name}-${suffix}.png`) })
  console.log(`${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
