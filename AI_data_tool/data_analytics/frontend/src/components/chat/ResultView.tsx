import { useState } from 'react'
import { useDirection } from '../../contexts/DirectionContext'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
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
  // On a phone, value labels over each bar collide; the axis and the rows
  // under the chart carry the numbers there instead.
  const narrow = typeof window !== 'undefined' && !!window.matchMedia?.('(max-width: 560px)').matches
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
        cfg={{ x_axis_label: axes.x, y_axis_label: axes.y, ...(narrow ? { data_labels: false } : {}) }}
        localSelected={null} onClickPoint={() => {}} />
    </div>
  )
}

/** What to draw when the server did not ask for a particular chart.
 *  Only shapes that read unambiguously get a chart: one number is a KPI;
 *  a label column with one numeric column and 2-24 rows is a bar chart, or a
 *  line when the labels are dates. Everything else stays a grid. */
export function autoChart(result: AgentResult): 'kpi' | 'bar' | 'line' | null {
  const { columns, rows } = result
  if (!columns.length || !rows.length) return null
  // A partial result would chart as if it were the whole answer; show the grid.
  if (result.truncated || rows.length < (Number(result.total) || 0)) return null
  if (columns.length === 1 && rows.length === 1 && isNumberish(rows[0][0])) return 'kpi'
  if (rows.length < 2 || rows.length > 24) return null
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  const nameIdx = numeric.findIndex(n => !n)
  const valueIdx = numeric.findIndex((n, i) => n && i !== nameIdx)
  if (nameIdx < 0 || valueIdx < 0) return null
  const dated = rows.every(r => typeof r[nameIdx] === 'string' && /^\d{4}-\d{2}/.test(r[nameIdx] as string))
  return dated ? 'line' : 'bar'
}

function Kpi({ result }: { result: AgentResult }) {
  const v = Number(result.rows[0][0])
  const shown = Number.isInteger(v) ? v.toLocaleString('en-US')
    : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return (
    <div className="dl-kpi" data-testid="result-kpi">
      <span className="dl-kpi__label">{result.columns[0].replace(/_/g, ' ')}</span>
      <span className="dl-kpi__value" dir="ltr">{localDigits(shown)}</span>
    </div>
  )
}

export default function ResultView({ results, presentation }: {
  results: AgentResult[]
  presentation?: AgentPresentation | null
}) {
  const t = useT()
  const [rowsOpen, setRowsOpen] = useState(false)
  const format = presentation?.format
  const chartable = (format === 'bar' || format === 'line' || format === 'pie') ? format : null
  return (
    <div className="dl-result">
      {results.map((r, i) => {
        const auto = chartable ? null : autoChart(r)
        const drawn = chartable ?? (auto === 'bar' || auto === 'line' ? auto : null)
        const showChart = !!drawn && r.total > 0
        return (
          <div key={`${r.step}-${i}`}>
            {auto === 'kpi' && <Kpi result={r} />}
            {showChart ? (
              <>
                <div className="dl-result__chart">
                  <ResultChart result={r} format={drawn!}
                    x={presentation?.x} y={presentation?.y} />
                </div>
                <button type="button" className="dl-result__rows-toggle" aria-expanded={rowsOpen}
                  onClick={() => setRowsOpen(o => !o)}>
                  {rowsOpen ? t('ask.hideRows') : t('ask.showRows', { n: localDigits(String(r.total)) })}
                </button>
                {rowsOpen && <ResultGrid result={r} />}
              </>
            ) : auto === 'kpi' ? null : (
              <ResultGrid result={r} />
            )}
          </div>
        )
      })}
    </div>
  )
}
