import { useMemo, useRef, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { dataSourcesApi } from '../../services/api'
import type { DataSource, ConnectorSpec } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import IconLabel from '../../components/ui/IconLabel'
import { Check, TriangleAlert, X as XIcon } from 'lucide-react'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { blankConfigFor } from './typeMaps'
import { friendlyMessage } from '../../lib/friendlyError'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { connectorFieldLabel } from '../../i18n/pages/adminPlatform'

/* ── Connection Form Modal ─────────────────────────────── */
export function ConnectionModal({ initial, catalog, onSave, onClose }: {
  initial?: DataSource | null
  catalog: ConnectorSpec[]
  onSave: (ds: DataSource) => void
  onClose: () => void
}) {
  const tr = useT()
  const { language } = useDirection()
  // QA5 L6: the server's field labels, translated by field key.
  const fieldLabel = (f: ConnectorSpec['config_fields'][number]) => connectorFieldLabel(tr, language, f.name, f.label)
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const specOf = (t: string) => catalog.find(s => s.key === t)
  const [name,    setName]    = useState(initial?.name ?? '')
  const [label,   setLabel]   = useState<string>(initial?.sensitivity ?? '')
  // Guided setup D1: on by default; changed later on the review page.
  const [allowAi, setAllowAi] = useState(true)
  const initialType = initial?.custom_connector_id != null
    ? (catalog.find(s => s.custom_connector_id === initial.custom_connector_id)?.key ?? initial?.type ?? catalog[0]?.key ?? 'postgresql')
    : (initial?.type ?? catalog[0]?.key ?? 'postgresql')
  const [type,    setType]    = useState(initialType)
  const [cfg,     setCfg]     = useState<Record<string, unknown>>(
    initial?.config ?? blankConfigFor(specOf(initial?.type ?? catalog[0]?.key ?? ''))
  )
  const [testing, setTesting] = useState(false)
  const [testOk,  setTestOk]  = useState<boolean | null>(null)
  const [testMsg, setTestMsg] = useState<string | null>(null)
  // The driver's own words, one click away: whoever is filling in this form
  // is the admin the friendly sentence would otherwise tell them to ask.
  const [testRaw, setTestRaw] = useState<string | null>(null)
  const [saving,  setSaving]  = useState(false)
  // Synchronous guard: two quick clicks on Create both passed the `saving`
  // check (state lags a render) and made two connections.
  const inFlight = useRef(false)
  // Which fields have been touched or submitted, for inline messages.
  const [showErrors, setShowErrors] = useState(false)
  // Edit form: the stored password stays on the server; the field starts
  // EMPTY so typing a new one does not append to a placeholder token.
  const [pwTouched, setPwTouched] = useState(false)

  const spec = specOf(type)
  // Any edit makes the last test result stale -- a green tick next to a
  // password you have since changed would be a lie.
  const setField = (k: string, v: unknown) => { setCfg(p => ({ ...p, [k]: v })); setTestOk(null); setTestMsg(null) }

  const changeType = (t: string) => {
    setType(t)
    setCfg(blankConfigFor(specOf(t)))
    setTestOk(null)
    setTestMsg(null)
  }

  // Connectors grouped by category for an <optgroup> dropdown.
  const grouped = useMemo(() => {
    const g: Record<string, ConnectorSpec[]> = {}
    for (const s of catalog) (g[s.category] ??= []).push(s)
    return g
  }, [catalog])

  // Tests what is IN THE FORM, before anything is saved: the only way to catch
  // a mistyped password used to be creating a broken connection first. The
  // result stays in the dialog, beside the fields it is about.
  /** Required fields (per the connector's own spec) that are still empty. */
  const NAME_FIELD = tr('pg.dataPages.conn.nameField')
  const missing = (): string[] => {
    const out: string[] = []
    if (!name.trim()) out.push(NAME_FIELD)
    for (const f of spec?.config_fields ?? []) {
      if (f.show_if && cfg[f.show_if[0]] !== f.show_if[1]) continue
      if (!f.required) continue
      const v = cfg[f.name]
      if (f.kind === 'password' && isEdit && !pwTouched) continue
      if (v === undefined || v === null || String(v).trim() === '') out.push(fieldLabel(f))
    }
    return out
  }
  const fieldMissing = (f: ConnectorSpec['config_fields'][number]) =>
    showErrors && f.required && (cfg[f.name] === undefined || String(cfg[f.name] ?? '').trim() === '')

  const handleTest = async () => {
    const miss = missing().filter(m => m !== NAME_FIELD)
    if (miss.length) { setShowErrors(true); setTestOk(false); setTestMsg(tr('pg.dataPages.conn.fillInFirstDot', { fields: miss.join(tr('pg.dataPages.listSep')) })); setTestRaw(null); return }
    setTesting(true)
    setTestOk(null)
    setTestMsg(null)
    setTestRaw(null)
    const submitType = spec?.is_custom ? spec.base_type! : type
    try {
      let r: { ok: boolean; error?: string }
      try {
        r = await dataSourcesApi.testSettings({
          type: submitType, config: cfg,
          custom_connector_id: spec?.is_custom ? spec.custom_connector_id : undefined,
          source_id: initial?.id,
        })
      } catch (e: any) {
        // A server without the settings probe: fall back to testing the saved
        // connection when there is one.
        const st = e?.response?.status
        if ((st === 404 || st === 405) && initial?.id) r = await dataSourcesApi.test(initial.id)
        else throw e
      }
      setTestOk(r.ok)
      setTestMsg(r.ok ? tr('pg.dataPages.conn.settingsWork') : friendlyMessage(r.error ?? tr('pg.dataPages.conn.connectionFailed')))
      setTestRaw(!r.ok && r.error && friendlyMessage(r.error) !== r.error ? r.error : null)
    } catch (e: any) {
      setTestOk(false)
      const d = e?.response?.data?.detail
      setTestMsg(typeof d === 'string' ? friendlyMessage(d) : tr('pg.dataPages.conn.testCouldNotRun'))
    } finally { setTesting(false) }
  }

  const handleSave = async () => {
    if (inFlight.current) return
    const miss = missing()
    if (miss.length) { setShowErrors(true); toast.error(tr('pg.dataPages.conn.fillInFirst', { fields: miss.join(tr('pg.dataPages.listSep')) })); return }
    inFlight.current = true
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
        ? await dataSourcesApi.update(initial!.id, { name, type: submitType, custom_connector_id: customConnectorId, config: submitCfg, sensitivity: label })
        : await dataSourcesApi.create({ name, type: submitType, custom_connector_id: customConnectorId, config: submitCfg, sensitivity: label || null, allow_llm_sampling: allowAi })
      onSave(result)
      toast.success(isEdit ? tr('pg.dataPages.conn.updated') : tr('pg.dataPages.conn.created'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? tr('pg.dataPages.conn.saveFailed'))
    } finally { setSaving(false); inFlight.current = false }
  }

  const inp = { style: fieldStyle }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? tr('pg.dataPages.conn.editTitle') : tr('pg.dataPages.conn.newTitle')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 480, maxWidth: '90vw', maxHeight: '90vh', overflowY: 'auto' }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? tr('pg.dataPages.conn.editTitle') : tr('pg.dataPages.conn.newTitle')}</h2>
          <button type="button" onClick={onClose} aria-label={tr('pg.dataPages.close')} title={tr('pg.dataPages.close')} className="dl-wicon"><XIcon size={16} aria-hidden /></button>
        </div>

        {/* Name */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{tr('pg.dataPages.conn.nameLabel')}</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder={tr('pg.dataPages.conn.namePlaceholder')} maxLength={120}
            id="conn-display-name" name="conn-display-name" autoComplete="off"
            aria-invalid={showErrors && !name.trim() ? true : undefined} {...inp} />
          {showErrors && !name.trim() && <div className="dl-field__error">{tr('pg.dataPages.conn.nameRequired')}</div>}
        </label>

        {/* Sensitivity: a floor for every dataset read from this connection,
            so an import of the salaries cannot come out Unlabelled. */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
            {tr('pg.dataPages.conn.sensLabel')} <span style={{ opacity: .8 }}>{tr('pg.dataPages.conn.sensHint')}</span>
          </div>
          <select aria-label={tr('pg.dataPages.conn.sensAria')} value={label} onChange={e => setLabel(e.target.value)} {...inp}>
            <option value="">{tr('pg.dataPages.conn.unlabelled')}</option>
            <option value="Public">{tr('sens.Public')}</option>
            <option value="Internal">{tr('sens.Internal')}</option>
            <option value="Confidential">{tr('sens.Confidential')}</option>
            <option value="Restricted">{tr('sens.Restricted')}</option>
          </select>
        </label>

        {/* Guided setup D1: the AI reads with this person's own access, and
            only describes the source when allowed to look at a few rows. */}
        {!initial && (
          <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 12, cursor: 'pointer' }}>
            <input type="checkbox" checked={allowAi} onChange={e => setAllowAi(e.target.checked)}
              style={{ marginTop: 3 }} />
            <span>
              <span style={{ display: 'block', fontSize: 13 }}>{tr('conn.allowAi')}</span>
              <span style={{ display: 'block', fontSize: 11, color: 'var(--muted)' }}>{tr('conn.allowAiHint')}</span>
            </span>
          </label>
        )}

        {/* Type — grouped by category, from the catalog */}
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{tr('pg.dataPages.conn.type')}</div>
          <select value={type} onChange={e => changeType(e.target.value)} {...inp}>
            {Object.entries(grouped).map(([cat, specs]) => (
              <optgroup key={cat} label={cat}>
                {specs.map(s => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        {spec && !spec.driver_installed && (
          <div role="note" style={{ fontSize: 12, color: 'var(--warning)', marginBottom: 10 }}>
            <TriangleAlert size={12} aria-hidden style={{ verticalAlign: -2 }} /> {tr('pg.dataPages.conn.driverMissing', { name: spec.label })}
          </div>
        )}

        {/* Config fields — rendered from the connector's field spec */}
        {(spec?.config_fields ?? [])
          .filter(f => !f.show_if || cfg[f.show_if[0]] === f.show_if[1])
          .map(f => (
            <label key={f.name} style={{ display: 'block', marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>
                {fieldLabel(f)}{f.required ? ' *' : ''}
              </div>
              {f.kind === 'select' ? (
                <select value={(cfg[f.name] as string) ?? (f.default as string) ?? ''}
                  onChange={e => setField(f.name, e.target.value)} {...inp}>
                  {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={f.kind === 'password' ? 'password' : f.kind === 'number' ? 'number' : 'text'}
                  value={f.kind === 'password' && isEdit && !pwTouched && cfg[f.name] === '__SECRET_UNCHANGED__' ? '' : (cfg[f.name] as string | number) ?? ''}
                  onChange={e => { if (f.kind === 'password') setPwTouched(true); setField(f.name, f.kind === 'number' ? +e.target.value : e.target.value) }}
                  placeholder={f.kind === 'password' && isEdit && !pwTouched ? tr('pg.dataPages.conn.keepPassword') : f.placeholder}
                  aria-invalid={fieldMissing(f) ? true : undefined}
                  autoComplete={f.kind === 'password' ? 'new-password' : 'off'}
                  id={`conn-${f.name}`} name={`conn-${f.name}`}
                  {...inp} />
              )}
              {fieldMissing(f) && <div className="dl-field__error">{tr('pg.dataPages.conn.fieldRequired', { name: fieldLabel(f) })}</div>}
            </label>
          ))}

        {testMsg && (
          <div role="status" className={`dl-conn-test dl-conn-test--${testOk ? 'ok' : 'fail'}`}>
            {testOk ? <Check size={14} aria-hidden /> : <XIcon size={14} aria-hidden />}
            <span style={{ minWidth: 0 }}>
              {testMsg}
              {testRaw && (
                <details className="dl-conn-test__raw">
                  <summary>{tr('pg.dataPages.conn.technicalDetails')}</summary>
                  <pre>{testRaw}</pre>
                </details>
              )}
            </span>
          </div>
        )}

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? tr('pg.dataPages.saving') : isEdit ? tr('pg.dataPages.saveChanges') : tr('pg.dataPages.conn.create')}
          </button>
          <button type="button" className="btn" onClick={handleTest} disabled={testing}>
            {testing ? tr('connections.testing')
            : testOk === true ? <IconLabel icon={Check}>{tr('pg.dataPages.conn.testConnection')}</IconLabel>
            : testOk === false ? <IconLabel icon={XIcon}>{tr('pg.dataPages.conn.testConnection')}</IconLabel>
            : tr('pg.dataPages.conn.testConnection')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{tr('common.cancel')}</button>
        </div>
      </div>
    </div>
  )
}

