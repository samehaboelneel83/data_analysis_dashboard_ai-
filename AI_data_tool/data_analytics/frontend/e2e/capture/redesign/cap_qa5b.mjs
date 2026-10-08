import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * 7-QA5b items (S1 and S3–S6; S2 is probe_s2c.mjs) in English light and Arabic light/dark.
 * Scratch dashboards are made and deleted through the API; S1 presses Enter in
 * a delete dialog, on a scratch dashboard only, and logs whether it survived.
 * Usage: node cap_qa5b.mjs <outdir> [scene-id-prefix]; ONLY=<theme>.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const API = process.env.API ?? 'http://localhost:8000/api/v1'
const THEMES = [['en-light', 'en', 'light'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const log = []

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.status === 404 ? { missing: true } : r.json())

async function fixture(name = 'QA5b scratch') {
  const r = await api('POST', '/reports', { name, dataset_id: 1 })
  const pid = (await api('GET', `/reports/${r.id}`)).pages[0].id
  await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: 'free' })
  await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: 'bar', title: 'Revenue by region',
    config: { dimension: 'region', measure: 'revenue' }, layout: { x: 0, y: 0, w: 8, h: 6 } })
  return { id: r.id, cleanup: () => api('DELETE', `/reports/${r.id}`).catch(() => {}) }
}

const tile = (p, t) => p.locator('[data-widget-id]').filter({ has: p.getByRole('heading', { name: t, exact: true }) }).first()
const fieldsTab = async p => { await p.locator('.dl-bd-lh [role="tab"]').nth(1).click(); await sleep(800) }

const scenes = [
  { id: 'S1', name: 'dashboard-delete-dialog', fix: () => fixture('QA5b delete me'), url: () => '/reports', act: async (p, fx) => {
    await p.getByRole('button', { name: /^(More actions for|إجراءات أخرى لـ) QA5b delete me$/ }).first().click({ force: true }); await sleep(500)
    await p.getByRole('menuitem', { name: /^(Delete|حذف)/ }).first().click(); await sleep(800)
    const focused = await p.evaluate(() => document.activeElement?.textContent?.trim())
    await p.screenshot({ path: `${OUT}/S1-dashboard-delete-dialog-${p.lang}.png` })
    await p.keyboard.press('Enter'); await sleep(1500)
    const after = await api('GET', `/reports/${fx.id}`)
    log.push(`S1 ${p.lang}: focus on open = "${focused}"; after Enter the dashboard ${after.missing ? 'WAS DELETED' : 'still exists'}`)
  }, shot: false },
  { id: 'S3', name: 'auto-title', fix: fixture, url: id => `/reports/${id}?edit=1`, act: async p => {
    await fieldsTab(p)
    await p.getByRole('checkbox', { name: /^(Select product|تحديد «product»)$/ }).first().check(); await sleep(800)
    log.push(`S3 ${p.lang}: staging = ${(await p.getByTestId('fields-staging').innerText()).replace(/\s+/g, ' ')}`)
  } },
  { id: 'S4', name: 'audit-trail', url: () => '/admin/audit', act: async p => {
    log.push(`S4 ${p.lang}: actions = ${JSON.stringify((await p.locator('tbody tr td:nth-child(3)').allInnerTexts()).slice(0, 4))}`)
    log.push(`S4 ${p.lang}: filter = ${JSON.stringify((await p.locator('select').first().locator('option').allInnerTexts()).slice(0, 4))}`)
  } },
  { id: 'S5', name: 'hierarchy-labels', fix: fixture, url: id => `/reports/${id}?edit=1`, act: async p => {
    await fieldsTab(p)
    const box = p.getByTestId('hierarchy-chains'); await box.scrollIntoViewIfNeeded().catch(() => {})
    const labels = await box.locator('[aria-label], [title]').evaluateAll(es => es.slice(0, 6).map(e => e.getAttribute('aria-label') ?? e.getAttribute('title')))
    log.push(`S5 ${p.lang}: hierarchy = ${JSON.stringify(labels)}`)
  } },
  { id: 'S5', name: 'sensitivity', url: () => '/datasets/1', act: async p => {
    const s = p.getByTestId('dataset-sensitivity').first()
    if (!await s.count()) { await p.getByRole('tab', { name: /^(Models|النماذج)$/ }).first().click(); await sleep(2500) }
    await s.scrollIntoViewIfNeeded().catch(() => {}); await s.hover().catch(() => {})
    log.push(`S5 ${p.lang}: sensitivity title = ${await s.getAttribute('title')}; select = ${await s.locator('select').getAttribute('aria-label')}`)
  } },
  { id: 'S6', name: 'difference-evidence', fix: fixture, url: id => `/reports/${id}`, act: async p => {
    const w = tile(p, 'Revenue by region'); await w.scrollIntoViewIfNeeded(); await w.hover(); await sleep(400)
    await w.locator('.dl-whead__ctl button.dl-wicon').first().click({ force: true }); await sleep(500)
    await p.getByRole('menuitem', { name: /difference|الفرق/ }).first().click(); await sleep(6000)
    log.push(`S6 ${p.lang}: chips = ${JSON.stringify(await p.getByTestId('evidence-chip').allInnerTexts())}`)
  } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const th of THEMES.filter(t => !process.env.ONLY || t[0] === process.env.ONLY)) {
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
    if (sc.act) await sc.act(page, fx)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  if (sc.shot !== false || note) await page.screenshot({ path: `${OUT}/${sc.id}-${sc.name}-${suffix}.png` })
  console.log(BASE, suffix, sc.id, sc.name, note)
  await ctx.close()
  if (fx) { await fx.cleanup(); await sleep(2000) }
}
await browser.close()
console.log(log.join('\n'))
