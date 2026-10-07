import { act } from 'react'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChatPane from './ChatPane'
import { columnsMentioned } from './clarifyColumns'
import { agentApi, api, llmApi } from '../../services/api'

/** What the Ask AI page kept from the reverted redesign, in v1's look:
 *  column chips on a clarification, "What was wrong?", Edit question, and
 *  the question box locked while the model server is down. */

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const COLUMNS = ['faculty', 'programme', 'final_score']

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
})

const page = () => render(<ChatPane datasetIds={[1]} conversationId={null} datasetColumns={COLUMNS} />)

async function ask(q: string) {
  fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: q } })
  fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
}

describe('columnsMentioned', () => {
  it('finds bold, code and quoted terms that name a column, once each, in order', () => {
    expect(columnsMentioned('By **faculty**, or `Programme`, or "faculty" again, or **department**?', COLUMNS))
      .toEqual(['faculty', 'programme'])
  })
  it('matches spaces to underscores', () => {
    expect(columnsMentioned('Do you mean the **final score**?', COLUMNS)).toEqual(['final_score'])
  })
})

describe('clarification', () => {
  it('offers the columns the reply names as chips, beside the server\'s choices, and sends the pick', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 31, status: 'needs_clarification', intent: null, error: null,
      answer: 'Did you mean the average final score by **faculty**, or a specific **department** column?',
      presentation: { kind: 'choices', options: ['Show all faculties'] } } as any)
    page()
    await ask('average final score by department')
    const group = await screen.findByRole('group', { name: 'Ways to continue' })
    const chips = Array.from(group.querySelectorAll('button')).map(b => b.textContent)
    // Set-apart terms first, then plain mentions (QA B3: "final score").
    expect(chips).toEqual(['Use faculty', 'Use final_score', 'Show all faculties'])
    fireEvent.click(screen.getByRole('button', { name: 'Use faculty' }))
    await waitFor(() => expect(agentApi.ask).toHaveBeenLastCalledWith(7, 'Use faculty'))
  })
})

describe('what was wrong', () => {
  it('asks after a thumbs down and sends the reply as the comment', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 21, status: 'ok', intent: 'aggregate', error: null,
      answer: 'Total is 5.', results: [] } as any)
    const feedback = vi.spyOn(agentApi, 'feedback').mockResolvedValue({ id: 1, run_id: 21, rating: 'down', comment: null })
    page()
    await ask('total')
    fireEvent.click(await screen.findByRole('button', { name: 'Bad answer' }))
    await waitFor(() => expect(feedback).toHaveBeenCalledWith(7, { runId: 21, rating: 'down' }))
    fireEvent.change(screen.getByLabelText('What was wrong?'), { target: { value: 'wrong column' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    await waitFor(() => expect(feedback).toHaveBeenCalledWith(7, { runId: 21, rating: 'down', comment: 'wrong column' }))
    expect(screen.queryByLabelText('What was wrong?')).not.toBeInTheDocument()
  })
})

describe('the answer bar keeps its elements across renders (QA V10)', () => {
  it('a re-render does not replace the buttons, so a click in progress still lands', async () => {
    // The bar was a component declared inside ChatPane: a new type on every
    // render, so React remounted it -- a press whose mousedown fell before a
    // re-render lost its click (the first 👎 "did nothing"), and state inside
    // the bar was dropped.
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 21, status: 'ok', intent: 'aggregate', error: null,
      answer: 'Total is 5.', results: [] } as any)
    vi.spyOn(agentApi, 'feedback').mockResolvedValue({ id: 1, run_id: 21, rating: 'up', comment: null })
    page()
    await ask('total')
    const bad = await screen.findByRole('button', { name: 'Bad answer' })
    fireEvent.click(screen.getByRole('button', { name: 'Good answer' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Good answer' })).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.getByRole('button', { name: 'Bad answer' })).toBe(bad)
  })
})

describe('error', () => {
  it('Edit question puts the question back in the box; Retry asks again', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 40, status: 'failed', answer: null, intent: null,
      error: 'Binder Error: column "grade" not found' } as any)
    page()
    await ask('How many got an A grade?')
    fireEvent.click(await screen.findByRole('button', { name: 'Edit question' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('How many got an A grade?')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(agentApi.ask).toHaveBeenCalledTimes(2))
  })
})

describe('AI offline', () => {
  const endpoints = (ok: boolean) => ({ data: {
    llm_enabled: true, default: 'main', auto_pick: null, source: 'saved',
    endpoints: [{ id: 'main', name: 'Main', model: 'm', enabled: true, is_default: true, strength: 5, context: null,
      status: { ok } }],
  } })

  it('reads the top bar\'s /llm/endpoints answer: down locks the question box with a line saying why', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(endpoints(false) as any)
    page()
    // What the top bar's poll does; the page does not poll by itself.
    await act(async () => { await llmApi.endpoints() })
    expect(await screen.findByTestId('ai-offline')).toHaveTextContent('The model server isn’t reachable, so new questions are paused.')
    const box = screen.getByRole('textbox', { name: 'Your question' })
    expect(box).toBeDisabled()
    expect(box).toHaveAttribute('placeholder', 'New questions are paused while the model server is unreachable')
    vi.mocked(api.get).mockResolvedValue(endpoints(true) as any)
    await act(async () => { await llmApi.endpoints() })
    await waitFor(() => expect(screen.queryByTestId('ai-offline')).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Your question' })).not.toBeDisabled()
  })

  it('never locks the builder mount', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(endpoints(false) as any)
    render(<ChatPane datasetIds={[1]} />)
    await act(async () => { await llmApi.endpoints() })
    expect(screen.queryByTestId('ai-offline')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Your question' })).not.toBeDisabled()
  })
})
