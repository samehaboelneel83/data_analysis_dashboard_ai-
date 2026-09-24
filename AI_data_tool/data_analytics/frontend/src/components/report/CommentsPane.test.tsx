import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import CommentsPane from './CommentsPane'
import { commentsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  commentsApi: { list: vi.fn(), add: vi.fn(), delete: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(commentsApi.list).mockResolvedValue([
    { id: 1, page_id: 10, text: 'Looks wrong on page 1', created_at: '2026-08-23T10:00:00Z', author: 'a@x.com', mine: false },
    { id: 2, page_id: null, text: 'Fixed now', created_at: '2026-08-23T11:00:00Z', author: 'me@x.com', mine: true },
  ])
  vi.mocked(commentsApi.add).mockResolvedValue({ id: 3 })
  vi.mocked(commentsApi.delete).mockResolvedValue(undefined as never)
})

describe('CommentsPane', () => {
  it('lists comments with author and page pin', async () => {
    render(<CommentsPane reportId={7} activePageId={10} pageNames={{ 10: 'Overview' }} />)
    expect(await screen.findByText('Looks wrong on page 1')).toBeInTheDocument()
    expect(screen.getByText(/a@x.com · Overview/)).toBeInTheDocument()
  })

  it('posts a comment pinned to the active page', async () => {
    render(<CommentsPane reportId={7} activePageId={10} pageNames={{ 10: 'Overview' }} />)
    fireEvent.change(await screen.findByLabelText('Write a comment'), { target: { value: 'New note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post' }))
    await waitFor(() => expect(commentsApi.add).toHaveBeenCalledWith(7, 'New note', 10))
  })

  it('unpinning posts without a page id', async () => {
    render(<CommentsPane reportId={7} activePageId={10} pageNames={{}} />)
    fireEvent.click(await screen.findByLabelText(/Pin to current page/))
    fireEvent.change(screen.getByLabelText('Write a comment'), { target: { value: 'Global note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Post' }))
    await waitFor(() => expect(commentsApi.add).toHaveBeenCalledWith(7, 'Global note', undefined))
  })

  it('only own comments offer delete', async () => {
    render(<CommentsPane reportId={7} activePageId={10} pageNames={{}} />)
    await screen.findByText('Fixed now')
    expect(screen.queryByLabelText('Delete comment 1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Delete comment 2'))
    // Destructive actions are guarded, so the dialog has to be accepted.
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(commentsApi.delete).toHaveBeenCalledWith(7, 2))
  })

  it('cancelling the confirm keeps the comment', async () => {
    render(<CommentsPane reportId={7} activePageId={10} pageNames={{}} />)
    await screen.findByText('Fixed now')
    fireEvent.click(screen.getByLabelText('Delete comment 2'))
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(commentsApi.delete).not.toHaveBeenCalled()
  })
})
