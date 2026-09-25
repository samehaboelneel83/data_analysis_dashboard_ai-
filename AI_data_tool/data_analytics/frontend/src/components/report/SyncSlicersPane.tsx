import type { ReportPage } from '../../types/report'
import type { WidgetInteraction } from './CrossFilterContext'

export default function SyncSlicersPane({ pages, interactions, onToggleSync }: {
  pages: ReportPage[]
  interactions: Record<number, WidgetInteraction>
  onToggleSync: (widgetId: number, sync: boolean) => void
}) {
  const pagesWithSlicers = pages
    .map(p => ({ page: p, slicers: p.widgets.filter(w => w.widget_type === 'slicer') }))
    .filter(g => g.slicers.length > 0)

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Sync slicers
      </div>
      {pagesWithSlicers.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No slicers in this report yet.</span>}
      {pagesWithSlicers.map(({ page, slicers }) => (
        <div key={page.id} style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>{page.name}</div>
          {slicers.map(s => {
            const synced = !!interactions[s.id]?.syncAllPages
            return (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 7px', fontSize: 12 }}>
                <span style={{ flex: 1 }}>{s.title}</span>
                <button onClick={() => onToggleSync(s.id, !synced)}
                  style={{ fontSize: 11, padding: '3px 8px', borderRadius: 99, border: '1px solid var(--border)',
                    background: synced ? 'var(--accent)' : 'var(--surface2)', color: synced ? 'var(--mc-accent-fg)' : 'var(--muted)', cursor: 'pointer' }}>
                  {synced ? 'All pages' : 'This page only'}
                </button>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
