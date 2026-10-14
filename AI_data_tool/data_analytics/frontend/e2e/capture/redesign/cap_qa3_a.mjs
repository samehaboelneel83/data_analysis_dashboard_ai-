import { chromium, signIn, openPage, sleep, THEMES, BASE } from './_qa3_lib.mjs'

/**
 * QA3 Batch A (builder behaviour) × light / dark / Arabic / Arabic dark.
 * Each theme gets its own scratch dashboard (made through the API, deleted at
 * the end): KPI 1–4 across the top, a bar with no dimension, a KPI with no
 * measure. What each scene changed is read back from the API and printed.
 * Usage: node cap_qa3_a.mjs <outdir> [scene]; ONLY=<theme> for one theme.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const API = process.env.API ?? 'http://localhost:8000/api/v1'

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())

async function fixture() {
  const r = await api('POST', '/reports', { name: 'QA3-fix scratch', dataset_id: 1 })
  const got = await api('GET', `/reports/${r.id}`)
  const pid = got.pages[0]?.id ?? (await api('POST', `/reports/${r.id}/pages`, { name: 'Page 1', position: 0 })).id
  // A saved layout mode, so the page is drawn where it is stored.
  await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: process.env.LAYOUT ?? 'free', layout_template: 'executive' })
  const W = [['kpi', 'KPI 1', { measure: 'revenue' }, [0, 0, 3, 2]], ['kpi', 'KPI 2', { measure: 'units' }, [3, 0, 3, 2]],
    ['kpi', 'KPI 3', { measure: 'revenue' }, [6, 0, 3, 2]], ['kpi', 'KPI 4', { measure: 'units' }, [9, 0, 3, 2]],
    ['bar', 'Empty bar', { measure: 'revenue' }, [0, 2, 6, 5]], ['kpi', 'Empty KPI', {}, [6, 2, 3, 2]]]
  for (const [t, title, config, [x, y, w, h]] of W)
    await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: t, title, config, layout: { x, y, w, h } })
  return r.id
}
const widgets = async rid => (await api('GET', `/reports/${rid}`)).pages[0].widgets
const brief = ws => ws.map(w => `${w.title}@${w.layout.x},${w.layout.y}`).join(' ')

const tile = (p, t) => p.locator('[data-widget-id]', { hasText: t }).first()
const head = (p, t) => tile(p, t).locator('.dl-whead')
const rail = (p, i) => p.locator('nav.dl-bd-rail button.dl-bd-ri').nth(i)
const fld = (p, n) => p.locator(`button.dl-bd-f__b:has(.nm bdi:text-is("${n}"))`).first()
async function fields(p) { await p.locator('.dl-bd-lh [role="tab"]').nth(1).click(); await sleep(500) }

const scenes = [
  { id: 'A1', name: 'shift-select-3', act: async p => {
    await head(p, 'KPI 1').click(); await sleep(300)
    await head(p, 'KPI 2').click({ modifiers: ['Shift'] }); await sleep(300)
    await head(p, 'KPI 3').click({ modifiers: ['Shift'] }); await sleep(600)
    return 'status: ' + await p.locator('.dl-bd-status, footer').last().innerText().catch(() => '?')
  } },
  { id: 'A2', name: 'drop-region-on-bar', act: async (p, rid) => {
    await fields(p); await fld(p, 'region').dragTo(tile(p, 'Empty bar')); await sleep(2500)
    return (await widgets(rid)).find(w => w.title === 'Empty bar').config.dimension ?? 'NO DIMENSION'
  } },
  { id: 'A3-A5', name: 'drop-units-on-kpi-panel', act: async (p, rid) => {
    await head(p, 'Empty KPI').click(); await sleep(800)
    await p.locator('.dl-bd-psec [role="tab"], [role="tab"]').filter({ hasText: /^(Data|البيانات)$/ }).last().click().catch(() => {}); await sleep(600)
    await fields(p); await fld(p, 'units').dragTo(tile(p, 'Empty KPI')); await sleep(2500)
    return (await widgets(rid)).find(w => w.title === 'Empty KPI').config.measure ?? 'NO MEASURE'
  } },
  { id: 'A4', name: 'quick-filters', act: async p => {
    await tile(p, 'KPI 2').hover(); await sleep(300)
    await tile(p, 'KPI 2').locator('.dl-bd-wt button').last().click(); await sleep(1200)
    return 'tab: ' + await p.locator('[role="tab"][aria-selected="true"]').allInnerTexts().then(a => a.join('|'))
  } },
  { id: 'A6', name: 'click-bar-edit', act: async (p, rid) => {
    await api('PATCH', `/reports/${rid}/pages/${(await api('GET', `/reports/${rid}`)).pages[0].id}/widgets/${(await widgets(rid)).find(w => w.title === 'Empty bar').id}`, { config: { measure: 'revenue', dimension: 'region' } })
    await p.reload(); await p.waitForSelector('[data-widget-id]'); await sleep(4000)
    const box = await tile(p, 'Empty bar').boundingBox()
    await p.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.6); await sleep(1200)
    return 'filter chips: ' + await p.locator('text=/1 filter|filter 1|فلتر|مرشح/i').count()
  } },
  { id: 'A7', name: 'move-kpi1-down', act: async (p, rid) => {
    // the ⠿ grip: in Arabic the header's left end holds the buttons
    const h = await head(p, 'KPI 1').locator('text=⠿').boundingBox()
    const cv = await p.locator('[data-canvas]').boundingBox()
    await p.mouse.move(h.x + h.width / 2, h.y + h.height / 2); await p.mouse.down()
    // to column 1, row 8 (empty space under everything)
    await p.mouse.move(cv.x + 20, cv.y + 8 * 66 + 10, { steps: 12 }); await sleep(200)
    await p.mouse.up(); await sleep(2500)
    return brief(await widgets(rid))
  } },
  { id: 'A8', name: 'tab-order', act: async (p, rid) => {
    // KPI 1 moved under the bar first: the order must follow it
    const pid = (await api('GET', `/reports/${rid}`)).pages[0].id
    const k1 = (await widgets(rid)).find(w => w.title === 'KPI 1')
    await api('PATCH', `/reports/${rid}/pages/${pid}/widgets/${k1.id}`, { layout: { x: 0, y: 8, w: 3, h: 2 } })
    await p.reload(); await p.waitForSelector('[data-widget-id]'); await sleep(2500)
    await rail(p, 11).click(); await sleep(800)
    return await p.locator('[data-testid="tab-order-row"]').allInnerTexts().then(a => a.map(s => s.replace(/\s+/g, ' ').replace(/[↑↓]/g, '').trim()).join(' | '))
  } },
  { id: 'A9', name: 'view-then-edit-rail', act: async p => {
    await p.getByTestId('mode-toggle').click(); await sleep(1500)
    await p.getByTestId('mode-toggle').click(); await sleep(1500)
    return 'rail expanded: ' + await p.getByTestId('app-rail').getAttribute('data-expanded')
  } },
  { id: 'A10', name: 'duplicate-and-escape', act: async p => {
    await head(p, 'Empty bar').click(); await sleep(300)
    await p.keyboard.press('Control+d'); await sleep(2500)
    await p.screenshot({ path: `${OUT}/A10-duplicate-in-view-${p.suffix}.png` })
    await p.keyboard.press('Escape'); await sleep(600)
    return 'outlined after Esc: ' + await p.locator('[data-widget-id] [data-selected="true"], .dl-bd-guides, [data-testid="selection-guides"]').count()
  } },
].filter(s => !only || s.id === only)

const browser = await chromium.launch()
const state = await signIn(browser)
for (const th of THEMES.filter(t => !process.env.ONLY || t[0] === process.env.ONLY)) {
  for (const sc of scenes) {
    const rid = await fixture()
    const { ctx, page } = await openPage(browser, state, th, `/reports/${rid}?edit=1`)
    page.suffix = th[0]
    let note = ''
    try {
      // The dev API rate-limits: on "Rate limit exceeded", wait and reload.
      for (let i = 0; i < 4; i++) {
        const got = await Promise.race([
          page.waitForSelector('[data-widget-id]', { timeout: 45000 }).then(() => 'ok'),
          page.waitForSelector('text=/Rate limit|تجاوز/', { timeout: 45000 }).then(() => 'limited')])
        if (got === 'ok') break
        await sleep(30000); await page.reload()
      }
      await sleep(2500)
      note = await sc.act(page, rid)
    } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
    await page.screenshot({ path: `${OUT}/${sc.id}-${sc.name}-${th[0]}.png` })
    console.log(BASE, th[0], sc.id, note, page.errors.length ? page.errors : '')
    await ctx.close()
    await api('DELETE', `/reports/${rid}`)
    await sleep(Number(process.env.PAUSE ?? 6000))
  }
}
await browser.close()
