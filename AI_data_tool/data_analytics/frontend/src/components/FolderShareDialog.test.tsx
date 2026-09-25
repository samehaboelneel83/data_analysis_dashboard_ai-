import { renderWithProviders as render, screen, waitFor, fireEvent } from '../test/renderWithProviders'
import { within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FolderShareDialog from './FolderShareDialog'
import { workspaceApi } from '../services/api'

/**
 * The share dialog for a workspace folder. What carries risk:
 *
 *   - Every change goes through the replace-the-list PUT, sending the rows
 *     that should REMAIN — remove must not send the removed row, add must
 *     resend the existing ones (or it would silently unshare everyone else).
 *   - Grant rows render the server-resolved names (email, role, team), never
 *     bare ids.
 */

vi.mock('../services/api', () => ({
  workspaceApi: {
    grants: vi.fn(),
    setGrants: vi.fn(),
    shareOptions: vi.fn(),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const node = { id: 7, parent_id: null, node_type: 'folder' as const, name: 'Sales HQ',
  report_id: null, position: 0, can_manage: true, is_mine: true, role_ids: [],
  pages: [], children: [] }

const userGrant = { id: 1, level: 'view' as const, user_id: 10,
  user_email: 'analyst@contoso.invalid', role_id: null, role_name: null,
  org_unit_id: null, org_unit_name: null }
const teamGrant = { id: 2, level: 'edit' as const, user_id: null, user_email: null,
  role_id: null, role_name: null, org_unit_id: 3, org_unit_name: 'Sales' }

// A real org chart: Country > Region > Department, plus a team under it.
const options = {
  roles: [{ id: 5, name: 'viewers' }],
  org_units: [
    { id: 9, name: 'Egypt', parent_id: null, level_name: 'Country' },
    { id: 8, name: 'Alexandria', parent_id: 9, level_name: 'Region' },
    { id: 3, name: 'Sales', parent_id: 8, level_name: 'Department' },
    { id: 4, name: 'Field team', parent_id: 3, level_name: 'Team' },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(workspaceApi.grants as any).mockResolvedValue([userGrant, teamGrant])
  ;(workspaceApi.shareOptions as any).mockResolvedValue(options)
  ;(workspaceApi.setGrants as any).mockResolvedValue([])
})

describe('FolderShareDialog', () => {
  it('lists the existing shares with resolved names', async () => {
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    expect(await screen.findByText('analyst@contoso.invalid')).toBeTruthy()
    // The row names the TIER it was given to, not a blanket "Team".
    expect(screen.getByText('Department: Sales')).toBeTruthy()
  })

  it('adding a member sends the existing rows PLUS the new one', async () => {
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    await screen.findByText('analyst@contoso.invalid')
    fireEvent.change(screen.getByLabelText('Member email'),
      { target: { value: 'new@contoso.invalid' } })
    fireEvent.change(screen.getByLabelText('Access level'), { target: { value: 'edit' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(workspaceApi.setGrants).toHaveBeenCalledWith(7, [
      { user_email: 'analyst@contoso.invalid', level: 'view' },
      { org_unit_id: 3, level: 'edit' },
      { user_email: 'new@contoso.invalid', level: 'edit' },
    ]))
  })

  it('adding a team uses the picker from share-options', async () => {
    ;(workspaceApi.grants as any).mockResolvedValue([])
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    await screen.findByLabelText('Share with')
    fireEvent.change(screen.getByLabelText('Share with'), { target: { value: 'unit:Team' } })
    fireEvent.change(await screen.findByLabelText('Team to share with'),
      { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(workspaceApi.setGrants).toHaveBeenCalledWith(7, [
      { org_unit_id: 4, level: 'view' },
    ]))
  })

  it('removing a share resends only the rows that remain', async () => {
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    await screen.findByText('analyst@contoso.invalid')
    fireEvent.click(screen.getByLabelText('Stop sharing with analyst@contoso.invalid'))
    await waitFor(() => expect(workspaceApi.setGrants).toHaveBeenCalledWith(7, [
      { org_unit_id: 3, level: 'edit' },
    ]))
  })

  it('changing a level resends the full list with the new level', async () => {
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    await screen.findByText('analyst@contoso.invalid')
    fireEvent.change(screen.getByLabelText('Access level for analyst@contoso.invalid'),
      { target: { value: 'edit' } })
    await waitFor(() => expect(workspaceApi.setGrants).toHaveBeenCalledWith(7, [
      { user_email: 'analyst@contoso.invalid', level: 'edit' },
      { org_unit_id: 3, level: 'edit' },
    ]))
  })

  it('offers every tier of the org chart as its own share-with option', async () => {
    // One combined "Team, department, region…" hid every other tier behind a
    // label that named only the last one. Each tier is now a first-class choice.
    ;(workspaceApi.grants as any).mockResolvedValue([])
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    const picker = await screen.findByLabelText('Share with')
    expect([...picker.querySelectorAll('option')].map(o => o.textContent))
      .toEqual(['Member', 'Role', 'Country', 'Region', 'Department', 'Team'])
  })

  it('shows each unit by its full path, so two same-named teams differ', async () => {
    ;(workspaceApi.grants as any).mockResolvedValue([])
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Share with'), { target: { value: 'unit:Department' } })
    const picker = await screen.findByLabelText('Department to share with')
    expect(within(picker).getByRole('option', { name: 'Egypt › Alexandria › Sales' }))
      .toBeTruthy()
    expect(within(picker).queryByRole('option', { name: 'Egypt' })).toBeNull()
  })

  it('shares with a country, not only with a team', async () => {
    ;(workspaceApi.grants as any).mockResolvedValue([])
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Share with'), { target: { value: 'unit:Country' } })
    fireEvent.change(await screen.findByLabelText('Country to share with'),
      { target: { value: '9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(workspaceApi.setGrants).toHaveBeenCalledWith(7, [
      { org_unit_id: 9, level: 'view' },
    ]))
  })

  it('says the share is live and interactive, not a snapshot', async () => {
    // The user requirement this feature exists for; the dialog must say it.
    render(<FolderShareDialog node={node} onClose={() => {}} />)
    await screen.findByText('analyst@contoso.invalid')
    expect(screen.getByText(/live/)).toBeTruthy()
  })
})
