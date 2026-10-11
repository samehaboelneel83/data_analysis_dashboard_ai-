import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 10, the robot: the picture alone (2x), EN/AR x light/dark, on the
 * empty page and in the step-2 hero; its reactions; one frame every 400ms of
 * the idle loop (12s: float, blink, glances, the wave); and the picture under
 * prefers-reduced-motion. The whole-page captures are cap_10a.mjs's `empty`
 * and `picked`. Reads only: no question is asked.
 *
 * Typing is real (keys in the chooser's search box and in the question box;
 * the model endpoints are faked as up in the browser so the box is not locked).
 * Thinking, happy and error are set on the robot's `data-mood` directly: the
 * hero leaves the page when a question is sent, so they cannot be reached by
 * asking one.
 * Usage: node cap_10robot.mjs <outdir>
 */
const OUT = process.argv[2]
const THEMES = [['en-light', 'en', 'light'], ['en-dark', 'en', 'dark'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]

const browser = await chromium.launch()
const state = await signIn(browser)
const open = async (lang, theme, url, extra = {}) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state, deviceScaleFactor: 2, ...extra })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  // The model server is down on this machine, which locks the question box.
  // Browser-only: the endpoints read as up, so the box can be typed in.
  await page.route(u => u.pathname.endsWith('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: true } }))
    await r.fulfill({ response: res, json: body })
  })
  await page.goto(BASE + url); await page.waitForSelector('.dl-ill'); await sleep(1500)
  return { ctx, page, ill: page.locator('.dl-ill').first() }
}
const force = (page, mood) => page.evaluate(m => document.querySelector('.dl-bot').setAttribute('data-mood', m), mood)

for (const [suffix, lang, theme] of THEMES) {
  // The empty page: the picture, then looking at the chooser while typing.
  let { ctx, page, ill } = await open(lang, theme, '/ask')
  await ill.screenshot({ path: `${OUT}/robot-empty-${suffix}.png` })
  await page.locator('.dl-pick__search input').pressSequentially('dem', { delay: 120 }); await sleep(500)
  await ill.screenshot({ path: `${OUT}/robot-empty-typing-${suffix}.png` })
  for (const mood of ['thinking', 'happy', 'error']) {
    await force(page, mood); await sleep(mood === 'happy' ? 1500 : 900)
    await ill.screenshot({ path: `${OUT}/robot-empty-${mood}-${suffix}.png` })
  }
  await ctx.close()

  // Step 2: the small robot, then looking down at the question box.
  ;({ ctx, page, ill } = await open(lang, theme, '/ask?dataset=1'))
  await ill.screenshot({ path: `${OUT}/robot-step2-${suffix}.png` })
  await page.locator('.dl-chat__composer textarea').pressSequentially('total', { delay: 120 }); await sleep(500)
  await ill.screenshot({ path: `${OUT}/robot-step2-typing-${suffix}.png` })
  await ctx.close()
  console.log(BASE, suffix)
}

// The idle loop, one frame every 400ms for 12s.
{
  const { ctx, page, ill } = await open('en', 'light', '/ask')
  const t0 = Date.now()
  for (let i = 0; i < 30; i++) {
    const wait = t0 + i * 400 - Date.now()
    if (wait > 0) await sleep(wait)
    await ill.screenshot({ path: `${OUT}/idle-${String(i).padStart(2, '0')}.png` })
  }
  await ctx.close()
  console.log('idle loop: 30 frames')
}

// Reduced motion: two captures 2.5s apart must be the same picture.
{
  const { ctx, ill } = await open('en', 'light', '/ask', { reducedMotion: 'reduce' })
  const a = await ill.screenshot({ path: `${OUT}/reduced-0.png` }); await sleep(2500)
  const b = await ill.screenshot({ path: `${OUT}/reduced-1.png` })
  console.log('reduced motion: still =', a.equals(b))
  await ctx.close()
}
await browser.close()
