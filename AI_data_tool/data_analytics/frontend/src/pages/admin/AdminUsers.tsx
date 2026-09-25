import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { adminUsersApi, adminRolesApi } from '../../services/api'
import type { User, Role } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useModalDialog } from '../../components/ui/useModalDialog'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'
import EmptyState from '../../components/ui/EmptyState'
import { Plus, Users as UsersIcon } from 'lucide-react'

function UserModal({ initial, roles, onSave, onClose }: {
  initial?: User | null
  roles: Role[]
  onSave: (u: User) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [email, setEmail] = useState(initial?.email ?? '')
  const [password, setPassword] = useState('')
  const [roleId, setRoleId] = useState<number | ''>(initial?.role.id ?? roles[0]?.id ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [saving, setSaving] = useState(false)

  const inp = { style: fieldStyle }

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
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? "Edit user" : "New user"}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 420, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
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

interface BulkResult { created_count: number; created: string[]; errors: { row: number; email: string; error: string }[] }

function BulkImportModal({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<BulkResult | null>(null)

  // One user per line: email,password,role. A header line (email,password,...) is skipped.
  const parse = (raw: string) => raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
    .map(line => {
      const parts = line.split(',').map(c => c.trim())
      return { email: parts[0] ?? '', password: parts[1] ?? '', role: (parts.slice(2).join(',')).trim() }
    })
    .filter(r => !(r.email.toLowerCase() === 'email' && r.password.toLowerCase() === 'password'))

  const submit = async () => {
    const rows = parse(text)
    if (rows.length === 0) { toast.error('Paste at least one row'); return }
    setBusy(true)
    try {
      const r = await adminUsersApi.bulkCreate(rows)
      setResult(r)
      if (r.created_count > 0) { toast.success(`Created ${r.created_count} user${r.created_count === 1 ? '' : 's'}`); onDone() }
      else toast.error('No users created — see the report below')
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'Bulk import failed') }
    finally { setBusy(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label="Bulk import users"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 520, maxWidth: '92vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Bulk import users</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
          One user per line: <code style={{ fontFamily: 'var(--mono)' }}>email,password,role</code> (role by name).
          A header line is skipped. Valid rows are created; invalid rows are reported.
        </div>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={8}
          aria-label="Bulk users CSV"
          placeholder={'email,password,role\nalice@acme.com,Passw0rd!,Analyst\nbob@acme.com,Passw0rd!,Viewer'}
          style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--mono)', fontSize: 12, padding: '8px',
            background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', resize: 'vertical' }} />
        {result && (
          <div style={{ marginTop: 12, fontSize: 12 }}>
            <div style={{ color: '#34d399', fontWeight: 600 }}>Created {result.created_count} user{result.created_count === 1 ? '' : 's'}</div>
            {result.errors.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 4 }}>{result.errors.length} row{result.errors.length === 1 ? '' : 's'} skipped:</div>
                <ul style={{ margin: 0, paddingInlineStart: 18, color: 'var(--muted)' }}>
                  {result.errors.map((e, i) => <li key={i}>Row {e.row} ({e.email || '—'}): {e.error}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={submit} disabled={busy} style={{ flex: 1 }}>
            {busy ? 'Importing…' : 'Import'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Close</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const t = useT()
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal, setModal] = useState<'add' | User | null>(null)
  const [bulk, setBulk] = useState(false)

  const loadUsers = () => adminUsersApi.list().then(setUsers).catch(() => {})

  // A load failure gets the persistent inline banner below, not a toast: this is
  // the page's whole content going missing, not a transient action result. Falling
  // through to "No users yet" / "Create a role first" here would tell an admin
  // their org is empty when the server is simply unreachable right now.
  const load = () => {
    setLoadError(null)
    return Promise.all([adminUsersApi.list(), adminRolesApi.list()])
      .then(([u, r]) => { setUsers(u); setRoles(r) })
      .catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const handleSaved = (u: User) => {
    setUsers(prev => {
      const idx = prev.findIndex(x => x.id === u.id)
      return idx >= 0 ? prev.map(x => x.id === u.id ? u : x) : [u, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (u: User) => {
    if (!await confirm({ title: `Delete user "${u.email}"?`, body: 'This cannot be undone.' })) return
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
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.users')}</h1>
        <button className="btn btn-ghost" onClick={() => setBulk(true)} disabled={loading || roles.length === 0} title={loading ? 'Loading roles…' : roles.length === 0 ? 'Create a role first: every user needs one' : undefined}
          style={{ marginInlineEnd: 8 }}>
          {t('admin.bulkImport')}
        </button>
        <button className="btn btn-primary" onClick={() => setModal('add')} disabled={loading || roles.length === 0} title={loading ? 'Loading roles…' : roles.length === 0 ? 'Create a role first: every user needs one' : undefined}>
          <Plus size={16} aria-hidden /> {t('admin.newUser')}
        </button>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="users" error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && roles.length === 0 && (
        <div className="dl-conn-notice">
          Create a role first — every user needs one.
        </div>
      )}

      {!loading && loadError == null && users.length === 0 && roles.length > 0 && (
        <EmptyState icon={UsersIcon} title="No users yet"
          description="Invite teammates and assign them a role to get started." />
      )}

      <div className="dl-rows">
        {users.map(u => (
          <div key={u.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title">
                {u.email}
                {!u.is_active && <span style={{ marginInlineStart: 8, fontSize: 11, color: 'var(--danger)' }}>Inactive</span>}
              </div>
              <div className="dl-rows__meta">{u.role.name}{u.role.is_org_admin ? ' (admin)' : ''}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(u)}>{t('admin.edit')}</button>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => handleDelete(u)}>{t('admin.delete')}</button>
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
      {bulk && <BulkImportModal onDone={loadUsers} onClose={() => setBulk(false)} />}
    </div>
  )
}
