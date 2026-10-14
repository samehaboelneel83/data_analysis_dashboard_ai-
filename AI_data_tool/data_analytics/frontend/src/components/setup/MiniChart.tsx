/**
 * A suggested chart in miniature (guided setup, PLAN_V2 4e).
 *
 * The suggestion card used to list chart titles; a person who does not know
 * charts cannot picture "Late rate by region". This draws what the server
 * already drew -- a number, sorted bars, a line, parts of a whole, the first
 * rows -- from the few values kept with the suggestion. Deliberately plain:
 * the real chart is the builder's; this only shows what the page will say.
 */
import { localDigits } from '../../lib/arabicFormats'
import type { SetupPreview } from '../../services/api'

function fmt(v: unknown, percent?: boolean): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return v == null ? '—' : String(v)
  const text = percent ? `${v.toFixed(1)}%`
    : Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2)}M`
    : Math.abs(v) >= 1e4 ? `${(v / 1e3).toFixed(1)}K`
    : v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 })
  return localDigits(text)
}

const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

export default function MiniChart({ preview, title }: { preview: SetupPreview; title: string }) {
  const { kind, rows, percent } = preview
  if (!rows.length) return null

  if (kind === 'number') {
    return (
      <div className="mini mini--number">
        {rows.map((r, i) => (
          <div key={i} className="mini__figure">
            <span className="mini__value">{fmt(r[1], percent)}</span>
            {rows.length > 1 && <span className="mini__label">{String(r[0])}</span>}
          </div>
        ))}
      </div>
    )
  }

  if (kind === 'table') {
    return (
      <div className="mini mini--table">
        <table>
          <thead><tr>{(preview.columns ?? []).map(c => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => <tr key={i}>{r.map((c, k) => <td key={k}>{c == null ? '—' : String(c)}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
    )
  }

  const values = rows.map(r => num(r[1]))
  const max = Math.max(...values.map(Math.abs), 1e-9)

  if (kind === 'line') {
    const lo = Math.min(...values), hi = Math.max(...values)
    const span = hi - lo || 1
    const W = 240, H = 56
    const points = values.map((v, i) =>
      `${(values.length === 1 ? W / 2 : (i / (values.length - 1)) * W).toFixed(1)},${(H - 4 - ((v - lo) / span) * (H - 8)).toFixed(1)}`).join(' ')
    return (
      <div className="mini mini--line">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} preserveAspectRatio="none">
          <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </svg>
        <div className="mini__ends">
          <span>{String(rows[0][0])}: {fmt(rows[0][1], percent)}</span>
          <span>{String(rows[rows.length - 1][0])}: {fmt(rows[rows.length - 1][1], percent)}</span>
        </div>
      </div>
    )
  }

  // bars, and parts of a whole (drawn as bars with their share: clearer small than a ring)
  const total = kind === 'parts' ? values.reduce((a, b) => a + Math.abs(b), 0) || 1 : 0
  return (
    <ul className="mini mini--bars" aria-label={title}>
      {rows.map((r, i) => (
        <li key={i}>
          <span className="mini__name" title={String(r[0])}>{String(r[0])}</span>
          <span className="mini__track"><span className="mini__bar" style={{ width: `${Math.max(2, (Math.abs(values[i]) / max) * 100)}%` }} /></span>
          <span className="mini__num">
            {fmt(r[1], percent)}
            {kind === 'parts' && ` · ${localDigits(String(Math.round((Math.abs(values[i]) / total) * 100)))}%`}
          </span>
        </li>
      ))}
      {(preview.more ?? 0) > 0 && <li className="mini__more">+{localDigits(String(preview.more))}</li>}
    </ul>
  )
}
