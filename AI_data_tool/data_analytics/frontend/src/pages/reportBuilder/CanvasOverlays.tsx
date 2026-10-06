import { AlignHorizontalDistributeCenter, AlignStartHorizontal, AlignStartVertical, Copy, Database, Filter, FilterX, Gauge } from 'lucide-react'
import type { Widget } from '../../types/report'
import { useCrossFilter } from '../../components/report/CrossFilterContext'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { gridStyle } from './grid'
import { HEAVY_PAGE } from '../../components/report/ReviewPane'

/**
 * The builder canvas's overlays (redesign 7e4), drawn beside WidgetRenderer,
 * never inside it, and never on the move path: they read the layout, they do
 * not change it. Physical left, like gridStyle: the canvas is not mirrored in
 * Arabic, so neither are its guides.
 */

/** The Review panel's heavy-page count, shared so the two never disagree. */
export { HEAVY_PAGE }

type Layout = Widget['layout']
const px = (l: Layout, w: number) => gridStyle(l, w) as { left: number; top: number; width: number; height: number }

/** The selected widget's edges carried across the page as dashed guides, and
 *  where it sits: "col 1–6 · row 8 · aligned ×5" (edges it shares with other
 *  widgets). */
export function SelectionGuides({ layout, others, containerW }: { layout: Layout; others: Layout[]; containerW: number }) {
  const t = useT()
  const b = px(layout, containerW)
  const shares = others.filter(o => o.x === layout.x || o.x + o.w === layout.x + layout.w || o.y === layout.y || o.y + o.h === layout.y + layout.h).length
  const where = t('bd.guide.where', { from: localDigits(String(layout.x + 1)), to: localDigits(String(layout.x + layout.w)), row: localDigits(String(layout.y + 1)) })
  return (
    <div className="dl-bd-guides" aria-hidden data-testid="selection-guides">
      <i className="v" style={{ left: b.left }} />
      <i className="v" style={{ left: b.left + b.width }} />
      <i className="h" style={{ top: b.top }} />
      <i className="h" style={{ top: b.top + b.height }} />
      <span className="dl-bd-coord" style={{ left: b.left, top: b.top + b.height + 4 }}>
        {where}{shares > 0 && ` · ${t('bd.guide.aligned', { n: localDigits(String(shares)) })}`}
      </span>
    </div>
  )
}

/** The box around a multi-selection, with how many and the quick lay-out
 *  actions. The full set of v1's align and distribute modes is in Properties. */
export function GroupBox({ layouts, containerW, onAlignLeft, onAlignTop, onDistribute }: {
  layouts: Layout[]; containerW: number; onAlignLeft: () => void; onAlignTop: () => void; onDistribute: () => void
}) {
  const t = useT()
  const bs = layouts.map(l => px(l, containerW))
  const left = Math.min(...bs.map(b => b.left)), top = Math.min(...bs.map(b => b.top))
  const right = Math.max(...bs.map(b => b.left + b.width)), bottom = Math.max(...bs.map(b => b.top + b.height))
  return (
    <div className="dl-bd-group" data-testid="group-box" style={{ left: left - 4, top: top - 4, width: right - left + 8, height: bottom - top + 8 }}>
      <div className="dl-bd-group__bar" role="toolbar" aria-label={t('bd.group.aria')}>
        <b>{t('bd.group.n', { n: localDigits(String(layouts.length)) })}</b>
        <button type="button" onClick={onAlignLeft} aria-label={t('bd.group.left')} title={t('bd.group.left')}><AlignStartVertical size={14} aria-hidden /></button>
        <button type="button" onClick={onAlignTop} aria-label={t('bd.group.top')} title={t('bd.group.top')}><AlignStartHorizontal size={14} aria-hidden /></button>
        <button type="button" onClick={onDistribute} aria-label={t('bd.group.spread')} title={t('bd.group.spread')}><AlignHorizontalDistributeCenter size={14} aria-hidden /></button>
      </div>
    </div>
  )
}

/** On hover, focus or selection in edit mode: the quick actions the
 *  prototype floats over a widget. WidgetRenderer's own header keeps delete
 *  and its ⋮ menu. */
export function EditToolbar({ title, onDuplicate, onAssign, onFilters }: {
  title: string; onDuplicate?: () => void; onAssign: () => void; onFilters: () => void
}) {
  const t = useT()
  return (
    <div className="dl-bd-wt" role="toolbar" aria-label={t('bd.wt.aria', { title })}>
      {onDuplicate && (
        <button type="button" onClick={onDuplicate} aria-label={t('bd.wt.dup', { title })} title={t('bd.wt.dupShort')}><Copy size={14} aria-hidden /></button>
      )}
      <button type="button" onClick={onAssign} aria-label={t('bd.wt.data', { title })} title={t('bd.wt.dataShort')}><Database size={14} aria-hidden /></button>
      <button type="button" onClick={onFilters} aria-label={t('bd.wt.filters', { title })} title={t('bd.wt.filtersShort')}><Filter size={14} aria-hidden /></button>
    </div>
  )
}

/** A widget that came back empty while the reader's filters are on says so,
 *  with the way out: clear the page and cross filters. */
export function EmptyResultNote({ rowCount, pageFiltered, onClearPage }: { rowCount?: number; pageFiltered: boolean; onClearPage: () => void }) {
  const t = useT()
  const { activeFilters, clearAllFilters } = useCrossFilter()
  if (rowCount !== 0 || !(pageFiltered || activeFilters.length > 0)) return null
  return (
    <div className="dl-bd-empty" role="status">
      <FilterX size={14} aria-hidden />
      <span>{t('bd.empty.text')}</span>
      <button type="button" onClick={() => { clearAllFilters(); onClearPage() }}>{t('bd.empty.clear')}</button>
    </div>
  )
}

/** The prototype's heavy-page hint. "Split page" needs a backend endpoint
 *  (listed), so it opens Performance instead. */
export function HeavyPageBanner({ n, onPerformance }: { n: number; onPerformance: () => void }) {
  const t = useT()
  if (n <= HEAVY_PAGE) return null
  return (
    <div className="dl-bd-hint" role="note">
      <Gauge size={16} aria-hidden />
      <span>{t('bd.heavy.text', { n: localDigits(String(n)) })}</span>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onPerformance}>{t('bd.heavy.perf')}</button>
    </div>
  )
}
