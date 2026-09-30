import { useEffect, useState, type CSSProperties } from 'react'
import toast from 'react-hot-toast'
import { ArrowDown, ArrowUp, Plus, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { useT } from '../../i18n'
import { llmApi, platformSettingsApi, type LlmEndpoint, type LlmEndpointsOut } from '../../services/api'
import { endpointLight, Led } from '../LlmPicker'

/**
 * Platform settings -> LLM endpoints: every OpenAI-compatible server the app
 * may use, which one is the default (or Auto), and a live light for each.
 *
 * A stored API key never comes back from the server: its field is empty with
 * a "saved" placeholder, and sending nothing for it keeps the stored key.
 */

interface Row {
  id?: string
  key: string                  // React key; the server id once saved
  name: string
  base_url: string
  model: string
  api_key: string              // what the admin typed ('' = unchanged)
  clear_key: boolean
  has_api_key: boolean
  enabled: boolean
  strength: string             // '' = guess from the model name
  context: string              // '' = read from the endpoint
  guessedStrength: number
  detectedContext: number | null
  status: LlmEndpoint['status']
}

function toRows(out: LlmEndpointsOut): Row[] {
  return out.endpoints.map(e => ({
    id: e.id, key: e.id, name: e.name, base_url: e.base_url ?? '', model: e.model, api_key: '',
    clear_key: false, has_api_key: !!e.has_api_key, enabled: e.enabled, status: e.status,
    strength: e.strength_set ? String(e.strength_set) : '', context: e.context_set ? String(e.context_set) : '',
    guessedStrength: e.strength, detectedContext: e.max_model_len ?? null,
  }))
}

function detail(e: unknown): string | undefined {
  return (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
}

let seq = 0

export default function LlmEndpointsPanel() {
  const t = useT()
  const [data, setData] = useState<LlmEndpointsOut | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [def, setDef] = useState('auto')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)

  const apply = (out: LlmEndpointsOut) => {
    setData(out); setRows(toRows(out)); setDef(out.default); setDirty(false)
  }
  const load = () => { platformSettingsApi.getLlmEndpoints().then(apply).catch(() => undefined) }
  useEffect(load, [])
  /** Probe every saved endpoint now, then show the fresh lights. */
  const recheck = async () => {
    setBusy(true)
    try { await llmApi.endpoints(true); apply(await platformSettingsApi.getLlmEndpoints()) }
    catch { /* keep the current lights */ }
    finally { setBusy(false) }
  }

  if (!data) return null

  const edit = (i: number, patch: Partial<Row>) => {
    setRows(rs => rs.map((r, j) => (j === i ? { ...r, ...patch } : r))); setDirty(true)
  }
  const move = (i: number, by: number) => {
    setRows(rs => {
      const next = [...rs]; const [r] = next.splice(i, 1); next.splice(i + by, 0, r); return next
    }); setDirty(true)
  }
  const remove = (i: number) => {
    const gone = rows[i]
    setRows(rs => rs.filter((_, j) => j !== i))
    if (gone.id && gone.id === def) setDef('auto')
    setDirty(true)
  }
  const add = () => {
    seq += 1
    setRows(rs => [...rs, { key: `new-${seq}`, name: t('llm.ep.new'), base_url: 'http://', model: '', api_key: '',
      clear_key: false, has_api_key: false, enabled: true, status: null,
      strength: '', context: '', guessedStrength: 5, detectedContext: null }])
    setDirty(true)
  }

  const save = async () => {
    setBusy(true)
    try {
      const out = await platformSettingsApi.saveLlmEndpoints(rows.map(r => ({
        id: r.id, name: r.name, base_url: r.base_url, model: r.model, enabled: r.enabled,
        api_key: r.clear_key ? '' : (r.api_key ? r.api_key : null),
        strength: r.strength.trim() ? Number(r.strength) : 0,
        context: r.context.trim() ? Number(r.context) : 0,
      })), def)
      apply(out); toast.success(t('llm.ep.saved'))
    } catch (e) { toast.error(detail(e) ?? t('settings.saveFailed')) }
    finally { setBusy(false) }
  }

  const reset = async () => {
    setBusy(true)
    try { apply(await platformSettingsApi.resetLlmEndpoints()); toast.success(t('llm.ep.resetDone')) }
    catch (e) { toast.error(detail(e) ?? t('settings.saveFailed')) }
    finally { setBusy(false) }
  }

  const test = async (r: Row) => {
    setTesting(r.key)
    try {
      const res = await platformSettingsApi.testLlm({
        endpoint_id: r.id, llm_base_url: r.base_url || undefined, llm_model: r.model || undefined,
        llm_api_key: r.clear_key ? '' : (r.api_key || undefined),
      })
      if (res.ok) toast.success(t('settings.testOk', { model: res.model, ms: res.latency_ms }))
      else toast.error(t('settings.testFail', { detail: res.detail }))
      // The light only: a test is not an edit, so the form stays clean.
      const status = { ok: res.ok, latency_ms: res.latency_ms, checked_at: new Date().toISOString(),
        error: res.ok ? null : res.detail }
      setRows(rs => rs.map(x => (x.key === r.key ? { ...x, status } : x)))
    } catch (e) { toast.error(t('settings.testFail', { detail: detail(e) ?? '' })) }
    finally { setTesting(null) }
  }

  const cell: CSSProperties = { padding: '6px 6px', verticalAlign: 'middle' }

  return (
    <div className="dl-setting" data-testid="llm-endpoints" style={{ display: 'block' }}>
      <div className="dl-setting__head">
        <span className="dl-setting__label" id="llm-ep-title">{t('llm.ep.title')}</span>
        {data.source === 'saved' && <span className="dl-setting__badge dl-setting__badge--saved">{t('settings.source.saved')}</span>}
      </div>
      <p className="dl-setting__hint" style={{ marginTop: 2 }}>{t('llm.ep.hint')}</p>
      {data.source !== 'saved' && !dirty && (
        <p className="dl-setting__hint" role="note">
          {data.source === 'deployment' ? t('llm.ep.deployNote') : t('llm.ep.envNote')}
        </p>
      )}
      <p className="dl-setting__hint">{t('llm.ep.strengthHint')}</p>

      <div style={{ overflowX: 'auto' }}>
        <table aria-labelledby="llm-ep-title" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)', fontSize: 11 }}>
              <th style={cell} aria-label="status" />
              <th style={{ ...cell, textAlign: 'start' }}>{t('llm.ep.name')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('llm.ep.url')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('llm.ep.model')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('llm.ep.key')}</th>
              <th style={{ ...cell, textAlign: 'start' }} title={t('llm.ep.strengthHint')}>{t('llm.ep.strength')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('llm.ep.context')}</th>
              <th style={cell}>{t('llm.ep.enabled')}</th>
              <th style={cell} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const l = endpointLight(r, data.llm_enabled)
              return (
                <tr key={r.key} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={cell} title={r.status?.error ?? (l === 'up' ? t('llm.up') : l === 'down' ? t('llm.down') : t('llm.unknown'))}>
                    <Led light={l} />
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" value={r.name} aria-label={t('llm.ep.name')}
                      onChange={e => edit(i, { name: e.target.value })} style={{ minWidth: 110 }} />
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" value={r.base_url} aria-label={`${t('llm.ep.url')}: ${r.name}`}
                      onChange={e => edit(i, { base_url: e.target.value })} style={{ minWidth: 200 }}
                      placeholder="http://host:8000/v1" dir="ltr" />
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" value={r.model} aria-label={`${t('llm.ep.model')}: ${r.name}`}
                      onChange={e => edit(i, { model: e.target.value })} style={{ minWidth: 110 }} dir="ltr" />
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" type="password" autoComplete="new-password" value={r.api_key}
                      aria-label={`${t('llm.ep.key')}: ${r.name}`} disabled={r.clear_key}
                      placeholder={r.has_api_key && !r.clear_key ? t('llm.ep.keyKeep') : t('llm.ep.keyNone')}
                      onChange={e => edit(i, { api_key: e.target.value })} style={{ minWidth: 110 }} />
                    {r.has_api_key && (
                      <label style={{ display: 'flex', gap: 4, fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                        <input type="checkbox" checked={r.clear_key} onChange={e => edit(i, { clear_key: e.target.checked, api_key: '' })} />
                        {t('llm.ep.keyClear')}
                      </label>
                    )}
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" type="number" min={1} max={10} value={r.strength}
                      aria-label={`${t('llm.ep.strength')}: ${r.name}`} placeholder={String(r.guessedStrength)}
                      title={t('llm.ep.strengthHint')}
                      onChange={e => edit(i, { strength: e.target.value })} style={{ width: 64 }} />
                  </td>
                  <td style={cell}>
                    <input className="dl-field__input" type="number" min={0} step={1024} value={r.context}
                      aria-label={`${t('llm.ep.context')}: ${r.name}`}
                      placeholder={r.detectedContext ? t('llm.ep.contextAuto', { n: r.detectedContext }) : ''}
                      onChange={e => edit(i, { context: e.target.value })} style={{ width: 110 }} />
                  </td>
                  <td style={{ ...cell, textAlign: 'center' }}>
                    <input type="checkbox" checked={r.enabled} aria-label={`${t('llm.ep.enabled')}: ${r.name}`}
                      onChange={e => edit(i, { enabled: e.target.checked })} />
                  </td>
                  <td style={{ ...cell, whiteSpace: 'nowrap' }}>
                    <button type="button" className="btn btn-sm" disabled={testing !== null} onClick={() => void test(r)}>
                      {testing === r.key ? t('settings.testing') : t('llm.ep.test')}
                    </button>{' '}
                    <button type="button" className="btn btn-sm" disabled={i === 0} onClick={() => move(i, -1)}
                      aria-label={t('llm.ep.up', { name: r.name })} title={t('llm.ep.up', { name: r.name })}><ArrowUp size={12} /></button>{' '}
                    <button type="button" className="btn btn-sm" disabled={i === rows.length - 1} onClick={() => move(i, 1)}
                      aria-label={t('llm.ep.down', { name: r.name })} title={t('llm.ep.down', { name: r.name })}><ArrowDown size={12} /></button>{' '}
                    <button type="button" className="btn btn-sm" disabled={rows.length === 1} onClick={() => remove(i)}
                      aria-label={t('llm.ep.remove', { name: r.name })} title={t('llm.ep.remove', { name: r.name })}
                      style={{ color: 'var(--danger)' }}><Trash2 size={12} /></button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginTop: 10 }}>
        <button type="button" className="btn btn-sm" onClick={add}><Plus size={12} aria-hidden /> {t('llm.ep.add')}</button>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5 }}>
          {t('llm.ep.default')}
          <select className="dl-field__input" value={def} style={{ width: 'auto' }}
            onChange={e => { setDef(e.target.value); setDirty(true) }}>
            <option value="auto">{t('llm.auto')} — {t('llm.autoHint')}</option>
            {rows.filter(r => r.id && r.enabled).map(r => <option key={r.key} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn btn-sm" disabled={busy || dirty} onClick={() => void recheck()} title={t('llm.refresh')}>
          <RefreshCw size={12} aria-hidden /> {t('llm.refresh')}
        </button>
        {data.source === 'saved' && (
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void reset()}>
            <RotateCcw size={12} aria-hidden /> {t('llm.ep.reset')}
          </button>
        )}
        <button type="button" className="btn btn-primary btn-sm" disabled={busy || (!dirty && data.source === 'saved')}
          onClick={() => void save()} aria-describedby={dirty ? 'llm-ep-dirty' : undefined}>
          {busy ? t('settings.saving') : t('llm.ep.save')}
        </button>
      </div>
      {dirty && <p id="llm-ep-dirty" role="status" className="dl-setting__hint" style={{ color: 'var(--warning, inherit)' }}>{t('llm.ep.unsaved')}</p>}
    </div>
  )
}
