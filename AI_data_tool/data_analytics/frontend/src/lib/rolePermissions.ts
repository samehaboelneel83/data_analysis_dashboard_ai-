import { useContext } from 'react'
import { AuthContext } from '../contexts/AuthContext'
import type { RolePermission, User } from '../services/api'

/**
 * QA E-08: what the signed-in person's role may do, read from /auth/me.
 *
 * A UI hint only -- the server refuses the action itself with 403 (backend
 * core/role_permissions.py). An org admin may do everything; a permission
 * the server did not send (an older server) counts as allowed.
 */
export const ROLE_PERMISSIONS: readonly RolePermission[] =
  ['upload_data', 'create_connection', 'create_dashboard', 'use_ai', 'export']

export function roleAllows(user: User | null | undefined, perm: RolePermission): boolean {
  if (!user) return true
  if (user.role?.is_org_admin) return true
  return user.role?.permissions?.[perm] !== false
}

/** `roleAllows` for the current user; true outside an AuthProvider. */
export function useRoleAllows(perm: RolePermission): boolean {
  return roleAllows(useContext(AuthContext)?.user, perm)
}
