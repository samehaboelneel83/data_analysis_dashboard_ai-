import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { datasetsApi, type IncrementalSettings } from '../../services/api'
import { useT } from '../../i18n'

/**
 * Pipeline plan, phase 4, inside the dataset's refresh menu: how AUTOMATIC
 * refreshes load it. Full each time, or incremental -- only rows past a
 * growing column, merged on a key so an updated row replaces the old one,
 * with an optional look-back and a periodic full reload.
 */
export default function IncrementalSettingsForm({ datasetId, columns }: { datasetId: number; columns: string[] }) {
  const t = useT()
  const [s, setS] = useState<IncrementalSettings | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    let live = true
    Promise.resolve().then(() => datasetsApi.incremental(datasetId))
      .then(v => { if (live && v) setS(v) }).catch(() => {})
    return () => { live = false }
  }, [datasetId])
  if (!s) return null

  const incremental = s.strategy === 'incremental'
  const set = (patch: Partial<IncrementalSettings>) => setS({ ...s, ...patch })
  const save = async () => {
    setSaving(true)
    try {
      setS(await datasetsApi.setIncremental(datasetId, {
        strategy: s.strategy, cursor_column: s.cursor_column || null, key_column: s.key_column || null,
        lookback_hours: s.key_column ? (s.lookback_hours || null) : null,
        full_reload_days: s.full_reload_days || null,
        reconcile_deletes: !!(s.key_column && s.reconcile_deletes) }))
      toast.success(t('incr.saved'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e))
    } finally { setSaving(false) }
  }
  const small = { fontSize: 11.5, color: 'var(--muted)', display: 'block', marginBottom: 3 } as const
  const field = { width: '100%', fontSize: 12, marginBottom: 8 } as const

  return (
    <div data-testid="incremental-settings" style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{t('incr.title')}</div>
      <label style={small} htmlFor="incr-strategy">{t('incr.how')}</label>
      <select id="incr-strategy" className="input" style={field} value={s.strategy}
        onChange={e => set({ strategy: e.target.value as 'full' | 'incremental' })}>
        <option value="full">{t('incr.full')}</option>
        <option value="incremental">{t('incr.incremental')}</option>
      </select>
      {incremental && (<>
        <label style={small} htmlFor="incr-cursor">{t('incr.cursor')}</label>
        <select id="incr-cursor" className="input" style={field} value={s.cursor_column ?? ''}
          onChange={e => set({ cursor_column: e.target.value || null })}>
          <option value="">—</option>
          {columns.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <label style={small} htmlFor="incr-key">{t('incr.key')}</label>
        <select id="incr-key" className="input" style={field} value={s.key_column ?? ''}
          onChange={e => set({ key_column: e.target.value || null })}>
          <option value="">{t('incr.noKey')}</option>
          {columns.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        {s.key_column && (<>
          <label style={small} htmlFor="incr-lookback">{t('incr.lookback')}</label>
          <input id="incr-lookback" className="input" type="number" min={1} max={744} style={field}
            value={s.lookback_hours ?? ''} onChange={e => set({ lookback_hours: e.target.value ? Number(e.target.value) : null })} />
          {/* Without this a row deleted at the source stays on every dashboard. */}
          <label style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, marginBottom: 8 }}>
            <input type="checkbox" checked={!!s.reconcile_deletes}
              onChange={e => set({ reconcile_deletes: e.target.checked })} />
            <span>{t('incr.deletes')}<br />
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{t('incr.deletesHint', { key: s.key_column })}</span></span>
          </label>
        </>)}
        <label style={small} htmlFor="incr-full">{t('incr.fullEvery')}</label>
        <select id="incr-full" className="input" style={field} value={s.full_reload_days ?? ''}
          onChange={e => set({ full_reload_days: e.target.value ? Number(e.target.value) : null })}>
          <option value="">{t('incr.never')}</option>
          <option value="1">{t('incr.daily')}</option>
          <option value="7">{t('incr.weekly')}</option>
          <option value="30">{t('incr.monthly')}</option>
        </select>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
          {s.key_column ? t('incr.noteKey', { key: s.key_column }) : t('incr.noteAppend')}
        </div>
      </>)}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-primary btn-sm" disabled={saving || (incremental && !s.cursor_column)}
          onClick={() => void save()}>{t('incr.save')}</button>
      </div>
    </div>
  )
}
