// Frontend fetch-waterfall benchmark: counts /widget-data requests and times
// page settle for the demo report, then measures the two refetch storms the
// perf plan attacks — Report→Data→Report and page flips.
//
// Run from the repo root (Playwright resolves from frontend/):
//   node frontend/scripts/bench_pageload.mjs <report-url> <storage-state.json>
import { createRequire } from 'module'
const require = createRequire('file:///D:/data_analytics/frontend/')
const { chromium } = require('playwright')

const reportUrl = process.argv[2] || 'http://localhost:3000/reports/85'
const authState = process.argv[3]

const browser = await chromium.launch({ args: ['--no-sandbox'] })
const ctx = await browser.newContext({
  viewport: { width: 1700, height: 1000 },
  ...(authState ? { storageState: authState } : {}),
})
const page = await ctx.newPage()

let widgetPosts = 0
let inFlight = 0
let maxConcurrent = 0
page.on('request', r => {
  if (r.url().includes('/widget-data') && r.method() === 'POST') {
    widgetPosts += 1
    inFlight += 1
    maxConcurrent = Math.max(maxConcurrent, inFlight)
  }
})
page.on('requestfinished', r => {
  if (r.url().includes('/widget-data') && r.method() === 'POST') inFlight -= 1
})
page.on('requestfailed', r => {
  if (r.url().includes('/widget-data') && r.method() === 'POST') inFlight -= 1
})

const settle = async () => {
  // networkidle plus a grace period: text widgets fire follow-up KPI queries
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(1500)
}

const t0 = Date.now()
await page.goto(reportUrl)
await settle()
const initial = { widgetPosts, maxConcurrent, settleMs: Date.now() - t0 }

// Report -> Data -> Report
widgetPosts = 0; maxConcurrent = 0
const strip = page.getByTestId('view-strip')
if (await strip.count()) {
  await strip.getByRole('button', { name: /Data/ }).click()
  await page.waitForTimeout(1200)
  await strip.getByRole('button', { name: /Report/ }).click()
  await settle()
}
const tabRoundtrip = { widgetPosts, maxConcurrent }

// Page flip there-and-back (first two page tabs if present)
widgetPosts = 0; maxConcurrent = 0
const pageA = process.argv[4] || 'Page 1'
const pageB = process.argv[5] || 'Profit & Margin'
const tabB = page.getByRole('button', { name: pageB }).first()
if (await tabB.count()) {
  await tabB.click()
  await settle()
  await page.getByRole('button', { name: pageA }).first().click()
  await settle()
}
const pageFlip = { widgetPosts, maxConcurrent }

console.log(JSON.stringify({ initial, tabRoundtrip, pageFlip }, null, 2))
await browser.close()
