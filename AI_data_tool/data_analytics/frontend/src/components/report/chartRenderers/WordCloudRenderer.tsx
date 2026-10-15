import { useT } from '../../../i18n'
import { useEffect, useRef, useState } from 'react'
import cloud from 'd3-cloud'
import { COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'

interface PlacedWord { text: string; size: number; x: number; y: number; rotate: number; fill: string }

/** The font-size scale for a box and a set of words (C-06). The largest size is
 *  capped so the LONGEST word fits the box's width (~0.6 em per character), and
 *  sizes spread from the smallest value to the largest -- not from 0, which
 *  gave ten similar revenue totals the same huge size. */
export function wordSizer(words: { text: string; value: number }[], boxW: number, scale = 1) {
  const values = words.map(w => Math.abs(w.value))
  const maxV = Math.max(...values), minV = Math.min(...values)
  const longest = Math.max(1, ...words.map(w => w.text.length))
  const maxFont = Math.max(8, Math.min(60, boxW / (longest * 0.6)) * scale)
  const minFont = Math.max(8, Math.min(14, maxFont * 0.35))
  return (d: { value: number }) => {
    const t = maxV > minV ? (Math.abs(d.value) - minV) / (maxV - minV) : 0.5
    return minFont + t * (maxFont - minFont)
  }
}

export default function WordCloudRenderer({ rows, onClickPoint, broadcasts, localSelected, plotW, plotH }: ChartRendererProps) {
  const t9 = useT()
  const containerRef = useRef<HTMLDivElement>(null)
  const [observed, setObserved] = useState({ width: 600, height: 400 })
  // The measured plot box when the tile gives one (MeasuredChart); otherwise
  // the container's own size.
  const size = plotW && plotH && plotW > 0 && plotH > 0 ? { width: plotW, height: plotH } : observed
  const [placed, setPlaced] = useState<PlacedWord[]>([])
  const [noneFit, setNoneFit] = useState(false)
  const hasRows = (rows ?? []).length > 0

  // Observe once the container exists: with [] deps this ran while the
  // "configure" branch was showing, found no element, and never attached.
  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setObserved({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasRows])

  useEffect(() => {
    const words = (rows ?? []).filter(r => r.name != null)
      .map(w => ({ text: String(w.name), value: Number(w.value) || 0 }))
    if (words.length === 0) { setPlaced([]); setNoneFit(false); return }
    let cancelled = false
    const run = (scale: number) => {
      cloud()
        .size([size.width, size.height])
        .words(words.map(w => ({ ...w })))
        .padding(3)
        .rotate(() => (Math.random() < 0.7 ? 0 : 90))
        .font('sans-serif')
        .fontSize(wordSizer(words, size.width, scale) as any)
        .on('end', (computed: any[]) => {
          if (cancelled) return
          // d3-cloud silently drops a word it cannot place: try once smaller.
          if (computed.length < words.length && scale === 1) { run(0.7); return }
          setNoneFit(computed.length === 0)
          setPlaced(computed.map((w, i) => ({
            text: w.text ?? '', size: w.size ?? 14, x: w.x ?? 0, y: w.y ?? 0, rotate: w.rotate ?? 0,
            fill: COLORS[i % COLORS.length],
          })))
        })
        .start()
    }
    run(1)
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(rows), size.width, size.height])

  if ((rows ?? []).length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>{t9('cr.configure')}</div>
  }

  return (
    <div ref={containerRef} style={{ height: '100%', width: '100%', overflow: 'hidden', position: 'relative' }}>
      {noneFit && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--muted)', fontSize: 12, padding: 12, textAlign: 'center' }}>{t9('cr.wordsTooLong')}</div>
      )}
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
