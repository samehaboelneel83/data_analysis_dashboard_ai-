// QA3 N3, against a RUNNING stack: opening an old dashboard in Edit must not
// write anything, and the first real layout edit writes once, in order.
//
//   node frontend/e2e/journeys/n3_versions_journey.mjs
//
// Environment: as release_journey.mjs (JOURNEY_BASE_URL, JOURNEY_API_URL,
// JOURNEY_EMAIL, JOURNEY_PASSWORD). Creates one scratch dashboard through the
// API and deletes it at the end. Two pages:
//   "Old"     no layout mode (v1's auto-packing runs on it in Edit), widgets
//             stored where the packing will move them;
//   "Overlap" a packed page whose stored widgets overlap.
// Steps and checks (each prints the version count):
//   1. open in Edit, visit both pages            -> 0 new versions, layouts unchanged
//   2. drag one widget on "Old" (first real edit) -> stored = what was shown;
//      the writes are sequential (no two PATCHes in flight); version rows added
//   3. undo (Ctrl+Z)                              -> stored layouts = before step 2
// Exit code 1 when a check fails.

import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const BASE = (process.env.JOURNEY_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.JOURNEY_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.JOURNEY_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.JOURNEY_PASSWORD || 'demo-password'
const sleep = ms => new Promise(r => setTimeout(r, ms))

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(async r => { if (!r.ok) throw new Error(`${m} ${p} ${r.status} ${await r.text()}`); return r.status === 204 ? null : r.json() })

let failed = 0
const check = (ok, what) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${what}`); if (!ok) failed++ }
const versions = async rid => (await api('GET', `/reports/${rid}/versions`)).length
const stored = async (rid, pid) => Object.fromEntries((await api('GET', `/reports/${rid}`)).pages.find(p => p.id === pid).widgets
  .map(w => [w.title, `${w.layout.x},${w.layout.y},${w.layout.w},${w.layout.h}`]))
const sorted = o => Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)))
const same = (a, b) => JSON.stringify(sorted(a)) === JSON.stringify(sorted(b))

// ── Setup ───────────────────────────────────────────────────────────────
const r = await api('POST', '/reports', { name: 'N3 journey (scratch)', dataset_id: 1 })
const rid = r.id
let pages = (await api('GET', `/reports/${rid}`)).pages
const oldPid = pages[0]?.id ?? (await api('POST', `/reports/${rid}/pages`, { name: 'Old', position: 0 })).id
await api('PATCH', `/reports/${rid}/pages/${oldPid}`, { name: 'Old' })
// stored one under another, full width: the automatic packing lays them out differently
const OLD = [['kpi', 'KPI A', { measure: 'revenue' }], ['kpi', 'KPI B', { measure: 'units' }],
  ['kpi', 'KPI C', { measure: 'revenue' }], ['bar', 'Bar D', { dimension: 'region', measure: 'revenue' }]]
for (const [i, [t, title, config]] of OLD.entries())
  await api('POST', `/reports/${rid}/pages/${oldPid}/widgets`, { widget_type: t, title, config, layout: { x: 0, y: i * 5, w: 12, h: 5 } })
const ovPid = (await api('POST', `/reports/${rid}/pages`, { name: 'Overlap', position: 1, layout_mode: 'packed' })).id
await api('POST', `/reports/${rid}/pages/${ovPid}/widgets`, { widget_type: 'kpi', title: 'KPI E', config: { measure: 'revenue' }, layout: { x: 0, y: 0, w: 6, h: 4 } })
await api('POST', `/reports/${rid}/pages/${ovPid}/widgets`, { widget_type: 'kpi', title: 'KPI F', config: { measure: 'units' }, layout: { x: 3, y: 2, w: 6, h: 4 } })
pages = (await api('GET', `/reports/${rid}`)).pages
console.log(`setup: report ${rid}; "Old" layout_mode=${JSON.stringify(pages.find(p => p.id === oldPid).layout_mode)}, "Overlap" layout_mode=${JSON.stringify(pages.find(p => p.id === ovPid).layout_mode)}`)

const browser = await chromium.launch()
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(BASE + '/login')
  await page.getByLabel('Email', { exact: true }).fill(EMAIL)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })

  // ── 1. Open in Edit, both pages ────────────────────────────────────────
  const v0 = await versions(rid)
  const oldBefore = await stored(rid, oldPid), ovBefore = await stored(rid, ovPid)
  await page.goto(`${BASE}/reports/${rid}?edit=1`)
  await page.waitForSelector('[data-widget-id]', { timeout: 30000 }); await sleep(6000)
  await page.getByRole('tab', { name: /Overlap/ }).or(page.locator('.dl-bd-pg', { hasText: 'Overlap' })).first().click(); await sleep(6000)
  await page.getByRole('tab', { name: /^Old/ }).or(page.locator('.dl-bd-pg', { hasText: 'Old' })).first().click(); await sleep(4000)
  const v1 = await versions(rid)
  console.log(`versions: before opening ${v0}, after opening in Edit and visiting both pages ${v1}`)
  check(v1 === v0, 'opening an old dashboard in Edit creates zero versions')
  check(same(await stored(rid, oldPid), oldBefore), '"Old" (no layout mode): stored layouts unchanged by opening')
  check(same(await stored(rid, ovPid), ovBefore), '"Overlap" (packed, overlapping): stored layouts unchanged by opening')

  // what the canvas shows, per widget, in px relative to the canvas
  const shown = () => page.evaluate(() => {
    const c = document.querySelector('[data-canvas]').getBoundingClientRect()
    return Object.fromEntries([...document.querySelectorAll('[data-widget-id]')].map(el => {
      const b = el.getBoundingClientRect(); const t = el.querySelector('[role="heading"]')?.textContent ?? el.dataset.widgetId
      return [t, [Math.round(b.left - c.left), Math.round(b.top - c.top), Math.round(b.width), Math.round(b.height)].join(',')]
    }))
  })
  const shownBefore = await shown()

  // ── 2. The first real edit: drag KPI A by its grip into empty space ────
  const inFlight = new Set(); let overlapped = 0; let writes = 0
  const t0 = Date.now(); const log = []
  page.on('request', q => { if (q.method() === 'PATCH' && /\/reports\/\d+\/pages\//.test(q.url())) { if (inFlight.size) overlapped++; inFlight.add(q); writes++; log.push(`${Date.now() - t0} start ${q.url().split('/v1')[1]}`) } })
  page.on('response', q => { if (q.request().method() === 'PATCH' && inFlight.has(q.request())) { inFlight.delete(q.request()); log.push(`${Date.now() - t0} done  ${q.url().split('/v1')[1]} ${q.status()}`) } })
  page.on('requestfailed', q => inFlight.delete(q))
  process.on('exit', () => { if (process.env.N3_LOG) console.log(log.join('\n')) })
  const grip = page.locator('[data-widget-id]', { hasText: 'KPI A' }).locator('.dl-whead').locator('text=⠿')
  const g = await grip.boundingBox(); const cv = await page.locator('[data-canvas]').boundingBox()
  await page.mouse.move(g.x + g.width / 2, g.y + g.height / 2); await page.mouse.down()
  await page.mouse.move(cv.x + cv.width * 0.75, cv.y + 22 * 66, { steps: 15 }); await sleep(200)
  await page.mouse.up(); await sleep(6000)
  const v2 = await versions(rid)
  const oldAfterEdit = await stored(rid, oldPid)
  const mode = (await api('GET', `/reports/${rid}`)).pages.find(p => p.id === oldPid).layout_mode
  console.log(`versions after the first edit: ${v2} (+${v2 - v1}); ${writes} PATCH requests; layout_mode now ${JSON.stringify(mode)}`)
  check(overlapped === 0 && writes > 0, `the first edit writes in one sequential pass (${writes} writes, ${overlapped} started while another was in flight)`)
  check(v2 - v1 === writes, `version rows added = writes (${v2 - v1})`)
  // stored = shown: reload, and every widget the drag did not move is drawn where it was before the drag
  await page.reload(); await page.waitForSelector('[data-widget-id]'); await sleep(4000)
  const shownAfter = await shown()
  const others = Object.keys(shownBefore).filter(k => k !== 'KPI A')
  check(others.every(k => shownAfter[k] === shownBefore[k]), `stored = shown: after a reload the other widgets are where they were shown (${others.map(k => `${k} ${shownBefore[k]}→${shownAfter[k]}`).join('; ')})`)
  check(shownAfter['KPI A'] !== shownBefore['KPI A'], `the dragged widget moved (${shownBefore['KPI A']} → ${shownAfter['KPI A']})`)

  // ── 3. Undo ────────────────────────────────────────────────────────────
  // the reload cleared this session's undo stack, so redo the edit and undo it in one visit
  writes = 0; overlapped = 0
  await api('PATCH', `/reports/${rid}/pages/${oldPid}`, { layout_mode: '' })
  for (const [title, l] of Object.entries(oldBefore)) {
    const w = (await api('GET', `/reports/${rid}`)).pages.find(p => p.id === oldPid).widgets.find(x => x.title === title)
    const [x, y, ww, h] = l.split(',').map(Number)
    await api('PATCH', `/reports/${rid}/pages/${oldPid}/widgets/${w.id}`, { layout: { x, y, w: ww, h } })
  }
  check(same(await stored(rid, oldPid), oldBefore), 'reset to the old stored layouts for the undo check')
  const vReset = await versions(rid)
  await page.reload(); await page.waitForSelector('[data-widget-id]'); await sleep(5000)
  const vPre = await versions(rid)
  const g2 = await page.locator('[data-widget-id]', { hasText: 'KPI A' }).locator('.dl-whead').locator('text=⠿').boundingBox()
  const cv2 = await page.locator('[data-canvas]').boundingBox()
  await page.mouse.move(g2.x + g2.width / 2, g2.y + g2.height / 2); await page.mouse.down()
  await page.mouse.move(cv2.x + cv2.width * 0.75, cv2.y + 22 * 66, { steps: 15 }); await sleep(200)
  await page.mouse.up(); await sleep(6000)
  const v3 = await versions(rid)
  await page.locator('[data-canvas]').click({ position: { x: 5, y: 5 } }).catch(() => {})
  await page.keyboard.press('Control+z'); await sleep(6000)
  const v4 = await versions(rid)
  const afterUndo = await stored(rid, oldPid)
  const modeAfterUndo = (await api('GET', `/reports/${rid}`)).pages.find(p => p.id === oldPid).layout_mode
  console.log(`versions: after re-opening ${vPre} (+0 expected), after the edit ${v3} (+${v3 - vPre}), after undo ${v4} (+${v4 - v3}); layout_mode after undo ${JSON.stringify(modeAfterUndo)}`)
  check(vPre === vReset, `re-opening after the reset wrote nothing either (${vReset} → ${vPre})`)
  check(same(afterUndo, oldBefore), `undo restores the pre-edit stored layouts (${JSON.stringify(afterUndo)})`)
  check(!modeAfterUndo, 'undo puts the page back to "no layout mode", so it is drawn as before')
  check(overlapped === 0, `undo writes sequentially too (${overlapped} overlapping)`)
} finally {
  await browser.close()
  await api('DELETE', `/reports/${rid}`).catch(() => {})
}
console.log(failed ? `${failed} check(s) failed` : 'all checks passed')
process.exit(failed ? 1 : 0)
