import type { CalcColumnFormat } from '../../services/api'
import { fmtStr } from './chartUtils'

/** The nested crosstab the server returns as `type: 'pivot'`
 *  (backend services/pivot.py). */
export interface PivotData {
  type: 'pivot'
  row_fields: string[]
  column_fields: string[]
  measures: string[]
  aggregation?: string
  column_keys: unknown[][]
  rows: { keys: unknown[]; values: (number | null)[] }[]
}

const label = (v: unknown) => (v === null || v === undefined || v === '' ? '(blank)' : String(v))

/** How many consecutive entries share the first `depth + 1` keys, from each
 *  index: the colspan / rowspan of a group header, 0 where it is covered. */
export function spans(keys: unknown[][], depth: number): number[] {
  const out = new Array(keys.length).fill(0)
  let i = 0
  while (i < keys.length) {
    let j = i + 1
    const same = (a: unknown[], b: unknown[]) => a.slice(0, depth + 1).every((v, k) => v === b[k])
    while (j < keys.length && same(keys[i], keys[j])) j++
    out[i] = j - i
    i = j
  }
  return out
}

/**
 * Rows down the side, each level its own column with repeated labels merged
 * (Continent spans its countries); columns across the top, each level its
 * own header row (Product Line spans its categories), and under them one
 * header per measure. An empty cell -- no rows there -- is a dash, never 0.
 */
export default function PivotTable({ data, rtl, formats }: {
  data: PivotData
  rtl?: boolean
  formats?: Record<string, CalcColumnFormat | undefined>
}) {
  const { row_fields: rowF, column_fields: colF, measures, column_keys: colKeys, rows } = data
  const m = measures.length
  const rowKeys = rows.map(r => r.keys)
  const rowSpans = rowF.map((_, d) => spans(rowKeys, d))
  const th: React.CSSProperties = {
    padding: '4px 8px', fontWeight: 600, fontSize: 11.5, whiteSpace: 'nowrap', textAlign: 'center',
    borderBottom: '1px solid var(--border)', background: 'var(--surface)', position: 'sticky', zIndex: 1,
  }
  const td: React.CSSProperties = { padding: '3px 8px', fontSize: 12, borderBottom: '1px solid var(--dl-table-rule, var(--border))' }
  const headerRows = colF.length + 1
  return (
    <div style={{ overflow: 'auto', height: '100%' }} dir={rtl ? 'rtl' : undefined} data-testid="pivot-table">
      <table style={{ borderCollapse: 'separate', borderSpacing: 0, minWidth: '100%', fontVariantNumeric: 'tabular-nums' }}>
        <thead>
          {colF.map((f, d) => {
            const s = spans(colKeys, d)
            return (
              <tr key={f}>
                {d === 0 && rowF.map((rf, i) => (
                  <th key={rf} rowSpan={headerRows} scope="col"
                    style={{ ...th, top: 0, textAlign: 'start', verticalAlign: 'bottom', borderInlineEnd: i === rowF.length - 1 ? '1px solid var(--border)' : undefined }}>
                    {rf}
                  </th>
                ))}
                {colKeys.map((ck, i) => s[i] > 0 && (
                  <th key={i} colSpan={s[i] * m} scope="colgroup" title={`${f}: ${label(ck[d])}`}
                    style={{ ...th, top: d * 24, fontWeight: d === colF.length - 1 ? 600 : 500, color: 'var(--muted)' }}>
                    {label(ck[d])}
                  </th>
                ))}
              </tr>
            )
          })}
          <tr>
            {colF.length === 0 && rowF.map((rf, i) => (
              <th key={rf} scope="col" style={{ ...th, top: 0, textAlign: 'start',
                borderInlineEnd: i === rowF.length - 1 ? '1px solid var(--border)' : undefined }}>{rf}</th>
            ))}
            {colKeys.flatMap((_, i) => measures.map(mn => (
              <th key={`${i}-${mn}`} scope="col" style={{ ...th, top: colF.length * 24, textAlign: 'end' }}>{mn}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {rowF.map((_, d) => rowSpans[d][ri] > 0 && (
                <th key={d} scope="row" rowSpan={rowSpans[d][ri]}
                  style={{ ...td, fontWeight: d === rowF.length - 1 ? 500 : 600, textAlign: 'start', verticalAlign: 'top',
                    whiteSpace: 'nowrap', borderInlineEnd: d === rowF.length - 1 ? '1px solid var(--border)' : undefined }}>
                  {label(r.keys[d])}
                </th>
              ))}
              {r.values.map((v, vi) => {
                const mn = measures[vi % m]
                return (
                  <td key={vi} style={{ ...td, textAlign: 'end', whiteSpace: 'nowrap', color: v == null ? 'var(--muted)' : undefined }}>
                    {v == null ? '—' : fmtStr(v, formats?.[mn])}
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
