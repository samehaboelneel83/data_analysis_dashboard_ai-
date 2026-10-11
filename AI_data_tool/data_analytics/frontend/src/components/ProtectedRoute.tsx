import { useT } from '../i18n'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute() {
  const t9 = useT()
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40, color: 'var(--muted)' }}>{t9('common.loading')}</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
