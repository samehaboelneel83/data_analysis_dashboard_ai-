import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { nodesT } from '../../i18n/pages/adminSecurity'
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
  const t = useT()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [email, setEmail] = useState(initial?.email ?? '')
  const [password, setPassword] = useState('')
  const [roleId, setRoleId] = useState<number | ''>(initial?.role.id ?? roles[0]?.id ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [saving, setSaving] = useState(false)

  const inp = { style: fieldStyle }

  const handleSave = async () => {
    if (!email.trim()) { toast.error(t('pg.adminSecurity.users.emailRequired')); return }
    if (!isEdit && !password) { toast.error(t('pg.adminSecurity.users.passwordRequired')); return }
    if (roleId === '') { toast.error(t('pg.adminSecurity.users.roleRequired')); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminUsersApi.update(initial!.id, {
            email, role_id: roleId as number, is_active: isActive,
            ...(password ? { password } : {}),
          })
        : await adminUsersApi.create({ email, password, role_id: roleId as number })
      onSave(result)
      toast.success(isEdit ? t('pg.adminSecurity.c.updated') : t('pg.adminSecurity.users.created'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.c.saveFailed'))
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? t('pg.adminSecurity.users.editAria') : t('pg.adminSecurity.users.newAria')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 420, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? t('pg.adminSecurity.users.editTitle') : t('pg.adminSecurity.users.newTitle')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.users.emailLabel')}</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
            {isEdit ? t('pg.adminSecurity.users.newPasswordLabel') : t('pg.adminSecurity.users.passwordLabel')}
          </div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.c.roleReq')}</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">{t('pg.adminSecurity.c.selectRole')}</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.is_org_admin ? t('pg.adminSecurity.c.roleOptionAdmin', { name: r.name }) : r.name}</option>)}
          </select>
        </label>

        {isEdit && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            <span style={{ fontSize: 12 }}>{t('pg.adminSecurity.users.activeCheck')}</span>
          </label>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: isEdit ? 0 : 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? t('pg.adminSecurity.c.saving') : isEdit ? t('pg.adminSecurity.c.saveChanges') : t('pg.adminSecurity.c.create')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('common.cancel')}</button>
        </div>
      </div>
    </div>
  )
}

interface BulkResult { created_count: number; created: string[]; errors: { row: number; email: string; error: string }[] }

function BulkImportModal({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const t = useT()
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
    if (rows.length === 0) { toast.error(t('pg.adminSecurity.users.bulk.pasteOne')); return }
    setBusy(true)
    try {
      const r = await adminUsersApi.bulkCreate(rows)
      setResult(r)
      if (r.created_count > 0) { toast.success(t('pg.adminSecurity.users.bulk.created', { n: r.created_count })); onDone() }
      else toast.error(t('pg.adminSecurity.users.bulk.noneCreated'))
    } catch (e: any) { toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.users.bulk.failed')) }
    finally { setBusy(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={t('pg.adminSecurity.users.bulk.title')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 520, maxWidth: '92vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{t('pg.adminSecurity.users.bulk.title')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
          {nodesT(t, 'pg.adminSecurity.users.bulk.help', {
            code: <code style={{ fontFamily: 'var(--mono)' }} dir="ltr">email,password,role</code>, // i18n-ok: a CSV header
          })}
        </div>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={8}
          aria-label={t('pg.adminSecurity.users.bulk.textAria')}
          placeholder={'email,password,role\nalice@acme.com,Passw0rd!,Analyst\nbob@acme.com,Passw0rd!,Viewer'} // i18n-ok: a CSV sample
          style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--mono)', fontSize: 12, padding: '8px',
            background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', resize: 'vertical' }} />
        {result && (
          <div style={{ marginTop: 12, fontSize: 12 }}>
            <div style={{ color: '#34d399', fontWeight: 600 }}>{t('pg.adminSecurity.users.bulk.created', { n: result.created_count })}</div>
            {result.errors.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 4 }}>{t('pg.adminSecurity.users.bulk.skipped', { n: result.errors.length })}</div>
                <ul style={{ margin: 0, paddingInlineStart: 18, color: 'var(--muted)' }}>
                  {result.errors.map((e, i) => <li key={i}>{t('pg.adminSecurity.users.bulk.rowError', { row: e.row, email: e.email || '—', error: e.error })}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={submit} disabled={busy} style={{ flex: 1 }}>
            {busy ? t('pg.adminSecurity.users.bulk.importing') : t('pg.adminSecurity.users.bulk.import')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('pg.adminSecurity.users.bulk.close')}</button>
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
    if (!await confirm({ title: t('pg.adminSecurity.users.deleteTitle', { email: u.email }), body: t('pg.adminSecurity.users.deleteBody') })) return
    try {
      await adminUsersApi.delete(u.id)
      setUsers(prev => prev.filter(x => x.id !== u.id))
      toast.success(t('pg.adminSecurity.c.deleted'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.c.deleteFailed'))
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.users')}</h1>
        <button className="btn btn-ghost" onClick={() => setBulk(true)} disabled={loading || roles.length === 0} title={loading ? t('pg.adminSecurity.users.loadingRoles') : roles.length === 0 ? t('pg.adminSecurity.users.createRoleFirstTitle') : undefined}
          style={{ marginInlineEnd: 8 }}>
          {t('admin.bulkImport')}
        </button>
        <button className="btn btn-primary" onClick={() => setModal('add')} disabled={loading || roles.length === 0} title={loading ? t('pg.adminSecurity.users.loadingRoles') : roles.length === 0 ? t('pg.adminSecurity.users.createRoleFirstTitle') : undefined}>
          <Plus size={16} aria-hidden /> {t('admin.newUser')}
        </button>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="users" title={t('pg.adminSecurity.users.loadErr')} retryLabel={t('pg.adminSecurity.c.retry')} error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && roles.length === 0 && (
        <div className="dl-conn-notice">
          {t('pg.adminSecurity.users.createRoleFirst')}
        </div>
      )}

      {!loading && loadError == null && users.length === 0 && roles.length > 0 && (
        <EmptyState icon={UsersIcon} title={t('pg.adminSecurity.users.emptyTitle')}
          description={t('pg.adminSecurity.users.emptyBody')} />
      )}

      <div className="dl-rows">
        {users.map(u => (
          <div key={u.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title">
                <bdi dir="ltr">{u.email}</bdi>
                {!u.is_active && <span style={{ marginInlineStart: 8, fontSize: 11, color: 'var(--danger)' }}>{t('pg.adminSecurity.users.inactive')}</span>}
              </div>
              <div className="dl-rows__meta"><bdi>{u.role.name}</bdi>{u.role.is_org_admin && <>{' '}{t('pg.adminSecurity.c.adminTag')}</>}</div>
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
