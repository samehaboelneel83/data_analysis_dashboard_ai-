import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * 7-QA6 items (A1–A10, B1–B4) in English light and Arabic light/dark, before
 * and after (BASE=http://localhost:3011 serves the code before the fix).
 * Scratch dashboards are named "QA6-…", made and deleted through the API;
 * nothing that already exists is changed, and no connection is synced.
 * Usage: node cap_qa6.mjs <outdir> [scene-id-prefix]; ONLY=<theme>.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const API = process.env.API ?? 'http://localhost:8000/api/v1'
const THEMES = [['en-light', 'en', 'light'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const AR = THEMES.slice(1)
const log = []

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())

/** A QA6- dashboard on `dataset` with these widgets ([type, title, config, [x,y,w,h]]). */
function board(name, widgets, dataset = 1) {
  return async () => {
    const r = await api('POST', '/reports', { name, dataset_id: dataset })
    const pid = (await api('GET', `/reports/${r.id}`)).pages[0].id
    await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: 'free' })
    for (const [t, title, config, [x, y, w, h]] of widgets)
      await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: t, title, config, layout: { x, y, w, h } })
    return { id: r.id, cleanup: () => api('DELETE', `/reports/${r.id}`).catch(() => {}) }
  }
}

const tile = (p, t) => p.locator('[data-widget-id]').filter({ has: p.getByRole('heading', { name: t, exact: true }) }).first()
const head = (p, t) => tile(p, t).locator('.dl-whead')
const leftTab = async (p, i) => { await p.locator('.dl-bd-lh [role="tab"]').nth(i).click(); await sleep(800) }
const fld = (p, n) => p.locator(`button.dl-bd-f__b:has(.nm bdi:text-is("${n}"))`).first()
const rowOf = (p, n) => fld(p, n).locator('xpath=..')

const scenes = [
  { id: 'A1', name: 'donut-key-on-light-bg', themes: [THEMES[0], THEMES[2]],
    fix: board('QA6-Builder A1', [['donut', 'Share', { dimension: 'channel', measure: 'revenue', widget_background: '#fde68a' }, [0, 0, 7, 6]]]),
    url: id => `/reports/${id}`, act: async p => {
      const key = p.getByTestId('donut-key').first(); await key.waitFor({ timeout: 8000 })
      log.push(`A1 ${p.lang}: key colours ${JSON.stringify(await key.locator('li > span').evaluateAll(es => es.slice(0, 3).map(e => getComputedStyle(e).color)))}`)
    }, clip: { x: 0, y: 90, width: 1000, height: 520 } },
  { id: 'A2', name: 'data-view-floats', fix: board('QA6-Builder A2', [['kpi', 'Rows', {}, [0, 0, 3, 2]]]),
    url: id => `/reports/${id}?edit=1`, act: async p => {
      await p.getByTestId('view-strip').getByRole('button').nth(1).click(); await sleep(3500)
      const heads = await p.locator('table thead th').allInnerTexts()
      const i = heads.findIndex(h => /profit/.test(h))
      log.push(`A2 ${p.lang}: profit cells ${i < 0 ? 'no profit column' : JSON.stringify(await p.locator(`table tbody tr td:nth-child(${i + 1})`).evaluateAll(es => es.slice(0, 5).map(e => e.textContent)))}`)
      if (i >= 0) await p.locator(`table thead th:nth-child(${i + 1})`).scrollIntoViewIfNeeded()
    } },
  { id: 'A3', name: 'value-input-minus', themes: AR, fix: board('QA6-Builder A3', [['kpi', 'Revenue', { measure: 'revenue' }, [0, 0, 3, 2]]]),
    url: id => `/reports/${id}?edit=1`, act: async p => {
      await leftTab(p, 1)
      const box = p.locator('.dl-bd-rf'); await box.scrollIntoViewIfNeeded()
      await box.locator('select').nth(0).selectOption('revenue').catch(() => {})
      await box.locator('select').nth(1).selectOption('gte').catch(() => {})
      const v = box.locator('input:not([type=checkbox])').first(); await v.fill('-5'); await sleep(300)
      await v.scrollIntoViewIfNeeded()
    } },
  { id: 'A4', name: 'map-text', themes: AR, url: () => '/reports/5', act: async p => {
      await sleep(3000)
      log.push(`A4 ${p.lang}: table heads ${JSON.stringify(await p.getByTestId('map-data-table').first().locator('thead th').allTextContents())}; summary ${JSON.stringify((await p.locator('[role=img][aria-label], [role=group][aria-label]').first().getAttribute('aria-label'))?.slice(0, 90))}`)
    } },
  { id: 'A5', name: 'geo-popup-pack-name', themes: AR, fix: board('QA6-Builder A5', [['kpi', 'Revenue', { measure: 'revenue' }, [0, 0, 3, 2]]]),
    url: id => `/reports/${id}?edit=1`, act: async p => {
      await leftTab(p, 1); await rowOf(p, 'country').getByRole('button', { name: /^(Classify|تصنيف|Map geography|جغرافيا الخرائط)/ }).first().click(); await sleep(1200)
      log.push(`A5 ${p.lang}: menu ${JSON.stringify(await p.getByRole('menuitem').allInnerTexts())}`)
    } },
  { id: 'A6', name: 'tls-options', url: () => '/connections', act: async p => {
      await p.getByRole('button', { name: /New connection|اتصال جديد/ }).first().click(); await sleep(1200)
      await p.getByRole('dialog').getByText(/PostgreSQL/).first().click().catch(() => {}); await sleep(1200)
      const sel = p.getByRole('dialog').locator('select').filter({ has: p.locator('option[value="verify-ca"]') }).first()
      log.push(`A6 ${p.lang}: TLS ${JSON.stringify(await sel.locator('option').allTextContents())}`)
      await sel.scrollIntoViewIfNeeded().catch(() => {})
    } },
  { id: 'A7', name: 'difference-dialog', fix: board('QA6-Builder A7', [['bar', 'Rows by region', { dimension: 'region' }, [0, 0, 8, 6]]]),
    url: id => `/reports/${id}`, act: async p => {
      const w = tile(p, 'Rows by region'); await w.scrollIntoViewIfNeeded(); await w.hover(); await sleep(400)
      await w.locator('.dl-whead__ctl button.dl-wicon').first().click({ force: true }); await sleep(500)
      await p.getByRole('menuitem', { name: /difference|الفرق/ }).first().click(); await sleep(6000)
      log.push(`A7 ${p.lang}: chip ${JSON.stringify(await p.getByTestId('evidence-chip').allInnerTexts())}`)
    } },
  { id: 'A8', name: 'formula-placeholder', themes: AR, url: () => '/datasets/1', act: async p => {
      await p.getByRole('tab', { name: /^(Data|البيانات)/ }).first().click(); await sleep(2000)
      await p.locator('button.dl-data3__tool', { hasText: 'ƒx' }).click(); await sleep(1200)
      await p.getByRole('button', { name: /^(\+ Add|\+ إضافة)$/ }).first().click(); await sleep(1500)
      await p.getByRole('button', { name: /formula|صيغة/i }).first().click().catch(() => {}); await sleep(800)
    } },
  { id: 'A9', name: 'floating-filter-badge', fix: board('QA6-Builder A9', [['bar', 'Revenue by region', { dimension: 'region', measure: 'revenue' }, [0, 0, 8, 6]]]),
    url: id => `/reports/${id}`, act: async p => {
      const bar = p.locator('.recharts-wrapper').first().locator('.recharts-bar-rectangle .recharts-rectangle').nth(1)
      const b = await bar.boundingBox(); await p.mouse.click(b.x + b.width / 2, b.y + b.height / 2); await sleep(2000)
      await p.mouse.move(5, 5); await sleep(500)
      const badge = p.getByTestId('floating-filters')
      log.push(`A9 ${p.lang}: badge "${(await badge.innerText()).trim()}" at ${JSON.stringify(await badge.boundingBox())}`)
    } },
  { id: 'A10', name: 'template-page', themes: AR, fix: board('QA6-Builder A10', [['kpi', 'Revenue', { measure: 'revenue' }, [0, 0, 3, 2]]]),
    url: id => `/reports/${id}?edit=1`, act: async (p, fx) => {
      await leftTab(p, 2)
      await p.getByRole('button', { name: /مقارنة من أربع لوحات|Four-panel/ }).first().click(); await sleep(4000)
      const r = await api('GET', `/reports/${fx.id}`)
      const pg = r.pages.at(-1)
      log.push(`A10 ${p.lang}: page "${pg.name}" / "${pg.title}"; widgets ${JSON.stringify(pg.widgets.map(w => w.title))}`)
    } },
  { id: 'B1', name: 'setup-never-read', themes: AR.concat([THEMES[0]]), url: () => '/setup/1', act: async p => { await sleep(3000) } },
  { id: 'B2', name: 'sunburst-assign-and-drop', themes: AR, fix: board('QA6-Builder B2', [['sunburst', 'Sunburst', { measure: 'revenue' }, [0, 0, 6, 7]]]),
    url: id => `/reports/${id}?edit=1`, act: async (p, fx) => {
      await leftTab(p, 1)
      await fld(p, 'region').dragTo(tile(p, 'Sunburst')); await sleep(2000)
      await fld(p, 'country').dragTo(tile(p, 'Sunburst')); await sleep(2500)
      const w = (await api('GET', `/reports/${fx.id}`)).pages[0].widgets[0]
      log.push(`B2 ${p.lang}: after two drops, levels = ${JSON.stringify(w.config.levels)}; widgets on page = ${(await api('GET', `/reports/${fx.id}`)).pages[0].widgets.length}`)
      await head(p, 'Sunburst').click(); await sleep(800)
      await p.getByRole('tab', { name: /^(Data|البيانات)$/ }).first().click().catch(() => {}); await sleep(1200)
    } },
  { id: 'B4', name: 'year-kind', themes: AR.concat([THEMES[0]]), fix: board('QA6-Builder B4', [['kpi', 'Revenue', { measure: 'revenue' }, [0, 0, 3, 2]]]),
    url: id => `/reports/${id}?edit=1`, act: async p => {
      await leftTab(p, 1)
      log.push(`B4 ${p.lang}: year glyph ${JSON.stringify(await rowOf(p, 'year').locator('.dl-bd-f__ty').first().innerText())}`)
      await rowOf(p, 'year').scrollIntoViewIfNeeded()
    } },
  { id: 'B4', name: 'year-data-view', themes: AR.concat([THEMES[0]]), url: () => '/datasets/1', act: async p => {
      await p.getByRole('tab', { name: /^(Data|البيانات)/ }).first().click(); await sleep(2500)
      log.push(`B4 ${p.lang}: data header ${JSON.stringify((await p.locator('thead th').allInnerTexts()).slice(1, 4))}`)
    }, clip: { x: 0, y: 0, width: 1440, height: 420 } },
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
    if (sc.act) await sc.act(page, fx)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/${sc.id}-${sc.name}-${suffix}.png`, ...(sc.clip ? { clip: sc.clip } : {}) })
  console.log(BASE, suffix, sc.id, sc.name, note)
  await ctx.close()
  if (fx) { await fx.cleanup(); await sleep(1500) }
}
await browser.close()
console.log(log.join('\n'))
