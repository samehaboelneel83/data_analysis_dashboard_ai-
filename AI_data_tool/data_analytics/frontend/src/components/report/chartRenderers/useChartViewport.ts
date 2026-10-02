import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { autoViewport, brushProps, isTemporalAxis, type BrushRange, type FormatConfig } from './axisOptions'

/**
 * Charts drawn for paper (the print page) show every point and no slider: a
 * slider cannot be dragged on paper, and a printed window would silently
 * leave data out. Everything interactive uses the default.
 */
export const StaticChartsContext = createContext(false)

type Row = Record<string, unknown>

/**
 * The window a category chart shows, and the <Brush> that moves it.
 *
 * - Congested (more points than the tile shows legibly -- axisOptions
 *   `autoViewport`): opens on a readable window with the slider under it.
 * - Not congested: the whole series, and no slider unless the author asked
 *   for the overview axis.
 * - `overview_axis: false` set by the author: never a slider (their choice).
 *
 * Until the reader drags, the window follows the tile: resize the tile and it
 * re-fits. Once they drag, their range is kept. New data (a filter, a
 * refresh) starts again from the automatic window.
 *
 * The rows themselves are never cut: Recharts draws the window from the full
 * data, and the slider reaches every point.
 */
export function useChartViewport(
  cfg: FormatConfig & Record<string, unknown>,
  rows: readonly Row[],
  plotW: number | undefined,
  opts: { dataKey?: string; onChange?: (range: BrushRange | null) => void } = {},
) {
  const isStatic = useContext(StaticChartsContext)
  const labels = useMemo(() => rows.map(r => String(r.name ?? '')), [rows])
  const n = labels.length
  // Identifies the series, so a drag on one dataset is not applied to the next.
  const sig = `${n}|${labels[0] ?? ''}|${labels[n - 1] ?? ''}`

  const auto = autoViewport(labels, {
    fontSize: cfg.axis_tick_size ?? undefined,
    width: plotW,
    anchor: isTemporalAxis(cfg, labels) ? 'end' : 'start',
  })

  const [dragged, setDragged] = useState<{ sig: string; a: number; b: number } | null>(null)
  const user = dragged && dragged.sig === sig ? dragged : null

  // The window exists because tick LABELS crowd; an axis drawn without them
  // (axis_ticks: false) has nothing to crowd, so it shows the whole series.
  const optedOut = cfg.overview_axis === false || (cfg as { axis_ticks?: boolean }).axis_ticks === false
  const show = !isStatic && n > 1 && !optedOut && (auto.congested || cfg.overview_axis === true)

  let a = 0, b = Math.max(0, n - 1)
  if (show) {
    if (user) {
      a = Math.min(Math.max(0, user.a), n - 1)
      b = Math.min(Math.max(a, user.b), n - 1)
    } else if (auto.congested) {
      a = auto.startIndex
      b = auto.endIndex
    }
  }

  // Tell the widget what slice is on screen -- including the automatic one,
  // which the reader never chose, so the transparency pane can say "showing
  // 12 of 48" rather than imply the chart is the whole series.
  const onChange = opts.onChange
  const reported = useRef<string>('')
  // Gone from the page (another chart type, a remount): no window any more.
  const latest = useRef(onChange)
  latest.current = onChange
  useEffect(() => () => { latest.current?.(null) }, [])
  useEffect(() => {
    if (!onChange) return
    const key = show && (a > 0 || b < n - 1) ? `${a}-${b}-${n}-${user ? 'u' : 'a'}` : 'all'
    if (key === reported.current) return
    reported.current = key
    onChange(key === 'all' ? null : {
      start: labels[a] ?? String(a), end: labels[b] ?? String(b), startIndex: a, endIndex: b, of: n,
      ...(user ? {} : { auto: true }),
    })
  }, [onChange, show, a, b, n, labels, user])

  const brush = show
    ? {
        ...brushProps({ ...cfg, overview_axis: true }, { rows, dataKey: opts.dataKey })!,
        startIndex: a,
        endIndex: b,
        onChange: (r: { startIndex?: number; endIndex?: number }) => {
          const na = r?.startIndex ?? 0
          const nb = r?.endIndex ?? n - 1
          setDragged({ sig, a: na, b: nb })
        },
      }
    : null

  return {
    brush,
    /** First and last row index on screen. */
    start: a,
    end: b,
    /** The rows on screen, for anything that is laid out per visible point
     *  (axis labels, per-bar colours, overlays). */
    visible: show ? rows.slice(a, b + 1) : rows,
  }
}
