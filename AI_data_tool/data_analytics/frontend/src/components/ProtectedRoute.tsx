import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useT } from '../i18n'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  const t = useT()
  if (loading) return <div style={{ padding: 40, color: 'var(--muted)' }}>{t('common.loading')}</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
