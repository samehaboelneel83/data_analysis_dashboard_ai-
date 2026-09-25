import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi, setUnauthorizedHandler, takeLegacyToken } from '../services/api'
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
    // The cookie is httpOnly: only the server can remove it.
    authApi.logout().catch(() => {})
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
    // T6: the session is an httpOnly cookie, invisible to script, so the only
    // way to know whether one exists is to ask. A token an older build left in
    // localStorage is moved into the cookie first, so the upgrade logs nobody out.
    const legacy = takeLegacyToken()
    ;(legacy ? authApi.adoptSession(legacy).catch(() => {}) : Promise.resolve())
      .then(() => authApi.me({ quiet: true }))
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    await authApi.login(email, password)
    try {
      const me = await authApi.me()
      setUser(me)
    } catch (e) {
      // Roll back the session — a login that can't be confirmed via /auth/me should not
      // leave a "logged in but no user" state; the caller's catch will show the error.
      authApi.logout().catch(() => {})
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
