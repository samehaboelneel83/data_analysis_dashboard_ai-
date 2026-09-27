// The object-family journey (E08), clicked in a browser against a RUNNING
// stack: for each of the 24 families backend/tests/test_object_families.py
// pins at the API level, an author
//
//   1. picks the chart from the gallery,
//   2. assigns its roles and aggregation in the widget panel,
//   3. adds a filter in the panel,
//
// and then, for all of them together,
//
//   4. the dashboard is reopened (reload) and every tile draws, and
//   5. each tile's data is exported as CSV from its right-click menu.
//
// After step 3 the SAVED config is checked through the API: the roles and
// the filter the panel wrote are there, and the filter changes the answer.
//
//   node frontend/e2e/journeys/families_journey.mjs
//
// Environment: as release_journey.mjs (JOURNEY_BASE_URL, JOURNEY_API_URL,
// JOURNEY_EMAIL, JOURNEY_PASSWORD), plus JOURNEY_DATASET -- the name of an
// import dataset with the demo's Sales columns (default "Demo — Sales":
// product, region, revenue, cost, units, date). JOURNEY_FAMILIES narrows the
// run to a comma-separated list of types. Creates one dashboard and deletes
// it at the end. Output: demo_output/journeys/families-<timestamp>/.

import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..', '..', '..')
const BASE = (process.env.JOURNEY_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.JOURNEY_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.JOURNEY_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.JOURNEY_PASSWORD || 'demo-password'
const DATASET = process.env.JOURNEY_DATASET || 'Demo — Sales'
const OUT = path.join(ROOT, 'demo_output', 'journeys', 'families-' + new Date().toISOString().replace(/[:.]/g, '-'))
fs.mkdirSync(OUT, { recursive: true })
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const expect = (cond, message) => { if (!cond) throw new Error(message) }

/** The families, as test_object_families.py configures them, in the demo's
 *  column names. Keys are ROLES (as the panel's fields are named), plus the
 *  aggregation and a date grouping where the family uses one. */
const FAMILIES = {
  bar:           { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  line:          { roles: { category: 'date', measure: 'revenue' }, agg: 'sum', granularity: 'month' },
  area:          { roles: { category: 'product', measure: 'units' }, agg: 'sum' },
  step:          { roles: { category: 'date', measure: 'units' }, agg: 'sum', granularity: 'quarter' },
  pie:           { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  donut:         { roles: { category: 'product', measure: 'cost' }, agg: 'avg' },
  treemap:       { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  funnel:        { roles: { category: 'product', measure: 'units' }, agg: 'sum' },
  dot_plot:      { roles: { category: 'product', measure: 'units' }, agg: 'sum' },
  word_cloud:    { roles: { category: 'product', measure: 'units' }, agg: 'sum' },
  waterfall:     { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  table:         { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  crosstab:      { roles: { category: 'product', category2: 'channel', measure: 'revenue' }, agg: 'sum' },
  matrix:        { roles: { category: 'product', category2: 'channel', measure: 'units' }, agg: 'avg' },
  heatmap:       { roles: { category: 'product', category2: 'channel', measure: 'revenue' }, agg: 'sum' },
  list:          { roles: { category: 'product', measure: 'revenue' }, agg: 'sum' },
  kpi:           { roles: { measure: 'revenue' }, agg: 'sum' },
  card:          { multi: { measures: ['revenue', 'cost'] }, agg: 'sum' },
  gauge:         { roles: { measure: 'units' }, agg: 'avg' },
  histogram:     { roles: { measure: 'revenue' } },
  box_plot:      { roles: { category: 'product', measure: 'revenue' } },
  butterfly:     { roles: { category: 'product', measure: 'revenue', measure2: 'cost' }, agg: 'sum' },
  dual_axis_bar: { roles: { category: 'product', measure: 'revenue', measure2: 'units' }, agg: 'sum' },
  bubble:        { roles: { category: 'product', measure: 'revenue', measure2: 'cost', size: 'units' }, agg: 'sum' },
}
const ROLE_KEY = { category: 'dimension', category2: 'dimension2' }
const keyOf = role => ROLE_KEY[role] ?? role

async function api(method, url, token, body) {
  const r = await fetch(API + url, {
    method, body: body === undefined ? undefined : JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
      ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  const text = await r.text()
  let json = null
  try { json = text ? JSON.parse(text) : null } catch { json = text }
  return { status: r.status, json }
}

const results = []          // one row per family: which step failed, if any
let token = null
let reportId = null

async function main() {
  token = (await api('POST', '/auth/login', null, { email: EMAIL, password: PASSWORD })).json?.access_token
  expect(token, 'admin login failed')
  const ds = ((await api('GET', '/datasets', token)).json ?? []).find(d => d.name === DATASET)
  expect(ds, `no dataset named ${DATASET}`)
  // A filter value the data has: the first region.
  const probe = await api('POST', `/datasets/${ds.id}/widget-data`, token,
    { widget_type: 'bar', config: { dimension: 'region', aggregation: 'count', limit: 1 } })
  const region = probe.json?.rows?.[0]?.name
  expect(region, `no region value to filter on: ${JSON.stringify(probe.json).slice(0, 200)}`)
  const rep = await api('POST', '/reports', token, { name: `E2E families ${Date.now() % 100000}`, dataset_id: ds.id })
  expect(rep.status === 201 || rep.status === 200, `report: ${rep.status}`)
  reportId = rep.json.id
  const pageId = (await api('GET', `/reports/${reportId}`, token)).json.pages[0].id
  const widgetsNow = async () => (await api('GET', `/reports/${reportId}`, token)).json.pages[0].widgets ?? []

  const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE } : {})
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, acceptDownloads: true })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  try {
    await page.goto(`${BASE}/login`)
    await page.getByLabel(/^email$/i).fill(EMAIL)
    await page.getByLabel(/^password$/i).fill(PASSWORD)
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await page.waitForURL(u => !String(u).includes('/login'), { timeout: 15000 })
    await page.goto(`${BASE}/reports/${reportId}`).catch(() => page.goto(`${BASE}/reports/${reportId}`))
    await page.locator('[data-testid="view-strip"]').waitFor({ timeout: 90000 })

    const only = (process.env.JOURNEY_FAMILIES || '').split(',').map(s => s.trim()).filter(Boolean)
    const families = Object.entries(FAMILIES).filter(([t]) => !only.length || only.includes(t))
    for (const [type, spec] of families) {
      const row = { family: type, ok: false, failed: null, detail: null }
      results.push(row)
      const at = async (stepName, fn) => {
        try { return await fn() } catch (e) { row.failed = stepName; row.detail = String(e?.message ?? e).slice(0, 600); throw e }
      }
      try {
        const before = new Set((await widgetsNow()).map(w => w.id))
        // 1. pick it from the gallery
        let id
        await at('insert', async () => {
          const tab = page.getByRole('tab', { name: 'Charts', exact: true })
          if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click()
          await page.locator(`[data-widget-type="${type}"]`).first().click()
          for (let i = 0; i < 40 && !id; i++) {
            await page.waitForTimeout(250)
            id = (await widgetsNow()).find(w => !before.has(w.id) && w.widget_type === type)?.id
          }
          expect(id, 'no widget was created')
        })
        // 2. roles in the Assign data dialog, then aggregation in the panel
        await at('assign roles', async () => {
          // An inserted chart that still needs data opens the dialog by itself;
          // one that needs nothing is given its data from the pane's button.
          const dialog = page.getByRole('dialog', { name: /^Assign data/ })
          const opened = await dialog.waitFor({ timeout: 4000 }).then(() => true, () => false)
          if (!opened) await page.getByRole('button', { name: /^Assign data$/ }).click()
          for (const [role, col] of Object.entries(spec.roles ?? {})) {
            const field = dialog.locator(`[data-role="${role}"] select`)
            await field.waitFor({ timeout: 10000 })
            await field.selectOption(col)
          }
          for (const [role, cols] of Object.entries(spec.multi ?? {})) {
            for (const col of cols) {
              await dialog.locator(`[data-role="${role}"] label`, { hasText: new RegExp(`^${col}`) })
                .locator('input[type="checkbox"]').check()
            }
          }
          if (spec.granularity) await dialog.locator('#date-granularity').selectOption(spec.granularity)
          await dialog.getByRole('button', { name: 'Done' }).click()
          // The panel opens on "Data roles" after an insert; the rest is under "All".
          await page.getByRole('tablist', { name: 'Settings sections' }).getByRole('tab', { name: 'All', exact: true }).click()
          if (spec.agg) await page.locator('#cfg-aggregation').selectOption(spec.agg)
          await page.waitForTimeout(1200)                        // the panel saves after 600 ms
          const cfg = (await widgetsNow()).find(w => w.id === id)?.config ?? {}
          for (const [role, col] of Object.entries(spec.roles ?? {})) {
            expect(cfg[keyOf(role)] === col, `${keyOf(role)} saved as ${JSON.stringify(cfg[keyOf(role)])}`)
          }
          for (const [role, cols] of Object.entries(spec.multi ?? {})) {
            expect(JSON.stringify(cfg[role]) === JSON.stringify(cols), `${role} saved as ${JSON.stringify(cfg[role])}`)
          }
          if (spec.agg) expect(cfg.aggregation === spec.agg, `aggregation saved as ${cfg.aggregation}`)
        })
        // 3. a filter, in the panel
        await at('filter', async () => {
          const group = page.getByRole('button', { name: /^Filters/, expanded: false })
          if (await group.count()) await group.first().click()     // collapsed by default
          await page.getByRole('button', { name: '+ Add filter' }).click()
          await page.getByLabel('Filter 1 column').selectOption('region')
          await page.getByLabel('Filter 1 operator').selectOption('eq')
          await page.getByLabel('Filter 1 value').fill(region)
          await page.waitForTimeout(1200)
          const cfg = (await widgetsNow()).find(w => w.id === id)?.config ?? {}
          // By value, not by JSON text: the panel writes the keys in its own order.
          const f0 = Array.isArray(cfg.filters) && cfg.filters.length === 1 ? cfg.filters[0] : {}
          expect(f0.column === 'region' && f0.op === 'eq' && f0.value === region,
            `filters saved as ${JSON.stringify(cfg.filters)}`)
          const { filters, ...unfiltered } = cfg
          const a = await api('POST', `/datasets/${ds.id}/widget-data`, token, { widget_type: type, config: cfg, report_id: reportId })
          const b = await api('POST', `/datasets/${ds.id}/widget-data`, token, { widget_type: type, config: unfiltered, report_id: reportId })
          expect(a.status === 200 && b.status === 200, `widget-data ${a.status}/${b.status}`)
          expect(a.json?.type !== 'error', `the saved widget does not run: ${JSON.stringify(a.json).slice(0, 200)}`)
          expect(JSON.stringify(a.json?.rows) !== JSON.stringify(b.json?.rows)
                 || JSON.stringify(a.json) !== JSON.stringify(b.json), 'the filter changed nothing')
        })
        row.ok = true
        log('PASS', type)
      } catch {
        log('FAIL', type, '-', row.failed, row.detail)
        await page.screenshot({ path: path.join(OUT, `fail_${type}.png`) }).catch(() => {})
      }
    }

    // 4. reopen: every tile that passed draws, with no error on it
    await page.reload()
    await page.locator('[data-testid="view-strip"]').waitFor({ timeout: 90000 })
    await page.waitForTimeout(4000)
    await page.screenshot({ path: path.join(OUT, 'reopened.png'), fullPage: true })
    const widgets = await widgetsNow()
    for (const row of results.filter(r => r.ok)) {
      const w = widgets.find(x => x.widget_type === row.family)
      const tile = page.locator(`[data-widget-id="${w.id}"]`)
      try {
        await tile.scrollIntoViewIfNeeded()
        await tile.locator('svg, table, canvas, [data-testid="result-kpi"], [role="img"]').first().waitFor({ timeout: 15000 })
        const text = (await tile.innerText()).toLowerCase()
        expect(!/could not|failed to|error loading|something went wrong/.test(text), `tile says: ${text.slice(0, 120)}`)
      } catch (e) {
        row.ok = false; row.failed = 'reopen'; row.detail = String(e?.message ?? e).slice(0, 300)
        log('FAIL', row.family, '- reopen', row.detail)
        continue
      }
      // 5. export from the tile's own menu
      try {
        await tile.click({ button: 'right', position: { x: 40, y: 60 } })
        const [download] = await Promise.all([
          page.waitForEvent('download', { timeout: 20000 }),
          page.getByRole('menuitem', { name: /Export data as CSV/ }).click(),
        ])
        const file = path.join(OUT, `${row.family}.csv`)
        await download.saveAs(file)
        const lines = fs.readFileSync(file, 'utf8').replace(/^﻿/, '').split(/\r?\n/).filter(Boolean)
        expect(lines.length >= 2, `export has ${lines.length} lines`)
        row.exported = lines.length - 1
      } catch (e) {
        row.ok = false; row.failed = 'export'; row.detail = String(e?.message ?? e).slice(0, 300)
        log('FAIL', row.family, '- export', row.detail)
        await page.keyboard.press('Escape').catch(() => {})
      }
    }
    if (errors.length) results.push({ family: '(page)', ok: false, failed: 'uncaught page errors', detail: errors.slice(0, 5) })
  } finally {
    await browser.close()
  }
}

try {
  await main()
} catch (e) {
  results.push({ family: '(setup)', ok: false, failed: 'setup', detail: String(e?.message ?? e) })
  log('FAIL setup -', String(e?.message ?? e))
} finally {
  if (token && reportId && !process.env.JOURNEY_KEEP) await api('DELETE', `/reports/${reportId}`, token).catch(() => {})
  fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify(results, null, 2))
  const failed = results.filter(r => !r.ok)
  log(`${results.length - failed.length} of ${results.length} families passed -- ${OUT}`)
  process.exitCode = failed.length ? 1 : 0
}
