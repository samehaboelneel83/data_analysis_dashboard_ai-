// Reshapes shape_series's crosstab output ({ type: 'crosstab', columns: [dim, ...series, '__total__'],
// rows: [[dimValue, ...seriesValues, total], ...] }) into recharts' wide-object format for a
// multi-series (clustered/stacked/100%-stacked) bar chart. Non-crosstab data (a plain single-series
// bar) returns no series, leaving the renderer's existing single-<Bar> path untouched.
export function toBarSeries(data: any, mode: string): { rows: Record<string, unknown>[]; series: string[] } {
  if (!data || data.type !== 'crosstab') return { rows: [], series: [] }
  const cols: string[] = data.columns ?? []
  const seriesCols = cols.slice(1, -1)
  const rawRows: any[][] = data.rows ?? []
  const wideRows = rawRows.map(r => {
    const obj: Record<string, unknown> = { name: r[0] }
    seriesCols.forEach((c, i) => { obj[c] = r[i + 1] })
    return obj
  })
  if (mode === 'stacked100') {
    const normalizedRows = wideRows.map(row => {
      const total = seriesCols.reduce((sum, c) => sum + (Number(row[c]) || 0), 0)
      const normalized: Record<string, unknown> = { name: row.name }
      seriesCols.forEach(c => { normalized[c] = total > 0 ? (Number(row[c]) || 0) / total * 100 : 0 })
      return normalized
    })
    return { rows: normalizedRows, series: seriesCols }
  }
  return { rows: wideRows, series: seriesCols }
}
