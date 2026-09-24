import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AdminSso from './AdminSso'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { ssoApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  apiOrigin: () => 'http://localhost',
  ssoApi: { getConfig: vi.fn(), putConfig: vi.fn(), deleteConfig: vi.fn() },
}))

function renderPage() {
  return render(<ConfirmProvider><AdminSso /></ConfirmProvider>)
}

describe('AdminSso loading and error states', () => {
  beforeEach(() => { vi.mocked(ssoApi.getConfig).mockReset() })

  it('shows the shared loading state before settings arrive', () => {
    vi.mocked(ssoApi.getConfig).mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows the form once settings load successfully', async () => {
    vi.mocked(ssoApi.getConfig).mockResolvedValue({ configured: false } as any)
    renderPage()
    await waitFor(() => expect(screen.getByText('Single sign-on')).toBeInTheDocument())
    expect(screen.getByPlaceholderText('application (client) id')).toHaveAttribute('autoComplete', 'off')
    expect(screen.getByPlaceholderText('client secret')).toHaveAttribute('autoComplete', 'new-password')
  })

  it('shows a retry-capable error banner instead of a silently blank form when the load fails', async () => {
    vi.mocked(ssoApi.getConfig).mockRejectedValue({ response: { data: { detail: 'Not authorized' } } })
    renderPage()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    // The form must not render underneath/instead of the error.
    expect(screen.queryByText('Single sign-on')).toBeNull()
  })

  it('retries the load when "Try again" is clicked', async () => {
    vi.mocked(ssoApi.getConfig)
      .mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
      .mockResolvedValueOnce({ configured: false } as any)
    renderPage()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText('Single sign-on')).toBeInTheDocument())
    expect(ssoApi.getConfig).toHaveBeenCalledTimes(2)
  })
})
