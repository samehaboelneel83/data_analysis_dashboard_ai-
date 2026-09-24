import { useMemo, useState } from 'react'
import { dataSourcesApi } from '../../services/api'
import type { DataSource, ConnectorSpec } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import IconLabel from '../../components/ui/IconLabel'
import { Check, TriangleAlert, X as XIcon } from 'lucide-react'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { blankConfigFor } from './typeMaps'

/* ── Connection Form Modal ─────────────────────────────── */
export function ConnectionModal({ initial, catalog, onSave, onClose }: {
  initial?: DataSource | null
  catalog: ConnectorSpec[]
  onSave: (ds: DataSource) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const specOf = (t: string) => catalog.find(s => s.key === t)
  const [name,    setName]    = useState(initial?.name ?? '')
  const initialType = initial?.custom_connector_id != null
    ? (catalog.find(s => s.custom_connector_id === initial.custom_connector_id)?.key ?? initial?.type ?? catalog[0]?.key ?? 'postgresql')
    : (initial?.type ?? catalog[0]?.key ?? 'postgresql')
  const [type,    setType]    = useState(initialType)
  const [cfg,     setCfg]     = useState<Record<string, unknown>>(
    initial?.config ?? blankConfigFor(specOf(initial?.type ?? catalog[0]?.key ?? ''))
  )
  const [testing, setTesting] = useState(false)
  const [testOk,  setTestOk]  = useState<boolean | null>(null)
  const [saving,  setSaving]  = useState(false)

  const spec = specOf(type)
  const setField = (k: string, v: unknown) => setCfg(p => ({ ...p, [k]: v }))

  const changeType = (t: string) => {
    setType(t)
    setCfg(blankConfigFor(specOf(t)))
    setTestOk(null)
  }

  // Connectors grouped by category for an <optgroup> dropdown.
  const grouped = useMemo(() => {
    const g: Record<string, ConnectorSpec[]> = {}
    for (const s of catalog) (g[s.category] ??= []).push(s)
    return g
  }, [catalog])

  const handleTest = async () => {
    if (!initial?.id) { toast.error('Save first, then test'); return }
    setTesting(true)
    setTestOk(null)
    try {
      const r = await dataSourcesApi.test(initial.id)
      setTestOk(r.ok)
      if (r.ok) toast.success('Connection successful')
      else toast.error(r.error ?? 'Connection failed')
    } catch { toast.error('Test failed') }
    finally { setTesting(false) }
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const submitType = spec?.is_custom ? spec.base_type! : type
      const customConnectorId = spec?.is_custom ? spec.custom_connector_id : undefined
      // For a custom preset, an untouched field is sent as '' by blankConfigFor — but the
      // backend only fills in the preset's non-locked default when the key is OMITTED
      // entirely. Strip empty-string values here so those defaults can actually apply.
      // Scoped to is_custom only: ordinary connectors must keep sending '' as-is.
      const submitCfg = spec?.is_custom
        ? Object.fromEntries(Object.entries(cfg).filter(([, v]) => v !== ''))
        : cfg
      const result = isEdit
        ? await dataSourcesApi.update(initial!.id, { name, type: submitType, custom_connector_id: customConnectorId, config: submitCfg })
        : await dataSourcesApi.create({ name, type: submitType, custom_connector_id: customConnectorId, config: submitCfg })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Connection created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? "Edit connection" : "New connection"}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 480, maxWidth: '90vw', maxHeight: '90vh', overflowY: 'auto' }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Connection' : 'New Connection'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Name */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Connection Name *</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="My Database" {...inp} />
        </label>

        {/* Type — grouped by category, from the catalog */}
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Type</div>
          <select value={type} onChange={e => changeType(e.target.value)} {...inp}>
            {Object.entries(grouped).map(([cat, specs]) => (
              <optgroup key={cat} label={cat}>
                {specs.map(s => (
                  <option key={s.key} value={s.key}>{s.icon} {s.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        {spec && !spec.driver_installed && (
          <div style={{ fontSize: 11, color: '#e6a03c', marginBottom: 10 }}>
            <TriangleAlert size={12} aria-hidden style={{ verticalAlign: -2 }} /> The driver for {spec.label} is not installed on the server. Install it, then
            connect with a full SQLAlchemy URL.
          </div>
        )}

        {/* Config fields — rendered from the connector's field spec */}
        {(spec?.config_fields ?? [])
          .filter(f => !f.show_if || cfg[f.show_if[0]] === f.show_if[1])
          .map(f => (
            <label key={f.name} style={{ display: 'block', marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>
                {f.label}{f.required ? ' *' : ''}
              </div>
              {f.kind === 'select' ? (
                <select value={(cfg[f.name] as string) ?? (f.default as string) ?? ''}
                  onChange={e => setField(f.name, e.target.value)} {...inp}>
                  {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={f.kind === 'password' ? 'password' : f.kind === 'number' ? 'number' : 'text'}
                  value={(cfg[f.name] as string | number) ?? ''}
                  onChange={e => setField(f.name, f.kind === 'number' ? +e.target.value : e.target.value)}
                  placeholder={f.placeholder}
                  autoComplete={f.kind === 'password' ? 'new-password' : 'off'}
                  name={`conn-${f.name}`}
                  {...inp} />
              )}
            </label>
          ))}

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          {isEdit && (
            <button className="btn btn-ghost" onClick={handleTest} disabled={testing}
              style={{ fontSize: 12, padding: '6px 14px' }}>
              {testing ? 'Testing…'
              : testOk === true ? <IconLabel icon={Check}>Test</IconLabel>
              : testOk === false ? <IconLabel icon={XIcon}>Test</IconLabel>
              : 'Test'}
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

