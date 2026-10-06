import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')
const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const VIEW = { width: Number(process.env.W || 1440), height: 900 }
const pages = [
  { name: 'list', url: '/datasets', ready: 'table.dl-dsl__table tbody tr' },
  { name: 'overview', url: '/datasets/1?tab=overview', ready: 'h1' },
  { name: 'columns', url: '/datasets/1?tab=columns', ready: 'h1' },
  { name: 'data', url: '/datasets/1?tab=data', ready: '.dl-data3__main table' },
  { name: 'analysis', url: '/datasets/1?tab=analysis', ready: 'h1' },
  { name: 'rules', url: '/datasets/1?tab=rules', ready: 'h1' },
  { name: 'models', url: '/datasets/1?tab=models', ready: 'h1' },
  { name: 'aggregates', url: '/datasets/6?tab=aggregates', ready: 'h1' },
  { name: 'live-overview', url: '/datasets/6?tab=overview', ready: 'h1' },
  { name: 'share', url: '/datasets/1?tab=overview', ready: 'h1', pre: async p => { await p.locator('button', { hasText: /^(Share|مشاركة)$/ }).first().click(); await p.waitForTimeout(1500) }, scope: '[role="dialog"]' },
]
// Triggers: popup buttons, "⋯" menus, the refresh options toggle; never destructive.
const TRIGGER = 'button[aria-haspopup], button[aria-expanded], .dl-dsd__actions button.btn-ghost.btn-sm'
const b = await chromium.launch()
const lc = await b.newContext({ viewport: VIEW }); const lp = await lc.newPage()
await lp.goto(BASE + '/login')
await lp.getByLabel('Email', { exact: true }).fill('admin@datalytics.local')
await lp.getByLabel('Password', { exact: true }).fill('demo-password')
await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
await lp.waitForURL(u => !String(u).includes('/login'))
const state = await lc.storageState(); await lc.close()
const problems = []
for (const lang of ['en', 'ar']) for (const pg of pages) {
  const ctx = await b.newContext({ viewport: VIEW, storageState: state })
  await ctx.addInitScript(l => { localStorage.setItem('theme', 'light'); localStorage.setItem('datalytics.language', l); localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr') }, lang)
  const p = await ctx.newPage()
  const load = async () => {
    await p.goto(BASE + pg.url); await p.locator(pg.ready).first().waitFor({ timeout: 90000 }).catch(() => {})
    await p.waitForTimeout(2500); if (pg.pre) await pg.pre(p)
  }
  await load()
  const root = pg.scope ? p.locator(pg.scope).first() : p.locator('main')
  const n = await root.locator(TRIGGER).count()
  // Rows repeat the same menu: first, middle, last row is enough.
  let idx = [...Array(n).keys()]
  const labels = await root.locator(TRIGGER).evaluateAll(els => els.map(e => (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 50)))
  const seen = new Map()
  idx = idx.filter(i => { const k = labels[i].replace(/dataset .*/, 'dataset *'); const c = (seen.get(k) || 0) + 1; seen.set(k, c); return c <= 2 || i === n - 1 })
  for (const i of idx) {
    const t = root.locator(TRIGGER).nth(i)
    if (!(await t.isVisible().catch(() => false)) || await t.isDisabled()) continue
    const before = await p.evaluate(() => { window.__mark = new Set([...document.querySelectorAll('*')]); return 0 })
    await t.scrollIntoViewIfNeeded().catch(() => {})
    await t.click({ timeout: 3000 }).catch(() => {})
    await p.waitForTimeout(400)
    const res = await p.evaluate(() => {
      const out = []
      for (const el of document.querySelectorAll('*')) {
        if (window.__mark.has(el)) continue
        const cs = getComputedStyle(el)
        if (!['absolute', 'fixed'].includes(cs.position) && el.getAttribute('role') !== 'menu') continue
        const r = el.getBoundingClientRect()
        if (r.width < 40 || r.height < 24 || cs.visibility === 'hidden' || cs.display === 'none') continue
        if (el.parentElement && !window.__mark.has(el.parentElement) && ['absolute', 'fixed'].includes(getComputedStyle(el.parentElement).position)) continue
        const pts = [[r.left + 4, r.top + 4], [r.right - 4, r.top + 4], [r.left + 4, r.bottom - 4], [r.right - 4, r.bottom - 4]]
        const hidden = pts.filter(([x, y]) => { const h = document.elementFromPoint(x, y); return !h || !(el === h || el.contains(h)) }).length
        const off = r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight
        out.push({ cls: (el.className?.baseVal ?? el.className ?? el.tagName).toString().slice(0, 60), role: el.getAttribute('role'), hidden, off, w: Math.round(r.width), h: Math.round(r.height) })
      }
      return out
    })
    const label = labels[i]
    for (const r of res) {
      const bad = r.hidden > 0 || r.off
      console.log(`${lang} ${pg.name} [${label}] -> ${r.role || r.cls} ${r.w}x${r.h} corners hidden:${r.hidden}${r.off ? ' OFFSCREEN' : ''}${bad ? '  <-- PROBLEM' : ''}`)
      if (bad) { problems.push(`${lang} ${pg.name} [${label}]`); await p.screenshot({ path: `${OUT}/${lang}-${pg.name}-${i}.png` }) }
    }
    await p.keyboard.press('Escape'); await p.waitForTimeout(200)
    if (await p.locator('[role="menu"]').count()) await p.mouse.click(5, 5)
    if (pg.scope && !(await p.locator(pg.scope).count())) await load()
  }
  await ctx.close()
}
console.log('PROBLEMS:', problems.length ? problems.join('\n') : 'none')
await b.close()
