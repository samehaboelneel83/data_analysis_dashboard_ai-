/**
 * The geography validation panel (MASTER_PLAN Phase 4 item 1).
 *
 * Before a column is classified as geography -- and so before any map is
 * built on it -- the author sees how many of its rows will land on a shape,
 * WHICH values will not (with how many rows each), and a preview of the
 * regions that did match. Committing below 100% is allowed; not knowing is
 * not. The hospital dashboard that drew a blank map of 27 governorates is the
 * case this exists for: its author would have been told which three names
 * did not match, before saving.
 */
import { useEffect, useMemo, useState } from 'react'
import { widgetDataApi } from '../../services/api'
import { useModalDialog } from '../ui/useModalDialog'
import { invalidateRegionSet, useRegionSet } from './geo/regionSetCache'
import { fittedProjection, regionBoundsPoints, regionLabel, type RegionFeature, type RegionSet } from './geo/worldGeometry'
import { boundarySetsApi } from '../../services/api'
import { geoMatchReport, geoMatchSentence, type GeoMatchReport } from '../../lib/geoMatch'
import { useT } from '../../i18n'
import { rich } from '../../i18n/pages/modelsMaps'

/** Distinct values of a column with their row counts, as the widget pipeline
 *  (row security included) sees them. The cap is disclosed, never silent. */
export const GEO_CHECK_LIMIT = 5000

export function useGeoMatch(datasetId: number | null | undefined, column: string | null | undefined,
                            setId: number | null | undefined, version = 0) {
  const t = useT()
  const { set, loading: setLoading, error: regionError } = useRegionSet(setId ?? null, version)
  const [values, setValues] = useState<{ name: unknown; count: number }[] | null>(null)
  const [truncated, setTruncated] = useState<{ shown: number; of: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!datasetId || !column) { setValues(null); return }
    let live = true
    setValues(null); setError(null); setTruncated(null)
    widgetDataApi.query(datasetId, { dimension: column, aggregation: 'count', limit: GEO_CHECK_LIMIT, sort: 'desc' }, [], 'bar')
      .then((d: any) => {
        if (!live) return
        setValues(((d?.rows ?? []) as { name: unknown; value: number }[]).map(r => ({ name: r.name, count: Number(r.value) || 0 })))
        const t = d?.truncation
        if (t?.applied) setTruncated({ shown: t.shown, of: t.of })
      })
      .catch(() => { if (live) setError(t('pg.modelsMaps.gm.readFailed', { column })) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- a language switch does not refetch
  }, [datasetId, column])
  const report: GeoMatchReport | null = useMemo(
    // Never scored against the fallback world map when the chosen set failed
    // to load: that would report a match rate for shapes nobody asked for.
    () => (values && !setLoading && !regionError ? geoMatchReport(values, set) : null), [values, set, setLoading, regionError])
  return { report, set, loading: values == null || setLoading, error: error ?? regionError, truncated }
}

function PreviewMap({ features, matched }: { features: RegionFeature[]; matched: Set<RegionFeature> }) {
  const t = useT()
  const W = 360, H = 200
  // Framed on what matched; with nothing matched, on the whole set, so the
  // author still sees WHICH shapes their values failed to name.
  const { path } = useMemo(() => fittedProjection(W, H,
    (matched.size ? [...matched] : features).flatMap(f => regionBoundsPoints(f)), 6), [matched, features])
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" data-testid="geo-check-preview"
      aria-label={t('pg.modelsMaps.gm.previewAria', { n: matched.size })}
      style={{ background: 'var(--surface2)', borderRadius: 6, display: 'block' }}>
      {features.map((f, i) => {
        const d = path(f as never)
        if (!d) return null
        const on = matched.has(f)
        return <path key={i} d={d} fill={on ? 'var(--accent)' : 'transparent'} fillOpacity={on ? 0.75 : 0}
          stroke="var(--border)" strokeWidth={0.5} />
      })}
    </svg>
  )
}

/** "Pin to…": send one unmatched spelling to a region of the set, by hand. */
function PinSelect({ set, value, label, onChange }: {
  set: RegionSet; value: number | undefined; label: string; onChange: (i: number | undefined) => void
}) {
  const t = useT()
  const options = useMemo(() => set.features
    .map((f, i) => ({ i, name: regionLabel(f, set) || t('pg.modelsMaps.gm.regionN', { n: i + 1 }) }))
    .sort((a, b) => a.name.localeCompare(b.name)), [set, t])
  return (
    <select aria-label={t('pg.modelsMaps.gm.pinAria', { label })} value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
      style={{ marginInlineStart: 6, fontSize: 11, maxWidth: 170 }}>
      <option value="">{t('pg.modelsMaps.gm.pinTo')}</option>
      {options.map(o => <option key={o.i} value={o.i}>{o.name}</option>)}
    </select>
  )
}

export default function GeoMatchCheck({ datasetId, column, setId, setName, onCommit, onClose }: {
  datasetId: number
  column: string
  setId: number | null
  setName: string
  onCommit: () => void
  onClose: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [version, setVersion] = useState(0)
  const { report, set, loading, error, truncated } = useGeoMatch(datasetId, column, setId, version)
  // Pins chosen in this dialog, not yet saved: value -> feature index.
  const [draft, setDraft] = useState<Record<string, number>>({})
  const [pinError, setPinError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const savePins = async () => {
    if (setId == null) return
    setSaving(true); setPinError(null)
    try {
      await boundarySetsApi.setPins(setId, { ...(set.pins ?? {}), ...draft })
      invalidateRegionSet(setId)
      setDraft({})
      setVersion(v => v + 1)
    } catch (e) {
      setPinError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? t('pg.modelsMaps.gm.saveFailed'))
    } finally { setSaving(false) }
  }
  const good = report != null && report.unmatched.length === 0
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t('pg.modelsMaps.gm.dialogAria', { column, set: setName })}
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(440px, calc(100vw - 32px))', maxHeight: 'calc(100vh - 64px)', overflow: 'auto',
          display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ fontWeight: 700 }}>{rich(t, 'pg.modelsMaps.gm.title', { column: <bdi>{column}</bdi>, set: <bdi>{setName}</bdi> })}</div>
        {error && <div role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>}
        {loading && !error && <div style={{ color: 'var(--muted)', fontSize: 12 }}>{t('pg.modelsMaps.gm.checking')}</div>}
        {report && (
          <>
            <div data-testid="geo-check-rate" style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 26, fontWeight: 700, color: good ? 'var(--success, #2e7d32)' : report.pctRows >= 80 ? 'var(--text)' : 'var(--danger)' }}>
                {report.pctRows}%
              </span>
              <span style={{ color: 'var(--muted)', fontSize: 12 }}>
                {t('pg.modelsMaps.gm.rate', { matched: report.matchedValues, total: report.totalValues })}
              </span>
            </div>
            <PreviewMap features={set.features} matched={report.matchedFeatures} />
            {report.unmatched.length > 0 ? (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
                  {t('pg.modelsMaps.gm.notOnMap', { n: report.unmatched.length })}
                </div>
                <ul data-testid="geo-check-unmatched" style={{ margin: 0, paddingInlineStart: 18, maxHeight: 140, overflow: 'auto', fontSize: 12 }}>
                  {report.unmatched.slice(0, 50).map(u => (
                    <li key={u.name} style={{ marginBottom: 2 }}>
                      <bdi>{u.name}</bdi> <span style={{ color: 'var(--muted)' }}>{t('pg.modelsMaps.gm.rows', { n: u.count.toLocaleString() })}</span>
                      {setId != null && (
                        <PinSelect set={set} value={draft[u.name]} label={u.name}
                          onChange={i => setDraft(d => {
                            const next = { ...d }
                            if (i == null) delete next[u.name]; else next[u.name] = i
                            return next
                          })} />
                      )}
                    </li>
                  ))}
                </ul>
                {report.unmatched.length > 50 && (
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{t('pg.modelsMaps.gm.more', { n: report.unmatched.length - 50 })}</div>
                )}
                {Object.keys(draft).length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                    <button type="button" className="btn btn-sm" disabled={saving} onClick={() => void savePins()}>
                      {saving ? t('pg.modelsMaps.gm.saving') : t('pg.modelsMaps.gm.savePins', { n: Object.keys(draft).length })}
                    </button>
                    <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('pg.modelsMaps.gm.pinsShared')}</span>
                  </div>
                )}
                {pinError && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{pinError}</div>}
                <p style={{ fontSize: 11, color: 'var(--muted)', margin: '6px 0 0' }}>
                  {t(setId != null ? 'pg.modelsMaps.gm.exactPin' : 'pg.modelsMaps.gm.exactFix')}
                </p>
              </div>
            ) : (
              <p style={{ margin: 0, fontSize: 12 }}>{t('pg.modelsMaps.gm.allMatch')}</p>
            )}
            {truncated && (
              <p role="note" style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>
                {t('pg.modelsMaps.gm.truncated', { shown: truncated.shown.toLocaleString(), of: truncated.of.toLocaleString() })}
              </p>
            )}
            <p style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>{geoMatchSentence(report, undefined, t)}</p>
          </>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
          <button type="button" className="btn btn-sm" onClick={onClose}>{t('pg.modelsMaps.cancel')}</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!report} title={!report ? t('pg.modelsMaps.gm.stillChecking') : undefined} onClick={onCommit}>
            {report && !good ? t('pg.modelsMaps.gm.useAnyway', { pct: report.pctRows }) : t('pg.modelsMaps.gm.use')}
          </button>
        </div>
      </div>
    </div>
  )
}
