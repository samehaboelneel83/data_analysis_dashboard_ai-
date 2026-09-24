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

/** Distinct values of a column with their row counts, as the widget pipeline
 *  (row security included) sees them. The cap is disclosed, never silent. */
export const GEO_CHECK_LIMIT = 5000

export function useGeoMatch(datasetId: number | null | undefined, column: string | null | undefined,
                            setId: number | null | undefined, version = 0) {
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
      .catch(() => { if (live) setError(`Could not read the values of ${column}.`) })
    return () => { live = false }
  }, [datasetId, column])
  const report: GeoMatchReport | null = useMemo(
    // Never scored against the fallback world map when the chosen set failed
    // to load: that would report a match rate for shapes nobody asked for.
    () => (values && !setLoading && !regionError ? geoMatchReport(values, set) : null), [values, set, setLoading, regionError])
  return { report, set, loading: values == null || setLoading, error: error ?? regionError, truncated }
}

function PreviewMap({ features, matched }: { features: RegionFeature[]; matched: Set<RegionFeature> }) {
  const W = 360, H = 200
  // Framed on what matched; with nothing matched, on the whole set, so the
  // author still sees WHICH shapes their values failed to name.
  const { path } = useMemo(() => fittedProjection(W, H,
    (matched.size ? [...matched] : features).flatMap(f => regionBoundsPoints(f)), 6), [matched, features])
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" data-testid="geo-check-preview"
      aria-label={`Preview: ${matched.size} matched regions filled`}
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
  const options = useMemo(() => set.features
    .map((f, i) => ({ i, name: regionLabel(f, set) || `Region ${i + 1}` }))
    .sort((a, b) => a.name.localeCompare(b.name)), [set])
  return (
    <select aria-label={`Pin ${label} to a region`} value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
      style={{ marginInlineStart: 6, fontSize: 11, maxWidth: 170 }}>
      <option value="">Pin to…</option>
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
        ?? 'Could not save the pins')
    } finally { setSaving(false) }
  }
  const good = report != null && report.unmatched.length === 0
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={`Check ${column} against ${setName}`}
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(440px, calc(100vw - 32px))', maxHeight: 'calc(100vh - 64px)', overflow: 'auto',
          display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ fontWeight: 700 }}>Map {column} with {setName}?</div>
        {error && <div role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>}
        {loading && !error && <div style={{ color: 'var(--muted)', fontSize: 12 }}>Checking every value…</div>}
        {report && (
          <>
            <div data-testid="geo-check-rate" style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 26, fontWeight: 700, color: good ? 'var(--success, #2e7d32)' : report.pctRows >= 80 ? 'var(--text)' : 'var(--danger)' }}>
                {report.pctRows}%
              </span>
              <span style={{ color: 'var(--muted)', fontSize: 12 }}>
                of rows mapped · {report.matchedValues} of {report.totalValues} values found
              </span>
            </div>
            <PreviewMap features={set.features} matched={report.matchedFeatures} />
            {report.unmatched.length > 0 ? (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
                  Not on the map ({report.unmatched.length})
                </div>
                <ul data-testid="geo-check-unmatched" style={{ margin: 0, paddingInlineStart: 18, maxHeight: 140, overflow: 'auto', fontSize: 12 }}>
                  {report.unmatched.slice(0, 50).map(u => (
                    <li key={u.name} style={{ marginBottom: 2 }}>
                      {u.name} <span style={{ color: 'var(--muted)' }}>— {u.count.toLocaleString()} row{u.count === 1 ? '' : 's'}</span>
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
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>…and {report.unmatched.length - 50} more.</div>
                )}
                {Object.keys(draft).length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                    <button type="button" className="btn btn-sm" disabled={saving} onClick={() => void savePins()}>
                      {saving ? 'Saving…' : `Save ${Object.keys(draft).length} pin${Object.keys(draft).length === 1 ? '' : 's'}`}
                    </button>
                    <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>Every map using this set will read them.</span>
                  </div>
                )}
                {pinError && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{pinError}</div>}
                <p style={{ fontSize: 11, color: 'var(--muted)', margin: '6px 0 0' }}>
                  Matching is exact (case and accents ignored), never guessed. {setId != null
                    ? 'Pin a value to the region it means, fix the spelling with a prep step (Find & replace), or use a boundary file that names these regions.'
                    : 'Fix the spelling with a prep step (Find & replace), or choose a boundary set that names these regions.'}
                </p>
              </div>
            ) : (
              <p style={{ margin: 0, fontSize: 12 }}>Every value names a region.</p>
            )}
            {truncated && (
              <p role="note" style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>
                Checked the {truncated.shown.toLocaleString()} most common of {truncated.of.toLocaleString()} values.
              </p>
            )}
            <p style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>{geoMatchSentence(report)}</p>
          </>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
          <button type="button" className="btn btn-sm" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!report} title={!report ? 'Still checking which values match' : undefined} onClick={onCommit}>
            {report && !good ? `Use anyway (${report.pctRows}% mapped)` : 'Use as geography'}
          </button>
        </div>
      </div>
    </div>
  )
}
