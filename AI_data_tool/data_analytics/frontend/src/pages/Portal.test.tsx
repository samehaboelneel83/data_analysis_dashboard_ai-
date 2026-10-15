import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../test/renderWithProviders'
import Portal from './Portal'
import { portalApi } from '../services/api'

/**
 * The reader's portal. Pinned: it shows what the server lists and nothing of
 * its own; sections, search and filters are asked of the server (so paging
 * stays right and nothing is filtered from a list the reader should not
 * hold); favourites are kept at once and put back when the server refuses;
 * loading, empty and failed are each said.
 */

vi.mock('../services/api', () => ({
  portalApi: { catalog: vi.fn(), facets: vi.fn(), favorite: vi.fn(), deliveries: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const item = (over = {}) => ({
  id: 1, name: 'Sales overview', description: 'Monthly view', category: 'Finance', tags: ['monthly'], owner: 'a@x.io', is_mine: false,
  level: 'view', state: 'published', published_at: '2026-10-01T10:00:00Z', updated_at: null, data_as_of: '2026-10-10T10:00:00Z',
  favorite: false, last_viewed: null, can_export: true, via: 'team', ...over,
})
const counts = { all: 2, mine: 0, shared: 1, team: 1, favorites: 0, recent: 0, archived: 0 }
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 24, offset: 0, counts })
const open = () => render(<MemoryRouter><Portal /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(portalApi.catalog).mockResolvedValue(page([item(), item({ id: 2, name: 'Stock', via: 'user', can_export: false, category: null, tags: [] })]) as never)
  vi.mocked(portalApi.facets).mockResolvedValue({ categories: [{ value: 'Finance', count: 1 }], tags: [], owners: [{ value: 'a@x.io', count: 2 }] } as never)
  vi.mocked(portalApi.deliveries).mockResolvedValue([] as never)
})

describe('Portal', () => {
  it('lists what the server lists, with how each reached the reader and whether it may be downloaded', async () => {
    open()
    const grid = await screen.findByTestId('portal-grid')
    expect(within(grid).getByRole('link', { name: 'Open Sales overview' })).toHaveAttribute('href', '/reports/1')
    expect(grid).toHaveTextContent('Shared with your team')
    expect(grid).toHaveTextContent('Shared with you')
    expect(grid).toHaveTextContent('View only, no downloads')
    expect(grid).toHaveTextContent('By a@x.io')
    expect(screen.getByText('2 dashboards')).toBeInTheDocument()
  })

  it('sections carry their counts; an empty Archived section is not offered', async () => {
    open()
    await screen.findByTestId('portal-grid')
    expect(screen.getByRole('tab', { name: /Shared with me/ })).toHaveTextContent('1')
    expect(screen.queryByRole('tab', { name: /Archived/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Shared with me/ }))
    await waitFor(() => expect(portalApi.catalog).toHaveBeenLastCalledWith(expect.objectContaining({ section: 'shared', offset: 0 })))
  })

  it('an empty My team says it is about the team, not about you (F-05)', async () => {
    open()
    await screen.findByTestId('portal-grid')
    vi.mocked(portalApi.catalog).mockResolvedValue(page([]) as never)
    fireEvent.click(screen.getByRole('tab', { name: /My team/ }))
    expect(await screen.findByText('Nothing has been shared with your team yet.')).toBeInTheDocument()
  })

  it('asks the server to search and filter', async () => {
    open()
    await screen.findByTestId('portal-grid')
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'stock' } })
    await waitFor(() => expect(portalApi.catalog).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'stock' })))
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'Finance' } })
    await waitFor(() => expect(portalApi.catalog).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'stock', category: 'Finance' })))
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(portalApi.catalog).toHaveBeenLastCalledWith(expect.objectContaining({ q: undefined, category: undefined })))
  })

  it('offers no filter that has no values', async () => {
    open()
    await screen.findByTestId('portal-grid')
    expect(screen.queryByLabelText('Tag')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Owner')).toBeInTheDocument()
  })

  it('shows more a page at a time', async () => {
    vi.mocked(portalApi.catalog).mockResolvedValueOnce(page([item()], 2) as never)
      .mockResolvedValueOnce(page([item({ id: 2, name: 'Stock' })], 2) as never)
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Show more' }))
    await waitFor(() => expect(portalApi.catalog).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 1 })))
    expect(await screen.findByRole('link', { name: 'Open Stock' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open Sales overview' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
  })

  it('keeps a favourite at once, and puts it back when the server refuses', async () => {
    vi.mocked(portalApi.favorite).mockResolvedValueOnce(undefined as never).mockRejectedValueOnce(new Error('no'))
    open()
    const star = await screen.findByRole('button', { name: 'Add Sales overview to favourites' })
    fireEvent.click(star)
    await waitFor(() => expect(portalApi.favorite).toHaveBeenCalledWith(1, true))
    const on = await screen.findByRole('button', { name: 'Remove Sales overview from favourites' })
    expect(on).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(on)
    await waitFor(() => expect(portalApi.favorite).toHaveBeenCalledWith(1, false))
    expect(await screen.findByRole('button', { name: 'Remove Sales overview from favourites' })).toBeInTheDocument()
  })

  it('says when there is nothing, and differently when a search finds nothing', async () => {
    vi.mocked(portalApi.catalog).mockResolvedValue(page([]) as never)
    open()
    expect(await screen.findByText('Nothing here yet.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })
    expect(await screen.findByText(/Nothing matches/)).toBeInTheDocument()
  })

  it('says when the list could not be loaded and offers to try again', async () => {
    vi.mocked(portalApi.catalog).mockRejectedValueOnce(new Error('down'))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your dashboards.')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('portal-grid')).toBeInTheDocument()
  })

  it('lists what the reader\'s schedules sent, with the reason when one did not go', async () => {
    vi.mocked(portalApi.deliveries).mockResolvedValue([
      { id: 9, report_id: 1, report: 'Sales overview', status: 'error', at: '2026-10-11T08:00:00Z', error: 'not sent: downloads are off', format: 'pdf' },
    ] as never)
    open()
    await screen.findByTestId('portal-grid')
    fireEvent.click(screen.getByRole('tab', { name: 'Reports sent' }))
    expect(await screen.findByText('Not sent')).toBeInTheDocument()
    expect(screen.getByText(/downloads are off/)).toBeInTheDocument()
  })
})
