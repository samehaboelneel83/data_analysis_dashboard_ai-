import type { ChartRendererProps } from './types'

// Diverging color scale: strong negative -> red, 0 -> neutral surface, strong positive -> accent blue.
function cellColor(v: number): string {
  const t = Math.max(-1, Math.min(1, v))
  if (t >= 0) {
    // Theme accent, not a baked-in rgb -- the positive side of the scale
    // follows the product palette in both themes.
    const pct = Math.round((0.12 + t * 0.75) * 100)
    return `color-mix(in srgb, var(--accent) ${pct}%, transparent)`
  }
  const alpha = 0.12 + -t * 0.75
  return `rgba(248,113,113,${alpha})`
}

export default function CorrelationMatrixRenderer({ data, rtl }: ChartRendererProps) {
  const measures: string[] = data?.measures ?? []
  const matrix: number[][] = data?.matrix ?? []

  if (measures.length < 2) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Select at least 2 measures</div>
  }

  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', padding: 4 }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {measures.map(m => (
              <th key={m} style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxHeight: 90 }}>{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {measures.map((rowMeasure, i) => (
            <tr key={rowMeasure}>
              <td style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{rowMeasure}</td>
              {measures.map((colMeasure, j) => {
                const v = matrix[i]?.[j] ?? 0
                return (
                  <td key={colMeasure} title={`${rowMeasure} × ${colMeasure}: ${v.toFixed(3)}`}
                    style={{ padding: 0, border: '1px solid var(--border)' }}>
                    <div style={{ background: cellColor(v), width: '100%', height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--text)' }}>
                      {v.toFixed(2)}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
