import type { CSSProperties } from 'react'
import ExpressionBuilder from '../../expr/ExpressionBuilder'
import type { PrepStep, DatasetColumn, Dataset } from '../../../services/api'
import { joinPairs, writeJoinPairs } from './join'
import { widgetDataApi } from '../../../services/api'
import { FILTER_FUNC_CATS } from './model'

const selStyle: CSSProperties = {
  fontSize: 11, padding: '3px 6px', background: 'var(--surface)',
  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', minWidth: 0,
}
const inputStyle: CSSProperties = { ...selStyle, width: '100%' }
const rowStyle: CSSProperties = { display: 'flex', gap: 6, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' }
const labelStyle: CSSProperties = { fontSize: 11, color: 'var(--muted)', minWidth: 60 }
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
          style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 3,
            padding: '1px 5px', border: '1px solid var(--border)', borderRadius: 4,
            background: value.includes(c.name) ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--surface)' }}>
          <input type="checkbox" checked={value.includes(c.name)} onChange={() => toggle(c.name)}
            style={{ margin: 0 }} />
          {c.name}
        </label>
      ))}
      {columns.length === 0 && <span style={{ fontSize: 11, color: 'var(--muted)' }}>no columns</span>}
    </div>
  )
}

// ── Per-kind mini forms ──────────────────────────────────────────────────────

const numberIn = (value: unknown, fallback: number) => (typeof value === 'number' ? value : fallback)
const hint: CSSProperties = { fontSize: 11, color: 'var(--muted)', marginTop: 4 }

/** One-hot needs its categories up front; this fills them from the data (the
 *  column's values by frequency, under the viewer's own row security). */
function FillCategories({ datasetId, column, onFill }:
  { datasetId?: number; column: string; onFill: (cats: string[]) => void }) {
  if (!datasetId || !column) return null
  return (
    <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
      onClick={() => {
        void widgetDataApi.query(datasetId, { dimension: column, limit: 50 }, [], 'bar')
          .then(r => onFill(((r?.rows as { name?: unknown }[]) || [])
            .map(x => x.name).filter(v => v != null && v !== '').map(String)))
          .catch(() => {})
      }}>Fill from data</button>
  )
}

export function StepEditor({ step, columns, otherDatasets, joinColumns = [], suggestKeys, onChange, datasetId }: {
  step: PrepStep; columns: DatasetColumn[]; otherDatasets: Dataset[]
  /** Column names of the dataset this step joins to, when it is a join and
      that dataset's columns have loaded. Empty means "not known yet". */
  joinColumns?: string[]
  /** Best known key pair for a candidate target, from the org's relationships. */
  suggestKeys?: (targetId: number) => { left_on: string; right_on: string; source: string } | null
  onChange: (patch: Partial<PrepStep>) => void
  /** The dataset being prepared, for steps that read its values (one-hot). */
  datasetId?: number
}) {
  switch (step.kind) {
    case 'outliers': {
      const cols = (step.columns as string[]) || []
      return (
        <div>
          <div style={labelStyle}>Numeric columns</div>
          <MultiColCheckboxes value={cols} columns={columns} onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <select aria-label="Outlier method" value={(step.method as string) || 'iqr'} style={selStyle}
              onChange={e => onChange({ method: e.target.value, k: e.target.value === 'zscore' ? 3 : 1.5 })}>
              <option value="iqr">IQR (quartiles)</option>
              <option value="zscore">z-score</option>
            </select>
            <span style={labelStyle}>Threshold</span>
            <input type="number" step="0.1" min={0.1} aria-label="Outlier threshold" style={{ ...selStyle, width: 64 }}
              value={numberIn(step.k, step.method === 'zscore' ? 3 : 1.5)}
              onChange={e => onChange({ k: Number(e.target.value) })} />
            <select aria-label="Outlier action" value={(step.action as string) || 'flag'} style={selStyle}
              onChange={e => onChange({ action: e.target.value })}>
              <option value="flag">flag in a column</option>
              <option value="remove">remove the rows</option>
              <option value="cap">cap to the limits</option>
            </select>
          </div>
          {(step.action ?? 'flag') === 'flag' && (
            <div style={rowStyle}>
              <span style={labelStyle}>Flag column</span>
              <input value={(step.name as string) ?? '_Outlier_'} style={{ ...selStyle, flex: 1 }}
                aria-label="Flag column name" onChange={e => onChange({ name: e.target.value })} />
            </div>
          )}
          <div style={hint}>
            {step.method === 'zscore'
              ? `Outside ${numberIn(step.k, 3)} standard deviations of the mean.`
              : `Beyond ${numberIn(step.k, 1.5)} × the interquartile range past the quartiles (1.5 is the box-plot rule).`}
          </div>
        </div>
      )
    }
    case 'normalize':
      return (
        <div>
          <div style={labelStyle}>Numeric columns</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <select aria-label="Normalization method" value={(step.method as string) || 'minmax'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="minmax">min-max (0 to 1)</option>
              <option value="zscore">z-score (mean 0, sd 1)</option>
              <option value="log">log (1 + x)</option>
            </select>
            <span style={labelStyle}>New column suffix</span>
            <input value={(step.suffix as string) ?? ''} placeholder="empty = replace" style={{ ...selStyle, width: 110 }}
              aria-label="New column suffix" onChange={e => onChange({ suffix: e.target.value })} />
          </div>
        </div>
      )
    case 'encode': {
      const cats = (step.categories as string[]) || []
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select aria-label="Encoding method" value={(step.method as string) || 'onehot'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="onehot">one-hot (a 0/1 column per value)</option>
              <option value="label">label code (0, 1, 2…)</option>
            </select>
          </div>
          <div style={rowStyle}>
            <input value={cats.join(', ')} style={{ ...selStyle, flex: 1 }} aria-label="Categories"
              placeholder={step.method === 'label' ? 'order (optional), comma-separated' : 'categories, comma-separated'}
              onChange={e => onChange({ categories: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
            <FillCategories datasetId={datasetId} column={(step.column as string) || ''}
              onFill={v => onChange({ categories: v })} />
          </div>
          <label style={{ ...rowStyle, fontSize: 11 }}>
            <input type="checkbox" checked={!!step.drop_original} style={{ margin: 0 }}
              onChange={e => onChange({ drop_original: e.target.checked })} />
            Remove the original column
          </label>
        </div>
      )
    }
    case 'date_parts': {
      const parts = (step.parts as string[]) || []
      const all = ['year', 'quarter', 'month', 'day', 'weekday', 'hour', 'dayofyear', 'week']
      return (
        <div>
          <ColSelect value={(step.column as string) || ''} columns={columns} placeholder="date column…"
            onChange={v => onChange({ column: v })} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {all.map(p => (
              <label key={p} style={{ fontSize: 11, display: 'flex', gap: 3, alignItems: 'center' }}>
                <input type="checkbox" checked={parts.includes(p)} style={{ margin: 0 }}
                  onChange={() => onChange({ parts: parts.includes(p) ? parts.filter(x => x !== p) : [...parts, p] })} />
                {p}
              </label>
            ))}
          </div>
        </div>
      )
    }
    case 'feature_select': {
      const rule = (key: string, label: string, placeholder: string) => (
        <div style={rowStyle}>
          <span style={{ ...labelStyle, minWidth: 150 }}>{label}</span>
          <input type="number" step="any" aria-label={label} placeholder={placeholder} style={{ ...selStyle, width: 80 }}
            value={typeof step[key] === 'number' ? (step[key] as number) : ''}
            onChange={e => onChange({ [key]: e.target.value === '' ? undefined : Number(e.target.value) })} />
        </div>
      )
      return (
        <div>
          {rule('max_missing_pct', 'Drop if empty above (%)', 'e.g. 50')}
          {rule('min_variance', 'Drop if variance at most', 'e.g. 0')}
          {rule('max_correlation', 'Drop if correlation above', 'e.g. 0.95')}
          <div style={{ ...labelStyle, marginTop: 6 }}>Always keep</div>
          <MultiColCheckboxes value={(step.keep as string[]) || []} columns={columns}
            onChange={v => onChange({ keep: v })} />
          <div style={hint}>Of two correlated columns the first is kept. A constant column counts as zero variance.</div>
        </div>
      )
    }
    case 'pca': {
      const cols = (step.columns as string[]) || []
      return (
        <div>
          <div style={labelStyle}>Numeric columns (two or more)</div>
          <MultiColCheckboxes value={cols} columns={columns} onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <span style={labelStyle}>Components</span>
            <input type="number" min={1} max={Math.max(1, Math.min(cols.length, 10))} aria-label="Components"
              value={numberIn(step.n, 2)} style={{ ...selStyle, width: 60 }}
              onChange={e => onChange({ n: Math.round(Number(e.target.value)) })} />
            <span style={labelStyle}>Prefix</span>
            <input value={(step.prefix as string) ?? 'PC'} style={{ ...selStyle, width: 60 }} aria-label="Prefix"
              onChange={e => onChange({ prefix: e.target.value })} />
          </div>
          <div style={hint}>Standardized first; rows with a blank in any chosen column get blank scores.</div>
        </div>
      )
    }
    case 'balance':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} placeholder="class column…"
              onChange={v => onChange({ column: v })} />
            <select aria-label="Balancing method" value={(step.method as string) || 'undersample'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="undersample">under-sample to the smallest class</option>
              <option value="oversample">over-sample to the largest class</option>
            </select>
            <span style={labelStyle}>Seed</span>
            <input type="number" value={numberIn(step.seed, 42)} style={{ ...selStyle, width: 64 }} aria-label="Seed"
              onChange={e => onChange({ seed: Math.round(Number(e.target.value)) })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Only rows where</span>
            <ColSelect value={(step.only_column as string) || ''} columns={columns} placeholder="all rows"
              onChange={v => onChange({ only_column: v || undefined, only_value: v ? (step.only_value ?? 'Training') : undefined })} />
            {!!step.only_column && (
              <>
                <span style={{ fontSize: 11 }}>=</span>
                <input value={String(step.only_value ?? '')} style={{ ...selStyle, width: 100 }} aria-label="Only rows with value"
                  onChange={e => onChange({ only_value: e.target.value })} />
              </>
            )}
          </div>
          <div style={hint}>Balance the TRAINING rows only (e.g. _Partition_ = Training): resampling the
            validation rows too would make the model look better than it is. The other rows are kept as they are.</div>
        </div>
      )
    case 'append':
      return (
        <div>
          <div style={rowStyle}>
            <select aria-label="Dataset to append" value={(step.dataset_id as number) ?? ''} style={selStyle}
              onChange={e => onChange({ dataset_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">dataset…</option>
              {otherDatasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Source column</span>
            <input value={(step.source_column as string) ?? ''} placeholder="optional, e.g. source"
              style={{ ...selStyle, width: 120 }} aria-label="Source column"
              onChange={e => onChange({ source_column: e.target.value || undefined })} />
          </div>
          {!!step.source_column && (
            <div style={rowStyle}>
              <input value={(step.base_label as string) ?? ''} placeholder="label for these rows" style={{ ...selStyle, flex: 1 }}
                aria-label="Label for these rows" onChange={e => onChange({ base_label: e.target.value })} />
              <input value={(step.label as string) ?? ''} placeholder="label for the appended rows" style={{ ...selStyle, flex: 1 }}
                aria-label="Label for the appended rows" onChange={e => onChange({ label: e.target.value })} />
            </div>
          )}
          <div style={hint}>Stacks the other dataset's rows under these, matching columns by name — the same table
            imported from two databases becomes one dataset.</div>
        </div>
      )
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
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => onChange({ columns: cols.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, marginTop: 4 }}
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
          {step.kind === 'dedupe' && (
            <div style={rowStyle}>
              <span style={labelStyle}>Keep</span>
              <select aria-label="Which copy to keep" value={(step.keep as string) || 'first'} style={selStyle}
                onChange={e => onChange({ keep: e.target.value })}>
                <option value="first">the first copy</option>
                <option value="last">the last copy</option>
                <option value="none">no copy (drop them all)</option>
              </select>
            </div>
          )}
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
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => onChange({ aggregations: aggs.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, marginTop: 4 }}
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
            <span style={labelStyle}>Test %</span>
            <input type="number" min={0} max={98} value={(step.test_pct as number) ?? 0} style={{ ...selStyle, width: 64 }}
              aria-label="Test percent" onChange={e => onChange({ test_pct: Number(e.target.value) || undefined })} />
            <span style={labelStyle}>Seed</span>
            <input type="number" value={(step.seed as number) ?? 42} style={{ ...selStyle, width: 64 }}
              aria-label="Seed" onChange={e => onChange({ seed: Math.round(Number(e.target.value)) })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Keep together</span>
            <ColSelect value={(step.key as string) || ''} columns={columns} placeholder="each row on its own"
              onChange={v => onChange({ key: v || undefined })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>Stratify by</span>
            <ColSelect value={(step.stratify as string) || ''} columns={columns} placeholder="no stratification"
              onChange={v => onChange({ stratify: v || undefined })} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
            Labels every row Training, Validation{(step.test_pct as number) ? ' or Test' : ''} from a seeded hash, so a
            row stays on its side under any filter or security rule. Stratifying splits each class in the same
            proportions. Model widgets take it as their Partition and score on Validation.
          </div>
        </div>
      )
    case 'fill_nulls':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select value={(step.method as string) || 'value'} style={selStyle} onChange={e => onChange({ method: e.target.value })}>
              {['value', 'zero', 'mean', 'median', 'mode', 'ffill', 'bfill', 'interpolate'].map(m => <option key={m} value={m}>{m}</option>)}
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
          <button type="button" style={{ ...iconBtn, width: 'auto', padding: '0 6px', fontSize: 11 }}
            onClick={() => onChange(writeJoinPairs([...pairs, { left: '', right: '' }]))}>
            + add key
          </button>
          {matched && (
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
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
