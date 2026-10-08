import { useEffect } from 'react'
import type { Widget } from '../../types/report'
import { useCrossFilter } from './CrossFilterContext'
import { useT, type MessageKey } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'

interface Props { widget: Widget; pageWidgets?: Widget[] }

// The arrows are part of each translation: they point the way the data
// flows, so they turn round in a right-to-left reading.
const MODES: { key: MessageKey; broadcasts: boolean; receives: boolean }[] = [
  { key: 'bc.canvas.ix.twoWay',    broadcasts: true,  receives: true  },
  { key: 'bc.canvas.ix.broadcast', broadcasts: true,  receives: false },
  { key: 'bc.canvas.ix.receive',   broadcasts: false, receives: true  },
  { key: 'bc.canvas.ix.isolated',  broadcasts: false, receives: false },
]

export default function InteractionSettings({ widget, pageWidgets }: Props) {
  const { setInteraction, initInteraction, interactions } = useCrossFilter()
  const current = interactions[widget.id] ?? { broadcasts: true, receives: true }
  const t = useT()
  // Letter-spacing pulls Arabic's joined letters apart, and the uppercase
  // headings must wrap rather than run past the panel's edge.
  const { language } = useDirection()
  const heading: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
    letterSpacing: language === 'ar' ? 0 : '.06em', overflowWrap: 'anywhere', whiteSpace: 'normal' }

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
      <div style={{ ...heading, marginBottom: 8 }}>
        {t('bc.canvas.ix.mode')}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {MODES.map((m, i) => (
          <button key={i} onClick={() => setInteraction(widget.id, { ...current, broadcasts: m.broadcasts, receives: m.receives })}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '6px 9px',
              background: i === activeIdx ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
              border: i === activeIdx ? '1px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 6, cursor: 'pointer', color: i === activeIdx ? 'var(--accent)' : 'var(--muted)',
              fontFamily: 'var(--sans)', fontSize: 12, textAlign: 'start', transition: 'all .15s',
            }}>
            {t(m.key)}
          </button>
        ))}
      </div>
      <div style={{ ...heading, margin: '12px 0 6px' }}>
        {t('bc.canvas.ix.whenReceiving')}
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
            {m === 'filter' ? t('bc.canvas.ix.filter') : t('bc.canvas.ix.highlight')}
          </button>
        ))}
      </div>
      <span style={{ fontSize: 11, color: 'var(--muted)' }}>
        {t('bc.canvas.ix.highlightHint')}
      </span>

      {/* Named per-pair actions (SAS's Actions pane): choose which specific
          widgets THIS widget's selections reach, and how each pair behaves.
          Defining any action replaces broadcast-to-all, as in SAS. */}
      {(pageWidgets ?? []).filter(w => w.id !== widget.id &&
          !['text', 'button', 'image', 'shape', 'container', 'web_content', 'custom_visual'].includes(w.widget_type)).length > 0 && (
        <>
          <div style={{ ...heading, margin: '12px 0 6px' }}>
            {t('bc.canvas.ix.actions')}
          </div>
          <span style={{ fontSize: 11, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>
            {t('bc.canvas.ix.actionsHint')}
          </span>
          {(pageWidgets ?? [])
            .filter(w => w.id !== widget.id &&
              !['text', 'button', 'image', 'shape', 'container', 'web_content', 'custom_visual'].includes(w.widget_type))
            .map(w => {
              const act = current.actions?.find(a => a.targetId === w.id)
              return (
                <div key={w.id} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span dir="auto" style={{ flex: 1, minWidth: 0, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {w.title || w.widget_type}
                  </span>
                  <select aria-label={t('bc.canvas.ix.actionOn', { name: w.title || w.widget_type })}
                    value={act?.mode ?? ''}
                    onChange={e => {
                      const mode = e.target.value as '' | 'filter' | 'highlight'
                      const rest = (current.actions ?? []).filter(a => a.targetId !== w.id)
                      const actions = mode === '' ? rest : [...rest, { targetId: w.id, mode }]
                      setInteraction(widget.id, { ...current, actions: actions.length ? actions : undefined })
                    }}
                    style={{ fontSize: 11, width: 110 }}>
                    <option value="">{t('bc.canvas.ix.default')}</option>
                    <option value="filter">{t('bc.canvas.ix.filter')}</option>
                    <option value="highlight">{t('bc.canvas.ix.highlight')}</option>
                  </select>
                </div>
              )
            })}
        </>
      )}
    </div>
  )
}
