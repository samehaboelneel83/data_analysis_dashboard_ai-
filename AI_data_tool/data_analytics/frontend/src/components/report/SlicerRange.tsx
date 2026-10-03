import { useEffect, useState } from 'react'
import { useT } from '../../i18n'

export type RangeValue = [number | null, number | null]

/**
 * A number slicer as a from-to range (live check item 12). The server sends
 * the column's min and max (`slicer_range`), never its value list; the reader
 * types either bound or both, and Apply emits one `between` cross-filter.
 * An empty bound is open-ended; both empty clears the filter.
 */
export default function SlicerRange({ data, value, rtl, onApply }: {
  data: { column?: string; min?: number | null; max?: number | null; integer?: boolean; error?: string }
  value: RangeValue | null
  rtl?: boolean
  onApply?: (range: RangeValue | null, column: string) => void
}) {
  const t = useT()
  const col = String(data.column ?? '')
  const [lo, setLo] = useState(value?.[0] != null ? String(value[0]) : '')
  const [hi, setHi] = useState(value?.[1] != null ? String(value[1]) : '')
  // A filter cleared elsewhere (the selection chip, "clear all") empties the boxes.
  useEffect(() => {
    setLo(value?.[0] != null ? String(value[0]) : '')
    setHi(value?.[1] != null ? String(value[1]) : '')
  }, [value?.[0], value?.[1]])

  if (data.error === 'not_numeric') {
    return <div role="status" style={{ padding: 8, fontSize: 12, color: 'var(--muted)' }}>
      {t('slicerRange.notNumeric', { col })}
    </div>
  }

  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  const a = num(lo), b = num(hi)
  const bad = (a != null && !Number.isFinite(a)) || (b != null && !Number.isFinite(b))
  const reversed = a != null && b != null && a > b
  const fmt = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString())
  const step = data.integer ? 1 : 'any'
  const apply = () => {
    if (bad || reversed) return
    onApply?.(a == null && b == null ? null : [a, b], col)
  }
  const box = { width: '100%', minWidth: 0, fontSize: 12, padding: '5px 8px', border: '1px solid var(--border)',
    borderRadius: 6, background: 'var(--surface)', color: 'var(--text)' } as const

  return (
    <form dir={rtl ? 'rtl' : undefined} data-testid="slicer-range"
      onSubmit={e => { e.preventDefault(); apply() }}
      style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input type="number" step={step} aria-label={t('slicerRange.from', { col })} value={lo}
          placeholder={fmt(data.min)} onChange={e => setLo(e.target.value)} style={box} />
        <span aria-hidden="true" style={{ color: 'var(--muted)' }}>–</span>
        <input type="number" step={step} aria-label={t('slicerRange.to', { col })} value={hi}
          placeholder={fmt(data.max)} onChange={e => setHi(e.target.value)} style={box} />
        <button type="submit" className="btn btn-sm" disabled={bad || reversed}>{t('slicerRange.apply')}</button>
      </div>
      <span style={{ fontSize: 10, color: reversed ? 'var(--negative, #e2606c)' : 'var(--muted)' }}>
        {reversed ? t('slicerRange.reversed') : t('slicerRange.hint', { min: fmt(data.min), max: fmt(data.max) })}
      </span>
    </form>
  )
}

/** The chip text for a range: "amount 10 – 50", "amount ≥ 10", "amount ≤ 50". */
export function rangeLabel(col: string, [a, b]: RangeValue): string {
  const f = (v: number) => v.toLocaleString()
  if (a != null && b != null) return `${col} ${f(a)} – ${f(b)}`
  return a != null ? `${col} ≥ ${f(a)}` : `${col} ≤ ${f(b as number)}`
}
