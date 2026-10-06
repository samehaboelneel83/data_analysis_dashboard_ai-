import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AskAI from './AskAI'
import { renderWithProviders } from '../test/renderWithProviders'

/**
 * The page's whole job is scope resolution: turn a URL or a picker choice
 * into the right ChatPane props. The pane itself has its own tests, so it is
 * mocked to a probe that reports what it was given.
 */

vi.mock('../components/chat/ChatPane', () => ({
  default: (props: { dataSourceId?: number; datasetIds?: number[]; conversationId?: number | null
                     onConversationCreated?: (c: { id: number; title: string }) => void }) => (
    <div data-testid="chat-pane">
      {props.dataSourceId != null ? `source:${props.dataSourceId}` : `datasets:${props.datasetIds?.join(',')}`}
      {` conversation:${props.conversationId === undefined ? 'unset' : String(props.conversationId)}`}
      <button onClick={() => props.onConversationCreated?.({ id: 99, title: 'Made by pane' })}>
        probe-create
      </button>
    </div>
  ),
}))

vi.mock('../services/api', () => ({
  datasetsApi: { list: vi.fn() },
  dataSourcesApi: { list: vi.fn() },
  agentApi: { listConversations: vi.fn(), rename: vi.fn(), remove: vi.fn() },
}))

import { datasetsApi, dataSourcesApi, agentApi } from '../services/api'

beforeEach(() => {
  vi.clearAllMocks()
  // `filename` is part of every DatasetOut the API sends; an import dataset
  // always has one. Leaving it off here would let the picker's filter pass a
  // shape the server never produces.
  vi.mocked(datasetsApi.list).mockResolvedValue([
    { id: 32, name: 'Orders', mode: 'import', filename: 'orders.csv' } as any,
  ])
  vi.mocked(dataSourcesApi.list).mockResolvedValue([
    { id: 3, name: 'Warehouse' } as any,
  ])
  vi.mocked(agentApi.listConversations).mockResolvedValue([])
  vi.mocked(agentApi.rename).mockImplementation(async (id, title) => ({ id, title }))
  vi.mocked(agentApi.remove).mockResolvedValue(undefined)
})

const renderAt = (path: string) => renderWithProviders(
  <MemoryRouter initialEntries={[path]}><AskAI /></MemoryRouter>,
)

describe('AskAI', () => {
  it('mounts nothing until a scope is picked -- a question needs a target', async () => {
    renderAt('/ask')
    expect(await screen.findByText('Choose your data')).toBeInTheDocument()
    expect(screen.queryByTestId('chat-pane')).not.toBeInTheDocument()
  })

  it('deep-links to a dataset scope: /ask?dataset=32 -> ChatPane datasetIds=[32]', async () => {
    renderAt('/ask?dataset=32')
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('datasets:32')
  })

  it('deep-links to a source scope: /ask?source=3 -> ChatPane dataSourceId=3', async () => {
    renderAt('/ask?source=3')
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('source:3')
  })

  it('picking a scope in the picker mounts the pane for it', async () => {
    renderAt('/ask')
    const trigger = await screen.findByRole('button', { name: 'What to ask about' })
    await waitFor(() => expect(trigger).not.toBeDisabled())
    fireEvent.click(trigger)
    fireEvent.click(await screen.findByRole('option', { name: /Orders/ }))
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('datasets:32')
  })

  it('the picker searches, and says what each choice is', async () => {
    renderAt('/ask')
    const trigger = await screen.findByRole('button', { name: 'What to ask about' })
    await waitFor(() => expect(trigger).not.toBeDisabled())
    fireEvent.click(trigger)
    const search = await screen.findByRole('combobox', { name: /search/i })
    expect(screen.getAllByRole('option').map(o => o.textContent)).toEqual(
      expect.arrayContaining([expect.stringMatching(/Warehouse/)]))
    fireEvent.change(search, { target: { value: 'ware' } })
    expect(screen.getAllByRole('option')).toHaveLength(1)
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('source:3')
  })

  it('before a scope is picked, shows only the data step -- no locked question box', async () => {
    // The locked composer was a second control nobody could use; the question
    // box now appears only once data is chosen.
    renderAt('/ask')
    expect(await screen.findByRole('heading', { name: 'Ask your data anything' })).toBeInTheDocument()
    expect(screen.getByText('Choose your data')).toBeInTheDocument()
    expect(screen.queryByText(/Step \d/)).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Your question' })).not.toBeInTheDocument()
  })

  it('a failed dataset list is an error, never "no data yet"', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValue(new Error('boom'))
    renderAt('/ask')
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load your data')
    expect(screen.queryByText(/No data yet/)).not.toBeInTheDocument()
  })

  it('says so when there is no data to ask about', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([])
    vi.mocked(dataSourcesApi.list).mockResolvedValue([])
    renderAt('/ask')
    expect(await screen.findByText(/No data yet/)).toBeInTheDocument()
  })
})

describe('AskAI — the history panel', () => {
  it('groups today\'s threads apart from earlier ones', async () => {
    const now = new Date().toISOString()
    vi.mocked(agentApi.listConversations).mockResolvedValue([
      { id: 60, title: 'Fresh', data_source_id: null, dataset_ids: [32], created_at: now },
      { id: 50, title: 'Stale', data_source_id: null, dataset_ids: [32], created_at: '2020-01-01T08:00:00' },
    ] as any)
    renderAt('/ask?dataset=32')
    const list = await screen.findByRole('list', { name: /conversations/i })
    const text = list.textContent ?? ''
    expect(text.indexOf('Today')).toBeLessThan(text.indexOf('Fresh'))
    expect(text.indexOf('Earlier')).toBeGreaterThan(text.indexOf('Fresh'))
    expect(text.indexOf('Earlier')).toBeLessThan(text.indexOf('Stale'))
  })

  it('folds to a rail and remembers it', async () => {
    localStorage.removeItem('datalytics.ask.historyFolded')
    renderAt('/ask?dataset=32')
    fireEvent.click(await screen.findByRole('button', { name: 'Collapse history' }))
    expect(screen.getByRole('button', { name: 'Expand history' })).toBeInTheDocument()
    expect(localStorage.getItem('datalytics.ask.historyFolded')).toBe('1')
    localStorage.removeItem('datalytics.ask.historyFolded')
  })
})

describe('AskAI — the conversation list', () => {
  const CONVS = [
    { id: 55, title: 'Orders by city', data_source_id: null, dataset_ids: [32], created_at: '2026-09-03T08:00:00' },
    { id: 54, title: 'Older orders chat', data_source_id: null, dataset_ids: [32], created_at: '2026-09-02T08:00:00' },
    { id: 40, title: 'Warehouse chat', data_source_id: 3, dataset_ids: null, created_at: '2026-09-01T08:00:00' },
    { id: 12, title: 'Other dataset', data_source_id: null, dataset_ids: [7], created_at: '2026-08-30T08:00:00' },
  ]
  beforeEach(() => vi.mocked(agentApi.listConversations).mockResolvedValue(CONVS))

  it('lists only the threads about the current scope and opens the newest', async () => {
    renderAt('/ask?dataset=32')
    const list = await screen.findByRole('list', { name: /conversations/i })
    expect(list).toHaveTextContent('Orders by city')
    expect(list).toHaveTextContent('Older orders chat')
    expect(list).not.toHaveTextContent('Warehouse chat')
    expect(list).not.toHaveTextContent('Other dataset')
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:55')
  })

  it('a source scope lists the source threads', async () => {
    renderAt('/ask?source=3')
    const list = await screen.findByRole('list', { name: /conversations/i })
    expect(list).toHaveTextContent('Warehouse chat')
    expect(list).not.toHaveTextContent('Orders by city')
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:40')
  })

  it('picking another thread hands its id to the pane', async () => {
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    // The title button's name starts with the title; Rename/Delete start
    // with their verb.
    fireEvent.click(screen.getByRole('button', { name: /^Older orders chat/ }))
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:54')
  })

  it('New chat opens an empty pane, and the pane reports the thread it creates', async () => {
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /new chat/i }))
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:null')
    fireEvent.click(screen.getByText('probe-create'))
    expect(await screen.findByRole('button', { name: /^Made by pane/ })).toBeInTheDocument()
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:99')
  })

  it('with no thread for the scope yet, the pane starts empty', async () => {
    renderAt('/ask?dataset=7')
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('conversation:12')
    vi.mocked(agentApi.listConversations).mockResolvedValue([])
    renderAt('/ask?dataset=8')
    await waitFor(() =>
      expect(screen.getAllByTestId('chat-pane').at(-1)).toHaveTextContent('conversation:null'))
  })

  it('renames a thread in place', async () => {
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /rename orders by city/i }))
    const input = screen.getByRole('textbox', { name: /title/i })
    fireEvent.change(input, { target: { value: 'Cities' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(agentApi.rename).toHaveBeenCalledWith(55, 'Cities'))
    expect(agentApi.rename).toHaveBeenCalledTimes(1)   // Enter, then blur: one PATCH
    expect(await screen.findByRole('button', { name: /^Cities/ })).toBeInTheDocument()
  })

  it('deletes a thread after confirming, and empties the pane if it was open', async () => {
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /delete orders by city/i }))
    // The app's own dialog, not window.confirm.
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete this conversation?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(agentApi.remove).toHaveBeenCalledWith(55))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Orders by city/ })).not.toBeInTheDocument())
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:null')
  })

  it('a declined confirm deletes nothing', async () => {
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /delete orders by city/i }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete this conversation?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(agentApi.remove).not.toHaveBeenCalled()
  })

  // A DirectQuery dataset keeps its rows in the connection, so it has no file
  // for the agent's dataset mode to read and the backend refuses it with a
  // 400. Offering it here is offering a dead option: the connection it reads
  // from is already in this same list, under Connections.
  it('leaves DirectQuery datasets out of the picker', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 32, name: 'Orders', mode: 'import', filename: 'orders.csv' } as any,
      { id: 167, name: 'Live orders', mode: 'directquery', filename: null } as any,
    ])
    renderAt('/ask')
    const trigger = await screen.findByRole('button', { name: 'What to ask about' })
    await waitFor(() => expect(trigger).not.toBeDisabled())
    fireEvent.click(trigger)
    await waitFor(() => expect(screen.getByText('Orders')).toBeInTheDocument(),
                  { timeout: 5000 })
    expect(screen.queryByText('Live orders')).not.toBeInTheDocument()
    expect(screen.getByText('Warehouse')).toBeInTheDocument()
  })
})
