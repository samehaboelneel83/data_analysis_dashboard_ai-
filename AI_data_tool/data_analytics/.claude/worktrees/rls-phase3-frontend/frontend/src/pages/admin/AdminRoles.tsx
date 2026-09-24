import { useEffect, useState } from 'react'
import { adminRolesApi } from '../../services/api'
import type { Role } from '../../services/api'
import toast from 'react-hot-toast'

function RoleModal({ initial, onSave, onClose }: {
  initial?: Role | null
  onSave: (r: Role) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [name, setName] = useState(initial?.name ?? '')
  const [isOrgAdmin, setIsOrgAdmin] = useState(initial?.is_org_admin ?? false)
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRolesApi.update(initial!.id, { name, is_org_admin: isOrgAdmin })
        : await adminRolesApi.create({ name, is_org_admin: isOrgAdmin })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Role created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 400 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Role' : 'New Role'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role Name *</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Regional Manager" {...inp} />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
          <input type="checkbox" checked={isOrgAdmin} onChange={e => setIsOrgAdmin(e.target.checked)} />
          <span style={{ fontSize: 12 }}>Org admin (bypasses all row-security rules, can manage users/roles/rules)</span>
        </label>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRoles() {
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | Role | null>(null)

  useEffect(() => {
    adminRolesApi.list()
      .then(setRoles)
      .catch((e: any) => toast.error(e?.response?.data?.detail ?? 'Failed to load roles'))
      .finally(() => setLoading(false))
  }, [])

  const handleSaved = (r: Role) => {
    setRoles(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (r: Role) => {
    if (!confirm(`Delete role "${r.name}"?`)) return
    try {
      await adminRolesApi.delete(r.id)
      setRoles(prev => prev.filter(x => x.id !== r.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Roles</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')}>+ New Role</button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && roles.length === 0 && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No roles yet
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{r.name}</div>
              {r.is_org_admin && <div style={{ fontSize: 11, color: 'var(--accent)' }}>Org admin</div>}
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <RoleModal initial={modal === 'add' ? null : modal} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
