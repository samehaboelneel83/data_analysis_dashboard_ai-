import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../../test/renderWithProviders'
import PublishingPanel from './PublishingPanel'
import { publishingApi, reviewApi } from '../../../services/api'
import toast from 'react-hot-toast'

/**
 * The Publishing tab. Pinned: the state is said in plain words with what it
 * means; archiving and going back to a version are asked about first, with
 * what they touch; approval controls show only when the organisation asks for
 * approval, and deciding only to an administrator; a refusal shows the
 * server's own reason.
 */

vi.mock('../../../services/api', () => ({
  publishingApi: { get: vi.fn(), releases: vi.fn(), set: vi.fn(), archive: vi.fn(), restore: vi.fn(), rollback: vi.fn(),
    transfer: vi.fn(), requestReview: vi.fn(), decideReview: vi.fn() },
  reviewApi: { setApproval: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const report = { id: 7, name: 'Sales', created_by: 1, is_mine: true, published: true }
const publication = (over = {}) => ({
  state: 'published', category: 'Finance', tags: ['monthly'], owner: 'me@x.io', published_at: '2026-10-01T10:00:00Z', published_by: 'me@x.io',
  updated_at: null, archived_at: null, viewers_may_export: true, release: { id: 31, revision: 4, reason: 'release', note: null, released_by: 1, released_at: '2026-10-01T10:00:00Z' },
  unreleased_changes: true, review: { required: false, state: 'none', current: false, note: null, requested_by: null, decided_by: null },
  depends: { shares: 3, links: 1, schedules: 2 }, ...over,
})
const open = (isAdmin = false, onStateChange = vi.fn()) => render(<PublishingPanel report={report} isAdmin={isAdmin} onStateChange={onStateChange} />)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(publishingApi.get).mockResolvedValue(publication() as never)
  vi.mocked(publishingApi.releases).mockResolvedValue([
    { id: 31, revision: 4, reason: 'release', note: null, released_by: 1, released_at: '2026-10-01T10:00:00Z' },
    { id: 30, revision: 2, reason: 'publish', note: null, released_by: 1, released_at: '2026-09-01T10:00:00Z' },
  ] as never)
})

describe('PublishingPanel', () => {
  it('says where the dashboard stands and what readers see', async () => {
    open()
    const panel = await screen.findByTestId('publishing-panel')
    expect(panel).toHaveTextContent('Published')
    expect(panel).toHaveTextContent('Everyone in your organisation can open it, view only.')
    expect(panel).toHaveTextContent('Readers see version 4')
    expect(panel).toHaveTextContent('You have changes readers do not see yet.')
    expect(screen.getByLabelText('Category')).toHaveValue('Finance')
  })

  it('archives only after saying what stops working', async () => {
    vi.mocked(publishingApi.archive).mockResolvedValue({ state: 'archived' } as never)
    const onStateChange = vi.fn()
    open(false, onStateChange)
    fireEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('3 shares, 1 links and 2 schedules are kept')
    expect(publishingApi.archive).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(publishingApi.archive).toHaveBeenCalledWith(7))
    await waitFor(() => expect(onStateChange).toHaveBeenCalledWith('archived'))
  })

  it('an archived dashboard offers Restore, not Archive', async () => {
    vi.mocked(publishingApi.get).mockResolvedValue(publication({ state: 'archived' }) as never)
    vi.mocked(publishingApi.restore).mockResolvedValue({ state: 'draft' } as never)
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(publishingApi.restore).toHaveBeenCalledWith(7))
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
  })

  it('goes back to an earlier version after being asked; the current one has no button', async () => {
    vi.mocked(publishingApi.rollback).mockResolvedValue({ release: {}, unreleased_changes: true } as never)
    open()
    const list = await screen.findByTestId('publishing-versions')
    expect(within(list).getAllByRole('button', { name: 'Go back to this' })).toHaveLength(1)
    expect(list).toHaveTextContent('What readers see')
    fireEvent.click(within(list).getByRole('button', { name: 'Go back to this' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Show readers version 2 again?')
    fireEvent.click(within(ask).getByRole('button', { name: 'Go back to this' }))
    await waitFor(() => expect(publishingApi.rollback).toHaveBeenCalledWith(7, 30))
  })

  it('saves the category and tags, and the readers-may-download switch', async () => {
    vi.mocked(publishingApi.set).mockResolvedValue({} as never)
    open()
    fireEvent.change(await screen.findByLabelText('Tags'), { target: { value: 'monthly, board ,  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(publishingApi.set).toHaveBeenCalledWith(7, { category: 'Finance', tags: ['monthly', 'board'] }))
    fireEvent.click(screen.getByLabelText(/Readers may download and export/))
    await waitFor(() => expect(publishingApi.set).toHaveBeenCalledWith(7, { viewers_may_export: false }))
  })

  it('shows approval only when the organisation asks for it; deciding only to an administrator', async () => {
    open()
    await screen.findByTestId('publishing-panel')
    expect(screen.queryByRole('button', { name: 'Ask for approval' })).not.toBeInTheDocument()

    vi.mocked(publishingApi.get).mockResolvedValue(publication({ state: 'draft',
      review: { required: true, state: 'requested', current: true, note: null, requested_by: 'me@x.io', decided_by: null } }) as never)
    const mine = open(false)
    await waitFor(() => expect(screen.getAllByText(/Waiting for approval/).length).toBeGreaterThan(0))
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    mine.unmount()

    vi.mocked(publishingApi.decideReview).mockResolvedValue({ state: 'approved' } as never)
    open(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(publishingApi.decideReview).toHaveBeenCalledWith(7, true, undefined))
  })

  it('only an administrator is offered the organisation\'s approval switch', async () => {
    const mine = open(false)
    await screen.findByTestId('publishing-panel')
    expect(screen.queryByTestId('approval-switch')).not.toBeInTheDocument()
    mine.unmount()
    vi.mocked(reviewApi.setApproval).mockResolvedValue({ publish_gate: false, require_approval: true } as never)
    open(true)
    fireEvent.click(within(await screen.findByTestId('approval-switch')).getByRole('checkbox'))
    await waitFor(() => expect(reviewApi.setApproval).toHaveBeenCalledWith(true))
  })

  it('an approval given before a later change counts as not asked for', async () => {
    vi.mocked(publishingApi.get).mockResolvedValue(publication({ state: 'draft',
      review: { required: true, state: 'approved', current: false, note: null, requested_by: 'me@x.io', decided_by: 'a@x.io' } }) as never)
    open()
    expect(await screen.findByText(/needs approval again/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask for approval' })).toBeInTheDocument()
  })

  it('hands over after being asked, and shows the reason when refused', async () => {
    vi.mocked(publishingApi.transfer).mockRejectedValue({ response: { data: { detail: 'No such person in your organisation' } } })
    open()
    fireEvent.change(await screen.findByLabelText("New owner's email"), { target: { value: 'b@x.io' } })
    fireEvent.click(screen.getByRole('button', { name: 'Hand over' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Hand "Sales" over to b@x.io?')
    fireEvent.click(within(ask).getByRole('button', { name: 'Hand over' }))
    await waitFor(() => expect(publishingApi.transfer).toHaveBeenCalledWith(7, 'b@x.io'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('No such person in your organisation'))
  })

  it('says so when the details cannot be loaded', async () => {
    vi.mocked(publishingApi.get).mockRejectedValue(new Error('down'))
    open()
    expect(await screen.findByText('Could not load the publishing details')).toBeInTheDocument()
  })
})
