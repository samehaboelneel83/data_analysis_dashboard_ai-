import { useMemo, useState } from 'react'
import { ArrowLeftRight, ChevronRight } from 'lucide-react'
import type { Widget } from '../../types/report'
import { conversionsFor } from '../../lib/convertWidget'
import { chartGroup, chartIcon, chartLabel, CHART_GROUP_ORDER } from './ChartGallery'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { chartName } from '../../lib/chartName'

/** The builder converts on this event: `{ widgetId, widget_type, config, label }`,
 *  saved as one undoable step. */
export const CONVERT_WIDGET_EVENT = 'datalytics:convert-widget'

/**
 * "Convert to" in a widget's right-click menu. Drills in two steps -- the
 * chart families that have a type this object can become, then the types --
 * and offers only types whose required fields the widget already holds
 * (lib/convertWidget.ts). Nothing else in the menu moves.
 */
export default function ConvertToMenu({ widget, itemStyle, onDone }: {
  widget: Widget
  itemStyle: React.CSSProperties
  onDone: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  // QA3 C6: chart names in the reader's language (the gallery's own names);
  // English keeps chartLabel exactly, as the menu always read.
  const name = (type: string) => language === 'ar' ? chartName(type, t, language) : chartLabel(type)
  const [open, setOpen] = useState(false)
  const [group, setGroup] = useState<string | null>(null)
  const options = useMemo(() => conversionsFor(widget.widget_type, (widget.config ?? {}) as Record<string, unknown>),
    [widget.widget_type, widget.config])
  const groups = useMemo(() => {
    const by = new Map<string, typeof options>()
    for (const o of options) {
      const g = chartGroup(o.type)
      by.set(g, [...(by.get(g) ?? []), o])
    }
    const rank = (g: string) => { const i = CHART_GROUP_ORDER.indexOf(g); return i < 0 ? 99 : i }
    return [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0]))
  }, [options])
  if (options.length === 0) return null

  const convert = (type: string, config: Record<string, unknown>) => {
    window.dispatchEvent(new CustomEvent(CONVERT_WIDGET_EVENT, { detail: {
      widgetId: widget.id, widget_type: type, config,
      label: t('bc.shell.undo.convert', { name: widget.title || name(widget.widget_type), to: name(type) }),
    } }))
    onDone()
  }
  const sub: React.CSSProperties = { ...itemStyle, display: 'flex', alignItems: 'center', gap: 6 }

  return (
    <div data-testid="convert-to">
      <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={open} style={sub}
        onClick={e => { e.stopPropagation(); setOpen(o => !o); setGroup(null) }}>
        <ArrowLeftRight size={12} aria-hidden />
        <span style={{ flex: 1 }}>{t('convert.menu')}</span>
        <ChevronRight size={12} aria-hidden style={{ transform: open ? 'rotate(90deg)' : 'none' }} />
      </button>
      {open && (
        <div role="menu" aria-label={t('convert.menu')} style={{ paddingInlineStart: 10, maxHeight: 300, overflowY: 'auto' }}>
          {groups.map(([g, items]) => (
            <div key={g}>
              <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={group === g} style={sub}
                onClick={e => { e.stopPropagation(); setGroup(cur => cur === g ? null : g) }}>
                <span style={{ flex: 1 }}>{g}</span>
                <span style={{ color: 'var(--muted)', fontSize: 11 }}>{items.length}</span>
                <ChevronRight size={12} aria-hidden style={{ transform: group === g ? 'rotate(90deg)' : 'none' }} />
              </button>
              {group === g && (
                <div role="menu" aria-label={g} style={{ paddingInlineStart: 10 }}>
                  {items.map(o => {
                    const Icon = chartIcon(o.type)
                    return (
                      <button key={o.type} type="button" role="menuitem" style={sub}
                        onClick={e => { e.stopPropagation(); convert(o.type, o.config) }}>
                        <Icon size={13} aria-hidden /> {name(o.type)}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
