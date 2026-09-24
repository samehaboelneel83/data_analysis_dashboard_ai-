import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'

/**
 * A decomposition tree: one number, broken down a level at a time.
 *
 * The breadcrumb is the whole interaction model. A reader drills by clicking a
 * child, and climbs by clicking a crumb — so the path is always visible and
 * always reversible, which is what keeps an exploration from becoming a maze.
 *
 * Two honesty rules are enforced here rather than left to the server:
 *
 *   - every child shows its share of the parent, because "412,905" means
 *     nothing next to a total the reader has to divide in their head; and
 *   - a level the server chose is LABELLED as chosen. A suggestion presented
 *     as the reader's own decision is how an analysis quietly becomes wrong.
 *
 * Drill state lives in the widget config (`path`), not in component state: the
 * server recomputes each level, so a drilled tree survives a refresh, a filter
 * change, and being saved into a report.
 */
export default function DecompositionRenderer(
  { data, cfg, measureFmt, onClickPoint }: ChartRendererProps,
) {
  const total: number = data?.total ?? 0
  const children: any[] = data?.children ?? []
  const path: { field: string; value: string }[] = data?.path ?? []
  const available: string[] = data?.available ?? []
  // fmtStr already renders null/undefined as an em dash.
  const fmt = (v: unknown) => fmtStr(v, measureFmt)

  // Clicking a crumb truncates the path; clicking a child extends it. Both go
  // through the same config update, so there is one code path for navigation.
  const goTo = (nextPath: { field: string; value: string }[], splitBy?: string | null) =>
    onClickPoint({ __decomposition: true, path: nextPath, split_by: splitBy ?? null })

  const widest = children.reduce(
    (m, c) => Math.max(m, Math.abs(Number(c.value) || 0)), 0) || 1

  return (
    <div style={{ height: '100%', overflow: 'auto', fontSize: 12, padding: 4 }}>
      {/* Breadcrumb — always shows where you are and how to get back */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4, marginBottom: 8 }}>
        <button type="button" onClick={() => goTo([], data?.split_by)}
          style={crumbStyle(path.length === 0)}>All</button>
        {path.map((p, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: 'var(--muted)' }}>›</span>
            <button type="button" onClick={() => goTo(path.slice(0, i + 1))}
              style={crumbStyle(i === path.length - 1)}>
              {p.value}
            </button>
          </span>
        ))}
      </div>

      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 2 }}>{fmt(total)}</div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        {data?.split_by
          ? <>by <strong>{data.split_by}</strong>
              {/* Never let a server-chosen level pass as the reader's own. */}
              {data?.auto && <span title="chosen automatically as the field that separates this level most"> · suggested</span>}
            </>
          : available.length
            ? 'choose a field to break this down by'
            : 'nothing left to break down'}
      </div>

      {children.map((c, i) => {
        const value = Number(c.value)
        const share = total ? (value / total) * 100 : 0
        const terminal = c.terminal || data?.at_max_depth || !available.length
        return (
          <div key={i}
            onClick={terminal ? undefined : () => goTo([...path, { field: data.split_by, value: c.name }])}
            style={{
              marginBottom: 4, padding: '5px 7px', borderRadius: 4,
              cursor: terminal ? 'default' : 'pointer',
              background: 'var(--surface)', border: '1px solid var(--border)',
            }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ fontWeight: 500 }}>
                {c.name}
                {c.collapsed ? <span style={{ color: 'var(--muted)', fontWeight: 400 }}>
                  {' '}({c.collapsed} more)</span> : null}
              </span>
              <span style={{ fontFamily: 'var(--mono)', whiteSpace: 'nowrap' }}>
                {fmt(c.value)}
                {/* The share is the point of a decomposition; a bare number
                    makes the reader do the division. */}
                {c.value !== null && (
                  <span style={{ color: 'var(--muted)' }}> · {share.toFixed(1)}%</span>
                )}
              </span>
            </div>
            {c.value !== null && (
              <div style={{ height: 3, marginTop: 4, background: 'var(--border)', borderRadius: 2 }}>
                <div style={{
                  height: '100%', borderRadius: 2, background: 'var(--accent)',
                  width: `${Math.max(1, (Math.abs(value) / widest) * 100)}%`,
                }} />
              </div>
            )}
          </div>
        )
      })}

      {!children.length && (
        <div style={{ color: 'var(--muted)', fontSize: 11 }}>
          {path.length ? 'No rows in this branch.' : 'No data.'}
        </div>
      )}
    </div>
  )
}

function crumbStyle(active: boolean): React.CSSProperties {
  return {
    fontSize: 11, padding: '1px 6px', borderRadius: 3, cursor: 'pointer',
    border: '1px solid var(--border)',
    background: active ? 'var(--accent)' : 'var(--surface)',
    color: active ? 'var(--mc-accent-fg)' : 'var(--text)',
  }
}
