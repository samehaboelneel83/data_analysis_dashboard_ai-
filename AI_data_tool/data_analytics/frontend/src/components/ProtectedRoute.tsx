import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'
import Loader from './ui/Loader'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  const t = useT()
  const { pathname, search, hash } = useLocation()
  // AD-13: the app's own loader, as the lazy-route fallback shows it -- not
  // bare text in the corner of a blank page while /auth/me answers.
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg)' }}>
        <Loader label={t('common.loading')} />
      </div>
    )
  }
  // AD-12: carry the requested page through the sign-in.
  if (!user) return <Navigate to="/login" replace state={{ from: pathname + search + hash }} />
  return <Outlet />
}
