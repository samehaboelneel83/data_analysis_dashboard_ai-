import type { Widget } from '../../types/report'

export default function TabOrderPane({ widgets, onUpdate }: {
  widgets: Widget[]
  onUpdate: (widgetId: number, config: Record<string, unknown>) => void
}) {
  const ordered = [...widgets].sort((a, b) => ((a.config as any).tabIndex ?? 999) - ((b.config as any).tabIndex ?? 999))

  const move = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= ordered.length) return
    const next = [...ordered]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    next.forEach((w, i) => onUpdate(w.id, { ...w.config, tabIndex: i + 1 }))
  }

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Tab order
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        Controls keyboard-Tab order through widgets in View mode.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {ordered.map((w, idx) => (
          <div key={w.id} data-testid="tab-order-row" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 7px', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', width: 16 }}>{idx + 1}</span>
            <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.title || w.widget_type}</span>
            <button onClick={() => move(idx, -1)} disabled={idx === 0} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === 0 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>↑</button>
            <button onClick={() => move(idx, 1)} disabled={idx === ordered.length - 1} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === ordered.length - 1 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>↓</button>
          </div>
        ))}
        {ordered.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No widgets on this page.</span>}
      </div>
    </div>
  )
}
