import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import AdminRoles from './AdminRoles'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../services/api', () => ({
  adminRolesApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  },
}))

import { adminRolesApi } from '../../services/api'

const renderPage = () => render(<ConfirmProvider><AdminRoles /></ConfirmProvider>)

describe('AdminRoles load failure', () => {
  it('shows a persistent LoadError banner instead of "No roles yet" when the initial load fails', async () => {
    vi.mocked(adminRolesApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('db down')).toBeInTheDocument()
    expect(screen.queryByText('No roles yet')).not.toBeInTheDocument()
  })

  it('recovers on retry: the banner disappears and real content renders', async () => {
    vi.mocked(adminRolesApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()
    await screen.findByRole('alert')

    vi.mocked(adminRolesApi.list).mockResolvedValueOnce([{ id: 1, name: 'Analyst', is_org_admin: false }])
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    // The name now shows twice: in the list and in the permission matrix (QA E-08).
    expect((await screen.findAllByText('Analyst'))[0]).toBeInTheDocument()
  })

  it('shows the genuine empty state when the load succeeds with zero roles', async () => {
    renderPage()
    expect(await screen.findByText('No roles yet')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('AdminRoles permission matrix (QA E-08)', () => {
  const roles = [
    { id: 1, name: 'Admin', is_org_admin: true, permissions: { upload_data: true, create_connection: true, create_dashboard: true, use_ai: true, export: true } },
    { id: 2, name: 'Analyst', is_org_admin: false, permissions: { upload_data: true, create_connection: true, create_dashboard: true, use_ai: true, export: false } },
  ]

  it('shows roles x permissions, admin rows locked on, and saves a change at once', async () => {
    vi.mocked(adminRolesApi.list).mockResolvedValueOnce(roles as never)
    vi.mocked(adminRolesApi.update).mockResolvedValueOnce({ ...roles[1], permissions: { ...roles[1].permissions, upload_data: false } } as never)
    renderPage()
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('columnheader').map(h => h.textContent)).toEqual(
      ['Role', 'Upload data', 'Add connections', 'Create dashboards', 'Use AI', 'Download and export'])
    const adminUpload = screen.getByRole('checkbox', { name: 'Upload data for Admin' })
    expect(adminUpload).toBeChecked()
    expect(adminUpload).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Download and export for Analyst' })).not.toBeChecked()
    const upload = screen.getByRole('checkbox', { name: 'Upload data for Analyst' })
    expect(upload).toBeChecked()
    fireEvent.click(upload)
    await waitFor(() => expect(adminRolesApi.update).toHaveBeenCalledWith(2, { permissions: { upload_data: false } }))
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Upload data for Analyst' })).not.toBeChecked())
  })

  it('a role from an older server (no permissions) shows every box on', async () => {
    vi.mocked(adminRolesApi.list).mockResolvedValueOnce([{ id: 3, name: 'Old', is_org_admin: false }] as never)
    renderPage()
    expect(await screen.findByRole('checkbox', { name: 'Use AI for Old' })).toBeChecked()
  })
})
