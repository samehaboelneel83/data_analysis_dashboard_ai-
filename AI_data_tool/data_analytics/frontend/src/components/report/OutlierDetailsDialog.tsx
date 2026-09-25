import { useEffect, useState } from 'react'
import { outlierApi } from '../../services/api'
import { useModalDialog } from '../ui/useModalDialog'

interface Details {
  column: string
  detector: string
  stats: { min: number; q1: number; median: number; q3: number; max: number; fence_low: number; fence_high: number }
  outliers: { count: number; total_rows: number; columns: string[]; rows: unknown[][] }
  impact: { share_of_sum: number | null; mean_with: number | null; mean_without: number | null }
}

const DETECTOR_OPTIONS = [
  { value: 'iqr',     label: '1.5×IQR fences' },
  { value: 'iforest', label: 'Isolation Forest' },
  { value: 'ecod',    label: 'ECOD' },
]

const fmt = (v: number | null | undefined) =>
  v == null ? '—' : Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })

/**
 * The detail behind the Fields pane's ⚠ badge — SAS's outlier-details report,
 * sized to a dialog: box-plot stats on the same secured frame widgets read,
 * the outlier rows themselves, and what they do to the total and the mean.
 */
export default function OutlierDetailsDialog({ datasetId, column, onClose }: {
  datasetId: number
  column: string
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [details, setDetails] = useState<Details | null>(null)
  const [error, setError] = useState('')
  const [detector, setDetector] = useState('iqr')

  useEffect(() => {
    setError('')
    outlierApi.details(datasetId, column, detector).then(setDetails)
      .catch(e => setError(e?.response?.data?.detail || 'Could not load outlier details'))
  }, [datasetId, column, detector])

  const s = details?.stats
  // Box plot geometry on a min→max scale; degenerate ranges collapse gracefully.
  const span = s ? Math.max(s.max - s.min, 1e-9) : 1
  const pct = (v: number) => `${(((v - (s?.min ?? 0)) / span) * 100).toFixed(1)}%`

  return (
    <div aria-label={`Outliers in ${column}`} onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={`Outliers in ${column}`}
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 560, maxWidth: '92vw', maxHeight: '84vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <strong style={{ fontSize: 13 }}>Outliers in {column}</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>

        <div style={{ marginBottom: 10 }}>
          <label htmlFor="anomaly-detector-select" style={{ fontSize: 11, color: 'var(--muted)', marginInlineEnd: 6 }}>
            Detector
          </label>
          <select id="anomaly-detector-select" value={detector} onChange={e => setDetector(e.target.value)}>
            {DETECTOR_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        {error && <p role="alert" style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</p>}
        {!details && !error && <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>}

        {details && s && (
          <>
            <p style={{ fontSize: 12, marginBottom: 10 }}>
              <strong>{details.outliers.count}</strong> of {details.outliers.total_rows.toLocaleString()} rows
              fall beyond 1.5×IQR ({fmt(s.fence_low)} – {fmt(s.fence_high)}).
            </p>

            {/* CSS box plot: whiskers min→max, box q1→q3, line at median */}
            <div data-testid="boxplot" style={{ position: 'relative', height: 26, margin: '4px 0 2px' }}>
              <div style={{ position: 'absolute', top: 12, left: 0, right: 0, height: 2, background: 'var(--border)' }} />
              <div style={{ position: 'absolute', top: 4, bottom: 4, left: pct(s.q1), width: `calc(${pct(s.q3)} - ${pct(s.q1)})`,
                background: 'color-mix(in srgb, var(--accent) 25%, transparent)', border: '1px solid var(--accent)', borderRadius: 3 }} />
              <div style={{ position: 'absolute', top: 2, bottom: 2, left: pct(s.median), width: 2, background: 'var(--accent)' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
              <span>min {fmt(s.min)}</span><span>q1 {fmt(s.q1)}</span><span>median {fmt(s.median)}</span>
              <span>q3 {fmt(s.q3)}</span><span>max {fmt(s.max)}</span>
            </div>

            <div style={{ fontSize: 12, borderTop: '1px solid var(--border)', paddingTop: 10, marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
                Impact
              </div>
              {details.impact.share_of_sum != null && (
                <p>The outlier rows carry <strong>{(details.impact.share_of_sum * 100).toFixed(1)}%</strong> of the column's total.</p>
              )}
              <p>Mean with outliers: <strong>{fmt(details.impact.mean_with)}</strong>
                {details.impact.mean_without != null && <> — without them: <strong>{fmt(details.impact.mean_without)}</strong></>}</p>
            </div>

            {details.outliers.rows.length > 0 && (
              <div style={{ overflowX: 'auto' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
                  Outlier rows{details.outliers.count > details.outliers.rows.length ? ` (first ${details.outliers.rows.length})` : ''}
                </div>
                <table style={{ fontSize: 11 }}>
                  <thead><tr>{details.outliers.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>
                    {details.outliers.rows.map((row, i) => (
                      <tr key={i}>{row.map((v, j) => <td key={j}>{v == null ? '—' : String(v)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
