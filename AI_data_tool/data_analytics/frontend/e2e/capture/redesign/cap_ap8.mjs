import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 8 (9-polish): the dashboards row menu (Open in edit mode),
 * the View hover toolbar (Copy image), Home's whole-page error, the Builder
 * rail's review count and the toolbar grip, the Datasets health strip while
 * loading, the dataset Overview (Models), the Models tab (Retrain), the Data
 * tab (grouped numbers) and the Share dialog's type-ahead. EN light and AR
 * dark. Reads only; the error and loading states are browser-only routes.
 * Usage: node cap_ap8.mjs <outdir> [scene-prefix] (REPORT=5, DATASET=1)
 */
const OUT = process.argv[2]
const only = process.argv[3]
const RID = process.env.REPORT ?? '5', DID = process.env.DATASET ?? '1'
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const scenes = [
  { id: 'dash-menu', url: '/reports', act: async p => { await p.locator('[aria-haspopup="menu"]').filter({ hasNot: p.locator('xxx') }).nth(1).click(); await sleep(500) } },
  { id: 'view-hover', url: `/reports/${RID}`, act: async p => { const w = p.locator('[data-widget-id]').nth(1); await w.hover(); await sleep(500) } },
  { id: 'home-error', url: '/', route: [/\/api\/v1\/reports$/, 500] },
  { id: 'builder-rail', url: `/reports/${RID}?edit=1`, act: async p => { await sleep(1500); await p.locator('[data-widget-id]').nth(1).hover(); await sleep(400) } },
  { id: 'datasets-loading', url: '/datasets', route: [/\/api\/v1\/datasets$/, 'never'] },
  { id: 'overview', url: `/datasets/${DID}` },
  { id: 'models', url: `/datasets/${DID}?tab=models` },
  { id: 'data', url: `/datasets/${DID}?tab=data` },
  { id: 'share', url: `/datasets/${DID}`, act: async p => { const b = p.getByRole('button', { name: /^(Share|مشاركة)/ }).first(); await b.click(); await sleep(800); await p.getByRole('combobox').first().focus(); await sleep(400) } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
  if (sc.route) await page.route(u => sc.route[0].test(new URL(u).pathname), r => (r.request().method() !== 'GET' ? r.continue()
    : sc.route[1] === 'never' ? undefined : r.fulfill({ status: sc.route[1], json: { detail: 'The database is starting up; try again in a minute.' } })))
  let note = ''
  try {
    await page.goto(BASE + sc.url); await sleep(3000)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/P-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
