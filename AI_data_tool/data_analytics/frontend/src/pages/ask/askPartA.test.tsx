import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import DataPicker from './DataPicker'
import SuggestionGrid from './SuggestionGrid'
import AskHero from './AskHero'
import ChatPane from '../../components/chat/ChatPane'
import { datasetSuggestionCards, connectionSuggestionCards } from './suggestions'
import { agentApi } from '../../services/api'
import { translate } from '../../i18n'
import { DirectionProvider } from '../../contexts/DirectionContext'

/** Step 10, Part A: the picker, the suggestion cards and the hero. */
const en = ((k: string, v?: Record<string, string | number>) => translate('en', k as never, v)) as never

const COLUMNS = [
  { name: 'order_id', dtype: 'integer' }, { name: 'region', dtype: 'text' }, { name: 'channel', dtype: 'text' },
  { name: 'order_date', dtype: 'datetime' }, { name: 'revenue', dtype: 'float' },
]

describe('suggestion cards, from the dataset\'s own columns', () => {
  it('name the real columns each question uses, raw, and never an id', () => {
    const cards = datasetSuggestionCards(COLUMNS as never, en)
    expect(cards.length).toBeGreaterThanOrEqual(4)
    expect(cards.length).toBeLessThanOrEqual(6)
    expect(cards[0]).toEqual({ text: 'Total revenue by region', icon: 'total', columns: ['region', 'revenue'] })
    expect(cards.find(c => c.icon === 'trend')?.columns).toEqual(['order_date', 'revenue'])
    const named = new Set(cards.flatMap(c => c.columns))
    for (const c of named) expect(COLUMNS.map(x => x.name)).toContain(c)
    expect(named.has('order_id')).toBe(false)
  })

  it('fall back to generic questions, with no columns named, when the columns say little', () => {
    const cards = datasetSuggestionCards([], en)
    expect(cards.every(c => c.columns.length === 0)).toBe(true)
    expect(connectionSuggestionCards(en).every(c => c.columns.length === 0)).toBe(true)
  })

  it('a card asks its question; its columns are shown left to right', () => {
    const onAsk = vi.fn()
    render(<SuggestionGrid cards={datasetSuggestionCards(COLUMNS as never, en)} onAsk={onAsk} />)
    const card = screen.getByRole('button', { name: /Total revenue by region/ })
    expect(card.querySelector('small')).toHaveAttribute('dir', 'ltr')
    expect(card.querySelector('small')).toHaveTextContent('region · revenue')
    fireEvent.click(card)
    expect(onAsk).toHaveBeenCalledWith('Total revenue by region')
  })
})

describe('the hero', () => {
  it('numbers its step and puts the last word of the headline in the accent', () => {
    render(<AskHero id="h" title="Ask your data anything" sub="sub" step={2} stepLabel="Ask a question" />)
    expect(screen.getByRole('heading', { name: 'Ask your data anything' })).toBeInTheDocument()
    expect(screen.getByText('anything')).toHaveClass('dl-hero__accent')
    expect(screen.getByText('Step 2')).toBeInTheDocument()
  })
})

describe('the picker (step 10)', () => {
  const ITEMS = [
    { key: 'd:1', kind: 'dataset' as const, name: 'Sales 2026', rows: 12400, cols: 9, updated: '2026-09-01T00:00:00' },
    { key: 'd:2', kind: 'dataset' as const, name: 'Orders', rows: 1, cols: 2 },
    { key: 's:3', kind: 'source' as const, name: 'Warehouse', sourceType: 'postgres' },
  ]
  beforeEach(() => localStorage.removeItem('datalytics.ask.recent'))
  const open = () => fireEvent.click(screen.getByRole('button', { name: 'What to ask about' }))

  it('the large trigger counts what there is, and names the last pick', () => {
    localStorage.setItem('datalytics.ask.recent', JSON.stringify(['d:2']))
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'What to ask about' })).toHaveTextContent('2 datasets · 1 connection · Try: Orders')
  })

  it('tabs narrow the list to datasets or to connections', () => {
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    open()
    fireEvent.click(screen.getByRole('tab', { name: 'Connections' }))
    expect(screen.getAllByRole('option').map(o => o.getAttribute('data-value'))).toEqual(['s:3'])
    fireEvent.click(screen.getByRole('tab', { name: 'Datasets' }))
    expect(screen.getAllByRole('option').map(o => o.getAttribute('data-value'))).toEqual(['d:1', 'd:2'])
  })

  it('marks the typed part of a name, and says when nothing matches', () => {
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    open()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ware' } })
    const opt = screen.getAllByRole('option').find(o => o.getAttribute('data-value') === 's:3')!
    expect(within(opt).getByText('Ware').tagName).toBe('B')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'zzz' } })
    expect(screen.getByText('No matches for “zzz”')).toBeInTheDocument()
  })

  it('counts with plurals: one row, one column', () => {
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter>)
    open()
    expect(screen.getByRole('option', { name: /Orders/ })).toHaveTextContent('1 row · 2 columns')
  })

  describe('in Arabic', () => {
    beforeEach(() => localStorage.setItem('datalytics.language', 'ar'))
    afterEach(() => localStorage.removeItem('datalytics.language'))
    it('counts with Arabic plurals', () => {
      const { container } = render(<DirectionProvider><MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} /></MemoryRouter></DirectionProvider>)
      expect(container.querySelector('.dl-pick__l2')).toHaveTextContent('مجموعتا بيانات · اتصال واحد')
    })
  })
})

describe('ChatPane start view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
    vi.spyOn(agentApi, 'messages').mockResolvedValue([])
  })

  it('an empty thread shows the page\'s start view, whose cards ask through the pane', async () => {
    const ask = vi.spyOn(agentApi, 'ask').mockResolvedValue({ run_id: 1, status: 'ok', answer: 'ok', intent: null, error: null })
    render(<ChatPane datasetIds={[1]} conversationId={null} suggestions={['x']}
      startView={send => <button type="button" onClick={() => send('Total revenue by region')}>card</button>} />)
    expect(screen.queryByText('Try one of these to start')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'card' }))
    await waitFor(() => expect(ask).toHaveBeenCalledWith(7, 'Total revenue by region'))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'card' })).not.toBeInTheDocument())
  })
})
