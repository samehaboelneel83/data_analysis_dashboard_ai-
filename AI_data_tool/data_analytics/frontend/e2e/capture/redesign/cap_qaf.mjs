import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * FIX-QAF: the screens the final-QA fixes touched, EN light and AR dark at
 * 1440 (the Dashboards toolbar also at 1180). Reads only: the AI answers and
 * the never-ending ask are faked in the browser, and nothing is created.
 * Usage: node cap_qaf.mjs <outdir> [scene-prefix] (DATASET=1 LIVE=6 REPORT=1)
 */
const OUT = process.argv[2]
const only = process.argv[3]
const DID = process.env.DATASET ?? '1', LIVE = process.env.LIVE ?? '6', RID = process.env.REPORT ?? '1'
const THEMES = [['en-light', 'en', 'light'], ['ar-dark', 'ar', 'dark']]
const ANSWER = {
  run_id: 999999, status: 'ok', intent: 'query', error: null,
  answer: 'Asia Pacific has the highest revenue at 2,221,091.66.',
  results: [{ step: 's1', columns: ['region', 'revenue'], rows: [['Asia Pacific', 2221091.66]], total: 1 }],
  presentation: { format: 'table', limit: null },
}
const askText = async (p, q) => {
  const box = p.getByRole('textbox').last()
  await box.fill(q); await box.press('Enter'); await sleep(1500)
}
const scenes = [
  { id: 'connections', url: '/connections' },
  { id: 'conn-step2', url: '/connections', act: async p => {
    await p.getByRole('button', { name: /New Connection|اتصال جديد/ }).first().click(); await sleep(600)
    await p.getByRole('button', { name: /^(Next|التالي)/ }).first().click(); await sleep(800) } },
  { id: 'dashboards', url: '/reports' },
  { id: 'dashboards-1180', url: '/reports', w: 1180 },
  { id: 'home', url: '/' },
  { id: 'ask-stop', url: `/ask?dataset=${DID}`, fake: 'hang', act: async p => { await sleep(1500); await askText(p, 'Total units by channel'); await sleep(2000) } },
  { id: 'panel-answer', url: `/reports/${RID}`, fake: 'answer', act: async p => {
    await p.getByTestId('view-ai-open').click(); await sleep(1200)
    await askText(p, 'Which region has the highest revenue?'); await sleep(1500)
    const rows = p.getByRole('button', { name: /Show rows|عرض الصفوف/ }).first()
    if (await rows.count()) { await rows.click(); await sleep(500) } } },
  { id: 'lineage-focus', url: `/lineage?focus=ds:${DID}`, wait: 4500 },
  { id: 'lineage-list', url: `/lineage?focus=ds:${DID}`, act: async p => {
    await p.getByRole('radio', { name: /^(List|قائمة)/ }).first().click(); await sleep(800) } },
  { id: 'datasets-preview', url: '/datasets', act: async p => {
    await p.getByRole('row', { name: /Live Orders/ }).first().click(); await sleep(2500) } },
  { id: 'overview', url: `/datasets/${DID}` },
  { id: 'analysis', url: `/datasets/${DID}?tab=analysis`, wait: 12000 },
  { id: 'models', url: `/datasets/${DID}?tab=models` },
  { id: 'upload-review', url: '/upload', act: async p => {
    const csv = 'region,city,revenue\nEurope,Paris,120\nMiddle East,القاهرة,95\nAsia,Tokyo,210\n'
    await p.locator('input[type=file]').first().setInputFiles({ name: 'QAF-upload.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
    await sleep(1500) } },
  { id: 'sso', url: '/admin/sso' },
  { id: 'audit', url: '/admin/audit' },
  { id: 'platform', url: '/platform/settings' },
].filter(s => !only || s.id.startsWith(only))

const browser = await chromium.launch()
const state = await signIn(browser)
for (const sc of scenes) for (const [suffix, lang, theme] of THEMES) {
  const ctx = await browser.newContext({ viewport: { width: sc.w ?? 1440, height: 900 }, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(String(e).slice(0, 160)))
  if (sc.fake) {
    // Never a real thread or run: creating answers a scratch id, asking is faked.
    await page.route(u => /\/agent\/conversations$/.test(new URL(u).pathname), r =>
      r.request().method() === 'POST' ? r.fulfill({ json: { id: 999999, title: 'New conversation' } }) : r.continue())
    await page.route(u => /\/agent\/conversations\/\d+\/ask$/.test(new URL(u).pathname), r =>
      sc.fake === 'hang' ? undefined : r.fulfill({ json: ANSWER }))
  }
  let note = ''
  try {
    await page.goto(BASE + sc.url); await sleep(sc.wait ?? 3000)
    if (sc.act) await sc.act(page)
  } catch (e) { note = 'FAILED ' + String(e).split('\n')[0] }
  await page.screenshot({ path: `${OUT}/Q-${sc.id}-${suffix}.png` })
  console.log(suffix, sc.id, note, errors.join(' | '))
  await ctx.close()
}
await browser.close()
