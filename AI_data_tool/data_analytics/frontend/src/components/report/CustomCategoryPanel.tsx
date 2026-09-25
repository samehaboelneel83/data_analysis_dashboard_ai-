import { useState, useEffect, useMemo } from 'react'
import { calcColumnsApi, widgetDataApi } from '../../services/api'
import type { CalcColumn, DatasetColumn } from '../../services/api'
import { groupingExpression, binningExpression, defaultBinEdges } from '../../lib/customCategories'
import type { ValueGroup } from '../../lib/customCategories'

/**
 * Custom categories — SAS's "custom category", Power BI's New group / New bin.
 *
 * Which mode you get follows the source column's type: a category column gets
 * value-grouping, a numeric column gets interval binning. That mirrors both
 * competitors and avoids asking the author a question the data already answers.
 *
 * The result is saved as an ordinary calculated column, so it needs no special
 * handling anywhere downstream. The generated expression is shown before saving
 * because it is the thing that actually runs — hiding it would make a wrong bucket
 * boundary undebuggable.
 */

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  onSaved: (cols: CalcColumn[]) => void
}

const OTHER = 'Other'
/** Values listed for grouping, most common first. More than this is not a
 *  list anyone assigns by hand; the cap is disclosed, not silent. */
export const GROUP_VALUE_LIMIT = 1000

export default function CustomCategoryPanel({ datasetId, columns, onSaved }: Props) {
  const [source, setSource] = useState('')
  const [name, setName] = useState('')
  const [assignments, setAssignments] = useState<Record<string, string>>({})
  const [distinct, setDistinct] = useState<string[]>([])
  /** Rows per value, and whether the value list was capped -- so the panel
   *  can say how much of the data each assignment covers (the geography
   *  check's pattern, applied to groups). */
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [capped, setCapped] = useState<{ shown: number; of: number } | null>(null)
  /**
   * The source column's [min, max], fetched rather than read off the column.
   *
   * `DatasetColumn.stats` is a declared field that nothing ever writes —
   * `stats={}` is passed literally at every creation site — so reading
   * `stats.min/max` gave 0 and 0 for every column in every dataset, no edges,
   * and "Pick at least two bin edges" on every attempt. The panel's own tests
   * missed it because their fixture supplied a `stats` object the application
   * never produces.
   *
   * Fetched through `widgetDataApi` like the distinct values beside it, so
   * row-level security and column rules apply to the range exactly as they do
   * to every other number on screen — a user who may not see the top region's
   * rows must not learn its maximum from a bin edge.
   */
  const [range, setRange] = useState<{ min: number; max: number } | null>(null)
  const [rangeState, setRangeState] = useState<'idle' | 'loading' | 'failed'>('idle')
  const [bins, setBins] = useState(4)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sourceCol = columns.find(c => c.name === source)
  const isNumeric = sourceCol?.dtype === 'numeric'

  // Distinct values only matter for grouping, so numeric columns skip the fetch.
  useEffect(() => {
    if (!source || isNumeric) { setDistinct([]); return }
    let alive = true
    setCapped(null)
    widgetDataApi.query(datasetId, { dimension: source, aggregation: 'count', limit: GROUP_VALUE_LIMIT, sort: 'desc' }, [], 'bar')
      .then((r: any) => {
        if (!alive) return
        const rows = (r.rows ?? []) as { name: unknown; value: number }[]
        setDistinct(rows.map(row => String(row.name)))
        setCounts(Object.fromEntries(rows.map(row => [String(row.name), Number(row.value) || 0])))
        if (r?.truncation?.applied) setCapped({ shown: r.truncation.shown, of: r.truncation.of })
      })
      .catch(() => { if (alive) { setDistinct([]); setCounts({}) } })
    return () => { alive = false }
  }, [datasetId, source, isNumeric])

  useEffect(() => {
    if (!source || !isNumeric) { setRange(null); setRangeState('idle'); return }
    let alive = true
    setRange(null); setRangeState('loading')
    const one = (aggregation: string) =>
      widgetDataApi.query(datasetId, { measure: source, aggregation }, [], 'kpi')
        .then((r: any) => Number(r?.rows?.[0]?.value))
    Promise.all([one('min'), one('max')])
      .then(([min, max]) => {
        if (!alive) return
        if (!Number.isFinite(min) || !Number.isFinite(max)) { setRangeState('failed'); return }
        setRange({ min, max }); setRangeState('idle')
      })
      .catch(() => { if (alive) setRangeState('failed') })
    return () => { alive = false }
  }, [datasetId, source, isNumeric])

  const edges = useMemo(() => {
    if (!isNumeric || !range) return []
    return defaultBinEdges(range.min, range.max, bins)
  }, [isNumeric, range, bins])

  const groups: ValueGroup[] = useMemo(() => {
    const byName: Record<string, string[]> = {}
    for (const [value, group] of Object.entries(assignments)) {
      if (!group.trim()) continue
      ;(byName[group] ??= []).push(value)
    }
    return Object.entries(byName).map(([n, values]) => ({ name: n, values }))
  }, [assignments])

  const expression = isNumeric
    ? binningExpression(source, edges, true)
    : groupingExpression(source, groups, OTHER)

  const create = async () => {
    if (!name.trim()) { setError('The new column needs a name'); return }
    if (!expression) {
      setError(isNumeric ? 'Pick at least two bin edges' : 'Assign at least one value to a group')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const cols = await calcColumnsApi.save(datasetId, { name: name.trim(), expression } as CalcColumn)
      onSaved(cols)
      setName('')
      setAssignments({})
      setSource('')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not create this column')
    } finally {
      setBusy(false)
    }
  }

  const lbl: React.CSSProperties = { fontSize: 10.5, color: 'var(--muted)', display: 'block', marginBottom: 2 }

  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
        letterSpacing: '.06em', marginBottom: 8 }}>
        ⊞ Group &amp; Bin
      </div>
      <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '0 0 8px', lineHeight: 1.45 }}>
        Bucket a column's values into named groups, or a numeric column into intervals.
        Saved as a calculated column, so it works anywhere a column does.
      </p>

      <div style={{ marginBottom: 6 }}>
        <label style={lbl} htmlFor="cc-source">Source column</label>
        <select id="cc-source" value={source} onChange={e => { setSource(e.target.value); setAssignments({}); setError(null) }}
          style={{ width: '100%', fontSize: 11 }}>
          <option value="">— pick a column —</option>
          {columns.filter(c => c.dtype !== 'calculated').map(c => (
            <option key={c.name} value={c.name}>{c.name} ({c.dtype})</option>
          ))}
        </select>
      </div>

      {source && (
        <div style={{ marginBottom: 6 }}>
          <label style={lbl} htmlFor="cc-name">New column name</label>
          <input id="cc-name" value={name} onChange={e => setName(e.target.value)}
            placeholder={isNumeric ? 'e.g. Sales Band' : 'e.g. Continent'}
            style={{ width: '100%', fontSize: 11 }} />
        </div>
      )}

      {/* Numeric -> interval binning */}
      {source && isNumeric && (
        <div style={{ marginBottom: 6 }}>
          <label style={lbl} htmlFor="cc-bins">Number of bins</label>
          <input id="cc-bins" type="number" min={1} max={20} value={bins}
            onChange={e => setBins(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            style={{ width: '100%', fontSize: 11 }} />
          <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3, fontFamily: 'var(--mono)' }}>
            {rangeState === 'loading' ? 'reading the range…'
              : rangeState === 'failed' ? 'could not read this column’s range'
              : range && range.min === range.max
                ? `every value is the same (${range.min}) — nothing to bin`
                : `edges: ${edges.join(', ') || '—'}`}
          </div>
        </div>
      )}

      {source && !isNumeric && distinct.length > 0 && (() => {
        const total = Object.values(counts).reduce((a, b) => a + b, 0)
        const grouped = distinct.filter(v => (assignments[v] ?? '').trim())
          .reduce((a, v) => a + (counts[v] ?? 0), 0)
        const rest = distinct.filter(v => !(assignments[v] ?? '').trim())
        const pct = total ? Math.floor((grouped / total) * 100) : 0
        return (
          <div data-testid="category-coverage" role="status" style={{ marginBottom: 6, fontSize: 10.5 }}>
            <b>{pct}%</b> of rows go to a named group
            {rest.length > 0 && (
              <span style={{ color: 'var(--muted)' }}>
                {' '}· {(total - grouped).toLocaleString()} rows ({rest.length} value{rest.length === 1 ? '' : 's'}) fall to “{OTHER}”
                {rest.length <= 3 ? `: ${rest.join(', ')}` : `, most: ${rest.slice(0, 3).join(', ')}…`}
              </span>
            )}
            {capped && (
              <div style={{ color: 'var(--muted)' }}>
                Listing the {capped.shown.toLocaleString()} most common of {capped.of.toLocaleString()} values; the rest fall to “{OTHER}”.
              </div>
            )}
          </div>
        )
      })()}

      {/* Category -> value grouping */}
      {source && !isNumeric && distinct.length > 0 && (
        <div style={{ marginBottom: 6, maxHeight: 190, overflowY: 'auto',
          border: '1px solid var(--border)', borderRadius: 5, padding: 6 }}>
          {distinct.map(v => (
            <div key={v} style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
              <span style={{ flex: 1, fontSize: 10.5, overflow: 'hidden', textOverflow: 'ellipsis',
                whiteSpace: 'nowrap' }} title={v}>{v}
                {counts[v] != null && <span style={{ color: 'var(--muted)' }}> · {counts[v].toLocaleString()}</span>}
              </span>
              <input aria-label={`Group for ${v}`} value={assignments[v] ?? ''}
                onChange={e => setAssignments(a => ({ ...a, [v]: e.target.value }))}
                placeholder={OTHER} list="cc-group-names"
                style={{ width: 96, fontSize: 11 }} />
            </div>
          ))}
          {/* Typing a group name once makes it offered for every other value. */}
          <datalist id="cc-group-names">
            {groups.map(g => <option key={g.name} value={g.name} />)}
          </datalist>
        </div>
      )}

      {expression && (
        <div style={{ marginBottom: 6, fontSize: 10.5, fontFamily: 'var(--mono)', color: 'var(--muted)',
          background: 'var(--surface2)', borderRadius: 4, padding: '5px 7px', wordBreak: 'break-all' }}>
          {expression}
        </div>
      )}

      {error && <div style={{ marginBottom: 6, fontSize: 10.5, color: '#f87171' }}>{error}</div>}

      {source && (
        <button className="btn btn-primary btn-sm" style={{ fontSize: 11, width: '100%' }}
          disabled={busy} onClick={create}>
          Create
        </button>
      )}
    </div>
  )
}
