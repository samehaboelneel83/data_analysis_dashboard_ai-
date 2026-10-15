import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AdminUsers from './AdminUsers'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { AuthContext } from '../../contexts/AuthContext'

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
import toast from 'react-hot-toast'

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

describe('AdminUsers — platform admin rows (QA E-01)', () => {
  // The server refuses an org admin's edit/delete of a platform admin; the row
  // says so instead of offering buttons that can only fail.
  const org = { id: 1, name: 'Default' }
  const rows = [
    { id: 1, email: 'platform@example.com', is_active: true, organization: org,
      role: { id: 2, name: 'Admin', is_org_admin: true }, is_super_admin: true },
    { id: 2, email: 'analyst@example.com', is_active: true, organization: org,
      role: { id: 1, name: 'Analyst', is_org_admin: false }, is_super_admin: false },
  ]
  const viewer = (isPlatformAdmin: boolean) => ({
    user: { id: 9, email: 'me@example.com', is_active: true, organization: org,
      role: { id: 2, name: 'Admin', is_org_admin: true }, is_super_admin: isPlatformAdmin },
    loading: false, login: vi.fn(), logout: vi.fn(),
  }) as never
  const renderAs = (isPlatformAdmin: boolean) => render(
    <AuthContext.Provider value={viewer(isPlatformAdmin)}>
      <ConfirmProvider><AdminUsers /></ConfirmProvider>
    </AuthContext.Provider>)

  it('an org admin sees no Edit or Delete on a platform admin, only on everyone else', async () => {
    vi.mocked(adminUsersApi.list).mockResolvedValueOnce(rows as never)
    renderAs(false)
    expect(await screen.findByText('platform@example.com')).toBeInTheDocument()
    expect(screen.getByText('Platform admin')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1)
  })

  it('a platform admin keeps both buttons on every row', async () => {
    vi.mocked(adminUsersApi.list).mockResolvedValueOnce(rows as never)
    renderAs(true)
    expect(await screen.findByText('platform@example.com')).toBeInTheDocument()
    expect(screen.queryByText('Platform admin')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(2)
  })
})

describe('AdminUsers — new user checks email and password before submitting (QA E-04)', () => {
  const openNewUser = async () => {
    renderPage()
    const add = await screen.findByRole('button', { name: /New user/i })
    await waitFor(() => expect(add).not.toBeDisabled())
    fireEvent.click(add)
    fireEvent.change(screen.getByLabelText('Role *'), { target: { value: '1' } })
  }

  it('an invalid email shows an inline error and the API is not called', async () => {
    vi.mocked(adminUsersApi.create).mockClear()
    await openNewUser()
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'not-an-email' } })
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'long-enough-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText('Enter a valid email address, like name@company.com')).toBeInTheDocument()
    expect(screen.getByLabelText('Email *')).toHaveAttribute('aria-invalid', 'true')
    expect(adminUsersApi.create).not.toHaveBeenCalled()
  })

  it('a password shorter than 8 characters shows an inline error and the API is not called', async () => {
    vi.mocked(adminUsersApi.create).mockClear()
    await openNewUser()
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText('Password must be at least 8 characters')).toBeInTheDocument()
    expect(adminUsersApi.create).not.toHaveBeenCalled()
  })

  it('valid values are submitted', async () => {
    vi.mocked(adminUsersApi.create).mockClear()
    vi.mocked(adminUsersApi.create).mockResolvedValueOnce({ id: 5, email: 'new@example.com', is_active: true,
      role: { id: 1, name: 'Analyst', is_org_admin: false }, organization: { id: 1, name: 'Default' } } as never)
    await openNewUser()
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'qa@corp.local' } })
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'long-enough-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(adminUsersApi.create).toHaveBeenCalledWith(
      { email: 'qa@corp.local', password: 'long-enough-1', role_id: 1 }))
  })
})

describe('AdminUsers — nothing is pre-selected in a new user (QA E-05)', () => {
  it('the role starts empty, and Create without a role says a role is required', async () => {
    vi.mocked(adminUsersApi.create).mockClear()
    const toastError = vi.spyOn(toast, 'error')
    renderPage()
    const add = await screen.findByRole('button', { name: /New user/i })
    await waitFor(() => expect(add).not.toBeDisabled())
    fireEvent.click(add)
    expect(screen.getByLabelText('Role *')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Password *'), { target: { value: 'long-enough-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Role is required'))
    expect(adminUsersApi.create).not.toHaveBeenCalled()
    toastError.mockRestore()
  })
})
