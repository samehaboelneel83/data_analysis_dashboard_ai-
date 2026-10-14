import { LineChart } from 'lucide-react'
import type { Report, Widget } from '../../types/report'
import { useT } from '../../i18n'

/**
 * A dashboard's thumbnail, drawn from its own first page: one box per widget at
 * the widget's place on the 12-column grid, with a glyph for its kind. There
 * are no rendered screenshots in this backend, so this is a schematic, never a
 * picture of data -- the bars and lines are the same for every chart.
 */

const ROWS_SHOWN = 10

type Glyph = 'kpi' | 'table' | 'text' | 'line' | 'donut' | 'bars'

const KPI = new Set(['kpi', 'card', 'gauge', 'needle'])
const TABLE = new Set(['table', 'crosstab', 'matrix', 'list', 'schedule'])
const TEXT = new Set(['text', 'button', 'image', 'shape', 'web_content', 'slicer', 'container', 'custom_visual', 'script'])
const LINE = new Set(['line', 'area', 'step', 'forecast', 'dual_axis_time_series', 'comparative_time_series', 'numeric_series', 'dual_axis_line', 'ribbon'])
const DONUT = new Set(['pie', 'donut', 'sunburst', 'circle_pack', 'map_pie'])

export function glyphOf(type: string): Glyph {
  if (KPI.has(type)) return 'kpi'
  if (TABLE.has(type)) return 'table'
  if (TEXT.has(type)) return 'text'
  if (LINE.has(type)) return 'line'
  if (DONUT.has(type)) return 'donut'
  return 'bars'
}

const BARS = [[42, 64, 52, 90, 70, 58], [80, 62, 50, 38, 24], [30, 55, 75, 60, 85, 45]]
const LINES = [[30, 26, 28, 19, 22, 15, 17, 10], [28, 22, 25, 17, 20, 12, 15, 9]]

function Body({ glyph, n }: { glyph: Glyph; n: number }) {
  const c = `var(--dl-series-${(n % 6) + 1})`
  switch (glyph) {
    case 'kpi': return <div className="hm-th__k"><i /><i /></div>
    case 'text': return <div className="hm-th__tx"><i /><i /><i /></div>
    case 'table': return (
      <div className="hm-th__tb">
        {[0, 1, 2, 3].map(i => <div key={i} className={i ? '' : 'h'}><i /><i /><i /></div>)}
      </div>
    )
    case 'line': {
      const p = LINES[n % LINES.length]
      const q = p.map((y, i) => `${(i * 100 / (p.length - 1)).toFixed(1)},${y}`).join(' ')
      return (
        <svg viewBox="0 0 100 40" preserveAspectRatio="none">
          <polygon points={`0,40 ${q} 100,40`} fill={c} opacity=".16" />
          <polyline points={q} fill="none" stroke={c} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </svg>
      )
    }
    case 'donut': {
      let o = 0
      return (
        <svg viewBox="0 0 40 40">
          {[21, 19, 20, 22].map((l, i) => {
            const el = <circle key={i} cx="20" cy="20" r="13" fill="none" stroke={`var(--dl-series-${i + 1})`} strokeWidth="7"
              strokeDasharray={`${l} 82`} strokeDashoffset={-o} transform="rotate(-90 20 20)" />
            o += l
            return el
          })}
        </svg>
      )
    }
    default: {
      const hs = BARS[n % BARS.length]
      const w = 94 / hs.length
      return (
        <svg viewBox="0 0 100 40" preserveAspectRatio="none">
          {hs.map((h, i) => <rect key={i} x={3 + i * w} y={39 - h * .37} width={w * .64} height={h * .37} rx="1.2" fill={c} />)}
        </svg>
      )
    }
  }
}

/** The page a reader lands on: the first ordinary page, else the first page. */
export function firstPageWidgets(report: Pick<Report, 'pages'> | undefined): Widget[] {
  const pages = [...(report?.pages ?? [])].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
  const page = pages.find(p => !p.page_type || p.page_type === 'normal') ?? pages[0]
  return page?.widgets ?? []
}

export default function Thumb({ widgets }: { widgets: Widget[] | null }) {
  const t = useT()
  const ws = (widgets ?? []).filter(w => w.layout && w.layout.w > 0 && w.layout.h > 0)
  if (!ws.length) {
    return (
      <div className="hm-th" aria-hidden="true">
        <div className="hm-th__em"><LineChart size={18} />{t('hm.thumb.empty')}</div>
      </div>
    )
  }
  const bottom = Math.max(...ws.map(w => w.layout.y + w.layout.h))
  const rows = Math.max(4, Math.min(bottom, ROWS_SHOWN))
  const pct = (v: number, of: number) => `${(v / of) * 100}%`
  return (
    <div className="hm-th" aria-hidden="true">
      <div className="hm-th__grid">
        {ws.filter(w => w.layout.y < rows).map((w, i) => (
          <div key={w.id} className="hm-th__b" style={{
            insetInlineStart: `calc(${pct(w.layout.x, 12)} + 2px)`, width: `calc(${pct(w.layout.w, 12)} - 4px)`,
            top: `calc(${pct(w.layout.y, rows)} + 2px)`, height: `calc(${pct(w.layout.h, rows)} - 4px)`,
          }}>
            <Body glyph={glyphOf(w.widget_type)} n={i} />
          </div>
        ))}
      </div>
    </div>
  )
}
