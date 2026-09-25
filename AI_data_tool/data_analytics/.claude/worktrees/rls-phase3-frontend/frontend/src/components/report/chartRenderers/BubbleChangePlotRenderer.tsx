import { useState, useEffect, useRef } from 'react'
import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function BubbleChangePlotRenderer({ data, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt }: ChartRendererProps) {
  const frames: unknown[] = data?.frames ?? []
  const allRows: any[] = data?.rows ?? []
  const [frameIdx, setFrameIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!playing || frames.length === 0) return
    timerRef.current = setInterval(() => {
      setFrameIdx(i => (i + 1) % frames.length)
    }, 900)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [playing, frames.length])

  useEffect(() => { setFrameIdx(0); setPlaying(false) }, [frames.length])

  if (frames.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const currentFrame = frames[frameIdx]
  const rows = allRows.filter(r => r.frame === currentFrame)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis type="number" dataKey="x" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
            <YAxis type="number" dataKey="y" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measure2Fmt)} />
            <ZAxis type="number" dataKey="size" range={[60, 600]} />
            <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
              formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
            <Scatter data={rows} name="bubbles"
              onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
              style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            >
              {rows.map((r: any, i: number) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <button className="btn" style={{ padding: '2px 8px', fontSize: 11 }} onClick={() => setPlaying(p => !p)}>{playing ? '⏸' : '▶'}</button>
        <input type="range" min={0} max={frames.length - 1} value={frameIdx}
          onChange={e => { setPlaying(false); setFrameIdx(Number(e.target.value)) }}
          style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 48, textAlign: 'right' }}>{String(currentFrame)}</span>
      </div>
    </div>
  )
}
