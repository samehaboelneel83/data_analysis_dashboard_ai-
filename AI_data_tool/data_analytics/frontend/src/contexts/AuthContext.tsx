import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi, getAuthToken, setAuthToken, setUnauthorizedHandler } from '../services/api'
import type { User } from '../services/api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

// Exported (not just useAuth) so call sites that want an admin-only UI hint
// without hard-requiring a provider (e.g. a page under test in isolation) can
// read it via useContext directly and fall back sanely instead of throwing.
export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const logout = () => {
    setAuthToken(null)
    setUser(null)
    navigate('/login', { replace: true })
  }

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      navigate('/login', { replace: true })
    })
    return () => setUnauthorizedHandler(null)
  }, [navigate])

  useEffect(() => {
    const token = getAuthToken()
    if (!token) {
      setLoading(false)
      return
    }
    authApi.me()
      .then(setUser)
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password)
    setAuthToken(access_token)
    try {
      const me = await authApi.me()
      setUser(me)
    } catch (e) {
      // Roll back the token — a login that can't be confirmed via /auth/me should not
      // leave a "logged in but no user" state; the caller's catch will show the error.
      setAuthToken(null)
      throw e
    }
    navigate('/')
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/** Non-throwing auth read: returns null outside a provider instead of raising.
 *  For components (like ReportBuilder) that are also mounted in test harnesses
 *  without the provider and only need auth as an optional signal. */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext)
}
