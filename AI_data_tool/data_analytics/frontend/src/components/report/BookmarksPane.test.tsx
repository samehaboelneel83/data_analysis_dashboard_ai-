import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import BookmarksPane from './BookmarksPane'
import { reportsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  reportsApi: { addBookmark: vi.fn(), deleteBookmark: vi.fn() },
}))

const BM = { id: 1, report_id: 1, name: 'Q1 view', position: 0,
  state: { pageId: 100, activeFilters: [], promptValues: {}, hiddenWidgetIds: [] }, created_at: '2026-01-01' }

describe('BookmarksPane', () => {
  it('lists saved bookmarks and applies one on click', () => {
    const onApply = vi.fn()
    render(<BookmarksPane reportId={1} bookmarks={[BM]} captureState={() => BM.state}
      onCaptured={vi.fn()} onApply={onApply} onDeleted={vi.fn()} />)
    fireEvent.click(screen.getByText('Q1 view'))
    expect(onApply).toHaveBeenCalledWith(BM)
  })

  it('captures and saves a new bookmark', async () => {
    vi.mocked(reportsApi.addBookmark).mockResolvedValue({ ...BM, id: 2, name: 'New view' } as any)
    const onCaptured = vi.fn()
    render(<BookmarksPane reportId={1} bookmarks={[]} captureState={() => BM.state}
      onCaptured={onCaptured} onApply={vi.fn()} onDeleted={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Add bookmark/i }))
    const input = await screen.findByPlaceholderText(/bookmark name/i)
    fireEvent.change(input, { target: { value: 'New view' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))
    await waitFor(() => expect(reportsApi.addBookmark).toHaveBeenCalledWith(1, { name: 'New view', position: 0, state: BM.state }))
    expect(onCaptured).toHaveBeenCalled()
  })
})
