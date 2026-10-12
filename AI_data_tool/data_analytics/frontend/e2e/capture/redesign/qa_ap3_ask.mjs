import { chromium, signIn, sleep, BASE } from './_qa3_lib.mjs'

/**
 * Autopilot step 3: a self-QA pass over Ask AI. Each flow is run and checked;
 * the result is one line per check (PASS / FAIL) and a screenshot per flow.
 * Model answers are faked in the browser (Playwright routes); the History
 * check makes one scratch conversation through the API ("AP3 scratch"),
 * renames and deletes it through the page, and removes it if anything fails.
 * Usage: node qa_ap3_ask.mjs <outdir>
 */
const OUT = process.argv[2]
const API = process.env.API ?? 'http://localhost:8000/api/v1'
const at = p => u => new URL(u).pathname === p
const results = []
const check = (name, ok, info = '') => { results.push(ok); console.log(ok ? 'PASS' : 'FAIL', name, info) }

const tok = await fetch(API + '/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'admin@datalytics.local', password: 'demo-password' }) }).then(r => r.json()).then(d => d.access_token)
const api = (m, p, d) => fetch(API + p, { method: m, headers: { Authorization: 'Bearer ' + tok, 'content-type': 'application/json' },
  body: d ? JSON.stringify(d) : undefined }).then(r => r.status === 204 ? null : r.json())

const BAR = { run_id: 701, status: 'ok', intent: 'aggregate', error: null, answer: '**Asia Pacific** leads with 2,348,914 in revenue.',
  results: [{ step: 'q1', columns: ['region', 'revenue'], total: 3, truncated: false, rows: [['Asia Pacific', 2348914], ['Europe', 2219630], ['Americas', 1882846]] }],
  sql: ['SELECT region, SUM(revenue) AS revenue FROM "Demo — Sales" GROUP BY region'], presentation: { format: 'bar', limit: null, x: 'region', y: 'revenue' },
  context_objects: null, evidence: null }
const FAILED = { run_id: 702, status: 'failed', intent: null, answer: null, results: [], sql: [], presentation: null, context_objects: null,
  error: 'Binder Error: Referenced column "rep" not found' }

const browser = await chromium.launch()
const state = await signIn(browser)
async function open(url, { ask, convs, endpointsUp = true } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state, permissions: ['clipboard-read', 'clipboard-write'] })
  await ctx.addInitScript(() => { localStorage.setItem('theme', 'light'); localStorage.setItem('datalytics.language', 'en'); localStorage.setItem('datalytics.direction', 'ltr') })
  const page = await ctx.newPage()
  page.errors = []
  page.on('pageerror', e => page.errors.push(String(e).slice(0, 160)))
  page.on('console', m => { if (m.type() === 'error') page.errors.push(m.text().slice(0, 160)) })
  if (endpointsUp) await page.route(at('/api/v1/llm/endpoints'), async r => {
    const res = await r.fetch(); const body = await res.json()
    body.endpoints = (body.endpoints || []).map(e => ({ ...e, enabled: true, status: { ok: true } })); body.auto_pick = body.endpoints[0]?.id ?? null
    await r.fulfill({ response: res, json: body })
  })
  if (convs) await page.route(at('/api/v1/agent/conversations'), r => r.request().method() === 'GET' ? r.fulfill({ json: convs })
    : r.fulfill({ json: { id: 510, title: 'New conversation' } }))
  if (ask) await page.route(at('/api/v1/agent/conversations/510/ask'), ask)
  await page.route(u => /\/api\/v1\/agent\/runs\/\d+$/.test(new URL(u).pathname), r => r.fulfill({ json: { ms: 1400, steps: [], context_objects: null } }))
  await page.goto(BASE + url); await sleep(2500)
  return { ctx, page }
}
const shot = (p, n) => p.screenshot({ path: `${OUT}/${n}.png` })
const botState = p => p.locator('.dl-bot').first().getAttribute('data-state')
const box = p => p.getByRole('textbox', { name: 'Your question' })

// 1. Empty state: search, tabs, keyboard, Upload dataset, "/" shortcut.
{
  const { ctx, page } = await open('/ask')
  const search = page.getByRole('combobox')
  await page.keyboard.press('/'); check('empty: "/" focuses the search', await search.evaluate(e => e === document.activeElement))
  await search.fill('sales'); await sleep(300)
  const names = await page.locator('.dl-pick__opt-name').allTextContents()
  check('empty: search narrows the list', names.length > 0 && names.every(n => /sales/i.test(n)), names.join(' | '))
  await search.fill('')
  const tabs = page.getByRole('tab')
  if (await tabs.count()) {
    await page.getByRole('tab', { name: /^Connections/ }).click(); await sleep(300)
    const kinds = await page.locator('.dl-pick__opt .dl-pick__mode').allTextContents()
    check('empty: Connections tab shows only connections', kinds.length > 0 && kinds.every(k => k === 'Live'), kinds.join(','))
    await page.getByRole('tab', { name: /^All/ }).click()
  }
  check('empty: Upload dataset links to /upload', (await page.getByRole('link', { name: 'Upload dataset' }).getAttribute('href')) === '/upload')
  await search.focus(); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter'); await sleep(1500)
  check('empty: keyboard picks a row and opens step 2', /\/ask\?(dataset|source)=/.test(page.url()), page.url())
  check('step 2: suggestion cards or the hero are shown', await page.locator('.dl-sug__card, .dl-hero--sm').first().isVisible())
  await shot(page, '1-empty-then-step2')
  check('empty: no console errors', page.errors.length === 0, page.errors.join(' | '))
  await ctx.close()
}

// 2. Loading, then the answer and its actions; robot states on the way.
{
  let asks = 0, release
  const gate = new Promise(r => { release = r })
  const { ctx, page } = await open('/ask?dataset=1', { convs: [], ask: async r => { asks++; if (asks === 1) await gate; else await sleep(400); await r.fulfill({ json: BAR }) } })
  await box(page).focus(); await sleep(300)
  check('robot: typing while the box has focus', (await botState(page)) === 'typing')
  await box(page).fill('Total revenue by region'); await page.keyboard.press('Enter'); await sleep(800)
  check('loading: the loading card shows', await page.getByTestId('loading-card').isVisible())
  check('loading: the head thinks', (await page.locator('.dl-bot--head').last().getAttribute('data-state')) === 'thinking')
  await sleep(1500)
  check('loading: elapsed time counts', /[1-9]\s?s/.test(await page.locator('.dl-ac__time').textContent()))
  await shot(page, '2a-loading')
  release(); await sleep(900)
  check('answer: the card shows with its header', /Datalytics AI/.test(await page.locator('.dl-ac--answer').first().textContent()))
  check('answer: the head is happy just after', (await page.locator('.dl-bot--head').last().getAttribute('data-state')) === 'happy')
  check('answer: duration from the run', /1\.4 s/.test(await page.getByTestId('answer-meta').first().textContent()))
  await page.getByRole('button', { name: /Rows behind this answer/ }).click(); await sleep(300)
  check('answer: rows group thousands', (await page.locator('.dl-sect__body table').first().textContent()).includes('2,348,914'))
  await page.getByRole('button', { name: 'Show SQL' }).click(); await sleep(300)
  check('answer: SQL is left-to-right', (await page.locator('pre.dl-sqlb__code').first().getAttribute('dir')) === 'ltr')
  await page.getByRole('button', { name: 'Export' }).click(); await sleep(300)
  check('answer: Export holds the three files', (await page.getByRole('menuitem').allTextContents()).join(',') === 'Download CSV,Download Excel,Download PDF')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Copy answer' }).click(); await sleep(300)
  check('answer: Copy puts the answer on the clipboard', /Asia Pacific/.test(await page.evaluate(() => navigator.clipboard.readText())))
  const up = page.getByRole('button', { name: 'Good answer' })
  await up.click(); await sleep(300)
  check('answer: 👍 is pressed', (await up.getAttribute('aria-pressed')) === 'true')
  await page.getByRole('button', { name: 'Edit question' }).click(); await sleep(200)
  check('answer: Edit question refills the box', (await box(page).inputValue()) === 'Total revenue by region')
  await box(page).fill('')
  await page.getByRole('button', { name: 'Retry' }).last().click(); await sleep(1500)
  check('answer: Retry asks again', asks === 2, `asks=${asks}`)
  await shot(page, '2b-answer')
  await sleep(4000)
  check('robot: back to calm after the answer', (await page.locator('.dl-bot--head').last().getAttribute('data-state')) === 'idle')
  // The fake conversation (510) does not exist on the server, so 👍's feedback POST is a 404 there.
  const errs = page.errors.filter(e => !/status of 404/.test(e))
  check('answer: no console errors (beyond the fake thread\'s feedback 404)', errs.length === 0, errs.join(' | '))
  await ctx.close()
}

// 3. The error card, and the agent unreachable.
{
  let n = 0
  const { ctx, page } = await open('/ask?dataset=1', { convs: [], ask: async r => { n++; if (n === 1) await r.fulfill({ json: FAILED }); else await r.abort() } })
  await box(page).fill('Which reps missed quota?'); await page.keyboard.press('Enter'); await sleep(1500)
  const card = page.locator('.dl-ac--error').first()
  check('error: title', (await card.getByRole('heading').textContent()) === 'I couldn’t answer that one')
  check('error: column chips', (await card.getByRole('group', { name: 'Try asking about these columns' }).getByRole('button').count()) > 0)
  check('error: details closed, server text inside', !(await card.locator('details').evaluate(d => d.open)) && /Binder Error/.test(await card.locator('details pre').textContent()))
  check('error: the head has the error look', (await card.locator('.dl-bot--head').getAttribute('data-state')) === 'error')
  await shot(page, '3a-error')
  await box(page).fill('again'); await page.keyboard.press('Enter'); await sleep(1500)
  check('unreachable: says so plainly', /Could not reach the agent/.test(await page.locator('.dl-ac--error').last().textContent()))
  check('unreachable: no technical details', (await page.locator('.dl-ac--error').last().locator('details').count()) === 0)
  await shot(page, '3b-unreachable')
  await ctx.close()
}

// 4. The composer limit, and "-5" in an Arabic text box.
{
  const { ctx, page } = await open('/ask?dataset=1', { convs: [] })
  check('composer: limit is 2000', (await box(page).getAttribute('maxlength')) === '2000')
  await box(page).fill('x'.repeat(1800)); await sleep(100)
  const count = page.locator('.dl-composer__count')
  check('composer: no warning at 1800', !(await count.getAttribute('class')).includes('warn'))
  await box(page).fill('x'.repeat(1801)); await sleep(100)
  check('composer: warning from 1801', (await count.getAttribute('class')).includes('warn'))
  await ctx.close()
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: state })
  await ctx2.addInitScript(() => { localStorage.setItem('datalytics.language', 'ar'); localStorage.setItem('datalytics.direction', 'rtl') })
  const p2 = await ctx2.newPage(); await p2.goto(BASE + '/ask'); await sleep(2500)
  await p2.getByRole('combobox').fill('-5'); await sleep(300)
  const bidi = await p2.getByRole('combobox').evaluate(e => getComputedStyle(e).unicodeBidi)
  check('7-QA6 A3: Arabic text boxes read "-5" left-to-right (plaintext)', bidi === 'plaintext', bidi)
  await ctx2.close()
}

// 5. History: switch, rename and delete a scratch chat (real API, cleaned up).
{
  const scratch = await api('POST', '/agent/conversations', { dataset_ids: [1], title: 'AP3 scratch' })
  try {
    const { ctx, page } = await open('/ask?dataset=1')
    const row = page.locator('.dl-hist__item').filter({ hasText: 'AP3 scratch' }).first()
    await row.getByRole('button', { name: /^AP3 scratch/ }).click(); await sleep(1200)
    check('history: picking a thread marks it current', (await row.getByRole('button', { name: /^AP3 scratch/ }).getAttribute('aria-current')) === 'true')
    await row.hover(); await row.getByRole('button', { name: 'Rename AP3 scratch' }).click()
    await page.getByRole('textbox', { name: 'Title' }).fill('AP3 scratch renamed'); await page.keyboard.press('Enter'); await sleep(1200)
    const list = await api('GET', '/agent/conversations')
    check('history: rename is saved', list.some(c => c.id === scratch.id && c.title === 'AP3 scratch renamed'))
    const row2 = page.locator('.dl-hist__item').filter({ hasText: 'AP3 scratch renamed' }).first()
    await row2.hover(); await row2.getByRole('button', { name: 'Delete AP3 scratch renamed' }).click(); await sleep(400)
    await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click(); await sleep(1200)
    const after = await api('GET', '/agent/conversations')
    check('history: delete removes it', !after.some(c => c.id === scratch.id))
    check('history: gone from the rail', (await page.locator('.dl-hist__item').filter({ hasText: 'AP3 scratch' }).count()) === 0)
    await shot(page, '5-history')
    await ctx.close()
  } finally {
    const left = await api('GET', '/agent/conversations')
    if (left.some(c => c.id === scratch.id)) { await api('DELETE', `/agent/conversations/${scratch.id}`); console.log('cleaned up the scratch conversation') }
  }
}

// 6. The robot: sleeps after 20 s alone, wakes on a key.
{
  const { ctx, page } = await open('/ask?dataset=1', { convs: [] })
  await sleep(21000)
  check('robot: asleep after 20 s', (await botState(page)) === 'sleep')
  await page.mouse.move(400, 400); await sleep(300)
  check('robot: wakes on the pointer', (await botState(page)) === 'idle')
  await ctx.close()
}

await browser.close()
console.log(`${results.filter(Boolean).length} / ${results.length} passed`)
