import { renderWithProviders as render, answerPrompt, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ChatPane from './ChatPane'
import { toCsv, chartRows, chartColumns } from './ResultView'
import { agentApi, dataSourcesApi } from '../../services/api'
import { axeViolations } from '../../test/axe'

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
})

async function send(question: string) {
  render(<ChatPane dataSourceId={2} />)
  fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
}

describe('asking a question', () => {
  it('shows the question and then the answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'Total sales are 12,400.',
      intent: 'aggregate', error: null })
    await send('total sales')
    await waitFor(() =>
      expect(screen.getByText('Total sales are 12,400.')).toBeInTheDocument())
    expect(screen.getByText('total sales')).toBeInTheDocument()
  })

  it('creates the conversation lazily, once, on first send', async () => {
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'ok', intent: null, error: null })
    render(<ChatPane dataSourceId={2} />)
    expect(agentApi.createConversation).not.toHaveBeenCalled()
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'q1' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(7, 'q1'))
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'q2' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(7, 'q2'))
    expect(agentApi.createConversation).toHaveBeenCalledTimes(1)
  })

  it('renders a clarifying question as a question, not an answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 2, status: 'needs_clarification',
      answer: 'Did you mean revenue or order count?', intent: null, error: null })
    await send('show me the numbers')
    await waitFor(() =>
      expect(screen.getByText(/did you mean/i)).toBeInTheDocument())
    expect(screen.getByText(/needs more detail/i)).toBeInTheDocument()
  })

  it('a failure reads as a failure, never as an answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 3, status: 'failed', answer: null, intent: null,
      error: 'step s1: no such column: discount' })
    await send('total discounts')
    await waitFor(() =>
      expect(screen.getByText(/no such column/i)).toBeInTheDocument())
  })

  it('show SQL reveals the provenance', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 4, status: 'ok', answer: 'Answer.', intent: 'lookup', error: null })
    const runDetail = vi.spyOn(agentApi, 'runDetail').mockResolvedValue({
      steps: [{ sql: 'SELECT sum(total) FROM orders', status: 'ok' }] })
    await send('total sales')
    await waitFor(() => screen.getByText('Answer.'))
    fireEvent.click(screen.getByRole('button', { name: /show sql/i }))
    await waitFor(() =>
      expect(screen.getByText(/SELECT sum\(total\)/)).toBeInTheDocument())
    expect(runDetail).toHaveBeenCalledTimes(1)

    // Toggling closed and reopening must not re-fetch: one message, one fetch.
    fireEvent.click(screen.getByText(/hide sql/i))
    fireEvent.click(screen.getByRole('button', { name: /show sql/i }))
    await waitFor(() =>
      expect(screen.getByText(/SELECT sum\(total\)/)).toBeInTheDocument())
    expect(runDetail).toHaveBeenCalledTimes(1)
  })

  it('a rejected ask surfaces as an error and re-enables the input', async () => {
    vi.spyOn(agentApi, 'ask').mockRejectedValue(new Error('network down'))
    await send('total sales')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /send|ask/i })).not.toBeDisabled())
    expect(screen.getByPlaceholderText(/ask/i)).not.toBeDisabled()
  })

  it('asking against a set of datasets sends dataset_ids, not a data source', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 5, status: 'ok', answer: 'joined answer', intent: null, error: null })
    render(<ChatPane datasetIds={[3, 4]} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'joined total' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() =>
      expect(agentApi.createConversation).toHaveBeenCalledWith({ datasetIds: [3, 4] }))
  })

  it('resumes the most recent matching conversation instead of creating one', async () => {
    // Backend orders conversations newest-first; the pane should resume the
    // first (most recent) match, not an older one further down the list.
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([
      { id: 55, title: 'Latest chat', data_source_id: 2, dataset_ids: null },
      { id: 42, title: 'Older chat', data_source_id: 2, dataset_ids: null },
    ])
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'ok', intent: null, error: null })
    await send('total sales')
    await waitFor(() => expect(ask).toHaveBeenCalledWith(55, 'total sales'))
    expect(agentApi.createConversation).not.toHaveBeenCalled()
  })

  it('does not resume a conversation targeting a different source', async () => {
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([
      { id: 42, title: 'Other source', data_source_id: 99, dataset_ids: null },
    ])
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'ok', intent: null, error: null })
    await send('total sales')
    await waitFor(() => expect(ask).toHaveBeenCalledWith(7, 'total sales'))
    expect(agentApi.createConversation).toHaveBeenCalledTimes(1)
  })

  it('rates an answer up or down via the feedback endpoint', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 11, status: 'ok', answer: 'Total is 30.', intent: null, error: null })
    const feedback = vi.spyOn(agentApi, 'feedback').mockResolvedValue({
      id: 1, run_id: 11, rating: 'up', comment: null })
    await send('total sales')
    await waitFor(() => screen.getByText('Total is 30.'))

    fireEvent.click(screen.getByLabelText('Good answer'))

    await waitFor(() => expect(feedback).toHaveBeenCalledWith(7, { runId: 11, rating: 'up' }))
    expect(screen.getByLabelText('Good answer')).toHaveAttribute('aria-pressed', 'true')
  })

  it('a failed feedback write does not blow up the chat', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 12, status: 'ok', answer: 'Total is 30.', intent: null, error: null })
    vi.spyOn(agentApi, 'feedback').mockRejectedValue(new Error('down'))
    await send('total sales')
    await waitFor(() => screen.getByText('Total is 30.'))

    fireEvent.click(screen.getByLabelText('Bad answer'))

    await waitFor(() =>
      expect(screen.getByLabelText('Bad answer')).toHaveAttribute('aria-pressed', 'true'))
  })

  it('disables the send button while a question is in flight', async () => {
    let resolveAsk!: (v: Awaited<ReturnType<typeof agentApi.ask>>) => void
    vi.spyOn(agentApi, 'ask').mockReturnValue(new Promise(res => { resolveAsk = res }))
    render(<ChatPane dataSourceId={2} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'q' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /send|ask/i })).toBeDisabled())
    resolveAsk({ run_id: 9, status: 'ok', answer: 'done', intent: null, error: null })
    await waitFor(() => expect(screen.getByText('done')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /send|ask/i })).not.toBeDisabled()
  })
})

const RESULT = { step: 's1', columns: ['city', 'n'], rows: [['Cairo', 3], ['Giza', 1]],
                 total: 2, truncated: false }
const SQL = 'SELECT city, count(*) AS n FROM orders GROUP BY city'

describe('the result travels with the answer', () => {
  it('draws the rows as a grid under the answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 20, status: 'ok', answer: 'Cairo leads.', intent: 'aggregate', error: null,
      results: [RESULT], sql: [SQL], presentation: null, context_objects: ['orders'] })
    await send('orders per city')
    await waitFor(() => screen.getByText('Cairo leads.'))
    const grid = screen.getByRole('table')
    expect(grid).toHaveTextContent('city')
    expect(grid).toHaveTextContent('Cairo')
    expect(grid).toHaveTextContent('3')
    expect(screen.getByText('2 rows')).toBeInTheDocument()
  })

  it('says when the grid is only the head of a larger result', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 21, status: 'ok', answer: 'Many.', intent: null, error: null,
      results: [{ ...RESULT, total: 250, truncated: true }], sql: [SQL] })
    await send('all rows')
    await waitFor(() => screen.getByText('Many.'))
    expect(screen.getByText('250 rows, showing 2')).toBeInTheDocument()
  })

  it('shows the SQL and the tables considered without a second fetch', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 22, status: 'ok', answer: 'A.', intent: null, error: null,
      results: [RESULT], sql: [SQL], context_objects: ['orders', 'customers'] })
    const runDetail = vi.spyOn(agentApi, 'runDetail')
    await send('q')
    await waitFor(() => screen.getByText('A.'))
    fireEvent.click(screen.getByRole('button', { name: /show sql/i }))
    expect(screen.getByText(SQL)).toBeInTheDocument()
    expect(screen.getByText(/tables considered/i)).toHaveTextContent('orders, customers')
    expect(runDetail).not.toHaveBeenCalled()
  })

  it('copies the SQL to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 23, status: 'ok', answer: 'A.', intent: null, error: null,
      results: [RESULT], sql: [SQL] })
    await send('q')
    await waitFor(() => screen.getByText('A.'))
    fireEvent.click(screen.getByRole('button', { name: /copy sql/i }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SQL))
  })

  it('downloads the rows as CSV', async () => {
    let captured: Blob | null = null
    const createObjectURL = vi.fn((b: Blob) => { captured = b; return 'blob:x' })
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 24, status: 'ok', answer: 'A.', intent: null, error: null,
      results: [{ ...RESULT, rows: [['Cairo, Egypt', 3], ['Giza "old"', null]] }], sql: [SQL] })
    await send('q')
    await waitFor(() => screen.getByText('A.'))
    fireEvent.click(screen.getByRole('button', { name: /download csv/i }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect((captured as unknown as Blob).type).toBe('text/csv;charset=utf-8')
    // jsdom's Blob cannot be read back; the text itself is pinned on toCsv:
    // a byte-order mark first (Excel otherwise reads Arabic as mojibake),
    // RFC 4180 quoting, CRLF line ends.
    expect(toCsv([{ ...RESULT, rows: [['Cairo, Egypt', 3], ['Giza "old"', null]] }]))
      .toBe('﻿city,n\r\n"Cairo, Egypt",3\r\n"Giza ""old""",\r\n')
  })

  it('downloads Excel and PDF through the export endpoint', async () => {
    // xlsx and PDF are built server-side from the stored snapshot; the
    // pane's job is only to name the run and the format.
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 26, status: 'ok', answer: 'A.', intent: null, error: null,
      results: [RESULT], sql: [SQL] })
    const dl = vi.spyOn(agentApi, 'downloadRunFile').mockResolvedValue(undefined)
    await send('q')
    await waitFor(() => screen.getByText('A.'))
    fireEvent.click(screen.getByRole('button', { name: /download excel/i }))
    await waitFor(() => expect(dl).toHaveBeenCalledWith(26, 'xlsx'))
    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }))
    await waitFor(() => expect(dl).toHaveBeenCalledWith(26, 'pdf'))
  })

  it('offers no file downloads on an empty result', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 27, status: 'ok', answer: 'None found.', intent: null, error: null,
      results: [{ ...RESULT, rows: [], total: 0 }], sql: [SQL] })
    await send('q')
    await waitFor(() => screen.getByText('None found.'))
    expect(screen.queryByRole('button', { name: /download/i })).not.toBeInTheDocument()
  })

  it('draws a chart when the answer is a presentation follow-up', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 25, status: 'ok', answer: 'Here is the result as a bar chart.',
      intent: 'present', error: null, results: [RESULT], sql: [SQL],
      presentation: { format: 'bar', limit: null } })
    await send('as a bar chart')
    await waitFor(() => screen.getByText(/as a bar chart\./))
    expect(screen.getByTestId('result-chart')).toHaveAttribute('data-format', 'bar')
    // The rows are still one click away.
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /show rows/i }))
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
})

describe('a conversation owned by the page', () => {
  const MESSAGES = [
    { id: 1, role: 'user' as const, content: 'orders per city', created_at: null, run: null },
    { id: 2, role: 'assistant' as const, content: 'Cairo leads.', created_at: null,
      run: { id: 20, status: 'ok' as const, intent: 'aggregate', error: null,
             results: [RESULT], sql: [SQL], presentation: null, context_objects: ['orders'] } },
  ]

  it('loads the stored thread, grids included, and continues it', async () => {
    const messages = vi.spyOn(agentApi, 'messages').mockResolvedValue(MESSAGES)
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 30, status: 'ok', answer: 'And Giza next.', intent: null, error: null })
    render(<ChatPane dataSourceId={2} conversationId={55} />)
    expect(await screen.findByText('Cairo leads.')).toBeInTheDocument()
    expect(screen.getByText('orders per city')).toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveTextContent('Cairo')
    expect(messages).toHaveBeenCalledWith(55)
    expect(agentApi.listConversations).not.toHaveBeenCalled()

    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'and giza?' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(55, 'and giza?'))
    expect(agentApi.createConversation).not.toHaveBeenCalled()
  })

  it('restores a clarification and a failure with their own shapes', async () => {
    vi.spyOn(agentApi, 'messages').mockResolvedValue([
      { id: 1, role: 'user', content: 'numbers', created_at: null, run: null },
      { id: 2, role: 'assistant', content: 'Which numbers?', created_at: null,
        run: { id: 1, status: 'needs_clarification', intent: null, error: null,
               results: [], sql: [], presentation: null, context_objects: null } },
      { id: 3, role: 'user', content: 'discounts', created_at: null, run: null },
      { id: 4, role: 'assistant', content: 'step s1: no such column', created_at: null,
        run: { id: 2, status: 'failed', intent: null, error: 'step s1: no such column',
               results: [], sql: [], presentation: null, context_objects: null } },
    ])
    render(<ChatPane dataSourceId={2} conversationId={56} />)
    expect(await screen.findByText(/needs more detail/i)).toBeInTheDocument()
    expect(screen.getByText(/could not answer that/i)).toBeInTheDocument()
  })

  it('loads under StrictMode double-mounting -- the dev server is StrictMode', async () => {
    // Seen live: the pane hung on "Loading conversation…" in the real app
    // while every jsdom test passed, because StrictMode runs each effect
    // twice and an unmount-flag guard disowned the first run's response
    // while the second run early-returned on the id ref. main.tsx renders
    // the whole app in StrictMode, so this harness must too.
    const { StrictMode } = await import('react')
    vi.spyOn(agentApi, 'messages').mockResolvedValue(MESSAGES)
    render(<StrictMode><ChatPane dataSourceId={2} conversationId={55} /></StrictMode>)
    expect(await screen.findByText('Cairo leads.')).toBeInTheDocument()
    expect(screen.queryByText(/loading conversation/i)).not.toBeInTheDocument()
  })

  it('the legacy mount shows the resumed thread instead of a blank slate', async () => {
    // The report-builder mount (no conversationId prop) has always RESUMED
    // the newest matching server thread -- but silently, so every visit
    // looked like an empty chat over a growing history. Opening now loads
    // that thread's messages.
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([
      { id: 55, title: 'Latest chat', data_source_id: 2, dataset_ids: null },
    ])
    const messages = vi.spyOn(agentApi, 'messages').mockResolvedValue(MESSAGES)
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 31, status: 'ok', answer: 'next', intent: null, error: null })
    render(<ChatPane dataSourceId={2} />)
    expect(await screen.findByText('Cairo leads.')).toBeInTheDocument()
    expect(messages).toHaveBeenCalledWith(55)
    // And a question continues that thread without re-resolving it.
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'more' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(55, 'more'))
    expect(agentApi.createConversation).not.toHaveBeenCalled()
  })

  it('a failed history load never blocks asking', async () => {
    // The mount-time load fails; the send-time resolution succeeds.
    vi.spyOn(agentApi, 'listConversations')
      .mockRejectedValueOnce(new Error('down')).mockResolvedValue([])
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 32, status: 'ok', answer: 'ok', intent: null, error: null })
    render(<ChatPane dataSourceId={2} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'q' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(ask).toHaveBeenCalled())
  })

  it('a new thread is created on the first send and reported to the page', async () => {
    const created = vi.fn()
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 31, status: 'ok', answer: 'ok', intent: null, error: null })
    render(<ChatPane dataSourceId={2} conversationId={null} onConversationCreated={created} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'first' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    // The server titles a default-titled thread from its first question;
    // the pane reports that title straight away so the list matches.
    await waitFor(() => expect(created).toHaveBeenCalledWith({ id: 7, title: 'first' }))
    expect(agentApi.listConversations).not.toHaveBeenCalled()
  })
})

describe('an answer that is an analysis, not rows', () => {
  /**
   * `AnalysisResult` is tested in isolation next door. That proves it renders
   * correctly and proves nothing about whether ChatPane ever reaches it — the
   * dispatch is four lines in a chain of ternaries, and a run with no `results`
   * used to render nothing at all below the text.
   *
   * The agent answers "is revenue really different between regions?" by running
   * `compare_groups` rather than writing SQL, so there are no rows: the answer
   * arrives entirely on `presentation`.
   */
  const ANALYSIS_RUN = {
    run_id: 31, status: 'ok' as const,
    answer: 'A statistically significant difference, with a large effect.',
    intent: 'compare', error: null,
    results: [],
    presentation: {
      kind: 'analysis_result', analysis: 'compare_groups',
      result_kind: 'statistical_test',
      params: { value_col: 'revenue', group_col: 'region' },
      result: {
        kind: 'compare_groups', statistic: 41.2, p_value: 0.0000001,
        effect_size: 2.9, effect_name: 'cohens_d', effect_label: 'large',
        significant: true, alpha: 0.05, n: 24,
        detail: { test: "Welch's t-test" },
        interpretation: 'A statistically significant difference, with a large effect.',
        caveats: ['Welch’s t-test does not assume equal variances'],
      },
    },
  }

  it('renders the statistic even though there are no rows', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANALYSIS_RUN as never)
    await send('is revenue really different between regions?')
    await waitFor(() =>
      expect(screen.getByText(/cohens d/i)).toBeInTheDocument())
    expect(screen.getByText('2.9')).toBeInTheDocument()
  })

  it('names the analysis that produced it', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANALYSIS_RUN as never)
    await send('is revenue really different between regions?')
    await waitFor(() =>
      expect(screen.getByText(/compare groups/i)).toBeInTheDocument())
  })

  it('keeps the caveats with the number', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANALYSIS_RUN as never)
    await send('is revenue really different between regions?')
    await waitFor(() =>
      expect(screen.getByText(/does not assume equal variances/i)).toBeInTheDocument())
  })

  it('offers no SQL controls, because no SQL was written', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANALYSIS_RUN as never)
    await send('is revenue really different between regions?')
    await waitFor(() => expect(screen.getByText(/cohens d/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /show sql/i })).not.toBeInTheDocument()
  })
})

describe('charting a result whose columns are all numeric', () => {
  /**
   * From a screenshot: "i need chart" over a result of five numeric columns
   * drew ten bars ~720 tall labelled 718-727 -- the id column plotted against
   * itself. `nameIdx` was -1 (no categorical column to label with), and the
   * value search then excluded `i !== nameIdx`, i.e. `i !== -1`, which
   * excludes nothing: column 0 became both the label and the height.
   */
  it('labels with the first column and sizes with a later one', () => {
    expect(chartRows({ step: 's1', columns: ['id', 'total'],
                       rows: [[718, 10], [719, 25]], total: 2, truncated: false }))
      .toEqual([{ name: '718', value: 10 }, { name: '719', value: 25 }])
  })

  it('still prefers a categorical column for the label when there is one', () => {
    expect(chartRows({ step: 's1', columns: ['city', 'n'],
                       rows: [['Cairo', 3]], total: 1, truncated: false }))
      .toEqual([{ name: 'Cairo', value: 3 }])
  })

  it('draws a single numeric column as a count of itself', () => {
    expect(chartRows({ step: 's1', columns: ['id'], rows: [[718], [719]],
                       total: 2, truncated: false }))
      .toEqual([{ name: '718', value: 1 }, { name: '719', value: 1 }])
  })
})

describe('a reply with no query behind it', () => {
  /**
   * A greeting, an analysis or a set of dashboard proposals has no SQL and no
   * rows. "Show SQL" on it is a control that does nothing -- a defect this
   * codebase has shipped before and the reason the buttons are guarded.
   */
  it('offers no SQL controls', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 40, status: 'ok', answer: 'Hello! Ask me about this data.',
      intent: 'chat', error: null, results: [], sql: [] })
    await send('hi')
    await waitFor(() => screen.getByText(/Hello! Ask me about this data\./))
    expect(screen.queryByRole('button', { name: /show sql/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /copy sql/i })).not.toBeInTheDocument()
    // The answer itself is still rated, and still an answer.
    expect(screen.getByRole('button', { name: /good answer/i })).toBeInTheDocument()
  })

  it('keeps them on a reply that did return rows', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 41, status: 'ok', answer: 'Cairo leads.', intent: 'aggregate',
      error: null, results: [RESULT], sql: [SQL] })
    await send('orders per city')
    await waitFor(() => screen.getByText('Cairo leads.'))
    expect(screen.getByRole('button', { name: /show sql/i })).toBeInTheDocument()
  })
})

describe('an answer that asks back with options', () => {
  /**
   * "i need chart" does not say what to chart. The server decides on the rows
   * (services/agent/charts.py) and, when they do not decide it, asks -- with
   * the real column names as ready-to-send messages. A button here is exactly
   * the message it shows: clicking it is the same as typing it, which is what
   * keeps the channel generic.
   */
  const ASKED = {
    run_id: 50, status: 'needs_clarification' as const, intent: null, error: null,
    answer: 'Which two columns should the chart use?',
    results: [], sql: [],
    presentation: { kind: 'choices', options: ['Chart symbol_code by id', 'Chart id by symbol_code'] },
  }

  it('draws each way forward as a button under the question', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ASKED as never)
    await send('i need chart')
    await waitFor(() => screen.getByText(/which two columns/i))
    expect(screen.getByRole('button', { name: 'Chart symbol_code by id' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Chart id by symbol_code' })).toBeInTheDocument()
  })

  it('sends the option exactly as typed would be', async () => {
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue(ASKED as never)
    await send('i need chart')
    await waitFor(() => screen.getByRole('button', { name: 'Chart symbol_code by id' }))
    ask.mockResolvedValue({
      run_id: 51, status: 'ok', answer: 'Here is the result as a bar chart.',
      intent: 'present', error: null, results: [RESULT], sql: [SQL],
      presentation: { format: 'bar', limit: null, x: 'city', y: 'n' },
    } as never)
    fireEvent.click(screen.getByRole('button', { name: 'Chart symbol_code by id' }))
    await waitFor(() =>
      expect(ask).toHaveBeenLastCalledWith(expect.any(Number), 'Chart symbol_code by id'))
    // The choice shows in the thread as the message it was -- so the option
    // text now appears twice: once as the button that was offered, once as
    // the message the person sent by clicking it.
    await waitFor(() =>
      expect(screen.getAllByText('Chart symbol_code by id')).toHaveLength(2))
    expect(await screen.findByTestId('result-chart')).toBeInTheDocument()
  })

  it('leaves the typed input alone when an option is clicked', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ASKED as never)
    await send('i need chart')
    await waitFor(() => screen.getByRole('button', { name: 'Chart id by symbol_code' }))
    const input = screen.getByPlaceholderText(/ask a question/i)
    fireEvent.change(input, { target: { value: 'half a thought' } })
    fireEvent.click(screen.getByRole('button', { name: 'Chart id by symbol_code' }))
    await waitFor(() => expect(input).toHaveValue('half a thought'))
  })

  it('shows no options on a plain clarifying question', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 52, status: 'needs_clarification', intent: null, error: null,
      answer: 'Which metric did you mean?', results: [], sql: [], presentation: null,
    } as never)
    await send('show me the numbers')
    await waitFor(() => screen.getByText(/which metric/i))
    expect(screen.queryByRole('group', { name: /ways to continue/i })).not.toBeInTheDocument()
  })
})

describe('a chart whose columns the server chose', () => {
  it('draws the named columns, not a second guess', () => {
    const result = { step: 's1', columns: ['id', 'symbol_code', 'institute_code'],
                     rows: [[718, 5000, 2], [719, 38, 2]], total: 2, truncated: false }
    expect(chartRows(result, 'id', 'symbol_code'))
      .toEqual([{ name: '718', value: 5000 }, { name: '719', value: 38 }])
  })

  it('falls back to the heuristic when a name is not a column', () => {
    const result = { step: 's1', columns: ['city', 'n'], rows: [['Cairo', 3]],
                     total: 1, truncated: false }
    expect(chartRows(result, 'month', 'revenue')).toEqual([{ name: 'Cairo', value: 3 }])
  })
})

describe('the chat chart says which columns it drew', () => {
  /**
   * "i didnot know what are you drawn what is this data no axis lable how
   * user understand" -- and the chat is the worst case for it: its rows are
   * `{name, value}` by the time they reach the renderer, so an untitled axis
   * would literally read "name" and "value".
   */
  it('names the axes after the two columns', () => {
    const result = { step: 's1', columns: ['id', 'symbol_code'],
                     rows: [[718, 5000], [719, 38]], total: 2, truncated: false }
    expect(chartColumns(result, 'id', 'symbol_code')).toEqual({ x: 'id', y: 'symbol_code' })
  })

  it('falls back to the same columns the heuristic draws', () => {
    const result = { step: 's1', columns: ['city', 'n'], rows: [['Cairo', 3]],
                     total: 1, truncated: false }
    expect(chartColumns(result)).toEqual({ x: 'city', y: 'n' })
    // ...and the rows it draws come from exactly those two columns.
    expect(chartRows(result)).toEqual([{ name: 'Cairo', value: 3 }])
  })

  it('ignores a column name that is not in this result', () => {
    const result = { step: 's1', columns: ['city', 'n'], rows: [['Cairo', 3]],
                     total: 1, truncated: false }
    expect(chartColumns(result, 'month', 'revenue')).toEqual({ x: 'city', y: 'n' })
  })

  // Recharts draws nothing inside a 0x0 ResponsiveContainer and jsdom
  // measures everything as 0x0, so without this the assertion below would
  // pass vacuously against an empty chart. Restored afterwards: the rest of
  // this file asserts on real DOM, not on chart geometry.
  const realRect = Element.prototype.getBoundingClientRect
  beforeEach(() => {
    Element.prototype.getBoundingClientRect = () => ({
      width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400,
      x: 0, y: 0, toJSON() {},
    }) as DOMRect
  })
  afterEach(() => { Element.prototype.getBoundingClientRect = realRect })

  it('draws them on the chart', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 60, status: 'ok', answer: 'Here is the result as a bar chart.',
      intent: 'present', error: null, results: [RESULT], sql: [SQL],
      presentation: { format: 'bar', limit: null, x: 'city', y: 'n' },
    } as never)
    await send('chart n by city')
    const chart = await screen.findByTestId('result-chart')
    await waitFor(() => {
      const titles = [...chart.querySelectorAll('.recharts-label')].map(e => e.textContent)
      expect(titles).toEqual(expect.arrayContaining(['city', 'n']))
    })
  })
})

describe('a grid that no query produced', () => {
  it('says the rows came from the catalog', async () => {
    // "describe this data" answers from the metadata store first and the
    // query second. Both are real; only one is query output, and rows with
    // no SQL behind them are the shape a fabricated answer has.
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 70, status: 'ok', intent: 'describe_data', error: null,
      answer: 'Seventeen tables, and 400 courses in the largest.',
      sql: ['SELECT count(*) FROM mdl_course'],
      results: [
        { step: 'catalog', source: 'catalog', columns: ['table', 'what it holds'],
          rows: [['mdl_course', 'Courses.']], total: 1, truncated: false },
        { step: 's1', source: 'query', columns: ['n'], rows: [[400]],
          total: 1, truncated: false },
      ],
    } as never)
    await send('describe this data')
    await waitFor(() => screen.getByText(/Seventeen tables/))
    expect(screen.getByText(/from the data catalog, not a query/)).toBeInTheDocument()
    // The query's own grid is not captioned that way.
    expect(screen.getAllByText(/from the data catalog/)).toHaveLength(1)
  })
})


// ── Keeping an answer ────────────────────────────────────────────────────────
//
// The chat could read anything and create nothing. Its result actions were
// thumbs, show/copy SQL and three downloads -- so the one thing a person wants
// after "show me X" (keep it, and build on it) meant copying the SQL out and
// re-running it on the Connections page by hand.

describe('saving an answer as a dataset', () => {
  const ANSWER = {
    run_id: 4, status: 'ok' as const, answer: 'Here they are.',
    intent: 'aggregate', error: null,
    sql: ['SELECT region, SUM(amount) AS total FROM orders GROUP BY region'],
    results: [{ columns: ['region', 'total'], rows: [['EU', 12]], total: 1 }],
  }

  it('imports the answer as a dataset on the connection it came from', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANSWER as never)
    vi.spyOn(dataSourcesApi, 'similarDatasets').mockResolvedValue({ matches: [] })
    const imp = vi.spyOn(dataSourcesApi, 'import').mockResolvedValue(
      { id: 9, name: 'Sales by region', row_count: 1, col_count: 2, mode: 'import' })
    await send('sales by region')
    fireEvent.click(await screen.findByLabelText('Save as dataset'))
    await answerPrompt('Sales by region')

    // The same call the AI dashboard proposals make: the agent still creates
    // nothing on its own, a person pressed a button.
    await waitFor(() => expect(imp).toHaveBeenCalledWith(
      2, 'Sales by region', undefined,
      'SELECT region, SUM(amount) AS total FROM orders GROUP BY region', 'import'))
  })

  it('cancelling the name creates nothing', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANSWER as never)
    const imp = vi.spyOn(dataSourcesApi, 'import')

    await send('sales by region')
    fireEvent.click(await screen.findByLabelText('Save as dataset'))
    // The dialog is really there -- asserting on it is what the old
    // `expect(window.prompt).toHaveBeenCalled()` was standing in for.
    expect(await screen.findByRole('dialog', { name: 'Name this dataset' })).toBeInTheDocument()
    await answerPrompt(null)
    expect(imp).not.toHaveBeenCalled()
  })

  it('warns when a dataset already covers it, and honours "no"', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANSWER as never)
    vi.spyOn(dataSourcesApi, 'similarDatasets').mockResolvedValue({
      matches: [{ dataset_id: 3, name: 'Regional sales', mode: 'import',
                  row_count: 40, overlap: 2, coverage: 1,
                  matched_columns: ['region', 'total'], by_name: false }],
    })
    const imp = vi.spyOn(dataSourcesApi, 'import')
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    await send('sales by region')
    fireEvent.click(await screen.findByLabelText('Save as dataset'))
    await answerPrompt('Sales by region')
    await waitFor(() => expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining('Regional sales')))
    expect(imp).not.toHaveBeenCalled()
  })

  it('is not offered in dataset mode, where there is no source to import from', async () => {
    /* A dataset-mode answer runs over frames registered in DuckDB. Offering a
       control that could only fail is the dead-control defect. */
    vi.spyOn(agentApi, 'ask').mockResolvedValue(ANSWER as never)
    render(<ChatPane datasetIds={[5]} />)
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'q' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await screen.findByText('Here they are.')
    expect(screen.queryByLabelText('Save as dataset')).toBeNull()
  })
})

describe('ChatPane accessibility', () => {
  it('has no structural accessibility violations', async () => {
    const { container } = render(<ChatPane dataSourceId={2} />)
    expect(await axeViolations(container)).toEqual([])
  })
})
