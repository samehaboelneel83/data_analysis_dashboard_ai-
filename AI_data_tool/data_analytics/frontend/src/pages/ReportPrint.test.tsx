import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ReportPrint from './ReportPrint'
import { reportsApi } from '../services/api'

vi.mock('../services/api', () => ({
  reportsApi: { get: vi.fn() },
  datasetsApi: { get: vi.fn() },
}))

function renderAt(id = 1) {
  return render(
    <MemoryRouter initialEntries={[`/reports/${id}/print`]}>
      <Routes><Route path="/reports/:id/print" element={<ReportPrint />} /></Routes>
    </MemoryRouter>
  )
}

describe('ReportPrint loading and error states', () => {
  beforeEach(() => { vi.mocked(reportsApi.get).mockReset() })

  it('shows the shared loading state before the report arrives', () => {
    vi.mocked(reportsApi.get).mockReturnValue(new Promise(() => {}))
    renderAt()
    expect(screen.getByText('Preparing print view…')).toBeInTheDocument()
  })

  it('shows a retry-capable error banner, not a bare error string, when the report fails to load', async () => {
    vi.mocked(reportsApi.get).mockRejectedValue({ response: { data: { detail: 'Report not found' } } })
    renderAt()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/could not load/i)).toBeInTheDocument()
    expect(screen.getByText('Report not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('retries the load when "Try again" is clicked', async () => {
    vi.mocked(reportsApi.get)
      .mockRejectedValueOnce({ response: { data: { detail: 'Report not found' } } })
      .mockResolvedValueOnce({ id: 1, name: 'Sales', dataset_id: null, pages: [] } as any)
    renderAt()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    screen.getByRole('button', { name: /try again/i }).click()

    await waitFor(() => expect(screen.getByText('Sales')).toBeInTheDocument())
    expect(reportsApi.get).toHaveBeenCalledTimes(2)
  })
})
