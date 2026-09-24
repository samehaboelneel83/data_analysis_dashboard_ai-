import type { ReportPage, Widget } from '../../types/report'

interface Props {
  page: ReportPage
  widgets: Widget[]
  onUpdate: (data: Partial<ReportPage>) => void
}

export default function MobileLayoutEditor({ page, widgets, onUpdate }: Props) {
  const known = new Set(widgets.map(w => w.id))
  const savedOrder = (page.mobile_layout?.order ?? []).filter(id => known.has(id))
  const missing = widgets.map(w => w.id).filter(id => !savedOrder.includes(id))
  const order = [...savedOrder, ...missing]
  const hidden = page.mobile_layout?.hidden ?? []

  const widgetsById = new Map(widgets.map(w => [w.id, w]))

  const commit = (nextOrder: number[], nextHidden: number[]) => {
    // Spread first: mobile_layout also carries page-level settings that are
    // not this editor's to drop (interaction_mode).
    onUpdate({ mobile_layout: { ...(page.mobile_layout ?? {}), order: nextOrder, hidden: nextHidden } })
  }

  const move = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= order.length) return
    const next = [...order]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    commit(next, hidden)
  }

  const toggleHidden = (id: number) => {
    const next = hidden.includes(id) ? hidden.filter(h => h !== id) : [...hidden, id]
    commit(order, next)
  }

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Mobile layout
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        Reorder and hide widgets for narrow-screen viewing. This does not affect the desktop layout.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {order.map((id, idx) => {
          const w = widgetsById.get(id)
          if (!w) return null
          const isHidden = hidden.includes(id)
          return (
            <div key={id} data-testid="mobile-layout-row"
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 7px',
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
                opacity: isHidden ? 0.5 : 1 }}>
              <input type="checkbox" checked={!isHidden} onChange={() => toggleHidden(id)} title="Show on mobile" />
              <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {w.title || w.widget_type}
              </span>
              <button onClick={() => move(idx, -1)} disabled={idx === 0}
                style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === 0 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>
                ↑
              </button>
              <button onClick={() => move(idx, 1)} disabled={idx === order.length - 1}
                style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === order.length - 1 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>
                ↓
              </button>
            </div>
          )
        })}
        {order.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No widgets on this page.</span>}
      </div>
    </div>
  )
}
