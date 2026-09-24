import { useState, useEffect, useRef } from 'react'
import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin } from './axisOptions'

export default function BubbleChangePlotRenderer({ data, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt, ruleStyles, plotH }: ChartRendererProps) {
  const rawFrames: unknown[] = data?.frames ?? []
  // Playback order: SAS exposes ascending/descending frame order.
  const frames: unknown[] = (cfg.anim_order === 'desc' ? [...rawFrames].reverse() : rawFrames)
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
  // origIndex tracks each row's position in the widget's full, unfiltered result rows --
  // what ruleStyles.rows is indexed by -- since the animation frame filter below leaves
  // only a subset whose local index no longer lines up with that array.
  const rows = allRows
    .map((r, origIndex) => ({ ...r, origIndex }))
    .filter(r => r.frame === currentFrame)
  // Both axes are measures: x is the first, y is the second. The builders'
  // default (the category on x) would name the wrong thing on each.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, measure2Fmt, 'y', rows.length)

  // On-chart animation value, SAS-style: 9 placement positions, text
  // size/style, transparency and an optional contrast box. 'none' (default)
  // keeps the value only in the control bar, exactly as before.
  const animPos: string = cfg.anim_label_position ?? 'none'
  const posStyle: React.CSSProperties = (() => {
    const [v, h] = animPos === 'center' ? ['middle', 'center'] : animPos.split('-')
    const st: React.CSSProperties = { position: 'absolute', zIndex: 1 }
    if (v === 'top') st.top = 8; else if (v === 'bottom') st.bottom = 8
    else { st.top = '50%'; st.transform = 'translateY(-50%)' }
    if (h === 'left') st.left = 12; else if (h === 'right') st.right = 12
    else { st.left = '50%'; st.transform = `${st.transform ?? ''} translateX(-50%)`.trim() }
    return st
  })()

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {animPos !== 'none' && (
          <div data-testid="anim-value-label" style={{
            ...posStyle, pointerEvents: 'none',
            fontSize: Number(cfg.anim_label_size) || 44,
            fontWeight: cfg.anim_label_style === 'normal' ? 400 : 700,
            fontStyle: cfg.anim_label_style === 'italic' ? 'italic' : undefined,
            opacity: cfg.anim_label_opacity != null ? Number(cfg.anim_label_opacity) : 0.25,
            color: 'var(--text)', fontFamily: 'var(--mono)',
            ...(cfg.anim_label_box ? { background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '2px 14px', opacity: cfg.anim_label_opacity != null ? Number(cfg.anim_label_opacity) : 0.85 } : {}),
          }}>
            {String(currentFrame)}
          </div>
        )}
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={chartMargin(rtl, { top: 4, right: 16, bottom: 4, left: 0 })}>
            {grid && <CartesianGrid {...grid} />}
            <XAxis type="number" dataKey="x" {...xAxisProps(cfg, rtl, undefined, undefined, { title: titles.measure })} tickFormatter={v => fmtStr(v, measureFmt)} />
            {/* allowDecimals forced true after the spread: this axis never set it before, so
                Recharts' own default (true) applied, unlike the builder's false default. */}
            <YAxis type="number" dataKey="y" {...yAxisProps(cfg, rtl, measure2Fmt, rows.map((r: any) => r.y), undefined, { height: plotH, title: titles.measure2 })} allowDecimals tickFormatter={v => fmtStr(v, measure2Fmt)} />
            <ZAxis type="number" dataKey="size" range={[60, 600]} />
            <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
              formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
            <Scatter data={rows} name="bubbles"
              onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
              style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            >
              {rows.map((r: any, i: number) => (
                <Cell key={i} fill={ruleStyles?.rows?.[r.origIndex]?.fill ?? COLORS[i % COLORS.length]} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
              ))}
              {labels && <LabelList {...labels} />}
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
