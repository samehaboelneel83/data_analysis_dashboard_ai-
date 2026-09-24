import { useState } from 'react'
import { useDirection } from '../../contexts/DirectionContext'
import BarChartRenderer from '../report/chartRenderers/BarChartRenderer'
import LineChartRenderer from '../report/chartRenderers/LineChartRenderer'
import PieChartRenderer from '../report/chartRenderers/PieChartRenderer'
import type { AgentPresentation, AgentResult } from '../../services/api'

/**
 * A sink step's rows, drawn in the chat.
 *
 * The answer used to be prose only: the rows existed for one run on the
 * server and were summarised into a sentence. Now they arrive as a capped
 * snapshot (`AgentResult`) and are drawn as a grid, or -- when the run was a
 * presentation follow-up ("as a bar chart") -- through the same chart
 * renderers the dashboards use, so a chart in the chat looks like a chart on
 * a report. A chart keeps its rows one click away.
 */

type Cell = string | number | boolean | null

const isNumberish = (v: Cell) =>
  typeof v === 'number' || (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v)))

/**
 * A cell as text, without the binary-float noise.
 *
 * A summed currency column arrives as 2010526.4600000004 -- IEEE-754's honest
 * answer to adding .46 a few hundred times, and a number nobody reads as a
 * total. 12 significant digits sits well inside a double's ~15-17 and well
 * outside where that artefact lives, so rounding there drops the tail without
 * altering a value anyone actually typed.
 *
 * Deliberately no thousands separators: this grid shows whatever columns the
 * question returned, ids included, and "2,024" for a year is its own wrong.
 */
export const cellText = (v: Cell): string => {
  if (v == null) return ''
  if (typeof v !== 'number' || !Number.isFinite(v) || Number.isInteger(v)) return String(v)
  return String(Number.parseFloat(v.toPrecision(12)))
}

/** `{name, value}` rows for the chart renderers: the first non-numeric
 *  column names the mark, the first numeric column sizes it. A result with
 *  only one column is drawn as a count of itself.
 *
 *  When EVERY column is numeric there is no label column, so the first one
 *  labels the marks -- and the value must then come from a LATER column.
 *  Without that second condition `i !== nameIdx` was `i !== -1`, true for
 *  every column, so column 0 was both the label and the height: an all-numeric
 *  result charted its id against itself, ten bars ~720 tall labelled 718-727.
 *  Seen in a screenshot, not in a test. */
/** The two columns a chart of this result draws: the server's choice when it
 *  made one, otherwise the same heuristic `chartRows` falls back to. Exported
 *  so the axes can be TITLED with them -- a chart whose axes are unnamed
 *  leaves the reader guessing which columns they are looking at. */
export function chartColumns(result: AgentResult, x?: string | null, y?: string | null):
  { x?: string; y?: string } {
  const { columns, rows } = result
  if (columns.length === 0 || rows.length === 0) return {}
  if (x && y && columns.includes(x) && columns.includes(y)) return { x, y }
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  const nameIdx = numeric.findIndex(n => !n)
  const valueIdx = columns.findIndex(
    (_, i) => numeric[i] && i !== nameIdx && (nameIdx >= 0 || i !== 0))
  return {
    x: columns[nameIdx >= 0 ? nameIdx : 0],
    y: valueIdx >= 0 ? columns[valueIdx] : undefined,
  }
}

export function chartRows(result: AgentResult, x?: string | null, y?: string | null):
  { name: string; value: number }[] {
  const { columns, rows } = result
  if (columns.length === 0 || rows.length === 0) return []
  // Named axes win. The server settles them on the rows themselves
  // (services/agent/charts.py) and asks the person when they are not
  // settled, so when it says which two columns to use, that IS the chart --
  // re-deciding here would be a second opinion nobody asked for.
  const namedX = x ? columns.indexOf(x) : -1
  const namedY = y ? columns.indexOf(y) : -1
  if (namedX >= 0 && namedY >= 0) {
    return rows.map(r => ({ name: String(r[namedX] ?? ''), value: Number(r[namedY] ?? 0) }))
  }
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  const nameIdx = numeric.findIndex(n => !n)
  const valueIdx = columns.findIndex(
    (_, i) => numeric[i] && i !== nameIdx && (nameIdx >= 0 || i !== 0))
  return rows.map((r, i) => ({
    name: nameIdx >= 0 ? String(r[nameIdx] ?? '') : String(r[0] ?? i + 1),
    value: valueIdx >= 0 ? Number(r[valueIdx] ?? 0) : 1,
  }))
}

/** RFC 4180 rows, CRLF-terminated, with a byte-order mark so Excel reads
 *  UTF-8 (Arabic cells otherwise open as mojibake). */
export function toCsv(results: AgentResult[]): string {
  // Same text the grid shows: an export that disagrees with the screen sends
  // the reader hunting for which one is the real number.
  const cell = (v: Cell) => {
    const s = cellText(v)
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const blocks = results.map(r =>
    [r.columns, ...r.rows].map(row => row.map(cell).join(',')).join('\r\n') + '\r\n')
  return '﻿' + blocks.join('\r\n')
}

export function downloadCsv(results: AgentResult[], filename: string) {
  const blob = new Blob([toCsv(results)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function Caption({ result }: { result: AgentResult }) {
  const shown = result.rows.length
  const partial = result.truncated || shown < result.total
  return (
    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
      {partial ? `${result.total} rows, showing ${shown}` : `${result.total} rows`}
      {/* A grid that no query produced says so. These rows are real -- they
          are this workspace's own catalog -- but "rows with no SQL behind
          them" is precisely what a made-up answer looks like, and the reader
          should never have to tell the two apart by instinct. */}
      {result.source === 'catalog' && ' · from the data catalog, not a query'}
    </span>
  )
}

export function ResultGrid({ result }: { result: AgentResult }) {
  if (result.total === 0 || result.columns.length === 0) {
    return <span style={{ fontSize: 12, color: 'var(--muted)' }}>No rows.</span>
  }
  return (
    <div>
      <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid var(--border)',
        borderRadius: 6, background: 'var(--surface)' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              {result.columns.map(c => (
                <th key={c} style={{ position: 'sticky', top: 0, background: 'var(--surface2)',
                  textAlign: 'start', padding: '5px 8px', fontWeight: 600, fontSize: 11,
                  color: 'var(--muted)', borderBottom: '1px solid var(--border)',
                  whiteSpace: 'nowrap' }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => (
                  <td key={j} style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)',
                    whiteSpace: 'nowrap', textAlign: typeof v === 'number' ? 'end' : 'start',
                    fontVariantNumeric: 'tabular-nums' }}>
                    {cellText(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 4 }}><Caption result={result} /></div>
    </div>
  )
}

function ResultChart({ result, format, x, y }: {
  result: AgentResult
  format: 'bar' | 'line' | 'pie'
  x?: string | null
  y?: string | null
}) {
  const { rtl } = useDirection()
  const rows = chartRows(result, x, y)
  const axes = chartColumns(result, x, y)
  const Renderer = format === 'bar' ? BarChartRenderer : format === 'line' ? LineChartRenderer : PieChartRenderer
  return (
    <div data-testid="result-chart" data-format={format}
      style={{ height: 240, width: '100%', minWidth: 280 }}>
      {/* The chat has no widget config to derive titles from, so it names the
          axes outright with the two columns it is actually drawing. The rows
          are `{name, value}` by then -- without this the axes would read
          "name" and "value", which say nothing about this data. */}
      <Renderer rows={rows} data={{ rows }} rtl={rtl} broadcasts={false}
        cfg={{ x_axis_label: axes.x, y_axis_label: axes.y }}
        localSelected={null} onClickPoint={() => {}} />
    </div>
  )
}

export default function ResultView({ results, presentation }: {
  results: AgentResult[]
  presentation?: AgentPresentation | null
}) {
  const [rowsOpen, setRowsOpen] = useState(false)
  const format = presentation?.format
  const chartable = (format === 'bar' || format === 'line' || format === 'pie') ? format : null
  return (
    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {results.map((r, i) => (
        <div key={`${r.step}-${i}`}>
          {chartable && r.total > 0 ? (
            <>
              <ResultChart result={r} format={chartable}
                x={presentation?.x} y={presentation?.y} />
              <button onClick={() => setRowsOpen(o => !o)}
                style={{ background: 'none', border: 'none', padding: 0, marginTop: 4,
                  color: 'var(--accent)', cursor: 'pointer', fontSize: 12 }}>
                {rowsOpen ? 'Hide rows' : 'Show rows'}
              </button>
              {rowsOpen && <ResultGrid result={r} />}
            </>
          ) : (
            <ResultGrid result={r} />
          )}
        </div>
      ))}
    </div>
  )
}
