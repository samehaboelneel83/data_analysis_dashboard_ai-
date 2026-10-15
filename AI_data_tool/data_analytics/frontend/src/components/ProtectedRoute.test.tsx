import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'

let auth: { user: unknown; loading: boolean } = { user: null, loading: false }
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))

function LoginProbe() {
  const loc = useLocation()
  return <div data-testid="login">{String((loc.state as { from?: string } | null)?.from ?? '')}</div>
}

const at = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/login" element={<LoginProbe />} />
      <Route element={<ProtectedRoute />}><Route path="/reports/:id" element={<div>report</div>} /></Route>
    </Routes>
  </MemoryRouter>,
)

beforeEach(() => { auth = { user: null, loading: false } })

describe('ProtectedRoute', () => {
  it('sends a signed-out visit to /login carrying where it was going (AD-12)', () => {
    at('/reports/1?page=2#w5')
    expect(screen.getByTestId('login')).toHaveTextContent('/reports/1?page=2#w5')
  })

  it('shows the app loader, not bare text, while the session is checked (AD-13)', () => {
    auth = { user: null, loading: true }
    at('/reports/1')
    const status = screen.getByRole('status')
    expect(status).toHaveClass('dl-loading')
  })

  it('renders the page for a signed-in user', () => {
    auth = { user: { id: 1 }, loading: false }
    at('/reports/1')
    expect(screen.getByText('report')).toBeInTheDocument()
  })
})
