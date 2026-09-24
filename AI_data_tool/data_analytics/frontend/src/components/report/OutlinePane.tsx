import { useState } from 'react'
import type { Report, ReportPage, Widget } from '../../types/report'

/**
 * The report's structure as a tree: pages, their widgets, and container
 * membership. SAS's Outline is also where objects get renamed and moved into
 * containers, so both live here: double-click renames a widget, and the
 * container select re-parents it — the same config.container_id the canvas
 * uses, so the two views can never disagree.
 */
export default function OutlinePane({ report, activePageId, selectedWidgetId, onSelect, onRename, onSetContainer }: {
  report: Report
  activePageId?: number
  selectedWidgetId?: number
  onSelect: (widgetId: number, pageId: number) => void
  onRename: (widgetId: number, pageId: number, title: string) => void
  onSetContainer: (widgetId: number, pageId: number, containerId: number | null) => void
}) {
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  const label = (w: Widget) => w.title || `${w.widget_type} ${w.id}`

  const commit = (w: Widget, pageId: number) => {
    setEditing(null)
    const title = draft.trim()
    if (title && title !== w.title) onRename(w.id, pageId, title)
  }

  const renderWidget = (w: Widget, page: ReportPage, containers: Widget[], depth: number) => (
    <li key={w.id}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingInlineStart: depth * 14,
        background: w.id === selectedWidgetId ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent', borderRadius: 4 }}>
        {editing === w.id ? (
          <input autoFocus value={draft} aria-label={`Rename ${label(w)}`}
            onChange={e => setDraft(e.target.value)}
            onBlur={() => commit(w, page.id)}
            onKeyDown={e => { if (e.key === 'Enter') commit(w, page.id); if (e.key === 'Escape') setEditing(null) }}
            style={{ fontSize: 11, flex: 1 }} />
        ) : (
          <button onClick={() => onSelect(w.id, page.id)}
            onDoubleClick={() => { setEditing(w.id); setDraft(w.title || '') }}
            title="Click to select, double-click to rename"
            style={{ flex: 1, textAlign: 'start', border: 'none', background: 'none', cursor: 'pointer',
              fontSize: 11, color: 'var(--text)', padding: '3px 4px', whiteSpace: 'nowrap',
              overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {w.widget_type === 'container' ? '▣ ' : ''}{label(w)}
          </button>
        )}
        {w.widget_type !== 'container' && containers.length > 0 && (
          <select aria-label={`Container for ${label(w)}`}
            value={(w.config as { container_id?: number })?.container_id ?? ''}
            onChange={e => onSetContainer(w.id, page.id, e.target.value ? Number(e.target.value) : null)}
            style={{ fontSize: 9, maxWidth: 70 }}>
            <option value="">—</option>
            {containers.map(c => <option key={c.id} value={c.id}>{label(c)}</option>)}
          </select>
        )}
      </div>
    </li>
  )

  return (
    <div style={{ padding: 12, overflowY: 'auto', height: '100%' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Outline
      </div>
      {report.pages.map(page => {
        const widgets = page.widgets ?? []
        const containers = widgets.filter(w => w.widget_type === 'container')
        const childOf = (id: number) => widgets.filter(w =>
          (w.config as { container_id?: number })?.container_id === id)
        const topLevel = widgets.filter(w =>
          (w.config as { container_id?: number })?.container_id == null)
        return (
          <div key={page.id} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 700, padding: '2px 0',
              color: page.id === activePageId ? 'var(--accent)' : 'var(--text)' }}>
              {page.name}
              <span style={{ fontWeight: 400, color: 'var(--muted)' }}> · {widgets.length}</span>
            </div>
            <ul style={{ listStyle: 'none' }}>
              {topLevel.map(w => (
                w.widget_type === 'container' ? (
                  <li key={w.id}>
                    <ul style={{ listStyle: 'none' }}>
                      {renderWidget(w, page, containers, 0)}
                      {childOf(w.id).map(c => renderWidget(c, page, containers, 1))}
                    </ul>
                  </li>
                ) : renderWidget(w, page, containers, 0)
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
