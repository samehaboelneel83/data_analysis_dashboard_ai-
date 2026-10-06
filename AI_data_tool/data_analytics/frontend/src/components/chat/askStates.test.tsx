import { act } from 'react'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../test/renderWithProviders'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChatPane from './ChatPane'
import { columnsMentioned } from './pageStates'
import { agentApi, api, llmApi } from '../../services/api'

/** The Ask AI page's states (redesign 4b), through ChatPane's page variant. */

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const COLUMNS = ['faculty', 'programme', 'final_score']

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
  vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  vi.spyOn(agentApi, 'messages').mockResolvedValue([])
})

const pane = (extra: Record<string, unknown> = {}) => render(
  <MemoryRouter>
    <ChatPane datasetIds={[1]} conversationId={null} variant="page" datasetName="Enrolments 2025"
      datasetColumns={COLUMNS} columnValues={{ faculty: 4 }} scopeRows={3612}
      suggestions={['Average final score by faculty', 'Monthly enrolments in 2025', 'Pass rate', 'Attendance vs score', 'Fifth']}
      {...extra} />
  </MemoryRouter>,
)

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

describe('first run', () => {
  it('names the data, offers four starters and says how it works', () => {
    pane()
    expect(screen.getByRole('heading', { name: 'Ask Enrolments 2025 anything' })).toBeInTheDocument()
    expect(screen.getByText('Enrolments 2025 · 3,612 rows')).toBeInTheDocument()
    const starters = within(screen.getByRole('group', { name: /suggested/i })).getAllByRole('button')
    expect(starters).toHaveLength(4)
    expect(screen.getByText('See how it was answered')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Ask a question about Enrolments 2025…')).toBeInTheDocument()
  })
})

describe('clarification', () => {
  beforeEach(() => {
    vi.spyOn(agentApi, 'ask').mockImplementation(async (_c, q) => (q.startsWith('Use ')
      ? { run_id: 32, status: 'ok', intent: 'aggregate', error: null, answer: 'Medicine is highest.', results: [] }
      : { run_id: 31, status: 'needs_clarification', intent: null, error: null,
          answer: 'Did you mean the average final score by **faculty**, or a specific **department** column?' }) as any)
  })

  it('offers the columns the reply names, with their value count, and sends the pick', async () => {
    pane()
    await ask('average final score by department')
    const card = await screen.findByTestId('clarify-card')
    expect(within(card).getByText('Needs one detail')).toBeInTheDocument()
    const option = within(card).getByRole('button', { name: /Use faculty/ })
    expect(option).toHaveTextContent('A column in Enrolments 2025 · 4 values')
    expect(within(card).queryByRole('button', { name: /department/ })).not.toBeInTheDocument()
    fireEvent.click(option)
    await waitFor(() => expect(agentApi.ask).toHaveBeenLastCalledWith(7, 'Use faculty'))
    // Answered: the card folds to one line and the pick is not repeated as a bubble.
    expect(await screen.findByTestId('clarify-resolved')).toHaveTextContent('Needs one detail · You chose Use faculty')
    expect(screen.queryByText('Use faculty', { selector: '.dl-turn__q-text' })).not.toBeInTheDocument()
  })

  it('takes an answer in the person\'s own words', async () => {
    pane()
    await ask('average final score by department')
    const card = await screen.findByTestId('clarify-card')
    const own = within(card).getByRole('textbox', { name: 'Or type your answer…' })
    fireEvent.change(own, { target: { value: 'by programme' } })
    fireEvent.submit(own.closest('form')!)
    await waitFor(() => expect(agentApi.ask).toHaveBeenLastCalledWith(7, 'by programme'))
  })
})

describe('error', () => {
  it('offers Try again and Edit question, with the technical details open', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 40, status: 'failed', answer: null, intent: null,
      error: 'Binder Error: Referenced column "grade" not found' } as any)
    pane()
    await ask('How many got an A grade?')
    expect(await screen.findByText('Could not answer that')).toBeInTheDocument()
    expect(screen.getByText(/Binder Error/).closest('details')).toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'Edit question' }))
    expect(screen.getByPlaceholderText(/ask/i)).toHaveValue('How many got an A grade?')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(agentApi.ask).toHaveBeenCalledTimes(2))
  })
})

describe('AI offline', () => {
  const endpoints = (ok: boolean) => ({ data: {
    llm_enabled: true, default: 'main', auto_pick: null, source: 'saved',
    endpoints: [{ id: 'main', name: 'Main', model: 'm', enabled: true, is_default: true, strength: 5, context: null,
      status: { ok } }],
  } })

  it('reads the top bar\'s /llm/endpoints answer: down pauses new questions, past answers stay', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(endpoints(false) as any)
    pane()
    // What the top bar's poll does; the page does not poll by itself.
    await act(async () => { await llmApi.endpoints() })
    const banner = await screen.findByTestId('ai-offline')
    expect(banner).toHaveTextContent('The model server isn’t reachable, so new questions are paused.')
    expect(within(banner).getByRole('link', { name: /Explore Enrolments 2025 without AI/ }))
      .toHaveAttribute('href', '/datasets/1?tab=data')
    expect(within(banner).getByRole('link', { name: /Build a chart yourself/ })).toHaveAttribute('href', '/reports?new=1')
    expect(screen.getByRole('textbox', { name: 'Your question' })).toBeDisabled()
    // Back up: the banner goes and the box opens.
    vi.mocked(api.get).mockResolvedValue(endpoints(true) as any)
    await act(async () => { await llmApi.endpoints() })
    await waitFor(() => expect(screen.queryByTestId('ai-offline')).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Your question' })).not.toBeDisabled()
  })

  it('never locks the builder mount', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(endpoints(false) as any)
    render(<MemoryRouter><ChatPane datasetIds={[1]} /></MemoryRouter>)
    await act(async () => { await llmApi.endpoints() })
    expect(screen.queryByTestId('ai-offline')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Your question' })).not.toBeDisabled()
  })
})
