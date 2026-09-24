import { useEffect, useRef, useState } from 'react'
import cloud from 'd3-cloud'
import { COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'

interface PlacedWord { text: string; size: number; x: number; y: number; rotate: number; fill: string }

export default function WordCloudRenderer({ rows, onClickPoint, broadcasts, localSelected }: ChartRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 600, height: 400 })
  const [placed, setPlaced] = useState<PlacedWord[]>([])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setSize({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const words = (rows ?? []).filter(r => r.name != null)
    if (words.length === 0) { setPlaced([]); return }
    const values = words.map(w => Math.abs(Number(w.value) || 0))
    const maxV = Math.max(...values, 1)
    const minV = Math.min(...values, 0)
    const scaleSize = (v: number) => {
      const t = maxV > minV ? (Math.abs(v) - minV) / (maxV - minV) : 0.5
      return 14 + t * 46
    }
    let cancelled = false
    const layout = cloud()
      .size([size.width, size.height])
      .words(words.map(w => ({ text: String(w.name), value: Number(w.value) || 0 })))
      .padding(3)
      .rotate(() => (Math.random() < 0.7 ? 0 : 90))
      .font('sans-serif')
      .fontSize((d: any) => scaleSize(d.value))
      .on('end', (computed: any[]) => {
        if (cancelled) return
        setPlaced(computed.map((w, i) => ({
          text: w.text ?? '', size: w.size ?? 14, x: w.x ?? 0, y: w.y ?? 0, rotate: w.rotate ?? 0,
          fill: COLORS[i % COLORS.length],
        })))
      })
    layout.start()
    return () => { cancelled = true }
  }, [JSON.stringify(rows), size.width, size.height])

  if ((rows ?? []).length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  return (
    <div ref={containerRef} style={{ height: '100%', width: '100%', overflow: 'hidden' }}>
      <svg width={size.width} height={size.height}>
        <g transform={`translate(${size.width / 2},${size.height / 2})`}>
          {placed.map((w, i) => (
            <text key={i} textAnchor="middle"
              transform={`translate(${w.x},${w.y}) rotate(${w.rotate})`}
              style={{ fontSize: w.size, fontFamily: 'sans-serif', fill: w.fill, cursor: 'pointer',
                opacity: !broadcasts || localSelected === null || localSelected === w.text ? 1 : 0.35 }}
              onClick={() => onClickPoint(w.text)}>
              {w.text}
            </text>
          ))}
        </g>
      </svg>
    </div>
  )
}
