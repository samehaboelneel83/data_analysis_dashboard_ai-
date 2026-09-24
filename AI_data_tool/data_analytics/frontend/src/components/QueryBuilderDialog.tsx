import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { dataSourcesApi, queryBuilderApi, type DataSource } from '../services/api'
import QueryCanvas from './QueryCanvas'
import { compileWhere, type SqlConditionRow } from '../lib/sqlWhere'
import { useConfirm } from './ui/ConfirmDialog'
import { useModalDialog } from './ui/useModalDialog'

// D3: the canvas cycles through a fixed subset of AGGS -- the click-badge is
// for the common PowerBuilder-feel case; count_distinct with a custom alias
// stays reachable from the form row below, so nothing is lost.
const CANVAS_AGG_CYCLE = ['', 'sum', 'avg', 'count', 'min', 'max']

interface JoinRow { left_table: string; table: string; left_column: string; right_column: string; how: string }
interface ColRow { table: string; column: string; aggregation: string; alias: string; func: string }
interface FilterRow { table: string; column: string; op: string; value: string }
/** A filter on the AGGREGATE -- what WHERE cannot express, because WHERE runs
 *  before grouping. */
interface HavingRow { table: string; column: string; aggregation: string; op: string; value: string }

const OPS = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'in', 'is_null', 'not_null']
const AGGS = ['', 'sum', 'avg', 'min', 'max', 'count', 'count_distinct']

const label = { display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)',
  textTransform: 'uppercase' as const, letterSpacing: '.06em', marginBottom: 4 }

/**
 * Visual query builder over any DBMS connection: pick tables, joins, columns
 * with aggregations, filters and sort — the SQL compiles server-side against
 * the live schema (identifiers are membership-checked, never escaped) and the
 * statement is shown as it evolves. The result saves as an ordinary dataset,
 * imported or DirectQuery, and from there every widget just works.
 */
export default function QueryBuilderDialog({ ds, onClose, onCreated, existing }: {
  ds: DataSource
  onClose: () => void
  onCreated?: (datasetId: number) => void
  // D1: reopening "Edit query" on a builder-created dataset -- hydrates the
  // canvas from the saved query_model and re-imports update the same dataset
  // (full reload) instead of creating a sibling.
  existing?: { id: number; name: string; query_model: Record<string, unknown> }
}) {
  const confirm = useConfirm()
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [tables, setTables] = useState<string[]>([])
  const [kinds, setKinds] = useState<Record<string, string>>({})
  const [functions, setFunctions] = useState<{ name: string; returns: string }[]>([])
  const [columnsByTable, setColumnsByTable] = useState<Record<string, string[]>>({})
  const [base, setBase] = useState('')
  const [joins, setJoins] = useState<JoinRow[]>([])
  const [cols, setCols] = useState<ColRow[]>([])
  const [filters, setFilters] = useState<FilterRow[]>([])
  const [filtersJoiner, setFiltersJoiner] = useState<'and' | 'or'>('and')
  const [having, setHaving] = useState<HavingRow[]>([])
  // Self-referencing hierarchy: when on, the query walks `hierTable` with a
  // recursive CTE and the CTE (named "hierarchy") becomes the base table.
  const [hierOn, setHierOn] = useState(false)
  const [hierTable, setHierTable] = useState('')
  const [hierId, setHierId] = useState('')
  const [hierParent, setHierParent] = useState('')
  const [sortAlias, setSortAlias] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [limit, setLimit] = useState('10000')
  const [sql, setSql] = useState('')
  const [sqlError, setSqlError] = useState('')
  const [preview, setPreview] = useState<{ columns: string[]; rows: unknown[][] } | null>(null)
  const [dsName, setDsName] = useState('')
  const [mode, setMode] = useState<'import' | 'directquery'>('import')
  const debounce = useRef<ReturnType<typeof setTimeout>>()

  // D2: Design | SQL tabs, PowerBuilder-style. The SQL tab starts read-only,
  // seeded from the live-compiled statement; "Edit SQL manually" unlocks the
  // textarea, and the first actual keystroke commits script mode. From then
  // on the statement is hand-authored truth: Design keeps rendering (so the
  // graph isn't lost) but greys out, and script mode is strictly one-way --
  // there is no path anywhere in this file that parses SQL back into the
  // graph. create() in script mode sends the hand-edited SQL with no model.
  const [tab, setTab] = useState<'design' | 'sql'>('design')
  const [scriptMode, setScriptMode] = useState(false)
  const [manualSql, setManualSql] = useState('')
  const [sqlUnlocked, setSqlUnlocked] = useState(false)
  const displaySql = scriptMode ? manualSql : sql

  useEffect(() => {
    dataSourcesApi.schema(ds.id)
      .then(r => {
        setTables(r.tables.map(t => t.name))
        setKinds(Object.fromEntries(r.tables.map(t => [t.name, t.kind])))
      })
      .catch(() => toast.error('Could not load the connection schema'))
    queryBuilderApi.functions(ds.id).then(setFunctions).catch(() => setFunctions([]))
  }, [ds.id])

  const ensureColumns = useCallback((table: string) => {
    if (!table || columnsByTable[table]) return
    queryBuilderApi.columns(ds.id, table)
      .then(r => setColumnsByTable(p => ({ ...p, [table]: r.map(c => c.name) })))
      .catch(() => setColumnsByTable(p => ({ ...p, [table]: [] })))
  }, [ds.id, columnsByTable])

  // D1: hydrate the canvas from a saved query_model once, on open.
  useEffect(() => {
    if (!existing?.query_model) return
    const m = existing.query_model as {
      table?: string
      joins?: { left_table?: string; table: string; left_column: string; right_column: string; how?: string }[]
      columns?: { table?: string; column: string; aggregation?: string; alias?: string; function?: string }[]
      filters?: { table?: string; column: string; op: string; value?: unknown }[]
      filters_joiner?: 'and' | 'or'
      having?: { table?: string; column: string; aggregation: string; op: string; value?: unknown }[]
      sort?: { alias: string; dir: 'asc' | 'desc' }[]
      limit?: number
    }
    setDsName(existing.name)
    if (m.table) { setBase(m.table); ensureColumns(m.table) }
    const js = (m.joins ?? []).map(j => ({
      left_table: j.left_table || m.table || '', table: j.table,
      left_column: j.left_column, right_column: j.right_column, how: j.how || 'left',
    }))
    setJoins(js)
    js.forEach(j => ensureColumns(j.table))
    setCols((m.columns ?? []).map(c => ({
      table: c.table || m.table || '', column: c.column,
      aggregation: c.aggregation || '', alias: c.alias || '', func: c.function || '',
    })))
    setFilters((m.filters ?? []).map(f => ({
      table: f.table || m.table || '', column: f.column, op: f.op,
      value: Array.isArray(f.value) ? f.value.join(', ') : f.value == null ? '' : String(f.value),
    })))
    if (m.filters_joiner) setFiltersJoiner(m.filters_joiner)
    setHaving((m.having ?? []).map(h => ({
      table: h.table || m.table || '', column: h.column,
      aggregation: h.aggregation, op: h.op,
      value: h.value == null ? '' : String(h.value),
    })))
    if (m.sort?.[0]) { setSortAlias(m.sort[0].alias); setSortDir(m.sort[0].dir) }
    if (m.limit) setLimit(String(m.limit))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing])

  const activeTables = [base, ...joins.map(j => j.table)].filter(Boolean)

  // D3: the canvas checkboxes/badges read and write the SAME `cols` rows the
  // form below edits -- there is no separate canvas-only state, so the two
  // stay in sync by construction rather than by an explicit reconciliation.
  const selectedColumns = new Set(cols.filter(c => c.column).map(c => `${c.table || base}.${c.column}`))
  const aggByColumn = Object.fromEntries(
    cols.filter(c => c.column).map(c => [`${c.table || base}.${c.column}`, c.aggregation]))

  const toggleCanvasColumn = (table: string, column: string) => {
    setCols(p => {
      const idx = p.findIndex(c => (c.table || base) === table && c.column === column)
      if (idx >= 0) return p.filter((_, k) => k !== idx)
      return [...p, { table, column, aggregation: '', alias: '', func: '' }]
    })
  }
  const cycleCanvasAggregation = (table: string, column: string) => {
    setCols(p => p.map(c => (c.table || base) === table && c.column === column
      ? { ...c, aggregation: CANVAS_AGG_CYCLE[(CANVAS_AGG_CYCLE.indexOf(c.aggregation) + 1) % CANVAS_AGG_CYCLE.length] }
      : c))
  }

  const model = useCallback(() => ({
    table: hierOn && hierTable && hierId && hierParent ? 'hierarchy' : base,
    ...(hierOn && hierTable && hierId && hierParent ? {
      hierarchy: { table: hierTable, id_column: hierId, parent_column: hierParent },
    } : {}),
    // A CROSS join is complete without endpoints -- filtering on
    // left_column/right_column would silently drop it from the model while
    // leaving it drawn on the canvas.
    joins: joins.filter(j => j.table && (j.how === 'cross' || (j.left_column && j.right_column)))
      .map(j => j.how === 'cross'
        ? { table: j.table, how: 'cross', left_table: j.left_table || base,
            left_column: '', right_column: '' }
        : { ...j, left_table: j.left_table || base }),
    columns: cols.filter(c => c.column).map(c => ({
      table: c.table || base, column: c.column,
      ...(c.aggregation ? { aggregation: c.aggregation } : {}),
      ...(c.alias ? { alias: c.alias } : {}),
      ...(c.func ? { function: c.func } : {}),
    })),
    filters: filters.filter(f => f.column && (f.op === 'is_null' || f.op === 'not_null' || f.value !== ''))
      .map(f => ({ table: f.table || base, column: f.column, op: f.op,
        value: f.op === 'in' ? f.value.split(',').map(x => x.trim()).filter(Boolean)
          : isNaN(Number(f.value)) || f.value === '' ? f.value : Number(f.value) })),
    ...(filters.length > 1 ? { filters_joiner: filtersJoiner } : {}),
    ...(having.filter(h => h.column && h.value !== '').length ? {
      having: having.filter(h => h.column && h.value !== '').map(h => ({
        table: h.table || base, column: h.column, aggregation: h.aggregation,
        op: h.op,
        value: isNaN(Number(h.value)) || h.value === '' ? h.value : Number(h.value),
      })),
    } : {}),
    ...(sortAlias ? { sort: [{ alias: sortAlias, dir: sortDir }] } : {}),
    limit: Number(limit) || 10000,
  }), [base, joins, cols, filters, filtersJoiner, having, sortAlias, sortDir, limit,
      hierOn, hierTable, hierId, hierParent])

  // live SQL: recompile 500ms after any edit — the statement is the truth of
  // what will run, so it is always on screen
  useEffect(() => {
    if (!base || !cols.some(c => c.column)) { setSql(''); setSqlError(''); return }
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => {
      queryBuilderApi.compile(ds.id, model())
        .then(r => { setSql(r.sql); setSqlError('') })
        .catch(e => { setSql(''); setSqlError(e?.response?.data?.detail || 'Invalid query') })
    }, 500)
    return () => clearTimeout(debounce.current)
  }, [ds.id, model, base, cols])

  const runPreview = () => {
    queryBuilderApi.preview(ds.id, model())
      .then(r => setPreview({ columns: r.columns, rows: r.rows }))
      .catch(e => toast.error(e?.response?.data?.detail || 'Preview failed'))
  }

  const create = async () => {
    if (!displaySql || !dsName.trim()) return
    try {
      // Script mode sends the hand-edited SQL with no model: a script-mode
      // save is not re-editable visually (D1's "Edit query" only appears when
      // query_model is set), which is why the Design tab warns before this.
      const r = await dataSourcesApi.import(
        ds.id, dsName.trim(), undefined, displaySql, mode,
        scriptMode ? undefined : model(), existing?.id)
      toast.success(existing ? `Dataset "${r.name}" updated` : `Dataset "${r.name}" created`)
      onCreated?.(r.id)
      onClose()
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Could not create the dataset')
    }
  }

  // Explicit + confirmed, since it discards whatever was hand-typed.
  const revertToDesign = async () => {
    if (!await confirm({
      title: 'Return to Design?',
      body: 'The SQL is regenerated from the model, and your manual edits are discarded.',
      confirmLabel: 'Return to Design',
    })) return
    setScriptMode(false)
    setManualSql('')
    setSqlUnlocked(false)
  }

  // GROUP BY is derived server-side: any aggregated column makes every plain
  // selected column a grouping key. So "is this query grouped" is exactly
  // "does anything aggregate" -- the client must not keep a second answer.
  const isGrouped = cols.some(c => c.column && c.aggregation)

  // The CTE exposes its source table's columns plus the three it generates,
  // so every picker in the dialog can offer them without a special case.
  const HIER_COLUMNS = ['__level', '__path', '__root_id']
  const effectiveColumns: Record<string, string[]> = hierOn && hierTable
    ? { ...columnsByTable, hierarchy: [...(columnsByTable[hierTable] ?? []), ...HIER_COLUMNS] }
    : columnsByTable

  const colSelect = (table: string, value: string, onChange: (v: string) => void, aria: string) => (
    <select aria-label={aria} value={value} onChange={e => onChange(e.target.value)} style={{ fontSize: 11 }}>
      <option value="">— column —</option>
      {(effectiveColumns[table] ?? []).map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  )

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={existing ? `Edit query — ${ds.name}` : `Query builder — ${ds.name}`}
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 920, maxWidth: '96vw', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <strong style={{ fontSize: 13 }}>{existing ? 'Edit query — ' : 'Query builder — '}{ds.name}</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>

        <div role="tablist" style={{ display: 'flex', gap: 2, marginBottom: 10, borderBottom: '1px solid var(--border)' }}>
          {(['design', 'sql'] as const).map(t => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
              className="btn btn-ghost btn-sm"
              style={{ fontSize: 11, borderRadius: 0, borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
                fontWeight: tab === t ? 700 : 400 }}>
              {t === 'design' ? 'Design' : 'SQL'}
            </button>
          ))}
        </div>

        {tab === 'design' && scriptMode && (
          <div role="alert" style={{ fontSize: 11, color: 'var(--warning, #b45309)', background: 'var(--surface2)',
            border: '1px solid var(--border)', borderRadius: 6, padding: '8px 10px', marginBottom: 10,
            display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Manual SQL — return to Design regenerates from the model and discards manual edits.</span>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={revertToDesign}>Return to Design</button>
          </div>
        )}

        <div style={scriptMode ? { opacity: 0.5, pointerEvents: 'none' } : undefined}
          aria-hidden={scriptMode || tab !== 'design'}
          hidden={tab !== 'design'}>

        {base && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
            <span style={{ ...label, marginBottom: 0 }}>Diagram</span>
            <select aria-label="Add table to canvas" value=""
              onChange={e => {
                const t = e.target.value
                if (!t) return
                ensureColumns(t)
                setJoins(p => [...p, { left_table: base, table: t, left_column: '', right_column: '', how: 'left' }])
              }}
              style={{ fontSize: 11 }}>
              <option value="">+ add table…</option>
              {tables.filter(t => t !== base && !joins.some(j => j.table === t)).map(t =>
                <option key={t} value={t}>{t}</option>)}
            </select>
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>
              Click a column, then a column in another table, to draw a join.
            </span>
          </div>
        )}
        {base && (
          <QueryCanvas
            tables={activeTables}
            kinds={kinds}
            columnsByTable={effectiveColumns}
            joins={joins.filter(j => j.table && j.left_column && j.right_column)
              .map(j => ({ ...j, left_table: j.left_table || base }))}
            onAddJoin={j => {
              ensureColumns(j.table)
              // the completed join replaces any keyless placeholder row that put
              // the table on the canvas in the first place
              setJoins(p => [...p.filter(x => !(x.table === j.table && !x.left_column && !x.right_column)), j])
            }}
            onCycleJoin={i => setJoins(p => {
              const real = p.filter(j => j.table && j.left_column && j.right_column)
              const target = real[i]
              const order = ['left', 'inner', 'right']
              const next = order[(order.indexOf(target.how) + 1) % order.length]
              return p.map(j => j === target ? { ...j, how: next } : j)
            })}
            onRemoveJoin={i => setJoins(p => {
              const real = p.filter(j => j.table && j.left_column && j.right_column)
              return p.filter(j => j !== real[i])
            })}
            onSetJoinType={(i, how) => setJoins(p => {
              const real = p.filter(j => j.table && j.left_column && j.right_column)
              const target = real[i]
              return p.map(j => j === target ? { ...j, how } : j)
            })}
            onCloseTable={t => {
              // The table AND everything that referenced it: its joins, its
              // output columns and its filters. Leaving those behind would
              // compile to a query selecting from a table it no longer joins.
              setJoins(p => p.filter(j => j.table !== t && j.left_table !== t))
              setCols(p => p.filter(c => (c.table || base) !== t))
              setFilters(p => p.filter(f => (f.table || base) !== t))
            }}
            selectedColumns={selectedColumns}
            aggByColumn={aggByColumn}
            onToggleColumn={toggleCanvasColumn}
            onCycleAggregation={cycleCanvasAggregation} />
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label style={label}>Base table</label>
            <select aria-label="Base table" value={base}
              onChange={e => { setBase(e.target.value); ensureColumns(e.target.value) }}
              style={{ width: '100%', fontSize: 12 }}>
              <option value="">— choose —</option>
              {tables.map(t => <option key={t} value={t}>{t}</option>)}
            </select>

            {/* Self-referencing hierarchy. Turning this on rewrites the query
                to walk the chosen table with a recursive CTE and adds
                __level / __path / __root_id -- the three columns an
                (id, parent_id) table cannot answer about itself. */}
            <div data-testid="qb-hierarchy" style={{ marginTop: 12 }}>
              <label style={{ ...label, display: 'flex', alignItems: 'center', gap: 6 }}>
                <input type="checkbox" aria-label="Walk a self-referencing hierarchy"
                  checked={hierOn}
                  onChange={e => {
                    const on = e.target.checked
                    setHierOn(on)
                    // The CTE becomes the base table; turning it off restores
                    // the source table so the query stays valid either way.
                    if (on) { setHierTable(base || ''); ensureColumns(base) }
                    else if (hierTable) setBase(hierTable)
                  }} />
                Walk a hierarchy (id → parent)
              </label>
              {hierOn && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                  <select aria-label="Hierarchy table" value={hierTable}
                    onChange={e => { setHierTable(e.target.value); ensureColumns(e.target.value) }}
                    style={{ fontSize: 11 }}>
                    <option value="">— table —</option>
                    {tables.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  {colSelect(hierTable, hierId, setHierId, 'Hierarchy id column')}
                  {colSelect(hierTable, hierParent, setHierParent, 'Hierarchy parent column')}
                  <span style={{ fontSize: 10, color: 'var(--muted)', alignSelf: 'center' }}>
                    adds __level, __path, __root_id
                  </span>
                </div>
              )}
            </div>

            <label style={{ ...label, marginTop: 12 }}>Joins</label>
            {joins.map((j, i) => (
              <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
                <select aria-label={`Join table ${i + 1}`} value={j.table}
                  onChange={e => { const t = e.target.value; ensureColumns(t); setJoins(p => p.map((x, k) => k === i ? { ...x, table: t } : x)) }}
                  style={{ fontSize: 11 }}>
                  <option value="">— table —</option>
                  {tables.filter(t => t !== base).map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <select aria-label={`Join type ${i + 1}`} value={j.how}
                  onChange={e => setJoins(p => p.map((x, k) => k === i ? { ...x, how: e.target.value } : x))} style={{ fontSize: 11 }}>
                  <option value="left">left</option><option value="inner">inner</option><option value="right">right</option>
                </select>
                {colSelect(base, j.left_column, v => setJoins(p => p.map((x, k) => k === i ? { ...x, left_column: v } : x)), `Join ${i + 1} base key`)}
                <span style={{ fontSize: 11, alignSelf: 'center' }}>=</span>
                {colSelect(j.table, j.right_column, v => setJoins(p => p.map((x, k) => k === i ? { ...x, right_column: v } : x)), `Join ${i + 1} joined key`)}
                <button aria-label={`Remove join ${i + 1}`} onClick={() => setJoins(p => p.filter((_, k) => k !== i))}
                  style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
              </div>
            ))}
            <button className="btn" style={{ fontSize: 10 }} disabled={!base} title={!base ? 'Choose a base table first' : undefined}
              onClick={() => setJoins(p => [...p, { left_table: base, table: '', left_column: '', right_column: '', how: 'left' }])}>+ Add join</button>

            <label style={{ ...label, marginTop: 12 }}>Columns</label>
            {cols.map((c, i) => (
              <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
                <select aria-label={`Column table ${i + 1}`} value={c.table || base}
                  onChange={e => setCols(p => p.map((x, k) => k === i ? { ...x, table: e.target.value, column: '' } : x))} style={{ fontSize: 11 }}>
                  {activeTables.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                {colSelect(c.table || base, c.column, v => setCols(p => p.map((x, k) => k === i ? { ...x, column: v } : x)), `Column ${i + 1}`)}
                {functions.length > 0 && (
                  <select aria-label={`Function ${i + 1}`} value={c.func}
                    onChange={e => setCols(p => p.map((x, k) => k === i ? { ...x, func: e.target.value } : x))} style={{ fontSize: 11 }}>
                    <option value="">— ƒ —</option>
                    {functions.map(f => <option key={f.name} value={f.name}>{f.name}</option>)}
                  </select>
                )}
                <select aria-label={`Aggregation ${i + 1}`} value={c.aggregation}
                  onChange={e => setCols(p => p.map((x, k) => k === i ? { ...x, aggregation: e.target.value } : x))} style={{ fontSize: 11 }}>
                  {AGGS.map(a => <option key={a} value={a}>{a || '— raw —'}</option>)}
                </select>
                <input aria-label={`Alias ${i + 1}`} value={c.alias} placeholder="alias"
                  onChange={e => setCols(p => p.map((x, k) => k === i ? { ...x, alias: e.target.value } : x))}
                  style={{ fontSize: 11, width: 80 }} />
                <button aria-label={`Remove column ${i + 1}`} onClick={() => setCols(p => p.filter((_, k) => k !== i))}
                  style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
              </div>
            ))}
            <button className="btn" style={{ fontSize: 10 }} disabled={!base} title={!base ? 'Choose a base table first' : undefined}
              onClick={() => setCols(p => [...p, { table: base, column: '', aggregation: '', alias: '', func: '' }])}>+ Add column</button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
              <label style={{ ...label, marginBottom: 0 }}>Filters</label>
              {filters.length > 1 && (
                <select aria-label="Filters match" value={filtersJoiner}
                  onChange={e => setFiltersJoiner(e.target.value as 'and' | 'or')} style={{ fontSize: 10 }}>
                  <option value="and">Match ALL (AND)</option>
                  <option value="or">Match ANY (OR)</option>
                </select>
              )}
            </div>
            {filters.map((f, i) => (
              <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
                <select aria-label={`Filter table ${i + 1}`} value={f.table || base}
                  onChange={e => setFilters(p => p.map((x, k) => k === i ? { ...x, table: e.target.value, column: '' } : x))} style={{ fontSize: 11 }}>
                  {activeTables.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                {colSelect(f.table || base, f.column, v => setFilters(p => p.map((x, k) => k === i ? { ...x, column: v } : x)), `Filter column ${i + 1}`)}
                <select aria-label={`Filter op ${i + 1}`} value={f.op}
                  onChange={e => setFilters(p => p.map((x, k) => k === i ? { ...x, op: e.target.value } : x))} style={{ fontSize: 11 }}>
                  {OPS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                {f.op !== 'is_null' && f.op !== 'not_null' && (
                  <input aria-label={`Filter value ${i + 1}`} value={f.value}
                    placeholder={f.op === 'in' ? 'a, b, c' : 'value'}
                    onChange={e => setFilters(p => p.map((x, k) => k === i ? { ...x, value: e.target.value } : x))}
                    style={{ fontSize: 11, width: 100 }} />
                )}
                <button aria-label={`Remove filter ${i + 1}`} onClick={() => setFilters(p => p.filter((_, k) => k !== i))}
                  style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
              </div>
            ))}
            <button className="btn" style={{ fontSize: 10 }} disabled={!base} title={!base ? 'Choose a base table first' : undefined}
              onClick={() => setFilters(p => [...p, { table: base, column: '', op: 'eq', value: '' }])}>+ Add filter</button>
            {filters.some(f => f.column) && (
              <div data-testid="qb-where-preview" style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>
                WHERE {compileWhere(
                  filters.map((f): SqlConditionRow => ({ table: f.table, column: f.column, op: f.op as SqlConditionRow['op'], value: f.value })),
                  filtersJoiner)}
              </div>
            )}

            {/* HAVING: only offered once something groups. WHERE runs BEFORE
                grouping, so "regions whose total exceeds 1000" cannot be said
                there -- and offering the control when nothing aggregates would
                be a form whose every value the compiler rejects. */}
            {isGrouped && (
              <div data-testid="qb-having" style={{ marginTop: 12 }}>
                <label style={label}>Having (filters the totals)</label>
                {having.map((h, i) => (
                  <div key={i} style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'center' }}>
                    <select aria-label={`Having aggregation ${i + 1}`} value={h.aggregation}
                      onChange={e => setHaving(p => p.map((x, k) => k === i ? { ...x, aggregation: e.target.value } : x))}
                      style={{ fontSize: 11 }}>
                      {AGGS.filter(Boolean).map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    {colSelect(h.table || base, h.column,
                      v => setHaving(p => p.map((x, k) => k === i ? { ...x, column: v } : x)),
                      `Having column ${i + 1}`)}
                    <select aria-label={`Having operator ${i + 1}`} value={h.op}
                      onChange={e => setHaving(p => p.map((x, k) => k === i ? { ...x, op: e.target.value } : x))}
                      style={{ fontSize: 11 }}>
                      {['gt', 'gte', 'lt', 'lte', 'eq', 'ne'].map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                    <input aria-label={`Having value ${i + 1}`} value={h.value}
                      onChange={e => setHaving(p => p.map((x, k) => k === i ? { ...x, value: e.target.value } : x))}
                      placeholder="e.g. 1000" style={{ fontSize: 11, width: 80 }} />
                    <button aria-label={`Remove having ${i + 1}`}
                      onClick={() => setHaving(p => p.filter((_, k) => k !== i))}
                      style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
                  </div>
                ))}
                <button className="btn" style={{ fontSize: 10 }}
                  onClick={() => setHaving(p => [...p, { table: base, column: '', aggregation: 'sum', op: 'gt', value: '' }])}>
                  + Add having
                </button>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'flex-end' }}>
              <div>
                <label style={label}>Sort by alias</label>
                <input aria-label="Sort alias" value={sortAlias} onChange={e => setSortAlias(e.target.value)}
                  placeholder="e.g. total" style={{ fontSize: 11, width: 100 }} />
              </div>
              <select aria-label="Sort direction" value={sortDir} onChange={e => setSortDir(e.target.value as 'asc' | 'desc')} style={{ fontSize: 11 }}>
                <option value="desc">desc</option><option value="asc">asc</option>
              </select>
              <div>
                <label style={label}>Limit</label>
                <input aria-label="Row limit" type="number" value={limit} onChange={e => setLimit(e.target.value)}
                  style={{ fontSize: 11, width: 90 }} />
              </div>
            </div>
          </div>

          <div>
            <label style={label}>SQL (compiled live, identifiers schema-checked)</label>
            <pre data-testid="qb-sql" style={{ fontSize: 11, background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: 6, padding: 10, whiteSpace: 'pre-wrap', minHeight: 80, margin: 0 }}>
              {sqlError ? '' : sql || '— pick a base table and columns —'}
            </pre>
            {sqlError && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{sqlError}</div>}
            {functions.length > 0 && (
              <details style={{ marginTop: 8 }}>
                <summary style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', cursor: 'pointer' }}>
                  ƒ Database functions ({functions.length})
                </summary>
                <ul style={{ listStyle: 'none', fontSize: 10, color: 'var(--muted)', maxHeight: 100, overflowY: 'auto', marginTop: 4 }}>
                  {functions.map(f => <li key={f.name}>{f.name}() → {f.returns}</li>)}
                </ul>
              </details>
            )}

            <div style={{ display: 'flex', gap: 8, margin: '10px 0' }}>
              <button className="btn" style={{ fontSize: 11 }} disabled={!sql} title={!sql ? 'Add a table and at least one column to preview' : undefined} onClick={runPreview}>Preview data</button>
            </div>
            {preview && (
              <div style={{ overflow: 'auto', maxHeight: 220, border: '1px solid var(--border)', borderRadius: 6 }}>
                <table style={{ fontSize: 11 }}>
                  <thead><tr>{preview.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>
                    {preview.rows.slice(0, 50).map((r, i) => (
                      <tr key={i}>{r.map((v, j) => <td key={j}>{v == null ? '—' : String(v)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
        </div>

        {tab === 'sql' && (
          <div>
            <label style={label}>
              SQL {scriptMode ? '(hand-edited — SQL edited by hand — Design view no longer reflects it)' : '(compiled live, identifiers schema-checked)'}
            </label>
            <textarea aria-label="SQL editor" value={displaySql} readOnly={!sqlUnlocked}
              onChange={e => { setManualSql(e.target.value); setScriptMode(true) }}
              style={{ width: '100%', fontSize: 11, fontFamily: 'var(--mono, monospace)',
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
                padding: 10, minHeight: 160, boxSizing: 'border-box',
                color: sqlUnlocked ? 'var(--text)' : 'var(--muted)' }} />
            {sqlError && !scriptMode && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{sqlError}</div>}
            {!sqlUnlocked && (
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, marginTop: 8 }}
                onClick={() => setSqlUnlocked(true)}>Edit SQL manually</button>
            )}
            {scriptMode && (
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
                This dataset will save from the SQL above only — the design is no longer editable visually once saved this way.{' '}
                <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={revertToDesign}>Return to Design</button>
              </div>
            )}
          </div>
        )}

        <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10 }}>
          <label style={label}>Save as dataset</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input aria-label="Dataset name" value={dsName} onChange={e => setDsName(e.target.value)}
              placeholder="e.g. Revenue by segment" style={{ fontSize: 12, flex: 1, minWidth: 160 }} />
            <select aria-label="Dataset mode" value={mode} onChange={e => setMode(e.target.value as 'import' | 'directquery')} style={{ fontSize: 12 }}>
              <option value="import">Import (materialise now)</option>
              <option value="directquery">DirectQuery (live)</option>
            </select>
            <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={!displaySql || !dsName.trim()} title={!displaySql ? 'Build the query first: a table and at least one column' : !dsName.trim() ? 'Name the dataset first' : undefined}
              onClick={() => void create()}>{existing ? 'Save changes' : 'Create dataset'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
