import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SourceSummary from './SourceSummary'
import { setupApi, type SetupSummary } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setupApi: { summary: vi.fn() },
}))

const summary = (totals: Partial<NonNullable<SetupSummary['totals']>>) => ({
  status: 'ready', source: { id: 1, name: 'Demo — Live SQLite', type: 'sqlite', allow_ai: false },
  sync: { status: 'ok', last_synced_at: null }, can_edit: true, language: 'en', overview: null, tables: [],
  totals: { tables: 1, views: 0, rows: 0, rows_known: false, date_from: null, date_to: null, dates_exact: false, ...totals },
}) as unknown as SetupSummary

describe('SourceSummary facts sentence (B-30)', () => {
  it('never says "0 rows" when the database keeps no row counts, and says "1 table"', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({ tables: 1, rows: 0, rows_known: false }))
    render(<MemoryRouter><SourceSummary sourceId={1} /></MemoryRouter>)
    const lead = await screen.findByText(/Demo — Live SQLite has 1 table/)
    expect(lead).not.toHaveTextContent(/0 rows/)
    expect(lead).not.toHaveTextContent(/1 tables/)
    expect(lead).toHaveTextContent(/does not keep row counts/)
  })

  it('counts rows and tables with the right plural when they are known', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(summary({ tables: 6, rows: 12000, rows_known: true }))
    render(<MemoryRouter><SourceSummary sourceId={1} /></MemoryRouter>)
    expect(await screen.findByText('Demo — Live SQLite has 6 tables with 12,000 rows in total.')).toBeInTheDocument()
  })
})
