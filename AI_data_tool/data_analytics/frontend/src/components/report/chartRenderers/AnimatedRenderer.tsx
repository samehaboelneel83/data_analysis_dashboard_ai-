import { useEffect, useState, type ComponentType } from 'react'
import type { ChartRendererProps } from './types'
import { MeasuredChart } from '../MeasuredChart'

/** Chart types with an animation role — must match ANIMATION_TYPES in widget_data.py. */
export const ANIMATION_WIDGETS = ['bar', 'line', 'area', 'scatter', 'step', 'dot_plot', 'pie', 'donut'] as const
export const FRAME_MS = 1200

interface Frame { label: string; result: any }

/**
 * Plays the widget's chart through an ordered field (a date, a year, a
 * version): one frame per value, a play/pause button and a scrubber. Every
 * frame is drawn on ONE value axis (the server's `domain`) so a bar visibly
 * grows or shrinks; an axis that rescaled each frame would make every frame
 * look the same size. Stops on the last frame rather than looping, so the
 * reader is left on the latest state, not an arbitrary one.
 */
export default function AnimatedRenderer({ Inner, props, onFrame }: {
  Inner: ComponentType<ChartRendererProps>
  props: ChartRendererProps
  onFrame?: (label: string | null) => void
}) {
  const data = props.data
  const frames: Frame[] = data.frames ?? []
  const [idx, setIdx] = useState(Math.max(0, frames.length - 1))
  const [playing, setPlaying] = useState(false)
  useEffect(() => { setIdx(Math.max(0, frames.length - 1)); setPlaying(false) }, [frames.length])
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      setIdx(i => {
        if (i >= frames.length - 1) { setPlaying(false); return i }
        return i + 1
      })
    }, FRAME_MS)
    return () => clearInterval(t)
  }, [playing, frames.length])
  const frame = frames[idx]
  useEffect(() => { onFrame?.(frame?.label ?? null) }, [frame?.label])  // eslint-disable-line react-hooks/exhaustive-deps

  const own = props.cfg ?? {}
  const domain: [number, number] | null = data.domain ?? null
  const cfg = { ...own, ...(domain && own.y_min === undefined && own.y_max === undefined
    ? { y_min: domain[0], y_max: domain[1] } : {}) }
  if (!frame) return <div style={{ color: 'var(--muted)', fontSize: 12, padding: 8 }}>No data.</div>
  const res = frame.result ?? {}
  return (
    <div data-testid="animated" style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 4px 4px' }}>
        <button className="btn" data-testid="anim-play" aria-label={playing ? 'Pause' : 'Play'}
          style={{ padding: '1px 8px', fontSize: 11 }}
          onClick={() => {
            if (!playing && idx >= frames.length - 1) setIdx(0)   // replay from the start
            setPlaying(p => !p)
          }}>{playing ? '⏸' : '▶'}</button>
        <input type="range" aria-label={`${data.animate_by} frame`} min={0} max={frames.length - 1} value={idx}
          onChange={e => { setPlaying(false); setIdx(Number(e.target.value)) }} style={{ flex: 1 }} />
        <span data-testid="anim-label" aria-live="polite" dir="auto"
          style={{ fontSize: 12, fontWeight: 600, minWidth: 70, textAlign: 'end' }}>{frame.label}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {res.type === 'empty' || !(res.rows?.length)
          ? <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, color: 'var(--muted)' }}>No rows in {frame.label}</div>
          : <MeasuredChart>{(w, h) => (
              <Inner {...props} data={res} rows={res.rows ?? []} cfg={cfg} plotW={w} plotH={h} />
            )}</MeasuredChart>}
      </div>
      <div style={{ fontSize: 10, color: 'var(--muted)', padding: '2px 4px' }}>
        {frames.length} frames by {data.animate_by}{data.granularity ? ` (${data.granularity})` : ''} · one axis for every frame
        {data.animation_truncation?.text ? ` · ${data.animation_truncation.text}` : ''}
      </div>
    </div>
  )
}
