import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')
const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const VIEW = { width: 1440, height: 1000 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
const states = ['full', 'loading', 'error', 'empty', 'firstrun'].filter(s => !only || s === only)
const path1 = p => u => new URL(u).pathname === p

const browser = await chromium.launch()
const login = await browser.newContext({ viewport: VIEW })
const lp = await login.newPage()
await lp.goto(BASE + '/login')
await lp.getByLabel('Email', { exact: true }).fill('admin@datalytics.local')
await lp.getByLabel('Password', { exact: true }).fill('demo-password')
await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
await lp.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })
const state = await login.storageState()
await login.close()

for (const st of states) for (const [suffix, lang, theme] of themes) {
  const ctx = await browser.newContext({ viewport: VIEW, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => errors.push(String(e).slice(0, 140)))
  let url = `${BASE}/datasets/1`
  if (st === 'loading') await page.route(path1('/api/v1/datasets/1/analysis'), r => r.request().method() === 'GET'
    ? r.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"No analysis found"}' }) : undefined)
  if (st === 'error') await page.route(path1('/api/v1/datasets/1/analysis'), r => r.request().method() === 'GET'
    ? r.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"No analysis found"}' })
    : r.fulfill({ status: 504, contentType: 'application/json', body: '{"detail":"The analysis worker didn’t respond (timeout after 60 s)"}' }))
  if (st === 'empty') await page.route(path1('/api/v1/datasets/1'), async r => {
    if (r.request().method() !== 'GET') return r.continue()
    const res = await r.fetch(); const j = await res.json(); j.row_count = 0
    r.fulfill({ response: res, json: j })
  })
  if (st === 'firstrun') url = `${BASE}/datasets/7?new=1`
  await page.goto(url)
  await page.locator('[data-testid=overview-trust]').waitFor({ timeout: 30000 })
  const profileBtn = page.locator('[data-testid=overview-glance] button.btn').first()
  if (st === 'full') {
    await page.waitForTimeout(800)
    if (await page.locator('.dl-ov__glance').count() === 0 && await profileBtn.count()) await profileBtn.click()
    await page.locator('.dl-ov__glance').waitFor({ timeout: 90000 })
  }
  if (st === 'loading' || st === 'error') { await profileBtn.click(); await page.waitForTimeout(st === 'error' ? 1200 : 400) }
  if (st === 'firstrun') await page.locator('.dl-ov__glance').first().waitFor({ timeout: 90000 }).catch(() => {})
  await page.waitForTimeout(1500)
  await page.screenshot({ path: path.join(OUT, `overview-${st}-${suffix}.png`) })
  console.log(`${st}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
