import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')
const BASE = 'http://localhost:3001'
const b = await chromium.launch()
const lc = await b.newContext({ viewport: { width: 1440, height: 900 } }); const lp = await lc.newPage()
await lp.goto(BASE + '/login')
await lp.getByLabel('Email', { exact: true }).fill('admin@datalytics.local')
await lp.getByLabel('Password', { exact: true }).fill('demo-password')
await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
await lp.waitForURL(u => !String(u).includes('/login'))
const state = await lc.storageState(); await lc.close()
for (const [lang, w] of [['en', 1440], ['ar', 1440], ['en', 900], ['ar', 900]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 }, storageState: state })
  await ctx.addInitScript(l => { localStorage.setItem('theme', 'light'); localStorage.setItem('datalytics.language', l); localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr') }, lang)
  const p = await ctx.newPage()
  await p.route(u => new URL(u).pathname === '/api/v1/datasets/1', async r => {
    if (r.request().method() !== 'GET') return r.continue()
    const res = await r.fetch(); const j = await res.json(); j.data_source_id = 2; j.last_refreshed_at = new Date().toISOString()
    await r.fulfill({ json: j })
  })
  await p.goto(BASE + '/datasets/1?tab=overview'); await p.locator('h1').first().waitFor(); await p.waitForTimeout(2500)
  const btn = p.locator('.dl-dsd__actions button.btn-ghost.btn-sm').first()
  console.log(lang, w, 'refresh button:', await btn.count() ? await btn.textContent() : 'none')
  if (!(await btn.count())) { await ctx.close(); continue }
  await btn.click(); await p.waitForTimeout(500)
  const r = await p.evaluate(() => {
    const el = [...document.querySelectorAll('.dl-dsd__actions div')].find(d => getComputedStyle(d).position === 'absolute' && d.getBoundingClientRect().width > 200)
    if (!el) return null
    const rc = el.getBoundingClientRect()
    const pts = [[rc.left + 4, rc.top + 4], [rc.right - 4, rc.top + 4], [rc.left + 4, rc.bottom - 4], [rc.right - 4, rc.bottom - 4]]
    return { hidden: pts.filter(([x, y]) => { const h = document.elementFromPoint(x, y); return !h || !el.contains(h) }).length,
      off: rc.left < 0 || rc.right > innerWidth || rc.bottom > innerHeight, rc: [rc.left, rc.top, rc.right, rc.bottom].map(Math.round) }
  })
  console.log(lang, w, 'refresh popup:', JSON.stringify(r))
  await p.screenshot({ path: `${process.argv[2] || '.'}/refresh-${lang}-${w}.png` })
  await ctx.close()
}
await b.close()
