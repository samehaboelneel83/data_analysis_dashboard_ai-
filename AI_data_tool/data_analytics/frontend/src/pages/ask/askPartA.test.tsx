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
    fireEvent.click(screen.getByRole('tab', { name: /^Connections/ }))
    expect(screen.getAllByRole('option').map(o => o.getAttribute('data-value'))).toEqual(['s:3'])
    fireEvent.click(screen.getByRole('tab', { name: /^Datasets/ }))
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

describe('the inline chooser (empty page, owner\'s change)', () => {
  const ITEMS = [
    { key: 'd:1', kind: 'dataset' as const, name: 'Sales 2026', rows: 12400, cols: 9 },
    { key: 's:3', kind: 'source' as const, name: 'Warehouse', sourceType: 'postgres' },
  ]
  it('is open without a trigger: Step 1, search, tabs, the list and Upload', () => {
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={() => {}} size="inline" /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: 'What to ask about' })).not.toBeInTheDocument()
    expect(screen.getByText('Step 1')).toBeInTheDocument()
    expect(screen.getByRole('combobox')).toBeInTheDocument()
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(screen.getAllByRole('option')).toHaveLength(2)
    expect(screen.getByRole('link', { name: /Upload dataset/ })).toHaveAttribute('href', '/upload')
  })

  it('arrows and Enter choose; Escape clears the search and keeps the list', () => {
    const onChoose = vi.fn()
    render(<MemoryRouter><DataPicker items={ITEMS} value="" onChoose={onChoose} size="inline" /></MemoryRouter>)
    const search = screen.getByRole('combobox')
    fireEvent.change(search, { target: { value: 'zzz' } })
    fireEvent.keyDown(search, { key: 'Escape' })
    expect(search).toHaveValue('')
    expect(screen.getAllByRole('option')).toHaveLength(2)
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChoose).toHaveBeenCalledWith('s:3')
  })
})

describe('the chooser, polished (autopilot step 2)', () => {
  const ITEMS2 = [
    { key: 'd:1', kind: 'dataset' as const, name: 'Demo — Sales', rows: 2000, cols: 13, updated: new Date(Date.now() - 3 * 86400_000).toISOString(), mode: 'import' as const },
    { key: 'd:2', kind: 'dataset' as const, name: 'Live Orders', rows: 12000, cols: 8, updated: new Date(Date.now() - 2 * 3600_000).toISOString(), mode: 'directquery' as const },
    { key: 's:3', kind: 'source' as const, name: 'Warehouse', sourceType: 'postgresql', updated: '2026-01-01T00:00:00' },
  ]
  const open = (extra: Partial<Parameters<typeof DataPicker>[0]> = {}) =>
    render(<MemoryRouter><DataPicker items={ITEMS2} value="" onChoose={vi.fn()} size="inline" {...extra} /></MemoryRouter>)

  it('says how each row holds its data, and when a dataset was updated, in words', () => {
    open()
    const row = (name: string) => screen.getAllByRole('option').find(o => o.textContent?.includes(name))!
    expect(row('Demo — Sales').querySelector('.dl-pick__mode')).toHaveTextContent('Import')
    expect(row('Demo — Sales').querySelector('.dl-pick__opt-up')).toHaveTextContent('3 days ago')
    expect(row('Live Orders').querySelector('.dl-pick__mode')).toHaveTextContent('DirectQuery')
    expect(row('Live Orders').querySelector('.dl-pick__opt-up')).toHaveTextContent('2 hours ago')
    expect(row('Warehouse').querySelector('.dl-pick__mode')).toHaveTextContent('Live')
    expect(row('Warehouse').querySelector('.dl-pick__opt-up')).toBeNull()
  })

  it('counts each tab, and holds the page’s toggles in the same row', () => {
    const mine = { on: false, set: vi.fn() }
    const test = { on: true, set: vi.fn(), n: 2 }
    const { container } = open({ tools: { mine, test } })
    expect(screen.getAllByRole('tab').map(b => b.textContent)).toEqual(['All 3', 'Datasets 2', 'Connections 1'])
    const tools = container.querySelector('.dl-pick__tools') as HTMLElement
    const mineBtn = within(tools).getByRole('button', { name: 'Mine' })
    expect(mineBtn).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(mineBtn)
    expect(mine.set).toHaveBeenCalledWith(true)
    const testBtn = within(tools).getByRole('button', { name: 'Test data (2)' })
    expect(testBtn).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(testBtn)
    expect(test.set).toHaveBeenCalledWith(false)
  })

  it('"/" goes to the search, but not from inside a text box', () => {
    render(<MemoryRouter><input aria-label="other" /><DataPicker items={ITEMS2} value="" onChoose={vi.fn()} size="inline" /></MemoryRouter>)
    const search = screen.getByRole('combobox')
    expect(search).toHaveAttribute('aria-keyshortcuts', '/')
    fireEvent.keyDown(screen.getByLabelText('other'), { key: '/' })
    expect(search).not.toHaveFocus()
    fireEvent.keyDown(document.body, { key: '/' })
    expect(search).toHaveFocus()
  })

  it('ends with the key hints and Upload dataset on one line', () => {
    const { container } = open()
    const foot = container.querySelector('.dl-pick__foot') as HTMLElement
    expect(foot.querySelector('.dl-pick__keys')).toHaveTextContent('to move')
    expect(within(foot).getByRole('link', { name: 'Upload dataset' })).toHaveAttribute('href', '/upload')
  })

  it('the hero has an eyebrow and facts when given', () => {
    render(<AskHero id="h2" title="Ask your data anything" sub="sub" eyebrow="AI data assistant · 8 datasets"
      facts={[{ icon: () => null, text: 'One' }, { icon: () => null, text: 'Two' }, { icon: () => null, text: 'Three' }] as never} />)
    expect(screen.getByText('AI data assistant · 8 datasets')).toHaveClass('dl-hero__eyebrow')
    expect(screen.getAllByRole('listitem').map(l => l.textContent)).toEqual(['One', 'Two', 'Three'])
  })

  it('the new strings are in Arabic', () => {
    for (const k of ['ask2.pick.mine', 'ask2.pick.mode.import', 'ask2.pick.mode.direct', 'ask2.pick.mode.live', 'ask2.hero.eyebrow', 'ask2.hero.fact1', 'ask2.hero.fact2', 'ask2.hero.fact3'] as const) {
      expect(translate('ar', k), k).not.toBe(translate('en', k))
    }
  })
})
