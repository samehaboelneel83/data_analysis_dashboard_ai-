import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { connectorFieldLabel } from '../../i18n/pages/adminPlatform'
import { Plug, Plus } from 'lucide-react'
import { customConnectorsApi, dataSourcesApi } from '../../services/api'
import type { CustomConnector, ConnectorSpec } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useModalDialog } from '../../components/ui/useModalDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

function PresetModal({ initial, catalog, onSave, onClose }: {
  initial?: CustomConnector | null
  catalog: ConnectorSpec[]
  onSave: (cc: CustomConnector) => void
  onClose: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [key, setKey] = useState(initial?.key ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [baseType, setBaseType] = useState(initial?.base_type ?? catalog[0]?.key ?? '')
  const [values, setValues] = useState<Record<string, unknown>>(initial?.base_config ?? {})
  const [locked, setLocked] = useState<Set<string>>(new Set(initial?.locked_fields ?? []))
  const [saving, setSaving] = useState(false)

  const spec = catalog.find(s => s.key === baseType)
  const inp = { style: fieldStyle }

  const toggleLocked = (name: string) => setLocked(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  const handleSave = async () => {
    if (!key.trim() || !label.trim()) { toast.error(t('pg.adminPlatform.cc.required')); return }
    setSaving(true)
    try {
      const body = { key, label, base_type: baseType, base_config: values, locked_fields: [...locked] }
      const result = isEdit ? await customConnectorsApi.update(initial!.id, body) : await customConnectorsApi.create(body)
      onSave(result)
      toast.success(isEdit ? t('pg.adminPlatform.cc.updated') : t('pg.adminPlatform.cc.created'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.cc.saveFailed'))
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={isEdit ? t('pg.adminPlatform.cc.editAria') : t('pg.adminPlatform.cc.newAria')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? t('pg.adminPlatform.cc.editTitle') : t('pg.adminPlatform.cc.newTitle')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminPlatform.cc.label')}</div>
          <input value={label} onChange={e => setLabel(e.target.value)} {...inp}
            id="connector-label" name="connector-label" autoComplete="off"
            placeholder="Acme Snowflake" // i18n-ok: an example name
          />
        </label>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminPlatform.cc.key')}</div>
          <input value={key} onChange={e => setKey(e.target.value)} placeholder="acme-snowflake" dir="ltr" {...inp} disabled={isEdit} // i18n-ok: an example id
            id="connector-key" name="connector-key" autoComplete="off"
            title={isEdit ? t('pg.adminPlatform.cc.keyFixed') : undefined} />
        </label>
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminPlatform.cc.baseType')}</div>
          <select value={baseType} onChange={e => { setBaseType(e.target.value); setValues({}); setLocked(new Set()) }} {...inp} disabled={isEdit} title={isEdit ? t('pg.adminPlatform.cc.baseFixed') : undefined}>
            {catalog.filter(s => !s.is_custom).map(s => <option key={s.key} value={s.key}>{s.icon} {s.label}</option>)}
          </select>
        </label>

        {spec?.config_fields.map(f => (
          <div key={f.name} style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginBottom: 10 }}>
            <label style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{connectorFieldLabel(t, language, f.name, f.label)}</div>
              {/* QA5 F4: not the admin's own login -- distinct name/id and
                  autocomplete off / new-password, so the browser does not
                  fill the admin's saved username and password in here. */}
              <input value={(values[f.name] as string) ?? ''} onChange={e => setValues(p => ({ ...p, [f.name]: e.target.value }))}
                type={f.kind === 'password' ? 'password' : 'text'} {...inp}
                id={`connector-${f.name}`} name={`connector-${f.name}`}
                autoComplete={f.kind === 'password' ? 'new-password' : 'off'} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', paddingBottom: 6 }}>
              <input type="checkbox" checked={locked.has(f.name)} onChange={() => toggleLocked(f.name)} />
              {t('pg.adminPlatform.cc.locked')}
            </label>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? t('pg.adminPlatform.saving') : isEdit ? t('pg.adminPlatform.cc.saveChanges') : t('pg.adminPlatform.cc.create')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('pg.adminPlatform.cancel')}</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminCustomConnectors() {
  const t = useT()
  const [presets, setPresets] = useState<CustomConnector[]>([])
  const [catalog, setCatalog] = useState<ConnectorSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal, setModal] = useState<'add' | CustomConnector | null>(null)

  const load = () => {
    setLoadError(null)
    return Promise.all([customConnectorsApi.list(), dataSourcesApi.connectors()])
      .then(([p, c]) => { setPresets(p); setCatalog(c) })
      .catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const handleSaved = (cc: CustomConnector) => {
    setPresets(prev => {
      const idx = prev.findIndex(x => x.id === cc.id)
      return idx >= 0 ? prev.map(x => x.id === cc.id ? cc : x) : [cc, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (cc: CustomConnector) => {
    if (!await confirm({ title: t('pg.adminPlatform.cc.deleteTitle', { name: cc.label }), body: t('pg.adminPlatform.cc.deleteBody') })) return
    try {
      await customConnectorsApi.delete(cc.id)
      setPresets(prev => prev.filter(x => x.id !== cc.id))
      toast.success(t('pg.adminPlatform.deleted'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminPlatform.cc.deleteFailed'))
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.customConnectors')}</h1>
        <button className="btn btn-primary" onClick={() => setModal('add')}><Plus size={16} aria-hidden /> {t('admin.newConnector')}</button>
      </div>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what={t('pg.adminPlatform.cc.loadWhat')} title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.cc.loadWhat') })}
          retryLabel={t('pg.adminPlatform.retry')} error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}
      {!loading && loadError == null && presets.length === 0 && (
        <EmptyState icon={Plug} title={t('pg.adminPlatform.cc.empty')}
          description={t('pg.adminPlatform.cc.emptyDesc')} />
      )}

      <div className="dl-rows">
        {presets.map(cc => (
          <div key={cc.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title"><bdi>{cc.label}</bdi></div>
              <div className="dl-rows__meta"><bdi dir="ltr">{cc.base_type}</bdi> · {t('pg.adminPlatform.cc.lockedCount', { n: cc.locked_fields.length })}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(cc)}>{t('admin.edit')}</button>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => handleDelete(cc)}>{t('admin.delete')}</button>
          </div>
        ))}
      </div>

      {modal && (
        <PresetModal initial={modal === 'add' ? null : modal} catalog={catalog} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
