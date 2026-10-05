import { useEffect, useRef, useState } from 'react'
import { useDirection } from '../../contexts/DirectionContext'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { formatCell } from '../../lib/displayNumber'
import BarChartRenderer from '../report/chartRenderers/BarChartRenderer'
import LineChartRenderer from '../report/chartRenderers/LineChartRenderer'
import PieChartRenderer from '../report/chartRenderers/PieChartRenderer'
import type { AgentPresentation, AgentResult, EvidenceClaim } from '../../services/api'
import './answerEvidence.css'

/**
 * A sink step's rows, drawn in the chat.
 *
 * The answer used to be prose only: the rows existed for one run on the
 * server and were summarised into a sentence. Now they arrive as a capped
 * snapshot (`AgentResult`) and are drawn through the same chart renderers the
 * dashboards use, so a chart in the chat looks like a chart on a report: the
 * chart the server asked for (a presentation follow-up, "as a bar chart"), or
 * else the one `autoChart` picks for an unambiguous shape -- one number is a
 * KPI, a label column with a measure is a bar (a line for dates), including a
 * label column of numeric-looking codes. Any other shape is a grid. A chart
 * keeps its rows one click away.
 */

type Cell = string | number | boolean | null

/** Where an answer's number came from, to point at in the grid (E11): the
 *  result, its rows (none for a whole-column figure: a total, an average)
 *  and its column (none for a row count). `seq` re-fires the same target. */
export interface EvidenceFocus {
  result: number
  rows: number[]
  column: string | null
  seq: number
}

/** Where to point for a traced number of an answer; `seq` follows `prev` so
 *  selecting the same number again scrolls to it again. */
export function focusFor(claim: EvidenceClaim, prev?: EvidenceFocus | null): EvidenceFocus | null {
  const s = claim.source
  if (!s) return null
  return { result: s.result, rows: s.rows ?? (s.row != null ? [s.row] : []),
           column: s.column, seq: (prev?.seq ?? 0) + 1 }
}

const isNumberish = (v: Cell) =>
  typeof v === 'number' || (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v)))

/**
 * A cell as the grid shows it: non-integer floats at most 2 dp (3 significant
 * digits below 1), so neither 2010526.4600000004 -- IEEE-754's honest answer
 * to adding .46 a few hundred times -- nor an average like 83.8883333333
 * reaches the reader. See `formatCell`.
 *
 * Deliberately no thousands separators: this grid shows whatever columns the
 * question returned, ids included, and "2,024" for a year is its own wrong.
 */
export const cellText = (v: Cell): string => formatCell(v)

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
/** 5.x (found in the Chrome re-test): "leavers per department" returned
 *  dept_no AND dept_name, and the chart labelled its bars d001…d009. When two
 *  text columns pair one-to-one and the first holds codes, the name labels the
 *  bars. Otherwise the first text column, as before. */
function labelIndex(columns: string[], rows: Cell[][], numeric: boolean[]): number {
  const text = numeric.map((n, i) => (n ? -1 : i)).filter(i => i >= 0)
  if (text.length < 2) return text[0] ?? -1
  const [a, b] = text
  const codeLike = (v: Cell) => typeof v === 'string' && v.length <= 6 && !/\s/.test(v) && /\d/.test(v)
  const pairs = new Map<string, string>()
  for (const r of rows) {
    const k = String(r[a] ?? ''), v = String(r[b] ?? '')
    if (pairs.has(k) && pairs.get(k) !== v) return a
    pairs.set(k, v)
  }
  const oneToOne = new Set(pairs.values()).size === pairs.size
  return oneToOne && rows.every(r => codeLike(r[a])) && !rows.every(r => codeLike(r[b])) ? b : a
}

export function chartColumns(result: AgentResult, x?: string | null, y?: string | null):
  { x?: string; y?: string } {
  const { columns, rows } = result
  if (columns.length === 0 || rows.length === 0) return {}
  if (x && y && columns.includes(x) && columns.includes(y)) return { x, y }
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  const nameIdx = labelIndex(columns, rows, numeric)
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
  const nameIdx = labelIndex(columns, rows, numeric)
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
  // Exports carry raw values at full precision; the screen rounds for reading.
  const cell = (v: Cell) => {
    const s = v == null ? '' : String(v)
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

export function ResultGrid({ result, focus }: {
  result: AgentResult
  focus?: Omit<EvidenceFocus, 'result'> | null
}) {
  const box = useRef<HTMLDivElement>(null)
  const col = focus?.column != null ? result.columns.indexOf(focus.column) : -1
  const marked = (i: number, j: number) => !!focus && j === col
    && (focus.rows.length === 0 || focus.rows.includes(i))
  useEffect(() => {
    if (!focus) return
    const hit = box.current?.querySelector<HTMLElement>('[data-evidence-focus]')
    hit?.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
  }, [focus])
  if (result.total === 0 || result.columns.length === 0) {
    return <span style={{ fontSize: 12, color: 'var(--muted)' }}>No rows.</span>
  }
  return (
    <div>
      <div ref={box} style={{ maxHeight: 260, overflow: 'auto', border: '1px solid var(--border)',
        borderRadius: 6, background: 'var(--surface)' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              {result.columns.map((c, j) => (
                <th key={c} className={focus && j === col ? 'dl-cell--evidence' : undefined} style={{ position: 'sticky', top: 0, background: 'var(--surface2)',
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
                  <td key={j}
                    className={marked(i, j) ? 'dl-cell--evidence' : undefined}
                    data-evidence-focus={marked(i, j) && (focus!.rows.length === 0 ? i === 0 : i === focus!.rows[0]) ? '' : undefined}
                    style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)',
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
      <div style={{ marginTop: 4 }}
        className={focus && col < 0 ? 'dl-cell--evidence' : undefined}
        data-evidence-focus={focus && col < 0 ? '' : undefined}><Caption result={result} /></div>
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
  // The server's named axes win; with none, a two-label result is grouped.
  const grouped = format === 'bar' && !(x && y) ? groupedBars(result) : null
  const rows = chartRows(result, x, y)
  const axes = grouped ? { x: grouped.x, y: grouped.y } : chartColumns(result, x, y)
  const data = grouped ? { type: 'crosstab', columns: grouped.columns, rows: grouped.rows } : { rows }
  const Renderer = format === 'bar' ? BarChartRenderer : format === 'line' ? LineChartRenderer : PieChartRenderer
  return (
    <div data-testid="result-chart" data-format={format} data-grouped={grouped ? grouped.series : undefined}
      style={{ height: 240, width: '100%', minWidth: 280 }}>
      {/* The chat has no widget config to derive titles from, so it names the
          axes outright with the two columns it is actually drawing. The rows
          are `{name, value}` by then -- without this the axes would read
          "name" and "value", which say nothing about this data. */}
      <Renderer rows={rows} data={data} rtl={rtl} broadcasts={false}
        cfg={{ x_axis_label: axes.x, y_axis_label: axes.y,
          // 5.13: long category names ("Assistant Engineer", department
          // names) clip with "…" like the Suggestions preview, instead of
          // tilting into the chart; the full name is in the tooltip.
          axis_tick_max_chars: 14, labels_compact: true,
          ...(grouped ? { bar_mode: 'clustered', legend_title: grouped.series } : {}), ...(narrow ? { data_labels: false } : {}) }}
        localSelected={null} onClickPoint={() => {}} />
    </div>
  )
}

/** Two label columns and a measure ("title, gender, avg_salary") read as a
 *  grouped bar chart: the first label is the axis, the second the series.
 *  Charting it as plain bars drew every title twice with no way to tell the
 *  genders apart. Returns the crosstab the bar renderer draws, or null when
 *  the result is not that shape (or would be too many bars to read). */
export function groupedBars(result: AgentResult):
  { columns: string[]; rows: Cell[][]; x: string; series: string; y: string } | null {
  const { columns, rows } = result
  if (columns.length < 3 || rows.length < 2) return null
  if (result.truncated || rows.length < (Number(result.total) || 0)) return null
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  const labels = numeric.map((n, i) => (n ? -1 : i)).filter(i => i >= 0)
  const valueIdx = numeric.findIndex(n => n)
  if (labels.length !== 2 || valueIdx < 0) return null
  const [xi, si] = labels
  const xs: string[] = []
  const ss: string[] = []
  for (const r of rows) {
    const xv = String(r[xi] ?? ''); const sv = String(r[si] ?? '')
    if (!xs.includes(xv)) xs.push(xv)
    if (!ss.includes(sv)) ss.push(sv)
  }
  if (ss.length < 2 || ss.length > 8 || xs.length < 1 || xs.length > 24) return null
  if (xs.length === rows.length || ss.length === rows.length) return null
  const out: Cell[][] = xs.map(xv => {
    const vals = ss.map(sv => {
      const hit = rows.find(r => String(r[xi] ?? '') === xv && String(r[si] ?? '') === sv)
      return hit ? Number(hit[valueIdx] ?? 0) : 0
    })
    return [xv, ...vals, vals.reduce((a, b) => a + b, 0)]
  })
  return { columns: [columns[xi], ...ss, 'Total'], rows: out, x: columns[xi], series: columns[si], y: columns[valueIdx] }
}

/** What to draw when the server did not ask for a particular chart.
 *  Only shapes that read unambiguously get a chart: one number is a KPI;
 *  a label column with one numeric column and 2-24 rows is a bar chart, or a
 *  line when the labels are dates. Two numeric columns whose first is unique
 *  count as label + value. Everything else stays a grid. */
export function autoChart(result: AgentResult): 'kpi' | 'bar' | 'line' | null {
  const { columns, rows } = result
  if (!columns.length || !rows.length) return null
  // A partial result would chart as if it were the whole answer; show the grid.
  if (result.truncated || rows.length < (Number(result.total) || 0)) return null
  if (columns.length === 1 && rows.length === 1 && isNumberish(rows[0][0])) return 'kpi'
  if (groupedBars(result)) return 'bar'
  if (rows.length < 2 || rows.length > 24) return null
  const numeric = columns.map((_, i) => rows.every(r => r[i] == null || isNumberish(r[i])))
  let nameIdx = numeric.findIndex(n => !n)
  // A label column of numeric-looking codes (faculty 1-4, "101", Arabic-Indic
  // digits) is still a label when it names each row once: chart it by column
  // 0, as `chartColumns` already does, instead of falling back to the grid.
  if (nameIdx < 0 && columns.length === 2 && new Set(rows.map(r => r[0])).size === rows.length) nameIdx = 0
  const valueIdx = numeric.findIndex((n, i) => n && i !== nameIdx)
  if (nameIdx < 0 || valueIdx < 0) return null
  const dated = rows.every(r => typeof r[nameIdx] === 'string' && /^\d{4}-\d{2}/.test(r[nameIdx] as string))
  return dated ? 'line' : 'bar'
}

function Kpi({ result, focused }: { result: AgentResult; focused?: boolean }) {
  const v = Number(result.rows[0][0])
  const shown = Number.isInteger(v) ? v.toLocaleString('en-US')
    : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return (
    <div className={focused ? 'dl-kpi dl-cell--evidence' : 'dl-kpi'} data-testid="result-kpi">
      <span className="dl-kpi__label">{result.columns[0].replace(/_/g, ' ')}</span>
      <span className="dl-kpi__value" dir="ltr">{localDigits(shown)}</span>
    </div>
  )
}

export default function ResultView({ results, presentation, focus }: {
  results: AgentResult[]
  presentation?: AgentPresentation | null
  /** A number of the answer to point at (E11). */
  focus?: EvidenceFocus | null
}) {
  const t = useT()
  const [rowsOpen, setRowsOpen] = useState(false)
  // A number in a charted result lives in the rows under the chart: open them.
  useEffect(() => { if (focus) setRowsOpen(true) }, [focus])
  const format = presentation?.format
  const chartable = (format === 'bar' || format === 'line' || format === 'pie') ? format : null
  return (
    <div className="dl-result">
      {results.map((r, i) => {
        const auto = chartable ? null : autoChart(r)
        const drawn = chartable ?? (auto === 'bar' || auto === 'line' ? auto : null)
        const showChart = !!drawn && r.total > 0
        const here = focus && focus.result === i ? focus : null
        return (
          <div key={`${r.step}-${i}`}>
            {auto === 'kpi' && <Kpi result={r} focused={!!here} />}
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
                {rowsOpen && <ResultGrid result={r} focus={here} />}
              </>
            ) : auto === 'kpi' ? null : (
              <ResultGrid result={r} focus={here} />
            )}
          </div>
        )
      })}
    </div>
  )
}
