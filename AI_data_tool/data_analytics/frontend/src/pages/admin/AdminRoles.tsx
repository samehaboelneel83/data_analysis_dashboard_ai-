import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { Plus, Shield } from 'lucide-react'
import { adminRolesApi } from '../../services/api'
import type { Role } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useModalDialog } from '../../components/ui/useModalDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

function RoleModal({ initial, onSave, onClose }: {
  initial?: Role | null
  onSave: (r: Role) => void
  onClose: () => void
}) {
  const t = useT()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [name, setName] = useState(initial?.name ?? '')
  const [isOrgAdmin, setIsOrgAdmin] = useState(initial?.is_org_admin ?? false)
  const [saving, setSaving] = useState(false)

  const inp = { style: fieldStyle }

  const handleSave = async () => {
    if (!name.trim()) { toast.error(t('pg.adminSecurity.roles.nameRequired')); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRolesApi.update(initial!.id, { name, is_org_admin: isOrgAdmin })
        : await adminRolesApi.create({ name, is_org_admin: isOrgAdmin })
      onSave(result)
      toast.success(isEdit ? t('pg.adminSecurity.c.updated') : t('pg.adminSecurity.roles.created'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.c.saveFailed'))
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? t('pg.adminSecurity.roles.editAria') : t('pg.adminSecurity.roles.newAria')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 400, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? t('pg.adminSecurity.roles.editTitle') : t('pg.adminSecurity.roles.newTitle')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.roles.nameLabel')}</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder={t('pg.adminSecurity.roles.namePlaceholder')} {...inp} />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
          <input type="checkbox" checked={isOrgAdmin} onChange={e => setIsOrgAdmin(e.target.checked)} />
          <span style={{ fontSize: 12 }}>{t('pg.adminSecurity.roles.orgAdminCheck')}</span>
        </label>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? t('pg.adminSecurity.c.saving') : isEdit ? t('pg.adminSecurity.c.saveChanges') : t('pg.adminSecurity.c.create')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('common.cancel')}</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRoles() {
  const t = useT()
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal, setModal] = useState<'add' | Role | null>(null)

  // A load failure gets the persistent inline banner below, not a toast: this is
  // the page's whole content going missing, not a transient action result.
  const load = () => {
    setLoadError(null)
    return adminRolesApi.list().then(setRoles).catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const handleSaved = (r: Role) => {
    setRoles(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (r: Role) => {
    if (!await confirm({ title: t('pg.adminSecurity.roles.deleteTitle', { name: r.name }), body: t('pg.adminSecurity.roles.deleteBody') })) return
    try {
      await adminRolesApi.delete(r.id)
      setRoles(prev => prev.filter(x => x.id !== r.id))
      toast.success(t('pg.adminSecurity.c.deleted'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.c.deleteFailed'))
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.roles')}</h1>
        <button className="btn btn-primary" onClick={() => setModal('add')}><Plus size={16} aria-hidden /> {t('admin.newRole')}</button>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="roles" title={t('pg.adminSecurity.roles.loadErr')} retryLabel={t('pg.adminSecurity.c.retry')} error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && roles.length === 0 && (
        <EmptyState icon={Shield} title={t('pg.adminSecurity.roles.emptyTitle')}
          description={t('pg.adminSecurity.roles.emptyBody')} />
      )}

      <div className="dl-rows">
        {roles.map(r => (
          <div key={r.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title"><bdi>{r.name}</bdi></div>
              {r.is_org_admin && <div style={{ fontSize: 11, color: 'var(--accent)' }}>{t('pg.adminSecurity.roles.orgAdmin')}</div>}
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)}>{t('admin.edit')}</button>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => handleDelete(r)}>{t('admin.delete')}</button>
          </div>
        ))}
      </div>

      {modal && (
        <RoleModal initial={modal === 'add' ? null : modal} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
