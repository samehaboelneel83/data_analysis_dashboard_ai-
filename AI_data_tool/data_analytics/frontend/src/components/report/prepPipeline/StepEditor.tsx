import type { CSSProperties } from 'react'
import ExpressionBuilder from '../../expr/ExpressionBuilder'
import type { PrepStep, DatasetColumn, Dataset } from '../../../services/api'
import { joinPairs, writeJoinPairs } from './join'
import { FILTER_FUNC_CATS } from './model'

const selStyle: CSSProperties = {
  fontSize: 11, padding: '3px 6px', background: 'var(--surface)',
  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', minWidth: 0,
}
const inputStyle: CSSProperties = { ...selStyle, width: '100%' }
const rowStyle: CSSProperties = { display: 'flex', gap: 6, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' }
const labelStyle: CSSProperties = { fontSize: 10, color: 'var(--muted)', minWidth: 60 }
//: Small square control for the per-key add/remove buttons, matching the
//: surrounding inputs rather than introducing a new button size.
const iconBtn: CSSProperties = { ...selStyle, cursor: 'pointer', lineHeight: 1, padding: '3px 6px' }

export function ColSelect({ value, onChange, columns, placeholder }:
  { value: string; onChange: (v: string) => void; columns: { name: string }[]; placeholder?: string }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={selStyle}>
      <option value="">{placeholder ?? 'column…'}</option>
      {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
    </select>
  )
}

export function MultiColCheckboxes({ value, onChange, columns }:
  { value: string[]; onChange: (v: string[]) => void; columns: DatasetColumn[] }) {
  const toggle = (name: string) => {
    onChange(value.includes(name) ? value.filter(c => c !== name) : [...value, name])
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
      {columns.map(c => (
        <label key={c.name}
          style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 3,
            padding: '1px 5px', border: '1px solid var(--border)', borderRadius: 4,
            background: value.includes(c.name) ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--surface)' }}>
          <input type="checkbox" checked={value.includes(c.name)} onChange={() => toggle(c.name)}
            style={{ margin: 0 }} />
          {c.name}
        </label>
      ))}
      {columns.length === 0 && <span style={{ fontSize: 10, color: 'var(--muted)' }}>no columns</span>}
    </div>
  )
}

// ── Per-kind mini forms ──────────────────────────────────────────────────────

export function StepEditor({ step, columns, otherDatasets, joinColumns = [], suggestKeys, onChange }: {
  step: PrepStep; columns: DatasetColumn[]; otherDatasets: Dataset[]
  /** Column names of the dataset this step joins to, when it is a join and
      that dataset's columns have loaded. Empty means "not known yet". */
  joinColumns?: string[]
  /** Best known key pair for a candidate target, from the org's relationships. */
  suggestKeys?: (targetId: number) => { left_on: string; right_on: string; source: string } | null
  onChange: (patch: Partial<PrepStep>) => void
}) {
  switch (step.kind) {
    case 'filter_rows':
      return (
        <ExpressionBuilder
          layout="flat" defaultMode="simple" columns={columns}
          functionsCatalog={FILTER_FUNC_CATS}
          value={(step.expression as string) || ''}
          onChange={v => onChange({ expression: v })}
          placeholder="`amount` > 100"
          rows={2}
        />
      )
    case 'sort': {
      const cols = (step.columns as { column: string; dir?: string }[]) || []
      return (
        <div>
          {cols.map((c, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={c.column} columns={columns}
                onChange={v => onChange({ columns: cols.map((x, j) => j === i ? { ...x, column: v } : x) })} />
              <select value={c.dir ?? 'asc'} style={selStyle}
                onChange={e => onChange({ columns: cols.map((x, j) => j === i ? { ...x, dir: e.target.value } : x) })}>
                <option value="asc">ascending</option>
                <option value="desc">descending</option>
              </select>
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                onClick={() => onChange({ columns: cols.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, marginTop: 4 }}
            onClick={() => onChange({ columns: [...cols, { column: '', dir: 'asc' }] })}>+ Add column</button>
        </div>
      )
    }
    case 'dedupe':
    case 'drop_duplicates':
      return (
        <div>
          <div style={labelStyle}>Match on (empty = all columns)</div>
          <MultiColCheckboxes value={(step.subset as string[]) || []} columns={columns}
            onChange={v => onChange({ subset: v })} />
        </div>
      )
    case 'aggregate': {
      const gb = (step.group_by as string[]) || []
      const aggs = (step.aggregations as { column: string; agg: string; as?: string }[]) || []
      return (
        <div>
          <div style={labelStyle}>Group by</div>
          <MultiColCheckboxes value={gb} columns={columns} onChange={v => onChange({ group_by: v })} />
          <div style={{ ...labelStyle, marginTop: 6 }}>Aggregations</div>
          {aggs.map((a, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={a.column} columns={columns}
                onChange={v => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, column: v } : x) })} />
              <select value={a.agg} style={selStyle}
                onChange={e => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, agg: e.target.value } : x) })}>
                {['sum', 'avg', 'min', 'max', 'count', 'median', 'nunique'].map(a2 => <option key={a2} value={a2}>{a2}</option>)}
              </select>
              <input value={a.as ?? ''} placeholder="as…" style={{ ...selStyle, width: 80 }}
                onChange={e => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, as: e.target.value } : x) })} />
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                onClick={() => onChange({ aggregations: aggs.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, marginTop: 4 }}
            onClick={() => onChange({ aggregations: [...aggs, { column: '', agg: 'sum', as: '' }] })}>+ Add aggregation</button>
        </div>
      )
    }
    case 'rename':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <span style={{ fontSize: 11 }}>→</span>
          <input value={(step.to as string) || ''} placeholder="new name" style={{ ...selStyle, flex: 1 }}
            onChange={e => onChange({ to: e.target.value })} />
        </div>
      )
    case 'retype':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <select value={(step.to as string) || 'text'} style={selStyle} onChange={e => onChange({ to: e.target.value })}>
            {['numeric', 'text', 'datetime'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      )
    case 'split':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <input value={(step.delimiter as string) || ''} placeholder="delimiter" style={{ ...selStyle, width: 70 }}
              onChange={e => onChange({ delimiter: e.target.value })} />
          </div>
          <input value={((step.into as string[]) || []).join(', ')} placeholder="new column names, comma-separated"
            style={{ ...inputStyle, marginTop: 4 }}
            onChange={e => onChange({ into: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
        </div>
      )
    case 'trim':
      return (
        <div>
          <div style={labelStyle}>Columns (empty = all text columns)</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
        </div>
      )
    case 'case':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <select value={(step.to as string) || 'upper'} style={selStyle} onChange={e => onChange({ to: e.target.value })}>
            {['upper', 'lower', 'title'].map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      )
    case 'replace':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select value={(step.match as string) || 'exact'} style={selStyle} onChange={e => onChange({ match: e.target.value })}>
              <option value="exact">exact</option>
              <option value="contains">contains</option>
            </select>
          </div>
          <div style={rowStyle}>
            <input value={(step.find as string) ?? ''} placeholder="find" style={{ ...selStyle, flex: 1 }}
              onChange={e => onChange({ find: e.target.value })} />
            <span style={{ fontSize: 11 }}>→</span>
            <input value={(step.replace as string) ?? ''} placeholder="replace with" style={{ ...selStyle, flex: 1 }}
              onChange={e => onChange({ replace: e.target.value })} />
          </div>
        </div>
      )
    case 'remove_columns':
      return <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
        onChange={v => onChange({ columns: v })} />
    case 'drop_nulls':
      return (
        <div>
          <div style={labelStyle}>Columns (empty = any column)</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
        </div>
      )
    case 'partition':
      return (
        <div>
          <div style={rowStyle}>
            <span style={labelStyle}>Column</span>
            <input value={(step.name as string) ?? ''} placeholder="_Partition_" style={{ ...selStyle, flex: 1 }}
              aria-label="Partition column name" onChange={e => onChange({ name: e.target.value })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Training %</span>
            <input type="number" min={1} max={99} value={(step.train_pct as number) ?? 70} style={{ ...selStyle, width: 64 }}
              aria-label="Training percent" onChange={e => onChange({ train_pct: Number(e.target.value) })} />
            <span style={labelStyle}>Seed</span>
            <input type="number" value={(step.seed as number) ?? 42} style={{ ...selStyle, width: 64 }}
              aria-label="Seed" onChange={e => onChange({ seed: Math.round(Number(e.target.value)) })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Keep together</span>
            <ColSelect value={(step.key as string) || ''} columns={columns} placeholder="each row on its own"
              onChange={v => onChange({ key: v || undefined })} />
          </div>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>
            Labels every row Training or Validation from a seeded hash, so a row stays on its side under
            any filter or security rule. Model widgets take it as their Partition and score on Validation.
          </div>
        </div>
      )
    case 'fill_nulls':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select value={(step.method as string) || 'value'} style={selStyle} onChange={e => onChange({ method: e.target.value })}>
              {['value', 'zero', 'mean', 'median', 'mode', 'ffill'].map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          {step.method === 'value' && (
            <input value={(step.value as string) ?? ''} placeholder="fill value" style={{ ...inputStyle, marginTop: 4 }}
              onChange={e => onChange({ value: e.target.value })} />
          )}
        </div>
      )
    case 'join': {
      const pairs = joinPairs(step)
      const hit = typeof step.dataset_id === 'number' ? suggestKeys?.(step.dataset_id) : null
      // Only claim provenance when the keys on screen ARE the suggested ones --
      // an author who overrode them must not be told they came from a model.
      const matched = hit && pairs.length === 1
        && hit.left_on === pairs[0].left && hit.right_on === pairs[0].right ? hit : null
      const setPair = (i: number, patch: Partial<{ left: string; right: string }>) =>
        onChange(writeJoinPairs(pairs.map((p, j) => (j === i ? { ...p, ...patch } : p))))
      return (
        <div>
          <div style={rowStyle}>
            <select value={(step.dataset_id as number) ?? ''} style={selStyle}
              onChange={e => {
                const id = e.target.value ? Number(e.target.value) : null
                // A modelled or inferred relationship already knows how these
                // two tables connect; typing it again is busywork and a chance
                // to get it wrong. Still fully editable afterwards.
                const s2 = id !== null ? suggestKeys?.(id) : null
                onChange({
                  dataset_id: id,
                  ...writeJoinPairs(s2 ? [{ left: s2.left_on, right: s2.right_on }]
                                       : [{ left: '', right: '' }]),
                })
              }}>
              <option value="">dataset…</option>
              {otherDatasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <select value={(step.how as string) || 'left'} style={selStyle} onChange={e => onChange({ how: e.target.value })}>
              {['left', 'right', 'inner', 'full'].map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </div>
          {pairs.map((p, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={p.left} columns={columns} placeholder="this column…"
                onChange={v => setPair(i, { left: v })} />
              <span style={{ fontSize: 11 }}>=</span>
              {joinColumns.length ? (
                <ColSelect value={p.right} columns={joinColumns.map(name => ({ name }))}
                  placeholder="their column…" onChange={v => setPair(i, { right: v })} />
              ) : (
                // No target chosen yet, or its columns are still loading: stay
                // typable rather than presenting an empty, unusable dropdown.
                <input value={p.right} placeholder="their column" style={{ ...selStyle, flex: 1 }}
                  onChange={e => setPair(i, { right: e.target.value })} />
              )}
              {pairs.length > 1 && (
                <button type="button" aria-label={`Remove key ${i + 1}`} style={iconBtn}
                  onClick={() => onChange(writeJoinPairs(pairs.filter((_, j) => j !== i)))}>×</button>
              )}
            </div>
          ))}
          {/* Only offered, never imposed: a one-column join -- the common case --
              looks exactly as it did before. A second key is what keeps the
              grain when one column alone matches too many rows. */}
          <button type="button" style={{ ...iconBtn, width: 'auto', padding: '0 6px', fontSize: 10 }}
            onClick={() => onChange(writeJoinPairs([...pairs, { left: '', right: '' }]))}>
            + add key
          </button>
          {matched && (
            <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
              Keys from {matched.source === 'inferred'
                ? 'a detected relationship — check them'
                : `a ${matched.source} relationship`}.
            </div>
          )}
        </div>
      )
    }
    default:
      return null
  }
}
