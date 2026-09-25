import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'

/**
 * Small multiples: the same chart repeated once per facet value.
 *
 * The panels share ONE scale, taken from the server's `max_value`. That is the
 * whole reason this visual exists — comparing panels to one another — and
 * per-panel axes would draw a small category exactly like a large one, which is
 * the single way small multiples lie. The scale is a server-side fact rather
 * than something each panel decides locally.
 *
 * Rendered as horizontal bars rather than by delegating to the inner chart's
 * own renderer: at panel size a Recharts axis is unreadable, and the comparison
 * the reader is making is between panels, not within one.
 */
export default function SmallMultiplesRenderer(
  { data, measureFmt }: ChartRendererProps,
) {
  const panels: any[] = data?.panels ?? []
  const omitted: number = data?.omitted ?? 0
  // Fall back to per-panel scaling only when the server had no numeric rows to
  // measure. Wrong for comparison, but better than dividing by zero.
  const shared: number | null = data?.max_value ?? null

  if (!panels.length) {
    return <div style={{ color: 'var(--muted)', fontSize: 12, padding: 8 }}>No data.</div>
  }

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: 4 }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${panels.length > 4 ? 150 : 200}px, 1fr))`,
        gap: 8,
      }}>
        {panels.map((p, i) => {
          const rows: any[] = p.result?.rows ?? []
          const localMax = rows.reduce(
            (m, r) => Math.max(m, Math.abs(Number(r.value) || 0)), 0) || 1
          const scale = shared && shared > 0 ? shared : localMax
          return (
            <div key={i} style={{
              border: '1px solid var(--border)', borderRadius: 4,
              padding: '6px 8px', background: 'var(--surface)',
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 5 }}>
                {p.name ?? data?.facet_by ?? 'All'}
              </div>
              {rows.slice(0, 8).map((r, j) => (
                <div key={j} style={{ marginBottom: 3 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, gap: 6 }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {String(r.name)}
                    </span>
                    <span style={{ fontFamily: 'var(--mono)', color: 'var(--muted)' }}>
                      {fmtStr(r.value, measureFmt)}
                    </span>
                  </div>
                  <div style={{ height: 4, background: 'var(--border)', borderRadius: 2 }}>
                    <div style={{
                      height: '100%', borderRadius: 2, background: 'var(--accent)',
                      width: `${Math.max(1, (Math.abs(Number(r.value) || 0) / scale) * 100)}%`,
                    }} />
                  </div>
                </div>
              ))}
              {!rows.length && (
                <div style={{ fontSize: 10, color: 'var(--muted)' }}>no rows</div>
              )}
            </div>
          )
        })}
      </div>

      {/* A reader comparing panels cannot see which categories never made it
          onto the page, so the count of those has to be stated. */}
      {omitted > 0 && (
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 6 }}>
          {omitted} more {data?.facet_by ? `${data.facet_by} value` : 'value'}
          {omitted === 1 ? '' : 's'} not shown.
        </div>
      )}
      {shared === null && panels.length > 1 && (
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>
          Panels are scaled independently.
        </div>
      )}
    </div>
  )
}
