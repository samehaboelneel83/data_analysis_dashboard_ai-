import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 8-i18n: the pages translated in this step, in Arabic (light, dark) and
 * in English light (which must be unchanged). Reads only.
 * Usage: node cap_8i18n.mjs <outdir> [page-name-prefix]; ONLY=<theme>.
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(t => !process.env.ONLY || t[0] === process.env.ONLY)

const tab = name => async p => { await p.getByRole('tab', { name }).or(p.getByRole('button', { name })).first().click(); await sleep(2500) }

const PAGES = [
  ['activity', '/monitoring/activity'],
  ['glossary', '/glossary'],
  ['connections', '/connections'],
  ['source-review', '/connections/1/review'],
  ['organizations', '/platform/organizations'],
  ['platform-settings', '/platform/settings'],
  ['admin-settings', '/admin/settings'],
  ['api-keys', '/admin/api-keys'],
  ['org-units', '/admin/org-units'],
  ['maps', '/admin/maps'],
  ['sso', '/admin/sso'],
  ['users', '/admin/users'],
  ['roles', '/admin/roles'],
  ['row-security', '/admin/row-security-rules'],
  ['column-security', '/admin/column-security-rules'],
  ['connection-rules', '/admin/connection-rules'],
  ['custom-connectors', '/admin/custom-connectors'],
  ['export-policy', '/admin/export-policy'],
  ['dataset-models', '/datasets/1', tab(/^(Models|النماذج)$/)],
  ['dashboards-list', '/reports'],
].filter(([n]) => !only || n.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const [name, url, act] of PAGES) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  let note = ''
  try {
    await page.goto(BASE + url); await sleep(4000)
    if (act) await act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/${name}-${suffix}.png` })
  console.log(BASE, suffix, name, note)
  await ctx.close()
}
await browser.close()
