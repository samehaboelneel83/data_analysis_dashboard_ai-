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
const themes0 = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const themes = process.env.ONE ? themes0.slice(0, 1) : themes0
const at = p => u => new URL(u).pathname === p
const now = new Date().toISOString()
const CONVS = [
  { id: 510, title: 'Average margin by region', data_source_id: null, dataset_ids: [1], created_at: now },
  { id: 509, title: 'Revenue vs. target by month', data_source_id: null, dataset_ids: [1], created_at: now },
  { id: 508, title: 'Units by channel', data_source_id: null, dataset_ids: [2], created_at: now },
  { id: 503, title: 'Top 10 products by margin', data_source_id: null, dataset_ids: [1], created_at: '2026-09-20T10:00:00' },
]
const RESULT = { step: 'q1', columns: ['region', 'avg_margin_pct'], total: 4, truncated: false,
  rows: [['Asia Pacific', 38.42], ['Europe', 34.17], ['Americas', 31.05], ['Africa', 27.66]] }
const SQL = 'SELECT region, ROUND(AVG(margin_pct), 2) AS avg_margin_pct\nFROM "Demo — Sales"\nGROUP BY region\nORDER BY avg_margin_pct DESC'
const L = (lang, en, ar) => (lang === 'ar' ? ar : en)
function answerMsg(lang, id = 2) {
  const text = L(lang, '**Asia Pacific** has the highest margin, averaging 38.4; **Africa** is lowest at 27.7 — a gap of 10.8 points.',
    'Asia Pacific هي الأعلى بمتوسط 38.4، وAfrica هي الأدنى عند 27.7 — بفارق 10.8 نقطة.')
  const claims = []
  for (const [n, row, kind] of [['38.4', 0, 'cell'], ['27.7', 3, 'cell'], ['10.8', null, 'difference']]) {
    const start = text.indexOf(n)
    claims.push({ start, end: start + n.length, text: n, status: 'traced',
      source: { result: 0, row, column: 'avg_margin_pct', value: n, kind, rows: row == null ? [0, 3] : undefined } })
  }
  return { id, role: 'assistant', content: text, created_at: now, run: { id: 701, status: 'ok', intent: 'aggregate', error: null,
    results: [RESULT], sql: [SQL], presentation: { format: 'bar', limit: null, x: 'region', y: 'avg_margin_pct' },
    context_objects: ['Demo — Sales'], evidence: { claims, untraced: 0 } } }
}
const user = (id, content) => ({ id, role: 'user', content, created_at: now, run: null })
const q1 = lang => L(lang, 'What is the average margin by department?', 'ما متوسط الهامش حسب القسم؟')
const clarify = (lang, id) => ({ id, role: 'assistant', created_at: now,
  content: L(lang, 'Did you mean the average margin by **region**, or is there a specific **department** column you intended to use?',
    'هل تقصد متوسط الهامش حسب **region**، أم هناك عمود **department** محدد تريد استخدامه؟'),
  run: { id: 700, status: 'needs_clarification', intent: null, error: null, results: [], sql: [], presentation: null, context_objects: null } })
const resolvedThread = lang => [user(1, q1(lang)), clarify(lang, 2), user(3, L(lang, 'Use region', 'استخدم region')), answerMsg(lang, 4)]
const screens = [
  { name: '01-no-dataset', url: '/ask' },
  { name: '02-first-run', url: '/ask?dataset=1', convs: [] },
  { name: '03-clarify', url: '/ask?dataset=1', msgs: lang => [user(1, q1(lang)), clarify(lang, 2)] },
  { name: '04-answer', url: '/ask?dataset=1', msgs: resolvedThread },
  { name: '05-answer-sql-open', url: '/ask?dataset=1', msgs: resolvedThread, sql: true },
  { name: '06-thinking', url: '/ask?dataset=1', msgs: resolvedThread, pending: lang => L(lang, 'Which product in Africa has the lowest margin?', 'أي منتج في Africa له أدنى هامش؟') },
  { name: '07-error', url: '/ask?dataset=1', msgs: lang => [...resolvedThread(lang), user(5, L(lang, 'How many orders got an A grade in each region?', 'كم طلبًا حصل على درجة A في كل منطقة؟')),
    { id: 6, role: 'assistant', created_at: now, content: '', run: { id: 702, status: 'failed', intent: null,
      error: 'Binder Error: Referenced column "grade" not found in FROM clause', results: [], sql: [], presentation: null, context_objects: null } }] },
  { name: '08-offline', url: '/ask?dataset=1', msgs: resolvedThread, offline: true },
].filter(s => !only || only.split(',').includes(s.name))

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
  await page.route(at('/api/v1/agent/conversations'), r => r.request().method() === 'GET' ? r.fulfill({ json: sc.convs ?? CONVS }) : r.continue())
  if (sc.msgs) await page.route(at('/api/v1/agent/conversations/510/messages'), r => r.fulfill({ json: sc.msgs(lang) }))
  await page.route(at('/api/v1/agent/runs/701'), r => r.fulfill({ json: { id: 701, status: 'ok', ms: 2400,
    plan: [{ id: 'q1', question: 'average of margin_pct, grouped by region', depends_on: [] }], context_objects: ['Demo — Sales'],
    steps: [{ node: 'execute', status: 'ok', sql: SQL, rows_returned: 4, validation_failures: 0, repair_attempts: 0, ms: 300 }] } }))
  if (sc.pending) await page.route(at('/api/v1/agent/conversations/510/ask'), () => { /* never answers */ })
  if (sc.offline) await page.route(u => new URL(u).pathname === '/api/v1/llm/endpoints', async r => {
    const res = await r.fetch(); const body = await res.json()
    body.auto_pick = null
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: false, error: 'connection refused' } }))
    await r.fulfill({ json: body })
  })
  await page.goto(BASE + sc.url)
  await page.waitForTimeout(3500)
  if (sc.pending) {
    await page.getByRole('textbox', { name: /question|سؤال/i }).fill(sc.pending(lang))
    await page.keyboard.press('Enter')
    await page.waitForTimeout(6500)
  }
  if (sc.offline) await page.waitForTimeout(1500)
  if (sc.sql) { await page.locator('button', { hasText: /Show SQL|عرض SQL/ }).last().click(); await page.waitForTimeout(1000) }
  await page.screenshot({ path: path.join(OUT, `${sc.name}-${suffix}.png`) })
  console.log(`${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
