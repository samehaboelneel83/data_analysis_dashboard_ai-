import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../../test/renderWithProviders'
import ShareDashboardDialog from './ShareDashboardDialog'
import { authzApi, publishingApi, reportGrantsApi, reportsApi, shareLinksApi, workspaceApi } from '../../../services/api'
import toast from 'react-hot-toast'

/**
 * The Share dialog (redesign 7c). Pinned: who may change sharing (the author
 * or an admin), that a share is changed in place (never re-created, which
 * would lose its end date and rights), that a role or a team and a removal are
 * asked about first, that general access is the publish flag, that guest links are greyed with the server's reason, and
 * that a viewer without edit rights gets People only.
 */

vi.mock('../../../services/api', () => ({
  authzApi: { decisions: vi.fn() },
  reportGrantsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
  reportsApi: { setPublished: vi.fn(), listedRecords: vi.fn() },
  publishingApi: { changeGrant: vi.fn(), get: vi.fn(), releases: vi.fn(), set: vi.fn(), archive: vi.fn(), restore: vi.fn(),
    rollback: vi.fn(), transfer: vi.fn(), requestReview: vi.fn(), decideReview: vi.fn() },
  workspaceApi: { shareOptions: vi.fn() },
  reviewApi: { setApproval: vi.fn() },
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
  vi.mocked(reportsApi.listedRecords).mockResolvedValue([] as never)
})

describe('ShareDashboardDialog', () => {
  it('says which charts show single records before sharing (persona test 3.7)', async () => {
    vi.mocked(reportsApi.listedRecords).mockResolvedValue([
      { widget_id: 1, title: 'Top members', page: 'P', column: 'member_no', kind: 'identifier' },
      { widget_id: 2, title: 'Contacts', page: 'P', column: 'email', kind: 'email' }] as never)
    open()
    const note = await screen.findByTestId('share-listed-records')
    expect(note).toHaveTextContent('2 charts here show single records')
    expect(note).toHaveTextContent('“Top members” has one mark per member_no (an identifier).')
    expect(note).toHaveTextContent('“Contacts” lists email, which holds personal data.')
  })

  it('says nothing when every chart shows groups', async () => {
    open()
    await screen.findByTestId('share-people')
    expect(screen.queryByTestId('share-listed-records')).not.toBeInTheDocument()
  })

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

  it("changes a person's level in place, keeping the share's other terms", async () => {
    vi.mocked(publishingApi.changeGrant).mockResolvedValue({ id: 5, user_id: 2, email: 'omar@x.io', level: 'edit' } as never)
    open()
    fireEvent.change(await screen.findByLabelText('Access level for omar@x.io'), { target: { value: 'edit' } })
    await waitFor(() => expect(publishingApi.changeGrant).toHaveBeenCalledWith(7, 5, { level: 'edit' }))
    expect(reportGrantsApi.create).not.toHaveBeenCalled()
  })

  it('removes access only after being asked', async () => {
    vi.mocked(reportGrantsApi.remove).mockResolvedValue(undefined as never)
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove access for omar@x.io' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Remove access for omar@x.io?')
    expect(reportGrantsApi.remove).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Remove access' }))
    await waitFor(() => expect(reportGrantsApi.remove).toHaveBeenCalledWith(7, 5))
    await waitFor(() => expect(screen.queryByText('omar@x.io')).not.toBeInTheDocument())
  })

  it('keeps access when the removal is cancelled', async () => {
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove access for omar@x.io' }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(reportGrantsApi.remove).not.toHaveBeenCalled()
    expect(screen.getByText('omar@x.io')).toBeInTheDocument()
  })

  it('shares with a team only after being asked, and says who it reaches', async () => {
    vi.mocked(workspaceApi.shareOptions).mockResolvedValue({ roles: [{ id: 3, name: 'Analyst' }],
      org_units: [{ id: 9, name: 'North', parent_id: null, level_name: 'Region' }] } as never)
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 8, kind: 'team', name: 'North', user_id: null, org_unit_id: 9, email: '', level: 'view' } as never)
    open()
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'A team' }))
    await within(dialog).findByRole('option', { name: 'North (Region)' })
    fireEvent.change(within(dialog).getByLabelText('Choose a team'), { target: { value: '9' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Share' }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Share with everyone in North (Region)?')
    expect(reportGrantsApi.create).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalledWith(7, { org_unit_id: 9, level: 'view' }))
    expect(await within(screen.getByTestId('share-people')).findByText('North')).toBeInTheDocument()
  })

  it('a new person starts at Can view, and is back at Can view after each invite and each switch (F-06)', async () => {
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 6, user_id: 3, email: 'b@x.io', level: 'edit' } as never)
    vi.mocked(workspaceApi.shareOptions).mockResolvedValue({ roles: [], org_units: [] } as never)
    open()
    const dialog = await screen.findByRole('dialog')
    const level = () => within(dialog).getByLabelText('Access level') as HTMLSelectElement
    expect(level().value).toBe('view')
    fireEvent.change(within(dialog).getByLabelText('Email to share with'), { target: { value: 'b@x.io' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Invite' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalledWith(7, { email: 'b@x.io', level: 'view' }))
    fireEvent.change(level(), { target: { value: 'edit' } })
    fireEvent.change(within(dialog).getByLabelText('Email to share with'), { target: { value: 'c@x.io' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Invite' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenLastCalledWith(7, { email: 'c@x.io', level: 'edit' }))
    await waitFor(() => expect(level().value).toBe('view'))
    fireEvent.change(level(), { target: { value: 'edit' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'A team' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'A person' }))
    expect(level().value).toBe('view')
  })

  it('sends an end date, no downloads, sharing on and a message only when chosen', async () => {
    vi.mocked(reportGrantsApi.create).mockResolvedValue({ id: 6, user_id: 3, email: 'b@x.io', level: 'view', can_export: false, can_share: true,
      expires_at: '2030-01-31T23:59:59Z' } as never)
    open()
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Email to share with'), { target: { value: 'b@x.io' } })
    fireEvent.change(within(dialog).getByLabelText('Access level'), { target: { value: 'view' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'More options' }))
    fireEvent.change(within(dialog).getByLabelText(/Access ends on/), { target: { value: '2030-01-31' } })
    fireEvent.click(within(dialog).getByLabelText('May download and export'))
    fireEvent.click(within(dialog).getByLabelText('May share it with other people (view only)'))
    fireEvent.change(within(dialog).getByLabelText('Message (optional)'), { target: { value: 'For the review' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Invite' }))
    await waitFor(() => expect(reportGrantsApi.create).toHaveBeenCalled())
    const body = vi.mocked(reportGrantsApi.create).mock.calls[0][1]
    expect(body).toMatchObject({ email: 'b@x.io', level: 'view', can_export: false, can_share: true, message: 'For the review' })
    expect(new Date(body.expires_at as string).getFullYear()).toBe(2030)
    const people = within(dialog).getByTestId('share-people')
    expect(people).toHaveTextContent('No downloads')
    expect(people).toHaveTextContent('May share')
  })

  it('shows a share that has ended as giving no access, and changes one in place', async () => {
    vi.mocked(reportGrantsApi.list).mockResolvedValue([{ id: 5, user_id: 2, email: 'omar@x.io', level: 'view',
      expires_at: '2020-01-01T00:00:00Z', expired: true, can_export: true }] as never)
    vi.mocked(publishingApi.changeGrant).mockResolvedValue({ id: 5, user_id: 2, email: 'omar@x.io', level: 'view', can_export: false } as never)
    open()
    expect(await screen.findByText(/no access now/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Options for omar@x.io' }))
    fireEvent.click(screen.getAllByLabelText('May download and export')[0])
    await waitFor(() => expect(publishingApi.changeGrant).toHaveBeenCalledWith(7, 5, { can_export: false }))
  })

  it('general access is the publish flag, asked about first (F-08)', async () => {
    vi.mocked(reportsApi.setPublished).mockResolvedValue({ published: true } as never)
    const onPublishedChange = vi.fn()
    open({ onPublishedChange })
    const everyone = await screen.findByRole('radio', { name: /Everyone in your organisation/ })
    expect(screen.getByRole('radio', { name: /Restricted/ })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(everyone)
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Publish “Sales” to everyone in your organisation?')
    expect(reportsApi.setPublished).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Publish' }))
    await waitFor(() => expect(reportsApi.setPublished).toHaveBeenCalledWith(7, true))
    expect(onPublishedChange).toHaveBeenCalledWith(true)
    await waitFor(() => expect(everyone).toHaveAttribute('aria-checked', 'true'))
  })

  it('cancelling the question publishes nothing and changes nothing (F-08)', async () => {
    open()
    const everyone = await screen.findByRole('radio', { name: /Everyone in your organisation/ })
    fireEvent.click(everyone)
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(reportsApi.setPublished).not.toHaveBeenCalled()
    expect(everyone).toHaveAttribute('aria-checked', 'false')
  })

  it('making a published dashboard private is asked about too (F-08)', async () => {
    vi.mocked(reportsApi.setPublished).mockResolvedValue({ published: false } as never)
    open({ report: report({ published: true }) })
    fireEvent.click(await screen.findByRole('radio', { name: /Restricted/ }))
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('Make “Sales” private?')
    expect(reportsApi.setPublished).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Make private' }))
    await waitFor(() => expect(reportsApi.setPublished).toHaveBeenCalledWith(7, false))
  })

  it("shows the publish gate's message when publishing is refused", async () => {
    vi.mocked(reportsApi.setPublished).mockRejectedValue({ response: { data: { detail: { message: 'Fix 2 review findings first' } } } })
    open()
    fireEvent.click(await screen.findByRole('radio', { name: /Everyone in your organisation/ }))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Publish' }))
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
    expect(screen.queryByRole('tab', { name: 'Embed' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Schedule' })).not.toBeInTheDocument()
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
