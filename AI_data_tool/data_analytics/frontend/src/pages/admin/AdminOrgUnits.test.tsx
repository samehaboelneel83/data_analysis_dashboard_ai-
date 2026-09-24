import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import AdminOrgUnits from './AdminOrgUnits'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { PromptProvider } from '../../components/ui/PromptDialog'

/**
 * The page authors the org chart and places people in it. What matters is that
 * it renders the real nesting (a flat list from the API, nested here) and that
 * placement is saved as the user's whole set -- the server replaces wholesale,
 * so sending a partial list would silently revoke access.
 */

vi.mock('../../services/api', () => ({
  orgUnitsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
    forUser: vi.fn(), setForUser: vi.fn(), myScope: vi.fn() },
  adminUsersApi: { list: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { orgUnitsApi, adminUsersApi } from '../../services/api'

const UNITS = [
  { id: 1, parent_id: null, name: 'Egypt', level_name: 'Country', match_value: 'Egypt', position: 0, child_count: 1 },
  { id: 2, parent_id: 1, name: 'Alexandria', level_name: 'Region', match_value: 'Alexandria', position: 0, child_count: 1 },
  { id: 3, parent_id: 2, name: 'Engineering', level_name: 'Department', match_value: 'Engineering', position: 0, child_count: 2 },
  { id: 4, parent_id: 3, name: 'Software', level_name: 'Team', match_value: 'Software', position: 0, child_count: 0 },
  { id: 5, parent_id: 3, name: 'Network', level_name: 'Team', match_value: 'Network', position: 0, child_count: 0 },
]

const renderPage = () => render(<ConfirmProvider><PromptProvider><AdminOrgUnits /></PromptProvider></ConfirmProvider>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(orgUnitsApi.list).mockResolvedValue(UNITS as never)
  vi.mocked(orgUnitsApi.forUser).mockResolvedValue([] as never)
  vi.mocked(orgUnitsApi.setForUser).mockResolvedValue({ org_unit_ids: [] } as never)
  vi.mocked(adminUsersApi.list).mockResolvedValue([
    { id: 21, email: 'analyst@ex.com' },
  ] as never)
})

describe('AdminOrgUnits', () => {
  it('nests the flat list the API returns', async () => {
    renderPage()
    expect(await screen.findByText('Egypt')).toBeInTheDocument()
    // Descendants are only visible once their ancestors are expanded, which is
    // itself the proof that the nesting was built rather than a flat render.
    fireEvent.click(screen.getByLabelText('Expand Alexandria'))
    fireEvent.click(await screen.findByLabelText('Expand Engineering'))
    expect(await screen.findByText('Software')).toBeInTheDocument()
    expect(screen.getByText('Network')).toBeInTheDocument()
  })

  it('shows each unit’s level so the hierarchy reads as an org chart', async () => {
    renderPage()
    await screen.findByText('Egypt')
    expect(screen.getByText('Country')).toBeInTheDocument()
    expect(screen.getByText('Region')).toBeInTheDocument()
  })

  it('saves a placement as the complete set of units', async () => {
    // The server REPLACES placements wholesale, so a partial list would
    // silently revoke the ones left out.
    renderPage()
    await screen.findByText('Egypt')
    fireEvent.change(screen.getByLabelText('Place a user'), { target: { value: '21' } })
    await waitFor(() => expect(orgUnitsApi.forUser).toHaveBeenCalledWith(21))

    fireEvent.click(screen.getByLabelText('Place at Egypt'))
    fireEvent.click(screen.getByLabelText('Place at Alexandria'))
    fireEvent.click(screen.getByRole('button', { name: 'Save placement' }))

    await waitFor(() => expect(orgUnitsApi.setForUser).toHaveBeenCalledWith(21, [1, 2]))
  })

  it('offers no placement checkboxes until a user is chosen', async () => {
    renderPage()
    await screen.findByText('Egypt')
    expect(screen.queryByLabelText('Place at Egypt')).not.toBeInTheDocument()
  })

  it('warns that deleting a unit removes the subtree and the access with it', async () => {
    renderPage()
    await screen.findByText('Egypt')
    fireEvent.click(screen.getByLabelText('Delete Egypt'))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent(/Everything beneath it is deleted/)
    expect(dialog).toHaveTextContent(/loses that access/)

    // Cancelling must not call the API -- rendering the dialog proves nothing.
    fireEvent.click(within(dialog).getByRole('button', { name: /Cancel/i }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(orgUnitsApi.remove).not.toHaveBeenCalled()
  })

  it('says what to do when there is no hierarchy yet', async () => {
    vi.mocked(orgUnitsApi.list).mockResolvedValue([] as never)
    renderPage()
    expect(await screen.findByText('No hierarchy yet')).toBeInTheDocument()
  })

  it('renders a load failure as an error, not an empty chart', async () => {
    vi.mocked(orgUnitsApi.list).mockRejectedValue(new Error('down'))
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText('No hierarchy yet')).not.toBeInTheDocument()
  })

  it('retries a failed load from the error banner and recovers', async () => {
    vi.mocked(orgUnitsApi.list)
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(UNITS as never)
    renderPage()

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Egypt')).toBeInTheDocument()
  })
})
