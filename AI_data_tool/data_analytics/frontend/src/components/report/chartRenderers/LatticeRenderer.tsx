import type { ComponentType } from 'react'
import type { ChartRendererProps } from './types'
import { MeasuredChart } from '../MeasuredChart'

/** Chart types that take lattice roles — must match LATTICE_TYPES in widget_data.py. */
export const LATTICE_WIDGETS = ['bar', 'line', 'area', 'scatter', 'step', 'dot_plot'] as const

interface Cell { row: string | null; col: string | null; result: any }

/**
 * A lattice: the widget's own chart once per (row value, column value), in a
 * grid with the values as headers. Every cell is drawn by the ordinary renderer
 * for the widget's type, with ONE shared value axis (the server's `domain`)
 * unless the author fixed their own — per-cell axes would draw a small panel
 * exactly like a big one. Legends, data labels and axis titles are dropped
 * inside cells: at panel size they cover the marks, and the headers already
 * name each panel. The measure is named once, under the grid.
 */
export default function LatticeRenderer({ Inner, props }: {
  Inner: ComponentType<ChartRendererProps>
  props: ChartRendererProps
}) {
  const data = props.data
  const rowVals: (string | null)[] = data.row_values?.length ? data.row_values : [null]
  const colVals: (string | null)[] = data.col_values?.length ? data.col_values : [null]
  const cells: Cell[] = data.cells ?? []
  const domain: [number, number] | null = data.domain ?? null
  const own = props.cfg ?? {}
  const cellCfg = {
    ...own,
    ...(domain && own.y_min === undefined && own.y_max === undefined
      ? { y_min: domain[0], y_max: domain[1] } : {}),
    legend: false, data_labels: false, overview_axis: false,
    // Axis titles repeat in every panel and eat the plot at panel size; the
    // headers name the panels and the widget title names the measure.
    x_axis_label: '', y_axis_label: '',
    axis_tick_size: Math.min(Number(own.axis_tick_size) || 9, 9),
  }
  const find = (r: string | null, c: string | null) => cells.find(x => x.row === r && x.col === c)
  const hasRows = rowVals[0] !== null
  const hasCols = colVals[0] !== null
  const head = { fontSize: 10, fontWeight: 600, color: 'var(--muted)', overflow: 'hidden',
    textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, padding: '0 4px' }
  return (
    <div data-testid="lattice" style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div role="grid" aria-label={`${data.inner} by ${[data.rows_by, data.cols_by].filter(Boolean).join(' and ')}`}
        style={{ flex: 1, minHeight: 0, display: 'grid', gap: 4,
          gridTemplateColumns: `${hasRows ? '72px ' : ''}repeat(${colVals.length}, minmax(0, 1fr))`,
          gridTemplateRows: `${hasCols ? 'auto ' : ''}repeat(${rowVals.length}, minmax(0, 1fr))` }}>
        {hasCols && (<>
          {hasRows && <div style={head}>{data.rows_by} \\ {data.cols_by}</div>}
          {colVals.map(c => <div key={`h-${c}`} role="columnheader" dir="auto" title={String(c)}
            style={{ ...head, textAlign: 'center' }}>{c}</div>)}
        </>)}
        {rowVals.map(r => (<RowCells key={`r-${r}`} r={r} />))}
      </div>
      <div data-testid="lattice-caption" style={{ fontSize: 10, color: 'var(--muted)', padding: '2px 4px' }}>
        {[own.y_axis_label || (own.measure ? `${own.aggregation ?? 'sum'}(${own.measure})` : 'count'),
          'by', own.x_axis_label || own.dimension || '—', '· one axis for every panel'].join(' ')}
      </div>
      {data.lattice_truncation?.text && (
        <div data-testid="lattice-truncation" role="note" style={{ fontSize: 10, color: 'var(--muted)', padding: '2px 4px' }}>
          {data.lattice_truncation.text}
        </div>
      )}
    </div>
  )

  function RowCells({ r }: { r: string | null }) {
    return (<>
      {hasRows && <div role="rowheader" dir="auto" title={String(r)}
        style={{ ...head, alignSelf: 'center' }}>{r}</div>}
      {colVals.map(c => {
        const cell = find(r, c)
        const res = cell?.result
        const empty = !res || res.type === 'empty' || !(res.rows?.length)
        return (
          <div key={`${r}|${c}`} role="gridcell" data-testid="lattice-cell"
            aria-label={[r, c].filter(v => v != null).join(' · ')}
            style={{ minWidth: 0, minHeight: 0, border: '1px solid var(--border)', borderRadius: 4, position: 'relative' }}>
            {empty
              ? <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, color: 'var(--muted)' }}>no rows</div>
              : <MeasuredChart>{(w, h) => (
                  <Inner {...props} data={res} rows={res.rows ?? []} cfg={cellCfg} plotW={w} plotH={h} />
                )}</MeasuredChart>}
          </div>
        )
      })}
    </>)
  }
}
