// A browser journey through a queued database import (E07/E12), with an
// accessibility pass over the connection browser (E10), against a RUNNING
// stack. The hand-over's owner action "try a queued import in the browser",
// automated.
//
//   node frontend/e2e/journeys/import_journey.mjs
//
// Environment: as release_journey.mjs (JOURNEY_BASE_URL, JOURNEY_API_URL,
// JOURNEY_EMAIL, JOURNEY_PASSWORD), plus JOURNEY_CONNECTION -- the name of a
// connection to browse (default: the first one listed). The admin must be
// able to import from it.
//
// It imports one table as "E2E Journey import <n>" and deletes that dataset
// at the end. Output: demo_output/journeys/<timestamp>/.

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
const OUT = path.join(ROOT, 'demo_output', 'journeys', 'import-' + new Date().toISOString().replace(/[:.]/g, '-'))
fs.mkdirSync(OUT, { recursive: true })
const NAME = `E2E Journey import ${Date.now() % 100000}`
const results = []
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const expect = (cond, message) => { if (!cond) throw new Error(message) }

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

async function step(name, fn) {
  try {
    results.push({ step: name, ok: true, detail: (await fn()) ?? null })
    log('PASS', name)
  } catch (e) {
    results.push({ step: name, ok: false, detail: String(e?.message ?? e) })
    log('FAIL', name, '-', String(e?.message ?? e))
  }
}

async function axe(page, where, context) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const found = await page.evaluate(async sel => {
    const r = await window.axe.run(sel ? document.querySelector(sel) : document, { resultTypes: ['violations'] })
    return r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
      .map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help,
                   targets: v.nodes.slice(0, 3).map(n => n.target.join(' ')) }))
  }, context)
  fs.writeFileSync(path.join(OUT, `axe_${where}.json`), JSON.stringify(found, null, 2))
  return found
}

let token = null
let datasetId = null

async function main() {
  token = (await api('POST', '/auth/login', null, { email: EMAIL, password: PASSWORD })).json?.access_token
  expect(token, 'admin login failed')
  const sources = (await api('GET', '/data-sources', token)).json ?? []
  const source = sources.find(s => s.name === process.env.JOURNEY_CONNECTION) ?? sources[0]
  expect(source, 'no connection to browse')

  const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE } : {})
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  try {
    await page.goto(`${BASE}/login`)
    await page.getByLabel(/^email$/i).fill(EMAIL)
    await page.getByLabel(/^password$/i).fill(PASSWORD)
    await page.getByRole('button', { name: /^sign in$/i }).click()
    await page.waitForURL(u => !String(u).includes('/login'), { timeout: 15000 })

    let table = null
    await step('the connection browser opens and lists tables', async () => {
      await page.goto(`${BASE}/connections`)
      const card = page.getByText(source.name, { exact: true }).first()
      await card.waitFor({ timeout: 15000 })
      await page.getByRole('button', { name: 'Browse' }).first().click()
      const dialog = page.getByRole('dialog', { name: `Browse ${source.name}` })
      await dialog.waitFor({ timeout: 10000 })
      await page.waitForTimeout(1500)
      const names = await dialog.getByRole('button').allTextContents()
      table = names.map(s => s.trim()).find(s => /^[A-Za-z_][\w.]*$/.test(s) && !/^(Import|DirectQuery|Run)$/i.test(s))
      expect(table, `no table button found among: ${names.join(' | ')}`)
      await dialog.getByRole('button', { name: table, exact: true }).click()
      await dialog.getByRole('button', { name: /Import as Dataset/ }).waitFor({ timeout: 15000 })
      return { table }
    })

    await step('the connection browser has no serious or critical accessibility violations', async () => {
      const found = await axe(page, 'connection_browser', '[role="dialog"]')
      expect(found.length === 0, found.map(v => `${v.id} (${v.nodes}): ${v.targets.join(', ')}`).join('; '))
    })

    await step('an import is queued, runs, and lands on the new dataset', async () => {
      const dialog = page.getByRole('dialog', { name: `Browse ${source.name}` })
      await dialog.getByPlaceholder('Dataset name…').fill(NAME)
      await dialog.getByRole('button', { name: /Import as Dataset/ }).click()
      // Queued: the dialog follows the job ("Waiting to start" / "Importing").
      await dialog.getByText(/Waiting to start|Importing|Done/).first().waitFor({ timeout: 15000 })
      await page.screenshot({ path: path.join(OUT, '01_import_queued.png') })
      // Done: the app opens the new dataset, as an upload does.
      await page.waitForURL(/\/datasets\/\d+\?new=1/, { timeout: 90000 })
      await page.screenshot({ path: path.join(OUT, '02_import_done.png') })
      datasetId = Number(new URL(page.url()).pathname.split('/').pop())
      const ds = (await api('GET', `/datasets/${datasetId}`, token)).json
      expect(ds?.name === NAME, `landed on ${ds?.name}`)
      expect((ds.row_count ?? 0) > 0, `row_count ${ds.row_count}`)
      return { dataset: ds.id, rows: ds.row_count }
    })

    await step('the job is listed with its outcome', async () => {
      const jobs = (await api('GET', '/jobs', token)).json ?? []
      const job = jobs.find(j => (j.subject ?? '').includes(NAME))
      expect(job && job.state === 'succeeded', `job: ${JSON.stringify(job)}`)
      expect(job.result?.dataset_id === datasetId, 'the job does not point at the dataset')
    })

    if (errors.length) results.push({ step: 'no uncaught page errors', ok: false, detail: errors.slice(0, 5) })
  } finally {
    await browser.close()
  }
}

try {
  await main()
} catch (e) {
  results.push({ step: 'setup', ok: false, detail: String(e?.message ?? e) })
  log('FAIL setup -', String(e?.message ?? e))
} finally {
  if (token && datasetId) await api('DELETE', `/datasets/${datasetId}`, token).catch(() => {})
  fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify(results, null, 2))
  const failed = results.filter(r => !r.ok).length
  log(`${results.length - failed} passed, ${failed} failed -- ${OUT}`)
  process.exitCode = failed ? 1 : 0
}
