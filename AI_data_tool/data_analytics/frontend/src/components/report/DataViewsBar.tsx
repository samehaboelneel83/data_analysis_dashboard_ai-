import { useEffect, useState } from 'react'
import { dataViewsApi } from '../../services/api'
import { useT } from '../../i18n'

/**
 * Save/apply SETTINGS TEMPLATES (stored as "data views"): a named snapshot of a dataset's semantic
 * layer (roles, formats, calc columns, measures, filter, prep, hierarchy),
 * applicable to any other import dataset in the org. Called templates in the UI
 * since 2026-09-25: a dataset's VIEW is its saved prep pipeline, and two things
 * named "view" in one product read as one.
 *
 * The apply result is reported verbatim — what applied, what was skipped and
 * why — because a silent partial apply would leave the author believing
 * formats exist that don't.
 */
export default function DataViewsBar({ datasetId, onApplied, isAdmin }: {
  datasetId: number
  onApplied?: () => void
  /** Only an admin may choose the view applied to every new dataset. The server
   *  refuses either way; hiding the control keeps everyone else from meeting a
   *  403 they could not have predicted. */
  isAdmin?: boolean
}) {
  const t = useT()
  const [views, setViews] = useState<{ id: number; name: string; pieces: string[]; is_default?: boolean }[]>([])
  const [selected, setSelected] = useState('')
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [status, setStatus] = useState('')

  const refresh = () => dataViewsApi.list().then(setViews).catch(() => setViews([]))
  useEffect(() => { refresh() }, [])

  const save = async () => {
    if (!name.trim()) return
    try {
      await dataViewsApi.save(datasetId, name.trim())
      setStatus(t('pg.panelsB.dvb.saved', { name: name.trim() }))
      setSaving(false); setName('')
      refresh()
    } catch {
      setStatus(t('pg.panelsB.dvb.saveFailed'))
    }
  }

  const apply = async () => {
    const id = Number(selected)
    if (!id) return
    try {
      const r = await dataViewsApi.apply(datasetId, id)
      const parts = Object.entries(r.applied).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(t('pg.panelsB.listSep'))
        || t('pg.panelsB.dvb.nothing')
      setStatus(r.skipped.length
        ? t('pg.panelsB.dvb.appliedSkipped', { parts, n: r.skipped.length, list: r.skipped.join('; ') })
        : t('pg.panelsB.dvb.applied', { parts }))
      onApplied?.()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setStatus(detail || t('pg.panelsB.dvb.applyFailed'))
    }
  }

  const chosen = views.find(v => String(v.id) === selected)

  const toggleDefault = async (on: boolean) => {
    if (!chosen) return
    try {
      await dataViewsApi.setDefault(chosen.id, on)
      setStatus(on
        ? t('pg.panelsB.dvb.defaultOn', { name: chosen.name })
        : t('pg.panelsB.dvb.defaultOff', { name: chosen.name }))
      refresh()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setStatus(detail || t('pg.panelsB.dvb.defaultFailed'))
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        {t('pg.panelsB.dvb.title')}
      </span>
      {saving ? (
        <>
          <input aria-label={t('pg.panelsB.dvb.nameLabel')} value={name} onChange={e => setName(e.target.value)}
            placeholder={t('pg.panelsB.dvb.namePh')} style={{ fontSize: 11, width: 180 }} />
          <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => void save()}>{t('pg.panelsB.dvb.save')}</button>
          <button className="btn" style={{ fontSize: 11 }} onClick={() => { setSaving(false); setName('') }}>{t('common.cancel')}</button>
        </>
      ) : (
        <button className="btn" style={{ fontSize: 11 }} onClick={() => setSaving(true)}>{t('pg.panelsB.dvb.saveAs')}</button>
      )}
      <select aria-label={t('pg.panelsB.dvb.templates')} value={selected} onChange={e => setSelected(e.target.value)} style={{ fontSize: 11 }}>
        <option value="">{t('pg.panelsB.dvb.choose')}</option>
        {views.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
      </select>
      <button className="btn" style={{ fontSize: 11 }} disabled={!selected} title={!selected ? t('pg.panelsB.dvb.chooseFirst') : undefined} onClick={() => void apply()}>{t('pg.panelsB.dvb.apply')}</button>
      {isAdmin && chosen && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)' }}>
          <input type="checkbox" checked={!!chosen.is_default}
            onChange={e => void toggleDefault(e.target.checked)}
            style={{ margin: 0 }} />
          {t('pg.panelsB.dvb.default')}
        </label>
      )}
      {isAdmin && chosen && (
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>
          {t('pg.panelsB.dvb.defaultNote')}
        </span>
      )}
      {status && <span data-testid="dataview-status" style={{ fontSize: 11, color: 'var(--muted)', flexBasis: '100%' }}>{status}</span>}
    </div>
  )
}
