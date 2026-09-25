import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import Composer from './Composer'
import AnswerText from './AnswerText'
import ChatPane from './ChatPane'
import DataPicker from '../../pages/ask/DataPicker'
import { agentApi } from '../../services/api'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

function Harness({ onSend }: { onSend: (v: string) => void }) {
  const [v, setV] = useState('')
  return <Composer value={v} onChange={setV} onSend={() => { onSend(v); setV('') }} />
}

describe('Composer', () => {
  it('Enter sends, Shift+Enter does not', () => {
    const onSend = vi.fn()
    render(<Harness onSend={onSend} />)
    const box = screen.getByRole('textbox', { name: 'Your question' })
    fireEvent.change(box, { target: { value: 'total sales' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('total sales')
  })

  it('an empty box sends nothing, and the counter counts', () => {
    const onSend = vi.fn()
    render(<Harness onSend={onSend} />)
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'abc' } })
    expect(screen.getByText('3 / 2000')).toBeInTheDocument()
  })

  it('locked: visible, inert, and says why', () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} locked lockedHint="Choose your data first" />)
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByPlaceholderText('Choose your data first')).toBeInTheDocument()
  })
})

describe('AnswerText', () => {
  it('marks the numbers, left-to-right, and keeps the sentence whole', () => {
    render(<AnswerText text="Revenue rose 12.5% to 1,240,000 in March." />)
    const marks = screen.getByTestId('answer-text').querySelectorAll('mark')
    expect([...marks].map(m => m.textContent)).toEqual(['12.5%', '1,240,000'])
    marks.forEach(m => expect(m).toHaveAttribute('dir', 'ltr'))
    expect(screen.getByTestId('answer-text')).toHaveTextContent('Revenue rose 12.5% to 1,240,000 in March.')
  })
})

describe('DataPicker', () => {
  const ITEMS = [
    { key: 'd:1', kind: 'dataset' as const, name: 'Sales 2026', rows: 12400, cols: 9, updated: '2026-09-01T00:00:00' },
    { key: 's:3', kind: 'source' as const, name: 'Warehouse', sourceType: 'postgres' },
  ]
  beforeEach(() => localStorage.removeItem('datalytics.ask.recent'))

  it('shows size and freshness, and chooses with the keyboard', () => {
    const onChoose = vi.fn()
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={onChoose} /></MemoryRouter>)
    fireEvent.keyDown(screen.getByRole('button', { name: 'What to ask about' }), { key: 'ArrowDown' })
    const opts = screen.getAllByRole('option')
    expect(opts[0]).toHaveTextContent('12,400 rows')
    expect(opts[0]).toHaveTextContent('9 columns')
    expect(screen.getByRole('option', { name: /Warehouse/ })).toHaveTextContent('postgres')
    const search = screen.getByRole('combobox')
    fireEvent.keyDown(search, { key: 'End' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChoose).toHaveBeenCalledWith('s:3')
    expect(JSON.parse(localStorage.getItem('datalytics.ask.recent')!)).toEqual(['s:3'])
  })

  it('puts recent picks first', () => {
    localStorage.setItem('datalytics.ask.recent', JSON.stringify(['s:3']))
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'What to ask about' }))
    expect(screen.getByRole('group', { name: 'Recent' })).toHaveTextContent('Warehouse')
  })

  it('Escape closes it', () => {
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'What to ask about' }))
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})

describe('ChatPane — the redesigned turns', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
    vi.spyOn(agentApi, 'messages').mockResolvedValue([])
    vi.spyOn(agentApi, 'listConversations').mockResolvedValue([])
  })

  it('starts with suggestion chips that ask when clicked', async () => {
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'ok', intent: null, error: null })
    render(<ChatPane datasetIds={[1]} suggestions={['Total revenue by region', 'How many rows are there?']} />)
    fireEvent.click(screen.getByRole('button', { name: /Total revenue by region/ }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(7, 'Total revenue by region'))
  })

  it('a failure gets a friendly card, rephrasings, and the raw error folded away', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 3, status: 'failed', answer: null, intent: null, error: 'no such column: discount' })
    render(<ChatPane datasetIds={[1]} suggestions={['Total revenue by region']} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'total discounts' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Could not answer that')).toBeInTheDocument()
    expect(screen.getByText('Technical details')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Try instead' })).toHaveTextContent('Total revenue by region')
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
  })

  it('offers "Add to dashboard" only for an answer the report engine can rebuild', async () => {
    const ask = vi.spyOn(agentApi, 'ask')
    ask.mockResolvedValueOnce({
      run_id: 5, status: 'ok', answer: 'North leads.', intent: 'aggregate', error: null,
      results: [{ step: 's1', columns: ['region', 'total'], rows: [['North', 10], ['South', 4]], total: 2, truncated: false }],
      sql: ['SELECT region, SUM(revenue) AS total FROM t GROUP BY region'] })
    render(<ChatPane datasetIds={[1]} datasetColumns={['region', 'revenue']} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'revenue by region' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('button', { name: 'Add to dashboard' })).toBeInTheDocument()

    ask.mockResolvedValueOnce({
      run_id: 6, status: 'ok', answer: 'Ratio.', intent: 'aggregate', error: null,
      results: [{ step: 's1', columns: ['region', 'ratio'], rows: [['North', 1.5], ['South', 2]], total: 2, truncated: false }],
      sql: ['SELECT region, SUM(revenue)/COUNT(*) AS ratio FROM t GROUP BY region'] })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ratio' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText('Ratio.')
    expect(screen.getAllByRole('button', { name: 'Add to dashboard' })).toHaveLength(1)
  })
})
