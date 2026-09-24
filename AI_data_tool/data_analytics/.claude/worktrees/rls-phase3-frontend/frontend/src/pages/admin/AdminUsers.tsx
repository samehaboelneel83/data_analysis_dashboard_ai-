import { useEffect, useState } from 'react'
import { adminUsersApi, adminRolesApi } from '../../services/api'
import type { User, Role } from '../../services/api'
import toast from 'react-hot-toast'

function UserModal({ initial, roles, onSave, onClose }: {
  initial?: User | null
  roles: Role[]
  onSave: (u: User) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [email, setEmail] = useState(initial?.email ?? '')
  const [password, setPassword] = useState('')
  const [roleId, setRoleId] = useState<number | ''>(initial?.role.id ?? roles[0]?.id ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!email.trim()) { toast.error('Email is required'); return }
    if (!isEdit && !password) { toast.error('Password is required for a new user'); return }
    if (roleId === '') { toast.error('Role is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminUsersApi.update(initial!.id, {
            email, role_id: roleId as number, is_active: isActive,
            ...(password ? { password } : {}),
          })
        : await adminUsersApi.create({ email, password, role_id: roleId as number })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'User created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 420 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit User' : 'New User'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Email *</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
            {isEdit ? 'New Password (leave blank to keep current)' : 'Password *'}
          </div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}{r.is_org_admin ? ' (admin)' : ''}</option>)}
          </select>
        </label>

        {isEdit && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            <span style={{ fontSize: 12 }}>Active (unchecking deactivates the account without deleting it)</span>
          </label>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: isEdit ? 0 : 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | User | null>(null)

  useEffect(() => {
    Promise.all([adminUsersApi.list(), adminRolesApi.list()])
      .then(([u, r]) => { setUsers(u); setRoles(r) })
      .catch((e: any) => toast.error(e?.response?.data?.detail ?? 'Failed to load users'))
      .finally(() => setLoading(false))
  }, [])

  const handleSaved = (u: User) => {
    setUsers(prev => {
      const idx = prev.findIndex(x => x.id === u.id)
      return idx >= 0 ? prev.map(x => x.id === u.id ? u : x) : [u, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (u: User) => {
    if (!confirm(`Delete user "${u.email}"?`)) return
    try {
      await adminUsersApi.delete(u.id)
      setUsers(prev => prev.filter(x => x.id !== u.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Users</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')} disabled={roles.length === 0}>
          + New User
        </button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && roles.length === 0 && (
        <div style={{ padding: 16, marginBottom: 16, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 8, fontSize: 12, color: 'var(--muted)' }}>
          Create a role first — every user needs one.
        </div>
      )}

      {!loading && users.length === 0 && roles.length > 0 && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No users yet
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {users.map(u => (
          <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {u.email}
                {!u.is_active && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--danger)' }}>Inactive</span>}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>{u.role.name}{u.role.is_org_admin ? ' (admin)' : ''}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(u)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(u)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <UserModal
          initial={modal === 'add' ? null : modal}
          roles={roles}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
