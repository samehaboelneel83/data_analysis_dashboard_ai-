import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot FINAL: one pass over every main page in EN light and AR dark.
 * For each: console errors, page errors, failed API calls, and a sideways
 * overflow of the page (a layout break). Reads only.
 * Usage: node reg_final.mjs <outdir> (REPORT=5, DATASET=1)
 */
const OUT = process.argv[2]
const RID = process.env.REPORT ?? '5', DID = process.env.DATASET ?? '1'
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const pages = [
  { id: 'home', url: '/' },
  { id: 'dashboards', url: '/reports' },
  { id: 'view', url: `/reports/${RID}` },
  { id: 'present', url: `/reports/${RID}`, act: async p => { await p.locator('.dl-bd-icn[aria-pressed]').first().click(); await sleep(1500) } },
  { id: 'builder', url: `/reports/${RID}?edit=1` },
  { id: 'datasets', url: '/datasets' },
  { id: 'dataset', url: `/datasets/${DID}` },
  { id: 'ask', url: '/ask' },
  { id: 'lineage', url: '/lineage' },
  { id: 'upload', url: '/upload' },
  { id: 'connections', url: '/connections' },
  { id: 'admin-users', url: '/admin/users' },
  { id: 'admin-roles', url: '/admin/roles' },
]

const browser = await chromium.launch()
const state = await signIn(browser)
const rows = []
for (const pg of pages) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const issues = []
  page.on('console', m => { if (m.type() === 'error') issues.push('console: ' + m.text().slice(0, 160)) })
  page.on('pageerror', e => issues.push('pageerror: ' + String(e).slice(0, 160)))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) issues.push(`api ${r.status()}: ${new URL(r.url()).pathname}`) })
  try {
    await page.goto(BASE + pg.url); await sleep(4000)
    if (pg.act) await pg.act(page)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    if (over > 1) issues.push(`layout: page ${over}px wider than the window`)
  } catch (e) { issues.push('FAILED ' + String(e).split('\n')[0]) }
  await page.screenshot({ path: `${OUT}/R-${pg.id}-${suffix}.png` })
  rows.push([pg.id, suffix, issues])
  console.log(`${issues.length ? '✗' : '✓'} ${pg.id} ${suffix}${issues.length ? '\n    ' + [...new Set(issues)].join('\n    ') : ''}`)
  await ctx.close()
}
await browser.close()
console.log(`\n${rows.filter(r => !r[2].length).length}/${rows.length} clean`)
