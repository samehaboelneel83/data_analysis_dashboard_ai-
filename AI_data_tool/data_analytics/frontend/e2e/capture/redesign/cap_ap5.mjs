import path from 'node:path'
import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 5 (Upload): the landing, drag-over, the review of one file
 * (with a date warning) and of three (combine on), importing, success and
 * error, EN light and AR dark. Browser-only: the uploads are answered by
 * Playwright routes, so nothing is saved. Files come from <fixtures>.
 * Usage: node cap_ap5.mjs <outdir> <fixtures> [scene-prefix]
 */
const [OUT, FX, only] = process.argv.slice(2)
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const at = p => u => new URL(u).pathname === p
const one = [path.join(FX, 'enrolments_2025.csv')]
const many = ['sales_2026_q1.csv', 'sales_2026_q2.csv', 'regions.xlsx'].map(f => path.join(FX, f))
const DS = { id: 9001, name: 'Enrolments 2025', row_count: 240, col_count: 6, file_size: 16300, filename: 'enrolments_2025.csv', columns: [] }
const pick = async (p, files) => { await p.locator('input[type=file]').setInputFiles(files); await sleep(900) }
const go = async p => { await p.getByRole('button', { name: /^(Import|استيراد)/ }).last().click() }
const scenes = [
  { id: 'landing' },
  { id: 'dragover', act: async p => {
    const dt = await p.evaluateHandle(() => new DataTransfer())
    await p.locator('.dl-up-drop, .dl-dropzone').first().dispatchEvent('dragover', { dataTransfer: dt }); await sleep(400) } },
  { id: 'review1', act: async p => pick(p, one) },
  { id: 'reviewN', act: async p => { await pick(p, many); const c = p.getByRole('switch'); if (await c.count()) { await c.click(); await sleep(300) } } },
  { id: 'importing', reply: 'never', act: async p => { await pick(p, one); await go(p); await sleep(1500) } },
  { id: 'success', reply: 'ok', act: async p => { await pick(p, one); await go(p); await sleep(1800) } },
  { id: 'error', reply: 'fail', act: async p => { await pick(p, one); await go(p); await sleep(1500) } },
  { id: 'review1-1024', view: { width: 1024, height: 768 }, act: async p => pick(p, one) },
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
  // Every upload is answered here; none reaches the server.
  await page.route(u => /\/api\/v1\/datasets(\/batch)?$/.test(new URL(u).pathname), async r => {
    if (r.request().method() !== 'POST') return r.continue()
    if (sc.reply === 'never') return
    await sleep(600)
    if (sc.reply === 'fail') return r.fulfill({ status: 400, json: { detail: 'Could not parse enrolments_2025.csv: line 241 has 7 fields, expected 6' } })
    return r.fulfill({ json: DS })
  })
  let note = ''
  try {
    await page.goto(BASE + '/upload'); await sleep(2200)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/U-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
