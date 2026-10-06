import { useState } from 'react'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChatPane from './ChatPane'
import { keyNumbers } from './AnswerCard'
import { agentApi } from '../../services/api'

/** The Ask AI page's answer card (redesign 4a), driven through ChatPane's
 *  page variant: the latest answer full, older ones compact. */

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const RESULT = {
  step: 's1', columns: ['faculty', 'avg_score'], total: 4, truncated: false,
  rows: [['Medicine', 83.89], ['Engineering', 71.41], ['Law', 68.23], ['Arts', 61.54]],
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  vi.spyOn(agentApi, 'runDetail').mockResolvedValue({
    ms: 2400, context_objects: ['enrolments'],
    plan: [{ id: 'q1', question: 'average of final_score, grouped by faculty' }],
    steps: [{ sql: 'SELECT faculty, AVG(final_score) FROM t GROUP BY 1', status: 'ok', rows_returned: 4, repair_attempts: 0 }],
  })
  vi.spyOn(agentApi, 'ask').mockResolvedValue({
    run_id: 21, status: 'ok', intent: 'aggregate', error: null,
    answer: 'Medicine scores highest, averaging 83.9; Arts is lowest at 61.5.',
    results: [RESULT] as any, sql: ['SELECT 1'],
  })
})

async function ask(q = 'average final score by faculty') {
  render(<ChatPane datasetIds={[1]} conversationId={null} variant="page" datasetName="Enrolments 2025"
    suggestions={['Average final score by programme', 'Average attendance by faculty', q]} />)
  fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: q } })
  fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
  return screen.findByTestId('answer-card')
}

describe('keyNumbers', () => {
  it('reads highest, lowest and the gap from the rows', () => {
    const k = keyNumbers(RESULT as any)!
    expect(k.hi).toEqual({ label: 'Medicine', value: 83.89 })
    expect(k.lo).toEqual({ label: 'Arts', value: 61.54 })
    expect(k.gap).toBeCloseTo(22.35)
    expect(k.groups).toBe(4)
  })
  it('has nothing to say about one row', () => {
    expect(keyNumbers({ ...RESULT, rows: [['A', 1]], total: 1 } as any)).toBeNull()
  })
})

describe('the answer card', () => {
  it('shows the dataset, the time, key numbers, rows and how it was worked out', async () => {
    const card = await ask()
    expect(within(card).getByText('· Enrolments 2025')).toBeInTheDocument()
    expect(await within(card).findByText('2.4 s')).toBeInTheDocument()
    const keys = within(card).getByTestId('key-numbers')
    expect(keys).toHaveTextContent('Highest')
    expect(keys).toHaveTextContent('Medicine')
    expect(keys).toHaveTextContent('Arts')
    expect(within(card).getByText('Rows (4)')).toBeInTheDocument()
    const steps = within(card).getByTestId('answer-steps')
    expect(steps).toHaveTextContent('average of final_score, grouped by faculty')
    expect(steps).toHaveTextContent('Wrote 1 query')
    expect(steps).toHaveTextContent('4 rows back')
    // The chart shows alone: its rows are beside it, not behind a toggle.
    expect(within(card).queryByRole('button', { name: /show rows/i })).not.toBeInTheDocument()
  })

  it('offers two starter questions not asked yet', async () => {
    const card = await ask()
    const next = within(card).getByRole('group', { name: 'Ask next' })
    expect(within(next).getAllByRole('button').map(b => b.textContent?.trim()))
      .toEqual(['Average final score by programme', 'Average attendance by faculty'])
  })

  it('keeps the latest answer full and folds older ones to compact', async () => {
    await ask()
    fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: 'again' } })
    fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
    await waitFor(() => expect(screen.getAllByTestId('answer-card-compact')).toHaveLength(1))
    expect(screen.getAllByTestId('answer-card')).toHaveLength(1)
  })

  it('asks what was wrong after a thumbs down and sends it as the comment', async () => {
    const feedback = vi.spyOn(agentApi, 'feedback').mockResolvedValue({ id: 1, run_id: 21, rating: 'down', comment: null })
    const card = await ask()
    fireEvent.click(within(card).getByRole('button', { name: 'Bad answer' }))
    await waitFor(() => expect(feedback).toHaveBeenCalledWith(7, { runId: 21, rating: 'down' }))
    fireEvent.change(within(card).getByLabelText('What was wrong?'), { target: { value: 'wrong column' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(feedback).toHaveBeenCalledWith(7, { runId: 21, rating: 'down', comment: 'wrong column' }))
  })

  it('opens the SQL from Show SQL and exports from one menu', async () => {
    const card = await ask()
    fireEvent.click(within(card).getByRole('button', { name: 'Show SQL' }))
    expect(within(card).getByText('SELECT 1')).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Export' }))
    expect(await screen.findByRole('menuitem', { name: 'CSV' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Excel' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'PDF' })).toBeInTheDocument()
  })

  it('puts a column from the side panel into the question box', () => {
    function Harness() {
      const [req, setReq] = useState<{ text: string; seq: number } | null>(null)
      return (<>
        <button onClick={() => setReq(r => ({ text: r ? 'region' : 'revenue', seq: (r?.seq ?? 0) + 1 }))}>col</button>
        <ChatPane datasetIds={[1]} conversationId={null} variant="page" insertRequest={req} />
      </>)
    }
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'col' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('revenue')
    fireEvent.click(screen.getByRole('button', { name: 'col' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('revenue region')
  })
})
