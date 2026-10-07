import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../../test/renderWithProviders'
import ShareDashboardDialog from './ShareDashboardDialog'
import { authzApi, reportGrantsApi, reportsApi, shareLinksApi } from '../../../services/api'
import toast from 'react-hot-toast'

/**
 * The Share dialog (redesign 7c). Pinned: who may change sharing (the author
 * or an admin), that a level change re-sends the grant, that general access is
 * the publish flag, that guest links are greyed with the server's reason, and
 * that a viewer without edit rights gets People only.
 */

vi.mock('../../../services/api', () => ({
  authzApi: { decisions: vi.fn() },
  reportGrantsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  reportsApi: { setPublished: vi.fn() },
  shareLinksApi: { list: vi.fn(), create: vi.fn(), revoke: vi.fn() },
  embedConfigsApi: { list: vi.fn(), create: vi.fn(), setEnabled: vi.fn(), delete: vi.fn() },
}))
vi.mock('../../../pages/reportBuilder/SchedulePanel', () => ({ SchedulePanel: () => <div data-testid="schedule-panel" /> }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const report = (over = {}) => ({ id: 7, name: 'Sales', created_by: 1, is_mine: true, published: false, ...over })
const open = (over: Partial<Parameters<typeof ShareDashboardDialog>[0]> = {}) => render(
  <ShareDashboardDialog report={report()} canEdit isAdmin={false} onClose={() => {}} {...over} />)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(authzApi.decisions).mockResolvedValue([{ resource: 'report', id: 7, action: 'share_link', allowed: true, reason: '' }] as never)
  vi.mocked(reportGrantsApi.list).mockResolvedValue([{ id: 5, user_id: 2, email: 'omar@x.io', level: 'view' }] as never)
  vi.mocked(shareLinksApi.list).mockResolvedValue([] as never)
})

describe('ShareDashboardDialog', () => {
  it('lists the people with access, the owner first', async () => {
    open()
    const people = await screen.findByTestId('share-people')
    expect(people).toHaveTextContent('You')
    expect(people).toHaveTextContent('Owner')
    expect(await within(people).findByText('omar@x.io')).toBeInTheDocument()
  })

  it('invites by email at the chosen level', async () => {
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 6, user_id: 3, email: 'b@x.io', level: 'data' } as never)
    open()
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Email to share with'), { target: { value: 'b@x.io' } })
    fireEvent.change(within(dialog).getByLabelText('Access level'), { target: { value: 'data' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Invite' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalledWith(7, { email: 'b@x.io', level: 'data' }))
    expect(await within(dialog).findByText('b@x.io')).toBeInTheDocument()
  })

  it("changes a person's level by re-sending their grant", async () => {
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 5, user_id: 2, email: 'omar@x.io', level: 'edit' } as never)
    open()
    fireEvent.change(await screen.findByLabelText('Access level for omar@x.io'), { target: { value: 'edit' } })
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalledWith(7, { email: 'omar@x.io', level: 'edit' }))
  })

  it('removes access', async () => {
    vi.mocked(reportGrantsApi.remove).mockResolvedValue(undefined as never)
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove access for omar@x.io' }))
    await waitFor(() => expect(reportGrantsApi.remove).toHaveBeenCalledWith(7, 5))
    await waitFor(() => expect(screen.queryByText('omar@x.io')).not.toBeInTheDocument())
  })

  it('general access is the publish flag', async () => {
    vi.mocked(reportsApi.setPublished).mockResolvedValue({ published: true } as never)
    const onPublishedChange = vi.fn()
    open({ onPublishedChange })
    const everyone = await screen.findByRole('radio', { name: /Everyone in your organisation/ })
    expect(screen.getByRole('radio', { name: /Restricted/ })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(everyone)
    await waitFor(() => expect(reportsApi.setPublished).toHaveBeenCalledWith(7, true))
    expect(onPublishedChange).toHaveBeenCalledWith(true)
    await waitFor(() => expect(everyone).toHaveAttribute('aria-checked', 'true'))
  })

  it("shows the publish gate's message when publishing is refused", async () => {
    vi.mocked(reportsApi.setPublished).mockRejectedValue({ response: { data: { detail: { message: 'Fix 2 review findings first' } } } })
    open()
    fireEvent.click(await screen.findByRole('radio', { name: /Everyone in your organisation/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Fix 2 review findings first'))
  })

  it("someone else's dashboard: no sharing controls, said plainly; no grants are requested", async () => {
    open({ report: report({ is_mine: false, created_by: 4 }) })
    expect(await screen.findByText(/Only the dashboard's author or an admin/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Email to share with')).not.toBeInTheDocument()
    expect(reportGrantsApi.list).not.toHaveBeenCalled()
  })

  it('an admin manages anyone\'s authored dashboard', async () => {
    open({ report: report({ is_mine: false, created_by: 4 }), isAdmin: true })
    expect(await screen.findByLabelText('Email to share with')).toBeInTheDocument()
  })

  it('greys guest links with the server\'s reason', async () => {
    vi.mocked(authzApi.decisions).mockResolvedValue([{ resource: 'report', id: 7, action: 'share_link', allowed: false,
      reason: 'The report is Restricted; share it with named people instead.' }] as never)
    open()
    expect(await screen.findByText(/share it with named people instead/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create guest link' })).not.toBeInTheDocument()
  })

  it('without edit rights: People only, no link, guest links, embed or schedule', async () => {
    open({ canEdit: false })
    await screen.findByTestId('share-people')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.queryByTestId('guest-links')).not.toBeInTheDocument()
    expect(authzApi.decisions).not.toHaveBeenCalled()
  })

  it('Embed and Schedule are their own tabs', async () => {
    open()
    fireEvent.click(await screen.findByRole('tab', { name: 'Schedule' }))
    expect(screen.getByTestId('schedule-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Embed' }))
    expect(screen.getByTestId('embed-section')).toBeInTheDocument()
  })

  it('offers "Your access, and why" and, to admins, "Access by role"', async () => {
    const why = vi.fn(), byRole = vi.fn()
    open({ isAdmin: true, onAccessWhy: why, onAccessByRole: byRole })
    fireEvent.click(await screen.findByRole('button', { name: 'Your access, and why' }))
    fireEvent.click(screen.getByRole('button', { name: 'Access by role' }))
    expect(why).toHaveBeenCalled()
    expect(byRole).toHaveBeenCalled()
  })
})
