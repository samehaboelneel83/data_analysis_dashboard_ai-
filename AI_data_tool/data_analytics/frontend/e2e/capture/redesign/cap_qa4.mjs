import { chromium, signIn, sleep, THEMES, BASE } from './_qa3_lib.mjs'

/**
 * QA4 items × light / dark / Arabic / Arabic dark. Builder scenes use a scratch dashboard made
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
    ['bar', 'Revenue by region', { dimension: 'region', measure: 'revenue' }, [0, 7, 9, 5]],
  ]
  for (const [t, title, config, [x, y, w, h]] of W)
    await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: t, title, config, layout: { x, y, w, h } })
  return r.id
}

const tile = (p, t) => p.locator('[data-widget-id]').filter({ has: p.getByRole('heading', { name: t, exact: true }) }).first()
const head = (p, t) => tile(p, t).locator('.dl-whead')
const rail = (p, i) => p.locator('nav.dl-bd-rail button.dl-bd-ri').nth(i)
const AR = THEMES.filter(t => t[1] === 'ar')
const fld = (p, n) => p.locator(`button.dl-bd-f__b:has(.nm bdi:text-is("${n}"))`).first()
const log = []

const scenes = [
  { id: 'E1', name: 'new-display-rule', builder: true, act: async p => {
    await head(p, 'KPI 1').click(); await sleep(700)
    await p.getByRole('tab', { name: /^(Display rules|قواعد العرض)$/ }).first().click(); await sleep(500)
    await p.locator('[data-side="builder-right"] button[aria-expanded="false"]', { hasText: /Display rules|قواعد العرض/i }).first().click().catch(() => {}); await sleep(400)
    await p.getByRole('button', { name: /^(\+ )?(Add rule|إضافة قاعدة)/ }).first().click(); await sleep(2500) } },
  { id: 'E2', name: 'text-field-on-full-bar', builder: true, act: async (p, rid) => {
    await p.locator('.dl-bd-lh [role="tab"]').nth(1).click(); await sleep(500)
    await fld(p, 'channel').dragTo(tile(p, 'Revenue by region')); await sleep(1200)
    await fld(p, 'region').dragTo(tile(p, 'Revenue by region')); await sleep(2500)
    const w = (await api('GET', `/reports/${rid}`)).pages[0].widgets.find(x => x.title === 'Revenue by region')
    log.push(`E2 ${p.lang}: bar config ${JSON.stringify(w.config)}`) } },
  { id: 'V1', name: 'custom-bg-text', builder: true, clip: { x: 340, y: 180, width: 760, height: 200 } },
  { id: 'V2', name: 'header-900', builder: true, view: { width: 900, height: 800 }, opened: true, clip: { x: 0, y: 40, width: 900, height: 150 } },
  { id: 'V3', name: 'panel-scrolled', builder: true, view: { width: 1440, height: 560 }, act: async p => {
    await head(p, 'KPI 1').click(); await sleep(800)
    await p.evaluate(() => { const s = [...document.querySelectorAll('[data-side="builder-right"] *')].find(d => d.scrollHeight > d.clientHeight + 20 && /auto|scroll/.test(getComputedStyle(d).overflowY)); if (s) s.scrollTop = 400 }); await sleep(500) } },
  { id: 'V4', name: 'tag-bottom-widget', builder: true, act: async p => { await head(p, 'Revenue by region').click(); await sleep(800); await p.locator('.dl-bd-coord').scrollIntoViewIfNeeded().catch(() => {}) } },
  { id: 'V5', name: 'multi-select-bar', builder: true, act: async p => {
    for (const t of ['KPI 1', 'Revenue on a custom background', 'Empty KPI']) { await head(p, t).click({ modifiers: t === 'KPI 1' ? [] : ['Shift'] }); await sleep(300) } } },
  { id: 'V6', name: 'view-click-then-edit', builder: true, url: 'view', act: async p => {
    const w = tile(p, 'Revenue by region').locator('.recharts-wrapper'); await w.scrollIntoViewIfNeeded(); const b = await w.boundingBox()
    await p.mouse.click(b.x + b.width * 0.2, b.y + b.height * 0.6); await sleep(1500)
    await p.getByTestId('mode-toggle').click(); await sleep(2500) } },
  { id: 'V7-T2', name: 'performance-pane', builder: true, act: async p => { await rail(p, 10).click(); await sleep(3000) } },
  { id: 'V8', name: 'crumbs-datasets', url: '/datasets', clip: { x: 0, y: 0, width: 1440, height: 60 } },
  { id: 'V8', name: 'crumbs-css125', url: '/datasets/1', zoom: 1.25, clip: { x: 0, y: 0, width: 1440, height: 70 } },
  { id: 'T1', name: 'review-roles', builder: true, themes: AR, act: async p => { await rail(p, 9).click(); await sleep(1500) } },
  { id: 'T4', name: 'undo-after-rule', builder: true, act: async p => {
    await head(p, 'KPI 1').click(); await sleep(700)
    await p.getByRole('tab', { name: /^(Display rules|قواعد العرض)$/ }).first().click(); await sleep(500)
    await p.locator('[data-side="builder-right"] button[aria-expanded="false"]', { hasText: /Display rules|قواعد العرض/i }).first().click().catch(() => {}); await sleep(400)
    await p.getByRole('button', { name: /^(\+ )?(Add rule|إضافة قاعدة)/ }).first().click(); await sleep(3000)
    log.push(`T4 ${p.lang}: undo title = ${await p.locator('.dl-bd-saveundo button').first().getAttribute('title')}`) } },
  { id: 'T5', name: 'difference-dialog', builder: true, url: 'view', act: async p => {
    const w = tile(p, 'Revenue by region'); await w.scrollIntoViewIfNeeded(); await w.hover(); await sleep(400)
    await w.locator('.dl-whead__ctl button.dl-wicon').first().click({ force: true }); await sleep(500)
    await p.getByRole('menuitem', { name: /difference|الفرق/ }).first().click(); await sleep(6000) } },
  { id: 'T6', name: 'dataset-delete-dialog', url: '/datasets', themes: AR, act: async p => {
    const more = p.getByRole('button', { name: /More actions for dataset|إجراءات أخرى لمجموعة البيانات/ }).nth(2)
    await more.click(); await sleep(800)
    if (!(await p.getByRole('menuitem').count())) { await more.click(); await sleep(800) }
    await p.getByRole('menuitem', { name: /Delete|حذف/ }).first().click(); await sleep(800) } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const th of (sc.themes ?? THEMES).filter(t => !process.env.ONLY || t[0] === process.env.ONLY)) {
  const [suffix, lang, theme] = th
  let rid = null
  if (sc.builder) rid = await fixture()
  if (sc.empty) { const g = await api('GET', `/reports/${rid}`); for (const w of g.pages[0].widgets) await api('DELETE', `/reports/${rid}/pages/${g.pages[0].id}/widgets/${w.id}`) }
  const ctx = await browser.newContext({ viewport: sc.view ?? VIEW, storageState: state })
  await ctx.addInitScript(({ theme, lang, list }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    if (list) { localStorage.setItem('datalytics:dashboards-layout', 'list'); for (let i = 0; i < 10; i++) localStorage.setItem('rail-expanded:' + i, '0') }
  }, { theme, lang, list: !!sc.list })
  const page = await ctx.newPage(); page.lang = suffix
  if (sc.opened) await ctx.addInitScript(() => sessionStorage.setItem('datalytics:open-reports', JSON.stringify([2, 3, 4, 5].map(id => ({ id, name: 'Report ' + id })))))
  let note = ''
  try {
    await page.goto(BASE + (sc.builder ? (sc.url === 'view' ? `/reports/${rid}` : `/reports/${rid}?edit=1`) : sc.url))
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
console.log(log.join('\n'))
