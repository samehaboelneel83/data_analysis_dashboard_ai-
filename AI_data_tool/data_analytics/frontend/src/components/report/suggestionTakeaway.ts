/**
 * What a suggested chart SAYS, read from its own data -- so the Suggestions
 * panel can lead with the finding ("Delivered has 98% of freight value")
 * instead of the column names it was built from ("freight_value by
 * order_status"), and sort the strongest findings first.
 *
 * Everything here is computed from the rows the chart itself draws; nothing
 * is guessed. A shape it cannot read (no rows, an unknown type) gets no
 * takeaway, and the card keeps its plain title.
 */

export type SugFamily = 'summary' | 'compare' | 'trend' | 'dist' | 'rel'

export interface Takeaway {
  headline: string
  /** The numbers behind the headline, for the expanded card. */
  detail: string
  /** 0..1: how striking the finding is. Sorts the panel, strongest first. */
  strength: number
}

interface Row { name?: unknown; value?: unknown; bin_start?: unknown; other?: unknown; x?: unknown; y?: unknown }

/** "freight_value" -> "freight value"; "orderDate" stays readable too. */
export function words(column: string): string {
  return column.replace(/[_\s]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim().toLowerCase()
}
export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export function familyOf(widgetType: string): SugFamily {
  if (['kpi', 'card', 'gauge'].includes(widgetType)) return 'summary'
  if (['line', 'area', 'step', 'stacked_area', 'combo'].includes(widgetType)) return 'trend'
  if (['histogram', 'box', 'boxplot', 'box_plot', 'violin'].includes(widgetType)) return 'dist'
  // Two things at once: a pair of numbers, two categories that travel
  // together, a model of what goes with what.
  if (['scatter', 'bubble', 'heatmap'].includes(widgetType) || widgetType.startsWith('model_')) return 'rel'
  return 'compare'
}

/** 1234567 -> "1.23M", 208716 -> "208.7K", 337.56 -> "338", 20.48 -> "20.5". */
export function short(n: number): string {
  const a = Math.abs(n)
  const trim = (s: string) => s.replace(/\.0+([KMB]?)$/, '$1').replace(/(\.\d*?)0+([KMB]?)$/, '$1$2')
  if (a >= 1e9) return trim((n / 1e9).toFixed(2)) + 'B'
  if (a >= 1e6) return trim((n / 1e6).toFixed(2)) + 'M'
  if (a >= 1e4) return trim((n / 1e3).toFixed(1)) + 'K'
  if (a >= 100) return String(Math.round(n))
  if (a >= 10) return trim(n.toFixed(1))
  return trim(n.toFixed(2))
}
const full = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
/** A time bucket's label in words: "2018-08" -> "Aug 2018", a week -> "the week of 13 Aug 2018". */
export function when(row: Row): string {
  const name = String(row.name ?? '')
  let m = /^(\d{4})-(\d{2})$/.exec(name)
  if (m) return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`
  m = /^(\d{4})-Q([1-4])$/.exec(name)
  if (m) return `Q${m[2]} ${m[1]}`
  if (/^\d{4}$/.test(name)) return name
  // The calendar day as written -- never through the reader's time zone,
  // which turned "2018-08-13" into the 12th east of Greenwich.
  const start = typeof row.bin_start === 'string' ? row.bin_start : /^\d{4}-\d{2}-\d{2}/.test(name) ? name : null
  const ymd = start ? /^(\d{4})-(\d{2})-(\d{2})/.exec(start) : null
  if (ymd) {
    const day = `${Number(ymd[3])} ${MONTHS[Number(ymd[2]) - 1]} ${ymd[1]}`
    return /W\d{2}$/.test(name) ? `the week of ${day}` : day
  }
  return name
}

const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v))

function aggOf(config: Record<string, unknown>): string {
  return String(config.aggregation ?? (config.measure ? 'sum' : 'count')).toLowerCase()
}

function measureWords(config: Record<string, unknown>): string {
  const m = typeof config.measure === 'string' ? config.measure : ''
  const agg = aggOf(config)
  if (agg === 'count') return 'rows'
  if (agg === 'countd') return m ? `distinct ${words(m)}` : 'rows'
  return m ? words(m) : 'rows'
}

/** An average (or median) has no whole to take a share of. */
const isAverage = (config: Record<string, unknown>) => ['avg', 'mean', 'average', 'median'].includes(aggOf(config))

/** The bin's upper edge from a label like "0.85–337.56". */
function binHigh(name: string): number | null {
  const parts = name.split(/[–-]/).map(s => Number(s.replace(/,/g, '').trim())).filter(n => Number.isFinite(n))
  return parts.length >= 2 ? parts[parts.length - 1] : null
}

export function takeaway(widgetType: string, config: Record<string, unknown>, rawRows: unknown): Takeaway | null {
  const rows: Row[] = Array.isArray(rawRows) ? (rawRows as Row[]).filter(r => r && typeof r === 'object') : []
  const fam = familyOf(widgetType)
  const measure = measureWords(config)

  if (fam === 'rel') return null    // the correlation already is the finding: keep its own words

  const vals = rows.map(r => num(r.value)).filter(Number.isFinite)
  if (vals.length < 2) return null

  if (fam === 'compare') {
    const named = rows.filter(r => !r.other && Number.isFinite(num(r.value)))
    const total = vals.reduce((s, v) => s + v, 0)
    if (!named.length || total <= 0) return null
    const sorted = [...named].sort((a, b) => num(b.value) - num(a.value))
    const top = sorted[0]
    if (isAverage(config)) {
      // "Sales has the highest average salary" -- never "Sales has 16% of
      // salary", which reads as a pay finding and is a head-count.
      const mean = vals.reduce((s, v) => s + v, 0) / vals.length
      const low = sorted[sorted.length - 1]
      const ratio = mean ? num(top.value) / mean : 1
      // Within 2% of each other is "the same": "M has the highest average
      // salary: 72K" headlined a 72,045 vs 71,964 non-difference (2026-10-02).
      const dim = typeof config.dimension === 'string' ? words(config.dimension) : 'group'
      if (mean && (num(top.value) - num(low.value)) / Math.abs(mean) < 0.02) {
        return {
          headline: `Average ${measure} is about the same for every ${dim}: ${short(mean)}`,
          detail: `From ${full(num(low.value))} (${low.name}) to ${full(num(top.value))} (${top.name}): under 2% apart.`,
          strength: 0.05,
        }
      }
      return {
        headline: `${cap(String(top.name))} has the highest average ${measure}: ${short(num(top.value))}`,
        detail: `${cap(String(top.name))} averages ${full(num(top.value))}; the lowest is ${low.name} at ${full(num(low.value))}.`,
        strength: Math.min(1, Math.max(0, (ratio - 1) * 2)),
      }
    }
    const share = num(top.value) / total
    const pct = Math.round(share * 100)
    const topName = String(top.name)
    const second = sorted[1]
    const detail = `${cap(topName)} accounts for ${full(num(top.value))} of ${full(total)} (${pct}%)`
      + (second ? `. Next is ${second.name} with ${full(num(second.value))} (${Math.round(num(second.value) / total * 100)}%).` : '.')
    return share >= 0.35
      ? { headline: `${cap(topName)} has ${pct}% of ${measure === 'rows' ? 'all rows' : measure}`, detail, strength: share }
      : { headline: `${cap(topName)} leads ${measure} with ${short(num(top.value))}`, detail, strength: share }
  }

  if (fam === 'trend') {
    let peak = 0
    vals.forEach((v, i) => { if (v > vals[peak]) peak = i })
    const mean = vals.reduce((s, v) => s + v, 0) / vals.length
    const peakRow = rows.filter(r => Number.isFinite(num(r.value)))[peak]
    const first = rows[0], last = rows[rows.length - 1]
    const lastV = vals[vals.length - 1]
    const strength = mean > 0 ? Math.min(1, (vals[peak] / mean - 1) / 2) : 0
    const detail = `${cap(measure)} went from ${full(vals[0])} in ${when(first)} to a peak of ${full(vals[peak])} in ${when(peakRow)}`
      + (peak < vals.length - 1 ? `, and was ${full(lastV)} in ${when(last)}.` : '.')
    return { headline: `${cap(measure)} peaked in ${when(peakRow)} at ${short(vals[peak])}`, detail, strength }
  }

  // dist: a histogram's rows are bins, value = how many rows fall in each.
  const total = vals.reduce((s, v) => s + v, 0)
  if (total <= 0) return null
  let maxI = 0
  vals.forEach((v, i) => { if (v > vals[maxI]) maxI = i })
  const share = vals[maxI] / total
  const pct = Math.round(share * 100)
  const bin = String(rows[maxI].name)
  const hi = binHigh(bin)
  const detail = `${full(vals[maxI])} of ${full(total)} rows (${pct}%) have ${measure} in ${bin}.`
  if (maxI === 0 && hi != null && share >= 0.5) {
    return { headline: `${pct}% of rows have ${measure} under ${short(hi)}`, detail, strength: share }
  }
  return { headline: `Most ${measure} values fall in ${bin}`, detail, strength: share }
}

/** Plain-word axis names for a chart: "Order status" and "Total freight value",
 *  not "order_status" and "sum(freight_value)". Pies have no axes. */
export function axisNames(widgetType: string, config: Record<string, unknown>): { x?: string; y?: string } {
  const fam = familyOf(widgetType)
  if (['pie', 'donut', 'treemap', 'funnel', 'kpi', 'card', 'gauge'].includes(widgetType) || widgetType.startsWith('model_')) return {}
  const str = (v: unknown) => (typeof v === 'string' ? cap(words(v)) : undefined)
  if (widgetType === 'bubble') return { x: str(config.measure), y: str(config.measure2) }
  if (widgetType === 'heatmap') return { x: str(config.dimension2), y: str(config.dimension) }
  if (widgetType === 'box_plot') return { x: str(config.dimension), y: str(config.measure) }
  const agg = String(config.aggregation ?? (config.measure ? 'sum' : 'count')).toLowerCase()
  const m = typeof config.measure === 'string' ? words(config.measure) : ''
  const AGG: Record<string, string> = { sum: 'Total', avg: 'Average', mean: 'Average', min: 'Lowest', max: 'Highest', median: 'Median' }
  const measureName = !m || agg === 'count' ? 'Number of rows'
    : agg === 'countd' ? `Count of ${m}` : `${AGG[agg] ?? cap(agg)} ${m}`
  if (fam === 'dist') return { x: cap(m || 'value'), y: 'Number of rows' }
  if (fam === 'rel') {
    const x = config.x_column ?? config.dimension
    const y = config.y_column ?? config.measure
    return { x: typeof x === 'string' ? cap(words(x)) : undefined, y: typeof y === 'string' ? cap(words(y)) : undefined }
  }
  const d = typeof config.dimension === 'string' ? cap(words(config.dimension)) : undefined
  // A 100% stack shows each bar's MIX: its axis is a share, not a count.
  if (config.bar_mode === 'stacked100') {
    const d2 = typeof config.dimension2 === 'string' ? words(config.dimension2) : ''
    return { x: d, y: d2 ? `Share of each ${d2}` : 'Share' }
  }
  return { x: d, y: measureName }
}

/** A tiny shape-only picture of the data: bars or a line in a w×h box (SVG path data). */
export function thumbnail(widgetType: string, rawRows: unknown, w = 64, h = 36): { kind: 'bars' | 'line'; d: string; area?: string } | null {
  const rows: Row[] = Array.isArray(rawRows) ? (rawRows as Row[]) : []
  const vals = rows.map(r => num(r?.value)).filter(Number.isFinite)
  if (vals.length < 2) return null
  const r1 = (x: number) => Math.round(x * 10) / 10
  if (familyOf(widgetType) === 'trend') {
    const top = Math.max(...vals) || 1
    const pts = vals.map((v, i) => [2 + i * (w - 4) / (vals.length - 1), 2 + (h - 4) * (1 - v / top)])
    const d = 'M' + pts.map(([x, y]) => `${r1(x)} ${r1(y)}`).join('L')
    return { kind: 'line', d, area: `${d}L${r1(pts[pts.length - 1][0])} ${h}L${r1(pts[0][0])} ${h}Z` }
  }
  // Square-root heights: one dominant bar would otherwise flatten the rest
  // to nothing, and the thumbnail is about the SHAPE, not exact values.
  const shown = vals.slice(0, 24)
  const top = Math.sqrt(Math.max(...shown.map(v => Math.max(0, v)))) || 1
  const gap = shown.length > 10 ? 0.8 : 3
  const bw = (w - gap * (shown.length - 1)) / shown.length
  const d = shown.map((v, i) => {
    const bh = v > 0 ? Math.max(1.2, h * Math.sqrt(v) / top) : 0.6
    return `M${r1(i * (bw + gap))} ${r1(h - bh)}h${r1(bw)}v${r1(bh)}h${r1(-bw)}Z`
  }).join('')
  return { kind: 'bars', d }
}

/** The chart's identity for "already on this page": same family, same fields.
 *  A donut of price by status IS a bar of price by status, for this purpose. */
export function signature(widgetType: string, config: Record<string, unknown>): string {
  const fam = familyOf(widgetType === 'donut' ? 'pie' : widgetType)
  const s = (v: unknown) => (typeof v === 'string' ? v : '')
  if (fam === 'rel') return `rel|${widgetType.startsWith('model_') ? widgetType : ''}|${s(config.x_column ?? config.dimension)}|${s(config.y_column ?? config.measure)}|${s(config.measure2 ?? config.dimension2)}`
  // A box plot splits by a group; a histogram does not -- not the same chart.
  if (fam === 'dist') return `dist|${s(config.measure)}|${widgetType === 'box_plot' ? s(config.dimension) : ''}`
  if (fam === 'summary') return `summary|${s(config.measure)}|${s(config.aggregation)}`
  // A mix (stacked by a second column) is not the plain split it stacks.
  return `${fam}|${s(config.dimension)}|${s(config.measure)}|${s(config.dimension2)}`
}
