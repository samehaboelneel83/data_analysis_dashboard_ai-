import type { Widget } from '../../types/report'
import { Eye, EyeOff } from 'lucide-react'

export default function SelectionPane({ widgets, onUpdate }: {
  widgets: Widget[]
  onUpdate: (widgetId: number, config: Record<string, unknown>) => void
}) {
  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Selection
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {widgets.map(w => {
          const hidden = !!(w.config as any).hidden
          return (
            <button key={w.id} aria-label={`Toggle visibility: ${w.title}`}
              onClick={() => onUpdate(w.id, { ...w.config, hidden: !hidden })}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 7px',
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
                cursor: 'pointer', textAlign: 'start', opacity: hidden ? 0.5 : 1 }}>
              <span style={{ display: 'inline-flex', color: 'var(--muted)' }}>{hidden ? <EyeOff size={13} /> : <Eye size={13} />}</span>
              <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.title}</span>
            </button>
          )
        })}
        {widgets.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No widgets on this page.</span>}
      </div>
    </div>
  )
}
