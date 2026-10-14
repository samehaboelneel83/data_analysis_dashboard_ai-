import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import VersionHistoryPane from './VersionHistoryPane'
import { reportsApi } from '../../services/api'

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }))

const ROWS = [
  { id: 9, revision: 3, created_at: '2026-09-05T10:00:00', created_by: 'a@b.com', pages: 1, widgets: 4 },
  { id: 8, revision: 2, created_at: '2026-09-05T09:00:00', created_by: 'a@b.com', pages: 1, widgets: 3 },
]

/** Selecting a version is what offers Restore (redesign 7c). */
const pick = async (name: string) => fireEvent.click(await screen.findByText(name))

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(reportsApi, 'versionDependencies').mockResolvedValue({ missing: [] })
})

describe('VersionHistoryPane', () => {
  it('lists versions newest first and marks the current revision', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue(ROWS)
    render(<VersionHistoryPane reportId={5} currentRevision={3} onRestored={vi.fn()} />)
    expect(await screen.findByText('Revision 3')).toBeInTheDocument()
    expect(screen.getByText('Revision 2')).toBeInTheDocument()
    // The current revision carries the badge; the older one does not.
    const current = screen.getByText('Revision 3').closest('[role="button"]')!
    expect(current).toHaveTextContent(/current/i)
    expect(screen.getByText('Revision 2').closest('[role="button"]')!).not.toHaveTextContent(/current/i)
    expect(screen.getByText(/4 widgets/)).toBeInTheDocument()
  })

  it('restores after confirm and reloads the builder', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue(ROWS)
    const restore = vi.spyOn(reportsApi, 'restoreVersion').mockResolvedValue({
      restored_version_id: 8, restored_revision: 2, note: 'Pins removed.' })
    const onRestored = vi.fn()
    render(<VersionHistoryPane reportId={5} currentRevision={3} onRestored={onRestored} />)
    await pick('Revision 2')
    fireEvent.click(screen.getByRole('button', { name: 'Restore revision 2' }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(restore).toHaveBeenCalledWith(5, 8))
    expect(onRestored).toHaveBeenCalled()
  })

  it('names what the version uses that no longer exists, before restoring (E09)', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue(ROWS)
    vi.spyOn(reportsApi, 'versionDependencies').mockResolvedValue({ missing: [
      { page: 'Overview', widget: 'Margin by region', kind: 'field', name: 'Margin' }] })
    const restore = vi.spyOn(reportsApi, 'restoreVersion').mockResolvedValue({
      restored_version_id: 8, restored_revision: 2, note: '',
      missing: [{ page: 'Overview', widget: 'Margin by region', kind: 'field', name: 'Margin' }] })
    render(<VersionHistoryPane reportId={5} currentRevision={3} onRestored={vi.fn()} />)
    await pick('Revision 2')
    fireEvent.click(screen.getByRole('button', { name: 'Restore revision 2' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('"Margin by region" uses the field "Margin"')
    expect(dialog).toHaveTextContent(/saved as a new version first/)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(restore).toHaveBeenCalledWith(5, 8))
  })

  it('a declined confirm restores nothing', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue(ROWS)
    const restore = vi.spyOn(reportsApi, 'restoreVersion')
    render(<VersionHistoryPane reportId={5} currentRevision={3} onRestored={vi.fn()} />)
    await pick('Revision 2')
    fireEvent.click(screen.getByRole('button', { name: 'Restore revision 2' }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: /cancel/i }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(restore).not.toHaveBeenCalled()
  })

  it('says so when there is no history yet', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue([])
    render(<VersionHistoryPane reportId={5} currentRevision={0} onRestored={vi.fn()} />)
    expect(await screen.findByText(/no saved versions yet/i)).toBeInTheDocument()
  })

  it('surfaces a load failure without crashing', async () => {
    vi.spyOn(reportsApi, 'versions').mockRejectedValue(new Error('down'))
    render(<VersionHistoryPane reportId={5} currentRevision={0} onRestored={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('VersionHistoryPane copilot attribution (Phase 7.1)', () => {
  it('marks the version captured before a copilot change and says who asked', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue([
      { id: 10, revision: 4, created_at: '2026-09-05T11:00:00', created_by: 'a@b.com', pages: 1, widgets: 4,
        via: 'copilot', note: 'Before the copilot removed "Sales"' },
      ...ROWS,
    ])
    render(<VersionHistoryPane reportId={5} currentRevision={5} onRestored={vi.fn()} />)
    const tag = await screen.findByTestId('version-copilot')
    expect(tag.textContent).toContain('Before the copilot removed "Sales" (asked by a@b.com)')
    expect(screen.getAllByTestId('version-copilot')).toHaveLength(1)
  })
})

describe('VersionHistoryPane layout (7c)', () => {
  it('groups versions by day and offers no Restore on the current one', async () => {
    const today = new Date().toISOString()
    vi.spyOn(reportsApi, 'versions').mockResolvedValue([
      { id: 9, revision: 3, created_at: today, created_by: 'a@b.com', pages: 1, widgets: 4 },
      { id: 8, revision: 2, created_at: '2025-01-05T09:00:00', created_by: 'a@b.com', pages: 1, widgets: 3 },
    ])
    render(<VersionHistoryPane reportId={5} currentRevision={3} onRestored={vi.fn()} />)
    expect(await screen.findByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Earlier')).toBeInTheDocument()
    await pick('Revision 3')
    expect(screen.queryByRole('button', { name: 'Restore revision 3' })).not.toBeInTheDocument()
  })
})

describe('a burst of saves reads as one change (QA2 N3), times in the reader\'s clock (QA2 V10)', () => {
  const at = (s: number) => new Date(Date.UTC(2026, 9, 6, 10, 1, 35) + s).toISOString()
  const BURST = [
    { id: 52, revision: 37, created_at: at(400), created_by: 'admin@x.io', pages: 2, widgets: 41 },
    { id: 51, revision: 35, created_at: at(390), created_by: 'admin@x.io', pages: 2, widgets: 41 },
    { id: 50, revision: 34, created_at: at(380), created_by: 'admin@x.io', pages: 2, widgets: 41 },
    { id: 49, revision: 34, created_at: at(0), created_by: 'admin@x.io', pages: 2, widgets: 41 },
    { id: 10, revision: 2, created_at: at(-3_600_000), created_by: 'sara@x.io', pages: 1, widgets: 4 },
  ]

  it('one entry for saves seconds apart by one person; it expands, and Restore goes to before the burst', async () => {
    vi.spyOn(reportsApi, 'versions').mockResolvedValue(BURST as never)
    vi.spyOn(reportsApi, 'versionDependencies').mockResolvedValue({ missing: [] } as never)
    const restore = vi.spyOn(reportsApi, 'restoreVersion').mockResolvedValue({ restored_revision: 34, missing: [] } as never)
    render(<VersionHistoryPane reportId={5} currentRevision={38} onRestored={vi.fn()} />)
    const burst = await screen.findByText('4 changes')
    expect(screen.getAllByRole('button', { pressed: false }).length).toBe(2)
    fireEvent.click(burst)
    expect(screen.getAllByText(/^Revision 3[457]$/).length).toBe(4)
    fireEvent.click(screen.getByRole('button', { name: 'Restore the state before these changes' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(restore).toHaveBeenCalledWith(5, 49))
  })

  it('an Arabic reader sees a 24-hour time, never "PM"', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    try {
      const { DirectionProvider } = await import('../../contexts/DirectionContext')
      vi.spyOn(reportsApi, 'versions').mockResolvedValue([BURST[4]] as never)
      render(<DirectionProvider><VersionHistoryPane reportId={5} currentRevision={null} onRestored={vi.fn()} /></DirectionProvider>)
      await screen.findByText('sara')
      // A 24-hour time, with no AM/PM after it in either script.
      expect(document.body.textContent).toMatch(/\d\d:\d\d/)
      expect(document.body.textContent).not.toMatch(/\d\d:\d\d\s*(AM|PM|ص|م)/)
    } finally { localStorage.removeItem('datalytics.language') }
  })
})
