// Screenshots of the sign-in page for design review: desktop + mobile, English + Arabic,
// light + dark. Nothing is submitted and nobody signs in.
//
//   node frontend/e2e/demo/auth_screens.mjs [before|after]
// Output: <data_analytics>/demo_output/auth_redesign/<phase>/*.png
// (run_auth_screens.cmd picks "before" the first time and "after" once that exists.)

import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.DEMO_PW_DIR
  ? path.join(process.env.DEMO_PW_DIR, 'node_modules', 'playwright')
  : 'playwright')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..', '..', '..')
const BASE = (process.env.DEMO_BASE_URL || 'http://localhost:3001').replace(/\/$/, '')
const phase = process.argv[2] || 'after'
const OUT = path.join(ROOT, 'demo_output', 'auth_redesign', phase)
fs.mkdirSync(OUT, { recursive: true })

async function launch() {
  for (const extra of [{}, { channel: 'msedge' }, { channel: 'chrome' }]) {
    try { return await chromium.launch({ ...extra }) } catch (e) { console.log('launch failed:', e.message.split('\n')[0]) }
  }
  throw new Error('no browser')
}

const views = [
  { name: 'login_desktop_en', w: 1440, h: 900, lang: 'en', theme: 'light' },
  { name: 'login_desktop_ar', w: 1440, h: 900, lang: 'ar', theme: 'light' },
  { name: 'login_mobile_en', w: 390, h: 844, lang: 'en', theme: 'light', mobile: true },
  { name: 'login_mobile_ar', w: 390, h: 844, lang: 'ar', theme: 'light', mobile: true },
  { name: 'login_desktop_en_dark', w: 1440, h: 900, lang: 'en', theme: 'dark' },
  { name: 'login_desktop_ar_dark', w: 1440, h: 900, lang: 'ar', theme: 'dark' },
  { name: 'login_mobile_en_dark', w: 390, h: 844, lang: 'en', theme: 'dark', mobile: true },
  { name: 'login_mobile_ar_dark', w: 390, h: 844, lang: 'ar', theme: 'dark', mobile: true },
]

const browser = await launch()
try {
  for (const v of views) {
    const ctx = await browser.newContext({
      viewport: { width: v.w, height: v.h },
      deviceScaleFactor: v.mobile ? 2 : 1,
      isMobile: !!v.mobile, hasTouch: !!v.mobile,
      // Screenshots show the finished (static) state of any animation.
      reducedMotion: 'reduce',
    })
    await ctx.addInitScript(([lang, theme]) => {
      localStorage.setItem('datalytics.language', lang)
      localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
      localStorage.setItem('theme', theme)
    }, [v.lang, v.theme])
    const page = await ctx.newPage()
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' }).catch(() => {})
    await page.waitForTimeout(1200)
    await page.screenshot({ path: path.join(OUT, `${v.name}.png`), fullPage: true })

    // One extra state per language on desktop light: the inline validation after an empty submit.
    if (!v.mobile && v.theme === 'light') {
      const submit = page.locator('button[type=submit]').first()
      if (await submit.isVisible().catch(() => false)) {
        await submit.click().catch(() => {})
        await page.waitForTimeout(800)
        await page.screenshot({ path: path.join(OUT, `${v.name}_validation.png`), fullPage: true })
      }
    }
    console.log('saved', v.name)
    await ctx.close()
  }
} finally {
  await browser.close()
}
console.log('done ->', OUT)
