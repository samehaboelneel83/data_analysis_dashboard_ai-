/** 7-QA5b S2: a cross-filter click in View on a light-background bar and a stacked bar; logs the visible tooltip. Usage: node cap_qa5b_s2.mjs <outdir> <tag>. */
import { chromium, signIn, sleep, openPage } from './_qa3_lib.mjs'
const OUT = process.argv[2]; const TAG = process.argv[3] ?? 'x'
const API = 'http://localhost:8000/api/v1'
const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' }, body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())
for (const x of (await api('GET', '/reports')).filter?.(x => x.name === 'QA5b scratch') ?? []) await api('DELETE', '/reports/' + x.id)
const r = await api('POST', '/reports', { name: 'QA5b scratch', dataset_id: 1 })
const pid = (await api('GET', `/reports/${r.id}`)).pages[0].id
await api('PATCH', `/reports/${r.id}/pages/${pid}`, { layout_mode: 'free' })
await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: 'bar', title: 'Breakdown', config: { dimension: 'region', measure: 'units', widget_background: '#fde68a' }, layout: { x: 0, y: 0, w: 6, h: 7 } })
await api('POST', `/reports/${r.id}/pages/${pid}/widgets`, { widget_type: 'bar', title: 'Stacked', config: { dimension: 'region', dimension2: 'channel', measure: 'revenue' }, layout: { x: 6, y: 0, w: 6, h: 7 } })
const browser = await chromium.launch(); const state = await signIn(browser)
const log = []
for (const th of [['ar-dark', 'ar', 'dark'], ['en-light', 'en', 'light']]) {
  const { ctx, page } = await openPage(browser, state, th, '/reports/' + r.id)
  await sleep(5000)
  for (const [wi, name] of [[0, 'single'], [1, 'stacked']]) {
    const bar = page.locator('.recharts-wrapper').nth(wi).locator('.recharts-bar-rectangle .recharts-rectangle').nth(2)
    const b = await bar.boundingBox()
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 4 }); await sleep(500)
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2); await sleep(2500)
    await page.mouse.move(b.x + b.width / 2 + 3, b.y + b.height / 2 + 30, { steps: 3 }); await sleep(800)
    log.push(th[0] + ' ' + name + ' ' + JSON.stringify(await page.evaluate(() => [...document.querySelectorAll('.recharts-tooltip-wrapper')]
      .filter(e => getComputedStyle(e).visibility !== 'hidden').map(e => ({ items: e.querySelectorAll('.recharts-tooltip-item').length, text: e.textContent.trim().slice(0, 50), w: Math.round(e.getBoundingClientRect().width) })))))
    await page.screenshot({ path: `${OUT}/S2-${TAG}-${name}-${th[0]}.png` })
    await page.getByRole('button', { name: /Reset filters|إعادة ضبط/ }).first().click({ timeout: 2000 }).catch(() => {}); await sleep(1500)
  }
  await ctx.close()
}
await api('DELETE', `/reports/${r.id}`)
await browser.close(); console.log(log.join('\n'))
