import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AdminRoles from './AdminRoles'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

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
    expect(await screen.findByText('Analyst')).toBeInTheDocument()
  })

  it('shows the genuine empty state when the load succeeds with zero roles', async () => {
    renderPage()
    expect(await screen.findByText('No roles yet')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
