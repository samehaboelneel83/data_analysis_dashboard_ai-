/**
 * A crosstab with hierarchies on rows and columns (hierarchy plan, step 3,
 * 2026-10-10). Each row and column header opens one level at a time (▸/▾).
 * An open group lists its members and then its own total ("Total Egypt");
 * a closed one is a single line with its value. Grand totals close the grid.
 * Every number comes from the server for exactly that group (services/
 * hier_pivot.py), so a subtotal of an average is the group's average.
 * Clicking a number filters the page to that row and column.
 */
import { useMemo } from 'react'
import { useT } from '../../i18n'

interface Node { value: string; children: Node[] }
interface Data {
  row_levels: { column: string }[]
  column_levels: { column: string }[]
  measure: string
  aggregation: string
  row_tree: Node[]
  column_tree: Node[]
  cells: [string[], string[], number | null][]
  truncation?: { applied?: boolean }
  missing_category?: { rows?: number }
  levels_dropped?: { rows?: string[]; columns?: string[] }
}
type Line = { path: string[]; kind: 'node' | 'head' | 'total'; leaf: boolean; open: boolean }

const keyOf = (p: string[]) => JSON.stringify(p)

/** Visible lines for one axis: a closed or leaf node is one line; an open one
 *  is its heading, its members, then its total. */
function lines(nodes: Node[], open: Set<string>, prefix: string[] = []): Line[] {
  return nodes.flatMap(n => {
    const p = [...prefix, n.value]
    const leaf = n.children.length === 0
    const isOpen = !leaf && open.has(keyOf(p))
    if (!isOpen) return [{ path: p, kind: 'node' as const, leaf, open: false }]
    return [{ path: p, kind: 'head' as const, leaf, open: true }, ...lines(n.children, open, p),
            { path: p, kind: 'total' as const, leaf, open: true }]
  })
}

const fmt = (v: number | null | undefined) => v == null ? '' :
  Math.abs(v) >= 100 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })

export default function HierPivot({ data, open, rtl, onToggle, onCellClick }: {
  data: Data
  open: { rows: string[]; cols: string[] }
  rtl?: boolean
  onToggle?: (axis: 'rows' | 'cols', key: string) => void
  onCellClick?: (rowPath: string[], colPath: string[]) => void
}) {
  const t = useT()
  const cells = useMemo(() => new Map(data.cells.map(([r, c, v]) => [keyOf([...r, '\u0001', ...c]), v])), [data.cells])
  const value = (r: string[], c: string[]) => cells.get(keyOf([...r, '\u0001', ...c])) ?? null
  const rowLines = lines(data.row_tree, new Set(open.rows))
  // Columns: heading lines carry no numbers, so only nodes and totals are columns.
  const colLines = data.column_levels.length ? lines(data.column_tree, new Set(open.cols)).filter(l => l.kind !== 'head') : []
  // The header row a column's own label sits on: a node on its level, an open
  // group's total one level below the group (under the group's spanning label).
  const labelDepth = (l: Line) => l.kind === 'total' ? l.path.length : l.path.length - 1
  const colDepth = Math.max(1, ...colLines.map(l => labelDepth(l) + 1))
  const arrow = (isOpen: boolean) => isOpen ? '▾' : rtl ? '◂' : '▸'

  const toggle = (axis: 'rows' | 'cols', path: string[], isOpen: boolean, name: string) => (
    <button type="button" onClick={e => { e.stopPropagation(); onToggle?.(axis, keyOf(path)) }}
      aria-expanded={isOpen} aria-label={isOpen ? t('hp.collapse', { name }) : t('hp.expand', { name })}
      style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--accent)', padding: '0 3px', fontSize: 10 }}>
      {arrow(isOpen)}
    </button>
  )
  const th: React.CSSProperties = { background: 'var(--surface2)', fontWeight: 600,
    padding: '4px 8px', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', textAlign: 'start' }
  const td: React.CSSProperties = { padding: '3px 8px', textAlign: 'end', fontVariantNumeric: 'tabular-nums',
    borderBottom: '1px solid var(--border)', cursor: onCellClick ? 'pointer' : undefined }

  // Column header rows, one per level. A column's label spans down to the last
  // header row; an open group's label spans across its members and its total.
  const headerRows = Array.from({ length: colDepth }, (_, depth) => {
    const out: React.ReactNode[] = []
    colLines.forEach((l, i) => {
      const ld = labelDepth(l)
      if (ld < depth) return
      if (ld === depth) {
        const name = l.path[l.path.length - 1]
        out.push(
          <th key={i} scope="col" rowSpan={colDepth - depth} style={{ ...th, textAlign: 'end', verticalAlign: 'bottom' }}>
            {l.kind === 'total' ? t('hp.total', { name }) : <>{!l.leaf && toggle('cols', l.path, false, name)}<bdi>{name}</bdi></>}
          </th>)
        return
      }
      const group = keyOf(l.path.slice(0, depth + 1))
      const inGroup = (c: Line) => labelDepth(c) > depth && keyOf(c.path.slice(0, depth + 1)) === group
      if (i > 0 && inGroup(colLines[i - 1])) return
      let span = 1
      while (i + span < colLines.length && inGroup(colLines[i + span])) span++
      const name = l.path[depth]
      out.push(
        <th key={i} scope="colgroup" colSpan={span} style={{ ...th, textAlign: 'center', borderInlineStart: '1px solid var(--border)' }}>
          {toggle('cols', l.path.slice(0, depth + 1), true, name)}<bdi>{name}</bdi>
        </th>)
    })
    return out
  })

  return (
    <div dir={rtl ? 'rtl' : undefined} data-testid="hier-pivot" style={{ overflow: 'auto', height: '100%', fontSize: 12 }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
          {headerRows.map((cellsOfRow, depth) => (
            <tr key={depth}>
              {depth === 0 && (
                <th style={{ ...th, verticalAlign: 'bottom' }} scope="col" rowSpan={colDepth}>
                  {data.row_levels.map(l => l.column).join(' › ')}
                </th>
              )}
              {cellsOfRow}
              {depth === 0 && <th style={{ ...th, textAlign: 'end', verticalAlign: 'bottom' }} scope="col" rowSpan={colDepth}>{t('hp.grand')}</th>}
            </tr>
          ))}
        </thead>
        <tbody>
          {rowLines.map((l, i) => {
            const name = l.path[l.path.length - 1]
            const indent = { paddingInlineStart: 8 + (l.path.length - 1) * 16 }
            if (l.kind === 'head') {
              return (
                <tr key={i} data-row-kind="head">
                  <th scope="row" style={{ ...td, ...indent, textAlign: 'start', fontWeight: 600, cursor: undefined }}>
                    {toggle('rows', l.path, true, name)}<bdi>{name}</bdi>
                  </th>
                  <td colSpan={colLines.length + 1} style={{ ...td, cursor: undefined }} />
                </tr>
              )
            }
            const isTotal = l.kind === 'total'
            return (
              <tr key={i} data-row-kind={l.kind} style={isTotal ? { background: 'var(--surface2)', fontWeight: 600 } : undefined}>
                <th scope="row" style={{ ...td, ...indent, textAlign: 'start', fontWeight: isTotal ? 600 : 400, cursor: undefined }}>
                  {isTotal ? t('hp.total', { name }) : <>{!l.leaf && toggle('rows', l.path, false, name)}<bdi>{name}</bdi></>}
                </th>
                {colLines.map((c, j) => (
                  <td key={j} style={{ ...td, fontWeight: c.kind === 'total' ? 600 : undefined }}
                    onClick={() => onCellClick?.(l.path, c.path)}>{fmt(value(l.path, c.path))}</td>
                ))}
                <td style={{ ...td, fontWeight: 600 }} onClick={() => onCellClick?.(l.path, [])}>{fmt(value(l.path, []))}</td>
              </tr>
            )
          })}
          <tr data-row-kind="grand" style={{ background: 'var(--surface2)', fontWeight: 700 }}>
            <th scope="row" style={{ ...td, textAlign: 'start', cursor: undefined }}>{t('hp.grand')}</th>
            {colLines.map((c, j) => (
              <td key={j} style={td} onClick={() => onCellClick?.([], c.path)}>{fmt(value([], c.path))}</td>
            ))}
            <td style={td}>{fmt(value([], []))}</td>
          </tr>
        </tbody>
      </table>
      {data.truncation?.applied && <div style={{ fontSize: 10.5, color: 'var(--muted)', padding: 4 }}>{t('hp.cut')}</div>}
      {[...(data.levels_dropped?.rows ?? []), ...(data.levels_dropped?.columns ?? [])].length > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', padding: 4 }}>
          {t('hp.dropped', { levels: [...(data.levels_dropped?.rows ?? []), ...(data.levels_dropped?.columns ?? [])].join(', ') })}
        </div>
      )}
      {!!data.missing_category?.rows && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', padding: 4 }}>{t('hp.missing', { n: data.missing_category.rows.toLocaleString() })}</div>
      )}
    </div>
  )
}
