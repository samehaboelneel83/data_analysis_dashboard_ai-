// Screenshots of the Ask AI page for design review: every state of the brief
// (hero, picker, suggestions, loading, answer, error, history), desktop and
// mobile, English and Arabic, dark and light.
//
//   node frontend/e2e/demo/ask_screens.mjs [before|after]
// Output: <data_analytics>/demo_output/ask_redesign/<phase>/*.png
//
// Creates ONE dataset, DEMO_Ask Sales, asks it two questions (one English,
// one Arabic), and deletes the dataset and every conversation this run made
// at the end. The error state is forced in the browser only (the ask request
// is answered locally with a failed run) -- nothing is sent to the agent.

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
const phase = process.argv[2] || 'after'
const OUT = path.join(ROOT, 'demo_output', 'ask_redesign', phase)
fs.mkdirSync(OUT, { recursive: true })
const DS_NAME = 'DEMO_Ask Sales'
const Q_EN = 'Total revenue by region'
const Q_AR = 'ما إجمالي الإيرادات حسب المنطقة؟'
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

function demoCsv() {
  const regions = ['North', 'South', 'East', 'West']
  const products = { Laptops: 900, Phones: 650, Tablets: 420, Accessories: 45 }
  const rows = ['order_date,region,product,units,revenue']
  let seed = 11
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280
  for (let m = 0; m < 12; m++) for (const r of regions) for (const [p, price] of Object.entries(products)) {
    const units = 20 + Math.round(rnd() * 80 + m * 3)
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
let dsId = null
const t0 = Date.now()
try {
  // ---- sign in once; every view reuses the session cookie
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

  // ---- the one DEMO_ dataset (a leftover from an aborted run is removed first)
  for (const d of await api('GET', '/datasets')) {
    if (d.name === DS_NAME) { await api('DELETE', `/datasets/${d.id}`).catch(() => {}); log('removed leftover', d.id) }
  }
  dsId = (await api('POST', '/datasets', {
    file: { name: 'DEMO_Ask_Sales.csv', mimeType: 'text/csv', buffer: Buffer.from(demoCsv(), 'utf8') },
    name: DS_NAME, description: 'Demo sales for Ask AI screenshots',
  }, { form: true })).id
  log('dataset', dsId)

  const view = async ({ lang = 'en', theme = 'dark', mobile = false } = {}) => {
    const ctx = await browser.newContext({
      storageState: state,
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
      deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile,
      reducedMotion: 'reduce',
    })
    await ctx.addInitScript(([l, th]) => {
      localStorage.setItem('datalytics.language', l)
      localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr')
      localStorage.setItem('theme', th)
      localStorage.removeItem('datalytics.ask.historyFolded')
    }, [lang, theme])
    const page = await ctx.newPage()
    return { ctx, page }
  }
  const toBottom = page => page.evaluate(() => document.querySelectorAll('.dl-chat__scroll')
    .forEach(el => { el.scrollTop = el.scrollHeight }))
  const shot = async (page, name, full = false) => {
    await page.waitForTimeout(700)
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: full })
    log('saved', name)
  }
  const safe = async (label, fn) => {
    try { await fn() } catch (e) { log(`!! ${label}:`, e.message.split('\n')[0]) }
  }
  const go = async (page, url) => {
    await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(900)
  }
  const questionBox = page => page.locator('textarea, input[placeholder]').filter({ hasNot: page.locator('[type=email]') }).last()
  const sendBtn = page => page.locator('.dl-composer__send, button:has-text("Send"), button:has-text("Ask")').last()
  const openPicker = async page => {
    const trig = page.locator('.dl-pick__trigger').first()
    if (await trig.count()) { await trig.click(); return true }
    return false
  }
  const newChat = async page => {
    const b = page.locator('.dl-hist__new, button:has-text("New chat"), button:has-text("محادثة جديدة")').first()
    if (await b.count()) await b.click().catch(() => {})
    await page.waitForTimeout(600)
  }
  const waitAnswer = page => Promise.race([
    page.locator('[data-testid=answer-source]').last().waitFor({ timeout: 180000 }),
    page.locator('.dl-answer-error').last().waitFor({ timeout: 180000 }),
    page.getByText(/Could not answer that|Could not reach the agent/).last().waitFor({ timeout: 180000 }),
  ])

  // ================= (a) hero / empty state, (b) picker =================
  for (const [lang, theme, mobile] of [
    ['en', 'dark', false], ['en', 'light', false], ['ar', 'dark', false], ['en', 'dark', true], ['ar', 'dark', true],
  ]) {
    const tag = `${lang}_${theme}${mobile ? '_mobile' : ''}`
    await safe(`hero ${tag}`, async () => {
      const { ctx, page } = await view({ lang, theme, mobile })
      await go(page, '/ask')
      await shot(page, `a_hero_${tag}`, true)
      if (await openPicker(page)) {
        await page.waitForTimeout(400)
        await shot(page, `b_picker_${tag}`, !mobile)
        const search = page.locator('.dl-pick__search input')
        if (!mobile && lang === 'en' && theme === 'dark' && await search.count()) {
          await search.fill('ask')
          await shot(page, `b_picker_search_${tag}`)
        }
      }
      await ctx.close()
    })
  }

  // ================= (c) scoped, suggestions; (d) loading; (e) answer =================
  await safe('ask en', async () => {
    const { ctx, page } = await view({ lang: 'en', theme: 'dark' })
    await go(page, `/ask?dataset=${dsId}`)
    await newChat(page)
    await shot(page, 'c_scoped_suggestions_en_dark')
    // Hold the ask request ~7 s so the progress steps are visible, then let it through.
    await page.route('**/agent/conversations/*/ask', async route => {
      await new Promise(r => setTimeout(r, 7000)); await route.continue()
    })
    await questionBox(page).fill(Q_EN)
    await shot(page, 'c_typed_en_dark')
    await sendBtn(page).click()
    await page.waitForTimeout(5500)
    await shot(page, 'd_loading_en_dark')
    await waitAnswer(page)
    await page.unroute('**/agent/conversations/*/ask')
    await page.waitForTimeout(1500)
    await shot(page, 'e_answer_en_dark')
    const sql = page.getByRole('button', { name: /show sql/i }).last()
    if (await sql.count()) { await sql.click(); await page.waitForTimeout(1200) }
    const rows = page.getByRole('button', { name: /show rows/i }).last()
    if (await rows.count()) { await rows.click(); await page.waitForTimeout(600) }
    await shot(page, 'e_answer_sql_rows_en_dark', true)
    await toBottom(page)
    await shot(page, 'e_answer_actions_en_dark')
    const add = page.getByRole('button', { name: 'Add to dashboard' }).last()
    if (await add.count()) { await add.click(); await page.waitForTimeout(1200); await shot(page, 'e_add_to_dashboard_menu_en_dark'); await page.keyboard.press('Escape') }
    await ctx.close()
  })

  // Same answer, light theme and mobile (the thread reopens as the newest).
  for (const [theme, mobile] of [['light', false], ['dark', true]]) {
    await safe(`answer ${theme} ${mobile}`, async () => {
      const { ctx, page } = await view({ lang: 'en', theme, mobile })
      await go(page, `/ask?dataset=${dsId}`)
      await page.waitForTimeout(1500)
      await shot(page, `e_answer_en_${theme}${mobile ? '_mobile' : ''}`)
      if (mobile) {
        const h = page.locator('.dl-ask__hist-btn')
        if (await h.count() && await h.isVisible()) { await h.click(); await page.waitForTimeout(600); await shot(page, 'f_history_drawer_en_dark_mobile') }
      }
      await ctx.close()
    })
  }

  // ================= (e) Arabic answer =================
  await safe('ask ar', async () => {
    const { ctx, page } = await view({ lang: 'ar', theme: 'dark' })
    await go(page, `/ask?dataset=${dsId}`)
    await newChat(page)
    await shot(page, 'c_scoped_suggestions_ar_dark')
    await questionBox(page).fill(Q_AR)
    await sendBtn(page).click()
    await page.waitForTimeout(2500)
    await shot(page, 'd_loading_ar_dark')
    await waitAnswer(page)
    await page.waitForTimeout(1500)
    const sql = page.locator('.dl-act[aria-expanded="false"]').filter({ hasText: 'SQL' }).last()
    if (await sql.count()) { await sql.click(); await page.waitForTimeout(1200) }
    await shot(page, 'e_answer_ar_dark', true)
    await ctx.close()
  })
  await safe('ar mobile', async () => {
    const { ctx, page } = await view({ lang: 'ar', theme: 'light', mobile: true })
    await go(page, `/ask?dataset=${dsId}`)
    await page.waitForTimeout(1500)
    await shot(page, 'e_answer_ar_light_mobile')
    await ctx.close()
  })

  // ================= (f) error state (forced locally) =================
  for (const lang of ['en', 'ar']) {
    await safe(`error ${lang}`, async () => {
      const { ctx, page } = await view({ lang, theme: 'dark' })
      await go(page, `/ask?dataset=${dsId}`)
      await newChat(page)
      await page.route('**/agent/conversations/*/ask', route => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ run_id: 0, status: 'failed', answer: null, intent: null,
          error: 'step s1: Binder Error: Referenced column "discount" not found in FROM clause' }),
      }))
      await questionBox(page).fill(lang === 'ar' ? 'ما إجمالي الخصومات؟' : 'What is the total discount?')
      await sendBtn(page).click()
      await page.waitForTimeout(2000)
      const det = page.locator('.dl-answer-error__details summary')
      if (await det.count()) { await det.click(); await page.waitForTimeout(300) }
      await shot(page, `g_error_${lang}_dark`)
      await ctx.close()
    })
  }

  // ================= history (desktop, light) =================
  await safe('history', async () => {
    const { ctx, page } = await view({ lang: 'en', theme: 'light' })
    await go(page, `/ask?dataset=${dsId}`)
    await page.waitForTimeout(1500)
    await shot(page, 'f_history_en_light')
    const fold = page.locator('.dl-hist__fold')
    if (await fold.count()) { await fold.click(); await page.waitForTimeout(500); await shot(page, 'f_history_collapsed_en_light') }
    await ctx.close()
  })
} finally {
  // ---- cleanup: this run's conversations, then the dataset
  try {
    if (dsId != null) {
      for (const c of await api('GET', '/agent/conversations')) {
        if ((c.dataset_ids ?? []).length === 1 && c.dataset_ids[0] === dsId && !c.data_source_id) {
          await api('DELETE', `/agent/conversations/${c.id}`).catch(e => log('!! conv', c.id, e.message))
        }
      }
      await api('DELETE', `/datasets/${dsId}`)
      log('cleanup: removed dataset', dsId, 'and its conversations')
    }
    const left = (await api('GET', '/datasets')).filter(d => d.name === DS_NAME)
    log(left.length ? `!! ${DS_NAME} still present` : 'cleanup verified: no DEMO_ items left')
  } catch (e) { log('!! cleanup:', e.message) }
  await browser.close()
}
log(`done in ${Math.round((Date.now() - t0) / 1000)} s ->`, OUT)
