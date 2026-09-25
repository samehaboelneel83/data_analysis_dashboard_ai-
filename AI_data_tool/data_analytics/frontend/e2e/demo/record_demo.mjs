// Datalytics demo recorder: a realistic, human-paced walkthrough, captured on video.
//
// It uses the plain `playwright` library that frontend/ already depends on
// (the same one scripts/bench_pageload.mjs uses); there is no @playwright/test runner here.
//
// Run from anywhere (Windows: double-click e2e\demo\run_demo.cmd):
//   node frontend/e2e/demo/record_demo.mjs
//
// Environment (all optional):
//   DEMO_BASE_URL   frontend origin              default http://localhost:3001
//   DEMO_API_URL    API base                     default http://localhost:8000/api/v1
//   DEMO_EMAIL      login email                  default admin@datalytics.local
//   DEMO_PASSWORD   login password               default demo-password
//   DEMO_HEADED=1   show the browser window while recording
//
// Only DEMO_-prefixed items are created, and all of them are removed at the end
// (leftovers from an earlier interrupted run are swept first). The video ends up in
//   <data_analytics>/demo_output/datalytics_demo.webm  (+ .mp4 when ffmpeg is on PATH)

import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// The frontend's own playwright (1.6x) needs Node 20+. On an older Node, run_demo.cmd
// installs a Node-18-compatible playwright into demo_output/.pw and points DEMO_PW_DIR at it.
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..', '..', '..')           // .../data_analytics
const OUT = path.join(ROOT, 'demo_output')
const RAW = path.join(OUT, 'raw')
const WEBM = path.join(OUT, 'datalytics_demo.webm')
const MP4 = path.join(OUT, 'datalytics_demo.mp4')

const BASE = (process.env.DEMO_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.DEMO_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.DEMO_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.DEMO_PASSWORD || 'demo-password'

const PREFIX = 'DEMO_'
const CONN_NAME = 'DEMO_Connection'
const DS_NAME = 'DEMO_Sales'
const DASH_NAME = 'DEMO_Dashboard'
const QUESTION = 'What is the total revenue by region?'

const W = 1920, H = 1080
const t0 = Date.now()
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s]`, ...a)
const problems = []

fs.mkdirSync(RAW, { recursive: true })

// ---------------------------------------------------------------- API helpers
// The app authenticates with an httpOnly session cookie (plus the X-Requested-With
// CSRF header on writes), so API calls go through the browser context and share its cookies.
let signedIn = false
async function api(method, p, body, { form = false } = {}) {
  const opts = { method, headers: { 'X-Requested-With': 'XMLHttpRequest' }, failOnStatusCode: false }
  if (form) opts.multipart = body
  else if (body !== undefined) opts.data = body
  const r = await context.request.fetch(API + p, opts)
  const text = await r.text()
  if (!r.ok()) throw new Error(`${method} ${p} -> ${r.status()} ${text.slice(0, 300)}`)
  return text ? JSON.parse(text) : null
}
const asList = x => (Array.isArray(x) ? x : x?.items || x?.results || [])

// Only ever deletes items whose name starts with DEMO_.
async function sweepDemoItems(label) {
  const done = []
  const kinds = [
    ['/reports', '/reports'],
    ['/datasets', '/datasets'],
    ['/data-sources', '/data-sources'],
  ]
  for (const [listPath, delPath] of kinds) {
    try {
      for (const it of asList(await api('GET', listPath))) {
        if (typeof it?.name === 'string' && it.name.startsWith(PREFIX)) {
          await api('DELETE', `${delPath}/${it.id}`)
          done.push(`${delPath}/${it.id} (${it.name})`)
        }
      }
    } catch (e) { problems.push(`${label} sweep ${listPath}: ${e.message}`) }
  }
  if (done.length) log(`${label}: removed`, done.join(', '))
  return done
}

function demoCsv() {
  const regions = ['North', 'South', 'East', 'West']
  const products = ['Laptops', 'Phones', 'Tablets', 'Accessories']
  const rows = ['order_date,region,product,units,revenue']
  let seed = 7
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  for (let m = 0; m < 12; m++) {
    for (const r of regions) for (const p of products) {
      const units = 20 + Math.round(rnd() * 80 + m * 3)
      const price = { Laptops: 900, Phones: 650, Tablets: 420, Accessories: 45 }[p]
      const d = `2025-${String(m + 1).padStart(2, '0')}-15`
      rows.push(`${d},${r},${p},${units},${(units * price * (0.9 + rnd() * 0.2)).toFixed(2)}`)
    }
  }
  return rows.join('\n') + '\n'
}

// ------------------------------------------------------------- page helpers
const pause = (page, ms = 1200) => page.waitForTimeout(ms)

// A visible cursor and a caption strip: headless video shows neither by default.
const OVERLAY = () => {
  const install = () => {
    if (document.getElementById('__demo_cursor')) return
    const c = document.createElement('div')
    c.id = '__demo_cursor'
    c.style.cssText = 'position:fixed;left:-40px;top:-40px;width:22px;height:22px;border-radius:50%;' +
      'background:rgba(37,99,235,.35);border:2px solid #2563eb;pointer-events:none;z-index:2147483647;' +
      'transform:translate(-50%,-50%);transition:left .18s ease,top .18s ease,transform .12s'
    document.documentElement.appendChild(c)
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px' }, true)
    addEventListener('mousedown', () => { c.style.transform = 'translate(-50%,-50%) scale(.7)' }, true)
    addEventListener('mouseup', () => { c.style.transform = 'translate(-50%,-50%)' }, true)
  }
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', install)
  else install()
}

async function caption(page, text) {
  log('▶', text)
  await page.evaluate(t => {
    let el = document.getElementById('__demo_caption')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_caption'
      el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483646;' +
        'background:rgba(15,23,42,.88);color:#fff;font:600 20px/1.3 system-ui,Segoe UI,sans-serif;' +
        'padding:10px 22px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.25);pointer-events:none;' +
        'transition:opacity .3s;direction:ltr'
      document.documentElement.appendChild(el)
    }
    el.textContent = t
    el.style.opacity = '1'
  }, text).catch(() => {})
}

// Move the mouse to the element first so the cursor glides there, then click.
async function humanClick(page, locator, opts = {}) {
  await locator.waitFor({ state: 'visible', timeout: opts.timeout ?? 15000 })
  await locator.scrollIntoViewIfNeeded().catch(() => {})
  const box = await locator.boundingBox()
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 })
  await pause(page, 250)
  await locator.click({ timeout: opts.timeout ?? 15000 })
}

async function humanType(page, locator, text) {
  await humanClick(page, locator)
  await locator.fill('')
  await locator.pressSequentially(text, { delay: 70 })
}

async function step(page, name, fn) {
  try { await fn() }
  catch (e) {
    const shot = path.join(OUT, `fail_${name.replace(/\W+/g, '_')}.png`)
    await page.screenshot({ path: shot }).catch(() => {})
    problems.push(`${name}: ${e.message.split('\n')[0]}`)
    log(`!! step "${name}" failed:`, e.message.split('\n')[0], `(screenshot ${path.basename(shot)})`)
  }
}

async function launch() {
  const opts = { headless: !process.env.DEMO_HEADED, slowMo: 500, args: [`--window-size=${W},${H}`] }
  for (const extra of [{}, { channel: 'msedge' }, { channel: 'chrome' }]) {
    try { return await chromium.launch({ ...opts, ...extra }) }
    catch (e) { log(`launch ${extra.channel || 'bundled chromium'} failed: ${e.message.split('\n')[0]}`) }
  }
  throw new Error('No usable browser (run: npx playwright install chromium)')
}

// ===================================================================== main
const ids = { conn: null, ds: null, report: null, conv: null }
let browser, context, page

try {
  browser = await launch()
  context = await browser.newContext({
    viewport: { width: W, height: H },
    recordVideo: { dir: RAW, size: { width: W, height: H } },
    locale: 'en-US',
  })
  await context.addInitScript(OVERLAY)
  // Always start in English; the Arabic switch later is part of the story.
  await context.addInitScript(() => {
    if (!sessionStorage.getItem('__demo_lang_set')) {
      localStorage.setItem('datalytics.language', 'en')
      localStorage.setItem('datalytics.direction', 'ltr')
      sessionStorage.setItem('__demo_lang_set', '1')
    }
  })
  page = await context.newPage()
  page.setDefaultTimeout(20000)
  page.on('response', async r => {
    try {
      if (r.request().method() === 'POST' && /\/agent\/conversations$/.test(r.url()) && r.ok()) {
        ids.conv = (await r.json())?.id ?? ids.conv
      }
    } catch { /* ignore */ }
  })

  // ---------------------------------------------------------------- 1. login
  await page.goto(`${BASE}/login`)
  await caption(page, 'Sign in to Datalytics')
  await pause(page, 1200)
  await humanType(page, page.locator('input[type=email]'), EMAIL)
  await humanType(page, page.locator('input[type=password]'), PASSWORD)
  await humanClick(page, page.locator('button[type=submit]'))
  await page.waitForURL(u => !u.pathname.startsWith('/login'), { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await api('GET', '/auth/me')   // proves the session cookie works for API calls too
  signedIn = true
  log('signed in as', EMAIL)
  await pause(page, 1500)

  // Off-camera prep: sweep old DEMO_ leftovers, then load the demo dataset.
  await sweepDemoItems('pre-run')
  {
    ids.ds = (await api('POST', '/datasets', {
      file: { name: 'DEMO_Sales.csv', mimeType: 'text/csv', buffer: Buffer.from(demoCsv()) },
      name: DS_NAME,
      description: 'Demo sales by month, region and product (created by the demo recorder)',
    }, { form: true })).id
    log('dataset', DS_NAME, '#' + ids.ds)
  }

  // ------------------------------------------------ 2. connection + test it
  await step(page, 'connection', async () => {
    await caption(page, 'Add a data connection and test it before saving')
    const nav = page.getByRole('link', { name: 'Connections', exact: true }).first()
    if (await nav.isVisible().catch(() => false)) await humanClick(page, nav)
    else await page.goto(`${BASE}/connections`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 1200)
    await humanClick(page, page.getByRole('button', { name: 'New Connection' }))
    const dlg = page.getByRole('dialog', { name: 'New connection' })
    await dlg.waitFor()
    await pause(page, 800)
    await humanType(page, dlg.getByPlaceholder('My Database'), CONN_NAME)
    const type = dlg.getByLabel('Type')
    await humanClick(page, type)
    await type.selectOption('sqlite')
    await pause(page, 900)
    await humanType(page, dlg.locator('input[name="conn-filepath"]'), '/tmp/DEMO_connection.db')
    await pause(page, 600)
    await humanClick(page, dlg.getByRole('button', { name: 'Test connection' }))
    const status = dlg.getByRole('status')
    await status.waitFor({ timeout: 30000 })
    await page.waitForFunction(() => !document.body.innerText.includes('Testing…'), null, { timeout: 30000 }).catch(() => {})
    log('test result:', (await status.innerText()).trim())
    await caption(page, 'Connection tested: the settings work')
    await pause(page, 2200)
    await humanClick(page, dlg.getByRole('button', { name: 'Create connection' }))
    await pause(page, 3000)
    await page.waitForLoadState('networkidle').catch(() => {})
    const conn = asList(await api('GET', '/data-sources')).find(c => c.name === CONN_NAME)
    ids.conn = conn?.id ?? null
    log('connection', CONN_NAME, '#' + ids.conn)
    await pause(page, 1500)
  })

  // ------------------------------------------------------ 3. preview dataset
  await step(page, 'dataset preview', async () => {
    await caption(page, 'Preview a dataset')
    const nav = page.getByRole('link', { name: 'Datasets', exact: true }).first()
    if (await nav.isVisible().catch(() => false)) await humanClick(page, nav)
    else await page.goto(`${BASE}/datasets`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 1500)
    const row = page.getByRole('link', { name: DS_NAME, exact: true }).first()
    if (await row.isVisible().catch(() => false)) await humanClick(page, row)
    else await page.goto(`${BASE}/datasets/${ids.ds}`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await caption(page, `${DS_NAME}: overview of columns and quality`)
    await pause(page, 2500)
    await page.mouse.wheel(0, 500); await pause(page, 1200)
    await page.mouse.wheel(0, -500); await pause(page, 800)
    const dataTab = page.getByRole('tablist', { name: 'Dataset sections' }).getByRole('tab', { name: 'Data' })
    await humanClick(page, dataTab)
    await page.waitForLoadState('networkidle').catch(() => {})
    await caption(page, 'The rows themselves')
    await pause(page, 3000)
  })

  // ------------------------------------------------------- 4. build dashboard
  await step(page, 'create dashboard', async () => {
    await caption(page, 'Create a dashboard')
    const nav = page.getByRole('link', { name: 'Dashboards', exact: true }).first()
    if (await nav.isVisible().catch(() => false)) await humanClick(page, nav)
    else await page.goto(`${BASE}/reports`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 1200)
    await humanClick(page, page.getByRole('button', { name: 'New dashboard' }))
    await page.waitForURL(/\/reports\/\d+/, { timeout: 20000 })
    ids.report = Number(page.url().match(/\/reports\/(\d+)/)[1])
    log('report #' + ids.report)
    const picker = page.getByRole('dialog', { name: 'Choose the data for this dashboard' })
    await picker.waitFor({ timeout: 15000 })
    await caption(page, 'Pick the data for it')
    await pause(page, 1200)
    await humanType(page, picker.getByRole('searchbox').or(picker.getByLabel('Search datasets')).first(), 'DEMO')
    await pause(page, 800)
    await humanClick(page, picker.getByRole('button', { name: new RegExp('^' + DS_NAME) }).first())
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 1500)
    await humanClick(page, page.getByRole('button', { name: 'Rename this dashboard' }))
    const nameBox = page.getByLabel('Dashboard name')
    await nameBox.fill('')
    await nameBox.pressSequentially(DASH_NAME, { delay: 70 })
    await nameBox.press('Enter')
    await pause(page, 1500)
  })

  const addVisual = async (tileLabel, label, fields) => {
    await step(page, `add ${label}`, async () => {
      await caption(page, `Add a ${label}`)
      const charts = page.getByRole('tablist', { name: 'Builder panel' }).getByRole('tab', { name: 'Charts' })
      if (await charts.isVisible().catch(() => false)) await humanClick(page, charts)
      const tile = page.locator(`button.dl-gallery__tile[aria-label="${tileLabel}"]`).first()
      await humanClick(page, tile)
      await pause(page, 1500)
      for (const [sel, value] of fields) {
        const s = page.locator(sel).first()
        await s.waitFor({ state: 'visible', timeout: 10000 })
        await humanClick(page, s)
        await s.selectOption(value)
        await pause(page, 900)
      }
      await page.getByText('Saved', { exact: true }).first().waitFor({ timeout: 8000 }).catch(() => {})
      await pause(page, 1500)
    })
  }
  const DIM = '#fld-dimension-group-x-axis, #dimension-select'
  const MEAS = '#fld-measure-numeric-column'
  if (ids.report) {
    await addVisual('KPI Card', 'KPI card: total revenue', [[MEAS, 'revenue']])
    await addVisual('Bar Chart', 'bar chart: revenue by region', [[DIM, 'region'], [MEAS, 'revenue']])
    await addVisual('Line Chart', 'line chart: revenue over time', [[DIM, 'order_date'], [MEAS, 'revenue']])
    await addVisual('Table', 'table: revenue by product', [[DIM, 'product'], [MEAS, 'revenue']])
    await addVisual('Slicer', 'filter (slicer) on region', [['#fld-field-to-filter-by', 'region']])

    // Safety net: anything the UI path did not produce is added through the API,
    // so the rest of the video still shows a complete dashboard.
    await step(page, 'verify widgets', async () => {
      const rep = await api('GET', `/reports/${ids.report}`)
      const pg = rep.pages?.[0]
      const have = new Set((pg?.widgets || []).map(w => w.widget_type))
      const want = {
        kpi: { measure: 'revenue', aggregation: 'sum' },
        bar: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
        line: { dimension: 'order_date', dimension_granularity: 'month', measure: 'revenue', aggregation: 'sum' },
        table: { dimension: 'product', measure: 'revenue', aggregation: 'sum' },
        slicer: { dimension: 'region' },
      }
      const missing = Object.keys(want).filter(k => !have.has(k))
      if (missing.length && pg) {
        problems.push(`widgets added via API fallback: ${missing.join(', ')}`)
        let y = 20
        for (const k of missing) {
          await api('POST', `/reports/${ids.report}/pages/${pg.id}/widgets`, {
            widget_type: k, config: { ...want[k], dataset_id: ids.ds }, layout: { x: 0, y, w: 6, h: 4 },
          })
          y += 4
        }
        await page.reload()
        await page.waitForLoadState('networkidle').catch(() => {})
      }
      log('widgets on page:', [...have].join(', '), missing.length ? `(+ fallback ${missing.join(', ')})` : '')
    })
  }

  // --------------------------------------------------- 5. view/edit + saved
  await step(page, 'view/edit', async () => {
    const group = page.getByRole('group', { name: 'Report mode' })
    await caption(page, 'Switch to View mode: what readers see')
    await humanClick(page, group.getByRole('button', { name: 'View mode' }))
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 3500)
    // Use the slicer like a reader would, if a value is clickable.
    const val = page.getByRole('figure').filter({ hasText: 'North' }).getByText('North', { exact: true }).first()
    if (await val.isVisible().catch(() => false)) {
      await caption(page, 'Filter the dashboard to one region')
      await humanClick(page, val).catch(() => {})
      await pause(page, 3000)
      await humanClick(page, val).catch(() => {})
      await pause(page, 1500)
    }
    await caption(page, 'Back to Edit mode')
    await humanClick(page, group.getByRole('button', { name: 'Edit mode' }))
    await pause(page, 2000)
    await caption(page, 'Every change is saved automatically')
    await page.getByText('Saved', { exact: true }).first().waitFor({ timeout: 10000 })
    const saved = page.getByText('Saved', { exact: true }).first()
    const box = await saved.boundingBox()
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 15 })
    await pause(page, 2500)
  })

  // ------------------------------------------------------------- 6. Ask AI
  await step(page, 'ask ai', async () => {
    await caption(page, 'Ask a question in plain language')
    const nav = page.getByRole('link', { name: 'Ask AI', exact: true }).first()
    if (await nav.isVisible().catch(() => false)) await humanClick(page, nav)
    else await page.goto(`${BASE}/ask`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 1200)
    // The scope picker is a searchable list: open it, then pick the option.
    await humanClick(page, page.getByRole('button', { name: 'What to ask about' }).first())
    await humanClick(page, page.locator(`[role=option][data-value="d:${ids.ds}"]`).first())
    await pause(page, 1200)
    await humanType(page, page.getByPlaceholder('Ask a question about this data…'), QUESTION)
    await pause(page, 600)
    await humanClick(page, page.getByRole('button', { name: 'Send' }))
    await caption(page, 'Datalytics works out the answer from the data')
    await Promise.race([
      page.locator('[data-testid=answer-source]').first().waitFor({ timeout: 150000 }),
      page.getByText('Could not answer that').first().waitFor({ timeout: 150000 }),
    ])
    await pause(page, 1500)
    await page.mouse.wheel(0, 400)
    await pause(page, 4000)
  })

  // ------------------------------------------------------------ 7. Arabic
  await step(page, 'arabic', async () => {
    await caption(page, 'Switch the whole interface to Arabic')
    await humanClick(page, page.getByRole('button', { name: 'Language: English' }))
    await pause(page, 900)
    await humanClick(page, page.getByRole('menuitemradio', { name: /العربية/ }).first())
    await page.waitForFunction(() => document.documentElement.dir === 'rtl', null, { timeout: 10000 })
    await pause(page, 2500)
  })

  // ----------------------------------------------- 8. back to the dashboards
  await step(page, 'dashboards list', async () => {
    await caption(page, 'Back to the dashboard list, now right-to-left')
    const nav = page.getByRole('link', { name: 'لوحات المعلومات' }).first()
    if (await nav.isVisible().catch(() => false)) await humanClick(page, nav)
    else await page.goto(`${BASE}/reports`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(page, 2000)
    const mine = page.getByText(DASH_NAME).first()
    if (await mine.isVisible().catch(() => false)) {
      const b = await mine.boundingBox()
      if (b) await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 15 })
    }
    await pause(page, 3500)
  })
} catch (e) {
  problems.push(`fatal: ${e.message.split('\n')[0]}`)
  log('FATAL', e.message)
  if (page) await page.screenshot({ path: path.join(OUT, 'fail_fatal.png') }).catch(() => {})
} finally {
  // -------------------------------------------------------- cleanup + video
  // Cleanup first: the API calls ride on the browser context's session cookie.
  if (signedIn && context) {
    if (ids.conv) await api('DELETE', `/agent/conversations/${ids.conv}`).then(() => log('removed conversation #' + ids.conv)).catch(e => problems.push(`cleanup conversation: ${e.message}`))
    await sweepDemoItems('cleanup')
    try {
      const left = []
      for (const p of ['/reports', '/datasets', '/data-sources']) {
        for (const it of asList(await api('GET', p))) if (String(it?.name).startsWith(PREFIX)) left.push(`${p}/${it.id}`)
      }
      log(left.length ? `!! DEMO_ items still present: ${left.join(', ')}` : 'cleanup verified: no DEMO_ items left')
      if (left.length) problems.push('cleanup incomplete: ' + left.join(', '))
    } catch (e) { problems.push(`cleanup check: ${e.message}`) }
  }
  let video = null
  try { video = page?.video() } catch { /* ignore */ }
  if (context) await context.close().catch(() => {})
  if (video) {
    try {
      await video.saveAs(WEBM)
      await video.delete().catch(() => {})
      log('video:', WEBM)
    } catch (e) { problems.push(`saving video: ${e.message}`) }
  }
  if (browser) await browser.close().catch(() => {})

  if (fs.existsSync(WEBM)) {
    const ff = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', WEBM, '-c:v', 'libx264', '-preset', 'medium',
      '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', MP4], { stdio: 'inherit' })
    if (ff.error) log('ffmpeg not found on PATH: keeping the .webm only')
    else if (ff.status === 0) log('mp4:', MP4)
    else problems.push(`ffmpeg exited ${ff.status}`)
  }
  try { fs.rmSync(RAW, { recursive: true, force: true }) } catch { /* ignore */ }

  log(problems.length ? `finished with ${problems.length} note(s):\n  - ${problems.join('\n  - ')}` : 'finished cleanly')
  fs.writeFileSync(path.join(OUT, 'last_run_status.txt'), problems.length ? problems.join('\n') + '\n' : 'OK\n')
  process.exitCode = problems.some(p => p.startsWith('fatal')) ? 1 : 0
}
