import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Step 10, the robot (the port of design-handoff-3/ask-ai/robot): the picture
 * alone at 2x, EN/AR x light/dark, on the empty page and in the step-2 hero,
 * with frames of typing, thinking, happy, error and sleep, a strip of the
 * idle routine, and the picture under prefers-reduced-motion. The whole-page
 * captures (1440 and 1024) are cap_10a.mjs's `empty` and `picked`.
 * Reads only: no question is asked.
 *
 *  - Typing and sleep are real: keys in the text box, and 20s of leaving the
 *    page alone.
 *  - Thinking, happy and error go through the page's own robot store
 *    (robotMood.ts, imported from the dev server), because the hero leaves
 *    the page when a question is sent.
 *  - The model endpoints are faked as up in the browser, so the question box
 *    is not locked.
 * Usage: node cap_10robot.mjs <outdir> [quick|step2]
 */
const OUT = process.argv[2]
const quick = process.argv[3] === 'quick'
const step2Only = process.argv[3] === 'step2'
const THEMES = [['en-light', 'en', 'light'], ['en-dark', 'en', 'dark'], ['ar-light', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter((_, i) => !quick || i === 0 || i === 3)

const browser = await chromium.launch()
const state = await signIn(browser)
const open = async (lang, theme, url, extra = {}) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state, deviceScaleFactor: 2, ...extra })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme); localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  page.on('pageerror', e => console.log('PAGE ERROR', String(e).slice(0, 200)))
  await page.route(u => u.pathname.endsWith('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: true } }))
    body.auto_pick = body.endpoints[0]?.id ?? null
    await r.fulfill({ response: res, json: body })
  })
  await page.goto(BASE + url); await page.waitForSelector('.dl-ill'); await sleep(1500)
  return { ctx, page, ill: page.locator('.dl-ill').first() }
}
// The store module exactly as the page loaded it (the dev server may add a
// version query; another URL would be another, unconnected copy).
const signal = async (page, what) => {
  await page.evaluate(async w => {
    const loaded = performance.getEntriesByType('resource').map(r => new URL(r.name)).find(u => u.pathname.endsWith('/ask/robotMood.ts'))
    ;(await import(loaded.pathname + loaded.search)).signalRobot(w)
  }, what)
}
const shown = page => page.evaluate(() => document.querySelector('.dl-bot').dataset.state)
// The picture with room around it: confetti, the "?" and the Zzz leave its box.
const shot = async (page, ill, name, pad = 30) => {
  const b = await ill.boundingBox()
  await page.screenshot({ path: `${OUT}/${name}.png`, clip: { x: b.x - pad, y: b.y - pad, width: b.width + 2 * pad, height: b.height + 2 * pad } })
}

for (const [suffix, lang, theme] of THEMES) {
  let ctx, page, ill
  if (!step2Only) {
  // The empty page: the full stage.
  ;({ ctx, page, ill } = await open(lang, theme, '/ask'))
  await shot(page, ill, `robot-empty-${suffix}`)
  await page.locator('.dl-pick__search input').pressSequentially('dem', { delay: 120 }); await sleep(600)
  await shot(page, ill, `robot-empty-typing-${suffix}`)
  await page.locator('.dl-pick__search input').fill(''); await page.locator('.dl-pick__search input').blur()
  await signal(page, 'running'); await sleep(900)
  await shot(page, ill, `robot-empty-thinking-${suffix}`); console.log(suffix, 'running:', await shown(page))
  await signal(page, 'answer'); await sleep(350)
  await shot(page, ill, `robot-empty-happy-${suffix}`, 90)
  await sleep(3600)
  await signal(page, 'running'); await signal(page, 'error'); await sleep(1300)
  await shot(page, ill, `robot-empty-error-${suffix}`)
  await sleep(2600); console.log(suffix, 'back to', await shown(page))
  await sleep(20500) // left alone: it falls asleep
  await shot(page, ill, `robot-empty-sleep-${suffix}`); console.log(suffix, 'after 20s:', await shown(page))
  await ctx.close()
  }

  // Step 2: the robot alone; typing in the question box, thinking, sleep.
  ;({ ctx, page, ill } = await open(lang, theme, '/ask?dataset=1'))
  await shot(page, ill, `robot-step2-${suffix}`)
  await page.locator('.dl-chat__composer textarea').pressSequentially('total', { delay: 120 }); await sleep(600)
  await shot(page, ill, `robot-step2-typing-${suffix}`); console.log(suffix, 'step 2, typing:', await shown(page))
  await page.reload(); await page.waitForSelector('.dl-ill'); await sleep(1500) // an empty, unfocused box again
  await signal(page, 'running'); await sleep(900)
  await shot(page, ill, `robot-step2-thinking-${suffix}`)
  await signal(page, 'rest'); await sleep(21000)
  await shot(page, ill, `robot-step2-sleep-${suffix}`); console.log(suffix, 'step 2, after 20s:', await shown(page))
  await ctx.close()
}

// Frames, EN light: a reaction from start to end, then the wake-up.
if (!step2Only) {
  const { ctx, page, ill } = await open('en', 'light', '/ask')
  for (const [name, signals, times] of [
    ['thinking', ['running'], [200, 700, 1200, 1700]],
    ['happy', ['answer'], [150, 450, 900, 1500, 2600, 3800]],
    ['error', ['running', 'error'], [200, 600, 1100, 2500, 3800]],
  ]) {
    for (const s of signals) await signal(page, s)
    const t0 = Date.now()
    for (const [i, at] of times.entries()) {
      await sleep(Math.max(0, t0 + at - Date.now())); await shot(page, ill, `frames-${name}-${i}`, 90)
    }
  }
  await sleep(20500)
  for (const i of [0, 1, 2]) { await shot(page, ill, `frames-sleep-${i}`, 90); await sleep(800) }
  await page.mouse.move(700, 500); await sleep(250); await shot(page, ill, 'frames-wake-0', 90)
  await sleep(900); await shot(page, ill, 'frames-wake-1', 90)

  // The idle routine: the pointer keeps it awake; one frame every 500ms for 30s.
  const moves = new Set()
  for (let i = 0; i < 60; i++) {
    await page.mouse.move(300 + (i % 2) * 4, 880); await sleep(500)
    const act = await page.evaluate(() => document.querySelector('.dl-bot').dataset.act)
    if (act) moves.add(act)
    await shot(page, ill, `idle-${String(i).padStart(2, '0')}`)
  }
  console.log('idle routine, moves seen in 30s:', [...moves].join(', ') || 'none')
  // A click on the robot: a spin or a jump, with sparks.
  await page.locator('.dl-bot').click(); await sleep(200)
  console.log('click:', await page.evaluate(() => document.querySelector('.dl-bot').dataset.act), 'sparks:', await page.locator('.dl-ill__fx b').count())
  await shot(page, ill, 'frames-click', 90)
  await ctx.close()
}

// Reduced motion: two captures 2.5s apart are the same picture; no packets.
if (!step2Only) {
  const { ctx, page, ill } = await open('en', 'light', '/ask', { reducedMotion: 'reduce' })
  const a = await ill.screenshot({ path: `${OUT}/reduced-0.png` }); await sleep(2500)
  const b = await ill.screenshot({ path: `${OUT}/reduced-1.png` })
  console.log('reduced motion: still =', a.equals(b), '| packets:', await page.locator('.dl-ill__pkt').count(), '| button:', await page.locator('button.dl-bot').count())
  await ctx.close()
}
await browser.close()
