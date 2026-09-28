import { fmtStr, seriesColor } from '../chartUtils'
import type { ChartRendererProps } from './types'

function cellColor(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0.5
  // color-mix over the theme accent, not a baked-in rgb: the scale then
  // follows the product palette in both themes instead of freezing the blue
  // this file was written under.
  const pct = Math.round((0.1 + t * 0.85) * 100)
  return `color-mix(in srgb, ${seriesColor(0)} ${pct}%, transparent)`
}

export default function HeatMapRenderer({ data, rtl, measureFmt, plotH }: ChartRendererProps) {
  const rowsAxis: string[] = data?.rows_axis ?? []
  const colsAxis: string[] = data?.cols_axis ?? []
  const cells: (number | null)[][] = data?.cells ?? []
  const min: number = data?.min ?? 0
  const max: number = data?.max ?? 1

  if (rowsAxis.length === 0 || colsAxis.length === 0) {
    // A result that came back empty is the data's answer, not a setup problem:
    // after a filter left no rows this said "Configure widget to see data",
    // blaming the author (live QA 2026-09-28).
    const answered = data != null && (data.type === 'empty' || data.type === 'heatmap' || data.total === 0)
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>
      {answered ? 'No data for the current selection' : 'Configure widget to see data'}
    </div>
  }

  // Rows share the tile's height, so a 24-hour grid is read at a glance
  // instead of 7 rows and a scrollbar (live QA 2026-09-28). Between 14 and 32
  // px a row; below 18 the figure moves to the cell's tooltip, the colour
  // carrying the reading.
  const HEADER = 24
  const rowH = plotH && plotH > HEADER
    ? Math.max(14, Math.min(32, Math.floor((plotH - HEADER - 8) / rowsAxis.length)))
    : 32
  const showFigures = rowH >= 18

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
              <td style={{ padding: '0 4px', fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap', fontSize: rowH < 18 ? 9.5 : undefined }}>{r}</td>
              {colsAxis.map((c, j) => {
                const v = cells[i]?.[j]
                return (
                  <td key={c} title={v == null ? 'No data' : `${r} × ${c}: ${fmtStr(v, measureFmt)}`}
                    style={{ padding: 0, border: '1px solid var(--border)' }}>
                    <div style={{ background: v == null ? 'var(--surface2)' : cellColor(v, min, max), width: '100%', height: rowH, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--text)' }}>
                      {!showFigures ? null : v == null ? '—' : fmtStr(v, measureFmt)}
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
