import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

function cellColor(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0.5
  const alpha = 0.1 + t * 0.85
  return `rgba(108,143,255,${alpha})`
}

export default function HeatMapRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const rowsAxis: string[] = data?.rows_axis ?? []
  const colsAxis: string[] = data?.cols_axis ?? []
  const cells: (number | null)[][] = data?.cells ?? []
  const min: number = data?.min ?? 0
  const max: number = data?.max ?? 1

  if (rowsAxis.length === 0 || colsAxis.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', padding: 4 }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {colsAxis.map(c => (
              <th key={c} style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowsAxis.map((r, i) => (
            <tr key={r}>
              <td style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{r}</td>
              {colsAxis.map((c, j) => {
                const v = cells[i]?.[j]
                return (
                  <td key={c} title={v == null ? 'No data' : `${r} × ${c}: ${fmtStr(v, measureFmt)}`}
                    style={{ padding: 0, border: '1px solid var(--border)' }}>
                    <div style={{ background: v == null ? 'var(--surface2)' : cellColor(v, min, max), width: '100%', height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--text)' }}>
                      {v == null ? '—' : fmtStr(v, measureFmt)}
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
