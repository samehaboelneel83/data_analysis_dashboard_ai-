import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import PlatformOrgs from './PlatformOrgs'

vi.mock('../../services/api', () => {
  const noQuota = { max_queries_per_day: null, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null }
  const noUsage = { queries_today: 0, agent_asks_today: 0, storage_bytes: 0 }
  return {
  platformApi: {
    listOrgs: vi.fn().mockResolvedValue([
      { id: 1, name: 'Parent Co', user_count: 3, parent_org_id: null, mcp_enabled: true, quota: noQuota, usage: noUsage },
      { id: 2, name: 'Child Co', user_count: 1, parent_org_id: null, mcp_enabled: false, quota: noQuota,
        usage: { queries_today: 4, agent_asks_today: 1, storage_bytes: 2 * 1024 * 1024 } },
    ]),
    createOrg: vi.fn().mockResolvedValue({ org_id: 9, name: 'Acme', admin_user_id: 5, admin_email: 'a@acme.com' }),
    setParent: vi.fn().mockResolvedValue({ org_id: 2, parent_org_id: 1 }),
    setMcp: vi.fn().mockResolvedValue({ org_id: 2, mcp_enabled: true }),
    setQuota: vi.fn().mockResolvedValue({ org_id: 2, max_queries_per_day: 100, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null }),
  },
  }
})

import { platformApi } from '../../services/api'

describe('PlatformOrgs', () => {
  it('lists orgs and provisions a new one', async () => {
    render(<PlatformOrgs />)
    expect(await screen.findByText(/3 users/)).toBeInTheDocument()   // the Parent Co row

    fireEvent.change(screen.getByLabelText('Organization name'), { target: { value: 'Acme' } })
    fireEvent.change(screen.getByLabelText('Admin email'), { target: { value: 'a@acme.com' } })
    fireEvent.change(screen.getByLabelText('Admin password'), { target: { value: 'pw' } })
    expect(screen.getByLabelText('Admin password')).toHaveAttribute('autoComplete', 'new-password')
    expect(screen.getByLabelText('Admin email')).toHaveAttribute('autoComplete', 'off')
    fireEvent.click(screen.getByRole('button', { name: 'Create organization' }))

    await waitFor(() => expect(platformApi.createOrg).toHaveBeenCalledWith(
      { name: 'Acme', admin_email: 'a@acme.com', admin_password: 'pw' }))
  })

  it('sets a parent from the per-org dropdown', async () => {
    render(<PlatformOrgs />)
    fireEvent.change(await screen.findByLabelText('Parent of Child Co'), { target: { value: '1' } })
    await waitFor(() => expect(platformApi.setParent).toHaveBeenCalledWith(2, 1))
  })

  it('activates MCP for an org via its toggle', async () => {
    render(<PlatformOrgs />)
    // Child Co starts disabled; ticking the box activates it
    fireEvent.click(await screen.findByLabelText('MCP access for Child Co'))
    await waitFor(() => expect(platformApi.setMcp).toHaveBeenCalledWith(2, true))
  })

  it('shows usage vs quota for each org', async () => {
    render(<PlatformOrgs />)
    expect(await screen.findByText(/Queries today: 4 \/ unlimited/)).toBeInTheDocument()
    expect(screen.getByText(/Storage: 2\.0 MB \/ unlimited/)).toBeInTheDocument()
  })

  it('edits and saves a quota for an org', async () => {
    render(<PlatformOrgs />)
    const editButtons = await screen.findAllByRole('button', { name: 'Edit quota' })
    fireEvent.click(editButtons[1])   // Child Co's row

    fireEvent.change(screen.getByLabelText('Max queries per day for Child Co'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save quota' }))

    await waitFor(() => expect(platformApi.setQuota).toHaveBeenCalledWith(2, {
      max_queries_per_day: 100, max_agent_asks_per_day: null, max_storage_mb: null, max_concurrent_asks: null,
    }))
  })
})

describe('PlatformOrgs loading, empty, and error states', () => {
  it('shows an empty state instead of a bare blank list when there are no organizations', async () => {
    vi.mocked(platformApi.listOrgs).mockResolvedValueOnce([])
    render(<PlatformOrgs />)
    await waitFor(() => expect(screen.getByText(/no organizations yet/i)).toBeInTheDocument())
  })

  it('shows a retry-capable error banner, not a silent empty list, when the load fails', async () => {
    vi.mocked(platformApi.listOrgs).mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
    render(<PlatformOrgs />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    // The load failure must not also render the empty state underneath the error.
    expect(screen.queryByText(/no organizations yet/i)).toBeNull()
  })

  it('retries the load when "Try again" is clicked, and clears the error once it succeeds', async () => {
    vi.mocked(platformApi.listOrgs)
      .mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
      .mockResolvedValueOnce([])
    render(<PlatformOrgs />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/no organizations yet/i)).toBeInTheDocument())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
