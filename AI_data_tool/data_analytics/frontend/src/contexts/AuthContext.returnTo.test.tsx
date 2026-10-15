import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './AuthContext'
import ProtectedRoute from '../components/ProtectedRoute'
import Login from '../pages/Login'
import { DirectionProvider } from './DirectionContext'

/**
 * AD-12 end to end, with the REAL AuthProvider, ProtectedRoute and Login (the
 * page tests mock AuthContext). Found in a real browser on 2026-10-15: a
 * signed-out visit to /ask?dataset=1 went to /login with the target in
 * history.state, but after signing in the person landed on Home --
 * AuthContext.login pushed "/" itself before Login could read the target.
 */

let signedIn = false
vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  takeLegacyToken: () => null,
  setUnauthorizedHandler: () => {},
  authApi: {
    me: vi.fn(async () => {
      if (!signedIn) throw Object.assign(new Error('401'), { response: { status: 401 } })
      return { id: 1, email: 'a@b.co', name: 'A', org_id: 1 }
    }),
    login: vi.fn(async () => { signedIn = true }),
    logout: vi.fn(async () => {}),
    adoptSession: vi.fn(async () => {}),
  },
}))

beforeEach(() => {
  signedIn = false
  window.history.replaceState(null, '', '/ask?dataset=1')
})
afterEach(() => { window.history.replaceState(null, '', '/') })

describe('signing in after a deep link (AD-12, real AuthProvider)', () => {
  it('lands on the page that asked for the sign-in, not on Home', async () => {
    render(
      <BrowserRouter>
        <DirectionProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/" element={<div>home page</div>} />
                <Route path="/ask" element={<div>ask page</div>} />
              </Route>
            </Routes>
          </AuthProvider>
        </DirectionProvider>
      </BrowserRouter>,
    )
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'a@b.co' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'demo-password' } })
    fireEvent.click(screen.getByRole('button', { name: /^Sign In/ }))
    // Login then hands over to window.location.replace(<target>) (pinned by
    // Login.test). jsdom does not navigate, so the router must simply NOT have
    // been sent to Home in between -- which is what lost the target.
    const { authApi } = await import('../services/api')
    await waitFor(() => expect(authApi.login).toHaveBeenCalled())
    await waitFor(() => expect(vi.mocked(authApi.me).mock.calls.length).toBeGreaterThanOrEqual(2))
    await new Promise(r => setTimeout(r, 50))
    expect(screen.queryByText('home page')).toBeNull()
    expect(window.location.pathname).toBe('/login')
    expect((window.history.state as { usr?: { from?: string } } | null)?.usr?.from).toBe('/ask?dataset=1')
  })
})
