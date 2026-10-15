import { renderWithProviders as render, screen, fireEvent, act, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ChatPane from './ChatPane'
import { sqlTokens } from './SqlBlock'
import { agentApi } from '../../services/api'
import type { AgentAnswer, AgentMessage } from '../../services/api'
import { REACTION_MS } from '../../pages/ask/robotMood'
import { translate } from '../../i18n'
import { LLM_ENDPOINTS_EVENT } from '../../services/api'
import SuggestionGrid from '../../pages/ask/SuggestionGrid'

/** Step 10, Part B: the Ask AI page's loading and answer cards. */

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const BAR: AgentAnswer = {
  run_id: 701, status: 'ok', intent: 'aggregate', error: null,
  answer: 'Asia leads with 2,348,914 in revenue.',
  results: [{ step: 'q1', columns: ['region', 'revenue'], total: 3, truncated: false,
    rows: [['Asia', 2348914], ['Europe', 2219630], ['Africa', 1882846]] }],
  sql: ["SELECT region, SUM(revenue) AS revenue\nFROM sales\nWHERE channel <> 'Partner'\nGROUP BY region"],
  presentation: { format: 'bar', limit: null, x: 'region', y: 'revenue' }, context_objects: ['sales'],
} as unknown as AgentAnswer
const TABLE: AgentAnswer = {
  run_id: 702, status: 'ok', intent: 'lookup', error: null, answer: 'The top products.',
  // Labels only: nothing to chart, so the rows are the answer.
  results: [{ step: 'q1', columns: ['product', 'category', 'channel'], total: 2, truncated: false,
    rows: [['Lamp', 'Home', 'Online'], ['Chair', 'Office', 'Retail']] }],
  sql: ['SELECT product, category, channel FROM sales LIMIT 2'], presentation: null, context_objects: null,
} as unknown as AgentAnswer
const FAILED = { run_id: 703, status: 'failed', intent: null, error: 'Binder Error', answer: null } as unknown as AgentAnswer
const run = (ms: number | null) => ({ ms, steps: [], context_objects: null })

const settle = () => act(async () => { for (let i = 0; i < 30; i++) await Promise.resolve() })
const pane = (extra: Partial<Parameters<typeof ChatPane>[0]> = {}) =>
  render(<ChatPane datasetIds={[1]} conversationId={null} datasetColumns={['region', 'revenue']} card={{ scopeName: 'Demo — Sales' }} {...extra} />)
const ask = async (q = 'total revenue by region') => {
  fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: q } })
  fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
  await settle()
}
const heads = (c: HTMLElement) => [...c.querySelectorAll('.dl-bot--head')] as HTMLElement[]

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  vi.spyOn(agentApi, 'runDetail').mockResolvedValue(run(1400) as never)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('the loading card', () => {
  it('shows the question as a bubble, then a busy card: thinking head, what is asked about, elapsed time, a skeleton, no steps', async () => {
    vi.spyOn(agentApi, 'ask').mockReturnValue(new Promise(() => {}))
    const { container } = pane()
    await ask()
    expect(container.querySelector('.dl-qb')).toHaveTextContent('total revenue by region')
    const card = screen.getByTestId('loading-card')
    expect(card).toHaveAttribute('aria-busy', 'true')
    expect(within(card).getByText('Analyzing your data…')).toBeInTheDocument()
    expect(within(card).getByText('Demo — Sales')).toBeInTheDocument()
    expect(within(card).getByRole('timer')).toHaveTextContent('0 s')
    act(() => { vi.advanceTimersByTime(3000) })
    expect(within(card).getByRole('timer')).toHaveTextContent('3 s')
    expect(card.querySelector('.dl-ac__skel')).toHaveAttribute('aria-hidden', 'true')
    expect(card.querySelector('ol, li')).toBeNull()
    const [head] = heads(card)
    expect(head).toHaveAttribute('data-state', 'thinking')
    expect(head).toHaveAttribute('data-live')
    expect(head).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('the answer card', () => {
  it('heads the answer with who, the data, the rows and the chart it drew', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { container } = pane()
    await ask()
    expect(screen.queryByTestId('loading-card')).toBeNull()
    const card = container.querySelector('.dl-ac--answer') as HTMLElement
    expect(within(card).getByText('Datalytics AI')).toBeInTheDocument()
    const meta = within(card).getByTestId('answer-meta')
    expect(meta).toHaveTextContent('Demo — Sales')
    expect(meta).toHaveTextContent('3 rows')
    expect(within(card).getByTestId('answer-chart-chip')).toHaveTextContent('Auto chart · Bar')
    expect(card.querySelector('figure.dl-ac__chart')).not.toBeNull()
    expect(screen.getByTestId('ask-live')).toHaveTextContent('Answer ready')
  })

  it('adds the real duration from one read of the run, without holding the answer back', async () => {
    let done!: (v: unknown) => void
    const detail = vi.spyOn(agentApi, 'runDetail').mockReturnValue(new Promise(r => { done = r }) as never)
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    pane()
    await ask()
    expect(screen.getByTestId('answer-text')).toHaveTextContent('Asia leads')
    expect(screen.queryByTestId('answer-took')).toBeNull()
    done(run(1400)); await settle()
    expect(screen.getByTestId('answer-took')).toHaveTextContent('1.4 s')
    expect(detail).toHaveBeenCalledTimes(1)
    expect(detail).toHaveBeenCalledWith(701)
  })

  it('shows no duration when the run does not give one or the read fails', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    vi.spyOn(agentApi, 'runDetail').mockRejectedValueOnce(new Error('nope')).mockResolvedValueOnce(run(null) as never)
    pane()
    await ask(); await ask('again')
    expect(screen.queryByTestId('answer-took')).toBeNull()
    expect(screen.getAllByTestId('answer-meta')).toHaveLength(2)
  })

  it('keeps the rows one band away under a chart, and open when rows are the answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValueOnce(BAR).mockResolvedValueOnce(TABLE)
    const { container } = pane()
    await ask()
    const rows = screen.getByRole('button', { name: /Rows behind this answer/ })
    expect(rows).toHaveAttribute('aria-expanded', 'false')
    expect(rows).toHaveTextContent('3')
    expect(container.querySelector('table')).toBeNull()
    fireEvent.click(rows)
    expect(rows).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById(rows.getAttribute('aria-controls')!)!.querySelector('table')).not.toBeNull()
    fireEvent.click(rows)
    await ask('top products')
    const second = screen.getAllByRole('button', { name: /Rows behind this answer/ })[1]
    expect(second).toHaveAttribute('aria-expanded', 'true')
    expect(screen.queryAllByTestId('answer-chart-chip')).toHaveLength(1)
    fireEvent.click(second)
    expect(container.querySelector('table')).toBeNull()
  })

  it('shows the SQL as a band: left-to-right, keywords and strings marked, with Copy', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const { container } = pane()
    await ask()
    fireEvent.click(screen.getByRole('button', { name: 'Show SQL' }))
    await settle()
    expect(screen.getByRole('button', { name: 'Hide SQL' })).toHaveAttribute('aria-expanded', 'true')
    const code = container.querySelector('pre.dl-sqlb__code') as HTMLElement
    expect(code).toHaveAttribute('dir', 'ltr')
    expect(code.textContent).toBe((BAR.sql as string[])[0])
    expect([...code.querySelectorAll('.dl-sqlb__kw')].map(e => e.textContent)).toEqual(['SELECT', 'SUM', 'AS', 'FROM', 'WHERE', 'GROUP', 'BY'])
    expect(code.querySelector('.dl-sqlb__str')).toHaveTextContent("'Partner'")
    fireEvent.click(screen.getByRole('button', { name: 'Copy SQL' }))
    await settle()
    expect(writeText).toHaveBeenCalledWith((BAR.sql as string[])[0])
  })

  it('offers Edit question on an answer, beside Retry', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    pane()
    await ask()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edit question' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('total revenue by region')
    expect(screen.getByRole('button', { name: 'Good answer' })).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('the GATE B changes', () => {
  it('groups thousands in the rows and holds numbers left-to-right, but never in a year or id column', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ ...TABLE, results: [{ step: 'q1', columns: ['region', 'year', 'order_id', 'revenue', 'margin'],
      total: 2, truncated: true, rows: [['Asia', 2026, 104233, 2348914, -1234.5678], ['Europe', 2025, 104234, 2219630.5, 0.04567]] }] } as unknown as AgentAnswer)
    const { container } = pane()
    await ask()
    const cells = [...container.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent))
    expect(cells).toEqual([['Asia', '2026', '104233', '2,348,914', '-1,234.57'], ['Europe', '2025', '104234', '2,219,630.5', '0.0457']])
    const revenue = container.querySelectorAll('tbody tr')[0].querySelectorAll('td')[3]
    expect(revenue.querySelector('bdi')).toHaveAttribute('dir', 'ltr')
    expect(container.querySelector('tfoot')).toBeNull()
  })

  // FIX-QAF 10 (owner): the compact view now uses the answer card's rule too,
  // so the floating panel's table matches its sentence ("2,348,914").
  it('groups quantities in the compact grid as on the card (QAF 10)', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { container } = render(<ChatPane datasetIds={[1]} conversationId={null} />)
    await ask()
    fireEvent.click(screen.getByRole('button', { name: /Show rows/ }))
    expect(container.querySelector('tbody td:nth-child(2)')).toHaveTextContent('2,348,914')
  })

  it('puts the downloads under one Export menu, worked by keyboard', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const file = vi.spyOn(agentApi, 'downloadRunFile').mockResolvedValue(undefined as never)
    const { container } = pane()
    await ask()
    const acts = container.querySelector('.dl-ac__acts') as HTMLElement
    expect([...acts.querySelectorAll('button')].map(b => b.getAttribute('aria-label') ?? b.textContent?.trim()))
      .toEqual(['Add to dashboard', 'Copy answer', 'Good answer', 'Bad answer', 'Export', 'Edit question', 'Retry'])
    expect(screen.queryByRole('button', { name: 'Download CSV' })).toBeNull()
    const trigger = screen.getByRole('button', { name: 'Export' })
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')
    fireEvent.click(trigger)
    const menu = screen.getByRole('menu', { name: 'Export' })
    expect(within(menu).getAllByRole('menuitem').map(i => i.textContent)).toEqual(['Download CSV', 'Download Excel', 'Download PDF'])
    expect(within(menu).getAllByRole('menuitem')[0]).toHaveFocus()
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(within(menu).getAllByRole('menuitem')[1]).toHaveFocus()
    fireEvent.keyDown(menu, { key: 'Enter' })
    expect(file).toHaveBeenCalledWith(701, 'xlsx')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(trigger).toHaveFocus()
    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('adds Save as dataset to the menu on a connection, and names the menu in Arabic', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    render(<ChatPane dataSourceId={2} conversationId={null} card={{ scopeName: 'Live' }} />)
    await ask()
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    expect(screen.getAllByRole('menuitem').map(i => i.textContent)).toEqual(['Download CSV', 'Download Excel', 'Download PDF', 'Save as dataset'])
    expect(translate('ar', 'ask2.ans.export')).toBe('تصدير')
  })
})

describe('the error card', () => {
  it('says why in words, offers the page’s column suggestions, hides the server text under Technical details', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(FAILED)
    const { container } = pane({ suggestions: ['Total revenue by region', 'Top 5 region by revenue', 'How many rows per region?', 'A fourth'] })
    await ask('which reps missed quota?')
    const card = container.querySelector('.dl-ac--error') as HTMLElement
    expect(within(card).getByRole('heading', { name: 'I couldn’t answer that one' })).toBeInTheDocument()
    const why = within(card).getByRole('alert')
    expect(why).toHaveTextContent('I couldn’t match your question to Demo — Sales. Try rephrasing it, or start from its columns.')
    expect(why.querySelector('bdi b')).toHaveTextContent('Demo — Sales')
    const chips = within(card).getByRole('group', { name: 'Try asking about these columns' })
    expect(within(chips).getAllByRole('button').map(b => b.textContent?.trim())).toEqual(['Total revenue by region', 'Top 5 region by revenue', 'How many rows per region?'])
    const details = card.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(details.querySelector('summary')).toHaveTextContent('Technical details')
    expect(details.querySelector('pre')).toHaveAttribute('dir', 'ltr')
    expect(details.querySelector('pre')).toHaveTextContent('Binder Error')
    expect(why).not.toHaveTextContent('Binder Error')
    expect(card.querySelector('[data-testid="answer-meta"]')).toBeNull()
  })

  it('Edit question refills the box; Retry and a suggestion ask again', async () => {
    const asked = vi.spyOn(agentApi, 'ask').mockResolvedValue(FAILED)
    const { container } = pane({ suggestions: ['Total revenue by region'] })
    await ask('which reps missed quota?')
    const acts = container.querySelector('.dl-ac--error .dl-ac__acts') as HTMLElement
    expect([...acts.querySelectorAll('button')].map(b => b.textContent?.trim())).toEqual(['Edit question', 'Retry'])
    expect(within(acts).getByRole('button', { name: 'Edit question' })).toHaveClass('dl-act--primary')
    fireEvent.click(within(acts).getByRole('button', { name: 'Edit question' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('which reps missed quota?')
    fireEvent.click(within(acts).getByRole('button', { name: 'Retry' }))
    await settle()
    expect(asked).toHaveBeenLastCalledWith(7, 'which reps missed quota?', expect.any(AbortSignal))
    fireEvent.click(screen.getAllByRole('button', { name: 'Total revenue by region' })[0])
    await settle()
    expect(asked).toHaveBeenLastCalledWith(7, 'Total revenue by region', expect.any(AbortSignal))
  })

  it('a request that never reached the agent says only that: no column advice, nothing technical', async () => {
    vi.spyOn(agentApi, 'ask').mockRejectedValue(new Error('down'))
    const { container } = pane({ suggestions: ['Total revenue by region'] })
    await ask()
    const card = container.querySelector('.dl-ac--error') as HTMLElement
    expect(within(card).getByRole('alert')).toHaveTextContent('Could not reach the agent. Try again.')
    expect(card.querySelector('details, .dl-err__try')).toBeNull()
    expect(within(card).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('does not announce the failures of a reopened thread', async () => {
    vi.spyOn(agentApi, 'messages').mockResolvedValue([
      { id: 1, role: 'user', content: 'q', created_at: null, run: null },
      { id: 2, role: 'assistant', content: '', created_at: null, run: { id: 9, status: 'failed', intent: null, error: 'Binder Error', results: [], sql: [], presentation: null, context_objects: null } },
    ] as AgentMessage[])
    const { container } = pane({ conversationId: 9 })
    await settle()
    expect(container.querySelector('.dl-ac--error')).not.toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('is in Arabic', () => {
    expect(translate('ar', 'ask2.err.title')).toBe('تعذّرت الإجابة عن هذا السؤال')
    expect(translate('ar', 'ask2.err.tryColumns')).toBe('جرّب السؤال عن هذه الأعمدة')
    expect(translate('ar', 'ask2.err.why', { name: 'X' })).toContain('X')
  })
})

describe('the question box on the page', () => {
  it('names the data, shows the keys and the count inside its frame, and a disclaimer under it', async () => {
    const { container } = pane()
    await settle()
    const box = screen.getByRole('textbox', { name: 'Your question' })
    expect(box).toHaveAttribute('placeholder', 'Ask about Demo — Sales…')
    expect(box).toHaveAttribute('maxlength', '2000')
    const foot = container.querySelector('.dl-composer--page .dl-composer__box .dl-composer__foot') as HTMLElement
    expect(foot.querySelector('.dl-composer__keys')).toHaveTextContent('Enter to send · Shift + Enter for a new line')
    expect(foot.querySelectorAll('kbd')).toHaveLength(3)
    expect(foot.querySelector('.dl-composer__count')).toHaveTextContent('0 / 2000')
    expect(screen.getByText('Answers are generated from your data. Check the SQL before you share them.')).toBeInTheDocument()
  })

  it('warns from 1800 characters, not before', async () => {
    const { container } = pane()
    await settle()
    const box = screen.getByRole('textbox', { name: 'Your question' })
    const count = () => container.querySelector('.dl-composer__count') as HTMLElement
    fireEvent.change(box, { target: { value: 'x'.repeat(1800) } })
    expect(count()).toHaveTextContent('1800 / 2000')
    expect(count()).not.toHaveClass('dl-composer__count--warn')
    fireEvent.change(box, { target: { value: 'x'.repeat(1801) } })
    expect(count()).toHaveClass('dl-composer__count--warn')
  })

  it('sends on Enter, not on Shift+Enter or while composing; Send is off while empty', async () => {
    const asked = vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    pane()
    await settle()
    const box = screen.getByRole('textbox', { name: 'Your question' })
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled()
    fireEvent.change(box, { target: { value: 'total' } })
    expect(screen.getByRole('button', { name: 'Send question' })).toBeEnabled()
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true })
    await settle()
    expect(asked).not.toHaveBeenCalled()
    fireEvent.keyDown(box, { key: 'Enter' })
    await settle()
    expect(asked).toHaveBeenCalledWith(7, 'total', expect.any(AbortSignal))
  })

  it('keeps the compact box outside the page', () => {
    const { container } = render(<ChatPane datasetIds={[1]} conversationId={null} />)
    expect(container.querySelector('.dl-composer--page, .dl-ask__disc')).toBeNull()
    expect(screen.getByRole('textbox', { name: 'Your question' })).toHaveAttribute('placeholder', 'Ask a question about this data…')
  })
})

describe("the robot's head on the cards", () => {
  it('is happy when the answer lands, then calm; only the newest head moves', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { container } = pane()
    await ask()
    expect(heads(container)).toHaveLength(1)
    expect(heads(container)[0]).toHaveAttribute('data-state', 'happy')
    expect(heads(container)[0]).toHaveAttribute('data-live')
    act(() => { vi.advanceTimersByTime(REACTION_MS) })
    expect(heads(container)[0]).toHaveAttribute('data-state', 'idle')
    expect(heads(container)[0]).toHaveAttribute('data-live')

    vi.spyOn(agentApi, 'ask').mockReturnValue(new Promise(() => {}))
    await ask('next')
    const [older, loading] = heads(container)
    expect(older).toHaveAttribute('data-state', 'idle')
    expect(older).not.toHaveAttribute('data-live')
    expect(loading).toHaveAttribute('data-state', 'thinking')
    expect(loading).toHaveAttribute('data-live')
  })

  it('has the error look when the question fails, then calm', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValueOnce(FAILED).mockRejectedValueOnce(new Error('down'))
    const { container } = pane()
    for (const q of ['one', 'two']) {
      await ask(q)
      const newest = heads(container).at(-1)!
      expect(newest.closest('.dl-ac')).toHaveClass('dl-ac--error')
      expect(newest).toHaveAttribute('data-state', 'error')
      act(() => { vi.advanceTimersByTime(REACTION_MS) })
      expect(heads(container).at(-1)).toHaveAttribute('data-state', 'idle')
    }
    expect(screen.getByTestId('ask-live')).toBeEmptyDOMElement()
  })

  it('is still, with calm eyes, on every answer of a stored thread but the last', async () => {
    const stored: AgentMessage[] = [1, 2].flatMap(n => [
      { id: n * 2 - 1, role: 'user', content: `q${n}`, created_at: null, run: null },
      { id: n * 2, role: 'assistant', content: 'The top products.', created_at: null,
        run: { id: 800 + n, status: 'ok', intent: 'lookup', error: null, results: TABLE.results!, sql: TABLE.sql!, presentation: null, context_objects: null } },
    ] as AgentMessage[])
    vi.spyOn(agentApi, 'messages').mockResolvedValue(stored)
    const { container } = pane({ conversationId: 9 })
    await settle()
    const [first, last] = heads(container)
    expect(first).toHaveAttribute('data-state', 'idle')
    expect(first).not.toHaveAttribute('data-live')
    expect(last).toHaveAttribute('data-state', 'idle')
    expect(last).toHaveAttribute('data-live')
    // A stored answer's duration is not known, and is not fetched per message.
    expect(agentApi.runDetail).not.toHaveBeenCalled()
    expect(screen.queryByTestId('answer-took')).toBeNull()
  })

  it('leaves no timer behind', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { unmount } = pane()
    await ask()
    expect(vi.getTimerCount()).toBeGreaterThan(0)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('outside the Ask AI page', () => {
  it('keeps the compact turn: no cards, no head, no extra read of the run', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { container } = render(<ChatPane datasetIds={[1]} conversationId={null} datasetColumns={['region', 'revenue']} />)
    await ask()
    expect(container.querySelector('.dl-ac, .dl-qb, .dl-bot--head, .dl-sect')).toBeNull()
    expect(container.querySelector('.dl-turn__a')).not.toBeNull()
    expect(screen.getByRole('button', { name: /Show rows/ })).toBeInTheDocument()
    expect(agentApi.runDetail).not.toHaveBeenCalled()
  })
})

describe('the card strings', () => {
  it('are in Arabic too', () => {
    for (const key of ['ask2.load.title', 'ask2.live.ready', 'ask2.ans.who', 'ask2.ans.rowsBehind', 'ask2.chart.bar', 'ask2.chart.line', 'ask2.chart.pie'] as const) {
      expect(translate('ar', key), key).not.toBe(translate('en', key))
    }
    expect(translate('ar', 'ask2.ans.autoChart', { kind: translate('ar', 'ask2.chart.bar') })).toBe('مخطط تلقائي · أعمدة')
  })
})

describe('sqlTokens', () => {
  it('keeps the text whole and marks only keywords and strings', () => {
    const sql = `SELECT "select", name FROM t WHERE note = 'from ''here''' -- group`
    const toks = sqlTokens(sql)
    expect(toks.map(t => t.text).join('')).toBe(sql)
    expect(toks.filter(t => t.kind === 'kw').map(t => t.text)).toEqual(['SELECT', 'FROM', 'WHERE', 'group'])
    expect(toks.filter(t => t.kind === 'str').map(t => t.text)).toEqual([`'from ''here'''`])
  })
})

describe('suggestion cards while new questions are paused (AD-02)', () => {
  const down = () => act(() => {
    window.dispatchEvent(new CustomEvent(LLM_ENDPOINTS_EVENT, { detail: { at: Date.now(), data: {
      llm_enabled: true, default: 'env', auto_pick: null, source: 'environment',
      endpoints: [{ id: 'env', name: 'Default', model: 'q', enabled: true, is_default: true, strength: 5, context: null,
        status: { ok: false, latency_ms: null, checked_at: new Date().toISOString(), error: 'ConnectTimeout' } }],
    } } }))
  })
  const cards = [{ text: 'Total revenue by region', icon: 'total' as const, columns: ['revenue', 'region'] }]
  const withCards = () => pane({
    startView: (send, busy, reason) => <SuggestionGrid cards={cards} onAsk={send} disabled={busy} disabledReason={reason} />,
  })

  it('disables every card, explains why, and never sends', async () => {
    const asked = vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    const { container } = withCards()
    down()
    const all = [...container.querySelectorAll<HTMLButtonElement>('.dl-sug__card')]
    expect(all.length).toBe(1)
    for (const c of all) {
      expect(c).toBeDisabled()
      expect(c.title).toMatch(/paused/i)
    }
    fireEvent.click(all[0])
    await settle()
    expect(asked).not.toHaveBeenCalled()
  })

  it('also refuses the typed question on Enter while paused', async () => {
    const asked = vi.spyOn(agentApi, 'ask').mockResolvedValue(BAR)
    pane()
    down()
    const box = screen.getByPlaceholderText(/ask|paused/i)
    fireEvent.change(box, { target: { value: 'total revenue' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await settle()
    expect(asked).not.toHaveBeenCalled()
  })
})
