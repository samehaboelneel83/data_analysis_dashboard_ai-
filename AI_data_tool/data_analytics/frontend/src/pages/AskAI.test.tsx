import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AskAI from './AskAI'

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

const renderAt = (path: string) => render(
  <MemoryRouter initialEntries={[path]}><AskAI /></MemoryRouter>,
)

describe('AskAI', () => {
  it('mounts nothing until a scope is picked -- a question needs a target', async () => {
    renderAt('/ask')
    expect(await screen.findByText(/Pick a dataset or connection/)).toBeInTheDocument()
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

  it('picking a scope in the select mounts the pane for it', async () => {
    renderAt('/ask')
    const select = await screen.findByLabelText('What to ask about')
    await waitFor(() => expect(screen.getByText('Orders')).toBeInTheDocument())
    fireEvent.change(select, { target: { value: 'd:32' } })
    expect(await screen.findByTestId('chat-pane')).toHaveTextContent('datasets:32')
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
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /delete orders by city/i }))
    await waitFor(() => expect(agentApi.remove).toHaveBeenCalledWith(55))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Orders by city/ })).not.toBeInTheDocument())
    expect(screen.getByTestId('chat-pane')).toHaveTextContent('conversation:null')
  })

  it('a declined confirm deletes nothing', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderAt('/ask?dataset=32')
    await screen.findByRole('list', { name: /conversations/i })
    fireEvent.click(screen.getByRole('button', { name: /delete orders by city/i }))
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
    await screen.findByLabelText('What to ask about')
    await waitFor(() => expect(screen.getByText('Orders')).toBeInTheDocument(),
                  { timeout: 5000 })
    expect(screen.queryByText('Live orders')).not.toBeInTheDocument()
    expect(screen.getByText('Warehouse')).toBeInTheDocument()
  })
})
