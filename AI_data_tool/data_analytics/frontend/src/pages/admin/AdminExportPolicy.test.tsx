import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AdminExportPolicy from './AdminExportPolicy'
import { datasetsApi, exportPolicyApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  datasetsApi: { list: vi.fn() },
  exportPolicyApi: { get: vi.fn(), setAll: vi.fn(), setGranular: vi.fn() },
}))

describe('AdminExportPolicy loading, empty, and error states', () => {
  beforeEach(() => { vi.mocked(datasetsApi.list).mockReset() })

  it('shows a loading state before the datasets arrive', () => {
    vi.mocked(datasetsApi.list).mockReturnValue(new Promise(() => {}))
    render(<AdminExportPolicy />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows the table once datasets and policies load', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 1, name: 'Sales' } as any])
    vi.mocked(exportPolicyApi.get).mockResolvedValue({ export_policy: false, has_security_rules: false })
    render(<AdminExportPolicy />)
    await waitFor(() => expect(screen.getByText('Sales')).toBeInTheDocument())
  })

  it('shows an empty state when there are no datasets at all', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([])
    render(<AdminExportPolicy />)
    await waitFor(() => expect(screen.getByText(/no datasets yet/i)).toBeInTheDocument())
  })

  it('shows a retry-capable error banner instead of a silent empty table when the load fails', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValue({ response: { data: { detail: 'Not authorized' } } })
    render(<AdminExportPolicy />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    expect(screen.queryByText(/no datasets yet/i)).toBeNull()
  })

  it('retries the load when "Try again" is clicked', async () => {
    vi.mocked(datasetsApi.list)
      .mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
      .mockResolvedValueOnce([])
    render(<AdminExportPolicy />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/no datasets yet/i)).toBeInTheDocument())
    expect(datasetsApi.list).toHaveBeenCalledTimes(2)
  })
})
