import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function RequireAdmin() {
  const { user } = useAuth()
  // Rendered only inside ProtectedRoute, so `user` is guaranteed non-null here —
  // this is a client-side UX guard only; the backend's require_org_admin dependency
  // is the actual enforcement (403 on every /admin/* endpoint for non-admins).
  if (!user?.role.is_org_admin) return <Navigate to="/" replace />
  return <Outlet />
}
