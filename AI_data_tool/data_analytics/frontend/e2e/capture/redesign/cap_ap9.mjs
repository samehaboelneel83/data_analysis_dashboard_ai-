import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 9 (i18n-2): the dataset page's tabs and panels, and the
 * shared components that held English (workspace tree, command palette,
 * share dialog). EN light and AR dark. Reads only.
 * Usage: node cap_ap9.mjs <outdir> [scene-prefix] (DATASET=1)
 */
const OUT = process.argv[2]
const only = process.argv[3]
const DID = process.env.DATASET ?? '1'
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const scenes = [
  { id: 'overview', url: `/datasets/${DID}` },
  { id: 'columns', url: `/datasets/${DID}?tab=columns` },
  { id: 'aggregates', url: `/datasets/${DID}?tab=aggregates` },
  { id: 'analysis', url: `/datasets/${DID}?tab=analysis`, wait: 12000 },
  { id: 'rules', url: `/datasets/${DID}?tab=rules` },
  { id: 'palette', url: '/', act: async p => { await p.keyboard.press('Control+k'); await sleep(700) } },
  { id: 'share', url: `/datasets/${DID}`, act: async p => { await p.getByRole('button', { name: /^(Share|مشاركة)/ }).first().click(); await sleep(800) } },
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
  let note = ''
  try {
    await page.goto(BASE + sc.url); await sleep(sc.wait ?? 3000)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/I-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
