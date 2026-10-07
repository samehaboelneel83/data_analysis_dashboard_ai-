// UI reference captures: one screenshot of every page and significant
// sub-state of the app (106 screens), against a RUNNING stack.
//
//   node frontend/e2e/capture/capture_screens.mjs                  # every screen
//   node frontend/e2e/capture/capture_screens.mjs 07 13            # only sections 07 and 13
//   node frontend/e2e/capture/capture_screens.mjs --out /some/dir  # somewhere else
//   node frontend/e2e/capture/capture_screens.mjs --list           # print the screen list only
//
// Replaces the lost `.ds-sync/capture.mjs` that produced the 2026-09-24
// design-screenshots set. Same screen list (plus four redesign Ask AI states, 02-05..02-08), same file names, same viewport
// (1440x900, deviceScaleFactor 1), so a new run can be compared file by file
// with the old one.
//
// Default output: <repo>/../screenshots_2 (the folder next to this repo).
// Writes <section>/<name>.png, .results.json (same shape as the old run),
// MANIFEST.md and _contact-sheets/contact-sheet-1..3.png.
//
// Environment (all optional):
//   CAPTURE_BASE_URL       app URL                      http://localhost:3001
//   CAPTURE_API_URL        API URL                      http://localhost:8000/api/v1
//   CAPTURE_EMAIL / CAPTURE_PASSWORD        admin login    admin@datalytics.local / demo-password
//   CAPTURE_ANALYST_EMAIL / CAPTURE_ANALYST_PASSWORD  non-admin login  demo-emea@example.invalid / demo-password
//                          (seeded analyst whose row security limits it to Europe; see CLAUDE.md)
//   CAPTURE_DATASET_ID     dataset for 03 / 13 / 14     170 if it exists, else picked from the API
//   CAPTURE_CONNECTION_ID  connection for the review    22 if it has a review, else picked
//   CAPTURE_REPORT_ID      dashboard for the builder    127 if it exists, else the one with most widgets
//   CAPTURE_MULTIPAGE_ID   dashboard with many pages    132 if it exists, else the one with most pages
//   CAPTURE_DATASET_FILTER text for "list filtered"     Demo
//   CAPTURE_ASK_CLARIFY    question that should need clarification
//   CAPTURE_ASK_ANSWER     question that should be answered
//   CAPTURE_ASK_CHART      question whose answer is charted (02-05, 02-06)
//   CAPTURE_ASK_ARABIC     question asked in the Arabic UI (02-07)
//   CAPTURE_ASK_TIMEOUT_S  how long to wait for a live answer   150
//   PLAYWRIGHT_EXECUTABLE  Chromium binary to use instead of Playwright's own
//   DEMO_PW_DIR            folder whose node_modules holds playwright (as the other e2e scripts)
//
// Reads only, with two exceptions: every Ask AI screen after 02-02 asks the
// live model and so creates a chat thread (six threads), and 07-33 mints a
// guest link and revokes it afterwards. No other write is made.
// Exit code 1 when any screen failed its preparation step.

import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '..', '..', '..', '..', '..')   // repo root (holds AI_data_tool/)
const BASE = (process.env.CAPTURE_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.CAPTURE_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const ADMIN = { email: process.env.CAPTURE_EMAIL || 'admin@datalytics.local',
                password: process.env.CAPTURE_PASSWORD || 'demo-password' }
const ANALYST = { email: process.env.CAPTURE_ANALYST_EMAIL || 'demo-emea@example.invalid',
                  password: process.env.CAPTURE_ANALYST_PASSWORD || 'demo-password' }
const VIEWPORT = { width: 1440, height: 900 }

const argv = process.argv.slice(2)
const outIdx = argv.indexOf('--out')
const OUT = path.resolve(outIdx >= 0 ? argv[outIdx + 1] : path.join(REPO, '..', 'screenshots_2'))
const ONLY = argv.filter((a, i) => (outIdx < 0 || i !== outIdx + 1) && /^\d{2}$/.test(a))

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const sleep = ms => new Promise(r => setTimeout(r, ms))
const ASK_TIMEOUT_MS = Number(process.env.CAPTURE_ASK_TIMEOUT_S || 150) * 1000
const LOADING_RE = /^(Loading…|جارٍ التحميل…|Loading data…|Preparing print view…)$/

// ------------------------------------------------------------ rate pacing
// The API allows 300 requests a minute per user (settings.rate_limit_*), and
// one dashboard load fires 50+ widget queries, so back-to-back builder screens
// trip it ("Rate limit exceeded"). Count the run's API calls over a rolling
// minute and wait before a screen when the budget is nearly spent.
const API_BUDGET = Number(process.env.CAPTURE_API_BUDGET || 200)
const apiHits = []
function countApi(page) {
  page.on('request', r => { if (r.url().includes('/api/v1/')) apiHits.push(Date.now()) })
}
async function pace() {
  for (;;) {
    while (apiHits.length && apiHits[0] < Date.now() - 60000) apiHits.shift()
    if (apiHits.length < API_BUDGET) return
    await sleep(Math.max(500, apiHits[0] + 60000 - Date.now() + 200))
  }
}
const RATE_RE = /Rate limit exceeded|rate-limited/

// ---------------------------------------------------------------- API helpers

async function apiLogin(who) {
  const r = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: JSON.stringify(who),
  })
  if (!r.ok) throw new Error(`API login failed for ${who.email}: HTTP ${r.status}`)
  return (await r.json()).access_token
}
async function api(token, url, init = {}) {
  const r = await fetch(API + url, { ...init, headers: {
    Authorization: `Bearer ${token}`, 'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/json', ...(init.headers || {}) } })
  if (!r.ok) return null
  const text = await r.text()
  return text ? JSON.parse(text) : {}
}

/** Fixed ids from the old run where they still exist, so before/after shows
 *  the same objects; otherwise the richest candidate from the API. */
async function discover(token) {
  const env = {}
  const datasets = (await api(token, '/datasets')) ?? []
  const pickDs = () => {
    const usable = datasets.filter(d => (d.row_count ?? 0) > 0 && d.filename && d.mode !== 'directquery')
    return usable.sort((a, b) => (b.col_count ?? 0) - (a.col_count ?? 0))[0] ?? datasets[0]
  }
  const dsWanted = Number(process.env.CAPTURE_DATASET_ID || 170)
  env.dataset = datasets.find(d => d.id === dsWanted) ?? pickDs()

  const sources = (await api(token, '/data-sources')) ?? []
  const connWanted = Number(process.env.CAPTURE_CONNECTION_ID || 22)
  const ordered = [...sources.filter(s => s.id === connWanted), ...sources.filter(s => s.id !== connWanted)]
  for (const s of ordered) {
    const rq = await api(token, `/data-sources/${s.id}/review`)
    if (rq && (rq.datasets?.length ?? 0) > 0) { env.reviewConn = s; break }
  }
  // The schema browser needs a source that answers with tables right now.
  for (const s of ordered.filter(s => s.type !== 'api')) {
    const sc = await api(token, `/data-sources/${s.id}/schema`)
    if (sc?.tables?.length) { env.liveConn = s; break }
  }
  env.anyConn = env.liveConn ?? env.reviewConn ?? sources[0]
  // No source has synced metadata yet: still show the review page (empty state).
  env.reviewConn ??= env.anyConn

  const reports = (await api(token, '/reports')) ?? []
  const widgets = r => (r.pages ?? []).reduce((n, p) => n + (p.widgets?.length ?? 0), 0)
  const normalPages = r => (r.pages ?? []).filter(p => !p.page_type || p.page_type === 'normal').length
  const editable = reports.filter(r => r.my_capability === 'data' || r.my_capability === 'edit')
  const repWanted = Number(process.env.CAPTURE_REPORT_ID || 127)
  env.report = reports.find(r => r.id === repWanted)
    ?? [...editable].sort((a, b) => widgets(b) - widgets(a))[0] ?? reports[0]
  const multiWanted = Number(process.env.CAPTURE_MULTIPAGE_ID || 132)
  env.multipage = reports.find(r => r.id === multiWanted)
    ?? [...reports].sort((a, b) => normalPages(b) - normalPages(a))[0]
  return env
}

// --------------------------------------------------------------- page helpers

async function go(page, route) {
  // A navigation the app starts itself (post-login redirect) can abort ours.
  await page.goto(BASE + route).catch(() => page.goto(BASE + route))
}

/** Network quiet, no loader or "Loading…" text visible, then a grace period. */
async function settle(page, extra = 600) {
  // The builder polls for revisions, so the network never fully idles there.
  await page.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => {})
  await page.waitForFunction(re => {
    // Only what is on screen counts: widgets below the fold load lazily on
    // scroll, so their "Loading…" never clears in a viewport capture.
    const rx = new RegExp(re)
    const onScreen = e => { if (!e.offsetParent) return false
      const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth }
    if ([...document.querySelectorAll('.dl-loading')].some(onScreen)) return false
    return ![...document.querySelectorAll('p, div, span')]
      .some(el => el.children.length === 0 && rx.test((el.textContent || '').trim()) && onScreen(el))
  }, LOADING_RE.source, { timeout: 20000 }).catch(() => {})
  await page.waitForTimeout(extra)
}

const h1 = (page, name) => page.getByRole('heading', { level: 1, name }).first()
  .waitFor({ timeout: 15000 })

async function builderReady(page) {
  await page.getByTestId('builder-header').waitFor({ timeout: 20000 })
  // Widgets draw into role=figure; wait until the visible ones stop loading.
  await page.waitForFunction(() => {
    const figs = [...document.querySelectorAll('[data-widget-id] [role=figure], [data-print-widget] [role=figure]')]
    if (!figs.length) return !!document.querySelector('[data-testid=empty-page]')
    const vis = figs.filter(f => { const r = f.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0 })
    return vis.every(f => !/Loading…/.test(f.textContent || ''))
  }, null, { timeout: 25000 }).catch(() => {})
  await settle(page, 800)
}

const panebar = page => page.locator('.dl-panebar')
async function openPane(page, name) {
  await panebar(page).getByRole('button', { name, exact: true }).click()
  await settle(page, 700)
}
async function openMorePanel(page, item) {
  await panebar(page).getByRole('button', { name: 'More panels' }).click()
  await page.getByRole('menu', { name: 'More panels' }).getByRole('menuitem', { name: item, exact: true }).click()
  await settle(page, 700)
}
const header = page => page.getByTestId('builder-header')
async function openShare(page) {
  await header(page).getByRole('button', { name: 'Share', exact: true }).click()
  await page.getByRole('menu').first().waitFor()
}

async function datasetPage(page, env, tab) {
  await go(page, `/datasets/${env.dataset.id}`)
  await page.getByRole('tablist', { name: 'Dataset sections' }).waitFor({ timeout: 20000 })
  if (tab) await page.getByRole('tablist', { name: 'Dataset sections' })
    .getByRole('tab', { name: tab, exact: true }).click()
  await settle(page)
}
async function openDatasetShare(page) {
  await page.getByRole('button', { name: 'Share', exact: true }).first().click()
  await page.getByRole('dialog', { name: 'Share dataset' }).waitFor()
  await settle(page, 400)
}

async function reviewPage(page, env, tab) {
  if (!env.reviewConn) throw new Error('no connections exist')
  await go(page, `/connections/${env.reviewConn.id}/review`)
  await h1(page, 'Review data source')
  // A sync still running reloads the page every 1.5s; wait it out.
  await page.getByRole('button', { name: 'Run sync' }).waitFor({ timeout: 20000 }).catch(() => {})
  await page.waitForFunction(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.textContent?.trim() === 'Run sync')
    return b && !b.disabled
  }, null, { timeout: 30000 }).catch(() => {})
  if (tab) await page.getByRole('tablist', { name: 'Review sections' }).getByRole('tab', { name: tab }).click()
  else await page.locator('.react-flow__node').first().waitFor({ timeout: 15000 }).catch(() => {})
  await settle(page, tab ? 700 : 1500)   // fitView animates after mount
}

async function connectionsPage(page) {
  await go(page, '/connections')
  await h1(page, 'Connections')
  await settle(page)
}

async function askScoped(page, env) {
  await go(page, `/ask?dataset=${env.dataset.id}`)
  await page.getByRole('complementary', { name: 'History' }).waitFor({ timeout: 20000 })
  // Start from a clean thread rather than the last one for this dataset.
  const fresh = page.getByRole('button', { name: 'New chat' })
  if (await fresh.count()) await fresh.first().click()
  await page.getByRole('textbox', { name: 'Your question' }).waitFor({ timeout: 20000 })
  await settle(page)
}
async function ask(page, question, done) {
  const box = page.getByRole('textbox', { name: 'Your question' })
  await box.fill(question)
  await page.getByRole('button', { name: 'Send' }).click()
  // Live model: can be slow. Stop early if it reports a failure.
  const failed = page.getByText('Could not answer that').or(page.getByTestId('ai-limit'))
  await done.or(failed).first().waitFor({ timeout: ASK_TIMEOUT_MS })
  if (await failed.count()) throw new Error('Ask AI could not answer (is the model server reachable?)')
  await settle(page, 1200)
}

/** Hold or fail one API path (exact pathname, so sub-resources pass). */
async function interceptPath(page, pathname, mode) {
  await page.route(u => new URL(u).pathname === pathname, route => {
    if (route.request().method() !== 'GET') return route.continue()
    if (mode === 'hold') return            // never answered: the page stays loading
    return route.fulfill({ status: 500, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Simulated failure for the UI capture' }) })
  })
}

// --------------------------------------------------------------- screen list
// [section, file, route, description, options, prepare(page, env)]
// options: anon (signed out), as: 'analyst', theme: 'dark', lang: 'ar', settleMs

const S = []
const add = (section, file, route, desc, opts, prep) => S.push({ section, file, route, desc, ...opts, prep })
const R = env => `/reports/${env.report.id}`

// 00 auth
add('00-auth', 'login', '/login', 'Sign-in screen, default state', { anon: true }, async page => {
  await go(page, '/login')
  await page.getByRole('button', { name: 'Sign In', exact: true }).waitFor()
  await settle(page, 400)
})
add('00-auth', 'login-error', '/login', 'Sign-in screen after a rejected credential', { anon: true }, async page => {
  await go(page, '/login')
  await page.getByLabel('Email', { exact: true }).fill(ADMIN.email)
  await page.getByLabel('Password', { exact: true }).fill('wrong-password-for-capture')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.locator('.dl-auth__card').getByRole('alert').waitFor()
  await settle(page, 400)
})

// 01 home
add('01-home', 'home', '/', 'Landing page: recents, dashboards, datasets', {}, async page => {
  await go(page, '/'); await h1(page, 'Home'); await settle(page)
})

// 02 Ask AI
add('02-ask-ai', 'initial', '/ask', 'Ask AI before any question (no data chosen yet)', {}, async page => {
  await go(page, '/ask')
  await page.getByRole('button', { name: 'What to ask about' }).first().waitFor({ timeout: 20000 })
  await settle(page)
})
add('02-ask-ai', 'dataset-chosen', '/ask', 'Ask AI with a dataset chosen, fresh thread', {}, async (page, env) => {
  await askScoped(page, env)
})
add('02-ask-ai', 'clarification', '/ask', 'Ask AI asking back for detail when a question names an unknown column',
  { settleMs: 2000 }, async (page, env) => {
    await askScoped(page, env)
    await ask(page, process.env.CAPTURE_ASK_CLARIFY || 'What is the average flux_capacitor_level by quarter?',
      page.locator('.dl-answer-clarify, [data-testid=answer-source]').first())
    if (!await page.locator('.dl-answer-clarify').count()) throw new Error('model answered instead of asking back')
  })
add('02-ask-ai', 'answered', '/ask', 'Ask AI answering a resolvable question (live model, answer + rows)',
  { settleMs: 2000 }, async (page, env) => {
    await askScoped(page, env)
    await ask(page, process.env.CAPTURE_ASK_ANSWER || 'How many rows are there, broken down by the first category column?',
      page.getByTestId('answer-source'))
  })

// The same thread, in any UI language: these screens also run in Arabic, where
// the accessible names above are translated, so they use the app's classes.
async function askAnyLang(page, env, question) {
  await go(page, `/ask?dataset=${env.dataset.id}`)
  const box = page.locator('.dl-chat__composer textarea')
  await box.waitFor({ timeout: 20000 })
  const fresh = page.locator('aside button').filter({ hasText: /New chat|محادثة جديدة/ })
  if (await fresh.count()) { await fresh.first().click(); await page.waitForTimeout(500) }
  await settle(page)
  await box.fill(question)
  await box.press('Enter')
  const done = page.locator('[data-testid=answer-source], .dl-answer-clarify')
  const failed = page.locator('.dl-answer-error, [data-testid=ai-limit]')
  await done.or(failed).first().waitFor({ timeout: ASK_TIMEOUT_MS })
  if (await failed.count()) throw new Error('Ask AI could not answer (is the model server reachable?)')
  await settle(page, 1200)
}
const ASK_CHART = process.env.CAPTURE_ASK_CHART
  || 'What is the average of the first numeric column for each value of the first category column?'
add('02-ask-ai', 'answer-chart', '/ask', 'Ask AI answer drawn as a chart, rows open under it (live model)',
  { settleMs: 2000 }, async (page, env) => {
    await askAnyLang(page, env, ASK_CHART)
    if (!await page.getByTestId('result-chart').count()) throw new Error('the answer was not charted')
    await page.locator('.dl-result__rows-toggle').first().click()
    await settle(page, 400)
  })
add('02-ask-ai', 'answer-sql-open', '/ask', 'Ask AI answer with "Show SQL" open (live model)',
  { settleMs: 2000 }, async (page, env) => {
    await askAnyLang(page, env, ASK_CHART)
    await page.getByRole('button', { name: 'Show SQL' }).first().click()
    await page.locator('.dl-sql__code').first().waitFor({ timeout: 20000 })
    await settle(page, 400)
  })
add('02-ask-ai', 'answer-arabic', '/ask', 'Ask AI question and answer in the Arabic UI (live model, RTL)',
  { settleMs: 2000, lang: 'ar' }, async (page, env) => {
    await askAnyLang(page, env, process.env.CAPTURE_ASK_ARABIC
      || 'ما متوسط أول عمود رقمي لكل قيمة من أول عمود فئوي؟ أجب بالعربية.')
    await page.locator('.dl-result__rows-toggle').first().click().catch(() => {})
    await settle(page, 400)
  })
add('02-ask-ai', 'clarification-arabic', '/ask', 'Ask AI asking back for detail in the Arabic UI (live model, RTL)',
  { settleMs: 2000, lang: 'ar' }, async (page, env) => {
    await askAnyLang(page, env, process.env.CAPTURE_ASK_CLARIFY
      || 'What is the average flux_capacitor_level by quarter?')
    if (!await page.locator('.dl-answer-clarify').count()) throw new Error('model answered instead of asking back')
  })

// 03 datasets
const datasetsList = async page => { await go(page, '/datasets'); await h1(page, 'Datasets'); await settle(page) }
// The list search box only renders once there are 8+ items (ListFilter).
async function search(page, name, text) {
  const box = page.getByRole('searchbox', { name })
  if (!await box.count()) throw new Error(`no "${name}" box: the list shows it only with 8 or more items`)
  await box.fill(text)
}
add('03-datasets', 'list', '/datasets', 'Dataset list, unfiltered', {}, datasetsList)
add('03-datasets', 'list-filtered', '/datasets', 'Dataset list filtered to real datasets via the page search box', {},
  async page => {
    await datasetsList(page)
    await search(page, 'Search datasets', process.env.CAPTURE_DATASET_FILTER || 'Demo')
    await settle(page, 500)
  })
add('03-datasets', 'list-no-match', '/datasets', 'Dataset list, search with no matches (empty state)', {}, async page => {
  await datasetsList(page)
  await search(page, 'Search datasets', 'zzqx-no-such-dataset')
  await page.locator('.dl-nomatch').waitFor()
  await settle(page, 300)
})
add('03-datasets', 'row-actions-menu', '/datasets', 'Per-dataset row actions menu open', {}, async page => {
  await datasetsList(page)
  await page.getByRole('button', { name: /^More actions for dataset / }).first().click()
  await page.getByRole('menu', { name: /^More actions for dataset / }).waitFor()
  await page.waitForTimeout(300)
})
for (const [n, file, tab, desc, ms] of [
  ['05', 'detail-overview', null, 'Dataset detail - Overview tab'],
  ['06', 'detail-data', 'Data', 'Dataset detail - Data tab (row grid)'],
  ['07', 'detail-meaning', 'Meaning', 'Dataset detail - Meaning tab (column semantics)'],
  ['08', 'detail-analysis', 'Analysis', 'Dataset detail - Analysis tab (statistics)', 2500],
  ['09', 'detail-alerts', 'Alerts', 'Dataset detail - Alerts tab'],
  ['10', 'detail-models', 'Models', 'Dataset detail - Models tab'],
]) add('03-datasets', file, '/datasets/:dataset', desc, ms ? { settleMs: ms } : {},
  (page, env) => datasetPage(page, env, tab))
// Aggregates shows only for DirectQuery datasets now; ?tab=aggregates still opens it.
add('03-datasets', 'detail-aggregates', '/datasets/:dataset', 'Dataset detail - Aggregates tab (via ?tab=aggregates; the tab is DirectQuery-only now)',
  {}, async (page, env) => {
    await go(page, `/datasets/${env.dataset.id}?tab=aggregates`)
    await page.getByRole('tablist', { name: 'Dataset sections' }).waitFor({ timeout: 20000 })
    await settle(page)
  })
add('03-datasets', 'detail-share-dialog', '/datasets/:dataset', 'Dataset share dialog', {}, async (page, env) => {
  await datasetPage(page, env); await openDatasetShare(page)
})

// 04 upload
add('04-upload', 'upload', '/upload', 'File upload / import screen', {}, async page => {
  await go(page, '/upload'); await h1(page, 'Upload a dataset'); await settle(page)
})

// 05 connections
add('05-connections', 'list', '/connections', 'Live connections list', {}, connectionsPage)
add('05-connections', 'row-actions-menu', '/connections', 'Per-connection actions menu open (Metadata, Edit, Delete)', {},
  async (page, env) => {
    await connectionsPage(page)
    await page.getByRole('button', { name: `More actions for ${env.anyConn.name}` }).first().click()
    await page.getByRole('menu', { name: `More actions for ${env.anyConn.name}` }).waitFor()
    await page.waitForTimeout(300)
  })
add('05-connections', 'new-connection-modal', '/connections', 'New connection modal', {}, async page => {
  const catalog = page.waitForResponse(r => r.url().includes('/data-sources/connectors'), { timeout: 15000 }).catch(() => {})
  await connectionsPage(page); await catalog
  const dialog = page.getByRole('dialog', { name: 'New connection' })
  for (let i = 0; i < 3 && !await dialog.isVisible(); i++) {
    await page.getByRole('button', { name: 'New Connection' }).click(); await page.waitForTimeout(800)
  }
  await dialog.waitFor({ timeout: 5000 })
  await settle(page, 400)
})
add('05-connections', 'schema-browser', '/connections', 'Schema browser listing tables on a live connection',
  { settleMs: 3000 }, async (page, env) => {
    if (!env.liveConn) throw new Error('no connection answered /schema with tables')
    await connectionsPage(page)
    await page.locator('.dl-conn').filter({ hasText: env.liveConn.name }).first()
      .getByRole('button', { name: 'Browse' }).click()
    const dialog = page.getByRole('dialog', { name: `Browse ${env.liveConn.name}` })
    await dialog.waitFor()
    await dialog.getByText('Loading…').waitFor({ state: 'detached', timeout: 30000 }).catch(() => {})
    await settle(page, 1000)
  })
for (const [file, tab, desc, ms] of [
  ['review-relationships', null, 'Source review - Relationships graph', 2000],
  ['review-columns', /^Columns \(\d+\)$/, 'Source review - Columns'],
  ['review-entities', /^Entities \(\d+\)$/, 'Source review - Entities'],
  ['review-business-terms', 'Business terms', 'Source review - Business terms / glossary'],
  ['review-schema-drift', 'Schema drift', 'Source review - Schema drift'],
  ['review-source-health', 'Source health', 'Source review - Source health'],
]) add('05-connections', file, '/connections/:conn/review', desc, ms ? { settleMs: ms } : {},
  (page, env) => reviewPage(page, env, tab))

// 06 lineage
add('06-lineage', 'graph', '/lineage', 'Lineage graph across sources, datasets and dashboards', { settleMs: 2500 },
  async page => { await go(page, '/lineage'); await h1(page, 'Lineage'); await settle(page, 1200) })

// 07 dashboards
const reportsList = async page => { await go(page, '/reports'); await h1(page, 'Dashboards'); await settle(page) }
const builder = async (page, env) => { await go(page, R(env)); await builderReady(page) }
add('07-dashboards', 'list', '/reports', 'Dashboard list with the workspace tree', {}, reportsList)
add('07-dashboards', 'list-no-match', '/reports', 'Dashboard list, search with no matches (empty state)', {}, async page => {
  await reportsList(page)
  await search(page, 'Search dashboards', 'zzqx-no-such-dashboard')
  await page.locator('p.dl-nomatch').waitFor()
  await settle(page, 300)
})
add('07-dashboards', 'builder-canvas', '/reports/:report', 'Report builder - edit mode canvas', { settleMs: 2000 }, builder)
add('07-dashboards', 'builder-view-mode', '/reports/:report', 'Report builder - VIEW mode, what a consumer sees (no writes fired)',
  { settleMs: 2000 }, async (page, env) => {
    await builder(page, env)
    await header(page).getByRole('button', { name: 'View mode', exact: true }).click()
    await page.getByRole('tablist', { name: 'Pages' }).waitFor({ timeout: 10000 }).catch(() => {})
    await builderReady(page)
  })
add('07-dashboards', 'builder-tab-charts', '/reports/:report', 'Left rail - Charts tab (chart picker)', {}, async (page, env) => {
  await builder(page, env)
  await page.getByRole('tablist', { name: 'Builder panel' }).getByRole('tab', { name: 'Charts' }).click()
  await page.getByLabel('Find a chart').waitFor(); await settle(page, 400)
})
add('07-dashboards', 'builder-tab-more', '/reports/:report', 'Left rail - More tab (templates, report filters)', {}, async (page, env) => {
  await builder(page, env)
  await page.getByRole('tablist', { name: 'Builder panel' }).getByRole('tab', { name: 'More' }).click()
  await settle(page, 400)
})
add('07-dashboards', 'pane-data', '/reports/:report', 'Add-dataset picker dialog (Fields tab "+ Add Dataset"; the old Data pane)', {},
  async (page, env) => {
    await builder(page, env)
    await page.getByRole('tablist', { name: 'Builder panel' }).getByRole('tab', { name: 'Fields' }).click()
    await page.getByRole('button', { name: '+ Add Dataset' }).click()
    await page.getByRole('dialog', { name: /^(Add another dataset to this dashboard|Choose the data for this dashboard)$/ }).waitFor()
    await settle(page, 500)
  })
add('07-dashboards', 'pane-model', '/reports/:report', 'Model view (view-strip "Model"; relationships between the report\'s datasets)', {},
  async (page, env) => {
    await builder(page, env)
    await page.getByTestId('view-strip').getByRole('button', { name: 'Model', exact: true }).click()
    await page.getByTestId('model-view').waitFor(); await settle(page, 600)
  })
for (const [n, file, pane, ms] of [
  ['09', 'pane-outline', 'Outline'], ['10', 'pane-suggest', 'Suggest', 3000], ['11', 'pane-review', 'Review'],
  ['12', 'pane-comments', 'Comments'], ['13', 'pane-parameters', 'Parameters'], ['14', 'pane-schedule', 'Schedule'],
  ['15', 'pane-ask', 'Ask'], ['16', 'pane-insights', 'Insights', 3000],
]) add('07-dashboards', file, '/reports/:report', `Builder pane - ${pane}`, ms ? { settleMs: ms } : {},
  async (page, env) => { await builder(page, env); await openPane(page, pane) })
add('07-dashboards', 'menu-more-panels', '/reports/:report', 'The "More panels" menu open (9 further panes)', {}, async (page, env) => {
  await builder(page, env)
  await panebar(page).getByRole('button', { name: 'More panels' }).click()
  await page.getByRole('menu', { name: 'More panels' }).waitFor(); await page.waitForTimeout(300)
})
for (const [file, item] of [
  ['pane-selection', 'Selection'], ['pane-bookmarks', 'Bookmarks'], ['pane-tab-order', 'Tab order'],
  ['pane-performance', 'Performance'], ['pane-report-rules', 'Report rules'], ['pane-translations', 'Translations'],
  ['pane-version-history', 'Version history'], ['pane-mobile-layout', 'Mobile layout'], ['pane-sync-slicers', 'Sync slicers'],
]) add('07-dashboards', file, '/reports/:report', `Builder pane - ${item}`, {},
  async (page, env) => { await builder(page, env); await openMorePanel(page, item) })
add('07-dashboards', 'menu-export', '/reports/:report', 'Export menu (Print, PDF, Excel, Offline package)', {}, async (page, env) => {
  await builder(page, env)
  await header(page).getByRole('button', { name: 'Export', exact: true }).click()
  await page.getByRole('menuitem', { name: /^Print/ }).waitFor(); await page.waitForTimeout(300)
})
add('07-dashboards', 'menu-share', '/reports/:report', 'Share menu (copy link, guest links, your access, access by role)', {},
  async (page, env) => { await builder(page, env); await openShare(page); await page.waitForTimeout(300) })
add('07-dashboards', 'dialog-guest-links', '/reports/:report', 'Guest links dialog', {}, async (page, env) => {
  await builder(page, env); await openShare(page)
  await page.getByRole('menuitem', { name: /^Guest links/ }).click()
  await page.getByRole('dialog', { name: 'Guest links' }).waitFor(); await settle(page, 400)
})
add('07-dashboards', 'dialog-access-by-role', '/reports/:report', 'Access-by-role dialog', {}, async (page, env) => {
  await builder(page, env); await openShare(page)
  await page.getByRole('menuitem', { name: /^Access by role/ }).click()
  await page.getByRole('dialog', { name: 'Report access' }).waitFor(); await settle(page, 400)
})
add('07-dashboards', 'multipage', '/reports/:multipage', 'Multi-page dashboard, page tabs visible', { settleMs: 2000 },
  async (page, env) => { await go(page, `/reports/${env.multipage.id}`); await builderReady(page) })
add('07-dashboards', 'print-view', '/reports/:report/print', 'Print / PDF layout of a dashboard', { settleMs: 2500 },
  async (page, env) => {
    await go(page, `${R(env)}/print`)
    await page.getByRole('button', { name: 'Print / Save as PDF' }).waitFor({ timeout: 20000 })
    await builderReady(page).catch(() => {})
  })
add('07-dashboards', 'shared-public-link', '/shared/:token (signed out)',
  'Public shared-link view of a dashboard, as an anonymous recipient sees it', { anon: true, settleMs: 2000 },
  async (page, env) => {
    if (!env.shareToken) throw new Error('could not mint a guest link (report Restricted, or no edit rights)')
    await go(page, `/shared/${env.shareToken}`)
    await page.getByTestId('shared-page').waitFor({ timeout: 20000 })
    await settle(page, 1500)
  })

// 08-11 single pages
const simple = (section, file, route, title, desc, opts = {}) =>
  add(section, file, route, desc, opts, async page => { await go(page, route); await h1(page, title); await settle(page) })
simple('08-insights', 'hub', '/insights', 'Insights', 'Insights hub', { settleMs: 2000 })
simple('09-monitoring', 'jobs', '/monitoring/jobs', 'Refresh & jobs', 'Refresh & jobs')
simple('09-monitoring', 'deliveries', '/monitoring/deliveries', 'Deliveries', 'Scheduled deliveries')
simple('09-monitoring', 'activity', '/monitoring/activity', 'Activity', 'Activity feed')
for (const [file, route, title, desc, ms] of [
  ['users', '/admin/users', 'Users', 'Users'],
  ['roles', '/admin/roles', 'Roles', 'Roles'],
  ['org-units', '/admin/org-units', 'Organization chart', 'Organization chart'],
  ['row-security', '/admin/row-security-rules', 'Row security', 'Row security rules'],
  ['column-security', '/admin/column-security-rules', 'Column security', 'Column security rules'],
  ['connection-rules', '/admin/connection-rules', /^Connection rules/, 'Connection row policies (the rules Ask AI obeys)'],
  ['export-policy', '/admin/export-policy', 'Export policy', 'Export policy'],
  ['api-keys', '/admin/api-keys', 'API keys', 'API keys'],
  ['custom-connectors', '/admin/custom-connectors', 'Custom connectors', 'Custom connectors'],
  ['sso', '/admin/sso', 'Single sign-on', 'Single sign-on configuration'],
  ['maps', '/admin/maps', 'Maps', 'Maps / boundary sets', 2500],
  ['audit', '/admin/audit', 'Audit trail', 'Audit trail'],
]) simple('10-admin', file, route, title, desc, ms ? { settleMs: ms } : {})
simple('11-platform', 'organizations', '/platform/organizations', 'Organizations', 'Platform organizations (super-admin only)')

// 12 chrome
const home = async page => { await go(page, '/'); await h1(page, 'Home'); await settle(page) }
add('12-chrome', 'rail-collapsed', '/', 'Navigation rail collapsed to icons', {}, async page => {
  await home(page)
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await page.waitForTimeout(500)
})
add('12-chrome', 'command-palette', '/', 'Command palette (Ctrl+K) - jump to any page', {}, async page => {
  await home(page)
  await page.getByRole('button', { name: 'Search everything (Ctrl+K)' }).click()
  await page.getByRole('dialog', { name: 'Command palette' }).waitFor(); await page.waitForTimeout(400)
})
add('12-chrome', 'notifications-menu', '/', 'Notifications dropdown', {}, async page => {
  await home(page)
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await page.getByRole('menu', { name: 'Notifications list' }).waitFor(); await settle(page, 400)
})
add('12-chrome', 'account-menu', '/', 'Account menu (identity, org, sign out)', {}, async page => {
  await home(page)
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menu', { name: 'Account' }).waitFor(); await page.waitForTimeout(300)
})
add('12-chrome', 'language-menu', '/', 'Language switcher (English LTR / Arabic RTL)', {}, async page => {
  await home(page)
  await page.getByRole('button', { name: /^Language: / }).click()
  await page.getByRole('menu', { name: 'Language' }).waitFor(); await page.waitForTimeout(300)
})
add('12-chrome', 'rail-non-admin', '/ (non-admin)', 'Rail as a non-admin analyst - no Admin, Monitoring or Platform sections',
  { as: 'analyst' }, home)
add('12-chrome', 'dashboards-non-admin', '/reports (non-admin)', 'Dashboard list as a non-admin analyst (row security in effect)',
  { as: 'analyst' }, reportsList)

// 13 themes
add('13-themes', 'dark-home', '/', 'Home in dark mode', { theme: 'dark' }, home)
add('13-themes', 'dark-datasets', '/datasets', 'Dataset list in dark mode', { theme: 'dark' }, datasetsList)
add('13-themes', 'dark-builder', '/reports/:report', 'Report builder in dark mode', { theme: 'dark', settleMs: 2000 }, builder)
add('13-themes', 'dark-admin-users', '/admin/users', 'Admin users in dark mode', { theme: 'dark' },
  async page => { await go(page, '/admin/users'); await h1(page, 'Users'); await settle(page) })
add('13-themes', 'dark-dialog', '/datasets/:dataset', 'A dialog in dark mode', { theme: 'dark' },
  async (page, env) => { await datasetPage(page, env); await openDatasetShare(page) })
// Arabic: wait on the URL's content, not English headings.
const arPage = route => async page => {
  await go(page, route)
  await page.locator('h1').first().waitFor({ timeout: 20000 })
  await settle(page)
}
add('13-themes', 'rtl-home', '/', 'Home in Arabic (RTL)', { lang: 'ar' }, arPage('/'))
add('13-themes', 'rtl-datasets', '/datasets', 'Dataset list in Arabic (RTL)', { lang: 'ar' }, arPage('/datasets'))
add('13-themes', 'rtl-builder', '/reports/:report', 'Report builder in Arabic (RTL) - chart internals stay LTR',
  { lang: 'ar', settleMs: 2000 }, builder)
add('13-themes', 'rtl-admin-users', '/admin/users', 'Admin users in Arabic (RTL)', { lang: 'ar' }, arPage('/admin/users'))
add('13-themes', 'rtl-dark-home', '/', 'Home in Arabic RTL + dark mode', { lang: 'ar', theme: 'dark' }, arPage('/'))

// 14 states
add('14-states', 'loading-dataset', '/datasets/:dataset', 'Dataset detail while its data request is still in flight (loading state)',
  { settleMs: 0 }, async (page, env) => {
    await interceptPath(page, apiPath(`/datasets/${env.dataset.id}`), 'hold')
    await go(page, `/datasets/${env.dataset.id}`)
    await page.getByText('Loading…').first().waitFor({ timeout: 15000 })
    await page.waitForTimeout(600)
  })
add('14-states', 'error-dataset', '/datasets/:dataset', 'Dataset detail when its request fails (LoadError with Try again)',
  { settleMs: 0 }, async (page, env) => {
    await interceptPath(page, apiPath(`/datasets/${env.dataset.id}`), 'fail')
    await go(page, `/datasets/${env.dataset.id}`)
    await page.getByRole('button', { name: 'Try again' }).waitFor({ timeout: 20000 })
    await page.waitForTimeout(400)
  })
add('14-states', 'error-dashboard', '/reports/:report', 'Report builder when the report request fails',
  { settleMs: 0 }, async (page, env) => {
    await interceptPath(page, apiPath(`/reports/${env.report.id}`), 'fail')
    await go(page, R(env))
    await page.getByRole('button', { name: 'Try again' }).waitFor({ timeout: 20000 })
    await page.waitForTimeout(400)
  })
add('14-states', 'route-loader', '/lineage', 'The route-transition loader (bouncing balls) while a lazy chunk loads',
  { settleMs: 0 }, async page => {
    // Vite dev serves /src/pages/Lineage.tsx; a production build serves assets/Lineage-<hash>.js.
    await page.route(u => /\/(src\/pages\/Lineage\.tsx|assets\/Lineage-[^/]*\.js)$/.test(new URL(u).pathname), () => {})
    await go(page, '/lineage')
    await page.locator('.dl-loading').waitFor({ timeout: 20000 })
    await page.waitForTimeout(700)
  })

function apiPath(p) { return new URL(API).pathname.replace(/\/$/, '') + p }

// Number files within each section in list order: 00-auth-01-login.png ...
{
  const n = {}
  for (const s of S) {
    n[s.section] = (n[s.section] ?? 0) + 1
    s.name = `${s.section}-${String(n[s.section]).padStart(2, '0')}-${s.file}.png`
    s.rel = path.join(s.section, s.name)
  }
}

// --------------------------------------------------------------------- run

if (argv.includes('--list')) {      // print the screen list and stop
  for (const s of S) console.log(s.rel.split(path.sep).join('/'), '|', s.route, '|', s.desc)
  process.exit(0)
}

async function uiLogin(browser, who) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await go(page, '/login')
  await page.getByLabel('Email', { exact: true }).fill(who.email)
  await page.getByLabel('Password', { exact: true }).fill(who.password)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  const file = path.join(os.tmpdir(), `capture-state-${who.email.replace(/\W+/g, '_')}.json`)
  await ctx.storageState({ path: file })
  await ctx.close()
  return file
}

async function health(page) {
  return page.evaluate(() => {
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim()
    return {
      chars: text.length,
      alerts: document.querySelectorAll('[role=alert]').length,
      loading: document.querySelectorAll('.dl-loading').length
        + [...document.querySelectorAll('p,div,span')].filter(e => {
          if (e.children.length || !e.offsetParent || !/^(Loading…|جارٍ التحميل…)$/.test((e.textContent || '').trim())) return false
          const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight
        }).length,
      charts: document.querySelectorAll('svg.recharts-surface, [role=figure] svg').length,
      sample: text.slice(0, 90),
    }
  }).catch(() => ({ chars: 0, alerts: 0, loading: 0, charts: 0, sample: '' }))
}

const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE
  ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE } : {})
const results = []
let shareLink = null
try {
  const screens = S.filter(s => !ONLY.length || ONLY.includes(s.section.slice(0, 2)))
  log(`${screens.length} screens -> ${OUT}`)
  const token = await apiLogin(ADMIN)
  const env = await discover(token)
  log('using dataset', env.dataset?.id, env.dataset?.name, '| review connection', env.reviewConn?.id,
    '| live connection', env.liveConn?.id, '| report', env.report?.id, '| multipage', env.multipage?.id)
  if (screens.some(s => s.file === 'shared-public-link') && env.report) {
    shareLink = await api(token, `/reports/${env.report.id}/share-links`, {
      method: 'POST', body: JSON.stringify({ expires_days: 1, pinned: false }) })
    if (shareLink) shareLink.reportId = env.report.id
    env.shareToken = shareLink?.token
  }
  const states = { admin: await uiLogin(browser, ADMIN) }
  if (screens.some(s => s.as === 'analyst')) {
    states.analyst = await uiLogin(browser, ANALYST).catch(e => { log('analyst login failed:', e.message); return null })
  }

  for (const s of screens) {
    fs.mkdirSync(path.join(OUT, s.section), { recursive: true })
    const state = s.anon ? undefined : states[s.as ?? 'admin']
    const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1,
      ...(state ? { storageState: state } : {}) })
    // Same starting UI for every screen, whatever the last run left in storage.
    await ctx.addInitScript(({ theme, lang }) => {
      try {
        localStorage.setItem('theme', theme)
        localStorage.setItem('datalytics.language', lang)
        localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
        localStorage.setItem('datalytics:builder-top-collapsed', '0')
        localStorage.setItem('datalytics:builder-left-tab', 'fields')
        localStorage.removeItem('datalytics.builderPanels')
        if (!sessionStorage.getItem('capture-init')) {
          sessionStorage.setItem('capture-init', '1')
          for (const k of Object.keys(localStorage)) if (k.startsWith('rail-expanded:')) localStorage.removeItem(k)
        }
      } catch { /* storage blocked */ }
    }, { theme: s.theme ?? 'light', lang: s.lang ?? 'en' })
    let page = await ctx.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(String(e.message || e).slice(0, 200)))
    page.on('console', m => { if (m.type() === 'error' && /Error/.test(m.text())) errors.push(m.text().slice(0, 200)) })
    const t0 = Date.now()
    let status = 'ok'
    for (let attempt = 1; attempt <= 3; attempt++) {
      status = 'ok'
      await pace()
      countApi(page)
      try {
        if (s.as === 'analyst' && !state) throw new Error('analyst account could not sign in')
        await s.prep(page, env)
        if (s.settleMs) await page.waitForTimeout(Math.max(0, s.settleMs - 600))
      } catch (e) {
        status = 'PREP FAILED: ' + String(e.message || e).split('\n')[0].slice(0, 200)
      }
      const limited = RATE_RE.test(await page.evaluate(() => document.body?.innerText || '').catch(() => ''))
      if (!limited || attempt === 3) { if (limited) status = 'RATE LIMITED (raise RATE_LIMIT_REQUESTS_PER_WINDOW or lower CAPTURE_API_BUDGET)'; break }
      log('rate-limited, waiting a minute then retrying', s.name)
      await sleep(61000)
      await page.close(); page = await ctx.newPage()
      page.on('pageerror', e => errors.push(String(e.message || e).slice(0, 200)))
    }
    await page.screenshot({ path: path.join(OUT, s.rel) }).catch(e => { status = 'SHOT FAILED: ' + e.message })
    const h = await health(page)
    const flags = []
    if (h.chars < 200) flags.push(`THIN(${h.chars}ch)`)
    if (h.alerts) flags.push(`ALERT(${h.alerts})`)
    if (h.loading) flags.push('LOADING')
    const route = s.route.replace(':dataset', env.dataset?.id).replace(':conn', env.reviewConn?.id)
      .replace(':multipage', env.multipage?.id).replace(':report', env.report?.id)
    results.push({ section: s.section, file: s.file, route, ...(s.anon ? { anon: true } : {}),
      ...(s.as ? { as: s.as } : {}), ...(s.theme ? { theme: s.theme } : {}), ...(s.lang ? { lang: s.lang } : {}),
      ...(s.settleMs != null ? { settleMs: s.settleMs } : {}), desc: s.desc, name: s.name, rel: s.rel,
      status, h, flags, errors: [...new Set(errors)].slice(0, 5), ms: Date.now() - t0 })
    log(status === 'ok' ? 'ok  ' : 'FAIL', s.name, status === 'ok' ? flags.join(' ') : status)
    await ctx.close()
  }
  for (const f of Object.values(states)) if (f) fs.rmSync(f, { force: true })

  // Keep results for screens not captured in this (partial) run.
  const resFile = path.join(OUT, '.results.json')
  let merged = results
  if (ONLY.length && fs.existsSync(resFile)) {
    const old = JSON.parse(fs.readFileSync(resFile, 'utf8')).filter(r => !results.some(n => n.name === r.name))
    merged = [...old, ...results].sort((a, b) => a.name.localeCompare(b.name))
  }
  fs.writeFileSync(resFile, JSON.stringify(merged, null, 1))
  writeManifest(merged, env)
  await contactSheets(browser, merged)
} finally {
  // Revoke the guest link minted for screen 33, whatever happened above.
  if (shareLink?.id) {
    const token = await apiLogin(ADMIN).catch(() => null)
    if (token) await api(token, `/reports/${shareLink.reportId}/share-links/${shareLink.id}`, { method: 'DELETE' })
      .catch(() => log('could not revoke guest link', shareLink.id, '- revoke it under Share > Guest links'))
  }
  await browser.close()
}

const failed = results.filter(r => r.status !== 'ok')
log(`${results.length - failed.length}/${results.length} captured cleanly -> ${OUT}`)
for (const f of failed) log('  ', f.name, '-', f.status)
process.exitCode = failed.length ? 1 : 0

// ---------------------------------------------------------------- outputs

function writeManifest(rows, env) {
  const TITLES = {
    '00-auth': 'Authentication', '01-home': 'Home', '02-ask-ai': 'Ask AI (natural-language querying)',
    '03-datasets': 'Datasets', '04-upload': 'Upload', '05-connections': 'Connections & source review',
    '06-lineage': 'Lineage', '07-dashboards': 'Dashboards / report builder', '08-insights': 'Insights',
    '09-monitoring': 'Monitoring', '10-admin': 'Administration', '11-platform': 'Platform (super-admin)',
    '12-chrome': 'Global chrome: rail, menus, permissions', '13-themes': 'Dark mode & Arabic RTL',
    '14-states': 'Loading, error and empty states',
  }
  const ok = rows.filter(r => r.status === 'ok').length
  const lines = [
    '# Datalytics — UI reference captures', '',
    `- **Captured:** ${new Date().toISOString().slice(0, 10)} · ${ok}/${rows.length} screens`,
    `- **Viewport:** ${VIEWPORT.width}×${VIEWPORT.height}, desktop, \`deviceScaleFactor: 1\``,
    `- **Source:** live app at \`${BASE}\``,
    `- **Signed in as:** \`${ADMIN.email}\` (non-admin screens: \`${ANALYST.email}\`)`,
    `- **Objects used:** dataset ${env.dataset?.id} · connection ${env.reviewConn?.id} · dashboard ${env.report?.id} · multi-page dashboard ${env.multipage?.id}`,
    '- **Regenerate:** `node AI_data_tool/data_analytics/frontend/e2e/capture/capture_screens.mjs` (add section prefixes to limit, e.g. `07 13`)',
    '', 'File names match the 2026-09-24 `design-screenshots` set one for one, so the two folders can be compared file by file.',
    '', '## Screens',
  ]
  for (const sec of [...new Set(rows.map(r => r.section))]) {
    lines.push('', `### ${sec} — ${TITLES[sec] ?? sec}`, '', '| Screenshot | Route | What it shows | Status |', '|---|---|---|---|')
    for (const r of rows.filter(r => r.section === sec)) {
      lines.push(`| \`${r.name}\` | \`${r.route}\` | ${r.desc} | ${r.status === 'ok' ? 'ok' : r.status.replace(/\|/g, '/')} |`)
    }
  }
  fs.writeFileSync(path.join(OUT, 'MANIFEST.md'), lines.join('\n') + '\n')
}

async function contactSheets(browserRef, rows) {
  const shots = rows.filter(r => fs.existsSync(path.join(OUT, r.rel)))
  if (!shots.length) return
  const dir = path.join(OUT, '_contact-sheets')
  fs.mkdirSync(dir, { recursive: true })
  const per = Math.ceil(shots.length / 3)
  const ctx = await browserRef.newContext({ viewport: { width: 1500, height: 900 }, deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  for (let i = 0; i * per < shots.length; i++) {
    const cells = shots.slice(i * per, (i + 1) * per).map(r => {
      const b64 = fs.readFileSync(path.join(OUT, r.rel)).toString('base64')
      return `<figure><img src="data:image/png;base64,${b64}"><figcaption>${r.name}</figcaption></figure>`
    }).join('')
    await page.setContent(`<style>body{margin:12px;font:11px system-ui;background:#fff}
      main{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
      figure{margin:0}img{width:100%;border:1px solid #ccc;display:block}
      figcaption{padding:3px 0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}</style><main>${cells}</main>`)
    await page.screenshot({ path: path.join(dir, `contact-sheet-${i + 1}.png`), fullPage: true })
  }
  await ctx.close()
}
