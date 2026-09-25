import { useEffect } from 'react'
import type { Widget } from '../../types/report'
import { useCrossFilter } from './CrossFilterContext'

interface Props { widget: Widget; pageWidgets?: Widget[] }

const MODES = [
  { label: 'Two-way ⇄',        broadcasts: true,  receives: true  },
  { label: 'Broadcast only →', broadcasts: true,  receives: false },
  { label: 'Receive only ←',   broadcasts: false, receives: true  },
  { label: 'Isolated —',        broadcasts: false, receives: false },
]

export default function InteractionSettings({ widget, pageWidgets }: Props) {
  const { setInteraction, initInteraction, interactions } = useCrossFilter()
  const current = interactions[widget.id] ?? { broadcasts: true, receives: true }

  useEffect(() => {
    // Initialize only when absent: re-opening the panel must not stomp a
    // choice (the old unconditional reset silently reverted receiveMode and
    // direction every time a widget was selected).
    // `initInteraction`, not `setInteraction`: this is a default nobody chose,
    // and writing it down would rewrite the widget's config on a mere click.
    // It is also a no-op when a saved value has already been hydrated, which is
    // what stops the panel reverting a setting as it is opened to look at it.
    if (!interactions[widget.id]) initInteraction(widget.id, { broadcasts: true, receives: true })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widget.id])

  const activeIdx = MODES.findIndex(m => m.broadcasts === current.broadcasts && m.receives === current.receives)
  const receiveMode = current.receiveMode ?? 'filter'

  return (
    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Interaction mode
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {MODES.map((m, i) => (
          <button key={i} onClick={() => setInteraction(widget.id, { ...current, ...m })}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '6px 9px',
              background: i === activeIdx ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
              border: i === activeIdx ? '1px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 6, cursor: 'pointer', color: i === activeIdx ? 'var(--accent)' : 'var(--muted)',
              fontFamily: 'var(--sans)', fontSize: 12, textAlign: 'start', transition: 'all .15s',
            }}>
            {m.label}
          </button>
        ))}
      </div>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', margin: '12px 0 6px' }}>
        When receiving a selection
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {(['filter', 'highlight'] as const).map(m => (
          <button key={m} onClick={() => setInteraction(widget.id, { ...current, receiveMode: m })}
            aria-pressed={receiveMode === m}
            style={{
              flex: 1, padding: '6px 9px',
              background: receiveMode === m ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
              border: receiveMode === m ? '1px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 6, cursor: 'pointer', color: receiveMode === m ? 'var(--accent)' : 'var(--muted)',
              fontFamily: 'var(--sans)', fontSize: 12, transition: 'all .15s',
            }}>
            {m === 'filter' ? 'Filter' : 'Highlight'}
          </button>
        ))}
      </div>
      <span style={{ fontSize: 10, color: 'var(--muted)' }}>
        Highlight keeps every bar and saturates the selected share (bar charts).
      </span>

      {/* Named per-pair actions (SAS's Actions pane): choose which specific
          widgets THIS widget's selections reach, and how each pair behaves.
          Defining any action replaces broadcast-to-all, as in SAS. */}
      {(pageWidgets ?? []).filter(w => w.id !== widget.id &&
          !['text', 'button', 'image', 'shape', 'container', 'web_content', 'custom_visual'].includes(w.widget_type)).length > 0 && (
        <>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', margin: '12px 0 6px' }}>
            Actions on specific widgets
          </div>
          <span style={{ fontSize: 10, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>
            Setting any action makes this widget's selections reach only the listed widgets.
          </span>
          {(pageWidgets ?? [])
            .filter(w => w.id !== widget.id &&
              !['text', 'button', 'image', 'shape', 'container', 'web_content', 'custom_visual'].includes(w.widget_type))
            .map(w => {
              const act = current.actions?.find(a => a.targetId === w.id)
              return (
                <div key={w.id} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ flex: 1, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {w.title || w.widget_type}
                  </span>
                  <select aria-label={`Action on ${w.title || w.widget_type}`}
                    value={act?.mode ?? ''}
                    onChange={e => {
                      const mode = e.target.value as '' | 'filter' | 'highlight'
                      const rest = (current.actions ?? []).filter(a => a.targetId !== w.id)
                      const actions = mode === '' ? rest : [...rest, { targetId: w.id, mode }]
                      setInteraction(widget.id, { ...current, actions: actions.length ? actions : undefined })
                    }}
                    style={{ fontSize: 11, width: 110 }}>
                    <option value="">— default —</option>
                    <option value="filter">Filter</option>
                    <option value="highlight">Highlight</option>
                  </select>
                </div>
              )
            })}
        </>
      )}
    </div>
  )
}
