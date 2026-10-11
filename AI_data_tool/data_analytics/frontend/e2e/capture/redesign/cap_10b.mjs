import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 10 Part B (Ask AI): the loading card and the answer card, EN/AR x
 * light/dark. Browser-only data (Playwright routes): the conversation, the
 * answer to /ask, the run's duration, and model endpoints that read as up.
 * Nothing is asked of a real model and nothing is saved.
 * Usage: node cap_10b.mjs <outdir> [scene-prefix]
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['en-dark', 'en', 'dark'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const now = new Date().toISOString()
const L = (lang, en, ar) => (lang === 'ar' ? ar : en)

const BAR = { step: 'q1', columns: ['region', 'revenue'], total: 4, truncated: false,
  rows: [['Asia Pacific', 2348914], ['Europe', 2219630], ['Latin America', 2181207], ['North America', 1882846]] }
const BAR_SQL = 'SELECT region, SUM(revenue) AS revenue\nFROM "Demo — Sales"\nWHERE year = 2026 AND channel <> \'Partner\'\nGROUP BY region\nORDER BY revenue DESC'
const LINE = { step: 'q1', columns: ['month', 'revenue'], total: 12, truncated: false,
  rows: ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09']
    .map((m, i) => [m, [612, 781, 694, 640, 655, 671, 688, 702, 690, 715, 709, 722][i] * 1000]) }
// Labels only: nothing to chart, so the rows are the answer.
const TABLE = { step: 'q1', columns: ['product', 'category', 'channel', 'country'], total: 5, truncated: false,
  rows: [['Aurora Lamp', 'Home', 'Online', 'Japan'], ['Nimbus Chair', 'Office', 'Retail', 'Germany'], ['Delta Desk', 'Office', 'Online', 'Brazil'],
    ['Pico Speaker', 'Audio', 'Partner', 'Canada'], ['Luma Shelf', 'Home', 'Retail', 'France']] }
const claims = (text, nums) => nums.map(([n, row, column]) => {
  const start = text.indexOf(n)
  return { start, end: start + n.length, text: n, status: 'traced', source: { result: 0, row, column, value: n, kind: 'cell' } }
})
const barText = lang => L(lang, '**Asia Pacific** leads with 2,348,914 in revenue. North America is lowest at 1,882,846.',
  'تتصدّر **Asia Pacific** بإيرادات 2,348,914. وتأتي North America في المرتبة الأخيرة بـ 1,882,846.')
const answers = {
  bar: lang => { const answer = barText(lang); return { run_id: 701, status: 'ok', intent: 'aggregate', error: null, answer, results: [BAR], sql: [BAR_SQL],
    presentation: { format: 'bar', limit: null, x: 'region', y: 'revenue' }, context_objects: ['Demo — Sales'],
    evidence: { claims: claims(answer, [['2,348,914', 0, 'revenue'], ['1,882,846', 3, 'revenue']]), untraced: 0 } } },
  line: lang => ({ run_id: 701, status: 'ok', intent: 'aggregate', error: null,
    answer: L(lang, 'Revenue rose from 612,000 in October 2025 to 722,000 in September 2026. November was the peak at 781,000.',
      'ارتفعت الإيرادات من 612,000 في أكتوبر 2025 إلى 722,000 في سبتمبر 2026. وكان نوفمبر الذروة بـ 781,000.'),
    results: [LINE], sql: ['SELECT month, SUM(revenue) AS revenue\nFROM "Demo — Sales"\nGROUP BY month\nORDER BY month'],
    presentation: { format: 'line', limit: null, x: 'month', y: 'revenue' }, context_objects: ['Demo — Sales'], evidence: null }),
  table: lang => ({ run_id: 701, status: 'ok', intent: 'lookup', error: null,
    answer: L(lang, 'These are the 5 products sold in the most countries.', 'هذه المنتجات الخمسة الأكثر انتشارًا بين الدول.'),
    results: [TABLE], sql: ['SELECT DISTINCT product, category, channel, country\nFROM "Demo — Sales"\nLIMIT 5'],
    presentation: null, context_objects: ['Demo — Sales'], evidence: null }),
}
const question = { bar: l => L(l, 'Total revenue by region', 'إجمالي الإيرادات حسب المنطقة'), line: l => L(l, 'Monthly trend of revenue', 'الاتجاه الشهري للإيرادات'),
  table: l => L(l, 'Which products sell in the most countries?', 'ما المنتجات الأكثر انتشارًا بين الدول؟') }
// A stored thread: an older answer, then (asked in the capture) a new one.
const stored = lang => { const a = answers.line(lang); return [
  { id: 1, role: 'user', content: question.line(lang), created_at: now, run: null },
  { id: 2, role: 'assistant', content: a.answer, created_at: now, run: { id: 700, status: 'ok', intent: a.intent, error: null,
    results: a.results, sql: a.sql, presentation: a.presentation, context_objects: a.context_objects, evidence: null } }] }
const CONV = { id: 510, title: 'Monthly trend of revenue', data_source_id: null, dataset_ids: [1], created_at: now }

const rowsBtn = p => p.locator('button', { hasText: /Show rows|Rows behind this answer|إظهار الصفوف|عرض الصفوف|الصفوف التي/ }).last()
const sqlBtn = p => p.locator('button', { hasText: /Show SQL|عرض SQL|إظهار SQL/ }).last()
const scenes = [
  { id: 'loading', ask: 'bar', never: true, wait: 4200 },
  { id: 'answer-lands', ask: 'bar', wait: 700 },                 // the happy head, just after the answer
  { id: 'answer', ask: 'bar', wait: 4600 },                      // calm
  { id: 'answer-open', ask: 'bar', wait: 4600, act: async p => { await rowsBtn(p).click(); await sqlBtn(p).click(); await sleep(900)
    await p.locator('.dl-chat__scroll').evaluate(el => { el.scrollTop = el.scrollHeight }); await sleep(400) } },
  { id: 'answer-line', ask: 'line', wait: 4600 },
  { id: 'answer-table', ask: 'table', wait: 4600 },
  { id: 'thread', ask: 'bar', thread: true, wait: 4600 },         // an older answer (static head) above the new one
  { id: 'answer-1024', ask: 'bar', wait: 4600, view: { width: 1024, height: 768 } },
  { id: 'loading-1024', ask: 'bar', never: true, wait: 4200, view: { width: 1024, height: 768 } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: sc.view ?? { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
  await page.route(at('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: true } }))
    body.auto_pick = body.endpoints[0]?.id ?? null
    await r.fulfill({ response: res, json: body })
  })
  await page.route(at('/api/v1/agent/conversations'), r => r.request().method() === 'GET'
    ? r.fulfill({ json: sc.thread ? [CONV] : [] }) : r.fulfill({ json: { id: 510, title: 'New conversation' } }))
  await page.route(at('/api/v1/agent/conversations/510/messages'), r => r.fulfill({ json: stored(lang) }))
  await page.route(at('/api/v1/agent/conversations/510/ask'), async r => {
    if (sc.never) return
    await sleep(1200); await r.fulfill({ json: answers[sc.ask](lang) })
  })
  await page.route(u => /\/api\/v1\/agent\/runs\/\d+$/.test(new URL(u).pathname), r => r.fulfill({ json: { id: 701, status: 'ok', ms: 1400, plan: [],
    context_objects: ['Demo — Sales'], steps: [{ node: 'execute', status: 'ok', sql: BAR_SQL, rows_returned: 4, validation_failures: 0, repair_attempts: 0, ms: 300 }] } }))
  let note = ''
  try {
    await page.goto(BASE + '/ask?dataset=1'); await sleep(3000)
    if (sc.thread) { await page.locator('.dl-hist__pick, .dl-hist button').filter({ hasText: /Monthly trend/ }).first().click(); await sleep(1500) }
    await page.getByRole('textbox', { name: /question|سؤال/i }).fill(question[sc.ask](lang))
    await page.keyboard.press('Enter')
    await sleep(sc.never ? 0 : 1200); await sleep(sc.wait)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/B-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
