import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function RequireSuperAdmin() {
  const { user } = useAuth()
  // Client-side UX guard only; the backend's require_super_admin dependency is the
  // actual enforcement (403 on every /platform/* endpoint for non-super-admins).
  if (!user?.is_super_admin) return <Navigate to="/" replace />
  return <Outlet />
}
