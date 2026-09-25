// Screenshots of the dashboard "Ask AI" button + panel for design review.
//
//   node frontend/e2e/demo/aibtn_screens.mjs
// Output: <data_analytics>/demo_output/aibtn_redesign/*.png
//
// Creates DEMO_AIBtn Sales (dataset) and DEMO_AIBtn Dashboard (3 widgets),
// asks the copilot one read-only data question, and deletes both at the end.

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
const BASE = (process.env.DEMO_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.DEMO_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.DEMO_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.DEMO_PASSWORD || 'demo-password'
const OUT = path.join(ROOT, 'demo_output', 'aibtn_redesign')
fs.mkdirSync(OUT, { recursive: true })
const DS_NAME = 'DEMO_AIBtn Sales'
const REP_NAME = 'DEMO_AIBtn Dashboard'
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

function demoCsv() {
  const regions = ['North America', 'Europe', 'Asia Pacific', 'Latin America']
  const products = { Laptops: 900, Phones: 650, Tablets: 420, Accessories: 45 }
  const rows = ['order_date,region,product,units,revenue']
  let seed = 5
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  for (let m = 0; m < 12; m++) for (const r of regions) for (const [p, price] of Object.entries(products)) {
    const units = 20 + Math.round(rnd() * 80 + m * 3) - (r === 'Latin America' ? 12 : 0)
    rows.push(`2025-${String(m + 1).padStart(2, '0')}-15,${r},${p},${units},${(units * price * (0.9 + rnd() * 0.2)).toFixed(2)}`)
  }
  return rows.join('\n') + '\n'
}

async function launch() {
  for (const extra of [{}, { channel: 'msedge' }, { channel: 'chrome' }]) {
    try { return await chromium.launch({ ...extra }) } catch (e) { log('launch failed:', e.message.split('\n')[0]) }
  }
  throw new Error('no browser')
}

let apiCtx
async function api(method, p, body, { form = false } = {}) {
  const opts = { method, headers: { 'X-Requested-With': 'XMLHttpRequest' }, failOnStatusCode: false }
  if (form) opts.multipart = body
  else if (body !== undefined) opts.data = body
  const r = await apiCtx.request.fetch(API + p, opts)
  const text = await r.text()
  if (!r.ok()) throw new Error(`${method} ${p} -> ${r.status()} ${text.slice(0, 200)}`)
  return text ? JSON.parse(text) : null
}

const browser = await launch()
let dsId = null, repId = null
const t0 = Date.now()
try {
  apiCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const lp = await apiCtx.newPage()
  await lp.goto(`${BASE}/login`, { waitUntil: 'networkidle' }).catch(() => {})
  await lp.locator('input[type=email]').fill(EMAIL)
  await lp.locator('input[type=password]').fill(PASSWORD)
  await lp.locator('button[type=submit]').click()
  await lp.waitForURL(u => !u.pathname.startsWith('/login'), { timeout: 30000 })
  await lp.close()
  const state = await apiCtx.storageState()
  log('signed in')

  // Leftovers from an aborted run go first.
  for (const r of await api('GET', '/reports')) if (r.name === REP_NAME) await api('DELETE', `/reports/${r.id}`).catch(() => {})
  for (const d of await api('GET', '/datasets')) if (d.name === DS_NAME) await api('DELETE', `/datasets/${d.id}`).catch(() => {})

  dsId = (await api('POST', '/datasets', {
    file: { name: 'DEMO_AIBtn_Sales.csv', mimeType: 'text/csv', buffer: Buffer.from(demoCsv(), 'utf8') },
    name: DS_NAME, description: 'Demo sales for the Ask AI button screenshots',
  }, { form: true })).id
  const rep = await api('POST', '/reports', { name: REP_NAME, dataset_id: dsId })
  repId = rep.id
  const pageId = (rep.pages?.[0] ?? (await api('GET', `/reports/${repId}`)).pages[0]).id
  const W = [
    { widget_type: 'pie', title: 'Revenue share by region', config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' }, layout: { x: 0, y: 0, w: 6, h: 5 } },
    { widget_type: 'bar', title: 'Units by product', config: { dimension: 'product', measure: 'units', aggregation: 'sum' }, layout: { x: 6, y: 0, w: 6, h: 5 } },
    { widget_type: 'line', title: 'Revenue over time', config: { dimension: 'order_date', measure: 'revenue', aggregation: 'sum', dimension_granularity: 'month' }, layout: { x: 0, y: 5, w: 12, h: 5 } },
  ]
  for (const w of W) await api('POST', `/reports/${repId}/pages/${pageId}/widgets`, w)
  log('dataset', dsId, 'report', repId)

  const view = async ({ lang = 'en', theme = 'dark', corner = null, w = 1440, h = 900 } = {}) => {
    const ctx = await browser.newContext({ storageState: state, viewport: { width: w, height: h }, reducedMotion: 'reduce' })
    await ctx.addInitScript(([l, th, c]) => {
      localStorage.setItem('datalytics.language', l)
      localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr')
      localStorage.setItem('theme', th)
      if (c) localStorage.setItem('datalytics.askai.corner', c); else localStorage.removeItem('datalytics.askai.corner')
      localStorage.removeItem('datalytics.askai.seenInsights')
    }, [lang, theme, corner])
    const page = await ctx.newPage()
    await page.goto(`${BASE}/reports/${repId}`, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(2500)
    return { ctx, page }
  }
  const shot = async (page, name) => {
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(OUT, `${name}.png`) })
    log('saved', name)
  }
  const safe = async (label, fn) => { try { await fn() } catch (e) { log(`!! ${label}:`, e.message.split('\n')[0]) } }
  const btn = page => page.locator('.dl-askai__btn')

  // Idle, then (after the insight scan) the badge, hover, open.
  await safe('dark en', async () => {
    const { ctx, page } = await view()
    await shot(page, 'a_idle_en_dark')
    await page.waitForTimeout(6000)   // the insight scan starts 2.5 s after load
    await shot(page, 'b_insight_badge_en_dark')
    await btn(page).hover(); await page.waitForTimeout(500)
    await shot(page, 'c_hover_pill_tooltip_en_dark')
    await btn(page).click(); await page.waitForTimeout(700)
    await shot(page, 'd_open_panel_en_dark')
    // Thinking: hold the request ~6 s, then let it through for a real answer.
    await page.route('**/copilot', async route => { await new Promise(r => setTimeout(r, 6000)); await route.continue() })
    await page.locator('.dl-askai__box textarea').fill('Total revenue by region')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1500)
    await shot(page, 'e_thinking_en_dark')
    await page.locator('.dl-askai__msg--ai:not(.dl-askai__thinking)').last().waitFor({ timeout: 180000 })
    await page.waitForTimeout(1500)
    await shot(page, 'f_answer_en_dark')
    await page.unroute('**/copilot')
    await ctx.close()
  })

  await safe('scrolling', async () => {
    const { ctx, page } = await view()
    await page.mouse.move(700, 450)
    await page.mouse.wheel(0, 300)
    await page.waitForTimeout(150)
    await page.screenshot({ path: path.join(OUT, 'g_scrolling_en_dark.png') })
    log('saved g_scrolling_en_dark')
    await ctx.close()
  })

  await safe('light', async () => {
    const { ctx, page } = await view({ theme: 'light' })
    await shot(page, 'a_idle_en_light')
    await btn(page).click(); await page.waitForTimeout(700)
    await shot(page, 'd_open_panel_en_light')
    await ctx.close()
  })

  await safe('arabic', async () => {
    const { ctx, page } = await view({ lang: 'ar', theme: 'dark' })
    await shot(page, 'a_idle_ar_dark')
    await btn(page).hover(); await page.waitForTimeout(500)
    await shot(page, 'c_hover_ar_dark')
    await btn(page).click(); await page.waitForTimeout(700)
    await shot(page, 'd_open_panel_ar_dark')
    await ctx.close()
  })

  await safe('corner', async () => {
    const { ctx, page } = await view({ corner: 'top-start' })
    await shot(page, 'h_moved_top_start_en_dark')
    await ctx.close()
  })

  await safe('drag', async () => {
    const { ctx, page } = await view()
    const b = await btn(page).boundingBox()
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2)
    await page.mouse.down()
    await page.mouse.move(700, 300, { steps: 8 })
    await shot(page, 'i_dragging_en_dark')
    await page.mouse.move(420, 220, { steps: 4 })
    await page.mouse.up()
    await page.waitForTimeout(600)
    await shot(page, 'i_dropped_snapped_en_dark')
    await ctx.close()
  })
} finally {
  try {
    if (repId != null) await api('DELETE', `/reports/${repId}`)
    if (dsId != null) await api('DELETE', `/datasets/${dsId}`)
    const left = [
      ...(await api('GET', '/reports')).filter(r => r.name === REP_NAME),
      ...(await api('GET', '/datasets')).filter(d => d.name === DS_NAME),
    ]
    log(left.length ? `!! DEMO_ items still present: ${left.map(x => x.name).join(', ')}` : 'cleanup verified: no DEMO_ items left')
  } catch (e) { log('!! cleanup:', e.message) }
  await browser.close()
}
log(`done in ${Math.round((Date.now() - t0) / 1000)} s ->`, OUT)
