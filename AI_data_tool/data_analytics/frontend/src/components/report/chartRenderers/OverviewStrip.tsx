import { useEffect, useMemo, useRef, useState } from 'react'
import { Brush, LineChart, ResponsiveContainer, XAxis } from 'recharts'
import { brushProps } from './axisOptions'

/**
 * The smart slider: an overview of the WHOLE series (the server's coarse,
 * auto-binned rows) with a draggable window.
 *
 * Dragging moves the window at once -- the chart above shows the coarse rows
 * inside it straight away, so panning feels instant. When the reader lets go,
 * `onCommit` fires and the widget asks the server for the window again, at a
 * finer grain (week -> day -> hour, or narrower number ranges). The overview
 * itself never changes while zoomed, so the reader always sees where the
 * window sits in the whole.
 */

export interface StripRow { name?: unknown; value?: unknown; bin_start?: unknown; bin_end?: unknown }

/** How long the window must rest before the finer rows are fetched. Recharts
 *  fires onChange on every pointer move; one request per drag, not per pixel. */
export const COMMIT_DELAY_MS = 350

export default function OverviewStrip({ rows, start, end, onChange, onCommit, resetNonce }: {
  rows: StripRow[]
  start: number
  end: number
  onChange: (a: number, b: number) => void
  onCommit: (a: number, b: number) => void
  /** Bumped to put the window back over the whole series. */
  resetNonce?: number
}) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
  // Remount the Brush on reset: it keeps its own drag state otherwise.
  const [key, setKey] = useState(0)
  useEffect(() => { if (resetNonce) setKey(k => k + 1) }, [resetNonce])

  const props = useMemo(
    () => brushProps({ overview_axis: true } as never, { rows: rows as Record<string, unknown>[], dataKey: 'value' }),
    [rows])
  if (!props || rows.length < 2) return null
  return (
    <div data-testid="overview-strip" style={{ height: 34, flexShrink: 0 }}
      title="Drag the handles to zoom. The chart shows more detail for the part you pick.">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows as Record<string, unknown>[]} margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
          <XAxis dataKey="name" hide />
          <Brush key={key} {...props} y={2} height={30} startIndex={start} endIndex={end}
            onChange={(r: { startIndex?: number; endIndex?: number }) => {
              const a = r?.startIndex ?? 0
              const b = r?.endIndex ?? rows.length - 1
              onChange(a, b)
              if (timer.current) clearTimeout(timer.current)
              timer.current = setTimeout(() => onCommit(a, b), COMMIT_DELAY_MS)
            }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
