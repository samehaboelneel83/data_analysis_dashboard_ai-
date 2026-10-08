import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Setup from './Setup'
import { setupApi, metadataApi, type SetupJourney, type SetupSummary } from '../services/api'

vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>()
  return {
    ...real,
    setupApi: {
      get: vi.fn(), update: vi.fn(), journeys: vi.fn(), summary: vi.fn(), refreshSummary: vi.fn(),
      sample: vi.fn(), editOverview: vi.fn(), editTable: vi.fn(),
      datasets: vi.fn(), suggestDatasets: vi.fn(), refineDataset: vi.fn(), createDatasets: vi.fn(),
    },
    metadataApi: { ...real.metadataApi, settings: vi.fn() },
  }
})

const journey = (over: Partial<SetupJourney> = {}): SetupJourney => ({
  id: 1, source: { id: 37, name: 'Cars DB', type: 'postgresql' }, step: 'understand',
  position: 1, total: 4, brief: {}, dataset_ids: [], report_id: null, updated_at: null, ...over,
})

const table = (over: Record<string, unknown> = {}) => ({
  id: 11, name: 'cars_hatla2ee', schema: 'public', kind: 'table', title: 'Car listings',
  what: 'One row per car for sale.', what_source: 'ai', useful_for: 'Prices by brand and age.',
  group: 'main', rows: 14269, columns_count: 28, measures: ['price_egp', 'mileage_km'], dates: ['listed_date'],
  date_from: '2025-04-29', date_to: '2026-06-18', dates_exact: false, related: [],
  canonical: false, deprecated: false, ...over,
})

const summary = (over: Partial<SetupSummary> = {}): SetupSummary => ({
  status: 'ready', source: { id: 37, name: 'Cars DB', type: 'postgresql', allow_ai: true },
  sync: { status: 'ok', last_synced_at: null }, can_edit: true, language: 'en',
  ai: { used: true, pending: false, reason: null },
  overview: 'Used-car listings across Egypt.', overview_source: 'ai',
  totals: { tables: 2, views: 0, rows: 14369, date_from: '2025-04-29', date_to: '2026-06-18', dates_exact: false },
  tables: [table() as never, table({ id: 12, name: 'import_log', title: null, what: null, group: 'technical',
                                     measures: [], useful_for: null }) as never],
  relationships: [], questions: ['Which brands hold their value?'], ...over,
})

const renderAt = (path = '/setup/37') => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/setup/:id" element={<Setup />} /></Routes>
  </MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(setupApi.datasets).mockResolvedValue({
    proposals: { pending: false, failed: null, items: [], language: null, asked: false },
    brief: {}, existing: [], chosen: [], can_create: true, allow_ai: true })
  vi.mocked(setupApi.get).mockResolvedValue(journey())
  vi.mocked(setupApi.summary).mockResolvedValue(summary())
})

describe('Guided setup — Understand', () => {
  it('shows the 4 steps and where the reader is', async () => {
    renderAt()
    expect(await screen.findByRole('heading', { name: 'Set up Cars DB' })).toBeInTheDocument()
    const progress = screen.getByRole('navigation', { name: 'Setup progress' })
    expect(progress).toHaveTextContent('Understand')
    expect(progress).toHaveTextContent('Dashboard')
    expect(within(progress).getByRole('button', { name: /Understand/ })).toHaveAttribute('aria-current', 'step')
    // A step not reached yet cannot be opened.
    expect(within(progress).getByRole('button', { name: /Choose data/ })).toBeDisabled()
  })

  it('reads plainly: overview, the most useful table first, questions', async () => {
    renderAt()
    expect(await screen.findByText('Used-car listings across Egypt.')).toBeInTheDocument()
    expect(screen.getByText('Written by AI')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Car listings' })).toBeInTheDocument()
    expect(screen.getByText('One row per car for sale.')).toBeInTheDocument()
    expect(screen.getByText('Numbers: price_egp, mileage_km')).toBeInTheDocument()
    expect(screen.getByText('Which brands hold their value?')).toBeInTheDocument()
    // Dates from a sample say they are approximate.
    expect(screen.getAllByText(/\(approximate\)/).length).toBeGreaterThan(0)
    // System tables are folded away, not removed.
    expect(screen.getByText('System tables (1)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Show details/ })).toHaveAttribute('href', '/connections/37/review')
  })

  it('without AI words it still describes the database from the facts', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({
      overview: null, overview_source: null, ai: { used: false, pending: false, reason: 'failed' } }))
    renderAt()
    expect(await screen.findByText('Cars DB has 2 tables with 14,369 rows in total.')).toBeInTheDocument()
    expect(screen.getByText(/The AI could not be reached/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Ask AI again/ }))
    await waitFor(() => expect(setupApi.refreshSummary).toHaveBeenCalledWith(37, 'en'))
  })

  it('offers to turn AI on to whoever may edit the connection', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({ ai: { used: false, pending: false, reason: 'off' } }))
    vi.mocked(metadataApi.settings).mockResolvedValue({} as never)
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Let AI describe it' }))
    await waitFor(() => expect(metadataApi.settings).toHaveBeenCalledWith(37, { allow_llm_sampling: true }))
    await waitFor(() => expect(setupApi.refreshSummary).toHaveBeenCalled())
  })

  it('shows sample rows on request, with empty values named', async () => {
    vi.mocked(setupApi.sample).mockResolvedValue({
      columns: ['make', 'title'], rows: [{ make: 'Audi', title: null }], restricted: true, error: null })
    renderAt()
    fireEvent.click((await screen.findAllByRole('button', { name: 'Show sample rows' }))[0])
    expect(await screen.findByText('Audi')).toBeInTheDocument()
    expect(screen.getByText('Empty')).toBeInTheDocument()
    expect(screen.getByText('You see only the rows your access allows.')).toBeInTheDocument()
  })

  it('saves a correction to what a table holds', async () => {
    vi.mocked(setupApi.editTable).mockResolvedValue({ id: 11, what: 'Every listing', what_source: 'you' })
    renderAt()
    await screen.findByRole('heading', { name: 'Car listings' })
    fireEvent.click(screen.getAllByRole('button', { name: /^Edit$/ })[0])
    fireEvent.change(screen.getByRole('textbox', { name: /Edit what "Car listings" holds/ }),
      { target: { value: 'Every listing' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(setupApi.editTable).toHaveBeenCalledWith(37, 11, 'Every listing'))
  })

  it('hides editing from someone who may not change the connection', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({ can_edit: false }))
    renderAt()
    await screen.findByRole('heading', { name: 'Car listings' })
    expect(screen.queryByRole('button', { name: /^Edit$/ })).not.toBeInTheDocument()
  })

  it('says when the database is still being read', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue({ ...summary(), status: 'syncing' })
    renderAt()
    expect(await screen.findByText(/still reading this database/)).toBeInTheDocument()
  })

  it('moves on to Choose data and remembers it', async () => {
    vi.mocked(setupApi.update).mockResolvedValue(journey({ step: 'data', position: 2 }))
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Next: Choose data' }))
    await waitFor(() => expect(setupApi.update).toHaveBeenCalledWith(37, { step: 'data' }))
    expect(await screen.findByRole('heading', { name: 'About you' })).toBeInTheDocument()
  })

  it('stops asking after a while and says the AI is slow, keeping the facts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      vi.mocked(setupApi.summary).mockResolvedValue(summary({ ai: { used: false, pending: true, reason: null } }))
      renderAt()
      expect(await screen.findByText(/AI is reading your database/)).toBeInTheDocument()
      for (let i = 0; i < 46; i++) await vi.advanceTimersByTimeAsync(4000)
      expect(await screen.findByText(/taking longer than usual/)).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Car listings' })).toBeInTheDocument()
      const calls = vi.mocked(setupApi.summary).mock.calls.length
      fireEvent.click(screen.getByRole('button', { name: /Check again/ }))
      await waitFor(() => expect(vi.mocked(setupApi.summary).mock.calls.length).toBe(calls + 1))
      expect(setupApi.refreshSummary).not.toHaveBeenCalled()
    } finally { vi.useRealTimers() }
  })

  it('keeps the AI\'s answer and asks again only when the reader presses the button', async () => {
    vi.mocked(setupApi.refreshSummary).mockResolvedValue(summary({ ai: { used: true, pending: true, reason: null } }))
    renderAt()
    await screen.findByText('Used-car listings across Egypt.')
    expect(setupApi.refreshSummary).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Ask AI again/ }))
    await waitFor(() => expect(setupApi.refreshSummary).toHaveBeenCalledWith(37, 'en'))
    // While the new answer is written, the earlier one stays on screen.
    expect(await screen.findByText(/AI is reading your database/)).toBeInTheDocument()
    expect(screen.getByText('Used-car listings across Egypt.')).toBeInTheDocument()
  })

  it('says so when asking again failed, keeping the earlier words', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({ ai: { used: true, pending: false, reason: 'failed' } }))
    renderAt()
    expect(await screen.findByText(/still see its earlier description/)).toBeInTheDocument()
    expect(screen.getByText('Used-car listings across Egypt.')).toBeInTheDocument()
  })
})
