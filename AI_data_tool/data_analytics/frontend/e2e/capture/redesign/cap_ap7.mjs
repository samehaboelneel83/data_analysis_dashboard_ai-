import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 7 (Connections): the list, a row's menu, a failing test,
 * empty and loading, the new-connection drawer (type, details), the edit
 * drawer, and the review page with its tabs. EN light and AR dark. Reads
 * only: the failing test, empty and loading are browser-only routes, and no
 * connection is created, changed or synced.
 * Usage: node cap_ap7.mjs <outdir> [scene-prefix]
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const scenes = [
  { id: 'list' },
  { id: 'menu', act: async p => { await p.locator('.dl-cn-acts [aria-haspopup="menu"]').first().click(); await sleep(500) } },
  { id: 'failing', test: true, act: async p => { await p.locator('.dl-cn-row').nth(1).hover(); await p.locator('.dl-cn-hover button').first().click(); await sleep(1200) } },
  { id: 'empty', route: [] },
  { id: 'loading', route: 'never' },
  { id: 'new-type', act: async p => { await p.locator('.dl-cn__head-acts .btn-primary').click(); await sleep(700) } },
  { id: 'new-details', act: async p => { await p.locator('.dl-cn__head-acts .btn-primary').click(); await sleep(500); await p.locator('.dl-cn-type').first().click(); await p.locator('.dl-cn-drawer__f .btn-primary').click(); await sleep(600) } },
  { id: 'edit', act: async p => { await p.locator('.dl-cn-acts [aria-haspopup="menu"]').first().click(); await sleep(300); await p.getByRole('menuitem', { name: /^(Edit|تعديل)/ }).click(); await sleep(700) } },
  { id: 'review', url: 'review' },
  { id: 'list-1024', view: { width: 1024, height: 768 } },
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
  if (sc.route) await page.route(at('/api/v1/data-sources'), r => (sc.route === 'never' ? undefined : r.fulfill({ json: sc.route })))
  if (sc.test) await page.route(u => /\/api\/v1\/data-sources\/\d+\/test$/.test(new URL(u).pathname),
    r => r.fulfill({ json: { ok: false, error: 'could not translate host name "qa-db.invalid" to address: Name or service not known' } }))
  let note = ''
  try {
    if (sc.url === 'review') {
      await page.goto(BASE + '/connections'); await sleep(2000)
      const href = await page.locator('.dl-cn-open').first().getAttribute('href')
      await page.goto(BASE + href); await sleep(3000)
    } else { await page.goto(BASE + '/connections'); await sleep(2500) }
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/C-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
