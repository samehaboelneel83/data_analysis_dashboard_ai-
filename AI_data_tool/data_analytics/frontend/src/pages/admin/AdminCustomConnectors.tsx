import { useEffect, useState } from 'react'
import { Plug } from 'lucide-react'
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
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [key, setKey] = useState(initial?.key ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [baseType, setBaseType] = useState(initial?.base_type ?? catalog[0]?.key ?? '')
  const [values, setValues] = useState<Record<string, unknown>>(initial?.base_config ?? {})
  const [locked, setLocked] = useState<Set<string>>(new Set(initial?.locked_fields ?? []))
  const [saving, setSaving] = useState(false)

  const spec = catalog.find(s => s.key === baseType)
  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const toggleLocked = (name: string) => setLocked(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  const handleSave = async () => {
    if (!key.trim() || !label.trim()) { toast.error('Key and label are required'); return }
    setSaving(true)
    try {
      const body = { key, label, base_type: baseType, base_config: values, locked_fields: [...locked] }
      const result = isEdit ? await customConnectorsApi.update(initial!.id, body) : await customConnectorsApi.create(body)
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Custom connector created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={isEdit ? 'Edit custom connector' : 'New custom connector'}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Custom Connector' : 'New Custom Connector'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Label *</div>
          <input value={label} onChange={e => setLabel(e.target.value)} placeholder="Acme Snowflake" {...inp} />
        </label>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Key *</div>
          <input value={key} onChange={e => setKey(e.target.value)} placeholder="acme-snowflake" {...inp} disabled={isEdit} title={isEdit ? 'The id is fixed once a connector exists' : undefined} />
        </label>
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Base connector type</div>
          <select value={baseType} onChange={e => { setBaseType(e.target.value); setValues({}); setLocked(new Set()) }} {...inp} disabled={isEdit} title={isEdit ? 'The base type is fixed once a connector exists' : undefined}>
            {catalog.filter(s => !s.is_custom).map(s => <option key={s.key} value={s.key}>{s.icon} {s.label}</option>)}
          </select>
        </label>

        {spec?.config_fields.map(f => (
          <div key={f.name} style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginBottom: 10 }}>
            <label style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{f.label}</div>
              <input value={(values[f.name] as string) ?? ''} onChange={e => setValues(p => ({ ...p, [f.name]: e.target.value }))}
                type={f.kind === 'password' ? 'password' : 'text'} {...inp} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', paddingBottom: 6 }}>
              <input type="checkbox" checked={locked.has(f.name)} onChange={() => toggleLocked(f.name)} />
              Locked
            </label>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminCustomConnectors() {
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
    if (!await confirm({ title: `Delete "${cc.label}"?`, body: 'Connections using this preset must be updated or removed first.' })) return
    try {
      await customConnectorsApi.delete(cc.id)
      setPresets(prev => prev.filter(x => x.id !== cc.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Custom Connectors</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')}>+ New Custom Connector</button>
      </div>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what="custom connectors" error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}
      {!loading && loadError == null && presets.length === 0 && (
        <EmptyState icon={Plug} title="No custom connectors yet"
          description="Create a sanctioned, pre-configured preset of a connector type for the rest of your org to use." />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {presets.map(cc => (
          <div key={cc.id} style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{cc.label}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>{cc.base_type} · {cc.locked_fields.length} locked field(s)</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(cc)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(cc)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <PresetModal initial={modal === 'add' ? null : modal} catalog={catalog} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
