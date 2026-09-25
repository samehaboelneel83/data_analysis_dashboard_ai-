// Datalytics demo, Arabic edition: the same walkthrough as record_demo.mjs, recorded in
// the Arabic (RTL) interface, paced by an Egyptian-Arabic voice-over.
//
// Pipeline (run_demo_ar.cmd does all of it):
//   1. tts_ar.py clips      -> demo_output/narration/<step>.mp3 + durations.json
//   2. this script          -> demo_output/narration/raw_ar.webm + timeline.json
//      Each step starts its narration clock, does its clicks, then waits until the
//      clip (plus 0.7 s) has had time to finish -- the voice is never cut off.
//   3. merge_ar.py          -> demo_output/datalytics_demo_ar.mp4 + .srt  (needs ffmpeg)
//
// Only DEMO_-prefixed items are created, and all are removed at the end.

import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND = path.resolve(HERE, '..', '..')
const ROOT = path.resolve(FRONTEND, '..')
const OUT = path.join(ROOT, 'demo_output')
const NARR = path.join(OUT, 'narration')
const RAW = path.join(NARR, 'raw')

const BASE = (process.env.DEMO_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.DEMO_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.DEMO_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.DEMO_PASSWORD || 'demo-password'

const PREFIX = 'DEMO_'
// DEMO_LANG=en: the same walk in the English interface, with English data and question.
const EN_UI = process.env.DEMO_LANG === 'en'
const CONN_NAME = EN_UI ? 'DEMO_Sales Connection' : 'DEMO_اتصال المبيعات'
const DS_NAME = 'DEMO_Sales'
const DASH_NAME = EN_UI ? 'DEMO_Sales Dashboard' : 'DEMO_لوحة المبيعات'
const QUESTION = EN_UI ? 'What is the total revenue by region?' : 'إيه إجمالي الإيرادات لكل منطقة؟'
const FILTER_VALUE = EN_UI ? 'North' : 'الشمال'
// DEMO_CLEAN=1: same walk and pacing, but no caption strip (for a silent, subtitle-free cut).
const CLEAN = !!process.env.DEMO_CLEAN
const SUFFIX = (EN_UI ? '_en' : '') + (CLEAN ? '_clean' : '')
const PAD_MS = 1000   // ~0.7 s asked for, plus slack for the video clock

const W = 1920, H = 1080
const t0 = Date.now()
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1).padStart(6)}s]`, ...a)
const problems = []
fs.mkdirSync(RAW, { recursive: true })

// ------------------------------------------------------------ narration data
const narration = JSON.parse(fs.readFileSync(path.join(HERE, 'narration_ar.json'), 'utf8'))
let durations = {}
try { durations = JSON.parse(fs.readFileSync(path.join(NARR, 'durations.json'), 'utf8')) }
catch { log('!! no durations.json -- run tts_ar.py clips first; pacing falls back to 5 s per step') }

// ------------------------------------------------------ i18n-aware selectors
// Strings are matched in English OR their Arabic translation from the app's own
// catalogues, so the script keeps working whether a label is translated or not.
function catalogue(file) {
  const out = {}
  const src = fs.readFileSync(path.join(FRONTEND, 'src', 'i18n', file), 'utf8')
  for (const m of src.matchAll(/^\s*'([^']+)':\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"),\s*$/gm)) {
    out[m[1]] = (m[2] ?? m[3]).replace(/\\'/g, "'")
  }
  return out
}
const EN = catalogue('en.ts'), AR = catalogue('ar.ts')
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
/** Exact-match regex for an English UI string and every Arabic translation of it. */
function L(en, { exact = true } = {}) {
  const alts = new Set([en])
  for (const [k, v] of Object.entries(EN)) if (v === en && AR[k]) alts.add(AR[k])
  const body = [...alts].map(esc).join('|')
  return new RegExp(exact ? `^\\s*(?:${body})\\s*$` : `(?:${body})`)
}

// ---------------------------------------------------------------- API helpers
let context, page, browser
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

async function sweepDemoItems(label) {
  const done = []
  for (const p of ['/reports', '/datasets', '/data-sources']) {
    try {
      for (const it of asList(await api('GET', p))) {
        if (typeof it?.name === 'string' && it.name.startsWith(PREFIX)) {
          await api('DELETE', `${p}/${it.id}`)
          done.push(`${p}/${it.id}`)
        }
      }
    } catch (e) { problems.push(`${label} sweep ${p}: ${e.message}`) }
  }
  if (done.length) log(`${label}: removed`, done.join(', '))
}

function demoCsv() {
  const regions = EN_UI ? ['North', 'South', 'East', 'West'] : ['الشمال', 'الجنوب', 'الشرق', 'الغرب']
  const products = EN_UI
    ? { Laptops: 900, Phones: 650, Tablets: 420, Accessories: 45 }
    : { 'لابتوب': 900, 'موبايل': 650, 'تابلت': 420, 'إكسسوارات': 45 }
  const rows = ['order_date,region,product,units,revenue']
  let seed = 7
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  for (let m = 0; m < 12; m++) {
    for (const r of regions) for (const [p, price] of Object.entries(products)) {
      const units = 20 + Math.round(rnd() * 80 + m * 3)
      const d = `2025-${String(m + 1).padStart(2, '0')}-15`
      rows.push(`${d},${r},${p},${units},${(units * price * (0.9 + rnd() * 0.2)).toFixed(2)}`)
    }
  }
  return rows.join('\n') + '\n'
}

// ------------------------------------------------------------- page helpers
const pause = (ms = 1000) => page.waitForTimeout(ms)

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

/** Arabic caption strip: RTL, the app's Arabic face, semi-transparent. */
// Step marker: an 8x8 px square in the bottom-right corner whose grey level
// encodes the step number (16 + 10*i). Playwright's video clock drifts from the
// wall clock, so merge_ar.py reads the step starts from THESE pixels, frame by
// frame, and paints the corner over again in the final video.
async function caption(text, stepIndex = null) {
  await page.evaluate(([t, idx]) => {
    if (idx !== null) {
      let m = document.getElementById('__demo_marker')
      if (!m) {
        m = document.createElement('div')
        m.id = '__demo_marker'
        m.style.cssText = 'position:fixed;right:0;bottom:0;width:8px;height:8px;z-index:2147483647;pointer-events:none'
        document.documentElement.appendChild(m)
      }
      const g = 16 + idx * 10
      m.style.background = `rgb(${g},${g},${g})`
    }
    let el = document.getElementById('__demo_caption')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_caption'
      el.dir = 'rtl'
      el.lang = 'ar'
      el.style.cssText = 'position:fixed;left:50%;bottom:32px;transform:translateX(-50%);z-index:2147483646;' +
        'max-width:min(1400px,86vw);text-align:center;direction:rtl;unicode-bidi:isolate;' +
        "font:600 26px/1.6 'IBM Plex Sans Arabic','Segoe UI','Tahoma',sans-serif;color:#fff;" +
        'background:rgba(15,23,42,.72);padding:12px 28px;border-radius:14px;' +
        'box-shadow:0 8px 24px rgba(0,0,0,.25);pointer-events:none;transition:opacity .25s'
      document.documentElement.appendChild(el)
    }
    el.textContent = t
    el.style.opacity = t && !window.__demoClean ? '1' : '0'
  }, [text, stepIndex]).catch(() => {})
}

// ----------------------------------------------------------- the step clock
let videoStart = 0
const timeline = []
let current = null
async function begin(id) {
  if (current) await end()
  const text = narration[id]
  const secs = durations[id]?.seconds ?? 5
  // The caption goes up first and the clock starts once it is on screen, so the
  // voice, the caption and the subtitle all begin on the same frame.
  await caption(text, timeline.length)
  const start = (Date.now() - videoStart) / 1000
  current = { id, start, until: Date.now() + secs * 1000 + PAD_MS }
  timeline.push({ id, start: +start.toFixed(3), seconds: secs, text })
  log('▶', id, `(${secs.toFixed(1)}s)`)
}
/** Hold the frame until the step's narration has finished playing. */
async function end() {
  if (!current) return
  const left = current.until - Date.now()
  if (left > 0) await page.waitForTimeout(left)
  current = null
}

async function humanClick(locator, opts = {}) {
  await locator.waitFor({ state: 'visible', timeout: opts.timeout ?? 15000 })
  await locator.scrollIntoViewIfNeeded().catch(() => {})
  const box = await locator.boundingBox()
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 })
  await pause(250)
  await locator.click({ timeout: opts.timeout ?? 15000 })
}
async function humanType(locator, text) {
  await humanClick(locator)
  await locator.fill('')
  await locator.pressSequentially(text, { delay: 70 })
}
async function hover(locator) {
  const b = await locator.boundingBox().catch(() => null)
  if (b) await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 15 })
}
async function nav(href) {
  const link = page.locator(`a[href="${href}"]`).first()
  if (await link.isVisible().catch(() => false)) await humanClick(link)
  else await page.goto(`${BASE}${href}`)
  await page.waitForLoadState('networkidle').catch(() => {})
}
async function guarded(name, fn) {
  try { await fn() }
  catch (e) {
    const shot = path.join(NARR, `fail_${name}.png`)
    await page.screenshot({ path: shot }).catch(() => {})
    problems.push(`${name}: ${e.message.split('\n')[0]}`)
    log(`!! "${name}" failed:`, e.message.split('\n')[0])
  }
}

async function launch() {
  const opts = { headless: !process.env.DEMO_HEADED, slowMo: 500, args: [`--window-size=${W},${H}`] }
  for (const extra of [{}, { channel: 'msedge' }, { channel: 'chrome' }]) {
    try { return await chromium.launch({ ...opts, ...extra }) }
    catch (e) { log(`launch ${extra.channel || 'bundled chromium'} failed: ${e.message.split('\n')[0]}`) }
  }
  throw new Error('No usable browser')
}

// ===================================================================== main
const ids = { conn: null, ds: null, report: null, conv: null }
try {
  browser = await launch()
  context = await browser.newContext({
    viewport: { width: W, height: H },
    recordVideo: { dir: RAW, size: { width: W, height: H } },
    locale: EN_UI ? 'en-US' : 'ar-EG',
  })
  await context.addInitScript(OVERLAY)
  if (CLEAN) await context.addInitScript(() => { window.__demoClean = true })
  // Arabic interface from the first frame.
  await context.addInitScript(lang => {
    if (!sessionStorage.getItem('__demo_lang_set')) {
      localStorage.setItem('datalytics.language', lang)
      localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
      localStorage.setItem('theme', 'light')
      sessionStorage.setItem('__demo_lang_set', '1')
    }
  }, EN_UI ? 'en' : 'ar')
  page = await context.newPage()
  videoStart = Date.now()                     // the recording starts with the page
  page.setDefaultTimeout(20000)
  page.on('response', async r => {
    try {
      if (r.request().method() === 'POST' && /\/agent\/conversations$/.test(r.url()) && r.ok()) {
        ids.conv = (await r.json())?.id ?? ids.conv
      }
    } catch { /* ignore */ }
  })

  // ---------------------------------------------------------- intro + login
  await page.goto(`${BASE}/login`)
  await page.waitForLoadState('networkidle').catch(() => {})
  await begin('intro')
  await pause(1500)
  await hover(page.locator('aside svg').first())
  await begin('login')
  await humanType(page.locator('input[type=email]'), EMAIL)
  await humanType(page.locator('input[type=password]'), PASSWORD)
  await humanClick(page.locator('button[type=submit]'))
  await page.waitForURL(u => !u.pathname.startsWith('/login'), { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await api('GET', '/auth/me')
  signedIn = true
  await caption(narration.login, timeline.length - 1)   // re-assert after the route change

  // Off-camera prep (while the login line is still being spoken).
  await sweepDemoItems('pre-run')
  ids.ds = (await api('POST', '/datasets', {
    file: { name: 'DEMO_Sales.csv', mimeType: 'text/csv', buffer: Buffer.from(demoCsv(), 'utf8') },
    name: DS_NAME,
    description: EN_UI ? 'Demo sales by month, region and product' : 'مبيعات تجريبية حسب الشهر والمنطقة والمنتج',
  }, { form: true })).id
  log('dataset', DS_NAME, '#' + ids.ds)

  // ------------------------------------------------------------ connection
  await guarded('connection', async () => {
    await begin('connection_open')
    await nav('/connections')
    await pause(800)
    await humanClick(page.getByRole('button', { name: L('New Connection') }))
    const dlg = page.locator('[role=dialog]').filter({ has: page.locator('input[name="conn-filepath"], select') }).first()
    await dlg.waitFor()
    await humanType(dlg.locator('input[maxlength="120"]').first(), CONN_NAME)
    const type = dlg.locator('select').first()
    await humanClick(type)
    await type.selectOption('sqlite')
    await pause(700)
    await humanType(dlg.locator('input[name="conn-filepath"]'), '/tmp/DEMO_connection.db')

    await begin('connection_test')
    await humanClick(dlg.getByRole('button', { name: L('Test connection') }))
    await dlg.getByRole('status').waitFor({ timeout: 30000 })
    await page.waitForFunction(() => !/Testing…|جارٍ الاختبار/.test(document.body.innerText), null, { timeout: 30000 }).catch(() => {})
    log('test result:', (await dlg.getByRole('status').innerText()).trim())
    await hover(dlg.getByRole('status'))

    await begin('connection_save')
    await humanClick(dlg.getByRole('button', { name: L('Create connection') }))
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(1500)
    ids.conn = asList(await api('GET', '/data-sources')).find(c => c.name === CONN_NAME)?.id ?? null
  })

  // --------------------------------------------------------------- dataset
  await guarded('dataset', async () => {
    await begin('dataset_overview')
    await nav('/datasets')
    await pause(900)
    const row = page.getByRole('link', { name: DS_NAME, exact: true }).first()
    if (await row.isVisible().catch(() => false)) await humanClick(row)
    else await page.goto(`${BASE}/datasets/${ids.ds}`)
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(1500)
    await page.mouse.wheel(0, 450); await pause(1200)
    await page.mouse.wheel(0, -450)

    await begin('dataset_data')
    const tabs = page.getByRole('tablist', { name: L('Dataset sections') })
    await humanClick(tabs.getByRole('tab').nth(1))
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  // ------------------------------------------------------------- dashboard
  await guarded('dashboard', async () => {
    await begin('dashboard_new')
    await nav('/reports')
    await pause(700)
    await humanClick(page.getByRole('button', { name: L('New dashboard') }).first())
    await page.waitForURL(/\/reports\/\d+/, { timeout: 20000 })
    ids.report = Number(page.url().match(/\/reports\/(\d+)/)[1])
    const picker = page.locator('[role=dialog]').filter({ has: page.locator('input[aria-label="Search datasets"], input[aria-label="' + (AR['search.datasets'] || 'x') + '"]') }).first()
    await picker.waitFor({ timeout: 15000 })
    await humanType(picker.locator('input').first(), 'DEMO')
    await pause(600)
    await humanClick(picker.getByRole('button', { name: new RegExp('^' + DS_NAME) }).first())
    await page.waitForLoadState('networkidle').catch(() => {})
    await pause(800)
    await humanClick(page.locator('button[aria-label="Rename this dashboard"]'))
    const nameBox = page.locator('input[aria-label="Dashboard name"]')
    await nameBox.fill('')
    await nameBox.pressSequentially(DASH_NAME, { delay: 70 })
    await nameBox.press('Enter')
    await pause(800)
  })

  const DIM = '#fld-dimension-group-x-axis, #dimension-select'
  const MEAS = '#fld-measure-numeric-column'
  const addVisual = async (id, tileLabel, fields) => {
    await guarded(id, async () => {
      await begin(id)
      const panel = page.getByRole('tablist', { name: L('Builder panel') })
      const charts = panel.getByRole('tab').first()
      if (await charts.isVisible().catch(() => false) && (await charts.getAttribute('aria-selected')) !== 'true') {
        await humanClick(charts)
      }
      await humanClick(page.locator(`button.dl-gallery__tile[aria-label="${tileLabel}"]`).first())
      await pause(1200)
      for (const [sel, value] of fields) {
        const s = page.locator(sel).first()
        await s.waitFor({ state: 'visible', timeout: 10000 })
        await humanClick(s)
        await s.selectOption(value)
        await pause(700)
      }
    })
  }
  if (ids.report) {
    await addVisual('kpi', 'KPI Card', [[MEAS, 'revenue']])
    await addVisual('bar', 'Bar Chart', [[DIM, 'region'], [MEAS, 'revenue']])
    await addVisual('line', 'Line Chart', [[DIM, 'order_date'], [MEAS, 'revenue']])
    await addVisual('table', 'Table', [[DIM, 'product'], [MEAS, 'revenue']])
    await addVisual('slicer', 'Slicer', [['#fld-field-to-filter-by', 'region']])
    await guarded('verify widgets', async () => {
      const pg = (await api('GET', `/reports/${ids.report}`)).pages?.[0]
      const have = new Set((pg?.widgets || []).map(w => w.widget_type))
      const missing = ['kpi', 'bar', 'line', 'table', 'slicer'].filter(k => !have.has(k))
      if (missing.length) problems.push(`widgets missing after the UI path: ${missing.join(', ')}`)
      log('widgets:', [...have].join(', '))
    })
  }

  // -------------------------------------------------------- view / edit
  await guarded('view', async () => {
    const group = page.getByRole('group', { name: L('Report mode') })
    await begin('view_mode')
    await humanClick(group.locator('button[aria-label="View mode"]'))
    await page.waitForLoadState('networkidle').catch(() => {})

    await begin('filter')
    const val = page.getByRole('figure').filter({ hasText: FILTER_VALUE }).getByText(FILTER_VALUE, { exact: true }).first()
    if (await val.isVisible().catch(() => false)) {
      await humanClick(val)
      await pause(3500)
      await humanClick(val).catch(() => {})
    } else problems.push('filter value not clickable in View mode')

    await begin('edit_mode')
    await humanClick(group.locator('button[aria-label="Edit mode"]'))
    await pause(1200)
    const saved = page.getByText(L('Saved')).first()
    await saved.waitFor({ timeout: 10000 }).catch(() => {})
    await hover(saved)
  })

  // ---------------------------------------------------------------- Ask AI
  await guarded('ask', async () => {
    await begin('ask')
    await nav('/ask')
    await pause(600)
    // The scope picker is a searchable list: open it, then pick the option.
    await humanClick(page.getByRole('button', { name: L('What to ask about') }).first())
    await humanClick(page.locator(`[role=option][data-value="d:${ids.ds}"]`).first())
    await pause(700)
    await humanType(page.locator('.dl-composer__input').first(), QUESTION)
    await humanClick(page.getByRole('button', { name: L('Send') }))
    await Promise.race([
      page.locator('[data-testid=answer-source]').first().waitFor({ timeout: 150000 }),
      page.getByText(L('Could not answer that')).first().waitFor({ timeout: 150000 }),
    ])
    await begin('ask_answer')
    await pause(1000)
    await page.mouse.wheel(0, 350)
  })

  // ------------------------------------------------ language: EN and back
  await guarded('language', async () => {
    await begin('language')
    const prefixes = [EN['lang.aria'], AR['lang.aria']].filter(Boolean).map(s => s.split('{')[0])
    const langBtn = () => page.locator(prefixes.map(p => `button[aria-haspopup="menu"][aria-label^="${p}"]`).join(', ')).first()
    await humanClick(langBtn())
    // Show the OTHER language, then come back.
    await humanClick(page.getByRole('menuitemradio', { name: EN_UI ? /العربية/ : /English/ }).first())
    await page.waitForFunction(d => document.documentElement.dir === d, EN_UI ? 'rtl' : 'ltr', { timeout: 10000 })
    await pause(2500)
    await humanClick(langBtn())
    await humanClick(page.getByRole('menuitemradio', { name: EN_UI ? /English/ : /العربية/ }).first())
    await page.waitForFunction(d => document.documentElement.dir === d, EN_UI ? 'ltr' : 'rtl', { timeout: 10000 })
  })

  // ------------------------------------------------- dashboards + outro
  await guarded('dashboards', async () => {
    await begin('dashboards_list')
    await nav('/reports')
    await pause(1200)
    await hover(page.getByText(DASH_NAME).first())
  })
  await begin('outro')
  await end()
  await caption('')
  await pause(600)
} catch (e) {
  problems.push(`fatal: ${e.message.split('\n')[0]}`)
  log('FATAL', e.message)
  if (page) await page.screenshot({ path: path.join(NARR, 'fail_fatal.png') }).catch(() => {})
} finally {
  if (signedIn && context) {
    if (ids.conv) await api('DELETE', `/agent/conversations/${ids.conv}`).catch(e => problems.push(`cleanup conversation: ${e.message}`))
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
  const videoEnd = (Date.now() - videoStart) / 1000
  if (context) await context.close().catch(() => {})
  if (video) {
    try {
      await video.saveAs(path.join(NARR, `raw_ar${SUFFIX}.webm`))
      await video.delete().catch(() => {})
    } catch (e) { problems.push(`saving video: ${e.message}`) }
  }
  if (browser) await browser.close().catch(() => {})
  try { fs.rmSync(RAW, { recursive: true, force: true }) } catch { /* ignore */ }
  fs.writeFileSync(path.join(NARR, `timeline${SUFFIX}.json`), JSON.stringify({ videoEnd, steps: timeline }, null, 2))
  log(problems.length ? `finished with ${problems.length} note(s):\n  - ${problems.join('\n  - ')}` : 'finished cleanly')
  fs.writeFileSync(path.join(NARR, 'last_run_status.txt'), problems.length ? problems.join('\n') + '\n' : 'OK\n')
  process.exitCode = problems.some(p => p.startsWith('fatal')) ? 1 : 0
}
