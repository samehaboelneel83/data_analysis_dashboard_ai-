import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AdminUsers from './AdminUsers'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

vi.mock('../../services/api', () => ({
  adminUsersApi: {
    list: vi.fn().mockResolvedValue([]),
    bulkCreate: vi.fn(),
    create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  },
  adminRolesApi: { list: vi.fn().mockResolvedValue([{ id: 1, name: 'Analyst', is_org_admin: false }]) },
}))

import { adminUsersApi } from '../../services/api'
import { axeViolations } from '../../test/axe'

const renderPage = () => render(<ConfirmProvider><AdminUsers /></ConfirmProvider>)

describe('AdminUsers load failure', () => {
  it('shows a persistent LoadError banner instead of the empty-state cards when the initial load fails', async () => {
    vi.mocked(adminUsersApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('db down')).toBeInTheDocument()
    // Neither the "no users" empty state nor the "create a role first" precondition
    // banner may render on a failed load -- both would misreport what actually happened.
    expect(screen.queryByText('No users yet')).not.toBeInTheDocument()
    expect(screen.queryByText(/Create a role first/)).not.toBeInTheDocument()
  })

  it('recovers on retry: the banner disappears and real content renders', async () => {
    vi.mocked(adminUsersApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()
    await screen.findByRole('alert')

    vi.mocked(adminUsersApi.list).mockResolvedValueOnce([])
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByText('No users yet')).toBeInTheDocument()
  })
})

describe('AdminUsers bulk import', () => {
  it('parses CSV rows (skipping the header), calls bulkCreate, and renders the report', async () => {
    vi.mocked(adminUsersApi.bulkCreate).mockResolvedValue({
      created_count: 1, created: ['a@x.com'],
      errors: [{ row: 2, email: 'bad', error: 'invalid email' }],
    })
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Bulk import' })).not.toBeDisabled())

    fireEvent.click(screen.getByRole('button', { name: 'Bulk import' }))
    fireEvent.change(screen.getByLabelText('Bulk users CSV'),
      { target: { value: 'email,password,role\na@x.com,pw,Analyst\nbad,pw,Analyst' } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))

    await waitFor(() => expect(adminUsersApi.bulkCreate).toHaveBeenCalledWith([
      { email: 'a@x.com', password: 'pw', role: 'Analyst' },   // header line dropped
      { email: 'bad', password: 'pw', role: 'Analyst' },
    ]))
    expect(await screen.findByText(/Created 1 user/)).toBeInTheDocument()
    expect(screen.getByText(/Row 2 \(bad\): invalid email/)).toBeInTheDocument()
  })
})

describe('AdminUsers accessibility', () => {
  it('has no structural accessibility violations', async () => {
    const { container } = renderPage()
    await screen.findByRole('heading', { name: 'Users' })
    expect(await axeViolations(container)).toEqual([])
  })
})
