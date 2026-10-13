import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 6: the floating Ask AI button on a dashboard in View --
 * at rest, hovered (the pill and its tooltip), quiet while scrolling, dragged
 * to the top start, open (the page's panel), and hidden in Present. EN light
 * and AR dark. Reads only; the corner is this browser's.
 * Usage: node cap_ap6.mjs <outdir> [report-id]
 */
const OUT = process.argv[2]
const RID = process.argv[3] ?? '5'
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const fab = p => p.getByTestId('view-ai-open')
const scenes = [
  { id: 'rest' },
  { id: 'hover', act: async p => { await fab(p).hover(); await sleep(500) } },
  { id: 'quiet', act: async p => { await p.mouse.move(700, 450); await p.evaluate(() => { const s = [...document.querySelectorAll('*')].find(e => e.scrollHeight > e.clientHeight + 20 && getComputedStyle(e).overflowY !== 'visible' && e.closest('main')); s && (s.scrollTop += 120) }); await sleep(150) } },
  { id: 'dragged', act: async p => { const b = await fab(p).boundingBox(); await p.mouse.move(b.x + 28, b.y + 28); await p.mouse.down(); await p.mouse.move(400, 200, { steps: 8 }); await p.mouse.up(); await sleep(500) } },
  { id: 'open', act: async p => { await fab(p).click(); await sleep(1200) } },
  { id: 'present', act: async p => { await p.keyboard.press('Escape'); const b = p.getByRole('button', { name: /^(Present|عرض تقديمي)/ }).first(); if (await b.count()) { await b.click(); await sleep(1200) } } },
]
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
    await page.goto(`${BASE}/reports/${RID}`); await sleep(3500)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/F-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '), sc.id === 'present' ? `fab visible: ${await fab(page).count()}` : '')
  await ctx.close()
}
await browser.close()
