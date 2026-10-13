import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 4 (Lineage): the graph, a focused node with its panel, a
 * search, issues only, the list view, and the empty and error states, EN light
 * and AR dark at 1440 (some at 1024). Reads only; the empty and error states
 * are browser-only routes. Usage: node cap_ap4.mjs <outdir> [scene-prefix]
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const node = (p, re) => p.locator('.dl-ln-n, [role="button"]').filter({ hasText: re }).first()
const scenes = [
  { id: 'graph' },
  { id: 'graph-1024', view: { width: 1024, height: 768 } },
  { id: 'focus', act: async p => { await node(p, /Demo — Sales/).click(); await sleep(900) } },
  { id: 'search', act: async p => { await p.getByRole('combobox').or(p.getByRole('searchbox')).first().fill('Demo'); await sleep(700) } },
  { id: 'issues', act: async p => { const b = p.getByRole('button', { name: /issues|المشكلات/i }); if (await b.count()) { await b.first().click(); await sleep(700) } } },
  { id: 'list', act: async p => { const b = p.getByRole('radio', { name: /^(List|قائمة)$/ }); if (await b.count()) { await b.click(); await sleep(700) } } },
  { id: 'empty', route: { sources: [], datasets: [], reports: [] } },
  { id: 'error', route: 500 },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: sc.view ?? { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
  if (sc.route) await page.route(at('/api/v1/datasets/lineage/graph'), r => sc.route === 500 ? r.fulfill({ status: 500, json: { detail: 'boom' } }) : r.fulfill({ json: sc.route }))
  let note = ''
  try {
    await page.goto(BASE + '/lineage'); await sleep(2800)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/L-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
