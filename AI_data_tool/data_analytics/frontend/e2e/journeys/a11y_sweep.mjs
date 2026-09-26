// An accessibility sweep over the main screens (E10), against a RUNNING stack.
//
//   node frontend/e2e/journeys/a11y_sweep.mjs
//
// Environment: as release_journey.mjs. Signs in, then visits Home, Datasets,
// one dataset, Dashboards, one dashboard, Ask AI, Connections and Insights,
// in English and in Arabic. On each it runs axe and records every serious or
// critical violation, and checks that Tab moves focus into the page's main
// content. Reads only; creates nothing. Output:
// demo_output/journeys/a11y-<timestamp>/ (report.json and a screenshot per
// screen). Exit code 1 when anything serious is found.

import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..', '..', '..')
const BASE = (process.env.JOURNEY_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const API = (process.env.JOURNEY_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const EMAIL = process.env.JOURNEY_EMAIL || 'admin@datalytics.local'
const PASSWORD = process.env.JOURNEY_PASSWORD || 'demo-password'
const OUT = path.join(ROOT, 'demo_output', 'journeys', 'a11y-' + new Date().toISOString().replace(/[:.]/g, '-'))
fs.mkdirSync(OUT, { recursive: true })
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

async function api(url, token) {
  const r = await fetch(API + url, { headers: { Authorization: `Bearer ${token}`, 'X-Requested-With': 'XMLHttpRequest' } })
  return r.ok ? r.json() : null
}

const token = (await (await fetch(API + '/auth/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
})).json()).access_token
const datasets = (await api('/datasets', token)) ?? []
const reports = (await api('/reports', token)) ?? []
const screens = [
  ['home', '/'],
  ['datasets', '/datasets'],
  ...(datasets[0] ? [['dataset', `/datasets/${datasets[0].id}`]] : []),
  ['dashboards', '/reports'],
  // Every dashboard with JOURNEY_ALL_DASHBOARDS=1 (each widget type draws its
  // own SVG), else the first.
  ...(process.env.JOURNEY_ALL_DASHBOARDS ? reports : reports.slice(0, 1))
    .map(r => [`dashboard ${r.id}`, `/reports/${r.id}`]),
  ['ask', '/ask'],
  ['connections', '/connections'],
  ['insights', '/insights'],
]

const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE
  ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE } : {})
const report = []
try {
  for (const lang of ['en', 'ar']) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await ctx.addInitScript(l => {
      try {
        localStorage.setItem('datalytics.language', l)
        localStorage.setItem('datalytics.direction', l === 'ar' ? 'rtl' : 'ltr')
      } catch { /* storage blocked */ }
    }, lang)
    const page = await ctx.newPage()
    await page.goto(`${BASE}/login`)
    await page.getByLabel(/^(email|البريد الإلكتروني)$/i).fill(EMAIL)
    await page.getByLabel(/^(password|كلمة المرور)$/i).fill(PASSWORD)
    await page.getByRole('button', { name: /^(sign in|تسجيل الدخول)$/i }).click()
    await page.waitForURL(u => !String(u).includes('/login'), { timeout: 15000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    for (const [name, url] of screens) {
      // A navigation the app itself starts (the post-login redirect) can
      // abort ours; one retry is enough.
      await page.goto(BASE + url).catch(() => page.goto(BASE + url))
      await page.waitForLoadState('networkidle').catch(() => {})
      // A dashboard is checked as its readers see it: an editor lands in the
      // designer, whose placement aids (faded hidden pages, widgets parked in
      // a container's other tab) are not what anyone reads.
      const viewMode = page.getByRole('button', { name: 'View mode' })
      if (url.startsWith('/reports/') && await viewMode.count()) await viewMode.click()
      await page.waitForTimeout(1200)
      await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
      const violations = await page.evaluate(async () => {
        const r = await window.axe.run(document, { resultTypes: ['violations'] })
        return r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
          .map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
                       targets: v.nodes.slice(0, 4).map(n => n.target.join(' ')),
                       html: v.nodes.slice(0, 2).map(n => n.html.slice(0, 160)) }))
      })
      // Tab from the top: the skip link first, then into the page.
      await page.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0) })
      await page.keyboard.press('Tab')
      const firstStop = await page.evaluate(() => (document.activeElement?.textContent ?? '').trim().slice(0, 40))
      await page.screenshot({ path: path.join(OUT, `${lang}_${name.replace(/\W+/g, '_')}.png`) })
      report.push({ lang, screen: name, url, firstTabStop: firstStop, violations })
      log(lang, name, violations.length ? violations.map(v => `${v.id}(${v.nodes})`).join(' ') : 'clean',
          `| first Tab: "${firstStop}"`)
    }
    await ctx.close()
  }
} finally {
  await browser.close()
}
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2))
const found = report.reduce((n, r) => n + r.violations.length, 0)
log(`${found} serious/critical violation kinds across ${report.length} screens -- ${OUT}`)
process.exitCode = found ? 1 : 0
