import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// frontend/ (this file is frontend/e2e/capture/redesign/<name>.mjs)
const FE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const { chromium } = createRequire(path.join(FE, 'package.json'))('playwright')

/**
 * Redesign 7c: Share (People, guest link minted, Embed, Schedule), Export
 * (PDF options, Excel, done, error, policy refusal) and Version history, on a
 * dashboard opened in the builder, × light / dark / Arabic / Arabic dark at
 * 1440 × 900. Browser-only data: grants and guest links (none are seeded),
 * versions, and the export responses. Usage: node cap_step7c.mjs <outdir>
 * [state] [reportId]; ONE=1 for light only.
 */

const BASE = 'http://localhost:3001'
const OUT = process.argv[2]
const only = process.argv[3]
const RID = Number(process.argv[4] ?? 1)
const VIEW = { width: 1440, height: 900 }
const themes = [['light', 'en', 'light'], ['dark', 'en', 'dark'], ['ar', 'ar', 'light'], ['ar-dark', 'ar', 'dark']]
  .filter(([s]) => !process.env.ONE || s === 'light')
const at = p => u => new URL(u).pathname === p
const ago = h => new Date(Date.now() - h * 3600000).toISOString()

const GRANTS = [{ id: 1, user_id: 2, email: 'sara.haddad@example.com', level: 'edit' }, { id: 2, user_id: 3, email: 'omar.khalil@example.com', level: 'view' }]
const LINKS = [{ id: 4, creator: 'admin@datalytics.local', created_at: ago(30), expires_at: ago(-24 * 6), active: true, pinned: false, access_count: 12, last_access_at: ago(2) }]
const VERSIONS = [
  { id: 30, revision: 14, created_at: ago(0.2), created_by: 'admin@datalytics.local', pages: 3, widgets: 12 },
  { id: 29, revision: 13, created_at: ago(2), created_by: 'sara.haddad@example.com', pages: 3, widgets: 12, via: 'copilot', note: 'Before the copilot added "Revenue by channel"' },
  { id: 28, revision: 12, created_at: ago(26), created_by: 'omar.khalil@example.com', pages: 3, widgets: 11 },
  { id: 27, revision: 11, created_at: ago(24 * 9), created_by: 'admin@datalytics.local', pages: 2, widgets: 8 },
]

const share = async p => { await p.getByRole('button', { name: /^(Share|مشاركة)$/ }).first().click(); await p.waitForTimeout(700) }
const exportOpen = async p => { await p.getByRole('button', { name: /^(Export|تصدير)$/ }).first().click(); await p.waitForTimeout(700) }
const screens = [
  { name: 'share-people', act: share },
  { name: 'share-guest', act: async p => { await share(p); await p.locator('.shx-dlg [data-testid=guest-links] .btn').last().click(); await p.waitForTimeout(500); await p.locator('.shx-b').evaluate(e => { e.scrollTop = e.scrollHeight }) } },
  { name: 'share-embed', act: async p => { await share(p); await p.locator('.shx-tab').nth(1).click() } },
  { name: 'share-schedule', act: async p => { await share(p); await p.locator('.shx-tab').nth(2).click() } },
  { name: 'export-pdf', act: exportOpen },
  { name: 'export-data', act: async p => { await exportOpen(p); await p.locator('.shx-fc').nth(1).click() } },
  { name: 'export-busy', fake: 'busy', act: async p => { await exportOpen(p); await p.locator('.shx-f .btn-primary').click() } },
  { name: 'export-done', fake: 'done', act: async p => { await exportOpen(p); await p.locator('.shx-f .btn-primary').click(); await p.waitForTimeout(600) } },
  { name: 'export-error', fake: 'error', act: async p => { await exportOpen(p); await p.locator('.shx-f .btn-primary').click(); await p.waitForTimeout(600) } },
  { name: 'export-blocked', fake: 'blocked', act: exportOpen },
  { name: 'versions', edit: true, act: async p => {
    await p.locator('.dl-panebar').getByRole('button', { name: /More|المزيد/ }).first().click().catch(() => {})
    await p.getByRole('menuitem', { name: /Version history|سجل الإصدارات/ }).click()
    await p.waitForTimeout(800); await p.locator('.shx-v').nth(1).click() } },
].filter(s => !only || s.name === only)

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

for (const sc of screens) for (const [suffix, lang, theme] of themes) {
  const ctx = await browser.newContext({ viewport: VIEW, storageState: state })
  await ctx.addInitScript(({ theme, lang }) => {
    localStorage.setItem('theme', theme)
    localStorage.setItem('datalytics.language', lang)
    localStorage.setItem('datalytics.direction', lang === 'ar' ? 'rtl' : 'ltr')
  }, { theme, lang })
  const page = await ctx.newPage()
  const errors = []
  page.on('console', m => { if (m.type() === 'error' && !/status of (500|401|403)/.test(m.text())) errors.push(m.text().slice(0, 140)) })
  page.on('pageerror', e => errors.push(String(e).slice(0, 140)))
  await page.route(at(`/api/v1/reports/${RID}/grants`), r => r.request().method() === 'GET' ? r.fulfill({ json: GRANTS }) : r.continue())
  await page.route(at(`/api/v1/reports/${RID}/share-links`), r => r.request().method() === 'GET' ? r.fulfill({ json: LINKS })
    : r.fulfill({ json: { id: 5, token: 'k3V9xQp2mN7aL0sW', expires_at: ago(-24 * 7), pinned: false, note: '' } }))
  await page.route(at(`/api/v1/reports/${RID}/versions`), r => r.fulfill({ json: VERSIONS }))
  // A dashboard the demo seed leaves without an author: presented as the
  // viewer's own so the author's controls show.
  await page.route(at(`/api/v1/reports/${RID}`), async r => {
    if (r.request().method() !== 'GET') return r.continue()
    const res = await r.fetch(); const body = await res.json()
    await r.fulfill({ json: { ...body, created_by: body.created_by ?? 1, is_mine: true, revision: 14 } })
  })
  if (sc.fake === 'busy') await page.route(at(`/api/v1/reports/${RID}/pdf`), () => { /* never answers */ })
  if (sc.fake === 'done') await page.route(at(`/api/v1/reports/${RID}/pdf`), r => r.fulfill({ body: '%PDF-1.4', contentType: 'application/pdf' }))
  if (sc.fake === 'error') await page.route(at(`/api/v1/reports/${RID}/pdf`), r => r.fulfill({ status: 503, json: { detail: 'The PDF renderer is not available on this server.' } }))
  if (sc.fake === 'blocked') await page.route(at('/api/v1/authz/decisions'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.decisions = body.decisions.map(d => d.action === 'download' ? { ...d, allowed: false, reason: 'Restricted data cannot be downloaded (export policy).' } : d)
    await r.fulfill({ json: body })
  })
  await page.goto(`${BASE}/reports/${RID}`)
  await page.waitForTimeout(3500)
  if (sc.edit) { await page.getByTestId('mode-toggle').click().catch(() => {}); await page.waitForTimeout(1200) }
  try { await sc.act(page) } catch (e) { errors.push('act: ' + String(e).slice(0, 120)) }
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(OUT, `${sc.name}-${suffix}.png`) })
  console.log(`${sc.name}-${suffix}`, errors.length ? 'CONSOLE: ' + errors.join(' | ') : 'clean')
  await ctx.close()
}
await browser.close()
