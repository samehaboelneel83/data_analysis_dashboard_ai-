import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 10 Part A (Ask AI): the empty page, the picker open (and searched),
 * a dataset picked (a new thread: hero + suggestion cards), and History as an
 * overlay at 1024px -- EN/AR x light/dark. Reads only: no question is asked.
 * BASE=http://localhost:3011 serves the code before the change.
 * Usage: node cap_10a.mjs <outdir> [scene-prefix]
 */
const OUT = process.argv[2]
const only = process.argv[3]
const THEMES = [['en-light', 'en', 'light'], ['en-dark', 'en', 'dark'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const trigger = p => p.getByRole('button', { name: /What to ask about|ما الذي تسأل عنه|ماذا تسأل/ }).first()

const scenes = [
  { id: 'empty', url: '/ask' },
  { id: 'empty-1024', url: '/ask', view: { width: 1024, height: 768 } },
  { id: 'open', url: '/ask', act: async p => { await trigger(p).click(); await sleep(700) } },
  { id: 'search', url: '/ask', act: async p => {
    await trigger(p).click(); await sleep(500); await p.keyboard.type('dem'); await sleep(500) } },
  { id: 'picked', url: '/ask?dataset=1' },
  { id: 'picked-1024', url: '/ask?dataset=1', view: { width: 1024, height: 768 } },
  { id: 'history-1024', url: '/ask?dataset=1', view: { width: 1024, height: 768 }, act: async p => {
    await p.getByRole('button', { name: /^(History|Show history|السجل|إظهار السجل)$/ }).first().click(); await sleep(700) } },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: sc.view ?? { width: 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
    localStorage.setItem('datalytics.ask.recent', JSON.stringify(['d:1']))
  }, { theme, lang })
  const page = await ctx.newPage()
  let note = ''
  try {
    await page.goto(BASE + sc.url); await sleep(3500)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/A-${sc.id}-${suffix}.png` })
  console.log(BASE, suffix, sc.id, note)
  await ctx.close()
}
await browser.close()
