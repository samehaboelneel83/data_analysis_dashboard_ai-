// A browser journey through drafts and releases (E09), edit conflicts, and
// a viewer's keyboard and accessibility pass (E10), against a RUNNING stack.
//
//   node frontend/e2e/journeys/release_journey.mjs
//
// Environment (defaults are the Compose stack):
//   JOURNEY_BASE_URL  http://localhost:3001      the app
//   JOURNEY_API_URL   http://localhost:8000/api/v1
//   JOURNEY_EMAIL / JOURNEY_PASSWORD             an organisation admin
//                                                (admin@datalytics.local / demo-password)
//
// It creates a role, a viewer and an editor ("E2E Journey ..."), and one
// dashboard over the first dataset it can read; everything it made is deleted
// at the end, pass or fail. Screenshots and a JSON summary go to
// <data_analytics>/demo_output/journeys/<timestamp>/. Exit code 1 when a
// step fails, so it can gate a release.

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
const STAMP = new Date().toISOString().replace(/[:.]/g, '-')
const OUT = path.join(ROOT, 'demo_output', 'journeys', STAMP)
fs.mkdirSync(OUT, { recursive: true })
const TAG = `E2E Journey ${Date.now() % 100000}`
const results = []
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

async function api(method, url, token, body) {
  const r = await fetch(API + url, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
      ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await r.text()
  let json = null
  try { json = text ? JSON.parse(text) : null } catch { json = text }
  return { status: r.status, json }
}

async function login(email, password) {
  const r = await api('POST', '/auth/login', null, { email, password })
  if (r.status !== 200) throw new Error(`login ${email}: ${r.status}`)
  return r.json.access_token
}

async function step(name, fn) {
  try {
    const detail = await fn()
    results.push({ step: name, ok: true, detail: detail ?? null })
    log('PASS', name)
  } catch (e) {
    results.push({ step: name, ok: false, detail: String(e?.message ?? e) })
    log('FAIL', name, '-', String(e?.message ?? e))
  }
}

function expect(cond, message) { if (!cond) throw new Error(message) }

async function uiLogin(browser, email, password, language = 'en') {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.addInitScript(l => {
    try {
      localStorage.setItem('datalytics.language', l)
      localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr')
    } catch { /* storage blocked: the app falls back to English */ }
  }, language)
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.goto(`${BASE}/login`)
  await page.getByLabel(/^(email|البريد الإلكتروني)$/i).fill(email)
  await page.getByLabel(/^(password|كلمة المرور)$/i).fill(password)
  await page.getByRole('button', { name: /^(sign in|تسجيل الدخول)$/i }).click()
  await page.waitForURL(u => !String(u).includes('/login'), { timeout: 15000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  return { ctx, page, errors }
}

/** A navigation the app itself starts (the post-login redirect) can abort
 *  ours; one retry is enough. */
async function go(page, url) {
  await page.goto(url).catch(() => page.goto(url))
}

async function widgetTitles(page) {
  await page.waitForTimeout(1500)
  return page.locator('[data-widget-id]').evaluateAll(els =>
    els.map(e => (e.querySelector('[data-testid="widget-title"], h3, header')?.textContent ?? e.textContent ?? '').trim()))
}

const made = { report: null, users: [], role: null }
let adminToken = null

async function main() {
  adminToken = await login(EMAIL, PASSWORD)

  // ── Setup through the API: a viewer, an editor, one published dashboard ──
  const role = await api('POST', '/admin/roles', adminToken, { name: `${TAG} members` })
  expect(role.status === 200, `role: ${role.status} ${JSON.stringify(role.json)}`)
  made.role = role.json.id
  const people = {}
  for (const who of ['viewer', 'editor']) {
    const email = `${who}.${Date.now() % 100000}@journey.example`
    const u = await api('POST', '/admin/users', adminToken, { email, password: 'Journey-pass-1', role_id: made.role })
    expect(u.status === 200, `user: ${u.status} ${JSON.stringify(u.json)}`)
    made.users.push(u.json.id)
    people[who] = { email, password: 'Journey-pass-1' }
  }
  const datasets = (await api('GET', '/datasets', adminToken)).json
  const ds = (datasets ?? []).find(d => d.mode !== 'directquery' && (d.columns?.length ?? 0) >= 2) ?? datasets?.[0]
  expect(ds, 'no dataset to build on')
  const cols = (await api('GET', `/datasets/${ds.id}`, adminToken)).json.columns ?? []
  const dim = cols.find(c => /text|string|categor/i.test(c.dtype))?.name ?? cols[0]?.name
  // A quantity, not a coordinate or an id: the chart refuses to sum those.
  const meas = cols.find(c => /num|int|float|decimal/i.test(c.dtype)
    && !/(^|_)(lat|lon|lng|latitude|longitude|id)$/i.test(c.name))?.name
  const rep = await api('POST', '/reports', adminToken, { name: `${TAG} dashboard`, dataset_id: ds.id })
  made.report = rep.json.id
  const pageId = (await api('GET', `/reports/${made.report}`, adminToken)).json.pages[0].id
  const w = await api('POST', `/reports/${made.report}/pages/${pageId}/widgets`, adminToken, {
    widget_type: 'bar', title: 'Released title',
    config: { dimension: dim, ...(meas ? { measure: meas, aggregation: 'sum' } : {}) },
    layout: { x: 0, y: 0, w: 8, h: 5 },
  })
  expect(w.status === 201, `widget: ${w.status}`)
  const widgetId = w.json.id
  await api('POST', `/reports/${made.report}/grants`, adminToken, { email: people.editor.email, level: 'edit' })
  const pub = await api('POST', `/reports/${made.report}/publish`, adminToken, { published: true })
  expect(pub.status === 200 && pub.json.release, `publish: ${pub.status}`)

  const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE } : {})
  try {
    const author = await uiLogin(browser, EMAIL, PASSWORD)
    const viewer = await uiLogin(browser, people.viewer.email, people.viewer.password)
    const url = `${BASE}/reports/${made.report}`

    await step('the author sees the published dashboard as released', async () => {
      await go(author.page, url)
      const status = author.page.getByTestId('release-control').getByRole('status')
      await status.waitFor({ timeout: 15000 })
      expect((await status.textContent()).includes('Released'), `status: ${await status.textContent()}`)
      await author.page.screenshot({ path: path.join(OUT, '01_author_released.png') })
    })

    // Someone with edit access changes the widget; the author's page reloads.
    const editorToken = await login(people.editor.email, people.editor.password)
    const before = (await api('GET', `/reports/${made.report}`, adminToken)).json.revision
    await api('PATCH', `/reports/${made.report}/pages/${pageId}/widgets/${widgetId}`, editorToken,
      { title: 'Draft title' })

    await step('the viewer still sees the released title after a draft edit', async () => {
      await go(viewer.page, url)
      await viewer.page.getByText('Released title').first().waitFor({ timeout: 15000 })
      expect(!(await viewer.page.getByText('Draft title').count()), 'the draft reached the viewer')
      expect(!(await viewer.page.getByTestId('release-control').count()), 'a viewer was shown the release control')
      await viewer.page.screenshot({ path: path.join(OUT, '02_viewer_before_release.png') })
    })

    await step('the author is told of unreleased changes and releases them from the keyboard', async () => {
      await go(author.page, url)
      const btn = author.page.getByRole('button', { name: 'Release changes' })
      await btn.waitFor({ timeout: 15000 })
      await author.page.screenshot({ path: path.join(OUT, '03_author_unreleased.png') })
      await btn.focus()
      await author.page.keyboard.press('Enter')
      await author.page.getByText('Released: viewers now see this version').waitFor({ timeout: 10000 })
      await author.page.getByTestId('release-control').getByText('Released').waitFor({ timeout: 10000 })
    })

    await step('the viewer sees the released change', async () => {
      await go(viewer.page, url)
      await viewer.page.getByText('Draft title').first().waitFor({ timeout: 15000 })
      await viewer.page.screenshot({ path: path.join(OUT, '04_viewer_after_release.png') })
    })

    await step('an edit conflict is shown instead of overwriting a colleague', async () => {
      const r = await api('PATCH', `/reports/${made.report}/pages/${pageId}/widgets/${widgetId}`, adminToken,
        { title: 'Mine', base_revision: before })
      expect(r.status === 409 && r.json?.detail?.code === 'edit_conflict', `got ${r.status}`)
      expect(r.json.detail.changed_by === people.editor.email, `named ${r.json.detail.changed_by}`)
    })

    await step('the author combines their change with the editor\'s instead of choosing one (E09)', async () => {
      await go(author.page, url)
      // Exact: the "Object to edit" list also names it, as "Draft title (bar)".
      await author.page.getByText('Draft title', { exact: true }).first().click({ timeout: 15000 })
      const titleBox = author.page.getByPlaceholder('Widget title')
      await titleBox.waitFor({ timeout: 10000 })
      // The editor changes another setting after the author's page loaded.
      const other = await api('GET', `/reports/${made.report}`, editorToken)
      const cfg = other.json.pages[0].widgets.find(x => x.id === widgetId).config
      const theirs = await api('PATCH', `/reports/${made.report}/pages/${pageId}/widgets/${widgetId}`, editorToken,
        { config: { ...cfg, data_labels: true } })
      expect(theirs.status === 200, `editor save: ${theirs.status}`)
      // The author renames the widget; the autosave is refused as a conflict.
      const refused = author.page.waitForResponse(r => r.url().includes(`/widgets/${widgetId}`)
        && r.request().method() === 'PATCH', { timeout: 10000 })
      await titleBox.fill('Author title')
      const res = await refused
      expect(res.status() === 409, `the author's save answered ${res.status()}`)
      const banner = author.page.getByTestId('edit-conflict')
      await banner.waitFor({ timeout: 10000 })
      await author.page.getByRole('button', { name: 'Combine…' }).click()
      const dialog = author.page.getByRole('dialog', { name: 'Combine your change with theirs' })
      await dialog.waitFor({ timeout: 5000 })
      const summary = await dialog.getByTestId('merge-summary').textContent()
      expect(/Nothing was changed by both of you/.test(summary), `summary: ${summary}`)
      await author.page.screenshot({ path: path.join(OUT, '05_author_combine.png') })
      await dialog.getByRole('button', { name: 'Save combined' }).click()
      await banner.waitFor({ state: 'detached', timeout: 10000 })
      const after = (await api('GET', `/reports/${made.report}`, adminToken)).json
        .pages[0].widgets.find(x => x.id === widgetId)
      expect(after.title === 'Author title', `title: ${after.title}`)
      expect(after.config.data_labels === true, `the editor's setting was lost: ${JSON.stringify(after.config)}`)
      // The panel shows the saved widget, not the refused copy.
      expect(await titleBox.inputValue() === 'Author title', `panel title: ${await titleBox.inputValue()}`)
      return { summary }
    })

    await step('a viewer can reach every toolbar control from the keyboard', async () => {
      await go(viewer.page, url)
      await viewer.page.getByText('Draft title').first().waitFor({ timeout: 15000 })
      const seen = new Set()
      for (let i = 0; i < 40; i++) {
        await viewer.page.keyboard.press('Tab')
        const name = await viewer.page.evaluate(() => {
          const el = document.activeElement
          if (!el || el === document.body) return ''
          return (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 40)
        })
        if (name) seen.add(name)
      }
      for (const want of ['Export', 'Subscribe']) {
        expect([...seen].some(s => s.includes(want)), `could not tab to "${want}" (reached: ${[...seen].join(' | ')})`)
      }
      return { reached: [...seen] }
    })

    await step('the viewer page has no serious or critical accessibility violations', async () => {
      await viewer.page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
      const found = await viewer.page.evaluate(async () => {
        const r = await window.axe.run(document, { resultTypes: ['violations'] })
        return r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
          .map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }))
      })
      fs.writeFileSync(path.join(OUT, 'axe_viewer.json'), JSON.stringify(found, null, 2))
      expect(found.length === 0, `${found.length}: ${found.map(v => `${v.id} (${v.nodes})`).join(', ')}`)
    })

    await step('in Arabic the page runs right to left and the release control speaks Arabic', async () => {
      const ar = await uiLogin(browser, EMAIL, PASSWORD, 'ar')
      await go(ar.page, url)
      await ar.page.getByTestId('release-control').waitFor({ timeout: 15000 })
      const dir = await ar.page.evaluate(() => document.documentElement.dir)
      expect(dir === 'rtl', `dir=${dir}`)
      const text = await ar.page.getByTestId('release-control').textContent()
      expect(/تم الإصدار|لم تُصدَر/.test(text), `release control reads: ${text}`)
      await ar.page.screenshot({ path: path.join(OUT, '05_author_arabic.png') })
      await ar.ctx.close()
    })

    for (const who of [author, viewer]) {
      if (who.errors.length) results.push({ step: 'no uncaught page errors', ok: false, detail: who.errors.slice(0, 5) })
    }
  } finally {
    await browser.close()
  }
}

async function cleanup() {
  if (!adminToken) return
  if (made.report) await api('DELETE', `/reports/${made.report}`, adminToken)
  for (const id of made.users) await api('DELETE', `/admin/users/${id}`, adminToken)
  if (made.role) await api('DELETE', `/admin/roles/${made.role}`, adminToken)
}

try {
  await main()
} catch (e) {
  results.push({ step: 'setup', ok: false, detail: String(e?.message ?? e) })
  log('FAIL setup -', String(e?.message ?? e))
} finally {
  await cleanup().catch(e => log('cleanup failed:', String(e)))
  fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify(results, null, 2))
  const failed = results.filter(r => !r.ok).length
  log(`${results.length - failed} passed, ${failed} failed -- ${OUT}`)
  process.exitCode = failed ? 1 : 0
}
