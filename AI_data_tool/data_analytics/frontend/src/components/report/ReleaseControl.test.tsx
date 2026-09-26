/**
 * E09: an editor can tell whether viewers have their changes, and give them
 * the changes in one click. A viewer sees none of it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ReleaseControl from './ReleaseControl'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { reportsApi } from '../../services/api'
import type { ReportRelease } from '../../types/report'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  reportsApi: { release: vi.fn() },
}))

const RELEASE: ReportRelease = {
  id: 3, revision: 7, reason: 'release', note: null, released_by: 1, released_at: '2026-09-20T10:00:00Z',
}

function renderIt(props: Partial<Parameters<typeof ReleaseControl>[0]> = {}) {
  const onReleased = vi.fn()
  render(<DirectionProvider><ReleaseControl
    report={{ id: 5, published: true, release: RELEASE, unreleased_changes: false }}
    canEdit revision={7} onReleased={onReleased} {...props} /></DirectionProvider>)
  return onReleased
}

beforeEach(() => { localStorage.clear(); vi.mocked(reportsApi.release).mockReset() })

describe('ReleaseControl', () => {
  it('shows a viewer nothing', () => {
    renderIt({ canEdit: false })
    expect(screen.queryByTestId('release-control')).not.toBeInTheDocument()
  })

  it('shows nothing on a private draft that was never released', () => {
    renderIt({ report: { id: 5, published: false, release: null, unreleased_changes: false } })
    expect(screen.queryByTestId('release-control')).not.toBeInTheDocument()
  })

  it('says a released report is up to date, with no button', () => {
    renderIt()
    expect(screen.getByRole('status')).toHaveTextContent('Released')
    expect(screen.getByRole('status').getAttribute('title')).toMatch(/^Viewers see the version released /)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('offers to release when the draft has moved on, even before the report reloads', () => {
    // The server said nothing changed when the report loaded; an edit since
    // moved the revision the page knows of.
    renderIt({ revision: 8 })
    expect(screen.getByRole('status')).toHaveTextContent('Unreleased changes')
    expect(screen.getByRole('button', { name: 'Release changes' })).toBeInTheDocument()
  })

  it('releases and lets the page reload', async () => {
    vi.mocked(reportsApi.release).mockResolvedValue({ release: { ...RELEASE, id: 4, revision: 8 }, unreleased_changes: false })
    const onReleased = renderIt({ report: { id: 5, published: true, release: RELEASE, unreleased_changes: true } })
    fireEvent.click(screen.getByRole('button', { name: 'Release changes' }))
    await waitFor(() => expect(onReleased).toHaveBeenCalled())
    expect(reportsApi.release).toHaveBeenCalledWith(5)
  })

  it('tells the editor of a published report with no release that viewers see edits live', () => {
    renderIt({ report: { id: 5, published: true, release: null, unreleased_changes: false } })
    expect(screen.getByRole('status')).toHaveTextContent('Viewers see edits live')
    expect(screen.getByRole('button', { name: 'Release' })).toBeInTheDocument()
  })

  it('speaks Arabic', () => {
    localStorage.setItem('datalytics.language', 'ar')
    renderIt({ revision: 8 })
    expect(screen.getByRole('status')).toHaveTextContent('تغييرات لم تُصدَر')
    expect(screen.getByRole('button', { name: 'إصدار التغييرات' })).toBeInTheDocument()
  })
})
