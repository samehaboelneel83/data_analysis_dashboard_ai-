import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
export const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')
export const BASE = process.env.BASE ?? 'http://localhost:3001'
export const sleep = ms => new Promise(r => setTimeout(r, ms))
export const VIEW = { width: 1440, height: 900 }
export const THEMES = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]

export async function signIn(browser) {
  const login = await browser.newContext({ viewport: VIEW })
  const lp = await login.newPage()
  await lp.goto(BASE + '/login')
  await lp.getByLabel('Email', { exact: true }).fill('admin@datalytics.local')
  await lp.getByLabel('Password', { exact: true }).fill('demo-password')
  await lp.getByRole('button', { name: 'Sign In', exact: true }).click()
  await lp.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 })
  const state = await login.storageState()
  await login.close()
  return state
}

export async function openPage(browser, state, [suffix, lang, theme], url, view = VIEW) {
  const ctx = await browser.newContext({ viewport: view, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  page.errors = []
  page.on('pageerror', e => page.errors.push(String(e).slice(0, 160)))
  await page.goto(BASE + url)
  return { ctx, page }
}
