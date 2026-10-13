import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 10 Part D (Ask AI): the History rail -- with threads (Today and
 * Earlier), with none, on the empty page, renaming, and as an overlay at
 * 1024px. EN light and AR dark. Browser-only data: the list of conversations
 * and one thread's messages. Nothing is created, renamed or deleted.
 * Usage: node cap_10d.mjs <outdir> [scene-prefix]
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const now = new Date()
const iso = (daysAgo, h, m) => { const d = new Date(now); d.setDate(d.getDate() - daysAgo); d.setHours(h, m, 0, 0); return d.toISOString() }
const conv = (id, title, when, extra = {}) => ({ id, title, data_source_id: null, dataset_ids: [1], created_at: when, ...extra })
const CONVS = [
  conv(510, 'Total revenue by region', iso(0, 10, 42)),
  conv(509, 'Which reps missed quota last quarter, and by how much did each one miss it?', iso(0, 10, 31)),
  conv(508, 'ما إجمالي الإيرادات لكل منطقة؟', iso(0, 9, 58)),
  conv(507, 'Units sold by category', iso(1, 15, 5)),
  conv(506, 'Average margin % by channel', iso(1, 11, 20)),
  conv(505, 'Revenue vs target this year', iso(24, 9, 0)),
  conv(504, 'Top 5 products this month', iso(30, 9, 0)),
  conv(503, 'Asked about another dataset', iso(0, 8, 0), { dataset_ids: [2] }),
]
const RESULT = { step: 'q1', columns: ['region', 'revenue'], total: 3, truncated: false, rows: [['Asia Pacific', 2348914], ['Europe', 2219630], ['Americas', 1882846]] }
const MSGS = [
  { id: 1, role: 'user', content: 'Total revenue by region', created_at: iso(0, 10, 42), run: null },
  { id: 2, role: 'assistant', content: '**Asia Pacific** leads with 2,348,914 in revenue.', created_at: iso(0, 10, 42), run: { id: 700, status: 'ok', intent: 'aggregate', error: null,
    results: [RESULT], sql: ['SELECT region, SUM(revenue) AS revenue FROM "Demo — Sales" GROUP BY region'], presentation: { format: 'bar', limit: null, x: 'region', y: 'revenue' }, context_objects: null, evidence: null } }]
const item = (p, re) => p.locator('.dl-hist button').filter({ hasText: re }).first()
const scenes = [
  { id: 'threads', url: '/ask?dataset=1', convs: CONVS, act: async p => { await item(p, /Total revenue by region/).click(); await sleep(1500) } },
  { id: 'new-chat', url: '/ask?dataset=1', convs: CONVS },
  { id: 'none', url: '/ask?dataset=1', convs: [] },
  { id: 'no-data', url: '/ask', convs: CONVS },
  { id: 'rename', url: '/ask?dataset=1', convs: CONVS, act: async p => { await item(p, /Units sold by category/).hover(); await sleep(200)
    await p.locator('.dl-hist li').filter({ hasText: /Units sold by category/ }).getByRole('button', { name: /Rename|إعادة تسمية/ }).click(); await sleep(500) } },
  { id: 'threads-1024', url: '/ask?dataset=1', convs: CONVS, view: { width: 1024, height: 768 } },
  { id: 'overlay-1024', url: '/ask?dataset=1', convs: CONVS, view: { width: 1024, height: 768 }, act: async p => {
    await p.getByRole('button', { name: /^(History|Show history|السجل|إظهار السجل)$/ }).first().click(); await sleep(700) } },
  { id: 'no-data-1024', url: '/ask', convs: CONVS, view: { width: 1024, height: 768 } },
  // Autopilot step 2: the polished empty page, and the robot's two reactions to the chooser.
  { id: 'polish-look', url: '/ask', convs: CONVS, act: async p => { await p.locator('.dl-pick__opt').nth(1).hover(); await sleep(900) } },
  { id: 'polish-search', url: '/ask', convs: CONVS, act: async p => { await p.keyboard.press('/'); await p.keyboard.type('dem'); await sleep(600) } },
  { id: 'polish-chosen', url: '/ask', convs: [], act: async p => { await p.locator('.dl-pick__opt').filter({ hasText: 'Demo — Sales' }).first().click(); await sleep(450) } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: sc.view ?? { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr'); localStorage.removeItem('datalytics.ask.historyFolded')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
  await page.route(at('/api/v1/agent/conversations'), r => r.request().method() === 'GET' ? r.fulfill({ json: sc.convs }) : r.continue())
  await page.route(at('/api/v1/agent/conversations/510/messages'), r => r.fulfill({ json: MSGS }))
  let note = ''
  try {
    await page.goto(BASE + sc.url); await sleep(3000)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/D-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
