import { chromium, signIn, sleep, THEMES, BASE } from './_qa3_lib.mjs'

/**
 * QA3 Batches B–D × light / dark / Arabic / Arabic dark (C: Arabic only — the
 * English is unchanged by design). Builder scenes use a scratch dashboard made
 * and deleted through the API; page scenes use the demo content.
 * Usage: node cap_qa3_bd.mjs <outdir> [scene-id-prefix]; ONLY=<theme>.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const API = process.env.API ?? 'http://localhost:8000/api/v1'
const VIEW = { width: 1440, height: 900 }

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())

async function fixture() {
  const r = await api('POST', '/reports', { name: 'QA3-fix scratch', dataset_id: 1 })
  const got = await api('GET', `/reports/${r.id}`)
  const pid = got.pages[0]?.id ?? (await api('POST', `/reports/${r.id}/pages`, { name: 'Page 1', position: 0 })).id
  await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: 'free' })
  const W = [
    ['kpi', 'KPI 1', { measure: 'revenue' }, [0, 0, 3, 2]],
    ['kpi', 'Revenue on a custom background', { measure: 'revenue', widget_background: '#fde68a' }, [3, 0, 3, 2]],
    ['kpi', 'Empty KPI', {}, [6, 0, 3, 2]],
    ['bar', 'Empty bar', { measure: 'revenue' }, [9, 0, 3, 4]],
    ['line', 'Revenue by date', { dimension: 'date', measure: 'revenue' }, [0, 2, 9, 5]],
  ]
  for (const [t, title, config, [x, y, w, h]] of W)
    await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: t, title, config, layout: { x, y, w, h } })
  return r.id
}

const tile = (p, t) => p.locator('[data-widget-id]', { hasText: t }).first()
const head = (p, t) => tile(p, t).locator('.dl-whead')
const rail = (p, i) => p.locator('nav.dl-bd-rail button.dl-bd-ri').nth(i)
const AR = THEMES.filter(t => t[1] === 'ar')
// rail order: properties 0, outline 1, selection 2, parameters 3, bookmarks 4, sync 5, ask 6, comments 7,
// history 8, review 9, performance 10, taborder 11, reportrules 12, schedule 13, translations 14, mobile 15
const pane = (id, name, i, themes = AR) => ({ id, name, builder: true, themes, act: async p => { await rail(p, i).click(); await sleep(1200) } })

const scenes = [
  { id: 'B1', name: 'ai-button-comments', builder: true, act: async p => { await rail(p, 7).click(); await sleep(1200) } },
  { id: 'B1', name: 'ai-button-schedule', builder: true, act: async p => { await rail(p, 13).click(); await sleep(1200) } },
  { id: 'B2', name: 'coord-tag-bottom', builder: true, act: async p => { await head(p, 'Revenue by date').click(); await sleep(800) } },
  { id: 'B3', name: 'header', builder: true, clip: { x: 300, y: 50, width: 1140, height: 100 } },
  { id: 'B4', name: 'header-selected-custom-bg', builder: true, act: async p => { await head(p, 'Revenue on a custom background').click(); await sleep(800) } },
  { id: 'B5', name: 'pinned-properties', builder: true, act: async p => {
    await head(p, 'KPI 1').click(); await sleep(600)
    await p.locator('.dl-bd-ph button[aria-pressed]').click(); await sleep(300)
    await rail(p, 1).click(); await sleep(1500) } },
  { id: 'B6', name: 'toast-over-statusbar', builder: true, act: async p => {
    await p.keyboard.press('Control+d').catch(() => {})
    await head(p, 'KPI 1').click(); await sleep(300); await p.keyboard.press('Control+d'); await sleep(1200) },
    clip: { x: 900, y: 700, width: 540, height: 200 } },
  { id: 'C1', name: 'placeholders', builder: true, themes: AR },
  { id: 'C2', name: 'properties-data-roles', builder: true, themes: AR, act: async p => {
    await head(p, 'Empty bar').click(); await sleep(600)
    await p.getByRole('tab', { name: /^(Data|البيانات)$/ }).last().click(); await sleep(1000) } },
  { id: 'C2', name: 'properties-interactions', builder: true, themes: AR, act: async p => {
    await head(p, 'KPI 1').click(); await sleep(600)
    await p.getByRole('tab', { name: /^(Interactions|التفاعلات)$/ }).last().click(); await sleep(1000) } },
  { id: 'C2', name: 'page-properties', builder: true, themes: AR, act: async p => { await p.keyboard.press('Escape'); await sleep(800) } },
  { id: 'C3', name: 'assign-data-dialog', builder: true, themes: AR, act: async p => {
    await tile(p, 'Empty KPI').locator('button.btn-primary').click(); await sleep(1200) } },
  pane('C4', 'outline', 1), pane('C4', 'selection', 2), pane('C4', 'parameters', 3), pane('C4', 'bookmarks', 4),
  pane('C4', 'sync-slicers', 5), pane('C4', 'comments', 7), pane('C4', 'review', 9), pane('C4', 'performance', 10),
  pane('C4', 'tab-order', 11), pane('C4', 'report-rules', 12), pane('C4', 'schedule', 13), pane('C4', 'translations', 14),
  pane('C4', 'mobile-layout', 15),
  { id: 'C5', name: 'delete-page-dialog', builder: true, themes: AR, act: async (p, rid) => {
    // a second page: the last one cannot be deleted
    await api('POST', `/reports/${rid}/pages`, { name: 'QA3 صفحة', position: 1 }); await p.reload(); await sleep(4000)
    await p.locator('.dl-bd-pg__m').last().click(); await sleep(400)
    await p.getByRole('menuitem', { name: /Delete|حذف/ }).first().click(); await sleep(800) } },
  { id: 'C5', name: 'empty-page', builder: true, empty: true, themes: AR },
  { id: 'C6', name: 'toast-page-added', builder: true, themes: AR, act: async p => {
    await p.locator('.dl-bd-bar button[aria-label]').filter({ has: p.locator('svg.lucide-plus') }).first().click(); await sleep(1000) } },
  { id: 'C7', name: 'fields-panel', builder: true, themes: AR, act: async p => { await p.locator('.dl-bd-lh [role="tab"]').nth(1).click(); await sleep(800) } },
  { id: 'C7', name: 'shortcuts', builder: true, themes: AR, act: async p => { await p.keyboard.press('?'); await sleep(800) } },
  { id: 'C8', name: 'why-popup', url: '/reports/1', themes: AR, act: async p => {
    const w = p.locator('[data-widget-id]').filter({ has: p.locator('.recharts-surface') }).first()
    await w.hover(); await sleep(400)
    await w.locator('.dl-whead__ctl button.dl-wicon').first().click({ force: true }); await sleep(500)
    await p.getByRole('menuitem').first().click(); await sleep(1500) } },
  { id: 'D1', name: 'breadcrumb-css125', url: '/datasets/1', zoom: 1.25, clip: { x: 0, y: 0, width: 1440, height: 70 } },
  { id: 'D2', name: 'tooltip', url: '/reports/1', act: async p => {
    const w = p.locator('[data-widget-id]', { hasText: /Revenue by region|الإيراد حسب المنطقة/ }).first().locator('.recharts-wrapper')
    await w.scrollIntoViewIfNeeded(); await sleep(800); const b = await w.boundingBox()
    await p.mouse.move(b.x + 5, b.y + 5); await p.mouse.move(b.x + b.width * 0.35, b.y + b.height * 0.6, { steps: 8 }); await sleep(1000) } },
  { id: 'D3', name: 'list-view', url: '/reports', list: true },
  { id: 'D4', name: 'activity-dates', url: '/monitoring/activity' },
  { id: 'D5', name: 'insights', url: '/insights', act: async p => {
    const v = await p.locator('#insights-hub-dataset option').evaluateAll(os => os.find(o => /^Demo — Sales\b/.test(o.textContent))?.value)
    await p.locator('#insights-hub-dataset').selectOption(v); await sleep(25000) } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const th of (sc.themes ?? THEMES).filter(t => !process.env.ONLY || t[0] === process.env.ONLY)) {
  const [suffix, lang, theme] = th
  let rid = null
  if (sc.builder) rid = await fixture()
  if (sc.empty) { const g = await api('GET', `/reports/${rid}`); for (const w of g.pages[0].widgets) await api('DELETE', `/reports/${rid}/pages/${g.pages[0].id}/widgets/${w.id}`) }
  const ctx = await browser.newContext({ viewport: VIEW, storageState: state })
  await ctx.addInitScript(({ theme, lang, list }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    if (list) { localStorage.setItem('datalytics:dashboards-layout', 'list'); for (let i = 0; i < 10; i++) localStorage.setItem('rail-expanded:' + i, '0') }
  }, { theme, lang, list: !!sc.list })
  const page = await ctx.newPage()
  let note = ''
  try {
    await page.goto(BASE + (sc.builder ? `/reports/${rid}?edit=1` : sc.url))
    for (let i = 0; i < 4; i++) {
      const got = await Promise.race([
        sc.builder && !sc.empty ? page.waitForSelector('[data-widget-id]', { timeout: 45000 }).then(() => 'ok') : sleep(sc.wait ?? 3500).then(() => 'ok'),
        page.waitForSelector('text=/Rate limit|تجاوز/', { timeout: 45000 }).then(() => 'limited')])
      if (got === 'ok') break
      await sleep(30000); await page.reload()
    }
    await sleep(2500)
    if (sc.zoom) { await page.addStyleTag({ content: `html { zoom: ${sc.zoom} }` }); await sleep(500) }
    if (sc.act) await sc.act(page, rid)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/${sc.id}-${sc.name}-${suffix}.png`, ...(sc.clip ? { clip: sc.clip } : {}) })
  console.log(BASE, suffix, sc.id, sc.name, note)
  await ctx.close()
  if (rid) { await api('DELETE', `/reports/${rid}`); await sleep(Number(process.env.PAUSE ?? 4000)) }
}
await browser.close()
