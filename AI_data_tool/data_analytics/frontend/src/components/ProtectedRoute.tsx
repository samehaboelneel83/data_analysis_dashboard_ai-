import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40, color: 'var(--muted)' }}>Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
