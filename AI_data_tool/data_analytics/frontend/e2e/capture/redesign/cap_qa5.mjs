import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * QA5 items × EN/AR × light/dark (a few in Arabic only, where English cannot
 * show the problem). A scratch dashboard and a scratch dataflow are made and
 * deleted through the API; everything else reads only.
 * Usage: node cap_qa5.mjs <outdir> [scene-id-prefix]; ONLY=<theme>.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const API = process.env.API ?? 'http://localhost:8000/api/v1'
const THEMES = [['en-light', 'en', 'light'], ['en-dark', 'en', 'dark'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const AR = THEMES.filter(t => t[1] === 'ar')
const log = []

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())

async function fixture() {
  const r = await api('POST', '/reports', { name: 'QA5-fix scratch', dataset_id: 1 })
  const pid = (await api('GET', `/reports/${r.id}`)).pages[0].id
  await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: 'free' })
  await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: 'bar', title: 'Revenue by region and channel',
    config: { dimension: 'region', dimension2: 'channel', measure: 'revenue', widget_background: '#fde68a' }, layout: { x: 0, y: 0, w: 8, h: 6 } })
  return { id: r.id, cleanup: () => api('DELETE', `/reports/${r.id}`) }
}
async function flowFixture() {
  const f = await api('POST', '/dataflows', { name: 'QA5-fix flow', source_dataset_id: 2, steps: [{ kind: 'filter_rows', expression: 'units > 0' }] })
  return { id: f.id, cleanup: () => api('DELETE', `/dataflows/${f.id}`) }
}

const fld = (p, n) => p.locator(`button.dl-bd-f__b:has(.nm bdi:text-is("${n}"))`).first()
const fieldsTab = async p => { await p.locator('.dl-bd-lh [role="tab"]').nth(1).click(); await sleep(700) }
const rowOf = (p, n) => fld(p, n).locator('xpath=..')

const scenes = [
  { id: 'F1', name: 'light-bg-legend-tooltip', fix: fixture, url: id => `/reports/${id}`, act: async p => {
    const w = p.locator('.recharts-wrapper').first(); await w.scrollIntoViewIfNeeded(); const b = await w.boundingBox()
    await p.mouse.move(b.x + 5, b.y + 5); await p.mouse.move(b.x + b.width * 0.3, b.y + b.height * 0.5, { steps: 8 }); await sleep(900) },
    clip: { x: 0, y: 100, width: 1440, height: 560 } },
  { id: 'F2', name: 'quick-calcs-popup', fix: fixture, url: id => `/reports/${id}?edit=1`, themes: [THEMES[0], THEMES[2]], act: async p => {
    await fieldsTab(p); await rowOf(p, 'revenue').getByRole('button', { name: /Calculations from|حسابات من/ }).click(); await sleep(700) } },
  { id: 'F2', name: 'classify-popup', fix: fixture, url: id => `/reports/${id}?edit=1`, themes: [THEMES[0], THEMES[2]], act: async p => {
    await fieldsTab(p); await rowOf(p, 'country').getByRole('button', { name: /^Classify|^تصنيف/ }).click(); await sleep(900) } },
  { id: 'L4-R2', name: 'field-properties', fix: fixture, url: id => `/reports/${id}?edit=1`, act: async p => {
    await fieldsTab(p); await rowOf(p, 'revenue').locator('button[aria-expanded]').last().click(); await sleep(700)
    log.push(`L4-R2 ${p.lang}: formats = ${JSON.stringify(await p.locator('select[id^="fp-fmt-"] option').allTextContents())}`)
    log.push(`L4-R2 ${p.lang}: aggregations = ${JSON.stringify((await p.locator('select[id^="fp-agg-"] option').allTextContents()).slice(0, 6))}`) } },
  { id: 'L5', name: 'report-filter-operators', fix: fixture, url: id => `/reports/${id}?edit=1`, act: async p => {
    await fieldsTab(p)
    const sel = p.locator('.dl-bd-rf select').nth(1); await sel.scrollIntoViewIfNeeded()
    log.push(`L5 ${p.lang}: operators = ${JSON.stringify(await sel.locator('option').allTextContents())}`)
    await sel.selectOption('gte'); await sleep(400) } },
  { id: 'F3-R2', name: 'outliers', fix: fixture, url: id => `/reports/${id}?edit=1`, act: async p => {
    await fieldsTab(p); await p.getByRole('button', { name: /outlier details for|تفاصيل القيم الشاذة/ }).first().click(); await sleep(3500) } },
  { id: 'R1-L1', name: 'calc-builder', url: () => '/datasets/1', themes: AR.concat([THEMES[0]]), act: async p => {
    await p.getByRole('tab', { name: /^(Data|البيانات)/ }).first().click(); await sleep(2000)
    await p.locator('button.dl-data3__tool', { hasText: 'ƒx' }).click(); await sleep(1200)
    await p.getByRole('button', { name: /^(\+ Add|\+ إضافة)$/ }).first().click(); await sleep(1500) } },
  { id: 'L2', name: 'step-editor', fix: flowFixture, url: () => '/dataflows', themes: AR.concat([THEMES[0]]), act: async p => {
    await p.getByText('QA5-fix flow').first().click(); await sleep(2500)
    await p.getByTestId('prep-step-card').first().click(); await sleep(1500) } },
  { id: 'R3', name: '404', url: () => '/activity-not-here', themes: AR },
  { id: 'R4', name: 'map-tooltip', url: () => '/reports/5', act: async p => {
    await sleep(3000); const c = p.locator('[data-country="United States of America"]').first()
    await c.scrollIntoViewIfNeeded(); await c.hover({ force: true }); await sleep(800) } },
  { id: 'L3', name: 'column-security-dialog', url: () => '/admin/column-security-rules', themes: AR, act: async p => {
    await p.getByRole('button', { name: /^(\+ )?(New rule|قاعدة جديدة)/ }).first().click(); await sleep(1500) } },
  { id: 'F4-L6', name: 'custom-connector-dialog', url: () => '/admin/custom-connectors', act: async p => {
    await p.getByRole('button', { name: /New custom connector|موصّل مخصص جديد/ }).first().click(); await sleep(1500)
    log.push(`F4 ${p.lang}: ${JSON.stringify(await p.locator('[role=dialog] input').evaluateAll(es => es.map(e => `${e.name}:${e.autocomplete}`)))}`) } },
  { id: 'L7', name: 'map-starter-packs', url: () => '/admin/maps', themes: AR.concat([THEMES[0]]) },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const th of (sc.themes ?? THEMES).filter(t => !process.env.ONLY || t[0] === process.env.ONLY)) {
  const [suffix, lang, theme] = th
  const fx = sc.fix ? await sc.fix() : null
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage(); page.lang = suffix
  let note = ''
  try {
    await page.goto(BASE + sc.url(fx?.id)); await sleep(4500)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/${sc.id}-${sc.name}-${suffix}.png`, ...(sc.clip ? { clip: sc.clip } : {}) })
  console.log(BASE, suffix, sc.id, sc.name, note)
  await ctx.close()
  if (fx) { await fx.cleanup(); await sleep(3000) }
}
await browser.close()
console.log(log.join('\n'))
