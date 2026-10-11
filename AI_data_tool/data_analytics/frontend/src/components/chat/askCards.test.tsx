import { renderWithProviders as render, screen, fireEvent, act, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ChatPane from './ChatPane'
import { sqlTokens } from './SqlBlock'
import { agentApi } from '../../services/api'
import type { AgentAnswer, AgentMessage } from '../../services/api'
import { REACTION_MS } from '../../pages/ask/robotMood'
import { translate } from '../../i18n'

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
